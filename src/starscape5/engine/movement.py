"""Movement phase — Phase 3 of each tick.

Responsibilities:
  1. Process arrivals: settle all in-transit fleets whose destination_tick
     equals the current tick.
  2. Record a full visit for each arrived fleet's polity at the arrival system.
  3. Detect new inter-polity contacts at each arrival system.
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_movement_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Movement phase.

    Returns human-readable summaries for arrivals and new contacts.
    """
    summaries: list[str] = []

    arrivals = game.process_arrivals(tick)
    for fleet_id, polity_id, system_id, prev_system_id in arrivals:
        game.record_visit(polity_id, system_id, world, tick)
        contacts = game.detect_contacts(system_id, tick)
        summaries.append(
            f"tick={tick} arrived fleet={fleet_id} polity={polity_id} system={system_id}"
        )
        for a, b in contacts:
            summaries.append(
                f"tick={tick} contact polity_a={a} polity_b={b} system={system_id}"
            )
        if prev_system_id is not None:
            game.record_jump_route(prev_system_id, system_id, tick, world)
        delivery = game.deliver_colonists(fleet_id, polity_id, system_id, world, tick)
        if delivery:
            summaries.append(delivery)

    return summaries
