# V1.1 — Habitability by Species

**Status: design**  
First and only confirmed V1.1 component.  Everything else is deferred.

---

## Purpose

`BodyHabitability` is a pre-computed table that answers, for every rocky body
and every species, two questions:

1. **Can this species colonise this world without sealed-environment life support?**  (`habitable` 0/1)
2. **How desirable is it?**  (`habitability_score` 0–100)

It is computed once at init from static data in `starscape.db` and lives in
`game_v1_1.db`.  It is the only table in the first V1.1 schema milestone.

---

## Inputs

All inputs are read-only from `starscape.db`.  No game state is involved.

**From `Bodies`:**

| Column | Role |
|---|---|
| `body_id`, `system_id` | Keys |
| `planet_class` | Filter — only `'rocky'`; moons included if they have atm data |
| `atm_type` | Atmosphere category gate |
| `atm_composition` | Composition match against `atm_req` |
| `atm_pressure_atm` | Pressure gate |
| `mean_temp_k` | Temperature gate (falls back to `surface_temp_k` if NULL) |
| `hydrosphere` | Quality bonus; aquatic species gate |
| `in_hz` | Quality bonus |
| `compatibility_rating` | Bio safety gate and quality bonus |
| `biomass_rating` | Bio safety gate |

**From `Species`:**

| Column | Role |
|---|---|
| `species_id` | Key |
| `temp_min_k`, `temp_max_k` | Temperature gate |
| `pressure_min_atm`, `pressure_max_atm` | Pressure gate |
| `atm_req` | Atmosphere composition gate |
| `diet_flexibility` | Modifies bio-safety score |

---

## Temporal model — insert-only state

**State tables in V1.1 are never updated.  Every change is a new INSERT.**

A state row is valid from its `sim_seconds` until the next row for the same
logical key appears.  To read state "as of" a given simulation time, query
the row with the highest `sim_seconds` that does not exceed the target time.

This applies to `BodyHabitability` and all future state tables.  It means:
- No `UPDATE` statements anywhere in the simulation engine
- Full history is always preserved
- Crash recovery is trivial — a partial insert either committed or did not
- The `_head` view always reflects current (latest committed) state

---

## Schema

Lives in `game_v1_1.db`.  This is the entire database at milestone 1.

```sql
CREATE TABLE "BodyHabitability" (
    "body_id"             INTEGER NOT NULL,   -- ref Bodies.body_id in starscape.db
    "species_id"          INTEGER NOT NULL,   -- ref Species.species_id in starscape.db
    "system_id"           INTEGER NOT NULL,   -- denormalised for query convenience
    "sim_seconds"         INTEGER NOT NULL DEFAULT 0,
                                             -- simulation time this row takes effect;
                                             -- 0 = initial state (pre-simulation)

    -- WBH habitability rating (species-specific DM table)
    "habitability_rating" INTEGER NOT NULL,   -- 10 + DMs; can be negative
    "habitable"           INTEGER NOT NULL,   -- 1 iff habitability_rating >= 1 and bio_safe = 1
    "factors"             TEXT    NOT NULL,   -- semicolon-separated non-zero DM contributors
                                             -- e.g. "atm_hostile:-10;hydro_none:-4"
                                             -- empty string if no penalties or bonuses

    -- Bio safety (not captured by WBH DM table alone)
    "bio_safe"            INTEGER NOT NULL,   -- 1 if compatibility > 0 or no life present

    PRIMARY KEY ("body_id", "species_id", "sim_seconds")
);

CREATE INDEX "idx_bh_species"   ON "BodyHabitability"("species_id", "sim_seconds");
CREATE INDEX "idx_bh_system"    ON "BodyHabitability"("system_id",  "sim_seconds");
CREATE INDEX "idx_bh_habitable" ON "BodyHabitability"("species_id", "habitable", "sim_seconds");

-- Current state: most recent row per (body_id, species_id)
CREATE VIEW "BodyHabitability_head" AS
    SELECT bh.*
    FROM   "BodyHabitability" bh
    WHERE  bh.sim_seconds = (
        SELECT MAX(sim_seconds)
        FROM   "BodyHabitability"
        WHERE  body_id   = bh.body_id
          AND  species_id = bh.species_id
    );
```

---

## Gate logic

### `bio_safe`

The WBH habitability DMs cover physical conditions but not biosphere
hostility.  `bio_safe` is retained as a separate flag:

```
bio_safe = 1  iff  biomass_rating = 0            (no life present)
              OR   compatibility_rating > 0       (life is biochemically compatible)
              OR   compatibility_rating IS NULL   (not evaluated — benefit of doubt)
```

`bio_safe = 0` only when `biomass_rating > 0 AND compatibility_rating = 0`.
A `bio_safe = 0` world imposes an additional effective DM applied after the
WBH formula — currently treated as making the world non-habitable regardless
of the WBH score.

### `habitable`

```
habitable = 1  iff  habitability_rating ≥ 1  AND  bio_safe = 1
```

The WBH does not define an explicit habitability threshold; using ≥ 1 means
any world where the DMs do not fully cancel the base 10 is considered
colonisable.  Worlds scoring 1–3 are marginal and will have a colonisation
cost penalty (future mechanic).

---

## Habitability rating — WBH formula (Terragens, p.132)

**This is the Terragens (human) table.**  Other sophont species will have
their own DM tables; the schema is identical but the computation differs.
Those tables are deferred until the relevant species are modelled.

### Formula

```
Habitability Rating = 10 + sum of all applicable DMs
```

Result can be negative (extremely hostile) or above 10 (near-ideal).
`habitable = 1` iff `habitability_rating ≥ 1`.

### DM table — Terragens

| Condition | DM | WBH description |
|---|---|---|
| Size 0–4 | −1 | Limited surface area |
| Size 9+ | +1 | Additional surface area |
| Atmosphere 0, 1, or A | −8 | Non-breathable |
| Atmosphere 2 or E | −4 | Very thin tainted or thin low |
| Atmosphere 3 or D | −3 | Very thin or very dense |
| Atmosphere 4 or 9 | −2 | Tainted thin or dense |
| Atmosphere 5, 7, or 8 | −1 | Thin, tainted standard, or dense |
| Atmosphere B | −10 | Hostile |
| Atmosphere C or F+ | −12 | Very hostile |
| Low oxygen taint (type L) | −2 | In addition to any atmosphere DM |
| Hydrographics 0 | −4 | No accessible liquid water |
| Hydrographics 1–3 | −2 | Desert conditions |
| Hydrographics 9 | −1 | Little useable land |
| Hydrographics A (10) | −2 | Very little useable land |
| Tidal lock 1:1 | −2 | Very little useable land surface |
| Mean temperature > 323 K | −4 | Too hot most of the time |
| Mean temperature 304–323 K | −2 | Too hot much of the time |
| Mean temperature < 273 K | −2 | Too cold most of the time |
| Gravity < 0.2 g | −4 | Unhealthy gravity |
| Gravity 0.2–0.4 g | −2 | Very low gravity |
| Gravity 0.4–0.7 g | −1 | Low gravity |
| Gravity 0.7–0.9 g | +1 | Comfortable gravity |
| Gravity 1.1–1.4 g | −1 | Somewhat high gravity |
| Gravity 1.4–2.0 g | −3 | Uncomfortably high gravity |
| Gravity > 2.0 g | −6 | Too high for acclimation |

**Notes on overlapping gravity bands:** the WBH table has overlapping ranges
(0.2–0.7 and 0.4–0.7; 1.1–1.4 and 1.1–2.0).  Interpretation: use the
narrower/more specific band when it applies.  So 0.4–0.7 g → DM−1 (not −2);
1.1–1.4 g → DM−1 (not −3); 1.4–2.0 g → DM−3.

**High/low seasonal temperatures:** `high_temp_k` and `low_temp_k` are
computed for all rocky bodies via the WBH 9-step procedure (pp.112–114) and
stored in Bodies.  The DMs for seasonal extremes (high > 323 K → DM−4;
low < 200 K → DM−2) are applied in addition to mean temperature DMs.

**Undefined gravity:** if `gravity_g` is NULL, use
`DM = +1 − abs(6 − size_num)` where size_num is the numeric size code value.

### `factors` text field

Records every non-zero DM contributor as a semicolon-separated list of
`key:dm` pairs.  Zero-DM conditions are omitted.  This is the only diagnostic
record — no separate component columns.

Format: `"key:dm;key:dm;..."` — signed integer DM, e.g. `+1` or `-4`.

Example — marginal desert world:
```
atm_3:-3;hydro_2:-2;mean_cold:-2;gravity_low:-1
```

Example — near-ideal world (only positive DM recorded):
```
gravity_comfortable:+1
```

Example — Earth at game start (atm 6, hydro 7, mean ~288 K, g ≈ 1.0):
```
gravity_comfortable:+1
```
(All other DMs are 0 — nothing to record.)

**Key names** (canonical, used in code and queries):

| Key | Condition |
|---|---|
| `size_small` | Size 0–4 |
| `size_large` | Size 9+ |
| `atm_none` | Atm 0, 1, A |
| `atm_very_thin` | Atm 2 or E |
| `atm_thin_dense` | Atm 3 or D |
| `atm_tainted` | Atm 4 or 9 |
| `atm_marginal` | Atm 5, 7, 8 |
| `atm_hostile` | Atm B |
| `atm_lethal` | Atm C or F+ |
| `taint_low_o2` | Low oxygen taint |
| `hydro_none` | Hydrographics 0 |
| `hydro_desert` | Hydrographics 1–3 |
| `hydro_ocean` | Hydrographics 9 |
| `hydro_water_world` | Hydrographics A |
| `tidal_locked` | 1:1 tidal lock |
| `temp_hot` | Mean > 323 K |
| `temp_warm` | Mean 304–323 K |
| `temp_cold` | Mean < 273 K |
| `gravity_lethal_low` | g < 0.2 |
| `gravity_very_low` | g 0.2–0.4 |
| `gravity_low` | g 0.4–0.7 |
| `gravity_comfortable` | g 0.7–0.9 |
| `gravity_high` | g 1.1–1.4 |
| `gravity_very_high` | g 1.4–2.0 |
| `gravity_lethal_high` | g > 2.0 |
| `gravity_undefined` | gravity_g IS NULL |

---

## Population strategy

### Coverage

Computed for every body where:
- `planet_class = 'rocky'` (planets), **OR** `orbit_body_id IS NOT NULL` (moons)
- `atm_type IS NOT NULL` (atmosphere data generated)

Belts, planetoids, and gas giants are excluded.

Crossed against all 11 species rows in `Species`.

Estimated row count at full DB generation:
roughly (rocky bodies generated) × 11.  At ~3–5 rocky bodies per system
and ~500k systems generated: **~15–25 million rows**.  The table is
append-only at this milestone; no updates during the run.

### Script: `scripts/seed_habitability.py`

Single-purpose script.  Reads from `starscape.db`, writes to `game_v1_1.db`.

Flow:
1. Load all 11 species rows into memory (tiny).
2. Cursor over eligible Bodies in batches of 50,000.
3. For each batch, compute gate flags and score for all 11 species.
4. Bulk INSERT into `BodyHabitability` with `INSERT OR IGNORE`.
5. Commit per batch; log progress.
6. Resumable: `INSERT OR IGNORE` skips already-computed rows.

No `--purge` flag needed — rerunning is safe and idempotent.

Estimated runtime: a few minutes at 50k bodies/batch with bulk inserts.

### Use at game init

When the game engine initialises, it does **not** recompute habitability.
It queries `BodyHabitability` directly.  The table must be pre-populated
by `seed_habitability.py` before any game init.

---

## Key queries

All queries have two forms: **current state** (use the `_head` view) and
**as-of a simulation time** (inline correlated subquery on `sim_seconds`).

**Current state — is this world colonisable by species X?**
```sql
SELECT habitable, habitability_rating, factors
FROM   BodyHabitability_head
WHERE  body_id = ? AND species_id = ?
```

**As-of — state at a specific simulation time:**
```sql
SELECT habitable, habitability_rating, factors
FROM   BodyHabitability
WHERE  body_id    = ?
  AND  species_id = ?
  AND  sim_seconds = (
      SELECT MAX(sim_seconds) FROM BodyHabitability
      WHERE  body_id = ? AND species_id = ? AND sim_seconds <= :as_of
  )
```

**Current — best colonisation targets for species X in a system:**
```sql
SELECT body_id, habitability_rating, factors
FROM   BodyHabitability_head
WHERE  system_id = ? AND species_id = ? AND habitable = 1
ORDER  BY habitability_rating DESC
```

**Current — all habitable worlds for species X, best first:**
```sql
SELECT body_id, system_id, habitability_rating, factors
FROM   BodyHabitability_head
WHERE  species_id = ? AND habitable = 1
ORDER  BY habitability_rating DESC
```

**History — how did habitability change for a body over time?**
```sql
SELECT sim_seconds, habitability_rating, habitable, factors
FROM   BodyHabitability
WHERE  body_id = ? AND species_id = ?
ORDER  BY sim_seconds
```

**Current — worlds penalised by hostile biosphere:**
```sql
SELECT body_id, system_id, habitability_rating, factors
FROM   BodyHabitability_head
WHERE  species_id = ? AND bio_safe = 0
ORDER  BY habitability_rating DESC
```

---

## What this does NOT include

- Mutable state (terraforming, bombardment effects) — deferred to `BodyMutableState`
- Recomputation triggers — will be added when mutable state exists
- `resource_rating` incorporation into `WorldPotential` — deferred
- `sim_seconds` timestamp — not needed until recomputation is possible
- Any other game state (polities, fleets, economy) — out of scope for milestone 1
