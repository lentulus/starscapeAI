"""Full tick runner and simulation loop — M13.

run_tick()       — executes all 9 phases with crash-safe advance/commit.
run_simulation() — loops run_tick(); handles resume from last committed state.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime

from starscape5.game.facade import GameFacade
from starscape5.game.polity import get_polity_processing_order
from starscape5.game.state import advance_phase, commit_phase, read_gamestate
from starscape5.world.facade import WorldFacade

from .intelligence import run_intelligence_phase
from .decision import run_decision_phase
from .movement import run_movement_phase
from .combat import run_combat_phase
from .bombardment import run_bombardment_phase
from .assault import run_assault_phase
from .economy import run_economy_phase
from .control import run_control_phase
from .log import run_log_phase


# Phase numbers follow game.md tick structure
_PHASES = [
    (1, run_intelligence_phase),
    (2, run_decision_phase),
    (3, run_movement_phase),
    (4, run_combat_phase),
    (5, run_bombardment_phase),
    (6, run_assault_phase),
    (8, run_economy_phase),
    (7, run_control_phase),
    (9, run_log_phase),
]


@dataclass
class TickResult:
    """Outcome summary for one completed tick."""
    tick: int
    summaries: list[str] = field(default_factory=list)
    phases_run: int = 0


def run_tick(
    tick: int,
    game: GameFacade,
    world: WorldFacade,
    game_conn: sqlite3.Connection,
    resume_from_phase: int = 0,
) -> TickResult:
    """Run all 9 phases for tick, committing after each.

    Args:
        tick:              Tick number to execute.
        game:              GameFacade implementation.
        world:             WorldFacade implementation.
        game_conn:         Open game.db connection (for advance/commit_phase).
        resume_from_phase: Skip phases ≤ this number (crash resume).
    """
    polity_order = get_polity_processing_order(game_conn)
    result = TickResult(tick=tick)

    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    for phase_num, phase_fn in _PHASES:
        if phase_num <= resume_from_phase:
            continue  # already committed; skip on resume

        print(f"[{_ts()}] tick={tick} phase={phase_num} {phase_fn.__module__.split('.')[-1]} start", flush=True)
        t_phase = time.perf_counter()
        advance_phase(game_conn, tick, phase_num)
        summaries = phase_fn(tick, phase_num, polity_order, game, world)
        commit_phase(game_conn, tick, phase_num)
        print(f"[{_ts()}] tick={tick} phase={phase_num} done ({time.perf_counter() - t_phase:.2f}s, {len(summaries)} events)", flush=True)

        result.summaries.extend(summaries)
        result.phases_run += 1

    return result


def run_simulation(
    game_conn: sqlite3.Connection,
    world: WorldFacade,
    game: GameFacade,
    max_ticks: int | None = None,
    verbose: bool = False,
) -> int:
    """Run the simulation loop from the last committed state.

    Reads GameState to find the resume point.  Runs up to max_ticks additional
    ticks (or indefinitely if max_ticks is None).  Handles KeyboardInterrupt
    cleanly — the last committed phase is safe.

    Returns the tick number at which the loop stopped.
    """
    state = read_gamestate(game_conn)

    crashed = state.current_tick > state.last_committed_tick
    if crashed:
        # Crash detected: current_tick was in-progress but nothing committed for it.
        # Re-run from phase 0 of that tick (advance_phase was called, not commit_phase).
        start_tick = state.current_tick
        crash_resume_phase = 0
        if verbose:
            print(f"Resume: re-running tick {start_tick} from phase 1")
    else:
        start_tick = state.last_committed_tick + 1
        crash_resume_phase = 0

    end_tick = start_tick + max_ticks - 1 if max_ticks is not None else None

    tick = start_tick
    try:
        while end_tick is None or tick <= end_tick:
            rfp_for_tick = crash_resume_phase if (tick == start_tick and crashed) else 0

            result = run_tick(
                tick, game, world, game_conn,
                resume_from_phase=rfp_for_tick,
            )
            if verbose:
                print(f"tick={tick} phases={result.phases_run} events={len(result.summaries)}")
                for s in result.summaries:
                    print(f"  {s}")

            tick += 1
    except KeyboardInterrupt:
        if verbose:
            print(f"\nSimulation paused at tick {tick}. Last committed: {read_gamestate(game_conn).last_committed_tick}")

    return tick - 1
