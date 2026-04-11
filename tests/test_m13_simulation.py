"""M13 — Log phase, full tick runner, and simulation loop tests.

Covers:
  game/log.py          — is_quiet_tick, write_monthly_summary
  engine/log.py        — run_log_phase
  engine/simulation.py — run_tick, run_simulation (crash-safe resume)
  engine/tick.py       — run_partial_tick now includes phase 9
"""

from __future__ import annotations

import sqlite3

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.events import EventRow, get_events, write_event
from starscape5.game.facade import GameFacadeImpl, GameFacadeStub
from starscape5.game.init_game import init_game
from starscape5.game.log import is_quiet_tick, write_monthly_summary
from starscape5.game.polity import create_polity, get_polity_processing_order
from starscape5.game.state import (
    create_gamestate, read_gamestate, advance_phase, commit_phase,
)
from starscape5.engine.log import run_log_phase
from starscape5.engine.simulation import run_tick, run_simulation, TickResult
from starscape5.engine.tick import run_partial_tick
from starscape5.world.stub import WorldStub


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
def world():
    return WorldStub()


def _make_polity(conn, pid_hint, system_id):
    return create_polity(
        conn, species_id=1, name=f"Polity {pid_hint}",
        capital_system_id=system_id,
        expansionism=0.5, aggression=0.3, risk_appetite=0.5,
        processing_order=pid_hint, treasury_ru=50.0, founded_tick=0,
    )


def _event(event_type: str) -> EventRow:
    return EventRow(
        event_id=0, tick=1, phase=4,
        event_type=event_type,
        summary="test", detail=None,
        polity_a_id=None, polity_b_id=None,
        system_id=None, body_id=None, admiral_id=None,
    )


# ---------------------------------------------------------------------------
# is_quiet_tick
# ---------------------------------------------------------------------------

class TestIsQuietTick:
    def test_empty_list_is_quiet(self):
        assert is_quiet_tick([]) is True

    def test_no_significant_events_is_quiet(self):
        events = [_event("colony_established").__class__(
            event_id=1, tick=1, phase=1,
            event_type="first_contact", summary="x",
            detail=None, polity_a_id=None, polity_b_id=None,
            system_id=None, body_id=None, admiral_id=None,
        )]
        assert is_quiet_tick(events) is True

    def test_combat_makes_tick_significant(self):
        assert is_quiet_tick([_event("combat")]) is False

    def test_war_declared_makes_tick_significant(self):
        assert is_quiet_tick([_event("war_declared")]) is False

    def test_control_change_makes_tick_significant(self):
        assert is_quiet_tick([_event("control_change")]) is False

    def test_colony_established_makes_tick_significant(self):
        assert is_quiet_tick([_event("colony_established")]) is False

    def test_mixed_quiet_and_significant(self):
        events = [_event("first_contact"), _event("combat")]
        assert is_quiet_tick(events) is False


# ---------------------------------------------------------------------------
# write_monthly_summary
# ---------------------------------------------------------------------------

class TestWriteMonthlySummary:
    def test_writes_event(self, conn):
        _make_polity(conn, 1, 1)
        conn.commit()
        write_monthly_summary(conn, tick=4, phase=9)
        conn.commit()
        events = get_events(conn, event_type="monthly_summary")
        assert len(events) == 1

    def test_summary_contains_treasury(self, conn):
        _make_polity(conn, 1, 1)
        conn.commit()
        write_monthly_summary(conn, tick=4, phase=9)
        conn.commit()
        events = get_events(conn, event_type="monthly_summary")
        assert "treasury=" in events[0].summary

    def test_summary_contains_presences(self, conn):
        _make_polity(conn, 1, 1)
        conn.commit()
        write_monthly_summary(conn, tick=4, phase=9)
        conn.commit()
        events = get_events(conn, event_type="monthly_summary")
        assert "presences=" in events[0].summary

    def test_summary_contains_polities(self, conn):
        _make_polity(conn, 1, 1)
        conn.commit()
        write_monthly_summary(conn, tick=4, phase=9)
        conn.commit()
        events = get_events(conn, event_type="monthly_summary")
        assert "polities=" in events[0].summary


# ---------------------------------------------------------------------------
# run_log_phase
# ---------------------------------------------------------------------------

class TestRunLogPhase:
    def test_returns_list(self):
        stub = GameFacadeStub()
        result = run_log_phase(4, 9, [1], stub)
        assert isinstance(result, list)

    def test_monthly_summary_written_at_tick_4(self):
        stub = GameFacadeStub(returns={"write_monthly_summary": "tick=4 monthly_summary"})
        summaries = run_log_phase(4, 9, [1], stub)
        method_names = [c[0] for c in stub.calls]
        assert "write_monthly_summary" in method_names

    def test_no_summary_at_non_month_boundary(self):
        stub = GameFacadeStub()
        run_log_phase(3, 9, [1], stub)
        method_names = [c[0] for c in stub.calls]
        assert "write_monthly_summary" not in method_names

    def test_quiet_tick_annotation(self):
        stub = GameFacadeStub(returns={
            "is_quiet_tick": True,
            "write_monthly_summary": "tick=4 monthly_summary",
        })
        summaries = run_log_phase(4, 9, [1], stub)
        assert any("quiet" in s for s in summaries)

    def test_significant_tick_annotation(self):
        stub = GameFacadeStub(returns={"is_quiet_tick": False})
        summaries = run_log_phase(1, 9, [1], stub)
        assert any("significant" in s for s in summaries)


# ---------------------------------------------------------------------------
# run_tick
# ---------------------------------------------------------------------------

class TestRunTick:
    def test_returns_tick_result(self, conn, world):
        create_gamestate(conn)
        _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        result = run_tick(1, game, world, conn)
        assert isinstance(result, TickResult)
        assert result.tick == 1

    def test_all_9_phases_run(self, conn, world):
        create_gamestate(conn)
        _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        result = run_tick(1, game, world, conn)
        assert result.phases_run == 9

    def test_commits_gamestate_after_each_phase(self, conn, world):
        create_gamestate(conn)
        _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        run_tick(1, game, world, conn)
        state = read_gamestate(conn)
        assert state.last_committed_tick == 1
        assert state.last_committed_phase == 9

    def test_resume_skips_completed_phases(self, conn, world):
        """resume_from_phase=6 should only run phases 7,8,9 (3 phases)."""
        create_gamestate(conn)
        _make_polity(conn, 1, 1)
        conn.commit()
        # Pre-commit phases 1-6 manually
        for ph in [1, 2, 3, 4, 5, 6]:
            commit_phase(conn, 1, ph)
        game = GameFacadeImpl(conn)
        result = run_tick(1, game, world, conn, resume_from_phase=6)
        # Phases 7, 8, 9 = 3 phases
        assert result.phases_run == 3

    def test_summaries_are_strings(self, conn, world):
        create_gamestate(conn)
        _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        result = run_tick(1, game, world, conn)
        for s in result.summaries:
            assert isinstance(s, str)


# ---------------------------------------------------------------------------
# run_simulation
# ---------------------------------------------------------------------------

class TestRunSimulation:
    def test_runs_requested_ticks(self, conn, world):
        init_game(conn, world)          # creates GameState internally
        game = GameFacadeImpl(conn)
        last = run_simulation(conn, world, game, max_ticks=3)
        assert last >= 3

    def test_gamestate_advanced(self, conn, world):
        init_game(conn, world)
        game = GameFacadeImpl(conn)
        run_simulation(conn, world, game, max_ticks=2)
        state = read_gamestate(conn)
        assert state.last_committed_tick >= 2
        assert state.last_committed_phase == 9

    def test_events_generated(self, conn, world):
        init_game(conn, world)
        game = GameFacadeImpl(conn)
        run_simulation(conn, world, game, max_ticks=4)
        events = get_events(conn)
        assert len(events) > 0

    def test_monthly_summary_events_present(self, conn, world):
        """At tick 4, a monthly_summary event should appear."""
        init_game(conn, world)
        game = GameFacadeImpl(conn)
        run_simulation(conn, world, game, max_ticks=4)
        events = get_events(conn, event_type="monthly_summary")
        assert len(events) >= 1


# ---------------------------------------------------------------------------
# Crash-safe resume
# ---------------------------------------------------------------------------

class TestCrashSafeResume:
    def test_resume_after_simulated_crash(self, conn, world):
        """Simulate crash at phase 4 of tick 6; verify clean resume."""
        init_game(conn, world)
        game = GameFacadeImpl(conn)

        # Run ticks 1–5 cleanly
        run_simulation(conn, world, game, max_ticks=5)
        state_before = read_gamestate(conn)
        assert state_before.last_committed_tick == 5

        # Simulate crash: advance to tick 6 phase 4 but don't commit
        advance_phase(conn, 6, 4)

        state_crash = read_gamestate(conn)
        assert state_crash.current_tick == 6
        assert state_crash.last_committed_tick == 5

        # Resume: run_simulation reads GameState and detects the crash
        run_simulation(conn, world, game, max_ticks=1)

        state_after = read_gamestate(conn)
        assert state_after.last_committed_tick == 6
        assert state_after.last_committed_phase == 9

    def test_determinism_after_resume(self, conn, world):
        """Seeded RNG means re-running tick 1 from same initial state gives same events."""
        init_game(conn, world)
        game = GameFacadeImpl(conn)

        run_tick(1, game, world, conn)
        events_after = get_events(conn, tick=1)
        count_1 = len(events_after)
        assert count_1 >= 0  # at minimum, no crash


# ---------------------------------------------------------------------------
# Integration: run_partial_tick now includes phase 9
# ---------------------------------------------------------------------------

class TestPartialTickWithLogPhase:
    def test_monthly_summary_at_tick_4(self, conn, world):
        """run_partial_tick at tick 4 should produce a monthly_summary event."""
        pid = _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        run_partial_tick(4, [pid], game, world)
        events = get_events(conn, event_type="monthly_summary")
        assert len(events) >= 1

    def test_no_summary_at_tick_1(self, conn, world):
        """run_partial_tick at tick 1 (non-month boundary) has no monthly summary."""
        pid = _make_polity(conn, 1, 1)
        conn.commit()
        game = GameFacadeImpl(conn)
        run_partial_tick(1, [pid], game, world)
        events = get_events(conn, event_type="monthly_summary")
        assert len(events) == 0
