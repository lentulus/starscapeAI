"""GameFacade — the seam between the engine layer and game.db.

Engine phase modules never import from game.* directly.  They call methods
on a GameFacade instance.  This keeps the engine testable without a database:
swap GameFacadeImpl for GameFacadeStub and the whole engine runs on recorded
dummy values.

Three classes are defined here:
  GameFacade      — Protocol (structural type-check only)
  GameFacadeStub  — records calls as (method, args) tuples; returns configured
                    dummy values; used in unit tests for engine logic
  GameFacadeImpl  — real implementation wrapping a game.db connection
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from random import Random

from starscape5.world.facade import WorldFacade
from .economy import compute_ru_production
from .polity import update_treasury, get_active_polities
from .presence import get_presences_by_polity
from .fleet import get_hulls_in_fleet, get_fleets_by_polity, mark_hull_active, FleetRow
from .ground import get_ground_forces_by_polity
from .constants import HULL_STATS, GROUND_STATS
from .events import write_event


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class GameFacade(Protocol):
    """Methods the engine may call on the game layer during Economy phase."""

    def collect_ru(self, polity_id: int, tick: int) -> float:
        """Sum RU production for all presences; deposit to treasury; log rows."""
        ...

    def pay_maintenance(self, polity_id: int, tick: int) -> float:
        """Sum hull + ground maintenance; deduct from treasury."""
        ...

    def advance_build_queues(self, tick: int) -> list[int]:
        """Tick all BuildQueue entries; create completed hulls; return hull_ids."""
        ...

    def advance_repair_queues(self, tick: int) -> list[int]:
        """Tick RepairQueue entries; restore hull status; return repaired hull_ids."""
        ...

    def apply_supply_degradation(self, polity_id: int, tick: int) -> None:
        """Double maintenance at 8+ supply_ticks; degrade ratings at 16+."""
        ...

    def update_passive_scan(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> int:
        """Scan 20 pc radius; upsert passive SystemIntelligence rows."""
        ...

    def check_growth_cycles(
        self, polity_id: int, tick: int, rng: Random
    ) -> list:
        """Roll development/state advancement at 25-week checkpoints."""
        ...

    def increment_peace_weeks(self) -> None:
        """Increment peace_weeks on all non-war ContactRecord rows."""
        ...

    def check_map_sharing(self, tick: int) -> list[tuple[int, int]]:
        """Fire intel exchange for pairs at peace >= 52 weeks."""
        ...

    def execute_jump(
        self, fleet_id: int, destination_system_id: int, tick: int
    ) -> None:
        """Order fleet to jump; status→in_transit, destination_tick=tick+1."""
        ...

    def process_arrivals(self, tick: int) -> list[tuple[int, int, int, int | None]]:
        """Settle all in-transit fleets with destination_tick==tick.

        Returns list of (fleet_id, polity_id, system_id, prev_system_id).
        prev_system_id is the jump origin (None if unknown).
        """
        ...

    def record_jump_route(
        self, from_system_id: int, to_system_id: int, tick: int, world: WorldFacade
    ) -> bool:
        """Record a deduped jump route; returns True if a new row was inserted."""
        ...

    def get_fleet(self, fleet_id: int) -> FleetRow:
        """Fetch a single Fleet row."""
        ...

    def record_visit(
        self, polity_id: int, system_id: int, world: WorldFacade, tick: int
    ) -> None:
        """Record a full-intel fleet visit to system_id."""
        ...

    def detect_contacts(
        self, system_id: int, tick: int
    ) -> list[tuple[int, int]]:
        """Create ContactRecord rows for newly co-present polity pairs."""
        ...

    def generate_expand_orders(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> list[tuple[int, int]]:
        """Return (fleet_id, dest_system_id) expand orders for polity."""
        ...

    def find_contested_systems(self) -> list[int]:
        """Return system_ids where at-war polity pairs both have active fleets."""
        ...

    def resolve_space_combat(
        self, system_id: int, tick: int, rng: "Random"
    ) -> list:
        """Resolve one combat round in system_id; return list[CombatResult]."""
        ...

    def find_bombardment_candidates(self) -> list[tuple[int, int, int]]:
        """Return (system_id, attacker_id, defender_id) where bombardment applies."""
        ...

    def run_bombardment_tick(
        self, system_id: int, attacker_id: int, defender_id: int,
        tick: int, rng: "Random"
    ):
        """Execute one tick of orbital bombardment; return BombardmentResult."""
        ...

    def find_assault_candidates(self) -> list[tuple[int, int, int, int]]:
        """Return (system_id, body_id, attacker_id, defender_id) for pending assaults."""
        ...

    def run_ground_assault(
        self, system_id: int, body_id: int,
        attacker_id: int, defender_id: int,
        tick: int, rng: "Random", first_round: bool = True
    ):
        """Resolve one tick of ground combat; return AssaultResult."""
        ...

    def build_snapshot(self, polity_id: int, tick: int):
        """Return a GameStateSnapshot for polity_id."""
        ...

    def process_war_rolls(self, tick: int, rng: "Random") -> list:
        """Roll war initiation for all in-contact non-war pairs; return WarDeclared list."""
        ...

    def execute_actions(
        self, polity_id: int, actions: list, world, tick: int
    ) -> list[str]:
        """Execute a list of decided CandidateActions; return summary strings."""
        ...

    def get_events_for_tick(self, tick: int) -> list:
        """Return all GameEvent rows for the given tick."""
        ...

    def is_quiet_tick(self, events_this_tick: list) -> bool:
        """Return True if tick has no significant events (combat/war/colony/control)."""
        ...

    def write_monthly_summary(self, tick: int, phase: int) -> str:
        """Write a monthly_summary event; return summary string."""
        ...


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------

@dataclass
class GameFacadeStub:
    """Records every call as (method_name, args_tuple) for engine unit tests.

    Configure return values via the `returns` dict keyed by method name.
    Defaults: collect_ru→0.0, pay_maintenance→0.0, advance_*→[], apply_*→None.
    """
    calls: list[tuple] = field(default_factory=list)
    returns: dict = field(default_factory=dict)

    def _record(self, method: str, *args):
        self.calls.append((method, args))

    def collect_ru(self, polity_id: int, tick: int) -> float:
        self._record("collect_ru", polity_id, tick)
        return self.returns.get("collect_ru", 0.0)

    def pay_maintenance(self, polity_id: int, tick: int) -> float:
        self._record("pay_maintenance", polity_id, tick)
        return self.returns.get("pay_maintenance", 0.0)

    def advance_build_queues(self, tick: int) -> list[int]:
        self._record("advance_build_queues", tick)
        return self.returns.get("advance_build_queues", [])

    def advance_repair_queues(self, tick: int) -> list[int]:
        self._record("advance_repair_queues", tick)
        return self.returns.get("advance_repair_queues", [])

    def apply_supply_degradation(self, polity_id: int, tick: int) -> None:
        self._record("apply_supply_degradation", polity_id, tick)

    def update_passive_scan(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> int:
        self._record("update_passive_scan", polity_id, tick)
        return self.returns.get("update_passive_scan", 0)

    def check_growth_cycles(
        self, polity_id: int, tick: int, rng: Random
    ) -> list:
        self._record("check_growth_cycles", polity_id, tick)
        return self.returns.get("check_growth_cycles", [])

    def increment_peace_weeks(self) -> None:
        self._record("increment_peace_weeks")

    def check_map_sharing(self, tick: int) -> list[tuple[int, int]]:
        self._record("check_map_sharing", tick)
        return self.returns.get("check_map_sharing", [])

    def execute_jump(
        self, fleet_id: int, destination_system_id: int, tick: int
    ) -> None:
        self._record("execute_jump", fleet_id, destination_system_id, tick)

    def process_arrivals(self, tick: int) -> list[tuple[int, int, int, int | None]]:
        self._record("process_arrivals", tick)
        return self.returns.get("process_arrivals", [])

    def record_jump_route(
        self, from_system_id: int, to_system_id: int, tick: int, world: WorldFacade
    ) -> bool:
        self._record("record_jump_route", from_system_id, to_system_id, tick)
        return False

    def get_fleet(self, fleet_id: int) -> FleetRow:
        self._record("get_fleet", fleet_id)
        return self.returns["get_fleet"]  # must be configured; no sensible default

    def record_visit(
        self, polity_id: int, system_id: int, world: WorldFacade, tick: int
    ) -> None:
        self._record("record_visit", polity_id, system_id, tick)

    def detect_contacts(
        self, system_id: int, tick: int
    ) -> list[tuple[int, int]]:
        self._record("detect_contacts", system_id, tick)
        return self.returns.get("detect_contacts", [])

    def generate_expand_orders(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> list[tuple[int, int]]:
        self._record("generate_expand_orders", polity_id, tick)
        return self.returns.get("generate_expand_orders", [])

    def find_contested_systems(self) -> list[int]:
        self._record("find_contested_systems")
        return self.returns.get("find_contested_systems", [])

    def resolve_space_combat(
        self, system_id: int, tick: int, rng: "Random"
    ) -> list:
        self._record("resolve_space_combat", system_id, tick)
        return self.returns.get("resolve_space_combat", [])

    def find_bombardment_candidates(self) -> list[tuple[int, int, int]]:
        self._record("find_bombardment_candidates")
        return self.returns.get("find_bombardment_candidates", [])

    def run_bombardment_tick(
        self, system_id: int, attacker_id: int, defender_id: int,
        tick: int, rng: "Random"
    ):
        self._record("run_bombardment_tick", system_id, attacker_id, defender_id, tick)
        return self.returns.get("run_bombardment_tick", None)

    def find_assault_candidates(self) -> list[tuple[int, int, int, int]]:
        self._record("find_assault_candidates")
        return self.returns.get("find_assault_candidates", [])

    def run_ground_assault(
        self, system_id: int, body_id: int,
        attacker_id: int, defender_id: int,
        tick: int, rng: "Random", first_round: bool = True
    ):
        self._record("run_ground_assault", system_id, body_id, attacker_id, defender_id, tick)
        return self.returns.get("run_ground_assault", None)

    def build_snapshot(self, polity_id: int, tick: int):
        self._record("build_snapshot", polity_id, tick)
        return self.returns.get("build_snapshot", None)

    def process_war_rolls(self, tick: int, rng: "Random") -> list:
        self._record("process_war_rolls", tick)
        return self.returns.get("process_war_rolls", [])

    def execute_actions(
        self, polity_id: int, actions: list, world, tick: int
    ) -> list[str]:
        self._record("execute_actions", polity_id, tick)
        return self.returns.get("execute_actions", [])

    def get_events_for_tick(self, tick: int) -> list:
        self._record("get_events_for_tick", tick)
        return self.returns.get("get_events_for_tick", [])

    def is_quiet_tick(self, events_this_tick: list) -> bool:
        self._record("is_quiet_tick")
        return self.returns.get("is_quiet_tick", True)

    def write_monthly_summary(self, tick: int, phase: int) -> str:
        self._record("write_monthly_summary", tick, phase)
        return self.returns.get("write_monthly_summary", "")


# ---------------------------------------------------------------------------
# Real implementation
# ---------------------------------------------------------------------------

class GameFacadeImpl:
    """Real GameFacade backed by an open game.db connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def collect_ru(self, polity_id: int, tick: int) -> float:
        """Sum RU production across all presences; deposit to treasury.

        Reads WorldPotential cache for each presence body.  If a body has no
        cached entry, uses potential=10 as a conservative default.
        """
        presences = get_presences_by_polity(self._conn, polity_id)
        total_produced = 0.0

        for p in presences:
            pot_row = self._conn.execute(
                "SELECT world_potential FROM WorldPotential WHERE body_id = ?",
                (p.body_id,),
            ).fetchone()
            potential = pot_row["world_potential"] if pot_row else 10
            ru = compute_ru_production(potential, p.control_state, p.development_level)
            total_produced += ru

            # Append to SystemEconomy log (ru_maintenance/construction filled
            # after maintenance pass; we write a placeholder row here and
            # update it — simpler to just write at end of economy phase).
            # For M6, write a simplified single row per polity instead.

        update_treasury(self._conn, polity_id, total_produced)
        return total_produced

    def pay_maintenance(self, polity_id: int, tick: int) -> float:
        """Sum and deduct maintenance for all hulls and ground forces."""
        total_maint = 0.0

        # Hull maintenance
        for fleet in get_fleets_by_polity(self._conn, polity_id):
            for hull in get_hulls_in_fleet(self._conn, fleet.fleet_id):
                stats = HULL_STATS.get(hull.hull_type)
                if stats:
                    maint = stats.maint_per_tick
                    # Supply degradation doubles maintenance (applied separately,
                    # but hulls with status 'damaged' still pay full maint)
                    total_maint += maint

        # SDB maintenance (squadron but no fleet)
        sdb_rows = self._conn.execute(
            """
            SELECT h.hull_type FROM Hull h
            JOIN   Squadron s ON s.squadron_id = h.squadron_id
            WHERE  h.polity_id = ? AND h.fleet_id IS NULL
              AND  h.status != 'destroyed'
            """,
            (polity_id,),
        ).fetchall()
        for row in sdb_rows:
            stats = HULL_STATS.get(row["hull_type"])
            if stats:
                total_maint += stats.maint_per_tick

        # Ground force maintenance
        for force in get_ground_forces_by_polity(self._conn, polity_id):
            stats = GROUND_STATS.get(force.unit_type)
            if stats:
                maint = stats.maint_per_tick
                # Occupation duty × 1.5
                if force.occupation_duty:
                    maint *= 1.5
                total_maint += maint

        update_treasury(self._conn, polity_id, -total_maint)
        return total_maint

    def advance_build_queues(self, tick: int) -> list[int]:
        """Tick all BuildQueue entries; complete finished builds."""
        from .names import NameGenerator

        self._conn.execute(
            "UPDATE BuildQueue SET ticks_elapsed = ticks_elapsed + 1"
        )

        completed = self._conn.execute(
            """
            SELECT * FROM BuildQueue
            WHERE  ticks_elapsed >= ticks_total
            """,
        ).fetchall()

        hull_ids: list[int] = []
        for row in completed:
            polity_id = row["polity_id"]
            system_id = row["system_id"]
            hull_type = row["hull_type"]

            # Determine fleet at this system for this polity (if any).
            fleet_row = self._conn.execute(
                """
                SELECT fleet_id FROM Fleet
                WHERE  polity_id = ? AND system_id = ? AND status = 'active'
                LIMIT  1
                """,
                (polity_id, system_id),
            ).fetchone()
            fleet_id = fleet_row["fleet_id"] if fleet_row else None

            polity_row = self._conn.execute(
                "SELECT species_id, name FROM Polity WHERE polity_id = ?", (polity_id,)
            ).fetchone()
            gen = NameGenerator(species_id=polity_row["species_id"])
            polity_name = polity_row["name"]
            seq = self._conn.execute(
                "SELECT COUNT(*) FROM Hull WHERE polity_id = ?", (polity_id,)
            ).fetchone()[0] + 1
            name = gen.hull(hull_type, seq)

            from .fleet import create_hull
            hull_id = create_hull(
                self._conn, polity_id, name, hull_type,
                system_id=system_id, fleet_id=fleet_id,
                squadron_id=None, created_tick=tick,
            )
            hull_ids.append(hull_id)

            write_event(
                self._conn, tick=tick, phase=8,
                event_type="hull_built",
                summary=f"{polity_name}: {hull_type} completed at system {system_id}",
                polity_a_id=polity_id, system_id=system_id,
            )

            self._conn.execute(
                "DELETE FROM BuildQueue WHERE queue_id = ?", (row["queue_id"],)
            )

        return hull_ids

    def advance_repair_queues(self, tick: int) -> list[int]:
        """Tick RepairQueue entries; restore damaged hulls on completion."""
        self._conn.execute(
            "UPDATE RepairQueue SET ticks_elapsed = ticks_elapsed + 1"
        )

        completed = self._conn.execute(
            """
            SELECT * FROM RepairQueue
            WHERE  ticks_elapsed >= ticks_total
            """,
        ).fetchall()

        hull_ids: list[int] = []
        for row in completed:
            mark_hull_active(self._conn, row["hull_id"])
            hull_ids.append(row["hull_id"])
            self._conn.execute(
                "DELETE FROM RepairQueue WHERE repair_id = ?", (row["repair_id"],)
            )

        return hull_ids

    def update_passive_scan(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> int:
        from .intelligence import update_passive_scan
        return update_passive_scan(self._conn, polity_id, world, tick)

    def check_growth_cycles(
        self, polity_id: int, tick: int, rng: Random
    ) -> list:
        from .control import check_growth_cycles
        return check_growth_cycles(self._conn, polity_id, tick, rng)

    def increment_peace_weeks(self) -> None:
        from .intelligence import increment_peace_weeks
        increment_peace_weeks(self._conn)

    def check_map_sharing(self, tick: int) -> list[tuple[int, int]]:
        from .intelligence import check_map_sharing
        return check_map_sharing(self._conn, tick)

    def execute_jump(
        self, fleet_id: int, destination_system_id: int, tick: int
    ) -> None:
        from .movement import execute_jump
        execute_jump(self._conn, fleet_id, destination_system_id, tick)

    def process_arrivals(self, tick: int) -> list[tuple[int, int, int, int | None]]:
        from .movement import process_arrivals
        return process_arrivals(self._conn, tick)

    def record_jump_route(
        self, from_system_id: int, to_system_id: int, tick: int, world: WorldFacade
    ) -> bool:
        from .routes import record_jump_route
        return record_jump_route(self._conn, world, from_system_id, to_system_id, tick)

    def get_fleet(self, fleet_id: int) -> FleetRow:
        from .fleet import get_fleet
        return get_fleet(self._conn, fleet_id)

    def record_visit(
        self, polity_id: int, system_id: int, world: WorldFacade, tick: int
    ) -> None:
        from .intelligence import record_visit
        record_visit(self._conn, polity_id, system_id, world, tick)

    def detect_contacts(
        self, system_id: int, tick: int
    ) -> list[tuple[int, int]]:
        from .movement import detect_contacts
        return detect_contacts(self._conn, system_id, tick)

    def generate_expand_orders(
        self, polity_id: int, world: WorldFacade, tick: int
    ) -> list[tuple[int, int]]:
        from .decision import generate_expand_orders
        return generate_expand_orders(self._conn, polity_id, world, tick)

    def find_contested_systems(self) -> list[int]:
        from .combat import find_contested_systems
        return find_contested_systems(self._conn)

    def resolve_space_combat(
        self, system_id: int, tick: int, rng: "Random"
    ) -> list:
        from .combat import resolve_space_combat
        return resolve_space_combat(self._conn, system_id, tick, rng)

    def find_bombardment_candidates(self) -> list[tuple[int, int, int]]:
        from .bombardment import find_bombardment_candidates
        return find_bombardment_candidates(self._conn)

    def run_bombardment_tick(
        self, system_id: int, attacker_id: int, defender_id: int,
        tick: int, rng: "Random"
    ):
        from .bombardment import run_bombardment_tick
        return run_bombardment_tick(self._conn, system_id, attacker_id, defender_id, tick, rng)

    def find_assault_candidates(self) -> list[tuple[int, int, int, int]]:
        from .assault import find_assault_candidates
        return find_assault_candidates(self._conn)

    def run_ground_assault(
        self, system_id: int, body_id: int,
        attacker_id: int, defender_id: int,
        tick: int, rng: "Random", first_round: bool = True
    ):
        from .assault import run_ground_assault
        return run_ground_assault(
            self._conn, system_id, body_id, attacker_id, defender_id,
            tick, rng, first_round
        )

    def build_snapshot(self, polity_id: int, tick: int):
        from .snapshot import build_snapshot
        return build_snapshot(self._conn, polity_id, tick)

    def process_war_rolls(self, tick: int, rng: "Random") -> list:
        from .war import process_war_rolls
        return process_war_rolls(self._conn, tick, rng)

    def execute_actions(
        self, polity_id: int, actions: list, world, tick: int
    ) -> list[str]:
        from .action_executor import execute_actions
        return execute_actions(self._conn, polity_id, actions, world, tick)

    def get_events_for_tick(self, tick: int) -> list:
        from .events import get_events
        return get_events(self._conn, tick=tick)

    def is_quiet_tick(self, events_this_tick: list) -> bool:
        from .log import is_quiet_tick
        return is_quiet_tick(events_this_tick)

    def write_monthly_summary(self, tick: int, phase: int) -> str:
        from .log import write_monthly_summary
        write_monthly_summary(self._conn, tick, phase)
        return f"tick={tick} monthly_summary"

    def apply_supply_degradation(self, polity_id: int, tick: int) -> None:
        """Apply supply penalties to fleets that have gone too long without resupply.

        8+ ticks: double maintenance this tick (extra deduction).
        16+ ticks: combat ratings degrade — mark hulls as 'damaged'.
        """
        for fleet in get_fleets_by_polity(self._conn, polity_id):
            st = fleet.supply_ticks
            if st == 0:
                continue
            if st >= 16:
                # Degrade: mark active hulls as damaged
                hulls = get_hulls_in_fleet(self._conn, fleet.fleet_id)
                for hull in hulls:
                    if hull.status == "active":
                        from .fleet import mark_hull_damaged
                        mark_hull_damaged(self._conn, hull.hull_id)
            elif st >= 8:
                # Double maintenance: deduct an extra maintenance cost
                extra = sum(
                    HULL_STATS[h.hull_type].maint_per_tick
                    for h in get_hulls_in_fleet(self._conn, fleet.fleet_id)
                    if h.hull_type in HULL_STATS
                )
                update_treasury(self._conn, polity_id, -extra)


# Runtime check
assert isinstance(GameFacadeStub(), GameFacade), (
    "GameFacadeStub does not satisfy GameFacade protocol"
)
assert isinstance(GameFacadeImpl.__new__(GameFacadeImpl), GameFacade), (
    "GameFacadeImpl does not satisfy GameFacade protocol"
)
