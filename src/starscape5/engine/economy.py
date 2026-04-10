"""Economy phase — Phase 8 of each tick.

Responsibilities (in order):
  1. Collect RU production for each active polity (all presences).
  2. Pay maintenance for all hulls and ground forces.
  3. Apply supply degradation for fleets on extended deployment.
  4. Advance build queues; deliver completed hulls.
  5. Advance repair queues; restore repaired hulls.

This is the first phase with the standard engine signature:

    run_economy_phase(tick, phase_num, polity_order, game, world, rng_factory)

world is None here — economy uses only the WorldPotential cache in game.db,
never queries the world layer directly.

rng_factory is accepted for signature uniformity but unused in economy phase
(no random decisions needed; all outcomes are deterministic given game state).
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade


def run_economy_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world=None,  # unused; accepted for uniform phase signature
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Economy phase for all active polities.

    Processing order:
      For each polity (in polity_order):
        1. collect_ru
        2. pay_maintenance
        3. apply_supply_degradation
      Then (once, not per-polity):
        4. advance_build_queues
        5. advance_repair_queues

    Build and repair queues are global (all polities share one pass) because
    ticks_elapsed is a simple counter — processing them per-polity would double-
    tick shared queues in a multi-polity scenario.

    Returns a list of human-readable summary strings (one per polity + one for
    completed builds/repairs).  These feed the Event log at M13.
    """
    summaries: list[str] = []

    for polity_id in polity_order:
        produced = game.collect_ru(polity_id, tick)
        paid = game.pay_maintenance(polity_id, tick)
        game.apply_supply_degradation(polity_id, tick)
        summaries.append(
            f"tick={tick} polity={polity_id} "
            f"produced={produced:.1f} maint={paid:.1f} "
            f"net={produced - paid:.1f}"
        )

    completed_hulls = game.advance_build_queues(tick)
    repaired_hulls = game.advance_repair_queues(tick)

    if completed_hulls:
        summaries.append(f"tick={tick} builds_completed={len(completed_hulls)}")
    if repaired_hulls:
        summaries.append(f"tick={tick} repairs_completed={len(repaired_hulls)}")

    return summaries
