"""Unit statistics constants — pure data, no DB dependency.

Values from specs/GameDesign/version1/units.md.  Adjust here after first
simulation runs; changes propagate automatically to all callers.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Hull stats
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HullStats:
    attack: int
    bombard: int
    defence: int
    jump: int           # max parsecs per jump; 0 = no jump drive
    build_cost: float   # RU
    build_time: int     # ticks
    maint_per_tick: float


HULL_STATS: dict[str, HullStats] = {
    "capital":          HullStats(attack=4, bombard=3, defence=4, jump=3,
                                  build_cost=40.0, build_time=20, maint_per_tick=2.0),
    "old_capital":      HullStats(attack=3, bombard=2, defence=3, jump=2,
                                  build_cost=28.0, build_time=16, maint_per_tick=1.5),
    "cruiser":          HullStats(attack=2, bombard=2, defence=2, jump=4,
                                  build_cost=20.0, build_time=12, maint_per_tick=1.0),
    "escort":           HullStats(attack=1, bombard=0, defence=1, jump=4,
                                  build_cost=8.0,  build_time=6,  maint_per_tick=0.5),
    "troop":            HullStats(attack=0, bombard=0, defence=1, jump=3,
                                  build_cost=10.0, build_time=7,  maint_per_tick=0.5),
    "transport":        HullStats(attack=0, bombard=0, defence=1, jump=3,
                                  build_cost=8.0,  build_time=6,  maint_per_tick=0.5),
    "colony_transport": HullStats(attack=0, bombard=0, defence=1, jump=3,
                                  build_cost=10.0, build_time=7,  maint_per_tick=0.5),
    "scout":            HullStats(attack=0, bombard=0, defence=0, jump=10,
                                  build_cost=4.0,  build_time=4,  maint_per_tick=0.1),
    "sdb":              HullStats(attack=2, bombard=2, defence=3, jump=0,
                                  build_cost=6.0,  build_time=5,  maint_per_tick=0.5),
}

# Hull types that form squadrons (warships only; logistics hulls are not
# squadroned but are individually tracked).
SQUADRON_HULL_TYPES: frozenset[str] = frozenset(
    {"capital", "old_capital", "cruiser", "escort", "sdb"}
)


# ---------------------------------------------------------------------------
# Ground force stats
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GroundStats:
    starting_strength: int
    max_strength: int
    embarkable: bool
    build_cost: float
    build_time: int     # ticks
    maint_per_tick: float


GROUND_STATS: dict[str, GroundStats] = {
    "garrison": GroundStats(starting_strength=4, max_strength=4,
                            embarkable=False, build_cost=3.0,
                            build_time=2, maint_per_tick=0.0),
    "army":     GroundStats(starting_strength=4, max_strength=6,
                            embarkable=True,  build_cost=6.0,
                            build_time=4, maint_per_tick=0.5),
}
