"""Planet and moon generation for the Bodies table."""

import math
import random


# --- Planet count by spectral class ---

_PLANET_LAMBDA: dict[str, float] = {
    "O": 2.0, "B": 2.0,
    "A": 4.0, "F": 4.0,
    "G": 6.0, "K": 6.0,
    "M": 3.0,
}


def planet_count(spectral_letter: str) -> int:
    """Draw planet count from a Poisson distribution conditioned on spectral class."""
    lam = _PLANET_LAMBDA.get(spectral_letter.upper(), 4.0)
    return _poisson(lam)


def planet_mass_earth() -> float:
    """Draw planet mass in Earth masses from a log-normal (μ=log₁₀(1), σ=1.5 dex)."""
    log_m = random.gauss(0.0, 1.5)
    return max(0.01, 10.0 ** log_m)


def radius_from_mass(mass_earth: float) -> float:
    """Estimate radius in Earth radii from mass via broken power law.

    Rocky:      M < 1.6 Mₑ  →  R = M^0.55
    Transition: 1.6–120 Mₑ  →  slow linear growth through volatile envelope
    Gas giant:  M ≥ 120 Mₑ  →  R = (M/318)^0.55 * 11.2  (Jupiter scaling)
    """
    if mass_earth < 1.6:
        return mass_earth ** 0.55
    if mass_earth < 120.0:
        return 1.0 + (mass_earth - 1.6) * 0.01
    return (mass_earth / 318.0) ** 0.55 * 11.2


def planet_semi_major_axis_au(star_luminosity: float) -> float:
    """Draw planet semi-major axis in AU, log-normally anchored to the habitable zone.

    HZ centre ≈ sqrt(L/L☉) AU.  σ = 1.0 dex.  Clamped to [0.01, 50] AU.
    """
    hz_centre = math.sqrt(max(star_luminosity, 1e-4))
    mu = math.log10(hz_centre)
    log_a = random.gauss(mu, 1.0)
    return max(0.01, min(50.0, 10.0 ** log_a))


def hz_bounds(star_luminosity: float) -> tuple[float, float]:
    """Return (inner_AU, outer_AU) of the habitable zone.

    Simple flux-scaling from solar values:
        inner = 0.95 * sqrt(L)   (runaway greenhouse analogue)
        outer = 1.67 * sqrt(L)   (maximum greenhouse analogue)
    """
    sqrt_l = math.sqrt(max(star_luminosity, 1e-4))
    return 0.95 * sqrt_l, 1.67 * sqrt_l


def moon_count(planet_mass_earth: float) -> int:
    """Draw moon count conditioned on planet mass."""
    if planet_mass_earth < 0.1:
        return 0
    if planet_mass_earth < 10.0:
        return _poisson(1.0)
    return _poisson(3.0)


def moon_mass_earth(planet_mass_earth: float) -> float:
    """Draw moon mass in Earth masses; uniform in [1e-5, planet_mass * 0.01]."""
    upper = planet_mass_earth * 0.01
    lower = min(1e-5, upper * 0.01)
    return random.uniform(lower, upper)


def moon_semi_major_axis_au(planet_mass_earth: float) -> float:
    """Draw moon semi-major axis in AU within half the planet's Hill sphere.

    Rough Hill radius: r_H ≈ planet_mass^(1/3) * 0.01 AU.
    """
    hill_au = (planet_mass_earth ** (1.0 / 3.0)) * 0.01
    return random.uniform(0.001, max(0.001, hill_au * 0.5))


def generate_planet(star_id: int, star_luminosity: float) -> dict:
    """Generate all fields for a planet row in Bodies."""
    from starscape5.orbits import thermal_eccentricity, random_angles

    mass = planet_mass_earth()
    radius = radius_from_mass(mass)
    a = planet_semi_major_axis_au(star_luminosity)
    e = thermal_eccentricity()
    i, omega_big, omega, m0 = random_angles()
    hz_inner, hz_outer = hz_bounds(star_luminosity)
    return {
        "body_type": "planet",
        "mass": mass,
        "radius": radius,
        "orbit_star_id": star_id,
        "orbit_body_id": None,
        "semi_major_axis": a,
        "eccentricity": e,
        "inclination": i,
        "longitude_ascending_node": omega_big,
        "argument_periapsis": omega,
        "mean_anomaly": m0,
        "epoch": 0,
        "in_hz": 1 if hz_inner <= a <= hz_outer else 0,
        "possible_tidal_lock": 1 if a < 0.5 * math.sqrt(max(star_luminosity, 1e-4)) else 0,
    }


def generate_moon(planet_body_id: int, planet_mass: float) -> dict:
    """Generate all fields for a moon row in Bodies."""
    from starscape5.orbits import thermal_eccentricity, random_angles

    mass = moon_mass_earth(planet_mass)
    radius = radius_from_mass(mass)
    a = moon_semi_major_axis_au(planet_mass)
    e = thermal_eccentricity()
    i, omega_big, omega, m0 = random_angles()
    return {
        "body_type": "moon",
        "mass": mass,
        "radius": radius,
        "orbit_star_id": None,
        "orbit_body_id": planet_body_id,
        "semi_major_axis": a,
        "eccentricity": e,
        "inclination": i,
        "longitude_ascending_node": omega_big,
        "argument_periapsis": omega,
        "mean_anomaly": m0,
        "epoch": 0,
        "in_hz": None,  # moons don't orbit stars; HZ not applicable
        "possible_tidal_lock": 1,  # nearly all moons at generated distances are tidally locked
    }


# --- Internal helpers ---

def _poisson(lam: float) -> int:
    """Draw from a Poisson distribution using Knuth's algorithm."""
    l = math.exp(-lam)
    k = 0
    p = 1.0
    while p > l:
        k += 1
        p *= random.random()
    return k - 1


# --- Belt and planetoid generation ---

_GIANT_MASS_ME = 50.0       # planet mass threshold for "giant"
_MIN_GAP_AU = 0.4           # minimum gap (AU) for an inner rocky belt
_INNER_BELT_PROB = 0.55     # probability of inner belt when gap qualifies
_OUTER_BELT_PROB = 0.35     # probability of outer icy belt when a giant exists
_ISOLATED_BELT_PROB = 0.20  # probability of belt when no giant is present
_BELT_ECC_MIN = 0.10
_BELT_ECC_MAX = 0.25
_PARETO_ALPHA = 1.83        # Dohnanyi (1969) collisional equilibrium exponent
_PARETO_M_MIN = 1e-4        # minimum planetoid mass in Earth masses (~Ceres lower bound)


def _belt_eccentricity() -> float:
    return random.uniform(_BELT_ECC_MIN, _BELT_ECC_MAX)


def belt_positions(sorted_planets: list[dict], star_luminosity: float) -> list[tuple[float, float]]:
    """Return (center_au, eccentricity) for each belt to place in this system.

    Rules:
    1. Inner rocky belt (P=0.55): if a giant exists and the gap between the last rocky
       planet and the first giant is > 0.4 AU → belt at gap midpoint.
    2. Outer icy belt (P=0.35): if any giant exists → belt at 1.5–3× outermost a.
    3. No giant present (P=0.20): single belt at 1.5–3× outermost planet's a.
    """
    positions: list[tuple[float, float]] = []
    giants = [p for p in sorted_planets if (p.get("mass") or 0) >= _GIANT_MASS_ME]
    rockies = [p for p in sorted_planets if (p.get("mass") or 0) < _GIANT_MASS_ME]

    if giants:
        first_giant = min(giants, key=lambda p: p["semi_major_axis"])
        inner_rockies = [p for p in rockies
                         if p["semi_major_axis"] < first_giant["semi_major_axis"]]
        if inner_rockies:
            last_rocky = max(inner_rockies, key=lambda p: p["semi_major_axis"])
            gap = first_giant["semi_major_axis"] - last_rocky["semi_major_axis"]
            if gap > _MIN_GAP_AU and random.random() < _INNER_BELT_PROB:
                center = (last_rocky["semi_major_axis"] + first_giant["semi_major_axis"]) / 2.0
                positions.append((center, _belt_eccentricity()))

        if sorted_planets and random.random() < _OUTER_BELT_PROB:
            outermost = max(sorted_planets, key=lambda p: p["semi_major_axis"])
            center = outermost["semi_major_axis"] * random.uniform(1.5, 3.0)
            positions.append((center, _belt_eccentricity()))

    elif sorted_planets and random.random() < _ISOLATED_BELT_PROB:
        outermost = max(sorted_planets, key=lambda p: p["semi_major_axis"])
        center = outermost["semi_major_axis"] * random.uniform(1.5, 3.0)
        positions.append((center, _belt_eccentricity()))

    return positions


def belt_mass_earth() -> float:
    """Draw asteroid belt mass in Earth masses; log-normal μ=−3 dex, σ=1.0 dex."""
    log_m = random.gauss(-3.0, 1.0)
    return max(1e-6, min(0.10, 10.0 ** log_m))


def planetoid_count() -> int:
    """Draw number of significant planetoids in a belt; Poisson(2), max 5."""
    return min(5, _poisson(2.0))


def planetoid_mass_pareto(belt_mass: float) -> float:
    """Draw planetoid mass from Dohnanyi (1969) Pareto distribution.

    dN/dm ∝ m^(−α), α=1.83.  Capped at min(0.01 Mₑ, 0.5 × belt_mass).
    """
    cap = max(_PARETO_M_MIN, min(0.01, belt_mass * 0.5))
    exponent = 1.0 / (_PARETO_ALPHA - 1.0)
    m = _PARETO_M_MIN * (random.random() ** (-exponent))
    return min(m, cap)


def planetoid_semi_major_axis_au(belt_center_au: float, belt_ecc: float) -> float:
    """Draw planetoid semi-major axis uniformly within the belt zone."""
    lo = belt_center_au * (1.0 - belt_ecc)
    hi = belt_center_au * (1.0 + belt_ecc)
    return random.uniform(lo, hi)


def generate_belt(star_id: int, center_au: float, ecc: float, mass: float,
                  hz_inner: float, hz_outer: float) -> dict:
    """Generate a belt row — a statistical entity representing the diffuse belt."""
    from starscape5.orbits import random_angles
    i, omega_big, omega, _m0 = random_angles()
    return {
        "body_type": "belt",
        "mass": mass,
        "radius": None,
        "orbit_star_id": star_id,
        "orbit_body_id": None,
        "semi_major_axis": center_au,
        "eccentricity": ecc,
        "inclination": i,
        "longitude_ascending_node": omega_big,
        "argument_periapsis": omega,
        "mean_anomaly": 0.0,
        "epoch": 0,
        "in_hz": 1 if hz_inner <= center_au <= hz_outer else 0,
        "possible_tidal_lock": None,
    }


def generate_planetoid(star_id: int, belt_center_au: float, belt_ecc: float,
                       belt_mass: float, hz_inner: float, hz_outer: float) -> dict:
    """Generate a significant planetoid (Ceres-scale) within a belt."""
    from starscape5.orbits import thermal_eccentricity, random_angles
    mass = planetoid_mass_pareto(belt_mass)
    radius = radius_from_mass(mass)
    a = planetoid_semi_major_axis_au(belt_center_au, belt_ecc)
    e = thermal_eccentricity()
    i, omega_big, omega, m0 = random_angles()
    return {
        "body_type": "planetoid",
        "mass": mass,
        "radius": radius,
        "orbit_star_id": star_id,
        "orbit_body_id": None,
        "semi_major_axis": a,
        "eccentricity": e,
        "inclination": i,
        "longitude_ascending_node": omega_big,
        "argument_periapsis": omega,
        "mean_anomaly": m0,
        "epoch": 0,
        "in_hz": 1 if hz_inner <= a <= hz_outer else 0,
        "possible_tidal_lock": None,
    }
