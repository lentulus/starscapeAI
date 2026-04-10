"""Admirals — naval commanders with species-biased tactical ability.

Admirals are generated on-demand when a fleet first enters a hostile system
with no commander.  Seniority is determined by admiral_id (creation order
within a polity): lower ID = more senior.  Combined command goes to the most
senior admiral present.

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
    status: str  # 'active' | 'killed' | 'captured'


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
# DB functions
# ---------------------------------------------------------------------------

def create_admiral(
    conn: sqlite3.Connection,
    polity_id: int,
    name: str,
    tactical_factor: int,
    fleet_id: int | None,
    created_tick: int,
) -> int:
    """Insert a new Admiral row and return its admiral_id."""
    cur = conn.execute(
        """
        INSERT INTO Admiral (polity_id, name, tactical_factor, fleet_id, created_tick)
        VALUES (?, ?, ?, ?, ?)
        """,
        (polity_id, name, tactical_factor, fleet_id, created_tick),
    )
    admiral_id = cur.lastrowid
    # Link fleet → admiral
    if fleet_id is not None:
        conn.execute(
            "UPDATE Fleet SET admiral_id = ? WHERE fleet_id = ?",
            (admiral_id, fleet_id),
        )
    return admiral_id  # type: ignore[return-value]


def get_admiral(conn: sqlite3.Connection, admiral_id: int) -> AdmiralRow:
    row = conn.execute(
        "SELECT * FROM Admiral WHERE admiral_id = ?", (admiral_id,)
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
        SELECT a.* FROM Admiral a
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
        SELECT a.* FROM Admiral a
        WHERE  a.polity_id = ? AND a.status = 'active'
          AND  a.fleet_id IN ({placeholders})
        ORDER  BY a.admiral_id ASC
        LIMIT  1
        """,
        (polity_id, *fleet_ids),
    ).fetchone()
    return _row_to_admiral(row) if row else None


def transfer_command(
    conn: sqlite3.Connection, from_fleet_id: int, to_fleet_id: int
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
    # Detach from old fleet
    conn.execute(
        "UPDATE Fleet SET admiral_id = NULL WHERE fleet_id = ?", (from_fleet_id,)
    )
    conn.execute(
        "UPDATE Admiral SET fleet_id = NULL WHERE admiral_id = ?", (admiral_id,)
    )
    # Assign to new fleet
    conn.execute(
        "UPDATE Fleet SET admiral_id = ? WHERE fleet_id = ?",
        (admiral_id, to_fleet_id),
    )
    conn.execute(
        "UPDATE Admiral SET fleet_id = ? WHERE admiral_id = ?",
        (to_fleet_id, admiral_id),
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
        "SELECT COUNT(*) FROM Admiral WHERE polity_id = ?", (polity_id,)
    ).fetchone()[0]
    name = name_gen.admiral(sequence=count + 1)
    factor = generate_tactical_factor(species_data, rng)
    return create_admiral(conn, polity_id, name, factor, fleet_id, tick)


def _row_to_admiral(row: sqlite3.Row) -> AdmiralRow:
    return AdmiralRow(
        admiral_id=row["admiral_id"],
        polity_id=row["polity_id"],
        name=row["name"],
        tactical_factor=row["tactical_factor"],
        fleet_id=row["fleet_id"],
        created_tick=row["created_tick"],
        status=row["status"],
    )
