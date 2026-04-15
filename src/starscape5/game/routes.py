"""Jump route recording — builds the deduped travel graph in JumpRoute.

Recording fires after every fleet arrival.  Routes are stored in canonical
order (from_system_id < to_system_id) so A→B and B→A are the same row.
INSERT OR IGNORE deduplicates naturally; each unique pair is recorded once
with the first_tick it was jumped.

GameState.routes_complete is retained as informational metadata (set
elsewhere) but no longer gates recording — routes accumulate for the full
lifetime of the simulation.
"""

from __future__ import annotations

import sqlite3

from starscape5.world.facade import WorldFacade


def record_jump_route(
    conn: sqlite3.Connection,
    world: WorldFacade,
    from_system_id: int,
    to_system_id: int,
    tick: int,
) -> bool:
    """Record the route between two systems if not already present.

    Skips silently if:
      - either system_id is None / 0
      - the route already exists (INSERT OR IGNORE also deduplicates)

    Returns True if a new row was inserted.
    """
    if not from_system_id or not to_system_id:
        return False
    if from_system_id == to_system_id:
        return False

    # Canonical order: lower ID first
    a = min(from_system_id, to_system_id)
    b = max(from_system_id, to_system_id)

    existing = conn.execute(
        "SELECT 1 FROM JumpRoute WHERE from_system_id = ? AND to_system_id = ?",
        (a, b),
    ).fetchone()
    if existing:
        return False

    pos_a = world.get_star_position(a)
    pos_b = world.get_star_position(b)
    dist_pc = pos_a.distance_pc_to(pos_b)

    conn.execute(
        """
        INSERT OR IGNORE INTO JumpRoute
            (from_system_id, to_system_id, dist_pc,
             from_x_mpc, from_y_mpc, from_z_mpc,
             to_x_mpc,   to_y_mpc,   to_z_mpc,
             first_tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (a, b, dist_pc,
         pos_a.x_mpc, pos_a.y_mpc, pos_a.z_mpc,
         pos_b.x_mpc, pos_b.y_mpc, pos_b.z_mpc,
         tick),
    )

    return True


def all_homeworlds_linked(conn: sqlite3.Connection) -> bool:
    """Return True when all polity capital systems are in one connected component.

    Uses a simple in-memory Union-Find over the full JumpRoute graph.
    """
    capital_rows = conn.execute(
        "SELECT DISTINCT capital_system_id FROM Polity_head "
        "WHERE capital_system_id IS NOT NULL AND status = 'active'"
    ).fetchall()
    capitals = {r["capital_system_id"] for r in capital_rows}

    if len(capitals) <= 1:
        return True

    routes = conn.execute(
        "SELECT from_system_id, to_system_id FROM JumpRoute"
    ).fetchall()

    # Union-Find (path compression, dict-based for arbitrary system IDs)
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])  # path halving
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for r in routes:
        union(r["from_system_id"], r["to_system_id"])

    cap_list = list(capitals)
    root = find(cap_list[0])
    return all(find(c) == root for c in cap_list[1:])
