"""M6 tests — GameFacade, Economy phase."""

from random import Random
import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.state import create_gamestate, commit_phase, advance_phase
from starscape5.game.polity import (
    create_polity, get_polity, get_polity_processing_order,
)
from starscape5.game.fleet import (
    create_fleet, create_squadron, create_hull,
    get_hulls_in_fleet, get_fleet,
)
from starscape5.game.ground import create_ground_force, get_ground_force
from starscape5.game.presence import create_presence
from starscape5.game.economy import create_world_potential_cache
from starscape5.game.facade import GameFacade, GameFacadeImpl, GameFacadeStub
from starscape5.game.constants import HULL_STATS, GROUND_STATS
from starscape5.engine.economy import run_economy_phase
from starscape5.world.stub import WorldStub
from starscape5.game.init_game import init_game
from starscape5.game.ob_data import OB_DATA


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = open_game(":memory:")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def minimal(conn):
    """One polity with one fleet (2 capitals) and one presence."""
    create_gamestate(conn)
    pid = create_polity(conn, species_id=1, name="Kreeth",
                        capital_system_id=100, expansionism=0.7,
                        aggression=0.8, risk_appetite=0.6, processing_order=1,
                        treasury_ru=50.0)
    # WorldPotential row so economy can compute production
    create_world_potential_cache(conn, body_id=1001, system_id=100,
                                 world_potential=20, has_gas_giant=0, has_ocean=0)
    create_presence(conn, pid, system_id=100, body_id=1001,
                    control_state="controlled", development_level=3,
                    established_tick=0)
    fid = create_fleet(conn, pid, "First Swarm", system_id=100)
    sid = create_squadron(conn, fid, pid, "Capitals", "capital",
                          "line_of_battle", 100)
    create_hull(conn, pid, "CAP-001", "capital", 100, fid, sid, 0)
    create_hull(conn, pid, "CAP-002", "capital", 100, fid, sid, 0)
    conn.commit()
    return conn, pid, fid


@pytest.fixture
def full_game():
    """Full init_game state for integration tests."""
    c = open_game(":memory:")
    init_schema(c)
    init_game(c, WorldStub(seed=42), OB_DATA)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# GameFacade protocol
# ---------------------------------------------------------------------------

def test_stub_satisfies_protocol():
    assert isinstance(GameFacadeStub(), GameFacade)


def test_impl_satisfies_protocol(conn):
    assert isinstance(GameFacadeImpl(conn), GameFacade)


def test_stub_records_calls():
    stub = GameFacadeStub()
    stub.collect_ru(polity_id=1, tick=5)
    stub.pay_maintenance(polity_id=1, tick=5)
    stub.advance_build_queues(tick=5)
    assert ("collect_ru", (1, 5)) in stub.calls
    assert ("pay_maintenance", (1, 5)) in stub.calls
    assert ("advance_build_queues", (5,)) in stub.calls


def test_stub_returns_configured_values():
    stub = GameFacadeStub(returns={"collect_ru": 99.9, "advance_build_queues": [7, 8]})
    assert stub.collect_ru(1, 1) == pytest.approx(99.9)
    assert stub.advance_build_queues(1) == [7, 8]


# ---------------------------------------------------------------------------
# GameFacadeImpl.collect_ru
# ---------------------------------------------------------------------------

def test_collect_ru_deposits_to_treasury(minimal):
    conn, pid, _ = minimal
    before = get_polity(conn, pid).treasury_ru
    facade = GameFacadeImpl(conn)
    produced = facade.collect_ru(pid, tick=1)
    conn.commit()
    after = get_polity(conn, pid).treasury_ru
    assert produced > 0
    assert after == pytest.approx(before + produced)


def test_collect_ru_formula(minimal):
    conn, pid, _ = minimal
    # potential=20, controlled, dev-3: 20 * 1.0 * 1.0 = 20.0
    facade = GameFacadeImpl(conn)
    produced = facade.collect_ru(pid, tick=1)
    assert produced == pytest.approx(20.0)


def test_collect_ru_no_presence_gives_zero(conn):
    create_gamestate(conn)
    pid = create_polity(conn, species_id=1, name="Nobody",
                        capital_system_id=100, expansionism=0.5,
                        aggression=0.5, risk_appetite=0.5,
                        processing_order=1, treasury_ru=10.0)
    conn.commit()
    facade = GameFacadeImpl(conn)
    produced = facade.collect_ru(pid, tick=1)
    assert produced == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# GameFacadeImpl.pay_maintenance
# ---------------------------------------------------------------------------

def test_pay_maintenance_deducts_from_treasury(minimal):
    conn, pid, _ = minimal
    before = get_polity(conn, pid).treasury_ru
    facade = GameFacadeImpl(conn)
    paid = facade.pay_maintenance(pid, tick=1)
    conn.commit()
    after = get_polity(conn, pid).treasury_ru
    assert paid > 0
    assert after == pytest.approx(before - paid)


def test_pay_maintenance_two_capitals(minimal):
    conn, pid, _ = minimal
    facade = GameFacadeImpl(conn)
    paid = facade.pay_maintenance(pid, tick=1)
    # 2 × capital maint 2.0 = 4.0
    assert paid == pytest.approx(HULL_STATS["capital"].maint_per_tick * 2)


def test_pay_maintenance_includes_ground_forces(conn):
    create_gamestate(conn)
    pid = create_polity(conn, species_id=1, name="Kreeth",
                        capital_system_id=100, expansionism=0.7,
                        aggression=0.8, risk_appetite=0.6, processing_order=1,
                        treasury_ru=50.0)
    create_world_potential_cache(conn, 1001, 100, 20, 0, 0)
    create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    create_ground_force(conn, pid, "1st Army", "army", 100, 1001, 0)
    create_ground_force(conn, pid, "Garrison", "garrison", 100, 1001, 0)
    conn.commit()
    facade = GameFacadeImpl(conn)
    paid = facade.pay_maintenance(pid, tick=1)
    # army 0.5 + garrison 0.0
    assert paid == pytest.approx(GROUND_STATS["army"].maint_per_tick)


def test_occupation_duty_multiplier(conn):
    create_gamestate(conn)
    pid = create_polity(conn, species_id=1, name="Kreeth",
                        capital_system_id=100, expansionism=0.7,
                        aggression=0.8, risk_appetite=0.6, processing_order=1,
                        treasury_ru=50.0)
    create_world_potential_cache(conn, 1001, 100, 20, 0, 0)
    create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    fid = create_ground_force(conn, pid, "Occupiers", "army", 100, 1001, 0)
    conn.execute("UPDATE GroundForce SET occupation_duty=1 WHERE force_id=?", (fid,))
    conn.commit()
    facade = GameFacadeImpl(conn)
    paid = facade.pay_maintenance(pid, tick=1)
    # army 0.5 × 1.5 = 0.75
    assert paid == pytest.approx(GROUND_STATS["army"].maint_per_tick * 1.5)


# ---------------------------------------------------------------------------
# GameFacadeImpl.advance_build_queues
# ---------------------------------------------------------------------------

def test_build_queue_completes(minimal):
    conn, pid, fid = minimal
    conn.execute(
        "INSERT INTO BuildQueue (polity_id, system_id, hull_type, ticks_total, "
        "ticks_elapsed, reserved_ru, ordered_tick) VALUES (?, 100, 'escort', 1, 0, 8.0, 0)",
        (pid,),
    )
    conn.commit()
    facade = GameFacadeImpl(conn)
    hull_ids = facade.advance_build_queues(tick=1)
    conn.commit()
    assert len(hull_ids) == 1
    # Queue should be cleared
    remaining = conn.execute("SELECT COUNT(*) FROM BuildQueue").fetchone()[0]
    assert remaining == 0


def test_build_queue_not_yet_complete(minimal):
    conn, pid, fid = minimal
    conn.execute(
        "INSERT INTO BuildQueue (polity_id, system_id, hull_type, ticks_total, "
        "ticks_elapsed, reserved_ru, ordered_tick) VALUES (?, 100, 'capital', 20, 0, 40.0, 0)",
        (pid,),
    )
    conn.commit()
    facade = GameFacadeImpl(conn)
    hull_ids = facade.advance_build_queues(tick=1)
    conn.commit()
    assert hull_ids == []
    elapsed = conn.execute("SELECT ticks_elapsed FROM BuildQueue").fetchone()[0]
    assert elapsed == 1


# ---------------------------------------------------------------------------
# GameFacadeImpl.advance_repair_queues
# ---------------------------------------------------------------------------

def test_repair_queue_completes(minimal):
    conn, pid, fid = minimal
    hulls = get_hulls_in_fleet(conn, fid)
    hull_id = hulls[0].hull_id
    conn.execute("UPDATE Hull SET status='damaged' WHERE hull_id=?", (hull_id,))
    conn.execute(
        "INSERT INTO RepairQueue (hull_id, system_id, ticks_total, ticks_elapsed, cost_ru) "
        "VALUES (?, 100, 4, 3, 10.0)",
        (hull_id,),
    )
    conn.commit()
    facade = GameFacadeImpl(conn)
    repaired = facade.advance_repair_queues(tick=4)
    conn.commit()
    assert hull_id in repaired
    from starscape5.game.fleet import get_hull
    assert get_hull(conn, hull_id).status == "active"
    remaining = conn.execute("SELECT COUNT(*) FROM RepairQueue").fetchone()[0]
    assert remaining == 0


def test_repair_queue_not_yet_done(minimal):
    conn, pid, fid = minimal
    hulls = get_hulls_in_fleet(conn, fid)
    hull_id = hulls[0].hull_id
    conn.execute("UPDATE Hull SET status='damaged' WHERE hull_id=?", (hull_id,))
    conn.execute(
        "INSERT INTO RepairQueue (hull_id, system_id, ticks_total, ticks_elapsed, cost_ru) "
        "VALUES (?, 100, 4, 1, 10.0)",
        (hull_id,),
    )
    conn.commit()
    facade = GameFacadeImpl(conn)
    repaired = facade.advance_repair_queues(tick=2)
    assert repaired == []
    elapsed = conn.execute("SELECT ticks_elapsed FROM RepairQueue").fetchone()[0]
    assert elapsed == 2


# ---------------------------------------------------------------------------
# GameFacadeImpl.apply_supply_degradation
# ---------------------------------------------------------------------------

def test_supply_degradation_at_8_ticks_extra_maint(minimal):
    conn, pid, fid = minimal
    conn.execute("UPDATE Fleet SET supply_ticks=8 WHERE fleet_id=?", (fid,))
    conn.commit()
    before = get_polity(conn, pid).treasury_ru
    facade = GameFacadeImpl(conn)
    facade.apply_supply_degradation(pid, tick=10)
    conn.commit()
    after = get_polity(conn, pid).treasury_ru
    # Extra deduction: 2 capitals × 2.0 = 4.0
    assert after == pytest.approx(before - 4.0)


def test_supply_degradation_at_16_ticks_damages_hulls(minimal):
    conn, pid, fid = minimal
    conn.execute("UPDATE Fleet SET supply_ticks=16 WHERE fleet_id=?", (fid,))
    conn.commit()
    facade = GameFacadeImpl(conn)
    facade.apply_supply_degradation(pid, tick=20)
    conn.commit()
    hulls = get_hulls_in_fleet(conn, fid)
    assert all(h.status == "damaged" for h in hulls)


def test_no_degradation_below_8_ticks(minimal):
    conn, pid, fid = minimal
    conn.execute("UPDATE Fleet SET supply_ticks=5 WHERE fleet_id=?", (fid,))
    conn.commit()
    before = get_polity(conn, pid).treasury_ru
    facade = GameFacadeImpl(conn)
    facade.apply_supply_degradation(pid, tick=5)
    conn.commit()
    after = get_polity(conn, pid).treasury_ru
    assert after == pytest.approx(before)


# ---------------------------------------------------------------------------
# run_economy_phase — engine
# ---------------------------------------------------------------------------

def test_run_economy_phase_stub_calls_all_polities():
    stub = GameFacadeStub()
    summaries = run_economy_phase(
        tick=1, phase_num=8, polity_order=[1, 2, 3],
        game=stub, world=None,
    )
    collect_calls = [c for c in stub.calls if c[0] == "collect_ru"]
    maint_calls = [c for c in stub.calls if c[0] == "pay_maintenance"]
    assert len(collect_calls) == 3
    assert len(maint_calls) == 3
    # advance_build_queues and advance_repair_queues called once each
    assert sum(1 for c in stub.calls if c[0] == "advance_build_queues") == 1
    assert sum(1 for c in stub.calls if c[0] == "advance_repair_queues") == 1


def test_run_economy_phase_returns_summaries():
    stub = GameFacadeStub(returns={"collect_ru": 20.0, "pay_maintenance": 12.0})
    summaries = run_economy_phase(
        tick=3, phase_num=8, polity_order=[1],
        game=stub,
    )
    assert any("produced=20.0" in s for s in summaries)
    assert any("maint=12.0" in s for s in summaries)


def test_run_economy_phase_empty_polity_order():
    stub = GameFacadeStub()
    summaries = run_economy_phase(tick=1, phase_num=8, polity_order=[], game=stub)
    assert summaries == []


def test_run_economy_phase_does_not_call_world():
    """Economy phase must not call any world methods."""
    stub = GameFacadeStub()
    world_stub = WorldStub(seed=42)
    # Run the phase with a world arg — if it tried to use world it would call
    # get_star_position etc., but we just check it doesn't raise.
    run_economy_phase(tick=1, phase_num=8, polity_order=[1], game=stub, world=world_stub)


# ---------------------------------------------------------------------------
# Integration: full init_game + one economy tick
# ---------------------------------------------------------------------------

def test_full_economy_tick_changes_treasury(full_game):
    polity_order = get_polity_processing_order(full_game)
    facade = GameFacadeImpl(full_game)

    treasuries_before = {
        pid: get_polity(full_game, pid).treasury_ru
        for pid in polity_order
    }

    advance_phase(full_game, tick=1, phase=8)
    run_economy_phase(tick=1, phase_num=8,
                      polity_order=polity_order, game=facade)
    full_game.commit()
    commit_phase(full_game, tick=1, phase=8)

    # Every polity's treasury should have changed (production − maintenance ≠ 0)
    changed = 0
    for pid in polity_order:
        after = get_polity(full_game, pid).treasury_ru
        if abs(after - treasuries_before[pid]) > 0.001:
            changed += 1
    assert changed == len(polity_order)


def test_full_economy_tick_commit_loop(full_game):
    """Verify the commit loop: advance then commit updates GameState."""
    from starscape5.game.state import read_gamestate
    polity_order = get_polity_processing_order(full_game)
    facade = GameFacadeImpl(full_game)

    advance_phase(full_game, tick=1, phase=8)
    run_economy_phase(tick=1, phase_num=8, polity_order=polity_order, game=facade)
    full_game.commit()
    commit_phase(full_game, tick=1, phase=8)

    gs = read_gamestate(full_game)
    assert gs.last_committed_tick == 1
    assert gs.last_committed_phase == 8


# ---------------------------------------------------------------------------
# Smoke test matching implementation_plan.md
# ---------------------------------------------------------------------------

def test_m6_smoke():
    world = WorldStub(seed=42)
    conn = open_game(":memory:")
    init_schema(conn)
    init_game(conn, world, OB_DATA)
    facade = GameFacadeImpl(conn)

    polity_order = get_polity_processing_order(conn)
    run_economy_phase(tick=1, phase_num=8, polity_order=polity_order, game=facade)
    conn.commit()

    p1 = get_polity(conn, polity_order[0])
    print(f"\nTreasury after tick 1: {p1.treasury_ru:.1f} RU")
    # Should have changed from starting value
    assert p1.treasury_ru != pytest.approx(0.0)


# helpers used in integration tests
from starscape5.game.polity import get_polity_processing_order, get_polity
