"""Name generation for game entities.

Two operating modes:
  - Code fallback (db_conn=None): generates structured codes, e.g. "KRT-FL-0003".
    No DB required; works at any milestone.
  - DB-backed (db_conn provided): draws pre-generated names from the NamePool
    table.  Falls back to codes when the pool is exhausted.

Species IDs are provisional until the Species table is seeded.  The mapping
here must stay in sync with seed_species.py.
"""

import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Species prefix table (species_id → 3-letter code).
# Provisional IDs; locked in when Species table is seeded.
# ---------------------------------------------------------------------------

_PREFIXES: dict[int, str] = {
    1:  "KRT",  # Kreeth
    2:  "VSH",  # Vashori
    3:  "KRA",  # Kraathi
    4:  "NAK",  # Nakhavi
    5:  "SKH",  # Skharri
    6:  "VLK",  # Vaelkhi
    7:  "SHK",  # Shekhari
    8:  "GLV",  # Golvhaan
    9:  "NHV",  # Nhaveth
    10: "VRD",  # Vardhek
    11: "HUM",  # Human
}

_UNKNOWN_PREFIX = "UNK"

# NamePool name_type values (hull is always code-only; not in DB pool).
_DB_NAME_TYPES = frozenset({"person", "system", "body", "fleet", "war", "polity"})

# Type tags used in structured codes.
_TYPE_TAGS: dict[str, str] = {
    "fleet":   "FL",
    "admiral": "ADM",
    "system":  "SYS",
    "body":    "BOD",
    "war":     "WAR",
    "hull":    "SHP",
    "polity":  "POL",
}


# ---------------------------------------------------------------------------
# Pure code-generation helpers (no DB, no side effects)
# ---------------------------------------------------------------------------

def species_prefix(species_id: int) -> str:
    """Return the 3-letter prefix for a species, e.g. "KRT" for Kreeth."""
    return _PREFIXES.get(species_id, _UNKNOWN_PREFIX)


def format_code(prefix: str, type_tag: str, sequence: int) -> str:
    """Format a structured name code, e.g. format_code("HUM", "FL", 3) → "HUM-FL-0003"."""
    return f"{prefix}-{type_tag}-{sequence:04d}"


# ---------------------------------------------------------------------------
# NameGenerator
# ---------------------------------------------------------------------------

@dataclass
class _PoolKey:
    species_id: int
    name_type: str


class NameGenerator:
    """Generates names for game entities.

    Args:
        species_id: The species whose name pool to draw from.
        db_conn:    An open game.db connection with NamePool populated.
                    Pass None to use code-fallback only.
    """

    def __init__(self, species_id: int, db_conn: sqlite3.Connection | None = None):
        self._species_id = species_id
        self._prefix = species_prefix(species_id)
        self._conn = db_conn

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fleet(self, polity_name: str, sequence: int) -> str:  # noqa: ARG002
        """Name for a new fleet."""
        return self._draw("fleet", sequence)

    def admiral(self, sequence: int) -> str:
        """Name for a newly commissioned admiral (draws from person pool)."""
        name = self._draw_from_pool("person")
        if name is not None:
            return name
        return format_code(self._prefix, "ADM", sequence)

    def system(self, system_id: int, sequence: int) -> str:  # noqa: ARG002
        """Per-polity name for a newly named system."""
        return self._draw("system", sequence)

    def body(self, body_id: int, sequence: int) -> str:  # noqa: ARG002
        """Per-polity name for a newly named body."""
        return self._draw("body", sequence)

    def war(self, polity_a: str, polity_b: str, tick: int) -> str:  # noqa: ARG002
        """Name for a newly declared war."""
        return self._draw("war", tick)

    def hull(self, hull_type: str, sequence: int) -> str:
        """Name for an individual hull.  Draws from the DB pool when available,
        falls back to structured code otherwise."""
        name = self._draw_from_pool("hull")
        if name is not None:
            return name
        tag = hull_type[:3].upper()
        return format_code(self._prefix, tag, sequence)

    def polity(self, sequence: int) -> str:
        """Name for a new polity (faction)."""
        return self._draw("polity", sequence)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _draw(self, name_type: str, fallback_sequence: int) -> str:
        """Draw from the DB pool for name_type; fall back to a structured code."""
        if name_type in _DB_NAME_TYPES:
            name = self._draw_from_pool(name_type)
            if name is not None:
                return name
        tag = _TYPE_TAGS.get(name_type, name_type[:3].upper())
        return format_code(self._prefix, tag, fallback_sequence)

    def _draw_from_pool(self, name_type: str) -> str | None:
        """Select and mark-used one unused name from NamePool.

        Returns None if no connection or pool is exhausted.
        """
        if self._conn is None:
            return None
        row = self._conn.execute(
            """
            SELECT name_id, name
            FROM   NamePool
            WHERE  species_id = ? AND name_type = ? AND used = 0
            ORDER  BY name_id
            LIMIT  1
            """,
            (self._species_id, name_type),
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE NamePool SET used = 1 WHERE name_id = ?",
            (row["name_id"],),
        )
        return row["name"]
