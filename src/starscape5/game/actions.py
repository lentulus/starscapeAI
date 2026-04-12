"""Candidate actions and scoring for the decision engine.

All functions are pure (no DB access).  They take a GameStateSnapshot and
return a scored list of action dataclasses.

Action dataclasses are discriminated by type; the engine only issues orders
that are supported by the current game state.

Scoring formula (per action):
    score = base_utility + f(disposition) + f(game_state)

Higher score = more likely to be selected.  Scores may be negative.

Selection uses softmax-weighted top-k sampling in select_actions().
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from random import Random
from typing import Union

from .posture import Posture
from .snapshot import (
    FleetSnapshot, GameStateSnapshot, IntelSnapshot, PresenceSnapshot
)


# ---------------------------------------------------------------------------
# Action dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScoutAction:
    """Send an idle scout fleet to a specific unvisited system."""
    fleet_id: int
    destination_system_id: int
    score: float = 0.0


@dataclass
class ColoniseAction:
    """Send a colony transport fleet to establish/develop a presence."""
    fleet_id: int
    destination_system_id: int
    score: float = 0.0


@dataclass
class BuildHullAction:
    """Place a hull build order at a shipyard system."""
    system_id: int
    hull_type: str
    score: float = 0.0


@dataclass
class MoveFleetAction:
    """Reposition a fleet toward a strategic objective."""
    fleet_id: int
    destination_system_id: int
    score: float = 0.0


@dataclass
class InitiateWarAction:
    """Declare war on a contacted polity (war initiation roll succeeded)."""
    target_polity_id: int
    score: float = 0.0


@dataclass
class AssaultAction:
    """Move an assault fleet toward a target system."""
    fleet_id: int
    target_system_id: int
    score: float = 0.0


@dataclass
class ConsolidateAction:
    """Invest in an existing presence (no fleet movement; just priority signal)."""
    system_id: int
    score: float = 0.0


@dataclass
class UpgradeJumpAction:
    """Spend RU to increase scout jump range by one step (2 pc)."""
    score: float = 0.0


CandidateAction = Union[
    ScoutAction, ColoniseAction, BuildHullAction,
    MoveFleetAction, InitiateWarAction, AssaultAction, ConsolidateAction,
    UpgradeJumpAction,
]


# ---------------------------------------------------------------------------
# Scoring helpers (pure)
# ---------------------------------------------------------------------------

def _score_scout(
    fleet: FleetSnapshot,
    candidate: IntelSnapshot,
    snap: GameStateSnapshot,
) -> float:
    """Score sending fleet to scout candidate system."""
    base = 1.0 + snap.polity.expansionism * 2.0
    # Prefer systems with passive intel suggesting good refuelling
    if candidate.world_potential and candidate.world_potential > 10:
        base += 1.0
    # Penalty for already-visited systems (shouldn't happen; guard anyway)
    if candidate.knowledge_tier == "visited":
        return -99.0
    return base


def _score_colonise(
    fleet: FleetSnapshot,
    target: IntelSnapshot,
    snap: GameStateSnapshot,
) -> float:
    """Score colonising a visited system."""
    if target.knowledge_tier != "visited":
        return -99.0
    if target.world_potential is None:
        return 0.0
    base = snap.polity.expansionism * 3.0
    # Strong preference for habitable worlds
    if target.habitable:
        base += 2.0
    # High-potential worlds score higher
    base += (target.world_potential or 0) * 0.05
    # Penalty if already in enemy territory
    if target.system_id in snap.enemy_systems:
        base -= 3.0
    return base


def _score_build_hull(
    presence: PresenceSnapshot,
    hull_type: str,
    posture: Posture,
    snap: GameStateSnapshot,
) -> float:
    """Score placing a build order for hull_type at presence.system_id."""
    if not presence.has_shipyard:
        return -99.0
    cost_map = {
        "capital": 40.0, "old_capital": 28.0, "cruiser": 20.0,
        "escort": 8.0, "scout": 4.0, "colony_transport": 10.0,
        "troop": 10.0, "transport": 8.0,
    }
    cost = cost_map.get(hull_type, 10.0)
    if snap.polity.treasury_ru < cost:
        return -99.0

    # Hard cap on scouts: one per colony + 1 for the homeworld. More is waste.
    _SCOUT_CAP = snap.n_colonies + 1
    if hull_type == "scout" and snap.n_scouts >= _SCOUT_CAP:
        return -99.0

    if posture == Posture.PREPARE:
        if hull_type in ("capital", "old_capital", "cruiser", "escort"):
            return snap.polity.aggression * 2.0 + 1.0
    if posture == Posture.EXPAND:
        if hull_type == "colony_transport":
            # Colony transports are the expansion priority — score above scouts
            return snap.polity.expansionism * 3.0 + 2.0
        if hull_type == "scout":
            return snap.polity.expansionism * 2.0 + 1.0
    if posture == Posture.PROSECUTE:
        if hull_type == "troop":
            # Urgently needed when at war with no armies left
            base = snap.polity.aggression * 2.5
            if snap.n_armies == 0:
                base += 4.0   # hard boost: must rebuild assault capability
            return base
        if hull_type in ("capital", "cruiser"):
            return snap.polity.aggression * 2.5
    return 0.3  # always worth considering even off-posture


def _score_assault(
    fleet: FleetSnapshot,
    target_system_id: int,
    snap: GameStateSnapshot,
) -> float:
    """Score moving an assault fleet to a target enemy system."""
    if not fleet.has_troop:
        return -99.0
    base = snap.polity.aggression * 3.0 + snap.polity.risk_appetite * 1.0
    # Penalty if fleet would be jumping into superior enemy forces
    if target_system_id in snap.enemy_systems:
        base -= snap.polity.risk_appetite * 1.0  # low risk → bigger penalty
    return base


# ---------------------------------------------------------------------------
# Candidate generation (pure, given snapshot)
# ---------------------------------------------------------------------------

def generate_candidates(
    snap: GameStateSnapshot,
    posture: Posture,
    world_neighbor_fn,   # callable(system_id, parsecs) -> list[int]
) -> list[CandidateAction]:
    """Build all candidate actions for this polity this tick.

    `world_neighbor_fn` is injected so this function stays pure (no DB/world
    import); the engine passes `world.get_systems_within_parsecs`.
    """
    candidates: list[CandidateAction] = []
    p = snap.polity

    visited_ids = {s.system_id for s in snap.known_systems if s.knowledge_tier == "visited"}
    presence_ids = {pr.system_id for pr in snap.presences}
    intel_by_system = {s.system_id: s for s in snap.known_systems}

    # -- Scout actions --
    for fleet in snap.fleets:
        if fleet.status != "active" or not fleet.has_scout or fleet.system_id is None:
            continue
        neighbors = world_neighbor_fn(fleet.system_id, float(fleet.jump_range))
        for sid in neighbors:
            if sid in visited_ids or sid == fleet.system_id:
                continue
            intel = intel_by_system.get(sid)
            if intel is None:
                intel = IntelSnapshot(
                    system_id=sid, polity_id=p.polity_id,
                    knowledge_tier="passive",
                    world_potential=None, habitable=None,
                )
            sc = _score_scout(fleet, intel, snap)
            candidates.append(ScoutAction(
                fleet_id=fleet.fleet_id,
                destination_system_id=sid,
                score=sc,
            ))

    # -- Colonise actions --
    for fleet in snap.fleets:
        if fleet.status != "active" or not fleet.has_colony_transport:
            continue
        if fleet.system_id is None:
            continue
        neighbors = world_neighbor_fn(fleet.system_id, float(fleet.jump_range))
        for sid in neighbors:
            intel = intel_by_system.get(sid)
            if intel is None or intel.knowledge_tier != "visited":
                continue
            if sid in presence_ids:
                continue   # already have a presence
            sc = _score_colonise(fleet, intel, snap)
            candidates.append(ColoniseAction(
                fleet_id=fleet.fleet_id,
                destination_system_id=sid,
                score=sc,
            ))

    # -- Build hull actions --
    for pr in snap.presences:
        if not pr.has_shipyard:
            continue
        if posture == Posture.PREPARE or posture == Posture.PROSECUTE:
            for ht in ("capital", "cruiser", "escort"):
                sc = _score_build_hull(pr, ht, posture, snap)
                if sc > -99.0:
                    candidates.append(BuildHullAction(system_id=pr.system_id, hull_type=ht, score=sc))
        if posture in (Posture.EXPAND, Posture.CONSOLIDATE):
            for ht in ("scout", "colony_transport"):
                sc = _score_build_hull(pr, ht, posture, snap)
                if sc > -99.0:
                    candidates.append(BuildHullAction(system_id=pr.system_id, hull_type=ht, score=sc))

    # -- War initiation actions --
    # (Actual roll handled by war_initiation_roll; here we just score the action)
    # Gate on having established colonies — young polities cannot afford war.
    _COLONY_WAR_THRESHOLD = 6
    if posture in (Posture.PREPARE, Posture.PROSECUTE) and snap.n_colonies >= _COLONY_WAR_THRESHOLD:
        for cid in p.in_contact_with:
            if cid in p.at_war_with:
                continue  # already at war
            sc = p.aggression * 3.0
            candidates.append(InitiateWarAction(target_polity_id=cid, score=sc))

    # -- Assault actions --
    if posture == Posture.PROSECUTE:
        for fleet in snap.fleets:
            if fleet.status != "active" or not fleet.has_troop:
                continue
            if fleet.system_id is None:
                continue
            for eid in p.at_war_with:
                enemy_sys_rows = [
                    s for s in snap.known_systems
                    if s.system_id in snap.enemy_systems
                ]
                for es in enemy_sys_rows:
                    neighbors = world_neighbor_fn(fleet.system_id, float(fleet.jump_range))
                    if es.system_id not in neighbors:
                        continue
                    sc = _score_assault(fleet, es.system_id, snap)
                    candidates.append(AssaultAction(
                        fleet_id=fleet.fleet_id,
                        target_system_id=es.system_id,
                        score=sc,
                    ))

    # -- Consolidate actions --
    for pr in snap.presences:
        sc = (1.0 - p.expansionism) * 0.5 + 0.1
        candidates.append(ConsolidateAction(system_id=pr.system_id, score=sc))

    # -- Jump upgrade --
    # Offer when: treasury can cover cost, not yet at max, and has scouts
    _UPGRADE_COST = 75.0
    _UPGRADE_MAX  = 20
    has_scouts = any(f.has_scout for f in snap.fleets)
    if (has_scouts
            and p.jump_level < _UPGRADE_MAX
            and p.treasury_ru >= _UPGRADE_COST):
        # Score: explorers want range; scale with treasury cushion above cost
        cushion = (p.treasury_ru - _UPGRADE_COST) / max(p.treasury_ru, 1.0)
        sc = p.expansionism * 2.5 + cushion * 1.0
        candidates.append(UpgradeJumpAction(score=sc))

    return candidates


# ---------------------------------------------------------------------------
# Softmax-weighted top-k selection (pure)
# ---------------------------------------------------------------------------

def select_actions(
    candidates: list[CandidateAction],
    rng: Random,
    top_k: int = 5,
    temperature: float = 1.0,
) -> list[CandidateAction]:
    """Select up to top_k actions by softmax-weighted sampling without replacement.

    Higher score = more likely to be drawn first.  `temperature` controls
    sharpness: low → near-deterministic; high → more random.
    """
    if not candidates:
        return []

    # Softmax weights
    scores = [c.score for c in candidates]
    max_s = max(scores)
    weights = [math.exp((s - max_s) / max(temperature, 1e-9)) for s in scores]

    selected: list[CandidateAction] = []
    remaining = list(zip(weights, candidates))

    for _ in range(min(top_k, len(candidates))):
        total = sum(w for w, _ in remaining)
        if total <= 0:
            break
        r = rng.random() * total
        cumulative = 0.0
        chosen_idx = len(remaining) - 1
        for i, (w, _) in enumerate(remaining):
            cumulative += w
            if r < cumulative:
                chosen_idx = i
                break
        _, action = remaining.pop(chosen_idx)
        selected.append(action)

    return selected
