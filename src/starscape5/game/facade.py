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

from .economy import compute_ru_production
from .polity import update_treasury, get_active_polities
from .presence import get_presences_by_polity
from .fleet import get_hulls_in_fleet, get_fleets_by_polity, mark_hull_active
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

            gen = NameGenerator(species_id=self._conn.execute(
                "SELECT species_id FROM Polity WHERE polity_id = ?", (polity_id,)
            ).fetchone()["species_id"])
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
                event_type="colony_established",  # reuse closest type; M13 adds hull_built
                summary=f"{hull_type} completed at system {system_id}",
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
