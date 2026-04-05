"""Spectral type classification and stellar multiplicity helpers."""

import math
import random

# (letter, ci_lo, ci_hi) — B-V color index boundaries per OBAFGKM class
_BV_CLASSES = [
    ("O", -0.50, -0.30),
    ("B", -0.30, -0.10),
    ("A", -0.10,  0.10),
    ("F",  0.10,  0.29),
    ("G",  0.29,  0.59),
    ("K",  0.59,  1.00),
    ("M",  1.00,  2.00),
]


def _parse_ci(ci_raw) -> float | None:
    if ci_raw is None:
        return None
    try:
        return float(ci_raw)
    except (ValueError, TypeError):
        return None


def _bv_to_letter(bv: float) -> str:
    for letter, _lo, hi in _BV_CLASSES:
        if bv < hi:
            return letter
    return "M"


def _bv_to_subtype(bv: float, letter: str) -> int:
    for ltr, lo, hi in _BV_CLASSES:
        if ltr == letter:
            t = (bv - lo) / (hi - lo)
            return min(9, max(0, int(t * 10)))
    return 5


def _luminosity_class(absmag: float | None) -> str:
    if absmag is None:
        return "V"
    if absmag < -5.0:
        return "I"
    if absmag < 0.0:
        return "III"
    return "V"


# Approximate main-sequence (Mv, B-V) lookup table for ci_from_absmag
_MS_TABLE: list[tuple[float, float]] = [
    (-6.0, -0.33),
    (-4.0, -0.24),
    (-2.0, -0.14),
    ( 0.0,  0.00),
    ( 1.0,  0.10),
    ( 2.0,  0.20),
    ( 3.0,  0.33),
    ( 4.0,  0.45),
    ( 5.0,  0.58),
    ( 6.0,  0.72),
    ( 7.0,  0.90),
    ( 8.0,  1.10),
    (10.0,  1.40),
    (14.0,  1.70),
    (16.0,  1.90),
]


def ci_from_absmag(absmag: float) -> float:
    """Estimate B-V color index for a main-sequence star given absolute magnitude."""
    mvs = [r[0] for r in _MS_TABLE]
    bvs = [r[1] for r in _MS_TABLE]
    if absmag <= mvs[0]:
        return bvs[0]
    if absmag >= mvs[-1]:
        return bvs[-1]
    for i in range(len(mvs) - 1):
        if mvs[i] <= absmag < mvs[i + 1]:
            t = (absmag - mvs[i]) / (mvs[i + 1] - mvs[i])
            return bvs[i] + t * (bvs[i + 1] - bvs[i])
    return 0.65  # fallback K dwarf


# IMF-weighted distribution for when both ci and absmag are absent
_IMF_TYPES: list[tuple[str, float]] = [
    ("M5V",  0.45),
    ("M2V",  0.25),
    ("K5V",  0.10),
    ("K2V",  0.06),
    ("G5V",  0.05),
    ("G2V",  0.03),
    ("F5V",  0.03),
    ("A5V",  0.02),
    ("B5V",  0.008),
    ("O5V",  0.002),
]


def _random_imf_spectral() -> str:
    r = random.random()
    cumulative = 0.0
    for stype, prob in _IMF_TYPES:
        cumulative += prob
        if r < cumulative:
            return stype
    return "M5V"


def format_spectral(ci_raw, absmag: float | None) -> str:
    """Return a spectral type string (e.g. 'G2V') from B-V color index and absolute magnitude.

    Falls back to IMF-weighted random type when both inputs are absent.
    Estimates ci from absmag via main-sequence relation when only absmag is available.
    """
    ci = _parse_ci(ci_raw)
    if ci is None and absmag is None:
        return _random_imf_spectral()
    if ci is None:
        ci = ci_from_absmag(absmag)
    letter = _bv_to_letter(ci)
    subtype = _bv_to_subtype(ci, letter)
    lclass = _luminosity_class(absmag)
    return f"{letter}{subtype}{lclass}"


# Multiplicity fractions by primary spectral class (Raghavan et al. 2010; Duchêne & Kraus 2013)
MULTIPLICITY_RATE: dict[str, float] = {
    "O": 0.75,
    "B": 0.70,
    "A": 0.50,
    "F": 0.46,
    "G": 0.46,
    "K": 0.35,
    "M": 0.27,
}


def should_create_multiple(spectral: str) -> bool:
    """Return True if a new companion should be generated for this primary."""
    letter = spectral[0].upper() if spectral else "G"
    rate = MULTIPLICITY_RATE.get(letter, 0.40)
    return random.random() < rate


def companion_absmag(primary_absmag: float | None) -> float:
    """Generate a companion's absolute magnitude via mass ratio and L ~ M^4 approximation."""
    if primary_absmag is None:
        primary_absmag = 5.0  # assume G dwarf
    q = random.uniform(0.1, 0.95)
    # delta_mag = -2.5 * log10(q^4) = -10 * log10(q)
    return primary_absmag + (-10.0 * math.log10(q))
