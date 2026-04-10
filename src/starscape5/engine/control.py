"""Control update phase — Phase 7 of each tick.

Responsibilities:
  1. At 25-week checkpoints, roll development advancement for each presence.
  2. Roll state advancement (outpost→colony→controlled) if colonist delivery
     thresholds are met.
  3. Log control_change events for any transitions.

Seeded randomness first appears here:
    rng = rng_factory(processing_order)
    where rng_factory = lambda po: Random(hash((tick, phase_num, po)))

This guarantees deterministic replay: same tick/phase/order → same rolls.
World is not required (all data comes from game.db).
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade


def run_control_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world=None,  # unused; accepted for uniform phase signature
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Control update phase for all active polities.

    Returns human-readable summary strings for changed presences.
    """
    if rng_factory is None:
        rng_factory = lambda po: Random(hash((tick, phase_num, po)))  # noqa: E731

    summaries: list[str] = []

    for processing_order, polity_id in enumerate(polity_order, start=1):
        rng = rng_factory(processing_order)
        advances = game.check_growth_cycles(polity_id, tick, rng)
        for adv in advances:
            summaries.append(
                f"tick={tick} polity={polity_id} "
                f"system={adv.system_id} "
                f"state={adv.old_state}→{adv.new_state} "
                f"dev={adv.old_dev}→{adv.new_dev}"
            )

    return summaries
