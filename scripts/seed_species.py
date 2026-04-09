#!/usr/bin/env python3
"""Seed the Species table with the 11 hand-authored sophont species.

homeworld_body_id is left NULL for all rows; it must be updated once homeworld
bodies are identified in the Bodies table (Earth is seeded by seed_sol.py).

Usage:
    uv run scripts/seed_species.py
    uv run scripts/seed_species.py --db /path/to/other.db
    uv run scripts/seed_species.py --force   # re-seed even if rows already exist
"""

import argparse
import logging
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Species data
# Columns (in order):
#   name, homeworld_body_id,
#   body_plan, locomotion, avg_mass_kg, avg_height_m, lifespan_years,
#   temp_min_k, temp_max_k, pressure_min_atm, pressure_max_atm, atm_req,
#   diet_type, diet_flexibility, metabolic_rate,
#   repro_strategy, gestation_years, maturity_years, offspring_per_cycle, repro_cycles_per_life,
#   risk_appetite, aggression, expansionism, xenophilia, adaptability,
#   social_cohesion, hierarchy_tolerance, faction_tendency, grievance_memory
# ---------------------------------------------------------------------------

SPECIES = [
    # --- Kreeth (source: Arachnid / Bug, Starship Troopers) ---
    (
        "Kreeth", None,
        "radial", "hexapedal", 90.0, 1.2, 12.0,
        260.0, 320.0, 0.5, 2.5, "reducing",
        "omnivore", 0.80, "high",
        "r_strategist", 0.05, 1.0, 80.0, 5.0,
        0.40, 0.95, 0.90, 0.02, 0.55,
        0.98, 1.00, 0.02, 0.85,
    ),
    # --- Vashori (source: Osirian, Viagens Interplanetarias) ---
    (
        "Vashori", None,
        "bilateral", "bipedal", 80.0, 1.75, 120.0,
        290.0, 345.0, 0.7, 1.8, "n2o2",
        "carnivore", 0.50, "low",
        "k_strategist", 0.5, 18.0, 3.0, 6.0,
        0.60, 0.40, 0.30, 0.85, 0.70,
        0.70, 0.65, 0.55, 0.70,
    ),
    # --- Kraathi (source: K'Kree, Traveller) ---
    (
        "Kraathi", None,
        "centauroid", "quadrupedal", 450.0, 2.0, 80.0,
        278.0, 330.0, 0.8, 1.5, "n2o2",
        "herbivore", 0.20, "medium",
        "k_strategist", 0.75, 20.0, 1.0, 4.0,
        0.45, 0.75, 0.95, 0.10, 0.20,
        0.95, 0.90, 0.20, 0.90,
    ),
    # --- Nakhavi (source: Octopod, Children of Ruin) ---
    (
        "Nakhavi", None,
        "cephalopod", "jet_aquatic", 12.0, 0.6, 18.0,
        273.0, 305.0, 1.0, 20.0, "aquatic",
        "carnivore", 0.45, "high",
        "r_strategist", 0.08, 2.0, 200.0, 1.0,
        0.80, 0.45, 0.40, 0.90, 0.95,
        0.25, 0.10, 0.15, 0.35,
    ),
    # --- Skharri (source: Kzin, Known Space) ---
    (
        "Skharri", None,
        "bilateral", "bipedal", 160.0, 2.4, 200.0,
        270.0, 330.0, 0.7, 1.8, "n2o2",
        "carnivore", 0.20, "high",
        "k_strategist", 0.6, 15.0, 2.0, 8.0,
        0.90, 0.95, 0.90, 0.05, 0.45,
        0.80, 0.95, 0.65, 0.95,
    ),
    # --- Vaelkhi (source: Ythrian, Technic History) ---
    (
        "Vaelkhi", None,
        "avian", "winged_flight", 50.0, 1.3, 80.0,
        265.0, 320.0, 0.5, 1.4, "n2o2",
        "carnivore", 0.25, "very_high",
        "k_strategist", 0.3, 16.0, 2.0, 5.0,
        0.70, 0.55, 0.30, 0.45, 0.55,
        0.70, 0.50, 0.45, 0.65,
    ),
    # --- Shekhari (source: Cynthian, Polesotechnic League) ---
    (
        "Shekhari", None,
        "bilateral", "arboreal", 10.0, 0.55, 90.0,
        268.0, 318.0, 0.7, 1.6, "n2o2",
        "omnivore", 0.75, "high",
        "k_strategist", 0.25, 12.0, 2.0, 6.0,
        0.75, 0.45, 0.55, 0.55, 0.85,
        0.40, 0.35, 0.25, 0.55,
    ),
    # --- Golvhaan (source: Wodenite, Polesotechnic League) ---
    (
        "Golvhaan", None,
        "draconic", "quadrupedal", 700.0, 2.2, 150.0,
        270.0, 325.0, 0.8, 2.5, "n2o2",
        "omnivore", 0.90, "medium",
        "k_strategist", 1.0, 25.0, 1.0, 5.0,
        0.45, 0.30, 0.35, 0.80, 0.65,
        0.55, 0.50, 0.30, 0.40,
    ),
    # --- Nhaveth (original — neural parasite) ---
    (
        "Nhaveth", None,
        "vermiform", "vermiform", 1.5, 0.6, 600.0,
        280.0, 320.0, 0.8, 1.6, "n2o2",
        "parasite", 0.30, "low",
        "r_strategist", 0.1, 5.0, 75.0, 3.0,
        0.55, 0.85, 0.90, 0.08, 0.40,
        0.25, 0.95, 0.90, 1.00,
    ),
    # --- Vardhek (source: Merseian, Technic History / Flandry Cycle) ---
    (
        "Vardhek", None,
        "bilateral", "bipedal", 110.0, 2.1, 110.0,
        275.0, 330.0, 0.8, 2.0, "n2o2",
        "omnivore", 0.65, "medium",
        "k_strategist", 0.7, 20.0, 2.0, 5.0,
        0.35, 0.70, 0.95, 0.20, 0.75,
        0.85, 0.88, 0.35, 0.85,
    ),
    # --- Human (Homo sapiens) ---
    (
        "Human", None,
        "bilateral", "bipedal", 70.0, 1.75, 80.0,
        283.0, 313.0, 0.5, 2.0, "n2o2",
        "omnivore", 0.85, "medium",
        "k_strategist", 0.75, 16.0, 1.0, 20.0,
        0.65, 0.55, 0.80, 0.50, 0.90,
        0.25, 0.45, 0.90, 0.60,
    ),
]

INSERT_SQL = """
INSERT INTO "Species" (
    name, homeworld_body_id,
    body_plan, locomotion, avg_mass_kg, avg_height_m, lifespan_years,
    temp_min_k, temp_max_k, pressure_min_atm, pressure_max_atm, atm_req,
    diet_type, diet_flexibility, metabolic_rate,
    repro_strategy, gestation_years, maturity_years, offspring_per_cycle, repro_cycles_per_life,
    risk_appetite, aggression, expansionism, xenophilia, adaptability,
    social_cohesion, hierarchy_tolerance, faction_tendency, grievance_memory
) VALUES (
    ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?
)
"""


def seed(db_path: Path, force: bool) -> None:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")

    existing = con.execute("SELECT COUNT(*) FROM Species").fetchone()[0]
    if existing and not force:
        log.info("Species table already has %d rows; skipping (use --force to re-seed).", existing)
        con.close()
        return

    if force and existing:
        log.info("--force: deleting %d existing Species rows.", existing)
        con.execute("DELETE FROM Species")

    inserted = 0
    for row in SPECIES:
        con.execute(INSERT_SQL, row)
        log.info("  inserted: %s", row[0])
        inserted += 1

    con.commit()
    con.close()
    log.info("Done. %d species inserted.", inserted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Species table.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database.")
    parser.add_argument("--force", action="store_true", help="Delete existing rows before inserting.")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    seed(args.db, args.force)


if __name__ == "__main__":
    main()
