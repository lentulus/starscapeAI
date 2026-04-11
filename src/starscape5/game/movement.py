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
from .fleet import arrive_fleet, get_hulls_in_fleet


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
    """
    conn.execute(
        """
        UPDATE Fleet
        SET    destination_system_id = ?,
               destination_tick      = ?,
               status                = 'in_transit',
               system_id             = NULL
        WHERE  fleet_id = ?
        """,
        (destination_system_id, tick + 1, fleet_id),
    )
    conn.execute(
        """
        UPDATE Hull
        SET    destination_system_id = ?,
               destination_tick      = ?,
               status                = 'in_transit',
               system_id             = NULL
        WHERE  fleet_id = ? AND status != 'destroyed'
        """,
        (destination_system_id, tick + 1, fleet_id),
    )


def get_fleet_jump_range(
    conn: sqlite3.Connection, fleet_id: int,
    polity_jump_level: int | None = None,
) -> int:
    """Return the effective jump range of fleet (min of all jumping hulls).

    If polity_jump_level is given, scout hulls use max(base_jump, polity_jump_level).
    Returns 0 if no hull in the fleet has a jump drive.
    """
    hulls = get_hulls_in_fleet(conn, fleet_id)
    ranges = []
    for h in hulls:
        if h.hull_type not in HULL_STATS or HULL_STATS[h.hull_type].jump == 0:
            continue
        j = HULL_STATS[h.hull_type].jump
        if h.hull_type == "scout" and polity_jump_level is not None:
            j = max(j, polity_jump_level)
        ranges.append(j)
    return min(ranges) if ranges else 0


# ---------------------------------------------------------------------------
# Arrival processing
# ---------------------------------------------------------------------------

def process_arrivals(
    conn: sqlite3.Connection, tick: int
) -> list[tuple[int, int, int]]:
    """Complete all fleet arrivals scheduled for this tick.

    Returns list of (fleet_id, polity_id, system_id) for each arrived fleet.
    """
    rows = conn.execute(
        """
        SELECT fleet_id, polity_id, destination_system_id
        FROM   Fleet
        WHERE  destination_tick = ? AND status = 'in_transit'
        """,
        (tick,),
    ).fetchall()

    arrived: list[tuple[int, int, int]] = []
    for row in rows:
        fleet_id = row["fleet_id"]
        system_id = row["destination_system_id"]
        arrive_fleet(conn, fleet_id, system_id)
        arrived.append((fleet_id, row["polity_id"], system_id))
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
        "SELECT DISTINCT polity_id FROM SystemPresence WHERE system_id = ?",
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
                "SELECT contact_id FROM ContactRecord "
                "WHERE polity_a_id = ? AND polity_b_id = ?",
                (a, b),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO ContactRecord
                        (polity_a_id, polity_b_id, contact_tick, contact_system_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (a, b, tick, system_id),
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
