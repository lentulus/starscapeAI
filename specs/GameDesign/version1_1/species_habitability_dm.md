# V1.1 — SpeciesHabitabilityDM

**Status: design**  
Data-driven DM table replacing hard-coded species logic in the habitability engine.

---

## Purpose

`SpeciesHabitabilityDM` stores the WBH habitability modifier rules as data rows.
Each row defines one condition that contributes a DM to a species'
`habitability_rating`.  The computation engine evaluates all rows for a given
species against a body's physical properties, sums the DMs, and adds them to the
base score of 10.

This approach allows new species to be added by inserting rows — no code changes
required.

---

## Schema

Lives in `game_v1_1.db`.

```sql
CREATE TABLE "SpeciesHabitabilityDM" (
    "rule_id"        INTEGER PRIMARY KEY,
    "species_id"     INTEGER NOT NULL,  -- ref Species.species_id in starscape.db

    -- What kind of condition triggers this DM
    "condition_type" TEXT NOT NULL CHECK(condition_type IN (
        'atm_code',        -- atm_code matches one value in str_value (comma-separated list)
        'taint_type',      -- any taint slot matches str_value
        'size_range',      -- size_num (numeric) in [lo_value, hi_value)
        'hydro_range',     -- hydro_code in [lo_value, hi_value)
        'temp_range',      -- mean_temp_k in [lo_value, hi_value)
        'high_temp_range', -- high_temp_k in [lo_value, hi_value)
        'low_temp_range',  -- low_temp_k in [lo_value, hi_value)
        'gravity_range',   -- gravity_g in [lo_value, hi_value)
        'gravity_size_fallback', -- gravity_g IS NULL; uses size_num formula
        'flag'             -- str_value names a boolean body property (e.g. 'tidal_lock_1_1')
    )),

    -- Condition parameters (usage depends on condition_type)
    "str_value"      TEXT,    -- atm codes (comma-separated), taint type, flag name
    "lo_value"       REAL,    -- lower bound inclusive; NULL = no lower limit
    "hi_value"       REAL,    -- upper bound exclusive; NULL = no upper limit

    -- The modifier
    "dm"             INTEGER NOT NULL,

    -- Canonical key name used in the factors text field
    "factor_key"     TEXT NOT NULL,

    -- Human-readable description (matches WBH language)
    "description"    TEXT NOT NULL
);

CREATE INDEX "idx_shdm_species" ON "SpeciesHabitabilityDM"("species_id");
```

---

## Computation

The engine evaluates `SpeciesHabitabilityDM` rows in `rule_id` order.
For each row:

1. Evaluate the condition against the body's physical data.
2. If the condition is met, add `dm` to the running total and append
   `factor_key:dm` to the factors list (omit zero-DM rows — none exist in
   this table, but guard anyway).
3. After all rows: `habitability_rating = 10 + total_dm`.
4. `habitable = 1` iff `habitability_rating >= 1 AND bio_safe = 1`.

### Condition evaluation rules

| condition_type | Fires when |
|---|---|
| `atm_code` | body.atm_code is in the comma-separated `str_value` list |
| `taint_type` | `str_value` appears in any of taint_type_1/2/3 |
| `size_range` | `lo_value <= size_num < hi_value` (NULL bounds = open) |
| `hydro_range` | `lo_value <= hydro_code < hi_value` (NULL bounds = open) |
| `temp_range` | `lo_value <= mean_temp_k < hi_value` (NULL bounds = open); skip if mean_temp_k IS NULL |
| `gravity_range` | `lo_value <= gravity_g < hi_value` (NULL bounds = open); skip if gravity_g IS NULL |
| `gravity_size_fallback` | gravity_g IS NULL; `dm = +1 - abs(6 - size_num)` applied directly |
| `flag` | body flag named by `str_value` is true (e.g. tidal_lock_status = '1:1') |

`gravity_size_fallback` is the only variable-DM row type.  The `dm` column
stores 0 for it; the engine computes the actual DM at runtime and uses the
`factor_key` from the row for the factors text.

---

## Terragens (Human) rows — species_id = 1

The WBH p.132 Terragens table, with overlapping gravity bands resolved to
non-overlapping (narrower/more specific band wins).  Base score is 10; these
are pure modifiers.

### Atmosphere DMs

| rule_id | condition_type | str_value | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|---|
| 101 | atm_code | `0,1,A` | | | −8 | atm_none | Non-breathable |
| 102 | atm_code | `2,E` | | | −4 | atm_very_thin | Very thin tainted or thin low |
| 103 | atm_code | `3,D` | | | −3 | atm_thin_dense | Very thin or very dense |
| 104 | atm_code | `4,9` | | | −2 | atm_tainted | Tainted thin or dense |
| 105 | atm_code | `5,7,8` | | | −1 | atm_marginal | Thin, tainted standard, or dense |
| 106 | atm_code | `B` | | | −10 | atm_hostile | Hostile |
| 107 | atm_code | `C,F,G,H` | | | −12 | atm_lethal | Very hostile |

Notes:
- Atm 6 (Standard breathable) has DM 0 — no row.
- Atm F+ covers codes F, G, H in the WBH "C or F+" entry.

### Taint DMs

| rule_id | condition_type | str_value | dm | factor_key | description |
|---|---|---|---|---|---|
| 111 | taint_type | `L` | −2 | taint_low_o2 | Low oxygen taint (in addition to atm DM) |

### Size DMs

`size_num` is the numeric interpretation of `size_code`
(S=0, 0=0, 1=1, …, 9=9, A=10, …).

| rule_id | condition_type | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|
| 121 | size_range | 0 | 5 | −1 | size_small | Limited surface area (Size 0–4) |
| 122 | size_range | 9 | | +1 | size_large | Additional surface area (Size 9+) |

Note: hi_value NULL means no upper limit (open-ended).

### Hydrographics DMs

| rule_id | condition_type | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|
| 131 | hydro_range | 0 | 1 | −4 | hydro_none | No accessible liquid water (Hydro 0) |
| 132 | hydro_range | 1 | 4 | −2 | hydro_desert | Desert conditions (Hydro 1–3) |
| 133 | hydro_range | 9 | 10 | −1 | hydro_ocean | Little useable land (Hydro 9) |
| 134 | hydro_range | 10 | | −2 | hydro_water_world | Very little useable land (Hydro A/10+) |

### Mean Temperature DMs

| rule_id | condition_type | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|
| 141 | temp_range | 323.0 | | −4 | temp_hot | Too hot most of the time (> 323 K) |
| 142 | temp_range | 304.0 | 323.0 | −2 | temp_warm | Too hot much of the time (304–323 K) |
| 143 | temp_range | | 273.0 | −2 | temp_cold | Too cold most of the time (< 273 K) |

Note: lo_value NULL means no lower limit.  These DMs apply to `mean_temp_k`.

### Seasonal High/Low Temperature DMs

These apply to `high_temp_k` and `low_temp_k` computed via the WBH 9-step
procedure (pp.112–114).  The condition types `high_temp_range` and
`low_temp_range` evaluate against those columns respectively.

| rule_id | condition_type | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|
| 144 | high_temp_range | 323.0 | | −4 | seasonal_hot | Seasonally too hot (high > 323 K) |
| 145 | low_temp_range | | 200.0 | −2 | seasonal_cold | Seasonally too cold (low < 200 K) |

Note: these DMs stack with the mean temperature DMs if both conditions are
met (e.g. a hot world with hot seasons gets both `temp_hot` and
`seasonal_hot`).

### Gravity DMs (non-overlapping, narrower-band-wins resolution)

| rule_id | condition_type | lo_value | hi_value | dm | factor_key | description |
|---|---|---|---|---|---|---|
| 151 | gravity_range | | 0.2 | −4 | gravity_lethal_low | Unhealthy gravity (< 0.2 g) |
| 152 | gravity_range | 0.2 | 0.4 | −2 | gravity_very_low | Very low gravity (0.2–0.4 g) |
| 153 | gravity_range | 0.4 | 0.7 | −1 | gravity_low | Low gravity (0.4–0.7 g) |
| 154 | gravity_range | 0.7 | 0.9 | +1 | gravity_comfortable | Comfortable gravity (0.7–0.9 g) |
| 155 | gravity_range | 0.9 | 1.1 | 0 | — | Earth-normal; no row needed |
| 156 | gravity_range | 1.1 | 1.4 | −1 | gravity_high | Somewhat high gravity (1.1–1.4 g) |
| 157 | gravity_range | 1.4 | 2.0 | −3 | gravity_very_high | Uncomfortably high gravity (1.4–2.0 g) |
| 158 | gravity_range | 2.0 | | −6 | gravity_lethal_high | Too high for acclimation (> 2.0 g) |
| 159 | gravity_size_fallback | | | 0 | gravity_undefined | gravity_g IS NULL; DM = +1 − abs(6 − size_num) |

Rule 155 (DM 0) and the "no row" note are informational only — zero-DM rows
are not inserted.  Rule 159 uses `dm = 0` as a placeholder; the actual DM
is computed at runtime.

### Tidal lock DMs

| rule_id | condition_type | str_value | dm | factor_key | description |
|---|---|---|---|---|---|
| 161 | flag | `tidal_lock_1_1` | −2 | tidal_locked | 1:1 tidal lock — very little useable land surface |

The flag `tidal_lock_1_1` is true when `tidal_lock_status = '1:1'` in Bodies.

---

## INSERT statements — Terragens seed

```sql
-- Atmosphere
INSERT INTO SpeciesHabitabilityDM VALUES(101,1,'atm_code','0,1,A',NULL,NULL,-8,'atm_none','Non-breathable');
INSERT INTO SpeciesHabitabilityDM VALUES(102,1,'atm_code','2,E',NULL,NULL,-4,'atm_very_thin','Very thin tainted or thin low');
INSERT INTO SpeciesHabitabilityDM VALUES(103,1,'atm_code','3,D',NULL,NULL,-3,'atm_thin_dense','Very thin or very dense');
INSERT INTO SpeciesHabitabilityDM VALUES(104,1,'atm_code','4,9',NULL,NULL,-2,'atm_tainted','Tainted thin or dense');
INSERT INTO SpeciesHabitabilityDM VALUES(105,1,'atm_code','5,7,8',NULL,NULL,-1,'atm_marginal','Thin, tainted standard, or dense');
INSERT INTO SpeciesHabitabilityDM VALUES(106,1,'atm_code','B',NULL,NULL,-10,'atm_hostile','Hostile');
INSERT INTO SpeciesHabitabilityDM VALUES(107,1,'atm_code','C,F,G,H',NULL,NULL,-12,'atm_lethal','Very hostile');

-- Taint
INSERT INTO SpeciesHabitabilityDM VALUES(111,1,'taint_type','L',NULL,NULL,-2,'taint_low_o2','Low oxygen taint');

-- Size
INSERT INTO SpeciesHabitabilityDM VALUES(121,1,'size_range',NULL,0,5,-1,'size_small','Limited surface area');
INSERT INTO SpeciesHabitabilityDM VALUES(122,1,'size_range',NULL,9,NULL,1,'size_large','Additional surface area');

-- Hydrographics
INSERT INTO SpeciesHabitabilityDM VALUES(131,1,'hydro_range',NULL,0,1,-4,'hydro_none','No accessible liquid water');
INSERT INTO SpeciesHabitabilityDM VALUES(132,1,'hydro_range',NULL,1,4,-2,'hydro_desert','Desert conditions');
INSERT INTO SpeciesHabitabilityDM VALUES(133,1,'hydro_range',NULL,9,10,-1,'hydro_ocean','Little useable land');
INSERT INTO SpeciesHabitabilityDM VALUES(134,1,'hydro_range',NULL,10,NULL,-2,'hydro_water_world','Very little useable land');

-- Mean temperature
INSERT INTO SpeciesHabitabilityDM VALUES(141,1,'temp_range',NULL,323.0,NULL,-4,'temp_hot','Too hot most of the time');
INSERT INTO SpeciesHabitabilityDM VALUES(142,1,'temp_range',NULL,304.0,323.0,-2,'temp_warm','Too hot much of the time');
INSERT INTO SpeciesHabitabilityDM VALUES(143,1,'temp_range',NULL,NULL,273.0,-2,'temp_cold','Too cold most of the time');

-- Seasonal high/low temperature
INSERT INTO SpeciesHabitabilityDM VALUES(144,1,'high_temp_range',NULL,323.0,NULL,-4,'seasonal_hot','Seasonally too hot (high > 323 K)');
INSERT INTO SpeciesHabitabilityDM VALUES(145,1,'low_temp_range',NULL,NULL,200.0,-2,'seasonal_cold','Seasonally too cold (low < 200 K)');

-- Gravity (non-overlapping)
INSERT INTO SpeciesHabitabilityDM VALUES(151,1,'gravity_range',NULL,NULL,0.2,-4,'gravity_lethal_low','Unhealthy gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(152,1,'gravity_range',NULL,0.2,0.4,-2,'gravity_very_low','Very low gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(153,1,'gravity_range',NULL,0.4,0.7,-1,'gravity_low','Low gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(154,1,'gravity_range',NULL,0.7,0.9,1,'gravity_comfortable','Comfortable gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(156,1,'gravity_range',NULL,1.1,1.4,-1,'gravity_high','Somewhat high gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(157,1,'gravity_range',NULL,1.4,2.0,-3,'gravity_very_high','Uncomfortably high gravity');
INSERT INTO SpeciesHabitabilityDM VALUES(158,1,'gravity_range',NULL,2.0,NULL,-6,'gravity_lethal_high','Too high for acclimation');
INSERT INTO SpeciesHabitabilityDM VALUES(159,1,'gravity_size_fallback',NULL,NULL,NULL,0,'gravity_undefined','gravity_g IS NULL; DM = +1 − abs(6 − size_num)');

-- Tidal lock
INSERT INTO SpeciesHabitabilityDM VALUES(161,1,'flag','tidal_lock_1_1',NULL,NULL,-2,'tidal_locked','1:1 tidal lock');
```

---

## What is deferred

- DM tables for the 10 non-Terragen species — deferred until each species is
  modelled in detail.  Their `species_id` rows will use the same schema with
  different values.
- Aquatic species gate (hydrographics minimum) — not present in the Terragens
  table; will appear in aquatic species rows.
- Cold-adapted and heat-adapted species variants — same schema, different
  `temp_range` rows.

---

## Relationship to seed_habitability.py

`seed_habitability.py` loads all `SpeciesHabitabilityDM` rows for each
species into memory at startup, then applies them in `rule_id` order to each
body.  This replaces hard-coded Python condition logic with a table lookup,
making species addition a data operation only.
