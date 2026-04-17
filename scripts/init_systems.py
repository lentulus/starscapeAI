#!/usr/bin/env python3
"""Initialise star systems on demand, working outward from Sol (0, 0, 0).

For each batch of --batch-size systems (ordered by distance from origin):
  1a. Velocity    — generate synthetic velocity if none in SystemVelocities
  1b. Spectral    — fill NULL spectral types; add companion stars if eligible
  1c. Metrics     — compute stellar physics if absent from DistinctStarsExtended
  1d. Star orbits — generate Keplerian orbits for companion stars if absent
  1e. Bodies      — generate planets/moons/belts; record in BodyGenerationStatus

A system is complete when every one of its stars has a BodyGenerationStatus row
with error = NULL.  Incomplete systems re-enter the queue on the next run.

Resume safety
-------------
Every step uses INSERT OR IGNORE / INSERT OR REPLACE.  The batch query
filters by BodyGenerationStatus so completed systems are naturally skipped;
no OFFSET is needed.

Stop flags
----------
--max-minutes N   stop after N elapsed minutes (wall-clock from script start)
--stop-at  HH:MM  stop at a specific wall-clock time today (24-hour, local time)
Either or both may be supplied; whichever triggers first wins.

NOTE: DistinctStarsExtended.age is in YEARS (t ~ 1e10 * M/L).
      generate_system() expects age_gyr.  Conversion: age_yr / 1e9.
      The existing generate_planets_wbh.py passes age_yr directly as age_gyr —
      this is a known bug in that script; do not replicate it here.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import KDTree

# ---------------------------------------------------------------------------
# Import generate_system and its INSERT helpers from the sibling script.
# That script is not a package module, so we insert the scripts directory
# into sys.path before importing.  Module-level code in generate_planets_wbh
# is limited to constants, function defs, and basicConfig (no-op here).
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import generate_planets_wbh as _gpw  # noqa: E402 (must follow sys.path insert)

from starscape5.metrics import MetricsError, compute_metrics
from starscape5.orbits import (
    OrbitsError,
    enforce_stability,
    generate_orbit,
    hill_radius_au,
    identify_primary,
)
from starscape5.spectral import (
    ci_from_absmag,
    companion_absmag,
    format_spectral,
    should_create_multiple,
)
from starscape5.velocities import generate_velocity

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
DEFAULT_BATCH = 1000
DEFAULT_MAX_MINUTES: float | None = None   # no default; at least one stop flag required

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column names that may be absent from generate_system() output and must
# default to NULL in the Bodies INSERT.
# ---------------------------------------------------------------------------
_NEW_COLS: tuple[str, ...] = (
    "atm_type", "atm_pressure_atm", "atm_composition",
    "surface_temp_k", "hydrosphere",
    "albedo", "greenhouse_factor",
    "atm_code", "pressure_bar", "ppo_bar", "gases",
    "taint_type_1", "taint_severity_1", "taint_persistence_1",
    "taint_type_2", "taint_severity_2", "taint_persistence_2",
    "taint_type_3", "taint_severity_3", "taint_persistence_3",
    "hydro_code", "hydro_pct", "mean_temp_k", "high_temp_k", "low_temp_k",
    "sidereal_day_hours", "solar_day_hours", "axial_tilt_deg", "tidal_lock_status",
    "seismic_residual", "seismic_tidal", "seismic_heating", "seismic_total",
    "tectonic_plates", "biomass_rating",
    "biocomplexity_rating", "native_sophants", "biodiversity_rating",
    "compatibility_rating", "resource_rating",
    "moon_PD", "hill_PD", "roche_PD",
)

# ---------------------------------------------------------------------------
# Batch selection query
# ---------------------------------------------------------------------------
# Uses the pre-computed, indexed dist2_mpc2 column on IndexedIntegerDistinctSystems
# for O(log n + batch_size) cursor-based pagination:
#
#   - dist2_mpc2 > :last_dist2  skips all systems already committed in prior
#     batches, so no OFFSET and no re-scan of completed work.
#   - EXISTS short-circuits on the first unprocessed star.
#   - ORDER BY dist2_mpc2 uses the idx_systems_dist2 index — no sort needed.
#
# The caller updates the InitCheckpoint('last_dist2_mpc2') after every commit
# so the next run (or the next batch in the same run) resumes at the frontier.
#
# Prerequisite: dist2_mpc2 column must be populated once before first use:
#   ALTER TABLE IndexedIntegerDistinctSystems ADD COLUMN dist2_mpc2 INTEGER;
#   UPDATE      IndexedIntegerDistinctSystems SET dist2_mpc2 = x*x + y*y + z*z;
# ---------------------------------------------------------------------------
_BATCH_QUERY = """
SELECT sys.system_id,
       sys.x, sys.y, sys.z,
       sys.dist2_mpc2
FROM   IndexedIntegerDistinctSystems sys
LEFT JOIN SystemGenerationStatus sgs ON sgs.system_id = sys.system_id
WHERE  sys.dist2_mpc2 > :last_dist2
  AND  sgs.system_id IS NULL
ORDER  BY sys.dist2_mpc2
LIMIT  :batch_size
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_batch_stars(
    conn: sqlite3.Connection,
    system_ids: list[int],
) -> dict[int, list[dict]]:
    """
    One query: fetch star + metrics data for every system in the batch.
    Returns {system_id: [star_dict, ...]} ordered by star_id within each system.
    Replaces the per-system SELECT inside _init_system().
    """
    ph   = ",".join("?" * len(system_ids))
    rows = conn.execute(
        f"""
        SELECT i.system_id, i.star_id, i.ci, i.absmag, i.spectral,
               e.mass, e.luminosity, e.radius, e.age, e.temperature
        FROM   IndexedIntegerDistinctStars i
        LEFT JOIN DistinctStarsExtended e ON e.star_id = i.star_id
        WHERE  i.system_id IN ({ph})
        ORDER  BY i.system_id, i.star_id
        """,
        system_ids,
    ).fetchall()

    result: dict[int, list[dict]] = {}
    for row in rows:
        star = {
            "star_id":     row[1], "ci":          row[2],
            "absmag":      row[3], "spectral":     row[4],
            "mass":        row[5], "luminosity":   row[6],
            "radius":      row[7], "age_yr":       row[8],
            "temperature": row[9],
        }
        result.setdefault(row[0], []).append(star)
    return result


def _fetch_batch_state(
    conn: sqlite3.Connection,
    system_ids: list[int],
    star_ids: list[int],
) -> tuple[set[int], set[int], set[int]]:
    """
    Three queries replacing all per-system/per-star read queries in _init_system().

    Returns:
        has_velocity  — system_ids already in SystemVelocities
        bgs_done      — star_ids with BodyGenerationStatus.error IS NULL (success)
        has_orbit     — star_ids appearing as companion or primary in StarOrbits
    """
    sph = ",".join("?" * len(system_ids))
    has_velocity: set[int] = {
        r[0] for r in conn.execute(
            f"SELECT system_id FROM SystemVelocities WHERE system_id IN ({sph})",
            system_ids,
        ).fetchall()
    }

    if not star_ids:
        return has_velocity, set(), set()

    stph = ",".join("?" * len(star_ids))
    bgs_done: set[int] = {
        r[0] for r in conn.execute(
            f"SELECT star_id FROM BodyGenerationStatus"
            f" WHERE star_id IN ({stph}) AND error IS NULL",
            star_ids,
        ).fetchall()
    }
    has_orbit: set[int] = {
        r[0] for r in conn.execute(
            f"SELECT star_id       FROM StarOrbits WHERE star_id       IN ({stph})"
            f" UNION "
            f"SELECT primary_star_id FROM StarOrbits WHERE primary_star_id IN ({stph})",
            star_ids + star_ids,
        ).fetchall()
    }

    return has_velocity, bgs_done, has_orbit


def _parse_deadline(max_minutes: float | None, stop_at: str | None) -> float:
    """Return the earliest deadline as a monotonic clock value."""
    deadlines: list[float] = []
    if max_minutes is not None:
        deadlines.append(time.monotonic() + max_minutes * 60.0)
    if stop_at is not None:
        t = datetime.datetime.strptime(stop_at, "%H:%M").time()
        now = datetime.datetime.now()
        target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        deadlines.append(time.monotonic() + (target - now).total_seconds())
    return min(deadlines) if deadlines else float("inf")


def _load_system_positions(conn: sqlite3.Connection) -> tuple[np.ndarray, dict[int, int]]:
    """Load all system positions into a numpy array + lookup dict for KDTree."""
    rows = conn.execute(
        "SELECT system_id, x, y, z FROM IndexedIntegerDistinctSystems"
    ).fetchall()
    positions = np.array([[r[1], r[2], r[3]] for r in rows], dtype=float)
    system_id_to_idx = {r[0]: i for i, r in enumerate(rows)}
    return positions, system_id_to_idx


def _nearest_dist_mpc(
    system_id: int,
    system_id_to_idx: dict[int, int],
    positions: np.ndarray,
    tree: KDTree,
    default_au: float = 100_000.0,
) -> float:
    """Distance in mpc to the nearest other system; default if not found."""
    idx = system_id_to_idx.get(system_id)
    if idx is None:
        return default_au
    point = positions[idx]
    dists, _ = tree.query(point, k=min(2, len(positions)))
    if len(dists) < 2:
        return default_au
    return float(dists[1]) if dists[1] > 0 else default_au


def _system_binary_constraints(
    conn: sqlite3.Connection,
    system_id: int,
) -> tuple[dict[int, float], set[int], dict[int, tuple[float, float]]]:
    """
    Return binary constraints for a system after orbit generation.

    binary_cap[star_id]   = max stable planet orbit AU (companion SMA × 0.3)
    binary_stars          = set of all star_ids involved in any binary
    binary_plane[star_id] = (inclination_rad, lan_rad) from StarOrbits
    """
    binary_cap: dict[int, float] = {}
    binary_stars: set[int] = set()
    binary_plane: dict[int, tuple[float, float]] = {}

    rows = conn.execute(
        """
        SELECT so.star_id, so.primary_star_id, so.semi_major_axis,
               so.inclination, so.longitude_ascending_node
        FROM   StarOrbits so
        JOIN   IndexedIntegerDistinctStars i ON i.star_id = so.star_id
        WHERE  i.system_id = ?
        """,
        (system_id,),
    ).fetchall()

    for o in rows:
        cap     = float(o[2]) * 0.3
        sid     = o[0]
        primary = o[1]
        plane   = (float(o[3]), float(o[4]))
        if sid not in binary_cap or cap < binary_cap[sid]:
            binary_cap[sid] = cap
        if primary not in binary_cap or cap < binary_cap[primary]:
            binary_cap[primary] = cap
        binary_stars.add(sid)
        binary_stars.add(primary)
        binary_plane[sid]     = plane
        binary_plane[primary] = plane

    return binary_cap, binary_stars, binary_plane


def _insert_bodies(
    conn: sqlite3.Connection,
    star_id: int,
    bodies: list[dict],
) -> int:
    """
    Insert Bodies + BeltProfile rows for one star.  Resolves moon parent
    links.  Returns the count of rows inserted.
    """
    idx_to_body_id: dict[int, int] = {}
    for i, b in enumerate(bodies):
        parent_idx   = b.pop("_parent_idx",   None)
        mutable      = b.pop("_mutable",       None)
        belt_profile = b.pop("_belt_profile",  None)
        b.pop("_is_binary", None)

        insert_row = {k: v for k, v in b.items() if not k.startswith("_")}

        # Merge ex-BodyMutable fields
        if mutable is not None:
            mutable.pop("_t_eq_k", None)
            mutable.pop("_v_esc",  None)
            mutable.pop("_sg",     None)
            insert_row.update(mutable)

        for col in _NEW_COLS:
            insert_row.setdefault(col, None)

        if parent_idx is not None:
            insert_row["orbit_body_id"] = idx_to_body_id.get(parent_idx)
            insert_row["orbit_star_id"] = None

        cur = conn.execute(_gpw._INSERT_SQL, insert_row)
        idx_to_body_id[i] = cur.lastrowid

        if belt_profile is not None:
            conn.execute(
                _gpw._BELT_PROFILE_INSERT_SQL,
                {"body_id": cur.lastrowid, **belt_profile},
            )

    return len(bodies)


# ---------------------------------------------------------------------------
# Per-system initialisation
# ---------------------------------------------------------------------------

def _init_system(
    conn: sqlite3.Connection,
    system_id: int,
    z_mpc: float,
    tree: KDTree,
    positions: np.ndarray,
    system_id_to_idx: dict[int, int],
    next_star_id: list[int],    # mutable ref; [0] holds current max + 1
    is_multi_system: set[int],  # updated in-place when companions added
    # --- pre-loaded from _fetch_batch_stars / _fetch_batch_state ---
    stars_list: list[dict],     # mutable dicts; may be extended by 1b
    has_velocity: set[int],     # system_ids already in SystemVelocities
    bgs_done: set[int],         # star_ids with successful BodyGenerationStatus
    has_orbit: set[int],        # star_ids already in StarOrbits (any role)
) -> tuple[int, int]:
    """
    Run the full 1a–1e pipeline for one system.
    Returns (stars_processed, bodies_inserted).

    All reads come from the pre-loaded sets (no per-system queries except
    _system_binary_constraints() after orbit generation).
    """
    # ---- 1a. Velocity ----
    if system_id not in has_velocity:
        prim = stars_list[0]
        vx, vy, vz = generate_velocity(system_id, prim["age_yr"], prim["spectral"], z_mpc)
        conn.execute(
            "INSERT OR IGNORE INTO SystemVelocities"
            " (system_id, vx, vy, vz, source_star_id, velocity_source)"
            " VALUES (?, ?, ?, ?, NULL, 'synthetic')",
            (system_id, vx, vy, vz),
        )

    # ---- 1b. Spectral types; companion creation ----
    for star in list(stars_list):   # copy so appended companions are included
        if star["spectral"] is not None:
            continue
        spectral = format_spectral(star["ci"], star["absmag"])
        conn.execute(
            "UPDATE IndexedIntegerDistinctStars"
            " SET spectral = ?, source = 'derived' WHERE star_id = ?",
            (spectral, star["star_id"]),
        )
        star["spectral"] = spectral

        if system_id not in is_multi_system and should_create_multiple(spectral):
            comp_absmag   = companion_absmag(star["absmag"])
            comp_ci       = ci_from_absmag(comp_absmag)
            comp_spectral = format_spectral(f"{comp_ci:.4f}", comp_absmag)
            comp_id       = next_star_id[0]
            next_star_id[0] += 1
            conn.execute(
                "INSERT INTO IndexedIntegerDistinctStars"
                " (system_id, star_id, ci, absmag, spectral, source)"
                " VALUES (?, ?, ?, ?, ?, 'generated')",
                (system_id, comp_id, f"{comp_ci:.4f}", comp_absmag, comp_spectral),
            )
            is_multi_system.add(system_id)
            # New companion: not in any pre-loaded set, so all steps run for it
            stars_list.append({
                "star_id": comp_id, "ci": f"{comp_ci:.4f}", "absmag": comp_absmag,
                "spectral": comp_spectral,
                "mass": None, "luminosity": None, "radius": None,
                "age_yr": None, "temperature": None,
            })

    # ---- 1c. Stellar metrics ----
    # star["mass"] already comes from the bulk LEFT JOIN on DistinctStarsExtended.
    # Only compute for stars where it's missing or errored (mass IS NULL or -1).
    for star in stars_list:
        if star["mass"] is not None and star["mass"] != -1:
            continue
        try:
            m = compute_metrics(star["ci"], star["absmag"], star["spectral"])
            conn.execute(
                "INSERT OR REPLACE INTO DistinctStarsExtended"
                " (star_id, mass, temperature, radius, luminosity, age, temp_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (star["star_id"], m["mass"], m["temperature"],
                 m["radius"], m["luminosity"], m["age"], m["temp_source"]),
            )
            star["mass"]       = m["mass"]
            star["luminosity"] = m["luminosity"]
            star["radius"]     = m["radius"]
            star["age_yr"]     = m["age"]
        except MetricsError as exc:
            log.warning("star_id=%d metrics error: %s", star["star_id"], exc)
            conn.execute(
                "INSERT OR REPLACE INTO DistinctStarsExtended"
                " (star_id, mass) VALUES (?, -1)",
                (star["star_id"],),
            )

    # ---- 1d. Star orbits for multiple systems ----
    if len(stars_list) > 1:
        # Use pre-loaded has_orbit; new companions (appended in 1b) are absent
        # from has_orbit so they correctly pass through to orbit generation.
        unorbed = [s for s in stars_list if s["star_id"] not in has_orbit]
        if len(unorbed) >= 2:
            star_dicts = [
                {"star_id": s["star_id"], "mass": s["mass"] or 1.0,
                 "absmag": s["absmag"], "spectral": s["spectral"] or ""}
                for s in stars_list
            ]
            primary_id = identify_primary(star_dicts)
            companions  = [s for s in unorbed if s["star_id"] != primary_id]

            dist_mpc = _nearest_dist_mpc(system_id, system_id_to_idx, positions, tree)
            h_au     = hill_radius_au(dist_mpc)

            orbits = []
            for comp in companions:
                letter = (comp["spectral"] or "G")[0].upper()
                try:
                    orbit = generate_orbit(primary_id, letter, epoch=0)
                    orbit["star_id"] = comp["star_id"]
                    orbits.append(orbit)
                except OrbitsError as exc:
                    log.warning("system_id=%d star_id=%d orbit error: %s",
                                system_id, comp["star_id"], exc)

            if orbits:
                orbits.sort(key=lambda o: o["semi_major_axis"])
                enforce_stability(orbits, h_au)
                for orbit in orbits:
                    conn.execute(
                        "INSERT OR IGNORE INTO StarOrbits"
                        " (star_id, primary_star_id, semi_major_axis, eccentricity,"
                        "  inclination, longitude_ascending_node, argument_periapsis,"
                        "  mean_anomaly, epoch)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (orbit["star_id"], orbit["primary_star_id"],
                         orbit["semi_major_axis"], orbit["eccentricity"],
                         orbit["inclination"], orbit["longitude_ascending_node"],
                         orbit["argument_periapsis"], orbit["mean_anomaly"],
                         orbit["epoch"]),
                    )

    # ---- 1e. Body generation ----
    # Binary constraints must be read after 1d (orbits may have just been written).
    binary_cap, binary_stars, binary_plane = _system_binary_constraints(conn, system_id)

    total_bodies = 0
    for star in stars_list:
        star_id = star["star_id"]

        # Pre-loaded check: skip if already successfully generated
        if star_id in bgs_done:
            continue

        lum       = max(float(star["luminosity"] or 1.0), 1e-6)
        age_gyr   = float(star["age_yr"]) / 1e9 if star["age_yr"] else 5.0  # age is in YEARS
        radius_sol = float(star["radius"] or 1.0)
        mass_msol  = float(star["mass"] or 1.0)
        if mass_msol <= 0:
            mass_msol = 1.0

        is_solitary       = star_id not in binary_stars
        companion_max_au  = binary_cap.get(star_id, 1e9)
        bin_incl, bin_lan = binary_plane.get(star_id, (0.0, 0.0))

        try:
            bodies = _gpw.generate_system(
                star_id            = star_id,
                spectral           = star["spectral"] or "",
                luminosity         = lum,
                age_gyr            = age_gyr,
                star_radius_rsol   = radius_sol,
                star_mass_msol     = mass_msol,
                companion_max_au   = companion_max_au,
                is_solitary        = is_solitary,
                binary_inclination = bin_incl,
                binary_lan         = bin_lan,
            )
            n = _insert_bodies(conn, star_id, bodies)
            total_bodies += n
            conn.execute(
                "INSERT OR REPLACE INTO BodyGenerationStatus"
                " (star_id, body_count, generated_at, error)"
                " VALUES (?, ?, ?, NULL)",
                (star_id, n, int(time.time())),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("star_id=%d body generation failed: %s", star_id, exc)
            conn.execute(
                "INSERT OR REPLACE INTO BodyGenerationStatus"
                " (star_id, body_count, generated_at, error)"
                " VALUES (?, 0, ?, ?)",
                (star_id, int(time.time()), str(exc)),
            )

    return len(stars_list), total_bodies


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help="Path to starscape.db (default: %(default)s)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help="Systems committed per transaction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-minutes", type=float, default=None,
        help="Stop after N elapsed minutes",
    )
    parser.add_argument(
        "--stop-at", type=str, default=None, metavar="HH:MM",
        help="Stop at a specific wall-clock time today, e.g. 23:00",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Log each system processed",
    )
    args = parser.parse_args()

    if args.max_minutes is None and args.stop_at is None:
        parser.error("Supply at least one of --max-minutes or --stop-at")

    deadline = _parse_deadline(args.max_minutes, args.stop_at)
    log.info(
        "Deadline in %.1f minutes",
        (deadline - time.monotonic()) / 60.0,
    )

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -65536")   # 64 MB page cache

    try:
        # Load system positions once for Hill-sphere KDTree
        log.info("Loading system positions for Hill-sphere KDTree…")
        t0 = time.monotonic()
        positions, system_id_to_idx = _load_system_positions(conn)
        tree = KDTree(positions) if len(positions) > 0 else None
        log.info("KDTree built: %d systems in %.1fs", len(positions), time.monotonic() - t0)

        # next_star_id: mutable ref so companion creation can advance the counter
        max_sid = conn.execute(
            "SELECT MAX(star_id) FROM IndexedIntegerDistinctStars"
        ).fetchone()[0] or 0
        next_star_id = [max_sid + 1]

        # is_multi_system: pre-load to avoid companion duplication
        is_multi_system: set[int] = {
            r[0] for r in conn.execute(
                "SELECT system_id FROM IndexedIntegerDistinctStars"
                " GROUP BY system_id HAVING COUNT(*) > 1"
            ).fetchall()
        }
        log.info("Pre-loaded %d multiple systems", len(is_multi_system))

        # Resume from checkpoint — avoid re-scanning completed systems
        conn.execute(
            "INSERT OR IGNORE INTO InitCheckpoint (key, value) VALUES ('last_dist2_mpc2', 0)"
        )
        last_dist2: int = conn.execute(
            "SELECT value FROM InitCheckpoint WHERE key = 'last_dist2_mpc2'"
        ).fetchone()[0]
        log.info("Resuming from dist2_mpc2 > %d (%.3f pc)", last_dist2, last_dist2 ** 0.5 / 1000.0)

        total_systems = 0
        total_stars   = 0
        total_bodies  = 0

        while True:
            if time.monotonic() >= deadline:
                log.info("Deadline reached before fetching next batch.")
                break

            batch = conn.execute(
                _BATCH_QUERY, {"batch_size": args.batch_size, "last_dist2": last_dist2}
            ).fetchall()

            if not batch:
                log.info("All systems initialised — nothing left to do.")
                break

            batch_max_dist2  = batch[-1][4]
            batch_system_ids = [r[0] for r in batch]

            # ---- Bulk pre-fetch for the whole batch (items 1 and 2) ----
            stars_by_system = _fetch_batch_stars(conn, batch_system_ids)
            all_star_ids    = [
                s["star_id"]
                for slist in stars_by_system.values()
                for s in slist
            ]
            has_velocity, bgs_done, has_orbit = _fetch_batch_state(
                conn, batch_system_ids, all_star_ids
            )

            for system_id, x, y, z, dist2 in batch:
                if time.monotonic() >= deadline:
                    conn.commit()
                    conn.execute(
                        "UPDATE InitCheckpoint SET value = ? WHERE key = 'last_dist2_mpc2'",
                        (last_dist2,),
                    )
                    conn.commit()
                    log.info(
                        "Deadline reached mid-batch — checkpoint saved at dist2=%d (%.3f pc).  "
                        "%d systems / %d stars / %d bodies this run.",
                        last_dist2, last_dist2 ** 0.5 / 1000.0,
                        total_systems, total_stars, total_bodies,
                    )
                    return

                # mutable copy so 1b can append companions without affecting cache
                stars_list = [dict(s) for s in stars_by_system.get(system_id, [])]

                try:
                    n_stars, n_bodies = _init_system(
                        conn, system_id, float(z),
                        tree, positions, system_id_to_idx,
                        next_star_id, is_multi_system,
                        stars_list, has_velocity, bgs_done, has_orbit,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("system_id=%d unhandled error: %s", system_id, exc)
                    n_stars, n_bodies = 0, 0

                conn.execute(
                    "INSERT OR IGNORE INTO SystemGenerationStatus (system_id, dist2_mpc2)"
                    " VALUES (?, ?)",
                    (system_id, dist2),
                )

                total_systems += 1
                total_stars   += n_stars
                total_bodies  += n_bodies

                if args.verbose:
                    dist_pc = dist2 ** 0.5 / 1000.0
                    log.debug(
                        "system_id=%d  dist=%.3f pc  stars=%d  bodies=%d",
                        system_id, dist_pc, n_stars, n_bodies,
                    )

            # Advance the checkpoint past this batch
            last_dist2 = batch_max_dist2
            conn.execute(
                "UPDATE InitCheckpoint SET value = ? WHERE key = 'last_dist2_mpc2'",
                (last_dist2,),
            )
            conn.commit()
            log.info(
                "Batch complete: dist frontier=%.3f pc | "
                "%d systems  %d stars  %d bodies total this run",
                last_dist2 ** 0.5 / 1000.0,
                total_systems, total_stars, total_bodies,
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
