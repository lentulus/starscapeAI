"""Action executor — translates decided CandidateActions into DB writes.

This is the only place where the output of the decision engine (pure Python
action objects) touches the database.  Each action type has a corresponding
executor that performs the minimal required DB mutation.

All executors return a human-readable summary string.
"""

from __future__ import annotations

import sqlite3

from starscape5.world.facade import WorldFacade

from .actions import (
    AssaultAction, BuildHullAction, CandidateAction, ColoniseAction,
    ConsolidateAction, InitiateWarAction, MoveFleetAction, ScoutAction,
)
from .constants import HULL_STATS
from .movement import execute_jump, get_fleet_jump_range


def execute_actions(
    conn: sqlite3.Connection,
    polity_id: int,
    actions: list[CandidateAction],
    world: WorldFacade,
    tick: int,
) -> list[str]:
    """Execute a list of selected actions.  Returns summary strings."""
    summaries: list[str] = []
    for action in actions:
        summary = _dispatch(conn, polity_id, action, world, tick)
        if summary:
            summaries.append(summary)
    return summaries


def _dispatch(
    conn: sqlite3.Connection,
    polity_id: int,
    action: CandidateAction,
    world: WorldFacade,
    tick: int,
) -> str | None:
    if isinstance(action, ScoutAction):
        return _execute_scout(conn, polity_id, action, tick)
    if isinstance(action, ColoniseAction):
        return _execute_colonise(conn, polity_id, action, tick)
    if isinstance(action, BuildHullAction):
        return _execute_build_hull(conn, polity_id, action, tick)
    if isinstance(action, MoveFleetAction):
        return _execute_move_fleet(conn, polity_id, action, tick)
    if isinstance(action, AssaultAction):
        return _execute_assault(conn, polity_id, action, tick)
    if isinstance(action, ConsolidateAction):
        return None   # no DB mutation; just a priority signal
    if isinstance(action, InitiateWarAction):
        return None   # war declared by process_war_rolls; scoring only here
    return None


def _execute_scout(
    conn: sqlite3.Connection,
    polity_id: int,
    action: ScoutAction,
    tick: int,
) -> str | None:
    """Order the scout fleet to jump."""
    # Verify the fleet still exists and is idle
    row = conn.execute(
        "SELECT system_id, status FROM Fleet WHERE fleet_id = ? AND polity_id = ?",
        (action.fleet_id, polity_id),
    ).fetchone()
    if row is None or row["status"] != "active" or row["system_id"] is None:
        return None

    # Verify destination is reachable
    jump_range = get_fleet_jump_range(conn, action.fleet_id)
    if jump_range == 0:
        return None

    execute_jump(conn, action.fleet_id, action.destination_system_id, tick)
    return (
        f"tick={tick} polity={polity_id} scout fleet={action.fleet_id} "
        f"jump→{action.destination_system_id}"
    )


def _execute_colonise(
    conn: sqlite3.Connection,
    polity_id: int,
    action: ColoniseAction,
    tick: int,
) -> str | None:
    """Order the colony fleet to jump toward target."""
    row = conn.execute(
        "SELECT system_id, status FROM Fleet WHERE fleet_id = ? AND polity_id = ?",
        (action.fleet_id, polity_id),
    ).fetchone()
    if row is None or row["status"] != "active" or row["system_id"] is None:
        return None

    execute_jump(conn, action.fleet_id, action.destination_system_id, tick)
    return (
        f"tick={tick} polity={polity_id} colony fleet={action.fleet_id} "
        f"jump→{action.destination_system_id}"
    )


def _execute_build_hull(
    conn: sqlite3.Connection,
    polity_id: int,
    action: BuildHullAction,
    tick: int,
) -> str | None:
    """Place a hull build order at a shipyard system."""
    stats = HULL_STATS.get(action.hull_type)
    if stats is None:
        return None

    # Check treasury
    treasury = conn.execute(
        "SELECT treasury_ru FROM Polity WHERE polity_id = ?", (polity_id,)
    ).fetchone()
    if treasury is None or treasury["treasury_ru"] < stats.build_cost:
        return None

    # Reserve RU
    conn.execute(
        "UPDATE Polity SET treasury_ru = treasury_ru - ? WHERE polity_id = ?",
        (stats.build_cost, polity_id),
    )

    conn.execute(
        """
        INSERT INTO BuildQueue
            (polity_id, system_id, hull_type, ticks_total, reserved_ru, ordered_tick)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (polity_id, action.system_id, action.hull_type,
         stats.build_time, stats.build_cost, tick),
    )
    return (
        f"tick={tick} polity={polity_id} build_order hull_type={action.hull_type} "
        f"system={action.system_id} cost={stats.build_cost:.0f}RU"
    )


def _execute_move_fleet(
    conn: sqlite3.Connection,
    polity_id: int,
    action: MoveFleetAction,
    tick: int,
) -> str | None:
    row = conn.execute(
        "SELECT system_id, status FROM Fleet WHERE fleet_id = ? AND polity_id = ?",
        (action.fleet_id, polity_id),
    ).fetchone()
    if row is None or row["status"] != "active" or row["system_id"] is None:
        return None

    execute_jump(conn, action.fleet_id, action.destination_system_id, tick)
    return (
        f"tick={tick} polity={polity_id} fleet={action.fleet_id} "
        f"move→{action.destination_system_id}"
    )


def _execute_assault(
    conn: sqlite3.Connection,
    polity_id: int,
    action: AssaultAction,
    tick: int,
) -> str | None:
    row = conn.execute(
        "SELECT system_id, status FROM Fleet WHERE fleet_id = ? AND polity_id = ?",
        (action.fleet_id, polity_id),
    ).fetchone()
    if row is None or row["status"] != "active" or row["system_id"] is None:
        return None

    execute_jump(conn, action.fleet_id, action.target_system_id, tick)
    return (
        f"tick={tick} polity={polity_id} assault fleet={action.fleet_id} "
        f"jump→{action.target_system_id}"
    )
