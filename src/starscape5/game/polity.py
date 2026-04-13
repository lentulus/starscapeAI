"""Polity — civilisation-level state.

Each Polity represents one politically independent actor in the simulation.
A species with faction_tendency > 0.85 spawns multiple polities at game start.

TEMPORAL TABLE: all mutations INSERT new rows (copy-on-write).
polity_id is the logical entity key; row_id is the physical autoincrement PK.
Use Polity_head view or ORDER BY row_id DESC LIMIT 1 for current state.

All write functions take an open game.db connection and return the logical
polity_id (NOT row_id).  Callers are responsible for committing at phase
boundaries via game.state.commit_phase().
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PolityRow:
    """In-memory snapshot of one Polity row."""
    polity_id: int
    species_id: int
    name: str
    capital_system_id: int | None
    treasury_ru: float
    expansionism: float
    aggression: float
    risk_appetite: float
    processing_order: int
    founded_tick: int
    jump_level: int   # scout jump range (pc); upgradeable via UpgradeJumpAction
    status: str  # 'active' | 'eliminated' | 'vassal'


def _row_to_polity(row: sqlite3.Row) -> PolityRow:
    return PolityRow(
        polity_id=row["polity_id"],
        species_id=row["species_id"],
        name=row["name"],
        capital_system_id=row["capital_system_id"],
        treasury_ru=row["treasury_ru"],
        expansionism=row["expansionism"],
        aggression=row["aggression"],
        risk_appetite=row["risk_appetite"],
        processing_order=row["processing_order"],
        founded_tick=row["founded_tick"],
        jump_level=row["jump_level"] if "jump_level" in row.keys() else 10,
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# Internal copy-on-write helper
# ---------------------------------------------------------------------------

def _current_polity_row(conn: sqlite3.Connection, polity_id: int) -> sqlite3.Row:
    """Return the most recent raw row for polity_id."""
    row = conn.execute(
        "SELECT * FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Polity {polity_id} not found")
    return row


def _insert_polity_row(
    conn: sqlite3.Connection,
    polity_id: int,
    species_id: int,
    name: str,
    capital_system_id: int | None,
    treasury_ru: float,
    expansionism: float,
    aggression: float,
    risk_appetite: float,
    processing_order: int,
    founded_tick: int,
    jump_level: int,
    status: str,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO Polity
            (polity_id, tick, seq, species_id, name, capital_system_id,
             treasury_ru, expansionism, aggression, risk_appetite,
             processing_order, founded_tick, jump_level, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (polity_id, tick, seq, species_id, name, capital_system_id,
         treasury_ru, expansionism, aggression, risk_appetite,
         processing_order, founded_tick, jump_level, status),
    )


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def create_polity(
    conn: sqlite3.Connection,
    species_id: int,
    name: str,
    capital_system_id: int | None,
    expansionism: float,
    aggression: float,
    risk_appetite: float,
    processing_order: int,
    treasury_ru: float = 0.0,
    founded_tick: int = 0,
) -> int:
    """Insert a new Polity row and return its polity_id."""
    # Assign next logical polity_id
    row = conn.execute("SELECT COALESCE(MAX(polity_id), 0) + 1 FROM Polity").fetchone()
    polity_id: int = row[0]
    _insert_polity_row(
        conn, polity_id, species_id, name, capital_system_id,
        treasury_ru, expansionism, aggression, risk_appetite,
        processing_order, founded_tick, jump_level=10, status="active",
        tick=0, seq=0,
    )
    return polity_id


def update_treasury(
    conn: sqlite3.Connection, polity_id: int, delta_ru: float,
    tick: int = 0, seq: int = 0,
) -> None:
    """Add delta_ru to the polity's treasury (delta may be negative)."""
    cur = _current_polity_row(conn, polity_id)
    _insert_polity_row(
        conn, polity_id,
        species_id=cur["species_id"],
        name=cur["name"],
        capital_system_id=cur["capital_system_id"],
        treasury_ru=cur["treasury_ru"] + delta_ru,
        expansionism=cur["expansionism"],
        aggression=cur["aggression"],
        risk_appetite=cur["risk_appetite"],
        processing_order=cur["processing_order"],
        founded_tick=cur["founded_tick"],
        jump_level=cur["jump_level"],
        status=cur["status"],
        tick=tick,
        seq=seq,
    )


def set_polity_status(
    conn: sqlite3.Connection, polity_id: int, status: str,
    tick: int = 0, seq: int = 0,
) -> None:
    """Update polity status to 'eliminated' or 'vassal'."""
    cur = _current_polity_row(conn, polity_id)
    _insert_polity_row(
        conn, polity_id,
        species_id=cur["species_id"],
        name=cur["name"],
        capital_system_id=cur["capital_system_id"],
        treasury_ru=cur["treasury_ru"],
        expansionism=cur["expansionism"],
        aggression=cur["aggression"],
        risk_appetite=cur["risk_appetite"],
        processing_order=cur["processing_order"],
        founded_tick=cur["founded_tick"],
        jump_level=cur["jump_level"],
        status=status,
        tick=tick,
        seq=seq,
    )


def set_capital(
    conn: sqlite3.Connection, polity_id: int, system_id: int,
    tick: int = 0, seq: int = 0,
) -> None:
    """Set or change the capital system for a polity."""
    cur = _current_polity_row(conn, polity_id)
    _insert_polity_row(
        conn, polity_id,
        species_id=cur["species_id"],
        name=cur["name"],
        capital_system_id=system_id,
        treasury_ru=cur["treasury_ru"],
        expansionism=cur["expansionism"],
        aggression=cur["aggression"],
        risk_appetite=cur["risk_appetite"],
        processing_order=cur["processing_order"],
        founded_tick=cur["founded_tick"],
        jump_level=cur["jump_level"],
        status=cur["status"],
        tick=tick,
        seq=seq,
    )


_JUMP_UPGRADE_STEP: int = 2   # parsecs added per upgrade
_JUMP_UPGRADE_MAX: int  = 20  # hard ceiling


def get_jump_upgrade_cost(current_level: int = 10) -> float:
    """Return RU cost to upgrade from current_level.  Doubles every step.

      J10→J12:  75 RU
      J12→J14: 150 RU
      J14→J16: 300 RU
      J16→J18: 600 RU
      J18→J20: 1200 RU
    """
    steps_taken = (current_level - 10) // 2
    return 75.0 * (2.0 ** steps_taken)


def upgrade_jump_level(
    conn: sqlite3.Connection, polity_id: int,
    tick: int = 0, seq: int = 0,
) -> int:
    """Increment polity jump_level by one step and deduct cost from treasury.

    Returns the new jump_level, or current level if already at max.
    """
    cur = _current_polity_row(conn, polity_id)
    current = cur["jump_level"]
    if current >= _JUMP_UPGRADE_MAX:
        return current
    new_level = min(current + _JUMP_UPGRADE_STEP, _JUMP_UPGRADE_MAX)
    cost = get_jump_upgrade_cost(current)
    _insert_polity_row(
        conn, polity_id,
        species_id=cur["species_id"],
        name=cur["name"],
        capital_system_id=cur["capital_system_id"],
        treasury_ru=cur["treasury_ru"] - cost,
        expansionism=cur["expansionism"],
        aggression=cur["aggression"],
        risk_appetite=cur["risk_appetite"],
        processing_order=cur["processing_order"],
        founded_tick=cur["founded_tick"],
        jump_level=new_level,
        status=cur["status"],
        tick=tick,
        seq=seq,
    )
    return new_level


# ---------------------------------------------------------------------------
# Read functions  (use Polity_head view / ORDER BY row_id DESC LIMIT 1)
# ---------------------------------------------------------------------------

def get_polity(conn: sqlite3.Connection, polity_id: int) -> PolityRow:
    """Fetch a single polity's current state.  Raises KeyError if not found."""
    row = conn.execute(
        "SELECT * FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Polity {polity_id} not found")
    return _row_to_polity(row)


def get_all_polities(conn: sqlite3.Connection) -> list[PolityRow]:
    """Return all polities (current state) ordered by processing_order."""
    rows = conn.execute(
        "SELECT * FROM Polity_head ORDER BY processing_order"
    ).fetchall()
    return [_row_to_polity(r) for r in rows]


def get_active_polities(conn: sqlite3.Connection) -> list[PolityRow]:
    """Return only active polities, ordered by processing_order."""
    rows = conn.execute(
        "SELECT * FROM Polity_head WHERE status = 'active' ORDER BY processing_order"
    ).fetchall()
    return [_row_to_polity(r) for r in rows]


def get_polity_processing_order(conn: sqlite3.Connection) -> list[int]:
    """Return polity_ids of active polities in processing order."""
    rows = conn.execute(
        "SELECT polity_id FROM Polity_head WHERE status = 'active' ORDER BY processing_order"
    ).fetchall()
    return [r["polity_id"] for r in rows]
