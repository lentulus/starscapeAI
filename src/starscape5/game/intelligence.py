"""System intelligence — per-polity knowledge of systems.

Three knowledge tiers:
  unknown  — no row in SystemIntelligence (absence = ignorance)
  passive  — within 20 pc of a Controlled world; gas_giant and ocean flags only
  visited  — a fleet or scout has entered the system; full world data

Map sharing: polities that have been in contact for 52 weeks without war
receive a one-time full intel exchange.

ContactRecord is TEMPORAL: append-only; all mutations INSERT new rows.
contact_id is the logical entity key; row_id is the physical autoincrement PK.
Use ContactRecord_head view for current state.

peace_weeks is incremented each tick the pair is not at war.
map_shared = 1 once the exchange has fired; never fires twice.
"""

from __future__ import annotations

import sqlite3

from starscape5.world.facade import WorldFacade

_PASSIVE_SCAN_RADIUS_PC: float = 10.0
_PASSIVE_SCAN_LIMIT: int = 20


# ---------------------------------------------------------------------------
# ContactRecord helpers
# ---------------------------------------------------------------------------

def _current_contact_row(conn: sqlite3.Connection, contact_id: int) -> sqlite3.Row:
    """Return the most recent raw row for contact_id."""
    row = conn.execute(
        "SELECT * FROM ContactRecord WHERE contact_id = ? ORDER BY row_id DESC LIMIT 1",
        (contact_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"ContactRecord {contact_id} not found")
    return row


def _insert_contact_row(
    conn: sqlite3.Connection,
    contact_id: int,
    polity_a_id: int,
    polity_b_id: int,
    contact_tick: int,
    contact_system_id: int,
    peace_weeks: int,
    at_war: int,
    map_shared: int,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO ContactRecord
            (contact_id, tick, seq, polity_a_id, polity_b_id,
             contact_tick, contact_system_id, peace_weeks, at_war, map_shared)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (contact_id, tick, seq, polity_a_id, polity_b_id,
         contact_tick, contact_system_id, peace_weeks, at_war, map_shared),
    )


# ---------------------------------------------------------------------------
# Passive scan
# ---------------------------------------------------------------------------

def update_passive_scan(
    conn: sqlite3.Connection,
    polity_id: int,
    world: WorldFacade,
    tick: int,
) -> int:
    """Scan 20 pc around every Controlled presence; upsert passive intel rows.

    Returns the number of new or updated intel rows written.
    """
    presences = conn.execute(
        """
        SELECT DISTINCT system_id FROM SystemPresence_head
        WHERE  polity_id = ? AND control_state IN ('controlled', 'colony')
        """,
        (polity_id,),
    ).fetchall()

    written = 0
    for row in presences:
        origin_id = row["system_id"]
        nearby = world.get_systems_within_parsecs(
            origin_id, _PASSIVE_SCAN_RADIUS_PC, limit=_PASSIVE_SCAN_LIMIT
        )
        for system_id in nearby:
            _upsert_passive(conn, polity_id, system_id, world)
            written += 1
    return written


def _upsert_passive(
    conn: sqlite3.Connection,
    polity_id: int,
    system_id: int,
    world: WorldFacade,
) -> None:
    """Insert or upgrade a passive SystemIntelligence row.

    If a 'visited' row already exists, leave it unchanged (visited > passive).
    """
    existing = conn.execute(
        "SELECT knowledge_tier FROM SystemIntelligence "
        "WHERE polity_id = ? AND system_id = ?",
        (polity_id, system_id),
    ).fetchone()

    if existing and existing["knowledge_tier"] == "visited":
        return  # don't downgrade

    gg_flag = world.get_gas_giant_flag(system_id)
    ocean_flag = world.get_ocean_flag(system_id)

    if existing is None:
        conn.execute(
            """
            INSERT INTO SystemIntelligence
                (polity_id, system_id, knowledge_tier, gas_giant, ocean_body)
            VALUES (?, ?, 'passive', ?, ?)
            """,
            (polity_id, system_id, int(bool(gg_flag)), int(bool(ocean_flag))),
        )
    else:
        conn.execute(
            """
            UPDATE SystemIntelligence
            SET knowledge_tier = 'passive', gas_giant = ?, ocean_body = ?
            WHERE polity_id = ? AND system_id = ?
            """,
            (int(bool(gg_flag)), int(bool(ocean_flag)), polity_id, system_id),
        )


# ---------------------------------------------------------------------------
# Visit recording (full data)
# ---------------------------------------------------------------------------

def record_visit(
    conn: sqlite3.Connection,
    polity_id: int,
    system_id: int,
    world: WorldFacade,
    tick: int,
) -> None:
    """Record a full visit to system_id, populating all intel columns.

    Idempotent: updates last_visit_tick on repeat visits.
    """
    bodies = world.resolve_system(system_id, conn)

    best = max(bodies, key=lambda b: b.world_potential) if bodies else None
    gg_flag = int(any(b.body_type == "gas_giant" for b in bodies))
    ocean_flag = int(any(b.hydrosphere >= 0.5 for b in bodies))
    world_potential = best.world_potential if best else None
    atm_type = best.atm_type if best else None
    surface_temp_k = best.surface_temp_k if best else None
    hydrosphere = best.hydrosphere if best else None

    # Habitability: check best body for polity's species
    habitable = 0
    if best:
        sp_row = conn.execute(
            "SELECT species_id FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
            (polity_id,),
        ).fetchone()
        if sp_row:
            habitable = int(world.check_habitability(best.body_id, sp_row["species_id"]))

    existing = conn.execute(
        "SELECT intel_id, first_visit_tick FROM SystemIntelligence "
        "WHERE polity_id = ? AND system_id = ?",
        (polity_id, system_id),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO SystemIntelligence
                (polity_id, system_id, knowledge_tier,
                 first_visit_tick, last_visit_tick,
                 gas_giant, ocean_body, world_potential,
                 atm_type, surface_temp_k, hydrosphere, habitable)
            VALUES (?, ?, 'visited', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (polity_id, system_id, tick, tick,
             gg_flag, ocean_flag, world_potential,
             atm_type, surface_temp_k, hydrosphere, habitable),
        )
    else:
        first_tick = existing["first_visit_tick"] or tick
        conn.execute(
            """
            UPDATE SystemIntelligence
            SET knowledge_tier = 'visited', first_visit_tick = ?,
                last_visit_tick = ?, gas_giant = ?, ocean_body = ?,
                world_potential = ?, atm_type = ?, surface_temp_k = ?,
                hydrosphere = ?, habitable = ?
            WHERE polity_id = ? AND system_id = ?
            """,
            (first_tick, tick, gg_flag, ocean_flag, world_potential,
             atm_type, surface_temp_k, hydrosphere, habitable,
             polity_id, system_id),
        )


# ---------------------------------------------------------------------------
# Map sharing
# ---------------------------------------------------------------------------

def check_map_sharing(
    conn: sqlite3.Connection, tick: int
) -> list[tuple[int, int]]:
    """Scan ContactRecord for pairs at peace for >= 52 weeks; fire exchange.

    Returns list of (polity_a_id, polity_b_id) pairs that just received maps.
    """
    rows = conn.execute(
        """
        SELECT contact_id, polity_a_id, polity_b_id
        FROM   ContactRecord_head
        WHERE  peace_weeks >= 52 AND at_war = 0 AND map_shared = 0
        """,
    ).fetchall()

    pairs: list[tuple[int, int]] = []
    for row in rows:
        copy_intel_between_polities(conn, row["polity_a_id"], row["polity_b_id"])
        copy_intel_between_polities(conn, row["polity_b_id"], row["polity_a_id"])
        # Temporal INSERT for map_shared=1
        cur = _current_contact_row(conn, row["contact_id"])
        _insert_contact_row(
            conn,
            contact_id=row["contact_id"],
            polity_a_id=cur["polity_a_id"],
            polity_b_id=cur["polity_b_id"],
            contact_tick=cur["contact_tick"],
            contact_system_id=cur["contact_system_id"],
            peace_weeks=cur["peace_weeks"],
            at_war=cur["at_war"],
            map_shared=1,
            tick=tick, seq=0,
        )
        pairs.append((row["polity_a_id"], row["polity_b_id"]))
    return pairs


def copy_intel_between_polities(
    conn: sqlite3.Connection, source_id: int, target_id: int
) -> None:
    """Copy all intel rows from source to target (merge; visited wins)."""
    source_rows = conn.execute(
        "SELECT * FROM SystemIntelligence WHERE polity_id = ?",
        (source_id,),
    ).fetchall()

    for src in source_rows:
        existing = conn.execute(
            "SELECT knowledge_tier FROM SystemIntelligence "
            "WHERE polity_id = ? AND system_id = ?",
            (target_id, src["system_id"]),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO SystemIntelligence
                    (polity_id, system_id, knowledge_tier,
                     first_visit_tick, last_visit_tick, gas_giant, ocean_body,
                     world_potential, atm_type, surface_temp_k,
                     hydrosphere, habitable)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (target_id, src["system_id"], src["knowledge_tier"],
                 src["first_visit_tick"], src["last_visit_tick"],
                 src["gas_giant"], src["ocean_body"], src["world_potential"],
                 src["atm_type"], src["surface_temp_k"],
                 src["hydrosphere"], src["habitable"]),
            )
        elif existing["knowledge_tier"] == "passive" and src["knowledge_tier"] == "visited":
            conn.execute(
                """
                UPDATE SystemIntelligence
                SET knowledge_tier = 'visited',
                    first_visit_tick = ?, last_visit_tick = ?,
                    gas_giant = ?, ocean_body = ?, world_potential = ?,
                    atm_type = ?, surface_temp_k = ?, hydrosphere = ?, habitable = ?
                WHERE polity_id = ? AND system_id = ?
                """,
                (src["first_visit_tick"], src["last_visit_tick"],
                 src["gas_giant"], src["ocean_body"], src["world_potential"],
                 src["atm_type"], src["surface_temp_k"], src["hydrosphere"],
                 src["habitable"], target_id, src["system_id"]),
            )
        # visited-to-visited: update last_visit_tick if source is more recent
        elif existing["knowledge_tier"] == "visited" and src["knowledge_tier"] == "visited":
            conn.execute(
                """
                UPDATE SystemIntelligence
                SET last_visit_tick = MAX(last_visit_tick, ?)
                WHERE polity_id = ? AND system_id = ?
                """,
                (src["last_visit_tick"] or 0, target_id, src["system_id"]),
            )


# ---------------------------------------------------------------------------
# Peace week tracking (called from intelligence phase)
# ---------------------------------------------------------------------------

def increment_peace_weeks(conn: sqlite3.Connection, tick: int = 0, seq: int = 0) -> None:
    """Increment peace_weeks for all non-war contact pairs (temporal INSERT)."""
    rows = conn.execute(
        "SELECT * FROM ContactRecord_head WHERE at_war = 0"
    ).fetchall()
    for row in rows:
        _insert_contact_row(
            conn,
            contact_id=row["contact_id"],
            polity_a_id=row["polity_a_id"],
            polity_b_id=row["polity_b_id"],
            contact_tick=row["contact_tick"],
            contact_system_id=row["contact_system_id"],
            peace_weeks=row["peace_weeks"] + 1,
            at_war=row["at_war"],
            map_shared=row["map_shared"],
            tick=tick, seq=seq,
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_intel(
    conn: sqlite3.Connection, polity_id: int, system_id: int
) -> dict | None:
    """Return the intel row for (polity_id, system_id) as a dict, or None."""
    row = conn.execute(
        "SELECT * FROM SystemIntelligence WHERE polity_id = ? AND system_id = ?",
        (polity_id, system_id),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_known_systems(
    conn: sqlite3.Connection, polity_id: int
) -> list[dict]:
    """Return all intel rows for a polity as dicts."""
    rows = conn.execute(
        "SELECT * FROM SystemIntelligence WHERE polity_id = ?",
        (polity_id,),
    ).fetchall()
    return [dict(r) for r in rows]
