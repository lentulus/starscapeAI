"""Log phase — Phase 9 of each tick.

Classifies the tick and, on every 4th tick (simulated month boundary),
writes a monthly_summary event to compress quiet history.
"""

from __future__ import annotations

from random import Random
from typing import Callable

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade


def run_log_phase(
    tick: int,
    phase_num: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade | None = None,
    rng_factory: Callable[[int], Random] | None = None,
) -> list[str]:
    """Run the Log phase for tick.

    Returns summary strings (non-empty only when a monthly summary is written).
    """
    summaries: list[str] = []

    events_this_tick = game.get_events_for_tick(tick)
    quiet = game.is_quiet_tick(events_this_tick)

    # Write monthly summary every 4 ticks (week 4 = end of game-month)
    if tick % 4 == 0:
        summary_str = game.write_monthly_summary(tick, phase_num)
        if summary_str:
            summaries.append(summary_str)

    if quiet and tick % 4 == 0:
        summaries.append(f"tick={tick} quiet_month")
    elif not quiet:
        summaries.append(f"tick={tick} significant_tick")

    return summaries
