#!/usr/bin/env python3
"""Generate planets and moons and populate the Bodies table.

For each star in IndexedIntegerDistinctStars not yet having planets in Bodies,
generates a system of planets with Keplerian orbits, then generates moons for
each planet. Uses luminosity from DistinctStarsExtended (falls back to 1.0 L☉).

Supports resuming: stars that already have planets in Bodies are skipped.
Stops cleanly after --max-minutes elapsed time; re-run to continue.

Spatial filtering: use --cx/--cy/--cz and --width to restrict generation to
stars whose system falls within a cube of the given side length (parsecs),
centred on (cx, cy, cz) in parsecs.  DB coordinates are milliparsecs (integer);
the conversion is applied automatically.

Usage:
    uv run scripts/generate_planets.py
    uv run scripts/generate_planets.py --db /path/to/other.db
    uv run scripts/generate_planets.py --batch-size 200 --max-minutes 120
    uv run scripts/generate_planets.py --cx 10 --cy 20 --cz 20 --width 10
    caffeinate -i uv run scripts/generate_planets.py --max-minutes 600
"""

import argparse
import logging
import math
import random
import sqlite3
import time
from pathlib import Path

from starscape5.orbits import enforce_stability, random_angles, thermal_eccentricity
from starscape5.planets import (
    belt_mass_earth,
    belt_positions,
    generate_belt,
    generate_moon,
    generate_planet,
    generate_planetoid,
    hz_bounds,
    moon_count,
    planet_count,
    planetoid_count,
    radius_from_mass,
    world_size_code,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
SOURCE_TABLE = "IndexedIntegerDistinctStars"
EXTENDED_TABLE = "DistinctStarsExtended"
TARGET_TABLE = "Bodies"
DEFAULT_BATCH = 500
DEFAULT_MAX_MINUTES = 60
PLANET_HILL_AU = 50.0
SYSTEMS_TABLE = "IndexedIntegerDistinctSystems"
PARSEC_TO_MPC = 1000  # DB stores coordinates as integer milliparsecs
# S-type stability: planet a must be < S_TYPE_FRACTION * companion a
S_TYPE_FRACTION = 0.3
# Minimum stable zone to bother generating planets (AU)
MIN_STABLE_AU = 0.05

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INSERT_SQL = (
    f"INSERT INTO {TARGET_TABLE}"
    " (body_type, mass, radius, orbit_star_id, orbit_body_id,"
    " semi_major_axis, eccentricity, inclination,"
    " longitude_ascending_node, argument_periapsis, mean_anomaly, epoch,"
    " in_hz, possible_tidal_lock, planet_class, has_rings,"
    " comp_metallic, comp_carbonaceous, comp_stony, span_inner_au, span_outer_au)"
    " VALUES (:body_type, :mass, :radius, :orbit_star_id, :orbit_body_id,"
    " :semi_major_axis, :eccentricity, :inclination,"
    " :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch,"
    " :in_hz, :possible_tidal_lock, :planet_class, :has_rings,"
    " :comp_metallic, :comp_carbonaceous, :comp_stony, :span_inner_au, :span_outer_au)"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Stars between commits (default: %(default)s)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                        help="Stop after this many elapsed minutes (default: %(default)s)")
    parser.add_argument("--cx", type=float, default=None,
                        help="Box centre X coordinate in parsecs (requires --cy, --cz, --width)")
    parser.add_argument("--cy", type=float, default=None,
                        help="Box centre Y coordinate in parsecs")
    parser.add_argument("--cz", type=float, default=None,
                        help="Box centre Z coordinate in parsecs")
    parser.add_argument("--width", type=float, default=None,
                        help="Cube side length in parsecs (half-width applied to each axis)")
    parser.add_argument("--solitary-stars-only", action="store_true", default=False,
                        help="Skip stars in multiple systems (companions and their primaries)")
    args = parser.parse_args()

    spatial_filter = all(v is not None for v in (args.cx, args.cy, args.cz, args.width))
    if any(v is not None for v in (args.cx, args.cy, args.cz, args.width)) and not spatial_filter:
        raise SystemExit("--cx, --cy, --cz, and --width must all be provided together")

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        # Ensure Bodies table exists
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS \"{TARGET_TABLE}\" ("
            "  body_id          INTEGER PRIMARY KEY,"
            "  body_type        TEXT    NOT NULL CHECK(body_type IN ('planet','moon','belt','planetoid')),"
            "  mass             REAL,"
            "  radius           REAL,"
            "  orbit_star_id    INTEGER,"
            "  orbit_body_id    INTEGER,"
            "  semi_major_axis  REAL    NOT NULL,"
            "  eccentricity     REAL    NOT NULL,"
            "  inclination      REAL    NOT NULL,"
            "  longitude_ascending_node REAL NOT NULL,"
            "  argument_periapsis       REAL NOT NULL,"
            "  mean_anomaly     REAL    NOT NULL,"
            "  epoch            INTEGER NOT NULL DEFAULT 0,"
            "  in_hz            INTEGER,"
            "  possible_tidal_lock INTEGER,"
            "  planet_class     TEXT,"
            "  has_rings        INTEGER,"
            "  comp_metallic    REAL,"
            "  comp_carbonaceous REAL,"
            "  comp_stony       REAL,"
            "  span_inner_au    REAL,"
            "  span_outer_au    REAL,"
            "  surface_gravity  REAL,"
            "  escape_velocity_kms REAL,"
            "  t_eq_k           REAL,"
            "  CHECK ("
            "    (orbit_star_id IS NOT NULL AND orbit_body_id IS NULL) OR"
            "    (orbit_star_id IS NULL     AND orbit_body_id IS NOT NULL)"
            "  )"
            ")"
        )
        conn.commit()

        # Pre-load binary constraints from StarOrbits.
        # For each star_id, compute the maximum stable planet semi-major axis:
        #   Primary stars: cap = S_TYPE_FRACTION * min(companion semi_major_axis)
        #   Companion stars: cap = S_TYPE_FRACTION * own semi_major_axis
        # Stars not in StarOrbits at all are single stars → cap = PLANET_HILL_AU.
        binary_cap: dict[int, float] = {}
        try:
            orbits = conn.execute(
                "SELECT star_id, primary_star_id, semi_major_axis FROM StarOrbits"
            ).fetchall()
            # companions → their own orbit caps their stable zone
            for o in orbits:
                cap = o["semi_major_axis"] * S_TYPE_FRACTION
                binary_cap[o["star_id"]] = cap
            # primaries → capped by their closest companion
            for o in orbits:
                primary = o["primary_star_id"]
                cap = o["semi_major_axis"] * S_TYPE_FRACTION
                if primary not in binary_cap or cap < binary_cap[primary]:
                    binary_cap[primary] = cap
        except sqlite3.OperationalError:
            log.warning("StarOrbits table not found — treating all stars as single")

        log.info(
            "Binary constraints loaded for %d stars (of which %d are companions or primaries)",
            len(binary_cap), len(binary_cap),
        )

        # Stars not yet having any planet, optionally restricted to a spatial box.
        # Coordinates in DB are integer milliparsecs; convert parsec params.
        if spatial_filter:
            half_mpc = int((args.width / 2) * PARSEC_TO_MPC)
            cx_mpc   = int(args.cx * PARSEC_TO_MPC)
            cy_mpc   = int(args.cy * PARSEC_TO_MPC)
            cz_mpc   = int(args.cz * PARSEC_TO_MPC)
            log.info(
                "Spatial filter: box centre (%g, %g, %g) pc, width %g pc "
                "→ (%d±%d, %d±%d, %d±%d) mpc",
                args.cx, args.cy, args.cz, args.width,
                cx_mpc, half_mpc, cy_mpc, half_mpc, cz_mpc, half_mpc,
            )
            pending = conn.execute(
                f"SELECT i.star_id, i.spectral, e.luminosity"
                f" FROM {SOURCE_TABLE} i"
                f" JOIN {SYSTEMS_TABLE} sys USING (system_id)"
                f" LEFT JOIN {EXTENDED_TABLE} e ON i.star_id = e.star_id"
                f" WHERE sys.x BETWEEN ? AND ?"
                f"   AND sys.y BETWEEN ? AND ?"
                f"   AND sys.z BETWEEN ? AND ?"
                f"   AND i.star_id NOT IN"
                f"     (SELECT DISTINCT orbit_star_id FROM {TARGET_TABLE}"
                f"      WHERE orbit_star_id IS NOT NULL)"
                f" ORDER BY i.star_id",
                (
                    cx_mpc - half_mpc, cx_mpc + half_mpc,
                    cy_mpc - half_mpc, cy_mpc + half_mpc,
                    cz_mpc - half_mpc, cz_mpc + half_mpc,
                ),
            ).fetchall()
        else:
            pending = conn.execute(
                f"SELECT i.star_id, i.spectral, e.luminosity"
                f" FROM {SOURCE_TABLE} i"
                f" LEFT JOIN {EXTENDED_TABLE} e ON i.star_id = e.star_id"
                f" WHERE i.star_id NOT IN"
                f"   (SELECT DISTINCT orbit_star_id FROM {TARGET_TABLE}"
                f"    WHERE orbit_star_id IS NOT NULL)"
                f" ORDER BY i.star_id"
            ).fetchall()

        if args.solitary_stars_only:
            before = len(pending)
            pending = [r for r in pending if r["star_id"] not in binary_cap]
            log.info(
                "Solitary-stars-only filter: %d → %d stars (removed %d in multiple systems)",
                before, len(pending), before - len(pending),
            )

        total = len(pending)
        log.info("Found %d stars to process", total)
        if total == 0:
            log.info("Nothing to do.")
            return

        processed = 0

        for row in pending:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info(
                    "Time limit reached after %d stars. Re-run to continue.",
                    processed,
                )
                return

            star_id = row["star_id"]
            spectral = row["spectral"] or ""
            spectral_letter = spectral[0].upper() if spectral else "G"
            lum = row["luminosity"] if row["luminosity"] and row["luminosity"] > 0 else 1.0

            # Apply binary stability cap
            stable_cap_au = binary_cap.get(star_id, PLANET_HILL_AU)
            if stable_cap_au < MIN_STABLE_AU:
                log.debug(
                    "star_id=%s: stable zone %.4f AU < %.4f AU minimum — skipping",
                    star_id, stable_cap_au, MIN_STABLE_AU,
                )
                processed += 1
                if processed % args.batch_size == 0:
                    conn.commit()
                    log.info("Progress: %d / %d stars", processed, total)
                continue

            n_planets = planet_count(spectral_letter)
            planets = [generate_planet(star_id, lum) for _ in range(n_planets)]
            # Clamp each planet's semi-major axis to the stable zone before sorting
            for p in planets:
                p["semi_major_axis"] = min(p["semi_major_axis"], stable_cap_au)
            planets.sort(key=lambda p: p["semi_major_axis"])
            planets = enforce_stability(planets, stable_cap_au)

            # HZ rocky bias: solitary F/G/K stars are guaranteed ≥1 Earth-sized
            # rocky planet (0.5–2.0 Mₑ) inside the habitable zone.
            hz_inner, hz_outer = hz_bounds(lum)
            if spectral_letter in "FGK" and star_id not in binary_cap:
                hz_ceil = min(hz_outer, stable_cap_au)
                has_hz_rocky = any(
                    p["in_hz"] == 1
                    and p["planet_class"] == "rocky"
                    and 0.5 <= p["mass"] <= 2.0
                    for p in planets
                )
                if not has_hz_rocky and hz_inner < hz_ceil:
                    mass = random.uniform(0.5, 2.0)
                    a = random.uniform(hz_inner, hz_ceil)
                    i_ang, lan, aop, ma = random_angles()
                    hz_rocky = {
                        "body_type": "planet",
                        "mass": mass,
                        "radius": radius_from_mass(mass),
                        "orbit_star_id": star_id,
                        "orbit_body_id": None,
                        "semi_major_axis": a,
                        "eccentricity": thermal_eccentricity(),
                        "inclination": i_ang,
                        "longitude_ascending_node": lan,
                        "argument_periapsis": aop,
                        "mean_anomaly": ma,
                        "epoch": 0,
                        "in_hz": 1,
                        "possible_tidal_lock": 1 if a < 0.5 * math.sqrt(lum) else 0,
                        "planet_class": "rocky",
                        "has_rings": 0,
                        "comp_metallic": None,
                        "comp_carbonaceous": None,
                        "comp_stony": None,
                        "span_inner_au": None,
                        "span_outer_au": None,
                    }
                    planets.append(hz_rocky)
                    planets.sort(key=lambda p: p["semi_major_axis"])
                    planets = enforce_stability(planets, stable_cap_au)

            for planet in planets:
                cur = conn.execute(INSERT_SQL, planet)
                planet_body_id = cur.lastrowid

                n_moons = moon_count(planet["mass"])
                if n_moons > 0:
                    moons = [generate_moon(planet_body_id, planet["mass"])
                             for _ in range(n_moons)]
                    moons.sort(key=lambda m: m["semi_major_axis"])
                    hill_au = (planet["mass"] ** (1.0 / 3.0)) * 0.01 * 0.5
                    moons = enforce_stability(moons, max(hill_au, 0.001))
                    for moon in moons:
                        conn.execute(INSERT_SQL, moon)

            # Generate asteroid belts and significant planetoids
            for center_au, belt_ecc in belt_positions(planets, lum):
                if center_au > stable_cap_au:
                    continue
                bmass = belt_mass_earth()
                conn.execute(INSERT_SQL, generate_belt(
                    star_id, center_au, belt_ecc, bmass, hz_inner, hz_outer, lum))
                for _ in range(planetoid_count()):
                    conn.execute(INSERT_SQL, generate_planetoid(
                        star_id, center_au, belt_ecc, bmass, hz_inner, hz_outer))

            processed += 1
            if processed % args.batch_size == 0:
                conn.commit()
                log.info("Progress: %d / %d stars", processed, total)

        conn.commit()
        log.info("Done. Processed %d stars.", processed)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
