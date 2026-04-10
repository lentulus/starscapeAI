"""Partial tick runner — chains engine phases for early milestones.

Phase execution order:
  1  Intelligence  — passive scan, peace-week increment, map sharing
  2  Decision      — stub: expand orders → execute jumps
  3  Movement      — settle arrivals, record visits, detect contacts
  4  Combat        — space combat in contested systems
  8  Economy       — collect RU, maintenance, build/repair queues
  7  Control       — 25-week growth cycles

Phases 5-6 (bombardment, assault) are added at M10.
The full 9-phase loop is assembled at M13.
"""

from __future__ import annotations

from starscape5.game.facade import GameFacade
from starscape5.world.facade import WorldFacade

from .intelligence import run_intelligence_phase
from .decision import run_decision_phase
from .movement import run_movement_phase
from .combat import run_combat_phase
from .economy import run_economy_phase
from .control import run_control_phase


def run_partial_tick(
    tick: int,
    polity_order: list[int],
    game: GameFacade,
    world: WorldFacade,
) -> list[str]:
    """Run phases 1, 2, 3, 4, 8, 7 for a single tick.

    Returns all summary strings from all phases in chronological order.
    """
    summaries: list[str] = []
    summaries += run_intelligence_phase(tick, 1, polity_order, game, world)
    summaries += run_decision_phase(tick, 2, polity_order, game, world)
    summaries += run_movement_phase(tick, 3, polity_order, game, world)
    summaries += run_combat_phase(tick, 4, polity_order, game, world)
    summaries += run_economy_phase(tick, 8, polity_order, game, world)
    summaries += run_control_phase(tick, 7, polity_order, game, world)
    return summaries
