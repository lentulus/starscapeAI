"""Assault phase — Phase 6 of each tick.

For each body where an at-war polity has landed armies and naval superiority,
resolve one tick of ground combat.

Seeded randomness:
    rng = rng_factory(system_id ^ body_id)  — unique per body per tick
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_assault_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade | None = None,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Assault phase for all eligible bodies.

    Returns human-readable summary strings for each ground combat tick.
    """
    if rng_factory is None:
        rng_factory = lambda seed: Random(hash((tick, phase_num, seed)))  # noqa: E731

    summaries: list[str] = []

    for system_id, body_id, attacker_id, defender_id in game.find_assault_candidates():
        rng = rng_factory(system_id ^ (body_id or 0))
        result = game.run_ground_assault(
            system_id, body_id, attacker_id, defender_id, tick, rng
        )
        if result is not None:
            summaries.append(
                f"tick={tick} assault system={result.system_id} body={result.body_id} "
                f"attacker={result.attacker_id} outcome={result.outcome} "
                f"net={result.net_shift:+d} "
                f"atk_str={result.attacker_str_before}→{result.attacker_str_after} "
                f"def_str={result.defender_str_before}→{result.defender_str_after}"
            )
            if result.control_changed:
                summaries.append(
                    f"tick={tick} control_change system={result.system_id} "
                    f"body={result.body_id} new_state={result.new_control_state}"
                )

    return summaries
