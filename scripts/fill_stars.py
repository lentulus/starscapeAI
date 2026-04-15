#!/usr/bin/env python3
"""Fill synthetic stars into IndexedIntegerDistinctStars to compensate for
catalog magnitude-limit incompleteness at large distances.

Algorithm
---------
The source catalog (Hipparcos-derived) is magnitude-limited: M dwarfs vanish
beyond ~100 pc, G dwarfs beyond ~300 pc.  Stars that should exist there are
simply absent.  This script:

  1. Calibrates a local catalog density rho_0 from observed systems within
     --calibration-radius-pc (default 300 pc), where the catalog is nearly
     complete for solar-neighbourhood stars.

  2. Divides a sphere of --sphere-radius-pc (default 1000 pc) into 100 pc
     cubic cells.  For each cell, estimates the expected system count using
     the double-exponential galactic disk model (scale heights 300/1000 pc),
     normalised by rho_0.

  3. Inserts (expected - observed) synthetic systems and stars per cell.
     Each primary gets a spectral type, absmag, ci drawn from IMF-weighted
     distributions.  A companion is probabilistically added using the same
     multiplicity rates as fill_spectral.py; companions share system_id.

  4. All inserted rows have source='fill'.  fill_spectral.py will skip them
     (spectral is already set).  compute_orbits.py should be (re-)run after
     this script to generate orbits for new multiple systems.

Dry-run mode
------------
--dry-run prints a table of 100 pc shells:
  Shell | Existing systems | Expected systems | To add (systems) | To add (stars)
without writing anything to the database.

Resume support
--------------
Cells already at or above expected count are skipped.  --max-minutes stops
cleanly; re-run to continue from where it left off.

Usage
-----
    uv run scripts/fill_stars.py --dry-run
    uv run scripts/fill_stars.py
    uv run scripts/fill_stars.py --max-minutes 240
    uv run scripts/fill_stars.py --db /path/to/other.db
"""

import argparse
import logging
import math
import random
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from starscape5.galaxy import (
    cell_expected_count,
    disk_density,
    draw_absmag,
    draw_ci,
    draw_spectral_class,
    eq_to_galactic_mpc,
)
from starscape5.spectral import (
    MULTIPLICITY_RATE,
    ci_from_absmag,
    format_spectral,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
STARS_TABLE   = "IndexedIntegerDistinctStars"
SYSTEMS_TABLE = "IndexedIntegerDistinctSystems"

DEFAULT_CELL_PC          = 100
DEFAULT_SPHERE_PC        = 1000
DEFAULT_CALIBRATION_PC   = 300
DEFAULT_BATCH            = 500
DEFAULT_MAX_MINUTES      = 120
_N_MC_SAMPLES            = 200   # Monte Carlo samples per cell
_MPC_PER_PC              = 1000

# Weighted mean companion probability across the IMF — used to estimate
# stars-per-system for the dry-run table without actually drawing companions.
_IMF_TOTAL = 0.003 + 0.13 + 0.6 + 3.0 + 7.6 + 12.1 + 76.45
_AVG_COMPANION_PROB = (
    0.003 * 0.75 + 0.13 * 0.70 + 0.6 * 0.50 + 3.0 * 0.46 +
    7.6 * 0.46 + 12.1 * 0.35 + 76.45 * 0.27
) / _IMF_TOTAL
_AVG_STARS_PER_SYSTEM = 1.0 + _AVG_COMPANION_PROB   # ≈ 1.30

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calibrate_rho0(conn: sqlite3.Connection, radius_pc: float) -> float:
    """Measure catalog system density (stars/pc³) within radius_pc of Sol."""
    radius_mpc = radius_pc * _MPC_PER_PC
    radius_mpc_sq = radius_mpc ** 2
    count = conn.execute(
        f"SELECT COUNT(*) FROM {SYSTEMS_TABLE}"
        " WHERE CAST(x AS REAL)*x + CAST(y AS REAL)*y + CAST(z AS REAL)*z <= ?",
        (radius_mpc_sq,),
    ).fetchone()[0]
    vol_pc3 = (4.0 / 3.0) * math.pi * radius_pc ** 3
    rho = count / vol_pc3 if vol_pc3 > 0 else 0.001
    log.info(
        "Calibrated rho_0 = %.6f systems/pc³ from %d catalog systems within %.0f pc",
        rho, count, radius_pc,
    )
    return rho


def _load_cell_counts(
    conn: sqlite3.Connection, cell_pc: float
) -> dict[tuple[int, int, int], int]:
    """Bucket all systems into grid cells. Returns {(ix,iy,iz): count}."""
    cell_mpc = cell_pc * _MPC_PER_PC
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    for row in conn.execute(f"SELECT x, y, z FROM {SYSTEMS_TABLE}"):
        ix = math.floor(row[0] / cell_mpc)
        iy = math.floor(row[1] / cell_mpc)
        iz = math.floor(row[2] / cell_mpc)
        counts[(ix, iy, iz)] += 1
    log.info("Bucketed existing systems into %d occupied grid cells", len(counts))
    return dict(counts)


def _should_create_companion(spectral: str, rng: random.Random) -> bool:
    """Multiplicity decision using the provided seeded RNG."""
    letter = spectral[0].upper() if spectral else "G"
    rate = MULTIPLICITY_RATE.get(letter, 0.40)
    return rng.random() < rate


def _cell_mc_rng(ix: int, iy: int, iz: int, base_seed: int) -> random.Random:
    """Return a per-cell RNG so Monte Carlo estimates are stable across runs.

    Using a deterministic seed per cell means dry-run and production produce
    the same expected counts for each cell regardless of iteration order.
    """
    return random.Random(hash((ix, iy, iz, base_seed)) & 0xFFFFFFFF)


def _print_shell_report(
    shell_stats: dict[int, dict],
    dry_run: bool,
) -> None:
    header = (
        f"  {'Shell':>12}  {'Exist.sys':>10}  {'Exp.sys':>10}"
        f"  {'Add sys':>8}  {'Add stars':>10}"
    )
    sep = "-" * len(header)
    print()
    print("Stellar fill — 100 pc shell breakdown" + (" (DRY RUN)" if dry_run else ""))
    print(sep)
    print(header)
    print(sep)
    tot_ex = tot_exp = tot_sys = tot_st = 0
    for shell in sorted(shell_stats):
        s = shell_stats[shell]
        print(
            f"  {shell:4d}–{shell + 100:<4d} pc"
            f"  {s['existing']:>10d}"
            f"  {s['expected']:>10.0f}"
            f"  {s['added_systems']:>8d}"
            f"  {s['added_stars']:>10d}"
        )
        tot_ex  += s["existing"]
        tot_exp += s["expected"]
        tot_sys += s["added_systems"]
        tot_st  += s["added_stars"]
    print(sep)
    print(
        f"  {'TOTAL':>12}"
        f"  {tot_ex:>10d}"
        f"  {tot_exp:>10.0f}"
        f"  {tot_sys:>8d}"
        f"  {tot_st:>10d}"
    )
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--cell-size-pc", type=float, default=DEFAULT_CELL_PC,
                        help="Grid cell edge length in pc (default: %(default)s)")
    parser.add_argument("--sphere-radius-pc", type=float, default=DEFAULT_SPHERE_PC,
                        help="Fill sphere radius around Sol in pc (default: %(default)s)")
    parser.add_argument("--calibration-radius-pc", type=float, default=DEFAULT_CALIBRATION_PC,
                        help="Radius used to calibrate local catalog density (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help="Systems between commits (default: %(default)s)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                        help="Stop after this many elapsed minutes (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print shell report without writing to the database")
    parser.add_argument("--seed", type=int, default=0,
                        help="Base seed for per-cell Monte Carlo RNGs (default: 0)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0

    # Main RNG for position and property draws (separate from per-cell MC RNGs)
    draw_rng = random.Random(args.seed + 1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        rho_0 = _calibrate_rho0(conn, args.calibration_radius_pc)
        if rho_0 <= 0:
            raise SystemExit("No catalog systems found within calibration radius")

        cell_pc   = args.cell_size_pc
        cell_mpc  = cell_pc * _MPC_PER_PC
        sphere_pc = args.sphere_radius_pc
        n_half    = math.ceil(sphere_pc / cell_pc)

        cell_counts = _load_cell_counts(conn, cell_pc)

        if not args.dry_run:
            next_system_id = (
                conn.execute(f"SELECT MAX(system_id) FROM {SYSTEMS_TABLE}").fetchone()[0] or 0
            ) + 1
            next_star_id = (
                conn.execute(f"SELECT MAX(star_id) FROM {STARS_TABLE}").fetchone()[0] or 0
            ) + 1

        shell_stats: dict[int, dict] = defaultdict(lambda: {
            "existing": 0, "expected": 0.0, "added_systems": 0, "added_stars": 0,
        })
        total_added_systems = 0
        total_added_stars   = 0

        for ix in range(-n_half, n_half):
            for iy in range(-n_half, n_half):
                for iz in range(-n_half, n_half):
                    cx_pc = (ix + 0.5) * cell_pc
                    cy_pc = (iy + 0.5) * cell_pc
                    cz_pc = (iz + 0.5) * cell_pc
                    dist_pc = math.sqrt(cx_pc**2 + cy_pc**2 + cz_pc**2)
                    if dist_pc > sphere_pc:
                        continue  # sphere-in-cube clip

                    cx_mpc = cx_pc * _MPC_PER_PC
                    cy_mpc = cy_pc * _MPC_PER_PC
                    cz_mpc = cz_pc * _MPC_PER_PC

                    # Per-cell seeded RNG for stable Monte Carlo estimates
                    mc_rng   = _cell_mc_rng(ix, iy, iz, args.seed)
                    existing = cell_counts.get((ix, iy, iz), 0)
                    expected = cell_expected_count(
                        cx_mpc, cy_mpc, cz_mpc, cell_pc, rho_0, mc_rng, _N_MC_SAMPLES
                    )
                    deficit = max(0, round(expected) - existing)

                    shell = int(dist_pc / 100) * 100
                    s = shell_stats[shell]
                    s["existing"] += existing
                    s["expected"] += expected
                    if deficit > 0:
                        s["added_systems"] += deficit
                        # Estimate stars for dry-run using mean multiplicity
                        s["added_stars"] += round(deficit * _AVG_STARS_PER_SYSTEM)

                    if args.dry_run or deficit == 0:
                        continue

                    if time.monotonic() >= deadline:
                        conn.commit()
                        log.info(
                            "Time limit reached after %d systems (%d stars). "
                            "Re-run to continue.",
                            total_added_systems, total_added_stars,
                        )
                        _print_shell_report(shell_stats, dry_run=False)
                        return

                    # --- Generate deficit systems for this cell ---
                    for _ in range(deficit):
                        # Position: uniform within cell
                        px_mpc = cx_mpc + draw_rng.uniform(-cell_mpc / 2, cell_mpc / 2)
                        py_mpc = cy_mpc + draw_rng.uniform(-cell_mpc / 2, cell_mpc / 2)
                        pz_mpc = cz_mpc + draw_rng.uniform(-cell_mpc / 2, cell_mpc / 2)

                        # Primary star properties
                        cls     = draw_spectral_class(draw_rng)
                        absmag  = draw_absmag(cls, draw_rng)
                        bv      = draw_ci(cls, draw_rng)
                        spectral = format_spectral(f"{bv:.4f}", absmag)

                        sys_id = next_system_id
                        conn.execute(
                            f"INSERT INTO {SYSTEMS_TABLE} (system_id, x, y, z)"
                            " VALUES (?, ?, ?, ?)",
                            (sys_id, round(px_mpc), round(py_mpc), round(pz_mpc)),
                        )
                        conn.execute(
                            f"INSERT INTO {STARS_TABLE}"
                            " (system_id, star_id, hip, ci, absmag, spectral, source)"
                            " VALUES (?, ?, NULL, ?, ?, ?, 'fill')",
                            (sys_id, next_star_id, f"{bv:.4f}", absmag, spectral),
                        )
                        next_system_id += 1
                        next_star_id   += 1
                        stars_this_system = 1

                        # Maybe add a companion (both share the same system_id)
                        if _should_create_companion(spectral, draw_rng):
                            q = draw_rng.uniform(0.1, 0.95)
                            comp_absmag  = absmag + (-10.0 * math.log10(q))
                            comp_ci_f    = ci_from_absmag(comp_absmag)
                            comp_spectral = format_spectral(f"{comp_ci_f:.4f}", comp_absmag)
                            conn.execute(
                                f"INSERT INTO {STARS_TABLE}"
                                " (system_id, star_id, hip, ci, absmag, spectral, source)"
                                " VALUES (?, ?, NULL, ?, ?, ?, 'fill')",
                                (sys_id, next_star_id,
                                 f"{comp_ci_f:.4f}", comp_absmag, comp_spectral),
                            )
                            next_star_id      += 1
                            stars_this_system += 1

                        total_added_systems += 1
                        total_added_stars   += stars_this_system

                        if total_added_systems % args.batch_size == 0:
                            conn.commit()
                            log.info(
                                "Progress: %d systems, %d stars inserted",
                                total_added_systems, total_added_stars,
                            )

        if not args.dry_run:
            conn.commit()
            log.info(
                "Done. Inserted %d systems, %d stars.",
                total_added_systems, total_added_stars,
            )

        _print_shell_report(shell_stats, dry_run=args.dry_run)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
