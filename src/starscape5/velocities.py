"""Synthetic space-velocity generation for star systems without catalog data.

Physical basis
--------------
Age-velocity dispersion relation (AVR): Holmberg et al. (2009), calibrated
against Nordstrom et al. (2004) and Wielen (1977).

Population assignment:
  - Galactic height |z| and stellar age jointly determine whether a star
    belongs to the thin disk, thick disk, or halo.

Asymmetric drift:
  - Mean V-lag from Strömberg's equation: ⟨V⟩ ≈ −σV² / (2 × V_c) where
    V_c = 220 km/s is the circular speed.

Coordinate transform:
  - Galactic (U, V, W) → ICRS Cartesian (vx, vy, vz) via the IAU 1958
    rotation matrix (verified against NGP α=192.859°, δ=27.128°, J2000).

Output units: parsecs per year (pc/yr), matching hygdata_v42 and
SystemVelocities.

Usage
-----
    from starscape5.velocities import generate_velocity
    vx, vy, vz = generate_velocity(system_id, age_yr, spectral, z_mpc)
"""

from __future__ import annotations

import random

# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

# 1 km/s × (3.15576×10⁷ s/yr) / (3.085678×10¹³ km/pc) = 1.02269×10⁻⁶ pc/yr
KMS_TO_PCYR: float = 1.02269e-6

# ---------------------------------------------------------------------------
# IAU galactic → ICRS Cartesian rotation matrix
#
# Transforms galactic velocity (U, V, W) to ICRS equatorial Cartesian
# (vx, vy, vz) where:
#   U = positive toward galactic centre (l=0°, b=0°)
#   V = positive in direction of galactic rotation (l=90°, b=0°)
#   W = positive toward North Galactic Pole (b=90°)
#   vx = positive toward vernal equinox (α=0°, δ=0°)
#   vy = positive toward α=90°, δ=0°
#   vz = positive toward North Celestial Pole (δ=90°)
#
# Source: Murray (1989); Hipparcos catalogue vol. 1 eq. 1.5.11.
# Verified: U=(1,0,0) → δ≈−28.94°, α≈266.40° (galactic centre ✓)
#           W=(0,0,1) → α≈192.86°, δ≈27.13° (NGP ✓)
# ---------------------------------------------------------------------------
_T: list[list[float]] = [
    [-0.0548756,  0.4941095, -0.8676661],   # vx row
    [-0.8734371, -0.4448296, -0.1980764],   # vy row
    [-0.4838350,  0.7469823,  0.4559838],   # vz row
]


def _gal_to_icrs(U: float, V: float, W: float) -> tuple[float, float, float]:
    """Rotate galactic velocity (U,V,W) pc/yr to ICRS Cartesian (vx,vy,vz) pc/yr."""
    vx = _T[0][0] * U + _T[0][1] * V + _T[0][2] * W
    vy = _T[1][0] * U + _T[1][1] * V + _T[1][2] * W
    vz = _T[2][0] * U + _T[2][1] * V + _T[2][2] * W
    return vx, vy, vz


# ---------------------------------------------------------------------------
# Spectral-type fallback age
# ---------------------------------------------------------------------------

_SPECTRAL_AGE_GYR: dict[str, float] = {
    'O': 0.005,   # O supergiants / main-sequence — very young
    'B': 0.1,
    'A': 0.6,
    'F': 3.0,
    'G': 5.5,
    'K': 7.0,
    'M': 8.0,
    'L': 10.0,    # cool brown dwarfs — ambiguous age, use old
    'T': 10.0,
    'W': 0.005,   # Wolf-Rayet
    'D': 8.0,     # white dwarfs — conservatively old (post-MS)
    'C': 8.0,     # carbon stars (evolved K/M giants)
    'S': 8.0,     # S-type (AGB, evolved)
}


def _spectral_age_gyr(spectral: str | None) -> float:
    """Return rough age estimate in Gyr from spectral type; default 5 Gyr."""
    if spectral:
        letter = spectral.strip()[0].upper()
        return _SPECTRAL_AGE_GYR.get(letter, 5.0)
    return 5.0


# ---------------------------------------------------------------------------
# Stellar population assignment
# ---------------------------------------------------------------------------

def _population(age_gyr: float, z_pc: float) -> str:
    """
    Classify a star into thin-disk / thick-disk / halo.

    Criteria (Bensby et al. 2014; Reddy et al. 2006):
      halo       — |z| > 3 kpc, or age > 11 Gyr
      thick_disk — |z| > 1 kpc, or (|z| > 600 pc and age > 6 Gyr), or age > 9 Gyr
      thin_disk_young — age < 2 Gyr
      thin_disk_mid   — 2–6 Gyr
      thin_disk_old   — 6–9 Gyr
    """
    if z_pc > 3000 or age_gyr > 11.0:
        return 'halo'
    if z_pc > 1000 or (z_pc > 600 and age_gyr > 6.0) or age_gyr > 9.0:
        return 'thick_disk'
    if age_gyr < 2.0:
        return 'thin_disk_young'
    if age_gyr < 6.0:
        return 'thin_disk_mid'
    return 'thin_disk_old'


# ---------------------------------------------------------------------------
# Age-velocity dispersion relation (Holmberg et al. 2009, Table 4)
# ---------------------------------------------------------------------------

def _thin_disk_avr(age_gyr: float) -> tuple[float, float, float]:
    """
    1-sigma velocity dispersion (km/s) for a thin-disk star of given age.

    Power-law fit: σU = 18 + 22·(t/10)^0.31
    Ratios: σV ≈ 0.63 σU, σW ≈ 0.42 σU
    (calibrated on Hipparcos F/G dwarfs; Holmberg 2009 Table 4)
    """
    t = min(max(age_gyr, 0.1), 10.0)
    sigma_U = 18.0 + 22.0 * (t / 10.0) ** 0.31
    sigma_V = sigma_U * 0.63
    sigma_W = sigma_U * 0.42
    return sigma_U, sigma_V, sigma_W


# Fixed dispersion parameters for non-thin-disk populations (km/s).
# (sigma_U, sigma_V, sigma_W, mean_V_lag)
# Sources: Bensby et al. (2014); Carollo et al. (2010) for halo.
_FIXED_PARAMS: dict[str, tuple[float, float, float, float]] = {
    'thick_disk': (67.0, 51.0, 35.0, -46.0),
    'halo':       (141.0, 106.0, 94.0, -220.0),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_velocity(
    system_id: int,
    age_yr: float | None,
    spectral: str | None,
    z_mpc: float | None,
) -> tuple[float, float, float]:
    """
    Generate a plausible space velocity (vx, vy, vz) in pc/yr for a star system.

    The result is in the ICRS frame with the Sun at rest — the same convention
    as hygdata_v42 and SystemVelocities.  The random seed is the system_id so
    the output is fully reproducible.

    Parameters
    ----------
    system_id : int
        Determines the random seed (reproducibility).
    age_yr : float | None
        Stellar age in YEARS (as stored in DistinctStarsExtended).
        None → estimated from spectral type.
    spectral : str | None
        Spectral type string; first character used for population fallback.
    z_mpc : float | None
        Galactic z coordinate in milli-parsecs (1 mpc = 0.001 pc).
        Used to detect thick-disk / halo membership by galactic height.
    """
    rng = random.Random(system_id)

    # Age in Gyr
    if age_yr is not None and age_yr > 0:
        age_gyr = age_yr / 1e9
    else:
        age_gyr = _spectral_age_gyr(spectral)

    # Galactic height in pc (z_mpc is in milli-parsecs)
    z_pc = abs(z_mpc) * 0.001 if z_mpc is not None else 0.0

    pop = _population(age_gyr, z_pc)

    if pop in _FIXED_PARAMS:
        sU, sV, sW, mean_V = _FIXED_PARAMS[pop]
    else:
        sU, sV, sW = _thin_disk_avr(age_gyr)
        # Strömberg asymmetric drift: ⟨V⟩ ≈ −σV² / (2 × V_circ)
        mean_V = -(sV ** 2) / (2.0 * 220.0)

    # Sample galactic velocity components (km/s), then convert to pc/yr
    U = rng.gauss(0.0, sU) * KMS_TO_PCYR
    V = (rng.gauss(0.0, sV) + mean_V) * KMS_TO_PCYR
    W = rng.gauss(0.0, sW) * KMS_TO_PCYR

    return _gal_to_icrs(U, V, W)
