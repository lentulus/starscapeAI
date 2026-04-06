# Concept: The Great 4X Space Strategy not-game

## Overview
The game will simulate a number of independent sophont species starting on different stars within a 2000 parsec cube near earth, exploring and colonizing the stars.  
- each species will have different priorities, politics, cultural dispositions and factions
- eventually conflict is expected
- economics, politics, society and war should all be covered
- ships travel by jumps of 1-6 parsecs and information travels with ships (much like the Traveller RPG).  Information lag most be considered
- records must be kept that would permit an LLM based AI to write a history for each species.
Time is interesting here.  Either 1-day or 1-week increments?
The simulation might run forever.


## Scope
**Includes:** everything else 
**Excludes:** The physical and biological but not cultural or economic status of each and every planet and moon will be static data

## Modules Involved

To be determined

## Data Flow

### Static World-Building Pipeline (pre-simulation, run once)
1. Stars generated and spectral types filled → `fillspectral.md`
2. Orbital mechanics computed per system → `orbits.md`
3. Worlds generated and assigned a habitability rating for each star system
4. Habitability ratings drive which worlds are candidates for colonization

### Simulation Pipeline (per tick)
TBD

## Interface Contracts
TBD
## Key Decisions
- Python implementation
- developent on mac (external 2TB hard drive mac mini)
- target Dell XPS 13 with i7 runniing Ubuntu
- SQLite database; but negotiable later
- Mongoose traveller conventions for describing worlds per World Builder's Handbook
- Warfare modeled on *Fifth Frontier War* (GDW board game) as a conceptual template — fleet-level abstractions, system control, naval superiority as a prerequisite for ground assault
- Habitability rating is a multi-factor score (viability + resources); criteria defined in a separate document (TBD)
- Habitability is evaluated per-species and evolves over time — a species without FTL may settle suboptimal worlds within reach that it would later pass over
- All species apply the same underlying habitability criteria, so conflict over prime real estate is structural
- ~6 sophont species all start simultaneously at interplanetary tech level (pre-FTL)
- Tech progress is a per-species priority; faster research priority → faster tech advancement

## Open Questions

- [x] **「Not-game」clarification** — Fully autonomous simulation; no runtime observer interface. Output is the generated history only. Two later enhancements noted: (1) a facility for a human to inject very-high-level policies; (2) a hook for an external LLM tool to provide input.
- [x] **Star count / scale** — 2.47 million stars total. Only a small percentage will have habitable/exploitable planets. Star types are drawn from the real stellar catalog with spectral types derived from B-V and absolute magnitude (see `fillspectral.md`). Habitability/exploitability will be a filter on top of that initial population.
- [x] **Species count and emergence** — ~6 sophont species, all starting simultaneously at interplanetary tech level (pre-FTL). Tech progress rate is a per-species priority setting; species can advance at different rates.
- [ ] **Information lag modeling** — Approach depends on whether every ship is individually modeled. Information travels with ships at jump speed, but faster corridors (analogous to Traveller X-Boat express routes) may exist, creating uneven lag across the map. Two sub-questions remain open: (1) do we track individual ships or use an aggregate flow model? (2) how are express routes established and by whom?
- [x] **Time increment** — 1-week ticks. Within each week, Traveller-style phases regulate event ordering (e.g. movement, combat, economics, information propagation). Phase structure to be defined in the simulation architecture spec.
- [x] **"Run forever" mode** — No fixed end condition. Runs as a background process. Must support: (1) clean stop/restart without killing the process (graceful pause/resume); (2) recovery from emergency shutdown (crash-safe — resume from last committed tick with no data loss or corruption). Checkpoint/commit strategy per tick is required.
- [x] **History granularity for LLM** — High granularity: all significant asset events logged at weekly tick/phase resolution. During quiet periods (nothing happens), monthly summary records are acceptable to reduce log volume. The LLM Historian's role is to sift logs and identify "decisive points" — the moments that shaped outcomes. Log design must ensure enough context is captured per event for the Historian to reconstruct causality.
- [x] **SQLite scaling** — Stay with SQLite for development; evaluate migration to PostgreSQL when moving to production on the Linux server. All code must be designed for easy migration (no SQLite-specific SQL). Trigger earlier migration if PostgreSQL-only features (e.g. advanced indexing, partitioning, LISTEN/NOTIFY) offer a material advantage. Possible hybrid: SQLite as an immutable store for static world-building truth (stars, worlds, orbital data); PostgreSQL for dynamic simulation state and event logs.
- [x] **Scope boundary** — Resource depletion, terraforming, and conflict with/extermination of native species are all in scope. Physical and biological world data remains static baseline; all changes (terraforming progress, resource depletion, population changes, native species status) are stored as deltas from that baseline, not modifications to the source record.
- [x] **Habitability rating spec** — Multi-factor (viability + resources), species-relative, time-evolving. Criteria to be defined in a dedicated document (owner: TBD). Must be resolved before world generation is implemented.

## For Later
- [ ] **Habitability rating criteria document** — Full multi-factor definition (viability, resources, orbital parameters, UWP attributes). **Next priority** — needed before planet generation begins.
- [ ] **Tech tree spec** — Define technology progression tiers (pre-FTL → jump-1 → jump-6 etc.), advancement rates, and how tech level gates colonization reach, ship capability, and communications delay. **Priority 2** — comms lag model depends on this.
- [ ] **Simulation architecture spec** — Phase structure within a weekly tick; event loop design; checkpoint/recovery strategy; player-AI decision hooks.
- [ ] **Tech progress spec** — Define how technology (especially FTL capability and jump range) advances over simulation time and how it affects colonization reach and military capability.
- [ ] **Ship tracking model** — Decide whether every ship is individually modeled or an aggregate flow model is used. For large military forces, fleet-level abstraction is a likely simplification (individual tracking for couriers/scouts; fleet abstraction for warships). Decision affects information-lag architecture and combat modeling.

## References

| File | Subject |
|------|---------|
| `worldgeneration/fillspectral.md` | Deriving spectral types from B-V/magnitude; companion star generation |
| `worldgeneration/orbits.md` | Orbital mechanics computation per star system |
| `worldgeneration/computemetrics.md` | Deriving physical stellar parameters (mass, temperature, radius, luminosity, age) from B-V and absolute magnitude into `DistinctStarsExtended` |
| `worldgeneration/_template.md` | Standard spec template for worldgeneration features |
| `worldgeneration/_template_concept.md` | Multi-module concept spec template |