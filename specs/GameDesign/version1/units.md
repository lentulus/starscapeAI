# Version 1 — Unit Types

Fixed menu of squadron and ground unit types for the initial simulation.
All values are starting points to be tuned empirically once the first runs
complete. Build times are in ticks (1 tick = 1 week).

---

## Squadron types

Jump ranges reflect standard drives at Version 1 tech level. SDBs have no
jump drive; all other hulls jump independently except as noted.

| Type | Attack | Bombard | Defence | Jump | Cargo | Build cost (RU) | Build time (ticks) | Maint (RU/tick) | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **Capital** | 4 | 3 | 4 | 3 | — | 40 | 20 | 2.0 | Dreadnought-class battle line |
| **Old Capital** | 3 | 2 | 3 | 2 | — | 28 | 16 | 1.5 | Pre-dreadnought; outclassed by Capitals but cheaper; limited jump range |
| **Cruiser** | 2 | 2 | 2 | 4 | — | 20 | 12 | 1.0 | Armoured cruiser; best jump range of combat hulls; patrol and independent raids |
| **Escort** | 1 | 0 | 1 | 4 | — | 8 | 6 | 0.5 | Destroyer/light cruiser; screening, picket, convoy |
| **Troop** | 0 | 0 | 1 | 3 | 4 Army | 10 | 7 | 0.5 | Dedicated assault carrier |
| **Transport** | 0 | 0 | 1 | 3 | 20 RU | 8 | 6 | 0.5 | Cargo; can carry 2 Army in lieu of 10 RU cargo; can deliver SDBs |
| **Colony transport** | 0 | 0 | 1 | 3 | 4 colonists | 10 | 7 | 0.5 | Colonist and equipment carrier; drives expansion |
| **Scout** | 0 | 0 | 0 | 4 | — | 4 | 4 | 0 | Contact detection; highest jump range; individually tracked |
| **SDB** | 2 | 2 | 3 | 0 | — | 6 | 5 | 0.5 | System fixed; no jump drive; delivered by Transport |

**Old Capital note:** Outmatched in a straight fight against an equal number
of Capitals — net shift will consistently favour the Capital side. Still
valuable for: bombardment operations, numerical bulk in combined fleet
actions, garrisoning secondary systems where a full Capital would be wasted.
They will be built by cost-constrained polities and retired as Capitals
become affordable.

**Colony transport note:** Carries colonist units — people, prefabricated
infrastructure, seed stock, equipment. Colonist deliveries are required to
establish outposts, advance control state, and raise development level.
Colony transports have no combat or cargo role; they cannot carry Army units
or RU. Individually tracked like scouts because position matters for
logistics planning.

**SDB note:** SDBs have no jump drive and cannot move between systems under
their own power. They can be delivered to a new system by a Transport hull
(carried as cargo, displacing 10 RU of capacity). On arrival, the SDB
requires 1 tick to establish itself — anchoring to local infrastructure,
spinning up sensors, calibrating orbital position — before it contributes
its ratings to system defence. During that establishment tick it is present
but inactive. Once established, it is fixed and cannot be recovered.
Destroyed in place if their system falls; no retreat.

**Damaged state:** Any hull reduced to damaged status fights at half Attack
and half Defence ratings (Bombardment unaffected — a damaged capital can
still shell a planet). Damaged hulls are repaired at a shipyard at 25% of
build cost over 4 ticks.

---

## Ground unit types

Ground units are raised at Colony or Controlled worlds. Garrison units
cannot be embarked; they are defensive installations only.

| Type | Strength | Embarkable | Build cost (RU) | Build time (ticks) | Maint (RU/tick) | Notes |
|---|---|---|---|---|---|---|
| **Garrison** | 2 | No | 3 | 2 | 0 | Defensive only; raised at any Outpost or above |
| **Army** | 4 | Yes | 6 | 4 | 0.5 | Mobile assault and defence; Colony or above to raise |

**Garrison note:** Defends a specific world only. Cannot be loaded onto
hulls. Destroyed or captured if their world falls; they do not retreat.

**Army note:** Transported by Troop hulls (up to 4 units) or Transport
hulls (up to 2 units, displacing 10 RU cargo). Can attack and defend. A
retreating ground force with an available fleet may withdraw; otherwise
destroyed.

**Bombard interaction:** Each point of net Bombardment advantage reduces
defending strength by 1 (minimum 1) before the ground combat roll.

---

## Refuelling

All hulls require periodic resupply of reaction mass, consumables, and power
plant fuel. In Version 1 (jump-0) this is an operational concern for fleets
on extended deployment rather than a per-jump cost. The mechanic matters most
for fleets operating away from home — the question is whether you can sustain
a force in a distant system indefinitely.

**Extended operations penalty:** A fleet that goes more than 8 ticks without
accessing a resupply source incurs double maintenance cost until resupplied.
At 16 ticks without resupply, combat ratings degrade by 1 (as if damaged)
until the fleet returns to a supply source.

### Resupply sources

| Source | Cost | Time | Notes |
|---|---|---|---|
| **Gas giant skimming** | Free | 1 tick stationary at GG | Unrefined; available in any system with a gas giant; fleet cannot conduct combat operations during skimming tick |
| **Ocean world** | Free | Same tick as arrival | Partially refined; any world with hydrosphere ≥ 0.5 that the polity controls or occupies |
| **Starport** (Colony+) | 1 RU per hull | Immediate | Refined fuel; requires the system to be at Colony or above under friendly control |
| **Naval base** | Free | Immediate | Refined; a naval base flag on a Controlled system; built as part of system fortification |
| **Fuel tender** | — | Same tick | A Transport designated as tender expends 10 RU of its cargo as fuel, resupplying up to 4 hulls |

**Gas giant strategic note:** Every system with a gas giant is a potential
sustained operation point for any fleet willing to spend a stationary tick.
This is the FFW mechanic preserved directly: a polity can maintain a blockade
or occupation indefinitely as long as they can skim. Denying an enemy gas
giant access requires keeping a hostile fleet in the system, which itself
requires its own supply.

**Fuel tender operations:** A Transport hull designated as a fuel tender
sacrifices its cargo role for the operation. It can resupply other hulls
from its cargo at a rate of 10 RU per 4 hulls per tick. A tender ship on
its own extended deployment still needs to skim or reach a starport.

---

## Build location constraints

| Unit | Requires |
|---|---|
| Capital, Old Capital, Cruiser, Escort, Troop, Transport, Colony transport, Scout | Shipyard (Colony level or above) |
| SDB | Shipyard at the defending system |
| Army | Colony or Controlled world (no shipyard needed) |
| Garrison | Any system presence (Outpost or above) |

---

## Economic reference

These ratios are the intended starting balance. Adjust after first runs.

A well-established homeworld with three productive colonies (≈ 57 RU/tick)
maintaining a fleet equivalent to the German High Seas Fleet in 1914 should
spend roughly 55–65% of income on fleet and garrison maintenance. The
starting force (homeworld only, ≈ 25 RU/tick) is sized to consume ≈ 50% on
maintenance, leaving headroom for construction and economic development.

| Relationship | Intended feel |
|---|---|
| Capital costs 40 RU | Major strategic commitment; takes 20 weeks to build; not ordered casually |
| Old Capital costs 28 RU | Affordable backbone of a growing fleet; outclassed but available |
| Cruiser costs 20 RU | Workhorse; bulk of independent patrol and line-support work |
| Escort costs 8 RU | Cheap in quantity; lose them without strategic consequence |
| SDB costs 6 RU | Cheaper than an Escort; fortify multiple systems; no mobility premium |
| Army costs 6 RU | Ground forces affordable relative to ships; attritional ground war is viable |
| Garrison costs 3 RU | Any outpost can maintain basic defence at minimal cost |
| Capital maintenance 2/tick | A fleet of 5 Capitals costs 10 RU/week continuously |
| Army maintenance 0.5/tick | Large standing armies are an ongoing drain; encourages offensive resolution |
