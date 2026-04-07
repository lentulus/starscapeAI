# Fill Stars — Synthetic Catalog Completion

## Quick-start — complete run order

All scripts default to `/Volumes/Data/starscape4/sqllite_database/starscape.db`.
Use `--db /path/to/other.db` only when targeting a different database.

```bash
# 0. Back up first
DB=/Volumes/Data/starscape4/sqllite_database/starscape.db
sqlite3 "$DB" ".backup ${DB}.bak"

# 1. Analyse completeness BEFORE fill (optional but recommended)
uv run scripts/analyze_completeness.py

# 2. Dry-run: preview how many systems/stars will be added per 100 pc shell
uv run scripts/fill_stars.py --dry-run

# 3. Fill synthetic stars (resumable; re-run if interrupted)
#    Observed insert rate on external drive: ~18–40 systems/s.
#    Estimated deficit ~670K systems → expect 5–10 hours total.
#    Run in sessions; each re-run resumes from where it left off.
caffeinate -i uv run scripts/fill_stars.py --max-minutes 600

# 4. Analyse completeness AFTER fill to verify the density profile is now smooth
uv run scripts/analyze_completeness.py

# 5. Fill spectral types for any remaining NULL rows
uv run scripts/fill_spectral.py

# 6. Compute stellar metrics (mass, temperature, radius, luminosity)
caffeinate -i uv run scripts/compute_metrics.py --max-minutes 600

# 7. Compute orbital elements for ALL multiple systems (including new fill systems)
#    Observed rate: ~18.5 systems/s on external drive.
#    ~693K original systems + ~87K new fill multiples ≈ 10–12 hours total.
#    Run in sessions; already-processed systems are skipped.
caffeinate -i uv run scripts/compute_orbits.py --max-minutes 600

# 8. Seed the real solar system for star_id=1
uv run scripts/seed_sol.py

# 9. Generate planets and moons for all stars
caffeinate -i uv run scripts/generate_planets.py --max-minutes 600
```

> **All scripts are resumable.** Re-run the same command after any interruption;
> already-processed rows are skipped automatically.
>
> **Observed throughput (external USB drive, Mac mini):**
> `compute_orbits` ran at ~18.5 systems/s (126K systems in 1h 54m).
> `fill_stars` does less computation per system so expect ~30–40 sys/s.
> Plan for multiple sessions across 1–2 days for the full pipeline.

---

## Overview

The Hipparcos-derived source catalog is magnitude-limited: M dwarfs become invisible beyond
~100 pc, G dwarfs beyond ~300 pc, only luminous hot stars survive to 1000+ pc. The far
reaches of the 2000 pc simulation cube are therefore nearly empty when physically they should
not be. This module fills the deficit so every 100 pc³ cell matches the expected stellar
density of the double-exponential galactic disk model.

### High-level algorithm

1. **Model the expected density.** The galactic disk density profile as a function of height
   above the galactic plane $z_\text{gal}$ is:

   $$\rho(z) = \rho_0 \left[ f_1\, e^{-|z_\text{gal}|/h_1} + f_2\, e^{-|z_\text{gal}|/h_2} \right]$$

   Parameters: $\rho_0 = 0.14\,\text{pc}^{-3}$, thin disk $h_1 = 300\,\text{pc}$, $f_1 = 0.86$;
   thick disk $h_2 = 1000\,\text{pc}$, $f_2 = 0.14$.

2. **Rotate coordinates.** The database stores ICRS equatorial Cartesian milliparsecs (x toward
   RA 0h, y toward RA 6h, z toward Dec +90°). A fixed 3×3 IAU matrix converts them to galactic
   Cartesian, where the z-component is height above the galactic plane.

3. **Grid the cube.** Divide the 2000 pc cube (−1000 to +1000 pc around Sol) into 20×20×20
   cells of 100 pc each. Clip to the inscribed sphere (radius 1000 pc) to avoid unphysical
   corner cells.

4. **Compute the deficit.** For each cell: Monte Carlo-integrate `density × cell_volume` to
   get `expected`. Count existing catalog stars in the cell (`observed`). If
   `deficit = expected − observed > 0`, generate that many synthetic stars.

5. **Draw star properties.** For each synthetic star draw a spectral class from IMF weights
   (M 76.5%, K 12.1%, G 7.6%, F 3.0%, A 0.6%, B 0.13%, O 0.003%), then draw a matching
   `absmag` and `ci` from per-class Gaussians.

6. **Allow multiple systems.** After generating all single-star row inserts, apply the same
   multiplicity logic used by `fill_spectral.py` (`should_create_multiple`) — companion rows
   share the `system_id` and are inserted with distinct `star_id` values. This means
   `fill_spectral.py` will have nothing extra to do for these stars (they arrive with
   `spectral` already set to NULL, ready for the normal pipeline).

7. **Insert and continue the pipeline.** New rows land in `IndexedIntegerDistinctStars`
   (`source = 'fill'`) and `IndexedIntegerDistinctSystems`. All downstream scripts
   (`fill_spectral.py`, `compute_metrics.py`, `compute_orbits.py`, `generate_planets.py`)
   treat fill stars identically to catalog stars.

---

## Requirements

- Grid the cube into 100 pc cells; clip to 1000 pc sphere.
- Per cell: compute expected count from disk model; count existing stars; insert deficit.
- Spectral class drawn from IMF weights; `absmag` and `ci` from per-class Gaussians.
- New positions drawn from weighted rejection sampling within the cell (respects sub-cell
  density gradient).
- Multiple system generation: apply `should_create_multiple(spectral)` per primary; companion
  drawn via `companion_absmag` / `ci_from_absmag` / `format_spectral` as in `fill_spectral.py`;
  companion shares `system_id`; companion `spectral` set to derived type immediately.
- Write `spectral` and `source='fill'` for primaries too so `fill_spectral.py` need not
  re-process them (though it will harmlessly skip the non-NULL rows).
- Dry-run mode: print a table of radial shells (0–100 pc, 100–200 pc, …) showing existing
  systems, expected systems, and deficit systems/stars without writing to the DB. Uses a
  seeded RNG so forecasted counts match what production will insert.
- Resume support: cells already at or above `expected` count are skipped. `--max-minutes`
  stops cleanly; re-run to continue.
- No new tables; no schema changes.

---

## Data / Schema

No schema changes. Uses existing tables:

```sql
TABLE "IndexedIntegerDistinctSystems" (
    "system_id" INTEGER PRIMARY KEY,
    "x"         INTEGER,   -- ICRS equatorial Cartesian mpc; X toward RA 0h Dec 0°
    "y"         INTEGER,   -- Y toward RA 6h Dec 0°
    "z"         INTEGER    -- Z toward Dec +90° (celestial north pole)
)

TABLE "IndexedIntegerDistinctStars" (
    "system_id" INTEGER,
    "star_id"   INTEGER,
    "hip"       TEXT,      -- NULL for fill stars
    "ci"        TEXT,
    "absmag"    REAL,
    "spectral"  TEXT,      -- set to derived type; fill_spectral.py skips non-NULL rows
    "source"    TEXT       -- 'fill' for synthetic stars
)
```

`source = 'fill'` is the provenance tag for all rows generated by this module.

---

## Module 1 — `src/starscape5/galaxy.py`

Shared library; no DB access.

**`eq_to_galactic_mpc(x, y, z)`** → `(x_gal, y_gal, z_gal)`
Apply the standard IAU equatorial-to-galactic rotation matrix (constants hard-coded):
```
R = [[-0.054876, -0.873437, -0.483835],
     [ 0.494109, -0.444830,  0.746982],
     [-0.867666, -0.198076,  0.455984]]
```
Input and output all in milliparsecs.

**`disk_density(x_mpc, y_mpc, z_mpc)`** → `stars / pc³`
Converts z_mpc to pc, applies the double-exponential formula above.

**`cell_expected_count(cell_center_mpc, cell_size_mpc, n_samples=200)`** → `float`
Monte Carlo integral: draw `n_samples` points uniformly in the cell, average
`disk_density()`, multiply by cell volume in pc³.

**`draw_spectral_class(rng)`** → `str` (single letter O–M)
IMF-weighted draw using `rng.choices`.

**`draw_absmag(cls, rng)`** → `float`
Gaussian: per-class (Mv_centre, σ=0.5). Centres: O −4.5, B −1.5, A +2.0, F +4.0,
G +5.5, K +7.5, M +11.0.

**`draw_ci(cls, rng)`** → `float`
Gaussian: per-class (BV_centre, σ=0.06). Centres: O −0.30, B −0.16, A +0.10, F +0.44,
G +0.65, K +1.05, M +1.45.

---

## Module 2 — `scripts/analyze_completeness.py`

Read-only diagnostic. No DB writes.

Joins `IndexedIntegerDistinctSystems` + `IndexedIntegerDistinctStars`, bins stars by distance
from Sol in 100 pc shells, computes observed density per shell, prints observed vs. expected
table, and estimates per-class completeness radius (where observed drops below 50% of model).
Used to validate fill before and after.

```
uv run scripts/analyze_completeness.py
uv run scripts/analyze_completeness.py --db /path/to/other.db
```

---

## Module 3 — `scripts/fill_stars.py`

Main fill script.

```
uv run scripts/fill_stars.py [--dry-run] [--db PATH] [--cell-size-pc 100]
                              [--batch-size 500] [--max-minutes 120]
                              [--seed 42]
```

`--seed` controls the RNG. Dry-run uses the same seed so output counts are reproducible
and will match what production inserts.

### Pseudocode

```
rng = Random(seed)

// Pre-load all existing system positions; bucket into 100 pc cells
cells = defaultdict(int)
for row in SELECT x, y, z FROM IndexedIntegerDistinctSystems:
    cell_key = (floor(x_pc / cell_size), floor(y_pc / cell_size), floor(z_pc / cell_size))
    cells[cell_key] += 1

next_system_id = MAX(system_id) + 1
next_star_id   = MAX(star_id)   + 1

totals_by_shell = defaultdict(lambda: {expected:0, existing:0, to_add:0, stars_to_add:0})

// Iterate all cells in 20x20x20 grid
for ix in -10..9, iy in -10..9, iz in -10..9:
    center_pc = ((ix+0.5)*cell_size, (iy+0.5)*cell_size, (iz+0.5)*cell_size)
    dist_pc = sqrt(center_pc^2)
    if dist_pc > 1000: continue          // sphere clip

    expected = cell_expected_count(center_pc, cell_size, rng, n_samples=200)
    existing = cells[(ix, iy, iz)]
    deficit  = max(0, round(expected) - existing)

    shell = floor(dist_pc / 100) * 100
    totals_by_shell[shell].expected  += expected
    totals_by_shell[shell].existing  += existing
    totals_by_shell[shell].to_add    += deficit   // system count
    // star count accounts for multiplicity; pre-estimate using avg multiplicity ~1.15
    totals_by_shell[shell].stars_to_add += deficit * avg_stars_per_system

    if dry_run: continue
    if deficit == 0: continue

    // Generate deficit systems in this cell
    for _ in range(deficit):
        // Position: rejection-sample within cell weighted by disk_density
        pos_mpc = weighted_position_in_cell(ix, iy, iz, cell_size, rng)

        cls      = draw_spectral_class(rng)
        absmag   = draw_absmag(cls, rng)
        ci       = draw_ci(cls, rng)
        spectral = format_spectral(f"{ci:.4f}", absmag)

        INSERT INTO IndexedIntegerDistinctSystems (next_system_id, x=pos_mpc.x, y=..., z=...)
        INSERT INTO IndexedIntegerDistinctStars
            (system_id=next_system_id, star_id=next_star_id, hip=NULL,
             ci, absmag, spectral, source='fill')

        // Maybe add a companion
        if should_create_multiple(spectral) and rng.random() confirms it:
            comp_absmag  = companion_absmag(absmag)
            comp_ci      = ci_from_absmag(comp_absmag)
            comp_spectral = format_spectral(f"{comp_ci:.4f}", comp_absmag)
            INSERT INTO IndexedIntegerDistinctStars
                (system_id=next_system_id, star_id=next_star_id+1, hip=NULL,
                 ci=comp_ci, absmag=comp_absmag, spectral=comp_spectral, source='fill')
            next_star_id += 2
        else:
            next_star_id += 1

        next_system_id += 1

    COMMIT every batch_size systems

if dry_run:
    PRINT table: shell | existing_systems | expected_systems | to_add | stars_to_add
```

---

## Run Order

Fill stars runs first; all subsequent pipeline steps process fill stars automatically.

1. `fill_stars.py`          ← **new; run before all others**
2. `fill_spectral.py`       ← skips fill stars already having `spectral != NULL`
3. `compute_metrics.py`
4. `compute_orbits.py`      ← will generate orbits for any fill multi-star systems
5. `seed_sol.py`
6. `generate_planets.py`

---

## Tests

- `test_eq_to_galactic_mpc` — known star (e.g. Sirius at RA 101.3°, Dec −16.7°, 2.64 pc)
  transforms to near-zero galactic latitude (|b| < 1°).
- `test_disk_density_midplane` — density at z_gal=0 ≈ 0.14 pc⁻³.
- `test_disk_density_falloff` — density at z_gal=300 pc ≈ 0.086 + 0.014·e⁻⁰·³ stays in range.
- `test_cell_expected_count` — 100 pc cell at origin has expected ≈ 140000 × cell_factor;
  result is stable within ±5% across different seeds at n_samples=200.
- `test_draw_spectral_class_distribution` — 10000 draws produce M fraction within 5% of 76.5%.
- `test_fill_stars_dry_run` — seed=42; capture stdout; total stars_to_add is consistent
  across two runs with the same seed.
- Integration: run against in-memory SQLite seeded with 10 catalog stars in 3 cells;
  verify deficit rows inserted; verify companion rows share system_id; re-run verifies
  resume skips already-filled cells.

## Notes

- Radial gradient of galactic disk density (toward/away from galactic centre) is ignored —
  ±1000 pc is ~12% variation on the 8500 pc galactocentric radius; acceptable.
- If the 2.47M target is not met, a `--density-scale` float multiplier can be added later.
- All fill stars arrive with `hip = NULL`.
- `fill_spectral.py` checks `WHERE spectral IS NULL` so companion stars generated here with
  derived spectral types will be skipped correctly.
- Back up database before running: `sqlite3 starscape.db ".backup starscape.db.bak"`
