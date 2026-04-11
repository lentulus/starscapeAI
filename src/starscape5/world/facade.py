"""World-layer public interface.

Defines the WorldFacade Protocol, all cross-layer dataclasses, and the pure
`compute_world_potential` scoring function.

Nothing in this file opens a database.  The Protocol is structural (uses
`typing.runtime_checkable`) so any class that implements the correct methods
satisfies it without subclassing.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Cross-layer dataclasses (plain Python objects; no DB dependency)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SystemPosition:
    """Cartesian position of a star system in milliparsecs (ICRS)."""
    system_id: int
    x_mpc: float
    y_mpc: float
    z_mpc: float

    def distance_pc_to(self, other: "SystemPosition") -> float:
        dx = (self.x_mpc - other.x_mpc) / 1000.0
        dy = (self.y_mpc - other.y_mpc) / 1000.0
        dz = (self.z_mpc - other.z_mpc) / 1000.0
        return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass(frozen=True)
class BodyData:
    """Physical snapshot of a single planetary body.

    world_potential is a derived integer score (see compute_world_potential).
    body_type is the broad class; planet_class is finer-grained (used for
    scoring and habitability).
    """
    body_id: int
    system_id: int
    body_type: str          # 'gas_giant' | 'rocky' | 'terrestrial' | 'ice' | 'belt'
    mass: float             # Earth masses
    radius: float           # Earth radii
    in_hz: int              # 1 = in habitable zone
    planet_class: str       # 'gas_giant' | 'rocky' | 'terrestrial'
    atm_type: str           # 'none' | 'trace' | 'thin' | 'standard' | 'dense' | 'corrosive'
    surface_temp_k: float
    hydrosphere: float      # 0.0 – 1.0
    world_potential: int    # scored by compute_world_potential; min 1


@dataclass(frozen=True)
class SpeciesData:
    """Static species definition.  All fields are immutable for V1 timescales."""
    species_id: int
    name: str
    aggression: float            # 0–1; how readily a polity starts wars
    expansionism: float          # 0–1; drive to claim new systems
    risk_appetite: float         # 0–1; tolerance for unfavourable odds
    adaptability: float          # 0–1; how easily a species colonises non-ideal worlds
    social_cohesion: float       # 0–1; resistance to polity splits
    hierarchy_tolerance: float   # 0–1; acceptance of rank/seniority structures
    faction_tendency: float      # 0–1; > 0.85 → multiple starting polities
    grievance_memory: float      # 0–1; how long historical wrongs affect decisions
    lifespan_years: int
    temp_min_k: float            # habitable temperature range
    temp_max_k: float
    atm_req: str                 # atmosphere requirement: 'any' | atm_type value


# ---------------------------------------------------------------------------
# Pure world-potential scoring function (game.md §Economy)
# ---------------------------------------------------------------------------

def compute_world_potential(body: BodyData) -> int:
    """Score a body's economic potential.

    From game.md scoring table:
      in_hz = 1             +10
      atm standard/dense    +5
      hydrosphere > 0.5     +5
      hydrosphere 0.1–0.5   +2
      planet_class rocky/terrestrial  +3
      mass 0.5–2.0 Mₑ       +2
      atm corrosive         −8
      atm none/trace        −3
      minimum               1

    Typical outputs: prime HZ earthlike ≈ 25; marginal HZ ≈ 12–15;
    hostile rocky ≈ 3–5; airless rock ≈ 2.
    """
    score = 0
    if body.in_hz:
        score += 10
    if body.atm_type in ("standard", "dense"):
        score += 5
    if body.hydrosphere > 0.5:
        score += 5
    elif body.hydrosphere >= 0.1:
        score += 2
    if body.planet_class in ("rocky", "terrestrial"):
        score += 3
    if 0.5 <= body.mass <= 2.0:
        score += 2
    if body.atm_type == "corrosive":
        score -= 8
    elif body.atm_type in ("none", "trace"):
        score -= 3
    return max(1, score)


# ---------------------------------------------------------------------------
# WorldFacade Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class WorldFacade(Protocol):
    """Read-only interface between the world layer and the game/engine layers.

    All methods return plain Python objects.  No DB connections cross this
    boundary except inside `resolve_system`, which is the documented exception.

    Implementors: WorldStub (always), WorldFacadeImpl (M12+).
    """

    def get_star_position(self, system_id: int) -> SystemPosition:
        """Return the ICRS Cartesian position of a star system in mpc."""
        ...

    def get_distance_pc(self, system_id_a: int, system_id_b: int) -> float:
        """Return the distance between two systems in parsecs."""
        ...

    def get_bodies(self, system_id: int) -> list[BodyData]:
        """Return all generated bodies for a system.

        Returns [] if bodies have not been generated yet (call resolve_system
        to trigger on-demand generation).
        """
        ...

    def get_gas_giant_flag(self, system_id: int) -> bool | None:
        """Return True if any body in the system is a gas giant.

        Returns None if the system has never been visited or passively scanned.
        Used for passive-scan refuelling route planning (20 pc radius).
        """
        ...

    def get_ocean_flag(self, system_id: int) -> bool | None:
        """Return True if any body has hydrosphere ≥ 0.5.

        Returns None if unknown.  Used for passive-scan refuelling planning.
        """
        ...

    def resolve_system(
        self, system_id: int, game_conn: sqlite3.Connection
    ) -> list[BodyData]:
        """On-demand body generation for a system.

        This is the one method permitted to hold both DB connections
        simultaneously.  Generates planets/atmosphere if not already present,
        writes WorldPotential cache rows to game.db, and returns BodyData.

        Idempotent: safe to call multiple times on the same system_id.
        """
        ...

    def get_species(self, species_id: int) -> SpeciesData:
        """Return the static species definition."""
        ...

    def check_habitability(self, body_id: int, species_id: int) -> bool:
        """Return True if the named species can inhabit the body without
        life-support infrastructure (controls whether a world can reach Colony
        or above, or is capped at Outpost)."""
        ...

    def get_systems_within_parsecs(
        self, system_id: int, parsecs: float
    ) -> list[int]:
        """Return system_ids of all other systems within `parsecs` distance.

        Used for passive-scan radius (20 pc) and jump-range planning.
        """
        ...

    def pick_homeworld_systems(self, n: int, seed: int = 0) -> list[int]:
        """Return n system_ids suitable for use as starting homeworlds.

        Real implementations should return spatially distributed systems.
        Stub returns sequential IDs starting at 1001 (existing behaviour).
        """
        ...
