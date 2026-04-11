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
    world/
        facade.py   — WorldFacade Protocol + dataclasses (BodyData, SpeciesData, etc.)
        stub.py     — WorldStub (deterministic test double)
        impl.py     — WorldFacadeImpl (real starscape.db backend, M12)
        db.py       — open_world_ro / open_world_rw helpers
    game/
        db.py           — open_game, init_schema
        facade.py       — GameFacade Protocol + GameFacadeStub + GameFacadeImpl
        state.py        — GameState singleton; advance_phase / commit_phase
        polity.py       — Polity CRUD
        fleet.py        — Fleet / Hull / Squadron CRUD + combat helpers
        ground.py       — GroundForce CRUD
        presence.py     — SystemPresence CRUD
        control.py      — control_state lifecycle, growth cycles
        economy.py      — RU production, WorldPotential, BuildQueue, RepairQueue
        intelligence.py — SystemIntelligence, passive scan, map sharing
        movement.py     — execute_jump, arrivals, contacts
        combat.py       — space combat resolution (M9)
        bombardment.py  — orbital bombardment (M10)
        assault.py      — ground combat (M10)
        snapshot.py     — GameStateSnapshot builder (M11)
        posture.py      — strategic posture draw (M11)
        actions.py      — candidate generation + softmax selection (M11)
        war.py          — war initiation rolls (M11)
        action_executor.py — CandidateAction → DB writes (M11)
        log.py          — is_quiet_tick, write_monthly_summary (M13)
        events.py       — GameEvent append + query
        admiral.py      — Admiral commissioning
        names.py        — NameGenerator (species-specific)
        constants.py    — HULL_STATS, GROUND_STATS, etc.
        init_game.py    — full game initialiser from OB_DATA
        ob_data.py      — starting Orders of Battle for 11 species
    engine/
        intelligence.py — phase 1 runner
        decision.py     — phase 2 runner (real AI, M11)
        movement.py     — phase 3 runner
        combat.py       — phase 4 runner
        bombardment.py  — phase 5 runner
        assault.py      — phase 6 runner
        economy.py      — phase 8 runner
        control.py      — phase 7 runner
        log.py          — phase 9 runner (M13)
        tick.py         — run_partial_tick (all 9 phases, no advance/commit)
        simulation.py   — run_tick + run_simulation with crash-safe resume (M13)
scripts/
    seed_sol.py             — manually seeds Sol
    seed_species.py         — inserts 11 hand-authored species rows
    fill_spectral.py        — fills NULL spectral types; generates companion stars
    compute_metrics.py      — populates DistinctStarsExtended (resumable)
    compute_orbits.py       — populates StarOrbits
    generate_planets.py     — populates Bodies
    generate_atmosphere.py  — populates BodyMutable; back-fills 3 cols on Bodies
    analyze_completeness.py — diagnostic pipeline completeness tool
    run_sim.py              — CLI simulation runner (--ticks, --resume, --verbose)
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
        version1/
            implementation_plan.md — 13-milestone build plan (complete)
            game.md                — full game rules reference
sql/
    schema.sql              — starscape.db CREATE TABLE statements
    schema_game.sql         — game.db CREATE TABLE statements (source of truth)
```

---

## Implementation status

From `specs/roadmap.md` — keep this in sync:

| Component | Status |
|---|---|
| Fill stars / orbits / planets / metrics | `done` |
| Atmosphere & surface conditions | `impl` — run against full DB, verify sanity checks |
| Species table + seed | `done` — 11 rows seeded in starscape.db |
| Game schema + DB helpers | `done` |
| Polity / fleet / hull / ground / presence | `done` |
| Economy phase (M6) | `done` |
| Intelligence phase (M7) | `done` |
| Movement phase + contact detection (M8) | `done` |
| Space combat (M9) | `done` |
| Bombardment + ground assault (M10) | `done` |
| Decision engine — posture, candidates, war rolls (M11) | `done` |
| WorldFacadeImpl — real starscape.db (M12) | `done` |
| Log phase + full tick loop + crash-safe resume (M13) | `done` |
| First simulation run | `in progress` — `scripts/run_sim.py` |

---

## Immediate next steps (ordered by dependency)

1. **Validate first 500-tick run** — check wars, contacts, colonies; tune thresholds if needed
2. **Run `generate_atmosphere.py`** to completion against full DB (promotes to `done`)
3. **Run longer simulation** (5000+ ticks) to observe multi-polity dynamics
4. **Tech tree implementation** — after simulation produces stable history
5. **LLM historian pipeline** — point at `GameEvent` table once sufficient history exists

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
