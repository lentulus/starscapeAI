# WBH Planet Generation Plan

Replace the existing `scripts/generate_planets.py` and `scripts/generate_atmosphere.py` (and the data they produce in `Bodies` + `BodyMutable`) with a new generator derived from the *World Builder's Handbook* (WBH) by Colin Dunn. The current generator has documented physical defects; this plan corrects them end-to-end using WBH methods.

---

## 1. Current defects

The existing generator (`planets.py` + the scripts that call it) has the following known anomalies, documented in `specs/system_orbital_data.md`:

| Defect | Source | Manifestation |
|---|---|---|
| Eccentricity hard-capped at 0.97 | `planets.py` | Bimodal `e` distribution; no values above 0.97 |
| SMA hard-capped at 50 AU | `planets.py` | Outer system truncated; Kuiper-belt-equivalent bodies cut off |
| No periapsis-inside-star check | `planets.py` | Orbits with periapsis < R★ exist (3 homeworld systems affected) |
| No Roche-limit check for companions | `orbits.py` | 35 888 companion pairs inside Roche limit |
| Companion SMA up to 6.58 M AU (unbound) | `orbits.py` | Hill sphere not enforced; ~20 924 companions with a_peri < R★ |
| Atmosphere/hydro classification only (no physics) | `atmosphere.py` | Pressure, temperature, gravity not computed; only codes stored |
| No density/mass/gravity chain | `planets.py` | `Bodies.mass` not independently derived from size + composition |
| Moon orbital periods of decades–centuries | `planets.py` | No Hill sphere / Roche check on moon SMA |
| Inclinations random 0–180° (uniform) | `planets.py` | No low-inclination prior; no retrograde flag |

---

## 2. Special handling: Sol system and Human homeworld

### 2a. Sol system preservation (star #1)

Star #1 in the database is Sol (`star_id = 1`, `system_id = 1030192`, position (0, 0, 0) mpc). The Sol system is seeded manually by `scripts/seed_sol.py` with real planetary data. The regeneration process must:

1. **Delete all Bodies rows for `system_id = 1030192` before regeneration**, but only after a confirmed backup.
2. **Re-run `seed_sol.py` after generation is complete** to restore accurate Sol data (Mercury through Neptune, major moons, asteroid belt). The procedural generator must not be run against `system_id = 1030192`.
3. Add a skip guard at the top of the new planet generator: `if system_id == 1030192: continue` (or equivalent).
4. Document this in the script's `--help` output.

### 2b. Human homeworld always at star #1

The game initialiser (`game/init_game.py`) and the Orders of Battle (`game/ob_data.py`) assign starting positions at game setup. The following rule must be hard-coded as an invariant, not a probabilistic outcome:

> **Humans (species identified as `species_id` for `Humaniti` / `Human` in the `Species` table) always start with their homeworld at `system_id = 1030192` (Sol, star #1).**

Implementation:
- In `ob_data.py`, the Human polity's `homeworld_system_id` must be set to `1030192` explicitly, not selected by proximity or chance.
- Earth (`body_type='planet'`, `name='Earth'`) within that system must be the designated homeworld body. After `seed_sol.py` runs, Earth is at orbit 3 (Orbit# 3.5, 1.0 AU). No other body should be assigned as the Human homeworld.
- Add an assertion in `init_game.py`: `assert human_polity.capital_system_id == 1030192`.
- This constraint must survive simulation resets and new game initialisation.

---

## 3. Pre-seeding near-Earth worlds in solitary F5–K5 systems (continuation method)

For every solitary star (no companions) with spectral class **F5 through K5** (inclusive), the generator will use the WBH **continuation method** to pre-place a single near-Earth mainworld in the habitable zone **before** running the normal probabilistic orbit generation. This ensures approximately Earth-like worlds are seeded throughout the simulation's habitable zone population, giving the LLM historian plausible colonisation targets.

### 3a. Spectral class filter

The filter applies to stars with:
- No entry in `StarOrbits` (no companion stars)
- Spectral type in the set: F5, F6, F7, F8, F9, G0, G1, G2, G3, G4, G5, G6, G7, G8, G9, K0, K1, K2, K3, K4, K5
- Luminosity class V (main sequence) only
- Not `system_id = 1030192` (Sol is handled separately)

This covers the "Goldilocks belt" of stellar types most likely to support long-duration main-sequence habitable zones. It excludes giant stars, subdwarfs, white dwarfs, very hot F stars, and cool K/M stars where tidal locking is near-inevitable at habitable distances.

### 3b. Near-Earth UWP template

The pre-placed world uses the following fixed parameters, drawn from WBH continuation-method logic:

*** Note. A: there muct e some variation, not exacltly terra (within recognized habitability limits for humans).  B: orbit placement dries temperature and must be adjusted to match the assigned values.

| Parameter | Value | Rationale |
|---|---|---|
| Orbit# | Computed HZCO ± 0.1D roll (max ±0.3) | Places world at or near the habitable zone centre |
| Size | 8 (fixed) | Earth-like diameter (12 000–13 599 km) |
| Diameter | 12 742 km (fixed to Terra) | Canonical value for Earth |
| Density | 1.00 (Rock and Metal, mid-table) | Terra standard |
| Gravity | 1.00 G | Derived |
| Mass | 1.00 ⊕ | Derived |
| Atmosphere code | 6 (Standard) | Breathable nitrogen-oxygen |
| Pressure | 1.0 bar | Terran standard |
| ppo | 0.21 bar | Terran oxygen partial pressure |
| Greenhouse factor | 0.59 | Terran value |
| Albedo | 0.30 | Terran value |
| Hydrographics code | 7 (66–75%) | Earth-like oceans |
| Hydro % | 71% | Earth surface water fraction |
| Eccentricity | 0.01–0.05 (1D×0.01) | Gently circular |
| Inclination | 0–5° (1D) | Low inclination |
| Axial tilt | 23° ± 5° (fixed range) | Seasonal but habitable |
| Day length | 24 hours (fixed) | Terran sidereal day as baseline |
| Tidal lock status | None (always free rotation) | F5–K5 at HZ distance, no lock |
| Seismic stress | Computed normally | Age/size/density driven |
| Biomass | 10+ (guaranteed non-zero) | Pre-biotic world flagged for life seeding |

The world is flagged with `source = 'continuation_seed'` in a new `Bodies.generation_source` column so it can be identified and filtered separately if needed.

### 3c. How normal generation proceeds after pre-seeding

After the continuation-seeded world is placed at its Orbit#:
1. The normal probabilistic orbit generator runs for the remaining slots in the system.
2. The pre-seeded world's Orbit# is treated as an **occupied slot** — no other world can be placed within ±spread/4 of it.
3. Gas giants, belts, and other terrestrials fill remaining slots normally.
4. The pre-seeded world does **not** participate in the baseline number or spread calculation — it is placed first and the remaining slots are distributed around it.

### 3d. Frequency note

As of the current catalog, the fraction of solitary F5–K5 V stars is approximately 8–12% of all catalog stars (several hundred thousand systems). This pre-seeding will create a rich population of colonisable worlds without hand-crafting each system.

---

## 4. WBH method summary

### 4a. Orbit# coordinate system

The WBH uses a logarithmic distance scale called **Orbit#** instead of raw AU:

The exact Orbit# ↔ AU mapping from the WBH availability table:

| Orbit# | AU | | Orbit# | AU |
|---|---|---|---|---|
| 0 | 0.20 | | 5.0 | 3.00 |
| 0.5 | 0.25 | | 5.5 | 4.00 |
| 1.0 | 0.40 | | 6.0 | 5.20 |
| 1.5 | 0.52 | | 6.5 | 7.20 |
| 2.0 | 0.65 | | 7.0 | 10.0 |
| 2.5 | 0.79 | | 7.5 | 14.0 |
| 3.0 | 0.97 | | 8.0 | 20.0 |
| 3.5 | 1.32 | | 8.5 | 30.0 |
| 4.0 | 1.60 | | 9.0 | 44.0 |
| 4.5 | 2.00 | | 9.5 | 58.5 |

Interpolation: linear between table entries. The lookup table is embedded as a sorted list in the generator; both directions are needed (`orbit_num_to_au`, `au_to_orbit_num`).

### 4b. System layout (replacing current orbit placement)

**Step 1 — World counts**

| Type | Roll | DMs |
|---|---|---|
| Gas giants present? | 2D: present on 9− | — |
| Gas giant quantity | See GG table | −1 per die if primary is M/K V or brown dwarf; −1 per die if spread < 0.1 |
| Planetoid belts | 2D ≥ 8: present; quantity via table | — |
| Terrestrials | 2D−2+DMs; minimum D3+2 if result < 3 | — |

**Step 2 — Minimum Allowable Orbit# (MAO)**

| Class | MAO |
|---|---|
| O, B | 3.5 |
| A | 3.0 |
| F | 2.5 |
| G | 2.0 |
| K | 1.5 |
| M V | 1.0 |
| M VI / brown dwarf | 0.5 |

For binary/multiple systems: additional exclusion zones apply around each companion star using the Hill sphere method. The outer exclusion zone for a companion at Orbit# C is `C + spread` inward (forbidden for primary-orbiting planets).

**Step 3 — Habitable Zone Center Orbit# (HZCO)**

```
HZCO_AU = sqrt(L_total)
HZCO    = au_to_orbit_num(HZCO_AU)
```

Where `L_total` = combined luminosity of all stars interior to the orbit.

**Step 4 — Baseline Orbit# and spread**

```
Baseline number  = 2D + DMs   (DMs: −1 per companion, +1 if solitary)
Baseline Orbit#  = HZCO ± deviation  (deviation: 1D×0.1 − 0.35, capped ±1.0)
Spread           = (Baseline Orbit# − MAO) / Baseline number
```

Minimum spread 0.05.

**Step 5 — Orbit slot assignment**

```
Orbit#(n) = MAO + spread × n     for n = 1 .. baseline_number
```

Then outward for additional worlds. Empty orbit rolls: 2D result 10 = 1 empty, 11 = 2, 12 = 3.

Anomalous orbit rolls (2D ≥ 11 per world):
- Eccentric orbit: add +2 DM to eccentricity roll
- Inclined orbit: inclination > 25°
- Retrograde orbit: inclination > 90°
- Trojan: shares orbit with adjacent world at ±60°

**Step 6 — World placement order**
1. Continuation-seeded mainworld (if applicable — see §3)
2. Gas giants (outermost slots first, fill inward)
3. Planetoid belts
4. Terrestrial planets

**Step 7 — Eccentricity**

Replace hard-cap with WBH Eccentricity Values table:

| 2D+DMs | e range |
|---|---|
| 2– | 0.00–0.04 |
| 3–6 | 0.05–0.09 |
| 7–8 | 0.10–0.14 |
| 9 | 0.15–0.19 |
| 10 | 0.20–0.29 |
| 11 | 0.30–0.39 |
| 12 | 0.40–0.49 |
| 13+ | 0.50–0.59 |

DMs: −2 for Orbit# < 1.5; +2 for anomalous eccentric flag; +4 for trojan. No hard cap; values > 0.6 are physically valid. Periapsis enforcement: if `a × (1−e) < R★ × 1.2`, reduce `e` to satisfy. Linear variance within range is used to get a precise value.

### 4c. Planet sizing (terrestrial)

Size code from roll, each code maps to a diameter band (1 600 km wide, 400 km for S):

| Size | Average km | Range |
|---|---|---|
| 0 | — | Planetoid belt |
| S | 600 | 400–799 |
| 1 | 1 600 | 800–2 399 |
| 2 | 3 200 | 2 400–3 999 |
| 3 | 4 800 | 4 000–5 599 |
| 4 | 6 400 | 5 600–7 199 |
| 5 | 8 000 | 7 200–8 799 |
| 6 | 9 600 | 8 800–10 399 |
| 7 | 11 200 | 10 400–11 999 |
| 8 | 12 800 | 12 000–13 599 |
| 9 | 14 400 | 13 600–15 199 |
| A | 16 000 | 15 200–16 799 |
| B | 17 600 | 16 800–18 399 |
| C | 19 200 | 18 400–19 999 |
| D | 20 800 | 20 000–21 599 |
| E | 22 400 | 21 600–23 199 |
| F | 24 000 | 23 200–24 799 |

Actual diameter within band: D3 roll (+0/+600/+1 200 km) then 1D adjustment (+0–+500 km); reroll if subtotal ≥ 1 600 km. d100 additive for km-level precision.

### 4d. Composition and density

**Terrestrial Composition** (2D + DM):

| 2D | Composition |
|---|---|
| −4 or less | Exotic Ice |
| −3 to 2 | Mostly Ice |
| 3–6 | Mostly Rock |
| 7–11 | Rock and Metal |
| 12–14 | Mostly Metal |
| 15+ | Compressed Metal |

DMs: −1 for Size 0–4; +1 for Size 6–9; +3 for Size A–F; +1 if at/inside HZCO; −1 per full Orbit# beyond HZCO; −1 if system age > 10 Gyr.

**Terrestrial Density** (2D lookup, column by composition, range 0.03–2.00 in units of Terra = 5.514 g/cm³).

**Derived chain:**

```
gravity       = density × (diameter_km / 12742)
mass_earth    = density × (diameter_km / 12742)³
escape_vel_ms = sqrt(mass_earth / (diameter_km / 12742)) × 11186
```

### 4e. Gas giant sizing

Three-step roll:
1. **1D** → category: 1–2 = GS, 3–4 = GM, 5–6 = GL
2. **Diameter** (by category): GS D3+D3 = 2–6×Terra; GM 1D+6 = 6–12×Terra; GL 2D+6 = 8–18×Terra
3. **Mass** (by category): GS 5×(1D+1) = 10–35⊕; GM 20×(3D−1) = 40–340⊕; GL D3×50×(3D+4) = 350–4 000⊕ (special correction at 3 000+)

### 4f. Significant moons

**Quantity roll base by planet Size:**

| Planet Size | Roll |
|---|---|
| 1–2 | 1D−5 |
| 3–9 | 2D−8 |
| A–F | 2D−6 |
| GS | 3D−7 |
| GM/GL | 4D−6 |

DM−1 per die if: Orbit# < 1.0; adjacent to companion exclusion zone; adjacent to Near/Far star outer range; Hill sphere < 60 PD. Result 0 = ring; < 0 = no moons.

**Hill sphere and Roche limit:**

```
hill_AU       = SMA_au × (1−ecc) × (m_earth × 3e−6 / (3 × M_solar))^(1/3)
hill_PD       = hill_AU × 149597870.9 / planet_diameter_km
moon_limit_PD = hill_PD / 2
roche_PD      = 1.537   # approximate (density ratio primary:secondary ≈ 2:1)
MOR           = floor(moon_limit_PD) − 2   # capped at 200+n_moons
```

If `moon_limit_PD < 1.5`: no moons (first moon → ring). If `< 0.5`: no rings.

**Moon orbital period:**

```
period_hours = 0.176927 × sqrt((PD × size_factor)³ / mass_planet_earth)
```

Where `size_factor = planet_diameter_km / 12742 × 8`.

Moon SMA in AU for storage: `SMA_km = PD × planet_diameter_km; SMA_AU = SMA_km / 149597870.9`.

### 4g. Atmosphere

1. **Habitable zone**: Roll 2D−7+Size. DM−2 for Size 2–4 (WBH variant).
2. **Non-habitable zone** (Orbit# > HZCO+1): Use WBH Non-Habitable Zone Atmosphere tables (Cold/Boiling atmosphere codes; exotic, corrosive, frozen, helium-dominated atmospheres).
3. **Pressure**: Determined from atmosphere code pressure span with linear dice variance.
4. **Greenhouse factor**: `gf_initial = 0.5 × sqrt(pressure_bar)`; then modified per Greenhouse Modifiers table (varies by atm code A/F/B/C/G/H; 3D×0.01 for standard codes).
5. **Albedo**: From Albedo Range table (rocky/icy/gas-giant baseline, modified by atmosphere code and hydrographics code). World type: rocky if density > 0.5, icy otherwise.
6. **Mean temperature** (replaces `surface_temp_k` and piecewise multipliers):
   ```
   mean_temp_K = 279 × (L × (1 − albedo) × (1 + greenhouse_factor) / AU²)^0.25
   ```
   For moons: use AU of parent planet, use combined luminosity of all interior stars.
7. **Hydrographics**: 2D−7+atm_code. DM−4 for atm codes 0/1/A+; DM−2 hot; DM−6 boiling. Outer system (WBH Method 2): drop DM−4 beyond HZCO+3, allow Size 1 rolls.
8. **ppo** (oxygen partial pressure): roll for N₂/O₂ atmosphere worlds (codes 2–9, D, E). System age > 4 Gyr: DM+1. Result × total pressure = ppo bar.

### 4h. Atmosphere subtypes — Taint

Applies to atmosphere codes 2, 4, 7, 9.

**Taint Subtype** (2D+DM table): Low Oxygen (L), Radioactivity (R), Biologic (B), Gas Mix (G), Particulates (P), Sulphur Compounds (S), High Oxygen (H). DM−2 for atm 4; DM+2 for atm 9. Result 10 = Particulates + roll again (up to 3 taints total).

**Taint Severity** (2D+DM, codes 1–9): Trivial irritant → Rapidly lethal (death in 1D minutes). DMs: +4 for High/Low oxygen; +6 for Atmosphere C.

**Taint Persistence** (2D+DM, codes 2–9): Occasional and brief → Constant. DMs: +4 for High/Low oxygen (further +2 if Severity 8+); +6 for Atmosphere C.

Store as three columns per taint slot: `taint_type_1`, `taint_severity_1`, `taint_persistence_1` (repeat for slots 2 and 3).

### 4i. Exotic atmosphere gas composition

For atmosphere codes A, B, C (and F-subtype), gas mix is determined by temperature zone and one or more rolls on the WBH Atmosphere Gas Mix Tables:

| Temperature zone | Table used |
|---|---|
| Mean temp > 453K | Boiling Gas Mix (HZCO −2.01 or worse) |
| Mean temp 353–453K | Boiling Gas Mix (HZCO −1.01 to −2.0) |
| Mean temp 303–353K | Hot Gas Mix |
| Mean temp 273–303K | Temperate Gas Mix |
| Mean temp 200–273K | Cold Gas Mix |
| Mean temp < 200K | Frozen Gas Mix |

Roll at minimum twice: primary component at (1D+4)×10% of mix, secondary components fill the remainder. Store result as a freeform string (e.g., `"N2:78,O2:21,Ar:1"`). A `gases` column (TEXT) in `Bodies` is sufficient.

### 4j. Day length (rotation period)

**Basic rotation rate:**

```
day_hours = (2D-2) × 4 + 2 + 1D + DMs
```

For gas giants and Size 0/S bodies: multiply base factor by 2 (faster rotation).

DMs: +1 per 2 Gyrs of system age (rounded down).

If result ≥ 40: roll 1D; on 5+ add another basic rotation rate iteration (chain). Slow rotators can reach hundreds to thousands of hours.

**Solar day** (from sidereal day and orbital period):

```
solar_days_in_year = period_hours / sidereal_day_hours − 1
solar_day_hours    = period_hours / solar_days_in_year
```

For retrograde rotation: sidereal day is negative, leading to longer solar days.

**Tidal lock check** — run after basic rotation. Uses Tidal Lock Status table (2D+DM):

| Result | Effect |
|---|---|
| 2− | No effect |
| 3–6 | Day × multiplier (1.5 to 5) |
| 7–8 | Prograde slow rotation (1D×5×24 or 1D×20×24 hours) |
| 9–10 | Retrograde slow rotation |
| 11 | 3:2 resonance lock |
| 12+ | 1:1 tidal lock (sidereal day = orbital period) |

**DMs (common to all lock cases):**
- +Size÷3 (round up)
- −ecc×10 (round down) if ecc > 0.1
- −2 if axial tilt > 30°; −4 if between 60°–120°
- −2 if pressure > 2.5 bar
- ±age modifiers (−2 if < 1 Gyr; +2 if 5–10 Gyr; +4 if > 10 Gyr)

**DMs for planet–star lock (base −4 + orbit-range DM):**
- Orbit# < 1: +14 to +4 (strong lock tendency)
- Orbit# 1–2: +4; Orbit# 2–3: +1; Orbit# > 3: −(floor Orbit#)×2
- Star mass DMs; companion star DM−n_stars; large moon DM

**DMs for moon–planet lock (base +6):**
- Moon orbit > 20 PD: −PD÷20; retrograde: −2
- Planet mass DMs: +2 to +8 depending on mass range

If tidal lock (1:1): axial tilt rerolled as (2D−2)÷10°; eccentricity rerolled with DM−2 and lower value kept.

Store: `sidereal_day_hours`, `solar_day_hours`, `tidal_lock_status` (TEXT: 'none'/'3:2'/'1:1'/'slow_prograde'/'slow_retrograde').

### 4k. Axial tilt

**Basic roll** (2D):

| 2D | Tilt range |
|---|---|
| 2–4 | (1D−1)÷50 → 0.0–0.10° |
| 5 | 1D÷5 → 0.2–1.2° |
| 6 | 1D → 1–6° |
| 7 | 6+1D → 7–12° |
| 8–9 | 5+1D×5 → 10–35° |
| 10+ | Roll on Extreme Axial Tilt table |

**Extreme Axial Tilt** (1D):

| 1D | Tilt | Notes |
|---|---|---|
| 1–2 | 10+1D×10 → 20–70° | High tilt |
| 3 | 30+1D×10 → 40–90° | Extreme tilt |
| 4 | 90+1D×1D → 91–126° | Retrograde rotation |
| 5 | 180−1D×1D → 144–180° | Extreme retrograde |
| 6 | 120+1D×10 → 130–180° | Extreme retrograde, high variance |

Axial tilt > 90° means retrograde rotation; treat as `180° − tilt` for axial tilt with negative sidereal day. Store `axial_tilt_deg` (REAL).

Note: tidal lock overrides axial tilt — if lock is 1:1 or 3:2 and tilt > 3°, reroll as `(2D−2)÷10°`.

### 4l. Seismic stress

Three components:

**Residual seismic stress:**
```
raw = Size − Age_Gyr + DMs
     DM+1 if world is a moon
     DM+1 per point of significant moon Size (max DM+12)
     DM+2 if density > 1.0
     DM-1 if density < 0.5
residual = max(0, floor(raw))²
```

**Tidal stress factor:**
```
tidal_stress = floor(Σ_tidal_effects_metres / 10)
```

Star tidal effect on planet (metres): `star_mass × planet_Size / (32 × AU³)`.
Moon/planet tidal effects: proportional formulae per WBH p.126.

**Tidal heating factor** (for moons with eccentric orbits):
```
heating = (primary_mass_earth² × world_Size⁵ × ecc²) /
          (3000 × dist_Mkm⁵ × period_days × world_mass_earth)
```

Ignore if result < 1.

**Total seismic stress:**
```
total_seismic = residual + tidal_stress + tidal_heating
```

**Temperature correction** (applies to mean/high/low temps):
```
new_temp_K = (old_temp_K⁴ + total_seismic⁴)^0.25
```

Negligible for HZ worlds but significant for rogue/outer bodies.

**Tectonic plates** (only if `total_seismic > 0` and `hydro_code ≥ 1`):
```
n_plates = max(1, Size + hydro_code − 2D + DMs)
     DM+1 if 10 ≤ total_seismic ≤ 100
     DM+2 if total_seismic > 100
```

Store: `seismic_residual` (REAL), `seismic_tidal` (REAL), `seismic_heating` (REAL), `seismic_total` (REAL), `tectonic_plates` (INTEGER, NULL if inactive).

### 4m. Biomass rating

Applicable to all worlds; determines presence and density of native life. Computed after all physical properties are set.

```
biomass = 2D + DMs   (clamped to DM range −12 to +4)
```

**Atmosphere DMs**: −6/−4/−3/−2/0/0/+2/−3/−5/−7/−5 for codes 0/1/2–3/4–5/6–7/8–9/D/A/B/C/F+.
**Hydrographics DMs**: −4/−2/0/+1/+2 for codes 0/1–3/4–5/6–8/9+.
**Age DMs**: −6 if < 0.2 Gyr; −2 if < 1 Gyr; +1 if > 4 Gyr.
**Temperature DMs**: −2 if high temp < 273K; −4 if mean temp < 273K; +2 if mean temp 279–303K; −2 if high temp > 353K; −4 if mean temp > 353K.

Result ≤ 0 → no native life. Result 1–9 → low to moderate life. Result A (10)+ → garden world.

Store: `biomass_rating` (INTEGER, NULL if no life check performed; 0 if confirmed absent).

### 4n. Planetoid belts

Per belt body:
- Belt span: `spread × (2D/10)` Orbit#s; DMs for adjacent gas giants and outermost position
- Composition: m-type/s-type/c-type percentages (2D+DM table, DM by distance from HZCO)
- Bulk: 2D² + age DM + composition DM
- Resource rating: 2D−7 + bulk + m-type DM − c-type DM
- Size 1 and Size S body counts (separate roll each, with bulk DMs)

---

## 5. Schema changes

### `Bodies` table additions

| Column | Type | Description |
|---|---|---|
| `generation_source` | TEXT | 'procedural' or 'continuation_seed' or 'manual' (Sol) |
| `orbit_num` | REAL | WBH Orbit# value |
| `size_code` | TEXT | UWP Size code (0–F, S, R, GS, GM, GL) |
| `diameter_km` | REAL | Actual diameter in km |
| `composition` | TEXT | Exotic Ice / Mostly Ice / Mostly Rock / Rock and Metal / Mostly Metal / Compressed Metal |
| `density` | REAL | Density relative to Terra (5.514 g/cm³ = 1.0) |
| `gravity_g` | REAL | Surface gravity in G |
| `mass_earth` | REAL | Mass in Earth masses (replaces `mass`) |
| `escape_vel_kms` | REAL | Escape velocity km/s |
| `albedo` | REAL | Bond albedo |
| `greenhouse_factor` | REAL | Computed greenhouse factor |
| `atm_code` | TEXT | Atmosphere code 0–H (replaces `atmosphere_type`) |
| `pressure_bar` | REAL | Atmospheric pressure in bar |
| `ppo_bar` | REAL | Oxygen partial pressure in bar |
| `gases` | TEXT | Exotic/corrosive/insidious gas mix (e.g., 'CO2:96,N2:4') |
| `taint_type_1` | TEXT | Taint subtype code (L/R/B/G/P/S/H), slot 1 |
| `taint_severity_1` | INTEGER | Taint severity 1–9, slot 1 |
| `taint_persistence_1` | INTEGER | Taint persistence 2–9, slot 1 |
| `taint_type_2` | TEXT | Taint slot 2 |
| `taint_severity_2` | INTEGER | Taint slot 2 |
| `taint_persistence_2` | INTEGER | Taint slot 2 |
| `taint_type_3` | TEXT | Taint slot 3 |
| `taint_severity_3` | INTEGER | Taint slot 3 |
| `taint_persistence_3` | INTEGER | Taint slot 3 |
| `mean_temp_k` | REAL | WBH mean temperature in Kelvin (replaces `surface_temp_k`) |
| `hydro_code` | INTEGER | Hydrographics code 0–10 |
| `hydro_pct` | REAL | Hydrographics percentage 0.0–1.0 |
| `sidereal_day_hours` | REAL | Rotation period (sidereal day) in hours |
| `solar_day_hours` | REAL | Solar day in hours (NULL if tidal lock 1:1) |
| `axial_tilt_deg` | REAL | Axial tilt in degrees (0–180) |
| `tidal_lock_status` | TEXT | 'none' / '3:2' / '1:1' / 'slow_prograde' / 'slow_retrograde' |
| `seismic_residual` | REAL | Residual seismic stress component |
| `seismic_tidal` | REAL | Tidal stress component |
| `seismic_heating` | REAL | Tidal heating component |
| `seismic_total` | REAL | Total seismic stress |
| `tectonic_plates` | INTEGER | Number of major tectonic plates (NULL if geologically dead) |
| `biomass_rating` | INTEGER | Native life biomass code (NULL = not checked; 0 = absent) |
| `moon_PD` | REAL | Moon orbit in planetary diameters (moons only) |
| `hill_PD` | REAL | Hill sphere in planetary diameters |
| `roche_PD` | REAL | Roche limit in planetary diameters |

Existing columns `semi_major_axis_au`, `eccentricity`, `inclination_deg`, `period_years` are retained. For moons, `semi_major_axis_au` is derived from `moon_PD` (not the primary stored value).

### `BeltProfile` table (new)

| Column | Type | Description |
|---|---|---|
| `body_id` | INTEGER | FK → Bodies |
| `span_orbit_num` | REAL | Belt half-width in Orbit#s |
| `m_type_pct` | INTEGER | Metallic body % |
| `s_type_pct` | INTEGER | Stony body % |
| `c_type_pct` | INTEGER | Carbonaceous body % |
| `other_pct` | INTEGER | Other body % |
| `bulk` | INTEGER | Belt bulk factor |
| `resource_rating` | INTEGER | Resource rating 2–12 |
| `size1_bodies` | INTEGER | Significant Size 1 body count |
| `sizeS_bodies` | INTEGER | Significant Size S body count |

---

## 6. Implementation plan

### Phase 0 — Backup and setup

1. `sqlite3 starscape.db ".backup starscape.db.bak"` — mandatory before any destructive run.
2. Add all new columns to `Bodies` and create `BeltProfile` as `ALTER TABLE` / schema migration.
3. Confirm `system_id = 1030192` guard logic is in place before running any generation.

### Phase 1 — Orbit placement rewrite (`generate_planets.py`)

1. Implement `orbit_num_to_au()` / `au_to_orbit_num()` lookup with linear interpolation.
2. Implement MAO lookup by spectral class + luminosity class.
3. Implement HZCO calculation from luminosity.
4. Implement baseline number, spread, empty/anomalous orbit rolls.
5. Generate ordered orbit slots per star, honouring companion exclusion zones.
6. For solitary F5–K5 V stars: run continuation-seed logic first (§3), mark body with `generation_source='continuation_seed'`.
7. Assign world types (GG, belt, terrestrial) to remaining slots per WBH placement order.
8. Assign eccentricity using WBH table (no hard cap; periapsis check enforced).
9. Assign inclinations: base 2D×2° prior; anomalous flag → 25–90°; retrograde flag → 90–180°.
10. Write results into `Bodies` with new Orbit#, diameter, composition, density chain.
11. Gas giant three-step sizing; store `size_code`, `diameter_km`, `mass_earth`.

### Phase 2 — Moon generation rewrite

1. Per planet, compute Hill sphere (planet mass, SMA, star mass).
2. Compute Roche limit in PD.
3. Roll moon quantity; apply DMs.
4. Check moon limit; convert to ring if below threshold.
5. Roll moon sizes.
6. Assign moon orbital PD values (Inner/Middle/Outer ranges); sort; assign designations a/b/c…
7. Compute moon SMA_AU and period_hours from PD and planet mass.
8. Roll moon eccentricity (DMs by zone); retrograde check.
9. Store in `Bodies` with `parent_body_id`, `moon_PD`, `hill_PD`, `roche_PD`.

### Phase 3 — Atmosphere and physical properties rewrite (`generate_atmosphere.py`)

1. Albedo per world (type + atmosphere + hydro modifiers).
2. Greenhouse factor per world.
3. Mean temperature from WBH formula.
4. Atmosphere code (HZ and non-HZ branches).
5. Pressure from code + variance.
6. ppo for N₂/O₂ worlds.
7. Exotic gas mix for codes A/B/C/F+ from gas mix tables by temperature zone.
8. Taint: subtype, severity, persistence (up to 3 taints).
9. Hydrographics code and percentage.
10. Store all atmosphere columns.

### Phase 4 — Rotation and tidal lock

1. Basic sidereal day: (2D−2)×4+2+1D+age DMs. Slow-rotation extension if ≥ 40.
2. Axial tilt: basic table → extreme table if needed.
3. Tidal lock check: compute DMs per all cases; roll Tidal Lock Status table.
4. If lock 1:1 or 3:2: update axial tilt and eccentricity per lock rules.
5. Solar day calculation.
6. Store `sidereal_day_hours`, `solar_day_hours`, `axial_tilt_deg`, `tidal_lock_status`.

### Phase 5 — Seismic stress and tectonics

1. Residual seismic stress: Size − Age + DMs, floor, square.
2. Tidal stress: sum of tidal amplitude effects ÷ 10.
3. Tidal heating: formula for eccentric moon/planet pairs.
4. Total seismic stress.
5. Temperature correction from seismic heating.
6. Tectonic plates: Size + Hydro − 2D + DMs (only if seismic > 0 and hydro ≥ 1).
7. Store all seismic columns.

### Phase 6 — Biomass rating

1. Roll 2D + all DMs for each world in or near the habitable zone.
2. Optionally roll for outer system worlds (single 2D roll per system, threshold 12+).
3. Store `biomass_rating`.

### Phase 7 — Belt profiles

1. For each Size-0 body, compute span, composition, bulk, resource rating, significant body counts.
2. Insert into `BeltProfile`.

### Phase 8 — Sol restoration

1. Delete all `Bodies` rows where `system_id = 1030192` and `generation_source != 'manual'`.
2. Re-run `scripts/seed_sol.py` to restore Mercury–Neptune, major moons, asteroid belt, Kuiper belt.
3. Set `generation_source = 'manual'` on all Sol bodies.
4. Verify: Earth body exists with `atm_code=6`, `hydro_code=7`, `mean_temp_k` ≈ 288, `biomass_rating` ≥ A.

### Phase 9 — Human homeworld invariant

1. Verify `ob_data.py` has Human polity's `homeworld_system_id = 1030192` hard-coded.
2. Verify `init_game.py` assertion: `human_polity.capital_system_id == 1030192`.
3. Add to `init_game.py` post-init check: confirm Earth body exists in system 1030192 and is flagged as the Human homeworld body.

### Phase 10 — Validation

1. **Eccentricity histogram**: no artefact at 0.97; no `e ≥ 1.0`.
2. **Periapsis check**: zero rows with `a × (1−e) < R★` in Bodies.
3. **Moon PD range**: sample 1 000 planets; all moon PD values within `[roche_PD, moon_limit_PD]`.
4. **Period sanity**: no moon with period > 1 year in inner system.
5. **Sol round-trip**: Earth `mean_temp_k` ≈ 288; Mars `mean_temp_k` ≈ 210; Jupiter orbital period ≈ 11.86 yr.
6. **HZCO check**: G2V solitary star → HZCO ≈ Orbit# 3.5 (1.32 AU).
7. **Atmosphere distribution**: no code-6 atmospheres beyond HZCO+2.
8. **Continuation seeds**: count of F5–K5 V solitary systems with `generation_source='continuation_seed'` ≈ expected fraction of catalog.
9. **Homeworld invariant**: `SELECT capital_system_id FROM Polity_head WHERE name LIKE '%Human%'` returns 1030192.
10. **Reference comparison**: five homeworld systems in `specs/system_orbital_data.md`; verify anomaly list (periapsis-inside-star, centuries-period moons) is cleared.

---

## 7. What is NOT changing

- Stellar physical data (`IndexedIntegerDistinctSystems`, `DistinctStarsExtended`) — untouched.
- `StarOrbits` companion orbit data — stellar orbit anomalies (35 888 inside Roche limit, unbound SMAs) are a separate issue and not addressed in this plan. The companion orbit generator needs its own fix pass.
- Game simulation tables — no game schema changes from this work.
- Planet/body naming conventions — not changed.
- `BodyMutable` columns for mutable atm/hydro state — the initial values are set from `Bodies` at game init; no schema change needed.

---

## 8. Scope and MOARN note

This plan covers all WBH physical characteristics sections in full, including the items previously deferred. The principle of MOARN (My Own Referee's Notes) applies strongly: the WBH procedures are detailed enough that they will produce 2.47 million systems with realistic diversity, but no Referee (or historian) will read every system. Richness of output is the goal; the data structure supports it without requiring it to be consumed.

The following items from the WBH are explicitly excluded from this pass:
- Detailed surface mapping (continent placement, hex terrain)
- Sophont species characteristics (handled by `Species` table separately)
- Trade codes, starport classification, population (game layer, not world generation)
- Detailed atmospheric chemistry for N₂/O₂ worlds beyond ppo (nitrogen/argon/CO₂ trace percentages)
- Ring profiles beyond count (ring centre/span in PD)

These can be added in a later pass without schema breaking changes.
