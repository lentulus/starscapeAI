# Version 1 — Implementation Design

*Backing design for `game.md`. Controls implementation decisions for the
simulation engine.*

---

## Status

`design` — game design stable. Implementation not yet begun.

---

## Architectural principle: three layers, two databases

The simulation has three distinct areas of responsibility that must be
kept separate at both the schema and code level.

```
┌─────────────────────────────────────────────────────┐
│  starscape.db  (read-only during simulation)        │
│  ┌───────────────────────┐                          │
│  │  Static world model   │  Stars, systems, orbits, │
│  │                       │  Bodies, Species         │
│  └───────────────────────┘                          │
│  ┌───────────────────────┐                          │
│  │  Mutable world model  │  BodyMutable             │
│  │                       │  (terraforming, climate) │
│  └───────────────────────┘                          │
└─────────────────────────────────────────────────────┘
          read-only interface │
                              ▼
┌─────────────────────────────────────────────────────┐
│  game.db  (simulation writes here only)             │
│  ┌───────────────────────┐                          │
│  │  Game logic           │  Polities, fleets,       │
│  │                       │  combat, economy,        │
│  │                       │  events, intelligence    │
│  └───────────────────────┘                          │
└─────────────────────────────────────────────────────┘
```

**starscape.db** is never written to during simulation. It is the physical
substrate — the result of the world-generation pipeline. The simulation
engine opens it read-only.

**game.db** is the simulation's working database. All game state lives here.
It references starscape.db entities by ID (star_id, system_id, body_id,
species_id) but holds no FK constraints into starscape.db — the databases
are physically separate files.

**BodyMutable** stays in starscape.db. In Version 1 it is effectively static
(terraforming is deferred); the simulation reads it but does not write it.
When terraforming is implemented, writes will go through a world-update
pathway that is explicitly separated from game logic writes.

---

## Firewall rules

These are enforced by code structure, not just convention:

1. **`src/starscape5/world/`** — the only code that opens starscape.db.
   All reads of static and mutable world data pass through this package.
   Nothing in `world/` ever writes to any database.

2. **`src/starscape5/game/`** — owns game.db. Never opens starscape.db
   directly. Receives world data exclusively through `world/` interfaces.

3. **`src/starscape5/engine/`** — orchestrates tick phases. Never queries
   any database directly. Calls into `world/` and `game/` through their
   public interfaces.

4. **Cross-layer data flows as plain Python objects**, not DB connections.
   A `world/` function returns a dataclass or dict; a `game/` function
   consumes that object. No shared connection handles cross the boundary.

---

## Database: starscape.db (read-only)

Existing tables, unchanged by simulation:

| Table | Owner | Notes |
|---|---|---|
| `IndexedIntegerDistinctStars` | world-gen | Stellar catalog |
| `DistinctStarsExtended` | world-gen | Derived stellar physics |
| `IndexedIntegerDistinctSystems` | world-gen | System positions (milliparsecs) |
| `StarOrbits` | world-gen | Companion star orbital elements |
| `Bodies` | world-gen | All planets, moons, belts |
| `BodyMutable` | world-gen | Atmosphere/hydrosphere state |
| `Species` | seed script | Sophont species definitions |

The simulation engine opens this file with `sqlite3.connect(..., check_same_thread=False)` in read-only URI mode: `file:starscape.db?mode=ro`.

---

## Database: game.db

All tables below are created by `sql/schema_game.sql` and owned by the
simulation. The file does not exist before first initialisation.

### World cache

Derived once from starscape.db at initialisation and never recomputed unless
explicitly refreshed. Allows the simulation to run without repeatedly joining
across the inter-database boundary.

```sql
CREATE TABLE "WorldPotential" (
    "body_id"         INTEGER PRIMARY KEY,  -- FK into starscape Bodies (by convention)
    "system_id"       INTEGER NOT NULL,
    "world_potential" INTEGER NOT NULL,     -- pre-computed score; see economy rules
    "has_gas_giant"   INTEGER NOT NULL,     -- 1 if system has a GG; for refuel map
    "has_ocean"       INTEGER NOT NULL      -- 1 if body hydrosphere >= 0.5
);
```

One row per rocky body that could be a colonisation target, plus one
system-level row for refuelling flags. Populated at `init_game.py` time.

### Intelligence

Per-polity knowledge of each system. Enforces the three-tier knowledge model.

```sql
CREATE TABLE "SystemIntelligence" (
    "intel_id"        INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "system_id"       INTEGER NOT NULL,     -- starscape system_id
    "knowledge_tier"  TEXT NOT NULL CHECK(knowledge_tier IN ('passive','visited')),
    "first_visit_tick" INTEGER,             -- NULL for passive-only
    "last_visit_tick"  INTEGER,             -- NULL for passive-only
    "gas_giant"       INTEGER,              -- known from passive range
    "ocean_body"      INTEGER,              -- known from passive range
    -- Full world data below: NULL until visited
    "world_potential" INTEGER,
    "atm_type"        TEXT,
    "surface_temp_k"  REAL,
    "hydrosphere"     REAL,
    "habitable"       INTEGER,              -- 1 if compatible with polity's species
    UNIQUE(polity_id, system_id)
);
```

### Polities and relationships

```sql
CREATE TABLE "Polity" (
    "polity_id"       INTEGER PRIMARY KEY,
    "species_id"      INTEGER NOT NULL,     -- starscape Species.species_id
    "name"            TEXT NOT NULL,
    "capital_system_id" INTEGER,
    "treasury_ru"     REAL NOT NULL DEFAULT 0,
    -- Disposition: copied from Species at founding; may drift later
    "expansionism"    REAL NOT NULL,
    "aggression"      REAL NOT NULL,
    "risk_appetite"   REAL NOT NULL,
    "founded_tick"    INTEGER NOT NULL DEFAULT 0,
    "processing_order" INTEGER NOT NULL,   -- fixed polity sequence within each phase
    "status"          TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active','eliminated','vassal'))
);

CREATE TABLE "ContactRecord" (
    "contact_id"      INTEGER PRIMARY KEY,
    "polity_a_id"     INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "polity_b_id"     INTEGER NOT NULL REFERENCES "Polity"("polity_b_id"),
    "contact_tick"    INTEGER NOT NULL,
    "contact_system_id" INTEGER NOT NULL,
    "peace_weeks"     INTEGER NOT NULL DEFAULT 0,  -- consecutive weeks without war
    "at_war"          INTEGER NOT NULL DEFAULT 0,
    "map_shared"      INTEGER NOT NULL DEFAULT 0,  -- 1 once 52-week exchange fired
    UNIQUE(polity_a_id, polity_b_id),
    CHECK(polity_a_id < polity_b_id)               -- canonical ordering; no duplicates
);

CREATE TABLE "WarRecord" (
    "war_id"          INTEGER PRIMARY KEY,
    "polity_a_id"     INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "polity_b_id"     INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,       -- generated at declaration
    "declared_tick"   INTEGER NOT NULL,
    "initiator_id"    INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "ended_tick"      INTEGER             -- NULL while active
);
```

### System presence

```sql
CREATE TABLE "SystemPresence" (
    "presence_id"     INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "system_id"       INTEGER NOT NULL,
    "body_id"         INTEGER NOT NULL,   -- which body is the foothold
    "control_state"   TEXT NOT NULL CHECK(control_state IN
                          ('outpost','colony','controlled','contested')),
    "development_level" INTEGER NOT NULL DEFAULT 0 CHECK(development_level BETWEEN 0 AND 5),
    "colonist_deliveries" INTEGER NOT NULL DEFAULT 0,  -- cumulative; tracks upgrade eligibility
    "has_shipyard"    INTEGER NOT NULL DEFAULT 0,
    "has_naval_base"  INTEGER NOT NULL DEFAULT 0,
    "growth_cycle_tick" INTEGER,          -- tick of next 25-week growth check
    "established_tick" INTEGER NOT NULL,
    "last_updated_tick" INTEGER NOT NULL
);
```

### Fleets, squadrons, and hulls

Every warship is individually tracked. Warships of the same type are grouped
into squadrons; squadrons of different types form a fleet. The squadron is
the tactical unit in combat.

```
Fleet
 └── Squadron (same hull type, 2–4 ships)
      └── Hull (individual ship)
```

Non-combat hulls (Scout, Colony transport, Troop, Transport) are individually
tracked but not organised into squadrons — they travel with a fleet or
independently.

```sql
CREATE TABLE "Fleet" (
    "fleet_id"        INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,
    "system_id"       INTEGER,            -- NULL if in transit
    "destination_system_id" INTEGER,      -- NULL if stationary
    "destination_tick" INTEGER,           -- arrival tick
    "admiral_id"      INTEGER REFERENCES "Admiral"("admiral_id"),
    "supply_ticks"    INTEGER NOT NULL DEFAULT 0,  -- ticks since last resupply
    "status"          TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active','in_transit','destroyed'))
);

-- Squadron: same-type warships grouped as the tactical unit.
-- Combat role is set at start of each engagement; may change between battles.
CREATE TABLE "Squadron" (
    "squadron_id"     INTEGER PRIMARY KEY,
    "fleet_id"        INTEGER REFERENCES "Fleet"("fleet_id"),  -- NULL if detached/SDB group
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,
    "hull_type"       TEXT NOT NULL CHECK(hull_type IN
                          ('capital','old_capital','cruiser','escort','sdb')),
    "combat_role"     TEXT NOT NULL DEFAULT 'line_of_battle'
                      CHECK(combat_role IN ('screen','line_of_battle','reserve')),
    "system_id"       INTEGER,            -- mirrors fleet location; set directly for SDB squadrons
    "status"          TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active','destroyed'))
);

-- Every warship: one row per hull.
-- All hull types including transports and support vessels.
CREATE TABLE "Hull" (
    "hull_id"         INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,
    "hull_type"       TEXT NOT NULL CHECK(hull_type IN (
                          'capital','old_capital','cruiser','escort',
                          'troop','transport','colony_transport','scout','sdb')),
    "squadron_id"     INTEGER REFERENCES "Squadron"("squadron_id"),
                                          -- NULL for non-combat hulls not in squadron
    "fleet_id"        INTEGER REFERENCES "Fleet"("fleet_id"),
                                          -- set for all fleet members; NULL for solo/SDB
    "system_id"       INTEGER,
    "destination_system_id" INTEGER,
    "destination_tick" INTEGER,
    "status"          TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN (
                          'active','damaged','establishing','in_transit','destroyed')),
    "marine_designated" INTEGER NOT NULL DEFAULT 0,  -- 1 if Army aboard designated for assault
    "cargo_type"      TEXT CHECK(cargo_type IN ('ru','colonists','army','sdb',NULL)),
    "cargo_id"        INTEGER,            -- hull_id of carried SDB, or NULL
    "establish_tick"  INTEGER,            -- tick when SDB becomes active
    "created_tick"    INTEGER NOT NULL
);
```

**Squadron combat roles:**

| Role | Typical hull types | Function |
|---|---|---|
| `screen` | Escort, sometimes Cruiser | First contact; absorbs opening fire; broken screen exposes line |
| `line_of_battle` | Capital, Old Capital, Cruiser | Main strength exchange |
| `reserve` | Any | Held back; committed by admiral decision mid-battle |

SDB squadrons are always `screen` for the defending side and cannot be
assigned a different role.

**Combat sequence:**
1. Screen squadrons engage first. Broken screen (all hulls damaged/destroyed)
   means opposing line fights line directly next round with an attack bonus.
2. Line squadrons exchange fire. Strength totals computed, admiral tactical
   factor applied, 2d6 net shift to damage table.
3. Reserve commitment is an admiral tactical decision (see tactical decisions
   in game.md). Positive tactical factor = right moment; negative = poor timing.
4. After each exchange: disengage evaluation, then next round or battle ends.

### Admirals

```sql
CREATE TABLE "Admiral" (
    "admiral_id"      INTEGER PRIMARY KEY,  -- global sequence; lower = more senior within polity
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,
    "tactical_factor" INTEGER NOT NULL CHECK(tactical_factor BETWEEN -3 AND 3),
    "fleet_id"        INTEGER REFERENCES "Fleet"("fleet_id"),
    "created_tick"    INTEGER NOT NULL,
    "status"          TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active','killed','captured'))
);
```

### Ground forces

Each formation is individually tracked. Strength is a rating 1–6; below 2
the formation is combat-ineffective and must refit. Garrison formations are
fixed at creation and cannot move.

```sql
CREATE TABLE "GroundForce" (
    "force_id"        INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "name"            TEXT NOT NULL,
    "unit_type"       TEXT NOT NULL CHECK(unit_type IN ('army','garrison')),
    "strength"        INTEGER NOT NULL CHECK(strength BETWEEN 0 AND 6),
    "max_strength"    INTEGER NOT NULL DEFAULT 6,
    -- Location: on a body, or embarked on a hull
    "system_id"       INTEGER,            -- NULL if in transit with fleet
    "body_id"         INTEGER,            -- NULL if embarked
    "embarked_hull_id" INTEGER REFERENCES "Hull"("hull_id"),
                                          -- NULL if on ground; set for Troop/Transport
    -- Flags
    "marine_designated" INTEGER NOT NULL DEFAULT 0,
                                          -- 1 = trained for hot-entry assault;
                                          -- no first-round penalty when landing
    "occupation_duty" INTEGER NOT NULL DEFAULT 0,
                                          -- 1 = holding conquered non-homeworld;
                                          -- maintenance ×1.5
    "refit_ticks_remaining" INTEGER NOT NULL DEFAULT 0,
                                          -- >0 = non-combat; recovering strength
    "created_tick"    INTEGER NOT NULL,
    "last_updated_tick" INTEGER NOT NULL
);
```

**Strength scale:**

| Strength | State |
|---|---|
| 6 | Full strength; consolidated formation |
| 5 | Combat-effective; minor losses |
| 4 | Starting strength for newly raised formation |
| 3 | Weakened; still combat-effective |
| 2 | Minimum combat-effective |
| 1 | Combat-ineffective; must refit |
| 0 | Destroyed or captured |

**Marine designation:** Any Army formation can be marine-designated (flag set
at creation or by polity decision). Non-designated formations take −1 strength
in the first ground combat round when assaulting from orbit (unprepared for
hot entry). Marine designation has no effect on defensive operations.

**Occupation duty modifier:** A formation holding a conquered
species-incompatible world pays 1.5× maintenance. Species-compatible worlds
return to normal maintenance once control state reaches Colony.

**Garrison defensive bonus:** Garrison formations fight at effective strength
×1.5 in their prepared positions. A Garrison that is overrun is destroyed in
place; Garrison formations cannot retreat or embark.

### Build and repair queues

```sql
CREATE TABLE "BuildQueue" (
    "queue_id"        INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "system_id"       INTEGER NOT NULL,
    "hull_type"       TEXT NOT NULL,      -- any hull type or 'army'/'garrison'
    "ticks_total"     INTEGER NOT NULL,
    "ticks_elapsed"   INTEGER NOT NULL DEFAULT 0,
    "reserved_ru"     REAL NOT NULL,
    "ordered_tick"    INTEGER NOT NULL
);

CREATE TABLE "RepairQueue" (
    "repair_id"       INTEGER PRIMARY KEY,
    "hull_id"         INTEGER NOT NULL REFERENCES "Hull"("hull_id"),
    "system_id"       INTEGER NOT NULL,   -- must have shipyard
    "ticks_total"     INTEGER NOT NULL DEFAULT 4,
    "ticks_elapsed"   INTEGER NOT NULL DEFAULT 0,
    "cost_ru"         REAL NOT NULL
);
```

### Economy log

Append-only. Never updated in-place; new rows written each Economy phase.

```sql
CREATE TABLE "SystemEconomy" (
    "economy_id"      INTEGER PRIMARY KEY,
    "tick"            INTEGER NOT NULL,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "system_id"       INTEGER NOT NULL,
    "ru_produced"     REAL NOT NULL,
    "ru_maintenance"  REAL NOT NULL,
    "ru_construction" REAL NOT NULL,
    "treasury_after"  REAL NOT NULL
);
```

### Event log

Append-only. The LLM historian's primary source.

```sql
CREATE TABLE "GameEvent" (
    "event_id"        INTEGER PRIMARY KEY,
    "tick"            INTEGER NOT NULL,
    "phase"           TEXT NOT NULL,
    "event_type"      TEXT NOT NULL,      -- 'contact'|'war_declared'|'combat'|
                                          -- 'control_change'|'fleet_destroyed'|
                                          -- 'disengage'|'pursuit'|'bombardment'|
                                          -- 'colony_established'|'admiral_commissioned'|
                                          -- 'map_shared'|'summary'
    "polity_a_id"     INTEGER REFERENCES "Polity"("polity_id"),
    "polity_b_id"     INTEGER REFERENCES "Polity"("polity_id"),
    "system_id"       INTEGER,
    "body_id"         INTEGER,
    "admiral_id"      INTEGER REFERENCES "Admiral"("admiral_id"),
    "summary"         TEXT NOT NULL,      -- human-readable; LLM historian input
    "detail"          TEXT               -- JSON payload for structured data
);
CREATE INDEX "idx_event_tick" ON "GameEvent"("tick");
CREATE INDEX "idx_event_type" ON "GameEvent"("event_type");
```

---

## Python module structure

```
src/starscape5/
│
├── world/                      — starscape.db access layer; lazy generation
│   ├── __init__.py
│   ├── db.py                   — connection factory; writable (generation only)
│   ├── systems.py              — system/star queries; position, distance
│   ├── bodies.py               — Bodies + BodyMutable queries
│   ├── species.py              — Species queries; habitability checks
│   ├── potential.py            — world_potential score from Bodies/BodyMutable
│   └── resolver.py             — on-demand generation; resolve(system_id) entry
│                                 point; calls planets/atmosphere/metrics as needed;
│                                 writes to starscape.db and WorldPotential cache
│
├── game/                       — game.db layer; all simulation state
│   ├── __init__.py
│   ├── db.py                   — connection factory; schema creation
│   ├── init.py                 — first-run initialisation; populates WorldPotential cache
│   ├── polity.py               — Polity, ContactRecord, WarRecord
│   ├── intelligence.py         — SystemIntelligence; knowledge tier management;
│   │                             passive scan (20pc range); map-sharing at 52 weeks
│   ├── fleet.py                — Fleet; movement; supply tracking
│   ├── squadron.py             — Squadron; combat role assignment; strength totals
│   ├── hull.py                 — Hull; all individual ships; damage state; cargo
│   ├── admiral.py              — Admiral generation (species-biased); seniority;
│   │                             combined command resolution
│   ├── ground.py               — GroundForce; embark/disembark; garrison
│   ├── presence.py             — SystemPresence; control state transitions;
│   │                             25-week growth cycle
│   ├── economy.py              — RU production; maintenance; build queues;
│   │                             repair queues; treasury
│   └── events.py               — GameEvent writes; summary compression
│
├── names/                      — name generation; culture-neutral interface
│   ├── __init__.py
│   ├── generator.py            — NameGenerator class; species-aware entry point
│   ├── codes.py                — current implementation: structured code strings
│   └── culture/                — future: per-species naming conventions
│       └── __init__.py
│
└── engine/                     — tick orchestration; no direct DB access
    ├── __init__.py
    ├── tick.py                 — 9-phase tick driver; calls phase modules in order
    ├── intelligence_phase.py   — Phase 1: scout reports; passive scan; 52-week check
    ├── decision_phase.py       — Phase 2: polity decision engine; order generation
    ├── movement_phase.py       — Phase 3: fleet movement; SDB delivery; contact detect
    ├── combat_phase.py         — Phase 4: space combat; admiral selection; damage
    ├── bombardment_phase.py    — Phase 5: orbital bombardment
    ├── assault_phase.py        — Phase 6: ground combat
    ├── control_phase.py        — Phase 7: control state update; growth cycle
    ├── economy_phase.py        — Phase 8: RU collection; queues; maintenance
    ├── log_phase.py            — Phase 9: event log; monthly summary check
    ├── decision/
    │   ├── posture.py          — posture probability draw by disposition
    │   ├── scoring.py          — action utility scoring
    │   └── selector.py        — soft-random action selection
    └── tactics/
        ├── engage.py           — engage-or-hold decision
        ├── disengage.py        — per-exchange disengage evaluation
        ├── pursuit.py          — pursuit decision
        └── retreat.py          — retreat destination selection
```

---

## On-demand world generation

The starscape.db stellar catalog contains ~2.47 million stars. Pre-generating
planets and orbital details for all of them at initialisation is not feasible.
World data is generated **lazily** as the simulation's zone of knowledge
expands — when a scout or fleet first approaches a system close enough to
resolve it.

This is entirely internal to the `world/` layer. The `game/` layer and
`engine/` never see the difference between a system that was pre-seeded and
one that was generated on demand five minutes ago. From outside `world/`, a
system either has data or it doesn't; if it doesn't, `world/` generates and
caches it before returning.

### Trigger

On-demand generation fires in two situations:

1. **Scout or fleet enters a system** — full planet/moon/belt generation for
   that system runs immediately before the visit is recorded.
2. **Passive 20-parsec scan** — for each system within passive range of a
   newly-established Controlled presence, `world/` checks whether the gas
   giant and ocean flags are known. If not, it runs a lightweight scan:
   enough to determine GG-present and ocean-present without generating full
   body details. Full details are deferred until a visit.

### What gets generated when

| Trigger | Generated |
|---|---|
| Passive 20pc scan (new system) | Star metrics (if missing), GG flag, ocean flag — no Bodies rows yet |
| Scout or fleet visits | Full Bodies generation (planets, moons, belts), BodyMutable for all rocky bodies, star metrics if not already present |

### Where it lives

All generation logic already exists in the pipeline scripts:
`generate_planets.py`, `generate_atmosphere.py`, `compute_metrics.py`.
The `world/` layer will call the same underlying functions from
`src/starscape5/planets.py`, `src/starscape5/atmosphere.py`, and
`src/starscape5/metrics.py` — no new generation logic is written; the
pipeline functions are called on demand and their results written to
starscape.db.

**starscape.db is writable by `world/` only for this purpose.** The
read-only rule for the simulation is relaxed specifically for on-demand
generation writes by the `world/` layer; no other layer ever writes to
starscape.db.

### Concurrency note

On-demand generation must complete and commit to starscape.db before
`world/` returns the result to the caller. The game engine sees a
synchronous interface: request system data, receive system data. The write
to starscape.db and the population of the `WorldPotential` cache in game.db
are part of the same operation, wrapped in a helper:

```
world.systems.resolve(system_id)
  → checks if Bodies rows exist for system_id
  → if not: generates planets, atmosphere, writes to starscape.db
  → populates WorldPotential cache row in game.db
  → returns body data to caller
```

This function is the only place where both database connections are held
open simultaneously. It is explicitly the exception to the "no shared
connections" rule and is documented as such.

---

## Cross-database access pattern

The `world/` layer and `game/` layer each hold their own connection. They
never share a connection handle. Data crosses the boundary as Python objects.

```python
# Correct: world layer returns a dataclass
body_data = world.bodies.get_body(body_id)          # reads starscape.db
potential = world.potential.compute(body_data)       # pure function

# Correct: game layer consumes the result
game.economy.set_world_potential(body_id, potential) # writes game.db

# Wrong: never do this
game.db.execute("ATTACH 'starscape.db' AS world")   # no ATTACH across layers
```

SQLite `ATTACH DATABASE` is explicitly prohibited for cross-layer joins.
If a query seems to need it, the answer is to pre-cache the world data in
`WorldPotential` or `SystemIntelligence` rather than joining at query time.

The single documented exception is `world.resolver.resolve()`, which holds
both database connections simultaneously to perform on-demand generation.
This function is the explicit, contained crossing point — it exists precisely
so that nothing else ever needs to.

---

## Initialisation sequence (`init_game.py`)

Runs once to create game.db and populate starting state.

1. Open starscape.db read-only; open (create) game.db
2. Create all game.db tables from `sql/schema_game.sql`
3. Populate `WorldPotential` cache for all Bodies rows
4. Populate `SystemIntelligence` passive tier for each polity's starting
   systems (homeworld and all systems within 20 parsecs)
5. Create `Polity` rows from Species; apply faction-tendency multi-polity
   rule (> 0.85 → multiple polities)
6. Create starting `SystemPresence` for each homeworld (Controlled/dev-3)
7. Create starting fleets, `FleetComposition`, and individually-tracked `Hull`
   rows from the starting OB
8. Generate starting admirals (one per primary fleet) using species-biased
   tactical factor procedure
9. Create starting `GroundForce` rows (Army + Garrison per OB)
10. Write tick-0 `GameEvent` rows for all starting entities
11. Set each polity's `treasury_ru` to starting value

---

## Naming

Every entity the simulation generates or discovers should have a name. Names
serve the event log and the LLM historian — "Fleet 7 attacked System 14291"
is unreadable; "the Vardhek Third Cohort engaged the Skharri Pride of Keth
at Rimward-7" is history.

Names are generated at entity creation by a `NameGenerator` that currently
produces structured codes. The generator interface is designed so that
per-culture naming standards can be substituted later without touching
anything else.

### Named entities

| Entity | Name lives in | Notes |
|---|---|---|
| `Polity` | `Polity.name` | Set at founding |
| `Fleet` | `Fleet.name` | Generated at fleet creation |
| `Admiral` | `Admiral.name` | Generated at commissioning |
| `Hull` (individual) | `Hull.name` | Scouts, colony transports, SDBs each get a name |
| System (star/system) | `PlaceName` table | Per-polity; each polity names what it discovers |
| Body (planet/moon) | `PlaceName` table | Per-polity |
| War | `WarRecord.name` | Generated when war is declared |

### PlaceName table

Systems and bodies live in starscape.db and cannot carry game-side names
there. Names are stored in game.db as a per-polity mapping so that two
polities can have different names for the same place — which they will, once
they make contact without sharing a language.

```sql
CREATE TABLE "PlaceName" (
    "name_id"         INTEGER PRIMARY KEY,
    "polity_id"       INTEGER NOT NULL REFERENCES "Polity"("polity_id"),
    "object_type"     TEXT NOT NULL CHECK(object_type IN ('system','body')),
    "object_id"       INTEGER NOT NULL,   -- system_id or body_id from starscape.db
    "name"            TEXT NOT NULL,
    "assigned_tick"   INTEGER NOT NULL,
    UNIQUE(polity_id, object_type, object_id)
);
```

The LLM historian resolves names by polity perspective — events are narrated
using the names the polity involved assigned to the locations. Shared names
(after the 52-week map exchange) are also shared names culturally; the
historian can note when two polities use different names for the same place.

### Name generator

```
src/starscape5/names/
    __init__.py
    generator.py     — NameGenerator class; produces names for any entity type
    codes.py         — current implementation: structured code strings
    culture/         — future: per-species naming conventions
        __init__.py
        human.py     — (future) human naming by polity flavour
        vardhek.py   — (future) Roidhunate naming conventions
        ...
```

`NameGenerator` is initialised with a species_id and an optional culture
parameter. Currently it delegates entirely to `codes.py`. The interface is:

```python
gen = NameGenerator(species_id=5)   # Skharri
gen.fleet(polity_name, sequence)    # → "SKH-FL-0003"
gen.admiral(sequence)               # → "SKH-ADM-0017"
gen.system(system_id, sequence)     # → "SKH-SYS-14291"
gen.body(body_id, sequence)         # → "SKH-BDY-88042-I"
gen.war(polity_a, polity_b, tick)   # → "SKH-WAR-0421-001"
gen.hull(hull_type, sequence)       # → "SKH-SCT-0004"
```

### NamePool table

Names are pre-generated and stored in game.db at initialisation. The
generator draws from the pool and marks entries used. When the pool for a
type runs dry it falls back to structured codes.

```sql
CREATE TABLE "NamePool" (
    "name_id"         INTEGER PRIMARY KEY,
    "species_id"      INTEGER NOT NULL,   -- starscape Species.species_id
    "name_type"       TEXT NOT NULL CHECK(name_type IN (
                          'person','system','body','fleet','war','polity')),
    "name"            TEXT NOT NULL,
    "used"            INTEGER NOT NULL DEFAULT 0,
    "used_by_id"      INTEGER,            -- entity_id that consumed this name
    "used_tick"       INTEGER,
    UNIQUE(species_id, name_type, name)
);
CREATE INDEX "idx_namepool_available"
    ON "NamePool"(species_id, name_type, used);
```

Populated by `scripts/seed_names.py` from `specs/GameDesign/version1/name_pools.md`
before the first simulation run.

### Code format (current implementation)

All codes follow `[SPECIES]-[TYPE]-[SEQUENCE]`. Species prefix is a 3-letter
abbreviation of the polity's species name. Sequence is zero-padded to 4
digits. Body codes append a Roman numeral for orbital position within the
system.

This produces unambiguous, log-readable identifiers immediately. When
per-culture naming is implemented, codes become fallback names for entities
generated before the culture module existed.

### Naming conventions for the historian

The event log stores the name string at the time of the event. Names do not
retroactively update if a place is renamed — the historian sees history as
it was narrated, which is the correct behaviour for a historical record.

---

## Simulation state and crash-safe resume

### GameState table

A single-row table tracks the current position in the simulation. This is
the authoritative resume point after a crash or pause.

```sql
CREATE TABLE "GameState" (
    "state_id"            INTEGER PRIMARY KEY CHECK(state_id = 1),  -- singleton
    "current_tick"        INTEGER NOT NULL DEFAULT 0,
    "current_phase"       INTEGER NOT NULL DEFAULT 0,  -- 1–9; 0 = between ticks
    "started_at"          TEXT NOT NULL,               -- wall-clock ISO timestamp
    "last_committed_at"   TEXT NOT NULL,               -- wall-clock ISO timestamp
    "last_committed_tick" INTEGER NOT NULL DEFAULT 0,
    "last_committed_phase" INTEGER NOT NULL DEFAULT 0
);
```

### Commit granularity: per phase

The simulation commits to game.db **after each phase completes** — not after
each polity within a phase, and not after the full tick.

Rationale:

- **Phases are the natural atomic unit.** Each phase has clear preconditions
  (prior phase complete) and postconditions (state ready for next phase).
  Phases within a tick are strictly sequential and interdependent.
- **Combat cannot be split by polity.** A combat engagement between Polity A
  and Polity B produces a single result affecting both. Committing after
  "Polity A's combat" would leave the database in an inconsistent state.
  Per-polity commits within phases that have cross-polity interactions are
  therefore not safe.
- **Maximum replay cost is one phase.** On resume, the engine reads
  `GameState` and re-enters the tick at the last committed phase + 1.
  Because polity processing order is fixed and all randomness is seeded from
  `(tick, phase)`, replaying is deterministic.
- **Per-tick commits are too coarse.** A full tick across all polities and
  phases may be expensive; replaying an entire tick after a late-phase crash
  wastes work.

### Polity processing order

Within any phase, polities are processed in a **fixed sequence** determined
at game initialisation:

1. Order is assigned at polity creation: `processing_order INTEGER` column
   on `Polity`, set once and never changed.
2. For starting polities, order is assigned by species (alphabetical by name)
   then by polity ID within a species.
3. New polities created by faction split are appended to the end of the
   sequence.

Fixed order plus per-phase commits means the simulation is fully
deterministic and resumable. A phase can be replayed from its committed
precondition state and will produce identical results.

### Random seed policy

All random draws within the simulation are seeded from `(tick, phase,
processing_order)`. This guarantees:
- Identical results on replay
- No hidden state accumulation between phases
- Phase-level commits are safe to use as exact resume points

### Commit sequence within a phase

```
begin_phase(tick, phase):
    update GameState.current_phase = phase
    [process all polities in fixed order]
    [write all game.db changes for this phase]
    commit
    update GameState.last_committed_tick = tick
    update GameState.last_committed_phase = phase
    update GameState.last_committed_at = now()
    commit
```

The double-commit pattern ensures `GameState` always reflects a committed
state, not an in-progress one. If the process dies between the phase commit
and the GameState update, the resume logic detects the discrepancy and
re-runs the phase (idempotent writes where needed).

### Resume logic

```
on startup:
    read GameState
    if current_phase != last_committed_phase:
        # crashed mid-phase; roll back to last committed state
        rollback current_phase partial writes (if any)
        re-enter at last_committed_phase + 1
    else:
        re-enter at current_phase + 1
```

---

## Open questions

- `RepairQueue` tracks by hull_type for fleet hulls (not individual hulls).
  Is a damaged_count per hull_type in FleetComposition sufficient, or do we
  need individual hull rows for fleet classes too? Current design says counts
  are enough for Version 1; revisit if the historian needs individual ship
  names.
- `WorldPotential` is one row per body. Systems with multiple rocky bodies
  need an aggregation rule for SystemPresence (which body is the presence on?).
  Current assumption: one SystemPresence row per body, polity can hold multiple
  bodies in a system.
- Game tick counter: resolved — explicit `GameState` singleton table with
  `(current_tick, current_phase, last_committed_tick, last_committed_phase)`.
  See Simulation state section above.
- Monthly summary threshold: "no combat, no control changes, no new colonies"
  — needs a precise definition of "quiet" for the log compression rule.
