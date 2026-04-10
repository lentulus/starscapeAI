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
    cur = conn.execute(
        """
        INSERT INTO GroundForce
            (polity_id, name, unit_type, strength, max_strength,
             system_id, body_id, marine_designated,
             created_tick, last_updated_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (polity_id, name, unit_type,
         stats.starting_strength, stats.max_strength,
         system_id, body_id, marine_designated,
         created_tick, created_tick),
    )
    return cur.lastrowid  # type: ignore[return-value]


def apply_strength_delta(
    conn: sqlite3.Connection,
    force_id: int,
    delta: int,
    tick: int,
) -> None:
    """Apply a strength change, clamping to [0, max_strength]."""
    conn.execute(
        """
        UPDATE GroundForce
        SET strength = MAX(0, MIN(max_strength, strength + ?)),
            last_updated_tick = ?
        WHERE force_id = ?
        """,
        (delta, tick, force_id),
    )


def embark_force(
    conn: sqlite3.Connection, force_id: int, hull_id: int
) -> None:
    """Load an army formation onto a hull.  Clears system/body assignment."""
    conn.execute(
        """
        UPDATE GroundForce
        SET embarked_hull_id = ?, system_id = NULL, body_id = NULL
        WHERE force_id = ?
        """,
        (hull_id, force_id),
    )


def disembark_force(
    conn: sqlite3.Connection,
    force_id: int,
    system_id: int,
    body_id: int,
    tick: int,
) -> None:
    """Land an army formation at a body.  Clears embarkation."""
    conn.execute(
        """
        UPDATE GroundForce
        SET embarked_hull_id = NULL, system_id = ?, body_id = ?,
            last_updated_tick = ?
        WHERE force_id = ?
        """,
        (system_id, body_id, tick, force_id),
    )


def set_occupation_duty(
    conn: sqlite3.Connection, force_id: int, flag: int
) -> None:
    """Set or clear the occupation_duty flag (1 = occupying alien world)."""
    conn.execute(
        "UPDATE GroundForce SET occupation_duty = ? WHERE force_id = ?",
        (flag, force_id),
    )


def set_refit(
    conn: sqlite3.Connection, force_id: int, ticks: int
) -> None:
    """Mark a formation as refitting for `ticks` ticks."""
    conn.execute(
        "UPDATE GroundForce SET refit_ticks_remaining = ? WHERE force_id = ?",
        (ticks, force_id),
    )


def tick_refit(conn: sqlite3.Connection, force_id: int) -> int:
    """Decrement refit counter by one.  Returns remaining ticks."""
    conn.execute(
        """
        UPDATE GroundForce
        SET refit_ticks_remaining = MAX(0, refit_ticks_remaining - 1)
        WHERE force_id = ?
        """,
        (force_id,),
    )
    return conn.execute(
        "SELECT refit_ticks_remaining FROM GroundForce WHERE force_id = ?",
        (force_id,),
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def get_ground_force(conn: sqlite3.Connection, force_id: int) -> GroundForceRow:
    row = conn.execute(
        "SELECT * FROM GroundForce WHERE force_id = ?", (force_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"GroundForce {force_id} not found")
    return _row_to_force(row)


def get_ground_forces_at_body(
    conn: sqlite3.Connection, body_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce WHERE body_id = ? AND strength > 0",
        (body_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_ground_forces_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce WHERE system_id = ? AND strength > 0",
        (system_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_ground_forces_by_polity(
    conn: sqlite3.Connection, polity_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce WHERE polity_id = ? AND strength > 0",
        (polity_id,),
    ).fetchall()
    return [_row_to_force(r) for r in rows]


def get_embarked_forces(
    conn: sqlite3.Connection, hull_id: int
) -> list[GroundForceRow]:
    rows = conn.execute(
        "SELECT * FROM GroundForce WHERE embarked_hull_id = ?",
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
