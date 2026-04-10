"""Decision phase — Phase 2 of each tick.

Stub implementation: generates Expand orders only (move each idle scout
fleet toward the nearest unvisited system within jump range).

Full decision engine comes at M11.
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_decision_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Decision phase (stub) for all active polities.

    Returns human-readable summaries for issued jump orders.
    """
    summaries: list[str] = []

    for polity_id in polity_order:
        orders = game.generate_expand_orders(polity_id, world, tick)
        for fleet_id, dest_id in orders:
            game.execute_jump(fleet_id, dest_id, tick)
            summaries.append(
                f"tick={tick} polity={polity_id} fleet={fleet_id} jump→{dest_id}"
            )

    return summaries
