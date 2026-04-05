"""Basic db helper tests."""

import sqlite3
from pathlib import Path

import pytest

from starscape5.db import get_connection, init_db


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).parent.parent / "sql" / "schema.sql"
    init_db(db_path=db_path, schema_path=schema_path)
    return db_path


def test_insert_and_select(tmp_db):
    with get_connection(tmp_db) as conn:
        conn.execute("INSERT INTO events (name) VALUES (?)", ("test_event",))
    with get_connection(tmp_db) as conn:
        row = conn.execute("SELECT name FROM events WHERE name = ?", ("test_event",)).fetchone()
    assert row["name"] == "test_event"
