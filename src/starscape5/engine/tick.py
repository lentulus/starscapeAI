"""Partial tick runner — chains all 9 engine phases.

Phase execution order (per game.md tick structure):
  1  Intelligence   — passive scan, peace-week increment, map sharing
  2  Decision       — war rolls, posture, candidate generation, action execution
  3  Movement       — settle arrivals, record visits, detect contacts
  4  Combat         — space combat in contested systems
  5  Bombardment    — orbital bombardment of ground targets
  6  Assault        — ground combat on contested bodies
  8  Economy        — collect RU, maintenance, build/repair queues
  7  Control        — 25-week growth cycles
  9  Log            — quiet-tick classifier, monthly summary (M13)
"""

from __future__ import annotations

from starscape5.game.facade import GameFacade
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


def run_partial_tick(
    tick: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
) -> list[str]:
    """Run all 9 phases for a single tick without crash-safe advance/commit.

    Used by tests and short scenarios.  For crash-safe production runs use
    engine.simulation.run_tick() which wraps each phase with advance/commit.

    Returns all summary strings from all phases in chronological order.
    """
    summaries: list[str] = []
    summaries += run_intelligence_phase(tick, 1, polity_order, game, world)
    summaries += run_decision_phase(tick, 2, polity_order, game, world)
    summaries += run_movement_phase(tick, 3, polity_order, game, world)
    summaries += run_combat_phase(tick, 4, polity_order, game, world)
    summaries += run_bombardment_phase(tick, 5, polity_order, game, world)
    summaries += run_assault_phase(tick, 6, polity_order, game, world)
    summaries += run_economy_phase(tick, 8, polity_order, game, world)
    summaries += run_control_phase(tick, 7, polity_order, game, world)
    summaries += run_log_phase(tick, 9, polity_order, game, world)
    return summaries
