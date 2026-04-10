"""M2 smoke tests — WorldFacade protocol and WorldStub.

No starscape.db required.  DB tests use an in-memory game.db.
"""

import math
import pytest

from starscape5.world.facade import (
    BodyData,
    SystemPosition,
    WorldFacade,
    compute_world_potential,
)
from starscape5.world.stub import WorldStub
from starscape5.game.db import open_game, init_schema


# ---------------------------------------------------------------------------
# compute_world_potential (pure function)
# ---------------------------------------------------------------------------

def _body(**kwargs) -> BodyData:
    defaults = dict(
        body_id=1, system_id=1, body_type="terrestrial",
        mass=1.0, radius=1.0, in_hz=1, planet_class="terrestrial",
        atm_type="standard", surface_temp_k=290.0,
        hydrosphere=0.6, world_potential=0,
    )
    defaults.update(kwargs)
    return BodyData(**defaults)


def test_potential_prime_hz_earthlike():
    body = _body(in_hz=1, atm_type="standard", hydrosphere=0.6,
                 planet_class="terrestrial", mass=1.0)
    # in_hz +10, atm_standard +5, hydro>0.5 +5, planet_class terrestrial +3, mass 0.5-2 +2 = 25
    assert compute_world_potential(body) == 25


def test_potential_minimum_enforced():
    body = _body(in_hz=0, atm_type="corrosive", hydrosphere=0.0,
                 planet_class="gas_giant", mass=500.0)
    # corrosive −8, nothing positive from planet_class/mass → could go negative
    assert compute_world_potential(body) >= 1


def test_potential_corrosive_penalty():
    base = _body(in_hz=1, atm_type="standard")
    corrosive = _body(in_hz=1, atm_type="corrosive")
    assert compute_world_potential(base) > compute_world_potential(corrosive)


def test_potential_no_atm_penalty():
    with_atm = _body(atm_type="thin")
    no_atm = _body(atm_type="none")
    assert compute_world_potential(with_atm) > compute_world_potential(no_atm)


def test_potential_hz_bonus():
    in_hz = _body(in_hz=1)
    out_hz = _body(in_hz=0)
    assert compute_world_potential(in_hz) > compute_world_potential(out_hz)


# ---------------------------------------------------------------------------
# WorldStub — protocol conformance
# ---------------------------------------------------------------------------

def test_worldstub_satisfies_protocol():
    stub = WorldStub()
    assert isinstance(stub, WorldFacade)


# ---------------------------------------------------------------------------
# WorldStub — positions
# ---------------------------------------------------------------------------

def test_get_star_position_deterministic():
    stub = WorldStub(seed=42)
    p1 = stub.get_star_position(1000)
    p2 = stub.get_star_position(1000)
    assert p1 == p2


def test_get_star_position_different_systems():
    stub = WorldStub(seed=42)
    p1 = stub.get_star_position(1)
    p2 = stub.get_star_position(2)
    assert p1 != p2


def test_position_in_universe_bounds():
    stub = WorldStub(seed=42)
    for sid in range(1, 20):
        p = stub.get_star_position(sid)
        assert 0.0 <= p.x_mpc <= 3000.0
        assert 0.0 <= p.y_mpc <= 3000.0
        assert 0.0 <= p.z_mpc <= 3000.0


def test_distance_symmetric():
    stub = WorldStub(seed=42)
    d_ab = stub.get_distance_pc(1, 2)
    d_ba = stub.get_distance_pc(2, 1)
    assert abs(d_ab - d_ba) < 1e-10


def test_distance_self_is_zero():
    stub = WorldStub(seed=42)
    assert stub.get_distance_pc(5, 5) == pytest.approx(0.0)


def test_systems_within_parsecs_excludes_self():
    stub = WorldStub(seed=42)
    nearby = stub.get_systems_within_parsecs(1, parsecs=3.0)
    assert 1 not in nearby


def test_systems_within_parsecs_symmetric():
    """If B is within range of A, A must be within range of B."""
    stub = WorldStub(seed=42)
    for a in range(1, 10):
        within = stub.get_systems_within_parsecs(a, parsecs=1.5)
        for b in within:
            assert a in stub.get_systems_within_parsecs(b, parsecs=1.5), (
                f"System {b} sees {a} as within 1.5 pc but {a} does not see {b}"
            )


def test_systems_within_parsecs_respects_range():
    stub = WorldStub(seed=42)
    close = stub.get_systems_within_parsecs(1, parsecs=0.5)
    far = stub.get_systems_within_parsecs(1, parsecs=2.5)
    assert len(far) >= len(close)
    for sid in close:
        assert stub.get_distance_pc(1, sid) <= 0.5


# ---------------------------------------------------------------------------
# WorldStub — bodies
# ---------------------------------------------------------------------------

def test_get_bodies_deterministic():
    stub = WorldStub(seed=42)
    b1 = stub.get_bodies(100)
    b2 = stub.get_bodies(100)
    assert b1 == b2


def test_get_bodies_count_range():
    stub = WorldStub(seed=42)
    for sid in range(1, 30):
        bodies = stub.get_bodies(sid)
        assert 0 <= len(bodies) <= 4


def test_body_ids_follow_scheme():
    stub = WorldStub(seed=42)
    for sid in range(1, 20):
        for i, body in enumerate(stub.get_bodies(sid)):
            assert body.body_id == sid * 10 + i
            assert body.system_id == sid


def test_body_world_potential_at_least_one():
    stub = WorldStub(seed=42)
    for sid in range(1, 50):
        for body in stub.get_bodies(sid):
            assert body.world_potential >= 1


def test_gas_giant_flag_consistent():
    stub = WorldStub(seed=42)
    for sid in range(1, 20):
        bodies = stub.get_bodies(sid)
        flag = stub.get_gas_giant_flag(sid)
        expected = any(b.body_type == "gas_giant" for b in bodies)
        assert flag == expected


def test_ocean_flag_consistent():
    stub = WorldStub(seed=42)
    for sid in range(1, 20):
        bodies = stub.get_bodies(sid)
        flag = stub.get_ocean_flag(sid)
        expected = any(b.hydrosphere >= 0.5 for b in bodies)
        assert flag == expected


# ---------------------------------------------------------------------------
# WorldStub — resolve_system (game.db integration)
# ---------------------------------------------------------------------------

@pytest.fixture
def game_conn():
    conn = open_game(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def test_resolve_system_populates_cache(game_conn):
    stub = WorldStub(seed=42)
    # Find a system that generates at least one body
    sid = next(s for s in range(1, 50) if stub.get_bodies(s))
    bodies = stub.resolve_system(sid, game_conn)

    rows = game_conn.execute(
        "SELECT * FROM WorldPotential WHERE system_id = ?", (sid,)
    ).fetchall()
    assert len(rows) == len(bodies)


def test_resolve_system_idempotent(game_conn):
    stub = WorldStub(seed=42)
    sid = next(s for s in range(1, 50) if stub.get_bodies(s))
    stub.resolve_system(sid, game_conn)
    stub.resolve_system(sid, game_conn)  # second call must not raise or duplicate

    rows = game_conn.execute(
        "SELECT * FROM WorldPotential WHERE system_id = ?", (sid,)
    ).fetchall()
    n_bodies = len(stub.get_bodies(sid))
    assert len(rows) == n_bodies


def test_resolve_system_returns_bodies(game_conn):
    stub = WorldStub(seed=42)
    sid = next(s for s in range(1, 50) if stub.get_bodies(s))
    returned = stub.resolve_system(sid, game_conn)
    assert returned == stub.get_bodies(sid)


def test_resolve_empty_system_no_rows(game_conn):
    stub = WorldStub(seed=42)
    # Find a system with no bodies
    sid = next((s for s in range(1, 50) if not stub.get_bodies(s)), None)
    if sid is None:
        pytest.skip("No empty system in first 50 — increase range or change seed")
    stub.resolve_system(sid, game_conn)
    rows = game_conn.execute(
        "SELECT * FROM WorldPotential WHERE system_id = ?", (sid,)
    ).fetchall()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# WorldStub — species
# ---------------------------------------------------------------------------

def test_get_species_deterministic():
    stub = WorldStub(seed=42)
    s1 = stub.get_species(1)
    s2 = stub.get_species(1)
    assert s1 == s2


def test_get_species_different_ids_differ():
    stub = WorldStub(seed=42)
    s1 = stub.get_species(1)
    s2 = stub.get_species(2)
    assert s1 != s2


def test_get_species_fields_in_range():
    stub = WorldStub(seed=42)
    for sid in range(1, 12):
        sp = stub.get_species(sid)
        assert 0.0 <= sp.aggression <= 1.0
        assert 0.0 <= sp.expansionism <= 1.0
        assert 0.0 <= sp.risk_appetite <= 1.0
        assert sp.lifespan_years >= 60
        assert sp.temp_min_k < sp.temp_max_k


# ---------------------------------------------------------------------------
# WorldStub — check_habitability
# ---------------------------------------------------------------------------

def test_habitability_known_body():
    stub = WorldStub(seed=42)
    # Stub species 1 has temp_min=250, temp_max=320 and atm_req='standard'.
    # Search for a matching body — first hit is system 133 with seed=42.
    sp = stub.get_species(1)
    for sid in range(1, 200):
        for body in stub.get_bodies(sid):
            if body.in_hz and body.atm_type == sp.atm_req:
                result = stub.check_habitability(body.body_id, 1)
                expected = sp.temp_min_k <= body.surface_temp_k <= sp.temp_max_k
                assert result == expected
                return
    pytest.skip("No qualifying body found in first 200 systems")


def test_habitability_unknown_body_id_returns_false():
    stub = WorldStub(seed=42)
    assert stub.check_habitability(body_id=999999, species_id=1) is False


# ---------------------------------------------------------------------------
# Smoke test matching implementation_plan.md
# ---------------------------------------------------------------------------

def test_m2_smoke():
    stub = WorldStub(seed=42)
    pos = stub.get_star_position(1000)
    bodies = stub.get_bodies(1000)
    print(f"\nSystem 1000: {pos}")
    print(f"  {len(bodies)} bodies")
    for b in bodies:
        print(f"    body_id={b.body_id} {b.body_type} in_hz={b.in_hz} "
              f"atm={b.atm_type} potential={b.world_potential}")
    assert isinstance(pos, SystemPosition)
