#!/usr/bin/env python3
"""Populate BodyMutable with atmospheric and hydrospheric state for rocky bodies.

Also back-fills three immutable physical properties on Bodies rows
(surface_gravity, escape_velocity_kms, t_eq_k) that require a DB join to
DistinctStarsExtended.  These are computed here rather than at planet
generation time to keep generate_planets.py free of luminosity joins for moons.

Processing order:
1. Rocky planets — join directly to DistinctStarsExtended for luminosity.
2. Moons — join through parent planet to get star luminosity; use parent
   planet's semi_major_axis for T_eq; apply tidal heating bonus for inner
   moons of gas giants.

Gas giants and belt/planetoid rows are skipped (no meaningful surface state).

Supports resuming: bodies already in BodyMutable are skipped.
Stops cleanly after --max-minutes; re-run to continue.

Usage:
    uv run scripts/generate_atmosphere.py
    uv run scripts/generate_atmosphere.py --db /path/to/other.db
    uv run scripts/generate_atmosphere.py --max-minutes 120
"""

import argparse
import logging
import sqlite3
import time
from pathlib import Path

from starscape5.atmosphere import (
    atm_composition,
    atm_pressure_atm,
    classify_atm,
    escape_velocity_kms,
    hydrosphere,
    surface_gravity,
    surface_temp_k,
    t_eq_k,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
TARGET_TABLE = "BodyMutable"
DEFAULT_MAX_MINUTES = 120
DEFAULT_BATCH = 500

# Inner GG moons closer than this (AU from parent) receive a tidal heating bonus
_TIDAL_HEAT_AU = 0.01
_TIDAL_HEAT_MIN_K = 10.0
_TIDAL_HEAT_MAX_K = 40.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INSERT_MUTABLE_SQL = (
    f"INSERT OR REPLACE INTO \"{TARGET_TABLE}\""
    " (body_id, atm_type, atm_pressure_atm, atm_composition,"
    "  surface_temp_k, hydrosphere, epoch)"
    " VALUES (:body_id, :atm_type, :atm_pressure_atm, :atm_composition,"
    "  :surface_temp_k, :hydrosphere, 0)"
)

UPDATE_BODIES_SQL = (
    "UPDATE Bodies SET"
    "  surface_gravity = :sg,"
    "  escape_velocity_kms = :v_esc,"
    "  t_eq_k = :t_eq"
    " WHERE body_id = :body_id"
)

# --- Queries ------------------------------------------------------------------

# Rocky planets: direct join to star luminosity
_PLANET_QUERY = """
    SELECT
        b.body_id,
        b.mass,
        b.radius,
        b.semi_major_axis      AS a_au,
        b.in_hz,
        b.possible_tidal_lock,
        b.planet_class,
        NULL                   AS moon_a_au,
        NULL                   AS parent_planet_class,
        COALESCE(e.luminosity, 1.0) AS luminosity
    FROM Bodies b
    LEFT JOIN DistinctStarsExtended e ON b.orbit_star_id = e.star_id
    WHERE b.body_type = 'planet'
      AND b.planet_class = 'rocky'
      AND b.body_id NOT IN (SELECT body_id FROM "{target}")
    ORDER BY b.body_id
""".format(target=TARGET_TABLE)

# Moons: join through parent planet to star
_MOON_QUERY = """
    SELECT
        b.body_id,
        b.mass,
        b.radius,
        b.semi_major_axis      AS moon_a_au,   -- distance from parent (for tidal threshold)
        p.semi_major_axis      AS a_au,         -- parent's distance from star (for T_eq)
        p.in_hz,
        b.possible_tidal_lock,
        b.planet_class,
        p.planet_class         AS parent_planet_class,
        COALESCE(e.luminosity, 1.0) AS luminosity
    FROM Bodies b
    JOIN Bodies p    ON b.orbit_body_id = p.body_id
    LEFT JOIN DistinctStarsExtended e ON p.orbit_star_id = e.star_id
    WHERE b.body_type = 'moon'
      AND b.body_id NOT IN (SELECT body_id FROM "{target}")
    ORDER BY b.body_id
""".format(target=TARGET_TABLE)


def _process_row(conn: sqlite3.Connection, row: sqlite3.Row, is_moon: bool) -> None:
    """Compute physical properties and write Bodies UPDATE + BodyMutable INSERT."""
    body_id    = row["body_id"]
    mass       = row["mass"] or 0.0
    radius     = row["radius"] or 1.0
    a_au       = row["a_au"] or 1.0
    lum        = row["luminosity"]
    in_hz      = row["in_hz"]
    tidal_lock = row["possible_tidal_lock"]
    parent_cls = row["parent_planet_class"]

    if mass <= 0.0 or radius <= 0.0:
        return

    # --- Immutable physical properties ---
    sg    = surface_gravity(mass, radius)
    v_esc = escape_velocity_kms(mass, radius)
    teq   = t_eq_k(lum, a_au)

    # Tidal heating bonus for close-in moons of gas giants
    if is_moon:
        moon_a = row["moon_a_au"] or 0.0
        if moon_a < _TIDAL_HEAT_AU and parent_cls in ("small_gg", "medium_gg", "large_gg"):
            import random
            teq += random.uniform(_TIDAL_HEAT_MIN_K, _TIDAL_HEAT_MAX_K)

    conn.execute(UPDATE_BODIES_SQL, {
        "sg": sg, "v_esc": v_esc, "t_eq": teq, "body_id": body_id,
    })

    # --- BodyMutable atmosphere / hydrosphere ---
    atm    = classify_atm(v_esc, teq, in_hz, tidal_lock)
    comp   = atm_composition(atm, teq)
    press  = atm_pressure_atm(atm)
    s_temp = surface_temp_k(teq, atm)
    hydro  = hydrosphere(atm, in_hz, s_temp)

    conn.execute(INSERT_MUTABLE_SQL, {
        "body_id":          body_id,
        "atm_type":         atm,
        "atm_pressure_atm": press,
        "atm_composition":  comp,
        "surface_temp_k":   s_temp,
        "hydrosphere":      hydro,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                        help="Stop after this many elapsed minutes (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Bodies between commits (default: %(default)s)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS \"{TARGET_TABLE}\" ("
            "  body_id          INTEGER PRIMARY KEY REFERENCES Bodies(body_id),"
            "  atm_type         TEXT,"
            "  atm_pressure_atm REAL,"
            "  atm_composition  TEXT,"
            "  surface_temp_k   REAL,"
            "  hydrosphere      REAL,"
            "  epoch            INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.commit()

        # --- Pass 1: rocky planets ---
        planets = conn.execute(_PLANET_QUERY).fetchall()
        log.info("Found %d rocky planets to process", len(planets))

        processed = 0
        for row in planets:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info("Time limit reached after %d bodies. Re-run to continue.", processed)
                return
            _process_row(conn, row, is_moon=False)
            processed += 1
            if processed % args.batch_size == 0:
                conn.commit()
                log.info("Planets progress: %d / %d", processed, len(planets))

        conn.commit()
        log.info("Planets done: %d processed", processed)

        # --- Pass 2: moons ---
        moons = conn.execute(_MOON_QUERY).fetchall()
        log.info("Found %d moons to process", len(moons))

        processed = 0
        for row in moons:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info("Time limit reached after %d moons. Re-run to continue.", processed)
                return
            _process_row(conn, row, is_moon=True)
            processed += 1
            if processed % args.batch_size == 0:
                conn.commit()
                log.info("Moons progress: %d / %d", processed, len(moons))

        conn.commit()
        log.info("Moons done: %d processed", processed)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
