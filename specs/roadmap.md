# Starscape 5 — Design & Implementation Roadmap

Cross-reference of every major system component: design spec, implementation
scripts, DB tables, and current status.

**Status codes:**
- `design` — spec written, nothing implemented
- `partial` — implementation started but incomplete or not integrated
- `impl` — implemented in scripts but not yet wired into main pipeline
- `done` — implemented, integrated, tested

---

## Pipeline Components

| Component | Status | Spec doc(s) | Script(s) | DB table(s) | Blockers / Notes |
|---|---|---|---|---|---|
| Star seeding | `done` | — | `seed_sol.py` | `Stars` | Sol seeded manually; procedural star gen out of scope |
| Fill stars (spectral/physical props) | `done` | `specs/worldgeneration/fillstars.md` | `scripts/fill_spectral.py` | `Stars` (update) | — |
| Orbit computation | `done` | `specs/worldgeneration/orbits.md` | `scripts/compute_orbits.py` | `StarOrbits` | — |
| Planet / moon / belt generation | `done` | `specs/worldgeneration/planets.md` | `scripts/generate_planets.py` | `Bodies` | Includes rings, belt composition, belt span, world_size_code |
| Atmosphere & surface conditions | `impl` | `specs/biosphere/planetbiosphere.md` | `scripts/generate_atmosphere.py` | `BodyMutable`, `Bodies` (3 immutable cols) | Two-pass resumable; tidal heating for inner GG moons |
| Metrics computation | `done` | `specs/worldgeneration/computemetrics.md` | `scripts/compute_metrics.py` | derived / reporting | — |
| Pipeline analysis / completeness | `done` | — | `scripts/analyze_completeness.py` | — | Diagnostic tool |

---

## Biosphere Layer

| Component | Status | Spec doc(s) | Script(s) | DB table(s) | Blockers / Notes |
|---|---|---|---|---|---|
| BodyMutable (atm, hydro, surface temp) | `impl` | `specs/biosphere/planetbiosphere.md` | `scripts/generate_atmosphere.py` | `BodyMutable` | Schema in `sql/schema.sql`; inline CREATE in generate_atmosphere.py |
| Biosphere table (native life presence) | `design` | `specs/biosphere/planetbiosphere.md` | — | `Biosphere` | Blocked on Species implementation |
| SophontPresence table | `design` | `specs/biosphere/planetbiosphere.md` | — | `SophontPresence` | Blocked on Species; presence_start=NULL for native species |
| TerraformProject table | `design` | `specs/biosphere/planetbiosphere.md` | — | `TerraformProject` | Blocked on SophontPresence + Species |

---

## Species Layer

| Component | Status | Spec doc(s) | Script(s) | DB table(s) | Blockers / Notes |
|---|---|---|---|---|---|
| Species table schema | `design` | `specs/biosphere/species.md` | — | `Species` | 11 hand-authored species data rows ready; vocab finalisation needed first |
| Controlled vocab finalisation | `design` | `specs/biosphere/species.md` (Open Questions) | — | — | body_plan, locomotion, atm_req, metabolic_rate — new terms from hand-authored species |
| Hand-authored species seed script | `design` | `specs/biosphere/species.md` | — | `Species` | Blocked on Species schema; data rows complete in spec |
| SpeciesCaste child table | `design` | `specs/biosphere/species.md` (note) | — | `SpeciesCaste` | Deferred; needed for Vrekkai (Moties) and Kreeth (Bugs) |
| SpeciesHost join table | `design` | `specs/biosphere/species.md` (note) | — | `SpeciesHost` | Deferred; needed for Nhaveth parasite/host operational stats |
| Procedural species generation | `design` | `specs/biosphere/species.md` (Generation Notes) | `generate_species.py` (future) | `Species` | Blocked on hand-authored seed + homeworld seeding |

---

## Civilisation Layer  *(not yet started)*

| Component | Status | Spec doc(s) | Script(s) | DB table(s) | Blockers / Notes |
|---|---|---|---|---|---|
| Tech tree spec | `design` | `specs/GameDesign/techtree.mmd` | — | `TechTree`, `TechNode` (future) | 6-domain DAG; jump range/transit split; see techtree.mmd |
| Polity / civilisation table | `design` | — | — | `Polity` (future) | Blocked on Species + tech tree; mixed vs homogenous polity decision pending |
| Tech tree implementation | `design` | `specs/GameDesign/techtree.mmd` | — | `PolityTech` (future) | Blocked on Polity + species-modifier design |
| Diplomacy / relations | `design` | — | — | `DiplomaticRelation` (future) | Blocked on Polity |
| Military / conflict | `design` | — | — | TBD | Blocked on Polity + tech tree |

---

## Game Design Reference

| Doc | Purpose |
|---|---|
| `specs/GameDesign/game_1.md` | High-level game design notes |
| `specs/GameDesign/greatspace4x.md` | 4X design reference / comparables |
| `specs/GameDesign/techtree.mmd` | Tech tree domain structure (Mermaid diagram) |
| `specs/biosphere/species.md` | Species schema, 11 hand-authored entries, tech tree species constraints |
| `specs/biosphere/planetbiosphere.md` | BodyMutable, Biosphere, SophontPresence, TerraformProject |
| `specs/worldgeneration/planets.md` | Bodies table, planet/moon/belt generation |
| `specs/worldgeneration/orbits.md` | StarOrbits, orbital mechanics |
| `specs/worldgeneration/fillstars.md` | Star spectral/physical fill |
| `specs/worldgeneration/worldnotes.md` | World classification notes (rings, belts, size codes) |
| `specs/datadictionary.md` | Cross-table data dictionary |

---

## Immediate Next Steps (ordered by dependency)

1. Finalise controlled vocabularies for `body_plan`, `locomotion`, `atm_req`,
   `metabolic_rate` — required before Species schema can be written to SQL
2. Write `Species` CREATE TABLE into `sql/schema.sql`
3. Write `seed_species.py` to insert the 11 hand-authored rows
4. Promote `generate_atmosphere.py` from `impl` to `done` — run against full
   DB, verify Earth/Venus/Moon sanity checks pass
5. Implement `Biosphere` + `SophontPresence` tables (unblocked once Species exists)
6. Begin civilisation-layer spec: Polity table design with species FK
7. Tech tree spec (full DAG write-up) — after Polity design resolves
   mixed-polity question
