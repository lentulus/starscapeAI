# Feature Name

## Overview
Populates NULL spectral type values in `IndexedIntegerDistinctStars` by deriving spectral class from B-V color index and absolute magnitude. Also probabilistically creates companion stars for singleton systems based on observed multiplicity rates.

## Requirements
-- we are operating on the database /Volumes/Data/starscape4/sqllite_database/starscape.db
-- each spectral column in IndexedIntegerDistinctStars must be filled in with a spectral type,
but ony where the existing spectral in currently null
-- but the spectral type must be consistent with the ci provided (assume b-v and ignore dimming) and the absolute magnitude provided.  If the ci or absmag is not provided, be creative
-- if the star is not already part of a multiple system then some percentage of the time we will create a multiple system.  Base that proportion on survey data.  Existing multiples have the same system_id values
-- recognize an existinge multiple if two or more distinct star_id share the same system_id
-- if you decide to create a multiple provide additional stars with the star with the existing row being the most massive.  assign a ci and absmag to the new star
-- insert additional stars with distinct star_id values but the same system_id


## Data / Schema
No schema changes

```sql
-- existing table
TABLE "IndexedIntegerDistinctStars" (
	"system_id"	INTEGER,
	"star_id"	INTEGER,
	"hip"	TEXT,
	"ci"	TEXT,
	"absmag"	REAL,
	"spectral"	TEXT,
	"source"	TEXT
)
```

## Shared Code
`src/starscape5/spectral.py` — new module providing:
- `format_spectral(ci, absmag)` — derives spectral type string from B-V and Mv
- `ci_from_absmag(absmag)` — estimates B-V from Mv via main-sequence lookup table
- `should_create_multiple(spectral)` — probabilistic companion decision (survey rates)
- `companion_absmag(primary_absmag)` — generates companion Mv via mass ratio and L ~ M^4
- `MULTIPLICITY_RATE` — dict of per-class multiplicity fractions


## Tests
- `test_format_spectral_bv_only` — known B-V values map to correct letter (e.g. 0.65 → K)
- `test_format_spectral_with_absmag` — luminosity class varies with Mv (I / III / V)
- `test_format_spectral_no_inputs` — returns a valid IMF-weighted type (no crash)
- `test_ci_from_absmag_roundtrip` — ci_from_absmag(5.0) → ~0.58 (solar G)
- `test_should_create_multiple_rates` — over N trials, fraction is within tolerance of survey rate
- `test_companion_absmag_fainter` — companion is always fainter than primary (q < 1 → delta > 0)
- Integration: run script against a small in-memory SQLite DB seeded with known rows, verify spectral types and companion rows are inserted correctly

## Notes
- Large database — script commits every `--batch-size` rows (default 1000); use `--dry-run` first
- `ci` column is stored as TEXT; parsed to float at read time
- Multiple-system detection is pre-cached at start (one GROUP BY query) to avoid per-row lookups
- `next_star_id` is seeded from `MAX(star_id)` at start; safe because script runs single-threaded
- `ci_from_absmag` assumes main sequence; companions generated this way will all be class V
- Back up the DB before running: `sqlite3 starscape.db ".backup starscape.db.bak"`

## Design / Logic

```
OPEN database at /Volumes/Data/starscape4/sqllite_database/starscape.db

// --- B-V (ci) to spectral type mapping (ignoring reddening) ---
function bv_to_spectral_type(ci):
    if   ci < -0.30  -> "O"
    elif ci < -0.10  -> "B"
    elif ci <  0.10  -> "A"
    elif ci <  0.29  -> "F"
    elif ci <  0.59  -> "G"
    elif ci <  1.00  -> "K"
    else             -> "M"

// --- Refine subtype and luminosity class from absmag ---
function luminosity_class(spectral_letter, absmag):
    if absmag is NULL -> assume "V" (main sequence)
    if absmag < -5   -> "I"   // supergiant
    if absmag < 0    -> "III" // giant
    else             -> "V"   // dwarf

function format_spectral(ci, absmag):
    if ci is NULL and absmag is NULL:
        return random plausible type weighted by IMF (mostly K/M dwarfs)
    letter = bv_to_spectral_type(ci)         // if ci available
    subtype = numeric subtype 0–9 from position within ci range
    lclass = luminosity_class(letter, absmag)
    return letter + subtype + lclass         // e.g. "G2V", "K5III"

// --- Multiplicity probability by spectral class (survey-based) ---
MULTIPLICITY_RATE = { O:0.75, B:0.70, A:0.50, F:0.46, G:0.46, K:0.35, M:0.27 }

function should_create_multiple(spectral_letter):
    return random() < MULTIPLICITY_RATE[spectral_letter]

// --- Generate a companion star ---
function make_companion(primary_spectral, primary_absmag, system_id, new_star_id):
    // mass ratio q drawn uniformly from [0.1, 1.0], skewed toward lower mass
    q = random uniform(0.1, 0.95)
    companion_absmag = primary_absmag + (-2.5 * log10(q^4))  // L ~ M^4 approx
    companion_ci = ci_from_absmag(companion_absmag)           // inverse of bv_to_spectral
    companion_spectral = format_spectral(companion_ci, companion_absmag)
    INSERT INTO IndexedIntegerDistinctStars
        (system_id, star_id, ci, absmag, spectral, source)
        VALUES (system_id, new_star_id, companion_ci, companion_absmag,
                companion_spectral, "generated")

// --- Main loop ---
BATCH_SIZE = 1000
commit_counter = 0

FETCH all rows WHERE spectral IS NULL
    ORDER BY system_id, star_id

FOR each row (system_id, star_id, ci, absmag):

    // 1. Assign spectral type
    spectral = format_spectral(ci, absmag)
    UPDATE row SET spectral = spectral, source = "derived"

    // 2. Check for existing multiple
    siblings = SELECT count(*) FROM IndexedIntegerDistinctStars
               WHERE system_id = row.system_id AND star_id != row.star_id
    is_multiple = siblings > 0

    // 3. Maybe create a new multiple system
    if NOT is_multiple:
        primary_letter = first character of spectral
        if should_create_multiple(primary_letter):
            new_star_id = SELECT max(star_id) + 1 FROM IndexedIntegerDistinctStars
            make_companion(spectral, absmag, system_id, new_star_id)

    commit_counter += 1
    if commit_counter % BATCH_SIZE == 0:
        COMMIT
        LOG progress

COMMIT  // final flush
CLOSE database
```
