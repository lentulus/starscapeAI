# Compute Stellar Metrics

## Overview
Derives physical stellar parameters (mass, temperature, radius, luminosity, age) for every star
in `IndexedIntegerDistinctStars` and writes them to `DistinctStarsExtended`. Inputs are B-V
color index (`ci`) and absolute visual magnitude (`absmag`); spectral type is used as a
cross-check. All values are rounded to 3 significant figures. Units: mass in M☉, temperature in
K, radius in R☉, luminosity in L☉, age in years.

## Requirements
- Every `star_id` in `IndexedIntegerDistinctStars` must have a row in `DistinctStarsExtended`.
- If a metric cannot be calculated (missing inputs, unphysical result), insert the row with
  `mass = -1` and log `star_id` plus reason; do not abort the run.
- On re-run, rows with `mass = -1` (previous failures) are retried alongside missing rows; use
  `INSERT OR REPLACE` to overwrite the error sentinel if computation now succeeds.
- Skip rows already present in `DistinctStarsExtended` with `mass != -1` (resume support).
- If `temperature_from_bv` yields a non-positive result (pathological B-V), or ci is absent, fall back in order to: spectral type interpolation via `temperature_from_spectral`, then mass-based estimate (`5778 × M^0.505`).
- Commit every `--batch-size` rows (default 1000).
- Stop cleanly after `--max-minutes` elapsed wall-clock time (default 60); progress is preserved
  and the next run resumes where it left off.

## Data / Schema
No new tables. `DistinctStarsExtended` already exists in the target DB.

```sql
CREATE TABLE "DistinctStarsExtended" (
    "star_id"      INTEGER,
    "mass"         REAL,    -- solar masses; -1 signals error
    "temperature"  REAL,    -- Kelvin
    "radius"       REAL,    -- solar radii
    "luminosity"   REAL,    -- solar luminosities
    "age"          REAL,    -- years
    "temp_source"  TEXT,    -- temperature provenance: 'bv', 'spectral:<type>', 'mass_est', or NULL on error
    PRIMARY KEY("star_id")
)
```

## Shared Code
`src/starscape5/metrics.py` — new module providing:
- `temperature_from_bv(bv)` — Ballesteros (2012) formula: T = 4600 × (1/(0.92·BV+1.7) + 1/(0.92·BV+0.62))
- `temperature_from_spectral(spectral)` — linear interpolation of T by class letter (O–M) and subtype digit (0–9); returns None if unparseable
- `luminosity_from_absmag(absmag)` — L/L☉ = 10^((4.83 − Mv) / 2.5)
- `radius_from_lum_temp(lum, temp)` — Stefan-Boltzmann: R/R☉ = √L × (5778/T)²
- `mass_from_luminosity(lum)` — piecewise MS mass-luminosity relation (see Design)
- `age_from_mass_lum(mass, lum)` — MS lifetime: t ≈ 10¹⁰ × M/L years
- `compute_metrics(ci, absmag, spectral=None)` — orchestrates the above; returns dict or raises `MetricsError`
- `sig3(x)` — round to 3 significant figures

## Design / Logic

```
// --- Physical relations ---

function temperature_from_bv(bv):
    // Ballesteros (2012) — valid ~O through M on main sequence
    return 4600 * (1/(0.92*bv + 1.7) + 1/(0.92*bv + 0.62))

function temperature_from_spectral(spectral):
    // Map class letter to (T at subtype 0, T at subtype 9)
    table = { O:(50000,32000), B:(30000,10500), A:(9750,7440),
              F:(7220,6160),   G:(5920,5340),   K:(5270,3910), M:(3850,2400) }
    cls = first letter of spectral (uppercase)
    if cls not in table: return NULL
    subtype = first digit after cls, or 5 if absent
    t0, t9 = table[cls]
    return t0 + (t9 - t0) * subtype / 9

function luminosity_from_absmag(absmag):
    // M_sun = 4.83
    return 10 ^ ((4.83 - absmag) / 2.5)

function radius_from_lum_temp(lum, temp):
    // Stefan-Boltzmann: L = 4πR²σT⁴  →  R/R_sun = sqrt(L) * (T_sun/T)²
    return sqrt(lum) * (5778 / temp) ^ 2

function mass_from_luminosity(lum):
    // Piecewise MS mass-luminosity (Duric 2004)
    // Invert: given L find M
    if lum < 0.033:                       // M < 0.43 M_sun: L = 0.23 * M^2.3
        return (lum / 0.23) ^ (1/2.3)
    elif lum < 16:                        // 0.43–2 M_sun:   L = M^4
        return lum ^ 0.25
    elif lum < 72000:                     // 2–55 M_sun:     L = 1.4 * M^3.5
        return (lum / 1.4) ^ (1/3.5)
    else:                                 // > 55 M_sun:     L = 32000 * M
        return lum / 32000

function age_from_mass_lum(mass, lum):
    // Main-sequence lifetime; giants are already past this — treat as lower bound
    return 1e10 * mass / lum             // years

function sig3(x):
    if x == 0: return 0
    magnitude = floor(log10(abs(x)))
    return round(x, -magnitude + 2)

// --- Per-star computation ---

function compute_metrics(ci, absmag, spectral):
    if ci is NULL and absmag is NULL:
        raise MetricsError("no ci or absmag")

    if absmag is NULL:
        raise MetricsError("absmag required for luminosity")

    lum  = luminosity_from_absmag(absmag)

    // Temperature fallback chain: B-V → spectral type → mass-based estimate
    if ci is not NULL:
        temp = temperature_from_bv(float(ci))
        temp_source = 'bv'
    else:
        temp = 0
        temp_source = NULL

    if temp <= 0 and spectral is not NULL:
        temp = temperature_from_spectral(spectral) or 0
        if temp > 0: temp_source = 'spectral:' + spectral

    if temp <= 0:
        // Last resort: rough MS fit from luminosity
        mass_est = mass_from_luminosity(lum)
        temp = 5778 * mass_est ^ 0.505
        temp_source = 'mass_est'

    radius = radius_from_lum_temp(lum, temp)
    mass   = mass_from_luminosity(lum)
    age    = age_from_mass_lum(mass, lum)

    return {
        mass:        sig3(mass),
        temperature: sig3(temp),
        temp_source: temp_source,   // 'bv' | 'spectral:<type>' | 'mass_est'
        radius:      sig3(radius),
        luminosity:  sig3(lum),
        age:         sig3(age),
    }

// --- Main loop ---

OPEN database
deadline = now() + max_minutes * 60

// Identify work: stars not yet in DistinctStarsExtended, or previous failures (mass = -1)
pending = SELECT i.star_id, i.ci, i.absmag, i.spectral
          FROM IndexedIntegerDistinctStars i
          LEFT JOIN DistinctStarsExtended e ON i.star_id = e.star_id
          WHERE e.star_id IS NULL OR e.mass = -1
          ORDER BY i.star_id

total = len(pending)
LOG "Found {total} stars to process"

processed = 0
errors = 0

FOR each (star_id, ci, absmag, spectral) in pending:

    if now() >= deadline:
        COMMIT
        LOG "Time limit reached after {processed} rows. Resume to continue."
        EXIT 0

    TRY:
        m = compute_metrics(ci, absmag, spectral)
        INSERT OR REPLACE INTO DistinctStarsExtended
            (star_id, mass, temperature, radius, luminosity, age, temp_source)
            VALUES (star_id, m.mass, m.temperature, m.radius, m.luminosity, m.age, m.temp_source)
    CATCH MetricsError as e:
        LOG ERROR "star_id={star_id} ci={ci} spectral={spectral}: {e}"
        INSERT OR REPLACE INTO DistinctStarsExtended
            (star_id, mass, temperature, radius, luminosity, age, temp_source)
            VALUES (star_id, -1, NULL, NULL, NULL, NULL)
        errors += 1

    processed += 1
    if processed % batch_size == 0:
        COMMIT
        LOG "Progress: {processed}/{total}, errors so far: {errors}"

COMMIT
LOG "Done. Processed {processed}, errors: {errors}"
CLOSE database

## Defects Found

| # | Where | Description | Fix |
|---|-------|-------------|-----|
| 1 | `metrics.py` `compute_metrics` | `temperature_from_bv` can yield a non-positive temperature for pathological B-V values; code raised `MetricsError` instead of recovering | Fall back to spectral-type interpolation, then mass-based estimate (`5778 × M^0.505`) when B-V temperature ≤ 0 |
| 2 | `scripts/compute_metrics.py` | Re-running the script after errors left `mass = -1` rows permanently unretried; SELECT excluded existing rows regardless of sentinel value | Changed SELECT to also include `e.mass = -1`; changed INSERT to `INSERT OR REPLACE` |
| 3 | `metrics.py` `compute_metrics` | When B-V was absent or unphysical, temperature fell back immediately to mass-based estimate, ignoring the available spectral type | Added `temperature_from_spectral()` (class-letter + subtype linear interpolation O–M); fallback chain is now: B-V → spectral type → mass-based estimate |
```

## Scripts
`scripts/compute_metrics.py`

```
uv run scripts/compute_metrics.py
uv run scripts/compute_metrics.py --db /path/to/other.db
uv run scripts/compute_metrics.py --batch-size 500 --max-minutes 30
```

## Tests
- `test_temperature_from_bv` — BV=0.65 (K dwarf) → ~4400 K; BV=0.0 (A) → ~9600 K
- `test_luminosity_from_absmag` — absmag=4.83 (Sun) → 1.0 L☉
- `test_radius_from_lum_temp` — L=1.0, T=5778 → 1.0 R☉
- `test_mass_from_luminosity` — L=1.0 → ~1.0 M☉; L=0.001 → enters low-mass branch
- `test_age_from_mass_lum` — M=1, L=1 → 1×10¹⁰ years
- `test_sig3` — 12345 → 12300; 0.006789 → 0.00679
- `test_compute_metrics_sun` — BV=0.65, absmag=4.83 → mass≈1, temp≈4400, radius≈1, lum≈1
- `test_compute_metrics_no_inputs` — both None → raises MetricsError
- `test_compute_metrics_no_ci` — ci=None, absmag=4.83 → succeeds with fallback temp
- Integration: seed small SQLite DB with 10 known rows; run script; verify DistinctStarsExtended
  is fully populated, error rows have mass=-1, resume skips already-present rows

## Notes
- Ballesteros formula is the most reliable single-equation BV→T; valid ~2000–50000 K
- Mass-luminosity inversion assumes main sequence; giants/supergiants will get underestimated mass — acceptable for this dataset
- Age estimate is MS lifetime only; treat as order-of-magnitude for evolved stars
- `--max-minutes` deadline is checked per row (cheap); no partial-batch data loss on timeout
- Same large DB as fill_spectral — run with `--max-minutes 60` overnight in successive sessions
- Back up before first run: `sqlite3 starscape.db ".backup starscape.db.bak"`
