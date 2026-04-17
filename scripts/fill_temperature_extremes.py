#!/usr/bin/env python3
"""Backfill high_temp_k and low_temp_k for all already-generated Bodies rows.

Computes WBH pp.112-114 high and low temperatures for every rocky planet and
moon where high_temp_k is still NULL.

Planets join DistinctStarsExtended directly via orbit_star_id.
Moons join their parent planet for semi_major_axis and eccentricity (WBH
requires parent planet's orbital parameters for moon temperature), then
DistinctStarsExtended via the parent's orbit_star_id.

Prerequisites
-------------
The two columns must exist.  Run migrate_bodies_wbh.py first if absent:
    uv run scripts/migrate_bodies_wbh.py

Usage
-----
    uv run scripts/fill_temperature_extremes.py
    uv run scripts/fill_temperature_extremes.py --max-minutes 120
    uv run scripts/fill_temperature_extremes.py --batch-size 5000 --verbose
    caffeinate -i uv run scripts/fill_temperature_extremes.py --max-minutes 480
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_planets_wbh as _gpw

DEFAULT_DB          = Path("/Volumes/Data/starscape4/starscape.db")
DEFAULT_BATCH       = 10_000
DEFAULT_MAX_MINUTES = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fetch queries
# ---------------------------------------------------------------------------

# Rocky planets: use planet's own semi_major_axis and eccentricity
_FETCH_PLANETS_SQL = """
SELECT
    b.body_id,
    b.albedo,
    b.greenhouse_factor,
    b.semi_major_axis,
    b.eccentricity,
    b.axial_tilt_deg,
    b.solar_day_hours,
    b.tidal_lock_status,
    b.hydro_code,
    b.pressure_bar,
    COALESCE(dse.luminosity, 1.0)   AS luminosity_lsun,
    COALESCE(dse.mass,       1.0)   AS star_mass_msol
FROM  Bodies b
LEFT  JOIN DistinctStarsExtended dse ON dse.star_id = b.orbit_star_id
WHERE b.high_temp_k IS NULL
  AND b.albedo IS NOT NULL
  AND b.greenhouse_factor IS NOT NULL
  AND b.planet_class = 'rocky'
  AND b.orbit_star_id IS NOT NULL
LIMIT :batch_size
"""

# Moons: use parent planet's semi_major_axis and eccentricity (WBH)
_FETCH_MOONS_SQL = """
SELECT
    b.body_id,
    b.albedo,
    b.greenhouse_factor,
    p.semi_major_axis,
    p.eccentricity,
    b.axial_tilt_deg,
    b.solar_day_hours,
    b.tidal_lock_status,
    b.hydro_code,
    b.pressure_bar,
    COALESCE(dse.luminosity, 1.0)   AS luminosity_lsun,
    COALESCE(dse.mass,       1.0)   AS star_mass_msol
FROM  Bodies b
JOIN  Bodies p   ON p.body_id       = b.orbit_body_id
LEFT  JOIN DistinctStarsExtended dse ON dse.star_id = p.orbit_star_id
WHERE b.high_temp_k IS NULL
  AND b.albedo IS NOT NULL
  AND b.greenhouse_factor IS NOT NULL
  AND b.orbit_body_id IS NOT NULL
LIMIT :batch_size
"""

_UPDATE_SQL = """
UPDATE Bodies SET high_temp_k = :high_temp_k, low_temp_k = :low_temp_k
WHERE body_id = :body_id
"""


def _compute_row(row: sqlite3.Row) -> dict | None:
    (body_id, albedo, greenhouse_factor,
     semi_major_axis, eccentricity,
     axial_tilt_deg, solar_day_hours, tidal_lock_status,
     hydro_code, pressure_bar,
     luminosity_lsun, star_mass_msol) = row

    if semi_major_axis is None or semi_major_axis <= 0:
        return None

    high_k, low_k = _gpw._high_low_temp_k(
        luminosity_lsun  = float(luminosity_lsun),
        albedo           = float(albedo),
        greenhouse_factor = float(greenhouse_factor),
        semi_major_axis_au = float(semi_major_axis),
        eccentricity     = float(eccentricity or 0.0),
        axial_tilt_deg   = float(axial_tilt_deg or 0.0),
        solar_day_hours  = float(solar_day_hours) if solar_day_hours is not None else None,
        tidal_lock_status = tidal_lock_status,
        hydro_code       = int(hydro_code) if hydro_code is not None else None,
        pressure_bar     = float(pressure_bar) if pressure_bar is not None else None,
        star_mass_msol   = float(star_mass_msol),
    )

    if high_k is None:
        return None

    return {"body_id": body_id, "high_temp_k": high_k, "low_temp_k": low_k}


def _run_pass(
    conn: sqlite3.Connection,
    fetch_sql: str,
    label: str,
    batch_size: int,
    deadline: float,
    verbose: bool,
) -> int:
    total = 0
    while time.monotonic() < deadline:
        rows = conn.execute(fetch_sql, {"batch_size": batch_size}).fetchall()
        if not rows:
            log.info("%s: no more rows — done.", label)
            break

        updates = [r for r in (_compute_row(row) for row in rows) if r is not None]
        if updates:
            conn.executemany(_UPDATE_SQL, updates)
            conn.commit()
        total += len(rows)

        if verbose:
            log.info("%s batch: %d rows  |  total so far: %d", label, len(rows), total)
        else:
            log.info("%s: updated %d rows (total %d)", label, len(rows), total)

    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    cols = {r[1] for r in conn.execute("PRAGMA table_info(Bodies)").fetchall()}
    if "high_temp_k" not in cols:
        sys.exit(
            "ERROR: Bodies.high_temp_k column missing.\n"
            "Run:  uv run scripts/migrate_bodies_wbh.py"
        )

    deadline = time.monotonic() + args.max_minutes * 60.0

    try:
        p_total = _run_pass(conn, _FETCH_PLANETS_SQL, "planets",
                            args.batch_size, deadline, args.verbose)
        m_total = _run_pass(conn, _FETCH_MOONS_SQL,   "moons",
                            args.batch_size, deadline, args.verbose)
    finally:
        conn.close()

    log.info("fill_temperature_extremes complete: %d planets, %d moons updated.",
             p_total, m_total)


if __name__ == "__main__":
    main()
