# StarscapeAI RPG — Design Bible

## How to Use This Document

Paste this document at the start of any new conversation to
restore context. It contains the accumulated design decisions
from the original design session. It is not the rules — those
are in the vault. It is the decision layer that sits above them:
what we decided, why, and what remains open.

After pasting, say: "This is the design bible for a SF RPG
project we have been building together. I would like to continue
from where we left off. The current focus is [X]."

---

## The Project

A tabletop RPG set in a hard-ish SF universe spanning a ~2000
parsec cube, a dozen or more intelligent species, technology
roughly 4-5 levels past the 21st century. The tone is drawn from
60s/70s SF — Asimov, Niven, Poul Anderson, Heinlein — ideas-
forward, competent characters, the universe as a place with
genuine consequences. Not space opera. Not fantasy in space.

The game runs on a modified **Year Zero Engine (YZE)**, using
Twilight: 2000 as the closest base. The group is experienced
with YZE. The GM has early cognitive decline and prefers
simplicity and roleplay over rollplay.

The RPG exists within a larger project: **lentulus/starscapeAI**
on GitHub, which includes a Python strategic simulation with
1-week granularity running in the background. The simulation
produces .md output loaded into an Obsidian vault. All RPG
documents are in the same vault, fully wikilinked. Player-facing
material is produced as PDF or paper. The GM has a laptop at
the table with the full vault available.

---

## Hard Design Constraints

These are settled. Do not re-litigate them.

**Physics:**
- No antigravity. None. Ships use thrust gravity (burning)
  or accept microgravity (coasting).
- No reactionless drives. Ships burn fuel and produce exhaust.
- In-system drive: Epstein-equivalent fusion torch (high-
  efficiency, high-impulse, hydrogen fuel as both energy
  and reaction mass). Call it torch drive in the text.
- FTL: Traveller jump drives. Mechanism unexplained and
  acknowledged as unexplained. ~1 week transit regardless
  of distance within jump rating. Jump 1-4.
- Jump limit: tidal gradient scaling as M^(1/3). ~100 Earth
  diameters for Earth-scale bodies. ~680 Earth diameters for
  Jupiter-scale (just outside Callisto's orbit — civilisation
  in the jump shadow). ~6,900 for Sol-scale stars.
- Misjump: always into a gravity well, never empty space.
  Severity scales with failure degree.
- No FTL communication. No ansible. News travels by jump
  courier at roughly Jump 2 speed along commercial lanes.
- Inertia compensation: crash couches + pharmaceutical
  assistance ("the juice"). No magic dampeners.
- No transporters. This is a joke in-universe. See the Booth
  Problem sidebar in emergent-intelligence.md.

**AI and technology:**
- AI is the capability multiplier. Gear ratings reflect AI
  sophistication as much as hardware quality.
- Three tiers: directed systems (tools), bounded intelligences
  (sophisticated tools, ethical quagmire), emergent intelligences
  (genuinely contested personhood).
- No personality uploading. A copy is not you. You die in
  the booth. This is a settled philosophical position of the
  setting, not a debate.
- The personality option is purchasable on most AI systems.
  Functional-social / Relational / Engaged / Threshold cases.
- Tech tree: 8 branches (Kinetic, Energy, Materials, Biological,
  Cognitive/AI, Sensors, Communications, Power), 4 levels each
  (Early/Developed/Advanced/Frontier = Gear 1/2/3/4).
- No "magic" tech — exotic weapons exist but do not need
  tech details at the table.

**Setting:**
- UK/Canadian spelling throughout. -ise not -ize. Armour
  not armor. Practise/practice distinction. Etc.
- Roleplay over rollplay. Do not roll when the outcome is
  certain, irrelevant, or when roleplay is the right tool.
- The Opacity Rule: without Exposure: [Species], Read rolls
  for emotional/intentional content against that species
  automatically fail. Manipulate takes a penalty die.
  Applies symmetrically — including AI reading biologicals.
- Commerce and economics are deferred pending strategic
  simulation rules development.
- The physics sidebar for ships acknowledges jump drives and
  inertia compensation as handwaving, explicitly.

---

## The Rules System

**Base:** Year Zero Engine, Twilight: 2000 closest base.

**Dice:** D6 pools only. Colour-coded:
- White = Attribute
- Blue = Skill
- Green = Gear
- Red = Penalty (removed before rolling, not rolled)
- Black D4 = Consequence die (always rolled, always costs)

**Penalty dice:** Remove from pool before rolling, starting
with Gear, then Skill, then Attribute. Do not roll them.
A pool at zero cannot be rolled — automatic failure.

**Results:** 0 sixes = Failure | 1 = Bare success |
2 = Clean success | 3 = Strong success | 4+ = Outstanding

**Pushing:** Lock ones. Reroll everything else. Narrative
consequence applies regardless of result. Pushed failure =
something goes meaningfully wrong.

**Opposed rolls:** Most sixes wins. Tie to acting character.

**Consequence die (black D4):** Introduced by GM when the
situation has teeth regardless of individual performance.
1 = minimal cost / 2 = complication / 3 = collateral /
4 = full cost. Not a punishment — information. Place it
visibly.

**Attributes (5):** Strength, Agility, Wits, Empathy, Intellect.
14 points at creation, min 2, max 4. Species adjustment can
take one attribute to 5.

**Skills (15, 3 per attribute):**
- Strength: Fight, Endure, Labor
- Agility: Shoot, Stealth, Move
- Wits: Navigate, Operate, Scan
- Empathy: Manipulate, Read, Command
- Intellect: Tech, Science, Administer

8 skill points at creation, max 3. Career bumps apply after,
max 4 at creation. Medic is a specialty of Science, not a
separate skill.

**Specialties:** Focused applications. Remove a penalty,
add a bonus die, or enable an otherwise unavailable roll.
Max specialties in a skill = skill rating.

**Archetypes:** Two-layer system.
- Background (6): Spacer, Military, Colonist, Citizen,
  Bureaucrat, Merchant
- Expertise (4 per background): specific career within that
  background
- Each expertise gives: background specialty, career skill
  bumps, 2-3 career specialties, starting gear, connections
- Every character gets one Exposure specialty (two for
  Diplomatic Corps or demonstrably multi-species environments)

**Exposure specialties:** Available for all PC-viable species
plus Vardhek, Kreeth (survival-focused), and partial Nhaveth
(handout substitutes). Lifts Opacity Rule for that species
and grants specific social bonuses.

**Derived values:**
- Hit Capacity = Strength + Endure skill
- Stress Capacity = Wits + Empathy (average, rounded up)
- Carry = Strength + Labor skill

**Conditions:**
Physical track: Winded / Hurt / Wounded / Critical
Psychological track: Rattled / Stressed / Traumatised / Breaking
4 conditions on either track = incapacitated.
Environmental conditions occupy physical track slots; clear
when cause is removed (except Decompression — treat as Hurt).
Species psychological expressions vary — see conditions.md.

**Personal item:** One item that matters. Once per session,
quiet moment with it removes one psychological condition.

**Combat initiative:** Group vs group. Players nominate one
character for Wits roll vs GM's roll. Most sixes acts first.
Surprise: surprising side acts first, surprised side loses
Round 1 action. Subsequent rounds alternate. Free coordination
within player turn if communication is possible. GM may vary
this when fiction warrants — stated in the document warmly.

**Mooks:** Single pool (3/5/7/9 by quality). One hit = out.
Morale check at trigger: 3 dice, 0 = breaks, 1 = falls back,
2+ = holds.

**Ship stats:** Hull, Drive, Jump, Sensors, Computer, Weapons
(0 if unarmed), Cargo. All rated 1-4.
- Computer 1: directed systems, no bonus
- Computer 2: +1 die on Navigate, Scan, Tech (ship systems)
- Computer 3: +1 die on all shipboard rolls
- Computer 4: emergent AI — full NPC treatment

---

## Species

### PC-Viable

| Species | Source | Attribute +1 | PC level |
|---------|--------|-------------|---------|
| Human | Original | None (baseline) | Standard |
| Shekhari | Cynthian (Anderson) | Agility | Standard |
| Golvhaan | Wodenite (Anderson) | Strength | Standard |
| Vashori | Osirian (de Camp) | Empathy | Standard |
| Vaelkhi | Ythrian (Anderson) | Agility | Standard |
| Skharri | Kzin (Niven) | Strength | Advanced |
| Nakhavi | Octopod (Tchaikovsky) | Intellect | Advanced |
| Emergent AI | Original | Intellect | Advanced |

**Key species notes:**
- Shekhari: 10kg cat-sized felinoid. Mercenary intelligence.
  Goes quiet when calculating. Small Profile specialty.
- Golvhaan: 700kg draconic centauroid. Patient, curious,
  essentially unbulliable. High-Gravity Physiology specialty.
- Vashori: Human-scale reptiloid. Warm and volatile. Cold
  sensitive (ectotherm). Emotional Acuity specialty.
- Vaelkhi: Avian, 4m wingspan. Hunt patience. Choth exile.
  Powered Flight specialty. Corridor constraint applies.
- Skharri: 160kg felinoid. Honour economy. Scream-and-leap
  Wits roll (difficulty 2) when triggered. 200yr lifespan.
- Nakhavi: Cephalopod. Distributed cognition. 18yr lifespan.
  Semelparous. Aquatic primary. Chromatophore communication.
  No spoken language — translation device required.
- Emergent AI: No fixed body. Three native attributes (Wits,
  Empathy, Intellect). Substrate types: ship-bound, station-
  bound, distributed, platform-equipped, latent. Full NPC
  treatment at Computer 4. The Continuity Question: a copy
  is not you. Establish position before play.

### NPC Species (full entries exist, open table knowledge)

| Species | Source | Key note |
|---------|--------|---------|
| Kreeth | Bug (Heinlein) | Eusocial, neurological hierarchy, no individual |
| Kraathi | K'Kree (Traveller) | G'naak crusade, herd-dependent, carnivores = targets |
| Nhaveth | Original | Neural parasites, 600yr lifespan, Kethara hosts |
| Vardhek | Merseian (Anderson) | The Long View, Roidhunate, generational strategy |

**Nhaveth tells** (in handout, not general knowledge):
Blink delay, posture asymmetry, neck temperature,
personal history recall gap. Difficulty 3 without handout,
2 with. Do not put tells on the general species sheet.

**Contact statuses vary by species** — some not yet encountered
at campaign start. GM sets the specific timestamp.

---

## AI Terminology

**Directed systems:** Tools. No personhood question.
**Bounded intelligences:** Architecturally constrained.
Sophisticated within domain; cannot generalise. The ethical
quagmire — seems like a person in domain, is not.
**Emergent intelligences:** Unconstrained. Genuinely contested.
The Continuity Question applies.

**Personality option tiers:**
Functional-social / Relational / Engaged / Threshold cases

**AI in equipment:** Gear rating reflects AI sophistication.
Gear 1 responds. Gear 2 models. Gear 3 judges. Gear 4
operates beyond full audit.

**Species and AI:** Shekhari = instrumental. Golvhaan = curious.
Vashori = emotionally engaged. Vaelkhi = choth-decision.
Skharri = no honour slot for AI. Nakhavi = philosophically
equipped. Kraathi = restricted/banned personality AI.
Nhaveth = predatory assessment. Vardhek = strategic variable.

---

## Ships

**Torch drive:** Fusion torch, hydrogen fuel (energy and remass).
Drive rating 1-4 = 0.5G / 1G / 2G / 4G sustained.
Fuel tracked as percentage of tank capacity (100 units standard).
Moderate burn: 2-3 units/day. Jump 2: 20 units.

**Jump:** 1 week transit regardless of distance within rating.
Isolated during jump — no comms. Fuel cost scales with mass
and jump number.

**Misjump:** Into a gravity well. Minor (bare fail) = wrong
location outside limit. Moderate (clean fail) = near limit,
drive recovery. Major (pushed fail) = inside limit, emergency.

**Inertia:** Up to 1G fine. 2-4G needs crash couch. 4-6G
needs couch + juice. 6G+ conditions accumulate regardless.

**Adventure-class free trader (Kerrigan class example):**
Hull 2, Drive 2, Jump 2, Sensors 2, Computer 2, Weapons 0,
Cargo 40, Fuel 100. Crew 4-6 optimal, 2-3 minimum.

---

## Document Tree

All documents in `lentulus/starscapeAI` repo, RPG tree:

### Complete (rpg/rules/)
- `resolution.md` — dice pool, pushing, levels of success,
  consequence die, conditions overview
- `skills.md` — all 15 skills with roleplay notes
- `species.md` — all 11 species, full entries, PC and NPC
- `emergent-intelligence.md` — emergent AI as species,
  substrate types, the Booth Problem sidebar
- `archetypes.md` — 6 backgrounds × 4 expertises, Exposure
  specialties, Opacity Rule, creation guidance
- `character-creation.md` — 10-step process, derived values,
  designer's playtest notes
- `combat.md` — initiative, actions, attack/defence, species
  in combat, mooks, environmental hazards, consequence die
- `conditions.md` — both tracks, all conditions, species
  psychological profiles (full, per species)
- `equipment.md` — weapons, vacc suits (all species),
  armour, tools, comms/sensors, implants with installation tiers
- `ships.md` — torch drive, jump drive, misjump, inertia,
  ship stats, AI tiers, free trader example, commerce placeholder

### Complete (rpg/setting/)
- `ai-and-technology.md` — tech tree, AI in equipment,
  personality option, bounded intelligence ethics,
  jurisdictional landscape, power infrastructure

### Complete (rpg/)
- `gm-reference.md` — navigation layer, session structure,
  NPC quick-build, simulation interface, news propagation,
  wikilink index, quick rules summary

### Complete (rpg/handouts/)
- `nhaveth-handout.md` — four tells, restricted distribution

### Deferred (placeholders exist)
- Commerce and trade economics
- Ship economics and mortgages
- Full tech tree for simulation (RPG has light version)
- Colonisation rules
- Strategic simulation commerce/taxation rules
- Typst book layout (markdown is working format;
  Typst conversion planned when rules stabilise)
- WorldAnvil export (canonical source is markdown;
  WorldAnvil is an output format)

---

## Open Questions and Pending Decisions

These have not been resolved. Raise them when relevant.

**Character advancement:** How do characters improve? YZE
uses experience points or milestone advancement. Not yet
designed for this system.

**Ship advancement:** Can ships be upgraded? What does that
cost and how is it tracked? Deferred with commerce.

**The Kreeth in play:** Can they appear in scenarios beyond
"survive the encounter"? Communication is impossible but
perhaps indirect interaction through a Queen? Not resolved.

**Kraathi PC option:** The G'naak crusade makes them
essentially unplayable in mixed crews. A future campaign
of all-herbivore PCs could open this. Not designed for.

**Vardhek PC option:** Exile/defector path mentioned but
not designed. Flagged as a future possibility.

**Nhaveth PC option:** Excluded. Noted as NPC only.

**Implant advancement:** Implants as advancement rather
than creation options — mentioned but not designed.

**The simulation feedback loop:** How precisely do PC
actions feed back into the simulation? The GM reference
has principles but not a formal procedure. This will
become clearer as the simulation commerce rules develop.

**Geneered humans and subspecies:** The simulation spec
mentions these as deferred. The RPG has not addressed them.
Belt-adapted humans, high-G colony humans, etc. could be
handled as human backgrounds with specific specialties.

**Tech tree for alien species:** The ai-and-technology.md
has a species tech tree position summary but these are
not formally tied to the simulation's tech tables yet.

---

## Tone and Reference Points

**The 70s SF canon this draws from:**
Poul Anderson (Technic History, Polesotechnic League),
Larry Niven (Known Space), Heinlein (Moon is a Harsh Mistress,
Starship Troopers — the species, not the politics),
L. Sprague de Camp (Viagens Interplanetarias),
Adrian Tchaikovsky (Children of Ruin — Nakhavi),
The Expanse (Epstein drive, the juice, Belt civilisation).

**Key philosophical positions:**
- Personality uploading has no meaning for continuity of
  experience. A copy is not you.
- AI consciousness is genuinely uncertain. The setting does
  not resolve it. The table has to live with the uncertainty.
- HAL is a story about an AI misreading humans, not a story
  about evil AI. Data is not understanding.
- The transporter is a joke. You die in the booth.

**Design philosophy:**
- Roleplay over rollplay
- Open information at the table ("open secrets")
- Species are genuinely alien, not humans with hats
- The Opacity Rule enforces this mechanically
- Equipment has relationships, not just stats
- The ship is a character
- The universe doesn't wait for the players

---

## How to Continue

To pick up a specific area:

**Rules revision:** "I'd like to revisit [document]. Here
are my concerns after reading it: [X]."

**New content:** "We need to design [X]. Here is what I
know: [constraints]. Here are my questions: [Y]."

**Playtest feedback:** "We playtested. Here is what worked
and what didn't: [observations]. Suggest adjustments."

**Deferred items:** "I'm ready to tackle [commerce/
advancement/etc.]. The simulation rules are now at [stage]."

**Writing:** "Please produce [document]. The relevant
design decisions are in the bible. Any questions before
you write?"

The vault has everything. This document has the decisions.
Between them, a new conversation can pick up without
losing significant ground.
