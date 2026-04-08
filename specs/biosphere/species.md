# Sophont Species

## Overview

Defines the `Species` table and associated design for representing intelligent
species in the simulation.  A species is a stable biological and cultural entity
within the ~4×10⁴ year simulation horizon — evolution and speciation do not occur.
Subspecies or geneered variants are out of scope here; cultural fracture is
captured via the `SophontPresence` and future faction tables, not by forking the
Species row.

This spec covers: biological traits, dietary and reproductive strategy, gaming
behavioural factors, and social cohesion metrics.  It does **not** cover tech
level, FTL capability, diplomacy, or military — those are civilisation-layer
concerns that will reference `species_id` but live in their own tables.

---

## Scope

**Includes:** Physical description, environmental tolerances, diet, reproduction,
risk/aggression disposition, social fracture risk.

**Excludes:** Individual characters, factions, civilisation state, tech trees,
FTL drive types.  Those will reference Species via FK but are defined elsewhere.

---

## Data / Schema

### `Species`

```sql
CREATE TABLE IF NOT EXISTS "Species" (
    -- Identity
    "species_id"          INTEGER PRIMARY KEY,
    "name"                TEXT NOT NULL UNIQUE,     -- canonical common name
    "homeworld_body_id"   INTEGER REFERENCES "Bodies"("body_id"),  -- NULL if homeworld unknown/destroyed

    -- Physical description
    "body_plan"           TEXT,   -- 'bilateral'|'radial'|'colonial'|'amorphous'|'exotic'
    "locomotion"          TEXT,   -- 'bipedal'|'quadrupedal'|'sessile'|'aquatic'|'aerial'|'mixed'
    "avg_mass_kg"         REAL,   -- typical adult mass in kg
    "avg_height_m"        REAL,   -- typical adult height/length in metres
    "lifespan_years"      REAL,   -- natural lifespan without medical intervention

    -- Environmental tolerances (comfortable ranges; outside = survival penalty)
    "temp_min_k"          REAL,   -- lower comfort threshold K
    "temp_max_k"          REAL,   -- upper comfort threshold K
    "pressure_min_atm"    REAL,   -- minimum survivable atmospheric pressure
    "pressure_max_atm"    REAL,   -- maximum survivable atmospheric pressure
    "atm_req"             TEXT,   -- required atmosphere composition: 'n2o2'|'co2'|'methane'|'any'|'vacuum'

    -- Diet and metabolism
    "diet_type"           TEXT,   -- 'herbivore'|'carnivore'|'omnivore'|'detritivore'|'chemotroph'|'phototroph'|'parasitic'
    "diet_flexibility"    REAL,   -- 0.0–1.0; 0=extreme specialist, 1=can eat almost anything
    "metabolic_rate"      TEXT,   -- 'low'|'medium'|'high'|'variable' (affects resource consumption per capita)

    -- Reproduction
    "repro_strategy"      TEXT,   -- 'r_strategist'|'k_strategist' (r=many offspring/low care, K=few/high care)
    "gestation_years"     REAL,   -- pregnancy/incubation duration in years
    "maturity_years"      REAL,   -- years from birth to reproductive maturity
    "offspring_per_cycle" REAL,   -- average number per reproductive event (can be fractional for probability)
    "repro_cycles_per_life" REAL, -- typical number of reproductive events in a lifespan

    -- Gaming: behavioural disposition
    -- All 0.0–1.0 scales; 0 = minimum, 1 = maximum of that trait
    "risk_appetite"       REAL,   -- 0=extreme risk-averse, 1=reckless; drives expansion and war decisions
    "aggression"          REAL,   -- 0=pacifist, 1=highly aggressive toward outgroup; affects conflict initiation
    "expansionism"        REAL,   -- 0=isolationist, 1=compulsive colonisers; resource pressure multiplier
    "xenophilia"          REAL,   -- 0=deeply xenophobic, 1=welcoming; affects trade and diplomacy chances
    "adaptability"        REAL,   -- 0=rigid/traditional, 1=highly flexible; rate of doctrine and tech adoption

    -- Gaming: social cohesion and fracture risk
    "social_cohesion"     REAL,   -- 0=atomised individualism, 1=near-hive unity; baseline fracture resistance
    "hierarchy_tolerance" REAL,   -- 0=intensely egalitarian, 1=accepts extreme hierarchy; affects governance stability
    "faction_tendency"    REAL,   -- 0=monolithic, 1=naturally schismatic; rate at which sub-factions form
    "grievance_memory"    REAL    -- 0=short memory, 1=perpetual grudge-holders; affects conflict re-ignition risk
);
```

---

## Field Notes

### Physical

**`body_plan`** — affects what environments a species can exploit and what
infrastructure they need.  Radial and colonial plans are rare but possible for
truly alien sophonts.

**`avg_mass_kg` / `avg_height_m`** — used to scale resource consumption per
capita.  A 200 kg K-strategist eats more per individual than a 2 kg r-strategist
even at lower population.

**`lifespan_years`** — combined with `maturity_years` and `gestation_years`
gives the effective generational cycle.  Long-lived K-strategists (lifespans of
centuries) will have very different population dynamics from short-lived
r-strategists.

### Environmental tolerances

`temp_min_k` / `temp_max_k` — compared against `BodyMutable.surface_temp_k` to
determine whether a world is colonisable without life support.

`atm_req` — compared against `BodyMutable.atm_composition`.  A species requiring
`'n2o2'` needs a breathable nitrogen-oxygen mix; `'any'` means the species uses
sealed suits or has evolved to exploit multiple chemistries; `'vacuum'` is a
species that has adapted to hard vacuum (exotic edge case).

### Diet

**`diet_flexibility`** — a carnivore with flexibility 0.9 can survive on
synthesised food or extreme dietary substitution; one at 0.1 requires fresh prey
of specific biochemistry and will starve on an alien ecosystem without food
imports.  This becomes important for colony viability calculations.

**`metabolic_rate`** — scales per-capita resource draw in the economic model.
`'variable'` species (e.g. hibernators or estivators) have lower consumption
during certain game phases.

### Reproduction

**r vs K strategy** — `'r_strategist'` species recover from population collapse
quickly but consume resources explosively when unchecked.  `'k_strategist'`
species are resilient to slow decline but cannot bounce back from sudden
catastrophe quickly.  Both are playable; they create different gameplay dynamics
under war and plague events.

**Derived: population growth rate** — computed from `gestation_years ×
repro_cycles_per_life × offspring_per_cycle / maturity_years`, not stored.
The simulation advances population each tick using this rate plus environment and
social modifiers.

### Gaming behaviour factors

All four disposition fields (`risk_appetite`, `aggression`, `expansionism`,
`xenophilia`) use independent 0–1 scales rather than a shared "personality axis"
so that unusual combinations (e.g. aggressive but xenophilic traders, pacific but
compulsive expansionists) are representable.

**`adaptability`** — a low-adaptability species takes longer to adopt new
technologies or change military doctrine after a defeat.  High adaptability
species can pivot quickly but may also abandon traditions that provided cohesion.

**`risk_appetite`** — separates from `aggression`.  A high-risk-appetite species
might take reckless military gambles or invest badly; a low-risk species will
avoid war even when it has military advantage.

### Social fracture risk

**`social_cohesion`** — the baseline resistance to the empire/polity splitting.
Modified at runtime by grievances, inequality, and war exhaustion.

**`hierarchy_tolerance`** — interacts with governance type (future table).
A low-hierarchy species under an autocratic government accumulates fracture
pressure faster than one at 0.9.

**`faction_tendency`** — rate at which sub-factions form even under stable
conditions.  A high-faction-tendency species will naturally produce trade guilds,
religious movements, and political parties that can become separatist under
pressure.

**`grievance_memory`** — affects how long occupation, atrocity, or economic
exploitation continues to generate fracture pressure after the inciting event
ends.  A 1.0 species never forgives; a 0.0 species returns to baseline
cohesion quickly.

---

## Generation Notes

When generating sophont species procedurally (`generate_species.py` — future):

- Draw homeworld from existing `SophontPresence` rows with `origin='native'`
  and domain `'sophont'` where `species_id IS NULL`, then assign the new ID back.
- Physical traits are seeded from homeworld `surface_temp_k`, `surface_gravity`,
  `atm_composition`, and `hydrosphere` — a heavy-gravity world produces denser,
  lower-profile species; a high-temperature world narrows `temp_max_k` room.
- Environmental tolerances are centred on homeworld conditions with ±σ drawn
  from a species-type distribution.
- Gaming traits are drawn independently and uniformly from [0.1, 0.9] — extremes
  (0.0 or 1.0) are reserved for hand-authored species.
- The ~6 sophont species in the simulation will be hand-authored for the initial
  dataset; procedural generation supports future expansion.

---

## Open Questions

- [ ] Should subspecies / geneered variants be a child table of Species, or a
  separate `SpeciesVariant` table?  Deferred until civilisation mechanics are
  clearer.
- [ ] `avg_mass_kg` for non-bilateral body plans may be ill-defined — revisit
  when first exotic sophont is authored.
- [ ] Should `atm_req` be a FK to a controlled vocabulary table, or is the tag
  string sufficient?  For ~6 species, tag is fine.
- [ ] New vocab terms introduced by hand-authored species need to be finalised
  before schema implementation: `metabolic_rate='very_high'` (Vaelkhi),
  `diet_type='parasite'` (Nhaveth), `atm_req='aquatic'` (Nakhavi),
  `atm_req='reducing'` (Kreeth), `body_plan='vermiform'` / `'draconic'` /
  `'centauroid'` / `'cephalopod'` / `'avian'`, `locomotion='hexapedal'` /
  `'jet_aquatic'` / `'winged_flight'` / `'arboreal'` / `'vermiform'`.
- [ ] **Tech tree design needed (future spec).** Species requirements must be
  factored in at design time — do not design the tech tree without revisiting
  this file.  Key constraints to carry forward:
    - `body_plan` + `locomotion` constrain buildable infrastructure (Nakhavi
      cannot build surface cities; Kraathi require open-volume architecture;
      Nhaveth tools are sized for Kethara-scale manipulators).
    - `atm_req` + environmental tolerances determine which worlds a tech tier
      can be deployed on without life-support overhead cost.
    - `adaptability` should gate the rate of advancement through tech tiers.
    - `diet_type` + `diet_flexibility` affect agricultural and food-production
      tech branch requirements.
    - `repro_strategy` + `maturity_years` affect population recovery time after
      a tech-destroying war event, which interacts with which tiers can be
      rebuilt quickly.

---

## Dependencies

- `Bodies` and `BodyMutable` must exist (homeworld reference and environmental
  match).
- `Biosphere` and `SophontPresence` gate on `species_id` — implement Species
  first, then those tables can have their FKs filled.

---

## Hand-Authored Species

Reference data rows for hand-authored sophont species.  All are sourced from
fiction with values reasoned from established lore.  `homeworld_body_id` is NULL
until the homeworld body is seeded in the database.

**Note:** Caste systems (e.g. Moties) are deferred — the `Species` table
represents species-level averages.  A `SpeciesCaste` child table is a future
design concern.

**Serial-number policy:** Species derived from copyrighted fiction use a filed-off
in-game `name` stored in the DB and all generated output.  The source attribution
is preserved in spec prose only.  Species marked *(original)* have no source.

### Species Index

| # | Game name (`name`) | Source | Notes |
|---|---|---|---|
| 1 | `Kreeth` | Arachnid — *Starship Troopers* (Heinlein) | Eusocial insectoid; hive-dependent |
| 2 | `Vashori` | Osirian — *Viagens Interplanetarias* (de Camp) | Emotional reptiloid diplomats |
| 3 | `Kraathi` | K'Kree — *Traveller* (GDW/Miller) | Obligate herbivore centauroids; G'naak crusade |
| 4 | `Nakhavi` | Octopod — *Children of Ruin* (Tchaikovsky) | Cephalopod; distributed cognition; semelparous |
| 5 | `Skharri` | Kzin — *Known Space* (Niven) | Felinoid carnivores; honour culture; scream-and-leap |
| 6 | `Vaelkhi` | Ythrian — *Technic History* (Anderson) | Avian carnivores; choth clan; God of Ythri |
| 7 | `Shekhari` | Cynthian — *Polesotechnic League* (Anderson) | Small arboreal felinoid traders |
| 8 | `Golvhaan` | Wodenite — *Polesotechnic League* (Anderson) | Large draconic herbivore; high-gravity world |
| 9 | `Nhaveth` | *(original)* | Vermiform neural parasites; Kethara hosts |
| 10 | `Vardhek` | Merseian — *Technic History / Flandry Cycle* (Anderson) | Reptiloid empire; the Long View |
| 11 | `Human` | *(real — Homo sapiens)* | Fragmented omnivores; extreme faction tendency; highest adaptability |

---

### Bug / Arachnid *(Starship Troopers — Heinlein)*

> **Serial-number note**: The canonical source names are "Bug" and "Arachnid". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Kreeth**.

The Bugs are the design-space inverse of Moties: maximum social cohesion, near-zero
faction tendency.  Workers and warriors are effectively non-functional sub-units
without Queen direction — hierarchy is neurological, not social, so `hierarchy_tolerance`
is 1.00 and `faction_tendency` near zero.  Strategic decisions (which Brains control)
are methodical and patient; individual units are expendable but the species is not
reckless, so `risk_appetite` is moderate.  Zero diplomatic contact ever attempted —
`xenophilia` is essentially nil.

**Caste note:** Worker/warrior plurality determines species-average physical stats;
Queens are orders of magnitude larger and longer-lived, Brains are fixed.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Kreeth'` | Filed-off in-game designation; source: Arachnid/Bug |
| `body_plan` | `'radial'` | Six-limbed exoskeletal insectoid |
| `locomotion` | `'hexapedal'` | Ground swarm and tunnel networks |
| `avg_mass_kg` | `90.0` | Warrior caste-weighted; worker plurality |
| `avg_height_m` | `1.2` | Low-slung, not erect |
| `lifespan_years` | `12.0` | Worker/warrior caste; Queens orders of magnitude longer |
| `temp_min_k` | `260.0` | Klendathu is cold and harsh |
| `temp_max_k` | `320.0` | |
| `pressure_min_atm` | `0.5` | Exoskeletal; wider pressure tolerance |
| `pressure_max_atm` | `2.5` | |
| `atm_req` | `'reducing'` | Klendathu atmosphere hostile to humans without suits |
| `diet_type` | `'omnivore'` | Tunnel-farm fungi; consume organic material broadly |
| `diet_flexibility` | `0.80` | Efficient converters; whatever the tunnel network produces |
| `metabolic_rate` | `'high'` | Warriors sustain mass battles |
| `repro_strategy` | `'r_strategist'` | Queens produce thousands; classic insect r-selection |
| `gestation_years` | `0.05` | ~3 weeks; implied by larval throughput |
| `maturity_years` | `1.0` | Combat-ready in ~1 year |
| `offspring_per_cycle` | `80.0` | Queen output per cycle |
| `repro_cycles_per_life` | `5.0` | Annual seasons; represents worker generation |
| `risk_appetite` | `0.40` | Units are expendable, not reckless — Brains are methodical |
| `aggression` | `0.95` | Buenos Aires bombardment; zero restraint when territory threatened |
| `expansionism` | `0.90` | Entire novel premise is territorial competition for stellar real estate |
| `xenophilia` | `0.02` | No diplomatic contact attempted; complete incomprehension |
| `adaptability` | `0.55` | Tactical shifts (new unit types, tunnel strategies) but no foreign tech adoption |
| `social_cohesion` | `0.98` | Warriors severed from Queen become non-functional |
| `hierarchy_tolerance` | `1.00` | Hierarchy is neurological, not social |
| `faction_tendency` | `0.02` | Internal factions physiologically impossible |
| `grievance_memory` | `0.85` | Territorial loss triggers persistent strategic response, not just tactical |

---

### Osirian *(Viagens Interplanetarias — L. Sprague de Camp)*

> **Serial-number note**: The canonical source name is "Osirian". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Vashori**.

Bilateral reptiloid bipeds, scaled, oviparous.  They are among the most
diplomatically accessible non-human species humanity encounters — polished
traders and scholars with a long stable civilisation.  "Very acceptable" is
essentially the in-universe diplomatic assessment.

As ectotherms they have a low metabolic rate and strong temperature preferences:
they prefer warmth and become sluggish in the cold.  Long-lived relative to
humans — slow metabolic pace correlates with extended lifespan, common in
reptiloid fiction and biology.

Reproductively: sapient oviparous species tend toward K-selection in fiction —
small clutches of carefully tended eggs rather than mass spawning.  
`repro_strategy` is K but with a reptile flavour: eggs incubated externally,
gestation measured in months.

Disposition profile encodes the "very acceptable" cultural profile directly:
high xenophilia, low aggression, low expansionism.  They are not passive —
they trade hard and remember slights — but confrontation is a last resort.

Crucially, Osirians are **highly emotional and excitable**: quick to enthusiasm,
quick to offence, quick to reconciliation.  This makes them genuinely engaging
diplomatic partners but also volatile — a perceived slight can escalate a
negotiation rapidly before cooling just as fast.  `risk_appetite` is therefore
moderate rather than low (emotional impulsivity overrides cold calculation),
`aggression` ticks up because of hot-tempered flare-ups, `faction_tendency` is
elevated because emotional disagreements fracture groups, and `grievance_memory`
is fairly high because they *feel* slights acutely even when they eventually
forgive.  High `adaptability` correlates with novelty-seeking and excitability.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Vashori'` | Filed-off in-game designation; source: Osirian |
| `body_plan` | `'bilateral'` | Upright bipedal with two manipulator arms; scaled |
| `locomotion` | `'bipedal'` | |
| `avg_mass_kg` | `80.0` | Denser than human average; muscular + scales |
| `avg_height_m` | `1.75` | Roughly human height |
| `lifespan_years` | `120.0` | Ectothermic slow-pace; long-lived |
| `temp_min_k` | `290.0` | Cold-blooded; sluggish below ~17 °C |
| `temp_max_k` | `345.0` | Tolerates warmth humans find uncomfortable |
| `pressure_min_atm` | `0.7` | |
| `pressure_max_atm` | `1.8` | |
| `atm_req` | `'n2o2'` | Breathable-air world; de Camp's inhabited planets are generally accessible |
| `diet_type` | `'carnivore'` | Reptiloid apex; consume animal protein; likely opportunistic |
| `diet_flexibility` | `0.50` | Some flexibility but protein-dependent |
| `metabolic_rate` | `'low'` | Ectothermic — resting consumption minimal |
| `repro_strategy` | `'k_strategist'` | Small clutch of tended eggs; sapient species |
| `gestation_years` | `0.5` | Eggs incubate ~6 months externally |
| `maturity_years` | `18.0` | Slow development correlates with long lifespan |
| `offspring_per_cycle` | `3.0` | Small clutch, high parental investment |
| `repro_cycles_per_life` | `6.0` | ~10-year intervals across adult life |
| `risk_appetite` | `0.60` | Emotional impulsivity; gets swept up in the moment |
| `aggression` | `0.40` | Quick to flare; hot-tempered but not war-seeking; cools rapidly |
| `expansionism` | `0.30` | Stable home civilisation; trade not conquest |
| `xenophilia` | `0.85` | Core of the "very acceptable" designation |
| `adaptability` | `0.70` | Novelty-seeking and excitability drive openness to new ideas |
| `social_cohesion` | `0.70` | Stable multi-generation civilisations; not monolithic |
| `hierarchy_tolerance` | `0.65` | Structured society but with scholarly/merchant meritocratic layer |
| `faction_tendency` | `0.55` | Emotional disagreements fracture groups faster than rational ones |
| `grievance_memory` | `0.70` | Slights felt acutely; eventual forgiveness but never forgotten |

---

### K'Kree *(Traveller — GDW/Marc Miller)*

> **Serial-number note**: The canonical source name is "K'Kree". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Kraathi**.

Large centauroid obligate herbivores.  Six-limbed: four legs for locomotion,
two manipulator arms.  Homeworld Kirur is open plains; K'Kree have profound
claustrophobia in enclosed spaces, which has shaped their entire civilisation
architecture and starship design (vast open interior volumes).

The defining characteristic is **herd-dependency**: a K'Kree cannot function
psychologically in isolation or even small groups.  A diplomat of rank will
travel with their full extended family.  No K'Kree ever travels alone if they
can help it.  `social_cohesion` is therefore near-maximum — not enforced
hierarchy but biological necessity.

The second defining characteristic is the **G'naak crusade**: K'Kree consider
carnivores ("eaters of the dead") a moral abomination.  Their stated
civilisational goal is the extermination of all carnivorous sophonts in the
galaxy, and they have prosecuted this as a military program across the Two
Thousand Worlds.  This drives high `expansionism` and high `aggression` despite
being technically herbivores; `xenophilia` is near-zero because the answer to
"do you eat meat?" determines whether you are a trading partner or a target.

Rigid dominant-male hierarchy within herds.  Extremely conservative; ancient
traditions are maintained unchanged.  Low `adaptability`.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Kraathi'` | Filed-off in-game designation; source: K'Kree |
| `body_plan` | `'centauroid'` | Four legs, two manipulator arms, upright humanoid torso |
| `locomotion` | `'quadrupedal'` | Lower body is the primary locomotion unit |
| `avg_mass_kg` | `450.0` | Horse-sized lower body + humanoid upper; large sophont |
| `avg_height_m` | `2.0` | Head height standing |
| `lifespan_years` | `80.0` | |
| `temp_min_k` | `278.0` | Open plains/savanna homeworld; moderate cold tolerance |
| `temp_max_k` | `330.0` | Warm-adapted grazer |
| `pressure_min_atm` | `0.8` | |
| `pressure_max_atm` | `1.5` | |
| `atm_req` | `'n2o2'` | Standard Traveller Major Race convention; oxygen-nitrogen breather |
| `diet_type` | `'herbivore'` | Obligate; eating or handling meat is profound taboo |
| `diet_flexibility` | `0.20` | Extremely narrow; plant matter only; specific biochemical requirements |
| `metabolic_rate` | `'medium'` | Large body with sustained grazing metabolism |
| `repro_strategy` | `'k_strategist'` | Large sophont; low offspring count, high investment |
| `gestation_years` | `0.75` | ~9 months; large-bodied |
| `maturity_years` | `20.0` | |
| `offspring_per_cycle` | `1.0` | Usually singleton |
| `repro_cycles_per_life` | `4.0` | |
| `risk_appetite` | `0.45` | Herd caution moderates individual risk; collective crusade overrides individual fear |
| `aggression` | `0.75` | Peaceful toward herbivores; genocidal toward carnivores — species average is elevated |
| `expansionism` | `0.95` | The G'naak crusade is an existential civilisational program |
| `xenophilia` | `0.10` | Herbivore species: tolerated; carnivore species: extermination target |
| `adaptability` | `0.20` | Deeply conservative; ancient tradition maintained unchanged across millennia |
| `social_cohesion` | `0.95` | Herd-dependency is biological; isolation is psychologically incapacitating |
| `hierarchy_tolerance` | `0.90` | Rigid dominant-male herd hierarchy; unquestioned |
| `faction_tendency` | `0.20` | Herd structure suppresses internal fracture; unity against G'naak further binds |
| `grievance_memory` | `0.90` | The G'naak crusade is itself a species-level inherited grievance; never forgiven |

---

### Octopod *(Children of Ruin — Adrian Tchaikovsky)*

> **Serial-number note**: The canonical source name is "Octopod". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Nakhavi**.

Cephalopod sophonts, technology-uplifted from a wild octopus ancestor on the
ocean world Nod.  Eight manipulator arms with semi-autonomous nervous ganglia —
the arms can problem-solve partially independently of the central brain, giving
Octopods a genuinely distributed cognition that has no mammalian equivalent.
Communication is via chromatophores: full-body skin colour and pattern changes
encoding language across multiple simultaneous channels.  No spoken language.

Short natural lifespan (real octopus: ~1-2 years; uplifted: extended but still
far shorter than most sophonts).  This shapes their entire relationship with
knowledge and continuity — individual memory is finite and brief, so culture
and technical memory are rigorously externalised.  

Baseline octopuses are solitary ambush predators with no social structure at
all.  Uplifting has created social cooperation but it sits on top of very
shallow social instincts.  `social_cohesion` is low not because the species
fractures but because the concept of "group" is alien and costly.  When they do
form collectives they are extremely effective, but it takes active effort.

Identity is fluid: the "This One / We Who Are" dual mode in the novel encodes
a genuine ambiguity between individual and collective self.  `hierarchy_tolerance`
is near zero — solitary predators have no instinct for rank whatsoever.

Intense curiosity and high problem-solving intelligence, combined with
chromatophore input from a bandwidth-rich visual/skin-display environment, makes
`adaptability` and `xenophilia` the two highest disposition values.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Nakhavi'` | Filed-off in-game designation; source: Octopod |
| `body_plan` | `'cephalopod'` | Mantle + eight arms; no rigid skeleton |
| `locomotion` | `'jet_aquatic'` | Jet propulsion primary; arm-walking for fine manipulation |
| `avg_mass_kg` | `12.0` | Larger than wild octopus; still much smaller than mammalian sophonts |
| `avg_height_m` | `0.6` | Mantle height; arm span ~1.5 m |
| `lifespan_years` | `18.0` | Uplifting extended the natural ~1-2 year lifespan significantly |
| `temp_min_k` | `273.0` | Cold oceanic tolerance; prefer temperate to warm |
| `temp_max_k` | `305.0` | Upper oceanic range; heat-sensitive |
| `pressure_min_atm` | `1.0` | Aquatic baseline; surface-capable |
| `pressure_max_atm` | `20.0` | Deep-ocean capable; flexible to depth pressure |
| `atm_req` | `'aquatic'` | Gill-breathing; surface excursions require equipment |
| `diet_type` | `'carnivore'` | Obligate; ambush predator ancestry |
| `diet_flexibility` | `0.45` | Specific prey requirements; limited substrate flexibility |
| `metabolic_rate` | `'high'` | Cephalopod metabolism is rapid; short lifespan partly caused by this |
| `repro_strategy` | `'r_strategist'` | Mass egg-laying; most larvae die; parental death follows spawning |
| `gestation_years` | `0.08` | ~1 month egg incubation |
| `maturity_years` | `2.0` | Reach cognitive maturity quickly given short lifespan |
| `offspring_per_cycle` | `200.0` | Thousands of eggs; massive r-selection; most die before sapience |
| `repro_cycles_per_life` | `1.0` | Single reproductive event followed by death; semelparous |
| `risk_appetite` | `0.80` | Short lifespan + intense curiosity = highly exploratory; little to lose |
| `aggression` | `0.45` | Territorial around den/resources; not warlike at civilisational scale |
| `expansionism` | `0.40` | Curious explorers but no instinct to hold territory at scale |
| `xenophilia` | `0.90` | Intense curiosity is core to the character; new = interesting, not threatening |
| `adaptability` | `0.95` | Distributed cognition + chromatophore learning loop; fastest adapters in the setting |
| `social_cohesion` | `0.25` | Cooperation is culturally constructed over zero social instinct baseline |
| `hierarchy_tolerance` | `0.10` | Solitary predator ancestry; rank is a completely alien concept |
| `faction_tendency` | `0.15` | Groups are hard to form; once formed, tend to stay together rather than split |
| `grievance_memory` | `0.35` | Short individual lifespan limits long-term grudges; externalised culture preserves some |

---

### Kzin *(Known Space — Larry Niven)*

> **Serial-number note**: The canonical source name is "Kzin" (plural: Kzinti). The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Skharri**.

Large felinoid obligate carnivores.  Digitigrade bipeds, tawny-furred,
averaging twice human mass.  One of the most militarily capable and aggressive
species in Known Space — and the most instructive failure mode, having lost
four Man-Kzin Wars against humans by the same mechanism each time: the
"scream and leap" instinct.  Kzinti fight when honour demands it, before
strategy is complete.  High aggression + high risk appetite + moderate
adaptability = a species that is formidable but predictable.

Rigid patriarchal pride structure.  Only males with sufficient honour earn the
right to a name (nameless males are referred to by occupation).  Females are
not regarded as sapient by Kzin culture.  This produces extreme
`hierarchy_tolerance` and moderately high `faction_tendency` — patriarch-led
clans compete bitterly for rank and territory, but within a pride the hierarchy
is absolute.

Territorial expansion is a cultural and biological imperative.  Every Man-Kzin
War started because Kzinti expanded, encountered humans, classified them as
prey, and attacked immediately without diplomatic contact.  `xenophilia` is
near-zero: other species are prey, slaves, or (grudgingly) allies of
convenience.

Honour culture produces very high `grievance_memory` — insults and defeats are
remembered across generations and must eventually be avenged.  This also
interacts with the war-loss pattern: the Patriarchy has not forgotten the Man-
Kzin Wars, even after centuries of occupied treaty.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Skharri'` | Filed-off in-game designation; source: Kzin |
| `body_plan` | `'bilateral'` | Felinoid biped; digitigrade legs, heavy build |
| `locomotion` | `'bipedal'` | Capable of quadrupedal sprint in combat |
| `avg_mass_kg` | `160.0` | ~twice human; large obligate carnivore |
| `avg_height_m` | `2.4` | Tall and powerfully built |
| `lifespan_years` | `200.0` | Long-lived; Niven implies multi-century lifespan |
| `temp_min_k` | `270.0` | Kzinhome analog warm but not tropical; fur provides cold buffer |
| `temp_max_k` | `330.0` | |
| `pressure_min_atm` | `0.7` | |
| `pressure_max_atm` | `1.8` | |
| `atm_req` | `'n2o2'` | Standard Known Space habitable worlds |
| `diet_type` | `'carnivore'` | Obligate; fresh meat strongly preferred; scavenger food is insult |
| `diet_flexibility` | `0.20` | Extremely narrow; live prey preferred culturally and physiologically |
| `metabolic_rate` | `'high'` | Large active predator with frequent combat demands |
| `repro_strategy` | `'k_strategist'` | Large sophont; small litters, high investment |
| `gestation_years` | `0.6` | |
| `maturity_years` | `15.0` | |
| `offspring_per_cycle` | `2.0` | Small litter |
| `repro_cycles_per_life` | `8.0` | Long-lived; multiple litters across centuries |
| `risk_appetite` | `0.90` | "Scream and leap" — honour demands attack before analysis |
| `aggression` | `0.95` | Defines the species; four wars started by pure aggression instinct |
| `expansionism` | `0.90` | Territorial conquest is cultural and biological imperative |
| `xenophilia` | `0.05` | Other species are prey or slaves; diplomacy is a temporary humiliation |
| `adaptability` | `0.45` | Tradition-bound honour culture resists change; tactics improve slowly after defeats |
| `social_cohesion` | `0.80` | Pride loyalty is fierce; would die for patriarch and family unit |
| `hierarchy_tolerance` | `0.95` | Absolute patriarch authority; rank is everything; nameless males have no standing |
| `faction_tendency` | `0.65` | Clans compete viciously for rank and territory; inter-pride rivalry is constant |
| `grievance_memory` | `0.95` | Honour culture; defeats and insults must be avenged; centuries-long memory |

---

### Nhaveth *(original — neural parasite)*

Vermiform neural parasites.  In natural form: ~0.6 m, ~1.5 kg, limbless,
with a recessed manipulator fringe for micro-tasks.  They evolved alongside
a sub-sapient hominid species — the **Kethara** — on the same homeworld, making
the parasitic relationship ancient and co-evolved.  Kethara are large (110 kg),
strong, durable, and have a suppressed flight response as a co-evolutionary
adaptation to millennia of parasitic pressure.  Kethara are not sapient; they
have no Species row.  Adult Nhaveth larvae must parasitize a Kethara host to
complete neural maturation.

**Operational form**: a parasitised Kethara, fully controlled by the Nhaveth
neural web.  The parasite's intelligence directs all behaviour.  The host
provides locomotion, manipulation, and respiration; the parasite provides
cognition.  Physical interactions with other species (diplomacy, labour,
combat) are always conducted via host.

**Natural-form physical stats** below describe the parasite organism.  For
`avg_mass_kg`, `avg_height_m`, and locomotion: operators should join to host
body stats for field-relevant encounter values.

**Social structure**: factions ("courts") controlled by a dominant Nhaveth whose
host displays court insignia.  Courts war on each other almost constantly for
territory and for access to Kethara populations (more hosts = more expansion
capacity).  No court has ever unified the species — low social cohesion between
courts, absolute hierarchy within.  This makes `faction_tendency` very high and
`social_cohesion` low: the species is fractured at civilisational scale but
tyrannical within each faction.

Lifespan is vastly extended by host transfer — a mature Nhaveth can move to a
fresh young host when the current one ages.  Effective lifespan measured in
centuries.  Combined with near-total `grievance_memory`, every Nhaveth carries
first-hand memory of ancient betrayals.

Larvae are released in clutches of 50-100; most parasitize Kethara sub-adults
and either die in incompatible hosts or survive to maturation.  Effective
reproductive rate is low despite r-strategy numbers.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Nhaveth'` | |
| `body_plan` | `'vermiform'` | Limbless in natural form; manipulator fringe for micro-tasks |
| `locomotion` | `'vermiform'` | Sinusoidal crawl in natural form; host locomotion in operation |
| `avg_mass_kg` | `1.5` | Natural form; operational mass ~110 kg via Kethara host |
| `avg_height_m` | `0.6` | Natural form length; operational height ~1.85 m via host |
| `lifespan_years` | `600.0` | Effective lifespan via sequential host transfer |
| `temp_min_k` | `280.0` | Parasite is metabolically fragile outside a host |
| `temp_max_k` | `320.0` | Narrow thermal tolerance without host thermoregulation |
| `pressure_min_atm` | `0.8` | |
| `pressure_max_atm` | `1.6` | |
| `atm_req` | `'n2o2'` | Co-evolved with Kethara on a standard habitable world |
| `diet_type` | `'parasite'` | Absorbs nutrients entirely from host bloodstream |
| `diet_flexibility` | `0.30` | Dependent on specific host biochemistry; Kethara-optimised |
| `metabolic_rate` | `'low'` | Parasite at rest; delegates all metabolic work to host |
| `repro_strategy` | `'r_strategist'` | Mass larval release; most larvae die in incompatible hosts |
| `gestation_years` | `0.1` | Rapid internal development before larval release |
| `maturity_years` | `5.0` | Larvae spend 5 years in a juvenile Kethara before neural maturation |
| `offspring_per_cycle` | `75.0` | Large clutch; high larval mortality |
| `repro_cycles_per_life` | `3.0` | Reproductive events spaced across centuries; rare and costly |
| `risk_appetite` | `0.55` | Cautious with their own life (irreplaceable cognition); reckless with hosts (replaceable) |
| `aggression` | `0.85` | Inter-court warfare is constant; subjugation of non-parasitic species routine |
| `expansionism` | `0.90` | Host population access drives territorial imperative |
| `xenophilia` | `0.08` | All non-Nhaveth species are either host-stock, labour, or threats |
| `adaptability` | `0.40` | Ancient species; traditions and court protocols calcified over centuries |
| `social_cohesion` | `0.25` | Civilisation-scale fracture into warring courts; no stable pan-species unity |
| `hierarchy_tolerance` | `0.95` | Absolute within a court; the dominant Nhaveth's word is physically enforced |
| `faction_tendency` | `0.90` | Court schisms are the dominant mode of Nhaveth history |
| `grievance_memory` | `1.00` | Six-century lifespan means first-hand memory of every betrayal; nothing is ever forgotten |

---

### Ythrian *(Technic History / Flandry Cycle — Poul Anderson)*

> **Serial-number note**: The canonical source name is "Ythrian". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Vaelkhi**.

Large avian carnivores native to Ythri, a world of slightly lower gravity than
Earth.  Wings are primary locomotion — Ythrians are uncomfortable and slow on
the ground.  The wing structure includes a hand-claw at the leading edge
(alula), giving limited ground manipulation; true fine motor work is done with
the hindlimb talons.  Hollow bones, high-efficiency respiratory system, and a
vastly accelerated metabolism enable powered flight at Ythrian mass.

Social unit is the **choth** — an extended clan of ~50-300 individuals sharing
territory.  The choth has a wyvan (elected leader) but individual autonomy
within it is strongly protected.  Leaving a choth is legal and not uncommon;
the decision is simply permanent and defines you forever.  This creates a
social structure that is loyal but not imprisoning — high cohesion within the
in-group, but not totalitarian.

The **God of Ythri** is a death-deity associated with the hunt, the sky, and
the moment of the kill.  Dying in the hunt or in honourable battle is the
preferred death; dying of illness or age is a mild shame.  This does not make
Ythrians reckless — the God respects skill and patience as much as courage —
but it raises risk appetite markedly above baseline.

They are not expansionist conquerors; they joined the Terran Empire reluctantly
and on negotiated terms after *The People of the Wind*, and their civilisational
drive is to maintain Ythrian space and culture, not to absorb others.
`xenophilia` is moderate — they deal pragmatically with humans and others but
prefer Ythrian company and Ythrian ways.

Key contrast with Kzinti: similar hunt-culture and honour system, but Ythrians
are patient, tactical, and not prone to the "scream and leap" failure mode.
`aggression` and `risk_appetite` are lower; `adaptability` and `hierarchy_tolerance`
reflect the elected-wyvan/individual-autonomy structure.

**Note on physical stats**: natural form describes the flight-capable organism.
`avg_height_m` is standing-crouch on ground; wingspan ~4 m.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Vaelkhi'` | Filed-off in-game designation; source: Ythrian |
| `body_plan` | `'avian'` | Wings primary; hindlimb talons for manipulation and perching |
| `locomotion` | `'winged_flight'` | Powered flight primary; ground movement awkward |
| `avg_mass_kg` | `50.0` | Large avian; hollow bones; low gravity homeworld |
| `avg_height_m` | `1.3` | Standing crouch on ground; wingspan ~4 m |
| `lifespan_years` | `80.0` | Roughly human-equivalent |
| `temp_min_k` | `265.0` | Flight-altitude cold tolerance; homeworld temperate |
| `temp_max_k` | `320.0` | |
| `pressure_min_atm` | `0.5` | High-altitude flight requires lower pressure tolerance |
| `pressure_max_atm` | `1.4` | |
| `atm_req` | `'n2o2'` | Standard Technic History habitable worlds |
| `diet_type` | `'carnivore'` | Obligate aerial hunt predator |
| `diet_flexibility` | `0.25` | Strong prey preferences; cultural taboo against eating non-hunted food |
| `metabolic_rate` | `'very_high'` | Powered flight demands enormous continuous energy; eat frequently |
| `repro_strategy` | `'k_strategist'` | Clutch of 2-3 eggs; intensive parental care through fledgling stage |
| `gestation_years` | `0.3` | Egg incubation ~3.5 months |
| `maturity_years` | `16.0` | Long juvenile flight-training period |
| `offspring_per_cycle` | `2.0` | Small clutch; high investment |
| `repro_cycles_per_life` | `5.0` | |
| `risk_appetite` | `0.70` | Hunt culture + God of Ythri; death in the sky is glorious — but skill, not recklessness |
| `aggression` | `0.55` | Fierce defenders; not proactive aggressors; choth raids exist but not conquest drives |
| `expansionism` | `0.30` | Defend Ythrian space; no drive to absorb others' worlds |
| `xenophilia` | `0.45` | Pragmatic dealmakers with other species; prefer Ythrian company |
| `adaptability` | `0.55` | Strong tradition; capable of change when the choth decides it |
| `social_cohesion` | `0.70` | Choth loyalty fierce; individual autonomy respected within it |
| `hierarchy_tolerance` | `0.50` | Elected wyvan, not absolute ruler; individual can leave or challenge |
| `faction_tendency` | `0.45` | Choth-vs-choth tension common; rarely escalates to civilisational fracture |
| `grievance_memory` | `0.65` | Honour memory; wrongs against the choth remembered; not quite as absolute as Kzinti |

---

### Cynthian *(Polesotechnic League / Muddlin' Through — Poul Anderson)*

> **Serial-number note**: The canonical source name is "Cynthian". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Shekhari**.

Small arboreal felinoids from Cynthia.  Quick, agile climbers with a
prehensile tail; capable of bipedal or quadrupedal movement.  About the size
of a large cat standing — deceptive, since Cynthians are extremely capable and
intensely aware that most species underestimate them on first contact, which
they consider a usable advantage.

Chee Lan on the Muddlin' Through is the exemplar: mercenary, fiercely
self-interested, sharp-tongued, and entirely comfortable operating in alien
cultures so long as there is profit in it.  The species as a whole tends
toward individualism, trade, and calculated risk-taking.  They are not
warmly xenophilic — *interested* in aliens as counterparties, not as friends.

Socially: no strong herd or choth equivalent.  Family units but high individual
mobility.  `faction_tendency` is low because Cynthians tend to defect from
groups rather than fracture them — loyalty is rented, not given.
`social_cohesion` reflects a species that cooperates readily when incentives
align but has no strong instinct toward group solidarity.

Aggression is moderate: Cynthians will fight efficiently and without hesitation
when threatened, but do not pick fights for honour — that would be expensive.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Shekhari'` | Filed-off in-game designation; source: Cynthian |
| `body_plan` | `'bilateral'` | Small felinoid; prehensile tail; four limbs plus tail |
| `locomotion` | `'arboreal'` | Quadrupedal/bipedal; climber; fast and agile |
| `avg_mass_kg` | `10.0` | Cat-sized sophont |
| `avg_height_m` | `0.55` | Standing bipedal; most interaction done at waist height of larger species |
| `lifespan_years` | `90.0` | Roughly human-scaled |
| `temp_min_k` | `268.0` | Furred; moderate cold tolerance |
| `temp_max_k` | `318.0` | |
| `pressure_min_atm` | `0.7` | |
| `pressure_max_atm` | `1.6` | |
| `atm_req` | `'n2o2'` | |
| `diet_type` | `'omnivore'` | Arboreal opportunist ancestry; eats widely |
| `diet_flexibility` | `0.75` | Wide dietary range; useful for long trading voyages |
| `metabolic_rate` | `'high'` | Small fast animal; burns energy quickly |
| `repro_strategy` | `'k_strategist'` | Sapient; small litter, high investment |
| `gestation_years` | `0.25` | |
| `maturity_years` | `12.0` | |
| `offspring_per_cycle` | `2.0` | |
| `repro_cycles_per_life` | `6.0` | |
| `risk_appetite` | `0.75` | Calculated risk for profit; trading ventures into the unknown are routine |
| `aggression` | `0.45` | Will fight efficiently; does not pick fights; aggression is a cost |
| `expansionism` | `0.55` | Trade routes, not empire; but persistent and geographically wide-ranging |
| `xenophilia` | `0.55` | Interested in aliens as counterparties; not warmly curious; profit-first |
| `adaptability` | `0.85` | Operates fluidly in alien contexts; excellent at reading a room |
| `social_cohesion` | `0.40` | Cooperative when incentives align; no deep solidarity instinct |
| `hierarchy_tolerance` | `0.35` | Individualist; tolerates structure when it pays; resents it otherwise |
| `faction_tendency` | `0.25` | Defects from groups rather than fractures them; loyalty is rented |
| `grievance_memory` | `0.55` | Remembers who cheated them; eventually prices it in rather than pursuing vengeance |

---

### Wodenite *(Polesotechnic League / Muddlin' Through — Poul Anderson)*

> **Serial-number note**: The canonical source name is "Wodenite". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Golvhaan**.

Large draconic centauroids from Woden, a high-gravity world.  Four sturdy
legs supporting a massive body, humanoid upper torso with two arms, long
neck, scaled hide.  Woden's higher gravity produces a denser, more
heavily-built physique than similarly-massed species on standard-gravity worlds.

Adzel is the exemplar and a genuine outlier within his own species — his
Buddhism and pacifism are personal philosophy, not species average.  Wodenites
generally are **calm, patient, and deliberate** rather than deeply non-violent:
they simply have no aggression hair-trigger.  A Wodenite enraged is a serious
problem; they just rarely get enraged because they have the size and confidence
not to feel threatened.

Omnivorous and highly adaptable dietarily — Woden's ecology is varied and
Wodenites eat almost everything organic.  Their sheer size means they need
enormous caloric throughput but are not picky about the source.

Socially: Wodenites have a clan/extended-family structure but individuals range
widely.  They integrate easily into multi-species environments.  `xenophilia`
is genuinely high — Wodenites find other species interesting in a relaxed,
curious way that has nothing to do with profit or threat assessment.

`hierarchy_tolerance` is moderate: they respect earned authority but are
difficult to bully.  Hard to intimidate when you mass 700 kg.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Golvhaan'` | Filed-off in-game designation; source: Wodenite |
| `body_plan` | `'draconic'` | Four legs, two arms, long neck, scaled; centauroid-draconic |
| `locomotion` | `'quadrupedal'` | Lower body primary locomotion; upper torso for manipulation |
| `avg_mass_kg` | `700.0` | High-gravity world; very dense and heavy |
| `avg_height_m` | `2.2` | Upper torso standing height; ground-to-spine ~1.6 m |
| `lifespan_years` | `150.0` | Long-lived; large body, slow metabolism |
| `temp_min_k` | `270.0` | |
| `temp_max_k` | `325.0` | |
| `pressure_min_atm` | `0.8` | Woden is higher-gravity; probably higher pressure baseline |
| `pressure_max_atm` | `2.5` | Dense-body tolerance to pressure |
| `atm_req` | `'n2o2'` | Polesotechnic League baseline |
| `diet_type` | `'omnivore'` | Eats almost anything organic; no strong preferences |
| `diet_flexibility` | `0.90` | Extremely wide; useful crewmember on long voyages |
| `metabolic_rate` | `'medium'` | Large body; high total throughput but low mass-specific rate |
| `repro_strategy` | `'k_strategist'` | Large long-lived sophont; low offspring count |
| `gestation_years` | `1.0` | |
| `maturity_years` | `25.0` | |
| `offspring_per_cycle` | `1.0` | Singleton births |
| `repro_cycles_per_life` | `5.0` | Long inter-birth intervals |
| `risk_appetite` | `0.45` | Patient, deliberate; not reckless; will act boldly when needed |
| `aggression` | `0.30` | Rarely provoked; difficult to threaten something that size; not a warlike species |
| `expansionism` | `0.35` | Wide-ranging individually; no civilisational conquest drive |
| `xenophilia` | `0.80` | Genuinely curious about other species; relaxed and open |
| `adaptability` | `0.65` | Integrates well into alien environments; tradition not rigid |
| `social_cohesion` | `0.55` | Clan loyalty present but not overwhelming; individual ranging common |
| `hierarchy_tolerance` | `0.50` | Respects earned authority; immune to intimidation by virtue of size |
| `faction_tendency` | `0.30` | Low internal fracture tendency; disagreements settled slowly and verbally |
| `grievance_memory` | `0.40` | Patient and forgiving; long lifespan dilutes short-term grievances |

---

### Merseian *(Technic History / Flandry Cycle — Poul Anderson)*

> **Serial-number note**: The canonical source name is "Merseian". The `name`
> field in the table below and in all generated database rows, histories, and
> simulation output uses the filed-off designation **Vardhek**.  This section
> preserves the full design rationale under the source name for reference.

Large reptiloid-amphibioid bipeds from Merseia.  Green-scaled, tailed, heavy-
set.  Slightly larger and denser than humans on a marginally higher-gravity
world.  Physiologically they can breed faster than their culture usually
permits — the Roidhunate deliberately regulates reproduction as a political
instrument.

The defining characteristic is **the Long View** (Gethfennu): Merseians think
in generational timescales.  A political program that will bear fruit in 300
years is a sensible plan, not an abstraction.  This makes them extraordinarily
dangerous antagonists — patient, methodical, and willing to invest enormous
resources in long-horizon subversion that humans rarely recognise until too
late.

The **Roidhunate** is a hierarchical imperial structure headed by the
Roidhun (War-lord).  Rank is earned through demonstrated competence and
service; the system has a meritocratic layer within its aristocracy.  
`hierarchy_tolerance` is very high but not absolute — a Roidhun who fails the
Long View can be replaced.

Inter-clan rivalries exist within the Roidhunate but are suppressed in favour of
species-level competition against other sophonts, principally humans.  The
Merseian project is long-term galactic dominance; all internal politics are
subordinated to that goal.  This gives a species-level `social_cohesion` much
higher than their internal clan tensions would suggest.

`xenophilia` is low but not zero — Merseians study alien species intensely,
recruit alien agents, and form alliances of convenience.  This is instrumental
curiosity in service of the Long View, not genuine openness.

`adaptability` is high for a tradition-bound empire because the Long View
*requires* strategic flexibility — the tactics change across centuries while
the goal stays fixed.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Vardhek'` | Filed-off in-game designation; source: Merseian |
| `body_plan` | `'bilateral'` | Reptiloid-amphibioid biped; tailed; scaled |
| `locomotion` | `'bipedal'` | |
| `avg_mass_kg` | `110.0` | Larger and denser than human baseline; higher-gravity world |
| `avg_height_m` | `2.1` | Tall; tail adds ~0.9 m beyond standing height |
| `lifespan_years` | `110.0` | Somewhat longer than human |
| `temp_min_k` | `275.0` | Amphibioid ancestry; prefer warm-temperate to warm |
| `temp_max_k` | `330.0` | |
| `pressure_min_atm` | `0.8` | |
| `pressure_max_atm` | `2.0` | |
| `atm_req` | `'n2o2'` | Standard Technic History baseline |
| `diet_type` | `'omnivore'` | Amphibioid ancestry; wide dietary range |
| `diet_flexibility` | `0.65` | |
| `metabolic_rate` | `'medium'` | |
| `repro_strategy` | `'k_strategist'` | Culturally regulated reproduction; Roidhunate controls population as policy |
| `gestation_years` | `0.7` | |
| `maturity_years` | `20.0` | |
| `offspring_per_cycle` | `2.0` | Biologically capable of more; culturally restricted |
| `repro_cycles_per_life` | `5.0` | |
| `risk_appetite` | `0.35` | The Long View suppresses short-term risk impulse; patience is doctrine |
| `aggression` | `0.70` | Fundamentally competitive and expansionist; not impulsive but relentless |
| `expansionism` | `0.95` | Species-level goal is galactic dominance; the entire Roidhunate exists to prosecute this |
| `xenophilia` | `0.20` | Studies aliens instrumentally; recruits alien agents; no genuine openness |
| `adaptability` | `0.75` | Long View requires tactical flexibility across centuries; strategy fixed, methods fluid |
| `social_cohesion` | `0.85` | Internal clan tensions suppressed by species-level competitive program |
| `hierarchy_tolerance` | `0.88` | Roidhunate rank system; meritocratic layer within aristocracy; not purely absolute |
| `faction_tendency` | `0.35` | Clan rivalry exists but systemically subordinated to Roidhunate unity |
| `grievance_memory` | `0.85` | Long View includes long grievance; territorial losses are items on a centuries-long accounting ledger |

---

### Human *(Homo sapiens — real)*

> **Serial-number note**: No filing required.  Humans are real.  The in-game
> `name` field uses `'Human'` directly.  Sol is seeded manually via `seed_sol.py`
> and Earth (`homeworld_body_id`) is populated from the canonical Bodies row.

Bilaterally symmetrical, bipedal, endothermic omnivores.  Average mass and
height among the hand-authored species; moderate lifespan; no unusual physical
capabilities.  The defining trait of humans in this simulation is not biological
but political: **they are the most internally fragmented starting civilisation
in the catalogue**.

Every other species enters the simulation with some unifying principle —
neurological hierarchy (Kreeth), species-level competitive programme (Vardhek),
herd-dependency (Kraathi), distributed consensus (Nakhavi).  Humans have none.
They start with contested borders, competing ideologies, and incompatible
definitions of legitimate authority.  `social_cohesion` is the lowest of any
starting species; `faction_tendency` is the highest.  The simulation question for
humans is not *when* they fracture but *how many polities did they field at tick 1*.

`adaptability` is the highest of all species.  Humans reverse-engineer, copy,
iterate, and discard doctrine with a speed that compensates for their
fragmentation — a human polity that survives its own internal competition emerges
lean and technically aggressive.  The selective pressure of inter-human conflict
accelerates tech adoption where other species might stagnate.

`expansionism` is high and structurally reinforced: competing polities each
independently face resource pressure and each independently model expansion as
the solution.  This produces a species-level push into space that does not require
coordinated intent — it is the aggregate output of multiple groups each trying
to outrun the others.

`xenophilia` is genuinely variable.  The species average is moderate; individual
polities range from actively hostile to genuinely curious.  This creates
inconsistent first-contact outcomes — a species-level diplomatic profile is
almost meaningless for humans.  An alien civilisation encountering humans for
the first time may receive three different responses from three different
human polities simultaneously.

The short lifespan and fast generational turnover (relative to Vardhek,
Golvhaan, or Vashori) means human cultural memory is shallow and doctrines
rotate quickly.  Grievances that persist across decades tend to be institutional
rather than personal — embedded in states and religions rather than individual
recall.  `grievance_memory` is moderate as a result: humans remember, but
imprecisely and selectively.

**Simulation trigger:** The `faction_tendency` value means a unified-humanity
starting scenario is mechanically implausible.  At initialisation, human
presence should be seeded as multiple independent polities sharing Sol and
possibly a handful of early colony systems, already in political competition.
The first inter-human war is a likely early-simulation event, not an edge case.

| Field | Value | Notes |
|---|---|---|
| `name` | `'Human'` | No filing required; real species |
| `body_plan` | `'bilateral'` | Standard upright biped; two arms, two legs |
| `locomotion` | `'bipedal'` | |
| `avg_mass_kg` | `70.0` | Species-average adult; sex dimorphism present but moderate |
| `avg_height_m` | `1.75` | |
| `lifespan_years` | `80.0` | Pre-medical-intervention baseline; relatively short among starting species |
| `temp_min_k` | `283.0` | Comfortable from ~10 °C; cold tolerance extended by clothing/tech |
| `temp_max_k` | `313.0` | Upper comfort ~40 °C; heat stress beyond this |
| `pressure_min_atm` | `0.5` | Altitude tolerance; low-pressure survivable short-term without suit |
| `pressure_max_atm` | `2.0` | |
| `atm_req` | `'n2o2'` | Nitrogen-oxygen breathable mix required |
| `diet_type` | `'omnivore'` | Extremely broad dietary range across evolutionary history |
| `diet_flexibility` | `0.85` | Adapts readily to local biochemistries; historically colonised extreme environments |
| `metabolic_rate` | `'medium'` | |
| `repro_strategy` | `'k_strategist'` | Low offspring count; high parental investment; sapient |
| `gestation_years` | `0.75` | ~9 months |
| `maturity_years` | `16.0` | Biological maturity; social maturity often later |
| `offspring_per_cycle` | `1.0` | Singletons typical; twins ~3% |
| `repro_cycles_per_life` | `20.0` | Potential; cultural and economic factors reduce actual rate |
| `risk_appetite` | `0.65` | Historically exploratory and commercially speculative; accepts high-variance outcomes |
| `aggression` | `0.55` | Inter-group conflict is endemic in the historical record; not a warlike species biologically but socially primed |
| `expansionism` | `0.80` | Competing polities independently pursue expansion; aggregate pressure is very high |
| `xenophilia` | `0.50` | Species average obscures extreme polity-level variance; some factions genuinely curious, others xenophobic |
| `adaptability` | `0.90` | Fastest technology adoption and doctrine iteration of all starting species |
| `social_cohesion` | `0.25` | Lowest of any starting species; no unifying biological or ideological principle at species level |
| `hierarchy_tolerance` | `0.45` | Highly variable by polity; species average masks the full range from despotism to anarchism |
| `faction_tendency` | `0.90` | Highest of any starting species; internal schism is the default state, not the exception |
| `grievance_memory` | `0.60` | Institutionalised memory (states, religions) persists where individual recall fades; selective and politically instrumentalised |
