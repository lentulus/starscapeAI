# Version 1 — Game Design

## Executive summary

**Scope and intent.** Version 1 is a pre-FTL fleet simulator modelled on *Fifth Frontier War*, designed to generate history rather than be played. The world-generation pipeline is complete; Version 1 picks up from there and runs the simulation clock until polities find each other and fight. Everything beyond that core loop — tech progression, diplomacy, trade, RPG events — is explicitly deferred.

**Starting conditions.** All species begin simultaneously at jump-capable interstellar tech with a homeworld, a small fleet, a ground force, and a resource pool. Any species with `faction_tendency` > 0.85 starts fractured into multiple competing polities — at launch this applies to Humans (0.90) and Nhaveth (0.90). Every other species starts unified. Extended jump range (J5+) is a future research milestone; standard drive ratings (J2–J4 by hull type) are available from tick 0.

**Political actors: Polities.** A polity is the unit of agency — it owns assets, makes decisions, and prosecutes war. Each polity inherits disposition parameters (`expansionism`, `aggression`, `risk_appetite`) from its founding species, which drive all of its decision-making. Species and polity are not the same: a species can fracture into multiple polities over time.

**System intelligence.** A polity knows only what it has visited or been told. Passive observation from a Controlled world within 20 parsecs reveals refuelling options only (gas giant or ocean present/absent) — enough for route planning, not enough to assess a world for colonisation. Full system data requires a physical visit. Two polities that make contact and remain at peace for 52 consecutive weeks exchange their complete explored maps; this is the primary intelligence incentive to delay war after first contact.

**Contact.** Contact occurs the moment a scout or fleet physically enters a system occupied by another polity. Before contact, polities expand freely with no risk of war; after contact, war becomes possible every turn. Contact is a one-time, persistent event per polity pair and is always logged.

**War initiation.** Each turn after contact, each non-belligerent polity pair rolls 2d6 with `aggression` as a positive DM; additional DMs accumulate from provocations. If the modified roll meets the threshold, war is declared and the initiator recorded. War continues until one polity is eliminated or reduced to its homeworld — no peace mechanics in Version 1.

**Admirals.** Admirals are generated on demand the first time a fleet without one enters a hostile system; starting polities receive one at initialisation. Seniority is determined by creation sequence, and when friendly fleets combine the most senior admiral commands all forces. Tactical ability is rolled at generation with the mean and variance biased by species parameters — `adaptability` raises the mean, `risk_appetite` widens the spread, `social_cohesion` narrows it.

**System control and starport.** Systems progress through four control states — Outpost, Colony, Controlled, and Contested — aligned with Traveller starport types E through A/B. Advancing control state requires colonist unit deliveries by colony transports, RU investment, no active combat, and a 25-week growth cycle check. Worlds incompatible with a species' environmental tolerances are capped at Outpost; no colony can be established without habitability.

**Ships and fleets.** Ships come in six hull classes — Capital, Old Capital, Cruiser, Escort, Transport, and Troop — each with fixed Attack, Bombardment, Defence, build cost, and maintenance ratings. Old Capitals are cheaper pre-dreadnoughts; outclassed by Capitals in fleet action but still useful for bombardment and garrisoning secondary systems. Fleets are named groups that move together; scouts, couriers, and System Defence Boats (SDBs) are tracked individually. SDBs are fixed to a system and cannot retreat; they are destroyed in place if their system falls.

**Refuelling.** Fleets that go more than 8 ticks without resupply pay double maintenance; at 16 ticks combat ratings degrade. Sources are gas giant skimming (free, 1 stationary tick, no combat), ocean worlds (free, immediate), friendly starports (1 RU/hull), naval bases (free), and fuel tenders. Gas giants are the key strategic anchor: a fleet can sustain an indefinite blockade or occupation in any system that has one, without a local starport.

**Ground forces.** Army units are the abstracted ground combat currency — raised on colonies, transported by Troop or Transport hulls, and expended in assaults. Naval superiority is a hard prerequisite before any ground action. Against a Controlled world, a bombardment phase must precede landing; ground combat then resolves as a 2d6 differential against combined defender and SDB strength.

**Combat.** Space combat fires when hostile fleets meet in a system. Each side totals its Attack ratings, applies the commanding admiral's `tactical_factor`, rolls 2d6, and applies the net shift to a damage table yielding outcomes from no effect to fleet broken. Damaged hulls fight at half ratings until repaired. The losing fleet retreats to the nearest friendly system or is destroyed if none exists.

**Shipbuilding.** Ships are built at shipyard systems (Colony level or above) via a build queue. Full RU cost is reserved at order placement; ticks advance the queue each Economy phase until the hull completes and joins its designated fleet. There is no shipyard capacity limit in Version 1.

**Repair.** Damaged hulls are repaired at shipyard systems over a fixed number of ticks at a fraction of build cost. A hull in the repair queue contributes nothing to fleet ratings until complete. Hulls may be moved while damaged; repair begins only on arrival at a shipyard.

**Economy.** A single resource — Resource Units — is produced each tick per the formula `world_potential × control_multiplier × development_multiplier`. World potential is a fixed score derived from the DB's physical data (HZ status, atmosphere, hydrosphere, mass); control state and development level are the mutable factors that grow through investment and colonist deliveries. RU are spent on construction, forces, maintenance, shipyards, and repair; unmet maintenance degrades hull ratings.

**Polity decision engine.** Each polity runs a parameterised behavioural model each tick — not a search or planning system. It draws a strategic posture (Expand, Consolidate, Prepare, Prosecute), scores all candidate actions using species disposition parameters and game state, then selects among top-scored actions with soft randomness. The result is species-consistent behaviour that generates distinct historical fingerprints without deterministic play.

**Tactical decisions.** Within each combat engagement, a second decision layer evaluates whether to enter and fight, disengage after an exchange, pursue a retreating enemy, and whether to bombard before landing. These decisions are driven primarily by `risk_appetite` and the commanding admiral's `tactical_factor`. Significant tactical choices — a disengage, a pursuit, an elected bombardment — are logged as events so the historian can reconstruct why a battle went the way it did.

**Tick structure.** One tick equals one simulated week. Nine phases run in fixed order: Intelligence, Decision, Movement, Combat, Bombardment, Ground assault, Control update, Economy, Event log. The 25-week growth cycle checkpoints fire in the Control update phase; build queues and repair advance in Economy.

**History logging.** Every significant event — control change, combat, fleet loss, contact, war declaration, major tactical decision — is written as a `GameEvent` with tick, phase, polities, location, and a structured summary. The log is designed to be self-contained: an LLM historian with no other context should be able to reconstruct events and causality from it alone. Quiet periods collapse to monthly summary records.

---

## Scope and intent

Version 1 is a single-tech-level fleet-level simulator modelled on the
*Fifth Frontier War* board game (GDW, 1981). The goal is to produce a
running simulation that generates history — contact, conflict, expansion,
system control changes — before any of the deeper RPG, economic, or
tech-progression mechanics are added. Everything not needed to make that
work is explicitly deferred.

The world-generation pipeline (stars, orbits, planets, atmospheres, species)
is complete. Version 1 begins where that pipeline ends: sophont species have
homeworlds, and the simulation clock starts ticking.

A typical run proceeds in two phases: an **expansion phase** where polities
spread through uninhabited space without contact, then a **contact phase**
where polities begin encountering each other and war becomes possible each
turn.

---

## Starting conditions

All six sophont species start simultaneously at the same tech level:
jump-capable interstellar travel at standard drive ratings (J2–J4 depending
on hull type). Extended jump range — J5 and above — is a research milestone,
not a starting capability.

**High faction-tendency species start fractured.** Any species with
`faction_tendency` > 0.85 begins as multiple independent polities rather
than a unified one. At Version 1 launch this applies to two species:

- **Humans** (0.90) — multiple competing polities sharing Sol and early
  colony systems, already in political tension. The exact number is left to
  the initialisation script.
- **Nhaveth** (0.90) — warring courts sharing the homeworld system, each
  controlling a portion of the Kethara host population. The dominant court
  is the largest but not unchallenged. The exact number of starting courts
  is left to the initialisation script.

Every other species starts as a single polity.

Each starting polity has:
- A homeworld (already seeded in the DB)
- A small interplanetary fleet (patrol vessels, transports)
- A ground force on the homeworld
- A starting resource pool
- A named admiral assigned to its primary fleet

---

## Political actors: Polities

A **polity** is the unit of agency in the simulation. It makes decisions,
owns assets, and prosecutes war. Species and polity are not the same thing:
a species can fracture into multiple polities over time.

Each polity has:
- A controlling species (FK to Species)
- A capital system
- A treasury (resource units)
- A set of disposition parameters inherited from the species at founding,
  but subject to drift over time as events accumulate

Polity disposition parameters used in Version 1:
- `expansionism` — probability weight for colonisation vs consolidation each tick
- `aggression` — DM applied to war initiation rolls after contact
- `risk_appetite` — modifies willingness to commit fleet assets to offensive
  operations

All three are read directly from the Species row at polity creation. Full
drift mechanics are deferred.

---

## System intelligence

A polity only knows what it has seen or been told. System knowledge has
three tiers:

| Knowledge tier | How acquired | What is known |
|---|---|---|
| **Passive** | Controlled world within 20 parsecs | Refuelling options only: gas giant present or absent; ocean world present or absent. Nothing else. |
| **Visited** | Scout or fleet physically present in system at any point | Full system data: all bodies, atmospheres, habitability, world potential, current control state at time of visit |
| **Unknown** | Neither of the above | System existence known from stellar catalogue; no operational data |

**Passive range is refuelling intelligence only.** A polity can see that a
system 15 parsecs away has a gas giant — enough to plan a route that skims
there — but cannot determine habitability, world potential, or whether it
is worth colonising without sending a scout.

**Visited knowledge is permanent for physical data.** World parameters
(gravity, atmosphere, hydrosphere) do not change. Control state and garrison
data from a visit become stale immediately after the fleet leaves; a polity
does not automatically know what has happened in a system since their last
visit.

**Intelligence sharing on sustained contact.** If two polities have made
contact and remained at peace (no war declaration) for 52 consecutive weeks,
they exchange full visited knowledge — each polity receives the other's
complete explored system map, including world data for every system the
other has visited. This transfer happens once at the 52-week mark and is
not ongoing; subsequent visits by either party do not automatically propagate.

The 52-week clause creates a strategic incentive to delay war after first
contact. A polity with superior explored territory has something valuable to
offer; a polity that makes war immediately forfeits that intelligence windfall.

**Route planning implication.** Jump range is only useful if you know where
to refuel. Scouts run ahead of expansion fleets specifically to establish the
refuelling map. Old Capitals at J2 are particularly dependent on this — their
shorter legs mean every hop must be pre-surveyed. A Cruiser or Scout at J4
can range further into unknown space but still needs to know there is fuel
at the other end before committing a fleet.

---

## Contact

Two polities make **contact** when a scout or fleet belonging to one polity
physically enters a system already occupied (or being entered simultaneously)
by another polity. Contact is a one-time event per polity pair; once contact
is established it persists.

Before contact, polities expand freely and cannot initiate war against each
other. After contact, war becomes possible every turn.

Contact is logged as a `GameEvent`. The polities involved and the system
where contact occurred are recorded.

---

## War initiation

Each turn, for every pair of polities that are in contact but not already at
war, the simulation rolls for war initiation:

1. Roll 2d6
2. Apply `aggression` as a positive DM (higher aggression = more likely to
   start war)
3. Apply additional DMs for recent provocations (contested systems,
   fleet incursions into claimed space)
4. If the modified result meets or exceeds the threshold, war is declared

War declaration is logged as a `GameEvent`. The polity that crossed the
threshold is recorded as the initiator.

Peace is not modelled in Version 1 — war, once declared, continues until
one polity is destroyed or reduced to its homeworld. Ceasefire and diplomacy
are deferred.

---

## Admirals

### Generation

Admirals are not assigned to fleets in peacetime. They are generated
**on demand** when a group of squadrons with no admiral enters a system
containing hostile forces. The moment of first contact creates the admiral
who will command that engagement.

Each starting polity is given one admiral for its primary fleet at
initialisation — the only exception to the on-demand rule.

Admiral attributes:
- `admiral_id` — sequential integer; lower = more senior (longer commissioned)
- `polity_id` — owning polity
- `name` — generated name for flavour and log readability
- `seniority` — same as `admiral_id` within a polity; used to resolve command
  when forces combine
- `tactical_factor` — integer modifier applied to combat rolls (see generation
  below)
- `created_tick` — when commissioned; log anchor

### Seniority and combined command (FFW rule)

When two or more friendly fleets from the same polity are in the same system,
command of all forces consolidates under the **most senior admiral present**
(lowest `admiral_id`). The junior admiral's forces join the senior's command;
the junior admiral remains present but does not apply their tactical factor.

If the senior admiral's squadron is destroyed during combat, command passes
immediately to the next most senior admiral in the system. An admiral with
no surviving ships under their direct command is not destroyed — they are
assumed to transfer flag — but if all ships in the system are lost, the
admiral is listed as killed or captured in the event log.

This rule means a veteran admiral who has been fighting for years can have
command stripped by a freshly-commissioned senior who arrives with
reinforcements. The seniority sequence is global and permanent: the first
admiral ever commissioned in a polity is always most senior, regardless of
their current assignment.

### Tactical factor generation

On generation, roll the admiral's `tactical_factor` using a species-biased
procedure:

**Base roll:** 2d6, drop lowest die, subtract 5. Raw range −4 to +7, but
clipped to −3 to +3 for Version 1.

**Species bias modifiers to the mean:**

| Parameter | Effect |
|---|---|
| `adaptability` | +1 to mean if ≥ 0.7; −1 if ≤ 0.3. Flexible thinking makes better tacticians. |
| `aggression` | +0.5 to mean if ≥ 0.7. Military culture produces more experienced officers. |
| `hierarchy_tolerance` | High (≥ 0.7): tighten variance (officers selected by seniority, not merit — consistent but seldom brilliant). Low (≤ 0.3): widen variance (meritocratic or chaotic selection — more extremes). |
| `social_cohesion` | High (≥ 0.8): tighten variance (shared doctrine, uniform training). Low (≤ 0.3): widen variance (fragmented institutions produce unpredictable officers). |
| `risk_appetite` | Widens variance. High-risk species produce gamblers and reckless commanders as often as brilliant ones. |
| `lifespan_years` | Long-lived species (> 200 yr) add +0.5 to mean — officers have decades of experience before flag rank. Short-lived (< 30 yr) subtract −0.5. |

Modifiers to the mean are additive and applied before the clip. Variance
modifications change the die-drop mechanic (tight variance: drop highest as
well as lowest; wide variance: keep both dice and take the larger).

The result is that species with high `adaptability`, high `aggression`, and
long lifespans produce reliably capable admirals; species with high
`risk_appetite` and low `social_cohesion` produce a wild spread — the
occasional genius alongside genuine incompetents.

### Tactical factor use

The commanding admiral's `tactical_factor` is applied as a DM to:
- Combat strength comparison rolls
- Disengage threshold evaluation (positive factor = recognises a losing
  position sooner and extracts in better order)
- Pursuit decision (positive factor = more effectively exploits a retreating
  enemy)

Admirals do not generate orders. The polity decision engine generates all
orders; the admiral's tactical factor modifies how well those orders are
executed.

---

## System control and starport

A system is either **uncontrolled** or in one of four control states for a
given polity. Control states are aligned with Traveller starport types:

| State | Starport equivalent | Meaning |
|---|---|---|
| **Outpost** | Type E/X | Minimal installation; no planetary defence; minimal resource extraction |
| **Colony** | Type C/D | Established civilian presence; light defence; resource extraction underway |
| **Controlled** | Type A/B | Full administrative control; planetary defences; full resource output |
| **Contested** | — | Two or more polities claim the system; control is unresolved |

A system can be Controlled by one polity and simultaneously Contested by
another initiating an assault. Control state changes are logged as events.

**Habitability gate:** A colony (Type C/D or above) requires that the
target world be compatible with the polity's species. A world outside the
species' atmospheric and temperature tolerance can support an Outpost only —
no civilian population, no growth track. Outposts can be established on
any world with sufficient resource value regardless of habitability.

**Growth cycle:** Population level and effective starport rating advance on
a 25-week cycle, not continuously. At each 25-week checkpoint, a system
that has met the prerequisites (sufficient RU investment, no active combat,
adequate garrison) may advance one step on the control track. Advancement is
not guaranteed — a probability roll modified by `expansionism` and local
stability determines whether the step occurs.

**Naval superiority is a prerequisite for ground assault.** A polity cannot
establish or upgrade a ground presence in a system where an opposing fleet
controls the space above it. This is the central FFW mechanic preserved
directly.

---

## Ships and fleets

Ships are abstracted to **hull classes** at the fleet level. Version 1 has
six fleet hull types plus individually-tracked light units:

| Type | Role |
|---|---|
| **Capital** | Dreadnought-class battle line; highest attack, bombardment, and defence; slow, expensive |
| **Old Capital** | Pre-dreadnought; outclassed by Capitals in fleet action but still decisive; cheaper |
| **Cruiser** | Armoured cruiser; patrol, line escort, independent raids; good bombardment |
| **Escort** | Destroyer/light cruiser; screening, picket, convoy |
| **Transport** | Cargo and troop movement; no combat value; essential for logistics |
| **Troop** | Dedicated ground-force carrier; light defence; assault operations |

Each hull class has fixed ratings for:
- **Attack** — offensive space combat strength
- **Bombardment** — offensive strength used against planetary targets and
  surface defences; separate from Attack because attacking worlds requires
  dedicated firepower
- **Defence** — defensive combat strength
- **Jump range** — parsecs per jump at Version 1 tech level: Capital J3,
  Old Capital J2, Cruiser/Escort/Scout J4, all Transports J3, SDB J0
- **Cargo capacity** — in resource units (for transports) or troop units
- **Build cost** — resource units
- **Build time** — ticks to complete at a shipyard
- **Maintenance cost** — RU per tick

A **fleet** is a named group of one or more hulls at a location. Fleets
move together. Individual hulls do not move independently except scouts,
couriers, and SDBs (see below).

**Scouts and couriers** are tracked individually because they carry
information. For Version 1, all polities are assumed to have perfect
positional information within their controlled space. Individual scout
positions matter for contact detection (see Contact section).

**System Defence Boats (SDBs)** have no jump drive and cannot move between
systems under their own power. They are delivered by Transport hulls and
require 1 tick to establish themselves on arrival before contributing to
system defence. Once established they are fixed permanently. SDBs are tracked
individually — each has its own ID, ratings, and damage state — and
contribute their defence rating to the system total and attack rating in
combat when hostile fleets enter their system.

---

## Refuelling

All hulls require periodic resupply of reaction mass and consumables. In
Version 1 (all hulls jump-0) this is an operational logistics concern rather
than a per-jump cost. The question is whether a deployed fleet can sustain
itself in a distant system.

**Extended operations penalty:** A fleet that goes more than 8 ticks without
a resupply source incurs double maintenance cost. At 16 ticks, combat ratings
degrade by 1 (treated as partially damaged) until resupply is reached.

Resupply sources, in order of strategic importance:

| Source | Cost | Time | Constraint |
|---|---|---|---|
| **Gas giant skimming** | Free | 1 tick stationary | Fleet cannot conduct combat during skim tick; available in any system with a GG |
| **Ocean world** | Free | Immediate on arrival | Any world with hydrosphere ≥ 0.5 under friendly or occupied control |
| **Starport** (Colony+) | 1 RU/hull | Immediate | Friendly Colony or above |
| **Naval base** | Free | Immediate | Flag on a Controlled system |
| **Fuel tender** | — | Same tick | Designated Transport expends 10 RU cargo to resupply up to 4 hulls |

**Gas giant as strategic anchor:** Any system with a gas giant is a
potential indefinite operation point for any fleet willing to sacrifice one
tick per eight to skim. A polity can maintain a blockade or occupation
without a local starport as long as the system has a gas giant. Denying
this requires keeping a hostile fleet in the system — which faces the same
supply problem. This is the FFW refuelling mechanic preserved directly.

---

## Ground forces

Ground forces consist of **Army units** — an abstracted strength value
representing conventional ground combat capability. They are raised on
colonies and controlled worlds, transported by Troop or Transport hulls,
and expended in ground combat.

A ground assault requires:
1. Naval superiority in the target system
2. At least one Troop or Transport hull in the assault fleet carrying Army units
3. A ground combat resolution step

If the target system has planetary defences (Controlled state), the attacker
must first conduct a **bombardment phase** using fleet Bombardment ratings
before landing. Bombardment can degrade defender strength before ground
combat resolves.

Ground combat resolution: attacker strength vs defender strength (Army units
plus any surviving SDB ground contribution) with a random modifier (2d6
differential, FFW-style). Winner holds the world; loser's Army units are
destroyed or retreated to an embarked fleet if one is present.

---

## Combat

Space combat occurs when two hostile fleets (including SDBs) occupy the
same system. Resolution:

1. Compute total Attack strength for each side (fleet Attack ratings + SDB
   Attack ratings for the defending side)
2. Apply commanding admiral's `tactical_factor` as a DM
3. Roll 2d6 for each side; subtract lower from higher as a net shift
4. Apply net shift to a damage table — results are: *no effect / one hull
   damaged / one hull destroyed / multiple hulls destroyed / fleet broken*
5. Damaged hulls have halved combat ratings until repaired at a shipyard
6. Losing fleet retreats to the nearest friendly system or is destroyed if
   retreat is impossible

SDBs cannot retreat — a destroyed SDB is removed permanently. If the
defending side loses, SDBs are destroyed in place.

The damage table concept is applied to strength totals rather than individual
counters. Version 1 does not model individual ship manoeuvre, formation
tactics, or weapon types.

---

## Shipbuilding

Ships are built at systems with a **shipyard**. A shipyard is a flag on a
system's control record; it requires the system to be at Colony level or
above, and costs RU to establish.

Build procedure:
1. Polity decision engine places a build order specifying hull class and system
2. A build queue entry is created with the hull class, total build time, and
   ticks elapsed
3. Each tick, the Economy phase advances all active build queue entries by 1
4. When ticks elapsed equals build time, the hull is completed and added to
   the system's garrison fleet (or a designated fleet)
5. Build cost RU is deducted in full when the order is placed (reservation
   model — simplest to implement correctly)

Multiple hulls can be under construction simultaneously at the same shipyard.
There is no shipyard capacity limit in Version 1.

---

## Repair

Damaged hulls (halved combat ratings) are repaired at any system with a
shipyard. Repair is not instantaneous:

- Each damaged hull requires **repair time** (TBD: a fixed number of ticks,
  probably 4) at a shipyard
- Repair cost is a fraction of the original build cost (TBD: 25%)
- A hull in a repair queue contributes nothing to fleet combat ratings until
  repair is complete

A hull can be moved to a different system while damaged; repair begins only
when it arrives at a system with an active shipyard.

---

## Economy

Version 1 uses a single resource: **Resource Units (RU)**.

### World potential

Each world has a **world potential** — a fixed integer derived once from
physical data in the DB and never changed. It represents the raw extractive
and productive value of the body regardless of who occupies it.

Derivation from existing DB fields:

| Condition | Points |
|---|---|
| `in_hz = 1` | +10 |
| `atm_type` in `standard`, `dense` | +5 |
| `hydrosphere` > 0.5 | +5 |
| `hydrosphere` 0.1–0.5 | +2 |
| `planet_class` rocky or terrestrial | +3 |
| `mass` 0.5–2.0 Mₑ | +2 |
| `atm_type = corrosive` | −8 |
| `atm_type` in `none`, `trace` | −3 |
| Minimum | 1 |

Typical results: prime HZ earthlike ≈ 25; marginal HZ world ≈ 12–15;
hostile rocky ≈ 3–5; airless rock ≈ 2. Any body has at least 1 (there is
always something worth extracting).

### Development level

Each controlled system has a **development level** (integer 0–5) tracking
accumulated investment — infrastructure, population, industrial capacity.
Development starts at 0 for a newly-contacted system and advances via
colonist unit deliveries and the 25-week growth cycle.

Development level caps by control state:
- Outpost: max development 1
- Colony: max development 3
- Controlled: max development 5

### RU production formula

```
RU/tick = world_potential × control_multiplier × development_multiplier
```

| Control state | Control multiplier |
|---|---|
| Outpost | 0.10 |
| Colony | 0.40 |
| Controlled | 1.00 |

| Development level | Development multiplier |
|---|---|
| 0 | 0.5 |
| 1 | 0.7 |
| 2 | 0.9 |
| 3 | 1.0 |
| 4 | 1.2 |
| 5 | 1.5 |

Example: a prime world (potential 25) at Controlled/dev-5 produces
37 RU/tick. The same world as a new outpost (dev-0) produces 1.25 RU/tick —
enough to justify holding it, not enough to fund a war from.

The habitability cap is implicit: a species-incompatible world is capped at
Outpost, which caps the control multiplier at 0.10 regardless of development.

### Colonist units and development

Development advances through **colonist unit deliveries** made by colony
transports. Each delivery increments development level by 1 (subject to the
control state cap). At Colony and Controlled level, natural population growth
also provides slow development increments without transport — development
can inch forward without resupply, but significantly slower.

The colonist unit requirement to advance control state (subject to the
25-week growth cycle check):

| Transition | Colonist deliveries required |
|---|---|
| → Outpost (establish) | 1 |
| Outpost → Colony | 3 |
| Colony → Controlled | 5 |

### RU expenditure

RU are spent on:
- Ship construction (full cost reserved at order placement)
- Ground force raising (at any Colony or Controlled world)
- Maintenance (flat per-hull cost per tick; unmet maintenance degrades combat
  rating)
- Shipyard establishment (Colony or above required)
- Repair (25% of build cost, 4 ticks at a shipyard)

There is no trade, no market, no inter-polity economic interaction in Version 1.
Those are deferred.

---

## Polity decision engine

The polity decision engine is not a search or planning system. It is a
**parameterised behavioural model** — weighted probability tables whose
weights derive from species disposition parameters and current game state.
The goal is not optimal play; it is species-consistent decisions that
generate plausible history.

Every polity runs the engine once per tick during the Decision phase.

### Posture

The engine first sets a strategic posture for the tick, drawn from a
probability distribution:

| Posture | Meaning |
|---|---|
| **Expand** | Prioritise scouting and colony establishment |
| **Consolidate** | Invest in existing systems; build economy and garrison |
| **Prepare** | Build military assets; hold expansion |
| **Prosecute** | At war; prioritise offensive operations |

Posture is not a rigid state machine. It is a weighted draw: a high-`expansionism`
species pulls Expand most ticks in peacetime; a high-`aggression` species near a
known contact pulls Prepare before war is declared; a polity under attack may run
Prosecute in contested theatres and Consolidate in rear systems simultaneously.

### Action scoring

Given the current posture, the engine scores all candidate actions:

```
score = base_utility
      + f(disposition_parameters)
      + f(game_state)
      + f(grievance_memory)
```

Candidate actions:

| Action | Primary disposition drivers |
|---|---|
| Scout a system | `expansionism`; adjacent unknown systems |
| Establish outpost/colony | `expansionism`; habitability; resource value |
| Build combat hulls | `aggression`; proximity to contact |
| Build transports/scouts | `expansionism` |
| Raise Army units | `aggression`; contested systems nearby |
| Move fleet to location | `risk_appetite`; threat assessment |
| Initiate war (roll) | `aggression` DM; provocation accumulation |
| Assault a system | Wartime; `risk_appetite` governs force committed |
| Consolidate system | `expansionism`; 25-week growth checkpoint proximity |

### Action selection

Top-scored actions are selected with soft randomness — the highest-utility
action wins most of the time, but the engine occasionally draws a lower-ranked
option. This prevents perfectly predictable play and generates the occasional
surprising historical move without dissolving species identity into noise.

### Species behavioural fingerprints

The disposition parameters produce distinct emergent profiles:

- A high-`aggression`, high-`risk_appetite`, low-`grievance_memory` polity
  expands aggressively, hits first on contact, and fights short total wars —
  they don't hold grudges because the grievance resolves immediately.

- A high-`grievance_memory`, moderate-`aggression` polity tolerates provocation
  for a long time, accumulating modifier debt, then responds with disproportionate
  force when the threshold finally breaks. The event log shows a quiet polity
  that launches a devastating campaign.

- Human polities — multiple, identical species parameters but diverging
  histories — will fight each other as readily as other species. High
  `faction_tendency` may trigger further splits under sustained war stress.

### Noise calibration

The disposition parameters must be spread far enough apart between species
that behavioural fingerprints survive the noise floor. If the random component
is too large, every species plays identically across runs; if too small, outcomes
are predetermined. Tuning this is an empirical task once the first runs complete.

---

## Tactical decisions

The decision engine operates at strategic and operational scale above. Within
a single combat engagement, a separate layer of tactical decisions fires during
the Combat phase. These use the same utility-scoring structure but with a much
shorter time horizon — the relevant state is the current engagement, not the
polity's long-term position.

### Engagement decision

Before a fleet enters a system known to contain hostile forces, the engine
decides whether to enter and fight or hold outside.

Inputs:
- Estimated strength ratio (own fleet vs known enemy)
- `risk_appetite` — low appetite avoids unfavourable ratios
- Strategic necessity — a polity cannot decline battle over its own homeworld
- Objective — probe vs committed assault

### Disengage decision

After each combat exchange, the damaged or losing side evaluates whether to
press on or disengage.

Inputs:
- Remaining strength vs estimated enemy remaining strength
- `risk_appetite` — sets the threshold at which retreat looks better than
  continued engagement
- Fleet condition — multiple already-damaged hulls lower the disengage
  threshold further
- Retreat availability — if no friendly system exists to retreat to, fighting
  to destruction may be the only option
- Objective value — do not disengage when defending a homeworld or capital
- Admiral `tactical_factor` — a skilled admiral recognises a losing position
  sooner and extracts in better order; a poor one commits too long

A high-`risk_appetite` polity fights longer. A low-`risk_appetite` polity
disengages as soon as an exchange goes against them.

### Pursuit decision

When the enemy disengages, the winning side decides whether to pursue.

Inputs:
- Own fleet condition (heavily damaged fleets do not pursue)
- `aggression` — high aggression favours pursuit to destroy fleet capacity
- Objective — if the goal was to take the system, holding is better than
  chasing; if the goal is attrition, pursue
- Destination risk — pursuing into a fortified system is penalised
- Admiral `tactical_factor` — positive factor improves exploitation of a
  retreating enemy

### Retreat destination

When disengaging, the engine selects where to retreat:
- Default: nearest friendly controlled system
- Preferred if hulls are damaged: a system with a shipyard
- Excluded: any system containing another hostile fleet

### Bombardment timing

When naval superiority exists and Army units are available, the engine
decides whether to bombard before landing or assault directly.

Inputs:
- Defender strength estimate (high defenders → bombard first)
- Own Army unit strength (thin attacking force → reduce defenders first)
- `risk_appetite` — low risk bombards even against weak defenders
- Fleet Bombardment rating available

The engine may elect to bombard over multiple ticks before committing ground
forces rather than assaulting in the same tick naval superiority is established.

---

## Tick structure

One tick = one week of simulated time. Within each tick, phases resolve in
order:

1. **Intelligence** — scouts report full system data for newly visited systems;
   passive 20-parsec scan updates refuelling map for all systems in range;
   52-week peace clock checked for intelligence-sharing events; polity decision
   engine evaluates current state including route options; contact detection runs
2. **Decision** — each polity decision engine generates orders (move fleets,
   begin construction, assign Army units, war initiation roll if in contact)
3. **Movement** — fleets execute one jump or in-system transit
4. **Combat** — space combat resolves in contested systems; SDBs engage;
   engagement, disengage, and pursuit decisions evaluated
5. **Bombardment** — orbital bombardment of planetary defences where naval
   superiority exists; bombardment timing decision evaluated
6. **Ground assault** — ground combat resolves where naval superiority exists
   and Army units are present
7. **Control update** — system control states updated; 25-week growth cycle
   checkpoints evaluated
8. **Economy** — RU collected; construction advanced (build queues ticked);
   maintenance paid; repair advanced
9. **Event log** — significant events written; monthly summary if quiet

---

## History logging

Every control state change, every combat engagement, every fleet loss, every
contact event, every war declaration, and every significant tactical decision
(disengage, pursuit, bombardment elected) is logged as a `GameEvent` with
tick, phase, polities involved, location, and a short structured summary.
The LLM historian reads this log; the log must be self-contained enough that
a historian with no other context can reconstruct what happened and why.

During quiet periods (no combat, no control changes, no new colonies) a
monthly summary record is written instead of weekly entries.

---

## Deferred — explicitly out of scope for Version 1

- Tech progression beyond starting level
- Extended jump range (J5+; researched as a milestone)
- Information lag and imperfect intelligence
- Diplomatic state (treaties, alliances, non-aggression pacts, peace)
- Trade and inter-polity economics
- Terraforming
- Biosphere interaction
- Species cultural drift and faction splitting
- Individual RPG-scale events
- Any observer or player interface
- Admiral advance-plotting and planning-factor mechanics
- Shipyard capacity limits
- Polity disposition drift over time
