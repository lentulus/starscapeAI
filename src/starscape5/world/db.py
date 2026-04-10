"""World database helpers.

starscape.db is the static read-only world model.  Nothing in the game
simulation may write to it; the only permitted exception is world/resolver.py
which generates planet/atmosphere data on demand as the zone of knowledge
expands.
"""

import sqlite3
from pathlib import Path


def open_world_ro(path: Path | str) -> sqlite3.Connection:
    """Open starscape.db read-only.

    Uses the URI filename syntax so SQLite refuses any write attempt at the
    driver level.  row_factory is set to sqlite3.Row for named-column access.
    """
    uri = f"file:{Path(path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_world_rw(path: Path | str) -> sqlite3.Connection:
    """Open starscape.db read-write.

    Used exclusively by world/resolver.py for lazy on-demand world generation.
    All other callers must use open_world_ro().
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn
