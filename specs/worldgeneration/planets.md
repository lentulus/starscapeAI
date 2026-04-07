# Planets and Moons

## Overview
For every star in `IndexedIntegerDistinctStars`, generate a system of planets and, for each
planet, zero or more moons. Physical properties (mass, radius) are drawn from empirical
distributions. Orbital elements use the same Keplerian model as `StarOrbits`. All bodies are
stored in the `Bodies` table. Runs once as a pre-simulation world-building step.

## Requirements
- Every star in `IndexedIntegerDistinctStars` is processed; stars that already have planets in
  `Bodies` are skipped (resume support).
- Planet count per star drawn from a distribution conditioned on spectral class.
- Planet mass drawn from a log-normal distribution; radius estimated from a mass-radius relation.
- Each planet gets a moon count drawn from a distribution conditioned on planet mass.
- Moon mass and radius drawn from distributions scaled to their parent planet.
- Orbital elements for both planets and moons use the same element generators as `orbits.py`
  (`thermal_eccentricity`, `random_angles`). Semi-major axis uses a separate planetary
  distribution (not the stellar-companion log-normal).
- Stability enforcement: planetary orbits must satisfy the same inter-body separation criterion
  used in `orbits.py` (periapsis of outer > 3 × apoapsis of inner), applied inside-out.
- **Binary/multiple system awareness:** before generating planets for any star, look up
  `StarOrbits` to determine the S-type stable zone:
  - *Primary stars* (have companions): planet `semi_major_axis` capped at `0.3 × min(companion a)`
  - *Companion stars* (have their own orbit): planet `semi_major_axis` capped at `0.3 × own a`
  - *Single stars* (not in `StarOrbits`): cap is the default 50 AU
  - Stars whose stable zone is < 0.05 AU are skipped entirely (no stable planet zone exists).
- Each planet is flagged `possible_tidal_lock = 1` if its semi-major axis is less than
  `0.5 × √L` AU (inside the inner half of the HZ inner edge); all moons are flagged 1
  (all generated moons orbit close enough to their parent to qualify).
- After planets and moons are placed, up to two asteroid belts are generated per star via
  `belt_positions()`: an inner rocky belt (P=0.55) in any qualifying gap before the first
  giant, and an outer icy belt (P=0.35) beyond the outermost planet.  When no giant is
  present, a single isolated belt is possible (P=0.20).  Belts and their planetoids are
  stored in `Bodies` with `body_type='belt'` or `'planetoid'`; `possible_tidal_lock` is NULL
  for both.  Each belt spawns 0–5 significant planetoids drawn from a Dohnanyi Pareto mass
  distribution (α=1.83, m_min=10⁻⁴ Mₑ).
- Commit every `--batch-size` stars (default 500).
- Stop cleanly after `--max-minutes` elapsed wall-clock time (default 60); re-run to continue.

## Data / Schema
New table — see `sql/schema.sql`.

```sql
CREATE TABLE IF NOT EXISTS "Bodies" (
    "body_id"          INTEGER PRIMARY KEY,
    "body_type"        TEXT    NOT NULL CHECK(body_type IN ('planet','moon','belt','planetoid')),
    "mass"             REAL,    -- Earth masses (Mₑ)
    "radius"           REAL,    -- Earth radii (Rₑ)
    "orbit_star_id"    INTEGER REFERENCES "IndexedIntegerDistinctStars"("star_id"),
    "orbit_body_id"    INTEGER REFERENCES "Bodies"("body_id"),
    "semi_major_axis"  REAL    NOT NULL,  -- AU
    "eccentricity"     REAL    NOT NULL,
    "inclination"      REAL    NOT NULL,  -- radians
    "longitude_ascending_node" REAL NOT NULL,  -- radians
    "argument_periapsis"       REAL NOT NULL,  -- radians
    "mean_anomaly"     REAL    NOT NULL,  -- radians at epoch
    "epoch"            INTEGER NOT NULL DEFAULT 0,
    "in_hz"            INTEGER,  -- 1/0 for planets & planetoids; NULL for moons
    "possible_tidal_lock" INTEGER, -- 1/0 for planets/moons; NULL for belts/planetoids
    CHECK (
        (orbit_star_id IS NOT NULL AND orbit_body_id IS NULL) OR
        (orbit_star_id IS NULL     AND orbit_body_id IS NOT NULL)
    )
)
```

## Shared Code
`src/starscape5/planets.py` — new module providing:
- `planet_count(spectral_letter)` — draw planet count: Poisson(λ) conditioned on class;
  O/B λ=2, A/F λ=4, G/K λ=6, M λ=3
- `planet_mass_earth()` — log-normal draw: μ=log₁₀(1), σ=1.5 dex; floor 0.01 Mₑ
- `radius_from_mass(mass_earth)` — empirical broken power law:
  M < 1.6 Mₑ: R = M^0.55 (rocky); M < 120 Mₑ: R = M^0.01 * 1.0 (transition plateau);
  M ≥ 120 Mₑ: R = (M/318)^0.55 * 11.2 (gas giant scaling to Jupiter)
- `planet_semi_major_axis_au(star_luminosity)` — log-uniform draw within habitable-zone-anchored
  range [0.01, 50] AU; log-normal μ = log₁₀(sqrt(star_luminosity)) (habitable zone centre)
- `hz_bounds(star_luminosity)` — returns (inner_au, outer_au) = (0.95√L, 1.67√L)
- `moon_count(planet_mass_earth)` — Poisson(λ): λ=0 for M<0.1, λ=1 for 0.1–10, λ=3 for >10
- `moon_mass_earth(planet_mass_earth)` — log-uniform in [1e-5, planet_mass * 0.01]
- `generate_planet(star_id, star_luminosity)` → dict of all planet fields (including `in_hz`,
  `possible_tidal_lock`)
- `generate_moon(planet_body_id, planet_mass_earth)` → dict; `possible_tidal_lock=1` always
- `belt_positions(sorted_planets, star_luminosity)` → list of (center_au, ecc) for belt placement
- `belt_mass_earth()` — log-normal μ=−3 dex, σ=1.0 dex, clamped to [1e-6, 0.10] Mₑ
- `planetoid_count()` — Poisson(2), max 5
- `planetoid_mass_pareto(belt_mass)` — Dohnanyi Pareto draw, α=1.83, capped at min(0.01 Mₑ,
  0.5 × belt_mass)
- `planetoid_semi_major_axis_au(belt_center_au, belt_ecc)` — uniform in belt zone
- `generate_belt(star_id, center_au, ecc, mass, hz_inner, hz_outer)` → dict
- `generate_planetoid(star_id, belt_center_au, belt_ecc, belt_mass, hz_inner, hz_outer)` → dict

Reuses from `src/starscape5/orbits.py`:
- `thermal_eccentricity()`
- `random_angles()`
- `enforce_stability(orbits, hill_au)`

## Design / Logic

```
// --- Distributions ---

function planet_count(spectral_letter):
    lambda = { O:2, B:2, A:4, F:4, G:6, K:6, M:3 }.get(spectral_letter, 4)
    return poisson(lambda)

function planet_mass_earth():
    log_m = normal(0, 1.5)          // μ = log10(1 Mₑ)
    return max(0.01, 10 ^ log_m)

function radius_from_mass(mass_earth):
    if mass_earth < 1.6:
        return mass_earth ^ 0.55
    elif mass_earth < 120:
        return 1.0 + (mass_earth - 1.6) * 0.01   // slow growth through transition
    else:
        return (mass_earth / 318) ^ 0.55 * 11.2   // gas giant

function planet_semi_major_axis_au(star_luminosity):
    hz_centre = sqrt(star_luminosity)              // in AU (L=1 → 1 AU)
    mu = log10(hz_centre)
    log_a = normal(mu, 1.0)
    return clamp(10 ^ log_a, 0.01, 50.0)

function moon_count(planet_mass_earth):
    if planet_mass_earth < 0.1:  return 0
    if planet_mass_earth < 10:   return poisson(1)
    return poisson(3)

function moon_mass_earth(planet_mass_earth):
    return uniform(1e-5, planet_mass_earth * 0.01)

// --- Per-body generation ---

function generate_planet(star_id, star_luminosity):
    mass   = planet_mass_earth()
    radius = radius_from_mass(mass)
    a      = planet_semi_major_axis_au(star_luminosity)
    e      = thermal_eccentricity()
    i, Ω, ω, M0 = random_angles()
    hz_inner, hz_outer = hz_bounds(star_luminosity)
    return { body_type:'planet', mass, radius, orbit_star_id:star_id,
             semi_major_axis:a, eccentricity:e, inclination:i,
             longitude_ascending_node:Ω, argument_periapsis:ω,
             mean_anomaly:M0, epoch:0,
             in_hz: 1 if hz_inner <= a <= hz_outer else 0,
             possible_tidal_lock: 1 if a < 0.5*sqrt(star_luminosity) else 0 }

function generate_moon(planet_body_id, planet_mass_earth):
    mass   = moon_mass_earth(planet_mass_earth)
    radius = radius_from_mass(mass)
    // Moon semi-major axis: Hill sphere fraction; Hill ~ 200 * (mass/3)^(1/3) Rₑ converted to AU
    hill_au = planet_mass_earth ^ (1/3) * 0.01    // rough scaling
    a = uniform(0.001, hill_au * 0.5)
    e = thermal_eccentricity()
    i, Ω, ω, M0 = random_angles()
    return { body_type:'moon', mass, radius, orbit_body_id:planet_body_id,
             semi_major_axis:a, eccentricity:e, inclination:i,
             longitude_ascending_node:Ω, argument_periapsis:ω,
             mean_anomaly:M0, epoch:0,
             in_hz: NULL, possible_tidal_lock: 1 }

// --- Main loop ---

OPEN database
deadline = now() + max_minutes * 60

// Stars not yet having any planet
pending = SELECT i.star_id, i.spectral, e.luminosity
          FROM IndexedIntegerDistinctStars i
          LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
          WHERE i.star_id NOT IN (SELECT DISTINCT orbit_star_id FROM Bodies
                                  WHERE orbit_star_id IS NOT NULL)
          ORDER BY i.star_id

total = len(pending)
LOG "Found {total} stars to process"

processed = 0

FOR each star in pending:

    if now() >= deadline:
        COMMIT
        LOG "Time limit reached after {processed} stars. Re-run to continue."
        EXIT 0

    spectral_letter = first char of star.spectral (default 'G')
    lum = star.luminosity if not NULL else 1.0    // default to solar

    stable_cap_au = binary_cap.get(star.star_id, 50.0)
    if stable_cap_au < 0.05:
        LOG DEBUG "star_id={star.star_id}: stable zone {stable_cap_au} AU too small, skipping"
        continue  // no stable planet zone

    n_planets = planet_count(spectral_letter)
    planets = []
    for _ in range(n_planets):
        p = generate_planet(star.star_id, lum)
        planets.append(p)

    sort planets by semi_major_axis ascending
    planets = enforce_stability(planets, stable_cap_au)   // use binary-aware cap

    for planet in planets:
        INSERT INTO Bodies (...) VALUES (...)
        planet_body_id = last inserted rowid

        n_moons = moon_count(planet.mass)
        moons = [generate_moon(planet_body_id, planet.mass) for _ in range(n_moons)]
        sort moons by semi_major_axis ascending
        moons = enforce_stability(moons, hill_au = planet.mass^(1/3) * 0.01 * 0.5)
        for moon in moons:
            INSERT INTO Bodies (...) VALUES (...)

    // --- Belts and planetoids ---
    hz_inner, hz_outer = hz_bounds(lum)
    for (center_au, belt_ecc) in belt_positions(planets, lum):
        if center_au > stable_cap_au: continue
        bmass = belt_mass_earth()
        INSERT belt row via generate_belt(star_id, center_au, belt_ecc, bmass, hz_inner, hz_outer)
        for _ in range(planetoid_count()):
            INSERT planetoid row via generate_planetoid(star_id, center_au, belt_ecc, bmass,
                                                        hz_inner, hz_outer)

    processed += 1
    if processed % batch_size == 0:
        COMMIT
        LOG "Progress: {processed}/{total}"

COMMIT
LOG "Done. {processed} stars processed."
CLOSE database
```

## Scripts
`scripts/generate_planets.py`

```
uv run scripts/generate_planets.py
uv run scripts/generate_planets.py --db /path/to/other.db
uv run scripts/generate_planets.py --batch-size 200 --max-minutes 120
caffeinate -i uv run scripts/generate_planets.py --max-minutes 600
```

Recommended run order:
1. `fill_spectral.py`
2. `compute_metrics.py` — luminosity values needed for HZ-anchored semi-major axis
3. `compute_orbits.py`
4. `seed_sol.py` — insert real solar system for star_id=1 (Sol); must run before step 5
5. `generate_planets.py` — generates all other stars; skips star_id=1 (already seeded)

## Tests
- `test_planet_count_range` — 1000 draws per class; mean within 1σ of expected λ
- `test_planet_mass_floor` — no draw below 0.01 Mₑ
- `test_radius_from_mass_rocky` — 1.0 Mₑ → 1.0 Rₑ
- `test_radius_from_mass_giant` — 318 Mₑ (Jupiter) → ~11.2 Rₑ
- `test_planet_sma_range` — all draws in [0.01, 50] AU
- `test_moon_count_zero_for_small` — planet < 0.1 Mₑ always yields 0 moons
- `test_moon_mass_bounded` — moon mass always < 1% of planet mass
- `test_enforce_stability_applied` — two planets violating separation criterion are corrected
- Integration: seed small DB with 5 stars; run script; verify Bodies populated, resume skips
  already-processed stars, time limit exits cleanly

## Notes
- Luminosity fallback to 1.0 L☉ when `DistinctStarsExtended` is unpopulated — acceptable for
  testing; run `compute_metrics.py` first in production.
- `enforce_stability` is imported from `orbits.py`; planet hill cap is hardcoded at 50 AU.
- Moon Hill sphere estimate is intentionally rough — detailed moon stability is not a priority
  at this stage.
- At ~2.47M stars × avg 4 planets × avg 1 moon ≈ 12M rows in `Bodies` — SQLite handles this
  comfortably with WAL mode; index on `orbit_star_id` recommended after bulk load.
- **Binary systems:** S-type stability fraction is 0.3 (conservative; literature suggests 0.2–0.5).
  P-type circumbinary planets are not generated. Companion stars in very tight binaries (< 0.17 AU
  separation) will be skipped entirely.
- Back up before first run: `sqlite3 starscape.db ".backup starscape.db.bak"`
