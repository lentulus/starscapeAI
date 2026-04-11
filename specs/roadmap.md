# Starscape 5 — Design & Implementation Roadmap

Cross-reference of every major system component: design spec, implementation
modules, DB tables, and current status.

**Status codes:**
- `design` — spec written, nothing implemented
- `partial` — implementation started but incomplete or not integrated
- `impl` — implemented but not yet fully integrated / run against full DB
- `done` — implemented, integrated, tested

---

## World Layer (starscape.db — static read-only substrate)

| Component | Status | Module(s) | DB table(s) | Notes |
|---|---|---|---|---|
| Star seeding | `done` | `scripts/seed_sol.py` | `IndexedIntegerDistinctStars` | Sol seeded manually |
| Fill stars (spectral/physical) | `done` | `scripts/fill_spectral.py` | `IndexedIntegerDistinctStars` | — |
| Orbit computation | `done` | `scripts/compute_orbits.py` | `StarOrbits` | — |
| Metrics computation | `done` | `scripts/compute_metrics.py` | `DistinctStarsExtended` | — |
| Planet/moon/belt generation | `done` | `scripts/generate_planets.py` | `Bodies` | Lazy generation also in `world/impl.py` |
| Atmosphere & surface conditions | `impl` | `scripts/generate_atmosphere.py` | `BodyMutable`, `Bodies` | Run against full DB; sanity-check Earth/Venus/Moon |
| WorldFacadeImpl (real world layer) | `done` | `src/starscape5/world/impl.py` | — | M12; neighbor index `idx_systems_x` created on DB |
| Species table + seed | `done` | `scripts/seed_species.py` | `Species` | 11 hand-authored rows seeded |

---

## Game Layer (game.db — mutable simulation state)

| Component | Status | Module(s) | DB table(s) | Notes |
|---|---|---|---|---|
| Schema | `done` | `sql/schema_game.sql` | all game tables | — |
| DB helpers | `done` | `src/starscape5/game/db.py` | — | open_game, init_schema |
| Polity / state | `done` | `game/polity.py`, `game/state.py` | `Polity`, `GameState` | crash-safe advance/commit |
| Fleet / hull / squadron | `done` | `game/fleet.py` | `Fleet`, `Hull`, `Squadron` | — |
| Ground forces | `done` | `game/ground.py` | `GroundForce` | army + garrison |
| Presence / control | `done` | `game/presence.py`, `game/control.py` | `SystemPresence` | control_state lifecycle |
| Economy | `done` | `game/economy.py` | `WorldPotential`, `BuildQueue`, `RepairQueue` | RU production, maintenance, build queues |
| Intelligence | `done` | `game/intelligence.py` | `SystemIntelligence` | passive scan, record_visit, map sharing |
| Movement | `done` | `game/movement.py` | `Fleet` | execute_jump, arrivals, contacts |
| Space combat | `done` | `game/combat.py` | `Hull`, `Fleet` | M9; simultaneous fire, disengage, pursuit |
| Bombardment | `done` | `game/bombardment.py` | `GroundForce`, `GameEvent` | M10; naval superiority prerequisite |
| Assault | `done` | `game/assault.py` | `GroundForce`, `SystemPresence` | M10; garrison bonus, rout/decisive table |
| Decision engine | `done` | `game/snapshot.py`, `game/posture.py`, `game/actions.py`, `game/war.py`, `game/action_executor.py` | — | M11; softmax candidate selection |
| Log / summary | `done` | `game/log.py` | `GameEvent` | M13; monthly_summary compression |
| Events | `done` | `game/events.py` | `GameEvent` | append-only history log |
| Admirals / names | `done` | `game/admiral.py`, `game/names.py` | `Admiral` | — |
| GameFacade | `done` | `game/facade.py` | — | Protocol + Stub + Impl; full engine seam |
| Game initialiser | `done` | `game/init_game.py`, `game/ob_data.py` | all | OB_DATA for 11 species |

---

## Engine Layer (orchestrates phases)

| Component | Status | Module(s) | Notes |
|---|---|---|---|
| Intelligence phase (1) | `done` | `engine/intelligence.py` | passive scan, peace weeks, map sharing |
| Decision phase (2) | `done` | `engine/decision.py` | war rolls, posture, candidate gen, action exec |
| Movement phase (3) | `done` | `engine/movement.py` | arrivals, visits, contacts |
| Combat phase (4) | `done` | `engine/combat.py` | space combat in contested systems |
| Bombardment phase (5) | `done` | `engine/bombardment.py` | orbital bombardment |
| Assault phase (6) | `done` | `engine/assault.py` | ground combat |
| Economy phase (8) | `done` | `engine/economy.py` | RU collect, maintenance, queues |
| Control phase (7) | `done` | `engine/control.py` | 25-week growth cycles |
| Log phase (9) | `done` | `engine/log.py` | quiet-tick classifier, monthly summary |
| Tick runner (partial) | `done` | `engine/tick.py` | `run_partial_tick` — all 9 phases, no crash-safe wrapping |
| Tick runner (crash-safe) | `done` | `engine/simulation.py` | `run_tick`, `run_simulation` with advance/commit and resume |

---

## Simulation Execution

| Component | Status | Module(s) | Notes |
|---|---|---|---|
| run_sim.py | `done` | `scripts/run_sim.py` | CLI runner; `--ticks N`, `--resume`, `--verbose` |
| First 500-tick run | `in progress` | — | M13 smoke test; `game.db` on local disk |

---

## Biosphere Layer (future)

| Component | Status | Notes |
|---|---|---|
| Biosphere table (native life) | `design` | Blocked on integration with running simulation |
| SophontPresence table | `design` | Blocked on Biosphere |
| TerraformProject table | `design` | Blocked on SophontPresence |

---

## Tech Tree & Advanced Civilisation (future)

| Component | Status | Notes |
|---|---|---|
| Tech tree DAG | `design` | `specs/GameDesign/techtree.md` — 6 domains, jump range progression |
| PolityTech table | `design` | Blocked on simulation stability validation |
| Diplomacy / relations | `design` | Blocked on tech tree |
| Faction splits | `design` | Triggered by social_cohesion + grievance_memory thresholds |
| LLM historian pipeline | `design` | `specs/GameDesign/documentation-pipeline.md` — reads GameEvent log |

---

## Immediate Next Steps (ordered by dependency)

1. **Validate first 500-tick run** — check event counts, verify wars fire for high-aggression species, colonies establish, no crashes
2. **Tune if needed** — if wars are too rare/frequent, adjust `_WAR_THRESHOLD` in `game/war.py` or posture weights in `game/posture.py`
3. **Run `generate_atmosphere.py` to completion** against full DB — promote to `done` after Earth/Venus/Moon sanity checks
4. **Run longer simulation** (5000 ticks ≈ 96 years) to observe multi-polity dynamics
5. **Tech tree spec** — begin DAG implementation once simulation produces stable history
6. **LLM historian** — point at `game.db` `GameEvent` table once sufficient history exists
