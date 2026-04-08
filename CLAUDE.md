# Starscape 5 — CLAUDE.md

Persistent context for AI-assisted development. Read this before touching any code or spec.

---

## What this project is

A **fully autonomous 4X space civilisation simulator** — not a playable game. It runs as a background process and produces history. No runtime observer UI. ~6 sophont species start simultaneously at interplanetary (pre-FTL) tech level on a 2000-parsec cube of real stellar data and expand, conflict, and evolve over ~4×10⁴ simulated years. Output feeds an LLM historian.

Key design references: Mongoose Traveller world conventions; *Fifth Frontier War* fleet-level warfare abstraction; Hipparcos stellar catalog as the physical substrate.

---

## Database

**Location:** `/Volumes/Data/starscape4/sqllite_database/starscape.db` (external 2 TB drive)

| Table | Purpose | Status |
|---|---|---|
| `IndexedIntegerDistinctStars` | Source catalog: `star_id`, `system_id`, `hip`, `ci`, `absmag`, `spectral`, `source` | Populated |
| `DistinctStarsExtended` | Derived stellar physics: `mass`, `temperature`, `radius`, `luminosity`, `age`, `temp_source` | Populated |
| `IndexedIntegerDistinctSystems` | System positions in milliparsecs (ICRS Cartesian `x`,`y`,`z`); 1 mpc = 206.265 AU | Populated |
| `StarOrbits` | Keplerian orbital elements for companion stars; primary star has no row | Populated |
| `Bodies` | Planets, moons, belts, planetoids; physical + orbital columns; 3 derived cols added by generate_atmosphere.py | Populated |
| `BodyMutable` | Mutable atm/hydro state per rocky body; updated each tick | Populated (initial) |
| `Biosphere` | Native/introduced life domains per body | **Design only** |
| `SophontPresence` | Sophont presence epochs per body | **Design only** |
| `TerraformProject` | Terraforming operations | **Design only** |
| `Species` | Sophont species definitions | **Design only** |

`PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL` are set.

**SQLite now; PostgreSQL migration planned** when moving to Linux production. Write SQL that works on both — no SQLite-specific syntax.

---

## Project layout

```
src/starscape5/
    atmosphere.py   — atmosphere/hydrosphere classification (pure functions)
    db.py           — SQLite connection helpers
    galaxy.py       — coordinate transforms (eq_to_galactic_mpc())
    metrics.py      — mass, temperature, radius, luminosity, age derivations
    orbits.py       — orbital mechanics
    planets.py      — planet/moon/belt generation logic
    spectral.py     — B-V → spectral type, multiplicity helpers
scripts/
    seed_sol.py             — manually seeds Sol
    fill_spectral.py        — fills NULL spectral types; generates companion stars
    compute_metrics.py      — populates DistinctStarsExtended (resumable, time-limited)
    compute_orbits.py       — populates StarOrbits
    generate_planets.py     — populates Bodies
    generate_atmosphere.py  — populates BodyMutable; back-fills 3 cols on Bodies
    analyze_completeness.py — diagnostic pipeline completeness tool
    fill_stars.py           — (backfill utility)
specs/
    roadmap.md              — canonical status tracker; update it when things change
    datadictionary.md       — authoritative field-level reference
    biosphere/
        planetbiosphere.md  — BodyMutable, Biosphere, SophontPresence, TerraformProject
        species.md          — Species schema + 11 hand-authored species entries
    worldgeneration/        — fill stars, orbits, planets, metrics specs
    GameDesign/
        greatspace4x.md     — top-level design decisions and open questions
        techtree.md         — tech tree DAG (6 domains)
sql/
    schema.sql              — CREATE TABLE statements (source of truth for schema)
```

---

## Implementation status

From `specs/roadmap.md` — keep this in sync:

| Component | Status |
|---|---|
| Fill stars (spectral/physical) | `done` |
| Orbit computation | `done` |
| Planet/moon/belt generation | `done` |
| Metrics computation | `done` |
| Atmosphere & surface conditions (`generate_atmosphere.py`) | `impl` — run against full DB, verify Earth/Venus/Moon sanity checks |
| Biosphere table | `design` — blocked on Species |
| SophontPresence | `design` — blocked on Species |
| TerraformProject | `design` — blocked on Species |
| Species table + seed script | `design` — 11 hand-authored rows ready in spec; blocked on vocab finalisation |

---

## Immediate next steps (ordered by dependency)

1. Finalise controlled vocabularies for `body_plan`, `locomotion`, `atm_req`, `metabolic_rate` in `specs/biosphere/species.md`
2. Write `Species` CREATE TABLE into `sql/schema.sql`
3. Write `seed_species.py` to insert the 11 hand-authored rows
4. Promote `generate_atmosphere.py` to `done` — full DB run + sanity checks
5. Implement `Biosphere` + `SophontPresence` tables
6. Begin civilisation-layer spec: `Polity` table design

---

## Key design decisions

- **Time unit:** 1-week game ticks. Traveller-style phase ordering within each tick.
- **Scale:** ~2.47 M stars; ~6 sophont species starting simultaneously, pre-FTL.
- **FTL:** Jump drive, 1–6 parsecs per jump. Information travels with ships (Traveller model). Information lag is structural and unresolved for express routes.
- **Static baseline:** Physical/biological world data is immutable baseline. Changes (terraforming, population, native species status) are stored as deltas — never modify source rows.
- **Species scope:** ~4×10⁴ yr horizon — no evolution or speciation. Species table is static per entity. Cultural fracture → faction tables (future), not species fork.
- **Warfare:** Fleet-level abstraction modelled on *Fifth Frontier War*. Naval superiority prerequisite for ground assault.
- **History logging:** All significant events logged at weekly tick/phase resolution. Quiet periods → monthly summary records. LLM historian identifies decisive points.
- **No fixed end condition.** Must support graceful pause/resume and crash-safe recovery from last committed tick.

---

## Physical methods (stellar)

| Quantity | Method |
|---|---|
| Temperature | Ballesteros (2012) from B-V; spectral interpolation fallback; mass estimate last resort |
| Luminosity | `L/L☉ = 10^((4.83 − Mv)/2.5)` |
| Radius | Stefan-Boltzmann: `R/R☉ = √L × (5778/T)²` |
| Mass | Piecewise MS mass-luminosity inversion (Duric 2004); −1 signals error |
| Age | MS lifetime: `t ≈ 10¹⁰ × M/L` yr |
| Spectral type | B-V boundaries (OBAFGKM), subtype 0–9, luminosity class I/III/V from Mv |
| Multiplicity | Survey rates by spectral class (Raghavan 2010; Duchêne & Kraus 2013) |

---

## Atmosphere classification (implemented)

Priority waterfall on `escape_velocity_kms` and `t_eq_k`:
```
v_esc < 1.0      → 'none'
v_esc < 3.0      → 'trace'
t_eq  > 650 K    → 'corrosive'
v_esc < 5.0      → 'thin'
t_eq  < 120 K    → 'thin'
tidal_lock       → 'thin'(70%) | 'standard'(30%)
in_hz = 1        → 'thin'(10%) | 'standard'(60%) | 'dense'(30%)
otherwise        → 'thin'(40%) | 'standard'(45%) | 'dense'(15%)
```
Greenhouse multiplier on `t_eq_k → surface_temp_k`:
`none/trace ×1.00 · thin ×1.05 · standard ×1.10 · dense ×1.25 · corrosive ×2.20`

Inner moons (< 0.01 AU from GG parent) receive +10–40 K tidal heating bonus.

---

## Conventions

- Run scripts with `uv run scripts/<name>.py`
- Long-running scripts are **resumable** and accept `--max-minutes N`
- Back up database before destructive runs: `sqlite3 starscape.db ".backup starscape.db.bak"`
- Keep macOS awake: `caffeinate -i uv run scripts/...`
- Tests: `uv run pytest`
- `specs/roadmap.md` is the canonical status tracker — update status codes (`design`/`partial`/`impl`/`done`) when work advances
- `specs/datadictionary.md` is the authoritative field reference — add new fields there

---

## Target environment

- Development: macOS (external 2 TB drive for DB)
- Production target: Dell XPS 13, i7, Ubuntu
- Python ≥ 3.14, [uv](https://github.com/astral-sh/uv)
