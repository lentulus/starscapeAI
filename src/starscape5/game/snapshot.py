"""GameStateSnapshot — a read-only view of game state for the decision engine.

Built once at the start of the Decision phase from live DB data, then passed
as a pure Python object to all scoring functions.  No DB connections inside
the decision/scoring layer.

Fields are deliberately flat: the snapshot is not a query object — it is the
data the decision engine needs, pre-extracted so scoring functions can be pure
and testable without a database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class PolitySnapshot:
    polity_id: int
    species_id: int
    capital_system_id: int | None
    treasury_ru: float
    expansionism: float
    aggression: float
    risk_appetite: float
    jump_level: int              # current scout jump range (pc); upgradeable
    at_war_with: list[int]       # polity_ids this polity is at war with
    in_contact_with: list[int]   # all contacted polity_ids (war or peace)


@dataclass
class PresenceSnapshot:
    presence_id: int
    polity_id: int
    system_id: int
    body_id: int
    control_state: str     # 'outpost'|'colony'|'controlled'|'contested'
    development_level: int
    has_shipyard: int
    world_potential: int   # 0 if not in WorldPotential yet


@dataclass
class FleetSnapshot:
    fleet_id: int
    polity_id: int
    system_id: int | None
    status: str            # 'active'|'in_transit'|'destroyed'
    hull_count: int        # non-destroyed hulls
    has_scout: bool
    has_colony_transport: bool
    has_troop: bool
    jump_range: int        # min jump across jumping hulls; 0 if none


@dataclass
class IntelSnapshot:
    system_id: int
    polity_id: int
    knowledge_tier: str    # 'passive'|'visited'
    world_potential: int | None
    habitable: int | None  # 1/0/None


@dataclass
class GameStateSnapshot:
    """Full read-only snapshot for one polity's decision turn."""
    tick: int
    polity: PolitySnapshot
    presences: list[PresenceSnapshot]
    fleets: list[FleetSnapshot]       # only this polity's fleets
    known_systems: list[IntelSnapshot]
    enemy_systems: set[int]           # systems known to have hostile forces


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_snapshot(
    conn: sqlite3.Connection,
    polity_id: int,
    tick: int,
) -> GameStateSnapshot:
    """Construct a GameStateSnapshot for polity_id at the current tick."""

    # Polity row
    p = conn.execute(
        "SELECT * FROM Polity WHERE polity_id = ?", (polity_id,)
    ).fetchone()

    contacts = conn.execute(
        """
        SELECT polity_a_id, polity_b_id, at_war
        FROM   ContactRecord
        WHERE  polity_a_id = ? OR polity_b_id = ?
        """,
        (polity_id, polity_id),
    ).fetchall()
    at_war_with = [
        (r["polity_b_id"] if r["polity_a_id"] == polity_id else r["polity_a_id"])
        for r in contacts if r["at_war"]
    ]
    in_contact_with = [
        (r["polity_b_id"] if r["polity_a_id"] == polity_id else r["polity_a_id"])
        for r in contacts
    ]

    polity_jump_level = p["jump_level"] if "jump_level" in p.keys() else 10
    polity = PolitySnapshot(
        polity_id=polity_id,
        species_id=p["species_id"],
        capital_system_id=p["capital_system_id"],
        treasury_ru=p["treasury_ru"],
        expansionism=p["expansionism"],
        aggression=p["aggression"],
        risk_appetite=p["risk_appetite"],
        jump_level=polity_jump_level,
        at_war_with=at_war_with,
        in_contact_with=in_contact_with,
    )

    # Presences
    prows = conn.execute(
        "SELECT sp.*, COALESCE(wp.world_potential, 0) AS wp_val "
        "FROM SystemPresence sp "
        "LEFT JOIN WorldPotential wp ON wp.body_id = sp.body_id "
        "WHERE sp.polity_id = ?",
        (polity_id,),
    ).fetchall()
    presences = [
        PresenceSnapshot(
            presence_id=r["presence_id"],
            polity_id=polity_id,
            system_id=r["system_id"],
            body_id=r["body_id"],
            control_state=r["control_state"],
            development_level=r["development_level"],
            has_shipyard=r["has_shipyard"],
            world_potential=r["wp_val"],
        )
        for r in prows
    ]

    # Fleets + hull composition
    frows = conn.execute(
        "SELECT * FROM Fleet WHERE polity_id = ? AND status != 'destroyed'",
        (polity_id,),
    ).fetchall()

    from .constants import HULL_STATS
    fleets = []
    for fr in frows:
        hulls = conn.execute(
            "SELECT hull_type FROM Hull "
            "WHERE fleet_id = ? AND status NOT IN ('destroyed')",
            (fr["fleet_id"],),
        ).fetchall()
        types = [h["hull_type"] for h in hulls]
        jump_vals = [
            max(HULL_STATS[t].jump, polity_jump_level) if t == "scout" else HULL_STATS[t].jump
            for t in types if t in HULL_STATS and HULL_STATS[t].jump > 0
        ]
        fleets.append(FleetSnapshot(
            fleet_id=fr["fleet_id"],
            polity_id=polity_id,
            system_id=fr["system_id"],
            status=fr["status"],
            hull_count=len(types),
            has_scout="scout" in types,
            has_colony_transport="colony_transport" in types,
            has_troop="troop" in types,
            jump_range=min(jump_vals) if jump_vals else 0,
        ))

    # Known systems (intel)
    irows = conn.execute(
        "SELECT * FROM SystemIntelligence WHERE polity_id = ?",
        (polity_id,),
    ).fetchall()
    known_systems = [
        IntelSnapshot(
            system_id=r["system_id"],
            polity_id=polity_id,
            knowledge_tier=r["knowledge_tier"],
            world_potential=r["world_potential"],
            habitable=r["habitable"],
        )
        for r in irows
    ]

    # Enemy system set: systems where at-war polities have active fleets
    enemy_systems: set[int] = set()
    if at_war_with:
        placeholders = ",".join("?" * len(at_war_with))
        rows = conn.execute(
            f"SELECT DISTINCT system_id FROM Fleet "
            f"WHERE polity_id IN ({placeholders}) AND status = 'active' AND system_id IS NOT NULL",
            at_war_with,
        ).fetchall()
        enemy_systems = {r["system_id"] for r in rows}

    return GameStateSnapshot(
        tick=tick,
        polity=polity,
        presences=presences,
        fleets=fleets,
        known_systems=known_systems,
        enemy_systems=enemy_systems,
    )
