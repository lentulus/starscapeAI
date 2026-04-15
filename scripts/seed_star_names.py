"""Seed StarNames in game.db from specs/sources/Famous_sf_stars_20.csv.

Cross-indexes each HIP number in the CSV against IndexedIntegerDistinctStars
in starscape.db to obtain star_id and system_id, then inserts into the
StarNames table in game.db.

Sol (star_id=1, system_id=1030192) has no HIP entry in the Hipparcos catalog
and is not in the CSV; it is inserted manually.

Usage:
    uv run scripts/seed_star_names.py
    uv run scripts/seed_star_names.py --dry-run      # print rows, no writes
    uv run scripts/seed_star_names.py --game path/to/game.db
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH  = REPO_ROOT / "specs" / "sources" / "Famous_sf_stars_20.csv"
WORLD_DB  = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
GAME_DB   = REPO_ROOT / "game.db"

SOL_ROW = {
    "star_id":      1,
    "system_id":    1030192,
    "hip":          None,
    "common_name":  "Sol",
    "display_name": "Sol / The Sun",
    "sf_notes":     "Earth's star; origin system for Humans",
}


def lookup_star(world_conn: sqlite3.Connection, hip: str) -> tuple[int, int] | None:
    """Return (star_id, system_id) for a HIP number, or None if not found."""
    row = world_conn.execute(
        "SELECT star_id, system_id FROM IndexedIntegerDistinctStars WHERE hip = ?",
        (hip,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def build_rows(world_conn: sqlite3.Connection) -> list[dict]:
    rows: list[dict] = [SOL_ROW]
    missing: list[str] = []

    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            hip = record["HIP"].strip()
            if not hip:
                print(f"  SKIP (no HIP): {record['CommonName']}", file=sys.stderr)
                continue

            result = lookup_star(world_conn, hip)
            if result is None:
                missing.append(f"{record['CommonName']} (HIP {hip})")
                continue

            star_id, system_id = result
            rows.append({
                "star_id":      star_id,
                "system_id":    system_id,
                "hip":          hip,
                "common_name":  record["CommonName"].strip(),
                "display_name": record["DisplayName"].strip() or None,
                "sf_notes":     record["FamousInSF"].strip() or None,
            })

    if missing:
        print(f"\nWARNING: {len(missing)} HIP number(s) not found in starscape.db:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)

    return rows


def seed(game_conn: sqlite3.Connection, rows: list[dict], dry_run: bool) -> None:
    if dry_run:
        print(f"{'name_id':>4}  {'star_id':>9}  {'system_id':>10}  {'hip':>8}  common_name")
        print("-" * 72)
        for i, r in enumerate(rows, 1):
            print(
                f"{i:>4}  {r['star_id']:>9}  {r['system_id']:>10}"
                f"  {r['hip'] or '':>8}  {r['common_name']}"
            )
        print(f"\n{len(rows)} row(s) would be inserted.")
        return

    inserted = 0
    skipped  = 0
    for r in rows:
        try:
            game_conn.execute(
                """
                INSERT OR IGNORE INTO StarNames
                    (star_id, system_id, hip, common_name, display_name, sf_notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (r["star_id"], r["system_id"], r["hip"],
                 r["common_name"], r["display_name"], r["sf_notes"]),
            )
            if game_conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
            else:
                skipped += 1
        except sqlite3.Error as exc:
            print(f"  ERROR inserting {r['common_name']}: {exc}", file=sys.stderr)

    game_conn.commit()
    print(f"StarNames: {inserted} inserted, {skipped} already present.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game",    default=str(GAME_DB), help="Path to game.db")
    parser.add_argument("--world",   default=str(WORLD_DB), help="Path to starscape.db")
    parser.add_argument("--dry-run", action="store_true", help="Print rows without writing")
    args = parser.parse_args()

    world_path = Path(args.world)
    game_path  = Path(args.game)

    if not world_path.exists():
        sys.exit(f"starscape.db not found: {world_path}")
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    world_conn = sqlite3.connect(str(world_path))

    if args.dry_run:
        rows = build_rows(world_conn)
        seed(None, rows, dry_run=True)
        return

    if not game_path.exists():
        sys.exit(f"game.db not found: {game_path}  (run init_game first, or create with open_game)")

    game_conn = sqlite3.connect(str(game_path))
    game_conn.execute("PRAGMA foreign_keys = ON")

    # Ensure the table exists (idempotent).
    schema_sql = (REPO_ROOT / "sql" / "schema_game.sql").read_text()
    game_conn.executescript(schema_sql)

    rows = build_rows(world_conn)
    seed(game_conn, rows, dry_run=False)

    world_conn.close()
    game_conn.close()


if __name__ == "__main__":
    main()
