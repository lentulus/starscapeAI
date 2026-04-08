# Planet Biosphere & Atmosphere

## Overview

Defines the atmospheric, hydrospheric, and biospheric state of rocky planets and
moons.  State is split across two tables:

- **`BodyMutable`** — atmosphere and hydrosphere; updated each simulation tick.
  *Implemented.*  Populated by `generate_atmosphere.py`.
- **`Biosphere`** — native and introduced life; one row per life-domain per body.
  *Design only — not yet implemented.*
- **`SophontPresence`** — sophont civilisation presence epochs; multiple rows per
  body to capture population, extermination, and re-population events.
  *Design only — not yet implemented.*
- **`TerraformProject`** — active and historical terraforming operations.
  *Design only — not yet implemented.*

Gas giants, belts, and planetoids have no rows in any of these tables.

---

## Scope

**Includes:** initial atmosphere/hydrosphere generation, biosphere seeding rules,
sophont presence tracking, terraforming progress model, moons (including tidal
heating and subsurface water cases).

**Excludes:** sophont civilisation mechanics (tech level, FTL, diplomacy) — those
belong to a future Species/Civilisation module.  Atmospheric weather simulation.

---

## Modules Involved

- `src/starscape5/atmosphere.py` — pure functions for physical classification.
- `scripts/generate_atmosphere.py` — initial population of `BodyMutable`; also
  back-fills `surface_gravity`, `escape_velocity_kms`, `t_eq_k` on `Bodies`.
- Future: `scripts/generate_biosphere.py` — initial seeding of `Biosphere` rows.
- Future: `src/starscape5/biosphere.py` — gating logic for biosphere generation.

**Prerequisite:** `Species` table must be designed and created before `Biosphere`
or `SophontPresence` can be implemented (both carry an FK to `species_id`).

---

## Data / Schema

### `BodyMutable` — *implemented*

```sql
CREATE TABLE IF NOT EXISTS "BodyMutable" (
    "body_id"          INTEGER PRIMARY KEY REFERENCES "Bodies"("body_id"),
    "atm_type"         TEXT,    -- 'none'|'trace'|'thin'|'standard'|'dense'|'corrosive'|'exotic'
    "atm_pressure_atm" REAL,    -- surface pressure in Earth atmospheres; 0.0 for none
    "atm_composition"  TEXT,    -- dominant gas: 'none'|'co2'|'n2o2'|'methane'|'h2so4'|'mixed'
    "surface_temp_k"   REAL,    -- post-greenhouse surface temperature (K)
    "hydrosphere"      REAL,    -- ocean/ice fraction 0.0–1.0; NULL if corrosive or no atmosphere
    "epoch"            INTEGER NOT NULL DEFAULT 0  -- game tick of last update
);
```

Also adds three immutable computed columns to `Bodies` (NULL until
`generate_atmosphere.py` has run):

```sql
"surface_gravity"     REAL,   -- g-units (1.0 = Earth); mass_me / radius_re²
"escape_velocity_kms" REAL,   -- km/s; 11.2 × √(M / R)
"t_eq_k"              REAL,   -- blackbody equilibrium temp (K); 278 × (L/a²)^0.25
```

---

### `Biosphere` — *design only*

One row per distinct life domain present on a body.  Multiple rows per body are
normal: native microbial life + introduced crop ecology + colonising sophonts are
three separate rows.  `species_id` is NULL for unnamed/non-sophont life.

```sql
CREATE TABLE IF NOT EXISTS "Biosphere" (
    "biosphere_id"     INTEGER PRIMARY KEY,
    "body_id"          INTEGER NOT NULL REFERENCES "Bodies"("body_id"),
    "species_id"       INTEGER REFERENCES "Species"("species_id"),  -- NULL for non-sophont life
    "domain"           TEXT NOT NULL,   -- 'microbial'|'complex'|'sophont'|'introduced'|'geneered'
    "origin"           TEXT NOT NULL,   -- 'native'|'seeded'|'colonized'|'refugee'
    "status"           TEXT NOT NULL,   -- 'emerging'|'extant'|'declining'|'remnant'|'extinct'
    "coverage"         REAL,            -- 0.0–1.0 fraction of surface occupied
    "is_active"        INTEGER NOT NULL DEFAULT 1,  -- 0 when epoch_extinct is set
    "epoch_established" INTEGER,        -- NULL for native pre-simulation life (predates epoch)
    "epoch_extinct"    INTEGER          -- NULL if still extant
);
```

**`epoch_established = NULL`** is the canonical marker for pre-simulation native
life — the species evolved there, it did not arrive.  Any row with a non-NULL
`epoch_established` represents a deliberate arrival event within the simulation
window.

**Active life query:** `WHERE is_active = 1` (avoids filtering on NULL).

---

### `SophontPresence` — *design only*

Detailed record of when a sophont species was present on a body.  A species can
have multiple rows on the same body (exterminated, world recovered, re-colonised
centuries later).  Separates from Biosphere because sophont presence has richer
temporal semantics and will grow considerably as civilisation mechanics are added.

```sql
CREATE TABLE IF NOT EXISTS "SophontPresence" (
    "presence_id"      INTEGER PRIMARY KEY,
    "body_id"          INTEGER NOT NULL REFERENCES "Bodies"("body_id"),
    "species_id"       INTEGER NOT NULL REFERENCES "Species"("species_id"),
    "presence_start"   INTEGER,         -- game tick; NULL for native species (pre-simulation)
    "presence_end"     INTEGER,         -- NULL if currently present
    "origin"           TEXT NOT NULL,   -- 'native'|'colonized'|'refugee'|'repopulated'
    "peak_population"  REAL,            -- highest headcount reached this presence period
    "end_cause"        TEXT             -- NULL|'exterminated'|'evacuated'|'abandoned'|'ascended'
);
```

**Example — native species wiped out then returned:**

| `presence_id` | `origin` | `presence_start` | `presence_end` | `end_cause` |
|---|---|---|---|---|
| 1 | `native` | NULL | 12450 | `exterminated` |
| 2 | `repopulated` | 18730 | NULL | NULL |

**Current presence query:** `WHERE body_id = ? AND presence_end IS NULL`

**Note:** The simulation horizon of ~4×10⁴ years means no evolutionary drift —
the Species table is static per entity; `SophontPresence` captures movements, not speciation.

---

### `TerraformProject` — *design only*

Tracks active and historical terraforming operations.  Multiple actors can work
the same body concurrently (or competitively).  `progress` (0.0–1.0) drives linear
interpolation of `BodyMutable` values from initial state toward target state.

```sql
CREATE TABLE IF NOT EXISTS "TerraformProject" (
    "project_id"           INTEGER PRIMARY KEY,
    "body_id"              INTEGER NOT NULL REFERENCES "Bodies"("body_id"),
    "executor_species_id"  INTEGER NOT NULL REFERENCES "Species"("species_id"),
    "target_atm_type"      TEXT,    -- goal atm_type in BodyMutable
    "target_atm_pressure_atm" REAL,
    "target_surface_temp_k"   REAL,
    "target_hydrosphere"   REAL,
    "progress"             REAL NOT NULL DEFAULT 0.0,  -- 0.0–1.0
    "status"               TEXT NOT NULL DEFAULT 'active',  -- 'active'|'paused'|'abandoned'|'complete'
    "epoch_started"        INTEGER NOT NULL,
    "epoch_completed"      INTEGER  -- NULL until done
);
```

When `progress = 1.0`, `BodyMutable` is set to target values and `status` →
`'complete'`.  A new `Biosphere` row can then be seeded for the terraformed
ecology.

---

## Design / Logic

### Atmosphere classification (implemented — see `atmosphere.py`)

Priority waterfall on `escape_velocity_kms` and `t_eq_k`:

```
v_esc < 1.0              → 'none'       (Moon-scale)
v_esc < 3.0              → 'trace'      (Mars-scale)
t_eq  > 650 K            → 'corrosive'  (runaway greenhouse)
v_esc < 5.0              → 'thin'
t_eq  < 120 K            → 'thin'       (gases freeze out)
tidal_lock               → 'thin'(70%) | 'standard'(30%)
in_hz = 1                → 'thin'(10%) | 'standard'(60%) | 'dense'(30%)
otherwise                → 'thin'(40%) | 'standard'(45%) | 'dense'(15%)
```

Greenhouse multiplier on `t_eq_k` → `surface_temp_k`:
`none/trace` ×1.00 · `thin` ×1.05 · `standard` ×1.10 · `dense` ×1.25 · `corrosive` ×2.20

Tidal heating: inner moons (< 0.01 AU from parent) of gas giants receive
+10–40 K on `t_eq_k` before classification.

### Hydrosphere (implemented — see `atmosphere.py`)

- `atm_type` = `'none'` or `'corrosive'` → NULL (no stable surface liquid)
- `surface_temp_k` > 380 K → 0.0
- `in_hz = 1` → Beta(2, 2) draw (Earthlike spread around 0.5)
- otherwise → Uniform(0, 0.30) (residual ice/subsurface)

### Biosphere gating (future — `generate_biosphere.py`)

Runs after `generate_atmosphere.py`.  One pass over all bodies with a `BodyMutable`
row:

```
If atm_type in ('none', 'corrosive')          → no Biosphere row
If in_hz=1 AND atm_type='standard'
   AND hydrosphere > 0.1                       → 'complex' (70%) | 'microbial' (30%)
If in_hz=1 AND atm_type in ('thin','standard')
   AND hydrosphere > 0                         → 'microbial'
If moon of GG AND surface_temp_k < 273
   AND parent has tidal heating                → 'microbial' (10% — Europa/Enceladus analogue)
Otherwise                                      → no Biosphere row
```

All generated Biosphere rows: `origin='native'`, `epoch_established=NULL`,
`status='extant'`, `species_id=NULL`.

---

## Scripts

```
# Initial atmosphere and hydrosphere generation (after generate_planets.py)
uv run scripts/generate_atmosphere.py
uv run scripts/generate_atmosphere.py --max-minutes 240

# Future — biosphere seeding (after generate_atmosphere.py)
uv run scripts/generate_biosphere.py
```

---

## Notes

- **Species table dependency:** `Biosphere` and `SophontPresence` carry a FK to
  `species_id`.  The `Species` table must be designed before either can be
  implemented.  A design reminder is saved in session memory.
- **BodyMutable is current state only** — no historical rows.  If game-time
  history is needed for atmosphere changes, a separate audit/ledger table is
  required.  Not in scope for initial implementation.
- **`atm_composition`** is a single dominant-gas tag.  Full multi-gas composition
  (e.g. 78% N₂, 21% O₂, …) is not modelled; tag is sufficient for gameplay
  classification.
- **Europa-analogue subsurface oceans** are partially captured: moons with tidal
  heating but `atm_type='none'` will have `hydrosphere=NULL` (no surface liquid).
  True subsurface water detection would require a separate flag; deferred.
