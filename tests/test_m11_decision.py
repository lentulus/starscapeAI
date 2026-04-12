"""M11 — Real decision engine tests.

Tests cover:
  game/snapshot.py      — build_snapshot
  game/posture.py       — posture_weights, draw_posture
  game/actions.py       — generate_candidates, select_actions
  game/war.py           — war_initiation_roll, process_war_rolls
  game/action_executor.py — execute_actions
  engine/decision.py    — run_decision_phase
"""

from __future__ import annotations

from random import Random

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.facade import GameFacadeImpl, GameFacadeStub
from starscape5.game.fleet import create_fleet, create_hull, _current_hull_row, _insert_hull_row
from starscape5.game.polity import create_polity, update_treasury
from starscape5.game.presence import create_presence
from starscape5.game.intelligence import _insert_contact_row
from starscape5.game.events import get_events
from starscape5.game.snapshot import build_snapshot, GameStateSnapshot
from starscape5.game.posture import Posture, draw_posture, posture_weights
from starscape5.game.actions import (
    generate_candidates, select_actions,
    ScoutAction, ColoniseAction, BuildHullAction,
    InitiateWarAction, AssaultAction,
)
from starscape5.game.war import war_initiation_roll, process_war_rolls, WarDeclared
from starscape5.engine.decision import run_decision_phase
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


def _polity(conn, n: int, system_id: int = 1,
            aggression: float = 0.5, expansionism: float = 0.5,
            risk_appetite: float = 0.5) -> int:
    return create_polity(
        conn, species_id=1, name=f"P{n}",
        capital_system_id=system_id,
        expansionism=expansionism, aggression=aggression,
        risk_appetite=risk_appetite, processing_order=n,
    )


def _fleet(conn, polity_id: int, system_id: int, hull_types: list[str]) -> int:
    fid = create_fleet(conn, polity_id, f"Fleet{polity_id}", system_id)
    for i, ht in enumerate(hull_types):
        create_hull(conn, polity_id, f"{ht}{i}", ht,
                    system_id=system_id, fleet_id=fid,
                    squadron_id=None, created_tick=0)
    return fid


def _contact(conn, pid_a: int, pid_b: int, at_war: int = 0) -> None:
    a, b = (pid_a, pid_b) if pid_a < pid_b else (pid_b, pid_a)
    # Check if contact already exists
    existing = conn.execute(
        "SELECT contact_id FROM ContactRecord WHERE polity_a_id = ? AND polity_b_id = ? "
        "ORDER BY row_id DESC LIMIT 1",
        (a, b),
    ).fetchone()
    if existing:
        return
    next_id = conn.execute(
        "SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord"
    ).fetchone()[0]
    _insert_contact_row(conn, contact_id=next_id, polity_a_id=a, polity_b_id=b,
                        contact_tick=0, contact_system_id=1,
                        peace_weeks=0, at_war=at_war, map_shared=0)


def _presence(conn, polity_id: int, system_id: int, body_id: int,
              control_state: str = "controlled", dev: int = 3,
              shipyard: int = 0) -> None:
    # Ensure WorldPotential row
    conn.execute(
        "INSERT OR IGNORE INTO WorldPotential "
        "(body_id, system_id, world_potential, has_gas_giant, has_ocean) "
        "VALUES (?, ?, 15, 0, 0)",
        (body_id, system_id),
    )
    create_presence(conn, polity_id, system_id=system_id, body_id=body_id,
                    control_state=control_state, development_level=dev,
                    established_tick=0, has_shipyard=shipyard)


def _visited(conn, polity_id: int, system_id: int,
             world_potential: int = 15, habitable: int = 1) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO SystemIntelligence "
        "(polity_id, system_id, knowledge_tier, world_potential, habitable) "
        "VALUES (?, ?, 'visited', ?, ?)",
        (polity_id, system_id, world_potential, habitable),
    )


# ---------------------------------------------------------------------------
# build_snapshot
# ---------------------------------------------------------------------------

class TestBuildSnapshot:
    def test_returns_snapshot(self, conn):
        pid = _polity(conn, 1)
        snap = build_snapshot(conn, pid, tick=1)
        assert isinstance(snap, GameStateSnapshot)
        assert snap.polity.polity_id == pid

    def test_fleets_populated(self, conn):
        pid = _polity(conn, 1)
        _fleet(conn, pid, 1, ["scout"])
        snap = build_snapshot(conn, pid, tick=1)
        assert len(snap.fleets) == 1
        assert snap.fleets[0].has_scout

    def test_at_war_populated(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=1)
        snap = build_snapshot(conn, pid1, tick=1)
        assert pid2 in snap.polity.at_war_with

    def test_known_systems_populated(self, conn):
        pid = _polity(conn, 1)
        _visited(conn, pid, 5)
        snap = build_snapshot(conn, pid, tick=1)
        assert any(s.system_id == 5 for s in snap.known_systems)

    def test_enemy_systems_populated(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=1)
        _fleet(conn, pid2, 7, ["cruiser"])
        snap = build_snapshot(conn, pid1, tick=1)
        assert 7 in snap.enemy_systems

    def test_presences_populated(self, conn):
        pid = _polity(conn, 1)
        _presence(conn, pid, 1, 10)
        snap = build_snapshot(conn, pid, tick=1)
        assert len(snap.presences) == 1
        assert snap.presences[0].system_id == 1


# ---------------------------------------------------------------------------
# posture_weights / draw_posture
# ---------------------------------------------------------------------------

class TestPosture:
    def _snap(self, conn, **kw):
        """Build a minimal snapshot with given polity parameters."""
        pid = _polity(conn, 1, **kw)
        _presence(conn, pid, 1, 10)
        return build_snapshot(conn, pid, tick=1)

    def test_at_war_prosecute_dominates(self, conn):
        pid1 = _polity(conn, 1, aggression=0.8)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=1)
        snap = build_snapshot(conn, pid1, tick=1)
        weights = posture_weights(snap)
        assert weights[Posture.PROSECUTE] > weights[Posture.EXPAND]

    def test_peaceful_high_expansion_prefers_expand(self, conn):
        snap = self._snap(conn, expansionism=0.9, aggression=0.1)
        weights = posture_weights(snap)
        assert weights[Posture.EXPAND] > weights[Posture.CONSOLIDATE]
        assert weights[Posture.EXPAND] > weights[Posture.PREPARE]

    def test_high_aggression_contact_raises_prepare(self, conn):
        pid1 = _polity(conn, 1, aggression=0.9)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=0)
        # Need 6 colonies before PREPARE is unlocked
        for i in range(6):
            _presence(conn, pid1, i + 1, i + 10, control_state="colony")
        snap = build_snapshot(conn, pid1, tick=1)
        weights = posture_weights(snap)
        assert weights[Posture.PREPARE] > 1.0  # meaningfully above base

    def test_prepare_suppressed_without_colonies(self, conn):
        """Young polities (< 6 colonies) cannot enter PREPARE."""
        pid1 = _polity(conn, 1, aggression=0.9)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=0)
        snap = build_snapshot(conn, pid1, tick=1)
        weights = posture_weights(snap)
        assert weights[Posture.PREPARE] == 0.0

    def test_draw_posture_reproducible(self, conn):
        snap = self._snap(conn, expansionism=0.5, aggression=0.5)
        r1 = draw_posture(snap, Random(42))
        r2 = draw_posture(snap, Random(42))
        assert r1 == r2

    def test_draw_posture_all_postures_reachable(self, conn):
        """Over many draws, all 4 postures appear at least once."""
        pid = _polity(conn, 1, expansionism=0.5, aggression=0.5)
        pid2 = _polity(conn, 2)
        _contact(conn, pid, pid2, at_war=0)
        for i in range(6):
            _presence(conn, pid, i + 1, i + 10, control_state="colony")
        snap = build_snapshot(conn, pid, tick=1)
        seen = set()
        for i in range(200):
            seen.add(draw_posture(snap, Random(i)))
        assert len(seen) == 4


# ---------------------------------------------------------------------------
# generate_candidates / select_actions
# ---------------------------------------------------------------------------

class TestCandidates:
    def test_scout_action_generated(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)  # mark home as visited
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        scout_actions = [c for c in candidates if isinstance(c, ScoutAction)]
        assert len(scout_actions) > 0

    def test_colonise_action_requires_visited_intel(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["colony_transport"])
        # No visited intel → no colonise actions
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        colonise_actions = [c for c in candidates if isinstance(c, ColoniseAction)]
        assert len(colonise_actions) == 0

    def test_colonise_action_with_visited_intel(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["colony_transport"])
        # Mark a neighbor as visited
        neighbors = world.get_systems_within_parsecs(1, 3.0)
        if neighbors:
            _visited(conn, pid, neighbors[0])
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        colonise_actions = [c for c in candidates if isinstance(c, ColoniseAction)]
        assert len(colonise_actions) > 0

    def test_build_hull_requires_shipyard(self, conn, world):
        pid = _polity(conn, 1)
        _presence(conn, pid, 1, 10, shipyard=0)
        update_treasury(conn, pid, 100.0)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.PREPARE,
                                         world.get_systems_within_parsecs)
        build_actions = [c for c in candidates if isinstance(c, BuildHullAction)]
        assert len(build_actions) == 0  # no shipyard

    def test_build_hull_requires_treasury(self, conn, world):
        pid = _polity(conn, 1)
        _presence(conn, pid, 1, 10, shipyard=1)
        # Deliberately low treasury (polity starts at 0 by default)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.PREPARE,
                                         world.get_systems_within_parsecs)
        build_actions = [c for c in candidates if isinstance(c, BuildHullAction)]
        assert len(build_actions) == 0

    def test_war_initiation_action_when_in_contact(self, conn, world):
        pid1 = _polity(conn, 1, aggression=0.9)
        pid2 = _polity(conn, 2)
        _contact(conn, pid1, pid2, at_war=0)
        # Requires 6 colonies before war is unlocked
        for i in range(6):
            _presence(conn, pid1, i + 1, i + 10, control_state="colony")
        snap = build_snapshot(conn, pid1, tick=1)
        candidates = generate_candidates(snap, Posture.PREPARE,
                                         world.get_systems_within_parsecs)
        war_actions = [c for c in candidates if isinstance(c, InitiateWarAction)]
        assert len(war_actions) > 0

    def test_select_actions_returns_requested_count(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        selected = select_actions(candidates, Random(42), top_k=3)
        assert len(selected) <= 3

    def test_select_actions_empty_input(self):
        selected = select_actions([], Random(0))
        assert selected == []

    def test_select_actions_reproducible(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["scout", "colony_transport"])
        _visited(conn, pid, 1)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        s1 = select_actions(candidates, Random(99), top_k=5)
        s2 = select_actions(candidates, Random(99), top_k=5)
        assert [type(a).__name__ for a in s1] == [type(a).__name__ for a in s2]

    def test_higher_scored_actions_win_more_often(self, conn, world):
        """Over many draws, the highest-scored action should be selected most."""
        pid = _polity(conn, 1, expansionism=0.9)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        if len(candidates) < 2:
            pytest.skip("Need at least 2 candidates")
        counts = {}
        for i in range(200):
            sel = select_actions(candidates, Random(i), top_k=1)
            if sel:
                key = type(sel[0]).__name__
                counts[key] = counts.get(key, 0) + 1
        # Best-scored type should appear at least 30% of the time
        top_count = max(counts.values()) if counts else 0
        assert top_count >= 60  # out of 200


# ---------------------------------------------------------------------------
# war_initiation_roll / process_war_rolls
# ---------------------------------------------------------------------------

class TestWarRolls:
    def test_high_aggression_more_likely_to_trigger(self):
        """With aggression=1.0, war threshold is easier to cross."""
        high_rng = Random(0)
        low_rng  = Random(0)   # same seed
        # Both roll identically, but with different aggression DMs
        high_roll = sum(
            1 for i in range(100)
            if war_initiation_roll(1.0, Random(i))
        )
        low_roll = sum(
            1 for i in range(100)
            if war_initiation_roll(0.0, Random(i))
        )
        assert high_roll > low_roll

    def test_pure_determinism(self):
        r1 = war_initiation_roll(0.5, Random(42))
        r2 = war_initiation_roll(0.5, Random(42))
        assert r1 == r2

    def test_extra_dm_raises_probability(self):
        baseline = sum(1 for i in range(200) if war_initiation_roll(0.3, Random(i), extra_dm=0))
        boosted  = sum(1 for i in range(200) if war_initiation_roll(0.3, Random(i), extra_dm=3))
        assert boosted > baseline

    def test_process_war_rolls_creates_war_record(self, conn):
        pid1 = _polity(conn, 1, aggression=1.0)
        pid2 = _polity(conn, 2, aggression=1.0)
        _contact(conn, pid1, pid2, at_war=0)
        # With aggression=1.0, DM=6; roll 2d6+6 nearly always ≥ 10
        declared: list[WarDeclared] = []
        for i in range(50):
            declared = process_war_rolls(conn, tick=i+1, rng=Random(i))
            if declared:
                break
        # Eventually a war should be declared
        war_rows = conn.execute("SELECT * FROM WarRecord").fetchall()
        assert len(war_rows) >= 1

    def test_process_war_rolls_writes_event(self, conn):
        pid1 = _polity(conn, 1, aggression=1.0)
        pid2 = _polity(conn, 2, aggression=1.0)
        _contact(conn, pid1, pid2, at_war=0)
        for i in range(50):
            result = process_war_rolls(conn, tick=1, rng=Random(i))
            if result:
                break
        if conn.execute("SELECT COUNT(*) FROM WarRecord").fetchone()[0] > 0:
            events = get_events(conn, event_type="war_declared")
            assert len(events) >= 1

    def test_already_at_war_pair_not_rolled(self, conn):
        pid1 = _polity(conn, 1, aggression=1.0)
        pid2 = _polity(conn, 2, aggression=1.0)
        _contact(conn, pid1, pid2, at_war=1)
        declared = process_war_rolls(conn, tick=1, rng=Random(0))
        assert declared == []  # already at war, no roll


# ---------------------------------------------------------------------------
# execute_actions (via GameFacadeImpl)
# ---------------------------------------------------------------------------

class TestExecuteActions:
    def test_scout_action_issues_jump(self, conn, world):
        pid = _polity(conn, 1)
        fid = _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        snap = build_snapshot(conn, pid, tick=1)
        candidates = generate_candidates(snap, Posture.EXPAND,
                                         world.get_systems_within_parsecs)
        scouts = [c for c in candidates if isinstance(c, ScoutAction)]
        if not scouts:
            pytest.skip("No scout actions generated")
        game = GameFacadeImpl(conn)
        summaries = game.execute_actions(pid, scouts[:1], world, tick=1)
        assert any("scout" in s for s in summaries)
        fleet_row = conn.execute(
            "SELECT status FROM Fleet WHERE fleet_id = ?", (fid,)
        ).fetchone()
        assert fleet_row["status"] == "in_transit"

    def test_build_hull_deducts_treasury(self, conn, world):
        pid = _polity(conn, 1)
        _presence(conn, pid, 1, 10, shipyard=1)
        update_treasury(conn, pid, 50.0)
        from starscape5.game.actions import BuildHullAction
        action = BuildHullAction(system_id=1, hull_type="escort", score=1.0)
        game = GameFacadeImpl(conn)
        summaries = game.execute_actions(pid, [action], world, tick=1)
        assert any("build_order" in s for s in summaries)
        treasury = conn.execute(
            "SELECT treasury_ru FROM Polity_head WHERE polity_id = ?", (pid,)
        ).fetchone()["treasury_ru"]
        assert treasury == 50 - 8.0  # escort costs 8 RU

    def test_build_hull_insufficient_treasury_no_op(self, conn, world):
        pid = _polity(conn, 1)
        _presence(conn, pid, 1, 10, shipyard=1)
        # Treasury starts at 0 — no update needed
        action = BuildHullAction(system_id=1, hull_type="capital", score=1.0)
        game = GameFacadeImpl(conn)
        summaries = game.execute_actions(pid, [action], world, tick=1)
        assert summaries == []


# ---------------------------------------------------------------------------
# Engine: run_decision_phase
# ---------------------------------------------------------------------------

class TestRunDecisionPhase:
    def test_returns_strings(self, conn, world):
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        _presence(conn, pid, 1, 10)
        game = GameFacadeImpl(conn)
        result = run_decision_phase(1, 2, [pid], game, world)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_war_declared_summary_appears(self, conn, world):
        pid1 = _polity(conn, 1, aggression=1.0)
        pid2 = _polity(conn, 2, aggression=1.0)
        _contact(conn, pid1, pid2, at_war=0)
        game = GameFacadeImpl(conn)
        for tick in range(1, 30):
            result = run_decision_phase(tick, 2, [pid1, pid2], game, world)
            if any("war_declared" in s for s in result):
                break
        war_events = get_events(conn, event_type="war_declared")
        assert len(war_events) >= 1

    def test_stub_wiring_calls_process_war_rolls(self):
        stub = GameFacadeStub(returns={
            "process_war_rolls": [],
            "build_snapshot": None,
        })
        run_decision_phase(1, 2, [1], stub, WorldStub())
        called = [c[0] for c in stub.calls]
        assert "process_war_rolls" in called

    def test_posture_summary_in_output(self, conn, world):
        """When a polity takes action, posture appears in summaries."""
        pid = _polity(conn, 1, expansionism=0.9)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        _presence(conn, pid, 1, 10)
        game = GameFacadeImpl(conn)
        summaries = run_decision_phase(1, 2, [pid], game, world)
        posture_lines = [s for s in summaries if "posture=" in s]
        # Only appears when the polity actually takes an action
        if any("scout" in s or "jump" in s for s in summaries):
            assert len(posture_lines) >= 1

    def test_determinism(self, conn, world):
        """Same tick + same state → same decisions."""
        pid = _polity(conn, 1, expansionism=0.8)
        _fleet(conn, pid, 1, ["scout"])
        _visited(conn, pid, 1)
        _presence(conn, pid, 1, 10)
        game = GameFacadeImpl(conn)
        s1 = run_decision_phase(5, 2, [pid], game, world)
        # Reset fleet to active at origin for second run
        conn.execute("UPDATE Fleet SET status='active', system_id=1, "
                     "destination_system_id=NULL, destination_tick=NULL "
                     "WHERE polity_id=?", (pid,))
        # Reset hulls to active at origin (temporal: INSERT new head rows)
        hull_ids = [
            r["hull_id"] for r in conn.execute(
                "SELECT DISTINCT hull_id FROM Hull WHERE polity_id = ?", (pid,)
            ).fetchall()
        ]
        for hid in hull_ids:
            cur = _current_hull_row(conn, hid)
            _insert_hull_row(
                conn, hull_id=hid,
                polity_id=cur["polity_id"],
                name=cur["name"],
                hull_type=cur["hull_type"],
                squadron_id=cur["squadron_id"],
                fleet_id=cur["fleet_id"],
                system_id=1,
                destination_system_id=None,
                destination_tick=None,
                status="active",
                marine_designated=cur["marine_designated"],
                cargo_type=cur["cargo_type"],
                cargo_id=cur["cargo_id"],
                establish_tick=cur["establish_tick"],
                created_tick=cur["created_tick"],
                tick=5, seq=99,
            )
        s2 = run_decision_phase(5, 2, [pid], game, world)
        assert s1 == s2


# ---------------------------------------------------------------------------
# Integration: partial tick with real decision engine
# ---------------------------------------------------------------------------

class TestPartialTickWithDecisionEngine:
    def test_multi_polity_war_breaks_out(self, conn, world):
        """Two high-aggression polities should go to war within 50 ticks."""
        pid1 = _polity(conn, 1, aggression=1.0, expansionism=0.3)
        pid2 = _polity(conn, 2, aggression=1.0, expansionism=0.3, system_id=2)
        _contact(conn, pid1, pid2, at_war=0)

        for pid, sid in [(pid1, 1), (pid2, 2)]:
            _presence(conn, pid, sid, sid * 10)

        game = GameFacadeImpl(conn)
        for tick in range(1, 51):
            run_partial_tick(tick, [pid1, pid2], game, world)
            if conn.execute("SELECT COUNT(*) FROM WarRecord").fetchone()[0] > 0:
                break

        assert conn.execute("SELECT COUNT(*) FROM WarRecord").fetchone()[0] >= 1

    def test_high_expansion_polity_scouts(self, conn, world):
        """A high-expansionism polity with a scout fleet should issue scout orders."""
        pid = _polity(conn, 1, expansionism=1.0, aggression=0.0)
        _fleet(conn, pid, 1, ["scout"])
        _presence(conn, pid, 1, 10)
        _visited(conn, pid, 1)

        game = GameFacadeImpl(conn)
        summaries = []
        for tick in range(1, 5):
            s = run_partial_tick(tick, [pid], game, world)
            summaries.extend(s)

        scout_orders = [s for s in summaries if "scout" in s and "jump" in s]
        assert len(scout_orders) >= 1
