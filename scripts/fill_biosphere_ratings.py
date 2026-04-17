#!/usr/bin/env python3
"""Backfill WBH biosphere ratings for all already-generated Bodies rows.

Computes and writes the five WBH biosphere columns (added after initial
body generation) for every rocky planet and moon whose biocomplexity_rating
is still NULL:

    biocomplexity_rating  — WBH p.129: complexity of native life (0–9+)
    native_sophants       — WBH p.130: NULL / 'none' / 'extinct' / 'current'
    biodiversity_rating   — WBH p.130: species richness (1–10+)
    compatibility_rating  — WBH pp.130-131: Terran biochem compatibility (0–10)
    resource_rating       — WBH p.131: natural resource endowment (2–12)

After the main pass, canonical WBH values are applied to Earth (Sol system):
    biomass=10, biocomplexity=9, native_sophants='current',
    biodiversity=10, compatibility=10, resource_rating=12

Prerequisites
-------------
The five columns must exist in the live database.  Run migrate_bodies_wbh.py
first if they are absent:
    uv run scripts/migrate_bodies_wbh.py

Usage
-----
    uv run scripts/fill_biosphere_ratings.py
    uv run scripts/fill_biosphere_ratings.py --max-minutes 120
    uv run scripts/fill_biosphere_ratings.py --batch-size 5000 --verbose
    caffeinate -i uv run scripts/fill_biosphere_ratings.py --max-minutes 480
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

# ---- import generator helpers from the sibling script ----------------------
sys.path.insert(0, str(Path(__file__).parent))
import generate_planets_wbh as _gpw

DEFAULT_DB          = Path("/Volumes/Data/starscape4/starscape.db")
SOL_SYSTEM_ID       = 1030192
DEFAULT_BATCH       = 10_000
DEFAULT_MAX_MINUTES = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query: all rocky planets + all moons where biocomplexity_rating is NULL.
# Age comes from DistinctStarsExtended: planets join directly on orbit_star_id;
# moons join through their parent planet's orbit_star_id.
# Fallback age = 5 Gyr if the star has no DSE row.
# ---------------------------------------------------------------------------
_FETCH_SQL = """
SELECT
    b.body_id,
    COALESCE(b.biomass_rating, 0)                          AS biomass,
    b.atm_code,
    b.taint_type_1,
    b.taint_type_2,
    b.taint_type_3,
    b.size_code,
    b.density,
    COALESCE(dse_p.age, dse_m.age, 5.0e9) / 1.0e9         AS age_gyr
FROM  Bodies b
LEFT  JOIN DistinctStarsExtended dse_p
       ON  dse_p.star_id = b.orbit_star_id
LEFT  JOIN Bodies parent
       ON  parent.body_id = b.orbit_body_id
LEFT  JOIN DistinctStarsExtended dse_m
       ON  dse_m.star_id = parent.orbit_star_id
WHERE b.biocomplexity_rating IS NULL
  AND (
       (b.planet_class = 'rocky' AND b.orbit_star_id IS NOT NULL)
    OR  b.orbit_body_id IS NOT NULL
  )
LIMIT :batch_size
"""

_UPDATE_SQL = """
UPDATE Bodies SET
    biocomplexity_rating  = :biocomplexity_rating,
    native_sophants       = :native_sophants,
    biodiversity_rating   = :biodiversity_rating,
    compatibility_rating  = :compatibility_rating,
    resource_rating       = :resource_rating
WHERE body_id = :body_id
"""


def _compute_row(row: sqlite3.Row) -> dict:
    body_id, biomass, atm_code, t1, t2, t3, size_code, density, age_gyr = row

    # Biologic-taint special case: zero-biomass world with B taint → biomass 1
    if biomass == 0 and 'B' in {t for t in (t1, t2, t3) if t}:
        biomass = 1

    bcmplx = _gpw._biocomplexity_rating(biomass, atm_code, t1, t2, t3, age_gyr)
    bdiv   = _gpw._biodiversity_rating(biomass, bcmplx)

    if biomass > 0:
        has_taint = any(t is not None for t in (t1, t2, t3))
        compat    = _gpw._compatibility_rating(bcmplx, atm_code, has_taint, age_gyr)
        res       = _gpw._resource_rating_world(size_code, density, biomass, bdiv, compat)
    else:
        compat = None
        res    = None

    return {
        "body_id":              body_id,
        "biocomplexity_rating": bcmplx,
        "native_sophants":      _gpw._native_sophants_status(bcmplx, age_gyr),
        "biodiversity_rating":  bdiv,
        "compatibility_rating": compat,
        "resource_rating":      res,
    }


def _set_earth(conn: sqlite3.Connection) -> None:
    """Apply canonical WBH values to Earth in the Sol system.

    Earth is identified as the rocky planet orbiting the primary Sol star
    (system_id=SOL_SYSTEM_ID) with semi_major_axis closest to 1.0 AU.
    """
    # Sol's primary star: lowest star_id in the Sol system
    row = conn.execute(
        "SELECT MIN(star_id) FROM IndexedIntegerDistinctStars WHERE system_id = ?",
        (SOL_SYSTEM_ID,),
    ).fetchone()
    if not row or row[0] is None:
        log.warning("Sol primary star not found — Earth update skipped.")
        return
    sol_star_id = row[0]

    # Earth: rocky planet orbiting Sol with SMA nearest 1.0 AU
    earth = conn.execute(
        """
        SELECT body_id, semi_major_axis
        FROM   Bodies
        WHERE  orbit_star_id = ?
          AND  planet_class  = 'rocky'
        ORDER  BY ABS(semi_major_axis - 1.0)
        LIMIT  1
        """,
        (sol_star_id,),
    ).fetchone()
    if not earth:
        log.warning("Earth body not found under star_id=%d — skipped.", sol_star_id)
        return

    earth_body_id, earth_sma = earth
    conn.execute(
        """
        UPDATE Bodies SET
            biomass_rating        = 10,
            biocomplexity_rating  = 9,
            native_sophants       = 'current',
            biodiversity_rating   = 10,
            compatibility_rating  = 10,
            resource_rating       = 12
        WHERE body_id = ?
        """,
        (earth_body_id,),
    )
    conn.commit()
    log.info(
        "Earth (body_id=%d, sma=%.3f AU): canonical WBH biosphere values set.",
        earth_body_id, earth_sma,
    )


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
        help="Rows fetched and committed per transaction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
        help="Stop after this many elapsed minutes; re-run to resume (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Log every batch",
    )
    args = parser.parse_args()

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Verify the new columns exist; if not, tell the user how to add them.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(Bodies)").fetchall()}
    if "biocomplexity_rating" not in cols:
        sys.exit(
            "ERROR: Bodies.biocomplexity_rating column missing.\n"
            "Run:  uv run scripts/migrate_bodies_wbh.py"
        )

    deadline = time.monotonic() + args.max_minutes * 60.0

    total_updated = 0
    try:
        while time.monotonic() < deadline:
            rows = conn.execute(
                _FETCH_SQL, {"batch_size": args.batch_size}
            ).fetchall()
            if not rows:
                log.info("No more rows to process — done.")
                break

            updates = [_compute_row(r) for r in rows]
            conn.executemany(_UPDATE_SQL, updates)
            conn.commit()
            total_updated += len(updates)

            if args.verbose:
                log.info("Batch committed: %d rows  |  total so far: %d",
                         len(updates), total_updated)
            else:
                log.info("Updated %d rows (total %d)", len(updates), total_updated)

    finally:
        # Always apply Earth values, regardless of whether we timed out
        _set_earth(conn)
        conn.close()

    log.info("fill_biosphere_ratings complete: %d rows updated.", total_updated)


if __name__ == "__main__":
    main()
