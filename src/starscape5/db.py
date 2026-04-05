"""Shared SQLite database helpers."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).parent.parent.parent / "data" / "starscape5.db"


@contextmanager
def get_connection(db_path: Path = DB_PATH):
    """Yield an open SQLite connection, closing it when done."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH, schema_path: Path | None = None) -> None:
    """Create tables from sql/schema.sql if they don't exist."""
    if schema_path is None:
        schema_path = Path(__file__).parent.parent.parent / "sql" / "schema.sql"
    with get_connection(db_path) as conn:
        conn.executescript(schema_path.read_text())
