#!/usr/bin/env python3
"""Example script — demonstrates using the shared db helper."""

from starscape5.db import get_connection, init_db


def main() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("INSERT INTO events (name) VALUES (?)", ("hello",))
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM events").fetchall()
    for row in rows:
        print(dict(row))


if __name__ == "__main__":
    main()
