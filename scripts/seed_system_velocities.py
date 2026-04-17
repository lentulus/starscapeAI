"""Populate SystemVelocities from hygdata_v42 vx/vy/vz columns.

For each system the primary star (MIN star_id) is joined to hygdata_v42 via
hip.  Systems with no matching HYG row are skipped.  Sol is inserted explicitly
as (0, 0, 0) because its catalog star has a blank hip.

Units: vx/vy/vz are parsecs per year (pc/yr) in the ICRS frame.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help="Path to starscape.db (default: %(default)s)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        # Create table if it doesn't exist yet (idempotent).
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS "SystemVelocities" (
                "system_id"      INTEGER PRIMARY KEY
                                 REFERENCES "IndexedIntegerDistinctSystems"("system_id"),
                "vx"             REAL NOT NULL,
                "vy"             REAL NOT NULL,
                "vz"             REAL NOT NULL,
                "source_star_id" INTEGER
            );
        """)

        # Sol: star_id=1 has a blank hip so cannot be joined; insert 0,0,0 manually.
        sol_row = conn.execute(
            "SELECT system_id FROM IndexedIntegerDistinctStars WHERE star_id = 1"
        ).fetchone()
        if sol_row is None:
            log.warning("star_id=1 not found — Sol row skipped")
        else:
            sol_system_id = sol_row[0]
            conn.execute(
                "INSERT OR REPLACE INTO SystemVelocities"
                " (system_id, vx, vy, vz, source_star_id, velocity_source)"
                " VALUES (?, 0.0, 0.0, 0.0, NULL, 'manual')",
                (sol_system_id,),
            )
            log.info("Sol system_id=%d inserted as (0, 0, 0)", sol_system_id)

        # All other systems: use primary star (MIN star_id per system) joined to HYG.
        # Skip if primary star has no hip or no matching HYG row.
        inserted = conn.execute("""
            INSERT OR IGNORE INTO SystemVelocities
                (system_id, vx, vy, vz, source_star_id, velocity_source)
            SELECT
                s.system_id,
                h.vx,
                h.vy,
                h.vz,
                s.star_id,
                'catalog'
            FROM IndexedIntegerDistinctStars s
            JOIN (
                -- One row per system: the primary star (lowest star_id)
                SELECT system_id, MIN(star_id) AS star_id
                FROM IndexedIntegerDistinctStars
                WHERE hip IS NOT NULL AND hip != ''
                GROUP BY system_id
            ) primary_stars USING (system_id, star_id)
            JOIN hygdata_v42 h ON h.hip = s.hip
            WHERE h.vx IS NOT NULL
              AND h.vy IS NOT NULL
              AND h.vz IS NOT NULL
        """).rowcount

        conn.commit()
        log.info("Inserted %d system velocity rows (excluding Sol).", inserted)

        total = conn.execute("SELECT COUNT(*) FROM SystemVelocities").fetchone()[0]
        log.info("Total rows in SystemVelocities: %d", total)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
