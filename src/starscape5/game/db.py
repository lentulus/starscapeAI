"""Game database helpers.

game.db holds all simulation state.  It is never shared with the world layer.

Typical usage:

    conn = open_game(":memory:")      # tests
    conn = open_game(path)            # production

    init_schema(conn)                 # idempotent; safe to call at startup
"""

import sqlite3
from pathlib import Path


_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / "sql" / "schema_game.sql"


def open_game(path: Path | str) -> sqlite3.Connection:
    """Open (or create) game.db and return a connection.

    WAL mode and foreign keys are enabled here; init_schema() will also set
    them via PRAGMA, but enabling early ensures they are active for the
    connection before any DDL runs.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Create all game.db tables and indexes if they do not exist.

    Idempotent: every statement uses IF NOT EXISTS, so safe to call at each
    startup or after a crash resume.

    Args:
        conn: An open game.db connection from open_game().
        schema_path: Override the default sql/schema_game.sql path (useful in
            tests that ship a minimal schema fixture).
    """
    if schema_path is None:
        schema_path = _SCHEMA_PATH
    sql = schema_path.read_text()
    conn.executescript(sql)
