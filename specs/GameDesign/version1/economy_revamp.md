# Economy Revamp — Diagnostic and Proposed Model

Written after the first 5000-tick run (2526–2622 CE). The current model has
three compounding failure modes that leave most polities in permanent deficit
by tick 500. This document diagnoses each failure, proposes specific fixes,
and gives target balance numbers.

---

## Diagnostic: what the 5000-tick run revealed

### Per-polity production vs maintenance at tick 5000

| Polity | Production (RU/tick) | Maintenance (RU/tick) | CT maintenance | Net | CTs held | Treasury |
|---|---|---|---|---|---|---|
| Kreeth Dominion | 12.0 | 14.7 | 0.5 | −2.7 | 1 | −23,805 |
| Vashori Compact | 22.5 | 22.2 | 13.0 | +0.3 | 26 | −963 |
| Kraathi Crusade | 10.7 | 12.8 | 0.5 | −2.1 | 1 | −18,809 |
| Nakhavi Reach | 18.0 | 17.8 | 9.0 | +0.2 | 18 | −1,428 |
| Skharri Pride | 35.1 | 34.0 | 19.0 | +1.1 | 38 | −1,638 |
| Vaelkhi Choth | 34.5 | 33.5 | 21.0 | +1.0 | 42 | +4 |
| Shekhari Exchange | 15.0 | 14.8 | 6.5 | +0.2 | 13 | −1,326 |
| Golvhaan Reach | 23.9 | 23.5 | 12.0 | +0.4 | 24 | −403 |
| Nhaveth Court A | 30.0 | 28.8 | 18.0 | +1.2 | 36 | −1,456 |
| Nhaveth Court B | 30.0 | 29.0 | 22.0 | +1.0 | 44 | +4 |
| Nhaveth Court C | 31.5 | 32.8 | 29.5 | −1.3 | 59 | −1,203 |
| Vardhek Roidhunate | 30.0 | 29.0 | 16.0 | +1.0 | 32 | +4 |
| Oceania | 10.6 | 12.2 | 0.5 | −1.6 | 1 | −8,481 |
| Eurasia | 0.6 | 6.7 | 0.0 | −6.1 | 0 | −30,547 |
| Eastasia | 1.0 | 7.2 | 0.5 | −6.2 | 1 | −28,496 |

**Key observations:**

1. All polities that survived economically did so by spending their entire
   surplus on colony transport maintenance — their net is +0.2 to +1.2 RU/tick.
   No surplus exists for warship construction, repairs, or jump upgrades.

2. Colony transport maintenance consumes 50–94% of production for the polities
   that built them at scale. Nhaveth Court C carries 59 CTs costing 29.5 RU/tick
   against 31.5 RU/tick production — 94% of economic output maintaining ships
   that have not moved in hundreds of ticks.

3. Three polities (Kreeth, Kraathi, Oceania) are in slow negative drift because
   their homeworld potential is low (7–8) and they carry military fleets. Their
   per-tick deficit means indefinite debt with no recovery path.

4. Eurasia and Eastasia lost their homeworlds to contested status early in the
   Earth war, dropping production to near zero (0.6 and 1.0 RU/tick). At −6
   RU/tick for 5000 ticks, that is −30,000 RU — purely from a contested
   homeworld multiplier of 0.10.

5. No polity built new warships in the final 4000+ ticks. The economy froze.

---

## Failure mode 1: Colony transport accumulation loop

### What happens

The decision engine scores `colony_transport` build actions at
`expansionism × 3.0 + 2.0` in EXPAND posture — the highest build score
available. There is no cap on how many CTs a polity may hold (unlike scouts,
which are capped at `n_colonies + 1`). The build loop runs as long as
`treasury_ru ≥ 10` (CT build cost).

Early in the run, polities have surplus production. They spend it on CTs. Each
CT takes 7 ticks to build and 10 RU. A polity earning 20 RU/tick net of
non-CT maintenance will build a CT every ~2 ticks. By tick 200 they may hold
20+ CTs. Each CT costs 0.5 RU/tick maintenance whether deployed or idle.

CTs that cannot reach a valid colonisation target (no visited unowned system in
jump range) sit permanently in fleet. Their maintenance consumes the entire
surplus. Treasury stagnates. No new useful ships can be built. The polity is
economically frozen.

### The fix

**CT build cap:** never build a CT when `n_colony_transports ≥ max(2, n_colonies)`.
One CT per settled colony plus a spare. This matches the one-trip-then-destroyed
model — you need one delivery pipeline per active target, not a fleet of them.

**Reduced idle maintenance:** CTs awaiting deployment at a friendly system pay
0.1 RU/tick (down from 0.5). This is half the scout rate. CTs in transit pay
full 0.5 RU/tick. "Idle" means `fleet.system_id IS NOT NULL` and
`fleet.status = 'active'`. This prevents the accumulation from being an
economic death sentence if it happens during a build run.

The cap is the primary fix; reduced idle maintenance is a safety valve.

---

## Failure mode 2: Low homeworld potential with military fleets

### What happens

World potential is derived from physical parameters (HZ position, atmosphere,
hydrosphere, body mass). Some homeworlds — notably Kreeth, Kraathi, and
Oceania — have potential scores of 7–8. At controlled/dev5, production is
`8 × 1.0 × 1.5 = 12 RU/tick`. A minimal military fleet (2 capitals, 3
escorts, 2 scouts) costs 6.2 RU/tick maintenance. A homeworld fleet also
carries SDBs (4–6 × 0.5 = 2–3 RU/tick). Total maintenance easily exceeds 12,
putting these polities in permanent deficit from tick 1.

This is not intentional game design — it punishes polities for having
astronomically accurate homeworlds that happen to score low on the potential
formula.

### The fix

**Homeworld potential floor:** during `init_game`, enforce a minimum
`world_potential ≥ 25` for the homeworld body of each polity. This represents
the millennia of industrial development a species would have achieved before
reaching interstellar capability. The physical data drives biology and
habitability; the economic floor reflects civilisational maturity.

At potential=25, controlled/dev5 production is `25 × 1.5 = 37.5 RU/tick`,
comfortably above the starting fleet maintenance load.

**Optional: starting development level.** Consider setting homeworld
`development_level = 3` (not 5) at game start, and allowing it to grow to 5
naturally. This creates early-game growth the historian can observe. The floor
ensures it's never unviable even at dev=3 (25 × 1.0 = 25 RU/tick at dev 3
— still viable).

---

## Failure mode 3: Contested homeworld = irreversible economic death

### What happens

When a homeworld becomes contested, the control multiplier drops to 0.10,
reducing production to 10% of normal. A contested potential-20 homeworld
produces 3 RU/tick instead of 30. Military maintenance continues at full
rate. The polity bleeds −6 RU/tick with no path to recovery: a contested
world cannot advance development, cannot build ships for lack of funds,
and without ships cannot resolve the contest.

Eurasia and Eastasia both had their homeworld (Sol, body shared) contested
for ~4700 of 5000 ticks, accumulating −30,000 RU each. This is a
death-spiral with no exit.

### The fix

**Revised contested multiplier: 0.35** (up from 0.10). Rationale: contested
does not mean the planetary economy ceases to function — it means production
is disrupted, not destroyed. War imposes costs in maintenance and attrition,
not an 90% economic collapse. Compare: a real wartime economy typically
operates at 60–80% of peacetime capacity even under siege conditions.

At 0.35 a contested potential-20 homeworld produces `20 × 0.35 × dev_mult`
RU/tick — roughly 10.5 at dev=0 rising to 10.5 at dev=1. Enough to
sustain a minimal fleet while prosecuting the war, rather than spiraling
to bankruptcy.

**Revised control multipliers (all):**

| Control state | Current | Proposed | Rationale |
|---|---|---|---|
| outpost | 0.10 | 0.20 | An outpost IS doing extractive work |
| colony | 0.40 | 0.55 | Growing colony, active resource flow |
| controlled | 1.00 | 1.00 | Unchanged |
| contested | 0.10 | 0.35 | Disruption, not collapse |

---

## Failure mode 4: No budget constraint — infinite debt

### What happens

There is no consequence to negative treasury beyond being unable to issue
new build orders (checked in `_score_build_hull` and `_execute_build_hull`).
A polity that goes negative continues to pay maintenance, continues to deduct
from treasury, and accumulates debt without limit. After 5000 ticks Kreeth
Dominion sits at −23,805 RU with no mechanism to recover or be penalised.

### The fix

**Maintenance shortfall cascade.** When treasury goes below a threshold, apply
a maintenance shortfall in order:

1. **Warning zone** (`treasury < 0`): no new build orders placed (already
   enforced). No change.

2. **Stress zone** (`treasury < −50`): logistics hulls (CTs, transports) at
   idle stations are placed into reserve — status `reserved`, maint halved
   to 0.1/tick. This is the automatic "moth-ball" response.

3. **Crisis zone** (`treasury < −200`): one surplus logistics hull is scrapped
   per tick (treasury += build_cost × 0.3 as scrap value). Priority:
   CTs first, then transports. This provides a path back to solvency.

4. **Collapse zone** (`treasury < −1000`): combat ratings degrade as
   crews go unpaid. Hulls receive a −1 to attack and defence (minimum 0)
   until treasury recovers above −200. Log event `economic_collapse`.

These thresholds may need tuning after the first revamp run. The cascade
ensures there is always an exit from a debt spiral, even if it means losing
ships.

---

## Summary of proposed changes

### Formula changes

```
Production per presence = world_potential × control_mult × dev_mult

control_mult:
  outpost    0.20  (was 0.10)
  colony     0.55  (was 0.40)
  controlled 1.00  (unchanged)
  contested  0.35  (was 0.10)

dev_mult (unchanged):
  0 → 0.5,  1 → 0.7,  2 → 0.9,  3 → 1.0,  4 → 1.2,  5 → 1.5
```

### Init changes

- Homeworld `world_potential` floor: 25 during `init_game`
- Homeworld `development_level`: consider starting at 3 instead of 5 to
  allow observable growth (optional — discuss before implementing)

### Decision engine changes

- CT build cap: `if n_colony_transports >= max(2, n_colonies): return −99.0`
  in `_score_build_hull`
- CT snapshot: `GameStateSnapshot` needs `n_colony_transports` field

### Maintenance changes

- Idle CT maintenance: 0.1 RU/tick (was 0.5) when at friendly system
- `pay_maintenance` needs to distinguish idle vs in-transit CT hulls

### Budget constraint changes

- Add `treasury_stress_check(conn, polity_id, tick)` called each Economy phase
- Implements warning/stress/crisis/collapse cascade above

---

## Expected post-revamp balance

With these changes, re-run the diagnostic estimates for a typical mid-range
polity (potential=20 homeworld, controlled/dev=5):

```
Production:              20 × 1.0 × 1.5 = 30.0 RU/tick (unchanged)
Military fleet maint:    ~8.0 RU/tick (2 capital, 2 cruiser, 4 escort)
Scout maint:             ~0.5 RU/tick (5 scouts × 0.1)
SDB maint:               ~2.0 RU/tick (4 SDB × 0.5)
CT maint (cap=2):        0.2 RU/tick (2 idle CTs × 0.1)
Net surplus:             ~19.3 RU/tick available for builds and outposts
```

A polity with 2 outpost colonies (potential=10 avg, outpost mult=0.20, dev=1):
```
Additional production:   2 × 10 × 0.20 × 0.7 = 2.8 RU/tick
```

Total: ~22 RU/tick surplus once established, enough to fund ship construction
every 2–4 ticks and accumulate a reserve buffer. War remains expensive (contested
multiplier still cuts homeworld production by 65%) but not instantly fatal.

Low-potential polities (potential=10 homeworld, floor prevents <25):
After floor enforcement this case no longer exists.

---

## Implementation order

1. **CT cap** in `actions.py` `_score_build_hull` (one-line guard, immediate
   impact, no schema change)
2. **Revised control multipliers** in `game/economy.py` (two constants changed)
3. **Homeworld potential floor** in `game/init_game.py` (requires fresh run)
4. **Idle CT maintenance** in `game/facade.py` `pay_maintenance` (requires
   checking fleet location)
5. **Budget constraint cascade** in `game/facade.py` or new `game/budget.py`
   (most complex; implement after verifying items 1–4 stabilise the run)

Items 1 and 2 can be applied to an existing `game.db` (resume run). Items 3
and 4 need a fresh run. Item 5 is new infrastructure.
