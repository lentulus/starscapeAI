"""Bombardment phase — Phase 5 of each tick.

For each system where an at-war polity has naval superiority and the
defender has ground forces, run one tick of orbital bombardment.

Seeded randomness (signature compatible; unused in this phase):
    rng = rng_factory(system_id)
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_bombardment_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade | None = None,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Bombardment phase for all eligible systems.

    Returns human-readable summary strings for each bombardment tick.
    """
    if rng_factory is None:
        rng_factory = lambda sid: Random(hash((tick, phase_num, sid)))  # noqa: E731

    summaries: list[str] = []

    for system_id, attacker_id, defender_id in game.find_bombardment_candidates():
        rng = rng_factory(system_id)
        result = game.run_bombardment_tick(system_id, attacker_id, defender_id, tick, rng)
        if result is not None:
            summaries.append(
                f"tick={tick} bombardment system={result.system_id} "
                f"attacker={result.attacker_id} net_bombard={result.net_bombard} "
                f"ground_str={result.defender_total_before}→{result.defender_total_after}"
            )

    return summaries
