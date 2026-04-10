"""Orbital bombardment — Phase 5 of each tick.

Prerequisite: naval superiority (no hostile active fleet in system).

Each tick of net Bombardment advantage (attacker bombard − defender bombard)
reduces total defending ground strength by 1.  The weakest unit is hit first;
no unit is reduced below 1 via bombardment alone (bombardment cannot destroy
a formation outright — that requires a ground assault).

Multiple bodies in a system may have defenders; bombardment targets the body
with the most defender strength (the primary target).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from random import Random

from .combat import get_fleet_strength_in_system
from .events import write_event
from .ground import apply_strength_delta, get_ground_forces_in_system


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BombardmentResult:
    system_id:      int
    attacker_id:    int
    body_id:        int | None       # primary target body
    net_bombard:    int              # attacker − defender bombard totals
    strength_delta: int              # strength removed from defenders (≤ 0)
    defender_total_before: int
    defender_total_after:  int


# ---------------------------------------------------------------------------
# Prerequisite check
# ---------------------------------------------------------------------------

def check_naval_superiority(
    conn: sqlite3.Connection,
    system_id: int,
    polity_id: int,
) -> bool:
    """Return True if polity_id has an active fleet and no hostile fleet present.

    Hostile = polity that is at_war with polity_id per ContactRecord.
    """
    own_fleet = conn.execute(
        "SELECT 1 FROM Fleet WHERE polity_id = ? AND system_id = ? AND status = 'active'",
        (polity_id, system_id),
    ).fetchone()
    if not own_fleet:
        return False

    # Check for at-war polities' fleets
    hostile = conn.execute(
        """
        SELECT 1
        FROM   Fleet f
        JOIN   ContactRecord cr
               ON  (cr.polity_a_id = ? AND cr.polity_b_id = f.polity_id
                    OR cr.polity_b_id = ? AND cr.polity_a_id = f.polity_id)
        WHERE  f.system_id = ?
          AND  f.status    = 'active'
          AND  cr.at_war   = 1
        LIMIT  1
        """,
        (polity_id, polity_id, system_id),
    ).fetchone()
    return hostile is None


# ---------------------------------------------------------------------------
# Tactical decision (pure)
# ---------------------------------------------------------------------------

def should_bombard(
    defender_ground_strength: int,
    own_army_strength: int,
    risk_appetite: float,
    net_bombard: int,
) -> bool:
    """Return True if this polity should bombard rather than assault immediately.

    Bombard when: net bombard advantage exists AND defender is stronger
    than attacker (adjusted by risk_appetite).
    """
    if net_bombard <= 0:
        return False
    # Low risk appetite: bombard even when roughly equal
    threshold = own_army_strength * (1.5 - risk_appetite)
    return defender_ground_strength > threshold


# ---------------------------------------------------------------------------
# Bombardment execution
# ---------------------------------------------------------------------------

def find_primary_target_body(
    conn: sqlite3.Connection,
    system_id: int,
    defender_id: int,
) -> int | None:
    """Return the body_id with the most combined defender ground strength."""
    row = conn.execute(
        """
        SELECT   body_id, SUM(strength) AS total
        FROM     GroundForce
        WHERE    system_id = ?
          AND    polity_id = ?
          AND    strength  > 0
          AND    embarked_hull_id IS NULL
        GROUP BY body_id
        ORDER BY total DESC
        LIMIT    1
        """,
        (system_id, defender_id),
    ).fetchone()
    return row["body_id"] if row else None


def run_bombardment_tick(
    conn: sqlite3.Connection,
    system_id: int,
    attacker_id: int,
    defender_id: int,
    tick: int,
    rng: Random,          # accepted for signature uniformity; unused here
) -> BombardmentResult:
    """Execute one tick of orbital bombardment.

    Reduces total defending ground strength by 1 if net bombard > 0.
    """
    str_att = get_fleet_strength_in_system(conn, attacker_id, system_id)
    str_def = get_fleet_strength_in_system(conn, defender_id, system_id)
    net_bombard = str_att["bombard"] - str_def["bombard"]

    body_id = find_primary_target_body(conn, system_id, defender_id)
    defender_forces = [
        f for f in get_ground_forces_in_system(conn, system_id)
        if f.polity_id == defender_id and f.body_id == body_id
           and f.embarked_hull_id is None
    ]

    total_before = sum(f.strength for f in defender_forces)
    total_after  = total_before
    strength_delta = 0

    if net_bombard > 0 and defender_forces:
        # Hit the weakest unit first; minimum 1 strength (bombardment can't destroy)
        target = min(defender_forces, key=lambda f: f.strength)
        if target.strength > 1:
            apply_strength_delta(conn, target.force_id, -1, tick)
            strength_delta = -1
            total_after = total_before - 1

    write_event(
        conn, tick=tick, phase=5,
        event_type="bombardment",
        summary=(
            f"system={system_id} attacker={attacker_id} defender={defender_id} "
            f"net_bombard={net_bombard} ground_strength={total_before}→{total_after}"
        ),
        polity_a_id=attacker_id, polity_b_id=defender_id,
        system_id=system_id, body_id=body_id,
    )

    return BombardmentResult(
        system_id=system_id,
        attacker_id=attacker_id,
        body_id=body_id,
        net_bombard=net_bombard,
        strength_delta=strength_delta,
        defender_total_before=total_before,
        defender_total_after=total_after,
    )


# ---------------------------------------------------------------------------
# Phase-level scan: find which systems have naval superiority + ground targets
# ---------------------------------------------------------------------------

def find_bombardment_candidates(
    conn: sqlite3.Connection,
) -> list[tuple[int, int, int]]:
    """Return (system_id, attacker_id, defender_id) triples where bombardment
    is applicable: at_war pair, attacker has naval superiority, defender has
    un-embarked ground forces in the system.
    """
    war_pairs = conn.execute(
        "SELECT polity_a_id, polity_b_id FROM ContactRecord WHERE at_war = 1"
    ).fetchall()

    candidates: list[tuple[int, int, int]] = []

    for row in war_pairs:
        for attacker, defender in (
            (row["polity_a_id"], row["polity_b_id"]),
            (row["polity_b_id"], row["polity_a_id"]),
        ):
            # Systems where defender has un-embarked ground forces
            systems = conn.execute(
                """
                SELECT DISTINCT system_id FROM GroundForce
                WHERE polity_id = ? AND system_id IS NOT NULL
                  AND strength > 0 AND embarked_hull_id IS NULL
                """,
                (defender,),
            ).fetchall()

            for s in systems:
                sid = s["system_id"]
                if check_naval_superiority(conn, sid, attacker):
                    candidates.append((sid, attacker, defender))

    return candidates
