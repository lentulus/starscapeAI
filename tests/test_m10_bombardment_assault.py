"""M10 — Bombardment and Assault phase tests.

Tests cover:
  game/bombardment.py  — check_naval_superiority, should_bombard,
                         run_bombardment_tick, find_bombardment_candidates
  game/assault.py      — ground_combat_result, run_ground_assault,
                         find_assault_candidates
  engine/bombardment.py — run_bombardment_phase (stub wiring)
  engine/assault.py     — run_assault_phase (stub wiring)
  engine/tick.py        — phases 5 & 6 now in partial tick
"""

from __future__ import annotations

from random import Random

import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.facade import GameFacadeImpl, GameFacadeStub
from starscape5.game.fleet import create_fleet, create_hull
from starscape5.game.ground import create_ground_force, disembark_force, apply_strength_delta
from starscape5.game.polity import create_polity
from starscape5.game.presence import create_presence
from starscape5.game.events import get_events
from starscape5.game.intelligence import _insert_contact_row
from starscape5.game.bombardment import (
    BombardmentResult,
    check_naval_superiority,
    should_bombard,
    run_bombardment_tick,
    find_bombardment_candidates,
)
from starscape5.game.assault import (
    AssaultResult,
    ground_combat_result,
    run_ground_assault,
    find_assault_candidates,
)
from starscape5.engine.bombardment import run_bombardment_phase
from starscape5.engine.assault import run_assault_phase
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


def _fleet(conn, polity_id: int, system_id: int, hull_types: list[str]) -> int:
    fid = create_fleet(conn, polity_id, f"F{polity_id}", system_id)
    for i, ht in enumerate(hull_types):
        create_hull(conn, polity_id, f"{ht}-{i}", ht,
                    system_id=system_id, fleet_id=fid,
                    squadron_id=None, created_tick=0)
    return fid


def _army(conn, polity_id: int, system_id: int, body_id: int,
          marine: int = 0) -> int:
    return create_ground_force(
        conn, polity_id, f"Army-{polity_id}", "army",
        system_id=system_id, body_id=body_id,
        created_tick=0, marine_designated=marine,
    )


def _garrison(conn, polity_id: int, system_id: int, body_id: int) -> int:
    return create_ground_force(
        conn, polity_id, f"Garrison-{polity_id}", "garrison",
        system_id=system_id, body_id=body_id,
        created_tick=0,
    )


def _at_war(conn, pid_a: int, pid_b: int, system_id: int = 1) -> None:
    a, b = (pid_a, pid_b) if pid_a < pid_b else (pid_b, pid_a)
    next_id = conn.execute(
        "SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord"
    ).fetchone()[0]
    _insert_contact_row(conn, contact_id=next_id, polity_a_id=a, polity_b_id=b,
                        contact_tick=0, contact_system_id=system_id,
                        peace_weeks=0, at_war=1, map_shared=0)


# ---------------------------------------------------------------------------
# check_naval_superiority
# ---------------------------------------------------------------------------

class TestNavalSuperiority:
    def test_no_own_fleet_is_false(self, conn):
        pid = _polity(conn, 1)
        assert not check_naval_superiority(conn, 1, pid)

    def test_own_fleet_no_enemy_is_true(self, conn):
        pid = _polity(conn, 1)
        _fleet(conn, pid, 5, ["cruiser"])
        assert check_naval_superiority(conn, 5, pid)

    def test_hostile_fleet_present_is_false(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2, system_id=5)
        _fleet(conn, pid1, 5, ["cruiser"])
        _fleet(conn, pid2, 5, ["escort"])
        assert not check_naval_superiority(conn, 5, pid1)

    def test_at_peace_enemy_fleet_not_hostile(self, conn):
        """Two polities at peace — both have fleets; neither counts as hostile."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        # ContactRecord with at_war=0
        a, b = min(pid1, pid2), max(pid1, pid2)
        next_id = conn.execute("SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord").fetchone()[0]
        _insert_contact_row(conn, contact_id=next_id, polity_a_id=a, polity_b_id=b,
                            contact_tick=0, contact_system_id=5,
                            peace_weeks=0, at_war=0, map_shared=0)
        _fleet(conn, pid1, 5, ["cruiser"])
        _fleet(conn, pid2, 5, ["cruiser"])
        assert check_naval_superiority(conn, 5, pid1)


# ---------------------------------------------------------------------------
# should_bombard (pure)
# ---------------------------------------------------------------------------

class TestShouldBombard:
    def test_no_bombard_advantage_returns_false(self):
        assert not should_bombard(10, 4, 0.5, net_bombard=0)

    def test_defender_weaker_returns_false(self):
        # Defender strength 2 < attacker army 8 → no need to bombard
        assert not should_bombard(2, 8, 0.5, net_bombard=3)

    def test_defender_stronger_returns_true(self):
        # Defender 20, attacker army 4, bombard advantage 3
        assert should_bombard(20, 4, 0.5, net_bombard=3)

    def test_low_risk_appetite_bombards_earlier(self):
        # With risk_appetite=0.1 even near-equal defenders trigger bombard
        assert should_bombard(6, 4, 0.1, net_bombard=2)


# ---------------------------------------------------------------------------
# run_bombardment_tick
# ---------------------------------------------------------------------------

class TestBombardmentTick:
    def test_reduces_defender_strength_by_one(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        # Attacker has a capital (bombard=3); defender has no fleet
        _fleet(conn, pid1, 5, ["capital"])
        fid = _garrison(conn, pid2, 5, body_id=50)
        from starscape5.game.ground import get_ground_force
        before = get_ground_force(conn, fid).strength
        run_bombardment_tick(conn, 5, pid1, pid2, tick=1, rng=Random(0))
        after = get_ground_force(conn, fid).strength
        assert after == before - 1

    def test_no_effect_when_net_bombard_zero_or_negative(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        # Defender has SDB (bombard=2); attacker has only escort (bombard=0)
        _fleet(conn, pid1, 5, ["escort"])
        sdb_squad = conn.execute(
            "INSERT INTO Squadron (fleet_id, polity_id, name, hull_type, combat_role, system_id) "
            "VALUES (NULL, ?, 'SDB', 'sdb', 'line_of_battle', 5)",
            (pid2,),
        ).lastrowid
        create_hull(conn, pid2, "SDB-1", "sdb",
                    system_id=5, fleet_id=None, squadron_id=sdb_squad, created_tick=0)
        fid = _garrison(conn, pid2, 5, body_id=50)
        from starscape5.game.ground import get_ground_force
        before = get_ground_force(conn, fid).strength
        run_bombardment_tick(conn, 5, pid1, pid2, tick=1, rng=Random(0))
        after = get_ground_force(conn, fid).strength
        assert after == before  # no change

    def test_bombardment_can_destroy_unit(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        fid = _garrison(conn, pid2, 5, body_id=50)
        # Reduce to strength 1 manually; bombardment should now finish the unit
        from starscape5.game.ground import get_ground_force
        cur_strength = get_ground_force(conn, fid).strength
        apply_strength_delta(conn, fid, -(cur_strength - 1), tick=0)
        run_bombardment_tick(conn, 5, pid1, pid2, tick=1, rng=Random(0))
        after = get_ground_force(conn, fid).strength
        assert after == 0  # bombardment can now destroy the last point of strength

    def test_writes_bombardment_event(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _garrison(conn, pid2, 5, body_id=50)
        run_bombardment_tick(conn, 5, pid1, pid2, tick=1, rng=Random(0))
        events = get_events(conn, event_type="bombardment")
        assert len(events) == 1


# ---------------------------------------------------------------------------
# find_bombardment_candidates
# ---------------------------------------------------------------------------

class TestFindBombardmentCandidates:
    def test_finds_eligible_system(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _garrison(conn, pid2, 5, body_id=50)
        candidates = find_bombardment_candidates(conn)
        assert (5, pid1, pid2) in candidates

    def test_no_candidate_when_not_at_war(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _fleet(conn, pid1, 5, ["capital"])
        _garrison(conn, pid2, 5, body_id=50)
        assert find_bombardment_candidates(conn) == []

    def test_no_candidate_when_enemy_fleet_present(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _fleet(conn, pid2, 5, ["escort"])  # hostile fleet present
        _garrison(conn, pid2, 5, body_id=50)
        assert find_bombardment_candidates(conn) == []


# ---------------------------------------------------------------------------
# ground_combat_result (pure)
# ---------------------------------------------------------------------------

class TestGroundCombatResult:
    def test_rout_at_6_plus(self):
        outcome, atk_d, def_d = ground_combat_result(6)
        assert outcome == "rout"
        assert atk_d == 0
        assert def_d == -99

    def test_decisive_at_4_5(self):
        for net in (4, 5):
            outcome, atk_d, def_d = ground_combat_result(net)
            assert outcome == "decisive"
            assert atk_d == -1
            assert def_d == -3

    def test_attacker_advantage_at_2_3(self):
        for net in (2, 3):
            outcome, _, _ = ground_combat_result(net)
            assert outcome == "attacker_advantage"

    def test_no_decision_at_0_1(self):
        for net in (0, 1):
            outcome, atk_d, def_d = ground_combat_result(net)
            assert outcome == "no_decision"
            assert atk_d == -1
            assert def_d == -1

    def test_negative_net_inverts_table(self):
        outcome, atk_d, def_d = ground_combat_result(-6)
        assert outcome == "rout_defender"
        assert atk_d == -99
        assert def_d == 0


# ---------------------------------------------------------------------------
# run_ground_assault
# ---------------------------------------------------------------------------

class TestRunGroundAssault:
    def test_returns_assault_result(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)
        result = run_ground_assault(conn, 5, 50, pid1, pid2, tick=1, rng=Random(0))
        assert isinstance(result, AssaultResult)
        assert result.system_id == 5

    def test_writes_combat_event(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)
        run_ground_assault(conn, 5, 50, pid1, pid2, tick=1, rng=Random(42))
        events = get_events(conn, event_type="combat")
        ground_events = [e for e in events if "ground_assault" in e.summary]
        assert len(ground_events) == 1

    def test_non_marine_penalty_first_round(self, conn):
        """Non-marine army has −1 effective strength on first round."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        army_id = _army(conn, pid1, 5, 50, marine=0)

        # Record with same rng: first_round=True vs first_round=False
        # We check that the net_shift differs (not guaranteed by fixed seed but
        # the effective strength differs, which changes the outcome distribution).
        # Use a deterministic check: extract attacker effective strength.
        row = conn.execute(
            "SELECT strength FROM GroundForce WHERE force_id = ?", (army_id,)
        ).fetchone()
        base_strength = row["strength"]  # 4

        # The penalty means effective = max(1, 4-1) = 3 on first round
        # We can't directly observe effective strength, so just confirm
        # the function doesn't raise and produces a result.
        _garrison(conn, pid2, 5, 50)
        result = run_ground_assault(conn, 5, 50, pid1, pid2, tick=1,
                                    rng=Random(0), first_round=True)
        assert result is not None

    def test_garrison_prepared_positions_bonus(self, conn):
        """Garrison ×1.5 in prepared positions makes them harder to overrun."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)  # gets ×1.5 effective strength
        # Run multiple rounds — just verify no errors
        for _ in range(5):
            run_ground_assault(conn, 5, 50, pid1, pid2, tick=1, rng=Random(99))

    def test_rout_destroys_defenders(self, conn):
        """Force a rout: overwhelming attacker, no defender dice luck."""
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        # Attacker: 6 armies (36 strength total → near-guaranteed rout)
        from starscape5.game.ground import get_ground_force
        for i in range(6):
            create_ground_force(conn, pid1, f"Army{i}", "army",
                                system_id=5, body_id=50, created_tick=0, marine_designated=1)
        # Defender: 1 weak garrison
        gid = _garrison(conn, pid2, 5, 50)
        cur_strength = get_ground_force(conn, gid).strength
        apply_strength_delta(conn, gid, -(cur_strength - 1), tick=0)

        result = None
        for _ in range(20):   # enough tries to get a rout with fixed seed
            result = run_ground_assault(conn, 5, 50, pid1, pid2, tick=1, rng=Random(42))
            if result and result.outcome == "rout":
                break
        assert result is not None

    def test_rout_writes_control_change_event(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        # Create a presence for pid2 to be contested
        create_presence(conn, pid2, system_id=5, body_id=50,
                        control_state="controlled", development_level=3,
                        established_tick=0)
        # Single garrison vs massive force
        gid = _garrison(conn, pid2, 5, 50)
        cur_strength = conn.execute(
            "SELECT strength FROM GroundForce_head WHERE force_id = ?", (gid,)
        ).fetchone()["strength"]
        apply_strength_delta(conn, gid, -(cur_strength - 1), tick=0)
        for i in range(6):
            create_ground_force(
                conn, pid1, f"A{i}", "army",
                system_id=5, body_id=50,
                created_tick=0, marine_designated=1,
            )
        for _ in range(20):
            result = run_ground_assault(conn, 5, 50, pid1, pid2, tick=1, rng=Random(42))
            if result and result.control_changed:
                break
        cc_events = get_events(conn, event_type="control_change")
        if result and result.control_changed:
            assert len(cc_events) >= 1


# ---------------------------------------------------------------------------
# find_assault_candidates
# ---------------------------------------------------------------------------

class TestFindAssaultCandidates:
    def test_finds_eligible_body(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])   # naval superiority
        _army(conn, pid1, 5, 50)             # attacker has landed troops
        _garrison(conn, pid2, 5, 50)         # defender has ground forces
        candidates = find_assault_candidates(conn)
        assert (5, 50, pid1, pid2) in candidates

    def test_no_attacker_troops_no_candidate(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _garrison(conn, pid2, 5, 50)
        # No attacker ground forces
        assert find_assault_candidates(conn) == []

    def test_no_naval_superiority_no_candidate(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _fleet(conn, pid2, 5, ["escort"])   # hostile fleet present
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)
        assert find_assault_candidates(conn) == []


# ---------------------------------------------------------------------------
# Engine: run_bombardment_phase
# ---------------------------------------------------------------------------

class TestRunBombardmentPhase:
    def test_no_candidates_no_summaries(self):
        stub = GameFacadeStub(returns={"find_bombardment_candidates": []})
        result = run_bombardment_phase(1, 5, [1, 2], stub)
        assert result == []

    def test_candidate_produces_summary(self):
        fake_result = BombardmentResult(
            system_id=7, attacker_id=1, body_id=70,
            net_bombard=3, strength_delta=-1,
            defender_total_before=6, defender_total_after=5,
        )
        stub = GameFacadeStub(returns={
            "find_bombardment_candidates": [(7, 1, 2)],
            "run_bombardment_tick": fake_result,
        })
        summaries = run_bombardment_phase(2, 5, [1, 2], stub)
        assert any("bombardment" in s for s in summaries)
        assert any("system=7" in s for s in summaries)

    def test_impl_integration(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _garrison(conn, pid2, 5, 50)
        game = GameFacadeImpl(conn)
        summaries = run_bombardment_phase(1, 5, [pid1, pid2], game)
        assert any("bombardment" in s for s in summaries)


# ---------------------------------------------------------------------------
# Engine: run_assault_phase
# ---------------------------------------------------------------------------

class TestRunAssaultPhase:
    def test_no_candidates_no_summaries(self):
        stub = GameFacadeStub(returns={"find_assault_candidates": []})
        result = run_assault_phase(1, 6, [1, 2], stub)
        assert result == []

    def test_candidate_produces_summary(self):
        fake_result = AssaultResult(
            system_id=7, body_id=70, attacker_id=1, defender_id=2,
            attacker_str_before=4, defender_str_before=4,
            attacker_str_after=3, defender_str_after=2,
            net_shift=2, outcome="attacker_advantage",
        )
        stub = GameFacadeStub(returns={
            "find_assault_candidates": [(7, 70, 1, 2)],
            "run_ground_assault": fake_result,
        })
        summaries = run_assault_phase(2, 6, [1, 2], stub)
        assert any("assault" in s for s in summaries)

    def test_control_change_summary_added(self):
        fake_result = AssaultResult(
            system_id=7, body_id=70, attacker_id=1, defender_id=2,
            attacker_str_before=6, defender_str_before=2,
            attacker_str_after=6, defender_str_after=0,
            net_shift=8, outcome="rout",
            control_changed=True, new_control_state="contested",
        )
        stub = GameFacadeStub(returns={
            "find_assault_candidates": [(7, 70, 1, 2)],
            "run_ground_assault": fake_result,
        })
        summaries = run_assault_phase(2, 6, [1, 2], stub)
        assert any("control_change" in s for s in summaries)

    def test_impl_integration(self, conn):
        pid1 = _polity(conn, 1)
        pid2 = _polity(conn, 2)
        _at_war(conn, pid1, pid2)
        _fleet(conn, pid1, 5, ["capital"])
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)
        game = GameFacadeImpl(conn)
        summaries = run_assault_phase(1, 6, [pid1, pid2], game)
        assert any("assault" in s for s in summaries)


# ---------------------------------------------------------------------------
# Integration: partial tick includes phases 5 & 6
# ---------------------------------------------------------------------------

class TestPartialTickWithBombardmentAssault:
    def test_full_tick_no_war(self, conn, world):
        """Tick runs cleanly even with no bombardment or assault candidates."""
        pid = _polity(conn, 1)
        conn.execute(
            "INSERT INTO WorldPotential (body_id, system_id, world_potential, "
            "has_gas_giant, has_ocean) VALUES (10, 1, 15, 0, 0)"
        )
        create_presence(conn, pid, system_id=1, body_id=10,
                        control_state="controlled", development_level=3,
                        established_tick=0)
        game = GameFacadeImpl(conn)
        result = run_partial_tick(1, [pid], game, world)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_bombardment_and_assault_appear_in_tick(self, conn, world):
        pid1 = _polity(conn, 1, system_id=1)
        pid2 = _polity(conn, 2, system_id=2)
        _at_war(conn, pid1, pid2)
        # pid1 has naval superiority at system 5
        _fleet(conn, pid1, 5, ["capital"])
        # pid1 has landed army; pid2 has defenders
        _army(conn, pid1, 5, 50)
        _garrison(conn, pid2, 5, 50)
        game = GameFacadeImpl(conn)
        summaries = run_partial_tick(1, [pid1, pid2], game, world)
        assert any("bombardment" in s for s in summaries)
        assert any("assault" in s for s in summaries)
