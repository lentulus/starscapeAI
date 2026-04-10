"""WorldStub — permanent test double for the WorldFacade protocol.

All output is deterministic for a given seed:
  - Per-system data seeds from (seed ^ system_id), so call order never matters.
  - Per-species data seeds from (seed ^ (species_id + 10_000)).

The stub universe contains system IDs 1..universe_size (default 100) spread
across a 3 pc cube.  get_systems_within_parsecs scans this range, so test
scenarios with predictable jump connectivity can be set up by choosing small
universe_size values.

body_id scheme: system_id * 10 + body_index (0-based).  Given a body_id,
system_id = body_id // 10.
"""

from __future__ import annotations

import math
import sqlite3
from random import Random

from .facade import (
    BodyData,
    SpeciesData,
    SystemPosition,
    WorldFacade,
    compute_world_potential,
)

_MPC_PER_PC: float = 1000.0
_UNIVERSE_SPAN_MPC: float = 3000.0  # 3 pc cube


class WorldStub:
    """Deterministic, database-free implementation of WorldFacade."""

    def __init__(self, seed: int = 42, universe_size: int = 100):
        self._seed = seed
        self._universe_size = universe_size

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_star_position(self, system_id: int) -> SystemPosition:
        rng = Random(self._seed ^ system_id)
        return SystemPosition(
            system_id=system_id,
            x_mpc=rng.uniform(0.0, _UNIVERSE_SPAN_MPC),
            y_mpc=rng.uniform(0.0, _UNIVERSE_SPAN_MPC),
            z_mpc=rng.uniform(0.0, _UNIVERSE_SPAN_MPC),
        )

    def get_distance_pc(self, system_id_a: int, system_id_b: int) -> float:
        a = self.get_star_position(system_id_a)
        b = self.get_star_position(system_id_b)
        return a.distance_pc_to(b)

    def get_systems_within_parsecs(
        self, system_id: int, parsecs: float
    ) -> list[int]:
        result = []
        for sid in range(1, self._universe_size + 1):
            if sid == system_id:
                continue
            if self.get_distance_pc(system_id, sid) <= parsecs:
                result.append(sid)
        return result

    # ------------------------------------------------------------------
    # Bodies
    # ------------------------------------------------------------------

    def get_bodies(self, system_id: int) -> list[BodyData]:
        rng = Random(self._seed ^ system_id)
        n = rng.randint(0, 4)
        return [self._generate_body(system_id, i, Random(self._seed ^ system_id ^ (i + 1))) for i in range(n)]

    def _generate_body(
        self, system_id: int, index: int, rng: Random
    ) -> BodyData:
        body_id = system_id * 10 + index
        body_type = rng.choice(["gas_giant", "rocky", "terrestrial", "ice", "belt"])
        in_hz = int(rng.random() < 0.2)

        if body_type == "gas_giant":
            mass = rng.uniform(50.0, 1000.0)
            radius = rng.uniform(5.0, 15.0)
            planet_class = "gas_giant"
            atm_type = "dense"
            surface_temp_k = rng.uniform(80.0, 200.0)
            hydrosphere = 0.0

        elif body_type == "terrestrial":
            mass = rng.uniform(0.3, 2.5)
            radius = rng.uniform(0.7, 1.4)
            planet_class = "terrestrial"
            if in_hz:
                atm_type = rng.choice(["standard", "dense", "thin"])
                surface_temp_k = rng.uniform(270.0, 320.0)
                hydrosphere = rng.uniform(0.0, 0.9)
            else:
                atm_type = rng.choice(["thin", "standard", "none", "trace"])
                surface_temp_k = rng.uniform(100.0, 600.0)
                hydrosphere = rng.uniform(0.0, 0.3)

        elif body_type == "rocky":
            mass = rng.uniform(0.01, 0.5)
            radius = rng.uniform(0.2, 0.8)
            planet_class = "rocky"
            atm_type = rng.choice(["none", "trace", "thin"])
            surface_temp_k = rng.uniform(100.0, 700.0)
            hydrosphere = 0.0

        elif body_type == "ice":
            mass = rng.uniform(0.01, 0.3)
            radius = rng.uniform(0.1, 0.6)
            planet_class = "rocky"
            atm_type = "trace"
            surface_temp_k = rng.uniform(40.0, 150.0)
            hydrosphere = rng.uniform(0.0, 0.2)

        else:  # belt
            mass = rng.uniform(0.0001, 0.01)
            radius = 0.0
            planet_class = "rocky"
            atm_type = "none"
            surface_temp_k = rng.uniform(100.0, 600.0)
            hydrosphere = 0.0

        # Two-pass: compute potential after other fields are known.
        proto = BodyData(
            body_id=body_id, system_id=system_id,
            body_type=body_type, mass=mass, radius=radius,
            in_hz=in_hz, planet_class=planet_class, atm_type=atm_type,
            surface_temp_k=surface_temp_k, hydrosphere=hydrosphere,
            world_potential=0,
        )
        return BodyData(
            body_id=body_id, system_id=system_id,
            body_type=body_type, mass=mass, radius=radius,
            in_hz=in_hz, planet_class=planet_class, atm_type=atm_type,
            surface_temp_k=surface_temp_k, hydrosphere=hydrosphere,
            world_potential=compute_world_potential(proto),
        )

    def get_gas_giant_flag(self, system_id: int) -> bool | None:
        return any(b.body_type == "gas_giant" for b in self.get_bodies(system_id))

    def get_ocean_flag(self, system_id: int) -> bool | None:
        return any(b.hydrosphere >= 0.5 for b in self.get_bodies(system_id))

    # ------------------------------------------------------------------
    # resolve_system — the one method that touches game.db
    # ------------------------------------------------------------------

    def resolve_system(
        self, system_id: int, game_conn: sqlite3.Connection
    ) -> list[BodyData]:
        """Generate bodies and upsert WorldPotential rows into game.db.

        In the stub there is no starscape.db to write to; bodies are generated
        in memory only.  The WorldPotential cache in game.db is still populated
        so downstream game logic works identically against stub and real world.
        """
        bodies = self.get_bodies(system_id)
        has_gg = int(any(b.body_type == "gas_giant" for b in bodies))
        has_ocean = int(any(b.hydrosphere >= 0.5 for b in bodies))

        for body in bodies:
            game_conn.execute(
                """
                INSERT INTO WorldPotential
                    (body_id, system_id, world_potential, has_gas_giant, has_ocean)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(body_id) DO UPDATE SET
                    world_potential = excluded.world_potential,
                    has_gas_giant   = excluded.has_gas_giant,
                    has_ocean       = excluded.has_ocean
                """,
                (body.body_id, body.system_id, body.world_potential, has_gg, has_ocean),
            )
        game_conn.commit()
        return bodies

    # ------------------------------------------------------------------
    # Species
    # ------------------------------------------------------------------

    def get_species(self, species_id: int) -> SpeciesData:
        rng = Random(self._seed ^ (species_id + 10_000))
        return SpeciesData(
            species_id=species_id,
            name=f"Stub Species {species_id}",
            aggression=round(rng.uniform(0.2, 0.8), 3),
            expansionism=round(rng.uniform(0.2, 0.8), 3),
            risk_appetite=round(rng.uniform(0.2, 0.8), 3),
            adaptability=round(rng.uniform(0.2, 0.8), 3),
            social_cohesion=round(rng.uniform(0.2, 0.8), 3),
            hierarchy_tolerance=round(rng.uniform(0.2, 0.8), 3),
            faction_tendency=round(rng.uniform(0.1, 0.6), 3),
            grievance_memory=round(rng.uniform(0.2, 0.8), 3),
            lifespan_years=rng.randint(60, 800),
            temp_min_k=250.0,
            temp_max_k=320.0,
            atm_req="standard",
        )

    def check_habitability(self, body_id: int, species_id: int) -> bool:
        """Return True if the species can inhabit the body without life support."""
        system_id = body_id // 10
        bodies = self.get_bodies(system_id)
        body = next((b for b in bodies if b.body_id == body_id), None)
        if body is None:
            return False
        species = self.get_species(species_id)
        temp_ok = species.temp_min_k <= body.surface_temp_k <= species.temp_max_k
        atm_ok = species.atm_req == "any" or body.atm_type == species.atm_req
        return temp_ok and atm_ok


# Runtime check that WorldStub satisfies WorldFacade.
# This fires at import time so any signature drift is caught immediately.
assert isinstance(WorldStub(), WorldFacade), (
    "WorldStub does not satisfy WorldFacade protocol — check method signatures"
)
