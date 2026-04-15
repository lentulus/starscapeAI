"""M12 — WorldFacadeImpl tests.

All tests skip gracefully when starscape.db is not mounted (CI, laptop without
external drive).  They are integration tests against the real stellar catalog.

Run locally with the external drive connected:
    uv run pytest tests/test_m12_world.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from starscape5.world.db import open_world_ro, open_world_rw
from starscape5.world.facade import WorldFacade, BodyData, SpeciesData
from starscape5.world.impl import WorldFacadeImpl
from starscape5.game.db import open_game, init_schema


STARSCAPE_DB = Path("/Volumes/Data/starscape4/starscape.db")

_db_available = STARSCAPE_DB.exists()
skip_no_db = pytest.mark.skipif(
    not _db_available, reason="starscape.db not mounted"
)

# Sol's system_id in the real catalog (star_id=1 → system_id=1030192).
# Use this for tests that need a system with pre-existing bodies.
SOL_SYSTEM_ID = 1030192
# A system with stars but no bodies generated yet (binary, system_id=1).
UNGENERATED_SYSTEM_ID = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ro_conn():
    if not _db_available:
        pytest.skip("starscape.db not mounted")
    conn = open_world_ro(STARSCAPE_DB)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def world(ro_conn):
    return WorldFacadeImpl(ro_conn)


@pytest.fixture
def game_conn():
    conn = open_game(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_satisfies_world_facade_protocol(self):
        """WorldFacadeImpl must satisfy the WorldFacade protocol at import time."""
        instance = object.__new__(WorldFacadeImpl)
        assert isinstance(instance, WorldFacade)


# ---------------------------------------------------------------------------
# Position queries
# ---------------------------------------------------------------------------

@skip_no_db
class TestPositions:
    def test_get_star_position_returns_system_position(self, world):
        pos = world.get_star_position(1)
        assert pos.system_id == 1
        # Coordinates are integer milliparsecs; real values can be large
        assert isinstance(pos.x_mpc, float)
        assert isinstance(pos.y_mpc, float)
        assert isinstance(pos.z_mpc, float)

    def test_unknown_system_raises_key_error(self, world):
        with pytest.raises(KeyError):
            world.get_star_position(999_999_999)

    def test_distance_pc_is_non_negative(self, world):
        # Distance between a system and itself is 0
        assert world.get_distance_pc(1, 1) == pytest.approx(0.0, abs=1e-9)

    def test_distance_pc_between_different_systems(self, world):
        d = world.get_distance_pc(1, 2)
        assert d > 0.0

    def test_distance_symmetric(self, world):
        assert world.get_distance_pc(1, 2) == pytest.approx(
            world.get_distance_pc(2, 1), rel=1e-9
        )


# ---------------------------------------------------------------------------
# Neighbor queries
# ---------------------------------------------------------------------------

@skip_no_db
class TestNeighbors:
    def test_within_20pc_returns_list(self, world):
        neighbors = world.get_systems_within_parsecs(1, 20.0)
        assert isinstance(neighbors, list)

    def test_self_not_in_neighbors(self, world):
        neighbors = world.get_systems_within_parsecs(1, 20.0)
        assert 1 not in neighbors

    def test_neighbors_within_range(self, world):
        """Every returned system is actually within the requested parsec radius."""
        neighbors = world.get_systems_within_parsecs(1, 5.0)
        for sid in neighbors[:50]:  # sample first 50 to keep test fast
            d = world.get_distance_pc(1, sid)
            assert d <= 5.0 + 1e-9, f"system {sid} at {d:.3f} pc claimed within 5 pc"

    def test_tight_radius_fewer_neighbors(self, world):
        n_small = world.get_systems_within_parsecs(1, 1.0)
        n_large = world.get_systems_within_parsecs(1, 5.0)
        assert len(n_small) <= len(n_large)

    def test_zero_radius_returns_empty(self, world):
        assert world.get_systems_within_parsecs(1, 0.0) == []


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------

@skip_no_db
class TestBodies:
    def test_get_bodies_returns_list(self, world):
        bodies = world.get_bodies(SOL_SYSTEM_ID)
        assert isinstance(bodies, list)

    def test_bodies_are_body_data(self, world):
        bodies = world.get_bodies(SOL_SYSTEM_ID)
        for b in bodies:
            assert isinstance(b, BodyData)

    def test_bodies_have_positive_world_potential(self, world):
        bodies = world.get_bodies(SOL_SYSTEM_ID)
        assert bodies, "Sol should have bodies in the DB"
        for b in bodies:
            assert b.world_potential >= 1

    def test_body_type_vocabulary(self, world):
        bodies = world.get_bodies(SOL_SYSTEM_ID)
        valid_types = {"gas_giant", "rocky", "belt", "terrestrial", "ice"}
        for b in bodies:
            assert b.body_type in valid_types, f"unexpected body_type={b.body_type!r}"

    def test_planet_class_vocabulary(self, world):
        bodies = world.get_bodies(SOL_SYSTEM_ID)
        valid_classes = {"gas_giant", "rocky", "terrestrial"}
        for b in bodies:
            assert b.planet_class in valid_classes, (
                f"unexpected planet_class={b.planet_class!r}"
            )

    def test_gas_giant_flag_sol(self, world):
        flag = world.get_gas_giant_flag(SOL_SYSTEM_ID)
        # Sol has Jupiter / Saturn → should be True
        assert flag is True

    def test_gas_giant_flag_ungenerated_is_none(self, world):
        flag = world.get_gas_giant_flag(UNGENERATED_SYSTEM_ID)
        assert flag is None

    def test_ocean_flag_is_bool_or_none(self, world):
        flag = world.get_ocean_flag(SOL_SYSTEM_ID)
        assert flag is True or flag is False or flag is None


# ---------------------------------------------------------------------------
# resolve_system
# ---------------------------------------------------------------------------

@skip_no_db
class TestResolveSystem:
    def test_resolve_populates_world_potential(self, game_conn):
        """resolve_system on Sol writes WorldPotential rows to game.db."""
        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)
        try:
            bodies = world.resolve_system(SOL_SYSTEM_ID, game_conn)
        finally:
            ro_conn.close()

        assert bodies, "Sol should have bodies in the DB"
        rows = game_conn.execute(
            "SELECT * FROM WorldPotential WHERE system_id = ?",
            (SOL_SYSTEM_ID,),
        ).fetchall()
        assert len(rows) >= 1, "WorldPotential not populated after resolve_system"
        for r in rows:
            assert r["world_potential"] >= 1

    def test_resolve_idempotent(self, game_conn):
        """Calling resolve_system twice must not raise or duplicate rows."""
        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)
        try:
            world.resolve_system(SOL_SYSTEM_ID, game_conn)
            world.resolve_system(SOL_SYSTEM_ID, game_conn)  # must be no-op
        finally:
            ro_conn.close()

        rows = game_conn.execute(
            "SELECT COUNT(*) AS cnt FROM WorldPotential WHERE system_id = ?",
            (SOL_SYSTEM_ID,),
        ).fetchone()
        body_count = game_conn.execute(
            "SELECT COUNT(DISTINCT body_id) AS cnt FROM WorldPotential WHERE system_id = ?",
            (SOL_SYSTEM_ID,),
        ).fetchone()
        # Idempotent: upsert means no duplicates
        assert rows["cnt"] == body_count["cnt"]

    def test_resolve_ungenerated_returns_empty_without_rw(self, game_conn):
        """resolve_system on a system with no bodies and no rw_conn returns []."""
        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)  # no rw_conn
        try:
            bodies = world.resolve_system(UNGENERATED_SYSTEM_ID, game_conn)
        finally:
            ro_conn.close()
        assert bodies == []

    def test_resolve_returns_body_data(self, game_conn):
        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)
        try:
            bodies = world.resolve_system(SOL_SYSTEM_ID, game_conn)
        finally:
            ro_conn.close()
        assert bodies
        for b in bodies:
            assert isinstance(b, BodyData)


# ---------------------------------------------------------------------------
# Species (fallback when table empty)
# ---------------------------------------------------------------------------

@skip_no_db
class TestSpecies:
    def test_get_species_returns_species_data(self, world):
        sp = world.get_species(1)
        assert isinstance(sp, SpeciesData)
        assert sp.species_id == 1

    def test_get_species_fallback_for_missing(self, world):
        """Missing species_id returns synthetic fallback, not KeyError."""
        sp = world.get_species(999_999)
        assert isinstance(sp, SpeciesData)
        assert sp.species_id == 999_999

    def test_check_habitability_returns_bool(self, world):
        # body_id 3 is Earth in Sol system (first BodyMutable row)
        result = world.check_habitability(3, 1)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Smoke test: init_game with WorldFacadeImpl
# ---------------------------------------------------------------------------

@skip_no_db
class TestInitGameSmoke:
    def test_world_potential_rows_populated_for_homeworlds(self, game_conn):
        """init_game with WorldFacadeImpl.

        Homeworld system IDs start at 1001.  These are real catalog IDs with
        no bodies generated yet and no rw_conn, so resolve_system returns [].
        init_game then creates synthetic WorldPotential rows via the fallback
        path.  This test verifies that path works end-to-end.
        """
        from starscape5.game.init_game import init_game

        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)  # no rw_conn — triggers [] fallback
        try:
            init_game(game_conn, world)
        finally:
            ro_conn.close()

        rows = game_conn.execute("SELECT * FROM WorldPotential").fetchall()
        assert len(rows) >= 1, "No WorldPotential rows after init_game"
        for r in rows:
            assert r["world_potential"] >= 1

    def test_polities_created(self, game_conn):
        from starscape5.game.init_game import init_game

        ro_conn = open_world_ro(STARSCAPE_DB)
        world = WorldFacadeImpl(ro_conn)
        try:
            init_game(game_conn, world)
        finally:
            ro_conn.close()

        polities = game_conn.execute("SELECT * FROM Polity").fetchall()
        # OB_DATA has 11 species with multiple polities; expect ≥ 11
        assert len(polities) >= 11, f"Expected ≥11 polities, got {len(polities)}"
