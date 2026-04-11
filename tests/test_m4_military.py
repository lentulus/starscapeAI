"""M4 tests — constants, Fleet/Squadron/Hull, Admiral, Ground forces."""

from random import Random
import pytest

from starscape5.game.db import open_game, init_schema
from starscape5.game.polity import create_polity
from starscape5.game.constants import HULL_STATS, GROUND_STATS, SQUADRON_HULL_TYPES
from starscape5.game.fleet import (
    create_fleet, create_squadron, create_hull,
    get_fleet, get_fleets_in_system, get_hostile_fleets,
    get_hulls_in_fleet, get_hulls_in_system, get_hulls_in_squadron,
    get_squadrons_in_fleet,
    set_fleet_destination, arrive_fleet, update_fleet_supply,
    assign_combat_role, compute_squadron_strength,
    mark_hull_damaged, mark_hull_destroyed,
)
from starscape5.game.admiral import (
    ADMIRAL_GENERATION_PARAMS,
    AdmiralRow,
    commission_on_demand,
    create_admiral,
    generate_tactical_factor,
    get_fleet_admiral,
    get_senior_admiral,
    transfer_command,
)
from starscape5.game.ground import (
    GroundForceRow,
    apply_strength_delta,
    create_ground_force,
    disembark_force,
    embark_force,
    get_ground_force,
    get_ground_forces_at_body,
    get_ground_forces_in_system,
    tick_refit,
)
from starscape5.world.stub import WorldStub
from starscape5.game.names import NameGenerator


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
def two_polities(conn):
    p1 = create_polity(conn, species_id=1, name="Kreeth",
                       capital_system_id=100, expansionism=0.7,
                       aggression=0.8, risk_appetite=0.6, processing_order=1)
    p2 = create_polity(conn, species_id=11, name="Humanity",
                       capital_system_id=200, expansionism=0.5,
                       aggression=0.4, risk_appetite=0.5, processing_order=2)
    conn.commit()
    return conn, p1, p2


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_hull_stats_all_types_present():
    expected = {"capital", "old_capital", "cruiser", "escort",
                "troop", "transport", "colony_transport", "scout", "sdb"}
    assert set(HULL_STATS.keys()) == expected


def test_ground_stats_both_types():
    assert set(GROUND_STATS.keys()) == {"garrison", "army"}


def test_sdb_no_jump():
    assert HULL_STATS["sdb"].jump == 0


def test_scout_maintenance():
    # Scouts have a small maintenance cost to prevent unlimited accumulation
    assert HULL_STATS["scout"].maint_per_tick == 0.1


def test_garrison_zero_maintenance():
    assert GROUND_STATS["garrison"].maint_per_tick == 0.0


def test_garrison_not_embarkable():
    assert GROUND_STATS["garrison"].embarkable is False


def test_army_embarkable():
    assert GROUND_STATS["army"].embarkable is True


def test_squadron_hull_types_are_warships():
    for ht in SQUADRON_HULL_TYPES:
        assert ht in HULL_STATS


def test_capital_outperforms_old_capital():
    c = HULL_STATS["capital"]
    oc = HULL_STATS["old_capital"]
    assert c.attack > oc.attack
    assert c.defence > oc.defence


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------

def test_create_fleet(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "First Swarm", system_id=100)
    assert isinstance(fid, int)
    f = get_fleet(conn, fid)
    assert f.name == "First Swarm"
    assert f.system_id == 100
    assert f.status == "active"


def test_get_fleets_in_system(two_polities):
    conn, p1, p2 = two_polities
    f1 = create_fleet(conn, p1, "Kreeth Fleet", system_id=100)
    f2 = create_fleet(conn, p2, "Human Fleet", system_id=100)
    create_fleet(conn, p1, "Elsewhere", system_id=999)
    conn.commit()
    fleets = get_fleets_in_system(conn, 100)
    ids = {f.fleet_id for f in fleets}
    assert f1 in ids and f2 in ids
    assert all(f.system_id == 100 for f in fleets)


def test_get_hostile_fleets(two_polities):
    conn, p1, p2 = two_polities
    create_fleet(conn, p1, "Kreeth", system_id=100)
    human = create_fleet(conn, p2, "Human", system_id=100)
    conn.commit()
    hostile = get_hostile_fleets(conn, 100, p1)
    assert len(hostile) == 1
    assert hostile[0].fleet_id == human


def test_set_fleet_destination(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", system_id=100)
    set_fleet_destination(conn, fid, destination_system_id=200, destination_tick=5)
    conn.commit()
    f = get_fleet(conn, fid)
    assert f.destination_system_id == 200
    assert f.destination_tick == 5
    assert f.status == "in_transit"


def test_arrive_fleet(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", system_id=100)
    hid = create_hull(conn, p1, "CAP-001", "capital", 100, fid, None, 0)
    set_fleet_destination(conn, fid, 200, 3)
    conn.execute("UPDATE Hull SET status='in_transit' WHERE hull_id=?", (hid,))
    conn.commit()
    arrive_fleet(conn, fid, 200)
    conn.commit()
    f = get_fleet(conn, fid)
    assert f.system_id == 200
    assert f.status == "active"


def test_update_fleet_supply(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", system_id=100)
    update_fleet_supply(conn, fid, 3)
    conn.commit()
    assert get_fleet(conn, fid).supply_ticks == 3


# ---------------------------------------------------------------------------
# Squadron
# ---------------------------------------------------------------------------

def test_create_squadron(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", system_id=100)
    sid = create_squadron(conn, fid, p1, "First Claw", "capital",
                          "line_of_battle", 100)
    conn.commit()
    squads = get_squadrons_in_fleet(conn, fid)
    assert len(squads) == 1
    assert squads[0].squadron_id == sid
    assert squads[0].hull_type == "capital"


def test_assign_combat_role(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", system_id=100)
    sid = create_squadron(conn, fid, p1, "Escorts", "escort", "line_of_battle", 100)
    assign_combat_role(conn, sid, "screen")
    conn.commit()
    sq = get_squadrons_in_fleet(conn, fid)[0]
    assert sq.combat_role == "screen"


def test_compute_squadron_strength_all_active(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    sid = create_squadron(conn, fid, p1, "Capitals", "capital", "line_of_battle", 100)
    create_hull(conn, p1, "CAP-001", "capital", 100, fid, sid, 0)
    create_hull(conn, p1, "CAP-002", "capital", 100, fid, sid, 0)
    conn.commit()
    s = compute_squadron_strength(conn, sid)
    stats = HULL_STATS["capital"]
    assert s["attack"] == stats.attack * 2
    assert s["defence"] == stats.defence * 2
    assert s["bombard"] == stats.bombard * 2


def test_compute_squadron_strength_damaged_halves_attack_defence(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    sid = create_squadron(conn, fid, p1, "Capitals", "capital", "line_of_battle", 100)
    h1 = create_hull(conn, p1, "CAP-001", "capital", 100, fid, sid, 0)
    h2 = create_hull(conn, p1, "CAP-002", "capital", 100, fid, sid, 0)
    mark_hull_damaged(conn, h1)
    conn.commit()
    s = compute_squadron_strength(conn, sid)
    stats = HULL_STATS["capital"]
    # h1 damaged: attack//2, defence//2; h2 active: full
    assert s["attack"] == stats.attack // 2 + stats.attack
    assert s["defence"] == stats.defence // 2 + stats.defence
    # bombard unaffected by damage
    assert s["bombard"] == stats.bombard * 2


def test_compute_squadron_strength_destroyed_excluded(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    sid = create_squadron(conn, fid, p1, "Capitals", "capital", "line_of_battle", 100)
    h1 = create_hull(conn, p1, "CAP-001", "capital", 100, fid, sid, 0)
    create_hull(conn, p1, "CAP-002", "capital", 100, fid, sid, 0)
    mark_hull_destroyed(conn, h1)
    conn.commit()
    s = compute_squadron_strength(conn, sid)
    stats = HULL_STATS["capital"]
    assert s["attack"] == stats.attack      # only one hull
    assert s["bombard"] == stats.bombard


def test_compute_empty_squadron_is_zero(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    sid = create_squadron(conn, fid, p1, "Empty", "capital", "line_of_battle", 100)
    conn.commit()
    s = compute_squadron_strength(conn, sid)
    assert s == {"attack": 0, "bombard": 0, "defence": 0}


# ---------------------------------------------------------------------------
# Hull
# ---------------------------------------------------------------------------

def test_create_hull(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    hid = create_hull(conn, p1, "CAP-001", "capital", 100, fid, None, 0)
    conn.commit()
    hulls = get_hulls_in_fleet(conn, fid)
    assert len(hulls) == 1
    assert hulls[0].hull_id == hid
    assert hulls[0].hull_type == "capital"
    assert hulls[0].status == "active"


def test_get_hulls_in_system(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    h1 = create_hull(conn, p1, "CAP-001", "capital", 100, fid, None, 0)
    create_hull(conn, p1, "CAP-002", "capital", 999, fid, None, 0)
    conn.commit()
    hulls = get_hulls_in_system(conn, 100)
    assert len(hulls) == 1
    assert hulls[0].hull_id == h1


def test_mark_hull_damaged(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    hid = create_hull(conn, p1, "CAP-001", "capital", 100, fid, None, 0)
    mark_hull_damaged(conn, hid)
    conn.commit()
    from starscape5.game.fleet import get_hull
    assert get_hull(conn, hid).status == "damaged"


def test_mark_hull_destroyed_excluded_from_fleet_query(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    h1 = create_hull(conn, p1, "CAP-001", "capital", 100, fid, None, 0)
    h2 = create_hull(conn, p1, "CAP-002", "capital", 100, fid, None, 0)
    mark_hull_destroyed(conn, h1)
    conn.commit()
    hulls = get_hulls_in_fleet(conn, fid)
    assert len(hulls) == 1
    assert hulls[0].hull_id == h2


# ---------------------------------------------------------------------------
# Admiral
# ---------------------------------------------------------------------------

def test_generate_tactical_factor_range():
    stub = WorldStub(seed=42)
    sp = stub.get_species(1)
    rng = Random(42)
    for _ in range(200):
        tf = generate_tactical_factor(sp, rng)
        assert -3 <= tf <= 3


def test_generate_tactical_factor_deterministic():
    stub = WorldStub(seed=42)
    sp = stub.get_species(5)  # Skharri — mean_bonus 0.5
    tf1 = generate_tactical_factor(sp, Random(99))
    tf2 = generate_tactical_factor(sp, Random(99))
    assert tf1 == tf2


def test_high_adaptability_skews_positive():
    """High-adaptability species should average above 0 over many rolls."""
    stub = WorldStub(seed=42)
    sp = stub.get_species(1)
    # Override with high adaptability manually via dataclass replace
    from dataclasses import replace
    high_sp = replace(sp, adaptability=0.9)
    rng = Random(7)
    scores = [generate_tactical_factor(high_sp, rng) for _ in range(500)]
    assert sum(scores) / len(scores) > 0


def test_admiral_generation_params_all_species():
    for species_id in range(1, 12):
        params = ADMIRAL_GENERATION_PARAMS.get(species_id)
        assert params is not None, f"Missing params for species {species_id}"
        assert "mean_bonus" in params and "spread_factor" in params


def test_create_admiral_links_fleet(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    aid = create_admiral(conn, p1, "Kreth-Vaa", 2, fid, 0)
    conn.commit()
    adm = get_fleet_admiral(conn, fid)
    assert adm is not None
    assert adm.admiral_id == aid
    assert adm.tactical_factor == 2


def test_get_fleet_admiral_none_when_unassigned(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    conn.commit()
    assert get_fleet_admiral(conn, fid) is None


def test_transfer_command(two_polities):
    conn, p1, _ = two_polities
    f1 = create_fleet(conn, p1, "Fleet A", 100)
    f2 = create_fleet(conn, p1, "Fleet B", 100)
    create_admiral(conn, p1, "Kreth-Vaa", 1, f1, 0)
    conn.commit()
    transfer_command(conn, f1, f2)
    conn.commit()
    assert get_fleet_admiral(conn, f1) is None
    assert get_fleet_admiral(conn, f2) is not None


def test_get_senior_admiral_picks_lowest_id(two_polities):
    conn, p1, _ = two_polities
    f1 = create_fleet(conn, p1, "Fleet A", 100)
    f2 = create_fleet(conn, p1, "Fleet B", 100)
    a1 = create_admiral(conn, p1, "Senior", 0, f1, 0)
    a2 = create_admiral(conn, p1, "Junior", 1, f2, 0)
    conn.commit()
    senior = get_senior_admiral(conn, p1, [f1, f2])
    assert senior is not None
    assert senior.admiral_id == min(a1, a2)


def test_commission_on_demand(two_polities):
    conn, p1, _ = two_polities
    fid = create_fleet(conn, p1, "Fleet", 100)
    conn.commit()
    stub = WorldStub(seed=42)
    sp = stub.get_species(1)
    gen = NameGenerator(species_id=1)
    aid = commission_on_demand(conn, p1, fid, sp, tick=5,
                               rng=Random(42), name_gen=gen)
    conn.commit()
    assert isinstance(aid, int)
    adm = get_fleet_admiral(conn, fid)
    assert adm is not None
    assert adm.created_tick == 5
    assert -3 <= adm.tactical_factor <= 3


# ---------------------------------------------------------------------------
# Ground forces
# ---------------------------------------------------------------------------

def test_create_army(two_polities):
    conn, p1, _ = two_polities
    fid = create_ground_force(conn, p1, "1st Army", "army",
                               system_id=100, body_id=1001, created_tick=0)
    conn.commit()
    f = get_ground_force(conn, fid)
    assert f.unit_type == "army"
    assert f.strength == 4   # starting strength
    assert f.max_strength == 6


def test_create_garrison(two_polities):
    conn, p1, _ = two_polities
    fid = create_ground_force(conn, p1, "Garrison Alpha", "garrison",
                               system_id=100, body_id=1001, created_tick=0)
    conn.commit()
    f = get_ground_force(conn, fid)
    assert f.max_strength == 4  # garrison cap


def test_apply_strength_delta_clamps(two_polities):
    conn, p1, _ = two_polities
    fid = create_ground_force(conn, p1, "Army", "army", 100, 1001, 0)
    apply_strength_delta(conn, fid, delta=10, tick=1)  # would exceed max_strength
    conn.commit()
    assert get_ground_force(conn, fid).strength == 6

    apply_strength_delta(conn, fid, delta=-20, tick=2)  # would go below 0
    conn.commit()
    assert get_ground_force(conn, fid).strength == 0


def test_apply_strength_delta_normal(two_polities):
    conn, p1, _ = two_polities
    fid = create_ground_force(conn, p1, "Army", "army", 100, 1001, 0)
    apply_strength_delta(conn, fid, delta=-2, tick=1)
    conn.commit()
    assert get_ground_force(conn, fid).strength == 2


def test_embark_disembark(two_polities):
    conn, p1, _ = two_polities
    fleet_id = create_fleet(conn, p1, "Fleet", 100)
    hull_id = create_hull(conn, p1, "TRP-001", "troop", 100, fleet_id, None, 0)
    force_id = create_ground_force(conn, p1, "1st Marines", "army", 100, 1001, 0,
                                   marine_designated=1)
    conn.commit()

    embark_force(conn, force_id, hull_id)
    conn.commit()
    f = get_ground_force(conn, force_id)
    assert f.embarked_hull_id == hull_id
    assert f.system_id is None

    disembark_force(conn, force_id, system_id=200, body_id=2001, tick=5)
    conn.commit()
    f = get_ground_force(conn, force_id)
    assert f.embarked_hull_id is None
    assert f.system_id == 200
    assert f.body_id == 2001


def test_get_ground_forces_at_body(two_polities):
    conn, p1, p2 = two_polities
    create_ground_force(conn, p1, "1st Army", "army", 100, 1001, 0)
    create_ground_force(conn, p2, "Garrison", "garrison", 100, 1001, 0)
    create_ground_force(conn, p1, "2nd Army", "army", 100, 9999, 0)
    conn.commit()
    forces = get_ground_forces_at_body(conn, 1001)
    assert len(forces) == 2
    assert all(f.body_id == 1001 for f in forces)


def test_tick_refit(two_polities):
    conn, p1, _ = two_polities
    from starscape5.game.ground import set_refit
    fid = create_ground_force(conn, p1, "Army", "army", 100, 1001, 0)
    set_refit(conn, fid, 3)
    conn.commit()
    remaining = tick_refit(conn, fid)
    assert remaining == 2


# ---------------------------------------------------------------------------
# Smoke test matching implementation_plan.md
# ---------------------------------------------------------------------------

def test_m4_smoke(two_polities):
    conn, p1, _ = two_polities
    fleet_id = create_fleet(conn, p1, "KRT-FL-0001", system_id=100)
    sq = create_squadron(conn, fleet_id, p1, "First Claw",
                         "capital", "line_of_battle", 100)
    for i in range(2):
        create_hull(conn, p1, f"KRT-CAP-{i:04}", "capital",
                    100, fleet_id, sq, created_tick=0)
    conn.commit()

    hulls = get_hulls_in_fleet(conn, fleet_id)
    maint = sum(HULL_STATS[h.hull_type].maint_per_tick for h in hulls)
    print(f"\n{len(hulls)} hulls, maintenance {maint} RU/tick")
    assert len(hulls) == 2
    assert maint == pytest.approx(4.0)  # 2 × 2.0
