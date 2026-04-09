# Version 1 — Unit Types

Fixed menu of squadron and ground unit types for the initial simulation.
All values are starting points to be tuned empirically once the first runs
complete. Build times are in ticks (1 tick = 1 week).

---

## Squadron types

All Version 1 hulls have jump range 0 (in-system only). Jump drive is a
future research milestone.

| Type | Attack | Bombard | Defence | Cargo | Build cost (RU) | Build time (ticks) | Maint (RU/tick) | Notes |
|---|---|---|---|---|---|---|---|---|
| **Capital** | 4 | 3 | 4 | — | 40 | 20 | 2 | Primary line combatant |
| **Escort** | 2 | 1 | 2 | — | 15 | 10 | 1 | Screening; patrol |
| **Troop** | 0 | 0 | 2 | 4 Army | 12 | 8 | 1 | Dedicated assault carrier |
| **Transport** | 0 | 0 | 1 | 20 RU | 10 | 8 | 1 | Cargo; can carry 2 Army units in lieu of cargo |
| **Scout** | 0 | 0 | 1 | — | 5 | 5 | 0 | Contact detection; individually tracked |
| **SDB** | 2 | 2 | 3 | — | 8 | 6 | 1 | System fixed; cannot move; individually tracked |

**Cargo column:** "—" means no cargo capacity. Troop hulls carry Army units
only. Transports carry RU cargo or up to 2 Army units (at the cost of 10 RU
cargo capacity per unit embarked).

**SDB note:** Built at the system they will defend; cannot be reassigned.
Destroyed in place if their system falls. No retreat.

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
| **Army** | 4 | Yes | 6 | 4 | 1 | Mobile assault and defence; Colony or above to raise |

**Garrison note:** Garrisons defend a specific world and contribute their
strength to ground combat on that world only. They cannot be loaded onto
hulls. They are destroyed or captured if their world is taken; they do not
retreat.

**Army note:** Army units are transported by Troop hulls (up to 4 units) or
Transport hulls (up to 2 units, displacing cargo). Army units can both attack
and defend. A retreating ground force that has an embarked fleet available
may withdraw; otherwise it is destroyed.

**Bombard interaction:** Bombardment from orbit reduces defender strength
before ground combat resolves. Each point of net Bombardment advantage
reduces defending strength by 1 (minimum 1) before the ground combat roll.

---

## Build location constraints

| Unit | Requires |
|---|---|
| Capital, Escort, Troop, Transport, Scout | Shipyard (Colony level or above) |
| SDB | Shipyard at the defending system |
| Army | Colony or Controlled world (no shipyard needed) |
| Garrison | Any system presence (Outpost or above) |

---

## Economic reference

These ratios are the intended starting balance. Adjust after first runs.

| Relationship | Intended feel |
|---|---|
| Capital costs 40 RU | A major strategic commitment; not a routine purchase |
| Escort costs 15 RU | Affordable in quantity for a mid-sized economy |
| SDB costs 8 RU | Cheap enough to fortify multiple systems; no mobility premium |
| Army costs 6 RU | Ground forces are cheaper than ships; attritional warfare is viable |
| Garrison costs 3 RU | Any outpost can maintain basic defence |
| Capital maintenance 2 RU/tick | A fleet of 5 Capitals costs 10 RU/week; a real ongoing drain |
| Army maintenance 1 RU/tick | A large standing army is expensive; encourages offensive resolution |
