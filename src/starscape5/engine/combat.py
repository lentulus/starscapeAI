"""Combat phase — Phase 4 of each tick.

For each contested system (at-war polity pair with active fleets on both
sides), resolve one round of space combat.  Seeded randomness:

    rng = rng_factory(system_id)
    where rng_factory = lambda sid: Random(hash((tick, phase_num, sid)))

Using system_id as the seed discriminator (not processing_order) ensures
that combat in the same system always produces the same rolls on replay,
regardless of which other systems are also in combat that tick.
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_combat_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade | None = None,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Combat phase for all contested systems.

    Returns human-readable summary strings for each combat round.
    """
    if rng_factory is None:
        rng_factory = lambda sid: Random(hash((tick, phase_num, sid)))  # noqa: E731

    summaries: list[str] = []

    for system_id in game.find_contested_systems():
        rng = rng_factory(system_id)
        results = game.resolve_space_combat(system_id, tick, rng)
        for r in results:
            summaries.append(
                f"tick={tick} combat system={r.system_id} "
                f"polity_a={r.polity_a_id} polity_b={r.polity_b_id} "
                f"hits_on_a={r.hits_on_a} hits_on_b={r.hits_on_b}"
            )
            if r.a_disengaged:
                summaries.append(
                    f"tick={tick} disengage system={r.system_id} polity={r.polity_a_id}"
                )
            if r.b_disengaged:
                summaries.append(
                    f"tick={tick} disengage system={r.system_id} polity={r.polity_b_id}"
                )

    return summaries
