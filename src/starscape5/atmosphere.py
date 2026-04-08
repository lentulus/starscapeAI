"""Atmosphere and hydrosphere classification for rocky planets and moons.

All functions are pure (deterministic inputs → deterministic output) except
for the probabilistic classifiers that draw from `random`.  Callers that need
reproducibility should seed `random` before calling.

Physical basis
--------------
- Equilibrium temperature:  T_eq = 278 × (L / a²)^0.25  (Bond albedo ~0.3, solar units)
- Escape velocity:          v_esc = 11.2 × √(M / R)       (km/s, Earth units)
- Surface gravity:          g     = M / R²                  (g-units, 1 = Earth)
- Greenhouse multipliers are empirical fits to known Solar System objects.
"""

import math
import random


# ---------------------------------------------------------------------------
# Immutable physical properties
# ---------------------------------------------------------------------------

def surface_gravity(mass_me: float, radius_re: float) -> float:
    """Surface gravity in g-units (1.0 = Earth)."""
    return mass_me / (radius_re ** 2)


def escape_velocity_kms(mass_me: float, radius_re: float) -> float:
    """Escape velocity in km/s.  Earth = 11.2 km/s."""
    return 11.2 * math.sqrt(mass_me / radius_re)


def t_eq_k(star_luminosity: float, a_au: float) -> float:
    """Blackbody equilibrium temperature in K (Bond albedo ~0.3).

    T_eq = 278 × (L / a²)^0.25   [L in L☉, a in AU]
    """
    return 278.0 * ((max(star_luminosity, 1e-6) / (a_au ** 2)) ** 0.25)


# ---------------------------------------------------------------------------
# Greenhouse modifiers
# ---------------------------------------------------------------------------

_GREENHOUSE: dict[str, float] = {
    "none":      1.00,
    "trace":     1.00,
    "thin":      1.05,
    "standard":  1.10,   # +28 K at Earth T_eq ≈ 255 K → ~283 K
    "dense":     1.25,
    "corrosive": 2.20,   # Venus: T_eq ~232 K → actual ~737 K (factor ~3.2 raw, modelled conservatively)
    "exotic":    1.15,
}


# ---------------------------------------------------------------------------
# Atmosphere classification
# ---------------------------------------------------------------------------

def classify_atm(
    v_esc: float,
    t_eq: float,
    in_hz: int | None,
    possible_tidal_lock: int | None,
) -> str:
    """Return atmosphere type string based on physical parameters.

    Priority order (first match wins):
    1. v_esc < 1.0  → 'none'     (Moon/Phobos-scale: can't hold anything)
    2. v_esc < 3.0  → 'trace'    (Mars-scale at low end)
    3. t_eq > 650   → 'corrosive' (runaway greenhouse locked in)
    4. v_esc < 5.0  → 'thin'     (insufficient gravity for standard)
    5. t_eq < 120   → 'thin'     (gases freeze out)
    6. tidal_lock   → 'thin' (70%) or 'standard' (30%)
    7. Probabilistic draw weighted by HZ membership.
    """
    if v_esc < 1.0:
        return "none"
    if v_esc < 3.0:
        return "trace"
    if t_eq > 650.0:
        return "corrosive"
    if v_esc < 5.0:
        return "thin"
    if t_eq < 120.0:
        return "thin"
    if possible_tidal_lock:
        return "thin" if random.random() < 0.70 else "standard"

    r = random.random()
    if in_hz:
        # In HZ: bias strongly toward habitable atmospheres
        if r < 0.10:
            return "thin"
        if r < 0.70:
            return "standard"
        return "dense"
    else:
        # Out of HZ: more thin, fewer dense
        if r < 0.40:
            return "thin"
        if r < 0.85:
            return "standard"
        return "dense"


def atm_composition(atm_type: str, t_eq: float) -> str:
    """Return dominant atmospheric composition tag."""
    if atm_type in ("none", "trace"):
        return "none"
    if atm_type == "corrosive":
        return "h2so4" if t_eq > 400.0 else "co2"
    if t_eq < 150.0:
        return "methane"   # Titan-like cold outer worlds
    # Standard/thin/dense: N2/O2 biogenic or CO2 primordial
    return "n2o2" if random.random() < 0.40 else "co2"


def atm_pressure_atm(atm_type: str) -> float:
    """Draw surface pressure in Earth atmospheres from type-conditioned distribution."""
    if atm_type == "none":
        return 0.0
    if atm_type == "trace":
        return random.uniform(0.001, 0.05)
    if atm_type == "thin":
        return random.uniform(0.05, 0.50)
    if atm_type == "standard":
        # Log-normal centred on 1 atm, σ=0.4 dex
        return max(0.5, min(2.0, math.exp(random.gauss(0.0, 0.4))))
    if atm_type == "dense":
        return random.uniform(2.0, 10.0)
    if atm_type == "corrosive":
        return random.uniform(30.0, 100.0)
    return 1.0   # exotic


def surface_temp_k(t_eq: float, atm_type: str) -> float:
    """Post-greenhouse surface temperature in K."""
    return t_eq * _GREENHOUSE.get(atm_type, 1.0)


def hydrosphere(
    atm_type: str,
    in_hz: int | None,
    surf_temp_k: float,
) -> float | None:
    """Ocean/ice fraction 0.0–1.0.  Returns None if atmosphere precludes liquid water.

    Logic:
    - No/corrosive atmosphere → None (no stable surface liquid)
    - Surface too hot (> 380 K) → 0.0
    - In HZ: Beta(2,2) draw centred at 0.5 (Earth-like distribution)
    - Out of HZ but cool enough (< 380 K): Uniform(0, 0.3) — residual ice or subsurface possible
    """
    if atm_type in ("none", "corrosive"):
        return None
    if surf_temp_k > 380.0:
        return 0.0
    if in_hz:
        return round(random.betavariate(2, 2), 3)
    return round(random.uniform(0.0, 0.30), 3)
