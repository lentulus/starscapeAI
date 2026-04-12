"""Fleet, Squadron, and Hull — the naval layer of game state.

Hierarchy:  Fleet  →  Squadron (same hull_type)  →  Hull (individual ship)

SDBs are squadroned but never assigned to a fleet (fleet_id=NULL); they are
fixed to a system.  All other warships belong to both a squadron and a fleet.
Logistics hulls (troop, transport, colony_transport, scout) belong to a fleet
but not a squadron.

Fleet and Squadron are NOT temporal (normal UPDATE-based mutation).
Hull IS temporal: append-only; all mutations INSERT new rows (copy-on-write).
hull_id is the logical entity key; row_id is the physical autoincrement PK.
Use Hull_head view or ORDER BY row_id DESC LIMIT 1 for current state.

Strength computation rules (units.md):
  - Destroyed hulls contribute nothing.
  - Damaged hulls contribute half Attack and half Defence (round down).
  - Bombard is unaffected by damage.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .constants import HULL_STATS


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FleetRow:
    fleet_id: int
    polity_id: int
    name: str
    system_id: int | None
    destination_system_id: int | None
    destination_tick: int | None
    admiral_id: int | None
    supply_ticks: int
    status: str  # 'active' | 'in_transit' | 'destroyed'


@dataclass
class SquadronRow:
    squadron_id: int
    fleet_id: int | None
    polity_id: int
    name: str
    hull_type: str
    combat_role: str  # 'screen' | 'line_of_battle' | 'reserve'
    system_id: int | None
    status: str  # 'active' | 'destroyed'


@dataclass
class HullRow:
    hull_id: int
    polity_id: int
    name: str
    hull_type: str
    squadron_id: int | None
    fleet_id: int | None
    system_id: int | None
    destination_system_id: int | None
    destination_tick: int | None
    status: str  # 'active' | 'damaged' | 'establishing' | 'in_transit' | 'destroyed'
    marine_designated: int
    cargo_type: str | None
    cargo_id: int | None
    establish_tick: int | None
    created_tick: int


# ---------------------------------------------------------------------------
# Internal Hull copy-on-write helpers
# ---------------------------------------------------------------------------

def _current_hull_row(conn: sqlite3.Connection, hull_id: int) -> sqlite3.Row:
    """Return the most recent raw row for hull_id."""
    row = conn.execute(
        "SELECT * FROM Hull WHERE hull_id = ? ORDER BY row_id DESC LIMIT 1",
        (hull_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Hull {hull_id} not found")
    return row


def _insert_hull_row(
    conn: sqlite3.Connection,
    hull_id: int,
    polity_id: int,
    name: str,
    hull_type: str,
    squadron_id: int | None,
    fleet_id: int | None,
    system_id: int | None,
    destination_system_id: int | None,
    destination_tick: int | None,
    status: str,
    marine_designated: int,
    cargo_type: str | None,
    cargo_id: int | None,
    establish_tick: int | None,
    created_tick: int,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO Hull
            (hull_id, tick, seq, polity_id, name, hull_type, squadron_id,
             fleet_id, system_id, destination_system_id, destination_tick,
             status, marine_designated, cargo_type, cargo_id,
             establish_tick, created_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (hull_id, tick, seq, polity_id, name, hull_type, squadron_id,
         fleet_id, system_id, destination_system_id, destination_tick,
         status, marine_designated, cargo_type, cargo_id,
         establish_tick, created_tick),
    )


# ---------------------------------------------------------------------------
# Fleet  (non-temporal — normal UPDATEs)
# ---------------------------------------------------------------------------

def create_fleet(
    conn: sqlite3.Connection,
    polity_id: int,
    name: str,
    system_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO Fleet (polity_id, name, system_id) VALUES (?, ?, ?)",
        (polity_id, name, system_id),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_fleet(conn: sqlite3.Connection, fleet_id: int) -> FleetRow:
    row = conn.execute(
        "SELECT * FROM Fleet WHERE fleet_id = ?", (fleet_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Fleet {fleet_id} not found")
    return _row_to_fleet(row)


def get_fleets_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[FleetRow]:
    rows = conn.execute(
        "SELECT * FROM Fleet WHERE system_id = ? AND status != 'destroyed'",
        (system_id,),
    ).fetchall()
    return [_row_to_fleet(r) for r in rows]


def get_hostile_fleets(
    conn: sqlite3.Connection, system_id: int, polity_id: int
) -> list[FleetRow]:
    """Return active fleets in system_id that belong to a different polity."""
    rows = conn.execute(
        """
        SELECT * FROM Fleet
        WHERE  system_id = ? AND polity_id != ? AND status = 'active'
        """,
        (system_id, polity_id),
    ).fetchall()
    return [_row_to_fleet(r) for r in rows]


def get_fleets_by_polity(
    conn: sqlite3.Connection, polity_id: int
) -> list[FleetRow]:
    rows = conn.execute(
        "SELECT * FROM Fleet WHERE polity_id = ? AND status != 'destroyed'",
        (polity_id,),
    ).fetchall()
    return [_row_to_fleet(r) for r in rows]


def set_fleet_destination(
    conn: sqlite3.Connection,
    fleet_id: int,
    destination_system_id: int,
    destination_tick: int,
) -> None:
    conn.execute(
        """
        UPDATE Fleet
        SET destination_system_id = ?, destination_tick = ?, status = 'in_transit'
        WHERE fleet_id = ?
        """,
        (destination_system_id, destination_tick, fleet_id),
    )


def arrive_fleet(
    conn: sqlite3.Connection, fleet_id: int, system_id: int, tick: int = 0
) -> None:
    """Complete an in-transit fleet's arrival at its destination."""
    conn.execute(
        """
        UPDATE Fleet
        SET system_id = ?, destination_system_id = NULL,
            destination_tick = NULL, status = 'active'
        WHERE fleet_id = ?
        """,
        (system_id, fleet_id),
    )
    # Move all hulls in the fleet to the new system (temporal INSERT per hull).
    in_transit = conn.execute(
        """
        SELECT * FROM Hull_head
        WHERE fleet_id = ? AND status = 'in_transit'
        """,
        (fleet_id,),
    ).fetchall()
    for h in in_transit:
        _insert_hull_row(
            conn, hull_id=h["hull_id"],
            polity_id=h["polity_id"],
            name=h["name"],
            hull_type=h["hull_type"],
            squadron_id=h["squadron_id"],
            fleet_id=h["fleet_id"],
            system_id=system_id,
            destination_system_id=None,
            destination_tick=None,
            status="active",
            marine_designated=h["marine_designated"],
            cargo_type=h["cargo_type"],
            cargo_id=h["cargo_id"],
            establish_tick=h["establish_tick"],
            created_tick=h["created_tick"],
            tick=tick, seq=0,
        )


def update_fleet_supply(
    conn: sqlite3.Connection, fleet_id: int, ticks_increment: int
) -> None:
    conn.execute(
        "UPDATE Fleet SET supply_ticks = supply_ticks + ? WHERE fleet_id = ?",
        (ticks_increment, fleet_id),
    )


def reset_fleet_supply(conn: sqlite3.Connection, fleet_id: int) -> None:
    conn.execute(
        "UPDATE Fleet SET supply_ticks = 0 WHERE fleet_id = ?",
        (fleet_id,),
    )


def _row_to_fleet(row: sqlite3.Row) -> FleetRow:
    return FleetRow(
        fleet_id=row["fleet_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        system_id=row["system_id"],
        destination_system_id=row["destination_system_id"],
        destination_tick=row["destination_tick"],
        admiral_id=row["admiral_id"],
        supply_ticks=row["supply_ticks"],
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# Squadron  (non-temporal — normal UPDATEs)
# ---------------------------------------------------------------------------

def create_squadron(
    conn: sqlite3.Connection,
    fleet_id: int | None,
    polity_id: int,
    name: str,
    hull_type: str,
    combat_role: str,
    system_id: int | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO Squadron
            (fleet_id, polity_id, name, hull_type, combat_role, system_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fleet_id, polity_id, name, hull_type, combat_role, system_id),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_squadrons_in_fleet(
    conn: sqlite3.Connection, fleet_id: int
) -> list[SquadronRow]:
    rows = conn.execute(
        "SELECT * FROM Squadron WHERE fleet_id = ? AND status = 'active'",
        (fleet_id,),
    ).fetchall()
    return [_row_to_squadron(r) for r in rows]


def get_squadrons_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[SquadronRow]:
    """Return active squadrons located in a system (includes SDBs)."""
    rows = conn.execute(
        "SELECT * FROM Squadron WHERE system_id = ? AND status = 'active'",
        (system_id,),
    ).fetchall()
    return [_row_to_squadron(r) for r in rows]


def assign_combat_role(
    conn: sqlite3.Connection, squadron_id: int, role: str
) -> None:
    conn.execute(
        "UPDATE Squadron SET combat_role = ? WHERE squadron_id = ?",
        (role, squadron_id),
    )


def compute_squadron_strength(
    conn: sqlite3.Connection, squadron_id: int
) -> dict[str, int]:
    """Return {attack, bombard, defence} summed across non-destroyed hulls.

    Damaged hulls contribute half attack and half defence (floor); bombard
    is unaffected by damage (units.md §Damaged state).
    """
    hulls = conn.execute(
        "SELECT hull_type, status FROM Hull_head WHERE squadron_id = ? AND status != 'destroyed'",
        (squadron_id,),
    ).fetchall()

    attack = defence = bombard = 0
    for h in hulls:
        stats = HULL_STATS[h["hull_type"]]
        if h["status"] == "damaged":
            attack += stats.attack // 2
            defence += stats.defence // 2
        else:
            attack += stats.attack
            defence += stats.defence
        bombard += stats.bombard
    return {"attack": attack, "bombard": bombard, "defence": defence}


def _row_to_squadron(row: sqlite3.Row) -> SquadronRow:
    return SquadronRow(
        squadron_id=row["squadron_id"],
        fleet_id=row["fleet_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        hull_type=row["hull_type"],
        combat_role=row["combat_role"],
        system_id=row["system_id"],
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# Hull  (temporal — INSERT-based copy-on-write)
# ---------------------------------------------------------------------------

def create_hull(
    conn: sqlite3.Connection,
    polity_id: int,
    name: str,
    hull_type: str,
    system_id: int | None,
    fleet_id: int | None,
    squadron_id: int | None,
    created_tick: int,
    marine_designated: int = 0,
) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(hull_id), 0) + 1 FROM Hull"
    ).fetchone()
    hull_id: int = row[0]
    _insert_hull_row(
        conn, hull_id=hull_id,
        polity_id=polity_id,
        name=name,
        hull_type=hull_type,
        squadron_id=squadron_id,
        fleet_id=fleet_id,
        system_id=system_id,
        destination_system_id=None,
        destination_tick=None,
        status="active",
        marine_designated=marine_designated,
        cargo_type=None,
        cargo_id=None,
        establish_tick=None,
        created_tick=created_tick,
        tick=created_tick, seq=0,
    )
    return hull_id


def get_hull(conn: sqlite3.Connection, hull_id: int) -> HullRow:
    row = conn.execute(
        "SELECT * FROM Hull WHERE hull_id = ? ORDER BY row_id DESC LIMIT 1",
        (hull_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Hull {hull_id} not found")
    return _row_to_hull(row)


def get_hulls_in_fleet(
    conn: sqlite3.Connection, fleet_id: int
) -> list[HullRow]:
    rows = conn.execute(
        "SELECT * FROM Hull_head WHERE fleet_id = ? AND status != 'destroyed'",
        (fleet_id,),
    ).fetchall()
    return [_row_to_hull(r) for r in rows]


def get_hulls_in_system(
    conn: sqlite3.Connection, system_id: int
) -> list[HullRow]:
    rows = conn.execute(
        "SELECT * FROM Hull_head WHERE system_id = ? AND status != 'destroyed'",
        (system_id,),
    ).fetchall()
    return [_row_to_hull(r) for r in rows]


def get_hulls_in_squadron(
    conn: sqlite3.Connection, squadron_id: int
) -> list[HullRow]:
    rows = conn.execute(
        "SELECT * FROM Hull_head WHERE squadron_id = ? AND status != 'destroyed'",
        (squadron_id,),
    ).fetchall()
    return [_row_to_hull(r) for r in rows]


def mark_hull_damaged(conn: sqlite3.Connection, hull_id: int, tick: int = 0, seq: int = 0) -> None:
    cur = _current_hull_row(conn, hull_id)
    _insert_hull_row(
        conn, hull_id=hull_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        hull_type=cur["hull_type"],
        squadron_id=cur["squadron_id"],
        fleet_id=cur["fleet_id"],
        system_id=cur["system_id"],
        destination_system_id=cur["destination_system_id"],
        destination_tick=cur["destination_tick"],
        status="damaged",
        marine_designated=cur["marine_designated"],
        cargo_type=cur["cargo_type"],
        cargo_id=cur["cargo_id"],
        establish_tick=cur["establish_tick"],
        created_tick=cur["created_tick"],
        tick=tick, seq=seq,
    )


def mark_hull_destroyed(conn: sqlite3.Connection, hull_id: int, tick: int = 0, seq: int = 0) -> None:
    cur = _current_hull_row(conn, hull_id)
    _insert_hull_row(
        conn, hull_id=hull_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        hull_type=cur["hull_type"],
        squadron_id=cur["squadron_id"],
        fleet_id=cur["fleet_id"],
        system_id=cur["system_id"],
        destination_system_id=cur["destination_system_id"],
        destination_tick=cur["destination_tick"],
        status="destroyed",
        marine_designated=cur["marine_designated"],
        cargo_type=cur["cargo_type"],
        cargo_id=cur["cargo_id"],
        establish_tick=cur["establish_tick"],
        created_tick=cur["created_tick"],
        tick=tick, seq=seq,
    )


def mark_hull_active(conn: sqlite3.Connection, hull_id: int, tick: int = 0, seq: int = 0) -> None:
    """Restore a damaged hull to active (after repair)."""
    cur = _current_hull_row(conn, hull_id)
    _insert_hull_row(
        conn, hull_id=hull_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        hull_type=cur["hull_type"],
        squadron_id=cur["squadron_id"],
        fleet_id=cur["fleet_id"],
        system_id=cur["system_id"],
        destination_system_id=cur["destination_system_id"],
        destination_tick=cur["destination_tick"],
        status="active",
        marine_designated=cur["marine_designated"],
        cargo_type=cur["cargo_type"],
        cargo_id=cur["cargo_id"],
        establish_tick=cur["establish_tick"],
        created_tick=cur["created_tick"],
        tick=tick, seq=seq,
    )


def _row_to_hull(row: sqlite3.Row) -> HullRow:
    return HullRow(
        hull_id=row["hull_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        hull_type=row["hull_type"],
        squadron_id=row["squadron_id"],
        fleet_id=row["fleet_id"],
        system_id=row["system_id"],
        destination_system_id=row["destination_system_id"],
        destination_tick=row["destination_tick"],
        status=row["status"],
        marine_designated=row["marine_designated"],
        cargo_type=row["cargo_type"],
        cargo_id=row["cargo_id"],
        establish_tick=row["establish_tick"],
        created_tick=row["created_tick"],
    )
