#!/usr/bin/env python3
"""Seed the Bodies table with the real Solar System for star_id = 1 (Sol).

All WBH and simulation columns are populated with real physical values.
This script is the authoritative source for Sol bodies and should be re-run
whenever Bodies is recreated from scratch.

Usage:
    uv run scripts/seed_sol.py
    uv run scripts/seed_sol.py --db /path/to/other.db
    uv run scripts/seed_sol.py --force   # re-seed even if Sol already has bodies
"""

from __future__ import annotations

import argparse
import logging
import math
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
SOL_STAR_ID = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _moon_pd(orbit_au: float, parent_diam_km: float) -> float:
    """Moon orbital radius in planetary diameters."""
    return round(orbit_au * 149_597_870.7 / parent_diam_km, 2)


def _hill_pd(
    planet_au: float,
    planet_ecc: float,
    mass_earth: float,
    parent_diam_km: float,
    star_mass_msol: float = 1.0,
) -> float:
    """Hill sphere limit in planetary diameters (moon limit = hill_PD / 2)."""
    hs_au  = planet_au * (1.0 - planet_ecc) * (mass_earth / (3.0 * star_mass_msol * 333_000)) ** (1/3)
    hs_pd  = hs_au * 149_597_870.7 / parent_diam_km
    return round(hs_pd / 2.0, 2)


# ---------------------------------------------------------------------------
# Solar System bodies
#
# Each dict contains every column that seed_sol.py populates.
# Keys match the Bodies column names exactly.
# Columns not set (e.g. taint slots for clean atmospheres) are omitted and
# default to NULL.
# ---------------------------------------------------------------------------

# --- Planets ---
# Orbital elements: all angles in radians; a in AU; mass in Mₑ; radius in Rₑ.
# WBH physical: density relative to Terra (5.514 g/cm³).

PLANETS: list[dict] = [
    {
        "name": "Mercury",
        "body_type": "planet", "planet_class": "rocky",
        "mass": 0.05527, "radius": 0.3829,
        "semi_major_axis": 0.38710, "eccentricity": 0.20563,
        "inclination": 0.12217, "longitude_ascending_node": 0.84301,
        "argument_periapsis": 0.50819, "mean_anomaly": 5.66, "epoch": 0,
        "in_hz": 0, "has_rings": 0, "generation_source": "manual",
        # WBH physical
        "size_code": "3", "diameter_km": 4879.0, "composition": "Rock and Metal",
        "density": 0.985, "gravity_g": 0.378, "mass_earth": 0.05527,
        "escape_vel_kms": 4.25,
        # Atmosphere
        "atm_type": "trace", "atm_pressure_atm": 1e-14, "atm_composition": "none",
        "surface_temp_k": 340.0, "hydrosphere": None,
        "albedo": 0.088, "greenhouse_factor": 1.00,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0, "gases": None,
        # Hydro
        "hydro_code": 0, "hydro_pct": 0.0, "mean_temp_k": 167.0,
        # Rotation — 3:2 resonance
        "tidal_lock_status": "3:2", "sidereal_day_hours": 1407.6,
        "solar_day_hours": None, "axial_tilt_deg": 0.03,
        "possible_tidal_lock": 1,
        # Seismic — geologically quiet, no active tectonics
        "seismic_residual": 1.0, "seismic_tidal": 0.2, "seismic_heating": 0.2,
        "seismic_total": 1.4, "tectonic_plates": None,
        "biomass_rating": 0,
    },
    {
        "name": "Venus",
        "body_type": "planet", "planet_class": "rocky",
        "mass": 0.81500, "radius": 0.9499,
        "semi_major_axis": 0.72333, "eccentricity": 0.00677,
        "inclination": 0.05924, "longitude_ascending_node": 1.33872,
        "argument_periapsis": 0.95877, "mean_anomaly": 0.04, "epoch": 0,
        "in_hz": 0, "has_rings": 0, "generation_source": "manual",
        "size_code": "8", "diameter_km": 12104.0, "composition": "Rock and Metal",
        "density": 0.950, "gravity_g": 0.905, "mass_earth": 0.81500,
        "escape_vel_kms": 10.36,
        "atm_type": "corrosive", "atm_pressure_atm": 92.0, "atm_composition": "h2so4",
        "surface_temp_k": 737.0, "hydrosphere": None,
        "albedo": 0.65, "greenhouse_factor": 2.20,
        "atm_code": "B", "pressure_bar": 93.2, "ppo_bar": 0.0,
        "gases": "CO2:97,SO2:2,N2:1",
        "hydro_code": 0, "hydro_pct": 0.0, "mean_temp_k": 737.0,
        # Retrograde slow rotation; solar day ≈ 2802 h
        "tidal_lock_status": "slow_retrograde", "sidereal_day_hours": -5832.5,
        "solar_day_hours": 2802.0, "axial_tilt_deg": 177.36,
        "possible_tidal_lock": 1,
        "seismic_residual": 2.5, "seismic_tidal": 0.0, "seismic_heating": 0.0,
        "seismic_total": 2.5, "tectonic_plates": None,
        "biomass_rating": 0,
    },
    {
        "name": "Earth",
        "body_type": "planet", "planet_class": "rocky",
        "mass": 1.00000, "radius": 1.0000,
        "semi_major_axis": 1.00000, "eccentricity": 0.01671,
        "inclination": 0.00000, "longitude_ascending_node": 0.00000,
        "argument_periapsis": 1.99330, "mean_anomaly": 0.00, "epoch": 0,
        "in_hz": 1, "has_rings": 0, "generation_source": "manual",
        "size_code": "8", "diameter_km": 12742.0, "composition": "Rock and Metal",
        "density": 1.000, "gravity_g": 1.000, "mass_earth": 1.00000,
        "escape_vel_kms": 11.19,
        # Standard N₂/O₂ atmosphere
        "atm_type": "standard", "atm_pressure_atm": 1.000, "atm_composition": "n2o2",
        "surface_temp_k": 288.0, "hydrosphere": 0.710,
        "albedo": 0.306, "greenhouse_factor": 1.10,
        "atm_code": "7", "pressure_bar": 1.013, "ppo_bar": 0.213,
        "gases": "N2:78,O2:21,Ar:1",
        "hydro_code": 7, "hydro_pct": 71.0, "mean_temp_k": 288.0,
        "tidal_lock_status": "none", "sidereal_day_hours": 23.934,
        "solar_day_hours": 24.000, "axial_tilt_deg": 23.44,
        "possible_tidal_lock": 0,
        "seismic_residual": 4.0, "seismic_tidal": 1.5, "seismic_heating": 1.2,
        "seismic_total": 6.7, "tectonic_plates": 8,
        "biomass_rating": 5,
        # surface_gravity and escape_velocity_kms (legacy cols)
        "surface_gravity": 1.0, "escape_velocity_kms": 11.19, "t_eq_k": 255.0,
    },
    {
        "name": "Mars",
        "body_type": "planet", "planet_class": "rocky",
        "mass": 0.10745, "radius": 0.5320,
        "semi_major_axis": 1.52366, "eccentricity": 0.09341,
        "inclination": 0.03229, "longitude_ascending_node": 0.86536,
        "argument_periapsis": 5.00017, "mean_anomaly": 1.35, "epoch": 0,
        "in_hz": 0, "has_rings": 0, "generation_source": "manual",
        "size_code": "4", "diameter_km": 6779.0, "composition": "Rock and Metal",
        "density": 0.713, "gravity_g": 0.379, "mass_earth": 0.10745,
        "escape_vel_kms": 5.03,
        "atm_type": "trace", "atm_pressure_atm": 0.006, "atm_composition": "co2",
        "surface_temp_k": 210.0, "hydrosphere": 0.0,
        "albedo": 0.250, "greenhouse_factor": 1.00,
        "atm_code": "1", "pressure_bar": 0.006, "ppo_bar": 0.0,
        "gases": "CO2:95,N2:3,Ar:2",
        "hydro_code": 0, "hydro_pct": 0.0, "mean_temp_k": 210.0,
        "tidal_lock_status": "none", "sidereal_day_hours": 24.623,
        "solar_day_hours": 24.660, "axial_tilt_deg": 25.19,
        "possible_tidal_lock": 0,
        "seismic_residual": 1.5, "seismic_tidal": 0.2, "seismic_heating": 0.2,
        "seismic_total": 1.9, "tectonic_plates": None,
        "biomass_rating": 0,
        "surface_gravity": 0.379, "escape_velocity_kms": 5.03, "t_eq_k": 210.0,
    },
    {
        "name": "Jupiter",
        "body_type": "planet", "planet_class": "large_gg",
        "mass": 317.83, "radius": 11.209,
        "semi_major_axis": 5.20336, "eccentricity": 0.04839,
        "inclination": 0.02271, "longitude_ascending_node": 1.75397,
        "argument_periapsis": 4.78218, "mean_anomaly": 3.30, "epoch": 0,
        "in_hz": 0, "has_rings": 1, "generation_source": "manual",
        "size_code": "GL", "diameter_km": 142984.0, "composition": "Mostly Ice",
        "density": 0.241, "gravity_g": 2.528, "mass_earth": 317.83,
        "escape_vel_kms": 59.5,
        "tidal_lock_status": "none", "sidereal_day_hours": 9.925,
        "solar_day_hours": 9.926, "axial_tilt_deg": 3.13,
        "possible_tidal_lock": 0,
    },
    {
        "name": "Saturn",
        "body_type": "planet", "planet_class": "large_gg",
        "mass": 95.162, "radius": 9.4492,
        "semi_major_axis": 9.53707, "eccentricity": 0.05415,
        "inclination": 0.04340, "longitude_ascending_node": 1.98349,
        "argument_periapsis": 5.92392, "mean_anomaly": 3.32, "epoch": 0,
        "in_hz": 0, "has_rings": 1, "generation_source": "manual",
        "size_code": "GL", "diameter_km": 120536.0, "composition": "Mostly Ice",
        "density": 0.125, "gravity_g": 1.065, "mass_earth": 95.162,
        "escape_vel_kms": 35.5,
        "tidal_lock_status": "none", "sidereal_day_hours": 10.656,
        "solar_day_hours": 10.657, "axial_tilt_deg": 26.73,
        "possible_tidal_lock": 0,
    },
    {
        "name": "Uranus",
        "body_type": "planet", "planet_class": "small_gg",
        "mass": 14.536, "radius": 4.0074,
        "semi_major_axis": 19.1913, "eccentricity": 0.04717,
        "inclination": 0.01344, "longitude_ascending_node": 1.29154,
        "argument_periapsis": 1.68418, "mean_anomaly": 0.47, "epoch": 0,
        "in_hz": 0, "has_rings": 1, "generation_source": "manual",
        "size_code": "GS", "diameter_km": 51118.0, "composition": "Mostly Ice",
        "density": 0.230, "gravity_g": 0.905, "mass_earth": 14.536,
        "escape_vel_kms": 21.3,
        # Retrograde rotation (axial tilt > 90°)
        "tidal_lock_status": "none", "sidereal_day_hours": -17.240,
        "solar_day_hours": -17.241, "axial_tilt_deg": 97.77,
        "possible_tidal_lock": 0,
    },
    {
        "name": "Neptune",
        "body_type": "planet", "planet_class": "small_gg",
        "mass": 17.147, "radius": 3.8827,
        "semi_major_axis": 30.0690, "eccentricity": 0.00859,
        "inclination": 0.03089, "longitude_ascending_node": 2.30031,
        "argument_periapsis": 4.76942, "mean_anomaly": 2.84, "epoch": 0,
        "in_hz": 0, "has_rings": 1, "generation_source": "manual",
        "size_code": "GS", "diameter_km": 49528.0, "composition": "Mostly Ice",
        "density": 0.297, "gravity_g": 1.137, "mass_earth": 17.147,
        "escape_vel_kms": 23.5,
        "tidal_lock_status": "none", "sidereal_day_hours": 16.110,
        "solar_day_hours": 16.111, "axial_tilt_deg": 28.32,
        "possible_tidal_lock": 0,
    },
]

# --- Moons ---
# a_au = semi-major axis in AU from parent planet centre.
# moon_PD / hill_PD computed in _build_moon() using parent data.

_MOON_DATA: list[dict] = [
    # Earth
    {
        "parent": "Earth", "name": "Moon",
        "mass": 0.012300, "radius": 0.27268,
        "a_au": 0.002569, "eccentricity": 0.0549,
        "inclination": 0.08980, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "2", "diameter_km": 3474.0, "composition": "Mostly Rock",
        "density": 0.606, "gravity_g": 0.165, "mass_earth": 0.01230,
        "escape_vel_kms": 2.38,
        "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
        "surface_temp_k": 250.0, "hydrosphere": None,
        "albedo": 0.12, "greenhouse_factor": 1.0,
        "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 207.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 655.7,
        "solar_day_hours": None, "axial_tilt_deg": 6.68,
        "seismic_residual": 1.2, "seismic_tidal": 0.9, "seismic_heating": 0.7,
        "seismic_total": 2.8, "tectonic_plates": None, "biomass_rating": 0,
    },
    # Mars
    {
        "parent": "Mars", "name": "Phobos",
        "mass": 1.07e-8, "radius": 0.00152,
        "a_au": 6.27e-5, "eccentricity": 0.0151,
        "inclination": 0.00175, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "S", "diameter_km": 22.0, "composition": "Mostly Rock",
        "density": 0.330, "gravity_g": 0.0006, "mass_earth": 1.07e-8,
        "escape_vel_kms": 0.011,
        "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
        "surface_temp_k": 233.0, "hydrosphere": None,
        "albedo": 0.07, "greenhouse_factor": 1.0,
        "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 233.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 7.65,
        "solar_day_hours": None, "axial_tilt_deg": 0.0,
        "seismic_residual": 0.0, "seismic_tidal": 0.5, "seismic_heating": 0.4,
        "seismic_total": 0.9, "tectonic_plates": None, "biomass_rating": 0,
    },
    {
        "parent": "Mars", "name": "Deimos",
        "mass": 1.48e-9, "radius": 0.00083,
        "a_au": 1.57e-4, "eccentricity": 0.0003,
        "inclination": 0.00505, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "S", "diameter_km": 13.0, "composition": "Mostly Rock",
        "density": 0.270, "gravity_g": 0.0003, "mass_earth": 1.48e-9,
        "escape_vel_kms": 0.006,
        "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
        "surface_temp_k": 233.0, "hydrosphere": None,
        "albedo": 0.07, "greenhouse_factor": 1.0,
        "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 233.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 30.31,
        "solar_day_hours": None, "axial_tilt_deg": 0.0,
        "seismic_residual": 0.0, "seismic_tidal": 0.1, "seismic_heating": 0.1,
        "seismic_total": 0.2, "tectonic_plates": None, "biomass_rating": 0,
    },
    # Jupiter — Galilean moons
    {
        "parent": "Jupiter", "name": "Io",
        "mass": 0.01496, "radius": 0.28602,
        "a_au": 0.002820, "eccentricity": 0.0041,
        "inclination": 0.00698, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "2", "diameter_km": 3643.0, "composition": "Rock and Metal",
        "density": 0.661, "gravity_g": 0.183, "mass_earth": 0.01496,
        "escape_vel_kms": 2.56,
        # SO₂-dominated tenuous atmosphere
        "atm_type": "trace", "atm_pressure_atm": 1e-7, "atm_composition": "none",
        "surface_temp_k": 130.0, "hydrosphere": None,
        "albedo": 0.63, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 130.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 42.46,
        "solar_day_hours": None, "axial_tilt_deg": 0.04,
        # Extreme tidal heating — most volcanically active body in Solar System
        "seismic_residual": 3.0, "seismic_tidal": 5.0, "seismic_heating": 4.0,
        "seismic_total": 12.0, "tectonic_plates": 12, "biomass_rating": 0,
    },
    {
        "parent": "Jupiter", "name": "Europa",
        "mass": 0.00804, "radius": 0.24520,
        "a_au": 0.004486, "eccentricity": 0.0094,
        "inclination": 0.00796, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "2", "diameter_km": 3122.0, "composition": "Mostly Ice",
        "density": 0.545, "gravity_g": 0.134, "mass_earth": 0.00804,
        "escape_vel_kms": 2.03,
        "atm_type": "trace", "atm_pressure_atm": 1e-8, "atm_composition": "none",
        "surface_temp_k": 102.0, "hydrosphere": 0.90,   # subsurface ocean
        "albedo": 0.67, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": 9, "hydro_pct": 90.0, "mean_temp_k": 102.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 85.23,
        "solar_day_hours": None, "axial_tilt_deg": 0.10,
        "seismic_residual": 2.0, "seismic_tidal": 3.5, "seismic_heating": 2.8,
        "seismic_total": 8.3, "tectonic_plates": 6, "biomass_rating": 0,
    },
    {
        "parent": "Jupiter", "name": "Ganymede",
        "mass": 0.02515, "radius": 0.41297,
        "a_au": 0.007155, "eccentricity": 0.0013,
        "inclination": 0.00314, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "3", "diameter_km": 5268.0, "composition": "Mostly Ice",
        "density": 0.346, "gravity_g": 0.146, "mass_earth": 0.02515,
        "escape_vel_kms": 2.74,
        "atm_type": "trace", "atm_pressure_atm": 1e-8, "atm_composition": "none",
        "surface_temp_k": 110.0, "hydrosphere": None,
        "albedo": 0.43, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 110.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 171.71,
        "solar_day_hours": None, "axial_tilt_deg": 0.18,
        "seismic_residual": 1.5, "seismic_tidal": 1.5, "seismic_heating": 1.2,
        "seismic_total": 4.2, "tectonic_plates": 2, "biomass_rating": 0,
    },
    {
        "parent": "Jupiter", "name": "Callisto",
        "mass": 0.01803, "radius": 0.37847,
        "a_au": 0.012585, "eccentricity": 0.0074,
        "inclination": 0.00349, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "3", "diameter_km": 4821.0, "composition": "Mostly Ice",
        "density": 0.337, "gravity_g": 0.126, "mass_earth": 0.01803,
        "escape_vel_kms": 2.44,
        "atm_type": "trace", "atm_pressure_atm": 7.5e-9, "atm_composition": "none",
        "surface_temp_k": 134.0, "hydrosphere": None,
        "albedo": 0.22, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 134.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 400.54,
        "solar_day_hours": None, "axial_tilt_deg": 0.19,
        "seismic_residual": 0.8, "seismic_tidal": 0.3, "seismic_heating": 0.2,
        "seismic_total": 1.3, "tectonic_plates": None, "biomass_rating": 0,
    },
    # Saturn
    {
        "parent": "Saturn", "name": "Titan",
        "mass": 0.02254, "radius": 0.40400,
        "a_au": 0.008168, "eccentricity": 0.0288,
        "inclination": 0.00872, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "3", "diameter_km": 5149.0, "composition": "Mostly Ice",
        "density": 0.342, "gravity_g": 0.138, "mass_earth": 0.02254,
        "escape_vel_kms": 2.64,
        # Dense N₂/CH₄ atmosphere
        "atm_type": "standard", "atm_pressure_atm": 1.467, "atm_composition": "methane",
        "surface_temp_k": 94.0, "hydrosphere": 0.20,   # methane lakes
        "albedo": 0.22, "greenhouse_factor": 1.10,
        "atm_code": "7", "pressure_bar": 1.486, "ppo_bar": 0.0,
        "gases": "N2:95,CH4:4,Ar:1",
        "hydro_code": 2, "hydro_pct": 20.0, "mean_temp_k": 94.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 382.69,
        "solar_day_hours": None, "axial_tilt_deg": 0.33,
        "seismic_residual": 1.2, "seismic_tidal": 1.0, "seismic_heating": 0.8,
        "seismic_total": 3.0, "tectonic_plates": None, "biomass_rating": 0,
    },
    {
        "parent": "Saturn", "name": "Enceladus",
        "mass": 1.80e-5, "radius": 0.03956,
        "a_au": 0.001591, "eccentricity": 0.0047,
        "inclination": 0.00000, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "S", "diameter_km": 504.0, "composition": "Mostly Ice",
        "density": 0.208, "gravity_g": 0.0082, "mass_earth": 1.80e-5,
        "escape_vel_kms": 0.24,
        "atm_type": "trace", "atm_pressure_atm": 1e-9, "atm_composition": "none",
        "surface_temp_k": 75.0, "hydrosphere": None,
        "albedo": 0.99, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 75.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 32.89,
        "solar_day_hours": None, "axial_tilt_deg": 0.0,
        "seismic_residual": 1.0, "seismic_tidal": 3.0, "seismic_heating": 2.4,
        "seismic_total": 6.4, "tectonic_plates": 4, "biomass_rating": 0,
    },
    # Uranus
    {
        "parent": "Uranus", "name": "Titania",
        "mass": 5.90e-4, "radius": 0.11394,
        "a_au": 0.002916, "eccentricity": 0.0011,
        "inclination": 0.00000, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "1", "diameter_km": 1578.0, "composition": "Mostly Ice",
        "density": 0.303, "gravity_g": 0.0376, "mass_earth": 5.90e-4,
        "escape_vel_kms": 0.77,
        "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
        "surface_temp_k": 60.0, "hydrosphere": None,
        "albedo": 0.35, "greenhouse_factor": 1.0,
        "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 60.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 208.94,
        "solar_day_hours": None, "axial_tilt_deg": 0.08,
        "seismic_residual": 0.5, "seismic_tidal": 0.2, "seismic_heating": 0.2,
        "seismic_total": 0.9, "tectonic_plates": None, "biomass_rating": 0,
    },
    {
        "parent": "Uranus", "name": "Oberon",
        "mass": 5.08e-4, "radius": 0.11003,
        "a_au": 0.003902, "eccentricity": 0.0014,
        "inclination": 0.00000, "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "1", "diameter_km": 1523.0, "composition": "Mostly Ice",
        "density": 0.286, "gravity_g": 0.0346, "mass_earth": 5.08e-4,
        "escape_vel_kms": 0.73,
        "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
        "surface_temp_k": 58.0, "hydrosphere": None,
        "albedo": 0.31, "greenhouse_factor": 1.0,
        "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 58.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 323.11,
        "solar_day_hours": None, "axial_tilt_deg": 0.10,
        "seismic_residual": 0.5, "seismic_tidal": 0.1, "seismic_heating": 0.1,
        "seismic_total": 0.7, "tectonic_plates": None, "biomass_rating": 0,
    },
    # Neptune — Triton is retrograde (captured KBO)
    {
        "parent": "Neptune", "name": "Triton",
        "mass": 3.58e-4, "radius": 0.21275,
        "a_au": 0.002371, "eccentricity": 0.0000,
        "inclination": 2.74889, "longitude_ascending_node": 0.0,   # retrograde; i > π/2
        "argument_periapsis": 0.0, "mean_anomaly": 0.0,
        "size_code": "2", "diameter_km": 2707.0, "composition": "Mostly Ice",
        "density": 0.369, "gravity_g": 0.0791, "mass_earth": 3.58e-4,
        "escape_vel_kms": 1.46,
        "atm_type": "trace", "atm_pressure_atm": 1.4e-5, "atm_composition": "none",
        "surface_temp_k": 38.0, "hydrosphere": None,
        "albedo": 0.76, "greenhouse_factor": 1.0,
        "atm_code": "1", "pressure_bar": 0.0, "ppo_bar": 0.0,
        "hydro_code": None, "hydro_pct": None, "mean_temp_k": 38.0,
        "tidal_lock_status": "1:1", "sidereal_day_hours": 141.05,
        "solar_day_hours": None, "axial_tilt_deg": 0.0,
        "seismic_residual": 0.8, "seismic_tidal": 1.2, "seismic_heating": 1.0,
        "seismic_total": 3.0, "tectonic_plates": None, "biomass_rating": 0,
    },
]

# --- Belt and Ceres ---
# Asteroid belt: representative row. BeltProfile row provides composition detail.
BELT: dict = {
    "body_type": "belt", "planet_class": None,
    "mass": 4.5e-4, "radius": None,
    "semi_major_axis": 2.70, "eccentricity": 0.17,
    "inclination": 0.0927, "longitude_ascending_node": 0.0,
    "argument_periapsis": 0.0, "mean_anomaly": 0.0, "epoch": 0,
    "orbit_star_id": SOL_STAR_ID, "orbit_body_id": None,
    "in_hz": 0, "has_rings": None, "generation_source": "manual",
    "size_code": "0", "diameter_km": 0.0,
    "composition": "Rock and Metal",
}
BELT_PROFILE: dict = {
    "span_orbit_num": 0.50,
    "m_type_pct": 8, "s_type_pct": 17, "c_type_pct": 75, "other_pct": 0,
    "bulk": 4, "resource_rating": 4,
    "size1_bodies": 4, "sizeS_bodies": 15,
}

CERES: dict = {
    "body_type": "planetoid", "planet_class": None,
    "mass": 1.57e-4, "radius": 0.074,
    "semi_major_axis": 2.7691, "eccentricity": 0.0760,
    "inclination": 0.1849, "longitude_ascending_node": 1.4024,
    "argument_periapsis": 1.2780, "mean_anomaly": 0.0, "epoch": 0,
    "orbit_star_id": SOL_STAR_ID, "orbit_body_id": None,
    "in_hz": 0, "has_rings": None, "generation_source": "manual",
    "size_code": "S", "diameter_km": 945.0, "composition": "Mostly Rock",
    "density": 0.390, "gravity_g": 0.029, "mass_earth": 1.57e-4,
    "escape_vel_kms": 0.51,
    "atm_type": "none", "atm_pressure_atm": 0.0, "atm_composition": "none",
    "surface_temp_k": 168.0, "hydrosphere": None,
    "albedo": 0.09, "greenhouse_factor": 1.0,
    "atm_code": "0", "pressure_bar": 0.0, "ppo_bar": 0.0,
    "hydro_code": None, "hydro_pct": None, "mean_temp_k": 168.0,
    "tidal_lock_status": "none", "sidereal_day_hours": 9.074,
    "solar_day_hours": 9.074, "axial_tilt_deg": 4.0,
    "possible_tidal_lock": 0,
    "seismic_residual": 0.5, "seismic_tidal": 0.0, "seismic_heating": 0.0,
    "seismic_total": 0.5, "tectonic_plates": None, "biomass_rating": 0,
}

# ---------------------------------------------------------------------------
# INSERT SQL — named parameters, covers all WBH columns.
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT INTO Bodies (
    body_type, mass, radius,
    orbit_star_id, orbit_body_id,
    semi_major_axis, eccentricity, inclination,
    longitude_ascending_node, argument_periapsis, mean_anomaly, epoch,
    in_hz, possible_tidal_lock, planet_class, has_rings,
    generation_source,
    size_code, diameter_km, composition, density,
    gravity_g, mass_earth, escape_vel_kms,
    surface_gravity, escape_velocity_kms, t_eq_k,
    atm_type, atm_pressure_atm, atm_composition, surface_temp_k, hydrosphere,
    albedo, greenhouse_factor, atm_code, pressure_bar, ppo_bar, gases,
    hydro_code, hydro_pct, mean_temp_k,
    sidereal_day_hours, solar_day_hours, axial_tilt_deg, tidal_lock_status,
    seismic_residual, seismic_tidal, seismic_heating, seismic_total, tectonic_plates,
    biomass_rating,
    moon_PD, hill_PD, roche_PD
) VALUES (
    :body_type, :mass, :radius,
    :orbit_star_id, :orbit_body_id,
    :semi_major_axis, :eccentricity, :inclination,
    :longitude_ascending_node, :argument_periapsis, :mean_anomaly, :epoch,
    :in_hz, :possible_tidal_lock, :planet_class, :has_rings,
    :generation_source,
    :size_code, :diameter_km, :composition, :density,
    :gravity_g, :mass_earth, :escape_vel_kms,
    :surface_gravity, :escape_velocity_kms, :t_eq_k,
    :atm_type, :atm_pressure_atm, :atm_composition, :surface_temp_k, :hydrosphere,
    :albedo, :greenhouse_factor, :atm_code, :pressure_bar, :ppo_bar, :gases,
    :hydro_code, :hydro_pct, :mean_temp_k,
    :sidereal_day_hours, :solar_day_hours, :axial_tilt_deg, :tidal_lock_status,
    :seismic_residual, :seismic_tidal, :seismic_heating, :seismic_total, :tectonic_plates,
    :biomass_rating,
    :moon_PD, :hill_PD, :roche_PD
)
"""

_ALL_COLS = {
    "body_type", "mass", "radius",
    "orbit_star_id", "orbit_body_id",
    "semi_major_axis", "eccentricity", "inclination",
    "longitude_ascending_node", "argument_periapsis", "mean_anomaly", "epoch",
    "in_hz", "possible_tidal_lock", "planet_class", "has_rings",
    "generation_source",
    "size_code", "diameter_km", "composition", "density",
    "gravity_g", "mass_earth", "escape_vel_kms",
    "surface_gravity", "escape_velocity_kms", "t_eq_k",
    "atm_type", "atm_pressure_atm", "atm_composition", "surface_temp_k", "hydrosphere",
    "albedo", "greenhouse_factor", "atm_code", "pressure_bar", "ppo_bar", "gases",
    "hydro_code", "hydro_pct", "mean_temp_k",
    "sidereal_day_hours", "solar_day_hours", "axial_tilt_deg", "tidal_lock_status",
    "seismic_residual", "seismic_tidal", "seismic_heating", "seismic_total", "tectonic_plates",
    "biomass_rating",
    "moon_PD", "hill_PD", "roche_PD",
}

_BELT_PROFILE_SQL = """
INSERT INTO BeltProfile
    (body_id, span_orbit_num, m_type_pct, s_type_pct, c_type_pct, other_pct,
     bulk, resource_rating, size1_bodies, sizeS_bodies)
VALUES
    (:body_id, :span_orbit_num, :m_type_pct, :s_type_pct, :c_type_pct, :other_pct,
     :bulk, :resource_rating, :size1_bodies, :sizeS_bodies)
"""


def _row(d: dict) -> dict:
    """Return a copy of d with all INSERT columns present (missing → None)."""
    out = {k: None for k in _ALL_COLS}
    out.update(d)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db",    type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true",
                        help="Re-seed Sol even if planets already exist")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM Bodies WHERE orbit_star_id = ?", (SOL_STAR_ID,)
        ).fetchone()[0]

        if existing and not args.force:
            log.info("Sol already has %d bodies. Use --force to re-seed.", existing)
            return

        if existing and args.force:
            log.info("--force: removing %d existing Sol bodies.", existing)
            conn.execute(
                "DELETE FROM Bodies WHERE orbit_body_id IN "
                "(SELECT body_id FROM Bodies WHERE orbit_star_id = ?)",
                (SOL_STAR_ID,),
            )
            conn.execute("DELETE FROM Bodies WHERE orbit_star_id = ?", (SOL_STAR_ID,))
            conn.commit()

        # --- Insert planets ---
        planet_ids: dict[str, int] = {}
        for p in PLANETS:
            row = _row({
                "orbit_star_id": SOL_STAR_ID,
                "orbit_body_id": None,
                "epoch":         0,
                "surface_gravity":      p.get("gravity_g"),
                "escape_velocity_kms":  p.get("escape_vel_kms"),
                "t_eq_k":               p.get("surface_temp_k"),
                **p,
            })
            row.pop("name", None)
            cur = conn.execute(_INSERT_SQL, row)
            planet_ids[p["name"]] = cur.lastrowid
            log.info("  Planet %-8s body_id=%d", p["name"], cur.lastrowid)

        # --- Insert moons ---
        for m in _MOON_DATA:
            parent_name = m["parent"]
            parent_id   = planet_ids[parent_name]
            parent_p    = next(p for p in PLANETS if p["name"] == parent_name)
            parent_diam = parent_p["diameter_km"]
            parent_mass = parent_p["mass_earth"]
            a_au        = m["a_au"]

            mpd  = _moon_pd(a_au, parent_diam)
            hpd  = _hill_pd(parent_p["semi_major_axis"], parent_p["eccentricity"],
                            parent_mass, parent_diam)
            rpd  = 1.54

            # Sidereal day = orbital period around parent
            parent_mass_solar = parent_mass / 333_000.0
            sid_hr = math.sqrt(a_au ** 3 / max(parent_mass_solar, 1e-20)) * 8766.0

            row = _row({
                "orbit_star_id": None,
                "orbit_body_id": parent_id,
                "epoch":         0,
                "body_type":     "moon",
                "planet_class":  None,
                "possible_tidal_lock": 1,
                "surface_gravity":     m.get("gravity_g"),
                "escape_velocity_kms": m.get("escape_vel_kms"),
                "t_eq_k":              m.get("surface_temp_k"),
                "sidereal_day_hours":  round(sid_hr, 2),
                "moon_PD":  mpd,
                "hill_PD":  hpd,
                "roche_PD": rpd,
                **m,
            })
            row.pop("name",   None)
            row.pop("parent", None)
            row.pop("a_au",   None)
            row["semi_major_axis"] = a_au
            cur = conn.execute(_INSERT_SQL, row)
            log.info("    Moon %-10s → %-8s body_id=%d", m["name"], parent_name, cur.lastrowid)

        # --- Insert asteroid belt ---
        belt_row = _row(BELT)
        cur = conn.execute(_INSERT_SQL, belt_row)
        belt_id = cur.lastrowid
        conn.execute(_BELT_PROFILE_SQL, {"body_id": belt_id, **BELT_PROFILE})
        log.info("  Belt (a=2.70 AU) body_id=%d", belt_id)

        # --- Insert Ceres ---
        ceres_row = _row({
            "orbit_star_id": SOL_STAR_ID,
            "orbit_body_id": None,
            "epoch": 0,
            "surface_gravity":     CERES.get("gravity_g"),
            "escape_velocity_kms": CERES.get("escape_vel_kms"),
            "t_eq_k":              CERES.get("surface_temp_k"),
            **CERES,
        })
        cur = conn.execute(_INSERT_SQL, ceres_row)
        log.info("  Ceres (a=2.77 AU) body_id=%d", cur.lastrowid)

        conn.commit()
        log.info(
            "Done. %d planets, %d moons, 1 belt, 1 planetoid inserted for Sol (star_id=%d).",
            len(PLANETS), len(_MOON_DATA), SOL_STAR_ID,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
