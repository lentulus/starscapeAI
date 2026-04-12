"""Ground forces — armies and garrisons.

Strength scale (units.md):
  6 — consolidated, full combat power
  4–5 — combat-effective
  2–3 — weakened but still fights
  1 — combat-ineffective; must refit
  0 — destroyed or captured

Garrisons are fixed at their body; armies can embark on Troop or Transport
hulls.  Marine-designated armies avoid the −1 first-round penalty when
assaulting from orbit onto a defended world.

TEMPORAL TABLE: append-only; all mutations INSERT new rows (copy-on-write).
force_id is the logical entity key; row_id is the physical autoincrement PK.
Use GroundForce_head view or ORDER BY row_id DESC LIMIT 1 for current state.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .constants import GROUND_STATS


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class GroundForceRow:
    force_id: int
    polity_id: int
    name: str
    unit_type: str          # 'army' | 'garrison'
    strength: int           # 0–6
    max_strength: int
    system_id: int | None
    body_id: int | None
    embarked_hull_id: int | None
    marine_designated: int  # 0 | 1
    occupation_duty: int    # 0 | 1
    refit_ticks_remaining: int
    created_tick: int
    last_updated_tick: int


# ---------------------------------------------------------------------------
# Internal copy-on-write helpers
# ---------------------------------------------------------------------------

def _current_force_row(conn: sqlite3.Connection, force_id: int) -> sqlite3.Row:
    """Return the most recent raw row for force_id."""
    row = conn.execute(
        "SELECT * FROM GroundForce WHERE force_id = ? ORDER BY row_id DESC LIMIT 1",
        (force_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"GroundForce {force_id} not found")
    return row


def _insert_force_row(
    conn: sqlite3.Connection,
    force_id: int,
    polity_id: int,
    name: str,
    unit_type: str,
    strength: int,
    max_strength: int,
    system_id: int | None,
    body_id: int | None,
    embarked_hull_id: int | None,
    marine_designated: int,
    occupation_duty: int,
    refit_ticks_remaining: int,
    created_tick: int,
    last_updated_tick: int,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO GroundForce
            (force_id, tick, seq, polity_id, name, unit_type,
             strength, max_strength, system_id, body_id, embarked_hull_id,
             marine_designated, occupation_duty, refit_ticks_remaining,
             created_tick, last_updated_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (force_id, tick, seq, polity_id, name, unit_type,
         strength, max_strength, system_id, body_id, embarked_hull_id,
         marine_designated, occupation_duty, refit_ticks_remaining,
         created_tick, last_updated_tick),
    )


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def create_ground_force(
    conn: sqlite3.Connection,
    polity_id: int,
    name: str,
    unit_type: str,
    system_id: int | None,
    body_id: int | None,
    created_tick: int,
    marine_designated: int = 0,
) -> int:
    """Create a new ground force at starting strength.  Returns force_id."""
    stats = GROUND_STATS[unit_type]
    row = conn.execute(
        "SELECT COALESCE(MAX(force_id), 0) + 1 FROM GroundForce"
    ).fetchone()
    force_id: int = row[0]
    _insert_force_row(
        conn, force_id, polity_id, name, unit_type,
        strength=stats.starting_strength,
        max_strength=stats.max_strength,
        system_id=system_id,
        body_id=body_id,
        embarked_hull_id=None,
        marine_designated=marine_designated,
        occupation_duty=0,
        refit_ticks_remaining=0,
        created_tick=created_tick,
        last_updated_tick=created_tick,
        tick=0, seq=0,
    )
    return force_id


def apply_strength_delta(
    conn: sqlite3.Connection,
    force_id: int,
    delta: int,
    tick: int,
    seq: int = 0,
) -> None:
    """Apply a strength change, clamping to [0, max_strength]."""
    cur = _current_force_row(conn, force_id)
    new_strength = max(0, min(cur["max_strength"], cur["strength"] + delta))
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=new_strength,
        max_strength=cur["max_strength"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        embarked_hull_id=cur["embarked_hull_id"],
        marine_designated=cur["marine_designated"],
        occupation_duty=cur["occupation_duty"],
        refit_ticks_remaining=cur["refit_ticks_remaining"],
        created_tick=cur["created_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )


def embark_force(
    conn: sqlite3.Connection, force_id: int, hull_id: int,
    tick: int = 0, seq: int = 0,
) -> None:
    """Load an army formation onto a hull.  Clears system/body assignment."""
    cur = _current_force_row(conn, force_id)
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=cur["strength"],
        max_strength=cur["max_strength"],
        system_id=None,
        body_id=None,
        embarked_hull_id=hull_id,
        marine_designated=cur["marine_designated"],
        occupation_duty=cur["occupation_duty"],
        refit_ticks_remaining=cur["refit_ticks_remaining"],
        created_tick=cur["created_tick"],
        last_updated_tick=cur["last_updated_tick"],
        tick=tick, seq=seq,
    )


def disembark_force(
    conn: sqlite3.Connection,
    force_id: int,
    system_id: int,
    body_id: int,
    tick: int,
    seq: int = 0,
) -> None:
    """Land an army formation at a body.  Clears embarkation."""
    cur = _current_force_row(conn, force_id)
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=cur["strength"],
        max_strength=cur["max_strength"],
        system_id=system_id,
        body_id=body_id,
        embarked_hull_id=None,
        marine_designated=cur["marine_designated"],
        occupation_duty=cur["occupation_duty"],
        refit_ticks_remaining=cur["refit_ticks_remaining"],
        created_tick=cur["created_tick"],
        last_updated_tick=tick,
        tick=tick, seq=seq,
    )


def set_occupation_duty(
    conn: sqlite3.Connection, force_id: int, flag: int,
    tick: int = 0, seq: int = 0,
) -> None:
    """Set or clear the occupation_duty flag (1 = occupying alien world)."""
    cur = _current_force_row(conn, force_id)
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=cur["strength"],
        max_strength=cur["max_strength"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        embarked_hull_id=cur["embarked_hull_id"],
        marine_designated=cur["marine_designated"],
        occupation_duty=flag,
        refit_ticks_remaining=cur["refit_ticks_remaining"],
        created_tick=cur["created_tick"],
        last_updated_tick=cur["last_updated_tick"],
        tick=tick, seq=seq,
    )


def set_refit(
    conn: sqlite3.Connection, force_id: int, ticks: int,
    tick: int = 0, seq: int = 0,
) -> None:
    """Mark a formation as refitting for `ticks` ticks."""
    cur = _current_force_row(conn, force_id)
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=cur["strength"],
        max_strength=cur["max_strength"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        embarked_hull_id=cur["embarked_hull_id"],
        marine_designated=cur["marine_designated"],
        occupation_duty=cur["occupation_duty"],
        refit_ticks_remaining=ticks,
        created_tick=cur["created_tick"],
        last_updated_tick=cur["last_updated_tick"],
        tick=tick, seq=seq,
    )


def tick_refit(conn: sqlite3.Connection, force_id: int, tick: int = 0, seq: int = 0) -> int:
    """Decrement refit counter by one.  Returns remaining ticks."""
    cur = _current_force_row(conn, force_id)
    new_refit = max(0, cur["refit_ticks_remaining"] - 1)
    _insert_force_row(
        conn, force_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        unit_type=cur["unit_type"],
        strength=cur["strength"],
        max_strength=cur["max_strength"],
        system_id=cur["system_id"],
        body_id=cur["body_id"],
        embarked_hull_id=cur["embarked_hull_id"],
        marine_designated=cur["marine_designated"],
        occupation_duty=cur["occupation_duty"],
        refit_ticks_remaining=new_refit,
        created_tick=cur["created_tick"],
        last_updated_tick=cur["last_updated_tick"],
        tick=tick, seq=seq,
    )
    return new_refit


# ---------------------------------------------------------------------------
# Read functions  (use GroundForce_head / ORDER BY row_id DESC LIMIT 1)
# ---------------------------------------------------------------------------

def get_ground_force(conn: sqlite3.Connection, force_id: int) -> GroundForceRow:
    row = conn.execute(
        "SELECT * FROM GroundForce WHERE force_id = ? ORDER BY row_id DESC LIMIT 1",
        (force_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"GroundForce {force_id} not found")
    return _row_to_force(row)


def get_ground_forces_at_body(
    conn: sqlite3.Connection, body_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce_head WHERE body_id = ? AND strength > 0",
        (body_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_ground_forces_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce_head WHERE system_id = ? AND strength > 0",
        (system_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_ground_forces_by_polity(
    conn: sqlite3.Connection, polity_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce_head WHERE polity_id = ? AND strength > 0",
        (polity_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_embarked_forces(
    conn: sqlite3.Connection, hull_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce_head WHERE embarked_hull_id = ?",
        (hull_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def _row_to_force(row: sqlite3.Row) -> GroundForceRow:
    return GroundForceRow(
        force_id=row["force_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        unit_type=row["unit_type"],
        strength=row["strength"],
        max_strength=row["max_strength"],
        system_id=row["system_id"],
        body_id=row["body_id"],
        embarked_hull_id=row["embarked_hull_id"],
        marine_designated=row["marine_designated"],
        occupation_duty=row["occupation_duty"],
        refit_ticks_remaining=row["refit_ticks_remaining"],
        created_tick=row["created_tick"],
        last_updated_tick=row["last_updated_tick"],
    )
