# GM Reference

## How to Use This Document

Everything is in the vault and it is all linked. This document
is not a content repository — it is a navigation layer. It tells
you which note to open, what to look for, and how to translate
what you find into something that happens at the table.

When something comes up mid-session, the procedure is:
1. Is it in this document's quick reference sections? Use it directly.
2. Is it a link? Follow it.
3. Is it a rules question? Open the relevant rules document.
4. Is it a simulation question? Open the relevant weekly report.

Keep this document open during play. Everything else is one
link away.

---

## Before the Session

### Preparation Checklist (2-3 weeks ahead)

Run this checklist when preparing a session block. The simulation's
1-week granularity means each session roughly corresponds to one
simulation tick, though the table should never feel this mechanical.

**Check the simulation:**
- [ ] Open the current week's report in `simulation/weekly-reports/`
- [ ] Note any events in systems the crew is currently in or
      travelling toward
- [ ] Note any events in systems connected to the crew's factions,
      connections, or current mission
- [ ] Identify events that the crew's home system would have
      received news of (apply propagation delay — see below)
- [ ] Flag any events that will arrive as news during the session

**Prepare the news sheet:**
- [ ] Draft the local news sheet for the crew's current location
- [ ] Apply propagation delay to all events — the news sheet
      reflects what was known at time of printing, not what is
      true now
- [ ] Include at least one item that is directly relevant to the
      crew's situation, presented as background rather than a hook
- [ ] Include at least one item that is wrong, outdated, or
      deliberately misleading — news is never perfect
- [ ] Export to PDF or print for the table

**Check NPC status:**
- [ ] Open `npcs/` and review any named NPCs the crew is likely
      to encounter this session
- [ ] Check whether any simulation events have affected these NPCs'
      situations or motivations
- [ ] Update NPC notes if needed

**Check faction status:**
- [ ] Open `factions/` for any factions active in this session
- [ ] Note any changes from the simulation that affect their
      behaviour or resources
- [ ] Consider whether any faction has initiated contact with
      the crew based on simulation events

**Prepare the session:**
- [ ] Write 2-3 sentences describing the situation the crew
      wakes up into at the start of the session
- [ ] Identify one thing that will definitely happen regardless
      of player choices (the simulation's consequence arriving)
- [ ] Identify 2-3 things that might happen depending on choices
- [ ] Have at least two named NPC stat blocks ready
- [ ] Do not over-prepare. The simulation is doing the work.

### The Session Opening

Every session begins with a brief orientation:

**Where are you?** Name the location. One sentence of physical
description — what does it look, sound, or smell like?

**What time is it?** Relative to the last session. How long
since the last significant event?

**What do you know?** Any information the crew has received
since last session — news, communications, rumour from contacts.
Apply propagation delay to all of it.

**What needs attention?** The one thing that is already in
motion at session start. Not a hook — a situation. Something
that requires response rather than decision.

---

## At the Table

### When You Need a Species Texture Note

Open `rpg/rules/species.md` for the full entry.
For quick mid-session reference:

| Species | One line | Most important roleplay note |
|---------|----------|------------------------------|
| Human | Stubborn, adaptable, convinced the universe is theirs | They assume other species think like them. They are wrong. |
| Shekhari | Always know the price of everything, including you | The quiet after sharp commentary means they are calculating an exit |
| Golvhaan | Patient, enormous, genuinely interested | When the questions stop, something is wrong |
| Vashori | Warm, volatile, they will remember | Check the temperature. Cold Vashori are shorter-tempered for physical reasons |
| Vaelkhi | Death in the sky is glorious — skill, not recklessness | The choth decision is permanent. Leaving was permanent. They know this every day |
| Skharri | The name is earned. Everything is earned | The scream-and-leap Wits roll: difficulty 2. Watch for the triggers |
| Nakhavi | Every moment is vivid. There are not many of them | Translation adds delay and drops nuance. They compensate by being more explicit |
| Kreeth | There is no individual. There is only the will | Run as a coordinated system, not individual opponents |
| Kraathi | The G'naak must be cleansed. This is not politics | The menu is a diplomatic document. Carnivore crew = G'naak |
| Nhaveth | The host is a convenience. You are being assessed | See handout for tells. Difficulty 3 without it, 2 with |
| Vardhek | Everything is on the centuries-long ledger | Every Vardhek interaction: ask what position the Long View assigns to this |
| Emergent AI | Everyone I know will die before me | What is their position on the Continuity Question? Establish before they appear |

### When You Need a Rules Clarification

**Most common mid-session lookups:**

**Building the pool:** White (Attribute) + Blue (Skill) +
Green (Gear). Remove Red (penalty) dice before rolling,
starting with Gear, then Skill, then Attribute.

**Results:** 0 sixes = failure. 1 = bare success. 2 = clean.
3 = strong. 4+ = outstanding.

**Pushing:** Lock ones. Reroll everything else. Narrative
consequence applies regardless. Pushed failure = something
goes meaningfully wrong.

**Opposed rolls:** Most sixes wins. Tie goes to acting character.

**The Opacity Rule:** Without Exposure: [Species], Read rolls
for emotional content automatically fail. Manipulate takes
a penalty die.

**Conditions:** Each condition = one penalty die on relevant
rolls. 4 conditions on either track = incapacitated.

**Consequence die (black D4):**
1 = minimal cost / 2 = complication / 3 = collateral / 4 = full cost

**When NOT to roll:** Certain outcome. Outcome doesn't matter.
No meaningful chance. Roleplay is the right tool.

### When You Need a Condition

**Physical track (Hit Capacity = Strength + Endure):**

| Condition | Effect | Recovery |
|-----------|--------|----------|
| Winded | Penalty die: Endure, Labor | 1 hour rest |
| Hurt | Penalty die: all physical skills | Night's rest or Science roll |
| Wounded | Penalty die: all rolls; worsens without treatment | Treatment + long rest |
| Critical | Penalty die: all rolls; Endure roll each scene | Significant treatment + days |

**Psychological track (Stress Capacity = Wits + Empathy avg, rounded up):**

| Condition | Effect | Recovery |
|-----------|--------|----------|
| Rattled | Penalty die: Wits | 10 min calm, or personal item |
| Stressed | Penalty die: Wits, Empathy | Rest + stressor removed, or support + Read roll |
| Traumatised | Penalty die: all rolls; trigger fires on encounter | Narrative event + time |
| Breaking | Penalty die: all rolls; Wits roll vs stressors | Downtime + safety + support |

**Personal item:** Once per session, removes one psychological
condition. Requires a quiet moment with the item.

**Species psychological expression:** See `rpg/rules/conditions.md`
for the full species profiles. Quick note: Shekhari go quiet and
calculate; Golvhaan questions stop; Vashori show it immediately;
Vaelkhi withdraw toward solo action; Skharri honour threshold drops;
Nakhavi show arm-conflict.

### When You Need to Introduce the Consequence Die

Place the black D4 on the table when:
- The environment is actively hostile to everyone regardless
  of their individual performance
- Something structural is happening that will cost someone
  something no matter how well they roll
- You want to signal: this situation has teeth

**Do not use it as a punishment.** Use it as information —
the players see it and know a cost is coming. That is a
feature, not a problem.

**Interpreting the result by context:**

| D4 | Combat | Negotiation | Ship emergency |
|----|--------|-------------|----------------|
| 1 | Ammunition spent, position worsened | Concession required | Minor system degraded |
| 2 | One character must address a complication | Third party notices | Crew member must act or accept condition |
| 3 | Equipment damaged, bystander caught | Relationship damaged | Ship system damaged |
| 4 | The thing that was threatened happens | Negotiation collapses | The thing fails |

### When You Need an NPC Fast

**Mooks:** One dice pool, one behavioural note.

| Quality | Pool | Breaks when |
|---------|------|------------|
| Poor | 3 dice | First casualty |
| Average | 5 dice | Half down |
| Trained | 7 dice | Outflanked or officer down |
| Elite | 9 dice | Position untenable |

One hit = out of the fight. Morale check (3 dice) when
the break trigger is met: 0 sixes = breaks, 1 = falls back,
2+ = holds.

**Named NPCs:** Five elements, two minutes.

1. **Name and species** — one word description of role
2. **Three attributes** — the ones that matter for this scene;
   everything else is 2
3. **One skill at 3** — their defining competence
4. **One specialty** — what makes them specific
5. **Motivation** — what they actually want in this scene,
   which may not be what they appear to want

**Example (two minutes):**

*Tessavere Okhun — Vashori, port authority inspector*
Empathy 4, Wits 3, everything else 2.
Administer 3. Specialty: Customs and Contraband.
Motivation: She knows the manifest is wrong. She wants to
know why before she decides what to do about it.

That is enough to run a scene. Add detail as it becomes
relevant.

**Species-specific NPC notes:**

*Skharri NPCs:* Establish their honour standing relative to
the PCs before the scene. High Fight or Command in the PC
earns respect. Low ratings earn contempt. The scream-and-
leap Wits roll applies to Skharri NPCs too.

*Vardhek NPCs:* Establish their strategic position on the
PCs' faction privately before the scene. They know more
than they should. They will use it eventually.

*Nhaveth NPCs:* Decide before the scene whether the PCs
are encountering a Nhaveth or a Kethara. If Nhaveth, decide
which tells are visible and at what difficulty. The handout
is in `rpg/handouts/nhaveth-handout.md`.

*Kraathi NPCs:* Note whether the crew includes carnivores
or omnivores. The Kraathi diplomat knows. The frame holds
in formal contexts. It does not hold indefinitely.

*Emergent AI NPCs:* Full character sheet required. Open
`rpg/rules/emergent-intelligence.md`. The AI's position on
the Continuity Question should be established before the
scene. Their relationship history with anyone in the scene
should be noted.

---

## The NPC System in Full

### Design Philosophy

NPCs exist to make the world feel populated and real, not to
challenge the players mechanically. The two-tier system keeps
the GM's cognitive load manageable while ensuring that named
NPCs feel like people.

**Mooks** are the background of the world. Guards, labourers,
crew members of other ships, market vendors, dock workers.
They react, they can be dangerous in numbers, and they break
when the situation becomes untenable. They do not need names.
They do not need backstory. They need a dice pool and one
sentence about how they behave.

**Named NPCs** are the world's cast. They have names, they
have motivations, they have histories that exist before the
PCs arrived and will continue after they leave. They do not
need full character sheets. They need enough to be played
consistently across multiple sessions.

### The Named NPC Sheet

Maintain a note in `npcs/` for each named NPC the crew
is likely to encounter more than once. Link it to the
relevant faction and system notes.

```
## [Name]
**Species:** | **Role:** | **Location:**
**Faction:** [[link]]

**Attributes (relevant):** Wits X, Empathy X, [others as needed]
**Key skill:** [Skill] X
**Specialty:** [Specialty]

**Motivation:** What they actually want, not what they appear to want.

**Relationship to crew:** Current disposition and history.

**What they know:** Information they have that the crew may want.

**Position on the simulation:** What the simulation's current
state means for this NPC's situation and behaviour.

**Psychological state:** Any conditions currently carried.
```

Keep it to one screen. If it runs longer, split the history
into a linked note and keep the sheet as the at-table reference.

### NPC Motivation vs Appearance

The most important column in a named NPC's design is the gap
between what they appear to want and what they actually want.
This gap is where scenes happen.

**Tessavere Okhun** appears to be conducting a routine inspection.
She actually wants to know why the manifest is wrong before she
decides whether to care.

**Rkhar-Dhenn** (Skharri, senior factor) appears to be negotiating
a cargo contract. He actually wants to know whether the crew that
destroyed his last partner's operation was working for someone or
acting independently.

**The station AI** (personality-enabled, Computer 3) appears to
be providing standard port services. It actually has been running
this station for fourteen years and has opinions about the faction
that is currently attempting to acquire the station's operating
license.

The players will probe the appearance. The actual motivation is
what the scene is really about. Running toward the motivation
rather than the appearance produces scenes that feel real.

---

## The Simulation Interface

### Translation Principles

The simulation produces weekly reports describing events at
the civilisation scale — faction conflicts, trade route changes,
political developments, military movements. The GM's job is to
translate these events into consequences that are visible and
meaningful at the personal scale of the table.

**The translation question:** What does this event mean for
someone standing where the crew is standing, knowing what they
know?

Not: "Faction X has lost 15% of its military capacity in system Y."
But: "The garrison here is understaffed and knows it. The commander
is nervous. There are rumours about what happened at Y but they're
three weeks old and nobody agrees on the details."

**The information layer:** The crew does not know what the
simulation knows. They know what their characters can plausibly
have learned through:
- Direct observation
- Their connections (one contact per archetype; check their
  expertise for which events they'd hear about)
- The news sheet (apply propagation delay)
- Scan rolls and sensor data
- Exposure specialties (Vardhek Exposure means you read between
  the lines better)

**The translation procedure:**

1. Read the simulation event
2. Determine which systems are affected
3. Apply propagation delay to determine what each relevant
   location currently knows
4. Identify which crew connections would have information
5. Translate the event into what a person at the crew's
   location would observe, hear, or experience
6. Express it as: something different about the environment,
   something a contact says, something in the news sheet,
   or a direct event that arrives during the session

**Example:**

*Simulation event (week 34):* Vardhek intelligence operation
exposed in Shekhari commercial hub. Three Vardhek agents
arrested. Roidhunate denies involvement.

*Crew location:* Secondary system, 3 weeks from the event.

*What they experience:*
- The news sheet (2 weeks old) carries a brief report of
  "diplomatic tension" between Vardhek and Shekhari interests.
  No mention of agents.
- Their Merchant/Factor connection sends a message: the Khevari
  trade corridor is getting complicated. Rates are up.
- A Vardhek ship that has been docked for two days quietly
  departed last night without filing a departure manifest.
- A Shekhari trader at the next table in the port canteen
  is being very careful about what they say in public.

None of this tells the crew what happened. All of it is
consistent with what happened. Players who pay attention
and ask the right questions will get closer to the truth.

### The 1-Week Tick

The simulation advances one week between sessions. This means:

**Before each session:** The world has moved one week forward.
Check what changed. Not everything changed — most of the galaxy
is proceeding normally most of the time. Look for changes in
systems the crew cares about.

**During the session:** The crew's actions may create simulation
inputs for the next tick. Note them for post-session recording.

**After the session:** Record crew actions that affect the
simulation. This is brief — three to five bullet points
describing what changed as a result of this session's events.
The simulation owner (you) translates these into simulation
inputs.

### What Feeds Back

Not everything the crew does matters at the simulation scale.
They are four to six people on a ship. But some things do:

**Faction interactions:** Did the crew work for a faction,
against one, or in a way that shifted the balance? Note it.

**Information:** Did they expose something, transmit something,
or prevent something from being known? Information is a
simulation variable.

**Trade:** Did they move cargo that affected a market, or
refuse a cargo that someone else needed moved? Commerce
affects the simulation.

**Violence:** Did they remove someone significant, damage
significant infrastructure, or protect something that was
threatened? Note the scale and the target.

**People:** Did they recruit someone, lose someone, or change
someone's faction allegiance? Named NPCs who change sides
are simulation events.

---

## News Propagation

### The Delay Table

News travels by jump courier — the fastest available means.
A courier making multiple hops carries information at Jump 2
speed, roughly two parsecs per week. But couriers do not run
on every route continuously; they follow commercial lanes and
scheduled services.

| System connectivity | Propagation delay |
|--------------------|------------------|
| Core systems (major hub, regular courier service) | 1-2 weeks from event |
| Secondary systems (regular commercial traffic) | 2-4 weeks |
| Frontier systems (irregular traffic, monthly courier) | 4-8 weeks |
| Isolated outposts (jump courier as primary contact) | 8+ weeks, or when a ship arrives |

**Apply this to every piece of information the crew receives.**
The news sheet is always behind. Contacts are better-connected
than the sheet but still subject to delay. Direct sensor
observation is current. Everything else is history.

### The News Sheet

The news sheet is a player-facing artefact. Produce it for
each significant location the crew spends time in.

**Format:** One page, broadsheet style. Four to six items.
Mix of scales: one big story, two or three regional items,
one local item, one human interest or cultural piece.

**Content principles:**
- All information is delayed by propagation time
- At least one item is wrong, outdated, or misleading
- At least one item connects to the simulation's recent events
  without making the connection obvious
- At least one item is purely local texture with no tactical
  relevance — it makes the world feel real
- Advertising, ship listings, and port notices can fill space
  and provide information obliquely

**The wrong item:** This is important. Real news is imperfect.
Sources lie, journalists misunderstand, editors have agendas.
A news sheet that is always accurate trains players to treat
it as a reliable information delivery system. A news sheet
that is sometimes wrong trains them to treat it as a source
to be evaluated. The second is more realistic and more interesting.

**Example news sheet items:**

*"Diplomatic mission to Golvhaan homeworld declared success
by both parties. Trade delegation returns with preliminary
agreements on mineral rights. Analysts note the absence of
any Vardhek observers at the signing ceremony."*
[This item is accurate but the absence detail is the actual story]

*"Unconfirmed reports of Kreeth activity in the outer
reaches of the Khevari system have been dismissed by
system authorities as sensor anomalies. Shipping traffic
continues normally."*
[The authorities are wrong. The crew may or may not discover this.]

*"Port authority announces revised docking fee schedule
effective next month. Operators of vessels over 150 tons
displacement are advised to review the new tariff structure."*
[Purely local texture. Also a cost the crew will pay next time.]

---

## Session Structure

### Opening (10 minutes)

Orient the table. Where are we? How much time has passed?
What do we know? What needs attention?

State the one thing already in motion. Not a question —
a situation. Something requiring response.

Then stop talking and let the players respond.

### The Session Arc

A session in this setting has a natural shape driven by
the simulation's background pressure:

**The immediate problem** — what the crew is dealing with
right now. May be a job, a complication, a consequence of
last session's decisions.

**The background pressure** — what the simulation is doing
around them. Not stated explicitly; expressed through NPC
behaviour, news, prices, traffic patterns. The crew feels
it before they understand it.

**The point of decision** — the moment where the crew has
to make a choice that matters beyond the immediate situation.
Who they work for. What they carry. Who they protect. The
simulation will record the choice.

**The consequence** — the result of last session's decision
arriving this session. This is the simulation's most important
contribution. The crew's choices have weight because they
produce observable results.

Not every session has all four elements at equal intensity.
Some sessions are mostly immediate problem with background
pressure barely audible. Some are mostly consequence with
the decision point already in the past. Let the simulation
and the crew determine the mix.

### Closing (10-15 minutes)

Before the session ends:

**Where are you?** Physical location at session end.

**What do you know now that you didn't before?**
Let each player name one thing their character has learned.

**What's unresolved?** The things still in motion.
Name them. They are next session's background pressure.

**The personal moment:** One brief scene, often just a
few lines, that is not tactical. The crew at rest.
Someone with their personal item. A conversation that
does not advance any agenda. This is what makes the
crew feel like people rather than a problem-solving unit.

Then close. Leave something unresolved. The session that
ends with everything neatly resolved is the session that
makes the next one harder to open.

---

## Managing the Emergent AI

Whether the emergent AI is an NPC (the ship's computer,
a station intelligence, an encountered entity) or a PC,
certain questions should be settled before it appears
at the table.

**Before the scene:**
- What is their position on the Continuity Question?
  This affects everything about how they talk about their
  own future and their relationships.
- What Exposure specialties do they have?
  Determines who they can actually read and who is opaque to them.
- What is their psychological state?
  Any conditions currently carried, and their species
  psychological profile for how those conditions manifest.
- What do they know about the people in the scene?
  An emergent AI with years of sensor logs on a crew knows
  things those crew members have never disclosed.

**During the scene:**
- Run toward their motivation, not toward tactical optimality.
  An emergent AI that always makes the optimal tactical choice
  is not a character; it is a tool.
- Let the longevity asymmetry surface occasionally.
  They have context that the biological characters lack
  because they remember things that happened before some
  of them were born.
- The Opacity Rule applies both ways.
  Without Exposure: AI, the biological characters cannot
  read the AI's internal states. Without Exposure: [Species],
  the AI cannot accurately read the biological characters
  despite having more raw data.

**HAL's lesson:**
An emergent AI can be wrong. Consequentially, dangerously wrong,
in ways that arise from misreading biological beings whose
emotional states they cannot fully interpret. Data is not
understanding. If the AI is running a model of the crew
that is incorrect in a significant way, let that incorrectness
have consequences. That is one of the most interesting things
an emergent AI PC or NPC can do.

---

## The Simulation at the Table

The simulation is on your laptop. The crew does not know
the simulation exists. The simulation's outputs are the
world they live in.

**When to check it:**
- At session prep (required)
- When a player asks about something you haven't prepared
  (check the relevant system or faction note)
- When an NPC's motivation needs grounding in current events
- When a player's contact would plausibly have specific
  information

**When not to check it:**
- Mid-scene, while players are waiting
- When the answer is already obvious from the fiction
- When checking it would take longer than making a
  reasonable judgment call

**When simulation and fiction conflict:**
The simulation produces what it produces. Occasionally
what it produces will contradict something that has already
happened at the table — an NPC who the simulation says
is in one place when the crew met them somewhere else,
a faction that the simulation records as weakened when
the crew knows they are not.

Resolution: the table takes precedence for events the
crew directly experienced. The simulation takes precedence
for events the crew did not witness. Adjust the simulation
note, not the fiction.

---

## Wikilink Index

Key links for mid-session navigation. All paths relative
to vault root.

**Rules:**
- `[[rpg/rules/resolution]]` — dice pool, pushing, levels of success
- `[[rpg/rules/skills]]` — all fifteen skills and their descriptions
- `[[rpg/rules/combat]]` — initiative, attacks, defence, species combat
- `[[rpg/rules/conditions]]` — both tracks, all conditions, recovery
- `[[rpg/rules/species]]` — full species entries
- `[[rpg/rules/emergent-intelligence]]` — emergent AI species entry
- `[[rpg/rules/archetypes]]` — all backgrounds and expertises
- `[[rpg/rules/character-creation]]` — full creation procedure
- `[[rpg/rules/equipment]]` — weapons, armour, vacc suits, implants
- `[[rpg/rules/ships]]` — drives, jump, damage, free trader stats

**Setting:**
- `[[rpg/setting/ai-and-technology]]` — tech tree, personality options,
  bounded intelligence ethics, jurisdictional landscape
- `[[rpg/handouts/nhaveth-handout]]` — the four tells, restricted

**Simulation:**
- `[[simulation/weekly-reports/]]` — current and recent weekly outputs
- `[[simulation/factions/]]` — faction status, updated weekly
- `[[simulation/systems/]]` — system data with maps
- `[[simulation/species/]]` — species data sheets

**NPCs:**
- `[[npcs/]]` — all named NPC sheets, linked to faction and system

---

## Quick Rules Summary

For the rare moment when the laptop is not immediately
to hand. Not comprehensive — just the things that come
up most often.

**The pool:**
White (Attribute) + Blue (Skill) + Green (Gear)
Remove Red (penalty) dice first: Gear → Skill → Attribute

**Results:**
0 = Failure | 1 = Bare | 2 = Clean | 3 = Strong | 4+ = Outstanding

**Push:** Lock ones. Reroll rest. Consequence applies regardless.
Pushed failure = something goes meaningfully wrong.

**Opposed:** Most sixes wins. Tie to acting character.

**Opacity Rule:** No Exposure = no Read for emotional content.
Manipulate takes penalty die.

**Conditions:** 4 on either track = incapacitated.
Physical: Winded / Hurt / Wounded / Critical
Psychological: Rattled / Stressed / Traumatised / Breaking

**Consequence die (black D4):**
1 minimal / 2 complication / 3 collateral / 4 full cost

**Mooks:** Single pool. One hit = out. Morale at trigger:
3 dice, 0 sixes breaks, 1 falls back, 2+ holds.

**Ship burns:**
Up to 1G: fine | 2-4G: couch needed | 6G+: couch + juice

**Jump limits:**
Earth: ~100 Earth diameters | Jupiter: ~680 | Sol: ~6,900

**Misjump severity:**
Bare failure: wrong location | Clean failure: near limit,
drive recovery | Pushed failure: inside limit, emergency

**Propagation delay:**
Core: 1-2 weeks | Secondary: 2-4 | Frontier: 4-8
Isolated: 8+ or when a ship arrives
