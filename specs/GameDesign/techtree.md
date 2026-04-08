# Tech Tree — Design Reference

This document explains the tech tree structure, the meaning of each domain and
node, and how the prerequisite graph produces the major civilisational milestones.
The canonical diagram source is `techtree.dot` (Graphviz) and `techtree.mmd`
(Mermaid).

---

## Overview

The tech tree is a **directed acyclic graph (DAG)** of prerequisite nodes, not
a single linear scale.  Technology is organised into six semi-independent
**domains**, each advancing on a scale of 0–8.  Specific technologies are nodes
within that domain; a technology requires that prerequisite nodes in one or more
domains have been reached before it becomes researchable.

This replaces the single Traveller-style Tech Level with a richer structure that
allows civilisations to be genuinely advanced in one area and behind in another
— a natural consequence of species traits, resource availability, and strategic
choice.

### Why six domains?

| Domain | What it represents |
|---|---|
| **Power** | Energy density, generation, and storage capability |
| **Materials** | Structural, thermal, and exotic matter engineering |
| **Computing / Info** | Sensors, navigation, communications, AI |
| **Life Support / Habitat** | Environmental engineering, colony endurance, terraforming |
| **Biotech** | Individual augmentation, germline engineering, consciousness technology |
| **Propulsion** | In-system and interstellar travel |

The first four are the classic "hard SF civilisation pillars" and gate virtually
everything.  Propulsion is separated because it is the domain most directly
connected to the major game milestones (interplanetary, interstellar, FTL).
Biotech is separated from Life Support because it operates on the *organism*, not
the *environment* — the design consequences are categorically different.

---

## Domain: Power

Progress in Power represents the energy density a civilisation can reliably
generate, store, and deliver.  Almost every other domain has a Power prerequisite
somewhere in its chain — you cannot build a fusion-powered starship drive without
fusion-grade power, and you cannot produce exotic matter without antimatter-tier
energy budgets.

| Level | Description | Significance |
|---|---|---|
| **P-1** | Chemical and fission power | Industrial base; orbital launch becomes practical |
| **P-2** | Fusion (practical) | Cheap energy surplus; powers high-thrust in-system drives and early life support |
| **P-3** | Fusion (high-density) | Enables the continuous power draw of interstellar drives and large terraforming operations |
| **P-4** | Antimatter / exotic matter tap | Gate-level requirement for jump drive research; enables relativistic propulsion |

---

## Domain: Materials

Progress in Materials determines what structures, vessels, and devices can
physically be built.  Jump drives require the ability to handle exotic matter —
you cannot reach jump capability without M-3 at minimum.  High-thrust
interstellar drives require materials that can survive relativistic particle
flux, which requires M-2.

| Level | Description | Significance |
|---|---|---|
| **M-1** | Industrial alloys and composites | Structural basis for orbital and in-system construction |
| **M-2** | Nanostructured materials | Enables heat shields and hull materials for high-velocity interstellar travel |
| **M-3** | Exotic matter detection and handling | The scientific prerequisite for understanding jump geometry; enables FTL research |
| **M-4** | Active exotic matter production | Engineering prerequisite for a working jump drive; produces the metric distortion field |

---

## Domain: Computing / Information

Progress in Computing governs sensors, navigation precision, communications
bandwidth, and artificial cognition.  Critically, it is the primary driver of
**jump transit time** — getting a ship through jumpspace faster is fundamentally
a navigational computation problem, not a power problem.

| Level | Description | Significance |
|---|---|---|
| **C-1** | Digital networks and basic AI | Baseline for coordination, targeting, and the early biotech research chain |
| **C-2** | High-bandwidth sensors and navigation AI | Enables precise long-range observation and the navigational demands of interstellar approaches |
| **C-3** | Predictive navigation and quantum communications | Required for jump drive navigation precision; enables fast transit times |
| **C-5** | Substrate-independent cognition | Consciousness can exist outside biological tissue; gates neural interface / upload tech |

C-4 is omitted from the initial diagram — it represents intermediate AI
capability between C-3 and C-5 that has not yet been designed in detail.

---

## Domain: Life Support / Habitat

Progress in Life Support determines how far from ideal conditions a species can
operate for how long, and ultimately what can be done to hostile worlds to make
them habitable.  It is the primary brake on colony sustainability and the
prerequisite chain for terraforming.

| Level | Description | Significance |
|---|---|---|
| **L-1** | Closed-loop life support | Sustained habitat in space; prerequisite for any crewed interplanetary mission |
| **L-2** | Long-duration cryo and generation ship technology | Enables interstellar travel at sublight speeds; centuries-long missions become survivable |
| **L-3** | Directed terraforming | Active planetary atmosphere and climate modification; also gates germline engineering (knowledge of large-scale biological systems) |
| **L-4** | Full planetary engineering | Restructuring of planetary bodies at civilisational scale; the ceiling of habitat expansion |

---

## Domain: Biotech

Progress in Biotech operates on the organism, not the environment.  It is the
domain most sensitive to species social traits — `hierarchy_tolerance` determines
who receives augmentation, `social_cohesion` determines whether germline
divergence causes polity fracture, and `adaptability` determines how quickly the
technology is culturally adopted.

| Level | Description | Significance |
|---|---|---|
| **B-1** | Advanced medicine and gene therapy | Extends lifespan, cures disease, enables genetic screening; requires C-1 and L-1 as foundations |
| **B-2** | Somatic augmentation and implants | Cybernetic and biochemical modification of individual adults; reversible in principle; requires C-2 (precision tools and interfaces) |
| **B-3** | Performance augmentation (military grade) | Augmentation specifically optimised for combat or extreme environments; a branch from B-2 |
| **B-4** | Germline engineering (heritable) | Modifications that pass to offspring; population-level consequences over generations; requires L-3 (equivalent understanding of complex biological systems) |
| **B-6** | Neural interface and consciousness substrate | The mind can interface directly with computing systems; at the ceiling, consciousness can be migrated; requires C-5 |

B-5 is reserved for an intermediate stage (deep neural augmentation, partial
upload) not yet designed in detail.

### Species notes for Biotech

- **Kraathi**: augmentation of individuals threatens the herd-dependency bond.
  B-2 is likely to produce a religious-political schism before it reaches
  widespread adoption.  Full germline modification (B-4) may be culturally
  prohibited entirely.
- **Vardhek**: B-6 neural interfaces are treated as a strategic intelligence
  asset and will be developed covertly before they are acknowledged publicly.
- **Nakhavi**: the Biotech chain advances *inward* — enhancing inter-arm
  communication bandwidth and stabilising the individual/collective cognition
  split — rather than outward as implants.  Same domain levels, structurally
  different research path.

---

## Domain: Propulsion

Progress in Propulsion is the most directly visible domain in gameplay — it
determines where ships can go and how fast.  The domain splits at the interstellar
threshold into two tracks that can advance independently:

- **Jump Range** (how far per jump) — driven primarily by Power and Materials
- **Jump Transit Time** (how long spent in jumpspace) — driven primarily by
  Computing

| Level | Description | Significance |
|---|---|---|
| **PR-1** | Orbital rockets | Reaches orbit; prerequisite for all space-based infrastructure |
| **PR-2** | In-system drive (weeks between planets) | Practical colonisation and mining within a home system |
| **PR-3** | High-thrust in-system / sublight capable | Interstellar transit at sublight speeds becomes physically achievable (though takes generations without cryo) |
| **PR-4** | Relativistic drives | Near-lightspeed travel; time dilation becomes a factor; enables fast interstellar courier runs pre-FTL |

---

## Milestones

Milestones are specific threshold events that mark civilisational capability
transitions.  They do not correspond to a single domain level — they require
prerequisites across multiple domains simultaneously.

### Orbital Capability
**Requires:** P-1, M-1, PR-1

The species can reliably reach and maintain orbital presence.  Unlocks
space-based telescopes, orbital manufacturing, and the foundations of
interplanetary industry.

### Space-Based Telescopes
**Requires:** Orbital Capability + C-1

Dramatically improves astronomical survey capability.  In a game context this
means improved advance knowledge of neighbouring star systems — which worlds are
present, rough composition, whether they are inhabited — before any ship is sent.

### Interplanetary Travel
**Requires:** P-2, PR-2, L-1

Crewed missions can sustain themselves across planetary distances.  Enables
asteroid mining, gas giant fuel skimming, and the establishment of permanent
off-world colonies within the home system.

### Interstellar Sublight
**Requires:** Interplanetary + P-3, PR-3, M-2, L-2, C-2

Generation ships or cryo vessels can reach other star systems.  Transit times
are measured in decades to centuries depending on destination.  This is the
first capability that expands a polity beyond its home system, but the pace of
expansion is extremely slow relative to FTL.

### FTL Precursor
**Requires:** M-3, C-3

The civilisation understands, theoretically, that jump geometry is possible.
They can detect exotic matter and model metric distortions.  This does not mean
they can build a jump drive — it means the research programme for one can begin.
Without this unlock, jump drive research cannot proceed regardless of Power or
Materials level.

---

## Jump Drive — Split Tracks

The jump drive is the primary FTL capability modelled.  It is split into two
independently advanceable tracks.

### Jump Range
**Requires for Range-1:** FTL Precursor + P-4 + M-4

Range is how far a single jump can carry a vessel — measured in parsecs.  It is
driven by **Power** (energy budget for the metric distortion) and **Materials**
(quality of exotic matter available and structural tolerance of the drive).

- **Range-1** (1 parsec per jump): first working jump drive; covers about 3
  light-years
- **Range-3** (3 parsecs per jump): mid-range capability; same prerequisites
  as Range-1 but at higher domain levels

Increasing range is expensive in fuel and drive mass.  Long-range drives are
large, power-hungry capital-ship equipment.  Short-range drives are smaller and
cheaper — courier ships and scouts will often run Range-1 drives.

### Jump Transit Time
**Requires for 5-day transit:** C-3 (already required for FTL Precursor)

Transit time is how long the ship spends *in* jumpspace on a single jump.  It
is driven by **Computing** — specifically the precision of the navigation
solution computed before jump entry.  A better AI plots a tighter trajectory
through jumpspace, shortening the transit.

- **3-week transit**: baseline capability; arrives safely but slowly
- **5-day transit**: optimised navigation; same jump, shorter subjective duration

These tracks are independent: a polity can have Range-3 / 3-week transit (heavy
long-range drives, primitive nav AI) or Range-1 / 5-day transit (short-range but
fast courier capability) as genuine distinct strategic postures.

---

## Species Modifiers

The tech tree structure is universal — every polity uses the same DAG.  Species
traits modify *how fast* a polity advances and *what costs* apply at specific
nodes; they do not change which prerequisites are required.

| Species field | Effect |
|---|---|
| `adaptability` | Rate of advancement per domain — high adaptability polities research faster |
| `hierarchy_tolerance` | Who receives Biotech upgrades — high hierarchy societies distribute B-2+ to dominant classes first |
| `social_cohesion` | B-4 germline fork destabilisation risk — low-cohesion polities are more likely to fracture at B-4 |
| `faction_tendency` | Parallel-track divergence — high-faction polities develop competing technology programmes, which can advance overall domain level faster but with incompatible implementations |

### Hard species constraints

Some constraints are structural, not modifier-based:

- **Kraathi**: all Propulsion and Life Support nodes carry an open-volume
  architecture cost multiplier (ships are larger for the same capability level)
- **Nakhavi**: planetary colonisation nodes are penalised; orbital habitat nodes
  are cheaper than for surface-dwelling species
- **Nhaveth**: technology advances through court competition — domain levels
  should be tracked per court/polity, not per species, and will vary significantly
  between courts
- **Kreeth**: no foreign technology adoption; cannot gain domain levels through
  trade or capture; no internal R&D competition means no faction-tendency
  acceleration bonus

---

## Open Design Questions

- [ ] Where do **weapons** sit — are they a domain, or derived technologies
  within Power / Materials / Computing?
- [ ] Does **communications range** branch off Computing, or is it a separate
  sub-track?  Interstellar communication without FTL is a significant strategic
  asymmetry.
- [ ] **AI risk / singularity events** at C-5 / B-6 intersections — does the
  game model these as polity-level events, or are they off the edge of the
  simulation?
- [ ] Exact domain level numbers at each prerequisite threshold need balancing
  pass once the economic model is designed.
- [ ] **Technology transfer** between polities — how does a low-adaptability
  species react to receiving a tech gift?  Does it accelerate domain level or
  just add the node without the underlying domain capability?
