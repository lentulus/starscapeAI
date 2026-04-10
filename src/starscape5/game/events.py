"""GameEvent — append-only history log.

One row per significant event.  The log is designed to be self-contained:
an LLM historian with no other context can reconstruct events and causality
from it alone.  Quiet periods collapse to monthly summary records (M13).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class EventRow:
    event_id: int
    tick: int
    phase: int
    event_type: str
    summary: str
    detail: str | None
    polity_a_id: int | None
    polity_b_id: int | None
    system_id: int | None
    body_id: int | None
    admiral_id: int | None


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_event(
    conn: sqlite3.Connection,
    tick: int,
    phase: int,
    event_type: str,
    summary: str,
    polity_a_id: int | None = None,
    polity_b_id: int | None = None,
    system_id: int | None = None,
    body_id: int | None = None,
    admiral_id: int | None = None,
    detail: str | None = None,
) -> int:
    """Append one GameEvent row and return its event_id."""
    cur = conn.execute(
        """
        INSERT INTO GameEvent
            (tick, phase, event_type, summary, detail,
             polity_a_id, polity_b_id, system_id, body_id, admiral_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tick, phase, event_type, summary, detail,
         polity_a_id, polity_b_id, system_id, body_id, admiral_id),
    )
    return cur.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_events(
    conn: sqlite3.Connection,
    tick: int | None = None,
    event_type: str | None = None,
    polity_id: int | None = None,
    limit: int | None = None,
) -> list[EventRow]:
    """Flexible event query.  All filters are optional and AND-combined."""
    clauses: list[str] = []
    params: list = []

    if tick is not None:
        clauses.append("tick = ?")
        params.append(tick)
    if event_type is not None:
        clauses.append("event_type = ?")
        params.append(event_type)
    if polity_id is not None:
        clauses.append("(polity_a_id = ? OR polity_b_id = ?)")
        params.extend([polity_id, polity_id])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_clause = f"LIMIT {limit}" if limit is not None else ""

    rows = conn.execute(
        f"SELECT * FROM GameEvent {where} ORDER BY event_id {limit_clause}",
        params,
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def get_recent_events(
    conn: sqlite3.Connection, n: int
) -> list[EventRow]:
    rows = conn.execute(
        "SELECT * FROM GameEvent ORDER BY event_id DESC LIMIT ?", (n,)
    ).fetchall()
    return list(reversed([_row_to_event(r) for r in rows]))


def _row_to_event(row: sqlite3.Row) -> EventRow:
    return EventRow(
        event_id=row["event_id"],
        tick=row["tick"],
        phase=row["phase"],
        event_type=row["event_type"],
        summary=row["summary"],
        detail=row["detail"],
        polity_a_id=row["polity_a_id"],
        polity_b_id=row["polity_b_id"],
        system_id=row["system_id"],
        body_id=row["body_id"],
        admiral_id=row["admiral_id"],
    )
