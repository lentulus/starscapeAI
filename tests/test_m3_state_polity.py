"""M3 smoke tests — GameState and Polity."""

import sqlite3
import time
import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.state import (
    GameState,
    advance_phase,
    commit_phase,
    create_gamestate,
    read_gamestate,
)
from starscape5.game.polity import (
    PolityRow,
    create_polity,
    get_active_polities,
    get_all_polities,
    get_polity,
    get_polity_processing_order,
    set_polity_status,
    update_treasury,
)


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
def seeded_conn(conn):
    """DB with gamestate + two polities."""
    create_gamestate(conn)
    create_polity(conn, species_id=11, name="Humanity Alpha",
                  capital_system_id=100, expansionism=0.5,
                  aggression=0.4, risk_appetite=0.5, processing_order=1)
    create_polity(conn, species_id=1, name="Kreeth Dominion",
                  capital_system_id=200, expansionism=0.7,
                  aggression=0.8, risk_appetite=0.6, processing_order=2)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

def test_create_gamestate(conn):
    create_gamestate(conn)
    gs = read_gamestate(conn)
    assert isinstance(gs, GameState)
    assert gs.current_tick == 0
    assert gs.current_phase == 0
    assert gs.last_committed_tick == 0
    assert gs.last_committed_phase == 0


def test_create_gamestate_with_tick(conn):
    create_gamestate(conn, tick=5)
    gs = read_gamestate(conn)
    assert gs.current_tick == 5
    assert gs.last_committed_tick == 5


def test_create_gamestate_twice_raises(conn):
    create_gamestate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        create_gamestate(conn)


def test_read_gamestate_missing_raises(conn):
    with pytest.raises(RuntimeError, match="GameState row not found"):
        read_gamestate(conn)


def test_advance_phase_updates_current(conn):
    create_gamestate(conn)
    advance_phase(conn, tick=1, phase=3)
    gs = read_gamestate(conn)
    assert gs.current_tick == 1
    assert gs.current_phase == 3
    # last_committed must NOT have advanced yet
    assert gs.last_committed_tick == 0
    assert gs.last_committed_phase == 0


def test_commit_phase_updates_committed(conn):
    create_gamestate(conn)
    advance_phase(conn, tick=1, phase=3)
    commit_phase(conn, tick=1, phase=3)
    gs = read_gamestate(conn)
    assert gs.last_committed_tick == 1
    assert gs.last_committed_phase == 3


def test_commit_phase_updates_timestamp(conn):
    create_gamestate(conn)
    gs_before = read_gamestate(conn)
    time.sleep(0.01)
    commit_phase(conn, tick=1, phase=1)
    gs_after = read_gamestate(conn)
    assert gs_after.last_committed_at > gs_before.last_committed_at


def test_advance_does_not_update_committed(conn):
    """Crash-safety: advance changes current_* but not last_committed_*."""
    create_gamestate(conn)
    commit_phase(conn, tick=1, phase=9)   # end of tick 1
    advance_phase(conn, tick=2, phase=4)  # mid-tick 2
    gs = read_gamestate(conn)
    assert gs.current_tick == 2
    assert gs.current_phase == 4
    assert gs.last_committed_tick == 1    # still tick 1
    assert gs.last_committed_phase == 9


def test_full_tick_commit_sequence(conn):
    create_gamestate(conn)
    for phase in range(1, 10):
        advance_phase(conn, tick=1, phase=phase)
        commit_phase(conn, tick=1, phase=phase)
    gs = read_gamestate(conn)
    assert gs.last_committed_tick == 1
    assert gs.last_committed_phase == 9


# ---------------------------------------------------------------------------
# Polity — create and read
# ---------------------------------------------------------------------------

def test_create_polity_returns_id(conn):
    create_gamestate(conn)
    pid = create_polity(conn, species_id=11, name="Humanity Alpha",
                        capital_system_id=100, expansionism=0.5,
                        aggression=0.4, risk_appetite=0.5,
                        processing_order=1)
    assert isinstance(pid, int)
    assert pid >= 1


def test_get_polity_roundtrip(seeded_conn):
    polities = get_all_polities(seeded_conn)
    assert len(polities) == 2
    p = get_polity(seeded_conn, polities[0].polity_id)
    assert isinstance(p, PolityRow)
    assert p.name == polities[0].name


def test_get_polity_not_found_raises(seeded_conn):
    with pytest.raises(KeyError):
        get_polity(seeded_conn, 9999)


def test_get_all_polities_ordered(seeded_conn):
    polities = get_all_polities(seeded_conn)
    orders = [p.processing_order for p in polities]
    assert orders == sorted(orders)


def test_polity_fields(seeded_conn):
    p = get_all_polities(seeded_conn)[0]
    assert p.species_id == 11
    assert p.name == "Humanity Alpha"
    assert p.capital_system_id == 100
    assert p.expansionism == pytest.approx(0.5)
    assert p.aggression == pytest.approx(0.4)
    assert p.risk_appetite == pytest.approx(0.5)
    assert p.treasury_ru == pytest.approx(0.0)
    assert p.status == "active"
    assert p.founded_tick == 0


# ---------------------------------------------------------------------------
# Polity — updates
# ---------------------------------------------------------------------------

def test_update_treasury_positive(seeded_conn):
    pid = get_all_polities(seeded_conn)[0].polity_id
    update_treasury(seeded_conn, pid, 25.0)
    seeded_conn.commit()
    assert get_polity(seeded_conn, pid).treasury_ru == pytest.approx(25.0)


def test_update_treasury_negative(seeded_conn):
    pid = get_all_polities(seeded_conn)[0].polity_id
    update_treasury(seeded_conn, pid, 100.0)
    update_treasury(seeded_conn, pid, -30.0)
    seeded_conn.commit()
    assert get_polity(seeded_conn, pid).treasury_ru == pytest.approx(70.0)


def test_update_treasury_accumulates(seeded_conn):
    pid = get_all_polities(seeded_conn)[0].polity_id
    update_treasury(seeded_conn, pid, 10.0)
    update_treasury(seeded_conn, pid, 5.5)
    seeded_conn.commit()
    assert get_polity(seeded_conn, pid).treasury_ru == pytest.approx(15.5)


def test_set_polity_status_eliminated(seeded_conn):
    pid = get_all_polities(seeded_conn)[0].polity_id
    set_polity_status(seeded_conn, pid, "eliminated")
    seeded_conn.commit()
    assert get_polity(seeded_conn, pid).status == "eliminated"


def test_get_active_polities_excludes_eliminated(seeded_conn):
    pid = get_all_polities(seeded_conn)[0].polity_id
    set_polity_status(seeded_conn, pid, "eliminated")
    seeded_conn.commit()
    active = get_active_polities(seeded_conn)
    assert all(p.polity_id != pid for p in active)
    assert len(active) == 1


def test_get_polity_processing_order(seeded_conn):
    order = get_polity_processing_order(seeded_conn)
    assert len(order) == 2
    assert all(isinstance(pid, int) for pid in order)


# ---------------------------------------------------------------------------
# Smoke test matching implementation_plan.md
# ---------------------------------------------------------------------------

def test_m3_smoke(conn):
    create_gamestate(conn)
    create_polity(conn, species_id=11, name="Humanity Alpha",
                  capital_system_id=100, expansionism=0.5,
                  aggression=0.4, risk_appetite=0.5, processing_order=1)
    create_polity(conn, species_id=1, name="Kreeth Dominion",
                  capital_system_id=200, expansionism=0.7,
                  aggression=0.8, risk_appetite=0.6, processing_order=2)
    conn.commit()

    gs = read_gamestate(conn)
    polities = get_all_polities(conn)
    names = [p.name for p in polities]
    print(f"\nTick {gs.current_tick}: {names}")

    assert gs.current_tick == 0
    assert "Humanity Alpha" in names
    assert "Kreeth Dominion" in names
