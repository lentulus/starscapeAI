# Version 1 — Starting Orders of Battle

Starting forces for each species at tick 0. All values should be treated as
initial estimates; tune after the first simulation runs.

---

## Calibration

**Economic baseline used:**
- Homeworld only (Controlled/dev-3): ≈ 25 RU/tick
- Homeworld + 3 productive colonies: ≈ 57 RU/tick

**Target:** A polity with a homeworld and three productive colonies should
be able to sustain a fleet roughly equivalent to the German High Seas Fleet
in August 1914 — a serious regional power with a credible battle line, not
a global hegemon. That fleet spends roughly 55–65% of income on maintenance.

**German High Seas Fleet equivalent (goal state):**

| Formation | Units |
|---|---|
| Battle line | 4 Capitals, 5 Old Capitals |
| Cruiser force | 4 Cruisers |
| Destroyer flotillas | 10 Escorts |
| Logistics | 2 Transports, 1 Troop, 1 Colony transport |
| Scouting | 2 Scouts |
| System defence | 12 SDBs (distributed across homeworld + 3 colonies) |
| Ground | 6 Army, 8 Garrison |

Fleet maintenance: ≈ 35 RU/tick (61% of 57 RU/tick income)

**Starting force derivation:** The homeworld economy (25 RU/tick) supports
roughly 45% of the goal state. Starting forces are scaled accordingly and
rounded to whole units, targeting ≈ 50% of income in maintenance.

---

## Neutral baseline starting OB

Used as the reference point. Species OBs are derived from this by varying
composition within the same approximate maintenance budget.

**Fleet (maintenance: 9.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Colony transport | 1 | 0.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 2.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 4 | 2.0 |
| Army | 2 | 1.0 |
| Garrison | 4 | 0 |

**Total maintenance: 12 RU/tick (48% of 25 RU/tick income)**

---

## Species starting OBs

Each entry shows the fleet, homeworld forces, total maintenance, and a brief
note on the disposition logic driving the composition differences.

---

### Kreeth

*Aggression 0.95 · Expansionism 0.90 · Risk appetite 0.40 · Social cohesion 0.98*

Methodical and relentless. The Brains plan; the Warriors execute without
hesitation. The starting fleet is skewed toward capital firepower and
defensive infrastructure over logistics — they establish presence by force
and then hold it. No Colony transports: initial outposts are military
installations, not civilian settlements.

**Fleet (maintenance: 11.0 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 2 | 4.0 |
| Old Capital | 3 | 4.5 |
| Cruiser | 1 | 1.0 |
| Escort | 3 | 1.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 5.0 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 6 | 3.0 |
| Army | 4 | 2.0 |
| Garrison | 6 | 0 |

**Total maintenance: 16 RU/tick (64% of income — always mobilised)**

---

### Vashori

*Aggression 0.40 · Expansionism 0.30 · Risk appetite 0.60 · Xenophilia 0.85*

Diplomatic traders with a long stable civilisation. The fleet is a
coast-guard and prestige instrument, not a war machine. More Transports and
Colony transports than the baseline; fewer Capitals. Two Scouts reflect a
species that wants to meet neighbours, not conquer them.

**Fleet (maintenance: 8.0 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 1 | 1.5 |
| Cruiser | 1 | 1.0 |
| Escort | 4 | 2.0 |
| Transport | 2 | 1.0 |
| Colony transport | 2 | 1.0 |
| Scout | 2 | 0 |

**Homeworld defence (maintenance: 2.0 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 3 | 1.5 |
| Army | 1 | 0.5 |
| Garrison | 4 | 0 |

**Total maintenance: 10 RU/tick (40% of income — economic headroom retained)**

---

### Kraathi

*Aggression 0.75 · Expansionism 0.95 · Risk appetite 0.45 · Adaptability 0.20*

The G'naak crusade requires both military force and colonisation capacity.
The starting OB emphasises Troop and Colony transports alongside a solid
battle line — they need to reach new systems and claim them, not just
bombard them. Heavy homeworld SDB installation reflects species paranoia
about carnivore threats.

**Fleet (maintenance: 10.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Troop | 1 | 0.5 |
| Colony transport | 2 | 1.0 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 3.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 5 | 2.5 |
| Army | 3 | 1.5 |
| Garrison | 4 | 0 |

**Total maintenance: 14 RU/tick (56% of income)**

---

### Nakhavi

*Aggression 0.45 · Expansionism 0.40 · Risk appetite 0.80 · Adaptability 0.95 · Xenophilia 0.90*

Curious and fast-learning but not militaristic. Short individual lifespans
mean the Nakhavi fleet cycles through crews quickly; ships outlast their
operators. Extra Scouts are the signature of a species that wants to
understand its neighbours before fighting them. Most non-homeworld worlds
are incompatible with their aquatic requirements, so Colony transports are
few — they establish Outposts, not Colonies, beyond their homeworld.

**Fleet (maintenance: 8.0 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 1 | 1.5 |
| Cruiser | 2 | 2.0 |
| Escort | 3 | 1.5 |
| Transport | 1 | 0.5 |
| Colony transport | 1 | 0.5 |
| Scout | 3 | 0 |

**Homeworld defence (maintenance: 1.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 2 | 1.0 |
| Army | 1 | 0.5 |
| Garrison | 2 | 0 |

**Total maintenance: 9.5 RU/tick (38% of income — lightest military of any species)**

---

### Skharri

*Aggression 0.95 · Expansionism 0.90 · Risk appetite 0.90 · Grievance memory 0.95*

Maximum aggression and maximum risk appetite. The starting fleet is the
heaviest combat-skewed of all species — Capital-heavy, minimal logistics,
minimal SDBs (honour is offence, not defence). Troop hull for ground assault
reflects the cultural imperative of face-to-face conquest. They will attack
before their fleet plan is complete; that is the point.

**Fleet (maintenance: 13.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 2 | 4.0 |
| Old Capital | 3 | 4.5 |
| Cruiser | 2 | 2.0 |
| Escort | 5 | 2.5 |
| Troop | 1 | 0.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 2.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 2 | 1.0 |
| Army | 4 | 2.0 |
| Garrison | 2 | 0 |

**Total maintenance: 16 RU/tick (64% of income — permanently on war footing)**

---

### Vaelkhi

*Aggression 0.55 · Expansionism 0.30 · Risk appetite 0.70 · Social cohesion 0.70*

Territorial defenders. The Vaelkhi fleet emphasises Escorts — fast patrol
vessels suited to a species that thinks in terms of ranges and sky-hunting
rather than massed battle. They defend what is theirs with skill and patience
rather than expanding aggressively. No Troop hull at start; they will raise
one if they need to assault, but it is not their default posture.

**Fleet (maintenance: 10.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 6 | 3.0 |
| Colony transport | 1 | 0.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 3.0 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 4 | 2.0 |
| Army | 2 | 1.0 |
| Garrison | 4 | 0 |

**Total maintenance: 13.5 RU/tick (54% of income)**

---

### Shekhari

*Aggression 0.45 · Expansionism 0.55 · Risk appetite 0.75 · Adaptability 0.85*

Traders and opportunists. The lightest combat fleet of the active military
species, offset by the most Transports and Scouts. They go everywhere and
carry everything — the fleet exists to protect trade routes, not to hold
territory. Three Scouts is the highest of any starting OB.

**Fleet (maintenance: 8.0 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 1 | 1.5 |
| Cruiser | 1 | 1.0 |
| Escort | 3 | 1.5 |
| Transport | 2 | 1.0 |
| Colony transport | 2 | 1.0 |
| Scout | 3 | 0 |

**Homeworld defence (maintenance: 1.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 2 | 1.0 |
| Army | 1 | 0.5 |
| Garrison | 3 | 0 |

**Total maintenance: 9.5 RU/tick (38% of income — minimal military overhead)**

---

### Golvhaan

*Aggression 0.30 · Expansionism 0.35 · Risk appetite 0.45 · Xenophilia 0.80*

The most peaceful species. No Capitals at start — Golvhaan do not build
them initially because they have no plans that require one. The Old Capitals
serve as their heaviest units. High-gravity homeworld produces dense
industrial infrastructure, so their SDB count is the highest of the
non-militaristic species — not aggression, just good construction. Two
Transports reflect a wide-ranging species that travels widely without
conquest intent.

**Fleet (maintenance: 8.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Transport | 2 | 1.0 |
| Colony transport | 1 | 0.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 3.5 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 6 | 3.0 |
| Army | 1 | 0.5 |
| Garrison | 4 | 0 |

**Total maintenance: 12 RU/tick (48% of income)**

---

### Nhaveth (multiple polities)

*Aggression 0.85 · Expansionism 0.90 · Faction tendency 0.90 · Grievance memory 1.00*

`faction_tendency` 0.90 places Nhaveth above the 0.85 threshold; they begin
fractured into competing courts, each controlling a portion of the homeworld
system's Kethara host population. Courts have been at war with each other
almost continuously; the simulation begins mid-conflict, not at some notional
peace. Long admiral lifespans (600 yr effective) mean every court's admirals
carry centuries of first-hand grievance — and will remember every slight
inflicted by the other courts indefinitely.

The working assumption is three starting courts. Total homeworld system
income (≈ 25 RU/tick) is divided between them with the dominant court
holding the most productive territory.

**Court A — dominant court**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 3 | 1.5 |
| Troop | 1 | 0.5 |
| Scout | 1 | 0 |
| SDB | 3 | 1.5 |
| Army | 3 | 1.5 |
| Garrison | 3 | 0 |

Maintenance: 12.0 RU/tick

**Court B — rival court**

| Hull | Count | Maint |
|---|---|---|
| Old Capital | 1 | 1.5 |
| Cruiser | 2 | 2.0 |
| Escort | 3 | 1.5 |
| Troop | 1 | 0.5 |
| Scout | 1 | 0 |
| SDB | 2 | 1.0 |
| Army | 2 | 1.0 |
| Garrison | 2 | 0 |

Maintenance: 7.5 RU/tick

**Court C — minor court**

| Hull | Count | Maint |
|---|---|---|
| Cruiser | 1 | 1.0 |
| Escort | 2 | 1.0 |
| Scout | 1 | 0 |
| SDB | 1 | 0.5 |
| Army | 2 | 1.0 |
| Garrison | 2 | 0 |

Maintenance: 3.5 RU/tick

**Combined homeworld system maintenance: 23 RU/tick (92% of income)**

The Nhaveth homeworld system is effectively fully militarised at tick 0.
Courts A and B are plausible war initiators against each other on turn 1;
Court C survives by staying out of the main conflict and controlling a
resource niche the larger courts tolerate. The first inter-Nhaveth war is
near-certain within the first year of simulation.

---

### Vardhek

*Aggression 0.70 · Expansionism 0.95 · Risk appetite 0.35 · Adaptability 0.75 · Social cohesion 0.85*

The Long View. Methodical, patient, and relentlessly expansionist. The
starting OB has the highest Colony transport count of any species — every
new system is a step on a centuries-long programme. SDB count is also high:
the Roidhunate builds infrastructure systematically. Low risk appetite means
the fleet is balanced and conservative; they will not commit Capitals
recklessly. They will still commit them, eventually, when the plan calls
for it.

**Fleet (maintenance: 10.5 RU/tick)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Transport | 1 | 0.5 |
| Colony transport | 3 | 1.5 |
| Scout | 1 | 0 |

**Homeworld defence (maintenance: 4.0 RU/tick)**

| Unit | Count | Maint |
|---|---|---|
| SDB | 6 | 3.0 |
| Army | 2 | 1.0 |
| Garrison | 4 | 0 |

**Total maintenance: 14.5 RU/tick (58% of income)**

---

### Human (multiple polities)

*Aggression 0.55 · Expansionism 0.80 · Faction tendency 0.90 · Adaptability 0.90*

Humans do not start as a single polity. The Sol system is divided among
competing powers at tick 0, already in political tension. The initialisation
script determines the exact number; three is the working assumption.

Each human polity receives a fraction of the standard OB, sized by relative
starting weight. The example below assumes three polities with a dominant
power (Earth-centred), a mid-weight rival (Mars-centred), and a smaller
outer-system presence.

**Polity A — dominant (Earth / inner system)**

| Hull | Count | Maint |
|---|---|---|
| Capital | 1 | 2.0 |
| Old Capital | 2 | 3.0 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Transport | 1 | 0.5 |
| Colony transport | 1 | 0.5 |
| Scout | 1 | 0 |
| SDB | 4 | 2.0 |
| Army | 3 | 1.5 |
| Garrison | 4 | 0 |

Maintenance: 13.5 RU/tick

**Polity B — mid-weight rival (Mars)**

| Hull | Count | Maint |
|---|---|---|
| Old Capital | 1 | 1.5 |
| Cruiser | 2 | 2.0 |
| Escort | 4 | 2.0 |
| Colony transport | 1 | 0.5 |
| Scout | 2 | 0 |
| SDB | 3 | 1.5 |
| Army | 2 | 1.0 |
| Garrison | 3 | 0 |

Maintenance: 8.5 RU/tick

**Polity C — outer system (Belt / gas giant operations)**

| Hull | Count | Maint |
|---|---|---|
| Cruiser | 1 | 1.0 |
| Escort | 3 | 1.5 |
| Transport | 2 | 1.0 |
| Colony transport | 1 | 0.5 |
| Scout | 2 | 0 |
| SDB | 2 | 1.0 |
| Army | 1 | 0.5 |
| Garrison | 2 | 0 |

Maintenance: 5.5 RU/tick

**Combined Sol system maintenance: 27.5 RU/tick**

Sol system income at tick 0 (Earth at Controlled/dev-4, Mars at Colony/dev-2,
plus outer-system bodies): estimated 28–32 RU/tick. The three polities
together spend nearly every credit on mutual deterrence — exactly the
condition that makes early inter-human war a likely simulation event.

---

## Notes for initialisation script

- Species OBs should be created in the DB at tick 0 as fleet records with
  assigned hull counts, homeworld SDB assignments, and ground force records.
- Species with `faction_tendency` > 0.85 start as multiple polities. At
  launch: Humans (0.90) and Nhaveth (0.90). Three polities each is the
  working default; the initialisation script controls the exact count.
- All starting admirals should be generated at tick 0 using the species-biased
  tactical factor procedure.
- Skharri (`faction_tendency` 0.65) starts as a single polity. Inter-pride
  rivalry manifests as a stability pressure modifier rather than formal splits
  until war stress accumulates sufficiently.
- Kreeth (`faction_tendency` 0.02) will almost never split; internal fracture
  is physiologically implausible.
