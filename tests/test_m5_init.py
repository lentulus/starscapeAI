"""M5 tests — SystemPresence, Economy helpers, Events, and init_game."""

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.polity import create_polity, get_all_polities, get_active_polities
from starscape5.game.state import create_gamestate, read_gamestate
from starscape5.world.stub import WorldStub
from starscape5.game.init_game import init_game
from starscape5.game.ob_data import OB_DATA
from starscape5.game.presence import (
    PresenceRow,
    advance_control_state,
    advance_development,
    create_presence,
    get_presence,
    get_presences_by_polity,
    get_presences_in_system,
    set_contested,
    transfer_control,
    record_colonist_delivery,
)
from starscape5.game.economy import (
    compute_ru_production,
    create_world_potential_cache,
    get_world_potential,
    get_best_body_in_system,
)
from starscape5.game.events import (
    EventRow,
    write_event,
    get_events,
    get_recent_events,
)
from starscape5.game.fleet import get_hulls_in_fleet, get_fleets_by_polity
from starscape5.game.constants import HULL_STATS, GROUND_STATS
from starscape5.game.ground import get_ground_forces_by_polity


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
def polity_conn(conn):
    create_gamestate(conn)
    pid = create_polity(conn, species_id=1, name="Kreeth",
                        capital_system_id=100, expansionism=0.7,
                        aggression=0.8, risk_appetite=0.6, processing_order=1)
    conn.commit()
    return conn, pid


@pytest.fixture
def world():
    return WorldStub(seed=42)


@pytest.fixture
def game_conn(world):
    c = open_game(":memory:")
    init_schema(c)
    init_game(c, world, OB_DATA)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# SystemPresence
# ---------------------------------------------------------------------------

def test_create_presence(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, system_id=100, body_id=1001,
                               control_state="controlled", development_level=3,
                               established_tick=0)
    conn.commit()
    p = get_presence(conn, pres_id)
    assert p.control_state == "controlled"
    assert p.development_level == 3
    assert p.polity_id == pid


def test_advance_control_state_outpost_to_colony(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "outpost", 0, 0)
    conn.commit()
    new_state = advance_control_state(conn, pres_id, tick=5)
    conn.commit()
    assert new_state == "colony"
    assert get_presence(conn, pres_id).control_state == "colony"


def test_advance_control_state_colony_to_controlled(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "colony", 1, 0)
    advance_control_state(conn, pres_id, tick=5)
    conn.commit()
    assert get_presence(conn, pres_id).control_state == "controlled"


def test_advance_control_state_controlled_stays(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    result = advance_control_state(conn, pres_id, tick=5)
    assert result == "controlled"


def test_advance_development_capped_by_outpost(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "outpost", 1, 0)
    result = advance_development(conn, pres_id, tick=1)
    assert result == 1   # already at cap for outpost


def test_advance_development_colony_cap_3(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "colony", 2, 0)
    result = advance_development(conn, pres_id, tick=1)
    assert result == 3
    result2 = advance_development(conn, pres_id, tick=2)
    assert result2 == 3   # capped


def test_set_contested(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    set_contested(conn, pres_id, tick=10)
    conn.commit()
    assert get_presence(conn, pres_id).control_state == "contested"


def test_transfer_control(polity_conn):
    conn, pid = polity_conn
    pid2 = create_polity(conn, species_id=11, name="Human",
                         capital_system_id=200, expansionism=0.5,
                         aggression=0.4, risk_appetite=0.5, processing_order=2)
    pres_id = create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    transfer_control(conn, pres_id, pid2, tick=20)
    conn.commit()
    p = get_presence(conn, pres_id)
    assert p.polity_id == pid2
    assert p.control_state == "controlled"


def test_record_colonist_delivery(polity_conn):
    conn, pid = polity_conn
    pres_id = create_presence(conn, pid, 100, 1001, "outpost", 0, 0)
    record_colonist_delivery(conn, pres_id, tick=3)
    record_colonist_delivery(conn, pres_id, tick=4)
    conn.commit()
    assert get_presence(conn, pres_id).colonist_deliveries == 2


def test_get_presences_in_system(polity_conn):
    conn, pid = polity_conn
    create_presence(conn, pid, 100, 1001, "controlled", 3, 0)
    create_presence(conn, pid, 100, 1002, "outpost", 0, 0)
    create_presence(conn, pid, 999, 9991, "outpost", 0, 0)
    conn.commit()
    presences = get_presences_in_system(conn, 100)
    assert len(presences) == 2
    assert all(p.system_id == 100 for p in presences)


# ---------------------------------------------------------------------------
# Economy — pure functions
# ---------------------------------------------------------------------------

def test_compute_ru_prime_world():
    # potential=25, controlled, dev-5: 25 * 1.0 * 1.5 = 37.5
    assert compute_ru_production(25, "controlled", 5) == pytest.approx(37.5)


def test_compute_ru_new_outpost():
    # potential=25, outpost, dev-0: 25 * 0.1 * 0.5 = 1.25
    assert compute_ru_production(25, "outpost", 0) == pytest.approx(1.25)


def test_compute_ru_homeworld_dev3():
    # potential=20, controlled, dev-3: 20 * 1.0 * 1.0 = 20
    assert compute_ru_production(20, "controlled", 3) == pytest.approx(20.0)


def test_compute_ru_colony_dev2():
    assert compute_ru_production(15, "colony", 2) == pytest.approx(15 * 0.4 * 0.9)


def test_compute_ru_contested_penalised():
    normal = compute_ru_production(20, "controlled", 3)
    contested = compute_ru_production(20, "contested", 3)
    assert contested < normal


# ---------------------------------------------------------------------------
# Economy — WorldPotential cache
# ---------------------------------------------------------------------------

def test_world_potential_cache_roundtrip(conn):
    create_world_potential_cache(conn, body_id=1001, system_id=100,
                                 world_potential=20, has_gas_giant=1, has_ocean=0)
    conn.commit()
    assert get_world_potential(conn, 1001) == 20


def test_world_potential_upsert(conn):
    create_world_potential_cache(conn, 1001, 100, 20, 0, 0)
    create_world_potential_cache(conn, 1001, 100, 25, 1, 0)  # update
    conn.commit()
    assert get_world_potential(conn, 1001) == 25


def test_world_potential_missing_returns_none(conn):
    assert get_world_potential(conn, 9999) is None


def test_get_best_body_in_system(conn):
    create_world_potential_cache(conn, 1001, 100, 15, 0, 0)
    create_world_potential_cache(conn, 1002, 100, 25, 0, 1)
    create_world_potential_cache(conn, 1003, 100, 10, 1, 0)
    conn.commit()
    assert get_best_body_in_system(conn, 100) == 1002


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _make_polities(conn, n=3):
    """Create n polities and return their IDs."""
    ids = []
    for i in range(n):
        pid = create_polity(conn, species_id=1, name=f"Polity {i+1}",
                            capital_system_id=100+i, expansionism=0.5,
                            aggression=0.5, risk_appetite=0.5,
                            processing_order=i+1)
        ids.append(pid)
    conn.commit()
    return ids


def test_write_and_read_event(conn):
    create_gamestate(conn)
    pids = _make_polities(conn, 2)
    eid = write_event(conn, tick=1, phase=3, event_type="combat",
                      summary="Battle at system 100",
                      polity_a_id=pids[0], polity_b_id=pids[1], system_id=100)
    conn.commit()
    events = get_events(conn, tick=1)
    assert len(events) == 1
    assert events[0].event_id == eid
    assert events[0].event_type == "combat"
    assert events[0].system_id == 100


def test_get_events_filter_type(conn):
    create_gamestate(conn)
    pids = _make_polities(conn, 2)
    write_event(conn, 1, 1, "contact", "First contact",
                polity_a_id=pids[0], polity_b_id=pids[1])
    write_event(conn, 1, 4, "combat", "Battle",
                polity_a_id=pids[0], polity_b_id=pids[1])
    conn.commit()
    contacts = get_events(conn, event_type="contact")
    assert len(contacts) == 1
    assert contacts[0].event_type == "contact"


def test_get_events_filter_polity(conn):
    create_gamestate(conn)
    pids = _make_polities(conn, 3)
    write_event(conn, 1, 1, "contact", "A meets B",
                polity_a_id=pids[0], polity_b_id=pids[1])
    write_event(conn, 1, 1, "contact", "B meets C",
                polity_a_id=pids[1], polity_b_id=pids[2])
    write_event(conn, 1, 1, "contact", "A meets C",
                polity_a_id=pids[0], polity_b_id=pids[2])
    conn.commit()
    polity1_events = get_events(conn, polity_id=pids[0])
    assert len(polity1_events) == 2


def test_get_recent_events(conn):
    create_gamestate(conn)
    for i in range(5):
        write_event(conn, tick=i, phase=1, event_type="summary", summary=f"tick {i}")
    conn.commit()
    recent = get_recent_events(conn, n=3)
    assert len(recent) == 3
    assert recent[-1].tick == 4  # most recent last


# ---------------------------------------------------------------------------
# init_game — full initialisation
# ---------------------------------------------------------------------------

def test_polity_count(game_conn):
    # 8 single-polity species + 3 Nhaveth + 3 Human = 14... but Nhaveth=3, Human=3
    # OB_DATA has: 8 single + nhaveth(3) + human(3) = 14
    polities = get_all_polities(game_conn)
    # 8 single-polity + 3 Nhaveth + 3 Human = 14; but let's count from OB_DATA
    expected = sum(len(e["polities"]) for e in OB_DATA)
    assert len(polities) == expected


def test_all_polities_have_homeworld_presence(game_conn):
    polities = get_all_polities(game_conn)
    for p in polities:
        presences = get_presences_by_polity(game_conn, p.polity_id)
        assert len(presences) >= 1, f"{p.name} has no presence"
        assert any(pr.control_state == "controlled" for pr in presences), \
            f"{p.name} has no controlled world"


def test_all_polities_have_fleets(game_conn):
    polities = get_all_polities(game_conn)
    for p in polities:
        fleets = get_fleets_by_polity(game_conn, p.polity_id)
        assert len(fleets) >= 1, f"{p.name} has no fleet"


def test_all_polities_have_hulls(game_conn):
    polities = get_all_polities(game_conn)
    for p in polities:
        fleets = get_fleets_by_polity(game_conn, p.polity_id)
        hulls = []
        for f in fleets:
            hulls.extend(get_hulls_in_fleet(game_conn, f.fleet_id))
        assert len(hulls) >= 1, f"{p.name} has no hulls"


def test_all_polities_have_admirals(game_conn):
    from starscape5.game.admiral import get_fleet_admiral
    polities = get_all_polities(game_conn)
    for p in polities:
        fleets = get_fleets_by_polity(game_conn, p.polity_id)
        has_admiral = any(get_fleet_admiral(game_conn, f.fleet_id) is not None
                          for f in fleets)
        assert has_admiral, f"{p.name} has no admiral"


def test_all_polities_have_ground_forces(game_conn):
    polities = get_all_polities(game_conn)
    for p in polities:
        forces = get_ground_forces_by_polity(game_conn, p.polity_id)
        assert len(forces) >= 1, f"{p.name} has no ground forces"


def test_world_potential_cache_populated(game_conn):
    rows = game_conn.execute("SELECT COUNT(*) FROM WorldPotential").fetchone()[0]
    assert rows > 0


def test_tick_zero_events_written(game_conn):
    events = get_events(game_conn, tick=0)
    assert len(events) >= len([e for e in OB_DATA for _ in e["polities"]])


def test_kreeth_capital_heavy(game_conn):
    """Kreeth should have 2 capitals per OB."""
    polities = get_all_polities(game_conn)
    kreeth = next(p for p in polities if "Kreeth" in p.name)
    fleets = get_fleets_by_polity(game_conn, kreeth.polity_id)
    all_hulls = [h for f in fleets for h in get_hulls_in_fleet(game_conn, f.fleet_id)]
    capitals = [h for h in all_hulls if h.hull_type == "capital"]
    assert len(capitals) == 2


def test_golvhaan_no_capitals(game_conn):
    """Golvhaan starts with no Capitals per OB."""
    polities = get_all_polities(game_conn)
    golvhaan = next(p for p in polities if "Golvhaan" in p.name)
    fleets = get_fleets_by_polity(game_conn, golvhaan.polity_id)
    all_hulls = [h for f in fleets for h in get_hulls_in_fleet(game_conn, f.fleet_id)]
    capitals = [h for h in all_hulls if h.hull_type == "capital"]
    assert len(capitals) == 0


def test_nhaveth_three_polities(game_conn):
    polities = get_all_polities(game_conn)
    nhaveth = [p for p in polities if "Nhaveth" in p.name]
    assert len(nhaveth) == 3


def test_human_three_polities(game_conn):
    polities = get_all_polities(game_conn)
    humans = [p for p in polities if "Human" in p.name]
    assert len(humans) == 3


def test_processing_order_unique(game_conn):
    polities = get_all_polities(game_conn)
    orders = [p.processing_order for p in polities]
    assert len(orders) == len(set(orders)), "Duplicate processing_order values"


# ---------------------------------------------------------------------------
# Smoke test matching implementation_plan.md
# ---------------------------------------------------------------------------

def test_m5_smoke(world):
    conn = open_game(":memory:")
    init_schema(conn)
    init_game(conn, world, OB_DATA)

    polities = get_all_polities(conn)
    all_hulls = []
    for p in polities:
        for f in get_fleets_by_polity(conn, p.polity_id):
            all_hulls.extend(get_hulls_in_fleet(conn, f.fleet_id))
    events = get_events(conn, tick=0)

    print(f"\n{len(polities)} polities, {len(all_hulls)} hulls, "
          f"{len(events)} tick-0 events")

    assert len(polities) >= 13   # 8 single + 3 Nhaveth + 3 Human
    assert len(all_hulls) > 50
    assert len(events) >= len(polities)
