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


# Temperatures (K) at subtype 0 and 9 for each spectral class.
# Linear interpolation by subtype gives a reasonable per-star estimate.
_SPECTRAL_TEMP: dict[str, tuple[float, float]] = {
    "O": (50000.0, 32000.0),
    "B": (30000.0, 10500.0),
    "A": ( 9750.0,  7440.0),
    "F": ( 7220.0,  6160.0),
    "G": ( 5920.0,  5340.0),
    "K": ( 5270.0,  3910.0),
    "M": ( 3850.0,  2400.0),
}


def temperature_from_spectral(spectral: str) -> float | None:
    """Estimate effective temperature in Kelvin from a spectral type string.

    Parses the leading class letter (O B A F G K M) and optional subtype digit
    (0–9), then linearly interpolates between class endpoints.  Returns None
    if the spectral type cannot be parsed or is an unrecognised class.
    """
    if not spectral:
        return None
    cls = spectral[0].upper()
    if cls not in _SPECTRAL_TEMP:
        return None
    t0, t9 = _SPECTRAL_TEMP[cls]
    # Try to read the first digit after the class letter
    subtype: float = 5.0  # default to mid-class
    for ch in spectral[1:]:
        if ch.isdigit():
            subtype = float(ch)
            break
    return t0 + (t9 - t0) * subtype / 9.0


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


def compute_metrics(ci_raw, absmag: float | None, spectral: str | None = None) -> dict[str, float]:
    """Derive mass, temperature, radius, luminosity, age from ci (B-V) and absmag (Mv).

    Returns a dict with keys: mass, temperature, radius, luminosity, age.
    All values are rounded to 3 significant figures.
    Temperature fallback order: B-V → spectral type → mass-based estimate.
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
        temp_source = "bv"
        if temp <= 0.0:
            # B-V gave unphysical result; try spectral type next
            temp = temperature_from_spectral(spectral or "") or 0.0
            temp_source = f"spectral:{spectral}" if temp > 0.0 else None
    else:
        temp = temperature_from_spectral(spectral or "") or 0.0
        temp_source = f"spectral:{spectral}" if temp > 0.0 else None

    if temp <= 0.0:
        # Final fallback: mass-based estimate via rough MS T ~ 5778 * M^0.505
        mass_est = mass_from_luminosity(lum)
        temp = 5778.0 * (mass_est ** 0.505)
        temp_source = "mass_est"

    if temp <= 0.0:
        raise MetricsError(f"non-positive temperature: {temp}")

    radius = radius_from_lum_temp(lum, temp)
    mass = mass_from_luminosity(lum)
    age = age_from_mass_lum(mass, lum)

    return {
        "mass":        sig3(mass),
        "temperature": sig3(temp),
        "temp_source": temp_source,
        "radius":      sig3(radius),
        "luminosity":  sig3(lum),
        "age":         sig3(age),
    }
