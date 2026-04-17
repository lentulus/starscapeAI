#!/usr/bin/env python3
"""WBH planet generation — full per-system pipeline.

For each star the script generates, in one pass:
  1. Orbit placement + world sizing (§4b–4e)
  2. Significant moons per planet (§Significant Moons, pp.55-57, 75-77)
  3. Atmosphere + hydrosphere for every rocky body (atmosphere.py)

Bodies rows and BeltProfile rows are committed together per batch.
Moons reference their parent planet via orbit_body_id, resolved at INSERT time.

Before generating, use --purge to delete all non-Sol Bodies rows first.
Sol (system_id = 1030192) is always skipped and never regenerated.

Usage:
    uv run scripts/generate_planets_wbh.py --purge
    uv run scripts/generate_planets_wbh.py           # resume from last run
    uv run scripts/generate_planets_wbh.py --max-minutes 120
    caffeinate -i uv run scripts/generate_planets_wbh.py --purge --max-minutes 600
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import re
import sqlite3
import time
from pathlib import Path

from starscape5.atmosphere import (
    atm_composition,
    atm_pressure_atm,
    classify_atm,
    hydrosphere,
    surface_temp_k,
    t_eq_k as _t_eq_k,
    escape_velocity_kms as _esc_vel_kms,
    surface_gravity as _surf_grav,
)

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
SOL_SYSTEM_ID = 1030192
DEFAULT_BATCH = 500
DEFAULT_MAX_MINUTES = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Companion star orbit generation (inline — used when a multi-star system is
# encountered during planet generation without existing StarOrbits rows).
# Mirrors generate_star_orbits_wbh.py so this script is self-contained.
# ---------------------------------------------------------------------------

def _co_2d() -> int:
    return random.randint(1, 6) + random.randint(1, 6)


def _co_separation_au_range(spectral_letter: str) -> tuple[float, float]:
    dm = {"O": 2, "B": 2, "A": 1, "F": 0, "G": 0, "K": 0,
          "M": -1, "L": -2, "T": -2}.get(spectral_letter.upper(), 0)
    roll = max(2, min(12, _co_2d() + dm))
    if roll <= 3:   return (0.02, 0.5)
    elif roll <= 5: return (0.5,  5.0)
    elif roll <= 7: return (5.0,  50.0)
    elif roll <= 9: return (50.0, 500.0)
    elif roll <= 11: return (500.0, 5000.0)
    else:            return (2000.0, 10000.0)


def _co_eccentricity(sma_au: float) -> float:
    if sma_au < 0.5:   return random.uniform(0.0,  0.08)
    elif sma_au < 5.0: return random.uniform(0.0,  0.40)
    elif sma_au < 50.: return random.uniform(0.0,  0.60)
    elif sma_au < 500: return random.uniform(0.05, 0.75)
    else:              return random.uniform(0.10, 0.90)


def _generate_companion_orbit_wbh(
    primary_mass_msol: float,
    companion_mass_msol: float,
    primary_radius_rsol: float,
    spectral_letter: str,
) -> dict:
    """Generate a WBH-style Keplerian orbit for one companion star."""
    lo, hi = _co_separation_au_range(spectral_letter)
    sma = math.exp(random.uniform(math.log(lo), math.log(hi)))
    e   = _co_eccentricity(sma)

    # Roche limit check — expand until periapsis is safe
    roche_au = 2.44 * primary_radius_rsol * 0.00465047 * (
        primary_mass_msol / max(companion_mass_msol, 0.01)
    ) ** (1.0 / 3.0)
    for _ in range(25):
        if sma * (1.0 - e) >= roche_au:
            break
        sma *= 1.5
        e    = _co_eccentricity(sma)
    else:
        sma, e = roche_au * 3.0, 0.1

    sma = min(sma, 10_000.0)

    return dict(
        semi_major_axis          = sma,
        eccentricity             = e,
        inclination              = random.uniform(0.0, math.pi),
        longitude_ascending_node = random.uniform(0.0, 2.0 * math.pi),
        argument_periapsis       = random.uniform(0.0, 2.0 * math.pi),
        mean_anomaly             = random.uniform(0.0, 2.0 * math.pi),
        epoch                    = 0,
    )


_ORBIT_INSERT_SQL = """
INSERT OR IGNORE INTO StarOrbits
    (star_id, primary_star_id, semi_major_axis, eccentricity, inclination,
     longitude_ascending_node, argument_periapsis, mean_anomaly, epoch)
VALUES
    (:star_id, :primary_star_id, :semi_major_axis, :eccentricity, :inclination,
     :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch)
"""


def _inline_generate_system_orbits(
    conn: sqlite3.Connection,
    system_id: int,
    binary_cap: dict[int, float],
    binary_stars: set[int],
    binary_plane: dict[int, tuple[float, float]],
) -> None:
    """Generate companion orbits for one multi-star system that has none.

    Inserts into StarOrbits and updates binary_cap / binary_stars /
    binary_plane in-place.
    """
    stars = conn.execute(
        """
        SELECT i.star_id, i.spectral,
               COALESCE(e.mass,       1.0) AS mass_msol,
               COALESCE(e.luminosity, 0.0) AS luminosity,
               COALESCE(e.radius,     1.0) AS radius_rsol
        FROM   IndexedIntegerDistinctStars i
        LEFT JOIN DistinctStarsExtended    e ON i.star_id = e.star_id
        WHERE  i.system_id = ?
        ORDER BY COALESCE(e.luminosity, 0.0) DESC, i.star_id ASC
        """,
        (system_id,),
    ).fetchall()

    if len(stars) < 2:
        return

    primary         = stars[0]
    primary_star_id = primary["star_id"]
    letter          = ((primary["spectral"] or "G").strip() or "G")[0].upper()

    for companion in stars[1:]:
        cid = companion["star_id"]
        orbit = _generate_companion_orbit_wbh(
            primary_mass_msol   = float(primary["mass_msol"]),
            companion_mass_msol = float(companion["mass_msol"]),
            primary_radius_rsol = float(primary["radius_rsol"]),
            spectral_letter     = letter,
        )
        orbit["star_id"]         = cid
        orbit["primary_star_id"] = primary_star_id

        conn.execute(_ORBIT_INSERT_SQL, orbit)

        cap = orbit["semi_major_axis"] * 0.3
        if cid not in binary_cap or cap < binary_cap[cid]:
            binary_cap[cid] = cap
        if primary_star_id not in binary_cap or cap < binary_cap[primary_star_id]:
            binary_cap[primary_star_id] = cap
        binary_stars.add(cid)
        binary_stars.add(primary_star_id)

        # Record the orbital plane so planet generation can align to it.
        # All companions in the system share the primary's reference plane
        # (hierarchical triples share the inner binary's plane to first order).
        plane = (orbit["inclination"], orbit["longitude_ascending_node"])
        binary_plane[cid]          = plane
        binary_plane[primary_star_id] = plane

    conn.commit()


# ---------------------------------------------------------------------------
# WBH Orbit# <-> AU lookup table  (§4a)
# ---------------------------------------------------------------------------

_ORBIT_TABLE: list[tuple[float, float]] = [
    (0.0, 0.20), (0.5, 0.25), (1.0, 0.40), (1.5, 0.52), (2.0, 0.65),
    (2.5, 0.79), (3.0, 0.97), (3.5, 1.32), (4.0, 1.60), (4.5, 2.00),
    (5.0, 3.00), (5.5, 4.00), (6.0, 5.20), (6.5, 7.20), (7.0, 10.0),
    (7.5, 14.0), (8.0, 20.0), (8.5, 30.0), (9.0, 44.0), (9.5, 58.5),
]


def orbit_num_to_au(n: float) -> float:
    """Convert WBH Orbit# to AU via linear interpolation; power-law beyond 9.5."""
    if n <= _ORBIT_TABLE[0][0]:
        return _ORBIT_TABLE[0][1]
    if n >= _ORBIT_TABLE[-1][0]:
        n0, a0 = _ORBIT_TABLE[-2]
        n1, a1 = _ORBIT_TABLE[-1]
        ratio = a1 / a0
        extra = (n - n1) / (n1 - n0)
        return a1 * (ratio ** extra)
    for i in range(len(_ORBIT_TABLE) - 1):
        n0, a0 = _ORBIT_TABLE[i]
        n1, a1 = _ORBIT_TABLE[i + 1]
        if n0 <= n <= n1:
            t = (n - n0) / (n1 - n0)
            return a0 + t * (a1 - a0)
    return _ORBIT_TABLE[-1][1]


def au_to_orbit_num(au: float) -> float:
    """Convert AU to WBH Orbit# via linear interpolation; power-law beyond 58.5 AU."""
    if au <= _ORBIT_TABLE[0][1]:
        return _ORBIT_TABLE[0][0]
    if au >= _ORBIT_TABLE[-1][1]:
        n0, a0 = _ORBIT_TABLE[-2]
        n1, a1 = _ORBIT_TABLE[-1]
        ratio = a1 / a0
        extra = math.log(au / a1) / math.log(ratio)
        return n1 + extra * (n1 - n0)
    for i in range(len(_ORBIT_TABLE) - 1):
        n0, a0 = _ORBIT_TABLE[i]
        n1, a1 = _ORBIT_TABLE[i + 1]
        if a0 <= au <= a1:
            t = (au - a0) / (a1 - a0)
            return n0 + t * (n1 - n0)
    return _ORBIT_TABLE[-1][0]


# ---------------------------------------------------------------------------
# MAO (Minimum Allowable Orbit#) by spectral class  (§4b Step 2)
# ---------------------------------------------------------------------------

_MAO: dict[str, float] = {
    'O': 3.5, 'B': 3.5, 'A': 3.0,
    'F': 2.5, 'G': 2.0, 'K': 1.5, 'M': 1.0,
}
_MAO_SUBDWARF = 0.5  # M VI / brown dwarf


# ---------------------------------------------------------------------------
# Dice helpers
# ---------------------------------------------------------------------------

def d3() -> int:
    return random.randint(1, 3)


def d6() -> int:
    return random.randint(1, 6)


def two_d6() -> int:
    return d6() + d6()


def _random_orbital_angles() -> tuple[float, float, float]:
    """Return (lan_rad, aop_rad, ma_rad) drawn uniformly."""
    return (
        random.uniform(0.0, 2 * math.pi),
        random.uniform(0.0, 2 * math.pi),
        random.uniform(0.0, 2 * math.pi),
    )


# ---------------------------------------------------------------------------
# Spectral type parsing
# ---------------------------------------------------------------------------

_SPECTRAL_RE = re.compile(
    r'^([OBAFGKMobafgkm])\s*(\d*\.?\d*)\s*(I{1,3}|IV|VI?)?',
    re.IGNORECASE,
)


def parse_spectral(s: str) -> tuple[str, float, str]:
    """Return (letter_upper, subtype_float, lum_class_upper).

    Defaults: ('G', 5.0, 'V') for unparseable input.
    """
    if not s:
        return 'G', 5.0, 'V'
    m = _SPECTRAL_RE.match(s.strip())
    if not m:
        return s[0].upper() if s else 'G', 5.0, 'V'
    letter = m.group(1).upper()
    sub_str = m.group(2)
    sub = float(sub_str) if sub_str else 5.0
    lum_raw = (m.group(3) or 'V').upper()
    # Normalise: treat missing as V
    lum_class = lum_raw if lum_raw else 'V'
    return letter, sub, lum_class


def is_fgk_continuation_candidate(letter: str, subtype: float, lum_class: str) -> bool:
    """True for solitary F5–K5 main-sequence stars (§3a)."""
    if lum_class not in ('V', ''):
        return False
    if letter == 'F' and subtype >= 5.0:
        return True
    if letter == 'G':
        return True
    if letter == 'K' and subtype <= 5.0:
        return True
    return False


# ---------------------------------------------------------------------------
# Eccentricity table  (§4b Step 7) — no hard cap
# ---------------------------------------------------------------------------

# (inclusive_max_roll, e_lo, e_hi)
_ECC_TABLE: list[tuple[int, float, float]] = [
    (2,   0.00, 0.04),
    (6,   0.05, 0.09),
    (8,   0.10, 0.14),
    (9,   0.15, 0.19),
    (10,  0.20, 0.29),
    (11,  0.30, 0.39),
    (12,  0.40, 0.49),
    (13,  0.50, 0.59),
    (14,  0.60, 0.74),
    (999, 0.75, 0.97),
]


def roll_eccentricity(orbit_num: float, anomalous_eccentric: bool = False) -> float:
    """Roll eccentricity from WBH table with appropriate DMs."""
    dm = 0
    if orbit_num < 1.5:
        dm -= 2
    if anomalous_eccentric:
        dm += 2
    roll = two_d6() + dm
    for max_r, lo, hi in _ECC_TABLE:
        if roll <= max_r:
            return random.uniform(lo, hi)
    return random.uniform(0.75, 0.97)


def _inclination_rad(anom_inclined: bool, anom_retrograde: bool) -> float:
    """Roll inclination with low-inclination prior for normal orbits."""
    if anom_retrograde:
        deg = random.uniform(135.0, 180.0)   # clearly retrograde
    elif anom_inclined:
        deg = random.uniform(20.0, 45.0)     # notably inclined but not projection-ambiguous
    else:
        deg = abs(random.gauss(0.0, 5.0))
        deg = min(deg, 20.0)
    return math.radians(deg)


# ---------------------------------------------------------------------------
# Terrestrial size bands  (§4c)
# ---------------------------------------------------------------------------

# Index 0 = 'S', 1 = '1', … 15 = 'F'
_SIZE_CODES = ['S', '1', '2', '3', '4', '5', '6', '7', '8', '9',
               'A', 'B', 'C', 'D', 'E', 'F']

# (min_km, max_km) — defines the valid band for each size code
_SIZE_BAND_KM: dict[str, tuple[float, float]] = {
    'S': (400,   799),
    '1': (800,   2399),
    '2': (2400,  3999),
    '3': (4000,  5599),
    '4': (5600,  7199),
    '5': (7200,  8799),
    '6': (8800,  10399),
    '7': (10400, 11999),
    '8': (12000, 13599),
    '9': (13600, 15199),
    'A': (15200, 16799),
    'B': (16800, 18399),
    'C': (18400, 19999),
    'D': (20000, 21599),
    'E': (21600, 23199),
    'F': (23200, 24799),
}


def _size_code_to_int(code: str) -> int:
    """Map size code to integer ordinal (S→0, 1→1, …, F→16)."""
    if code.upper() == 'S':
        return 0
    try:
        return int(code, 16)
    except ValueError:
        return 5


def roll_diameter(size_code: str) -> float:
    """Roll actual diameter within the WBH size band (§4c, d100-precision)."""
    band = _SIZE_BAND_KM.get(size_code.upper())
    if band is None:
        return 0.0
    lo, hi = band
    # D3 coarse step (0 / +600 / +1200 km) + 1D fine (+0–500) + d100 (+0–99)
    step     = (d3() - 1) * 600
    fine     = random.randint(0, 500)
    veryfine = random.randint(0, 99)
    return float(max(lo, min(hi, lo + step + fine + veryfine)))


# ---------------------------------------------------------------------------
# Composition and density  (§4d)
# ---------------------------------------------------------------------------

_COMP_TABLE: list[tuple[int, str]] = [
    (-3,  'Exotic Ice'),
    (2,   'Mostly Ice'),
    (6,   'Mostly Rock'),
    (11,  'Rock and Metal'),
    (14,  'Mostly Metal'),
    (999, 'Compressed Metal'),
]

_DENSITY_RANGES: dict[str, tuple[float, float]] = {
    'Exotic Ice':       (0.03, 0.15),
    'Mostly Ice':       (0.15, 0.35),
    'Mostly Rock':      (0.35, 0.65),
    'Rock and Metal':   (0.65, 1.10),
    'Mostly Metal':     (1.10, 1.60),
    'Compressed Metal': (1.60, 2.00),
}


def roll_composition(size_code: str, orbit_num: float, hzco: float,
                     age_gyr: float) -> str:
    """Roll terrestrial composition with WBH DMs (§4d)."""
    dm = 0
    s = _size_code_to_int(size_code)
    if s <= 4:
        dm -= 1
    elif 6 <= s <= 9:
        dm += 1
    elif s >= 10:
        dm += 3
    if orbit_num <= hzco:
        dm += 1
    else:
        dm -= int(orbit_num - hzco)
    if age_gyr > 10.0:
        dm -= 1
    roll = two_d6() + dm
    for max_r, comp in _COMP_TABLE:
        if roll <= max_r:
            return comp
    return 'Compressed Metal'


def roll_density(composition: str) -> float:
    lo, hi = _DENSITY_RANGES.get(composition, (0.65, 1.10))
    return random.uniform(lo, hi)


def derive_physical(diameter_km: float, density: float) -> tuple[float, float, float]:
    """Compute (gravity_g, mass_earth, escape_vel_kms) from WBH physical chain (§4d).

        gravity   = density × (D/12742)
        mass      = density × (D/12742)³
        esc_vel   = sqrt(mass / (D/12742)) × 11.186
    """
    d_ratio = diameter_km / 12742.0
    gravity = density * d_ratio
    mass_e  = density * d_ratio ** 3
    esc_vel = math.sqrt(max(0.0, mass_e / max(d_ratio, 1e-9))) * 11.186
    return gravity, mass_e, esc_vel


# ---------------------------------------------------------------------------
# Gas giant sizing  (§4e)
# ---------------------------------------------------------------------------

def roll_gg_size() -> tuple[str, float, float, str]:
    """Roll gas giant category, diameter, and mass.

    Returns (size_code, diameter_km, mass_earth, planet_class).
    Density is derived from mass and diameter, not stored directly.
    """
    cat = d6()
    if cat <= 2:
        # Small GG: 2–6 × Terra diameter; 10–35 Mₑ
        size_factor = d3() + d3()           # 2–6
        diameter_km = size_factor * 12742.0
        mass_e      = float(5 * (d6() + 1))  # 10–35
        return 'GS', diameter_km, mass_e, 'small_gg'
    elif cat <= 4:
        # Medium GG: 7–12 × Terra; 40–340 Mₑ
        size_factor = d6() + 6              # 7–12
        diameter_km = size_factor * 12742.0
        mass_e      = float(20 * max(2, d6() + d6() + d6() - 1))
        return 'GM', diameter_km, mass_e, 'medium_gg'
    else:
        # Large GG: 8–18 × Terra; 350–4000 Mₑ
        size_factor = d6() + d6() + 6      # 8–18
        diameter_km = size_factor * 12742.0
        mass_e      = float(min(4000, d3() * 50 * (d6() + d6() + d6() + 4)))
        return 'GL', diameter_km, mass_e, 'large_gg'


# ---------------------------------------------------------------------------
# Orbital stability enforcement
# ---------------------------------------------------------------------------

def enforce_orbital_stability(bodies: list[dict], clearance: float = 0.01) -> list[dict]:
    """Reduce eccentricities to eliminate radial orbit crossing between planets.

    For each adjacent pair of planets sorted by SMA, if apo(inner) is not
    below peri(outer) by at least `clearance` fraction, the more eccentric
    body's eccentricity is reduced until the gap is satisfied.  Iterates
    until no crossing pairs remain (max 50 passes).

    Why adjacent pairs only: if all adjacent pairs satisfy apo(i) < peri(i+1),
    then for any non-adjacent pair (i, k) with i < j < k the chain
        apo(i) < peri(i+1) ≤ apo(i+1) < … < peri(k)
    guarantees apo(i) < peri(k) by transitivity — so non-adjacent crossings
    are impossible once all adjacent ones are resolved.

    Belts are excluded; they have no meaningful periapsis/apoapsis in Phase 1.
    """
    planets = sorted(
        [b for b in bodies if b['body_type'] == 'planet'],
        key=lambda b: b['semi_major_axis'],
    )
    others = [b for b in bodies if b['body_type'] != 'planet']

    for _ in range(50):
        changed = False
        for idx in range(len(planets) - 1):
            bi = planets[idx]
            bj = planets[idx + 1]
            ai, ei = bi['semi_major_axis'], bi['eccentricity']
            aj, ej = bj['semi_major_axis'], bj['eccentricity']

            apo_i  = ai * (1.0 + ei)
            peri_j = aj * (1.0 - ej)

            # Required: apo_i * (1 + clearance) <= peri_j
            # Tolerance of 1e-10 AU absorbs floating-point rounding when the
            # enforcement already set the pair exactly at the clearance boundary.
            if apo_i * (1.0 + clearance) <= peri_j + 1e-10:
                continue

            # Reduce the more eccentric body first.
            if ei >= ej:
                # Lower ei so that ai*(1+ei_new)*(1+clearance) = peri_j
                ei_new = max(0.0, peri_j / (ai * (1.0 + clearance)) - 1.0)
                bi['eccentricity'] = ei_new
                # If ei hit zero and still crossing, also reduce ej
                new_apo = ai * (1.0 + bi['eccentricity'])
                if new_apo * (1.0 + clearance) > peri_j:
                    ej_new = max(0.0, 1.0 - new_apo * (1.0 + clearance) / aj)
                    bj['eccentricity'] = ej_new
            else:
                # Lower ej so that apo_i*(1+clearance) = aj*(1-ej_new)
                ej_new = max(0.0, 1.0 - apo_i * (1.0 + clearance) / aj)
                bj['eccentricity'] = ej_new
                # If ej hit zero and still crossing, also reduce ei
                new_peri = aj * (1.0 - bj['eccentricity'])
                if apo_i * (1.0 + clearance) > new_peri:
                    ei_new = max(0.0, new_peri / (ai * (1.0 + clearance)) - 1.0)
                    bi['eccentricity'] = ei_new

            changed = True

        if not changed:
            break

    return planets + others


# ---------------------------------------------------------------------------
# Atmosphere helpers
# ---------------------------------------------------------------------------

def _possible_tidal_lock(au: float, luminosity: float) -> int:
    """1 if the planet is likely tidally locked to its star (rough cutoff)."""
    # Tidal locking timescale ∝ a^6; for a Sun-like star tidally locked
    # within ~100 Myr at 0.1 AU.  Scale by L^0.5 (effective HZ distance).
    return 1 if au < 0.15 * math.sqrt(max(luminosity, 1e-6)) else 0


def _mutable_dict(
    mass_earth: float,
    radius_re: float,
    a_au: float,
    luminosity: float,
    in_hz: int,
    tidal_lock: int,
) -> dict:
    """Compute BodyMutable fields for one rocky body."""
    teq   = _t_eq_k(luminosity, a_au)
    v_esc = _esc_vel_kms(mass_earth, radius_re)
    sg    = _surf_grav(mass_earth, radius_re)
    atm   = classify_atm(v_esc, teq, in_hz, tidal_lock)
    comp  = atm_composition(atm, teq)
    press = atm_pressure_atm(atm)
    stemp = surface_temp_k(teq, atm)
    hydro = hydrosphere(atm, in_hz, stemp)
    return dict(
        atm_type         = atm,
        atm_pressure_atm = press,
        atm_composition  = comp,
        surface_temp_k   = stemp,
        hydrosphere      = hydro,
        # Physical values echoed back so the INSERT can populate Bodies columns too
        _t_eq_k          = teq,
        _v_esc           = v_esc,
        _sg              = sg,
    )


# ---------------------------------------------------------------------------
# Rotation  (WBH §4f–4g)
# ---------------------------------------------------------------------------

def _tidal_lock_status(orbit_num: float, hzco: float) -> str:
    """Tidal lock resonance category from orbit placement relative to HZ (§4f).

    Thresholds (orbit_num vs HZCO):
      ≤ HZCO−3        → always 1:1
      ≤ HZCO−2        → roll 2D: 9+ = 1:1, 7–8 = 3:2, 5–6 = slow_prograde
      ≤ HZCO−1        → roll 2D: 10+ = 3:2, 8–9 = slow_prograde
      > HZCO−1        → anomalous slow/retrograde on 12
    """
    delta = orbit_num - hzco
    if delta <= -3.0:
        return '1:1'
    if delta <= -2.0:
        r = two_d6()
        if r >= 9: return '1:1'
        if r >= 7: return '3:2'
        if r >= 5: return 'slow_prograde'
        return 'none'
    if delta <= -1.0:
        r = two_d6()
        if r >= 10: return '3:2'
        if r >= 8:  return 'slow_prograde'
        return 'none'
    r = two_d6()
    if r == 12:
        return 'slow_retrograde' if random.random() < 0.4 else 'slow_prograde'
    return 'none'


def _roll_axial_tilt() -> float:
    """Axial tilt in degrees (0–90+) from WBH table (§4g)."""
    r = two_d6()
    if r <= 4:  return random.uniform(0.0,  5.0)
    if r <= 6:  return random.uniform(5.0,  15.0)
    if r <= 8:  return random.uniform(15.0, 30.0)
    if r <= 10: return random.uniform(30.0, 50.0)
    if r == 11: return random.uniform(50.0, 70.0)
    return random.uniform(70.0, 90.0)


def _rotation_period(
    tidal_status:   str,
    si:             int,
    a_au:           float,
    star_mass_msol: float,
) -> tuple[float, float | None]:
    """Return (sidereal_day_hours, solar_day_hours).

    solar_day_hours is None for 1:1/3:2 locks — not a meaningful concept.
    Negative sidereal = retrograde rotation.

    WBH §4f rotation period:
      1:1          → sidereal = orbital period
      3:2          → sidereal = 2/3 × orbital period
      slow_*       → 2D×100 + si×20 hours
      normal       → (2D + si) × 2 hours, min 6 h
    """
    orbital_hr = math.sqrt(
        max(a_au, 1e-4) ** 3 / max(star_mass_msol, 0.05)
    ) * 8766.0

    if tidal_status == '1:1':
        return orbital_hr, None
    if tidal_status == '3:2':
        return orbital_hr * (2.0 / 3.0), None
    if tidal_status == 'slow_prograde':
        return float(two_d6() * 100 + si * 20), None
    if tidal_status == 'slow_retrograde':
        return -float(two_d6() * 100 + si * 20), None

    # Normal rotation (occasional retrograde anomaly)
    sid = float(max(6, (d6() + d6() + si) * 2))
    if two_d6() >= 12 and random.random() < 0.3:
        sid = -sid

    sid_abs = abs(sid)
    if sid_abs >= orbital_hr:
        return sid, None
    if sid > 0:
        denom = orbital_hr - sid
        solar: float | None = sid * orbital_hr / denom if denom > 1e-6 else None
        if solar is not None:
            solar = max(sid, min(solar, 8_766_000.0))
    else:
        solar = sid_abs * orbital_hr / (orbital_hr + sid_abs)
    return sid, solar


def _rotation_attrs(
    orbit_num:      float,
    hzco:           float,
    size_code:      str,
    a_au:           float,
    star_mass_msol: float,
) -> dict:
    """All rotation-related Bodies fields as a dict."""
    si     = _size_code_to_int(size_code)
    status = _tidal_lock_status(orbit_num, hzco)
    tilt   = _roll_axial_tilt()
    sid, solar = _rotation_period(status, si, a_au, star_mass_msol)
    return {
        'tidal_lock_status':  status,
        'sidereal_day_hours': round(sid,   2),
        'solar_day_hours':    round(solar, 2) if solar is not None else None,
        'axial_tilt_deg':     round(tilt,  1),
    }


# ---------------------------------------------------------------------------
# Seismic  (WBH §4h)
# ---------------------------------------------------------------------------

def _seismic_residual(size_code: str, age_gyr: float) -> float:
    """Residual internal heat stress from formation (§4h).

    Base = 2D−7 + si÷2; penalise 1 per 2 Gyr beyond 5 Gyr.
    """
    si   = _size_code_to_int(size_code)
    base = float(two_d6() - 7 + si // 2)
    base -= max(0.0, (age_gyr - 5.0) / 2.0)
    return max(0.0, round(base, 2))


def _seismic_tidal_from_moons(planet_moons: list[dict]) -> float:
    """Tidal stress on a planet from its significant moons (§4h)."""
    total = 0.0
    for m in planet_moons:
        si   = _size_code_to_int(m.get('size_code') or 'S')
        m_pd = m.get('moon_PD') or 0.0
        if si >= 6:
            if m_pd < 5:    total += 3.0
            elif m_pd < 10: total += 2.0
            elif m_pd < 25: total += 1.0
        elif si >= 3:
            if m_pd < 5:    total += 2.0
            elif m_pd < 15: total += 1.0
        else:
            if m_pd < 5:    total += 0.5
    return round(total, 2)


def _seismic_tidal_from_parent(parent_mass_earth: float, moon_pd: float) -> float:
    """Tidal stress on a moon from its parent body.

    Significant for inner moons of gas giants (Io/Europa scale).
    """
    if parent_mass_earth <= 0 or moon_pd <= 0:
        return 0.0
    mass_factor  = math.log10(max(1.0, parent_mass_earth)) / math.log10(300.0)
    dist_factor  = max(0.0, 1.0 - moon_pd / 50.0) ** 2
    return round(min(5.0, mass_factor * dist_factor * 6.0), 2)


def _seismic_heating(seismic_tidal: float) -> float:
    return round(seismic_tidal * 0.8, 2)


def _tectonic_plates(seismic_total: float) -> int | None:
    if seismic_total < 3.0:
        return None
    if seismic_total < 6.0:
        return d3()
    if seismic_total < 10.0:
        return d6() + 2
    return d6() + d6()


def _seismic_attrs(
    size_code:    str,
    age_gyr:      float,
    planet_moons: list[dict],
) -> dict:
    """All seismic fields for a planet body."""
    res   = _seismic_residual(size_code, age_gyr)
    tidal = _seismic_tidal_from_moons(planet_moons)
    heat  = _seismic_heating(tidal)
    total = round(res + tidal + heat, 2)
    return {
        'seismic_residual': res,
        'seismic_tidal':    tidal,
        'seismic_heating':  heat,
        'seismic_total':    total,
        'tectonic_plates':  _tectonic_plates(total),
    }


def _moon_seismic_attrs(
    size_code:         str,
    age_gyr:           float,
    parent_mass_earth: float,
    moon_pd:           float,
) -> dict:
    """All seismic fields for a moon body."""
    res   = _seismic_residual(size_code, age_gyr)
    tidal = _seismic_tidal_from_parent(parent_mass_earth, moon_pd)
    heat  = _seismic_heating(tidal)
    total = round(res + tidal + heat, 2)
    return {
        'seismic_residual': res,
        'seismic_tidal':    tidal,
        'seismic_heating':  heat,
        'seismic_total':    total,
        'tectonic_plates':  _tectonic_plates(total),
    }


# ---------------------------------------------------------------------------
# Atmosphere detail  (WBH §5)
# ---------------------------------------------------------------------------

_ATM_CODE_BASE: dict[str, str] = {
    'none':      '0',
    'trace':     '1',
    'thin':      '5',
    'standard':  '7',
    'dense':     '9',
    'corrosive': 'B',
    'exotic':    'A',
}

_GH_FACTOR: dict[str, float] = {
    'none': 1.00, 'trace': 1.00, 'thin': 1.05,
    'standard': 1.10, 'dense': 1.25, 'corrosive': 2.20, 'exotic': 1.15,
}

_ALBEDO_RANGES: dict[str, tuple[float, float]] = {
    'none':      (0.05, 0.15),
    'trace':     (0.07, 0.20),
    'thin':      (0.12, 0.28),
    'standard':  (0.23, 0.38),
    'dense':     (0.32, 0.55),
    'corrosive': (0.55, 0.80),
    'exotic':    (0.15, 0.40),
}

# Taint types: L=Low-O2, R=Radiation, B=Biological, G=Gas, P=Particulate, S=Sulfur, H=Hydrocarbons
_TAINT_PROBABILITY: dict[str, float] = {
    'none': 0.00, 'trace': 0.10, 'thin': 0.25,
    'standard': 0.20, 'dense': 0.35, 'corrosive': 0.85, 'exotic': 0.50,
}
_TAINT_BY_COMP: dict[str, list[str]] = {
    'n2o2':    ['R', 'B', 'P', 'L', 'B', 'R'],
    'co2':     ['L', 'G', 'L', 'G', 'B', 'P'],
    'methane': ['L', 'G', 'H', 'H', 'B', 'P'],
    'h2so4':   ['S', 'S', 'G', 'P', 'S', 'G'],
    'none':    ['G', 'P', 'R', 'L', 'B', 'S'],
}


def _roll_taints(
    atm_type: str,
    atm_composition: str,
) -> list[tuple[str, int, int]]:
    """Roll 0–3 atmospheric taints (§5 taint table).

    Returns list of (type, severity 1–9, persistence 2–9) tuples.
    """
    prob = _TAINT_PROBABILITY.get(atm_type, 0.0)
    if prob <= 0.0:
        return []
    pool   = _TAINT_BY_COMP.get(atm_composition or 'none', _TAINT_BY_COMP['none'])
    taints: list[tuple[str, int, int]] = []
    for multiplier in (1.0, 0.35, 0.10):
        if random.random() < prob * multiplier:
            taints.append((
                random.choice(pool),
                max(1, min(9, d6() - 1 + d3())),
                max(2, min(9, d6() + 2)),
            ))
    return taints[:3]


def _atm_detail(
    atm_type:         str | None,
    atm_composition:  str | None,
    atm_pressure_atm: float | None,
    surface_temp_k:   float | None,
    hydrosphere:      float | None,
) -> dict:
    """All static atmosphere detail columns for Bodies INSERT (§5)."""
    _null = {
        'albedo': round(random.uniform(0.05, 0.15), 3),
        'greenhouse_factor': 1.0, 'atm_code': '0',
        'pressure_bar': 0.0, 'ppo_bar': 0.0, 'gases': None,
        'taint_type_1': None, 'taint_severity_1': None, 'taint_persistence_1': None,
        'taint_type_2': None, 'taint_severity_2': None, 'taint_persistence_2': None,
        'taint_type_3': None, 'taint_severity_3': None, 'taint_persistence_3': None,
    }
    if not atm_type:
        return _null

    comp   = atm_composition or 'none'
    press  = atm_pressure_atm or 0.0
    hydro  = hydrosphere or 0.0
    taints = _roll_taints(atm_type, comp)

    base_code = _ATM_CODE_BASE.get(atm_type, '7')
    if taints and base_code in ('5', '7', '9'):
        code = str(int(base_code) - 1)   # 5→4, 7→6, 9→8
    else:
        code = base_code

    lo, hi = _ALBEDO_RANGES.get(atm_type, (0.20, 0.35))
    if comp == 'n2o2' and hydro > 0.3:
        hi = min(0.70, hi + 0.15)        # cloud boost
    albedo = round(random.uniform(lo, hi), 3)

    press_bar = round(press * 1.01325, 4)
    ppo       = round(press * 1.01325 * 0.21, 4) if comp == 'n2o2' and press > 0 else 0.0

    gas_map = {
        'n2o2':    'N2:78,O2:21,Ar:1',
        'co2':     'CO2:95,N2:3,Ar:2',
        'h2so4':   'CO2:97,SO2:2,N2:1',
        'methane': 'N2:95,CH4:4,Ar:1',
    }
    gases = gas_map.get(comp, 'N2:90,CO2:8,Ar:2') if atm_type not in ('none', 'trace') else None

    t1 = taints[0] if len(taints) > 0 else None
    t2 = taints[1] if len(taints) > 1 else None
    t3 = taints[2] if len(taints) > 2 else None
    return {
        'albedo':              albedo,
        'greenhouse_factor':   _GH_FACTOR.get(atm_type, 1.10),
        'atm_code':            code,
        'pressure_bar':        press_bar,
        'ppo_bar':             ppo,
        'gases':               gases,
        'taint_type_1':        t1[0] if t1 else None,
        'taint_severity_1':    t1[1] if t1 else None,
        'taint_persistence_1': t1[2] if t1 else None,
        'taint_type_2':        t2[0] if t2 else None,
        'taint_severity_2':    t2[1] if t2 else None,
        'taint_persistence_2': t2[2] if t2 else None,
        'taint_type_3':        t3[0] if t3 else None,
        'taint_severity_3':    t3[1] if t3 else None,
        'taint_persistence_3': t3[2] if t3 else None,
    }


# ---------------------------------------------------------------------------
# Hydrographics detail  (WBH §6)
# ---------------------------------------------------------------------------

def _hydro_detail(hydrosphere: float | None) -> tuple[int | None, float | None]:
    """Return (hydro_code 0–10, hydro_pct 0.0–100.0)."""
    if hydrosphere is None:
        return None, None
    return min(10, int(round(hydrosphere * 10.0))), round(hydrosphere * 100.0, 1)


# ---------------------------------------------------------------------------
# Mean temperature  (WBH §7)
# ---------------------------------------------------------------------------

def _mean_temp_k(
    surface_temp_k:   float | None,
    axial_tilt_deg:   float,
    tidal_lock_status: str,
) -> float | None:
    """WBH mean surface temperature adjusted for axial tilt and tidal lock (§7)."""
    if surface_temp_k is None:
        return None
    # Tidal lock: hot-side/cold-side average pulls mean below equatorial T
    lock_mod = 0.83 if tidal_lock_status == '1:1' else 1.0
    # High axial tilt: polar regions receive more annual insolation → slight mean increase
    tilt_mod = 1.0 + (axial_tilt_deg / 90.0) * 0.04
    return round(surface_temp_k * lock_mod * tilt_mod, 1)


def _high_low_temp_k(
    luminosity_lsun:  float,
    albedo:           float | None,
    greenhouse_factor: float | None,
    semi_major_axis_au: float,
    eccentricity:     float,
    axial_tilt_deg:   float,
    solar_day_hours:  float | None,
    tidal_lock_status: str | None,
    hydro_code:       int | None,
    pressure_bar:     float | None,
    star_mass_msol:   float = 1.0,
) -> tuple[float | None, float | None]:
    """WBH pp.112-114 high and low temperature (9-step procedure).

    Returns (high_temp_k, low_temp_k).
    For a moon, pass the parent planet's semi_major_axis and eccentricity
    (WBH: moons use their parent planet's orbital parameters).
    Returns (None, None) if albedo/greenhouse_factor are unavailable.
    """
    if albedo is None or greenhouse_factor is None:
        return None, None
    if semi_major_axis_au <= 0:
        return None, None

    # Step 1: Axial Tilt Factor — normalise tilt to 0–90°
    tilt = axial_tilt_deg if axial_tilt_deg <= 90.0 else 180.0 - axial_tilt_deg
    axial_tilt_factor = math.sin(math.radians(tilt))
    # Year-length adjustment: T_years = AU^1.5 / sqrt(M_star_sol)
    orbital_year = (semi_major_axis_au ** 1.5) / math.sqrt(max(star_mass_msol, 0.01))
    if orbital_year < 0.1:
        axial_tilt_factor *= 0.5
    elif orbital_year > 2.0:
        increase = min(0.01 * (orbital_year - 2.0), 0.25)
        axial_tilt_factor = min(1.0, axial_tilt_factor + increase)

    # Step 2: Rotation Factor
    if tidal_lock_status == '1:1' or (solar_day_hours is not None and abs(solar_day_hours) > 2500):
        rotation_factor = 1.0
    elif solar_day_hours is not None and solar_day_hours != 0:
        rotation_factor = min(1.0, math.sqrt(abs(solar_day_hours)) / 50.0)
    else:
        rotation_factor = 0.0

    # Step 3: Geographic Factor — (10 − HYD) / 20; no surface distribution modifier
    hyd = hydro_code if hydro_code is not None else 5
    geographic_factor = (10 - hyd) / 20.0

    # Step 4: Variance Factors (clamped to [0, 1])
    variance_factors = max(0.0, min(1.0,
        axial_tilt_factor + rotation_factor + geographic_factor))

    # Step 5: Atmospheric Factor = 1 + pressure_bar
    pbar = pressure_bar if pressure_bar is not None else 0.0
    atmospheric_factor = 1.0 + pbar

    # Step 6: Luminosity Modifier (clamped to [0, 1])
    luminosity_modifier = max(0.0, min(1.0, variance_factors / atmospheric_factor))

    # Step 7: High and Low Luminosity
    high_luminosity = luminosity_lsun * (1.0 + luminosity_modifier)
    low_luminosity  = luminosity_lsun * (1.0 - luminosity_modifier)

    # Step 8: Near and Far AU (eccentricity modifiers)
    ecc = max(0.0, min(0.99, eccentricity))
    near_au = max(semi_major_axis_au * (1.0 - ecc), 1e-6)
    far_au  = semi_major_axis_au * (1.0 + ecc)

    # Step 9: High and Low Temperature
    factor = (1.0 - albedo) * (1.0 + greenhouse_factor)
    try:
        high_temp_k = round(279.0 * (high_luminosity * factor / near_au ** 2) ** 0.25, 1)
        low_temp_k  = round(279.0 * (low_luminosity  * factor / far_au  ** 2) ** 0.25, 1)
    except (ValueError, ZeroDivisionError):
        return None, None

    return high_temp_k, low_temp_k


# ---------------------------------------------------------------------------
# Native life  (WBH §10)
# ---------------------------------------------------------------------------

def _biomass_rating(
    in_hz:           int,
    atm_type:        str | None,
    hydrosphere:     float | None,
    surface_temp_k:  float | None,
    tectonic_plates: int | None,
    age_gyr:         float,
) -> int:
    """Native life biomass rating 0–5 (§10).

    0 = no life, 5 = rich complex biosphere.
    Prerequisites: liquid water, non-hostile atmosphere, 230–390 K surface.
    Base 2D−5 with DMs.
    """
    if not hydrosphere or hydrosphere < 0.01:
        return 0
    if atm_type in (None, 'none', 'trace', 'corrosive', 'exotic'):
        return 0
    if surface_temp_k is None or not (230.0 <= surface_temp_k <= 390.0):
        return 0

    base = two_d6() - 5
    if in_hz:              base += 2
    if atm_type == 'standard': base += 1
    elif atm_type == 'thin':   base -= 1
    if hydrosphere > 0.5:  base += 1
    if hydrosphere > 0.8:  base += 1
    if tectonic_plates and tectonic_plates >= 5:
        base += 1   # active geology → nutrient cycling
    if age_gyr >= 3.0:     base += 1
    if age_gyr >= 7.0:     base += 1
    if 275.0 <= surface_temp_k <= 320.0:
        base += 1
    return max(0, min(10, base))


# ---------------------------------------------------------------------------
# Biosphere chain  (WBH pp.128-131)
# ---------------------------------------------------------------------------

def _biocomplexity_rating(
    biomass:      int,
    atm_code:     str | None,
    taint_type_1: str | None,
    taint_type_2: str | None,
    taint_type_3: str | None,
    age_gyr:      float,
) -> int:
    """Biocomplexity rating (WBH p.129).

    0 = no life; 1 = prokaryotes; 9 = sophont-level.
    Special case: biologic taint (type B) on a biomass-0 world → return 1.
    """
    taint_codes = {t for t in (taint_type_1, taint_type_2, taint_type_3) if t}
    has_biologic = 'B' in taint_codes

    if biomass <= 0:
        return 1 if has_biologic else 0

    # Biomass > 9 treated as 9
    bm = min(biomass, 9)

    dm = 0
    code = (atm_code or '0').upper()
    if code not in ('4', '5', '6', '7', '8', '9'):
        dm -= 2                          # atmosphere not 4-9
    if 'L' in taint_codes:              # low oxygen taint
        dm -= 2
    if age_gyr < 1.0:
        dm -= 10
    elif age_gyr < 2.0:
        dm -= 8
    elif age_gyr < 3.0:
        dm -= 4
    elif age_gyr < 4.0:
        dm -= 2

    return max(1, two_d6() - 7 + bm + dm)


def _native_sophants_status(biocomplexity: int, age_gyr: float) -> str | None:
    """Determine native sophont presence (WBH p.130).

    Returns None if biocomplexity < 8.  Otherwise 'current', 'extinct', or 'none'.
    """
    if biocomplexity < 8:
        return None

    bc = min(biocomplexity, 9)  # ratings above 9 treated as 9

    # Current sophonts: 2D + biocomplexity − 7 ≥ 13
    if two_d6() + bc - 7 >= 13:
        return 'current'

    # Extinct sophonts: same roll with DM+1 if age > 5 Gyr
    ext_dm = 1 if age_gyr > 5.0 else 0
    if two_d6() + bc - 7 + ext_dm >= 13:
        return 'extinct'

    return 'none'


def _biodiversity_rating(biomass: int, biocomplexity: int) -> int:
    """Biodiversity rating (WBH p.130).

    Species richness/ecosystem resilience.  0 if no life.
    """
    if biomass <= 0:
        return 0
    result = math.ceil(two_d6() - 7 + (biomass + biocomplexity) / 2.0)
    return max(1, result)


_COMPAT_ATM_DM: dict[str, int] = {
    '0': -8, '1': -8,
    '2': -2, '4': -2, '7': -2, '9': -2,
    '3':  1, '5':  1, '8':  1,
    '6':  2,
    'A': -6, 'F': -6,
    'B': -8,
    'C': -10,
    'D': -2, 'E': -2,
    'G': -8, 'H': -8,
}

def _compatibility_rating(
    biocomplexity: int,
    atm_code:      str | None,
    has_any_taint: bool,
    age_gyr:       float,
) -> int:
    """Terran compatibility rating (WBH pp.130-131).

    0 = biochemically incompatible; 10 = full Terran compatibility.
    Only call when biomass > 0.
    """
    code = (atm_code or '0').upper()
    dm = _COMPAT_ATM_DM.get(code, 0)

    # "Otherwise tainted" — taint on a non-already-tainted code
    if has_any_taint and code not in ('2', '4', '7', '9'):
        dm -= 2

    if age_gyr > 8.0:
        dm -= 2

    result = math.floor(two_d6() - biocomplexity / 2.0 + dm)
    return max(0, result)


_SIZE_NUM: dict[str, int] = {
    'S': 0, '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
    '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15,
}

def _resource_rating_world(
    size_code:    str | None,
    density:      float | None,
    biomass:      int,
    biodiversity: int,
    compatibility: int,
) -> int | None:
    """Resource rating for non-belt rocky worlds (WBH p.131).

    Returns 2–12 (C).  Returns None for gas giants and belts.
    """
    if not size_code or size_code in ('GS', 'GM', 'GL'):
        return None

    size_num = _SIZE_NUM.get(size_code.upper(), 0)
    dm = 0

    if density is not None:
        if density > 1.12:
            dm += 2
        elif density < 0.5:
            dm -= 2

    if biomass >= 3:
        dm += 2

    if biodiversity >= 11:       # B+ (11+)
        dm += 2
    elif biodiversity >= 8:      # 8–A
        dm += 1

    if biomass >= 1:
        if compatibility <= 3:
            dm -= 1
        elif compatibility >= 8:
            dm += 2

    return max(2, min(12, two_d6() - 7 + size_num + dm))


# ---------------------------------------------------------------------------
# Belt profile  (WBH §8)
# ---------------------------------------------------------------------------

def _belt_profile(orbit_num: float, hzco: float, age_gyr: float) -> dict:
    """BeltProfile row for a belt body (§8).

    Inner belts (orbit_num < HZCO): richer in S-type and M-type.
    Outer belts: carbonaceous and icy.
    Composition percentages sum to 100.
    """
    inner = orbit_num < hzco

    c_raw = (two_d6() - 2) * 4 + (0 if inner else 15)
    c_pct = max(5, min(70, c_raw))

    s_raw = (two_d6() - 2) * 4 + (15 if inner else 0)
    s_pct = max(5, min(65, s_raw))

    m_raw = max(0, two_d6() - 7 + (3 if inner else 0))
    m_pct = max(0, min(35, m_raw * 3))

    total = c_pct + s_pct + m_pct
    if total > 100:
        scale = 90.0 / total
        c_pct = int(c_pct * scale)
        s_pct = int(s_pct * scale)
        m_pct = int(m_pct * scale)
    other_pct = max(0, 100 - c_pct - s_pct - m_pct)

    bulk_dm = (2 if inner else 0) - (1 if orbit_num > hzco + 3 else 0)
    bulk    = max(1, min(12, two_d6() - 3 + bulk_dm))

    res_dm = m_pct // 10 + bulk // 4 - (1 if age_gyr > 8.0 else 0)
    resource_rating = max(0, min(10, two_d6() - 5 + res_dm))

    return {
        'span_orbit_num':  round(random.uniform(0.10, 0.45), 3),
        'm_type_pct':      m_pct,
        's_type_pct':      s_pct,
        'c_type_pct':      c_pct,
        'other_pct':       other_pct,
        'bulk':            bulk,
        'resource_rating': resource_rating,
        'size1_bodies':    max(0, two_d6() - 8),
        'sizeS_bodies':    max(0, two_d6() - 6),
    }


# ---------------------------------------------------------------------------
# Moon generation (WBH §Significant Moons, pp.55-57, 75-77)
# ---------------------------------------------------------------------------

def _moon_quantity(
    size_code: str,
    planet_class: str,
    orbit_num: float,
    is_binary: bool,
) -> int:
    """Roll number of significant moons (p.55).  Result < 0 → 0; = 0 → ring."""
    pc = (planet_class or '').lower()
    is_gg = 'gg' in pc

    if is_gg:
        n_dice, sub = (3, 7) if pc == 'small_gg' else (4, 6)
    else:
        si = _size_code_to_int(size_code)
        if si <= 2:
            n_dice, sub = 1, 5
        elif si <= 9:
            n_dice, sub = 2, 8
        else:
            n_dice, sub = 2, 6

    # Only one DM condition applies (most restrictive)
    dm_per_die = -1 if (orbit_num < 1.0 or is_binary) else 0
    total = sum(d6() for _ in range(n_dice)) + dm_per_die * n_dice - sub
    return max(0, total)


def _roll_moon_size_code(parent_si: int, is_gg: bool) -> str:
    """Roll one significant moon size code (p.57)."""
    first = d6()
    if first <= 3:
        return 'S'
    if first <= 5:
        # D3-1 → 0, 1, 2  →  R, 1, 2
        r = d3() - 1
        return ('R', '1', '2')[r]
    # first == 6
    if not is_gg:
        # Terrestrial: (parent Size - 1) - 1D, min S
        result = max(0, (parent_si - 1) - d6())
        if result <= 0:
            return 'S'
        return _SIZE_CODES[min(result, len(_SIZE_CODES) - 1)]
    else:
        # Gas giant special table (p.57)
        cat = d6()
        if cat <= 3:
            return _SIZE_CODES[min(d6(), len(_SIZE_CODES) - 1)]       # 1-6
        if cat <= 5:
            r = max(0, d6() + d6() - 2)                               # 0(R)-A(10)
            return 'R' if r == 0 else _SIZE_CODES[min(r, len(_SIZE_CODES) - 1)]
        # cat == 6: 2D+4 → 6-16; 16 = small GG moon
        r = d6() + d6() + 4
        if r >= 16:
            return 'GS'   # moon is itself a small gas giant
        return _SIZE_CODES[min(r, len(_SIZE_CODES) - 1)]


def _hill_sphere_moon_limit_pd(
    planet_au: float,
    planet_ecc: float,
    mass_earth: float,
    planet_diam_km: float,
    star_mass_msol: float,
) -> float:
    """Hill sphere moon limit in planetary diameters (p.75-76)."""
    if planet_diam_km <= 0 or mass_earth <= 0:
        return 0.0
    m_solar = mass_earth * 0.000003
    M       = max(star_mass_msol, 0.1)
    hs_au   = planet_au * (1.0 - planet_ecc) * (m_solar / (3.0 * M)) ** (1.0 / 3.0)
    hs_pd   = hs_au * 149_597_870.9 / planet_diam_km
    return hs_pd / 2.0   # Moon limit = Hill sphere PD / 2


def _moon_orbit_au(
    mor: float,
    n_moons: int,
    planet_diam_km: float,
) -> float:
    """Roll one moon orbit (p.76).  Returns orbit in AU."""
    effective_mor = min(mor, 200 + n_moons) if mor > 200 else mor
    dm = 1 if effective_mor < 60 else 0
    roll = d6() + dm
    two_d = d6() + d6()
    if roll <= 3:           # Inner
        pd = (two_d - 2) * effective_mor / 60.0 + 2.0
    elif roll <= 5:         # Middle
        pd = (two_d - 2) * effective_mor / 30.0 + effective_mor / 6.0 + 3.0
    else:                   # Outer
        pd = (two_d - 2) * effective_mor / 20.0 + effective_mor / 2.0 + 4.0
    pd = max(2.0, pd)
    return pd * planet_diam_km / 149_597_870.7


def _generate_moons(
    planet_bodies:  list[dict],
    star_luminosity: float,
    star_mass_msol:  float,
    age_gyr:         float,
) -> list[dict]:
    """Generate significant moons for all planets.

    Returns a flat list of moon body dicts.  Each dict carries a temporary
    '_parent_idx' key (index in planet_bodies) that the main loop resolves
    into orbit_body_id after INSERT.
    """
    moons: list[dict] = []
    for p_idx, planet in enumerate(planet_bodies):
        if planet['body_type'] != 'planet':
            continue
        diam    = planet.get('diameter_km') or 0.0
        mass_e  = planet.get('mass_earth') or 0.0
        sc      = planet.get('size_code', 'S') or 'S'
        pc      = planet.get('planet_class') or ''
        au      = planet['semi_major_axis']
        ecc     = planet['eccentricity']
        in_hz   = planet.get('in_hz', 0) or 0
        is_gg   = 'gg' in pc.lower()
        is_bin  = planet.get('_is_binary', False)

        if diam <= 0 or mass_e <= 0:
            continue

        hl_pd = _hill_sphere_moon_limit_pd(au, ecc, mass_e, diam, star_mass_msol)
        # Roche limit ≈ 1.537 × planet diameter (1 PD) — need ≥ 1.5 PD hill limit
        if hl_pd < 1.5:
            continue

        mor = math.floor(hl_pd) - 2
        if mor < 1:
            continue

        parent_si = _size_code_to_int(sc)
        n = _moon_quantity(sc, pc, planet.get('orbit_num', 2.0), is_bin)
        if n == 0 and random.random() < 0.3:
            # Result of exactly 0 → ring; already handled by has_rings flag
            continue

        # Sort moon orbits so they don't overlap
        orbit_pds: list[float] = sorted(
            max(2.0, _moon_orbit_au(mor, n, diam) / diam * 149_597_870.7)
            for _ in range(n)
        )

        for moon_pd in orbit_pds:
            m_sc = _roll_moon_size_code(parent_si, is_gg)
            if m_sc == 'R':
                continue   # ring — already tracked on planet via has_rings

            is_moon_gg = m_sc == 'GS'
            m_diam     = roll_diameter(m_sc) if not is_moon_gg else d6() * 12742.0
            if m_diam <= 0:
                m_sc, m_diam = 'S', random.uniform(400, 799)

            m_comp  = 'Mostly Ice' if is_moon_gg else roll_composition(
                m_sc, planet.get('orbit_num', 2.0), 0.0, 5.0)
            m_dens  = random.uniform(0.15, 0.35) if is_moon_gg else roll_density(m_comp)
            m_grav, m_mass, m_esc = derive_physical(m_diam, m_dens)
            m_au    = moon_pd * m_diam / 149_597_870.7

            # Moon orbital elements — anchored to parent's plane
            _, aop, ma = _random_orbital_angles()
            incl = math.radians(abs(random.gauss(0.0, 3.0)))
            lan  = random.uniform(0.0, 2.0 * math.pi)

            moon: dict = {
                'body_type':                'moon',
                'orbit_star_id':            None,
                'orbit_body_id':            None,   # resolved in main loop
                '_parent_idx':              p_idx,
                'semi_major_axis':          m_au,
                'eccentricity':             random.uniform(0.0, 0.05),
                'inclination':              incl,
                'longitude_ascending_node': lan,
                'argument_periapsis':       aop,
                'mean_anomaly':             ma,
                'epoch':                    0,
                'in_hz':                    in_hz,  # inherit parent's HZ flag
                'possible_tidal_lock':      1,       # moons are nearly always locked
                'planet_class':             'rocky' if not is_moon_gg else 'small_gg',
                'has_rings':                0,
                'size_code':                m_sc,
                'diameter_km':              m_diam,
                'composition':              m_comp,
                'density':                  m_dens,
                'gravity_g':                m_grav,
                'mass_earth':               m_mass,
                'mass':                     m_mass,
                'radius':                   m_diam / 12742.0,
                'escape_vel_kms':           m_esc,
                'generation_source':        'procedural',
                'orbit_num':                None,
            }

            # Physical columns (echoed for Bodies INSERT)
            moon['surface_gravity']       = m_grav
            moon['escape_velocity_kms']   = m_esc
            moon['t_eq_k']                = _t_eq_k(star_luminosity, au)  # use parent's a_au

            # Rotation: moons are 1:1 tidally locked to parent
            parent_mass_solar  = mass_e / 333_000.0
            moon_orbital_hr    = (
                math.sqrt(max(m_au, 1e-10) ** 3 / max(parent_mass_solar, 1e-10))
                * 8766.0
            )
            moon.update({
                'tidal_lock_status':  '1:1',
                'possible_tidal_lock': 1,
                'sidereal_day_hours':  round(moon_orbital_hr, 2),
                'solar_day_hours':     None,
                'axial_tilt_deg':      round(abs(random.gauss(0.0, 2.5)), 1),
            })

            # Atmosphere and surface for rocky moons
            if not is_moon_gg and m_mass > 0 and m_diam > 0:
                mut = _mutable_dict(m_mass, m_diam / 12742.0, au,
                                    star_luminosity, in_hz, 1)
                moon['_mutable'] = mut

                # Static atm detail
                atm_det = _atm_detail(
                    mut['atm_type'], mut['atm_composition'],
                    mut['atm_pressure_atm'], mut['surface_temp_k'],
                    mut['hydrosphere'],
                )
                moon.update(atm_det)

                # Hydro detail
                hc, hp = _hydro_detail(mut['hydrosphere'])
                moon['hydro_code'] = hc
                moon['hydro_pct']  = hp

                # Mean temperature
                moon['mean_temp_k'] = _mean_temp_k(
                    mut['surface_temp_k'], moon['axial_tilt_deg'], '1:1')
                # High/low temperature — moons use parent planet's AU and eccentricity (WBH)
                moon['high_temp_k'], moon['low_temp_k'] = _high_low_temp_k(
                    lum,
                    mut.get('albedo'),
                    mut.get('greenhouse_factor'),
                    au,
                    ecc,
                    moon['axial_tilt_deg'],
                    moon.get('solar_day_hours'),
                    moon.get('tidal_lock_status', '1:1'),
                    moon.get('hydro_code'),
                    moon.get('pressure_bar'),
                    star_mass_msol,
                )

                # Seismic (tidal heating from parent planet)
                m_seismic = _moon_seismic_attrs(m_sc, age_gyr, mass_e, moon_pd)
                moon.update(m_seismic)

                # Native life (low probability for moons but possible in HZ)
                moon['biomass_rating'] = _biomass_rating(
                    in_hz, mut['atm_type'], mut['hydrosphere'],
                    mut['surface_temp_k'], m_seismic.get('tectonic_plates'),
                    age_gyr,
                )
                # Special case: biologic taint on zero-biomass moon (WBH p.128)
                mt1 = moon.get('taint_type_1')
                mt2 = moon.get('taint_type_2')
                mt3 = moon.get('taint_type_3')
                if moon['biomass_rating'] == 0 and 'B' in {t for t in (mt1, mt2, mt3) if t}:
                    moon['biomass_rating'] = 1
                m_bmass = moon['biomass_rating']

                moon['biocomplexity_rating'] = _biocomplexity_rating(
                    m_bmass, moon.get('atm_code'), mt1, mt2, mt3, age_gyr)
                m_bcmplx = moon['biocomplexity_rating']

                moon['native_sophants']     = _native_sophants_status(m_bcmplx, age_gyr)
                moon['biodiversity_rating'] = _biodiversity_rating(m_bmass, m_bcmplx)

                if m_bmass > 0:
                    m_has_taint = any(t is not None for t in (mt1, mt2, mt3))
                    moon['compatibility_rating'] = _compatibility_rating(
                        m_bcmplx, moon.get('atm_code'), m_has_taint, age_gyr)
                    moon['resource_rating'] = _resource_rating_world(
                        moon.get('size_code'), moon.get('density'),
                        m_bmass, moon['biodiversity_rating'], moon['compatibility_rating'])
                else:
                    moon['compatibility_rating'] = None
                    moon['resource_rating']      = None

            # Orbital geometry columns (moons only)
            moon['moon_PD']  = round(moon_pd, 2)
            moon['hill_PD']  = round(hl_pd, 2)
            moon['roche_PD'] = 1.54   # Roche limit constant (PD)

            moons.append(moon)

    return moons


# ---------------------------------------------------------------------------
# System generation
# ---------------------------------------------------------------------------

def generate_system(
    star_id:            int,
    spectral:           str,
    luminosity:         float,
    age_gyr:            float,
    star_radius_rsol:   float,
    star_mass_msol:     float,
    companion_max_au:   float,   # 1e9 for solitary
    is_solitary:        bool,
    binary_inclination: float = 0.0,
    binary_lan:         float = 0.0,
) -> list[dict]:
    """Generate full per-system pipeline for one star: orbits, moons, atmosphere.

    Returns a flat list of body dicts (planets, belts, moons) ready for DB
    INSERT.  Moon dicts carry a '_parent_idx' key pointing to their parent
    planet's index in the list; the main loop resolves this to orbit_body_id.
    Rocky body dicts carry a '_mutable' key with atmosphere/hydrosphere fields (merged into Bodies at INSERT).
    No DB access.
    """
    letter, subtype, lum_class = parse_spectral(spectral)

    # Skip stellar remnants and brown dwarfs — no WBH planet generation
    # D* = white dwarf, N/X = neutron star/black hole, L/T/Y = brown dwarf
    if letter in ("D", "N", "X", "L", "T", "Y") or spectral.strip().startswith("D"):
        return []

    # --- MAO ---
    if lum_class == 'VI' and letter == 'M':
        mao = _MAO_SUBDWARF
    else:
        mao = _MAO.get(letter, 2.0)

    # --- Binary upper cap: S-type stability limit = 0.3 × companion SMA ---
    if companion_max_au < 1e8:
        companion_cap_on = au_to_orbit_num(companion_max_au * 0.3)
    else:
        companion_cap_on = 13.0  # unbounded — allow up to ~200 AU

    if companion_cap_on <= mao:
        return []  # stable zone too narrow

    # --- HZCO from luminosity (§4b Step 3) ---
    lum    = max(luminosity, 1e-6)
    hzco   = au_to_orbit_num(math.sqrt(lum))

    # --- World counts (§4b Step 1) ---
    gg_dm  = -2 if letter in ('M', 'K') else 0
    has_gg = (two_d6() + gg_dm) >= 9
    if has_gg:
        qty = d6()
        n_gg = 1 if qty <= 3 else (2 if qty <= 5 else 3)
        if letter in ('M', 'K'):
            n_gg = max(1, n_gg - 1)
    else:
        n_gg = 0

    has_belt = two_d6() >= 8
    n_belt   = (1 if d6() <= 4 else 2) if has_belt else 0

    terr_dm   = 1 if is_solitary else -1
    terr_roll = two_d6() - 2 + terr_dm
    n_terr    = (d3() + 2) if terr_roll < 3 else terr_roll

    total_worlds = n_gg + n_belt + n_terr
    if total_worlds == 0:
        return []

    # --- Baseline Orbit# and spread (§4b Steps 3–4) ---
    baseline_dm  = 1 if is_solitary else -1
    baseline_num = max(1, two_d6() + baseline_dm)

    deviation         = d6() * 0.1 - 0.35          # –0.25 to +0.25
    deviation         = max(-1.0, min(1.0, deviation))
    baseline_orbit_on = max(mao + 0.05, hzco + deviation)
    spread            = max(0.05, (baseline_orbit_on - mao) / baseline_num)

    # Cap to companion stability limit
    max_on = min(companion_cap_on, baseline_orbit_on + spread * (total_worlds + 4))

    # --- Generate orbit slots (§4b Step 5) ---
    slots: list[float] = []
    slot_n = 1
    while len(slots) < total_worlds + 6:
        on = mao + spread * slot_n
        if on > max_on:
            break
        slots.append(on)
        slot_n += 1

    # Remove empty slots (2D result 10/11/12)
    empty_roll = two_d6()
    n_empty    = {10: 1, 11: 2, 12: 3}.get(empty_roll, 0)
    if n_empty and len(slots) > total_worlds + n_empty:
        remove = set(random.sample(range(len(slots)), n_empty))
        slots  = [s for i, s in enumerate(slots) if i not in remove]

    slots = slots[:total_worlds]
    if not slots:
        return []

    # --- World type assignment (§4b Step 6): GGs outermost → belts → terrestrials ---
    slots_desc  = sorted(slots, reverse=True)
    world_types = (['GG'] * n_gg) + (['belt'] * n_belt) + (['terrestrial'] * n_terr)
    assignments = list(zip(slots_desc, world_types))

    # --- Continuation seed (§3): pre-place near-Earth world for solitary F5–K5 V ---
    continuation_seed: dict | None = None
    if is_solitary and is_fgk_continuation_candidate(letter, subtype, lum_class):
        dev    = (d6() * 0.1) * random.choice([-1, 1])
        dev    = max(-0.3, min(0.3, dev))
        cs_on  = max(mao, hzco + dev)
        cs_au  = orbit_num_to_au(cs_on)

        cs_diam  = random.uniform(11500.0, 13599.0)  # Size 8 band, some variation
        cs_dens  = random.uniform(0.90, 1.10)
        cs_grav, cs_mass, cs_esc = derive_physical(cs_diam, cs_dens)
        cs_ecc   = random.uniform(0.01, 0.05)

        r_star_au = (star_radius_rsol or 1.0) * 0.00465
        if cs_au * (1.0 - cs_ecc) < r_star_au * 1.2:
            cs_ecc = max(0.0, 1.0 - (r_star_au * 1.2 / cs_au))

        _, aop, ma = _random_orbital_angles()
        cs_incl = min(math.pi, binary_inclination + math.radians(random.uniform(0.0, 5.0)))
        cs_lan  = (binary_lan + random.gauss(0.0, math.radians(10.0))) % (2.0 * math.pi)
        cs_teq  = _t_eq_k(lum, cs_au)
        cs_rot  = _rotation_attrs(cs_on, hzco, '8', cs_au, star_mass_msol)
        cs_tidal_bool = 0 if cs_rot['tidal_lock_status'] == 'none' else 1
        cs_mut  = _mutable_dict(cs_mass, cs_diam / 12742.0, cs_au, lum, 1, cs_tidal_bool)
        cs_atm  = _atm_detail(
            cs_mut['atm_type'], cs_mut['atm_composition'],
            cs_mut['atm_pressure_atm'], cs_mut['surface_temp_k'], cs_mut['hydrosphere'],
        )
        cs_hc, cs_hp = _hydro_detail(cs_mut['hydrosphere'])
        continuation_seed = {
            'body_type':                'planet',
            'orbit_star_id':            star_id,
            'orbit_body_id':            None,
            'semi_major_axis':          cs_au,
            'eccentricity':             cs_ecc,
            'inclination':              cs_incl,
            'longitude_ascending_node': cs_lan,
            'argument_periapsis':       aop,
            'mean_anomaly':             ma,
            'epoch':                    0,
            'in_hz':                    1,
            'possible_tidal_lock':      cs_tidal_bool,
            'orbit_num':                cs_on,
            'generation_source':        'continuation_seed',
            'size_code':                '8',
            'diameter_km':              cs_diam,
            'composition':              'Rock and Metal',
            'density':                  cs_dens,
            'gravity_g':                cs_grav,
            'mass_earth':               cs_mass,
            'mass':                     cs_mass,
            'radius':                   cs_diam / 12742.0,
            'escape_vel_kms':           cs_esc,
            'surface_gravity':          cs_grav,
            'escape_velocity_kms':      cs_esc,
            't_eq_k':                   cs_teq,
            'planet_class':             'rocky',
            'has_rings':                0,
            'hydro_code':               cs_hc,
            'hydro_pct':                cs_hp,
            '_mutable':                 cs_mut,
            **cs_rot,
            **cs_atm,
        }
        # Remove any slot within half a spread of the continuation seed.
        # Using spread/2 rather than targeting only terrestrials prevents
        # a GG or belt slot from landing at essentially the same orbit as the seed.
        assignments = [(on, wt) for on, wt in assignments
                       if abs(on - cs_on) > spread / 2]

    # --- Build body rows ---
    r_star_au = (star_radius_rsol or 1.0) * 0.00465
    bodies: list[dict] = []

    if continuation_seed:
        bodies.append(continuation_seed)

    for orbit_n, world_type in assignments:
        au = orbit_num_to_au(orbit_n)

        # Anomalous orbit flags
        anom_eccentric = anom_inclined = anom_retrograde = False
        if two_d6() >= 11:
            sub = d6()
            if sub <= 2:
                anom_eccentric = True
            elif sub == 3:
                anom_inclined  = True
            elif sub == 4:
                anom_retrograde = True
            else:
                anom_eccentric = True
                anom_inclined  = True

        ecc = roll_eccentricity(orbit_n, anom_eccentric)
        # Periapsis enforcement: a(1-e) >= 1.2 R★
        if au * (1.0 - ecc) < r_star_au * 1.2:
            ecc = max(0.0, 1.0 - (r_star_au * 1.2 / au))

        # Inclination: measured from sky reference plane.
        # In a binary system, the disk formed in the binary orbital plane, so
        # planet i ≈ binary_inclination + small perturbation.
        incl_perturb    = _inclination_rad(anom_inclined, anom_retrograde)
        incl_rad        = min(math.pi, binary_inclination + incl_perturb)

        # LAN: for normal prograde orbits in a binary, anchor to binary LAN.
        # For anomalous-inclined / retrograde, draw fully random (plane
        # perturbation can point in any direction).
        _, aop, ma = _random_orbital_angles()
        if not (anom_inclined or anom_retrograde):
            lan = (binary_lan + random.gauss(0.0, math.radians(10.0))) % (2.0 * math.pi)
        else:
            lan = random.uniform(0.0, 2.0 * math.pi)
        in_hz = 1 if abs(orbit_n - hzco) <= 1.0 else 0
        teq   = _t_eq_k(lum, au)

        body: dict = {
            'orbit_star_id':            star_id,
            'orbit_body_id':            None,
            'semi_major_axis':          au,
            'eccentricity':             ecc,
            'inclination':              incl_rad,
            'longitude_ascending_node': lan,
            'argument_periapsis':       aop,
            'mean_anomaly':             ma,
            'epoch':                    0,
            'in_hz':                    in_hz,
            'orbit_num':                orbit_n,
            'generation_source':        'procedural',
            't_eq_k':                   teq,
        }

        if world_type == 'GG':
            sc, diam, mass_e, pc = roll_gg_size()
            d_ratio = diam / 12742.0
            density = mass_e / max(d_ratio ** 3, 1e-9)
            grav, _, esc = derive_physical(diam, density)
            rot = _rotation_attrs(orbit_n, hzco, sc, au, star_mass_msol)
            body.update({
                'body_type':            'planet',
                'size_code':            sc,
                'diameter_km':          diam,
                'composition':          'Mostly Ice',
                'density':              density,
                'gravity_g':            grav,
                'mass_earth':           mass_e,
                'mass':                 mass_e,
                'radius':               diam / 12742.0,
                'escape_vel_kms':       esc,
                'surface_gravity':      grav,
                'escape_velocity_kms':  esc,
                'planet_class':         pc,
                'has_rings':            1 if random.random() < 0.3 else 0,
                'possible_tidal_lock':  0 if rot['tidal_lock_status'] == 'none' else 1,
                '_is_binary':           not is_solitary,
                **rot,
            })

        elif world_type == 'belt':
            comp = roll_composition('0', orbit_n, hzco, age_gyr)
            body.update({
                'body_type':                'belt',
                'size_code':                '0',
                'diameter_km':              0.0,
                'composition':              comp,
                'density':                  None,
                'gravity_g':                None,
                'mass_earth':               None,
                'mass':                     None,
                'radius':                   None,
                'escape_vel_kms':           None,
                'surface_gravity':          None,
                'escape_velocity_kms':      None,
                'planet_class':             None,
                'has_rings':                None,
                'possible_tidal_lock':      0,
                'eccentricity':             0.0,
                'inclination':              binary_inclination,
                'longitude_ascending_node': binary_lan,
                '_belt_profile':            _belt_profile(orbit_n, hzco, age_gyr),
            })

        else:  # terrestrial
            size_roll = max(0, min(15, two_d6() - 2))
            sc        = _SIZE_CODES[size_roll]
            diam      = roll_diameter(sc)
            comp      = roll_composition(sc, orbit_n, hzco, age_gyr)
            dens      = roll_density(comp)
            if diam > 0.0:
                grav, mass_e, esc = derive_physical(diam, dens)
            else:
                grav = mass_e = esc = 0.0
            rot       = _rotation_attrs(orbit_n, hzco, sc, au, star_mass_msol)
            tidal_bool = 0 if rot['tidal_lock_status'] == 'none' else 1
            body.update({
                'body_type':            'planet',
                'size_code':            sc,
                'diameter_km':          diam,
                'composition':          comp,
                'density':              dens,
                'gravity_g':            grav,
                'mass_earth':           mass_e,
                'mass':                 mass_e,
                'radius':               diam / 12742.0 if diam > 0.0 else None,
                'escape_vel_kms':       esc,
                'surface_gravity':      grav,
                'escape_velocity_kms':  esc,
                'planet_class':         'rocky',
                'has_rings':            0,
                'possible_tidal_lock':  tidal_bool,
                '_is_binary':           not is_solitary,
                **rot,
            })
            if diam > 0.0 and mass_e > 0.0:
                mut = _mutable_dict(mass_e, diam / 12742.0, au, lum, in_hz, tidal_bool)
                body['_mutable']   = mut
                body['hydro_code'], body['hydro_pct'] = _hydro_detail(mut['hydrosphere'])
                body.update(_atm_detail(
                    mut['atm_type'], mut['atm_composition'],
                    mut['atm_pressure_atm'], mut['surface_temp_k'], mut['hydrosphere'],
                ))

        bodies.append(body)

    stable = enforce_orbital_stability(bodies)

    # Generate moons for all planets in the stable list
    moons = _generate_moons(stable, lum, star_mass_msol, age_gyr)

    # -------------------------------------------------------------------------
    # Pass 2: seismic, mean_temp, biomass (need moon list to compute seismic)
    # -------------------------------------------------------------------------
    moon_by_parent: dict[int, list[dict]] = {}
    for m in moons:
        pi = m.get('_parent_idx')
        if pi is not None:
            moon_by_parent.setdefault(pi, []).append(m)

    for i, b in enumerate(stable):
        if b.get('body_type') != 'planet' or b.get('planet_class') != 'rocky':
            continue   # belts and GGs: skip seismic/biomass
        sc_b = b.get('size_code') or 'S'
        seis = _seismic_attrs(sc_b, age_gyr, moon_by_parent.get(i, []))
        b.update(seis)
        mut = b.get('_mutable') or {}
        b['mean_temp_k'] = _mean_temp_k(
            mut.get('surface_temp_k'),
            b.get('axial_tilt_deg', 0.0),
            b.get('tidal_lock_status', 'none'),
        )
        b['high_temp_k'], b['low_temp_k'] = _high_low_temp_k(
            lum,
            mut.get('albedo'),
            mut.get('greenhouse_factor'),
            b.get('semi_major_axis', 0.0),
            b.get('eccentricity', 0.0),
            b.get('axial_tilt_deg', 0.0),
            b.get('solar_day_hours'),
            b.get('tidal_lock_status', 'none'),
            b.get('hydro_code'),
            b.get('pressure_bar'),
            star_mass_msol,
        )
        b['biomass_rating'] = _biomass_rating(
            b.get('in_hz', 0),
            mut.get('atm_type'),
            mut.get('hydrosphere'),
            mut.get('surface_temp_k'),
            seis.get('tectonic_plates'),
            age_gyr,
        )
        # Special case: biologic taint on zero-biomass world (WBH p.128)
        t1, t2, t3 = b.get('taint_type_1'), b.get('taint_type_2'), b.get('taint_type_3')
        if b['biomass_rating'] == 0 and 'B' in {t for t in (t1, t2, t3) if t}:
            b['biomass_rating'] = 1
        bmass = b['biomass_rating']

        b['biocomplexity_rating'] = _biocomplexity_rating(
            bmass, b.get('atm_code'), t1, t2, t3, age_gyr)
        bcmplx = b['biocomplexity_rating']

        b['native_sophants']    = _native_sophants_status(bcmplx, age_gyr)
        b['biodiversity_rating'] = _biodiversity_rating(bmass, bcmplx)

        if bmass > 0:
            has_taint = any(t is not None for t in (t1, t2, t3))
            b['compatibility_rating'] = _compatibility_rating(
                bcmplx, b.get('atm_code'), has_taint, age_gyr)
            b['resource_rating'] = _resource_rating_world(
                b.get('size_code'), b.get('density'),
                bmass, b['biodiversity_rating'], b['compatibility_rating'])
        else:
            b['compatibility_rating'] = None
            b['resource_rating']      = None

    return stable + moons


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_sol_body_ids(conn: sqlite3.Connection) -> set[int]:
    """Return all body_ids in the Sol system (system_id=1030192)."""
    sol_stars = {r[0] for r in conn.execute(
        "SELECT star_id FROM IndexedIntegerDistinctStars WHERE system_id = ?",
        (SOL_SYSTEM_ID,),
    ).fetchall()}
    if not sol_stars:
        return set()

    ph = ','.join('?' * len(sol_stars))
    planets = {r[0] for r in conn.execute(
        f"SELECT body_id FROM Bodies WHERE orbit_star_id IN ({ph})",
        list(sol_stars),
    ).fetchall()}

    all_sol: set[int] = set(planets)
    parents: set[int] = set(planets)
    # Walk moons recursively (handles moons-of-moons if any)
    while parents:
        ph2   = ','.join('?' * len(parents))
        moons = {r[0] for r in conn.execute(
            f"SELECT body_id FROM Bodies WHERE orbit_body_id IN ({ph2})",
            list(parents),
        ).fetchall()}
        new = moons - all_sol
        if not new:
            break
        all_sol |= new
        parents  = new

    return all_sol


def purge_non_sol_bodies(conn: sqlite3.Connection) -> int:
    """Delete all Bodies rows except Sol system.  Returns count deleted."""
    sol_ids = get_sol_body_ids(conn)
    log.info("Sol system: %d body rows will be preserved.", len(sol_ids))

    if sol_ids:
        ph  = ','.join('?' * len(sol_ids))
        cur = conn.execute(
            f"DELETE FROM Bodies WHERE body_id NOT IN ({ph})",
            list(sol_ids),
        )
    else:
        cur = conn.execute("DELETE FROM Bodies")

    deleted = cur.rowcount
    conn.commit()
    log.info("Purged %d non-Sol body rows.", deleted)
    return deleted


# ---------------------------------------------------------------------------
# INSERT template
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT INTO Bodies (
    body_type, orbit_star_id, orbit_body_id,
    semi_major_axis, eccentricity, inclination,
    longitude_ascending_node, argument_periapsis, mean_anomaly, epoch,
    in_hz, possible_tidal_lock, planet_class, has_rings,
    mass, radius,
    generation_source, orbit_num,
    size_code, diameter_km, composition, density,
    gravity_g, mass_earth, escape_vel_kms,
    surface_gravity, escape_velocity_kms, t_eq_k,
    atm_type, atm_pressure_atm, atm_composition, surface_temp_k, hydrosphere,
    albedo, greenhouse_factor,
    atm_code, pressure_bar, ppo_bar, gases,
    taint_type_1, taint_severity_1, taint_persistence_1,
    taint_type_2, taint_severity_2, taint_persistence_2,
    taint_type_3, taint_severity_3, taint_persistence_3,
    hydro_code, hydro_pct, mean_temp_k, high_temp_k, low_temp_k,
    sidereal_day_hours, solar_day_hours, axial_tilt_deg, tidal_lock_status,
    seismic_residual, seismic_tidal, seismic_heating, seismic_total, tectonic_plates,
    biomass_rating,
    biocomplexity_rating, native_sophants, biodiversity_rating,
    compatibility_rating, resource_rating,
    moon_PD, hill_PD, roche_PD
) VALUES (
    :body_type, :orbit_star_id, :orbit_body_id,
    :semi_major_axis, :eccentricity, :inclination,
    :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch,
    :in_hz, :possible_tidal_lock, :planet_class, :has_rings,
    :mass, :radius,
    :generation_source, :orbit_num,
    :size_code, :diameter_km, :composition, :density,
    :gravity_g, :mass_earth, :escape_vel_kms,
    :surface_gravity, :escape_velocity_kms, :t_eq_k,
    :atm_type, :atm_pressure_atm, :atm_composition, :surface_temp_k, :hydrosphere,
    :albedo, :greenhouse_factor,
    :atm_code, :pressure_bar, :ppo_bar, :gases,
    :taint_type_1, :taint_severity_1, :taint_persistence_1,
    :taint_type_2, :taint_severity_2, :taint_persistence_2,
    :taint_type_3, :taint_severity_3, :taint_persistence_3,
    :hydro_code, :hydro_pct, :mean_temp_k, :high_temp_k, :low_temp_k,
    :sidereal_day_hours, :solar_day_hours, :axial_tilt_deg, :tidal_lock_status,
    :seismic_residual, :seismic_tidal, :seismic_heating, :seismic_total, :tectonic_plates,
    :biomass_rating,
    :biocomplexity_rating, :native_sophants, :biodiversity_rating,
    :compatibility_rating, :resource_rating,
    :moon_PD, :hill_PD, :roche_PD
)
"""

_BELT_PROFILE_INSERT_SQL = """
INSERT OR IGNORE INTO BeltProfile
    (body_id, span_orbit_num,
     m_type_pct, s_type_pct, c_type_pct, other_pct,
     bulk, resource_rating, size1_bodies, sizeS_bodies)
VALUES
    (:body_id, :span_orbit_num,
     :m_type_pct, :s_type_pct, :c_type_pct, :other_pct,
     :bulk, :resource_rating, :size1_bodies, :sizeS_bodies)
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help="Path to starscape.db (default: %(default)s)",
    )
    parser.add_argument(
        "--purge", action="store_true",
        help="Delete all non-Sol Bodies rows before generating",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help="Stars committed per transaction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
        help="Stop after this many elapsed minutes; re-run to resume (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Log every star processed",
    )
    parser.add_argument(
        "--system-ids", nargs="+", type=int, metavar="SYSTEM_ID",
        help="Only process stars in these system IDs (for targeted runs)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    deadline = time.monotonic() + args.max_minutes * 60.0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        # --- Optional purge ---
        if args.purge:
            log.info("--purge: removing all non-Sol Bodies rows...")
            purge_non_sol_bodies(conn)

        # --- Pre-load binary constraints ---
        # binary_cap[star_id]  = max stable planet AU for that star
        # binary_stars         = every star_id involved in any binary
        binary_cap:   dict[int, float] = {}
        binary_stars: set[int]         = set()
        try:
            for o in conn.execute(
                "SELECT star_id, primary_star_id, semi_major_axis FROM StarOrbits"
            ).fetchall():
                cap     = float(o["semi_major_axis"]) * 0.3
                sid     = o["star_id"]
                primary = o["primary_star_id"]
                # Companion: capped by its own orbit
                if sid not in binary_cap or cap < binary_cap[sid]:
                    binary_cap[sid] = cap
                binary_stars.add(sid)
                # Primary: capped by closest companion
                if primary not in binary_cap or cap < binary_cap[primary]:
                    binary_cap[primary] = cap
                binary_stars.add(primary)
        except sqlite3.OperationalError:
            log.warning("StarOrbits not found — treating all stars as solitary")

        log.info("Binary constraints pre-loaded: %d stars in multiple systems.", len(binary_stars))

        # binary_plane[star_id] = (inclination_rad, lan_rad) of the companion orbit.
        # Both the companion and its primary map to the same plane entry.
        binary_plane: dict[int, tuple[float, float]] = {}
        try:
            for o in conn.execute(
                "SELECT star_id, primary_star_id, inclination, longitude_ascending_node FROM StarOrbits"
            ).fetchall():
                plane = (float(o["inclination"]), float(o["longitude_ascending_node"]))
                binary_plane[o["star_id"]]         = plane
                binary_plane[o["primary_star_id"]] = plane
        except sqlite3.OperationalError:
            pass

        # --- Pre-load system membership for inline orbit generation ---
        # systems_with_orbits: system_ids that already have ≥1 StarOrbits row.
        # inline_orbit_done:   systems for which we generated orbits this run.
        systems_with_orbits: set[int] = set()
        try:
            for r in conn.execute(
                """
                SELECT DISTINCT i.system_id
                FROM StarOrbits so
                JOIN IndexedIntegerDistinctStars i ON so.star_id = i.star_id
                """
            ):
                systems_with_orbits.add(r["system_id"])
        except sqlite3.OperationalError:
            pass
        inline_orbit_done: set[int] = set()

        # --- Pending stars: skip Sol and any already having Bodies rows ---
        system_filter = ""
        filter_params: list = [SOL_SYSTEM_ID]
        if args.system_ids:
            ph = ",".join("?" * len(args.system_ids))
            system_filter = f"AND i.system_id IN ({ph})"
            filter_params += args.system_ids

        pending = conn.execute(
            f"""
            SELECT
                i.star_id,
                i.system_id,
                i.spectral,
                COALESCE(e.luminosity, 1.0)  AS luminosity,
                COALESCE(e.age,        5.0)  AS age_gyr,
                COALESCE(e.radius,     1.0)  AS radius_rsol,
                COALESCE(e.mass,       1.0)  AS mass_msol
            FROM IndexedIntegerDistinctStars i
            LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
            WHERE i.system_id != ?
              {system_filter}
              AND i.star_id NOT IN (
                  SELECT DISTINCT orbit_star_id
                  FROM Bodies
                  WHERE orbit_star_id IS NOT NULL
              )
            ORDER BY i.star_id
            """,
            filter_params,
        ).fetchall()

        total = len(pending)
        log.info("Stars to process: %d", total)
        if total == 0:
            log.info("Nothing to do.")
            return

        processed      = 0
        bodies_inserted = 0

        for row in pending:
            if time.monotonic() >= deadline:
                conn.commit()
                log.info(
                    "Time limit reached after %d/%d stars (%d bodies). Re-run to continue.",
                    processed, total, bodies_inserted,
                )
                return

            star_id    = row["star_id"]
            system_id  = row["system_id"]
            spectral   = row["spectral"] or ""
            lum        = max(float(row["luminosity"]), 1e-6)
            age_gyr    = float(row["age_gyr"]) if row["age_gyr"] else 5.0
            radius_sol = float(row["radius_rsol"]) if row["radius_rsol"] else 1.0
            mass_msol  = float(row["mass_msol"]) if row["mass_msol"] else 1.0

            # --- Inline companion orbit generation ---
            # If this star is in a multi-star system with no StarOrbits entries,
            # generate them now before placing planets.
            if (system_id not in systems_with_orbits
                    and system_id not in inline_orbit_done):
                _inline_generate_system_orbits(
                    conn, system_id, binary_cap, binary_stars, binary_plane
                )
                inline_orbit_done.add(system_id)
                systems_with_orbits.add(system_id)

            is_solitary      = star_id not in binary_stars
            companion_max_au = binary_cap.get(star_id, 1e9)
            bin_incl, bin_lan = binary_plane.get(star_id, (0.0, 0.0))

            bodies = generate_system(
                star_id             = star_id,
                spectral            = spectral,
                luminosity          = lum,
                age_gyr             = age_gyr,
                star_radius_rsol    = radius_sol,
                star_mass_msol      = mass_msol,
                companion_max_au    = companion_max_au,
                is_solitary         = is_solitary,
                binary_inclination  = bin_incl,
                binary_lan          = bin_lan,
            )

            # Insert bodies; resolve moon parent links and BeltProfile rows.
            # All columns default to None (NULL) if not set by generate_system().
            _NEW_COLS = (
                'atm_type', 'atm_pressure_atm', 'atm_composition',
                'surface_temp_k', 'hydrosphere',
                'albedo', 'greenhouse_factor',
                'atm_code', 'pressure_bar', 'ppo_bar', 'gases',
                'taint_type_1', 'taint_severity_1', 'taint_persistence_1',
                'taint_type_2', 'taint_severity_2', 'taint_persistence_2',
                'taint_type_3', 'taint_severity_3', 'taint_persistence_3',
                'hydro_code', 'hydro_pct', 'mean_temp_k', 'high_temp_k', 'low_temp_k',
                'sidereal_day_hours', 'solar_day_hours', 'axial_tilt_deg', 'tidal_lock_status',
                'seismic_residual', 'seismic_tidal', 'seismic_heating', 'seismic_total',
                'tectonic_plates', 'biomass_rating',
                'biocomplexity_rating', 'native_sophants', 'biodiversity_rating',
                'compatibility_rating', 'resource_rating',
                'moon_PD', 'hill_PD', 'roche_PD',
            )
            idx_to_body_id: dict[int, int] = {}
            for i, b in enumerate(bodies):
                parent_idx   = b.pop('_parent_idx',   None)
                mutable      = b.pop('_mutable',       None)
                belt_profile = b.pop('_belt_profile',  None)
                b.pop('_is_binary', None)
                # Strip remaining private keys; fill new columns with None if absent
                insert_row = {k: v for k, v in b.items() if not k.startswith('_')}
                # Merge ex-BodyMutable fields directly into Bodies row
                if mutable is not None:
                    mutable.pop('_t_eq_k', None)
                    mutable.pop('_v_esc',  None)
                    mutable.pop('_sg',     None)
                    insert_row.update(mutable)
                for col in _NEW_COLS:
                    insert_row.setdefault(col, None)
                if parent_idx is not None:
                    insert_row['orbit_body_id'] = idx_to_body_id.get(parent_idx)
                    insert_row['orbit_star_id'] = None
                cur = conn.execute(_INSERT_SQL, insert_row)
                body_id = cur.lastrowid
                idx_to_body_id[i] = body_id
                if belt_profile is not None:
                    conn.execute(_BELT_PROFILE_INSERT_SQL, {'body_id': body_id, **belt_profile})

            bodies_inserted += len(bodies)

            processed += 1
            if args.verbose:
                log.debug("star_id=%d spectral=%r bodies=%d", star_id, spectral, len(bodies))

            if processed % args.batch_size == 0:
                conn.commit()
                log.info(
                    "Progress: %d / %d stars  |  %d bodies inserted",
                    processed, total, bodies_inserted,
                )

        conn.commit()
        log.info(
            "Done. %d stars processed, %d bodies inserted.",
            processed, bodies_inserted,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
