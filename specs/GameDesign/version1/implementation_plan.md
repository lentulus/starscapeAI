# Version 1 — Implementation Plan

Phased build order with conceptual modules, key functions, and testability
strategy. The system should produce observable output at every milestone —
not just pass unit tests.

---

## Testability strategy

Three mechanisms make every module independently testable:

1. **WorldStub** — implements the `WorldFacade` protocol with seeded-random
   data. Every game and engine module that needs world data accepts a facade
   argument; swapping stub for real requires changing one call site.

2. **In-memory game.db** — every test that touches game state calls
   `open_game(":memory:")`. No filesystem artefacts. Tests are trivially
   parallelisable and completely isolated.

3. **GameFacade protocol** — engine phase modules never import from `game.*`
   directly. They call methods on a `GameFacade` instance. A `GameFacadeStub`
   records calls as `(method, args)` tuples for unit testing engine logic
   without a database.

Each engine phase module has this signature:

```python
def run_PHASE_phase(
    tick: int,
    phase_num: int,           # 1–9; used for RNG seeding
    polity_order: list[int],  # fixed; never changes
    game: GameFacade,
    world: WorldFacade | None,  # None for phases that don't query the world
    rng_factory: Callable[[int], Random]  # rng_factory(processing_order) → seeded RNG
) -> list[EventSummary]:
```

Seeded randomness: `rng = Random(hash((tick, phase_num, processing_order)))`.
Given the same game state at phase entry, every phase is deterministic and
replayable. This is required for crash-safe resume.

---

## Dependency graph

```
M0: schema + DB factories
    M1: names (independent)
    M2: WorldFacade + WorldStub
        M3: Polity + GameState
            M4: Hull + Squadron + Fleet + Admiral + Ground
                M5: Game initialiser (full OB, all stubs)
                    M6: Economy phase   ← first runnable phase
                        M7: Intelligence + Control phases
                            M8: Movement + Contact detection
                                M9: Combat phase
                                    M10: Bombardment + Assault phases
                                        M11: Real decision engine
                                            M12: Real world layer
                                                M13: Log phase + full tick loop
```

M1 and M2 can be built in parallel with M0. M1 and M2 are prerequisites
for M5 but not for M3–M4.

---

## Milestone 0 — Schema and DB factories

**Goal:** Schema exists, packages importable, connection factories work.

### Modules

**World DB factory**
- `open_world_ro(path) → Connection` — read-only URI mode for simulation
- `open_world_rw(path) → Connection` — read-write for on-demand generation only
- Separate from the existing pipeline `db.py`; simulation gets its own factory

**Game DB factory + schema**
- `open_game(path) → Connection` — creates or opens game.db
- `init_schema(conn)` — executes `sql/schema_game.sql`; accepts `":memory:"`
- `sql/schema_game.sql` — all game.db tables: `GameState`, `WorldPotential`,
  `SystemIntelligence`, `Polity`, `ContactRecord`, `WarRecord`,
  `SystemPresence`, `Fleet`, `Squadron`, `Hull`, `Admiral`, `GroundForce`,
  `BuildQueue`, `RepairQueue`, `SystemEconomy`, `GameEvent`, `PlaceName`,
  `NamePool`

**Smoke test:**
```python
conn = open_game(":memory:")
init_schema(conn)
# query sqlite_master; assert all expected table names present
```

---

## Milestone 1 — Names (independent)

**Goal:** Name generation works in isolation; every entity gets a name.

### Modules

**NameGenerator**
- `__init__(species_id, db_conn=None)` — None → code fallback; conn → draws
  from NamePool table
- `fleet(polity_name, sequence) → str`
- `admiral(sequence) → str`
- `system(system_id, sequence) → str`
- `body(body_id, sequence) → str`
- `war(polity_a, polity_b, tick) → str`
- `hull(hull_type, sequence) → str`

**Name codes (fallback)**
- `species_prefix(species_id) → str` — 3-letter abbreviation
- `format_code(prefix, type_tag, sequence) → str` — `"HUM-FL-0003"`
- Pure functions; no dependencies

**Smoke test:**
```python
gen = NameGenerator(species_id=1)
print(gen.fleet("Humanity", 1))   # → "HUM-FL-0001"
print(gen.admiral(42))            # → "HUM-ADM-0042"
```

---

## Milestone 2 — WorldFacade and WorldStub

**Goal:** Define the world/game firewall seam; implement the stub; engine can
run against fake data with no starscape.db.

### Modules

**WorldFacade (protocol)**

All functions the game and engine may call on the world:

- `get_star_position(system_id) → SystemPosition`
- `get_distance_pc(system_id_a, system_id_b) → float`
- `get_bodies(system_id) → list[BodyData]` — returns `[]` if not generated
- `get_gas_giant_flag(system_id) → bool | None`
- `get_ocean_flag(system_id) → bool | None`
- `resolve_system(system_id, game_conn)` — on-demand generation; the one
  function allowed to hold both DB connections simultaneously
- `get_species(species_id) → SpeciesData`
- `check_habitability(body_id, species_id) → bool`
- `get_systems_within_parsecs(system_id, parsecs) → list[int]`

**Dataclasses**
- `SystemPosition(system_id, x_mpc, y_mpc, z_mpc)`
- `BodyData(body_id, system_id, body_type, mass, radius, in_hz, planet_class,
  atm_type, surface_temp_k, hydrosphere, world_potential)`
- `SpeciesData(species_id, name, aggression, expansionism, risk_appetite,
  adaptability, social_cohesion, hierarchy_tolerance, faction_tendency,
  grievance_memory, lifespan_years, temp_min_k, temp_max_k, atm_req)`

**WorldStub**
- `__init__(seed=42)`
- All methods return seeded-random but plausible data
- `get_bodies(system_id)` seeds per-system from `seed ^ system_id` — same
  system always returns the same bodies regardless of call order
- Satisfies the full WorldFacade protocol

**Smoke test:**
```python
stub = WorldStub(seed=42)
pos = stub.get_star_position(1000)
bodies = stub.get_bodies(1000)
print(f"System 1000: {pos}, {len(bodies)} bodies")
```

---

## Milestone 3 — Polity and GameState

**Goal:** Tick counter works; polities round-trip in game.db.

### Modules

**GameState**
- `create_gamestate(conn, tick=0) → None`
- `read_gamestate(conn) → GameState`
- `advance_phase(conn, tick, phase) → None`
- `commit_phase(conn, tick, phase) → None`
- `GameState` dataclass: `current_tick, current_phase, last_committed_tick,
  last_committed_phase, started_at, last_committed_at`

**Polity**
- `create_polity(conn, species_id, name, capital_system_id, expansionism,
  aggression, risk_appetite, processing_order) → int`
- `get_all_polities(conn) → list[PolityRow]`
- `get_polity(conn, polity_id) → PolityRow`
- `update_treasury(conn, polity_id, delta_ru) → None`

**Smoke test:**
```python
conn = open_game(":memory:")
init_schema(conn)
create_gamestate(conn)
create_polity(conn, species_id=1, name="Humanity Alpha", ...)
create_polity(conn, species_id=2, name="Kreeth Dominion", ...)
gs = read_gamestate(conn)
print(f"Tick {gs.current_tick}: {[p.name for p in get_all_polities(conn)]}")
```

---

## Milestone 4 — Military layer (Hull, Squadron, Fleet, Admiral, Ground)

**Goal:** Starting OB can be instantiated in-memory and round-trips correctly.

### Modules

**Hull constants**
- `HULL_STATS: dict[str, HullStats]` — unit table from units.md as a
  module-level constant (attack, bombard, defence, jump, build_cost,
  build_time, maint_per_tick)
- Pure data; no DB dependency

**Hull**
- `create_hull(conn, polity_id, name, hull_type, system_id, fleet_id,
  squadron_id, created_tick) → int`
- `get_hulls_in_fleet(conn, fleet_id) → list[HullRow]`
- `get_hulls_in_system(conn, system_id) → list[HullRow]`
- `mark_hull_damaged(conn, hull_id) → None`
- `mark_hull_destroyed(conn, hull_id) → None`

**Squadron**
- `create_squadron(conn, fleet_id, polity_id, name, hull_type, combat_role,
  system_id) → int`
- `get_squadrons_in_fleet(conn, fleet_id) → list[SquadronRow]`
- `compute_squadron_strength(conn, squadron_id) → dict` — `{attack, defence,
  bombard}` summed from non-destroyed hulls; halved for damaged hulls
- `assign_combat_role(conn, squadron_id, role) → None`

**Fleet**
- `create_fleet(conn, polity_id, name, system_id) → int`
- `get_fleets_in_system(conn, system_id) → list[FleetRow]`
- `get_hostile_fleets(conn, system_id, polity_id) → list[FleetRow]`
- `set_fleet_destination(conn, fleet_id, destination_system_id,
  destination_tick) → None`
- `update_fleet_supply(conn, fleet_id, ticks_increment) → None`

**Admiral**
- `ADMIRAL_GENERATION_PARAMS: dict[str, dict]` — species bias values
- `generate_tactical_factor(species_data: SpeciesData, rng: Random) → int`
  — species-biased 2d6 drop-lowest; mean/variance modifiers from species
  parameters; clip to [−3, +3]
- `create_admiral(conn, polity_id, name, tactical_factor, fleet_id,
  created_tick) → int`
- `get_fleet_admiral(conn, fleet_id) → AdmiralRow | None`
- `transfer_command(conn, from_fleet_id, to_fleet_id) → None`
- `commission_on_demand(conn, polity_id, fleet_id, species_data, tick,
  rng, name_gen) → int` — fires when fleet enters hostile system with no
  admiral

**Ground constants**
- `GROUND_STATS: dict[str, GroundStats]`

**Ground**
- `create_ground_force(conn, polity_id, name, unit_type, system_id, body_id,
  created_tick) → int`
- `get_ground_forces_at_body(conn, body_id) → list[GroundForceRow]`
- `embark_force(conn, force_id, hull_id) → None`
- `disembark_force(conn, force_id, system_id, body_id) → None`
- `apply_strength_delta(conn, force_id, delta) → None`

**Smoke test:**
```python
conn = open_game(":memory:")
init_schema(conn)
p1 = create_polity(conn, ...)
fleet_id = create_fleet(conn, p1, "KRT-FL-0001", system_id=100)
sq = create_squadron(conn, fleet_id, p1, "First Claw", "capital", "line_of_battle", 100)
for i in range(2):
    create_hull(conn, p1, f"KRT-CAP-{i:04}", "capital", 100, fleet_id, sq, tick=0)
hulls = get_hulls_in_fleet(conn, fleet_id)
maint = sum(HULL_STATS[h.hull_type].maint_per_tick for h in hulls)
print(f"{len(hulls)} hulls, maintenance {maint} RU/tick")
```

---

## Milestone 5 — Game initialiser

**Goal:** One function call creates the full starting game state for all species
from the starting OB data. First end-to-end initialisation.

### Modules

**System presence**
- `create_presence(conn, polity_id, system_id, body_id, control_state,
  development_level, established_tick) → int`
- `get_presences_by_polity(conn, polity_id) → list[PresenceRow]`
- `advance_control_state(conn, presence_id) → str`
- `set_contested(conn, presence_id) → None`

**Economy (init portion)**
- `compute_world_potential(body_data: BodyData) → int` — pure; scoring table
  from game.md
- `create_world_potential_cache(conn, body_id, system_id, potential, has_gg,
  has_ocean) → None`
- `compute_ru_production(world_potential, control_state, development_level)
  → float` — pure; multiplier tables

**Events**
- `write_event(conn, tick, phase, event_type, summary, polity_a_id=None,
  polity_b_id=None, system_id=None, body_id=None, admiral_id=None,
  detail=None) → int`
- `get_events(conn, tick=None, event_type=None) → list[EventRow]`

**Game initialiser**
- `init_game(game_conn, world: WorldFacade, ob_data: dict) → None`
  1. `create_gamestate`
  2. Populate WorldPotential cache via `world.resolve_system` for each
     homeworld system (stub or real)
  3. Create Polity rows; apply `faction_tendency > 0.85` multi-polity rule
  4. Create starting SystemPresence (Controlled/dev-3 per homeworld)
  5. Create fleets, squadrons, hulls from OB constants
  6. Create starting admirals
  7. Create starting ground forces
  8. Write tick-0 GameEvents for all entities
  9. Set starting treasury

**OB data** is encoded as Python dicts keyed by species name, mirroring
`starting_ob.md`. This is a plain data constant, not a module.

**Smoke test:**
```python
world = WorldStub(seed=42)
conn = open_game(":memory:")
init_schema(conn)
init_game(conn, world, OB_DATA)

polities = get_all_polities(conn)
all_hulls = [h for p in polities
             for f in get_fleets_in_system(conn, p.capital_system_id)
             for h in get_hulls_in_fleet(conn, f.fleet_id)]
events = get_events(conn, tick=0)
print(f"{len(polities)} polities, {len(all_hulls)} hulls, {len(events)} tick-0 events")
```

Observable: 13+ polities (6 species + 2 human polities + 3 Nhaveth courts),
hull counts matching starting_ob.md, event log entries for each entity.

---

## Milestone 6 — Economy phase (first runnable phase)

**Goal:** First complete, independently-testable tick phase. Economy runs;
treasury changes; build queues advance.

**Rationale:** Economy is the simplest phase — no inter-polity interaction,
no world queries beyond the WorldPotential cache, no randomness. Run it first
to prove the phase/commit loop works before adding complexity.

### Modules

**GameFacade (protocol)**

The second critical seam. Engine phase modules never import from `game.*`
directly. They call methods on a `GameFacade`.

Methods required for economy phase:
- `collect_ru(polity_id, tick) → float`
- `pay_maintenance(polity_id, tick) → float`
- `advance_build_queues(tick) → list[int]` — returns completed hull_ids
- `advance_repair_queues(tick) → list[int]` — returns repaired hull_ids
- `apply_supply_degradation(polity_id, tick) → None`

**GameFacadeStub** — records calls as `(method, args)` tuples; returns
configured dummy values. Used for unit-testing engine logic.

**GameFacadeImpl** — real implementation wrapping a game.db connection.

**Economy (complete)**
- `collect_ru(conn, polity_id, tick) → float` — sums production for all
  presences; writes SystemEconomy rows; deposits to treasury
- `pay_maintenance(conn, polity_id, tick) → float` — sums hull + squadron +
  ground maintenance; deducts from treasury; marks deferred-maintenance hulls
- `advance_build_queues(conn, tick) → list[int]` — ticks all BuildQueue
  entries; creates Hull/GroundForce rows for completed builds
- `advance_repair_queues(conn, tick) → list[int]` — ticks RepairQueue;
  restores hull status
- `apply_supply_degradation(conn, polity_id, tick) → None` — double
  maintenance at 8 ticks; combat rating degradation at 16

**Economy phase (engine)**
- `run_economy_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Commit loop (first use):**
```python
# In run_tick:
game.state.advance_phase(tick, 8)
events = run_economy_phase(tick, 8, polity_order, game, ...)
game.state.commit_phase(tick, 8)
```

**Smoke test:**
```python
world = WorldStub(seed=42)
conn = open_game(":memory:")
init_schema(conn)
init_game(conn, world, OB_DATA)
facade = GameFacadeImpl(conn)

run_economy_phase(tick=1, phase_num=8, polity_order=[...], game=facade, ...)

p1 = get_polity(conn, 1)
print(f"Treasury after tick 1: {p1.treasury_ru:.1f} RU")
```

Observable: Treasury value differs from tick-0 by `production − maintenance`.

---

## Milestone 7 — Intelligence and Control phases

### Modules

**Intelligence**
- `update_passive_scan(conn, polity_id, world: WorldFacade, tick) → list[int]`
  — for each Controlled presence, find all systems within 20pc; insert/update
  SystemIntelligence at `knowledge_tier='passive'` with GG/ocean flags only
- `record_visit(conn, polity_id, system_id, world: WorldFacade, tick) → None`
  — upgrades to `knowledge_tier='visited'`; populates all world-data columns
- `check_map_sharing(conn, tick) → list[tuple[int,int]]` — scans ContactRecord
  for `peace_weeks >= 52`; fires map exchange; returns pairs
- `copy_intel_between_polities(conn, polity_a_id, polity_b_id) → None`

**Intelligence phase (engine)**
- `run_intelligence_phase(tick, phase_num, polity_order, game, world,
  rng_factory) → list[EventSummary]`

**Presence growth**
- `check_growth_cycles(conn, tick, rng) → list[PresenceAdvanced]` — at
  25-week checkpoints, roll advancement probability; calls
  `advance_control_state` on successes
- `compute_growth_probability(expansionism, stability, development_level)
  → float` — pure

**Control phase (engine)**
- `run_control_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Seeded randomness first appears here** (control phase advancement rolls):
`rng = rng_factory(processing_order)` where
`rng_factory = lambda po: Random(hash((tick, 7, po)))`

**Smoke test:**
```python
for tick in range(1, 26):
    run_intelligence_phase(tick, 1, polity_order, facade, world, rng_factory)
    run_economy_phase(tick, 8, polity_order, facade, None, rng_factory)
    run_control_phase(tick, 7, polity_order, facade, None, rng_factory)

events = get_events(conn, event_type='control_change')
print(f"Control changes after 25 ticks: {len(events)}")
```

---

## Milestone 8 — Movement phase and contact detection

### Modules

**Fleet movement**
- `execute_jump(conn, fleet_id, destination_system_id, arrival_tick) → None`
- `arrive_fleet(conn, fleet_id, tick) → None` — sets system_id, clears
  destination, sets hulls active
- `detect_contacts(conn, system_id, tick) → list[tuple[int,int]]` — after
  all arrivals for this tick; creates ContactRecord rows for new contacts;
  returns new (polity_a, polity_b) pairs
- Note: contact detection runs after all arrivals, not per-polity, to handle
  simultaneous entry

**Movement phase (engine)**
- `run_movement_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`
- Processes arrivals → runs `detect_contacts` per newly-occupied system →
  writes contact GameEvents

**Decision stub (temporary)**
- `run_decision_phase_stub(tick, polity_order, game, world) → list[Order]`
- Generates "Expand" decisions only: move one scout toward nearest unvisited
  system within jump range
- Decision result is a list of pure dataclasses (`FleetOrder`, `BuildOrder`);
  no DB writes in decision phase itself

**Partial tick runner**
- `run_partial_tick(tick, facade, world)` — chains phases 1, 2 (stub), 3,
  8, 7 in order; commits after each

**Smoke test:**
```python
for tick in range(1, 11):
    run_partial_tick(tick, facade, world)

contacts = get_events(conn, event_type='contact')
print(f"Contacts after 10 ticks: {len(contacts)}")
for c in contacts:
    print(f"  {c.summary}")
```

Observable: First inter-polity contact events in the log. Multi-line history.

---

## Milestone 9 — Combat phase

The most complex phase. Built here because it is the core dramatic mechanic.

### Modules

**Tactical decisions (pure functions)**

`engage`:
- `should_engage(attacker_strength, defender_strength, risk_appetite,
  is_homeworld) → bool`
- `compute_side_strength(squadrons: list[SquadronStrength],
  admiral_factor: int) → int`

`disengage`:
- `should_disengage(own_strength, enemy_strength, risk_appetite,
  retreat_available, tactical_factor) → bool`

`pursuit`:
- `should_pursue(own_condition, aggression, objective, tactical_factor) → bool`

`retreat`:
- `select_retreat_destination(conn, fleet_id, world) → int | None` — nearest
  friendly system; prefers shipyard if hulls damaged; avoids hostile systems

**Damage table**
- `damage_table_result(net_shift: int, rng: Random) → DamageOutcome` — pure
  function; results: `no_effect / one_damaged / one_destroyed /
  multiple_destroyed / fleet_broken`

**Combat resolver**
- `resolve_combat_in_system(system_id, tick, phase_num, game: GameFacade,
  rng: Random) → CombatResult`
  1. Get all hostile fleet pairs in system
  2. SDBs always screen for defender; other roles per Squadron.combat_role
  3. Screen engages first; broken screen → direct line engagement with attack
     bonus
  4. Line exchange: strength totals + admiral DM + 2d6 → damage table
  5. Reserve commitment check after each exchange (admiral tactical decision)
  6. Disengage evaluation after each exchange
  7. Returns `CombatResult` with damage lists, retreat destinations, outcome

- `apply_combat_result(conn, result: CombatResult, tick) → list[GameEvent]`
  — writes hull damage/destruction, fleet retreat movements, admiral status,
  GameEvents

**Admiral on-demand commissioning**
- Fires inside combat resolver when fleet enters hostile system with no
  admiral: `commission_on_demand(conn, polity_id, fleet_id, species_data,
  tick, rng, name_gen) → int`

**Combat phase (engine)**
- `run_combat_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Smoke test:**
```python
# Two fleets in same system; force them hostile
conn = open_game(":memory:")
# ...setup two fleets, hostile polities, squadrons with hulls...
result = resolve_combat_in_system(100, tick=5, phase_num=4, game=facade,
                                   rng=Random(42))
for event in apply_combat_result(conn, result, tick=5):
    print(event.summary)
```

Observable: Combat narrative. Damage applied to Hull rows. Winner/loser.

---

## Milestone 10 — Bombardment and Assault phases

### Modules

**Bombardment**
- `check_naval_superiority(conn, system_id, polity_id) → bool` — no hostile
  fleet present
- `run_bombardment_tick(conn, system_id, attacker_id, tick, rng)
  → BombardmentResult` — net Bombardment advantage reduces defender combined
  strength by 1; writes GameEvent
- `should_bombard(defender_strength, own_army_strength, risk_appetite,
  bombardment_rating) → bool` — pure; tactical decision

**Bombardment phase (engine)**
- `run_bombardment_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Assault**
- `run_ground_assault(conn, system_id, attacker_id, tick, rng)
  → AssaultResult`
  - Non-marine penalty: −1 first-round strength if not marine-designated
  - Garrison bonus: effective strength ×1.5 in prepared positions
  - 2d6 differential per ground combat result table (units.md)
  - Multi-round loop until attacker withdraws or defender destroyed/retreats
  - Garrison destroyed in place if overrun; Army may retreat to fleet

- `apply_assault_result(conn, result: AssaultResult, tick) → list[GameEvent]`

**Presence extended**
- `set_contested(conn, system_id, attacker_polity_id) → None`
- `transfer_control(conn, presence_id, new_polity_id) → None`

**Assault phase (engine)**
- `run_assault_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Smoke test:**
```python
result = run_bombardment_tick(conn, 100, polity_a, tick=10, rng=Random(99))
print(f"Bombardment: strength {result.before} → {result.after}")
assault = run_ground_assault(conn, 100, polity_a, tick=11, rng=Random(100))
print(f"Assault: {assault.outcome}, control change: {assault.control_change}")
```

---

## Milestone 11 — Real decision engine

### Modules

**Posture**
- `draw_posture(expansionism, aggression, risk_appetite, at_war,
  known_contacts) → Posture` — weighted draw from `{Expand, Consolidate,
  Prepare, Prosecute}`; pure function
- `Posture` enum

**Action scoring**
- `score_action(action: CandidateAction, posture: Posture, polity: PolityRow,
  snapshot: GameStateSnapshot) → float` — pure function; no DB
- `CandidateAction` discriminated union: `ScoutAction`, `ColoniseAction`,
  `BuildHullAction`, `MoveFleetAction`, `InitiateWarAction`,
  `AssaultAction`, `ConsolidateAction`

**Action selector**
- `select_actions(scored_actions, rng, top_k=5) → list[CandidateAction]`
  — softmax-weighted selection; top-scored wins most often

**GameStateSnapshot**
- Read-only view of current game state: computed once at Decision phase
  start from game.db, then passed as a pure Python object to scoring functions
- No DB connections inside scoring; this is critical for testability

**War initiation**
- `war_initiation_roll(aggression, extra_dms, rng) → bool` — 2d6 + aggression
  DM; pure function
- `process_war_rolls(conn, tick, rng) → list[WarDeclared]` — scans
  ContactRecord for in-contact non-war pairs; rolls; creates WarRecord rows

**Polity extended**
- `create_contact_record(conn, polity_a_id, polity_b_id, tick, system_id)`
- `increment_peace_weeks(conn, tick) → None`
- `declare_war(conn, polity_a_id, polity_b_id, initiator_id, tick,
  name_gen) → int`

**Decision phase (engine)**
- `run_decision_phase(tick, phase_num, polity_order, game, world,
  rng_factory) → list[Order]`

**AI test:** Create HighAggression snapshot; draw posture 1000 times; assert
`Prosecute` most common when at war.

**Smoke test:**
```python
for tick in range(1, 101):
    run_tick(tick, facade, world)

wars = get_events(conn, event_type='war_declared')
combats = get_events(conn, event_type='combat')
print(f"100 ticks: {len(wars)} wars, {len(combats)} combats")
for e in get_events(conn)[-10:]:
    print(f"  Tick {e.tick}: {e.summary}")
```

Observable: Full 100-tick history. Species behavioural differences visible in
event patterns — Skharri declaring war earlier than Golvhaan, Vardhek
expanding more systematically than Nakhavi.

---

## Milestone 12 — Real world layer (starscape.db)

**Goal:** Replace WorldStub with real implementation. First milestone
requiring actual starscape.db.

### Modules

**World systems**
- `get_system_position(conn, system_id) → SystemPosition`
- `get_systems_within_distance_mpc(conn, system_id, distance_mpc) → list[int]`

**World bodies**
- `get_bodies_for_system(conn, system_id) → list[BodyData]`
- `has_bodies_generated(conn, system_id) → bool`

**World species**
- `get_species(conn, species_id) → SpeciesData`
- `check_habitability(body: BodyData, species: SpeciesData) → bool`

**World potential (canonical)**
- `compute_world_potential(body: BodyData) → int` — moved here from game
  economy module; game economy calls through WorldFacade

**World resolver**

The documented exception to the one-connection rule:

- `resolve_system(system_id, world_conn, game_conn) → list[BodyData]`
  1. `has_bodies_generated(world_conn, system_id)` — if yes, return existing
  2. Look up star data from `DistinctStarsExtended`
  3. Seed RNG from `system_id` — deterministic; same system always generates
     the same planets
  4. Call `planets.generate_planet`, `atmosphere.classify_atm`, etc.
  5. Write Bodies + BodyMutable to starscape.db (`INSERT OR IGNORE`)
  6. Compute world_potential per body
  7. Upsert WorldPotential cache rows in game.db
  8. Return BodyData list
- Fully idempotent: safe to call twice on the same system_id

**Passive scan (lightweight)**
- `passive_scan_system(world_conn, system_id) → tuple[bool|None, bool|None]`
  — gas_giant_flag, ocean_flag; does NOT trigger full body generation

**WorldFacadeImpl**
- Real implementation of the WorldFacade protocol
- Swapping `WorldStub` → `WorldFacadeImpl` requires changing one argument
  in `init_game` and `run_tick`; nothing else changes

**Smoke test:**
```python
world = WorldFacadeImpl(open_world_ro(STARSCAPE_DB), open_world_rw(STARSCAPE_DB))
conn = open_game(":memory:")
init_schema(conn)
init_game(conn, world, OB_DATA)

potentials = get_world_potentials(conn)
print(f"WorldPotential rows: {len(potentials)}")
for p in potentials[:5]:
    print(f"  body_id={p.body_id}, potential={p.world_potential}")
```

Observable: Real world potential values from real stellar data.

---

## Milestone 13 — Log phase and full tick loop

**Goal:** All 9 phases chain. Event log compression fires. Crash-safe resume
verified. First persistent simulation run.

### Modules

**Log phase**
- `is_quiet_tick(events_this_tick: list[EventRow]) → bool` — no combat, no
  control changes, no new colonies
- `write_monthly_summary(conn, tick, polities, game_facade) → None` —
  aggregates treasury totals, fleet counts, territory extent
- `run_log_phase(tick, phase_num, polity_order, game, world=None,
  rng_factory) → list[EventSummary]`

**Full tick runner**
- `run_tick(tick: int, game: GameFacade, world: WorldFacade) → TickResult`
  — all 9 phases in order; `commit_phase` after each;
  `TickResult` with phase outcomes and event counts

**Simulation loop**
- `run_simulation(game_conn, world_facade, max_ticks: int | None = None)`
  — reads GameState for resume point; loops `run_tick`; handles
  `KeyboardInterrupt` cleanly by committing current phase and exiting

**Resume test:**
```python
# Run 5 ticks; raise exception in phase 4 of tick 6; re-open; verify resume
for tick in range(1, 6):
    run_tick(tick, facade, world)
# Simulate crash: advance to phase 4, don't commit
# Re-open: verify last_committed_phase < 4; re-run phase 4; same result
```

**Final smoke test:**
```python
world = WorldFacadeImpl(...)
conn = open_game("game.db")
init_schema(conn)
init_game(conn, world, OB_DATA)
run_simulation(conn, world, max_ticks=500)

events = get_events(conn)
print(f"500-tick run ({500//52:.0f} years):")
print(f"  {sum(1 for e in events if e.event_type=='war_declared')} wars declared")
print(f"  {sum(1 for e in events if e.event_type=='combat')} combat events")
print(f"  {sum(1 for e in events if e.event_type=='colony_established')} colonies established")
print("Last 10 events:")
for e in events[-10:]:
    print(f"  Tick {e.tick}: {e.summary}")
```

Observable: A complete 500-tick (~10 year) history in a persistent game.db.
The LLM historian can now be pointed at this event log.

---

## Notes

- Start each milestone by writing the smoke test. If the smoke test runs
  and produces the expected output, the milestone is done.
- Each milestone's modules are fully testable before the next milestone
  begins. Never block on a downstream dependency.
- The `WorldStub` remains in the codebase permanently as the test double for
  the world layer. It is not scaffolding to be deleted.
- `HULL_STATS` and `GROUND_STATS` as module-level constants (not DB queries)
  means game balance changes are a one-line edit with immediate effect across
  all tests.
- The `GameStateSnapshot` pattern (compute once at Decision phase start,
  pass as pure Python object to scoring functions) is the key to making the
  decision engine fast and trivially testable.
