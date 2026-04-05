#!/usr/bin/env python3
"""Fill NULL spectral types in IndexedIntegerDistinctStars.

For each star with a NULL spectral column:
  - Derives a spectral type from B-V color index and absolute magnitude.
  - Optionally creates a companion star based on survey multiplicity rates.

Usage:
    uv run scripts/fill_spectral.py
    uv run scripts/fill_spectral.py --db /path/to/other.db
    uv run scripts/fill_spectral.py --batch-size 500 --dry-run
"""

import argparse
import logging
import sqlite3
from pathlib import Path

from starscape5.spectral import (
    ci_from_absmag,
    companion_absmag,
    format_spectral,
    should_create_multiple,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
TABLE = "IndexedIntegerDistinctStars"
DEFAULT_BATCH = 1000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _load_multi_system_ids(conn: sqlite3.Connection) -> set[int]:
    """Return the set of system_ids that already contain more than one star."""
    rows = conn.execute(
        f"SELECT system_id FROM {TABLE} GROUP BY system_id HAVING COUNT(*) > 1"
    ).fetchall()
    return {row[0] for row in rows}


def _max_star_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(f"SELECT MAX(star_id) FROM {TABLE}").fetchone()
    return row[0] or 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Rows between commits (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and log changes without writing to the database")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        # Load all rows that need spectral types
        null_rows = conn.execute(
            f"SELECT system_id, star_id, ci, absmag"
            f" FROM {TABLE} WHERE spectral IS NULL"
            f" ORDER BY system_id, star_id"
        ).fetchall()

        total_null = len(null_rows)
        log.info("Found %d rows with NULL spectral", total_null)
        if total_null == 0:
            log.info("Nothing to do.")
            return

        # Pre-build the set of already-multiple system_ids to avoid per-row queries
        multi_systems: set[int] = _load_multi_system_ids(conn)
        log.info("Found %d existing multiple systems", len(multi_systems))

        next_star_id = _max_star_id(conn) + 1
        updated = 0
        companions_added = 0

        for row in null_rows:
            system_id = row["system_id"]
            star_id = row["star_id"]
            ci = row["ci"]
            absmag = row["absmag"]

            # 1. Derive spectral type
            spectral = format_spectral(ci, absmag)

            if not args.dry_run:
                conn.execute(
                    f"UPDATE {TABLE} SET spectral = ?, source = 'derived'"
                    f" WHERE star_id = ?",
                    (spectral, star_id),
                )

            # 2. Maybe create a companion for singleton stars
            if system_id not in multi_systems and should_create_multiple(spectral):
                comp_absmag = companion_absmag(absmag)
                comp_ci = ci_from_absmag(comp_absmag)
                comp_spectral = format_spectral(f"{comp_ci:.4f}", comp_absmag)

                if not args.dry_run:
                    conn.execute(
                        f"INSERT INTO {TABLE}"
                        f" (system_id, star_id, ci, absmag, spectral, source)"
                        f" VALUES (?, ?, ?, ?, ?, 'generated')",
                        (system_id, next_star_id, f"{comp_ci:.4f}", comp_absmag, comp_spectral),
                    )

                # Mark this system as multiple so we don't double-add
                multi_systems.add(system_id)
                next_star_id += 1
                companions_added += 1

            updated += 1
            if updated % args.batch_size == 0:
                if not args.dry_run:
                    conn.commit()
                log.info(
                    "Progress: %d / %d rows processed, %d companions added",
                    updated, total_null, companions_added,
                )

        if not args.dry_run:
            conn.commit()

        log.info(
            "%s complete. Updated %d spectral types, added %d companion stars.",
            "Dry-run" if args.dry_run else "Run",
            updated,
            companions_added,
        )

    except Exception:
        if not args.dry_run:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
