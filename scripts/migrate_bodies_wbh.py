"""Add WBH generation columns to Bodies and create BeltProfile in starscape.db.

Idempotent — checks for existing columns before adding them.  Safe to run
multiple times.

Usage:
    uv run scripts/migrate_bodies_wbh.py
    uv run scripts/migrate_bodies_wbh.py --world /path/to/starscape.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

WORLD_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")

# (column_name, column_definition)  — order matters for readability only
NEW_BODIES_COLUMNS: list[tuple[str, str]] = [
    ("generation_source",   "TEXT CHECK(generation_source IN ('procedural','continuation_seed','manual'))"),
    ("orbit_num",           "REAL"),
    ("size_code",           "TEXT"),
    ("diameter_km",         "REAL"),
    ("composition",         "TEXT"),
    ("density",             "REAL"),
    ("gravity_g",           "REAL"),
    ("mass_earth",          "REAL"),
    ("escape_vel_kms",      "REAL"),
    ("albedo",              "REAL"),
    ("greenhouse_factor",   "REAL"),
    ("atm_code",            "TEXT"),
    ("pressure_bar",        "REAL"),
    ("ppo_bar",             "REAL"),
    ("gases",               "TEXT"),
    ("taint_type_1",        "TEXT"),
    ("taint_severity_1",    "INTEGER"),
    ("taint_persistence_1", "INTEGER"),
    ("taint_type_2",        "TEXT"),
    ("taint_severity_2",    "INTEGER"),
    ("taint_persistence_2", "INTEGER"),
    ("taint_type_3",        "TEXT"),
    ("taint_severity_3",    "INTEGER"),
    ("taint_persistence_3", "INTEGER"),
    ("mean_temp_k",         "REAL"),
    ("hydro_code",          "INTEGER"),
    ("hydro_pct",           "REAL"),
    ("sidereal_day_hours",  "REAL"),
    ("solar_day_hours",     "REAL"),
    ("axial_tilt_deg",      "REAL"),
    ("tidal_lock_status",   "TEXT CHECK(tidal_lock_status IN ('none','3:2','1:1','slow_prograde','slow_retrograde'))"),
    ("seismic_residual",    "REAL"),
    ("seismic_tidal",       "REAL"),
    ("seismic_heating",     "REAL"),
    ("seismic_total",       "REAL"),
    ("tectonic_plates",     "INTEGER"),
    ("biomass_rating",      "INTEGER"),
    ("moon_PD",             "REAL"),
    ("hill_PD",             "REAL"),
    ("roche_PD",            "REAL"),
]

BELT_PROFILE_DDL = """
CREATE TABLE IF NOT EXISTS "BeltProfile" (
    "body_id"          INTEGER PRIMARY KEY REFERENCES "Bodies"("body_id") ON DELETE CASCADE,
    "span_orbit_num"   REAL,
    "m_type_pct"       INTEGER,
    "s_type_pct"       INTEGER,
    "c_type_pct"       INTEGER,
    "other_pct"        INTEGER,
    "bulk"             INTEGER,
    "resource_rating"  INTEGER,
    "size1_bodies"     INTEGER,
    "sizeS_bodies"     INTEGER
);
"""


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def migrate(conn: sqlite3.Connection) -> None:
    have = existing_columns(conn, "Bodies")
    added = 0
    skipped = 0
    for col, defn in NEW_BODIES_COLUMNS:
        if col in have:
            skipped += 1
        else:
            conn.execute(f'ALTER TABLE "Bodies" ADD COLUMN "{col}" {defn}')
            print(f"  + Bodies.{col}")
            added += 1

    conn.executescript(BELT_PROFILE_DDL)

    conn.commit()
    print(f"\nBodies: {added} column(s) added, {skipped} already present.")
    print("BeltProfile: table created (or already exists).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--world", default=str(WORLD_DB), help="Path to starscape.db")
    args = parser.parse_args()

    world_path = Path(args.world)
    if not world_path.exists():
        sys.exit(f"starscape.db not found: {world_path}")

    conn = sqlite3.connect(str(world_path))
    conn.execute("PRAGMA foreign_keys = OFF")   # avoid FK issues during ALTER
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        migrate(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
