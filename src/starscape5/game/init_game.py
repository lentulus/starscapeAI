"""Game initialiser — builds the full starting game state from OB data.

Called once at the start of a new simulation run.  Uses WorldStub (M0–M11)
or WorldFacadeImpl (M12+) transparently — the facade interface is identical.

Homeworld system IDs are assigned sequentially starting at 1001 (stub-safe
range; real IDs come from starscape.db at M12).  Body IDs follow the WorldStub
convention: system_id * 10.

init_game() is idempotent against an empty DB only — calling it twice on the
same connection will violate the GameState singleton constraint.
"""

from __future__ import annotations

import sqlite3
from random import Random

from starscape5.world.facade import WorldFacade
from .db import init_schema
from .state import create_gamestate
from .polity import create_polity
from .fleet import create_fleet, create_squadron, create_hull
from .admiral import commission_on_demand
from .ground import create_ground_force
from .presence import create_presence
from .economy import create_world_potential_cache
from .events import write_event
from .names import NameGenerator
from .ob_data import OB_DATA

def init_game(
    game_conn: sqlite3.Connection,
    world: WorldFacade,
    ob_data: list[dict] | None = None,
    rng_seed: int = 0,
) -> None:
    """Populate game.db with the full tick-0 game state.

    Args:
        game_conn:  Open game.db connection (schema must already exist).
        world:      WorldFacade implementation (stub or real).
        ob_data:    OB list; defaults to the canonical OB_DATA constant.
        rng_seed:   Seed for admiral tactical factor generation at tick 0.
    """
    if ob_data is None:
        ob_data = OB_DATA

    create_gamestate(game_conn)

    rng = Random(rng_seed)

    # Pick spatially distributed homeworld systems (real impl) or sequential
    # stub IDs — the facade decides which is appropriate.
    homeworld_systems = world.pick_homeworld_systems(len(ob_data), seed=rng_seed)

    for entry_idx, entry in enumerate(ob_data):
        species_id = entry["species_id"]

        # Determine per-polity hull/ground lists.
        polity_defs = entry["polities"]
        n_polities = len(polity_defs)

        if "hulls_by_polity" in entry:
            hulls_by_polity = entry["hulls_by_polity"]
            sdbs_by_polity = entry["sdbs_by_polity"]
            armies_by_polity = entry["armies_by_polity"]
            garrisons_by_polity = entry["garrisons_by_polity"]
        else:
            # All polities share a single homeworld system and the same OB
            # (single-polity species always have exactly one entry).
            hulls_by_polity = [entry["hulls"]] * n_polities
            sdbs_by_polity = [entry["sdbs"]] * n_polities
            armies_by_polity = [entry["armies"]] * n_polities
            garrisons_by_polity = [entry["garrisons"]] * n_polities

        # All polities of a species share one homeworld system.
        homeworld_system = homeworld_systems[entry_idx]

        # Seed WorldPotential cache for the homeworld via resolve_system.
        world.resolve_system(homeworld_system, game_conn)
        bodies = world.get_bodies(homeworld_system)

        # Pick the best body as the homeworld body.
        best_body = max(bodies, key=lambda b: b.world_potential) if bodies else None
        homeworld_body_id = best_body.body_id if best_body else homeworld_system * 10

        # has_gg and has_ocean flags for WorldPotential rows.
        has_gg = int(any(b.body_type == "gas_giant" for b in bodies))
        has_ocean = int(any(b.hydrosphere >= 0.5 for b in bodies))

        # Ensure WorldPotential row exists for the homeworld body (for
        # bodyless systems, insert a synthetic row so economy phase works).
        if not bodies:
            create_world_potential_cache(
                game_conn,
                body_id=homeworld_body_id,
                system_id=homeworld_system,
                world_potential=20,  # synthetic homeworld default
                has_gas_giant=0,
                has_ocean=0,
            )

        for i, pdef in enumerate(polity_defs):
            name_gen = NameGenerator(species_id=species_id)
            polity_id = create_polity(
                game_conn,
                species_id=species_id,
                name=pdef["name"],
                capital_system_id=homeworld_system,
                expansionism=pdef["expansionism"],
                aggression=pdef["aggression"],
                risk_appetite=pdef["risk_appetite"],
                processing_order=pdef["processing_order"],
                treasury_ru=pdef["treasury_ru"],
                founded_tick=0,
            )

            write_event(
                game_conn, tick=0, phase=0, event_type="colony_established",
                summary=f"{pdef['name']} founded at system {homeworld_system}",
                polity_a_id=polity_id, system_id=homeworld_system,
                body_id=homeworld_body_id,
            )

            # Homeworld presence: Controlled / dev-3 / shipyard.
            create_presence(
                game_conn,
                polity_id=polity_id,
                system_id=homeworld_system,
                body_id=homeworld_body_id,
                control_state="controlled",
                development_level=3,
                established_tick=0,
                has_shipyard=1,
            )

            # Fleet hulls.
            hull_list = hulls_by_polity[i]
            fleet_hulls = [(ht, c) for ht, c in hull_list
                           if ht not in ("sdb",)]

            if fleet_hulls:
                fleet_id = create_fleet(
                    game_conn, polity_id,
                    name_gen.fleet(pdef["name"], sequence=1),
                    system_id=homeworld_system,
                )

                # Group warship types into squadrons.
                from .constants import SQUADRON_HULL_TYPES
                hull_seq: dict[str, int] = {}
                sq_ids: dict[str, int] = {}

                for hull_type, count in fleet_hulls:
                    is_warship = hull_type in SQUADRON_HULL_TYPES
                    if is_warship:
                        if hull_type not in sq_ids:
                            sq_ids[hull_type] = create_squadron(
                                game_conn, fleet_id, polity_id,
                                name=f"{pdef['name']} {hull_type.replace('_',' ').title()}",
                                hull_type=hull_type,
                                combat_role="line_of_battle",
                                system_id=homeworld_system,
                            )
                        for _ in range(count):
                            hull_seq[hull_type] = hull_seq.get(hull_type, 0) + 1
                            create_hull(
                                game_conn, polity_id,
                                name=name_gen.hull(hull_type, hull_seq[hull_type]),
                                hull_type=hull_type,
                                system_id=homeworld_system,
                                fleet_id=fleet_id,
                                squadron_id=sq_ids[hull_type],
                                created_tick=0,
                            )
                    else:
                        for _ in range(count):
                            hull_seq[hull_type] = hull_seq.get(hull_type, 0) + 1
                            create_hull(
                                game_conn, polity_id,
                                name=name_gen.hull(hull_type, hull_seq[hull_type]),
                                hull_type=hull_type,
                                system_id=homeworld_system,
                                fleet_id=fleet_id,
                                squadron_id=None,
                                created_tick=0,
                            )

                # Commission a starting admiral for the fleet.
                sp = world.get_species(species_id)
                commission_on_demand(
                    game_conn, polity_id, fleet_id, sp,
                    tick=0, rng=rng, name_gen=name_gen,
                )

            # SDBs — no fleet, fixed to homeworld system.
            sdb_count = sdbs_by_polity[i]
            if sdb_count:
                sdb_sq = create_squadron(
                    game_conn, fleet_id=None, polity_id=polity_id,
                    name=f"{pdef['name']} SDB Defence",
                    hull_type="sdb", combat_role="screen",
                    system_id=homeworld_system,
                )
                for j in range(sdb_count):
                    create_hull(
                        game_conn, polity_id,
                        name=name_gen.hull("sdb", j + 1),
                        hull_type="sdb",
                        system_id=homeworld_system,
                        fleet_id=None,
                        squadron_id=sdb_sq,
                        created_tick=0,
                    )

            # Ground forces.
            for _ in range(armies_by_polity[i]):
                create_ground_force(
                    game_conn, polity_id,
                    name=name_gen.hull("army", _),
                    unit_type="army",
                    system_id=homeworld_system,
                    body_id=homeworld_body_id,
                    created_tick=0,
                )

            for _ in range(garrisons_by_polity[i]):
                create_ground_force(
                    game_conn, polity_id,
                    name=name_gen.hull("garrison", _),
                    unit_type="garrison",
                    system_id=homeworld_system,
                    body_id=homeworld_body_id,
                    created_tick=0,
                )

    game_conn.commit()
