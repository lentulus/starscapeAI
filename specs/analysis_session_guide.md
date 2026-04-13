# Starscape 5 — Analysis Session Guide

This document is for the AI assistant in a new session. It provides everything needed
to analyse the completed simulation run and write the requested histories.

---

## Context

A 500-tick simulation was run on **2026-04-12** from a fresh `game.db`.
The run covers approximately 500 weeks (~9.6 years) of simulated time.

All game data is in `game.db` (project root). The world/stellar data is in
`/Volumes/Data/starscape4/sqllite_database/starscape.db` (external drive — must be mounted).

---

## Simulation configuration

- **Ticks:** 500 (1 tick = 1 week)
- **Species:** 11 sophont species (see `src/starscape5/game/ob_data.py` for names/IDs)
- **Started from:** fresh init (no resume)
- **Script:** `uv run scripts/run_sim.py --ticks 500`

### Species IDs (from `ob_data.py`)

| species_id | Name | Notes |
|---|---|---|
| 1 | Kreeth | insectoid hive-mind |
| 2 | Vashori | amphibian traders |
| 3 | Kraathi | reptilian warriors |
| 4 | Nakhavi | fungal collective |
| 5 | Skharri | honour-culture mammals |
| 6 | Vaelkhi | avian explorers |
| 7 | Shekhari | pragmatic primates |
| 8 | Golvhaan | deliberate lithomorphs |
| 9 | Nhaveth | court-politics sophonts |
| 10 | Vardhek | Roidhunate-style hierarchy |
| 11 | Human | Sol-based humans |

Each species has exactly one polity in V1 (polity_id = species_id).

---

## Key database tables for analysis

### Finding wars (task: write Earth/Human war history)

```sql
-- All wars involving Humans (polity_id = 11)
SELECT wr.*, 
       pa.name AS polity_a_name, pb.name AS polity_b_name
FROM WarRecord wr
JOIN Polity_head pa ON pa.polity_id = wr.polity_a_id
JOIN Polity_head pb ON pb.polity_id = wr.polity_b_id
WHERE wr.polity_a_id = 11 OR wr.polity_b_id = 11
ORDER BY wr.declared_tick;

-- All wars, any polities
SELECT * FROM WarRecord ORDER BY declared_tick;
```

### GameEvent table — the narrative record

```sql
-- All events (there may be thousands; filter by type)
SELECT * FROM GameEvent ORDER BY tick, phase;

-- Event types available:
-- 'combat', 'bombardment', 'ground_assault', 'control_change',
-- 'colony_established', 'colonist_delivery', 'war_declared', 'peace',
-- 'contact', 'map_shared', 'admiral_retired', 'hull_destroyed',
-- 'fleet_supply_degraded', 'build_completed', 'repair_completed',
-- 'monthly_summary', 'quiet_period'

-- Human war events
SELECT tick, phase, event_type, summary
FROM GameEvent
WHERE (polity_a_id = 11 OR polity_b_id = 11)
  AND event_type IN ('war_declared','peace','combat','bombardment',
                     'ground_assault','control_change')
ORDER BY tick, phase;

-- All combat events with participants
SELECT tick, event_type, summary, polity_a_id, polity_b_id, system_id
FROM GameEvent
WHERE event_type IN ('combat', 'bombardment', 'ground_assault')
ORDER BY tick;

-- Colony events
SELECT tick, event_type, summary, polity_a_id, system_id, body_id
FROM GameEvent
WHERE event_type IN ('colony_established', 'colonist_delivery', 'control_change')
ORDER BY polity_a_id, tick;
```

### Finding the most-colonised polity

```sql
-- Count colonies per polity at end of run
SELECT sp.polity_id, p.name AS polity_name, COUNT(*) AS colony_count
FROM SystemPresence_head sp
JOIN Polity_head p ON p.polity_id = sp.polity_id
WHERE sp.control_state IN ('colony', 'controlled')
GROUP BY sp.polity_id
ORDER BY colony_count DESC
LIMIT 5;

-- Full colonisation timeline for the leader
SELECT tick, event_type, summary, system_id, body_id
FROM GameEvent
WHERE polity_a_id = <WINNER_POLITY_ID>
  AND event_type IN ('colony_established', 'colonist_delivery', 'control_change')
ORDER BY tick;
```

### Admirals — for the war history narrative

```sql
-- All admirals for Human polity
SELECT a.admiral_id, a.name, a.tactical_factor,
       a.created_tick, a.retirement_tick, a.status
FROM Admiral_head a
WHERE a.polity_id = 11
ORDER BY a.created_tick;

-- Admiral death/retirement events
SELECT tick, summary FROM GameEvent
WHERE event_type IN ('admiral_retired', 'admiral_killed', 'admiral_captured')
  AND (polity_a_id = 11 OR polity_b_id = 11)
ORDER BY tick;
```

### System positions (for geographic context)

```sql
-- Where is a system?
SELECT s.system_id, s.x/1000.0 AS x_pc, s.y/1000.0 AS y_pc, s.z/1000.0 AS z_pc
FROM IndexedIntegerDistinctSystems s
WHERE s.system_id = <SID>;
-- Note: attach starscape.db first: ATTACH '/Volumes/Data/starscape4/sqllite_database/starscape.db' AS world;
```

### ContactRecord — diplomatic history

```sql
-- Who met whom and when
SELECT contact_id, polity_a_id, polity_b_id, contact_tick, contact_system_id,
       at_war, peace_weeks
FROM ContactRecord_head
ORDER BY contact_tick;
```

---

## Connecting to the database

```python
import sqlite3

conn = sqlite3.connect("game.db")
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")
```

Or use the project helpers:
```python
import sys; sys.path.insert(0, "src")
from starscape5.game.db import open_game
conn = open_game("game.db")
```

---

## Tasks for the analysis session

### 1. History of the Human war(s)

- Find all wars involving polity_id=11 in `WarRecord`
- For each war: find the opponent, declared_tick → ended_tick
- Pull all combat/bombardment/ground_assault events in that tick range for those two polities
- Pull admiral names at the time (from `Admiral_head` or `Admiral` table filtered by tick range)
- Write a narrative: dates (tick → approximate year, 1 tick = 1 week, 52 ticks = 1 year),
  system names (use system_id; check HIP catalog for named stars), key battles, admiral names
- If no Human war occurred in 500 ticks, write about the largest Human conflict or first contact

**Date conversion:** tick 0 = year 0, tick 52 = year 1. `year = tick / 52`

### 2. Colonisation history of the most-colonised species

- Run the colony-count query above
- Pick the polity with the most colonies
- Pull the full event log of their colonisation efforts
- Write a narrative of expansion: which systems, in what order, at what dates

---

## State of the codebase at time of run

- All 424 tests passing
- Last commit: `2ac2a50` — "Temporal table refactor + admiral retirement system"
- Key recent changes:
  - Tables now temporal (append-only with tick/seq): SystemPresence, GroundForce,
    Hull, Admiral, ContactRecord, Polity
  - Admiral retirement system: admirals serve ~30% of species lifespan then retire;
    replacements auto-commissioned; events logged as `admiral_retired`
  - `WarRecord` table tracks war start/end ticks
  - `GameEvent` table has all significant events

---

## Running queries

From project root:
```bash
sqlite3 -column -header game.db "SELECT ..."
# or
uv run python3 -c "
import sqlite3; conn = sqlite3.connect('game.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT ...'): print(dict(r))
"
```

---

## Notes for the historian task

- System IDs are integers referencing the Hipparcos catalogue.
  Sol = system_id for the Sun (find it via `SELECT system_id FROM SystemIntelligence WHERE polity_id=11 ORDER BY first_visit_tick LIMIT 1`)
- Polity names are in `Polity_head.name`
- Admiral names are in `Admiral_head.name` (species-appropriate procedural names)
- All war/combat events have `system_id` — these are the battle locations
- The `summary` column in `GameEvent` is a free-text key=value string;
  parse it for details (e.g., `strength_delta`, `net_bombard`, `victor`)
