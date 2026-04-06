"""Stellar physical parameter derivations from photometric inputs."""

import math


class MetricsError(ValueError):
    """Raised when a stellar metric cannot be computed from the available inputs."""


def sig3(x: float) -> float:
    """Round x to 3 significant figures."""
    if x == 0.0:
        return 0.0
    magnitude = math.floor(math.log10(abs(x)))
    return round(x, -int(magnitude) + 2)


def temperature_from_bv(bv: float) -> float:
    """Effective temperature in Kelvin from B-V color index.

    Ballesteros (2012) formula — valid ~2000–50000 K on the main sequence.
    """
    return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


def luminosity_from_absmag(absmag: float) -> float:
    """Luminosity in solar units from absolute visual magnitude (M_sun = 4.83)."""
    return 10.0 ** ((4.83 - absmag) / 2.5)


def radius_from_lum_temp(lum: float, temp: float) -> float:
    """Radius in solar radii via Stefan-Boltzmann: R/R_sun = sqrt(L) * (T_sun/T)^2."""
    return math.sqrt(lum) * (5778.0 / temp) ** 2


def mass_from_luminosity(lum: float) -> float:
    """Mass in solar masses via piecewise main-sequence mass-luminosity inversion (Duric 2004).

    Branches:
        L < 0.033  L_sun  (M < 0.43):  L = 0.23 * M^2.3
        0.033–16   L_sun  (0.43–2 M):  L = M^4
        16–72000   L_sun  (2–55 M):    L = 1.4 * M^3.5
        > 72000    L_sun  (> 55 M):    L = 32000 * M
    """
    if lum <= 0.0:
        raise MetricsError(f"non-positive luminosity: {lum}")
    if lum < 0.033:
        return (lum / 0.23) ** (1.0 / 2.3)
    if lum < 16.0:
        return lum ** 0.25
    if lum < 72000.0:
        return (lum / 1.4) ** (1.0 / 3.5)
    return lum / 32000.0


def age_from_mass_lum(mass: float, lum: float) -> float:
    """Estimated main-sequence lifetime in years: t ~ 1e10 * M / L."""
    if lum <= 0.0:
        raise MetricsError(f"non-positive luminosity: {lum}")
    return 1.0e10 * mass / lum


def _parse_ci(ci_raw) -> float | None:
    if ci_raw is None:
        return None
    try:
        return float(ci_raw)
    except (ValueError, TypeError):
        return None


def compute_metrics(ci_raw, absmag: float | None) -> dict[str, float]:
    """Derive mass, temperature, radius, luminosity, age from ci (B-V) and absmag (Mv).

    Returns a dict with keys: mass, temperature, radius, luminosity, age.
    All values are rounded to 3 significant figures.
    Raises MetricsError if computation is not possible.
    """
    ci = _parse_ci(ci_raw)

    if ci is None and absmag is None:
        raise MetricsError("both ci and absmag are absent")

    if absmag is None:
        raise MetricsError("absmag is required to compute luminosity")

    lum = luminosity_from_absmag(absmag)
    if lum <= 0.0:
        raise MetricsError(f"non-positive luminosity derived from absmag={absmag}")

    if ci is not None:
        temp = temperature_from_bv(ci)
        if temp <= 0.0:
            # B-V gave unphysical result; fall back to mass-based estimate
            mass_est = mass_from_luminosity(lum)
            temp = 5778.0 * (mass_est ** 0.505)
    else:
        # Fallback: estimate T from mass via rough MS T ~ 5778 * M^0.505
        mass_est = mass_from_luminosity(lum)
        temp = 5778.0 * (mass_est ** 0.505)

    if temp <= 0.0:
        raise MetricsError(f"non-positive temperature: {temp}")

    radius = radius_from_lum_temp(lum, temp)
    mass = mass_from_luminosity(lum)
    age = age_from_mass_lum(mass, lum)

    return {
        "mass":        sig3(mass),
        "temperature": sig3(temp),
        "radius":      sig3(radius),
        "luminosity":  sig3(lum),
        "age":         sig3(age),
    }
