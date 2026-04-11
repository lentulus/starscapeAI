"""WorldFacadeImpl — real starscape.db-backed implementation of WorldFacade.

This is the M12 production implementation.  It replaces WorldStub once the
external starscape.db is available on the simulation host.

Connection discipline:
    ro_conn — starscape.db opened read-only (open_world_ro())
    rw_conn — starscape.db opened read-write (open_world_rw()); optional.
              Required only for resolve_system() (lazy planet generation).

The `x` index on IndexedIntegerDistinctSystems is created on first rw_conn
open so that get_systems_within_parsecs() runs in O(1) rather than O(8M).
"""

from __future__ import annotations

import random as _rng_module
import sqlite3
from pathlib import Path

from .facade import (
    BodyData,
    SpeciesData,
    SystemPosition,
    WorldFacade,
    compute_world_potential,
)

# ---------------------------------------------------------------------------
# DB column mappings
# ---------------------------------------------------------------------------

_GG_CLASSES = frozenset(("small_gg", "medium_gg", "large_gg"))


def _db_planet_class(db_pc: str | None, db_bt: str) -> str:
    """Map DB planet_class + body_type to BodyData.planet_class vocabulary."""
    if db_bt in ("belt", "planetoid"):
        return "rocky"
    if db_pc in _GG_CLASSES:
        return "gas_giant"
    return "rocky"


def _db_body_type(db_pc: str | None, db_bt: str) -> str:
    """Map DB columns to BodyData.body_type vocabulary."""
    if db_bt in ("belt", "planetoid"):
        return "belt"
    if db_pc in _GG_CLASSES:
        return "gas_giant"
    return "rocky"


# ---------------------------------------------------------------------------
# WorldFacadeImpl
# ---------------------------------------------------------------------------

class WorldFacadeImpl:
    """Real implementation of WorldFacade backed by starscape.db."""

    def __init__(
        self,
        ro_conn: sqlite3.Connection,
        rw_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._ro = ro_conn
        self._rw = rw_conn

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_star_position(self, system_id: int) -> SystemPosition:
        row = self._ro.execute(
            "SELECT x, y, z FROM IndexedIntegerDistinctSystems WHERE system_id = ?",
            (system_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"system_id {system_id} not found in starscape.db")
        return SystemPosition(
            system_id=system_id,
            x_mpc=float(row["x"]),
            y_mpc=float(row["y"]),
            z_mpc=float(row["z"]),
        )

    def get_distance_pc(self, system_id_a: int, system_id_b: int) -> float:
        a = self.get_star_position(system_id_a)
        b = self.get_star_position(system_id_b)
        return a.distance_pc_to(b)

    def get_systems_within_parsecs(
        self, system_id: int, parsecs: float
    ) -> list[int]:
        pos = self.get_star_position(system_id)
        r_mpc = parsecs * 1000.0
        r_mpc_sq = r_mpc * r_mpc
        rows = self._ro.execute(
            """
            SELECT system_id, x, y, z
            FROM   IndexedIntegerDistinctSystems
            WHERE  system_id != ?
              AND  x BETWEEN ? AND ?
              AND  y BETWEEN ? AND ?
              AND  z BETWEEN ? AND ?
            """,
            (
                system_id,
                pos.x_mpc - r_mpc, pos.x_mpc + r_mpc,
                pos.y_mpc - r_mpc, pos.y_mpc + r_mpc,
                pos.z_mpc - r_mpc, pos.z_mpc + r_mpc,
            ),
        ).fetchall()
        result = []
        for r in rows:
            dx = r["x"] - pos.x_mpc
            dy = r["y"] - pos.y_mpc
            dz = r["z"] - pos.z_mpc
            if dx * dx + dy * dy + dz * dz <= r_mpc_sq:
                result.append(r["system_id"])
        return result

    # ------------------------------------------------------------------
    # Bodies
    # ------------------------------------------------------------------

    def _get_star_ids(self, system_id: int) -> list[int]:
        rows = self._ro.execute(
            "SELECT star_id FROM IndexedIntegerDistinctStars WHERE system_id = ?",
            (system_id,),
        ).fetchall()
        return [r["star_id"] for r in rows]

    def _row_to_body(self, r: sqlite3.Row) -> BodyData:
        db_pc = r["planet_class"]
        db_bt = r["body_type"]
        body_type   = _db_body_type(db_pc, db_bt)
        planet_class = _db_planet_class(db_pc, db_bt)
        atm_type = r["atm_type"] or "none"
        surface_temp_k = r["surface_temp_k"] or 200.0
        hydrosphere = r["hydrosphere"] or 0.0
        proto = BodyData(
            body_id=r["body_id"],
            system_id=r["system_id"],
            body_type=body_type,
            mass=r["mass"] or 0.1,
            radius=r["radius"] or 0.3,
            in_hz=r["in_hz"] or 0,
            planet_class=planet_class,
            atm_type=atm_type,
            surface_temp_k=surface_temp_k,
            hydrosphere=hydrosphere,
            world_potential=0,
        )
        return BodyData(
            body_id=proto.body_id,
            system_id=proto.system_id,
            body_type=proto.body_type,
            mass=proto.mass,
            radius=proto.radius,
            in_hz=proto.in_hz,
            planet_class=proto.planet_class,
            atm_type=proto.atm_type,
            surface_temp_k=proto.surface_temp_k,
            hydrosphere=proto.hydrosphere,
            world_potential=compute_world_potential(proto),
        )

    def get_bodies(self, system_id: int) -> list[BodyData]:
        star_ids = self._get_star_ids(system_id)
        if not star_ids:
            return []
        ph = ",".join("?" * len(star_ids))
        rows = self._ro.execute(
            f"""
            SELECT b.body_id, b.body_type, b.mass, b.radius, b.in_hz,
                   b.planet_class, s.system_id,
                   bm.atm_type, bm.surface_temp_k, bm.hydrosphere
            FROM   Bodies b
            JOIN   IndexedIntegerDistinctStars s ON b.orbit_star_id = s.star_id
            LEFT JOIN BodyMutable bm ON b.body_id = bm.body_id
            WHERE  b.orbit_star_id IN ({ph})
              AND  b.orbit_body_id IS NULL
            """,
            star_ids,
        ).fetchall()
        return [self._row_to_body(r) for r in rows]

    def get_gas_giant_flag(self, system_id: int) -> bool | None:
        star_ids = self._get_star_ids(system_id)
        if not star_ids:
            return None
        ph = ",".join("?" * len(star_ids))
        # Check if any bodies exist at all for this system (proxy for "scanned")
        total = self._ro.execute(
            f"SELECT COUNT(*) AS cnt FROM Bodies WHERE orbit_star_id IN ({ph})",
            star_ids,
        ).fetchone()
        if not total or not total["cnt"]:
            return None  # Bodies not yet generated — treat as unknown
        gg_row = self._ro.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM Bodies
            WHERE  orbit_star_id IN ({ph})
              AND  orbit_body_id IS NULL
              AND  planet_class IN ('small_gg', 'medium_gg', 'large_gg')
            """,
            star_ids,
        ).fetchone()
        return bool(gg_row["cnt"]) if gg_row else False

    def get_ocean_flag(self, system_id: int) -> bool | None:
        star_ids = self._get_star_ids(system_id)
        if not star_ids:
            return None
        ph = ",".join("?" * len(star_ids))
        total = self._ro.execute(
            f"SELECT COUNT(*) AS cnt FROM Bodies WHERE orbit_star_id IN ({ph})",
            star_ids,
        ).fetchone()
        if not total or not total["cnt"]:
            return None  # Bodies not yet generated — treat as unknown
        row = self._ro.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM   Bodies b
            JOIN   BodyMutable bm ON b.body_id = bm.body_id
            WHERE  b.orbit_star_id IN ({ph})
              AND  b.orbit_body_id IS NULL
              AND  bm.hydrosphere >= 0.5
            """,
            star_ids,
        ).fetchone()
        return bool(row["cnt"]) if row else False

    # ------------------------------------------------------------------
    # resolve_system — lazy on-demand planet + atmosphere generation
    # ------------------------------------------------------------------

    def _has_bodies(self, star_ids: list[int]) -> bool:
        ph = ",".join("?" * len(star_ids))
        row = self._ro.execute(
            f"SELECT COUNT(*) AS cnt FROM Bodies WHERE orbit_star_id IN ({ph})",
            star_ids,
        ).fetchone()
        return bool(row["cnt"])

    def _upsert_world_potential(
        self,
        game_conn: sqlite3.Connection,
        bodies: list[BodyData],
        system_id: int,
    ) -> None:
        has_gg    = int(any(b.body_type == "gas_giant" for b in bodies))
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
                (body.body_id, body.system_id,
                 body.world_potential, has_gg, has_ocean),
            )
        game_conn.commit()

    def resolve_system(
        self, system_id: int, game_conn: sqlite3.Connection
    ) -> list[BodyData]:
        """Generate bodies for system_id if not yet generated; update WorldPotential cache."""
        star_ids = self._get_star_ids(system_id)

        if star_ids and not self._has_bodies(star_ids):
            if self._rw is not None:
                self._generate_bodies_for_system(system_id, star_ids)
            # else: no rw_conn — bodies can't be generated; return what we have

        bodies = self.get_bodies(system_id)
        if bodies:
            self._upsert_world_potential(game_conn, bodies, system_id)
        return bodies

    def _generate_bodies_for_system(
        self, system_id: int, star_ids: list[int]
    ) -> None:
        """Generate planets + atmospheres for all stars in system_id.

        Seeded deterministically from system_id so the same system always
        produces the same planets regardless of processing order.
        """
        _rng_module.seed(system_id)

        from starscape5.planets import (
            planet_count, generate_planet, generate_moon,
            generate_belt, generate_planetoid,
            moon_count, planetoid_count, belt_mass_earth,
            belt_positions, hz_bounds,
        )
        from starscape5.atmosphere import (
            classify_atm, atm_composition, atm_pressure_atm,
            surface_temp_k as surf_temp, hydrosphere as hydro_fn,
            escape_velocity_kms, t_eq_k,
        )

        _INSERT_BODY = """
            INSERT INTO Bodies
                (body_type, mass, radius, orbit_star_id, orbit_body_id,
                 semi_major_axis, eccentricity, inclination,
                 longitude_ascending_node, argument_periapsis, mean_anomaly,
                 epoch, in_hz, possible_tidal_lock, planet_class, has_rings,
                 comp_metallic, comp_carbonaceous, comp_stony,
                 span_inner_au, span_outer_au)
            VALUES
                (:body_type, :mass, :radius, :orbit_star_id, :orbit_body_id,
                 :semi_major_axis, :eccentricity, :inclination,
                 :longitude_ascending_node, :argument_periapsis, :mean_anomaly,
                 :epoch, :in_hz, :possible_tidal_lock, :planet_class, :has_rings,
                 :comp_metallic, :comp_carbonaceous, :comp_stony,
                 :span_inner_au, :span_outer_au)
        """

        _INSERT_MUTABLE = """
            INSERT OR IGNORE INTO BodyMutable
                (body_id, atm_type, atm_pressure_atm, atm_composition,
                 surface_temp_k, hydrosphere, epoch)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """

        for star_id in star_ids:
            star_row = self._ro.execute(
                """
                SELECT s.spectral, COALESCE(e.luminosity, 1.0) AS luminosity
                FROM   IndexedIntegerDistinctStars s
                LEFT JOIN DistinctStarsExtended e ON s.star_id = e.star_id
                WHERE  s.star_id = ?
                """,
                (star_id,),
            ).fetchone()
            if star_row is None:
                continue

            spectral = star_row["spectral"] or "G"
            spec_letter = spectral[0].upper() if spectral else "G"
            lum = max(float(star_row["luminosity"]), 1e-4)

            n_planets = planet_count(spec_letter)
            planets = [generate_planet(star_id, lum) for _ in range(n_planets)]
            planets.sort(key=lambda p: p["semi_major_axis"])

            for planet in planets:
                cur = self._rw.execute(_INSERT_BODY, planet)
                planet_id = cur.lastrowid
                if planet_id and planet["mass"] and planet["radius"]:
                    v_esc = escape_velocity_kms(planet["mass"], planet["radius"])
                    teq   = t_eq_k(lum, planet["semi_major_axis"])
                    atm   = classify_atm(
                        v_esc, teq,
                        planet["in_hz"] or 0,
                        planet["possible_tidal_lock"] or 0,
                    )
                    s_temp = surf_temp(teq, atm)
                    self._rw.execute(_INSERT_MUTABLE, (
                        planet_id, atm,
                        atm_pressure_atm(atm),
                        atm_composition(atm, teq),
                        s_temp,
                        hydro_fn(atm, planet["in_hz"] or 0, s_temp),
                    ))

                # Moons
                n_moons = moon_count(planet["mass"] or 0)
                moons = [
                    generate_moon(planet_id, planet["mass"])
                    for _ in range(n_moons)
                ] if planet_id and n_moons else []
                for moon in moons:
                    m_cur = self._rw.execute(_INSERT_BODY, moon)
                    m_id  = m_cur.lastrowid
                    if m_id and moon["mass"] and moon["radius"]:
                        v_esc = escape_velocity_kms(moon["mass"], moon["radius"])
                        teq   = t_eq_k(lum, planet["semi_major_axis"])
                        atm   = classify_atm(v_esc, teq, 0, 0)
                        s_temp = surf_temp(teq, atm)
                        self._rw.execute(_INSERT_MUTABLE, (
                            m_id, atm,
                            atm_pressure_atm(atm),
                            atm_composition(atm, teq),
                            s_temp,
                            hydro_fn(atm, 0, s_temp),
                        ))

            # Belts
            hz_inner, hz_outer = hz_bounds(lum)
            for center_au, belt_ecc in belt_positions(planets, lum):
                bmass = belt_mass_earth()
                self._rw.execute(
                    _INSERT_BODY,
                    generate_belt(star_id, center_au, belt_ecc, bmass,
                                  hz_inner, hz_outer, lum),
                )
                for _ in range(planetoid_count()):
                    self._rw.execute(
                        _INSERT_BODY,
                        generate_planetoid(star_id, center_au, belt_ecc, bmass,
                                           hz_inner, hz_outer),
                    )

        self._rw.commit()

    # ------------------------------------------------------------------
    # Species
    # ------------------------------------------------------------------

    def get_species(self, species_id: int) -> SpeciesData:
        """Return species data from DB; falls back to synthetic defaults if not seeded."""
        row = self._ro.execute(
            "SELECT * FROM Species WHERE species_id = ?", (species_id,)
        ).fetchone()
        if row is None:
            # Species table not yet seeded — return a neutral synthetic stand-in
            from random import Random
            rng = Random(species_id + 99_999)
            return SpeciesData(
                species_id=species_id,
                name=f"Species {species_id}",
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
                atm_req="any",
            )
        return SpeciesData(
            species_id=row["species_id"],
            name=row["name"],
            aggression=row["aggression"] or 0.5,
            expansionism=row["expansionism"] or 0.5,
            risk_appetite=row["risk_appetite"] or 0.5,
            adaptability=row["adaptability"] or 0.5,
            social_cohesion=row["social_cohesion"] or 0.5,
            hierarchy_tolerance=row["hierarchy_tolerance"] or 0.5,
            faction_tendency=row["faction_tendency"] or 0.3,
            grievance_memory=row["grievance_memory"] or 0.5,
            lifespan_years=int(row["lifespan_years"] or 80),
            temp_min_k=row["temp_min_k"] or 250.0,
            temp_max_k=row["temp_max_k"] or 320.0,
            atm_req=row["atm_req"] or "any",
        )

    def check_habitability(self, body_id: int, species_id: int) -> bool:
        """Return True if the species can inhabit the body without life support."""
        row = self._ro.execute(
            """
            SELECT bm.atm_type, bm.surface_temp_k
            FROM   Bodies b
            JOIN   BodyMutable bm ON b.body_id = bm.body_id
            WHERE  b.body_id = ?
            """,
            (body_id,),
        ).fetchone()
        if row is None:
            return False
        species = self.get_species(species_id)
        atm_type = row["atm_type"] or "none"
        temp_k   = row["surface_temp_k"] or 0.0
        temp_ok  = species.temp_min_k <= temp_k <= species.temp_max_k
        atm_ok   = species.atm_req == "any" or atm_type == species.atm_req
        return temp_ok and atm_ok


# ---------------------------------------------------------------------------
# Runtime protocol check (fires at import time)
# ---------------------------------------------------------------------------
_check_instance = object.__new__(WorldFacadeImpl)
assert isinstance(_check_instance, WorldFacade), (
    "WorldFacadeImpl does not satisfy WorldFacade protocol — check method signatures"
)
del _check_instance
