#!/usr/bin/env python3
"""Compute stellar physical parameters and populate DistinctStarsExtended.

For each star in IndexedIntegerDistinctStars not yet present in DistinctStarsExtended,
derives mass, temperature, radius, luminosity, and age from B-V color index and
absolute visual magnitude. Rows that cannot be computed are inserted with mass=-1
and logged.

Supports resuming: already-present star_ids are skipped.
Stops cleanly after --max-minutes elapsed time; re-run to continue.

Usage:
    uv run scripts/compute_metrics.py
    uv run scripts/compute_metrics.py --db /path/to/other.db
    uv run scripts/compute_metrics.py --batch-size 500 --max-minutes 30
"""

import argparse
import logging
import sqlite3
import time
from pathlib import Path

from starscape5.metrics import MetricsError, compute_metrics

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
SOURCE_TABLE = "IndexedIntegerDistinctStars"
TARGET_TABLE = "DistinctStarsExtended"
DEFAULT_BATCH = 1000
DEFAULT_MAX_MINUTES = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Rows between commits (default: %(default)s)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                        help="Stop after this many elapsed minutes (default: %(default)s)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        # Fetch all stars not yet processed, or previously failed (mass = -1)
        pending = conn.execute(
            f"SELECT i.star_id, i.ci, i.absmag, i.spectral"
            f" FROM {SOURCE_TABLE} i"
            f" LEFT JOIN {TARGET_TABLE} e ON i.star_id = e.star_id"
            f" WHERE e.star_id IS NULL OR e.mass = -1"
            f" ORDER BY i.star_id"
        ).fetchall()

        total = len(pending)
        log.info("Found %d stars to process", total)
        if total == 0:
            log.info("Nothing to do.")
            return

        processed = 0
        errors = 0

        for row in pending:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info(
                    "Time limit reached after %d rows (%d errors). Re-run to continue.",
                    processed, errors,
                )
                return

            star_id = row["star_id"]
            ci = row["ci"]
            absmag = row["absmag"]
            spectral = row["spectral"]

            try:
                m = compute_metrics(ci, absmag, spectral)
                conn.execute(
                    f"INSERT OR REPLACE INTO {TARGET_TABLE}"
                    f" (star_id, mass, temperature, radius, luminosity, age, temp_source)"
                    f" VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (star_id, m["mass"], m["temperature"],
                     m["radius"], m["luminosity"], m["age"], m["temp_source"]),
                )
            except MetricsError as exc:
                log.error("star_id=%s ci=%s spectral=%s: %s", star_id, ci, spectral, exc)
                conn.execute(
                    f"INSERT OR REPLACE INTO {TARGET_TABLE}"
                    f" (star_id, mass, temperature, radius, luminosity, age, temp_source)"
                    f" VALUES (?, -1, NULL, NULL, NULL, NULL, NULL)",
                    (star_id,),
                )
                errors += 1

            processed += 1
            if processed % args.batch_size == 0:
                conn.commit()
                log.info("Progress: %d / %d rows, %d errors", processed, total, errors)

        conn.commit()
        log.info("Complete. Processed %d rows, %d errors.", processed, errors)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
