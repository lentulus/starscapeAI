"""Movement — fleet jumps, arrivals, and first-contact detection.

Jump mechanics:
  - A fleet's jump range is the minimum jump value among its hulls (hulls
    with jump=0 are excluded — SDBs are never in a fleet anyway).
  - execute_jump fires immediately; the fleet status is set to 'in_transit'
    and destination_tick = tick + 1 (one-week transit time).
  - process_arrivals is called each tick; it settles all fleets whose
    destination_tick equals the current tick.
  - detect_contacts scans the arrival system for polity co-presence and
    creates new ContactRecord rows on first encounter.
"""

from __future__ import annotations

import sqlite3

from .constants import HULL_STATS
from .events import write_event
from .fleet import arrive_fleet, get_hulls_in_fleet, _insert_hull_row, _current_hull_row
from .intelligence import _insert_contact_row


# ---------------------------------------------------------------------------
# Jump execution
# ---------------------------------------------------------------------------

def execute_jump(
    conn: sqlite3.Connection,
    fleet_id: int,
    destination_system_id: int,
    tick: int,
) -> None:
    """Order a fleet to jump; it arrives at destination_tick = tick + 1.

    Sets the fleet and all non-destroyed hulls to 'in_transit'.
    Saves system_id → prev_system_id before nulling it.
    """
    conn.execute(
        """
        UPDATE Fleet
        SET    prev_system_id        = system_id,
               destination_system_id = ?,
               destination_tick      = ?,
               status                = 'in_transit',
               system_id             = NULL
        WHERE  fleet_id = ?
        """,
        (destination_system_id, tick + 1, fleet_id),
    )
    # Update all non-destroyed hulls in the fleet to in_transit (temporal INSERT)
    hulls = conn.execute(
        "SELECT * FROM Hull_head WHERE fleet_id = ? AND status != 'destroyed'",
        (fleet_id,),
    ).fetchall()
    for h in hulls:
        _insert_hull_row(
            conn, hull_id=h["hull_id"],
            polity_id=h["polity_id"],
            name=h["name"],
            hull_type=h["hull_type"],
            squadron_id=h["squadron_id"],
            fleet_id=h["fleet_id"],
            system_id=None,
            destination_system_id=destination_system_id,
            destination_tick=tick + 1,
            status="in_transit",
            marine_designated=h["marine_designated"],
            cargo_type=h["cargo_type"],
            cargo_id=h["cargo_id"],
            establish_tick=h["establish_tick"],
            created_tick=h["created_tick"],
            tick=tick, seq=3,
        )


def get_fleet_jump_range(
    conn: sqlite3.Connection, fleet_id: int,
    polity_jump_level: int | None = None,
) -> int:
    """Return the effective jump range of fleet (min of all jumping hulls).

    All jump-capable hulls use max(base_jump, polity_jump_level) when the
    polity jump level is provided — the same upgrade rules as scouts.
    Returns 0 if no hull in the fleet has a jump drive.
    """
    hulls = get_hulls_in_fleet(conn, fleet_id)
    ranges = []
    for h in hulls:
        if h.hull_type not in HULL_STATS or HULL_STATS[h.hull_type].jump == 0:
            continue
        j = HULL_STATS[h.hull_type].jump
        if polity_jump_level is not None:
            j = max(j, polity_jump_level)
        ranges.append(j)
    return min(ranges) if ranges else 0


# ---------------------------------------------------------------------------
# Arrival processing
# ---------------------------------------------------------------------------

def process_arrivals(
    conn: sqlite3.Connection, tick: int
) -> list[tuple[int, int, int, int | None]]:
    """Complete all fleet arrivals scheduled for this tick.

    Returns list of (fleet_id, polity_id, system_id, prev_system_id) for each
    arrived fleet.  prev_system_id is the jump origin (may be None if unknown).
    """
    rows = conn.execute(
        """
        SELECT fleet_id, polity_id, destination_system_id, prev_system_id
        FROM   Fleet
        WHERE  destination_tick = ? AND status = 'in_transit'
        """,
        (tick,),
    ).fetchall()

    arrived: list[tuple[int, int, int, int | None]] = []
    for row in rows:
        fleet_id = row["fleet_id"]
        system_id = row["destination_system_id"]
        arrive_fleet(conn, fleet_id, system_id, tick=tick)
        arrived.append((fleet_id, row["polity_id"], system_id, row["prev_system_id"]))
    return arrived


# ---------------------------------------------------------------------------
# Contact detection
# ---------------------------------------------------------------------------

def detect_contacts(
    conn: sqlite3.Connection,
    system_id: int,
    tick: int,
) -> list[tuple[int, int]]:
    """Detect new inter-polity contacts at system_id.

    Collects all polities with a presence or active fleet in the system,
    then creates a ContactRecord for each pair that has not yet met.

    Returns list of newly created (polity_a_id, polity_b_id) pairs.
    """
    present: set[int] = set()

    for r in conn.execute(
        "SELECT DISTINCT polity_id FROM SystemPresence_head WHERE system_id = ?",
        (system_id,),
    ).fetchall():
        present.add(r["polity_id"])

    for r in conn.execute(
        "SELECT DISTINCT polity_id FROM Fleet "
        "WHERE system_id = ? AND status = 'active'",
        (system_id,),
    ).fetchall():
        present.add(r["polity_id"])

    polities = sorted(present)
    new_contacts: list[tuple[int, int]] = []

    for i, a in enumerate(polities):
        for b in polities[i + 1:]:
            existing = conn.execute(
                "SELECT contact_id FROM ContactRecord_head "
                "WHERE polity_a_id = ? AND polity_b_id = ?",
                (a, b),
            ).fetchone()
            if existing is None:
                # Assign new contact_id
                next_id = conn.execute(
                    "SELECT COALESCE(MAX(contact_id), 0) + 1 FROM ContactRecord"
                ).fetchone()[0]
                _insert_contact_row(
                    conn,
                    contact_id=next_id,
                    polity_a_id=a,
                    polity_b_id=b,
                    contact_tick=tick,
                    contact_system_id=system_id,
                    peace_weeks=0,
                    at_war=0,
                    map_shared=0,
                    tick=tick, seq=3,
                )
                write_event(
                    conn, tick=tick, phase=3,
                    event_type="contact",
                    summary=(
                        f"First contact between polity {a} and polity {b} "
                        f"at system {system_id}"
                    ),
                    polity_a_id=a,
                    polity_b_id=b,
                    system_id=system_id,
                )
                new_contacts.append((a, b))

    return new_contacts
