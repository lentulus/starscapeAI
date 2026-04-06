"""Keplerian orbital element generation for companion stars in multiple systems."""

import math
import random

# 1 milliparsec = 0.001 parsec = 0.001 * 206,265 AU
MILLIPARSEC_TO_AU: float = 206.265

# Hill sphere radius factor assuming equal neighbour mass: (M/(3M))^(1/3) = (1/3)^(1/3)
_HILL_MASS_FACTOR: float = (1.0 / 3.0) ** (1.0 / 3.0)

# Minimum periapsis-of-outer / apoapsis-of-inner ratio for inter-companion stability
_STABILITY_K: float = 3.0


class OrbitsError(ValueError):
    """Raised when an orbit cannot be generated or validated."""


def semi_major_axis_au(spectral_letter: str) -> float:
    """Draw a semi-major axis in AU from a log-normal distribution.

    O/B primaries use μ=log₁₀(200); all others use μ=log₁₀(50). σ=1.5 dex.
    Floored at 0.01 AU.
    """
    mu = math.log10(200.0) if spectral_letter.upper() in ("O", "B") else math.log10(50.0)
    log_a = random.gauss(mu, 1.5)
    return max(0.01, 10.0 ** log_a)


def thermal_eccentricity() -> float:
    """Draw eccentricity from the thermal distribution f(e)=2e → e=√(uniform).

    Capped at 0.97 to avoid near-parabolic orbits.
    """
    return min(0.97, math.sqrt(random.random()))


def random_angles() -> tuple[float, float, float, float]:
    """Return (inclination, Ω, ω, M₀) with physically correct distributions.

    Inclination is drawn from an isotropic sphere: i = arccos(uniform(-1, 1)).
    Ω, ω, M₀ are uniform on [0, 2π).
    """
    i = math.acos(random.uniform(-1.0, 1.0))
    two_pi = 2.0 * math.pi
    Omega = random.uniform(0.0, two_pi)   # longitude of ascending node
    omega = random.uniform(0.0, two_pi)   # argument of periapsis
    M0 = random.uniform(0.0, two_pi)      # mean anomaly at epoch
    return i, Omega, omega, M0


def identify_primary(stars: list[dict]) -> int:
    """Return the star_id of the most massive star in the system.

    Uses mass from DistinctStarsExtended; falls back to absmag (lower = brighter
    = more massive on the main sequence). Raises OrbitsError if neither is available.

    Each entry in stars must have keys: star_id, mass (float or None), absmag (float or None).
    """
    by_mass = [s for s in stars if s.get("mass") is not None and s["mass"] > 0]
    if by_mass:
        return max(by_mass, key=lambda s: s["mass"])["star_id"]
    by_absmag = [s for s in stars if s.get("absmag") is not None]
    if by_absmag:
        return min(by_absmag, key=lambda s: s["absmag"])["star_id"]
    raise OrbitsError("cannot identify primary: no mass or absmag available")


def hill_radius_au(neighbor_dist_mpc: float) -> float:
    """Estimate the primary's Hill sphere radius in AU.

    Assumes equal neighbour mass: r_H = d × 206.265 × (1/3)^(1/3).
    """
    return neighbor_dist_mpc * MILLIPARSEC_TO_AU * _HILL_MASS_FACTOR


def generate_orbit(primary_star_id: int, spectral_letter: str, epoch: int = 0) -> dict:
    """Generate a full set of Keplerian elements for one companion.

    Returns a dict with keys: primary_star_id, semi_major_axis, eccentricity,
    inclination, longitude_ascending_node, argument_periapsis, mean_anomaly, epoch.
    """
    a = semi_major_axis_au(spectral_letter)
    e = thermal_eccentricity()
    i, Omega, omega, M0 = random_angles()
    return {
        "primary_star_id":          primary_star_id,
        "semi_major_axis":          a,
        "eccentricity":             e,
        "inclination":              i,
        "longitude_ascending_node": Omega,
        "argument_periapsis":       omega,
        "mean_anomaly":             M0,
        "epoch":                    epoch,
    }


def enforce_stability(orbits: list[dict], hill_au: float) -> list[dict]:
    """Apply stability constraints to a list of companion orbit dicts.

    orbits must be sorted ascending by semi_major_axis before calling.
    Modifies dicts in-place and returns the list.

    Pass 1 (inside-out): expand outer semi_major_axis so that
        periapsis_outer >= STABILITY_K * apoapsis_inner
    Pass 2: cap any semi_major_axis exceeding hill_au down to hill_au.

    In very crowded systems the Hill cap may re-violate pass-1 constraints;
    this is logged at call sites and accepted as an edge case.
    """
    # Pass 1: inter-companion separation
    for idx in range(1, len(orbits)):
        inner = orbits[idx - 1]
        outer = orbits[idx]
        apoapsis_inner = inner["semi_major_axis"] * (1.0 + inner["eccentricity"])
        periapsis_outer = outer["semi_major_axis"] * (1.0 - outer["eccentricity"])
        if periapsis_outer < _STABILITY_K * apoapsis_inner:
            outer["semi_major_axis"] = (
                _STABILITY_K * apoapsis_inner / (1.0 - outer["eccentricity"])
            )

    # Pass 2: Hill sphere cap
    for orbit in orbits:
        if orbit["semi_major_axis"] > hill_au:
            orbit["semi_major_axis"] = hill_au

    return orbits
