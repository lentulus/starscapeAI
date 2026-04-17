# Starscape 5 — Version 1.1 Architecture

Event-driven re-architecture design document.  
**Status: design** — no implementation yet.

---

## Why re-architect

Version 1 uses a fixed weekly tick with 9 sequential phases.  This works but
imposes artificial synchronisation: a fleet that jumps on Monday and one that
jumps on Friday both "arrive" at the same phase boundary.  Event ordering
within a tick is by processing_order, which is a proxy for causality rather
than a real one.

The deeper problem appears when the simulation scales: a quiet period where
nothing happens for 50 simulated years burns 2,600 ticks of CPU doing nothing.
An event-driven model skips directly to the next thing that matters.

---

## Core model

### Time: sim_seconds

All timestamps are **sim_seconds** — integer seconds of simulated universe
time elapsed since the simulation epoch (t=0).  No fixed relationship between
sim_seconds and wall-clock time.

Reference durations:
| Unit | sim_seconds |
|---|---|
| 1 day | 86,400 |
| 1 week | 604,800 |
| 1 year | 31,557,600 |
| 40,000 years (horizon) | ~1.26 × 10¹² |

A 64-bit integer holds the full horizon with room to spare.

### The event queue

The simulation maintains a priority queue of **scheduled events**, ordered by
`fire_at` (sim_seconds).  The main loop is:

```
while queue is not empty and not halted:
    event = queue.pop_earliest()
    handlers = dispatch(event.type)
    new_events = handlers(event, state)
    queue.push_all(new_events)
    commit(event, new_events)
```

Each handler returns zero or more new events to enqueue.  The simulation
advances to exactly the next event's `fire_at` — no wasted cycles on empty
time.

### Events

An event is a record with:
- `event_id` — unique, assigned at enqueue time
- `fire_at` — sim_seconds when it executes
- `event_type` — string key that selects the handler
- `payload` — JSON blob of handler-specific parameters
- `caused_by` — event_id of the parent event (NULL for externally injected)

Events are **immutable once enqueued**.  Cancellation is by recording a
`cancelled` flag; the handler checks on pop and discards if cancelled.

---

## What replaces the 9-phase model

V1 phases become event types.  The weekly synchronisation is gone; each
process fires when its own timer elapses.

| V1 phase | V1.1 event type(s) | Typical recurrence |
|---|---|---|
| Intelligence (1) | `passive_scan` | Per-system, weekly |
| Decision (2) | `polity_decision` | Per-polity, weekly |
| Movement (3) | `fleet_arrival` | Per-fleet, on-demand |
| Combat (4) | `space_combat` | Triggered by `fleet_arrival` |
| Bombardment (5) | `orbital_bombardment` | On decision |
| Assault (6) | `ground_assault` | After bombardment |
| Control (7) | `control_check` | Per-presence, 25-week cycle |
| Economy (8) | `economy_tick` | Per-polity, weekly |
| Log (9) | `summary_log` | Monthly |

**Critical difference:** `fleet_arrival` fires when a specific fleet's travel
time elapses, not at the next weekly boundary.  Two fleets jumping to the same
system on the same simulated day can arrive seconds apart; causality is exact.

---

## State model — insert-only temporal tables

**State tables are never updated.  Every change is a new INSERT.**

Every state table carries a `sim_seconds INTEGER NOT NULL DEFAULT 0` column.
The primary key includes `sim_seconds`.  Current state is always a correlated
`MAX(sim_seconds)` subquery, exposed as a `_head` view.  Historical state is
readable at any point in time with `sim_seconds <= :as_of`.

Consequences:
- No `UPDATE` or `DELETE` in the engine — only `INSERT` and `SELECT`
- Full history is preserved at negligible cost for slowly-changing tables
- Crash recovery is trivial: a committed row is valid; a missing row means
  the operation did not complete — re-run it
- The `_head` view always reflects the latest committed state

Example pattern (used for all state tables):
```sql
CREATE VIEW "Foo_head" AS
    SELECT f.* FROM "Foo" f
    WHERE  f.sim_seconds = (
        SELECT MAX(sim_seconds) FROM "Foo"
        WHERE  entity_id = f.entity_id
    );
```

---

## State model

Simulation state lives in a single **game_v1_1.db**.  It has two logical
layers:

**Static world cache** — copied from starscape.db at init, never updated
during the simulation.  Bodies, stars, positions, species definitions,
baseline physical properties.

**Dynamic simulation state** — everything that changes during the run.
Polities, fleets, presences, event log, the event queue itself.

The two layers communicate only through `body_id` and `system_id` keys.

---

## Crash safety

The event-driven loop commits after each event execution:

1. Pop event from queue
2. Execute handler → produce state mutations + new events
3. Write state mutations to DB
4. Write new events to `ScheduledEvent` table
5. Mark popped event `executed`
6. Commit transaction

On restart: the queue is reconstructed from `ScheduledEvent WHERE status =
'pending'`.  The last executed event is the resume point.  No event is
executed twice.

This replaces the V1 `advance_phase` / `commit_phase` pattern.

---

## First V1.1 component: Habitability

The first schema block is **BodyHabitability** — per-species colonisability
derived from Bodies + Species.  This is static at init (computed once from
baseline Bodies) and updated whenever a body's mutable state changes.

It is deliberately the first component because:
- It depends only on starscape.db (no game state needed)
- It defines the colonisation cap logic that everything else builds on
- It is pure computation — no events, no queue

Full schema: see [habitability.md](habitability.md) (to be written).

---

## What V1 built that carries forward

The following V1 concepts are **architecturally valid** and will be adapted,
not replaced:

- Polity, Fleet, Hull, Squadron, GroundForce data models
- `world_potential` scoring (will incorporate `resource_rating`)
- `WorldFacade` protocol — still the seam between world and game layers
- `GameEvent` append-only history log — becomes the authoritative event
  record (ScheduledEvent is separate: operational queue, not history)
- Combat, bombardment, and assault resolution logic
- Decision engine posture + candidate scoring model

---

## What changes substantially

| V1 concept | V1.1 replacement |
|---|---|
| `tick` (integer week counter) | `sim_seconds` throughout |
| `GameState.current_tick` + `current_phase` | `SimulationClock.sim_seconds` + last executed event_id |
| 9-phase sequential loop | Dispatched event handlers |
| `processing_order` tie-breaker | `fire_at` + `event_id` (deterministic ordering) |
| Seeded RNG per `(tick, phase, polity)` | Seeded RNG per `(event_id, polity_id)` |
| `WorldPotential` species-agnostic score | `WorldPotential` + `BodyHabitability` per species |
| `SystemIntelligence.habitable` (single bool) | `BodyHabitability.habitable` + `habitability_score` |

---

## What is deferred

- Tech tree
- Terraforming / BodyMutableState
- Faction splits
- Diplomacy
- LLM historian pipeline
- Performance: parallel event execution, sharding by system

---

## Open questions

1. **Polity decision cadence.** In V1, all polities decide simultaneously once
   per week.  In V1.1, should `polity_decision` fire at a fixed weekly
   interval per polity (staggered), or should all polities still synchronise
   on the same weekly beat?  Staggered is more realistic but complicates
   reactions to shared events (e.g. contact).

2. **Simultaneous arrival ordering.** Two fleets arrive at the same
   `fire_at`.  Combat fires — who is attacker?  Proposal: lower `event_id`
   wins (arrival insertion order).  Needs explicit policy.

3. **Recurring event scheduling.** Weekly economy ticks are scheduled N weeks
   ahead at init and each execution re-schedules the next.  Or: a single
   `recurring_schedule` table drives them.  Trade-off: simplicity vs.
   inspectability of the queue.

4. **Queue persistence vs. rebuild.** Should the `ScheduledEvent` table be
   the source of truth (queue reconstructed from DB on every restart), or is
   an in-memory heap the primary structure with DB as a write-ahead log?
   The former is simpler and more crash-safe; the latter is faster for large
   queues.

5. **Sub-second granularity.** Is sim_seconds fine enough, or do some events
   (e.g. battle phase ordering within a single engagement) need
   sub-second sequencing?  If so: sim_milliseconds, or a `seq` tiebreaker
   column.
