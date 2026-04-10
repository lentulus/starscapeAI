"""Intelligence phase — Phase 1 of each tick.

Responsibilities:
  1. Passive scan: for each polity, update SystemIntelligence for all systems
     within 20 pc of a Controlled/Colony world (gas_giant + ocean flags only).
  2. Increment peace_weeks on all non-war ContactRecord rows.
  3. Check map sharing: fire intel exchange for pairs at peace >= 52 weeks.

World is required for this phase (passive scan queries positions and flags).
RNG is unused (no random decisions in intelligence phase).
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_intelligence_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Intelligence phase for all active polities.

    Returns human-readable summary strings.
    """
    summaries: list[str] = []

    for polity_id in polity_order:
        n = game.update_passive_scan(polity_id, world, tick)
        if n:
            summaries.append(
                f"tick={tick} polity={polity_id} passive_scan={n} systems"
            )

    # Peace week increment (once per tick, not per polity)
    game.increment_peace_weeks()

    # Map sharing (once per tick)
    pairs = game.check_map_sharing(tick)
    for a, b in pairs:
        summaries.append(
            f"tick={tick} map_shared polity_a={a} polity_b={b}"
        )

    return summaries
