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
    UpgradeJumpAction,
)
from .constants import HULL_STATS
from .movement import execute_jump, get_fleet_jump_range
from .events import write_event
from .polity import upgrade_jump_level, get_jump_upgrade_cost, update_treasury


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
    if isinstance(action, UpgradeJumpAction):
        return _execute_upgrade_jump(conn, polity_id, action, tick)
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

    # Verify destination is reachable using polity jump level
    polity_jl = conn.execute(
        "SELECT jump_level FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    polity_jump_level = polity_jl["jump_level"] if polity_jl else None
    jump_range = get_fleet_jump_range(conn, action.fleet_id, polity_jump_level)
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
        "SELECT treasury_ru FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    if treasury is None or treasury["treasury_ru"] < stats.build_cost:
        return None

    # Reserve RU (temporal INSERT via update_treasury)
    update_treasury(conn, polity_id, -stats.build_cost, tick=tick, seq=2)

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


def _execute_upgrade_jump(
    conn: sqlite3.Connection,
    polity_id: int,
    action: "UpgradeJumpAction",
    tick: int,
) -> str | None:
    """Spend RU to increase polity scout jump range by one step."""
    row = conn.execute(
        "SELECT treasury_ru, jump_level FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    if row is None:
        return None
    cost = get_jump_upgrade_cost()
    if row["treasury_ru"] < cost:
        return None
    old_level = row["jump_level"]
    new_level = upgrade_jump_level(conn, polity_id)
    if new_level == old_level:
        return None  # already at max
    polity_name = conn.execute(
        "SELECT name FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()["name"]
    write_event(
        conn, tick=tick, phase=2,
        event_type="jump_upgrade",
        summary=f"{polity_name}: scout jump J{old_level}→J{new_level}",
        polity_a_id=polity_id,
    )
    return (
        f"tick={tick} polity={polity_id} jump_upgrade "
        f"J{old_level}→J{new_level} cost={cost:.0f}RU"
    )
