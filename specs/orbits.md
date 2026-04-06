# Orbits

## Overview
For each multiple star system, generate Keplerian orbital elements for every companion star,
treating the most massive star as stationary. All six classical elements are stored, but
semi-major axis and eccentricity are the ones that matter most for gameplay. Positions at any
game time are computed on demand from the elements; no positions are stored in the database.

## Requirements
- Every companion `star_id` in a multiple system must have a row in `StarOrbits`.
- Primary stars (most massive per system) get no row — they are the reference frame.
- Identify the primary by `mass` from `DistinctStarsExtended`; fall back to `absmag` (lower =
  brighter = more massive on the main sequence) if `DistinctStarsExtended` is not yet populated.
  Abort with a clear error if neither is available for a system.
- Skip `star_id`s already present in `StarOrbits` (resume support).
- Commit every `--batch-size` systems (default 1000).
- Stop cleanly after `--max-minutes` elapsed wall-clock time (default 60); re-run to continue.
- `epoch` is always 0 (game start) for the initial generation run.

## Data / Schema

No changes to existing tables.

```sql
CREATE TABLE IF NOT EXISTS "StarOrbits" (
    "star_id"                  INTEGER PRIMARY KEY,  -- orbiting companion
    "primary_star_id"          INTEGER NOT NULL,     -- most massive star in system (stationary)
    "semi_major_axis"          REAL NOT NULL,        -- AU
    "eccentricity"             REAL NOT NULL,        -- [0, 1)
    "inclination"              REAL NOT NULL,        -- radians
    "longitude_ascending_node" REAL NOT NULL,        -- radians
    "argument_periapsis"       REAL NOT NULL,        -- radians
    "mean_anomaly"             REAL NOT NULL,        -- radians, defined at epoch
    "epoch"                    INTEGER NOT NULL DEFAULT 0  -- game time of mean_anomaly definition
)
```

Reference tables (read-only):
- `IndexedIntegerDistinctStars` — `system_id`, `star_id`, `spectral`
- `DistinctStarsExtended` — `star_id`, `mass`
- `IndexedIntegerDistinctSystems` — `system_id`, `x`, `y`, `z` (milliparsecs)

Position at game time `t`:
```
n    = 2π / orbital_period          # mean motion (game-time units must match period units)
M(t) = mean_anomaly + n * (t - epoch)
```
Solve Kepler's equation M = E − e·sin(E) for eccentric anomaly E, then convert to (x, y, z)
relative to the primary. Add the system's galactic position from `IndexedIntegerDistinctSystems`
to get absolute coordinates.

## Shared Code

`src/starscape5/orbits.py` — new module providing:
- `semi_major_axis_au(spectral_letter)` — log-normal draw (μ=log₁₀(50), σ=1.5 dex); O/B stars
  use μ=log₁₀(200) to reflect wider observed separations
- `thermal_eccentricity()` — draw from thermal distribution f(e)=2e: `e = sqrt(uniform(0, 1))`,
  capped at 0.97 to avoid near-parabolic orbits
- `random_angles()` → `(i, Ω, ω, M₀)` tuple; inclination from isotropic sphere
  (`i = arccos(uniform(-1, 1))`), the rest uniform on [0, 2π)
- `identify_primary(system_stars)` — given list of `(star_id, mass, absmag)`, return the
  `star_id` with highest mass (or lowest absmag as fallback)
- `generate_orbit(primary_star_id, spectral_letter, epoch=0)` → dict of all elements
- `hill_radius_au(neighbor_dist_mpc)` — primary's Hill sphere radius in AU, assuming equal
  neighbour mass: `r_H = dist_mpc * 206.265 * (1/3)^(1/3)`
- `enforce_stability(orbits, hill_au)` — given a list of orbit dicts (one per companion),
  sorted by `semi_major_axis`, apply two passes:
  1. Inter-companion: for each adjacent pair, ensure periapsis of outer > 3 × apoapsis of inner;
     if violated, expand `semi_major_axis` of outer to satisfy the constraint
  2. Hill sphere cap: reduce any `semi_major_axis` exceeding `hill_au` to `hill_au`

## Design / Logic

```
MILLIPARSEC_TO_AU = 206.265          // 1 mpc = 206.265 AU
HILL_MASS_FACTOR  = (1.0/3.0)^(1/3) // ~0.693; assumes equal neighbour mass
STABILITY_K       = 3.0              // periapsis of outer > K × apoapsis of inner

// --- Element distributions ---

function semi_major_axis_au(spectral_letter):
    mu = log10(200) if spectral_letter in ("O", "B") else log10(50)
    sigma = 1.5
    log_a = normal(mu, sigma)
    return max(0.01, 10 ^ log_a)            // floor at 0.01 AU

function thermal_eccentricity():
    return min(0.97, sqrt(uniform(0.0, 1.0)))

function random_angles():
    i  = arccos(uniform(-1.0, 1.0))        // isotropic inclination
    Ω  = uniform(0, 2π)
    ω  = uniform(0, 2π)
    M0 = uniform(0, 2π)
    return (i, Ω, ω, M0)

function identify_primary(stars):            // stars: list of (star_id, mass, absmag)
    // prefer mass; fall back to absmag (lower = brighter = more massive)
    if any mass is not NULL and mass > 0:
        return star_id with max(mass)
    if any absmag is not NULL:
        return star_id with min(absmag)
    raise OrbitsError("cannot identify primary: no mass or absmag")

function hill_radius_au(neighbor_dist_mpc):
    return neighbor_dist_mpc * MILLIPARSEC_TO_AU * HILL_MASS_FACTOR

function generate_orbit(primary_star_id, spectral_letter, epoch=0):
    a       = semi_major_axis_au(spectral_letter)
    e       = thermal_eccentricity()
    i, Ω, ω, M0 = random_angles()
    return {
        primary_star_id:          primary_star_id,
        semi_major_axis:          a,
        eccentricity:             e,
        inclination:              i,
        longitude_ascending_node: Ω,
        argument_periapsis:       ω,
        mean_anomaly:             M0,
        epoch:                    epoch,
    }

function enforce_stability(orbits, hill_au):
    // orbits: list of orbit dicts, sorted ascending by semi_major_axis
    // Pass 1: inter-companion separation (inside-out)
    for i in 1 .. len(orbits)-1:
        inner = orbits[i-1]
        outer = orbits[i]
        apoapsis_inner   = inner.a * (1 + inner.e)
        periapsis_outer  = outer.a * (1 - outer.e)
        if periapsis_outer < STABILITY_K * apoapsis_inner:
            // expand outer semi-major axis to satisfy criterion
            outer.a = STABILITY_K * apoapsis_inner / (1 - outer.e)

    // Pass 2: Hill sphere cap (outside-in so inner orbits are unaffected)
    for orbit in orbits:
        if orbit.a > hill_au:
            orbit.a = hill_au

    return orbits

// --- Main loop ---

OPEN database
deadline = now() + max_minutes * 60

// Pre-load all system positions for nearest-neighbour lookup (KDTree)
all_positions = SELECT system_id, x, y, z FROM IndexedIntegerDistinctSystems
kdtree = KDTree([(x, y, z) for each row])   // coordinates in milliparsecs

// Find all multiple systems not yet fully processed
systems = SELECT system_id FROM IndexedIntegerDistinctStars
          GROUP BY system_id HAVING COUNT(*) > 1
already_done = SELECT DISTINCT primary_star_id FROM StarOrbits
pending = [s for s in systems if primary not already in StarOrbits]

total = len(pending)
LOG "Found {total} multiple systems to process"

processed = 0
errors = 0

FOR each system in pending:

    if now() >= deadline:
        COMMIT
        LOG "Time limit reached after {processed} systems. Re-run to continue."
        EXIT 0

    TRY:
        // Load star data for this system
        stars = SELECT i.star_id, e.mass, i.absmag, i.spectral
                FROM IndexedIntegerDistinctStars i
                LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
                WHERE i.system_id = system.system_id

        primary_id = identify_primary(stars)

        // Nearest-neighbour Hill sphere limit
        sys_pos = position of system.system_id in all_positions
        nearest_dist_mpc = kdtree.query(sys_pos, k=2).second_result  // skip self
        hill_au = hill_radius_au(nearest_dist_mpc)

        // Generate all companion orbits first, then enforce stability together
        companions = [s for s in stars where s.star_id != primary_id
                                         and s.star_id not already in StarOrbits]
        orbits = []
        for each companion in companions:
            spectral_letter = first char of companion.spectral (default "G")
            orbit = generate_orbit(primary_id, spectral_letter, epoch=0)
            orbit.star_id = companion.star_id
            orbits.append(orbit)

        sort orbits by semi_major_axis ascending
        orbits = enforce_stability(orbits, hill_au)

        for orbit in orbits:
            INSERT INTO StarOrbits
                (star_id, primary_star_id, semi_major_axis, eccentricity,
                 inclination, longitude_ascending_node, argument_periapsis,
                 mean_anomaly, epoch)
                VALUES (orbit.star_id, orbit...)

    CATCH OrbitsError as err:
        LOG ERROR "system_id={system.system_id}: {err}"
        errors += 1

    processed += 1
    if processed % batch_size == 0:
        COMMIT
        LOG "Progress: {processed}/{total}, errors: {errors}"

COMMIT
LOG "Done. Processed {processed} systems, {errors} errors."
CLOSE database
```

## Scripts

`scripts/compute_orbits.py`

```
uv run scripts/compute_orbits.py
uv run scripts/compute_orbits.py --db /path/to/other.db
uv run scripts/compute_orbits.py --batch-size 500 --max-minutes 120
caffeinate -i uv run scripts/compute_orbits.py --max-minutes 600
```

Recommended run order:
1. `fill_spectral.py` — spectral types and companion stars must exist
2. `compute_metrics.py` — mass values needed for primary identification
3. `compute_orbits.py` — this script

## Tests

- `test_semi_major_axis_range` — 10,000 draws all fall within [0.01, 100,000] AU
- `test_semi_major_axis_ob_wider` — mean draw for O/B > mean draw for M (log scale)
- `test_thermal_eccentricity_range` — 10,000 draws all in [0, 0.97]
- `test_thermal_eccentricity_distribution` — median ≈ 0.71 (√0.5); skewed toward high e
- `test_random_angles_ranges` — i ∈ [0, π], Ω/ω/M₀ ∈ [0, 2π)
- `test_inclination_isotropic` — cos(i) is approximately uniform (K-S test or histogram check)
- `test_identify_primary_by_mass` — returns star with highest mass
- `test_identify_primary_fallback_absmag` — all mass=NULL, returns star with lowest absmag
- `test_identify_primary_no_data` — raises OrbitsError
- `test_generate_orbit_keys` — returned dict has all 8 expected keys
- `test_hill_radius_au` — 1 mpc → 206.265 × 0.693 ≈ 142.9 AU; 1000 mpc → 142,900 AU
- `test_enforce_stability_separation` — two companions where outer periapsis < 3 × inner
  apoapsis; after enforce_stability, outer.a is expanded to satisfy constraint
- `test_enforce_stability_hill_cap` — companion with a > hill_au is reduced to hill_au
- `test_enforce_stability_cascade` — three companions where adjusting middle also requires
  adjusting outer; verify all three satisfy the criterion after one call
- `test_enforce_stability_noop` — well-separated companions are unchanged
- Integration: seed small SQLite DB with a 2-star and a 3-star system; run script; verify
  StarOrbits has exactly 1 row for the binary and 2 rows for the triple, primary gets no row,
  all orbits satisfy the stability criterion, resume skips already-present rows, time limit
  exits cleanly

## Notes

- **Frame of reference**: all companions orbit the primary directly, even in triples. This is
  physically wrong for hierarchical systems (where inner pair + outer body is more stable) but
  avoids N-body complexity. Acceptable for this simulator.
- **Stability**: two constraints are enforced after orbit generation:
  1. *Inter-companion*: periapsis of each outer companion > 3 × apoapsis of the next inner one
     (applied inside-out so each adjustment is coherent). This uses a flat-orbit model — all
     companions orbit the primary — which is physically wrong for hierarchical triples but avoids
     N-body complexity.
  2. *Hill sphere cap*: semi-major axis capped at `d_nearest × 206.265 × (1/3)^(1/3)` AU,
     assuming equal neighbour mass. In very crowded regions, the cap may squeeze multiple
     companions together; a second stability pass is not performed in that case — log and accept.
- **KDTree performance**: all system positions are loaded into memory at startup for O(log n)
  nearest-neighbour queries. At ~1.8 M systems × 3 integers this is ~20 MB — acceptable.
- **Units**: `semi_major_axis` in AU; angles in radians; galactic positions in
  `IndexedIntegerDistinctSystems` are in milliparsecs (integer).
- **Epoch**: always 0 (game start) on initial generation. If an orbit is updated mid-game,
  write the current game time as `epoch` and the current `mean_anomaly` together atomically.
- **Period**: not stored — compute as `T = 2π * sqrt(a³ / (G·M_primary))` in game code.
  Requires converting AU and M☉ to whatever time units the game uses.
- Same large DB pattern as other scripts — run overnight with `--max-minutes 60` in successive
  sessions if needed.
- Back up before first run: `sqlite3 starscape.db ".backup starscape.db.bak"`
