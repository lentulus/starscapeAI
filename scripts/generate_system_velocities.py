"""Generate synthetic space velocities for systems not in SystemVelocities.

For each system that has no row in SystemVelocities (i.e. no Hipparcos proper-
motion data), a plausible (vx, vy, vz) is derived from:

  - Stellar age (DistinctStarsExtended.age, years)
  - Spectral type (IndexedIntegerDistinctStars.spectral)
  - Galactic height z (IndexedIntegerDistinctSystems.z, milli-parsecs)

via the age-velocity dispersion relation and galactic-population assignment
in src/starscape5/velocities.py.

Rows are tagged velocity_source = 'synthetic'.
Catalog and manual rows (seeded by seed_system_velocities.py) are not touched.

Resume: the script skips systems already in SystemVelocities (INSERT OR IGNORE),
so it is safe to interrupt and re-run.  Use --max-minutes to cap wall-clock time.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from pathlib import Path

from starscape5.velocities import generate_velocity

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
DEFAULT_BATCH = 10_000
DEFAULT_MAX_MINUTES = 60.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fetch query
# ---------------------------------------------------------------------------
# Streams systems that have no SystemVelocities row, joining in the primary
# star's spectral type and age.  Primary star = MIN(star_id) per system.
# LEFT JOIN on DistinctStarsExtended — age may be NULL for some stars.
# ---------------------------------------------------------------------------
_FETCH_SQL = """
SELECT
    sys.system_id,
    sys.z,
    s.spectral,
    e.age
FROM IndexedIntegerDistinctSystems sys
JOIN (
    SELECT system_id, MIN(star_id) AS star_id
    FROM IndexedIntegerDistinctStars
    GROUP BY system_id
) prim ON prim.system_id = sys.system_id
JOIN IndexedIntegerDistinctStars s ON s.star_id = prim.star_id
LEFT JOIN DistinctStarsExtended e ON e.star_id = prim.star_id
LEFT JOIN SystemVelocities sv ON sv.system_id = sys.system_id
WHERE sv.system_id IS NULL
ORDER BY sys.system_id
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO SystemVelocities
    (system_id, vx, vy, vz, source_star_id, velocity_source)
VALUES
    (?, ?, ?, ?, NULL, 'synthetic')
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help="Path to starscape.db (default: %(default)s)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help="Rows committed per transaction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
        help="Stop after N elapsed minutes; re-run to resume (default: %(default)s)",
    )
    args = parser.parse_args()

    deadline = time.monotonic() + args.max_minutes * 60.0

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -65536")   # 64 MB page cache

    try:
        total_missing = conn.execute(
            "SELECT COUNT(*) FROM IndexedIntegerDistinctSystems sys"
            " LEFT JOIN SystemVelocities sv ON sv.system_id = sys.system_id"
            " WHERE sv.system_id IS NULL"
        ).fetchone()[0]
        log.info("%d systems need synthetic velocities", total_missing)

        # Stream results so we never hold the full 8M-row result in memory.
        fetch_cur = conn.execute(_FETCH_SQL)

        inserted = 0
        batch: list[tuple] = []

        def flush(cur_conn: sqlite3.Connection) -> None:
            nonlocal inserted
            cur_conn.executemany(_INSERT_SQL, batch)
            cur_conn.commit()
            inserted += len(batch)
            batch.clear()

        for row in fetch_cur:
            if time.monotonic() >= deadline:
                log.info("Time limit reached — flushing and stopping.")
                break

            system_id, z_mpc, spectral, age_yr = row
            vx, vy, vz = generate_velocity(system_id, age_yr, spectral, z_mpc)
            batch.append((system_id, vx, vy, vz))

            if len(batch) >= args.batch_size:
                flush(conn)
                log.info(
                    "Progress: %d inserted  (%.1f%% of missing)",
                    inserted, 100.0 * inserted / total_missing if total_missing else 0,
                )

        if batch:
            flush(conn)

        remaining = conn.execute(
            "SELECT COUNT(*) FROM IndexedIntegerDistinctSystems sys"
            " LEFT JOIN SystemVelocities sv ON sv.system_id = sys.system_id"
            " WHERE sv.system_id IS NULL"
        ).fetchone()[0]
        log.info(
            "Done. %d synthetic velocity rows inserted; %d systems still missing.",
            inserted, remaining,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
