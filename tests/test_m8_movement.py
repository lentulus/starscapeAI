"""M8 — Movement phase and contact detection tests.

Tests cover:
  game/movement.py  — execute_jump, process_arrivals, detect_contacts
  game/decision.py  — generate_expand_orders
  engine/decision.py  — run_decision_phase
  engine/movement.py  — run_movement_phase
  engine/tick.py      — run_partial_tick
"""

from __future__ import annotations

import sqlite3

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.facade import GameFacadeImpl, GameFacadeStub
from starscape5.game.fleet import (
    create_fleet, create_hull, set_fleet_destination,
    get_fleet, get_hulls_in_fleet,
)
from starscape5.game.polity import create_polity
from starscape5.game.movement import (
    execute_jump, process_arrivals, detect_contacts, get_fleet_jump_range,
)
from starscape5.game.decision import generate_expand_orders
from starscape5.game.intelligence import record_visit
from starscape5.game.events import get_recent_events
from starscape5.engine.decision import run_decision_phase
from starscape5.engine.movement import run_movement_phase
from starscape5.engine.tick import run_partial_tick
from starscape5.world.stub import WorldStub


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory game.db, fully initialised."""
    c = open_game(":memory:")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def world():
    return WorldStub(seed=42, universe_size=30)


def _make_polity(conn, polity_id_hint: int, system_id: int) -> int:
    """Create a polity and return its polity_id."""
    return create_polity(
        conn,
        species_id=1,
        name=f"P{polity_id_hint}",
        capital_system_id=system_id,
        expansionism=0.5,
        aggression=0.5,
        risk_appetite=0.5,
        processing_order=polity_id_hint,
    )


def _make_scout_fleet(conn, polity_id: int, system_id: int) -> tuple[int, int]:
    """Create a fleet with one scout hull at system_id. Returns (fleet_id, hull_id)."""
    fleet_id = create_fleet(conn, polity_id, f"Scout Fleet {polity_id}", system_id)
    hull_id = create_hull(
        conn, polity_id, f"Scout {polity_id}", "scout",
        system_id=system_id, fleet_id=fleet_id,
        squadron_id=None, created_tick=0,
    )
    return fleet_id, hull_id


def _make_presence(conn, polity_id: int, system_id: int, body_id: int | None = None) -> None:
    """Insert a minimal controlled presence for polity at system."""
    if body_id is None:
        body_id = system_id * 10
    presence_id = conn.execute(
        "SELECT COALESCE(MAX(presence_id), 0) + 1 FROM SystemPresence"
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO SystemPresence
            (presence_id, polity_id, system_id, body_id, control_state,
             development_level, established_tick, last_updated_tick)
        VALUES (?, ?, ?, ?, 'controlled', 3, 0, 0)
        """,
        (presence_id, polity_id, system_id, body_id),
    )


# ---------------------------------------------------------------------------
# execute_jump
# ---------------------------------------------------------------------------

class TestExecuteJump:
    def test_sets_fleet_in_transit(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 2, tick=1)
        fleet = get_fleet(conn, fleet_id)
        assert fleet.status == "in_transit"
        assert fleet.destination_system_id == 2
        assert fleet.destination_tick == 2
        assert fleet.system_id is None

    def test_sets_hull_in_transit(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id, hull_id = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 5, tick=3)
        row = conn.execute(
            "SELECT status, destination_system_id, destination_tick, system_id "
            "FROM Hull_head WHERE hull_id = ?", (hull_id,)
        ).fetchone()
        assert row["status"] == "in_transit"
        assert row["destination_system_id"] == 5
        assert row["destination_tick"] == 4
        assert row["system_id"] is None


# ---------------------------------------------------------------------------
# get_fleet_jump_range
# ---------------------------------------------------------------------------

class TestFleetJumpRange:
    def test_scout_fleet_has_range_10(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        assert get_fleet_jump_range(conn, fleet_id) == 10

    def test_empty_fleet_has_range_0(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id = create_fleet(conn, pid, "Empty Fleet", 1)
        assert get_fleet_jump_range(conn, fleet_id) == 0

    def test_mixed_fleet_uses_minimum(self, conn):
        """A fleet with a capital (J3) and cruiser (J4) has range 3."""
        pid = _make_polity(conn, 1, 1)
        fleet_id = create_fleet(conn, pid, "Mixed", 1)
        create_hull(conn, pid, "Cap", "capital",
                    system_id=1, fleet_id=fleet_id, squadron_id=None, created_tick=0)
        create_hull(conn, pid, "Cru", "cruiser",
                    system_id=1, fleet_id=fleet_id, squadron_id=None, created_tick=0)
        assert get_fleet_jump_range(conn, fleet_id) == 3


# ---------------------------------------------------------------------------
# process_arrivals
# ---------------------------------------------------------------------------

class TestProcessArrivals:
    def test_fleet_arrives_at_destination(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 7, tick=1)
        # No arrivals at tick 1 (destination_tick = 2)
        assert process_arrivals(conn, 1) == []
        # Arrive at tick 2
        arrived = process_arrivals(conn, 2)
        assert len(arrived) == 1
        fid, pid_ret, sid, prev_sid = arrived[0]
        assert fid == fleet_id
        assert pid_ret == pid
        assert sid == 7

    def test_fleet_status_active_after_arrival(self, conn):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 3, tick=5)
        process_arrivals(conn, 6)
        fleet = get_fleet(conn, fleet_id)
        assert fleet.status == "active"
        assert fleet.system_id == 3
        assert fleet.destination_system_id is None

    def test_no_spurious_arrivals(self, conn):
        """Fleets still in transit don't appear as arrived."""
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 4, tick=10)
        assert process_arrivals(conn, 10) == []
        assert process_arrivals(conn, 9) == []


# ---------------------------------------------------------------------------
# detect_contacts
# ---------------------------------------------------------------------------

class TestDetectContacts:
    def test_single_polity_no_contact(self, conn):
        pid = _make_polity(conn, 1, 1)
        _make_presence(conn, pid, 1)
        assert detect_contacts(conn, 1, tick=1) == []

    def test_two_polities_fleet_and_presence(self, conn):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        _make_presence(conn, pid2, 5)
        _make_scout_fleet(conn, pid1, 5)  # fleet arrives in polity2's system
        contacts = detect_contacts(conn, 5, tick=10)
        assert len(contacts) == 1
        a, b = contacts[0]
        assert a < b  # schema enforces this

    def test_contact_creates_record(self, conn):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        _make_presence(conn, pid1, 8)
        _make_presence(conn, pid2, 8)
        detect_contacts(conn, 8, tick=5)
        row = conn.execute(
            "SELECT * FROM ContactRecord WHERE contact_system_id = 8"
        ).fetchone()
        assert row is not None
        assert row["contact_tick"] == 5

    def test_contact_writes_event(self, conn):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        _make_presence(conn, pid1, 3)
        _make_presence(conn, pid2, 3)
        detect_contacts(conn, 3, tick=7)
        events = get_recent_events(conn, 10)
        contact_events = [e for e in events if e.event_type == "contact"]
        assert len(contact_events) == 1

    def test_contact_not_duplicated(self, conn):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        _make_presence(conn, pid1, 4)
        _make_presence(conn, pid2, 4)
        first = detect_contacts(conn, 4, tick=1)
        second = detect_contacts(conn, 4, tick=2)
        assert len(first) == 1
        assert len(second) == 0  # already recorded

    def test_three_polities_three_contacts(self, conn):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        pid3 = _make_polity(conn, 3, 3)
        for pid in (pid1, pid2, pid3):
            _make_presence(conn, pid, 9)
        contacts = detect_contacts(conn, 9, tick=1)
        assert len(contacts) == 3


# ---------------------------------------------------------------------------
# generate_expand_orders
# ---------------------------------------------------------------------------

class TestGenerateExpandOrders:
    def test_scout_fleet_gets_order(self, conn, world):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        # Mark system 1 as visited (homeworld)
        record_visit(conn, pid, 1, world, tick=0)
        orders = generate_expand_orders(conn, pid, world, tick=1)
        assert len(orders) == 1
        fid, dest = orders[0]
        assert fid == fleet_id
        assert dest != 1  # not going back to same system

    def test_no_order_when_all_visited(self, conn, world):
        """Fleet stays put if every reachable system is already visited."""
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        # Mark all nearby systems visited
        nearby = world.get_systems_within_parsecs(1, 4.0)
        for sid in [1] + nearby:
            record_visit(conn, pid, sid, world, tick=0)
        orders = generate_expand_orders(conn, pid, world, tick=1)
        assert orders == []

    def test_in_transit_fleet_gets_no_order(self, conn, world):
        """In-transit fleets are excluded (status != 'active')."""
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        record_visit(conn, pid, 1, world, tick=0)
        execute_jump(conn, fleet_id, 2, tick=1)  # now in_transit
        orders = generate_expand_orders(conn, pid, world, tick=2)
        assert orders == []


# ---------------------------------------------------------------------------
# Engine: run_decision_phase
# ---------------------------------------------------------------------------

class TestRunDecisionPhase:
    def test_issues_jump_summaries(self, conn, world):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        record_visit(conn, pid, 1, world, tick=0)
        game = GameFacadeImpl(conn)
        summaries = run_decision_phase(1, 2, [pid], game, world)
        assert any("jump" in s for s in summaries)

    def test_stub_calls_recorded(self):
        stub = GameFacadeStub()
        run_decision_phase(1, 2, [1], stub, WorldStub())
        method_names = [c[0] for c in stub.calls]
        assert "process_war_rolls" in method_names
        assert "build_snapshot" in method_names


# ---------------------------------------------------------------------------
# Engine: run_movement_phase
# ---------------------------------------------------------------------------

class TestRunMovementPhase:
    def test_arrival_in_summary(self, conn, world):
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        execute_jump(conn, fleet_id, 2, tick=1)
        game = GameFacadeImpl(conn)
        summaries = run_movement_phase(2, 3, [pid], game, world)
        assert any("arrived" in s for s in summaries)
        assert any(f"fleet={fleet_id}" in s for s in summaries)

    def test_contact_in_summary(self, conn, world):
        pid1 = _make_polity(conn, 1, 1)
        pid2 = _make_polity(conn, 2, 2)
        fleet_id, _ = _make_scout_fleet(conn, pid1, 1)
        # pid2 has a presence at system 2
        _make_presence(conn, pid2, 2)
        execute_jump(conn, fleet_id, 2, tick=1)
        game = GameFacadeImpl(conn)
        summaries = run_movement_phase(2, 3, [pid1, pid2], game, world)
        assert any("contact" in s for s in summaries)


# ---------------------------------------------------------------------------
# Engine: run_partial_tick
# ---------------------------------------------------------------------------

class TestRunPartialTick:
    def test_partial_tick_returns_strings(self, conn, world):
        pid = _make_polity(conn, 1, 1)
        _make_scout_fleet(conn, pid, 1)
        # Seed a WorldPotential row so economy can run
        conn.execute(
            "INSERT INTO WorldPotential (body_id, system_id, world_potential, "
            "has_gas_giant, has_ocean) VALUES (10, 1, 15, 0, 0)"
        )
        _make_presence(conn, pid, 1, body_id=10)
        record_visit(conn, pid, 1, world, tick=0)
        game = GameFacadeImpl(conn)
        result = run_partial_tick(1, [pid], game, world)
        assert isinstance(result, list)
        # At minimum passive_scan should produce something
        assert all(isinstance(s, str) for s in result)

    def test_multiple_ticks_produce_contact(self, conn, world):
        """Two polities make first contact when pid1's scout reaches pid2's homeworld."""
        s1 = 1
        neighbors_of_1 = world.get_systems_within_parsecs(s1, 4.0)
        assert neighbors_of_1, "WorldStub too sparse for this test"
        # Pick the NEAREST neighbor so the scout targets it on tick 1.
        s2 = min(neighbors_of_1, key=lambda sid: world.get_distance_pc(s1, sid))

        pid1 = _make_polity(conn, 1, s1)
        pid2 = _make_polity(conn, 2, s2)

        # pid1 has scout fleet at s1; pid2 has only a presence at s2
        fleet_id, _ = _make_scout_fleet(conn, pid1, s1)

        # WorldPotential + presences for economy phase
        for pid, sid in [(pid1, s1), (pid2, s2)]:
            body_id = sid * 10
            conn.execute(
                "INSERT OR IGNORE INTO WorldPotential "
                "(body_id, system_id, world_potential, has_gas_giant, has_ocean) "
                "VALUES (?, ?, 15, 0, 0)",
                (body_id, sid),
            )
            _make_presence(conn, pid, sid, body_id=body_id)

        # Mark s1 as visited for pid1 (homeworld) — scout won't try to "visit" it.
        # Also mark all other neighbors of s1 as visited so s2 is the ONLY valid
        # scout target (the new decision engine scores candidates, not nearest-first).
        record_visit(conn, pid1, s1, world, tick=0)
        for other_sid in neighbors_of_1:
            if other_sid != s2:
                record_visit(conn, pid1, other_sid, world, tick=0)

        game = GameFacadeImpl(conn)
        order = [pid1, pid2]

        # Tick 1: decision → scout jumps to s2 (only unvisited neighbor)
        # Tick 2: movement → scout arrives at s2 → detect_contacts fires
        for tick in range(1, 5):
            run_partial_tick(tick, order, game, world)

        all_events = get_recent_events(conn, 100)
        contact_events = [e for e in all_events if e.event_type == "contact"]
        assert len(contact_events) >= 1, "No first-contact event after 4 ticks"

    def test_phase_order_preserved(self, conn, world):
        """Decision-phase jumps (issued at tick T) are settled at tick T+1."""
        pid = _make_polity(conn, 1, 1)
        fleet_id, _ = _make_scout_fleet(conn, pid, 1)
        record_visit(conn, pid, 1, world, tick=0)
        game = GameFacadeImpl(conn)

        # After tick 1 the fleet should be in_transit (jump ordered in decision phase)
        run_partial_tick(1, [pid], game, world)
        fleet = get_fleet(conn, fleet_id)
        assert fleet.status == "in_transit"
        dest = fleet.destination_system_id
        assert dest is not None

        # After tick 2 the fleet should have arrived
        run_partial_tick(2, [pid], game, world)
        fleet = get_fleet(conn, fleet_id)
        assert fleet.status == "active"
        assert fleet.system_id == dest
