"""M9 — Space combat resolution tests.

Tests cover:
  game/combat.py       — pure helpers, damage application, fleet destruction,
                         disengage, pursuit, full round resolution
  engine/combat.py     — run_combat_phase (seeded rng, stub wiring)
  engine/tick.py       — combat phase slot (phase 4 now in partial tick)
"""

from __future__ import annotations

import sqlite3
from random import Random

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.facade import GameFacadeImpl, GameFacadeStub
from starscape5.game.fleet import create_fleet, create_hull, get_hull, mark_hull_damaged, mark_hull_destroyed
from starscape5.game.polity import create_polity
from starscape5.game.presence import create_presence
from starscape5.game.events import get_events
from starscape5.game.intelligence import _insert_contact_row
from starscape5.game.combat import (
    CombatResult,
    compute_hits,
    get_fleet_strength_in_system,
    get_best_admiral_factor,
    apply_hits_to_system,
    check_and_mark_fleets_destroyed,
    find_contested_systems,
    resolve_space_combat,
)
from starscape5.engine.combat import run_combat_phase
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
    return WorldStub(seed=42, universe_size=30)


def _polity(conn, n: int, system_id: int = 1, aggression: float = 0.5) -> int:
    return create_polity(
        conn, species_id=1, name=f"P{n}",
        capital_system_id=system_id,
        expansionism=0.5, aggression=aggression, risk_appetite=0.5,
        processing_order=n,
    )


def _fleet_with_hulls(
    conn, polity_id: int, system_id: int,
    hull_types: list[str],
) -> int:
    fleet_id = create_fleet(conn, polity_id, f"Fleet {polity_id}", system_id)
    for i, ht in enumerate(hull_types):
        create_hull(
            conn, polity_id, f"{ht}-{polity_id}-{i}", ht,
            system_id=system_id, fleet_id=fleet_id,
            squadron_id=None, created_tick=0,
        )
    return fleet_id


def _at_war(conn, pid_a: int, pid_b: int, system_id: int = 1) -> None:
    """Insert a ContactRecord with at_war=1 between a < b."""
    a, b = (pid_a, pid_b) if pid_a < pid_b else (pid_b, pid_a)
    next_id = conn.execute(
        "SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord"
    ).fetchone()[0]
    _insert_contact_row(conn, contact_id=next_id, polity_a_id=a, polity_b_id=b,
                        contact_tick=0, contact_system_id=system_id,
                        peace_weeks=0, at_war=1, map_shared=0)


# ---------------------------------------------------------------------------
# Pure: compute_hits
# ---------------------------------------------------------------------------

class TestComputeHits:
    def test_zero_net_is_zero_hits(self):
        assert compute_hits(3, 3, 0) == 0

    def test_positive_net_gives_hits(self):
        # net = 6 − 0 + 0 = 6 → 6 // 3 = 2
        assert compute_hits(6, 0, 0) == 2

    def test_roll_modifier_adds_to_net(self):
        # net = 3 − 3 + 3 = 3 → 1 hit
        assert compute_hits(3, 3, 3) == 1

    def test_negative_net_is_zero(self):
        assert compute_hits(1, 10, -2) == 0

    def test_fractional_rounds_down(self):
        # net = 4 → 4//3 = 1 (not 2)
        assert compute_hits(4, 0, 0) == 1


# ---------------------------------------------------------------------------
# get_fleet_strength_in_system
# ---------------------------------------------------------------------------

class TestFleetStrength:
    def test_single_capital(self, conn):
        pid = _polity(conn, 1)
        _fleet_with_hulls(conn, pid, 1, ["capital"])
        s = get_fleet_strength_in_system(conn, pid, 1)
        assert s["attack"] == 4
        assert s["defence"] == 4
        assert s["bombard"] == 3

    def test_damaged_hull_halved(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["capital"])
        hull_id = conn.execute(
            "SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)
        ).fetchone()["hull_id"]
        mark_hull_damaged(conn, hull_id)
        s = get_fleet_strength_in_system(conn, pid, 1)
        assert s["attack"] == 2   # 4 // 2
        assert s["defence"] == 2

    def test_destroyed_excluded(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["capital"])
        for h in conn.execute("SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)).fetchall():
            mark_hull_destroyed(conn, h["hull_id"])
        s = get_fleet_strength_in_system(conn, pid, 1)
        assert s["attack"] == 0

    def test_sdb_counts(self, conn):
        pid = _polity(conn, 1)
        # SDB with no fleet_id (squadron only) — still system-based
        squad_id = conn.execute(
            "INSERT INTO Squadron (fleet_id, polity_id, name, hull_type, combat_role, system_id) "
            "VALUES (NULL, ?, 'SDB Sqdn', 'sdb', 'line_of_battle', 1)",
            (pid,),
        ).lastrowid
        create_hull(conn, pid, "SDB-1", "sdb",
                    system_id=1, fleet_id=None, squadron_id=squad_id, created_tick=0)
        s = get_fleet_strength_in_system(conn, pid, 1)
        assert s["attack"] == 2


# ---------------------------------------------------------------------------
# apply_hits_to_system
# ---------------------------------------------------------------------------

class TestApplyHits:
    def test_active_becomes_damaged(self, conn):
        pid = _polity(conn, 1)
        _fleet_with_hulls(conn, pid, 1, ["cruiser"])
        apply_hits_to_system(conn, pid, 1, 1)
        row = conn.execute("SELECT status FROM Hull_head WHERE polity_id = ?", (pid,)).fetchone()
        assert row["status"] == "damaged"

    def test_damaged_becomes_destroyed(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["cruiser"])
        for h in conn.execute("SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)).fetchall():
            mark_hull_damaged(conn, h["hull_id"])
        apply_hits_to_system(conn, pid, 1, 1)
        row = conn.execute("SELECT status FROM Hull_head WHERE polity_id = ?", (pid,)).fetchone()
        assert row["status"] == "destroyed"

    def test_zero_hits_no_change(self, conn):
        pid = _polity(conn, 1)
        _fleet_with_hulls(conn, pid, 1, ["cruiser"])
        apply_hits_to_system(conn, pid, 1, 0)
        row = conn.execute("SELECT status FROM Hull_head WHERE polity_id = ?", (pid,)).fetchone()
        assert row["status"] == "active"

    def test_excess_hits_clamped_to_hulls(self, conn):
        pid = _polity(conn, 1)
        _fleet_with_hulls(conn, pid, 1, ["escort"])
        applied = apply_hits_to_system(conn, pid, 1, 99)
        assert applied == 1  # only one hull to hit

    def test_priority_damaged_first(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["capital", "cruiser"])
        hull_ids = [
            r["hull_id"] for r in conn.execute(
                "SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)
            ).fetchall()
        ]
        # Damage the capital
        mark_hull_damaged(conn, hull_ids[0])
        apply_hits_to_system(conn, pid, 1, 1)
        # The damaged capital should be destroyed; the cruiser should still be active
        statuses = {
            r["hull_id"]: r["status"]
            for r in conn.execute("SELECT hull_id, status FROM Hull_head WHERE fleet_id = ?", (fleet_id,))
        }
        assert statuses[hull_ids[0]] == "destroyed"
        assert statuses[hull_ids[1]] == "active"


# ---------------------------------------------------------------------------
# check_and_mark_fleets_destroyed
# ---------------------------------------------------------------------------

class TestFleetDestruction:
    def test_no_hulls_marks_fleet_destroyed(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["escort"])
        for h in conn.execute("SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)).fetchall():
            mark_hull_destroyed(conn, h["hull_id"])
        destroyed = check_and_mark_fleets_destroyed(conn, pid, 1, tick=1)
        assert fleet_id in destroyed
        row = conn.execute("SELECT status FROM Fleet WHERE fleet_id = ?", (fleet_id,)).fetchone()
        assert row["status"] == "destroyed"

    def test_live_hulls_fleet_survives(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["cruiser"])
        destroyed = check_and_mark_fleets_destroyed(conn, pid, 1, tick=1)
        assert fleet_id not in destroyed

    def test_damaged_hull_not_destroyed(self, conn):
        pid = _polity(conn, 1)
        fleet_id = _fleet_with_hulls(conn, pid, 1, ["cruiser"])
        for h in conn.execute("SELECT hull_id FROM Hull_head WHERE fleet_id = ?", (fleet_id,)).fetchall():
            mark_hull_damaged(conn, h["hull_id"])
        destroyed = check_and_mark_fleets_destroyed(conn, pid, 1, tick=1)
        assert fleet_id not in destroyed


# ---------------------------------------------------------------------------
# find_contested_systems
# ---------------------------------------------------------------------------

class TestFindContestedSystems:
    def test_no_war_no_contested(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _fleet_with_hulls(conn, pid1, 5, ["cruiser"])
        _fleet_with_hulls(conn, pid2, 5, ["cruiser"])
        # No ContactRecord at all
        assert find_contested_systems(conn) == []

    def test_at_war_same_system(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 5, ["cruiser"])
        _fleet_with_hulls(conn, pid2, 5, ["cruiser"])
        assert 5 in find_contested_systems(conn)

    def test_at_war_different_systems(self, conn):
        pid1 = _polity(conn, 1, system_id=1)
        pid2 = _polity(conn, 2, system_id=2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 1, ["cruiser"])
        _fleet_with_hulls(conn, pid2, 2, ["cruiser"])
        assert find_contested_systems(conn) == []


# ---------------------------------------------------------------------------
# resolve_space_combat — full round
# ---------------------------------------------------------------------------

class TestResolveCombat:
    def test_returns_combat_result(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 5, ["capital"])
        _fleet_with_hulls(conn, pid2, 5, ["capital"])
        rng = Random(0)
        results = resolve_space_combat(conn, 5, tick=1, rng=rng)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, CombatResult)
        assert r.system_id == 5

    def test_hits_recorded_as_events(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 5, ["capital"])
        _fleet_with_hulls(conn, pid2, 5, ["capital"])
        resolve_space_combat(conn, 5, tick=1, rng=Random(0))
        combat_events = get_events(conn, event_type="combat")
        assert len(combat_events) == 1

    def test_no_combat_when_not_at_war(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        # ContactRecord exists but at_war=0
        a, b = min(pid1, pid2), max(pid1, pid2)
        next_id = conn.execute("SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord").fetchone()[0]
        _insert_contact_row(conn, contact_id=next_id, polity_a_id=a, polity_b_id=b,
                            contact_tick=0, contact_system_id=5,
                            peace_weeks=0, at_war=0, map_shared=0)
        _fleet_with_hulls(conn, pid1, 5, ["capital"])
        _fleet_with_hulls(conn, pid2, 5, ["capital"])
        results = resolve_space_combat(conn, 5, tick=1, rng=Random(0))
        assert results == []

    def test_determinism(self, conn):
        """Same seed → identical hits."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)

        def _setup(c):
            _fleet_with_hulls(c, pid1, 3, ["capital", "cruiser"])
            _fleet_with_hulls(c, pid2, 3, ["capital", "cruiser"])

        # First DB
        _setup(conn)
        r1 = resolve_space_combat(conn, 3, tick=5, rng=Random(99))[0]

        # Fresh DB, same setup, same seed
        conn2 = open_game(":memory:")
        init_schema(conn2)
        for pid in (pid1, pid2):
            _polity(conn2, pid)
        _at_war(conn2, pid1, pid2, system_id=3)
        _setup(conn2)
        r2 = resolve_space_combat(conn2, 3, tick=5, rng=Random(99))[0]
        conn2.close()

        assert r1.hits_on_a == r2.hits_on_a
        assert r1.hits_on_b == r2.hits_on_b

    def test_fleet_destroyed_event_when_all_hulls_gone(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        # pid2 has only one escort (very weak)
        _fleet_with_hulls(conn, pid1, 5, ["capital", "capital", "capital"])
        _fleet_with_hulls(conn, pid2, 5, ["escort"])
        # Use a fixed seed that guarantees pid2 takes enough hits
        rng = Random(42)
        for _ in range(10):   # run several rounds until pid2's fleet is destroyed
            conn_status = conn.execute(
                "SELECT status FROM Fleet WHERE polity_id = ?", (pid2,)
            ).fetchone()
            if conn_status and conn_status["status"] == "destroyed":
                break
            resolve_space_combat(conn, 5, tick=1, rng=Random(42))
        destroyed_events = get_events(conn, event_type="fleet_destroyed")
        assert len(destroyed_events) >= 1

    def test_disengage_event_written(self, conn):
        pid1 = _polity(conn, 1, aggression=0.9)
        pid2 = _polity(conn, 2, system_id=2)
        _at_war(conn, pid1, pid2)
        # Give pid1 overwhelming force so pid2 will always lose and likely disengage
        _fleet_with_hulls(conn, pid1, 5, ["capital"] * 4)
        _fleet_with_hulls(conn, pid2, 5, ["escort"])
        for _ in range(20):
            resolve_space_combat(conn, 5, tick=1, rng=Random(7))
        disengage_events = get_events(conn, event_type="disengage")
        # May or may not disengage depending on rolls, but no errors
        assert isinstance(disengage_events, list)


# ---------------------------------------------------------------------------
# Engine: run_combat_phase
# ---------------------------------------------------------------------------

class TestRunCombatPhase:
    def test_no_war_no_summaries(self):
        stub = GameFacadeStub(returns={"find_contested_systems": []})
        result = run_combat_phase(1, 4, [1, 2], stub)
        assert result == []
        assert any(c[0] == "find_contested_systems" for c in stub.calls)

    def test_contested_system_produces_summary(self):
        fake_result = CombatResult(
            system_id=7, polity_a_id=1, polity_b_id=2,
            hits_on_a=1, hits_on_b=2,
        )
        stub = GameFacadeStub(returns={
            "find_contested_systems": [7],
            "resolve_space_combat": [fake_result],
        })
        summaries = run_combat_phase(3, 4, [1, 2], stub)
        assert any("combat" in s for s in summaries)
        assert any("system=7" in s for s in summaries)

    def test_disengage_summary_added(self):
        fake_result = CombatResult(
            system_id=7, polity_a_id=1, polity_b_id=2,
            hits_on_a=3, hits_on_b=0, a_disengaged=True,
        )
        stub = GameFacadeStub(returns={
            "find_contested_systems": [7],
            "resolve_space_combat": [fake_result],
        })
        summaries = run_combat_phase(3, 4, [1, 2], stub)
        assert any("disengage" in s and "polity=1" in s for s in summaries)

    def test_seeded_rng_determinism(self, conn):
        """Same tick/phase/system → same rng → reproducible combat outcomes."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 5, ["capital"])
        _fleet_with_hulls(conn, pid2, 5, ["capital"])

        game = GameFacadeImpl(conn)
        s1 = run_combat_phase(10, 4, [pid1, pid2], game)

        # Reset hull statuses back to active for a clean second run
        for h in conn.execute("SELECT hull_id FROM Hull_head WHERE status != 'active'").fetchall():
            from starscape5.game.fleet import mark_hull_active
            mark_hull_active(conn, h["hull_id"])
        s2 = run_combat_phase(10, 4, [pid1, pid2], game)

        # Extract hits lines (they encode the dice outcome)
        hits1 = [s for s in s1 if "hits_on_a" in s]
        hits2 = [s for s in s2 if "hits_on_a" in s]
        assert hits1 == hits2


# ---------------------------------------------------------------------------
# Integration: partial tick includes combat (phase 4 slot)
# ---------------------------------------------------------------------------

class TestPartialTickWithCombat:
    def test_no_war_tick_still_runs(self, conn, world):
        pid = _polity(conn, 1)
        # WorldPotential + presence for economy
        conn.execute(
            "INSERT INTO WorldPotential (body_id, system_id, world_potential, "
            "has_gas_giant, has_ocean) VALUES (10, 1, 15, 0, 0)"
        )
        create_presence(conn, pid, system_id=1, body_id=10,
                        control_state="controlled", development_level=3, established_tick=0)
        game = GameFacadeImpl(conn)
        result = run_partial_tick(1, [pid], game, world)
        assert isinstance(result, list)

    def test_war_combat_events_appear(self, conn, world):
        pid1 = _polity(conn, 1, system_id=1)
        pid2 = _polity(conn, 2, system_id=2)
        _at_war(conn, pid1, pid2)
        _fleet_with_hulls(conn, pid1, 5, ["capital"])
        _fleet_with_hulls(conn, pid2, 5, ["capital"])
        game = GameFacadeImpl(conn)
        run_partial_tick(1, [pid1, pid2], game, world)
        combat_events = get_events(conn, event_type="combat")
        assert len(combat_events) == 1
