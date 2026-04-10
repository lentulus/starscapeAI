"""SystemPresence — per-polity foothold and control state for each body.

Control state progression: outpost → colony → controlled.
'contested' is set by the combat/assault phases when control is challenged.

Development level is capped by control state:
  outpost   → max 1
  colony    → max 3
  controlled → max 5
  contested  → max 1 (fighting prevents investment)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


_CONTROL_PROGRESSION: dict[str, str] = {
    "outpost":  "colony",
    "colony":   "controlled",
}

_DEV_CAPS: dict[str, int] = {
    "outpost":    1,
    "colony":     3,
    "controlled": 5,
    "contested":  1,
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PresenceRow:
    presence_id: int
    polity_id: int
    system_id: int
    body_id: int
    control_state: str      # 'outpost' | 'colony' | 'controlled' | 'contested'
    development_level: int  # 0–5
    colonist_deliveries: int
    has_shipyard: int       # 0 | 1
    has_naval_base: int     # 0 | 1
    growth_cycle_tick: int | None
    established_tick: int
    last_updated_tick: int


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def create_presence(
    conn: sqlite3.Connection,
    polity_id: int,
    system_id: int,
    body_id: int,
    control_state: str,
    development_level: int,
    established_tick: int,
    has_shipyard: int = 0,
    has_naval_base: int = 0,
) -> int:
    """Insert a SystemPresence row and return its presence_id."""
    cur = conn.execute(
        """
        INSERT INTO SystemPresence
            (polity_id, system_id, body_id, control_state, development_level,
             has_shipyard, has_naval_base, established_tick, last_updated_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (polity_id, system_id, body_id, control_state, development_level,
         has_shipyard, has_naval_base, established_tick, established_tick),
    )
    return cur.lastrowid  # type: ignore[return-value]


def advance_control_state(
    conn: sqlite3.Connection, presence_id: int, tick: int
) -> str:
    """Advance outpost → colony → controlled.  Returns the new state.

    If already at 'controlled', returns 'controlled' unchanged.
    """
    row = conn.execute(
        "SELECT control_state FROM SystemPresence WHERE presence_id = ?",
        (presence_id,),
    ).fetchone()
    current = row["control_state"]
    next_state = _CONTROL_PROGRESSION.get(current, current)
    if next_state != current:
        conn.execute(
            """
            UPDATE SystemPresence
            SET control_state = ?, last_updated_tick = ?
            WHERE presence_id = ?
            """,
            (next_state, tick, presence_id),
        )
    return next_state


def advance_development(
    conn: sqlite3.Connection, presence_id: int, tick: int
) -> int:
    """Increment development_level by 1, capped by control_state.

    Returns the new development_level.
    """
    row = conn.execute(
        "SELECT control_state, development_level FROM SystemPresence WHERE presence_id = ?",
        (presence_id,),
    ).fetchone()
    cap = _DEV_CAPS.get(row["control_state"], 1)
    new_level = min(row["development_level"] + 1, cap)
    conn.execute(
        """
        UPDATE SystemPresence
        SET development_level = ?, last_updated_tick = ?
        WHERE presence_id = ?
        """,
        (new_level, tick, presence_id),
    )
    return new_level


def set_contested(
    conn: sqlite3.Connection, presence_id: int, tick: int
) -> None:
    conn.execute(
        """
        UPDATE SystemPresence
        SET control_state = 'contested', last_updated_tick = ?
        WHERE presence_id = ?
        """,
        (tick, presence_id),
    )


def transfer_control(
    conn: sqlite3.Connection,
    presence_id: int,
    new_polity_id: int,
    tick: int,
) -> None:
    """Hand a presence to a new polity after a successful assault."""
    conn.execute(
        """
        UPDATE SystemPresence
        SET polity_id = ?, control_state = 'controlled', last_updated_tick = ?
        WHERE presence_id = ?
        """,
        (new_polity_id, tick, presence_id),
    )


def record_colonist_delivery(
    conn: sqlite3.Connection, presence_id: int, tick: int
) -> None:
    conn.execute(
        """
        UPDATE SystemPresence
        SET colonist_deliveries = colonist_deliveries + 1, last_updated_tick = ?
        WHERE presence_id = ?
        """,
        (tick, presence_id),
    )


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def get_presence(conn: sqlite3.Connection, presence_id: int) -> PresenceRow:
    row = conn.execute(
        "SELECT * FROM SystemPresence WHERE presence_id = ?", (presence_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"SystemPresence {presence_id} not found")
    return _row_to_presence(row)


def get_presences_by_polity(
    conn: sqlite3.Connection, polity_id: int
) -> list[PresenceRow]:
    rows = conn.execute(
        "SELECT * FROM SystemPresence WHERE polity_id = ?", (polity_id,)
    ).fetchall()
    return [_row_to_presence(r) for r in rows]


def get_presences_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[PresenceRow]:
    rows = conn.execute(
        "SELECT * FROM SystemPresence WHERE system_id = ?", (system_id,)
    ).fetchall()
    return [_row_to_presence(r) for r in rows]


def get_presence_at_body(
    conn: sqlite3.Connection, polity_id: int, body_id: int
) -> PresenceRow | None:
    row = conn.execute(
        "SELECT * FROM SystemPresence WHERE polity_id = ? AND body_id = ?",
        (polity_id, body_id),
    ).fetchone()
    return _row_to_presence(row) if row else None


def _row_to_presence(row: sqlite3.Row) -> PresenceRow:
    return PresenceRow(
        presence_id=row["presence_id"],
        polity_id=row["polity_id"],
        system_id=row["system_id"],
        body_id=row["body_id"],
        control_state=row["control_state"],
        development_level=row["development_level"],
        colonist_deliveries=row["colonist_deliveries"],
        has_shipyard=row["has_shipyard"],
        has_naval_base=row["has_naval_base"],
        growth_cycle_tick=row["growth_cycle_tick"],
        established_tick=row["established_tick"],
        last_updated_tick=row["last_updated_tick"],
    )
