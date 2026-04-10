"""Decision logic — stub implementation (Expand orders only).

The full decision engine (M11) replaces this.  For now, each polity with
an idle scout fleet attempts to jump to the nearest unvisited system within
its jump range.

generate_expand_orders() is the only public entry point.  It is called once
per polity per tick during the Decision phase.
"""

from __future__ import annotations

import sqlite3

from starscape5.world.facade import WorldFacade
from .movement import execute_jump, get_fleet_jump_range


def generate_expand_orders(
    conn: sqlite3.Connection,
    polity_id: int,
    world: WorldFacade,
    tick: int,
) -> list[tuple[int, int]]:
    """Return expand orders for polity_id: one jump per idle scout fleet.

    Returns list of (fleet_id, destination_system_id).
    """
    # Active fleets that contain at least one live scout hull and are at a system.
    scout_fleets = conn.execute(
        """
        SELECT DISTINCT f.fleet_id, f.system_id
        FROM   Fleet f
        JOIN   Hull  h ON h.fleet_id = f.fleet_id
        WHERE  f.polity_id   = ?
          AND  f.status      = 'active'
          AND  f.system_id   IS NOT NULL
          AND  h.hull_type   = 'scout'
          AND  h.status     != 'destroyed'
        """,
        (polity_id,),
    ).fetchall()

    orders: list[tuple[int, int]] = []
    for row in scout_fleets:
        fleet_id  = row["fleet_id"]
        system_id = row["system_id"]

        jump_range = get_fleet_jump_range(conn, fleet_id)
        if jump_range == 0:
            continue

        dest = _nearest_unvisited(conn, polity_id, system_id, world, jump_range)
        if dest is not None:
            orders.append((fleet_id, dest))

    return orders


def _nearest_unvisited(
    conn: sqlite3.Connection,
    polity_id: int,
    from_system_id: int,
    world: WorldFacade,
    jump_range_pc: int,
) -> int | None:
    """Return the nearest system in jump range that this polity has not visited."""
    candidates = world.get_systems_within_parsecs(
        from_system_id, float(jump_range_pc)
    )

    visited = {
        r["system_id"]
        for r in conn.execute(
            """
            SELECT system_id FROM SystemIntelligence
            WHERE  polity_id = ? AND knowledge_tier = 'visited'
            """,
            (polity_id,),
        ).fetchall()
    }

    best_dist: float | None = None
    best_id:   int   | None = None

    for cand_id in candidates:
        if cand_id == from_system_id or cand_id in visited:
            continue
        dist = world.get_distance_pc(from_system_id, cand_id)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_id   = cand_id

    return best_id
