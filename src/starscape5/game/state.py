"""GameState — singleton simulation clock and crash-safe resume point.

The GameState table has exactly one row (state_id = 1 enforced by CHECK).

Crash-safe commit pattern
--------------------------
Before running a phase:
    advance_phase(conn, tick, phase)   # updates current_tick/current_phase

After all DB writes for that phase are committed:
    commit_phase(conn, tick, phase)    # updates last_committed_tick/phase

On resume after a crash: last_committed_tick/phase is the last confirmed state.
Re-run any phase where current_phase > last_committed_phase for the same tick.
Seeded randomness ensures replaying a phase from the same state gives identical
results.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """In-memory snapshot of the GameState table row."""
    current_tick: int
    current_phase: int
    last_committed_tick: int
    last_committed_phase: int
    started_at: str
    last_committed_at: str


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def create_gamestate(conn: sqlite3.Connection, tick: int = 0) -> None:
    """Insert the singleton GameState row.

    Raises sqlite3.IntegrityError if a row already exists (state_id = 1
    unique constraint).  Call only once at game initialisation.
    """
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO GameState
            (state_id, current_tick, current_phase,
             started_at, last_committed_at,
             last_committed_tick, last_committed_phase)
        VALUES (1, ?, 0, ?, ?, ?, 0)
        """,
        (tick, now, now, tick),
    )
    conn.commit()


def read_gamestate(conn: sqlite3.Connection) -> GameState:
    """Read the singleton row.  Raises RuntimeError if not yet created."""
    row = conn.execute("SELECT * FROM GameState WHERE state_id = 1").fetchone()
    if row is None:
        raise RuntimeError("GameState row not found — call create_gamestate first")
    return GameState(
        current_tick=row["current_tick"],
        current_phase=row["current_phase"],
        last_committed_tick=row["last_committed_tick"],
        last_committed_phase=row["last_committed_phase"],
        started_at=row["started_at"],
        last_committed_at=row["last_committed_at"],
    )


def advance_phase(conn: sqlite3.Connection, tick: int, phase: int) -> None:
    """Mark that tick/phase is now in progress.

    Written immediately so monitoring tools can see the live position, but
    NOT the crash-safe checkpoint — last_committed_* is unchanged.
    """
    conn.execute(
        """
        UPDATE GameState
        SET current_tick = ?, current_phase = ?
        WHERE state_id = 1
        """,
        (tick, phase),
    )
    conn.commit()


def commit_phase(conn: sqlite3.Connection, tick: int, phase: int) -> None:
    """Record that tick/phase completed successfully.

    This is the crash-safe checkpoint.  Call after all DB writes for the
    phase have been committed.
    """
    conn.execute(
        """
        UPDATE GameState
        SET last_committed_tick   = ?,
            last_committed_phase  = ?,
            last_committed_at     = ?
        WHERE state_id = 1
        """,
        (tick, phase, _now_iso()),
    )
    conn.commit()
