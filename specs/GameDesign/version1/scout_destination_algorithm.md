# Scout Destination Selection — Algorithm

How a scout fleet chooses its next jump destination each tick.

---

## Module map

| Step | Module |
|---|---|
| Phase entry point | `src/starscape5/engine/decision.py` — `run_decision_phase()` |
| Snapshot construction | `src/starscape5/game/snapshot.py` — `build_snapshot()` |
| Posture draw | `src/starscape5/game/posture.py` — `draw_posture()` |
| Candidate generation + scoring | `src/starscape5/game/actions.py` — `generate_candidates()`, `_score_scout()` |
| Action selection | `src/starscape5/game/actions.py` — `select_actions()` |
| Jump execution | `src/starscape5/game/action_executor.py` — `_execute_scout()` |
| Physical jump | `src/starscape5/game/movement.py` — `execute_jump()` |
| Neighbor lookup | `src/starscape5/world/impl.py` — `get_systems_within_parsecs()` |

---

## Full algorithm

```
EACH TICK, PHASE 2 (Decision), for each active polity:

1. BUILD SNAPSHOT  [snapshot.py :: build_snapshot()]
   ├── Read current polity state (treasury, jump_level, at_war_with, etc.)
   ├── Read all fleets and their hull composition
   ├── Compute fleet.jump_range = min over all jumping hulls of:
   │       max(hull.base_jump, polity.jump_level)
   │   (all hulls benefit from polity jump upgrades, not just scouts)
   ├── Read known systems (SystemIntelligence rows for this polity)
   │   └── knowledge_tier is either 'passive' (refuelling info only)
   │       or 'visited' (full survey data)
   └── Derive:
       ├── visited_ids  = systems where knowledge_tier == 'visited'
       ├── n_scouts     = count of non-destroyed scout hulls
       └── n_colonies   = presences with control_state in (colony, controlled)

2. DRAW POSTURE  [posture.py :: draw_posture()]
   Weighted random draw from {EXPAND, CONSOLIDATE, PREPARE, PROSECUTE}
   Relevant weights for scout activity:
   ├── EXPAND      = 1.0 + expansionism×2.0 − aggression×0.5 + 1.0(if peace)
   └── CONSOLIDATE = 0.5 + (1−expansionism)×1.0
   Scout destination candidates are generated regardless of posture,
   but posture affects what competes against them in final selection.

3. GENERATE SCOUT CANDIDATES  [actions.py :: generate_candidates()]

   NOTE: All calls to world.get_systems_within_parsecs() are memoized within
   the tick via a local dict cache so that BFS and upgrade checks re-use
   already-fetched neighbor lists without additional DB round-trips.

   FOR each fleet in snapshot.fleets:
     IF fleet.status != 'active'      → skip
     IF fleet.has_scout == False      → skip
     IF fleet.system_id is None       → skip  (fleet is in transit)

     neighbors = world.get_systems_within_parsecs(
                     fleet.system_id,
                     fleet.jump_range   ← polity-upgraded range
                 )
     unvisited = [ s for s in neighbors if s not in visited_ids ]

     IF unvisited is non-empty:
       FOR each neighbor_system in unvisited:
         intel = known intel for neighbor_system, or synthetic passive record
                 if no prior knowledge exists
         score = _score_scout(fleet, intel, snapshot)
         APPEND ScoutAction(fleet_id, destination=neighbor_system, score=score)

     ELSE (dead end — all reachable neighbors already visited):
       hops = _frontier_first_hop(
                  fleet.system_id, visited_ids,
                  fleet.jump_range, neighbor_fn  ← memoized
              )
       FOR each hop_system in hops:
         APPEND ScoutAction(fleet_id, destination=hop_system,
                            score = 1.0 + expansionism×2.0)
         ↑ Backtrack move: scout jumps one hop toward the nearest frontier.
           Scored identically to normal scouting so it competes fairly.
           The scout will continue backtracking each tick until it reaches
           a visited system that has unvisited neighbors.

3a. FRONTIER FIRST-HOP (BACKTRACK BFS)  [actions.py :: _frontier_first_hop()]

   A "frontier" visited system is any visited system that has at least one
   unvisited neighbor within jump_range.

   BFS from current_system_id through VISITED space only:
     seed queue with { (nb, nb) for nb in neighbors(current) if nb in visited }
     process level by level:
       FOR each (node, first_hop) at current BFS depth:
         IF node has any unvisited neighbor → record first_hop as result
         EXPAND to unvisited-BFS visited neighbors of node
       IF any result collected at this depth → STOP (nearest frontier found)

   Returns all distinct first_hop values at the minimum BFS depth.
   Returns [] if current position is already a frontier (should not be called)
   or no frontier is reachable through connected visited space.

4. SCORE SCOUT ACTION  [actions.py :: _score_scout()]

   score = 1.0 + expansionism × 2.0
   IF intel.world_potential > 10:   score += 1.0   ← passive refuelling hint
   IF intel.knowledge_tier == 'visited':  score = −99.0  ← guard; already seen

   Note: score is the same for all unvisited neighbors except the
   world_potential bonus. There is no directional preference, no
   gradient following, and no memory of prior scouts' routes.

5. COMPETE AGAINST OTHER ACTIONS  [actions.py :: generate_candidates()]
   Scout candidates (both normal and backtrack) enter the same pool as:
   ├── ColoniseActions   (scored by world_potential, habitability, enemy proximity)
   ├── BuildHullActions  (scored by posture, hull type, treasury)
   ├── AssaultActions    (PROSECUTE posture only)
   ├── UpgradeJumpAction (only when ALL visited systems are exhausted — see §6 below)
   └── ConsolidateActions (low-score filler)

6. SELECT TOP ACTIONS  [actions.py :: select_actions()]
   Softmax-weighted sampling without replacement, top_k = 5.

   weights[i] = exp( (score[i] − max_score) / temperature )
                          temperature = 1.0

   Draw up to 5 actions from the weighted pool (without replacement).
   Higher score → higher probability of selection, but not guaranteed.
   Multiple ScoutActions for the same fleet may all be in the pool;
   whichever is drawn first wins — subsequent ones for the same fleet
   will be executed if also drawn (each issues a jump order).

6a. JUMP UPGRADE GATE (exhaustion check)
    The upgrade fires only when EVERY visited system has been drained:

    any_reachable = any(
        True
        for vsid in visited_ids                        ← all visited, not just fleet positions
        for sid  in neighbors(vsid, polity.jump_level)
        if sid not in visited_ids
    )
    IF any_reachable → do NOT offer upgrade; scouts will backtrack to those frontiers.
    IF NOT any_reachable → all known space exhausted; upgrade offered.

    This guarantees scouts backtrack and exhaust every frontier at the current
    jump level before the polity spends RU on a range increase.

7. EXECUTE SELECTED SCOUT ACTIONS  [action_executor.py :: _execute_scout()]
   FOR each selected ScoutAction:
     Verify fleet still exists and status == 'active'
     Verify destination is within jump range (re-check against live DB)
       NOTE: backtrack destinations are visited systems — range check still applies.
     CALL execute_jump(fleet_id, destination_system_id, tick)
       └── Sets fleet.status = 'in_transit'
           Sets fleet.destination_system_id, fleet.destination_tick = tick+1
           Fleet arrives next tick (Phase 3, Movement)

8. ON ARRIVAL  [engine/movement.py :: run_movement_phase()]
   Fleet settles at destination.
   record_visit() is called → upserts SystemIntelligence with knowledge_tier='visited'
   WorldFacadeImpl.resolve_system() populates planet data for the system
   (lazy generation: Bodies and WorldPotential rows created on first visit)
```

---

## What the algorithm does NOT do

- **No long-range pathfinding.** Backtracking uses BFS through visited space
  to reach the nearest unexhausted frontier, but scouts cannot plan a
  multi-hop route into *unvisited* space — they can only see one jump ahead.
- **No coordination.** Two scout fleets may jump to the same system on the
  same tick. There is no deconfliction.
- **No memory of prior routes.** The score for an unvisited system is the
  same whether the polity has been scouting toward it for 10 ticks or
  has never looked that direction.
- **No directional preference.** The scoring function has no concept of
  "toward the galactic core" or "away from a rival." All unvisited neighbors
  are treated equally except for the passive world_potential hint.
- **No galaxy-scale awareness.** The polity only sees systems in
  SystemIntelligence. Stars beyond passive scan range (20 pc) and beyond
  jump range are invisible regardless of their value.

---

## Key parameters

| Parameter | Value | Location |
|---|---|---|
| Scout base jump range | J10 (parsecs) | `constants.py` — `HULL_STATS["scout"].jump` |
| Polity jump upgrade start | J10 | `polity.py` — `create_polity()` |
| Jump upgrade step | +2 pc | `polity.py` — `_JUMP_UPGRADE_STEP` |
| Jump upgrade max | J20 | `polity.py` — `_JUMP_UPGRADE_MAX` |
| Scout cap | n_colonies + 1 | `actions.py` — `_SCOUT_CAP` |
| Score base | 1.0 + expansionism × 2.0 | `actions.py` — `_score_scout()` |
| World_potential bonus threshold | > 10 | `actions.py` — `_score_scout()` |
| Top-k selection | 5 | `engine/decision.py` — `select_actions(..., top_k=5)` |
| Softmax temperature | 1.0 | `actions.py` — `select_actions()` |
