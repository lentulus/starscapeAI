"""Log / summary phase — Phase 9 of each tick.

Two responsibilities:
  1. Classify the tick as quiet or significant.
  2. On quiet ticks (every 4 weeks = 1 game-month), write a monthly summary
     aggregating treasury totals, fleet counts, and territory extent.

A tick is quiet when it has NO events of the following types:
    combat, war_declared, control_change, colony_established

Monthly summary is written regardless of quietness, but only at week 4 of
each simulated month (tick % 4 == 0).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .events import EventRow, write_event


# ---------------------------------------------------------------------------
# Quiet-tick classifier
# ---------------------------------------------------------------------------

_SIGNIFICANT_TYPES = frozenset(
    ("combat", "war_declared", "control_change", "colony_established")
)


def is_quiet_tick(events_this_tick: list[EventRow]) -> bool:
    """Return True if the tick has no significant events.

    'Significant' = combat, war declaration, control change, or new colony.
    """
    return not any(e.event_type in _SIGNIFICANT_TYPES for e in events_this_tick)


# ---------------------------------------------------------------------------
# Monthly summary
# ---------------------------------------------------------------------------

@dataclass
class MonthlySummaryData:
    """Aggregated game-state snapshot written as a summary event."""
    total_treasury_ru: float
    total_active_fleets: int
    total_presences: int
    polity_count: int


def _gather_summary_data(conn: sqlite3.Connection) -> MonthlySummaryData:
    """Query game.db for summary statistics."""
    treasury = conn.execute(
        "SELECT COALESCE(SUM(treasury_ru), 0.0) AS total FROM Polity_head WHERE status = 'active'"
    ).fetchone()

    fleets = conn.execute(
        """
        SELECT COUNT(*) AS total FROM Fleet f
        JOIN Polity_head p ON p.polity_id = f.polity_id
        WHERE f.status != 'destroyed' AND p.status = 'active'
        """
    ).fetchone()

    presences = conn.execute(
        """
        SELECT COUNT(*) AS total FROM SystemPresence_head sp
        JOIN Polity_head p ON p.polity_id = sp.polity_id
        WHERE p.status = 'active'
        """
    ).fetchone()

    polities = conn.execute(
        "SELECT COUNT(*) AS total FROM Polity_head WHERE status = 'active'"
    ).fetchone()

    return MonthlySummaryData(
        total_treasury_ru=float(treasury["total"]),
        total_active_fleets=int(fleets["total"]),
        total_presences=int(presences["total"]),
        polity_count=int(polities["total"]),
    )


def write_monthly_summary(
    conn: sqlite3.Connection,
    tick: int,
    phase: int = 9,
) -> None:
    """Write a monthly_summary GameEvent to compress quiet history.

    Called every 4 ticks (1 simulated month = 4 weeks).
    """
    data = _gather_summary_data(conn)
    summary = (
        f"month_end treasury={data.total_treasury_ru:.0f}RU "
        f"fleets={data.total_active_fleets} "
        f"presences={data.total_presences} "
        f"polities={data.polity_count}"
    )
    write_event(
        conn, tick=tick, phase=phase,
        event_type="monthly_summary",
        summary=summary,
    )
