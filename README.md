# starscape5

## Ultimate objective:
A star empire simulator

## Claude created details.
A Python toolkit for enriching a stellar database with derived physical properties.
Operates on a SQLite database of stars drawn from Hipparcos and related catalogs,
adding spectral classifications, physical parameters, and companion star systems.

## What it does

| Script | Description |
|---|---|
| `scripts/fill_spectral.py` | Fills NULL spectral types in `IndexedIntegerDistinctStars` from B-V color index and absolute magnitude. Probabilistically generates companion stars for singleton systems based on observed multiplicity rates. |
| `scripts/compute_metrics.py` | Derives mass, temperature, radius, luminosity, and age for every star and writes them to `DistinctStarsExtended`. Resumable; stops after a configurable time limit. |

## Database

The target database is a SQLite file containing ~1.8 million stars:

```
/Volumes/Data/starscape4/sqllite_database/starscape.db
```

Key tables:

- **`IndexedIntegerDistinctStars`** — source catalog (`system_id`, `star_id`, `hip`, `ci`, `absmag`, `spectral`, `source`)
- **`DistinctStarsExtended`** — derived physical parameters (`star_id`, `mass`, `temperature`, `radius`, `luminosity`, `age`)

## Setup

Requires Python ≥ 3.14 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/lentulus/starscapeAI.git
cd starscape5
uv sync
```

## Usage

**Back up the database first:**
```bash
sqlite3 starscape.db ".backup starscape.db.bak"
```

**Fill spectral types:**
```bash
uv run scripts/fill_spectral.py --dry-run        # preview
uv run scripts/fill_spectral.py                   # run
uv run scripts/fill_spectral.py --batch-size 500
```

**Compute stellar metrics** (resumable, stops after 60 min by default):
```bash
uv run scripts/compute_metrics.py
uv run scripts/compute_metrics.py --max-minutes 120
```

Keep the system awake for long runs:
```bash
caffeinate -i uv run scripts/compute_metrics.py --max-minutes 600
```

## Project layout

```
src/starscape5/
    spectral.py     B-V → spectral type, multiplicity helpers
    metrics.py      Mass, temperature, radius, luminosity, age derivations
    db.py           SQLite connection helpers
scripts/
    fill_spectral.py
    compute_metrics.py
specs/              Feature design documents
tests/
sql/                Schema definitions
```

## Physical methods

| Quantity | Method |
|---|---|
| Temperature | Ballesteros (2012) formula from B-V |
| Luminosity | $M_\odot = 4.83$, $L/L_\odot = 10^{(4.83 - M_v)/2.5}$ |
| Radius | Stefan-Boltzmann: $R/R_\odot = \sqrt{L} \cdot (5778/T)^2$ |
| Mass | Piecewise MS mass-luminosity inversion (Duric 2004) |
| Age | MS lifetime: $t \approx 10^{10} \cdot M/L$ yr |
| Spectral type | B-V boundaries (OBAFGKM), subtype 0–9, luminosity class I/III/V from $M_v$ |
| Multiplicity | Survey rates by spectral class (Raghavan et al. 2010; Duchêne & Kraus 2013) |

## Running tests

```bash
uv run pytest
```
