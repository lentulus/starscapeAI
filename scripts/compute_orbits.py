#!/usr/bin/env python3
"""Generate Keplerian orbital elements for companion stars in multiple systems.

For each multiple system not yet in StarOrbits:
  - Identifies the primary (most massive) star.
  - Generates orbital elements for every companion using physically motivated
    distributions (log-normal semi-major axis, thermal eccentricity, isotropic
    inclination).
  - Enforces Hill sphere and inter-companion stability constraints.

Requires fill_spectral.py and compute_metrics.py to have been run first.

Usage:
    uv run scripts/compute_orbits.py
    uv run scripts/compute_orbits.py --db /path/to/other.db
    uv run scripts/compute_orbits.py --batch-size 500 --max-minutes 120
    caffeinate -i uv run scripts/compute_orbits.py --max-minutes 600
"""

import argparse
import logging
import sqlite3
import time
from pathlib import Path

import numpy as np
from scipy.spatial import KDTree

from starscape5.orbits import (
    OrbitsError,
    enforce_stability,
    generate_orbit,
    hill_radius_au,
    identify_primary,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
STARS_TABLE = "IndexedIntegerDistinctStars"
METRICS_TABLE = "DistinctStarsExtended"
SYSTEMS_TABLE = "IndexedIntegerDistinctSystems"
ORBITS_TABLE = "StarOrbits"
DEFAULT_BATCH = 1000
DEFAULT_MAX_MINUTES = 60
DEFAULT_HILL_AU = 100_000.0   # fallback when system has no position entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _load_system_positions(conn: sqlite3.Connection) -> tuple[np.ndarray, dict[int, int]]:
    """Load all system positions into a numpy array for KDTree construction.

    Returns:
        positions: (N, 3) float array of (x, y, z) in milliparsecs
        system_id_to_idx: mapping from system_id to row index in positions
    """
    rows = conn.execute(
        f"SELECT system_id, x, y, z FROM {SYSTEMS_TABLE}"
    ).fetchall()
    if not rows:
        return np.empty((0, 3), dtype=float), {}
    positions = np.array([[r["x"], r["y"], r["z"]] for r in rows], dtype=float)
    system_id_to_idx = {r["system_id"]: i for i, r in enumerate(rows)}
    return positions, system_id_to_idx


def _nearest_neighbour_dist_mpc(
    system_id: int,
    system_id_to_idx: dict[int, int],
    positions: np.ndarray,
    tree: KDTree,
) -> float:
    """Return the distance in milliparsecs to the nearest other system.

    Falls back to DEFAULT_HILL_AU / hill_factor if the system has no position entry.
    """
    idx = system_id_to_idx.get(system_id)
    if idx is None:
        return DEFAULT_HILL_AU  # already in AU; caller converts via hill_radius_au
    point = positions[idx]
    # k=2: nearest is itself (dist≈0), second is the true nearest neighbour
    dists, _ = tree.query(point, k=min(2, len(positions)))
    if len(dists) < 2:
        return DEFAULT_HILL_AU
    return float(dists[1]) if dists[1] > 0 else DEFAULT_HILL_AU


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Systems between commits (default: %(default)s)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                        help="Stop after this many elapsed minutes (default: %(default)s)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        # Pre-load all system positions for O(log n) nearest-neighbour queries
        log.info("Loading system positions for Hill sphere calculation...")
        positions, system_id_to_idx = _load_system_positions(conn)
        tree = KDTree(positions) if len(positions) > 0 else None
        log.info("Loaded %d system positions", len(positions))

        # Find multiple systems that still have at least one companion with no orbit row.
        # A companion is "done" if its star_id appears in StarOrbits.star_id.
        # A primary is recognised by appearing in StarOrbits.primary_star_id.
        # Any star in a multi-star system that is neither a recorded companion nor a
        # recorded primary is a missing companion — find its system_id for reprocessing.
        # INSERT OR IGNORE below means already-present companions are skipped safely.
        pending_rows = conn.execute(f"""
            SELECT DISTINCT s.system_id
            FROM {STARS_TABLE} s
            WHERE s.system_id IN (
                SELECT system_id FROM {STARS_TABLE}
                GROUP BY system_id HAVING COUNT(*) > 1
            )
            AND s.star_id NOT IN (SELECT star_id         FROM {ORBITS_TABLE})
            AND s.star_id NOT IN (SELECT primary_star_id FROM {ORBITS_TABLE})
        """).fetchall()
        pending = [r["system_id"] for r in pending_rows]

        total = len(pending)
        log.info("Found %d multiple systems to process", total)
        if total == 0:
            log.info("Nothing to do.")
            return

        processed = 0
        errors = 0

        for system_id in pending:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info(
                    "Time limit reached after %d systems (%d errors). Re-run to continue.",
                    processed, errors,
                )
                return

            try:
                # Load star data for this system
                stars_rows = conn.execute(
                    f"SELECT i.star_id, m.mass, i.absmag, i.spectral"
                    f" FROM {STARS_TABLE} i"
                    f" LEFT JOIN {METRICS_TABLE} m ON i.star_id = m.star_id"
                    f" WHERE i.system_id = ?",
                    (system_id,),
                ).fetchall()

                stars = [
                    {
                        "star_id": r["star_id"],
                        "mass": r["mass"],
                        "absmag": r["absmag"],
                        "spectral": r["spectral"] or "",
                    }
                    for r in stars_rows
                ]

                primary_id = identify_primary(stars)

                # Hill sphere radius for this system
                if tree is not None:
                    dist_mpc = _nearest_neighbour_dist_mpc(
                        system_id, system_id_to_idx, positions, tree
                    )
                    hill_au = hill_radius_au(dist_mpc)
                else:
                    hill_au = DEFAULT_HILL_AU

                # Generate orbits for all companions
                companions = [s for s in stars if s["star_id"] != primary_id]
                orbits = []
                for companion in companions:
                    spectral_letter = companion["spectral"][0].upper() if companion["spectral"] else "G"
                    orbit = generate_orbit(primary_id, spectral_letter, epoch=0)
                    orbit["star_id"] = companion["star_id"]
                    orbits.append(orbit)

                # Enforce stability constraints
                orbits.sort(key=lambda o: o["semi_major_axis"])
                enforce_stability(orbits, hill_au)

                # Check whether Hill cap caused any re-violations and warn
                for idx in range(1, len(orbits)):
                    inner = orbits[idx - 1]
                    outer = orbits[idx]
                    if (outer["semi_major_axis"] * (1 - outer["eccentricity"])
                            < 3 * inner["semi_major_axis"] * (1 + inner["eccentricity"])):
                        log.warning(
                            "system_id=%d: Hill cap left companions %d and %d "
                            "in unstable configuration (crowded region)",
                            system_id, inner["star_id"], outer["star_id"],
                        )

                # Insert
                for orbit in orbits:
                    conn.execute(
                        f"INSERT OR IGNORE INTO {ORBITS_TABLE}"
                        f" (star_id, primary_star_id, semi_major_axis, eccentricity,"
                        f"  inclination, longitude_ascending_node, argument_periapsis,"
                        f"  mean_anomaly, epoch)"
                        f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            orbit["star_id"],
                            orbit["primary_star_id"],
                            orbit["semi_major_axis"],
                            orbit["eccentricity"],
                            orbit["inclination"],
                            orbit["longitude_ascending_node"],
                            orbit["argument_periapsis"],
                            orbit["mean_anomaly"],
                            orbit["epoch"],
                        ),
                    )

            except OrbitsError as exc:
                log.error("system_id=%d: %s", system_id, exc)
                errors += 1

            processed += 1
            if processed % args.batch_size == 0:
                conn.commit()
                log.info("Progress: %d / %d systems, %d errors", processed, total, errors)

        conn.commit()
        log.info("Complete. Processed %d systems, %d errors.", processed, errors)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
