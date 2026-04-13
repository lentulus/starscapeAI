"""Economy helpers — pure production formula and WorldPotential cache writes.

The full Economy phase (M6) builds on these functions.  This module contains
only the pieces needed at game initialisation.
"""

from __future__ import annotations

import sqlite3


# ---------------------------------------------------------------------------
# Production formula (pure functions — no DB)
# ---------------------------------------------------------------------------

_CONTROL_MULTIPLIERS: dict[str, float] = {
    "outpost":    0.20,  # extractive presence, not full development
    "colony":     0.55,  # growing settlement, active resource flow
    "controlled": 1.00,
    "contested":  0.35,  # disruption, not collapse
}

_DEV_MULTIPLIERS: dict[int, float] = {
    0: 0.5,
    1: 0.7,
    2: 0.9,
    3: 1.0,
    4: 1.2,
    5: 1.5,
}


def compute_ru_production(
    world_potential: int,
    control_state: str,
    development_level: int,
) -> float:
    """Return RU/tick for one presence.

    Formula: world_potential × control_multiplier × development_multiplier
    (game.md §Economy).
    """
    cm = _CONTROL_MULTIPLIERS.get(control_state, 0.0)
    dm = _DEV_MULTIPLIERS.get(development_level, 1.0)
    return world_potential * cm * dm


# ---------------------------------------------------------------------------
# WorldPotential cache (game.db writes)
# ---------------------------------------------------------------------------

def create_world_potential_cache(
    conn: sqlite3.Connection,
    body_id: int,
    system_id: int,
    world_potential: int,
    has_gas_giant: int,
    has_ocean: int,
) -> None:
    """Upsert one WorldPotential row.  Safe to call multiple times."""
    conn.execute(
        """
        INSERT INTO WorldPotential
            (body_id, system_id, world_potential, has_gas_giant, has_ocean)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(body_id) DO UPDATE SET
            world_potential = excluded.world_potential,
            has_gas_giant   = excluded.has_gas_giant,
            has_ocean       = excluded.has_ocean
        """,
        (body_id, system_id, world_potential, has_gas_giant, has_ocean),
    )


def get_world_potential(
    conn: sqlite3.Connection, body_id: int
) -> int | None:
    """Return cached world_potential for a body, or None if not cached."""
    row = conn.execute(
        "SELECT world_potential FROM WorldPotential WHERE body_id = ?",
        (body_id,),
    ).fetchone()
    return row["world_potential"] if row else None


def get_best_body_in_system(
    conn: sqlite3.Connection, system_id: int
) -> int | None:
    """Return body_id with the highest world_potential in the cached system.

    Returns None if the system has no WorldPotential rows yet.
    """
    row = conn.execute(
        """
        SELECT body_id FROM WorldPotential
        WHERE  system_id = ?
        ORDER  BY world_potential DESC
        LIMIT  1
        """,
        (system_id,),
    ).fetchone()
    return row["body_id"] if row else None
