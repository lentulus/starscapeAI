#!/usr/bin/env python3
"""WBH companion star orbit generation — pre-step for generate_planets_wbh.py.

Run this BEFORE generate_planets_wbh.py.  Step 3 (procedural orbit generation
for unknown multiple systems) is now handled inline by generate_planets_wbh.py;
this script performs steps 0–2 only.

Steps performed here:
  0. Add any known companion stars that are absent from the catalog
     (IndexedIntegerDistinctStars / DistinctStarsExtended) as a single sweep.
     These are real companions (white dwarfs, faint M dwarfs) that lacked
     individual Hipparcos entries.
  1. Purge all existing StarOrbits rows.
  2. Seed StarOrbits for known nearby multiple systems (Sirius, α Cen, 61 Cyg,
     …) with accurate published orbital parameters.

After this script finishes, run generate_planets_wbh.py --purge.  That script
will generate companion orbits on-the-fly for any multi-star system it
encounters that still lacks StarOrbits rows.

Usage:
    uv run scripts/generate_star_orbits_wbh.py
    uv run scripts/generate_star_orbits_wbh.py --world /path/to/starscape.db
    uv run scripts/generate_star_orbits_wbh.py --dry-run
    uv run scripts/generate_star_orbits_wbh.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
SOL_SYSTEM_ID = 1030192

# ---------------------------------------------------------------------------
# Known nearby multiple systems — accurate published parameters.
#
# Key   = HIP number of the PRIMARY (most luminous) star.
# Value = list of companion specs, in order of increasing SMA:
#           (sma_au, eccentricity, inclination_rad, label)
#
# The script matches companions by position within the system (sorted by
# luminosity desc in the DB).  If the catalog has fewer companions than the
# list, extras are silently skipped.  If HIP lookup fails the whole entry is
# skipped without error.
# ---------------------------------------------------------------------------
KNOWN_MULTIPLES: dict[int, list[tuple[float, float, float, str]]] = {
    # α Centauri system — G2V primary, K1V secondary, Proxima M5Ve wide
    71683: [
        (23.4,    0.518, math.radians(79.2),  "α Cen B (K1V)"),
        (13000.0, 0.51,  math.radians(107.6), "Proxima Centauri (M5Ve)"),
    ],
    # Sirius — A1V + DA2 white dwarf (Sirius B likely not in HIP catalog)
    32349: [
        (19.8, 0.592, math.radians(136.5), "Sirius B (DA2)"),
    ],
    # Procyon — F5IV + DQZ white dwarf (Procyon B likely not in HIP catalog)
    37279: [
        (15.0, 0.40, math.radians(31.1), "Procyon B (DQZ)"),
    ],
    # 61 Cygni — K5V + K7V
    104214: [
        (84.0, 0.49, math.radians(51.5), "61 Cyg B (K7V)"),
    ],
    # η Cassiopeiae — G0V + K7V
    3821: [
        (71.0, 0.497, math.radians(34.8), "η Cas B (K7V)"),
    ],
    # 70 Ophiuchi — K0V + K4V
    88601: [
        (23.2, 0.499, math.radians(121.0), "70 Oph B (K4V)"),
    ],
    # 36 Ophiuchi — K1V + K1V + K5V triple
    89937: [
        (69.0, 0.14, math.radians(131.0), "36 Oph B (K1V)"),
    ],
}


# ---------------------------------------------------------------------------
# Step 0: Known companions absent from the Hipparcos catalog.
#
# These stars are real, well-characterised companions that lacked individual
# HIP entries (typically white dwarfs, or close faint secondaries resolved
# only by HST).  They are inserted into IndexedIntegerDistinctStars with
# star_id < 0 (negative, never used by Hipparcos) and into
# DistinctStarsExtended with their published physical parameters.
#
# WBH spectral type conventions are used (e.g. "DA2" for a DA white dwarf).
# ---------------------------------------------------------------------------

UNCATALOGUED_COMPANIONS: list[dict] = [
    {
        "star_id":       11419549,
        "primary_hip":   32349,     # Sirius A (A1V)
        "spectral":      "DA2",     # hydrogen-atmosphere white dwarf
        "mass_msol":     1.018,
        "radius_rsol":   0.0084,    # ~0.84% of Sun
        "luminosity":    0.026,     # L/L_sun
        "temperature_k": 25200,
        "age_gyr":       None,      # inherit primary's age
        "source":        "manual",
    },
    {
        "star_id":       11419550,
        "primary_hip":   37279,     # Procyon A (F5IV)
        "spectral":      "DQZ",     # carbon/metal WD
        "mass_msol":     0.604,
        "radius_rsol":   0.01234,
        "luminosity":    0.00055,
        "temperature_k": 7740,
        "age_gyr":       None,
        "source":        "manual",
    },
]


def add_uncatalogued_companions(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Insert known companions absent from the catalog.  Idempotent — uses
    INSERT OR IGNORE.  Returns number of rows actually inserted.
    """
    inserted = 0
    for entry in UNCATALOGUED_COMPANIONS:
        # Locate primary by HIP
        row = conn.execute(
            "SELECT star_id, system_id FROM IndexedIntegerDistinctStars WHERE hip = ?",
            (entry["primary_hip"],),
        ).fetchone()
        if row is None:
            log.warning("Primary HIP %d not found — skipping %s",
                        entry["primary_hip"], entry["spectral"])
            continue

        primary_star_id = row["star_id"]
        system_id       = row["system_id"]

        # Check if this companion already exists (by negative star_id)
        exists = conn.execute(
            "SELECT 1 FROM IndexedIntegerDistinctStars WHERE star_id = ?",
            (entry["star_id"],),
        ).fetchone()
        if exists:
            log.debug("star_id %d already in catalog — skipping.", entry["star_id"])
            continue

        # Inherit age from primary if not specified
        age_gyr = entry["age_gyr"]
        if age_gyr is None:
            age_row = conn.execute(
                "SELECT age FROM DistinctStarsExtended WHERE star_id = ?",
                (primary_star_id,)
            ).fetchone()
            age_gyr = float(age_row["age"]) if age_row and age_row["age"] else 5.0

        if dry_run:
            log.info("[dry-run] Would add  star_id=%d  %s  (companion of HIP %d)",
                     entry["star_id"], entry["spectral"], entry["primary_hip"])
            inserted += 1
            continue

        # Insert into IndexedIntegerDistinctStars
        conn.execute(
            """
            INSERT OR IGNORE INTO IndexedIntegerDistinctStars
                (star_id, system_id, hip, spectral, source)
            VALUES (?, ?, NULL, ?, ?)
            """,
            (entry["star_id"], system_id, entry["spectral"], entry["source"]),
        )

        # Insert into DistinctStarsExtended
        conn.execute(
            """
            INSERT OR IGNORE INTO DistinctStarsExtended
                (star_id, mass, luminosity, radius, age, temperature)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry["star_id"], entry["mass_msol"], entry["luminosity"],
             entry["radius_rsol"], age_gyr, entry["temperature_k"]),
        )

        log.info("Added  star_id=%d  %s  (companion of HIP %d, system %d)",
                 entry["star_id"], entry["spectral"], entry["primary_hip"], system_id)
        inserted += 1

    if not dry_run:
        conn.commit()

    log.info("Uncatalogued companions: %d added.", inserted)
    return inserted


# ---------------------------------------------------------------------------
# WBH companion orbit generation (§3)
# ---------------------------------------------------------------------------

def _2d() -> int:
    return random.randint(1, 6) + random.randint(1, 6)


def _separation_au_range(spectral_letter: str) -> tuple[float, float]:
    """Return (min_au, max_au) for the rolled separation class.

    Uses a 2D6 roll with a spectral-type DM derived from survey data
    (Raghavan 2010; Duchêne & Kraus 2013).
    """
    dm = {
        "O": 2, "B": 2, "A": 1,
        "F": 0, "G": 0, "K": 0,
        "M": -1, "L": -2, "T": -2,
    }.get(spectral_letter.upper(), 0)
    roll = max(2, min(12, _2d() + dm))

    if roll <= 3:
        return (0.02, 0.5)       # very close — tidal circularisation likely
    elif roll <= 5:
        return (0.5, 5.0)        # close
    elif roll <= 7:
        return (5.0, 50.0)       # moderate
    elif roll <= 9:
        return (50.0, 500.0)     # wide
    elif roll <= 11:
        return (500.0, 5000.0)   # very wide
    else:
        return (2000.0, 10000.0) # distant (barely bound)


def _eccentricity_for_sma(sma_au: float) -> float:
    """Sample eccentricity appropriate for the given semi-major axis."""
    if sma_au < 0.5:
        return random.uniform(0.0, 0.08)   # tidal circularisation
    elif sma_au < 5.0:
        return random.uniform(0.0, 0.40)
    elif sma_au < 50.0:
        return random.uniform(0.0, 0.60)
    elif sma_au < 500.0:
        return random.uniform(0.05, 0.75)
    else:
        return random.uniform(0.10, 0.90)


def generate_companion_orbit(
    primary_mass_msol: float,
    companion_mass_msol: float,
    primary_radius_rsol: float,
    spectral_letter: str,
) -> dict:
    """Generate a WBH-style Keplerian orbit for a companion star.

    Returns a dict with all StarOrbits columns except star_id / primary_star_id.
    Guarantees periapsis > Roche limit and SMA ≤ 10 000 AU.
    """
    lo, hi = _separation_au_range(spectral_letter)

    # Log-uniform within the separation class
    sma = math.exp(random.uniform(math.log(lo), math.log(hi)))
    e   = _eccentricity_for_sma(sma)

    # Roche limit: periapsis must exceed 2.44 R_primary (M1/M2)^(1/3)
    # 1 R_sol = 0.00465047 AU
    r_primary_au  = primary_radius_rsol * 0.00465047
    roche_au      = 2.44 * r_primary_au * (primary_mass_msol / max(companion_mass_msol, 0.01)) ** (1.0 / 3.0)

    for _ in range(25):
        if sma * (1.0 - e) >= roche_au:
            break
        sma *= 1.5
        e    = _eccentricity_for_sma(sma)
    else:
        sma = roche_au * 3.0
        e   = 0.1

    sma = min(sma, 10_000.0)  # hard cap — beyond this orbit is effectively unbound

    return dict(
        semi_major_axis          = sma,
        eccentricity             = e,
        inclination              = random.uniform(0.0, math.pi),
        longitude_ascending_node = random.uniform(0.0, 2.0 * math.pi),
        argument_periapsis       = random.uniform(0.0, 2.0 * math.pi),
        mean_anomaly             = random.uniform(0.0, 2.0 * math.pi),
        epoch                    = 0,
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT INTO StarOrbits
    (star_id, primary_star_id, semi_major_axis, eccentricity, inclination,
     longitude_ascending_node, argument_periapsis, mean_anomaly, epoch)
VALUES
    (:star_id, :primary_star_id, :semi_major_axis, :eccentricity, :inclination,
     :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch)
"""


def purge_star_orbits(conn: sqlite3.Connection) -> int:
    """Delete all StarOrbits rows. Returns count deleted."""
    count = conn.execute("DELETE FROM StarOrbits").rowcount
    conn.commit()
    log.info("Purged %d StarOrbits rows.", count)
    return count


def _system_stars(conn: sqlite3.Connection, system_id: int) -> list[sqlite3.Row]:
    """All stars in a system, sorted by luminosity desc (primary first)."""
    return conn.execute(
        """
        SELECT i.star_id, i.spectral, i.hip,
               COALESCE(e.mass,       1.0) AS mass_msol,
               COALESCE(e.luminosity, 0.0) AS luminosity,
               COALESCE(e.radius,     1.0) AS radius_rsol
        FROM   IndexedIntegerDistinctStars i
        LEFT JOIN DistinctStarsExtended    e ON i.star_id = e.star_id
        WHERE  i.system_id = ?
        ORDER BY COALESCE(e.luminosity, 0.0) DESC, i.star_id ASC
        """,
        (system_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Step 2: seed known systems
# ---------------------------------------------------------------------------

def seed_known_orbits(conn: sqlite3.Connection, dry_run: bool = False) -> set[int]:
    """Insert accurate orbital elements for well-known nearby binaries.

    Returns the set of companion star_ids that were seeded (or would be seeded
    in dry-run mode) so the procedural pass can skip them.
    """
    seeded: set[int] = set()

    for primary_hip, companions_spec in KNOWN_MULTIPLES.items():
        # Locate primary in catalog
        row = conn.execute(
            "SELECT star_id, system_id FROM IndexedIntegerDistinctStars WHERE hip = ?",
            (primary_hip,),
        ).fetchone()
        if row is None:
            log.debug("HIP %d not found — skipping known-system seed.", primary_hip)
            continue

        primary_star_id = row["star_id"]
        system_id       = row["system_id"]

        stars = _system_stars(conn, system_id)
        if len(stars) < 2:
            log.debug("HIP %d: only 1 star in system — nothing to seed.", primary_hip)
            continue

        companions_in_db = [s for s in stars if s["star_id"] != primary_star_id]
        companions_spec_sorted = sorted(companions_spec, key=lambda x: x[0])

        for i, (sma_au, ecc, incl_rad, label) in enumerate(companions_spec_sorted):
            if i >= len(companions_in_db):
                log.debug("  HIP %d: DB has only %d companion(s) — no slot for %s",
                          primary_hip, len(companions_in_db), label)
                break

            comp = companions_in_db[i]
            orbit = dict(
                star_id                  = comp["star_id"],
                primary_star_id          = primary_star_id,
                semi_major_axis          = sma_au,
                eccentricity             = ecc,
                inclination              = incl_rad,
                longitude_ascending_node = random.uniform(0.0, 2.0 * math.pi),
                argument_periapsis       = random.uniform(0.0, 2.0 * math.pi),
                mean_anomaly             = random.uniform(0.0, 2.0 * math.pi),
                epoch                    = 0,
            )
            seeded.add(comp["star_id"])

            if dry_run:
                log.info("[dry-run] Would seed  HIP %d → %s  a=%.1f AU  e=%.3f",
                         primary_hip, label, sma_au, ecc)
            else:
                try:
                    conn.execute(_INSERT_SQL, orbit)
                    log.info("Seeded  HIP %d → %s  a=%.1f AU  e=%.3f",
                             primary_hip, label, sma_au, ecc)
                except sqlite3.IntegrityError as exc:
                    log.warning("Seed conflict for %s: %s", label, exc)

    if not dry_run:
        conn.commit()

    log.info("Known-system seed complete: %d companion(s) seeded.", len(seeded))
    return seeded


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--world",   default=str(DEFAULT_DB), help="Path to starscape.db")
    parser.add_argument("--dry-run", action="store_true", help="Describe actions without writing")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    world_path = Path(args.world)
    if not world_path.exists():
        sys.exit(f"Database not found: {world_path}")

    conn = sqlite3.connect(str(world_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    dry_run = args.dry_run

    try:
        # -- Step 0: add known uncatalogued companions ---------------------
        add_uncatalogued_companions(conn, dry_run=dry_run)

        # -- Step 1: purge StarOrbits --------------------------------------
        if dry_run:
            n = conn.execute("SELECT COUNT(*) FROM StarOrbits").fetchone()[0]
            log.info("[dry-run] Would purge %d existing StarOrbits rows.", n)
        else:
            purge_star_orbits(conn)

        # -- Step 2: seed known systems with accurate parameters -----------
        seed_known_orbits(conn, dry_run=dry_run)

        total = conn.execute("SELECT COUNT(*) FROM StarOrbits").fetchone()[0]
        if dry_run:
            log.info("[dry-run] Done. (DB unchanged)")
        else:
            log.info("Done. StarOrbits seeded: %d rows.", total)
            log.info("Now run:  uv run scripts/generate_planets_wbh.py --purge")
            log.info("Remaining multi-star orbits will be generated inline during planet gen.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
