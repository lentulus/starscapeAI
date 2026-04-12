# game.db — Data Dictionary

Simulation state database. Never contains world-generation data; that lives in `starscape.db`. Cross-database references are by stored integer ID only — no SQLite `ATTACH` joins at runtime.

---

## Table index

| Table | Role |
|---|---|
| [GameState](#gamestate) | Singleton clock and crash-safe resume point |
| [WorldPotential](#worldpotential) | Per-body habitability cache copied from starscape.db at init |
| [Polity](#polity) | A faction: treasury, disposition traits, jump-tech level |
| [ContactRecord](#contactrecord) | Diplomatic pair: tracks first contact, war status, peace weeks |
| [WarRecord](#warrecord) | Named war between two polities with start/end ticks |
| [SystemIntelligence](#systemintelligence) | Per-polity knowledge tier and cached physical data for each system |
| [SystemPresence](#systempresence) | Per-polity foothold on a body: control state, development, deliveries |
| [Fleet](#fleet) | A named group of hulls under common orders; moves as a unit |
| [Squadron](#squadron) | Warships of the same type within a fleet; the tactical combat unit |
| [Hull](#hull) | Every individual ship, troop transport, or colony vessel |
| [Admiral](#admiral) | Named commander attached to a fleet; provides a tactical modifier |
| [GroundForce](#groundforce) | Army or garrison on a body; drives assault and occupation |
| [BuildQueue](#buildqueue) | In-progress hull construction at a shipyard |
| [RepairQueue](#repairqueue) | Damaged hull awaiting repair |
| [SystemEconomy](#systemeconomy) | Append-only per-system RU ledger for each tick |
| [NamePool](#namepool) | Pre-generated species-specific names drawn at entity creation |
| [PlaceName](#placename) | Per-polity names assigned to systems and bodies |
| [GameEvent](#gameevent) | Append-only authoritative history: wars, combat, colonies, etc. |
| [JumpRoute](#jumproute) | Deduped record of every (from, to) system pair actually jumped |

---

## GameState

Singleton row (`state_id = 1`). Stores the current tick and phase so a crashed process can resume exactly where it left off without replaying history.

| Column | Type | Notes |
|---|---|---|
| `state_id` | INTEGER PK | Always 1 |
| `current_tick` | INTEGER | Tick currently being processed |
| `current_phase` | INTEGER | Phase 1–9; 0 = between ticks |
| `started_at` | TEXT | ISO timestamp of first run |
| `last_committed_at` | TEXT | ISO timestamp of last successful commit |
| `last_committed_tick` | INTEGER | Last fully committed tick |
| `last_committed_phase` | INTEGER | Last committed phase within that tick |
| `routes_complete` | INTEGER | 1 once all homeworlds form a connected jump graph |

---

## WorldPotential

Read-only cache populated at game init from `starscape.db`. Provides each body's habitability score to the economy phase without requiring a cross-database query at runtime.

| Column | Type | Notes |
|---|---|---|
| `body_id` | INTEGER PK | Matches `Bodies.body_id` in starscape.db |
| `system_id` | INTEGER | Matches `IndexedIntegerDistinctSystems.system_id` |
| `world_potential` | INTEGER | 0–100 score; drives RU production formula |
| `has_gas_giant` | INTEGER | 1 if the system has a gas giant (refuelling) |
| `has_ocean` | INTEGER | 1 if the best body has liquid water |

---

## Polity

One row per faction. Treasury and `jump_level` change during the simulation; disposition traits (`expansionism`, `aggression`, `risk_appetite`) are fixed at init and drive AI decisions.

| Column | Type | Notes |
|---|---|---|
| `polity_id` | INTEGER PK | |
| `species_id` | INTEGER | Links to species in starscape.db |
| `name` | TEXT | Display name |
| `capital_system_id` | INTEGER | Home system |
| `treasury_ru` | REAL | Current resource units; may go negative |
| `expansionism` | REAL | 0–1; governs colony/scout priorities |
| `aggression` | REAL | 0–1; governs war initiation and fleet building |
| `risk_appetite` | REAL | 0–1; governs willingness to bombard/assault |
| `processing_order` | INTEGER | Tie-breaker within a tick phase |
| `founded_tick` | INTEGER | |
| `jump_level` | INTEGER | Current scout jump range in parsecs (upgradeable, default 10) |
| `status` | TEXT | `active` / `eliminated` / `vassal` |

---

## ContactRecord

Created the first tick two polity fleets share a system. One row per ordered pair (`polity_a_id < polity_b_id`). `peace_weeks` increments each tick while not at war; reaching 52 triggers map sharing.

| Column | Type | Notes |
|---|---|---|
| `contact_id` | INTEGER PK | |
| `polity_a_id` | INTEGER FK | Lower polity_id of the pair |
| `polity_b_id` | INTEGER FK | Higher polity_id of the pair |
| `contact_tick` | INTEGER | Tick of first meeting |
| `contact_system_id` | INTEGER | System where first contact occurred |
| `peace_weeks` | INTEGER | Consecutive weeks without war |
| `at_war` | INTEGER | 1 if currently at war |
| `map_shared` | INTEGER | 1 once intelligence has been exchanged |

---

## WarRecord

Supplement to `ContactRecord.at_war`. Stores the named war and its duration; `ended_tick` is NULL while ongoing. Multiple wars between the same pair are possible in theory.

| Column | Type | Notes |
|---|---|---|
| `war_id` | INTEGER PK | |
| `polity_a_id` | INTEGER FK | |
| `polity_b_id` | INTEGER FK | |
| `name` | TEXT | Procedurally generated war name |
| `declared_tick` | INTEGER | |
| `initiator_id` | INTEGER FK | Which polity declared war |
| `ended_tick` | INTEGER | NULL while ongoing |

---

## SystemIntelligence

Per-polity knowledge of each system. `passive` tier = inferred from 20 pc scan radius (position only). `visited` tier = direct fleet visit (full physical data populated).

| Column | Type | Notes |
|---|---|---|
| `intel_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `system_id` | INTEGER | starscape.db system_id |
| `knowledge_tier` | TEXT | `passive` or `visited` |
| `first_visit_tick` | INTEGER | NULL for passive tier |
| `last_visit_tick` | INTEGER | Updated each time a fleet visits |
| `gas_giant` | INTEGER | 1 if system has a gas giant |
| `ocean_body` | INTEGER | body_id of best ocean world, or NULL |
| `world_potential` | INTEGER | Best body's habitability score |
| `atm_type` | TEXT | Atmosphere classification of best body |
| `surface_temp_k` | REAL | |
| `hydrosphere` | REAL | 0–1 water fraction |
| `habitable` | INTEGER | 1 if within HZ with standard atm |

---

## SystemPresence

The core territorial record. One row per (polity, body) pair. A polity may have presences on multiple bodies in the same system. `control_state` progresses outpost → colony → controlled via colonist deliveries; `contested` is set by combat.

| Column | Type | Notes |
|---|---|---|
| `presence_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `system_id` | INTEGER | |
| `body_id` | INTEGER | Which body within the system |
| `control_state` | TEXT | `outpost` / `colony` / `controlled` / `contested` |
| `development_level` | INTEGER | 0–5; capped by control_state |
| `colonist_deliveries` | INTEGER | Running count; thresholds: 3→colony, 5→controlled |
| `has_shipyard` | INTEGER | 1 if a shipyard is present |
| `has_naval_base` | INTEGER | 1 if a naval base is present |
| `growth_cycle_tick` | INTEGER | Last tick a growth cycle fired |
| `established_tick` | INTEGER | |
| `last_updated_tick` | INTEGER | |

**Income formula:** `world_potential × control_multiplier × dev_multiplier`

| control_state | multiplier |
|---|---|
| outpost | 0.10 |
| colony | 0.40 |
| controlled | 1.00 |
| contested | 0.10 |

| dev_level | multiplier |
|---|---|
| 0 | 0.50 |
| 1 | 0.70 |
| 2 | 0.90 |
| 3 | 1.00 |
| 4 | 1.20 |
| 5 | 1.50 |

---

## Fleet

A named collection of hulls under shared orders. While in transit `system_id` is NULL; `destination_system_id` and `destination_tick` are set. `prev_system_id` records the jump origin for route tracking.

| Column | Type | Notes |
|---|---|---|
| `fleet_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `name` | TEXT | |
| `system_id` | INTEGER | NULL while in transit |
| `prev_system_id` | INTEGER | Origin of last jump |
| `destination_system_id` | INTEGER | NULL when not jumping |
| `destination_tick` | INTEGER | Tick of arrival |
| `admiral_id` | INTEGER FK | NULL if no admiral assigned |
| `supply_ticks` | INTEGER | Ticks away from a naval base; doubles maintenance at 8+ |
| `status` | TEXT | `active` / `in_transit` / `destroyed` |

---

## Squadron

Warships of the same type grouped within a fleet for tactical combat. Non-warship hulls (scouts, colony transports, etc.) are not squadroned.

| Column | Type | Notes |
|---|---|---|
| `squadron_id` | INTEGER PK | |
| `fleet_id` | INTEGER FK | |
| `polity_id` | INTEGER FK | |
| `name` | TEXT | |
| `hull_type` | TEXT | `capital` / `old_capital` / `cruiser` / `escort` / `sdb` |
| `combat_role` | TEXT | `screen` / `line_of_battle` / `reserve`; redrawn each engagement |
| `system_id` | INTEGER | Denormalised for query speed |
| `status` | TEXT | `active` / `destroyed` |

---

## Hull

Every individual ship. `fleet_id` is NULL for SDBs (system defence boats, which are shore-based). `cargo_type` / `cargo_id` track what a transport is carrying.

| Column | Type | Notes |
|---|---|---|
| `hull_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `name` | TEXT | Species-specific generated name |
| `hull_type` | TEXT | `capital` / `cruiser` / `escort` / `scout` / `colony_transport` / `troop` / `transport` / `sdb` / `old_capital` |
| `squadron_id` | INTEGER FK | NULL for non-warships |
| `fleet_id` | INTEGER FK | NULL for SDBs |
| `system_id` | INTEGER | Current location (NULL in transit) |
| `destination_system_id` | INTEGER | |
| `destination_tick` | INTEGER | |
| `status` | TEXT | `active` / `damaged` / `establishing` / `in_transit` / `destroyed` |
| `marine_designated` | INTEGER | 1 = trained for assault; waives first-round landing penalty |
| `cargo_type` | TEXT | `ru` / `colonists` / `army` / `sdb` / NULL |
| `cargo_id` | INTEGER | FK to the cargo entity |
| `establish_tick` | INTEGER | Tick an SDB began establishing |
| `created_tick` | INTEGER | |

**Maintenance per tick:**

| hull_type | RU/tick |
|---|---|
| capital | 2.0 |
| old_capital | 1.5 |
| cruiser | 1.0 |
| escort | 0.5 |
| scout | 0.1 |
| colony_transport | 0.5 |
| troop / transport / sdb | 0.5 |

---

## Admiral

Named commander attached to a fleet. `tactical_factor` (−3 to +3) adds to the fleet's combat roll. Killed or captured admirals retain their row with updated status.

| Column | Type | Notes |
|---|---|---|
| `admiral_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `name` | TEXT | |
| `tactical_factor` | INTEGER | −3 to +3; added to fleet's 2d6 combat roll |
| `fleet_id` | INTEGER FK | NULL if unassigned |
| `created_tick` | INTEGER | |
| `status` | TEXT | `active` / `killed` / `captured` |

---

## GroundForce

An army (mobile, embarkable) or garrison (stationary, defensive bonus ×1.5). `embarked_hull_id` is non-NULL while the force is aboard a troop transport. `occupation_duty` increases maintenance by 50%.

| Column | Type | Notes |
|---|---|---|
| `force_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `name` | TEXT | |
| `unit_type` | TEXT | `army` / `garrison` |
| `strength` | INTEGER | 0–6; 0 = effectively destroyed |
| `max_strength` | INTEGER | Ceiling for recovery |
| `system_id` | INTEGER | NULL while embarked |
| `body_id` | INTEGER | Which body the force is on |
| `embarked_hull_id` | INTEGER FK | Hull carrying this force |
| `marine_designated` | INTEGER | 1 = waives landing penalty |
| `occupation_duty` | INTEGER | 1 = on foreign soil; +50% maintenance |
| `refit_ticks_remaining` | INTEGER | Ticks until recovered from combat |
| `created_tick` | INTEGER | |
| `last_updated_tick` | INTEGER | |

---

## BuildQueue

One row per hull under construction. RU is reserved up front; the row is deleted when `ticks_elapsed >= ticks_total` and the hull is created.

| Column | Type | Notes |
|---|---|---|
| `queue_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `system_id` | INTEGER | Shipyard location |
| `hull_type` | TEXT | |
| `ticks_total` | INTEGER | Build time from `HULL_STATS` |
| `ticks_elapsed` | INTEGER | Incremented each economy phase |
| `reserved_ru` | REAL | RU already deducted from treasury |
| `ordered_tick` | INTEGER | |

---

## RepairQueue

One row per damaged hull undergoing repair. Deleted on completion.

| Column | Type | Notes |
|---|---|---|
| `repair_id` | INTEGER PK | |
| `hull_id` | INTEGER FK | |
| `system_id` | INTEGER | Location of repair |
| `ticks_total` | INTEGER | Default 4 |
| `ticks_elapsed` | INTEGER | |
| `cost_ru` | REAL | |

---

## SystemEconomy

Append-only ledger. One row per system per tick. Not currently read back during the simulation — written for post-run analysis and the LLM historian.

| Column | Type | Notes |
|---|---|---|
| `economy_id` | INTEGER PK | |
| `tick` | INTEGER | |
| `polity_id` | INTEGER FK | |
| `system_id` | INTEGER | |
| `ru_produced` | REAL | Gross production this tick |
| `ru_maintenance` | REAL | Fleet + ground maintenance paid |
| `ru_construction` | REAL | RU reserved for new build orders |
| `treasury_after` | REAL | Treasury balance after all economy operations |

---

## NamePool

Pre-generated names drawn at entity creation to avoid runtime LLM calls. One row per name; `used = 1` once assigned.

| Column | Type | Notes |
|---|---|---|
| `name_id` | INTEGER PK | |
| `species_id` | INTEGER | |
| `name_type` | TEXT | `person` / `system` / `body` / `fleet` / `war` / `polity` |
| `name` | TEXT | |
| `used` | INTEGER | 0 / 1 |
| `used_by_id` | INTEGER | ID of the entity that claimed this name |
| `used_tick` | INTEGER | |

---

## PlaceName

Per-polity names for systems and bodies. Each polity names things it visits in its own language; the same system may have different names in different polity records.

| Column | Type | Notes |
|---|---|---|
| `name_id` | INTEGER PK | |
| `polity_id` | INTEGER FK | |
| `object_type` | TEXT | `system` / `body` |
| `object_id` | INTEGER | The system_id or body_id being named |
| `name` | TEXT | |
| `assigned_tick` | INTEGER | |

---

## GameEvent

Append-only authoritative event log. Never updated; new rows only. The primary feed for the LLM historian. Quiet periods produce `monthly_summary` rolls instead of individual events.

| Column | Type | Notes |
|---|---|---|
| `event_id` | INTEGER PK | |
| `tick` | INTEGER | |
| `phase` | INTEGER | 1–9, matching the phase that produced the event |
| `event_type` | TEXT | See types below |
| `polity_a_id` | INTEGER FK | Primary actor (or NULL) |
| `polity_b_id` | INTEGER FK | Secondary actor (or NULL) |
| `system_id` | INTEGER | Location (or NULL) |
| `body_id` | INTEGER | Body within system (or NULL) |
| `admiral_id` | INTEGER FK | Relevant admiral (or NULL) |
| `summary` | TEXT | Human-readable one-liner |
| `detail` | TEXT | Extended JSON detail (optional) |

**event_type values:**

| type | When written |
|---|---|
| `contact` | First meeting between two polities |
| `war_declared` | War initiation roll succeeded |
| `combat` | Space combat round or ground assault round |
| `control_change` | Presence state changes (outpost→colony, etc., or contested) |
| `fleet_destroyed` | All hulls in a fleet destroyed |
| `disengage` | Fleet retreated from combat |
| `pursuit` | Pursuing fleet lands hits on retreating fleet |
| `bombardment` | Orbital bombardment tick |
| `colony_established` | New outpost created by colony transport arrival |
| `hull_built` | Build queue item completed |
| `jump_upgrade` | Polity scout jump range increased |
| `admiral_commissioned` | New admiral assigned to fleet |
| `map_shared` | Intelligence exchange between peaceful polities |
| `summary` | Significant tick summary |
| `monthly_summary` | Aggregate quiet-period summary |

---

## JumpRoute

Deduped graph of every (from, to) pair actually jumped by any fleet. Canonical ordering (`from < to`) eliminates duplicates. Recording stops once `GameState.routes_complete = 1`. Used to generate the `jumproutes.dot` visualisation.

| Column | Type | Notes |
|---|---|---|
| `route_id` | INTEGER PK | |
| `from_system_id` | INTEGER | Always the lower of the two system IDs |
| `to_system_id` | INTEGER | Always the higher |
| `dist_pc` | REAL | Jump distance in parsecs |
| `from_x_mpc` | REAL | ICRS Cartesian position of origin (milliparsecs) |
| `from_y_mpc` | REAL | |
| `from_z_mpc` | REAL | |
| `to_x_mpc` | REAL | |
| `to_y_mpc` | REAL | |
| `to_z_mpc` | REAL | |
| `first_tick` | INTEGER | Tick the route was first recorded |
