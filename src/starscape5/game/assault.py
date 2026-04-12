"""Ground assault — Phase 6 of each tick.

Prerequisite: naval superiority (enforced before calling run_ground_assault).

Assault sequence per body per tick:
  1. Identify landed attacker armies and all defender forces (Army + Garrison).
  2. Compute effective strengths (Garrison ×1.5; non-marine attacker −1 first round).
  3. Both sides roll 2d6; net shift = (roll_atk + eff_atk) − (roll_def + eff_def).
  4. Apply ground combat result table (units.md):
       net ≥ 6   : Rout  — defender destroyed; attacker −0
       net 4–5   : Decisive — defender −3, attacker −1; defender retreats
       net 2–3   : Attacker advantage — defender −2, attacker −1
       net 0–1   : No decision — both −1
       net < 0   : Table inverted — attacker takes mirror losses
  5. Garrison destroyed in place if overrun; Army may retreat to fleet.
  6. If defender eliminated/retreated, transfer control to attacker.
  7. Loop continues next tick unless attacker withdraws or resolution reached.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from random import Random

from .events import write_event
from .ground import apply_strength_delta, get_ground_forces_in_system
from .presence import advance_control_state, set_contested, transfer_control


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AssaultResult:
    system_id:          int
    body_id:            int | None
    attacker_id:        int
    defender_id:        int
    attacker_str_before: int
    defender_str_before: int
    attacker_str_after: int
    defender_str_after:  int
    net_shift:          int
    outcome:            str   # 'no_decision' | 'attacker_advantage' |
                              # 'decisive' | 'rout' | 'defender_advantage'
    control_changed:    bool  = False
    new_control_state:  str | None = None


# ---------------------------------------------------------------------------
# Ground combat result table (pure)
# ---------------------------------------------------------------------------

def ground_combat_result(net_shift: int) -> tuple[str, int, int]:
    """Return (outcome, attacker_delta, defender_delta) from net 2d6 shift.

    Positive net favours attacker.  Table is symmetric for negative net.
    """
    if net_shift >= 6:
        return "rout", 0, -99          # defender wiped; marker -99 = destroy all
    elif net_shift >= 4:
        return "decisive", -1, -3
    elif net_shift >= 2:
        return "attacker_advantage", -1, -2
    elif net_shift >= 0:
        return "no_decision", -1, -1
    elif net_shift >= -1:
        return "no_decision", -1, -1   # symmetric for -1
    elif net_shift >= -3:
        return "defender_advantage", -2, -1
    elif net_shift >= -5:
        return "decisive_defender", -3, -1
    else:
        return "rout_defender", -99, 0


# ---------------------------------------------------------------------------
# Assault execution
# ---------------------------------------------------------------------------

def run_ground_assault(
    conn: sqlite3.Connection,
    system_id: int,
    body_id: int,
    attacker_id: int,
    defender_id: int,
    tick: int,
    rng: Random,
    first_round: bool = True,
) -> AssaultResult:
    """Resolve one tick of ground combat on body_id.

    `first_round`: if True, non-marine attacker armies take −1 effective
    strength this round (landing-under-fire penalty).
    """
    attacker_forces = [
        f for f in get_ground_forces_in_system(conn, system_id)
        if f.polity_id == attacker_id
           and (f.body_id == body_id or f.body_id is None)
           and f.embarked_hull_id is None
           and f.strength > 0
    ]
    defender_forces = [
        f for f in get_ground_forces_in_system(conn, system_id)
        if f.polity_id == defender_id
           and (f.body_id == body_id or f.body_id is None)
           and f.embarked_hull_id is None
           and f.strength > 0
    ]

    # Effective strengths
    atk_str = 0
    for f in attacker_forces:
        base = f.strength
        if first_round and not f.marine_designated:
            base = max(1, base - 1)   # landing penalty
        atk_str += base

    def_str = 0
    for f in defender_forces:
        if f.unit_type == "garrison":
            def_str += int(f.strength * 1.5)   # prepared positions bonus
        else:
            def_str += f.strength

    str_before_atk = sum(f.strength for f in attacker_forces)
    str_before_def = sum(f.strength for f in defender_forces)

    # 2d6 rolls
    roll_atk = rng.randint(1, 6) + rng.randint(1, 6)
    roll_def = rng.randint(1, 6) + rng.randint(1, 6)
    net_shift = (roll_atk + atk_str) - (roll_def + def_str)

    outcome, atk_delta, def_delta = ground_combat_result(net_shift)

    # Apply attacker losses
    if atk_delta == -99:
        _destroy_all_forces(conn, attacker_forces, tick)
    elif atk_delta < 0 and attacker_forces:
        # Distribute loss across attacker's strongest unit
        target = max(attacker_forces, key=lambda f: f.strength)
        apply_strength_delta(conn, target.force_id, atk_delta, tick)

    # Apply defender losses
    control_changed = False
    new_control_state = None

    if def_delta == -99:
        _destroy_all_forces(conn, defender_forces, tick)
        # Rout: control transfers to attacker
        control_changed = True
        new_control_state = _transfer_system_control(
            conn, system_id, body_id, attacker_id, defender_id, tick
        )
    elif def_delta < 0 and defender_forces:
        remaining = _apply_defender_losses(conn, defender_forces, def_delta, tick)
        # If decisive or better and defenders all wiped/retreated
        if remaining == 0 and outcome in ("decisive", "attacker_advantage"):
            control_changed = True
            new_control_state = _transfer_system_control(
                conn, system_id, body_id, attacker_id, defender_id, tick
            )

    str_after_atk = sum(
        conn.execute(
            "SELECT COALESCE(SUM(strength), 0) FROM GroundForce_head "
            "WHERE force_id IN (%s)" % ",".join("?" * len(attacker_forces)),
            [f.force_id for f in attacker_forces],
        ).fetchone()[0]
        for _ in [1]
    ) if attacker_forces else 0

    str_after_def = (
        conn.execute(
            "SELECT COALESCE(SUM(strength), 0) FROM GroundForce_head "
            "WHERE force_id IN (%s)" % ",".join("?" * len(defender_forces)),
            [f.force_id for f in defender_forces],
        ).fetchone()[0]
        if defender_forces else 0
    )

    write_event(
        conn, tick=tick, phase=6,
        event_type="combat",
        summary=(
            f"ground_assault system={system_id} body={body_id} "
            f"attacker={attacker_id} defender={defender_id} "
            f"outcome={outcome} net={net_shift:+d} "
            f"atk_str={str_before_atk}→{str_after_atk} "
            f"def_str={str_before_def}→{str_after_def}"
        ),
        polity_a_id=attacker_id, polity_b_id=defender_id,
        system_id=system_id, body_id=body_id,
    )

    return AssaultResult(
        system_id=system_id,
        body_id=body_id,
        attacker_id=attacker_id,
        defender_id=defender_id,
        attacker_str_before=str_before_atk,
        defender_str_before=str_before_def,
        attacker_str_after=str_after_atk,
        defender_str_after=str_after_def,
        net_shift=net_shift,
        outcome=outcome,
        control_changed=control_changed,
        new_control_state=new_control_state,
    )


# ---------------------------------------------------------------------------
# Phase-level scan
# ---------------------------------------------------------------------------

def find_assault_candidates(
    conn: sqlite3.Connection,
) -> list[tuple[int, int, int, int]]:
    """Return (system_id, body_id, attacker_id, defender_id) where an assault
    can proceed: at_war, attacker has un-embarked armies in system, defender
    has ground forces on the body, no hostile fleet present.
    """
    from .bombardment import check_naval_superiority

    war_pairs = conn.execute(
        "SELECT polity_a_id, polity_b_id FROM ContactRecord_head WHERE at_war = 1"
    ).fetchall()

    candidates: list[tuple[int, int, int, int]] = []

    for row in war_pairs:
        for attacker, defender in (
            (row["polity_a_id"], row["polity_b_id"]),
            (row["polity_b_id"], row["polity_a_id"]),
        ):
            # Bodies in contested systems where defender has ground forces
            bodies = conn.execute(
                """
                SELECT DISTINCT body_id
                FROM   GroundForce_head
                WHERE  polity_id = ? AND system_id IS NOT NULL
                  AND  strength  > 0  AND embarked_hull_id IS NULL
                """,
                (defender,),
            ).fetchall()

            for b in bodies:
                body_id = b["body_id"]
                # Get system_id for this body
                sys_row = conn.execute(
                    "SELECT system_id FROM GroundForce_head "
                    "WHERE polity_id = ? AND body_id = ? AND system_id IS NOT NULL LIMIT 1",
                    (defender, body_id),
                ).fetchone()
                if sys_row is None:
                    continue
                sid = sys_row["system_id"]

                # Check attacker has landed armies in this system
                atk_forces = conn.execute(
                    "SELECT 1 FROM GroundForce_head "
                    "WHERE polity_id = ? AND system_id = ? "
                    "AND strength > 0 AND embarked_hull_id IS NULL LIMIT 1",
                    (attacker, sid),
                ).fetchone()
                if not atk_forces:
                    continue

                if check_naval_superiority(conn, sid, attacker):
                    candidates.append((sid, body_id, attacker, defender))

    return candidates


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _destroy_all_forces(conn, forces, tick: int) -> None:
    for f in forces:
        apply_strength_delta(conn, f.force_id, -f.strength, tick)


def _apply_defender_losses(conn, forces, delta: int, tick: int) -> int:
    """Apply delta to defender forces (delta is negative).  Return total remaining."""
    remaining_loss = abs(delta)
    for f in sorted(forces, key=lambda x: x.strength):
        if remaining_loss <= 0:
            break
        loss = min(remaining_loss, f.strength)
        apply_strength_delta(conn, f.force_id, -loss, tick)
        remaining_loss -= loss
    total = conn.execute(
        "SELECT COALESCE(SUM(strength), 0) FROM GroundForce_head "
        "WHERE force_id IN (%s)" % ",".join("?" * len(forces)),
        [f.force_id for f in forces],
    ).fetchone()[0]
    return total


def _transfer_system_control(
    conn: sqlite3.Connection,
    system_id: int,
    body_id: int | None,
    attacker_id: int,
    defender_id: int,
    tick: int,
) -> str | None:
    """Transfer or contest control of body_id to the attacker.

    Returns new control_state string, or None if no presence row found.
    """
    presence = conn.execute(
        """
        SELECT presence_id, control_state FROM SystemPresence_head
        WHERE  polity_id = ? AND system_id = ?
          AND  (? IS NULL OR body_id = ?)
        LIMIT  1
        """,
        (defender_id, system_id, body_id, body_id),
    ).fetchone()

    if presence is None:
        return None

    presence_id = presence["presence_id"]
    # First mark contested
    set_contested(conn, presence_id, tick)
    write_event(
        conn, tick=tick, phase=6,
        event_type="control_change",
        summary=(
            f"system={system_id} body={body_id}: "
            f"{presence['control_state']}→contested "
            f"(polity {defender_id} overrun by polity {attacker_id})"
        ),
        polity_a_id=attacker_id, polity_b_id=defender_id,
        system_id=system_id, body_id=body_id,
    )
    return "contested"
