"""M0 smoke test — game.db schema.

Verifies that init_schema() creates every expected table and index in an
in-memory database.  No external files or the real starscape.db are needed.
"""

import sqlite3
import pytest
from starscape5.game.db import open_game, init_schema


EXPECTED_TABLES = {
    "GameState",
    "WorldPotential",
    "SystemIntelligence",
    "Polity",
    "ContactRecord",
    "WarRecord",
    "SystemPresence",
    "Fleet",
    "Squadron",
    "Hull",
    "Admiral",
    "GroundForce",
    "BuildQueue",
    "RepairQueue",
    "SystemEconomy",
    "NamePool",
    "PlaceName",
    "GameEvent",
    "JumpRoute",
}

EXPECTED_INDEXES = {
    "idx_worldpotential_system",
    "idx_intel_polity",
    "idx_presence_polity",
    "idx_presence_system",
    "idx_fleet_system",
    "idx_fleet_polity",
    "idx_squadron_fleet",
    "idx_hull_fleet",
    "idx_hull_system",
    "idx_hull_squadron",
    "idx_groundforce_system",
    "idx_economy_tick",
    "idx_namepool_available",
    "idx_event_tick",
    "idx_event_type",
    "idx_jumproute_from",
    "idx_jumproute_to",
}


@pytest.fixture
def game_conn():
    conn = open_game(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r["name"] for r in rows}


def _indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    # exclude auto-generated sqlite_ internal indexes
    return {r["name"] for r in rows if not r["name"].startswith("sqlite_")}


def test_all_tables_created(game_conn):
    missing = EXPECTED_TABLES - _tables(game_conn)
    assert not missing, f"Tables missing from schema: {missing}"


def test_no_unexpected_tables(game_conn):
    extra = _tables(game_conn) - EXPECTED_TABLES
    assert not extra, f"Unexpected tables in schema: {extra}"


def test_all_indexes_created(game_conn):
    missing = EXPECTED_INDEXES - _indexes(game_conn)
    assert not missing, f"Indexes missing from schema: {missing}"


def test_foreign_keys_enforced(game_conn):
    """A FK violation must raise IntegrityError when FK pragma is on."""
    with pytest.raises(sqlite3.IntegrityError):
        # Hull.fleet_id REFERENCES Fleet(fleet_id) — referencing a non-existent fleet
        game_conn.execute(
            "INSERT INTO Hull (fleet_id, tick, seq, polity_id, hull_type, status, created_tick) "
            "VALUES (9999, 0, 0, 1, 'escort', 'active', 0)"
        )
        game_conn.commit()


def test_gamestate_singleton_constraint(game_conn):
    """GameState CHECK(state_id = 1) must reject any row with id != 1."""
    game_conn.execute(
        "INSERT INTO GameState "
        "(state_id, started_at, last_committed_at) "
        "VALUES (1, 'now', 'now')"
    )
    game_conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        game_conn.execute(
            "INSERT INTO GameState "
            "(state_id, started_at, last_committed_at) "
            "VALUES (2, 'now', 'now')"
        )
        game_conn.commit()


def test_init_schema_idempotent(game_conn):
    """Calling init_schema() a second time must not raise."""
    init_schema(game_conn)  # second call — all IF NOT EXISTS
