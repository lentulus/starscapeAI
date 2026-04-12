"""Admirals — naval commanders with species-biased tactical ability.

Admirals are generated on-demand when a fleet first enters a hostile system
with no commander.  Seniority is determined by admiral_id (creation order
within a polity): lower ID = more senior.  Combined command goes to the most
senior admiral present.

TEMPORAL TABLE: append-only; all mutations INSERT new rows (copy-on-write).
admiral_id is the logical entity key; row_id is the physical autoincrement PK.
Use Admiral_head view or ORDER BY row_id DESC LIMIT 1 for current state.

Tactical factor generation
--------------------------
Base: Gaussian centred at 0, std ≈ 2.0.
Species modifiers:
  - adaptability shifts the mean:  (adaptability − 0.5) × 2.0
  - risk_appetite widens the spread: base_std × (1.0 + risk_appetite × 0.5)
  - hierarchy_tolerance tightens the spread (hierarchical species produce
    more uniform officers): spread × (1.0 − hierarchy_tolerance × 0.25)
Result clipped to [−3, +3].

Per-species fine-tune bonuses in ADMIRAL_GENERATION_PARAMS can shift mean
and scale spread beyond the formula defaults.  All start at neutral (0.0, 1.0)
for V1; adjust after first runs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from random import Random

from starscape5.world.facade import SpeciesData
from .events import write_event
from .names import NameGenerator


# ---------------------------------------------------------------------------
# Species-level generation parameters (tuning layer above the base formula).
# Keys are species_id (int).  mean_bonus stacks on the formula mean;
# spread_factor multiplies the formula spread.
# ---------------------------------------------------------------------------

ADMIRAL_GENERATION_PARAMS: dict[int, dict[str, float]] = {
    1:  {"mean_bonus": 0.0, "spread_factor": 1.0},   # Kreeth
    2:  {"mean_bonus": 0.0, "spread_factor": 1.0},   # Vashori
    3:  {"mean_bonus": 0.0, "spread_factor": 1.0},   # Kraathi
    4:  {"mean_bonus": 0.0, "spread_factor": 1.0},   # Nakhavi
    5:  {"mean_bonus": 0.5, "spread_factor": 1.2},   # Skharri — honour-culture; more variance, slight positive lean
    6:  {"mean_bonus": 0.0, "spread_factor": 1.0},   # Vaelkhi
    7:  {"mean_bonus": 0.0, "spread_factor": 0.9},   # Shekhari — pragmatic; slightly tighter distribution
    8:  {"mean_bonus": 0.0, "spread_factor": 0.8},   # Golvhaan — deliberate; consistent, rarely brilliant
    9:  {"mean_bonus": 0.0, "spread_factor": 1.3},   # Nhaveth — court politics; high variance
    10: {"mean_bonus": 0.3, "spread_factor": 0.9},   # Vardhek — Roidhunate training; slight positive lean
    11: {"mean_bonus": 0.0, "spread_factor": 1.0},   # Human
}

_DEFAULT_PARAMS: dict[str, float] = {"mean_bonus": 0.0, "spread_factor": 1.0}

_BASE_STD: float = 2.0


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class AdmiralRow:
    admiral_id: int
    polity_id: int
    name: str
    tactical_factor: int  # −3 to +3
    fleet_id: int | None
    created_tick: int
    retirement_tick: int
    status: str  # 'active' | 'killed' | 'captured' | 'retired'


# ---------------------------------------------------------------------------
# Retirement tick calculation (pure)
# ---------------------------------------------------------------------------

_WEEKS_PER_YEAR: int = 52

def compute_retirement_tick(
    created_tick: int,
    lifespan_years: int,
    rng: Random,
) -> int:
    """Return the tick at which this admiral retires.

    Service life = ~30% of species lifespan, ±20% random variation.
    Minimum 52 ticks (1 year) regardless of species lifespan.
    """
    base_service_years = max(1.0, lifespan_years * 0.30)
    # ±20% jitter
    service_years = base_service_years * rng.uniform(0.8, 1.2)
    service_ticks = max(_WEEKS_PER_YEAR, round(service_years * _WEEKS_PER_YEAR))
    return created_tick + service_ticks


# ---------------------------------------------------------------------------
# Tactical factor generation (pure function)
# ---------------------------------------------------------------------------

def generate_tactical_factor(species_data: SpeciesData, rng: Random) -> int:
    """Return a species-biased tactical factor in [−3, +3].

    Higher adaptability → more capable officers on average.
    Higher risk_appetite → more variance (brilliant or incompetent).
    Higher hierarchy_tolerance → tighter, more predictable distribution.
    Species-specific bonuses from ADMIRAL_GENERATION_PARAMS stack on top.
    """
    params = ADMIRAL_GENERATION_PARAMS.get(species_data.species_id, _DEFAULT_PARAMS)

    mean = (species_data.adaptability - 0.5) * 2.0 + params["mean_bonus"]
    spread = (
        _BASE_STD
        * (1.0 + species_data.risk_appetite * 0.5)
        * (1.0 - species_data.hierarchy_tolerance * 0.25)
        * params["spread_factor"]
    )
    raw = rng.gauss(mean, spread)
    return max(-3, min(3, round(raw)))


# ---------------------------------------------------------------------------
# Internal copy-on-write helpers
# ---------------------------------------------------------------------------

def _current_admiral_row(conn: sqlite3.Connection, admiral_id: int) -> sqlite3.Row:
    """Return the most recent raw row for admiral_id."""
    row = conn.execute(
        "SELECT * FROM Admiral WHERE admiral_id = ? ORDER BY row_id DESC LIMIT 1",
        (admiral_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Admiral {admiral_id} not found")
    return row


def _insert_admiral_row(
    conn: sqlite3.Connection,
    admiral_id: int,
    polity_id: int,
    name: str,
    tactical_factor: int,
    fleet_id: int | None,
    created_tick: int,
    retirement_tick: int,
    status: str,
    tick: int = 0,
    seq: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO Admiral
            (admiral_id, tick, seq, polity_id, name, tactical_factor,
             fleet_id, created_tick, retirement_tick, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (admiral_id, tick, seq, polity_id, name, tactical_factor,
         fleet_id, created_tick, retirement_tick, status),
    )


# ---------------------------------------------------------------------------
# DB functions
# ---------------------------------------------------------------------------

def create_admiral(
    conn: sqlite3.Connection,
    polity_id: int,
    name: str,
    tactical_factor: int,
    fleet_id: int | None,
    created_tick: int,
    retirement_tick: int,
) -> int:
    """Insert a new Admiral row and return its admiral_id."""
    row = conn.execute(
        "SELECT COALESCE(MAX(admiral_id), 0) + 1 FROM Admiral"
    ).fetchone()
    admiral_id: int = row[0]
    _insert_admiral_row(
        conn, admiral_id, polity_id, name, tactical_factor,
        fleet_id, created_tick, retirement_tick, status="active",
        tick=created_tick, seq=0,
    )
    # Link fleet → admiral (Fleet is non-temporal; normal UPDATE)
    if fleet_id is not None:
        conn.execute(
            "UPDATE Fleet SET admiral_id = ? WHERE fleet_id = ?",
            (admiral_id, fleet_id),
        )
    return admiral_id


def get_admiral(conn: sqlite3.Connection, admiral_id: int) -> AdmiralRow:
    row = conn.execute(
        "SELECT * FROM Admiral WHERE admiral_id = ? ORDER BY row_id DESC LIMIT 1",
        (admiral_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Admiral {admiral_id} not found")
    return _row_to_admiral(row)


def get_fleet_admiral(
    conn: sqlite3.Connection, fleet_id: int
) -> AdmiralRow | None:
    """Return the admiral assigned to fleet_id, or None."""
    row = conn.execute(
        """
        SELECT a.* FROM Admiral_head a
        JOIN   Fleet f ON f.admiral_id = a.admiral_id
        WHERE  f.fleet_id = ? AND a.status = 'active'
        """,
        (fleet_id,),
    ).fetchone()
    return _row_to_admiral(row) if row else None


def get_senior_admiral(
    conn: sqlite3.Connection, polity_id: int, fleet_ids: list[int]
) -> AdmiralRow | None:
    """Return the most senior (lowest admiral_id) active admiral across
    the given fleets.  Used for combined command resolution."""
    if not fleet_ids:
        return None
    placeholders = ",".join("?" * len(fleet_ids))
    row = conn.execute(
        f"""
        SELECT a.* FROM Admiral_head a
        WHERE  a.polity_id = ? AND a.status = 'active'
          AND  a.fleet_id IN ({placeholders})
        ORDER  BY a.admiral_id ASC
        LIMIT  1
        """,
        (polity_id, *fleet_ids),
    ).fetchone()
    return _row_to_admiral(row) if row else None


def transfer_command(
    conn: sqlite3.Connection, from_fleet_id: int, to_fleet_id: int,
    tick: int = 0, seq: int = 0,
) -> None:
    """Move the admiral from from_fleet_id to to_fleet_id.

    The receiving fleet's previous admiral (if any) is detached but not
    removed — they revert to unassigned.
    """
    row = conn.execute(
        "SELECT admiral_id FROM Fleet WHERE fleet_id = ?", (from_fleet_id,)
    ).fetchone()
    if row is None or row["admiral_id"] is None:
        return
    admiral_id = row["admiral_id"]
    # Detach from old fleet (Fleet non-temporal)
    conn.execute(
        "UPDATE Fleet SET admiral_id = NULL WHERE fleet_id = ?", (from_fleet_id,)
    )
    # Update admiral's fleet_id (temporal INSERT)
    cur = _current_admiral_row(conn, admiral_id)
    _insert_admiral_row(
        conn, admiral_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        tactical_factor=cur["tactical_factor"],
        fleet_id=None,
        created_tick=cur["created_tick"],
        retirement_tick=cur["retirement_tick"],
        status=cur["status"],
        tick=tick, seq=seq,
    )
    # Assign to new fleet (Fleet non-temporal)
    conn.execute(
        "UPDATE Fleet SET admiral_id = ? WHERE fleet_id = ?",
        (admiral_id, to_fleet_id),
    )
    # Update admiral row with new fleet_id
    cur2 = _current_admiral_row(conn, admiral_id)
    _insert_admiral_row(
        conn, admiral_id,
        polity_id=cur2["polity_id"],
        name=cur2["name"],
        tactical_factor=cur2["tactical_factor"],
        fleet_id=to_fleet_id,
        created_tick=cur2["created_tick"],
        retirement_tick=cur2["retirement_tick"],
        status=cur2["status"],
        tick=tick, seq=seq,
    )


def commission_on_demand(
    conn: sqlite3.Connection,
    polity_id: int,
    fleet_id: int,
    species_data: SpeciesData,
    tick: int,
    rng: Random,
    name_gen: NameGenerator,
) -> int:
    """Generate and assign an admiral to fleet_id on first combat contact.

    Returns the new admiral_id.
    """
    # Count existing admirals to derive a sequence number for the name.
    count = conn.execute(
        "SELECT COUNT(DISTINCT admiral_id) FROM Admiral WHERE polity_id = ?", (polity_id,)
    ).fetchone()[0]
    name = name_gen.admiral(sequence=count + 1)
    factor = generate_tactical_factor(species_data, rng)
    ret_tick = compute_retirement_tick(tick, species_data.lifespan_years, rng)
    return create_admiral(conn, polity_id, name, factor, fleet_id, tick, ret_tick)


def retire_admiral(
    conn: sqlite3.Connection,
    admiral_id: int,
    tick: int,
    seq: int = 0,
) -> None:
    """Mark an admiral as retired and detach from their fleet."""
    cur = _current_admiral_row(conn, admiral_id)
    if cur["fleet_id"] is not None:
        conn.execute(
            "UPDATE Fleet SET admiral_id = NULL WHERE fleet_id = ?",
            (cur["fleet_id"],),
        )
    _insert_admiral_row(
        conn, admiral_id,
        polity_id=cur["polity_id"],
        name=cur["name"],
        tactical_factor=cur["tactical_factor"],
        fleet_id=None,
        created_tick=cur["created_tick"],
        retirement_tick=cur["retirement_tick"],
        status="retired",
        tick=tick, seq=seq,
    )
    write_event(
        conn, tick=tick, phase=1,
        event_type="admiral_retired",
        summary=(
            f"admiral_id={admiral_id} name={cur['name']} "
            f"polity={cur['polity_id']} tactical_factor={cur['tactical_factor']}"
        ),
        polity_a_id=cur["polity_id"],
    )


def process_retirements(
    conn: sqlite3.Connection,
    polity_id: int,
    tick: int,
    species_data: SpeciesData,
    rng: Random,
    name_gen: NameGenerator,
) -> list[int]:
    """Retire any admirals of polity_id whose retirement_tick has passed.

    For each retired admiral who was commanding a fleet, commission a
    replacement immediately.

    Returns list of retired admiral_ids.
    """
    due = conn.execute(
        """
        SELECT * FROM Admiral_head
        WHERE  polity_id = ? AND status = 'active' AND retirement_tick <= ?
        """,
        (polity_id, tick),
    ).fetchall()

    retired_ids: list[int] = []
    for row in due:
        fleet_id = row["fleet_id"]
        retire_admiral(conn, row["admiral_id"], tick)
        retired_ids.append(row["admiral_id"])
        # Commission a replacement if the admiral was commanding a fleet
        if fleet_id is not None:
            commission_on_demand(conn, row["polity_id"], fleet_id,
                                 species_data, tick, rng, name_gen)
    return retired_ids


def _row_to_admiral(row: sqlite3.Row) -> AdmiralRow:
    return AdmiralRow(
        admiral_id=row["admiral_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        tactical_factor=row["tactical_factor"],
        fleet_id=row["fleet_id"],
        created_tick=row["created_tick"],
        retirement_tick=row["retirement_tick"],
        status=row["status"],
    )
