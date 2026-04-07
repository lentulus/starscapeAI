#!/usr/bin/env python3
"""Seed the Bodies table with the real solar system for star_id = 1 (Sol).

Uses known orbital elements and physical properties.  All angles in radians.
Mean anomalies are approximate values for a near-future game epoch (~2100 CE).

Run this BEFORE generate_planets.py so that Sol is skipped by the random generator.

Usage:
    uv run scripts/seed_sol.py
    uv run scripts/seed_sol.py --db /path/to/other.db
    uv run scripts/seed_sol.py --force   # re-seed even if Sol already has planets
"""

import argparse
import logging
import math
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
SOL_STAR_ID = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Solar system data
# All angles in radians.  Mass in Earth masses (Mₑ).  Radius in Earth radii (Rₑ).
# Semi-major axis in AU.  Mean anomaly at game epoch ~2100 CE (approximate).
# ---------------------------------------------------------------------------

# (name, mass_Me, radius_Re, a_AU, e, i_rad, Omega_rad, omega_rad, M0_rad)
PLANETS = [
    # Mercury
    ("Mercury",  0.05527, 0.3829, 0.38710, 0.20563, 0.12217, 0.84301, 0.50819, 5.66),
    # Venus
    ("Venus",    0.81500, 0.9499, 0.72333, 0.00677, 0.05924, 1.33872, 0.95877, 0.04),
    # Earth
    ("Earth",    1.00000, 1.0000, 1.00000, 0.01671, 0.00000, 0.00000, 1.99330, 0.00),
    # Mars
    ("Mars",     0.10745, 0.5320, 1.52366, 0.09341, 0.03229, 0.86536, 5.00017, 1.35),
    # Jupiter
    ("Jupiter",  317.830, 11.209, 5.20336, 0.04839, 0.02271, 1.75397, 4.78218, 3.30),
    # Saturn
    ("Saturn",   95.162, 9.4492, 9.53707, 0.05415, 0.04340, 1.98349, 5.92392, 3.32),
    # Uranus
    ("Uranus",   14.536, 4.0074, 19.1913, 0.04717, 0.01344, 1.29154, 1.68418, 0.47),
    # Neptune
    ("Neptune",  17.147, 3.8827, 30.0690, 0.00859, 0.03089, 2.30031, 4.76942, 2.84),
]

# (planet_name, name, mass_Me, radius_Re, a_AU, e, i_rad, Omega_rad, omega_rad, M0_rad)
MOONS = [
    # Earth
    ("Earth",   "Moon",     0.012300, 0.27268, 0.002569, 0.0549, 0.08980, 0.00, 0.00, 0.00),
    # Mars
    ("Mars",    "Phobos",   1.07e-8,  0.00152, 6.27e-5,  0.0151, 0.00175, 0.00, 0.00, 0.00),
    ("Mars",    "Deimos",   1.48e-9,  0.00083, 1.57e-4,  0.0003, 0.00505, 0.00, 0.00, 0.00),
    # Jupiter — Galilean moons
    ("Jupiter", "Io",       0.01496,  0.28602, 0.002820, 0.0041, 0.00698, 0.00, 0.00, 0.00),
    ("Jupiter", "Europa",   0.00804,  0.24520, 0.004486, 0.0094, 0.00796, 0.00, 0.00, 0.00),
    ("Jupiter", "Ganymede", 0.02515,  0.41297, 0.007155, 0.0013, 0.00314, 0.00, 0.00, 0.00),
    ("Jupiter", "Callisto", 0.01803,  0.37847, 0.012585, 0.0074, 0.00349, 0.00, 0.00, 0.00),
    # Saturn
    ("Saturn",  "Titan",    0.02254,  0.40400, 0.008168, 0.0288, 0.00872, 0.00, 0.00, 0.00),
    ("Saturn",  "Enceladus",1.80e-5,  0.03956, 0.001591, 0.0047, 0.00000, 0.00, 0.00, 0.00),
    # Uranus
    ("Uranus",  "Titania",  5.90e-4,  0.11394, 0.002916, 0.0011, 0.00000, 0.00, 0.00, 0.00),
    ("Uranus",  "Oberon",   5.08e-4,  0.11003, 0.003902, 0.0014, 0.00000, 0.00, 0.00, 0.00),
    # Neptune — Triton is retrograde: i > π/2
    ("Neptune", "Triton",   3.58e-4,  0.21275, 0.002371, 0.0000, 2.74889, 0.00, 0.00, 0.00),
]


# Sol L = 1.0 solar luminosities → HZ = [0.95, 1.67] AU; tidal lock radius = 0.5√L AU
_SOL_HZ_INNER = 0.95
_SOL_HZ_OUTER = 1.67
_SOL_TIDAL_LOCK_AU = 0.5    # a < 0.5 AU → possible tidal lock to Sol (Mercury qualifies)

INSERT_SQL = """
    INSERT INTO Bodies
        (body_type, mass, radius, orbit_star_id, orbit_body_id,
         semi_major_axis, eccentricity, inclination,
         longitude_ascending_node, argument_periapsis, mean_anomaly, epoch,
         in_hz, possible_tidal_lock)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--force", action="store_true",
                        help="Re-seed Sol even if planets already exist")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM Bodies WHERE orbit_star_id = ?", (SOL_STAR_ID,)
        ).fetchone()[0]

        if existing and not args.force:
            log.info("Sol already has %d bodies in Bodies table. Use --force to re-seed.", existing)
            return

        if existing and args.force:
            log.info("--force: deleting %d existing Sol bodies.", existing)
            # Delete moons of Sol planets first (FK constraint order)
            conn.execute(
                "DELETE FROM Bodies WHERE orbit_body_id IN "
                "(SELECT body_id FROM Bodies WHERE orbit_star_id = ?)",
                (SOL_STAR_ID,)
            )
            conn.execute("DELETE FROM Bodies WHERE orbit_star_id = ?", (SOL_STAR_ID,))

        # Index planets by name so moons can look up their parent body_id
        planet_ids: dict[str, int] = {}

        for (name, mass, radius, a, e, i, omega_big, omega, m0) in PLANETS:
            in_hz = 1 if _SOL_HZ_INNER <= a <= _SOL_HZ_OUTER else 0
            tidal_lock = 1 if a < _SOL_TIDAL_LOCK_AU else 0
            cur = conn.execute(
                INSERT_SQL,
                ("planet", mass, radius, SOL_STAR_ID, None, a, e, i, omega_big, omega, m0,
                 in_hz, tidal_lock)
            )
            planet_ids[name] = cur.lastrowid
            log.info("Inserted planet %s (body_id=%d, in_hz=%d, tidal_lock=%d)",
                     name, cur.lastrowid, in_hz, tidal_lock)

        for (planet_name, moon_name, mass, radius, a, e, i, omega_big, omega, m0) in MOONS:
            parent_id = planet_ids[planet_name]
            cur = conn.execute(
                INSERT_SQL,
                ("moon", mass, radius, None, parent_id, a, e, i, omega_big, omega, m0, None, 1)
            )
            log.info("  Inserted moon %s → %s (body_id=%d)", moon_name, planet_name, cur.lastrowid)

        # Asteroid belt — representative statistical row for the Sol main belt
        conn.execute(INSERT_SQL, (
            "belt", 4.5e-4, None, SOL_STAR_ID, None,
            2.70, 0.17, 0.0927, 0.0, 0.0, 0.0,  # a=2.70 AU, e, i, Ω, ω, M0
            0, None,  # in_hz=0, possible_tidal_lock=NULL
        ))
        log.info("Inserted Sol asteroid belt (center=2.70 AU)")

        # Ceres — largest known body in the asteroid belt
        conn.execute(INSERT_SQL, (
            "planetoid", 1.57e-4, 0.074, SOL_STAR_ID, None,
            2.7691, 0.0760, 0.1849, 1.4024, 1.2780, 0.0,
            0, None,  # in_hz=0, possible_tidal_lock=NULL
        ))
        log.info("Inserted Ceres (a=2.77 AU)")

        conn.commit()
        log.info(
            "Done. Inserted %d planets, %d moons, 1 belt, 1 planetoid for Sol (star_id=%d).",
            len(PLANETS), len(MOONS), SOL_STAR_ID,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
