#!/usr/bin/env python3
"""Seed StarName table in starscape.db from hygdata_v42.

Sources for each star (cross-matched by HIP number):
  proper  → name_type='proper'   (e.g. "Sirius", "Rigil Kentaurus")
  bayer   → name_type='bayer'    (e.g. "Alp CMa", "Alp1 Cen")
  flam    → name_type='flamsteed' (e.g. "9 CMa", "61 Cyg")
  gl      → name_type='gliese'   (e.g. "Gl 551", "GJ 1293")

Greek letters are already stored as 3-char abbreviations in the HYG bayer
field ("Alp", "Bet", "Gam" …).  Any full-word Greek letter that slips in via
the proper field is normalised to 3-char form.

Names with "/" in the proper field are split into individual entries.

Additional custom names are added for known nearby systems that are missing
from hygdata_v42 (e.g. white-dwarf companions catalogued here but not in HYG).

Usage:
    uv run scripts/seed_star_names.py
    uv run scripts/seed_star_names.py --world /path/to/starscape.db
    uv run scripts/seed_star_names.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")

# ---------------------------------------------------------------------------
# Greek letter → IAU 3-char abbreviation (for normalisation of proper names)
# ---------------------------------------------------------------------------
_GREEK_NORM: dict[str, str] = {
    "alpha": "Alp", "beta": "Bet", "gamma": "Gam", "delta": "Del",
    "epsilon": "Eps", "zeta": "Zet", "eta": "Eta", "theta": "The",
    "iota": "Iot", "kappa": "Kap", "lambda": "Lam", "mu": "Mu",
    "nu": "Nu", "xi": "Xi", "omicron": "Omi", "pi": "Pi",
    "rho": "Rho", "sigma": "Sig", "tau": "Tau", "upsilon": "Ups",
    "phi": "Phi", "chi": "Chi", "psi": "Psi", "omega": "Ome",
}

_GREEK_RE = re.compile(
    r"\b(" + "|".join(_GREEK_NORM) + r")\b",
    re.IGNORECASE,
)


def _norm_greek(text: str) -> str:
    """Replace full Greek letter words with 3-char abbreviations."""
    def _replace(m: re.Match) -> str:
        return _GREEK_NORM[m.group(0).lower()]
    return _GREEK_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# bf / bayer field parsing helpers
# ---------------------------------------------------------------------------

def _bayer_name(bayer: str, con: str) -> str | None:
    """Construct a Bayer designation string from the structured bayer + con fields.

    Handles:
      "Alp"    → "Alp CMa"
      "Alp1"   → "Alp1 Cen"   (superscript component)
      "Kap-1"  → "Kap-1 Scl"  (split component variant)
    """
    bayer = bayer.strip()
    con   = con.strip()
    if not bayer or not con:
        return None
    return f"{bayer} {con}"


def _flamsteed_name(flam: str, con: str) -> str | None:
    """Construct a Flamsteed designation from the structured flam + con fields."""
    flam = flam.strip()
    con  = con.strip()
    if not flam or not con:
        return None
    return f"{flam} {con}"


def _gliese_names(gl: str) -> list[str]:
    """Return clean Gliese/GJ designations from the gl field.

    The field may contain slash-separated variants: "Gl 559A/Gl 559B".
    Single entries: "Gl 551", "GJ 1293", "Gl 4.1A".
    """
    if not gl or not gl.strip():
        return []
    return [part.strip() for part in gl.split("/") if part.strip()]


# ---------------------------------------------------------------------------
# Sol — manually inserted (no HIP number in hygdata_v42)
# ---------------------------------------------------------------------------
SOL_NAMES: list[dict] = [
    {"star_id": 1, "name": "Sol",     "name_type": "proper"},
    {"star_id": 1, "name": "The Sun", "name_type": "proper"},
]

# ---------------------------------------------------------------------------
# Custom names for known companions not in hygdata_v42
# ---------------------------------------------------------------------------
# Format: (hip_of_primary, star_id_or_None, name, name_type)
# star_id_or_None: if None the entry is looked up via
#   IndexedIntegerDistinctStars WHERE hip = primary_hip, system_id used to
#   find the companion.
# These are companion stars whose proper names exist but aren't in the HYG
# catalog (white dwarfs, faint companions that lacked separate HIP entries).

CUSTOM_NAMES: list[dict] = [
    # Sirius B — white dwarf companion of Sirius A (HIP 32349)
    {"primary_hip": 32349, "companion_index": 0, "name": "Sirius B",        "name_type": "proper"},
    {"primary_hip": 32349, "companion_index": 0, "name": "Pup",             "name_type": "custom"},
    # Procyon B — white dwarf companion of Procyon A (HIP 37279)
    {"primary_hip": 37279, "companion_index": 0, "name": "Procyon B",       "name_type": "proper"},
    # 70 Oph B — if not in HYG (some editions omit it)
    {"primary_hip": 88601, "companion_index": 0, "name": "70 Oph B",        "name_type": "proper"},
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT OR IGNORE INTO StarName (star_id, name, name_type, species_id, tick)
VALUES (:star_id, :name, :name_type, NULL, 0)
"""

_DDL = """
CREATE TABLE IF NOT EXISTS "StarName" (
    "id"         INTEGER PRIMARY KEY AUTOINCREMENT,
    "star_id"    INTEGER NOT NULL,
    "name"       TEXT    NOT NULL,
    "name_type"  TEXT    NOT NULL CHECK(name_type IN ('proper','bayer','flamsteed','gliese','custom')),
    "species_id" INTEGER DEFAULT NULL,
    "tick"       INTEGER NOT NULL DEFAULT 0,
    UNIQUE("star_id", "name", "name_type")
);
CREATE INDEX IF NOT EXISTS "idx_starname_star"   ON "StarName"("star_id");
CREATE INDEX IF NOT EXISTS "idx_starname_lookup" ON "StarName"("name");
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    conn.commit()


def _build_hip_map(conn: sqlite3.Connection) -> dict[str, int]:
    """Return {hip_str: star_id} for all stars that have a HIP number."""
    rows = conn.execute(
        "SELECT CAST(hip AS TEXT), star_id FROM IndexedIntegerDistinctStars WHERE hip IS NOT NULL"
    ).fetchall()
    return {r[0].strip(): r[1] for r in rows}


def _system_companions(conn: sqlite3.Connection, primary_hip: int) -> list[int]:
    """Return star_ids of companions in the same system, sorted by luminosity asc
    (so index 0 = the closest-to-primary by luminosity ranking)."""
    row = conn.execute(
        "SELECT star_id, system_id FROM IndexedIntegerDistinctStars WHERE hip = ?",
        (primary_hip,),
    ).fetchone()
    if row is None:
        return []
    primary_id = row["star_id"]
    system_id  = row["system_id"]
    rows = conn.execute(
        """
        SELECT i.star_id
        FROM   IndexedIntegerDistinctStars i
        LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
        WHERE  i.system_id = ? AND i.star_id != ?
        ORDER BY COALESCE(e.luminosity, 0.0) DESC, i.star_id ASC
        """,
        (system_id, primary_id),
    ).fetchall()
    return [r["star_id"] for r in rows]


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

def seed(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    _ensure_table(conn)

    rows = conn.execute(
        """
        SELECT h.hip, h.proper, h.bayer, h.flam, h.con, h.gl
        FROM   hygdata_v42 h
        WHERE  h.hip IS NOT NULL
          AND  (h.proper IS NOT NULL OR h.bayer IS NOT NULL
                OR h.flam IS NOT NULL OR h.gl IS NOT NULL)
        """
    ).fetchall()

    log.info("hygdata_v42 rows to process: %d", len(rows))

    hip_map = _build_hip_map(conn)
    log.info("HIP map built: %d entries", len(hip_map))

    batch: list[dict] = []
    missing_hip = 0

    for h in rows:
        hip     = str(h["hip"]).strip()
        star_id = hip_map.get(hip)
        if star_id is None:
            missing_hip += 1
            log.debug("HIP %s not found in IndexedIntegerDistinctStars", hip)
            continue

        # --- proper name(s) ---
        if h["proper"]:
            for raw in h["proper"].split("/"):
                name = _norm_greek(raw.strip())
                if name:
                    batch.append({"star_id": star_id, "name": name, "name_type": "proper"})

        # --- Bayer designation ---
        bname = _bayer_name(h["bayer"], h["con"]) if h["bayer"] and h["con"] else None
        if bname:
            batch.append({"star_id": star_id, "name": bname, "name_type": "bayer"})

        # --- Flamsteed designation ---
        fname = _flamsteed_name(h["flam"], h["con"]) if h["flam"] and h["con"] else None
        if fname:
            batch.append({"star_id": star_id, "name": fname, "name_type": "flamsteed"})

        # --- Gliese designation(s) ---
        for gname in _gliese_names(h["gl"]):
            batch.append({"star_id": star_id, "name": gname, "name_type": "gliese"})

    log.info("Name entries generated: %d  (HIP misses: %d)", len(batch), missing_hip)

    # --- Custom names for companions not in HYG ---
    custom_added = 0
    for entry in CUSTOM_NAMES:
        companions = _system_companions(conn, entry["primary_hip"])
        idx = entry["companion_index"]
        if idx < len(companions):
            cid = companions[idx]
            batch.append({"star_id": cid, "name": entry["name"], "name_type": entry["name_type"]})
            custom_added += 1
        else:
            log.debug("No companion at index %d for HIP %d (%s)",
                      idx, entry["primary_hip"], entry["name"])

    log.info("Custom companion names: %d", custom_added)

    # --- Sol (no HIP — not in hygdata_v42 query) ---
    batch.extend(SOL_NAMES)

    log.info("Total name entries to insert: %d", len(batch))

    if dry_run:
        log.info("[dry-run] Would insert up to %d StarName rows. (DB unchanged)", len(batch))
        # Print a sample
        for r in batch[:20]:
            print(f"  star_id={r['star_id']:>10}  {r['name_type']:12}  {r['name']}")
        if len(batch) > 20:
            print(f"  … and {len(batch) - 20} more")
        return

    # Bulk insert
    before = conn.execute("SELECT COUNT(*) FROM StarName").fetchone()[0]
    conn.executemany(_INSERT_SQL, batch)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM StarName").fetchone()[0]
    log.info("Done. StarName rows inserted: %d  (total: %d)", total - before, total)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--world",   default=str(DEFAULT_DB), help="Path to starscape.db")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    world_path = Path(args.world)
    if not world_path.exists():
        sys.exit(f"Database not found: {world_path}")

    conn = sqlite3.connect(str(world_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        seed(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
