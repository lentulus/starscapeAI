#!/usr/bin/env python3
"""Analyse catalog completeness vs. the galactic disk density model.

Read-only diagnostic — makes no changes to the database.

Prints two tables:
  1. Per 100 pc shell: observed system count, expected count from disk model,
     fraction observed/expected.
  2. Completeness radius per spectral class — the shell where observed density
     drops below 50% of the expected model density.

Run before fill_stars.py to see the raw deficit, and again after to confirm
the density profile is now approximately flat.

Usage
-----
    uv run scripts/analyze_completeness.py
    uv run scripts/analyze_completeness.py --db /path/to/other.db
    uv run scripts/analyze_completeness.py --calibration-radius-pc 200
"""

import argparse
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from starscape5.galaxy import disk_density, disk_profile, eq_to_galactic_mpc

DEFAULT_DB              = Path("/Volumes/Data/starscape4/starscape.db")
STARS_TABLE             = "IndexedIntegerDistinctStars"
SYSTEMS_TABLE           = "IndexedIntegerDistinctSystems"
DEFAULT_CALIBRATION_PC  = 300
_MPC_PER_PC             = 1000


def _calibrate_rho0(conn: sqlite3.Connection, radius_pc: float) -> float:
    radius_mpc_sq = (radius_pc * _MPC_PER_PC) ** 2
    count = conn.execute(
        f"SELECT COUNT(*) FROM {SYSTEMS_TABLE}"
        " WHERE CAST(x AS REAL)*x + CAST(y AS REAL)*y + CAST(z AS REAL)*z <= ?",
        (radius_mpc_sq,),
    ).fetchone()[0]
    vol_pc3 = (4.0 / 3.0) * math.pi * radius_pc ** 3
    return count / vol_pc3 if vol_pc3 > 0 else 0.001


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--calibration-radius-pc", type=float, default=DEFAULT_CALIBRATION_PC,
                        help="Radius to calibrate rho_0 (default: %(default)s pc)")
    parser.add_argument("--max-radius-pc", type=float, default=1000,
                        help="Outer radius for analysis (default: %(default)s pc)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        rho_0 = _calibrate_rho0(conn, args.calibration_radius_pc)
        print(f"rho_0 (catalog density within {args.calibration_radius_pc:.0f} pc) = "
              f"{rho_0:.6f} systems/pc³\n")

        # ------------------------------------------------------------------ #
        # Load all system positions; bucket by 100 pc shell and spectral class
        # ------------------------------------------------------------------ #
        max_mpc_sq = (args.max_radius_pc * _MPC_PER_PC) ** 2

        # shell_obs:  {shell_pc: count of observed systems}
        # class_obs:  {(shell_pc, class_letter): count}
        shell_obs: dict[int, int]            = defaultdict(int)
        class_obs: dict[tuple, int]          = defaultdict(int)

        # Join systems + stars to get spectral class per system (primary only)
        rows = conn.execute(
            f"SELECT s.x, s.y, s.z, st.spectral"
            f" FROM {SYSTEMS_TABLE} s"
            f" JOIN {STARS_TABLE} st ON s.system_id = st.system_id"
            f" WHERE CAST(s.x AS REAL)*s.x + CAST(s.y AS REAL)*s.y"
            f"       + CAST(s.z AS REAL)*s.z <= ?"
            # Take one star per system (the one with the smallest star_id = primary)
            f" GROUP BY s.system_id HAVING st.star_id = MIN(st.star_id)",
            (max_mpc_sq,),
        ).fetchall()

        for row in rows:
            x, y, z = row["x"], row["y"], row["z"]
            dist_pc = math.sqrt(x**2 + y**2 + z**2) / _MPC_PER_PC
            shell = int(dist_pc / 100) * 100
            shell_obs[shell] += 1

            spectral = row["spectral"] or ""
            cls = spectral[0].upper() if spectral else "?"
            if cls not in "OBAFGKM":
                cls = "?"
            class_obs[(shell, cls)] += 1

        # ------------------------------------------------------------------ #
        # Table 1: shell observed vs. expected counts
        # ------------------------------------------------------------------ #
        print("Table 1 — System density by 100 pc shell")
        header = (
            f"  {'Shell':>12}  {'Obs.sys':>9}  {'Exp.sys':>9}"
            f"  {'Vol(pc³)':>12}  {'Obs/Exp':>8}"
        )
        sep = "-" * len(header)
        print(sep)
        print(header)
        print(sep)

        max_shell = int(args.max_radius_pc / 100) * 100
        for shell in range(0, max_shell, 100):
            # Shell volume (spherical annulus, clipped to sphere of max_radius)
            r_in  = shell
            r_out = shell + 100
            vol_pc3 = (4.0 / 3.0) * math.pi * (r_out**3 - r_in**3)

            # Expected = rho_0 × disk_profile(z_midplane_of_shell) × vol
            # Average disk_profile over the shell via midpoint radius and z=0
            # (approximate: true average would require integrating over solid angle)
            r_mid = (r_in + r_out) / 2.0
            # Use midplane (z_gal=0) reference; multiply by profile at shell midpoint
            # For a full sphere, the mean galactic z spans [−r_mid, +r_mid], so
            # the mean profile ≈ ∫₀^r₋ₘᵢ_ₐ disk_profile(z) dz / r_mid
            mean_profile = _mean_profile_1d(r_mid, 100.0)
            expected = rho_0 * mean_profile * vol_pc3

            obs = shell_obs.get(shell, 0)
            ratio = obs / expected if expected > 0 else 0.0
            print(
                f"  {shell:4d}–{shell + 100:<4d} pc"
                f"  {obs:>9d}"
                f"  {expected:>9.0f}"
                f"  {vol_pc3:>12,.0f}"
                f"  {ratio:>8.2f}"
            )

        print(sep)
        print()

        # ------------------------------------------------------------------ #
        # Table 2: spectral-class completeness radii
        # ------------------------------------------------------------------ #
        print("Table 2 — Completeness radius by spectral class")
        print("  (shell where observed density first drops below 50% of model)\n")
        header2 = f"  {'Class':>6}  {'Completeness radius':>22}"
        print(header2)
        print("-" * len(header2))

        for cls in list("OBAFGKM"):
            completeness_pc = _completeness_radius(
                shell_obs, class_obs, cls, rho_0, max_shell
            )
            if completeness_pc is None:
                print(f"  {cls:>6}  {'> max radius':>22}")
            else:
                print(f"  {cls:>6}  {completeness_pc:>18.0f} pc")

        print()

    finally:
        conn.close()


def _mean_profile_1d(r_mid: float, dr: float) -> float:
    """Approximate mean disk_profile over a spherical shell of radius r_mid ± dr/2.

    Averages over all galactic latitudes assuming isotropic distribution.
    Uses 50-point Gauss-Legendre-style numerical integration over cos(b).
    For simplicity uses a 50-point uniform sum over z_gal ∈ [−r, +r].
    """
    r = r_mid
    n = 50
    total = 0.0
    for i in range(n):
        z_pc = -r + (2 * r / n) * (i + 0.5)
        total += disk_profile(z_pc)
    return total / n


def _completeness_radius(
    shell_obs: dict[int, int],
    class_obs: dict[tuple, int],
    cls: str,
    rho_0: float,
    max_shell: int,
) -> int | None:
    """Return the 100 pc shell where class completeness first falls below 50%."""
    # IMF fraction for this class (approximate; used to scale rho_0)
    _IMF_FRAC = {"O": 0.00003, "B": 0.0013, "A": 0.006, "F": 0.030,
                 "G": 0.076, "K": 0.121, "M": 0.7645}
    frac = _IMF_FRAC.get(cls, 0.076)

    for shell in range(0, max_shell, 100):
        r_in  = shell
        r_out = shell + 100
        vol_pc3 = (4.0 / 3.0) * math.pi * (r_out**3 - r_in**3)
        r_mid = (r_in + r_out) / 2.0
        mean_p = _mean_profile_1d(r_mid, 100.0)
        expected_cls = rho_0 * frac * mean_p * vol_pc3

        obs_cls = class_obs.get((shell, cls), 0)
        if expected_cls > 0 and (obs_cls / expected_cls) < 0.5:
            return shell + 100  # first shell where we fall below 50%

    return None


if __name__ == "__main__":
    main()
