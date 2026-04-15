#!/usr/bin/env python3
"""WBH planet generation — Phase 1: orbit placement and world sizing.

Implements World Builder's Handbook (WBH) orbit placement, world-type
assignment, terrestrial sizing/composition/density chain, and gas giant
sizing.  Atmosphere (Phase 3) and moons (Phase 2) are NOT populated here.

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

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
SOL_SYSTEM_ID = 1030192
DEFAULT_BATCH = 500
DEFAULT_MAX_MINUTES = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


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
        deg = random.uniform(90.0, 180.0)
    elif anom_inclined:
        deg = random.uniform(25.0, 90.0)
    else:
        deg = abs(random.gauss(0.0, 7.0))
        deg = min(deg, 25.0)
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
# System generation
# ---------------------------------------------------------------------------

def generate_system(
    star_id:          int,
    spectral:         str,
    luminosity:       float,
    age_gyr:          float,
    star_radius_rsol: float,
    companion_max_au: float,   # 1e9 for solitary
    is_solitary:      bool,
) -> list[dict]:
    """Generate WBH Phase 1 orbit placement for one star.

    Returns a list of body dicts ready for DB INSERT.  No DB access.
    """
    letter, subtype, lum_class = parse_spectral(spectral)

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

        lan, aop, ma = _random_orbital_angles()
        continuation_seed = {
            'body_type':                'planet',
            'orbit_star_id':            star_id,
            'orbit_body_id':            None,
            'semi_major_axis':          cs_au,
            'eccentricity':             cs_ecc,
            'inclination':              math.radians(random.uniform(0.0, 5.0)),
            'longitude_ascending_node': lan,
            'argument_periapsis':       aop,
            'mean_anomaly':             ma,
            'epoch':                    0,
            'in_hz':                    1,
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
            'planet_class':             'rocky',
            'has_rings':                0,
        }
        # Remove the terrestrial slot nearest to the continuation orbit#
        terr_indices = [(i, on) for i, (on, wt) in enumerate(assignments)
                        if wt == 'terrestrial']
        if terr_indices:
            nearest_i = min(terr_indices, key=lambda x: abs(x[1] - cs_on))[0]
            assignments.pop(nearest_i)

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

        incl_rad        = _inclination_rad(anom_inclined, anom_retrograde)
        lan, aop, ma    = _random_orbital_angles()
        in_hz           = 1 if abs(orbit_n - hzco) <= 1.0 else 0

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
        }

        if world_type == 'GG':
            sc, diam, mass_e, pc = roll_gg_size()
            # Derive density from WBH mass and diameter (self-consistent)
            d_ratio = diam / 12742.0
            density = mass_e / max(d_ratio ** 3, 1e-9)
            grav, _, esc = derive_physical(diam, density)
            body.update({
                'body_type':      'planet',
                'size_code':      sc,
                'diameter_km':    diam,
                'composition':    'Mostly Ice',   # hydrogen-dominated
                'density':        density,
                'gravity_g':      grav,
                'mass_earth':     mass_e,
                'mass':           mass_e,
                'radius':         diam / 12742.0,
                'escape_vel_kms': esc,
                'planet_class':   pc,
                'has_rings':      1 if random.random() < 0.3 else 0,
            })

        elif world_type == 'belt':
            comp = roll_composition('0', orbit_n, hzco, age_gyr)
            body.update({
                'body_type':      'belt',
                'size_code':      '0',
                'diameter_km':    0.0,
                'composition':    comp,
                'density':        None,
                'gravity_g':      None,
                'mass_earth':     None,
                'mass':           None,
                'radius':         None,
                'escape_vel_kms': None,
                'planet_class':   None,
                'has_rings':      None,
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
            body.update({
                'body_type':      'planet',
                'size_code':      sc,
                'diameter_km':    diam,
                'composition':    comp,
                'density':        dens,
                'gravity_g':      grav,
                'mass_earth':     mass_e,
                'mass':           mass_e,
                'radius':         diam / 12742.0 if diam > 0.0 else None,
                'escape_vel_kms': esc,
                'planet_class':   'rocky',
                'has_rings':      0,
            })

        bodies.append(body)

    return enforce_orbital_stability(bodies)


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
    gravity_g, mass_earth, escape_vel_kms
) VALUES (
    :body_type, :orbit_star_id, :orbit_body_id,
    :semi_major_axis, :eccentricity, :inclination,
    :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch,
    :in_hz, NULL, :planet_class, :has_rings,
    :mass, :radius,
    :generation_source, :orbit_num,
    :size_code, :diameter_km, :composition, :density,
    :gravity_g, :mass_earth, :escape_vel_kms
)
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

        log.info("Binary constraints: %d stars in multiple systems.", len(binary_stars))

        # --- Pending stars: skip Sol and any already having Bodies rows ---
        pending = conn.execute(
            """
            SELECT
                i.star_id,
                i.spectral,
                COALESCE(e.luminosity, 1.0)  AS luminosity,
                COALESCE(e.age,        5.0)  AS age_gyr,
                COALESCE(e.radius,     1.0)  AS radius_rsol
            FROM IndexedIntegerDistinctStars i
            LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
            WHERE i.system_id != ?
              AND i.star_id NOT IN (
                  SELECT DISTINCT orbit_star_id
                  FROM Bodies
                  WHERE orbit_star_id IS NOT NULL
              )
            ORDER BY i.star_id
            """,
            (SOL_SYSTEM_ID,),
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
            spectral   = row["spectral"] or ""
            lum        = max(float(row["luminosity"]), 1e-6)
            age_gyr    = float(row["age_gyr"]) if row["age_gyr"] else 5.0
            radius_sol = float(row["radius_rsol"]) if row["radius_rsol"] else 1.0
            is_solitary      = star_id not in binary_stars
            companion_max_au = binary_cap.get(star_id, 1e9)

            bodies = generate_system(
                star_id          = star_id,
                spectral         = spectral,
                luminosity       = lum,
                age_gyr          = age_gyr,
                star_radius_rsol = radius_sol,
                companion_max_au = companion_max_au,
                is_solitary      = is_solitary,
            )

            for b in bodies:
                conn.execute(_INSERT_SQL, b)
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
