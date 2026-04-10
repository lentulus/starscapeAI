"""Decision phase — Phase 2 of each tick.

Full behavioural decision engine:
  1. Roll war initiation for all in-contact non-war pairs.
  2. For each polity (in processing order):
     a. Build a GameStateSnapshot (read-only DB view).
     b. Draw a strategic posture (weighted by disposition + state).
     c. Generate and score all candidate actions.
     d. Select top-k actions by softmax-weighted sampling.
     e. Execute selected actions (issue jumps, place build orders, etc.).

Seeded randomness:
    war_rng = rng_factory(0)            — one RNG for all war rolls this tick
    polity_rng = rng_factory(polity_id) — one RNG per polity for posture + action

Using polity_id (not processing_order) as the discriminator for the posture
RNG means a polity's decisions are reproducible regardless of how many other
polities exist or what order they are processed in.
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.actions import generate_candidates, select_actions
from starscape5.game.facade import GameFacade
from starscape5.game.posture import draw_posture
from starscape5.world.facade import WorldFacade


def run_decision_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the full Decision phase for all active polities.

    Returns human-readable summary strings for all significant orders issued.
    """
    if rng_factory is None:
        rng_factory = lambda seed: Random(hash((tick, phase_num, seed)))  # noqa: E731

    summaries: list[str] = []

    # Step 1: War initiation rolls (once per tick; single shared RNG)
    war_rng = rng_factory(0)
    wars = game.process_war_rolls(tick, war_rng)
    for w in wars:
        summaries.append(
            f"tick={tick} war_declared polity_a={w.polity_a_id} "
            f"polity_b={w.polity_b_id} initiator={w.initiator_id} "
            f"name={w.war_name!r}"
        )

    # Step 2: Per-polity decisions
    for polity_id in polity_order:
        snap = game.build_snapshot(polity_id, tick)
        if snap is None:
            continue

        polity_rng = rng_factory(polity_id)
        posture = draw_posture(snap, polity_rng)

        candidates = generate_candidates(
            snap, posture,
            world_neighbor_fn=world.get_systems_within_parsecs,
        )

        selected = select_actions(candidates, polity_rng, top_k=5)

        action_summaries = game.execute_actions(polity_id, selected, world, tick)
        summaries.extend(action_summaries)

        if action_summaries:
            summaries.insert(
                summaries.index(action_summaries[0]),
                f"tick={tick} polity={polity_id} posture={posture.value}",
            )

    return summaries
