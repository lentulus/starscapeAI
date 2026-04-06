"""Tests for src/starscape5/orbits.py and the compute_orbits script."""

import math
import sqlite3
import sys
from pathlib import Path

import pytest

from starscape5.orbits import (
    OrbitsError,
    MILLIPARSEC_TO_AU,
    enforce_stability,
    generate_orbit,
    hill_radius_au,
    identify_primary,
    random_angles,
    semi_major_axis_au,
    thermal_eccentricity,
)

# ---------------------------------------------------------------------------
# semi_major_axis_au
# ---------------------------------------------------------------------------

def test_semi_major_axis_range():
    results = [semi_major_axis_au("G") for _ in range(1000)]
    assert all(0.01 <= a for a in results), "semi-major axis below floor"


def test_semi_major_axis_ob_wider():
    ob_draws = [semi_major_axis_au("O") for _ in range(2000)]
    m_draws = [semi_major_axis_au("M") for _ in range(2000)]
    ob_log_mean = sum(math.log10(a) for a in ob_draws) / len(ob_draws)
    m_log_mean = sum(math.log10(a) for a in m_draws) / len(m_draws)
    assert ob_log_mean > m_log_mean, "O/B systems should have wider orbits on average"


# ---------------------------------------------------------------------------
# thermal_eccentricity
# ---------------------------------------------------------------------------

def test_thermal_eccentricity_range():
    results = [thermal_eccentricity() for _ in range(1000)]
    assert all(0.0 <= e <= 0.97 for e in results)


def test_thermal_eccentricity_distribution():
    results = [thermal_eccentricity() for _ in range(10_000)]
    median = sorted(results)[len(results) // 2]
    # theoretical median of sqrt(uniform) = sqrt(0.5) ≈ 0.707; allow ±0.05
    assert abs(median - math.sqrt(0.5)) < 0.05, f"median {median:.3f} out of range"


# ---------------------------------------------------------------------------
# random_angles
# ---------------------------------------------------------------------------

def test_random_angles_ranges():
    two_pi = 2.0 * math.pi
    for _ in range(500):
        i, Omega, omega, M0 = random_angles()
        assert 0.0 <= i <= math.pi, f"inclination {i} out of [0, π]"
        assert 0.0 <= Omega < two_pi
        assert 0.0 <= omega < two_pi
        assert 0.0 <= M0 < two_pi


def test_inclination_isotropic():
    # cos(i) should be approximately uniform on [-1, 1]
    samples = [random_angles()[0] for _ in range(4000)]
    cos_vals = [math.cos(i) for i in samples]
    # Split into 4 equal-width bins of cos(i): [-1,-0.5), [-0.5,0), [0,0.5), [0.5,1]
    bins = [0, 0, 0, 0]
    for c in cos_vals:
        idx = min(3, int((c + 1.0) / 0.5))
        bins[idx] += 1
    # Each bin should have roughly 25% ± 5%
    for count in bins:
        assert abs(count / len(samples) - 0.25) < 0.05, \
            f"Inclination not isotropic: bin counts {bins}"


# ---------------------------------------------------------------------------
# identify_primary
# ---------------------------------------------------------------------------

def test_identify_primary_by_mass():
    stars = [
        {"star_id": 1, "mass": 0.5, "absmag": 6.0},
        {"star_id": 2, "mass": 2.0, "absmag": 2.0},
        {"star_id": 3, "mass": 1.0, "absmag": 4.0},
    ]
    assert identify_primary(stars) == 2


def test_identify_primary_fallback_absmag():
    stars = [
        {"star_id": 1, "mass": None, "absmag": 6.0},
        {"star_id": 2, "mass": None, "absmag": 2.0},  # brightest → most massive
        {"star_id": 3, "mass": None, "absmag": 4.0},
    ]
    assert identify_primary(stars) == 2


def test_identify_primary_ignores_zero_mass():
    # mass=0 or negative should fall through to absmag
    stars = [
        {"star_id": 1, "mass": 0.0,  "absmag": 6.0},
        {"star_id": 2, "mass": -1.0, "absmag": 2.0},
    ]
    assert identify_primary(stars) == 2


def test_identify_primary_no_data():
    stars = [
        {"star_id": 1, "mass": None, "absmag": None},
        {"star_id": 2, "mass": None, "absmag": None},
    ]
    with pytest.raises(OrbitsError):
        identify_primary(stars)


# ---------------------------------------------------------------------------
# hill_radius_au
# ---------------------------------------------------------------------------

def test_hill_radius_au_known_value():
    # 1 mpc → 206.265 * (1/3)^(1/3) ≈ 142.9 AU
    expected = 1.0 * MILLIPARSEC_TO_AU * (1.0 / 3.0) ** (1.0 / 3.0)
    assert abs(hill_radius_au(1.0) - expected) < 0.01


def test_hill_radius_au_scales_linearly():
    assert abs(hill_radius_au(1000.0) / hill_radius_au(1.0) - 1000.0) < 0.001


# ---------------------------------------------------------------------------
# generate_orbit
# ---------------------------------------------------------------------------

def test_generate_orbit_keys():
    orbit = generate_orbit(primary_star_id=42, spectral_letter="G")
    expected_keys = {
        "primary_star_id", "semi_major_axis", "eccentricity",
        "inclination", "longitude_ascending_node", "argument_periapsis",
        "mean_anomaly", "epoch",
    }
    assert set(orbit.keys()) == expected_keys


def test_generate_orbit_primary_and_epoch():
    orbit = generate_orbit(primary_star_id=7, spectral_letter="K", epoch=0)
    assert orbit["primary_star_id"] == 7
    assert orbit["epoch"] == 0


def test_generate_orbit_values_in_range():
    two_pi = 2.0 * math.pi
    for _ in range(200):
        orbit = generate_orbit(99, "F")
        assert orbit["semi_major_axis"] >= 0.01
        assert 0.0 <= orbit["eccentricity"] <= 0.97
        assert 0.0 <= orbit["inclination"] <= math.pi
        assert 0.0 <= orbit["longitude_ascending_node"] < two_pi
        assert 0.0 <= orbit["argument_periapsis"] < two_pi
        assert 0.0 <= orbit["mean_anomaly"] < two_pi


# ---------------------------------------------------------------------------
# enforce_stability
# ---------------------------------------------------------------------------

def _make_orbit(a: float, e: float) -> dict:
    return {
        "star_id": 0,
        "primary_star_id": 1,
        "semi_major_axis": a,
        "eccentricity": e,
        "inclination": 0.0,
        "longitude_ascending_node": 0.0,
        "argument_periapsis": 0.0,
        "mean_anomaly": 0.0,
        "epoch": 0,
    }


def test_enforce_stability_noop():
    # Well-separated orbits should not be modified
    inner = _make_orbit(1.0, 0.0)   # apoapsis = 1.0 AU
    outer = _make_orbit(10.0, 0.0)  # periapsis = 10.0 AU  (> 3×1.0)
    result = enforce_stability([inner, outer], hill_au=1_000.0)
    assert result[0]["semi_major_axis"] == pytest.approx(1.0)
    assert result[1]["semi_major_axis"] == pytest.approx(10.0)


def test_enforce_stability_separation():
    # outer periapsis = 2*0.8 = 1.6 AU, inner apoapsis = 1*1.2 = 1.2 AU → 1.6 < 3×1.2=3.6
    inner = _make_orbit(1.0, 0.2)   # apoapsis = 1.2 AU
    outer = _make_orbit(2.0, 0.2)   # periapsis = 1.6 AU → too close
    enforce_stability([inner, outer], hill_au=1_000.0)
    periapsis_outer = outer["semi_major_axis"] * (1.0 - outer["eccentricity"])
    apoapsis_inner = inner["semi_major_axis"] * (1.0 + inner["eccentricity"])
    assert periapsis_outer >= 3.0 * apoapsis_inner - 1e-9


def test_enforce_stability_hill_cap():
    orbit = _make_orbit(5_000.0, 0.1)
    enforce_stability([orbit], hill_au=500.0)
    assert orbit["semi_major_axis"] == pytest.approx(500.0)


def test_enforce_stability_cascade():
    # Three companions where expanding middle also requires expanding outer
    c1 = _make_orbit(1.0, 0.0)   # apoapsis = 1 AU
    c2 = _make_orbit(2.0, 0.0)   # initially violates c1 (periapsis 2 < 3×1=3) → expands to 3
    c3 = _make_orbit(4.0, 0.0)   # after c2 expands to a=3, c3 periapsis 4 < 3×3=9 → also expands
    enforce_stability([c1, c2, c3], hill_au=1_000.0)
    for idx in range(1, 3):
        inner = [c1, c2, c3][idx - 1]
        outer = [c1, c2, c3][idx]
        assert (outer["semi_major_axis"] * (1 - outer["eccentricity"])
                >= 3.0 * inner["semi_major_axis"] * (1 + inner["eccentricity"]) - 1e-9)


# ---------------------------------------------------------------------------
# Integration: run against a small in-memory SQLite database
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IndexedIntegerDistinctStars (
    system_id INTEGER, star_id INTEGER, hip TEXT,
    ci TEXT, absmag REAL, spectral TEXT, source TEXT
);
CREATE TABLE DistinctStarsExtended (
    star_id INTEGER PRIMARY KEY, mass REAL, temperature REAL,
    radius REAL, luminosity REAL, age REAL
);
CREATE TABLE IndexedIntegerDistinctSystems (
    system_id INTEGER, x INTEGER, y INTEGER, z INTEGER
);
CREATE TABLE StarOrbits (
    star_id INTEGER PRIMARY KEY,
    primary_star_id INTEGER NOT NULL,
    semi_major_axis REAL NOT NULL,
    eccentricity REAL NOT NULL,
    inclination REAL NOT NULL,
    longitude_ascending_node REAL NOT NULL,
    argument_periapsis REAL NOT NULL,
    mean_anomaly REAL NOT NULL,
    epoch INTEGER NOT NULL DEFAULT 0
);
"""


def _seed_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # System 1: binary (stars 1 and 2)
    conn.executemany(
        "INSERT INTO IndexedIntegerDistinctStars VALUES (?,?,?,?,?,?,?)",
        [
            (1, 1, None, "0.65", 4.83, "G2V", "catalog"),
            (1, 2, None, "1.20", 8.0,  "M3V", "catalog"),
        ],
    )
    # System 2: triple (stars 3, 4, 5)
    conn.executemany(
        "INSERT INTO IndexedIntegerDistinctStars VALUES (?,?,?,?,?,?,?)",
        [
            (2, 3, None, "0.00", 2.0,  "A0V", "catalog"),
            (2, 4, None, "0.65", 4.83, "G2V", "catalog"),
            (2, 5, None, "1.20", 8.0,  "M3V", "catalog"),
        ],
    )
    # Masses
    conn.executemany(
        "INSERT INTO DistinctStarsExtended (star_id, mass) VALUES (?,?)",
        [(1, 1.0), (2, 0.3), (3, 2.5), (4, 1.0), (5, 0.3)],
    )
    # System positions (milliparsecs) — far apart so Hill sphere is generous
    conn.executemany(
        "INSERT INTO IndexedIntegerDistinctSystems VALUES (?,?,?,?)",
        [(1, 0, 0, 0), (2, 1000, 0, 0)],
    )
    conn.commit()


def _run_script(db_path: Path) -> None:
    """Invoke the script's main() directly against a file-backed DB."""
    import importlib.util, sys
    script = Path(__file__).parent.parent / "scripts" / "compute_orbits.py"
    spec = importlib.util.spec_from_file_location("compute_orbits", script)
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["compute_orbits.py", "--db", str(db_path)]
    spec.loader.exec_module(mod)
    mod.main()


def test_integration_orbit_counts(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed_db(conn)
    conn.close()

    _run_script(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT * FROM StarOrbits").fetchall()
    # binary: 1 companion; triple: 2 companions → 3 total
    assert len(rows) == 3, f"Expected 3 orbit rows, got {len(rows)}"

    star_ids = {r["star_id"] for r in rows}
    # Primaries (1 and 3) must not appear as companions
    assert 1 not in star_ids
    assert 3 not in star_ids
    # Companions must be present
    assert {2, 4, 5} == star_ids

    conn.close()


def test_integration_resume_skips(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed_db(conn)
    conn.close()

    _run_script(db_path)  # first run

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Record semi_major_axis values after first run
    first_values = {
        r["star_id"]: r["semi_major_axis"]
        for r in conn.execute("SELECT star_id, semi_major_axis FROM StarOrbits").fetchall()
    }
    conn.close()

    _run_script(db_path)  # second run — should be a no-op

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    second_values = {
        r["star_id"]: r["semi_major_axis"]
        for r in conn.execute("SELECT star_id, semi_major_axis FROM StarOrbits").fetchall()
    }
    conn.close()

    assert first_values == second_values, "Resume run should not alter existing orbits"


def test_integration_stability_satisfied(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    _seed_db(conn)
    conn.close()

    _run_script(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # For the triple system (primary=3), check companions 4 and 5 are stable
    triple_orbits = conn.execute(
        "SELECT semi_major_axis, eccentricity FROM StarOrbits"
        " WHERE primary_star_id = 3 ORDER BY semi_major_axis"
    ).fetchall()
    conn.close()

    assert len(triple_orbits) == 2
    inner, outer = triple_orbits
    apoapsis_inner = inner["semi_major_axis"] * (1 + inner["eccentricity"])
    periapsis_outer = outer["semi_major_axis"] * (1 - outer["eccentricity"])
    assert periapsis_outer >= 3.0 * apoapsis_inner - 1e-6, \
        f"Triple system orbits violate stability: periapsis_outer={periapsis_outer:.2f}, " \
        f"3×apoapsis_inner={3*apoapsis_inner:.2f}"
