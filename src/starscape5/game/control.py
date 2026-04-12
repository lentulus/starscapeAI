"""Control update — presence growth and development advancement.

Growth cycle fires every 25 ticks.  At each checkpoint each presence rolls
for development advancement within the cap for its current control state.
State transitions (outpost → colony → controlled) also require the colonist
delivery threshold to have been met (set via presence.record_colonist_delivery).

Colonist delivery thresholds (game.md):
  → Outpost (establish):   1 delivery
  Outpost → Colony:        3 deliveries
  Colony  → Controlled:    5 deliveries

Development advancement is independent of deliveries — it represents natural
population growth and infrastructure maturation within a settled world.

Seeded randomness: rng = Random(hash((tick, phase_num, processing_order)))
This ensures deterministic replay from any phase checkpoint.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from random import Random

from .events import write_event
from .presence import advance_control_state, advance_development


_GROWTH_CYCLE_WEEKS: int = 25

# Colonist deliveries required to unlock a state transition.
_DELIVERY_THRESHOLD: dict[str, int] = {
    "outpost": 3,   # to reach colony
    "colony":  5,   # to reach controlled
}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def compute_growth_probability(
    expansionism: float,
    development_level: int,
) -> float:
    """Return the probability [0, 1] of development advancing this cycle.

    Higher expansionism → more investment → faster growth.
    Higher development_level → slower marginal gains (diminishing returns).
    Formula is intentionally simple and tunable.
    """
    base = 0.25 + expansionism * 0.35        # range 0.25 – 0.60
    penalty = development_level * 0.06       # −0.06 per level
    return max(0.05, min(0.90, base - penalty))


def compute_state_advance_probability(
    expansionism: float,
    colonist_deliveries: int,
    threshold: int,
) -> float:
    """Return probability of state advancing given deliveries vs threshold.

    Requires deliveries >= threshold; otherwise returns 0.
    Extra deliveries above the threshold improve the odds.
    """
    if colonist_deliveries < threshold:
        return 0.0
    surplus = colonist_deliveries - threshold
    base = 0.40 + expansionism * 0.30
    bonus = min(0.25, surplus * 0.05)
    return min(0.95, base + bonus)


# ---------------------------------------------------------------------------
# Growth cycle check
# ---------------------------------------------------------------------------

@dataclass
class PresenceAdvanced:
    presence_id: int
    polity_id: int
    system_id: int
    body_id: int
    old_state: str
    new_state: str
    old_dev: int
    new_dev: int


def check_growth_cycles(
    conn: sqlite3.Connection,
    polity_id: int,
    tick: int,
    rng: Random,
) -> list[PresenceAdvanced]:
    """Run growth cycle checks for all presences of polity_id.

    Only fires on ticks that are multiples of GROWTH_CYCLE_WEEKS.
    Returns list of PresenceAdvanced describing any changes made.
    """
    if tick % _GROWTH_CYCLE_WEEKS != 0:
        return []

    polity_row = conn.execute(
        "SELECT expansionism FROM Polity WHERE polity_id = ? ORDER BY row_id DESC LIMIT 1",
        (polity_id,),
    ).fetchone()
    if polity_row is None:
        return []
    expansionism = polity_row["expansionism"]

    presences = conn.execute(
        """
        SELECT presence_id, system_id, body_id, control_state,
               development_level, colonist_deliveries
        FROM   SystemPresence_head
        WHERE  polity_id = ?
        """,
        (polity_id,),
    ).fetchall()

    results: list[PresenceAdvanced] = []

    for p in presences:
        old_state = p["control_state"]
        old_dev = p["development_level"]
        new_state = old_state
        new_dev = old_dev

        # Try state advancement first (requires colonist deliveries)
        threshold = _DELIVERY_THRESHOLD.get(old_state)
        if threshold is not None:
            prob = compute_state_advance_probability(
                expansionism, p["colonist_deliveries"], threshold
            )
            if prob > 0 and rng.random() < prob:
                new_state = advance_control_state(conn, p["presence_id"], tick)
                write_event(
                    conn, tick=tick, phase=7,
                    event_type="control_change",
                    summary=(
                        f"System {p['system_id']} body {p['body_id']}: "
                        f"{old_state} → {new_state}"
                    ),
                    polity_a_id=polity_id,
                    system_id=p["system_id"],
                    body_id=p["body_id"],
                )

        # Try development advancement (independent of state transition)
        dev_prob = compute_growth_probability(expansionism, new_dev)
        if rng.random() < dev_prob:
            new_dev = advance_development(conn, p["presence_id"], tick)

        if new_state != old_state or new_dev != old_dev:
            results.append(PresenceAdvanced(
                presence_id=p["presence_id"],
                polity_id=polity_id,
                system_id=p["system_id"],
                body_id=p["body_id"],
                old_state=old_state,
                new_state=new_state,
                old_dev=old_dev,
                new_dev=new_dev,
            ))

    return results
