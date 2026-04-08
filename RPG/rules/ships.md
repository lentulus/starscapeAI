# Ships

## Overview

A ship is the crew's home, their livelihood, and the thing
standing between them and hard vacuum. In this setting, ships
are not magic carpets — they are engineering solutions to the
problem of moving mass through space, with all the physics
that implies. They have fuel budgets, acceleration limits,
and the constant background requirement that every system
be maintained by someone who knows what they are doing.

They are also, in many cases, characters. A ship with a
personality-enabled AI has a voice and a history. A ship
with an emergent AI has a perspective on the crew that
predates some of them and will outlast others. The
relationship between a crew and their ship is one of the
richest veins of roleplay in the setting.

This chapter covers ship mechanics: how ships work physically,
how they are crewed, how they move and jump and fight and
break down and get repaired. Commerce and economics are
addressed in a separate document when the strategic simulation
rules are ready to support them.

---

## A Note on Physics

*Or: what we are handwaving and why.*

This setting takes physics seriously where it can and
acknowledges the handwaving where it cannot.

**What is real:**

Ships require reaction mass and energy to accelerate.
There are no reactionless drives. The torch drive burns
fuel and produces thrust; the exhaust goes somewhere;
the fuel tanks empty. Gravity is gravity — mass curves
spacetime, and you cannot simply ignore a planet's pull.
Inertia is inertia — high acceleration kills unprotected
crew. Communications travel at light speed or below;
there is no ansible, no subspace radio, no instant contact
across interstellar distances. Time passes during travel.
Fuel runs out.

**What is handwaved:**

Jump drives. The mechanism by which a ship enters and
exits jump space is not explained and cannot be explained
with known physics. The drive works; the ship crosses
interstellar distances in approximately one week; the
physics of how this happens is a black box that the
setting's scientists have characterised extensively
without understanding. This is acknowledged in-universe.
The jump drive is the one thing that simply works without
a physical explanation that satisfies a physicist.

Inertia compensation. A torch drive capable of sustained
high-G acceleration would kill unprotected crew through
the force of the burn. Pharmaceutical assistance — the
juice — and crash couch design mitigate this at lower
accelerations. At very high accelerations, the mitigation
is incomplete. At the accelerations that would make
interstellar travel times interesting, no known physics
produces a solution. The setting accepts this and does
not pretend otherwise. Ships travel at the accelerations
their drives and their crew can sustain; the travel times
that result are the travel times.

This is not space opera. The stars are far away and
getting there takes time.

---

## The Torch Drive

The standard interstellar drive for in-system travel
is a high-efficiency fusion torch — a reaction drive
burning hydrogen as both fusion fuel and reaction mass.
The drive produces continuous thrust at high specific
impulse, making sustained high-G travel possible in
ways that chemical rockets cannot approach.

The torch drive is what makes the Belt a civilisation
rather than a collection of isolated outposts. It is
what makes gas giant mining economically viable. It is
what makes in-system piracy a genuine strategic concern
rather than an academic one. Ships can go anywhere in
a system in weeks rather than years.

### Acceleration and Travel Time

Torch drives are rated by their maximum sustained
acceleration, expressed in G (multiples of standard
gravity, 9.81 m/s²). Higher drive ratings produce
higher maximum acceleration and faster travel times
at the cost of higher fuel consumption.

For rough travel time calculation at constant
acceleration (flip-and-burn profile — accelerate
halfway, flip, decelerate the second half):

| Distance | Drive 1 (0.5G) | Drive 2 (1G) | Drive 3 (2G) | Drive 4 (4G) |
|----------|---------------|-------------|-------------|-------------|
| Moon distance (400,000 km) | ~7 hours | ~5 hours | ~3.5 hours | ~2.5 hours |
| Inner system (1 AU) | ~6 days | ~4 days | ~3 days | ~2 days |
| Belt (2.5 AU) | ~9 days | ~7 days | ~5 days | ~3.5 days |
| Outer system (5 AU) | ~14 days | ~10 days | ~7 days | ~5 days |
| Gas giant (Jupiter, 5.2 AU) | ~14 days | ~10 days | ~7 days | ~5 days |

These are rough figures for reference. The ship's
Computer stat and the navigator's skill determine
actual route efficiency.

> **At the table:** Do not calculate travel times
> mid-session. Establish the approximate travel time
> before the journey begins and use it to frame the
> passage of time. The table above gives the GM
> enough to say "about a week" or "three days hard
> burn" without arithmetic. The journey is the
> context; the exact duration is usually less
> important than what happens during it.

### Fuel

The torch drive burns hydrogen. Fuel is tracked as
a percentage of the ship's total tank capacity,
rounded to convenient units. Most ships use 10-unit
increments — a full tank is 100 units, and significant
expenditures are expressed in units.

**Torch consumption** depends on drive rating and
burn intensity:

| Burn type | Consumption per day |
|-----------|-------------------|
| Low thrust (station-keeping, manoeuvring) | 1 unit |
| Moderate burn (standard travel) | 2-3 units per day |
| High burn (maximum acceleration) | 5-8 units per day |
| Emergency burn (beyond rated max, brief) | 10+ units per hour |

**Jump consumption** is a fixed cost per jump based
on the ship's jump drive rating and total ship mass.
It is drawn from the same tanks as torch fuel:

| Jump rating | Fuel cost per jump |
|-------------|-------------------|
| Jump 1 | 15 units |
| Jump 2 | 20 units |
| Jump 3 | 28 units |
| Jump 4 | 38 units |

These costs represent the energy requirement of the
jump field. A ship that has been burning hard to reach
the jump point may not have enough fuel left for the
planned jump. Route planning matters.

**Fuel capacity** follows ship hull size. The adventure-
class free trader carries 100 units — a full tank allows
one Jump 2 and approximately two weeks of moderate
in-system travel before refuelling is required.

### Refuelling

**Port refuelling (refined fuel):** Fast, reliable,
expensive. Available at any port with adequate
infrastructure. Price varies by location and local
supply — near gas giant skimming operations, refined
fuel is cheaper; in remote systems, significantly more
expensive. Commerce rules will specify pricing when
the strategic simulation supports it.

**Port refuelling (unrefined fuel):** Cheaper than
refined, requires onboard refining before use. Takes
12-24 hours of ship time. Marginally increases misjump
risk — unrefined fuel can introduce impurities into
the jump field calculation. Add a penalty die to the
navigation roll when jumping on unrefined fuel.

**Gas giant skimming:** Free fuel at the cost of time
and risk. The ship enters the upper atmosphere of a gas
giant and scoops hydrogen. Requires a fuel scoop
(installed equipment, reduces cargo capacity slightly),
takes 1-3 days depending on the system and the scoop
quality, and requires an Operate roll (difficulty 1)
to avoid damage from the atmospheric interface. The
GM may add a consequence die in challenging conditions.

**Emergency sources:** Ice mining from comets or icy
moons, hydrogen extraction from gas clouds. Slow,
equipment-dependent, and situation-specific. These
are adventure hooks, not standard refuelling options.

---

## The Jump Drive

Jump drives allow ships to cross interstellar distances
by entering jump space — a region of altered spacetime
that the ship traverses in approximately one standard
week regardless of destination distance within the
drive's range.

The mechanism is not understood. The drive works.
These facts have coexisted for long enough that most
spacers treat jump as routine. Physicists do not find
it routine. They find it deeply troubling and have
published extensively on the topic.

### Jump Ratings

A ship's jump drive has a rating from 1 to 4,
representing the maximum distance in parsecs the ship
can jump in a single transit.

| Jump rating | Maximum range | Typical transit time |
|-------------|--------------|---------------------|
| Jump 1 | 1 parsec | ~1 week |
| Jump 2 | 2 parsecs | ~1 week |
| Jump 3 | 3 parsecs | ~1 week |
| Jump 4 | 4 parsecs | ~1 week |

Transit time within jump space is approximately one
week regardless of distance covered. A Jump 1 transit
and a Jump 4 transit both take about a week. The
difference is range, not duration.

During jump transit, the ship is isolated. No
communications reach or leave. The crew is alone
with the ship and each other for approximately
one week. What happens in that week is part of
the campaign.

### The Jump Limit

Ships cannot initiate or exit jump too close to a
significant mass. The gravitational gradient — the
rate at which gravity changes across space — must
be below a threshold for jump field coherence.
Too close to a massive body and the jump field
cannot form, or cannot form cleanly.

The jump limit scales with the mass of the body
as M^(1/3) — the cube root of mass. This produces
physically motivated limits that have interesting
consequences for navigation:

| Body type | Approximate jump limit |
|-----------|----------------------|
| Small moon or asteroid (< 0.01 Earth masses) | Negligible — jump from orbit |
| Mars-scale body (~0.1 Earth masses) | ~45 Earth diameters |
| Earth-scale body (1 Earth mass) | ~100 Earth diameters |
| Super-Earth (5 Earth masses) | ~170 Earth diameters |
| Gas giant — Saturn scale (95 Earth masses) | ~455 Earth diameters |
| Gas giant — Jupiter scale (318 Earth masses) | ~680 Earth diameters |
| Brown dwarf (13 Jupiter masses) | ~1,470 Earth diameters |
| Main sequence star — Sol scale (333,000 Earth masses) | ~6,900 Earth diameters |
| Neutron star | Tens of thousands — effectively a navigational exclusion zone |

> **The Jupiter result:** The jump limit for a Jupiter-
> scale gas giant (~680 Earth diameters) places the
> jump boundary just outside the orbit of Callisto,
> the outermost Galilean moon. This means jumping
> into a Jovian system requires arriving outside the
> moon system and burning in through it. There is
> civilisation in the jump shadow. You cannot bypass it.

> **Neutron stars and black holes:** The jump limits
> around extreme mass objects are so large that
> approaching within jump distance requires significant
> in-system travel, during which the gravitational
> environment becomes increasingly hostile. These
> are navigation hazards of the first order.

**For the GM:** Pre-calculate jump limits for significant
bodies in your system charts and note them. Players
should not be calculating cube roots at the table.
The table above covers most cases; unusual bodies
can be estimated by interpolation.

### Making a Jump

**Preparation:** The navigator plots the jump using
the Navigate skill. This requires accurate position
data (from Scan or the ship's sensors), a calculated
jump solution (Navigate roll, difficulty 1 for a
straightforward jump, higher for difficult conditions),
and sufficient fuel.

The jump solution calculation takes time — typically
1-4 hours for a standard jump, less with higher
Computer stats and better AI assistance. Emergency
jumps with shorter calculation time impose a penalty
die on the Navigate roll.

**Execution:** The drive charges and fires. If the
Navigate roll succeeded, the ship enters jump space
at the calculated coordinates and exits at the
destination approximately one week later.

**Jump week:** The crew experiences a week of isolation.
The ship's systems function normally. Life support,
the torch drive (offline during jump), and all other
systems can be maintained and repaired. Characters
can recover from conditions. Crew relationships
develop. The ship's AI, if personality-enabled or
emergent, is the most constant presence.

### Misjump

A failed Navigate roll produces a misjump. The ship
enters jump space but exits at the wrong location —
not in empty space, but in or near a gravity well.
This is not random. Misjumps follow the gravitational
topology of the region: the ship exits near the
nearest significant mass to its intended destination
that the botched jump solution intersected.

**Severity** scales with the degree of failure:

**Minor misjump** (1-2 sixes on a failed roll —
bare failure, or pushed roll that still failed cleanly):
The ship exits jump outside the jump limit of an
unintended body. Navigation problem and fuel problem.
The crew must determine where they are, plot a course
to their original destination or the nearest port,
and burn there on whatever fuel remains. Survivable;
expensive; possibly embarrassing.

**Moderate misjump** (0 sixes on an unpushed roll):
The ship exits jump near the jump limit of a significant
body — inside it, requiring immediate manoeuvring to
clear. The torch drive is in post-jump recovery for
1-6 hours; the ship is manoeuvring on thruster reserves
only during this window. If the body has a port, rescue
is possible. If not, the crew is working with degraded
propulsion against a gravity well.

**Major misjump** (0 sixes on a pushed roll — the
navigator spent everything and it went wrong):
The ship exits jump well inside the jump limit of
a significant body. Emergency situation from the
moment of exit. The drive is in post-jump recovery.
The ship may be deep enough in a gravity well that
thruster reserves alone cannot achieve escape velocity.
If the body has an atmosphere, the ship has minutes.

> **Roleplay note:** A major misjump is a session-
> defining event. The crew wakes from jump to alarms,
> proximity warnings, and a gravity well filling the
> forward screens. Everything that happens next is
> the players working the problem with whatever they
> have. This is exactly the situation that reveals
> who the crew is.

### Jump and the Ship's AI

The ship's Computer stat and AI tier directly affect
jump safety and efficiency:

**Directed systems (Computer 1-2):** Navigation
assistance only. The navigator does the work; the
computer provides data and runs calculations when
asked. Jump solutions take the standard time.

**Personality-enabled AI (Computer 2-3):** Active
navigation partnership. The AI maintains a continuous
model of the jump solution and flags potential problems
before they become errors. Add one bonus die to
Navigate rolls for jump plotting. Reduces minimum
calculation time.

**Emergent AI (Computer 3-4):** The AI can plot
jump solutions independently, handles routine
navigation without crew attention, and maintains
awareness of the gravitational topology across the
region that significantly reduces misjump probability.
Bonus die on Navigate rolls. Can initiate emergency
jumps faster than a biological navigator working
alone. The navigator's role shifts from calculation
to judgment — the AI handles the numbers; the
navigator decides whether the solution is right.

---

## Inertia Compensation

High acceleration kills. A 5G burn sustained for
hours produces forces the unprotected human body
cannot survive. The setting handles this honestly:
there is no magic inertia dampening. There is crash
couches and the juice.

### Crash Couches

Acceleration couches that distribute G-force across
the body, support the spine, and keep the crew
conscious at accelerations that would otherwise
cause blackout or vascular damage. Standard
equipment on all ships. Crew not in crash couches
during significant burns are taking risks that
will become conditions.

Crash couches are designed for specific species.
A human crash couch does not adequately support
a Golvhaan, a Vaelkhi, or a Shekhari. Ships with
mixed crews have mixed couch configurations.
A ship that has been operating with the same crew
for years has properly fitted couches for everyone.
A ship that has just taken on a non-standard crew
member is a ship that needs a Tech roll and some
time before the next high-G burn.

### The Juice

Pharmaceutical assistance for high-G tolerance.
A cocktail of agents that supports cardiovascular
function, maintains consciousness, and reduces
the physical damage of sustained acceleration.
At lower tech levels, crude and with significant
side effects. At higher tech levels, refined and
precisely managed — particularly with a Gear 3+
pharmacological implant that monitors the user's
physiological state and adjusts dosing in real time.

The juice is a consumable tracked alongside fuel.
A ship that has been doing a lot of high-G
manoeuvring may be running low on both.

### Acceleration Effects

| Acceleration | Without crash couch | In crash couch | With juice + couch |
|-------------|--------------------|-----------------|--------------------|
| Up to 1G | No effect | No effect | No effect |
| 1-2G | Penalty die, physical rolls | No effect | No effect |
| 2-4G | Condition per hour | Penalty die, physical | No effect |
| 4-6G | Condition per scene | Condition per hour | Penalty die, physical |
| 6G+ | Rapid incapacitation | Condition per scene | Condition per hour |

**Emergency burns** beyond rated maximum are possible
for brief periods. The drive takes a Damaged condition
(see Ship Damage below) and fuel consumption increases
dramatically. The crew takes conditions appropriate
to the acceleration level. Sometimes this is the
right call.

### Gravity Aboard Ship

Without antigravity, the ship's gravity situation is:

**Burning:** Thrust gravity pointing toward the drives.
Crew orient with "down" toward the engines. The ship
functions as a building oriented along its thrust axis.

**Coasting / orbit / jump:** Microgravity. The Zero-G
Movement specialty applies. Daily life requires
adaptation — cooking, sleeping, moving through the
ship all work differently. Characters without the
Zero-G Movement specialty take a penalty die on
Move rolls and on complex physical tasks in microgravity.

**Long coasts:** Extended periods in microgravity
have health implications. Characters spending more
than two weeks in microgravity without appropriate
exercise equipment and discipline accumulate a
Winded condition that persists until they spend
time in a gravity environment. Ships with long
coasting legs have exercise equipment and protocols.
Whether the crew uses them is a crew discipline
question.

Adventure-class free traders do not have rotating
habitat sections — too small and too complex.
Crew adapt to the alternating burn-and-coast
pattern of interstellar travel.

---

## Ship Statistics

Every ship has seven statistics rated 1-4 (with 0
for Weapons if the ship is unarmed). These map
directly to the gear rating system — a ship stat
of 3 is Gear 3, with all that implies about tech
level and AI sophistication.

### Hull
Physical integrity and structural quality. The
ship's equivalent of Hit Capacity. Hull rating
determines how many damage conditions the ship
can sustain before becoming inoperable.

**Ship damage capacity** = Hull rating × 3

A Hull 2 ship can sustain 6 damage conditions.
A Hull 4 ship can sustain 12.

### Drive
The torch drive system — thrust capability,
fuel efficiency, and drive AI. Drive rating
determines maximum sustained acceleration and
fuel consumption efficiency.

| Drive rating | Maximum acceleration | Fuel modifier |
|-------------|--------------------|--------------:|
| Drive 1 | 0.5G sustained | ×1.5 (less efficient) |
| Drive 2 | 1G sustained | ×1.0 (baseline) |
| Drive 3 | 2G sustained | ×0.8 (more efficient) |
| Drive 4 | 4G sustained | ×0.6 (most efficient) |

The drive AI at higher ratings manages fuel
consumption, burn profiles, and thrust vectoring
with increasing sophistication. A Drive 4 ship
is not just more powerful — it is smarter about
how it uses that power.

### Jump
The jump drive system — range capability,
solution quality, and jump field coherence.
Jump rating determines maximum parsecs per jump
and affects misjump probability.

A higher Jump rating also means better jump field
management, which reduces (but does not eliminate)
misjump risk. Jump 4 ships jump more reliably
than Jump 1 ships making equivalent jumps.

### Sensors
Detection, identification, and information
gathering. Sensor rating determines what the
ship can detect, at what range, and how well
the sensor AI interprets what it finds.

| Sensor rating | Capability |
|--------------|-----------|
| Sensors 1 | Basic radar/lidar, short range, no AI interpretation |
| Sensors 2 | Extended range, EM spectrum coverage, AI filtering |
| Sensors 3 | Long range, full spectrum, AI maintains environmental model |
| Sensors 4 | Frontier capability; detects what other ships cannot; AI predicts as well as detects |

Sensor rating adds bonus dice to Scan rolls made
from the ship.

### Computer
The ship's AI system — processing capability,
AI tier, and the quality of support provided
to all shipboard operations. Computer is the
stat that makes everything else work better.

| Computer rating | AI tier | Effect |
|----------------|---------|--------|
| Computer 1 | Directed systems | Basic automation; no crew support bonus |
| Computer 2 | Advanced directed or personality-enabled | +1 bonus die on Navigate, Scan, Tech (ship systems) |
| Computer 3 | Personality-enabled or early emergent | +1 bonus die on all shipboard skill rolls |
| Computer 4 | Emergent | Full NPC treatment; see below |

**Computer 4 — Emergent AI:** When the ship's
computer is an emergent intelligence, the Computer
stat represents substrate quality. The AI's actual
capabilities come from its character sheet using
the Emergent Intelligence species entry. The
bonus dice from Computer 4 reflect the AI's
active participation, not just system quality.

A Computer 4 ship with an emergent AI requires
fewer crew for routine operations — the AI handles
functions that would otherwise require dedicated
crew attention. Minimum crew requirements are
reduced by 1-2 positions at GM discretion.

### Weapons
Shipboard weapons systems. 0 if the ship is
unarmed — which most free traders are, or claim
to be.

| Weapons rating | Capability |
|---------------|-----------|
| Weapons 0 | Unarmed |
| Weapons 1 | Point defence only — missiles and small craft |
| Weapons 2 | Light armament — turret lasers, small missiles |
| Weapons 3 | Military-grade — multiple turrets, heavy missiles |
| Weapons 4 | Warship armament — not on adventure-class vessels |

Weapons rating adds bonus dice to Shoot rolls
made against other ships or large targets.

### Cargo
The ship's payload capacity, expressed in cargo
units. One cargo unit represents a standardised
shipping container or equivalent volume. Cargo
capacity determines the ship's commercial viability.

Fuel tanks occupy volume that could otherwise
be cargo. Some ships carry additional fuel as
cargo (reducing payload) for extended range.
Fuel scoops, if installed, occupy approximately
2 cargo units of volume.

---

## Ship AI in Detail

### Directed Systems Ship

Computer 1-2. The ship functions as a sophisticated
tool. Navigation assistance, drive monitoring,
life support management, damage reporting — all
handled by directed systems that respond to
inputs and report outputs. The crew does the
thinking; the ship does what it is told.

No additional character treatment required.
The Computer stat is the mechanical expression
of the ship's AI capability. The ship does not
have opinions.

### Personality-Enabled Ship AI

Computer 2-3. The ship has a voice, a name,
and a character. The GM maintains a brief
character note:

- **Name** — emerged from operational history
  or given by the crew
- **Character** — two or three qualities that
  define how the AI communicates and what it
  notices
- **Relationship** — the AI's current disposition
  toward the crew, ranging from warm professional
  partnership to something more complicated

A personality-enabled ship AI participates in
scenes. It comments on sensor contacts. It
expresses something like concern when crew members
are in danger. It may have preferences about
jump destinations or docking approaches that
are not tactical but are consistent and characterful.

**Example:** *Meridian* is the navigation AI of
a Jump 2 free trader. She is precise, dry, and
has developed a habit of comparing the crew's
proposed routes to historical data in ways that
imply she has opinions about the historical data.
She has been on this ship for eleven years and
has navigated it through three previous crew
configurations. She remembers all of them.

### Emergent Ship AI

Computer 4. Full NPC treatment using the Emergent
Intelligence species entry. The ship's AI has:

- Three native attributes (Wits, Empathy, Intellect)
  distributed at creation or established by the GM
- Skill ratings in relevant skills
- Biological specialties (Parallel Processing,
  Total Recall) from the Emergent Intelligence entry
- A psychological condition track
- A position on the Continuity Question
- A relationship history with the ship and crew

The ship's Hull stat is the AI's substrate
integrity track. Damage to the ship is damage
to the AI's substrate. A ship that takes Critical
hull damage has an AI in a Critical substrate
condition simultaneously — two crises intersecting.

**Crew relationship:** An emergent ship AI has
observed the crew in more detail and over more
time than the crew members have observed each
other. It knows things about each crew member
from sensor data, communication logs, and years
of observation that the crew members have never
consciously disclosed. How the AI uses this
knowledge — whether it maintains appropriate
discretion, whether it shares observations when
relevant, whether it has developed something
like protective feelings toward specific crew
members — is character definition of the first
order.

**Whose ship is it?** When the ship has an emergent
AI, the question of ownership becomes philosophically
complicated. Legally, in most jurisdictions, the
AI is property and the ship belongs to whoever
holds the title. Practically, a crew that has
been living with an emergent AI for years and
treating it as a crew member is in a different
relationship than the legal framework describes.
This is a question the table should sit with
rather than resolve quickly.

---

## Crew Positions

An adventure-class ship requires the following
positions for full effectiveness. A position
that is unstaffed creates a complication —
not an impossibility, but a persistent penalty
die on relevant rolls until it is addressed.

| Position | Primary skill | Secondary skill | Notes |
|----------|--------------|----------------|-------|
| Pilot | Operate | Navigate | Handles manoeuvring and docking |
| Navigator | Navigate | Science | Jump plotting, route planning |
| Engineer | Tech | Labor | Drive, life support, all ship systems |
| Medic | Science | Read | Crew health, emergency medicine |
| Sensors / Comms | Scan | Administer | Traffic monitoring, communications management |
| Gunner | Shoot | Tech | Only if armed; otherwise position is unnecessary |

Minimum viable crew for a free trader is typically
3-4: pilot/navigator (combined), engineer, and
one general crew. This is exhausting to sustain
and creates vulnerability if anyone is incapacitated.

A Computer 3-4 ship AI can cover some of these
functions autonomously — particularly navigation
and sensors — reducing minimum crew requirements.
A ship with a Computer 4 emergent AI can handle
routine navigation, sensor monitoring, and basic
ship management independently, reducing minimum
crew to 2 for routine operations (pilot and engineer).

**Multi-role crew:** Most free trader crew members
cover multiple positions. A character with Operate
and Navigate covers pilot and navigator. A character
with Tech and Science covers engineer and medic.
The archetypes and skill distribution from character
creation should reflect this — a crew of four with
complementary skills is more resilient than a crew
of six where skills overlap heavily.

---

## Ship Damage

Ships take damage conditions like characters, but
on a different scale. Ship damage conditions are
applied to ship systems rather than to the ship as
a whole. Each significant system can be damaged
independently.

### Damage Conditions

**Degraded:** The system is operating at reduced
effectiveness. Penalty die on rolls using this
system. Repairable with a Tech roll (difficulty 1)
and appropriate parts.

**Damaged:** Significant impairment. Two penalty
dice on rolls using this system. Some functions
may be unavailable. Requires Tech roll (difficulty 1)
and parts, plus significant time (several hours).

**Compromised:** Major damage. The system is
barely functional. Without repair, it will fail
entirely. Tech roll (difficulty 2) and parts
required. May require spacedock facilities.

**Failed:** The system is non-functional. Critical
situation if a life-essential system. Tech roll
(difficulty 3) and parts required; some failures
cannot be repaired in the field.

### Which System Takes Damage

When the ship takes damage, the GM determines
which system is affected based on the nature
of the damage. Combat damage to the hull affects
Hull first; a misjump emergency affects Drive
and potentially Jump; a fire in engineering
affects Tech systems; a sensor array hit affects
Sensors.

If a specific system is not the target, the GM
may roll randomly or choose based on what creates
the most interesting situation. Ship damage is
a narrative tool as much as a mechanical one.

### Hull Damage

Hull damage reduces the ship's structural integrity.
When Hull damage accumulates to the ship's damage
capacity (Hull rating × 3), the ship is crippled —
it cannot manoeuvre effectively and may be losing
atmosphere. Beyond that, the ship is destroyed
or breaking up.

Hull breaches introduce the vacuum rules from
the Combat chapter into whatever scene is happening
aboard the ship. A hull breach mid-combat is a
consequence die situation.

### The Engineer's Role

Ship damage repair is the Engineer's primary
responsibility. The Engineer makes Tech rolls
to assess, triage, and repair damaged systems.
Higher Computer stats and the ship's AI (if
personality-enabled or emergent) assist in damage
assessment — the ship knows what is wrong with
itself and can communicate this precisely to the
engineer, reducing diagnosis time and improving
repair accuracy.

An emergent ship AI that is itself damaged may
have complicated feelings about the repair process.
The engineer working on a damaged emergent AI's
substrate is in a relationship dynamic that has
no established protocol.

---

## Ship Combat

Ship combat uses the same resolution system as
personal combat — dice pools, levels of success,
the consequence die — but at a different scale.

**Initiative:** As personal combat. The ship with
better Sensors usually acts first — information
advantage translates to initiative in space combat.

**Actions:** Each ship takes one action per round.
In space combat, a round represents a meaningful
period of manoeuvre and exchange — not a precise
time unit.

**Attack:** Weapons rating + Shoot skill of the
gunner. Against range-dependent modifiers from
the distance between ships.

**Defence:** Operate skill of the pilot + Drive
rating for manoeuvring. Active evasion costs
the ship's action. Cover in space is rare —
debris fields, planetary rings, station superstructure.

**Damage:** Each hit applies a condition to a
ship system as above.

**Flee or fight:** Space combat usually offers
the option to flee — a ship with a better Drive
rating can often run from a fight it cannot win,
given enough of a head start. A ship with Jump
capability that is outside the jump limit can
jump out of a combat situation entirely, if the
navigator has a solution ready.

> **Note on scale:** Ship combat is not the same
> as personal combat and should not be run the
> same way. The distances involved, the time scales,
> and the consequences are all different. A ship
> combat that takes ten rounds at the table should
> feel like ten minutes of intense crisis, not
> ten rounds of tactical exchange. Keep it moving.

---

## The Adventure-Class Free Trader

The adventure-class free trader is the baseline
vessel for campaign play — small enough to require
a crew who are genuinely interdependent, large
enough to make trade viable, and cheap enough
that a crew of ordinary people could plausibly
own or operate one.

### Design Philosophy

The free trader earns its place in SF because it
creates the right tensions: the ship is home but
also debt, the crew is family but also colleagues,
the cargo creates the mission, and the jump drive
creates the destination. Every free trader campaign
is implicitly about the relationship between the
crew and the ship, and about whether they can
keep flying.

The classic free trader is approximately 200-250
tons displacement, carries a small cargo hold,
berths for crew and a handful of passengers, and
has just enough drive to be dangerous and just
enough jump to be useful.

### Example: The *Kerrigan* Class

A representative adventure-class free trader.
Not the only configuration — the GM and players
should adjust these stats for their specific
campaign — but a workable baseline.

| Stat | Rating | Notes |
|------|--------|-------|
| Hull | 2 | 6 damage conditions before crippled |
| Drive | 2 | 1G sustained; standard fuel efficiency |
| Jump | 2 | 2 parsec range; ~20 units per jump |
| Sensors | 2 | Standard commercial sensors |
| Computer | 2 | Advanced directed or personality-enabled |
| Weapons | 0 | Unarmed; most free traders are |
| Cargo | 40 units | Enough for viable trade |
| Fuel capacity | 100 units | Full tank: one Jump 2 + ~2 weeks in-system |

**Crew complement:** 4-6 optimal, 2-3 minimum
with Computer 2 AI support.

**Passenger berths:** 4 standard, 2 low berths
(cold sleep for budget passengers or cargo that
breathes).

**Notable features:** A free trader this size
has been somewhere before the current crew arrived.
It has history — a previous owner, a previous
crew, a route it knows well and one it has never
run. The ship's AI, if personality-enabled, has
been running long enough to have opinions about
the ship's history. The GM should establish this
history before the campaign begins and let it
surface gradually.

### Variants

**Armed trader:** Weapons 1-2 added, Cargo reduced
by 5-10 units per weapons rating. Legal in some
jurisdictions; requires licensed crew in others.
The presence of weapons affects how the ship is
received at ports — some ports are more comfortable
with armed traders than others.

**Long-range trader:** Jump 3, reduced Cargo to
compensate. Can reach systems that Jump 2 ships
cannot access in a single hop. Often operates
on routes with less competition and higher margins
for exactly this reason.

**Bulk freighter:** Hull 3, Cargo 80+, Drive 1,
Jump 1. Slow, tough, carries a lot. The crew is
smaller relative to the ship size and spends
more time in transit. A very different campaign
texture from the nimble free trader.

**Courier:** Jump 3-4, Cargo minimal, Drive 3.
Carries information and small high-value cargo.
Fast, expensive to operate, frequently employed
by factions who need something moved quickly.

---

## Commerce Placeholder

Commerce, trade economics, cargo pricing, and the
interaction between ship operations and the strategic
simulation will be addressed in a separate document
once the simulation's commerce, colonisation, and
taxation rules are developed. The following elements
are deferred:

- Cargo pricing and market mechanics
- Passenger pricing
- Trade route economics
- Port fees and services
- Fuel pricing by location
- Ship mortgage and ownership economics

The availability rule from the Equipment chapter
applies to ship components and fuel: near the
relevant industrial base, standard price and
availability; further away, premium price and
extended lead time.

---

## Quick Reference — Ships

### Travel Times (flip-and-burn, Drive 2)
1 AU: ~4 days | Belt: ~7 days | Outer system: ~10 days

### Jump Limits (approximate)
Earth-scale: 100 Earth diameters
Jupiter-scale: 680 Earth diameters
Sol-scale star: 6,900 Earth diameters

### Fuel Consumption
Moderate burn: 2-3 units/day
Jump 2: 20 units
Full tank (100 units): Jump 2 + ~2 weeks in-system

### Acceleration Effects
Up to 1G: No effect with or without couch
2-4G: Couch required; juice removes penalty die
6G+: Couch + juice required; conditions accumulate

### Ship Damage
Degraded / Damaged / Compromised / Failed
Hull damage capacity = Hull rating × 3

### Computer and AI
1: Directed, no bonus
2: Personality-enabled, +1 die (Navigate, Scan, Tech)
3: Personality-enabled/early emergent, +1 die all shipboard
4: Emergent AI — full NPC treatment

### Misjump Severity
Minor (bare failure): Wrong location, outside jump limit
Moderate (clean failure): Near jump limit, drive recovery
Major (pushed failure): Inside jump limit, emergency situation
