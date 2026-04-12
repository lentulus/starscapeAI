"""SystemPresence — per-polity foothold and control state for each body.

Control state progression: outpost → colony → controlled.
'contested' is set by the combat/assault phases when control is challenged.

Development level is capped by control state:
  outpost   → max 1
  colony    → max 3
  controlled → max 5
  contested  → max 1 (fighting prevents investment)

TEMPORAL TABLE: append-only; all mutations INSERT new rows (copy-on-write).
presence_id is the logical entity key; row_id is the physical autoincrement PK.
Use SystemPresence_head view or ORDER BY row_id DESC LIMIT 1 for current state.
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
# Internal copy-on-write helpers
# ---------------------------------------------------------------------------

def _current_presence_row(conn: sqlite3.Connection, presence_id: int) -> sqlite3.Row:
    """Return the most recent raw row for presence_id."""
    row = conn.execute(
        "SELECT * FROM SystemPresence WHERE presence_id = ? ORDER BY row_id DESC LIMIT 1",
        (presence_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"SystemPresence {presence_id} not found")
    return row


def _insert_presence_row(
    conn: sqlite3.Connection,
    presence_id: int,
    polity_id: int,
    system_id: int,
    body_id: int,
    control_state: str,
    development_level: int,
    colonist_deliveries: int,
    has_shipyard: int,
    has_naval_base: int,
    growth_cycle_tick: int | None,
    established_tick: int,
    last_updated_tick: int,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO SystemPresence
            (presence_id, tick, seq, polity_id, system_id, body_id,
             control_state, development_level, colonist_deliveries,
             has_shipyard, has_naval_base, growth_cycle_tick,
             established_tick, last_updated_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (presence_id, tick, seq, polity_id, system_id, body_id,
         control_state, development_level, colonist_deliveries,
         has_shipyard, has_naval_base, growth_cycle_tick,
         established_tick, last_updated_tick),
    )


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
    row = conn.execute(
        "SELECT COALESCE(MAX(presence_id), 0) + 1 FROM SystemPresence"
    ).fetchone()
    presence_id: int = row[0]
    _insert_presence_row(
        conn, presence_id, polity_id, system_id, body_id,
        control_state, development_level, colonist_deliveries=0,
        has_shipyard=has_shipyard, has_naval_base=has_naval_base,
        growth_cycle_tick=None,
        established_tick=established_tick,
        last_updated_tick=established_tick,
        tick=0, seq=0,
    )
    return presence_id


def advance_control_state(
    conn: sqlite3.Connection, presence_id: int, tick: int, seq: int = 0,
) -> str:
    """Advance outpost → colony → controlled.  Returns the new state.

    If already at 'controlled', returns 'controlled' unchanged.
    """
    cur = _current_presence_row(conn, presence_id)
    current = cur["control_state"]
    next_state = _CONTROL_PROGRESSION.get(current, current)
    if next_state != current:
        _insert_presence_row(
            conn, presence_id,
            polity_id=cur["polity_id"],
            system_id=cur["system_id"],
            body_id=cur["body_id"],
            control_state=next_state,
            development_level=cur["development_level"],
            colonist_deliveries=cur["colonist_deliveries"],
            has_shipyard=cur["has_shipyard"],
            has_naval_base=cur["has_naval_base"],
            growth_cycle_tick=cur["growth_cycle_tick"],
            established_tick=cur["established_tick"],
            last_updated_tick=tick,
            tick=tick, seq=seq,
        )
    return next_state


def advance_development(
    conn: sqlite3.Connection, presence_id: int, tick: int, seq: int = 0,
) -> int:
    """Increment development_level by 1, capped by control_state.

    Returns the new development_level.
    """
    cur = _current_presence_row(conn, presence_id)
    cap = _DEV_CAPS.get(cur["control_state"], 1)
    new_level = min(cur["development_level"] + 1, cap)
    _insert_presence_row(
        conn, presence_id,
        polity_id=cur["polity_id"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        control_state=cur["control_state"],
        development_level=new_level,
        colonist_deliveries=cur["colonist_deliveries"],
        has_shipyard=cur["has_shipyard"],
        has_naval_base=cur["has_naval_base"],
        growth_cycle_tick=cur["growth_cycle_tick"],
        established_tick=cur["established_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )
    return new_level


def set_contested(
    conn: sqlite3.Connection, presence_id: int, tick: int, seq: int = 0,
) -> None:
    cur = _current_presence_row(conn, presence_id)
    _insert_presence_row(
        conn, presence_id,
        polity_id=cur["polity_id"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        control_state="contested",
        development_level=cur["development_level"],
        colonist_deliveries=cur["colonist_deliveries"],
        has_shipyard=cur["has_shipyard"],
        has_naval_base=cur["has_naval_base"],
        growth_cycle_tick=cur["growth_cycle_tick"],
        established_tick=cur["established_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )


def transfer_control(
    conn: sqlite3.Connection,
    presence_id: int,
    new_polity_id: int,
    tick: int,
    seq: int = 0,
) -> None:
    """Hand a presence to a new polity after a successful assault."""
    cur = _current_presence_row(conn, presence_id)
    _insert_presence_row(
        conn, presence_id,
        polity_id=new_polity_id,
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        control_state="controlled",
        development_level=cur["development_level"],
        colonist_deliveries=cur["colonist_deliveries"],
        has_shipyard=cur["has_shipyard"],
        has_naval_base=cur["has_naval_base"],
        growth_cycle_tick=cur["growth_cycle_tick"],
        established_tick=cur["established_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )


def record_colonist_delivery(
    conn: sqlite3.Connection, presence_id: int, tick: int, seq: int = 0,
) -> None:
    cur = _current_presence_row(conn, presence_id)
    _insert_presence_row(
        conn, presence_id,
        polity_id=cur["polity_id"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        control_state=cur["control_state"],
        development_level=cur["development_level"],
        colonist_deliveries=cur["colonist_deliveries"] + 1,
        has_shipyard=cur["has_shipyard"],
        has_naval_base=cur["has_naval_base"],
        growth_cycle_tick=cur["growth_cycle_tick"],
        established_tick=cur["established_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )


# ---------------------------------------------------------------------------
# Read functions  (use SystemPresence_head / ORDER BY row_id DESC LIMIT 1)
# ---------------------------------------------------------------------------

def get_presence(conn: sqlite3.Connection, presence_id: int) -> PresenceRow:
    row = conn.execute(
        "SELECT * FROM SystemPresence WHERE presence_id = ? ORDER BY row_id DESC LIMIT 1",
        (presence_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"SystemPresence {presence_id} not found")
    return _row_to_presence(row)


def get_presences_by_polity(
    conn: sqlite3.Connection, polity_id: int
) -> list[PresenceRow]:
    rows = conn.execute(
        "SELECT * FROM SystemPresence_head WHERE polity_id = ?", (polity_id,)
    ).fetchall()
    return [_row_to_presence(r) for r in rows]


def get_presences_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[PresenceRow]:
    rows = conn.execute(
        "SELECT * FROM SystemPresence_head WHERE system_id = ?", (system_id,)
    ).fetchall()
    return [_row_to_presence(r) for r in rows]


def get_presence_at_body(
    conn: sqlite3.Connection, polity_id: int, body_id: int
) -> PresenceRow | None:
    row = conn.execute(
        "SELECT * FROM SystemPresence_head WHERE polity_id = ? AND body_id = ?",
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
