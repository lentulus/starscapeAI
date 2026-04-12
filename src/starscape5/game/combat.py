"""Space combat resolution — Phase 4 of each tick.

One combat round is resolved per at-war polity pair per contested system
per tick.  Combat is simultaneous fire: both sides take hits before any
disengage check.

Resolution sequence:
  1. Sum each side's attack and defence (including SDBs; damaged = half).
  2. Roll 2d6 per side, modified by best admiral tactical_factor.
     Net attack = (side_attack - opp_defence) + (roll - 7).
  3. Hits on opponent = max(0, net_attack) // DAMAGE_DIVISOR.
  4. Apply hits to opponent's hulls (damaged→destroyed, active→damaged).
  5. Mark fleets with zero remaining hulls as destroyed.
  6. Losing side (took more hits, or fewer hulls remain) may disengage:
     roll 2d6 >= DISENGAGE_THRESHOLD.
  7. If disengage succeeds: fleet retreats to capital; winning side may pursue
     (aggression >= PURSUE_AGGRESSION_MIN → free half-hits on fleeing side).

References:
  specs/GameDesign/version1/units.md — attack/defence stats, damage rules
  *Fifth Frontier War* — simultaneous fire, hit allocation model
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from random import Random

from .constants import HULL_STATS
from .events import write_event
from .fleet import (
    mark_hull_damaged, mark_hull_destroyed, set_fleet_destination,
)
from .movement import execute_jump


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DAMAGE_DIVISOR:          int   = 3     # net-attack points per hull hit
_DISENGAGE_THRESHOLD:     int   = 8     # 2d6 roll needed to disengage
_PURSUE_AGGRESSION_MIN:   float = 0.5   # aggression threshold to pursue


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CombatResult:
    """Outcome of one combat round between two polities in a system."""
    system_id:        int
    polity_a_id:      int   # canonical a < b
    polity_b_id:      int
    hits_on_a:        int   = 0
    hits_on_b:        int   = 0
    a_disengaged:     bool  = False
    b_disengaged:     bool  = False
    pursuit_hits_on_a: int  = 0
    pursuit_hits_on_b: int  = 0


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def compute_hits(
    attacker_attack: int,
    defender_defence: int,
    roll_modifier: int,
) -> int:
    """Return hits on defender from a single fire phase.

    Net attack = attacker_attack − defender_defence + roll_modifier.
    One hit per DAMAGE_DIVISOR net-attack points (floor division).
    """
    net = attacker_attack - defender_defence + roll_modifier
    return max(0, net) // _DAMAGE_DIVISOR


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def find_contested_systems(conn: sqlite3.Connection) -> list[int]:
    """Return system_ids where at least one at-war polity pair both have active fleets."""
    war_pairs = conn.execute(
        "SELECT polity_a_id, polity_b_id FROM ContactRecord_head WHERE at_war = 1"
    ).fetchall()

    contested: set[int] = set()
    for row in war_pairs:
        a, b = row["polity_a_id"], row["polity_b_id"]
        systems = conn.execute(
            """
            SELECT DISTINCT f1.system_id
            FROM   Fleet f1
            JOIN   Fleet f2
                   ON  f1.system_id  = f2.system_id
                   AND f1.polity_id != f2.polity_id
            WHERE  f1.polity_id = ? AND f2.polity_id = ?
              AND  f1.status    = 'active'
              AND  f2.status    = 'active'
            """,
            (a, b),
        ).fetchall()
        for s in systems:
            contested.add(s["system_id"])
    return list(contested)


def get_fleet_strength_in_system(
    conn: sqlite3.Connection, polity_id: int, system_id: int
) -> dict[str, int]:
    """Sum attack/defence for all non-destroyed polity hulls in a system.

    Includes SDBs (fleet_id IS NULL but system_id matches).
    Damaged hulls count at half attack and half defence (floor).
    """
    hulls = conn.execute(
        """
        SELECT hull_type, status
        FROM   Hull_head
        WHERE  polity_id = ?
          AND  system_id = ?
          AND  status NOT IN ('destroyed', 'in_transit', 'establishing')
        """,
        (polity_id, system_id),
    ).fetchall()

    attack = defence = bombard = 0
    for h in hulls:
        stats = HULL_STATS.get(h["hull_type"])
        if stats is None:
            continue
        if h["status"] == "damaged":
            attack  += stats.attack  // 2
            defence += stats.defence // 2
        else:
            attack  += stats.attack
            defence += stats.defence
        bombard += stats.bombard

    return {"attack": attack, "defence": defence, "bombard": bombard}


def get_best_admiral_factor(
    conn: sqlite3.Connection, polity_id: int, system_id: int
) -> int:
    """Return the highest tactical_factor among active admirals at system_id."""
    row = conn.execute(
        """
        SELECT MAX(a.tactical_factor) AS best
        FROM   Admiral a
        JOIN   Fleet   f ON f.admiral_id = a.admiral_id
        WHERE  f.polity_id = ?
          AND  f.system_id = ?
          AND  f.status    = 'active'
          AND  a.status    = 'active'
        """,
        (polity_id, system_id),
    ).fetchone()
    return row["best"] if row and row["best"] is not None else 0


# ---------------------------------------------------------------------------
# Damage application
# ---------------------------------------------------------------------------

def apply_hits_to_system(
    conn: sqlite3.Connection,
    polity_id: int,
    system_id: int,
    n_hits: int,
) -> int:
    """Apply n_hits to polity's hulls in system.  Returns hulls actually hit.

    Hit priority: damaged hulls first (→ destroyed), then active (→ damaged).
    Warships (attack > 0) are targeted before logistics hulls.
    """
    if n_hits <= 0:
        return 0

    hulls = conn.execute(
        """
        SELECT hull_id, hull_type, status
        FROM   Hull_head
        WHERE  polity_id = ?
          AND  system_id = ?
          AND  status IN ('damaged', 'active')
        ORDER BY
          CASE status    WHEN 'damaged' THEN 0 ELSE 1 END,
          CASE hull_type
            WHEN 'capital'     THEN 0
            WHEN 'old_capital' THEN 1
            WHEN 'cruiser'     THEN 2
            WHEN 'escort'      THEN 3
            WHEN 'sdb'         THEN 4
            ELSE 5
          END
        """,
        (polity_id, system_id),
    ).fetchall()

    applied = 0
    for hull in hulls:
        if applied >= n_hits:
            break
        if hull["status"] == "damaged":
            mark_hull_destroyed(conn, hull["hull_id"])
        else:
            mark_hull_damaged(conn, hull["hull_id"])
        applied += 1

    return applied


def check_and_mark_fleets_destroyed(
    conn: sqlite3.Connection,
    polity_id: int,
    system_id: int,
    tick: int,
) -> list[int]:
    """Mark each polity fleet in system as destroyed if it has no active hulls.

    Returns list of destroyed fleet_ids.
    """
    fleets = conn.execute(
        "SELECT fleet_id FROM Fleet "
        "WHERE polity_id = ? AND system_id = ? AND status = 'active'",
        (polity_id, system_id),
    ).fetchall()

    destroyed: list[int] = []
    for row in fleets:
        fleet_id = row["fleet_id"]
        remaining = conn.execute(
            "SELECT COUNT(*) FROM Hull_head "
            "WHERE fleet_id = ? AND status IN ('active','damaged')",
            (fleet_id,),
        ).fetchone()[0]
        if remaining == 0:
            conn.execute(
                "UPDATE Fleet SET status = 'destroyed' WHERE fleet_id = ?",
                (fleet_id,),
            )
            destroyed.append(fleet_id)
    return destroyed


def _has_active_fleet(
    conn: sqlite3.Connection, polity_id: int, system_id: int
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM Fleet WHERE polity_id = ? AND system_id = ? AND status = 'active'",
        (polity_id, system_id),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Combat resolution
# ---------------------------------------------------------------------------

def resolve_space_combat(
    conn: sqlite3.Connection,
    system_id: int,
    tick: int,
    rng: Random,
) -> list[CombatResult]:
    """Resolve one round of space combat for all at-war pairs in system_id.

    Returns one CombatResult per pair.  Results are recorded as GameEvents.
    """
    war_pairs = conn.execute(
        "SELECT polity_a_id, polity_b_id FROM ContactRecord_head WHERE at_war = 1"
    ).fetchall()

    results: list[CombatResult] = []

    for row in war_pairs:
        a, b = row["polity_a_id"], row["polity_b_id"]

        if not (_has_active_fleet(conn, a, system_id) and
                _has_active_fleet(conn, b, system_id)):
            continue

        result = _resolve_pair(conn, system_id, a, b, tick, rng)
        results.append(result)

    return results


def _resolve_pair(
    conn: sqlite3.Connection,
    system_id: int,
    a: int,
    b: int,
    tick: int,
    rng: Random,
) -> CombatResult:
    """Resolve one combat round between polity a and polity b in system."""
    result = CombatResult(system_id=system_id, polity_a_id=a, polity_b_id=b)

    str_a = get_fleet_strength_in_system(conn, a, system_id)
    str_b = get_fleet_strength_in_system(conn, b, system_id)
    adm_a = get_best_admiral_factor(conn, a, system_id)
    adm_b = get_best_admiral_factor(conn, b, system_id)

    # Simultaneous fire
    roll_a = rng.randint(1, 6) + rng.randint(1, 6) - 7 + adm_a
    roll_b = rng.randint(1, 6) + rng.randint(1, 6) - 7 + adm_b

    hits_on_b = compute_hits(str_a["attack"], str_b["defence"], roll_a)
    hits_on_a = compute_hits(str_b["attack"], str_a["defence"], roll_b)
    result.hits_on_a = hits_on_a
    result.hits_on_b = hits_on_b

    apply_hits_to_system(conn, b, system_id, hits_on_b)
    apply_hits_to_system(conn, a, system_id, hits_on_a)

    write_event(
        conn, tick=tick, phase=4,
        event_type="combat",
        summary=(
            f"system={system_id} polity_a={a} polity_b={b} "
            f"hits_on_a={hits_on_a} hits_on_b={hits_on_b}"
        ),
        polity_a_id=a, polity_b_id=b, system_id=system_id,
    )

    # Fleet destruction
    for polity_id in (a, b):
        for fleet_id in check_and_mark_fleets_destroyed(conn, polity_id, system_id, tick):
            write_event(
                conn, tick=tick, phase=4,
                event_type="fleet_destroyed",
                summary=f"Fleet {fleet_id} (polity {polity_id}) destroyed at system {system_id}",
                polity_a_id=polity_id, system_id=system_id,
            )

    # Disengage check for both sides (loser first)
    loser  = a if hits_on_a >= hits_on_b else b
    winner = b if loser == a else a

    _try_disengage(conn, system_id, loser, winner, result, tick, rng)

    return result


def _try_disengage(
    conn: sqlite3.Connection,
    system_id: int,
    loser: int,
    winner: int,
    result: CombatResult,
    tick: int,
    rng: Random,
) -> None:
    """Attempt disengage for the losing polity; apply pursuit if it succeeds."""
    if not _has_active_fleet(conn, loser, system_id):
        return  # already destroyed

    disengage_roll = rng.randint(1, 6) + rng.randint(1, 6)
    if disengage_roll < _DISENGAGE_THRESHOLD:
        return  # failed to disengage

    # Loser retreats to capital
    capital_row = conn.execute(
        "SELECT capital_system_id FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (loser,),
    ).fetchone()
    capital = capital_row["capital_system_id"] if capital_row else None

    if loser == result.polity_a_id:
        result.a_disengaged = True
    else:
        result.b_disengaged = True

    # Move all the loser's fleets out of the system
    fleeing_fleets = conn.execute(
        "SELECT fleet_id FROM Fleet WHERE polity_id = ? AND system_id = ? AND status = 'active'",
        (loser, system_id),
    ).fetchall()

    if capital and capital != system_id:
        for row in fleeing_fleets:
            execute_jump(conn, row["fleet_id"], capital, tick)
    # If no capital (or same system), fleet stays — disengage fails silently

    write_event(
        conn, tick=tick, phase=4,
        event_type="disengage",
        summary=f"Polity {loser} disengaged from system {system_id} to system {capital}",
        polity_a_id=loser, system_id=system_id,
    )

    # Pursuit
    winner_row = conn.execute(
        "SELECT aggression FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (winner,),
    ).fetchone()
    if winner_row and winner_row["aggression"] >= _PURSUE_AGGRESSION_MIN:
        str_w = get_fleet_strength_in_system(conn, winner, system_id)
        str_l = get_fleet_strength_in_system(conn, loser, system_id)
        # Half-round pursuit hits (no return fire)
        pursuit_hits = max(0, str_w["attack"] - str_l["defence"]) // (_DAMAGE_DIVISOR * 2)
        if pursuit_hits > 0:
            apply_hits_to_system(conn, loser, system_id, pursuit_hits)
            if loser == result.polity_a_id:
                result.pursuit_hits_on_a = pursuit_hits
            else:
                result.pursuit_hits_on_b = pursuit_hits
            write_event(
                conn, tick=tick, phase=4,
                event_type="pursuit",
                summary=(
                    f"Polity {winner} pursues polity {loser} "
                    f"at system {system_id}: {pursuit_hits} pursuit hits"
                ),
                polity_a_id=winner, polity_b_id=loser, system_id=system_id,
            )
