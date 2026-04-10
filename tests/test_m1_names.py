"""M1 smoke tests — name generation.

All tests run without starscape.db.  DB-backed tests use an in-memory game.db
with a small NamePool fixture.
"""

import sqlite3
import pytest

from starscape5.game.names import (
    NameGenerator,
    species_prefix,
    format_code,
)
from starscape5.game.db import open_game, init_schema


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

def test_species_prefix_known():
    assert species_prefix(1) == "KRT"
    assert species_prefix(11) == "HUM"
    assert species_prefix(9) == "NHV"


def test_species_prefix_unknown():
    assert species_prefix(99) == "UNK"


def test_format_code():
    assert format_code("HUM", "FL", 1) == "HUM-FL-0001"
    assert format_code("HUM", "FL", 3) == "HUM-FL-0003"
    assert format_code("KRT", "ADM", 42) == "KRT-ADM-0042"
    assert format_code("NHV", "SYS", 1000) == "NHV-SYS-1000"


# ---------------------------------------------------------------------------
# Code-fallback mode (db_conn=None)
# ---------------------------------------------------------------------------

def test_fleet_fallback():
    gen = NameGenerator(species_id=11)
    name = gen.fleet("Humanity", 1)
    assert name == "HUM-FL-0001"


def test_admiral_fallback():
    gen = NameGenerator(species_id=1)
    name = gen.admiral(42)
    assert name == "KRT-ADM-0042"


def test_system_fallback():
    gen = NameGenerator(species_id=2)
    name = gen.system(system_id=5000, sequence=7)
    assert name == "VSH-SYS-0007"


def test_body_fallback():
    gen = NameGenerator(species_id=3)
    name = gen.body(body_id=10000, sequence=3)
    assert name == "KRA-BOD-0003"


def test_war_fallback():
    gen = NameGenerator(species_id=5)
    name = gen.war("Skharri", "Kreeth", tick=52)
    assert name == "SKH-WAR-0052"


def test_hull_always_code():
    """hull() must return a code even when a DB connection is available."""
    gen = NameGenerator(species_id=11)
    name = gen.hull("capital", 7)
    assert "HUM" in name
    assert "0007" in name


# ---------------------------------------------------------------------------
# DB-backed mode
# ---------------------------------------------------------------------------

@pytest.fixture
def pool_conn():
    """In-memory game.db seeded with a small NamePool."""
    conn = open_game(":memory:")
    init_schema(conn)
    # Seed a handful of names for species_id=11 (Human)
    names = [
        (11, "person",  "Chen Wei"),
        (11, "person",  "Amara Okonkwo"),
        (11, "fleet",   "First Fleet"),
        (11, "fleet",   "Far Reach"),
        (11, "system",  "New Carthage"),
        (11, "body",    "Prospero Deep"),
        (11, "war",     "The First Sol War"),
    ]
    conn.executemany(
        "INSERT INTO NamePool (species_id, name_type, name) VALUES (?, ?, ?)",
        names,
    )
    conn.commit()
    yield conn
    conn.close()


def test_admiral_draws_from_pool(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    name = gen.admiral(sequence=1)
    assert name in {"Chen Wei", "Amara Okonkwo"}


def test_fleet_draws_from_pool(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    name = gen.fleet("Humanity", sequence=1)
    assert name in {"First Fleet", "Far Reach"}


def test_pool_marked_used(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    first = gen.fleet("Humanity", sequence=1)
    second = gen.fleet("Humanity", sequence=2)
    # Two distinct fleet names in pool — both drawn, never the same
    assert first != second


def test_pool_exhaustion_falls_back(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    # Draw all 2 fleet names
    gen.fleet("Humanity", sequence=1)
    gen.fleet("Humanity", sequence=2)
    # Third draw must fall back to code
    fallback = gen.fleet("Humanity", sequence=3)
    assert fallback == "HUM-FL-0003"


def test_admiral_pool_exhaustion_falls_back(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    gen.admiral(sequence=1)  # Chen Wei
    gen.admiral(sequence=2)  # Amara Okonkwo
    # Pool exhausted
    fallback = gen.admiral(sequence=3)
    assert fallback == "HUM-ADM-0003"


def test_war_draws_from_pool(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    name = gen.war("A", "B", tick=1)
    assert name == "The First Sol War"


def test_system_draws_from_pool(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    name = gen.system(system_id=1, sequence=1)
    assert name == "New Carthage"


def test_body_draws_from_pool(pool_conn):
    gen = NameGenerator(species_id=11, db_conn=pool_conn)
    name = gen.body(body_id=1, sequence=1)
    assert name == "Prospero Deep"


def test_unknown_species_uses_unk_prefix():
    gen = NameGenerator(species_id=99)
    assert gen.fleet("Unknown", 1) == "UNK-FL-0001"
