"""Galactic disk density model and coordinate utilities.

Used by fill_stars.py to estimate expected stellar density at any point in
the 2000 pc simulation cube and to draw properties for synthetic fill stars.

Coordinate note
---------------
The database stores positions in ICRS equatorial Cartesian milliparsecs
(1 mpc = 0.001 pc):
  x → RA 0h  Dec  0°  (vernal equinox)
  y → RA 6h  Dec  0°
  z → Dec +90°         (ICRS north celestial pole, NOT galactic north)

`eq_to_galactic_mpc` rotates to galactic Cartesian where z is height above
the galactic plane, which drives the disk density model.
"""

import math
import random as _random_std

# ---------------------------------------------------------------------------
# IAU J2000.0 equatorial -> galactic rotation matrix
# (Murray 1989 / Hipparcos vol.1 §1.5.3)
# ---------------------------------------------------------------------------
_R: tuple[tuple[float, float, float], ...] = (
    (-0.054876, -0.873437, -0.483835),
    ( 0.494109, -0.444830,  0.746982),
    (-0.867666, -0.198076,  0.455984),
)

# ---------------------------------------------------------------------------
# Double-exponential disk model
# ρ(z) = ρ₀ × [f₁·exp(-|z|/h₁) + f₂·exp(-|z|/h₂)]
# Profile is normalised to 1.0 at z=0 (f₁+f₂ = 1.0).
# ρ₀ is calibrated from the local catalog density, NOT the physical density.
# ---------------------------------------------------------------------------
_H1_PC = 300.0   # thin-disk scale height (pc)
_H2_PC = 1000.0  # thick-disk scale height (pc)
_F1    = 0.86    # thin-disk fraction
_F2    = 0.14    # thick-disk fraction

# ---------------------------------------------------------------------------
# IMF-weighted spectral class distribution (Ledrew 2001 / Kroupa 2002)
# ---------------------------------------------------------------------------
_IMF_CLASSES = ["O", "B", "A", "F", "G", "K", "M"]
_IMF_WEIGHTS = [0.003, 0.13, 0.6, 3.0, 7.6, 12.1, 76.45]

# Per-class absolute magnitude Mv (Gaussian centre, σ = 0.5 mag)
_CLASS_MV: dict[str, float] = {
    "O": -4.5, "B": -1.5, "A": 2.0, "F": 4.0, "G": 5.5, "K": 7.5, "M": 11.0,
}

# Per-class B-V colour index (Gaussian centre, σ = 0.06)
_CLASS_BV: dict[str, float] = {
    "O": -0.30, "B": -0.16, "A": 0.10, "F": 0.44, "G": 0.65, "K": 1.05, "M": 1.45,
}

_MPC_PER_PC = 1000.0


# ---------------------------------------------------------------------------
# Coordinate transformation
# ---------------------------------------------------------------------------

def eq_to_galactic_mpc(
    x: float, y: float, z: float
) -> tuple[float, float, float]:
    """Rotate ICRS equatorial Cartesian (mpc) to galactic Cartesian (mpc).

    The z-component of the result is height above the galactic plane.
    """
    xg = _R[0][0] * x + _R[0][1] * y + _R[0][2] * z
    yg = _R[1][0] * x + _R[1][1] * y + _R[1][2] * z
    zg = _R[2][0] * x + _R[2][1] * y + _R[2][2] * z
    return xg, yg, zg


# ---------------------------------------------------------------------------
# Density model
# ---------------------------------------------------------------------------

def disk_profile(z_pc: float) -> float:
    """Normalised disk density profile at galactic height z_pc.

    Returns 1.0 at z=0 (midplane).  Multiply by rho_0 for abs. density.
    """
    z = abs(z_pc)
    return _F1 * math.exp(-z / _H1_PC) + _F2 * math.exp(-z / _H2_PC)


def disk_density(
    x_mpc: float, y_mpc: float, z_mpc: float, rho_0: float
) -> float:
    """Stellar catalog density in stars/pc³ at the given ICRS position (mpc).

    rho_0: calibrated local catalog density (stars/pc³) at the solar
           neighbourhood — derived from the actual catalog, not from the
           physical stellar density.
    """
    _, _, zg_mpc = eq_to_galactic_mpc(x_mpc, y_mpc, z_mpc)
    zg_pc = zg_mpc / _MPC_PER_PC
    return rho_0 * disk_profile(zg_pc)


def cell_expected_count(
    cx_mpc: float,
    cy_mpc: float,
    cz_mpc: float,
    cell_size_pc: float,
    rho_0: float,
    rng: _random_std.Random,
    n_samples: int = 200,
) -> float:
    """Monte Carlo estimate of expected catalog star count in a cubic cell.

    Parameters
    ----------
    cx, cy, cz  : cell centre in mpc
    cell_size_pc: cell edge length in pc
    rho_0       : calibrated local density (stars/pc³)
    rng         : Random instance (can be seeded per-cell for reproducibility)
    n_samples   : Monte Carlo samples
    """
    half_mpc = cell_size_pc * 0.5 * _MPC_PER_PC
    cell_vol_pc3 = cell_size_pc ** 3

    total = 0.0
    for _ in range(n_samples):
        px = cx_mpc + rng.uniform(-half_mpc, half_mpc)
        py = cy_mpc + rng.uniform(-half_mpc, half_mpc)
        pz = cz_mpc + rng.uniform(-half_mpc, half_mpc)
        total += disk_density(px, py, pz, rho_0)

    return (total / n_samples) * cell_vol_pc3


# ---------------------------------------------------------------------------
# Draw functions for synthetic star properties
# ---------------------------------------------------------------------------

def draw_spectral_class(rng: _random_std.Random) -> str:
    """Draw a spectral class letter from IMF-weighted distribution."""
    return rng.choices(_IMF_CLASSES, weights=_IMF_WEIGHTS, k=1)[0]


def draw_absmag(cls: str, rng: _random_std.Random) -> float:
    """Draw absolute magnitude Mv for a star of the given spectral class."""
    return rng.gauss(_CLASS_MV[cls], 0.5)


def draw_ci(cls: str, rng: _random_std.Random) -> float:
    """Draw B-V colour index for a star of the given spectral class."""
    return rng.gauss(_CLASS_BV[cls], 0.06)
