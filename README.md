# Starscape 5

A **fully autonomous 4X space civilisation simulator** — not a playable game. It runs as a background process and produces history. ~6 sophont species start simultaneously at interplanetary (pre-FTL) tech level on a 2000-parsec cube of real stellar data and expand, conflict, and evolve over ~40,000 simulated years. Output feeds an LLM historian.

Key design references: Mongoose Traveller world conventions; *Fifth Frontier War* fleet-level warfare abstraction; Hipparcos stellar catalog as the physical substrate.

---

## What this project is

Starscape 5 is a simulation engine, not a game. There is no player, no runtime UI, and no win condition. The simulator runs, logs history, and stops. A separate LLM historian step reads the event log and synthesises narrative.

The physical world — ~2.47 million stars, their planets, moons, belts, and atmospheres — is generated once from the Hipparcos catalog and held as a static baseline. Civilisation-layer changes (terraforming, population, colonisation, war) are stored as deltas against that baseline, never overwriting source rows.

---

## Current implementation status

| Component | Status |
|---|---|
| Fill stars (spectral/physical) | done |
| Orbit computation | done |
| Planet/moon/belt generation | done |
| Metrics computation | done |
| Atmosphere & surface conditions | impl — full DB run + sanity checks pending |
| Biosphere table | design — blocked on Species |
| SophontPresence | design — blocked on Species |
| TerraformProject | design — blocked on Species |
| Species table + seed script | design — 11 hand-authored rows ready; blocked on vocab finalisation |

See `specs/roadmap.md` for the authoritative status tracker.

---

## Database

**Location:** `/Volumes/Data/starscape4/sqllite_database/starscape.db` (external 2 TB drive)

| Table | Purpose | Status |
|---|---|---|
| `IndexedIntegerDistinctStars` | Source catalog: `star_id`, `system_id`, `hip`, `ci`, `absmag`, `spectral`, `source` | Populated |
| `DistinctStarsExtended` | Derived stellar physics: `mass`, `temperature`, `radius`, `luminosity`, `age` | Populated |
| `IndexedIntegerDistinctSystems` | System positions in milliparsecs (ICRS Cartesian x/y/z) | Populated |
| `StarOrbits` | Keplerian orbital elements for companion stars | Populated |
| `Bodies` | Planets, moons, belts, planetoids; physical + orbital columns | Populated |
| `BodyMutable` | Mutable atmosphere/hydro state per rocky body; updated each tick | Populated (initial) |
| `Biosphere` | Native/introduced life domains per body | Design only |
| `SophontPresence` | Sophont presence epochs per body | Design only |
| `TerraformProject` | Terraforming operations | Design only |
| `Species` | Sophont species definitions | Design only |

SQLite now; PostgreSQL migration planned for Linux production. All SQL is written to be compatible with both.

---

## Project layout

```
src/starscape5/
    atmosphere.py   — atmosphere/hydrosphere classification (pure functions)
    db.py           — SQLite connection helpers
    galaxy.py       — coordinate transforms
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
specs/
    roadmap.md              — canonical status tracker
    datadictionary.md       — authoritative field-level reference
    biosphere/              — BodyMutable, Biosphere, SophontPresence, TerraformProject specs
    worldgeneration/        — fill stars, orbits, planets, metrics specs
    GameDesign/
        greatspace4x.md     — top-level design decisions and open questions
        techtree.md         — tech tree DAG (6 domains)
sql/
    schema.sql              — CREATE TABLE statements (source of truth for schema)
articles/
    Species/                — hand-authored species lore articles
```

---

## Key design decisions

- **Time unit:** 1-week game ticks. Traveller-style phase ordering within each tick.
- **Scale:** ~2.47 M stars across a 2000-parsec cube; ~6 sophont species starting simultaneously, pre-FTL.
- **FTL:** Jump drive, 1–6 parsecs per jump. Information travels with ships (Traveller model). Information lag is structural.
- **Static baseline:** Physical/biological world data is immutable. Changes are stored as deltas — source rows are never modified.
- **Species scope:** ~40,000 yr horizon — no evolution or speciation. Cultural fracture → faction tables (future), not species fork.
- **Warfare:** Fleet-level abstraction modelled on *Fifth Frontier War*. Naval superiority is prerequisite for ground assault.
- **History logging:** All significant events logged at weekly tick/phase resolution. Quiet periods → monthly summary records.
- **No fixed end condition.** Supports graceful pause/resume and crash-safe recovery from last committed tick.

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

## Atmosphere classification

Priority waterfall on escape velocity and equilibrium temperature:

```
v_esc < 1.0      → none
v_esc < 3.0      → trace
t_eq  > 650 K    → corrosive
v_esc < 5.0      → thin
t_eq  < 120 K    → thin
tidal_lock       → thin (70%) | standard (30%)
in_hz = 1        → thin (10%) | standard (60%) | dense (30%)
otherwise        → thin (40%) | standard (45%) | dense (15%)
```

Greenhouse multiplier on surface temperature: `none/trace ×1.00 · thin ×1.05 · standard ×1.10 · dense ×1.25 · corrosive ×2.20`

Inner moons (< 0.01 AU from gas giant parent) receive +10–40 K tidal heating bonus.

---

## Setup

Requires Python ≥ 3.14 and [uv](https://github.com/astral-sh/uv).

```bash
git clone <repo>
cd starscape5
uv sync
```

---

## Usage

**Back up the database before any destructive run:**
```bash
sqlite3 starscape.db ".backup starscape.db.bak"
```

**Run any script:**
```bash
uv run scripts/<name>.py
```

Long-running scripts are resumable and accept `--max-minutes N`. Keep macOS awake for long runs:
```bash
caffeinate -i uv run scripts/generate_planets.py --max-minutes 600
```

**Run tests:**
```bash
uv run pytest
```

---

## Target environment

- Development: macOS (external 2 TB drive for DB)
- Production target: Dell XPS 13, i7, Ubuntu
