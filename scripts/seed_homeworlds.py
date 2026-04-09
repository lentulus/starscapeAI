#!/usr/bin/env python3
"""Assign homeworld stars, generate planetary systems, and seed Earthlike
BodyMutable conditions for all 11 hand-authored sophont species.

Algorithm:
  - Humans: star_id 1 (Sol). Earth = HZ rocky planet with mass closest to 1.0 Mₑ.
    BodyMutable set to exact Earth values (288 K, 1.0 atm, 71% ocean).
  - Others: each gets a unique solitary F5–K5 star with ≥ 50 parsecs separation
    from every other chosen homeworld. A planetary system is generated, the best
    HZ rocky planet is identified, and Earthlike conditions are forced onto it.

Prerequisites (run these first):
  1. seed_sol.py        — Sol + solar system must exist in Bodies
  2. seed_species.py    — Species table must be populated

Usage:
    uv run scripts/seed_homeworlds.py
    uv run scripts/seed_homeworlds.py --db /path/to/other.db
    uv run scripts/seed_homeworlds.py --force     # re-assign even if already set
    uv run scripts/seed_homeworlds.py --seed 42   # reproducible star selection
"""

import argparse
import logging
import math
import random
import sqlite3
from pathlib import Path

from starscape5.atmosphere import escape_velocity_kms, surface_gravity, t_eq_k
from starscape5.orbits import enforce_stability, random_angles, thermal_eccentricity
from starscape5.planets import (
    belt_mass_earth,
    belt_positions,
    generate_belt,
    generate_moon,
    generate_planet,
    generate_planetoid,
    hz_bounds,
    moon_count,
    planet_count,
    planetoid_count,
    radius_from_mass,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
MIN_SEPARATION_PC = 50.0
PARSEC_TO_MPC = 1000  # DB stores coordinates as integer milliparsecs
PLANET_HILL_AU = 50.0
S_TYPE_FRACTION = 0.3
MIN_STABLE_AU = 0.05

# Exact Earth values
EARTH_MUTABLE = {
    "atm_type":         "standard",
    "atm_pressure_atm": 1.0,
    "atm_composition":  "n2o2",
    "surface_temp_k":   288.0,
    "hydrosphere":      0.71,
}
EARTH_PHYS = {
    "surface_gravity":      1.0,
    "escape_velocity_kms":  11.2,
    "t_eq_k":               255.0,
}

# Earthlike values applied to all other homeworlds
EARTHLIKE_MUTABLE = {
    "atm_type":         "standard",
    "atm_pressure_atm": 1.0,
    "atm_composition":  "n2o2",
    "surface_temp_k":   288.0,
    "hydrosphere":      0.71,
}

# Order determines which species gets which star when multiple need assignment.
# Human must be in the list but is handled separately (always star_id 1).
SPECIES_NAMES = [
    "Human",
    "Kreeth",
    "Vashori",
    "Kraathi",
    "Nakhavi",
    "Skharri",
    "Vaelkhi",
    "Shekhari",
    "Golvhaan",
    "Nhaveth",
    "Vardhek",
]

_INSERT_BODY = (
    "INSERT INTO Bodies"
    " (body_type, mass, radius, orbit_star_id, orbit_body_id,"
    "  semi_major_axis, eccentricity, inclination,"
    "  longitude_ascending_node, argument_periapsis, mean_anomaly, epoch,"
    "  in_hz, possible_tidal_lock, planet_class, has_rings,"
    "  comp_metallic, comp_carbonaceous, comp_stony, span_inner_au, span_outer_au)"
    " VALUES (:body_type, :mass, :radius, :orbit_star_id, :orbit_body_id,"
    "  :semi_major_axis, :eccentricity, :inclination,"
    "  :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch,"
    "  :in_hz, :possible_tidal_lock, :planet_class, :has_rings,"
    "  :comp_metallic, :comp_carbonaceous, :comp_stony, :span_inner_au, :span_outer_au)"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Star filtering
# ---------------------------------------------------------------------------

def _in_fgk5(spectral: str | None) -> bool:
    """Return True for F5–K5 spectral types.

    - All G (G0–G9) — fully within range
    - F with subtype digit ≥ 5 (F5, F6, F7, F8, F9)
    - K with subtype digit ≤ 5 (K0, K1, K2, K3, K4, K5)
    """
    if not spectral:
        return False
    s = spectral.strip()
    if not s:
        return False
    letter = s[0].upper()
    if letter == "G":
        return True
    if len(s) < 2 or not s[1].isdigit():
        return False
    subtype = int(s[1])
    if letter == "F":
        return subtype >= 5
    if letter == "K":
        return subtype <= 5
    return False


def _dist_pc(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Homeworld star selection
# ---------------------------------------------------------------------------

def select_homeworld_stars(
    conn: sqlite3.Connection,
    n: int,
    min_sep_pc: float,
    rng: random.Random,
) -> list[tuple[int, tuple[float, float, float]]]:
    """Return n (star_id, (x_pc, y_pc, z_pc)) tuples for suitable homeworld stars.

    Criteria: F5–K5, solitary (not in StarOrbits), no existing planets, not Sol.
    Each chosen star must be ≥ min_sep_pc parsecs from all other chosen stars.
    """
    log.info("Loading candidate homeworld stars (F5–K5, solitary, no planets)...")

    # Derive cube bounds from actual data and apply 100 pc inward buffer.
    # This keeps homeworlds well inside the simulation volume regardless of
    # the exact catalog extent.
    bounds = conn.execute("""
        SELECT MIN(x), MAX(x), MIN(y), MAX(y), MIN(z), MAX(z)
        FROM IndexedIntegerDistinctSystems
    """).fetchone()
    edge_buf_mpc = 100 * PARSEC_TO_MPC
    x_lo, x_hi = bounds[0] + edge_buf_mpc, bounds[1] - edge_buf_mpc
    y_lo, y_hi = bounds[2] + edge_buf_mpc, bounds[3] - edge_buf_mpc
    z_lo, z_hi = bounds[4] + edge_buf_mpc, bounds[5] - edge_buf_mpc
    log.info(
        "Cube bounds (mpc): x=[%d, %d]  y=[%d, %d]  z=[%d, %d]  (100 pc buffer applied)",
        x_lo, x_hi, y_lo, y_hi, z_lo, z_hi,
    )

    rows = conn.execute("""
        SELECT i.star_id, i.spectral, sys.x, sys.y, sys.z
        FROM IndexedIntegerDistinctStars i
        JOIN IndexedIntegerDistinctSystems sys USING (system_id)
        WHERE i.star_id NOT IN (SELECT star_id         FROM StarOrbits)
          AND i.star_id NOT IN (SELECT primary_star_id FROM StarOrbits)
          AND i.star_id NOT IN (
                SELECT DISTINCT orbit_star_id FROM Bodies
                WHERE orbit_star_id IS NOT NULL)
          AND i.star_id != 1
          AND sys.x BETWEEN ? AND ?
          AND sys.y BETWEEN ? AND ?
          AND sys.z BETWEEN ? AND ?
        ORDER BY i.star_id
    """, (x_lo, x_hi, y_lo, y_hi, z_lo, z_hi)).fetchall()

    # Spectral filtering in Python — SQLite LIKE can't express numeric ranges
    candidates: list[tuple[int, tuple[float, float, float]]] = [
        (
            r[0],
            (r[2] / PARSEC_TO_MPC, r[3] / PARSEC_TO_MPC, r[4] / PARSEC_TO_MPC),
        )
        for r in rows
        if _in_fgk5(r[1])
    ]
    log.info("  %d candidates after spectral + edge-buffer filter", len(candidates))
    if len(candidates) < n:
        raise RuntimeError(
            f"Only {len(candidates)} candidate stars available; need {n}."
        )

    rng.shuffle(candidates)

    chosen: list[tuple[int, tuple[float, float, float]]] = []
    for star_id, pos in candidates:
        if all(_dist_pc(pos, c[1]) >= min_sep_pc for c in chosen):
            chosen.append((star_id, pos))
            log.info(
                "  Selected star_id=%d at (%.0f, %.0f, %.0f) pc",
                star_id, *pos,
            )
            if len(chosen) == n:
                break

    if len(chosen) < n:
        raise RuntimeError(
            f"Could only find {len(chosen)} homeworld stars with ≥{min_sep_pc} pc "
            f"separation (needed {n}). Try a smaller --min-sep value."
        )

    return chosen


# ---------------------------------------------------------------------------
# Planet generation for a single star
# ---------------------------------------------------------------------------

def generate_planets_for_star(conn: sqlite3.Connection, star_id: int) -> None:
    """Generate and insert a complete planetary system for one star."""
    row = conn.execute("""
        SELECT i.spectral, e.luminosity
        FROM IndexedIntegerDistinctStars i
        LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
        WHERE i.star_id = ?
    """, (star_id,)).fetchone()
    if row is None:
        raise ValueError(f"star_id {star_id} not found in star catalog")

    spectral = (row[0] or "").strip()
    letter = spectral[0].upper() if spectral else "G"
    lum = row[1] if row[1] and row[1] > 0 else 1.0

    hz_inner, hz_outer = hz_bounds(lum)

    # Generate planets and enforce mutual stability
    planets = [generate_planet(star_id, lum) for _ in range(planet_count(letter))]
    planets.sort(key=lambda p: p["semi_major_axis"])
    planets = enforce_stability(planets, PLANET_HILL_AU)

    # Guarantee ≥1 HZ rocky planet for F/G/K stars (mirrors generate_planets.py)
    if letter in "FGK":
        has_hz_rocky = any(
            p["in_hz"] == 1
            and p["planet_class"] == "rocky"
            and 0.5 <= (p["mass"] or 0.0) <= 2.0
            for p in planets
        )
        if not has_hz_rocky and hz_inner < hz_outer:
            mass = random.uniform(0.5, 2.0)
            a = random.uniform(hz_inner, min(hz_outer, PLANET_HILL_AU))
            i_ang, lan, aop, ma = random_angles()
            planets.append({
                "body_type":                 "planet",
                "mass":                      mass,
                "radius":                    radius_from_mass(mass),
                "orbit_star_id":             star_id,
                "orbit_body_id":             None,
                "semi_major_axis":           a,
                "eccentricity":              thermal_eccentricity(),
                "inclination":               i_ang,
                "longitude_ascending_node":  lan,
                "argument_periapsis":        aop,
                "mean_anomaly":              ma,
                "epoch":                     0,
                "in_hz":                     1,
                "possible_tidal_lock":       1 if a < 0.5 * math.sqrt(lum) else 0,
                "planet_class":              "rocky",
                "has_rings":                 0,
                "comp_metallic":             None,
                "comp_carbonaceous":         None,
                "comp_stony":                None,
                "span_inner_au":             None,
                "span_outer_au":             None,
            })
            planets.sort(key=lambda p: p["semi_major_axis"])
            planets = enforce_stability(planets, PLANET_HILL_AU)

    # Insert planets and their moons
    for planet in planets:
        cur = conn.execute(_INSERT_BODY, planet)
        planet_body_id = cur.lastrowid
        planet_mass = planet["mass"] or 0.001

        n_moons = moon_count(planet_mass)
        if n_moons > 0:
            moons = [generate_moon(planet_body_id, planet_mass) for _ in range(n_moons)]
            moons.sort(key=lambda m: m["semi_major_axis"])
            hill_au = max((planet_mass ** (1.0 / 3.0)) * 0.01 * 0.5, 0.001)
            moons = enforce_stability(moons, hill_au)
            for moon in moons:
                conn.execute(_INSERT_BODY, moon)

    # Asteroid belts and significant planetoids
    for center_au, belt_ecc in belt_positions(planets, lum):
        if center_au > PLANET_HILL_AU:
            continue
        bmass = belt_mass_earth()
        conn.execute(_INSERT_BODY, generate_belt(
            star_id, center_au, belt_ecc, bmass, hz_inner, hz_outer, lum))
        for _ in range(planetoid_count()):
            conn.execute(_INSERT_BODY, generate_planetoid(
                star_id, center_au, belt_ecc, bmass, hz_inner, hz_outer))


# ---------------------------------------------------------------------------
# Homeworld planet selection
# ---------------------------------------------------------------------------

def find_earth_body_id(conn: sqlite3.Connection) -> int | None:
    """Return body_id of Earth: HZ rocky planet of star 1 with mass closest to 1.0 Mₑ."""
    row = conn.execute("""
        SELECT body_id FROM Bodies
        WHERE orbit_star_id = 1
          AND body_type = 'planet'
          AND planet_class = 'rocky'
        ORDER BY ABS(COALESCE(mass, 0) - 1.0)
        LIMIT 1
    """).fetchone()
    return row[0] if row else None


def pick_homeworld_planet(conn: sqlite3.Connection, star_id: int) -> int | None:
    """Return body_id of the best HZ rocky planet for homeworld assignment.

    Preference:
    1. rocky, in_hz=1, not tidally locked, mass in [0.5, 2.0] — closest to 1.0 Mₑ
    2. rocky, in_hz=1 — closest to 1.0 Mₑ (fallback)
    """
    rows = conn.execute("""
        SELECT body_id, mass, possible_tidal_lock
        FROM Bodies
        WHERE orbit_star_id = ?
          AND body_type = 'planet'
          AND planet_class = 'rocky'
          AND in_hz = 1
        ORDER BY ABS(COALESCE(mass, 1.0) - 1.0)
    """, (star_id,)).fetchall()

    if not rows:
        return None

    for row in rows:
        m = row[1]
        if row[2] == 0 and m is not None and 0.5 <= m <= 2.0:
            return row[0]

    return rows[0][0]  # best available HZ rocky planet


# ---------------------------------------------------------------------------
# Database writes
# ---------------------------------------------------------------------------

def _update_bodies_phys(conn: sqlite3.Connection, body_id: int, phys: dict) -> None:
    conn.execute("""
        UPDATE Bodies
        SET surface_gravity     = :surface_gravity,
            escape_velocity_kms = :escape_velocity_kms,
            t_eq_k              = :t_eq_k
        WHERE body_id = :body_id
    """, {**phys, "body_id": body_id})


def _upsert_body_mutable(conn: sqlite3.Connection, body_id: int, vals: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO BodyMutable
            (body_id, atm_type, atm_pressure_atm, atm_composition,
             surface_temp_k, hydrosphere, epoch)
        VALUES (:body_id, :atm_type, :atm_pressure_atm, :atm_composition,
                :surface_temp_k, :hydrosphere, 0)
    """, {"body_id": body_id, **vals})


def _set_homeworld(conn: sqlite3.Connection, species_name: str, body_id: int) -> None:
    conn.execute(
        "UPDATE Species SET homeworld_body_id = ? WHERE name = ?",
        (body_id, species_name),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--force", action="store_true",
                        help="Re-assign homeworlds even if already set")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for reproducible star selection")
    parser.add_argument("--min-sep", type=float, default=MIN_SEPARATION_PC,
                        help=f"Minimum parsec separation between homeworlds (default: {MIN_SEPARATION_PC})")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    rng = random.Random(args.seed)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        # --- Verify prerequisites ---
        earth_body_id = find_earth_body_id(conn)
        if earth_body_id is None:
            raise SystemExit(
                "Earth not found in Bodies (expected rocky planet with orbit_star_id=1). "
                "Run seed_sol.py first."
            )
        log.info("Earth identified: body_id=%d", earth_body_id)

        existing: dict[str, int | None] = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT name, homeworld_body_id FROM Species"
            ).fetchall()
        }
        if not existing:
            raise SystemExit("Species table is empty. Run seed_species.py first.")

        # Determine which species still need homeworld assignment
        needs: list[str] = []
        for name in SPECIES_NAMES:
            if name not in existing:
                log.warning("Species '%s' not in Species table — skipping", name)
                continue
            if existing[name] is not None and not args.force:
                log.info("  %-12s homeworld already set (body_id=%d) — skipping",
                         name, existing[name])
            else:
                needs.append(name)

        if not needs:
            log.info("All homeworlds already assigned. Use --force to reassign.")
            return

        log.info("Species to assign: %s", needs)

        # --- Human: Earth (star_id 1) ---
        if "Human" in needs:
            _update_bodies_phys(conn, earth_body_id, EARTH_PHYS)
            _upsert_body_mutable(conn, earth_body_id, EARTH_MUTABLE)
            _set_homeworld(conn, "Human", earth_body_id)
            conn.commit()
            log.info("  Human      → body_id %d (Earth, star_id 1)", earth_body_id)

        # --- Non-human species: select stars, generate systems, assign ---
        non_human = [n for n in needs if n != "Human"]
        if not non_human:
            log.info("Done (only Human needed assignment).")
            return

        chosen = select_homeworld_stars(conn, len(non_human), args.min_sep, rng)

        for species_name, (star_id, pos_pc) in zip(non_human, chosen):
            log.info("Processing %-12s → star_id=%d (%.0f, %.0f, %.0f pc)",
                     species_name, star_id, *pos_pc)

            # Generate planetary system
            generate_planets_for_star(conn, star_id)
            conn.commit()

            # Identify homeworld planet
            hw_body_id = pick_homeworld_planet(conn, star_id)
            if hw_body_id is None:
                log.error("  No suitable HZ rocky planet generated for star_id=%d — skipping", star_id)
                continue

            # Fetch planet and star properties for Bodies physics columns
            prow = conn.execute(
                "SELECT mass, radius, semi_major_axis FROM Bodies WHERE body_id = ?",
                (hw_body_id,),
            ).fetchone()
            lum_row = conn.execute(
                "SELECT e.luminosity FROM DistinctStarsExtended e WHERE e.star_id = ?",
                (star_id,),
            ).fetchone()

            mass   = (prow["mass"]            or 1.0)
            radius = (prow["radius"]           or 1.0)
            a_au   = (prow["semi_major_axis"]  or 1.0)
            lum    = (lum_row[0] if lum_row and lum_row[0] else 1.0)

            phys = {
                "surface_gravity":      surface_gravity(mass, radius),
                "escape_velocity_kms":  escape_velocity_kms(mass, radius),
                "t_eq_k":               t_eq_k(lum, a_au),
            }
            _update_bodies_phys(conn, hw_body_id, phys)
            _upsert_body_mutable(conn, hw_body_id, EARTHLIKE_MUTABLE)
            _set_homeworld(conn, species_name, hw_body_id)
            conn.commit()

            log.info("  %-12s → body_id %d  mass=%.2f Mₑ  a=%.3f AU  sg=%.2f g  T_eq=%.0f K",
                     species_name, hw_body_id, mass, a_au,
                     phys["surface_gravity"], phys["t_eq_k"])

        log.info("Done.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
