"""Polity — civilisation-level state.

Each Polity represents one politically independent actor in the simulation.
A species with faction_tendency > 0.85 spawns multiple polities at game start.

All write functions take an open game.db connection and return the new
primary key (or None for updates).  Callers are responsible for committing
at phase boundaries via game.state.commit_phase().
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
        status=row["status"],
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
    cur = conn.execute(
        """
        INSERT INTO Polity
            (species_id, name, capital_system_id,
             treasury_ru, expansionism, aggression, risk_appetite,
             processing_order, founded_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (species_id, name, capital_system_id,
         treasury_ru, expansionism, aggression, risk_appetite,
         processing_order, founded_tick),
    )
    return cur.lastrowid  # type: ignore[return-value]


def update_treasury(
    conn: sqlite3.Connection, polity_id: int, delta_ru: float
) -> None:
    """Add delta_ru to the polity's treasury (delta may be negative)."""
    conn.execute(
        "UPDATE Polity SET treasury_ru = treasury_ru + ? WHERE polity_id = ?",
        (delta_ru, polity_id),
    )


def set_polity_status(
    conn: sqlite3.Connection, polity_id: int, status: str
) -> None:
    """Update polity status to 'eliminated' or 'vassal'."""
    conn.execute(
        "UPDATE Polity SET status = ? WHERE polity_id = ?",
        (status, polity_id),
    )


def set_capital(
    conn: sqlite3.Connection, polity_id: int, system_id: int
) -> None:
    """Set or change the capital system for a polity."""
    conn.execute(
        "UPDATE Polity SET capital_system_id = ? WHERE polity_id = ?",
        (system_id, polity_id),
    )


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def get_polity(conn: sqlite3.Connection, polity_id: int) -> PolityRow:
    """Fetch a single polity.  Raises KeyError if not found."""
    row = conn.execute(
        "SELECT * FROM Polity WHERE polity_id = ?", (polity_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Polity {polity_id} not found")
    return _row_to_polity(row)


def get_all_polities(conn: sqlite3.Connection) -> list[PolityRow]:
    """Return all polities ordered by processing_order."""
    rows = conn.execute(
        "SELECT * FROM Polity ORDER BY processing_order"
    ).fetchall()
    return [_row_to_polity(r) for r in rows]


def get_active_polities(conn: sqlite3.Connection) -> list[PolityRow]:
    """Return only active polities, ordered by processing_order."""
    rows = conn.execute(
        "SELECT * FROM Polity WHERE status = 'active' ORDER BY processing_order"
    ).fetchall()
    return [_row_to_polity(r) for r in rows]


def get_polity_processing_order(conn: sqlite3.Connection) -> list[int]:
    """Return polity_ids of active polities in processing order."""
    rows = conn.execute(
        "SELECT polity_id FROM Polity WHERE status = 'active' ORDER BY processing_order"
    ).fetchall()
    return [r["polity_id"] for r in rows]
