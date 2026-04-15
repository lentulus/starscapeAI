#!/usr/bin/env python3
"""Generate prose homeworld environment descriptions and append them to species articles.

Queries each species' homeworld from the DB, assembles the physical context
(star type, orbit, gravity, surface conditions), then calls the Claude API to
write a 2–3 paragraph description in the voice of the existing articles.

The generated section is appended to articles/Species/<name>.md, separated by
a horizontal rule. Use --dry-run to print to stdout without modifying files.

Usage:
    uv run scripts/generate_homeworld_prose.py --dry-run
    uv run scripts/generate_homeworld_prose.py
    uv run scripts/generate_homeworld_prose.py --species Human Kreeth
    uv run scripts/generate_homeworld_prose.py --db /path/to/other.db
"""

import argparse
import logging
import sqlite3
import textwrap
from pathlib import Path

import anthropic

DEFAULT_DB = Path("/Volumes/Data/starscape4/starscape.db")
ARTICLES_DIR = Path(__file__).parent.parent / "articles" / "Species"
MODEL = "claude-sonnet-4-6"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style reference: excerpt from an existing article, given to the model
# ---------------------------------------------------------------------------

STYLE_REFERENCE = textwrap.dedent("""\
    The following is an excerpt from the article on Humans, showing the
    voice and register to match:

    ---
    They are, physically, unremarkable. Bilateral, bipedal, endothermic, mid-range in
    mass and height, short-lived by the standards of their neighbours. They have no
    unusual sensory capability, no exoskeletal armour, no biological weapons, no
    collective cognition. In any direct physical comparison with most of the species
    they share this region of space with, they are not the largest, not the fastest,
    not the most resilient.
    ---

    And from the article on Kreeth:

    ---
    You will not meet a Kreeth. Not in the sense that matters. What you will meet, if
    you are unlucky, is a Kreeth warrior unit — exoskeletal, six-limbed, low to the
    ground, built for tunnel warfare and open assault with equal indifference. It will
    not be curious about you. It will not be hostile toward you in any way that involves
    recognition. You are terrain.
    ---
""")

# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

HOMEWORLD_QUERY = """
SELECT
    sp.name                         AS species_name,
    sp.body_plan,
    sp.locomotion,
    sp.avg_mass_kg,
    sp.avg_height_m,
    sp.lifespan_years,
    sp.temp_min_k,
    sp.temp_max_k,
    sp.pressure_min_atm,
    sp.pressure_max_atm,
    sp.atm_req,
    sp.diet_type,
    sp.metabolic_rate,

    b.body_id                       AS homeworld_body_id,
    b.mass                          AS planet_mass_me,
    b.radius                        AS planet_radius_re,
    b.semi_major_axis               AS orbit_au,
    b.in_hz,
    b.possible_tidal_lock,
    b.planet_class,

    bm.atm_type,
    bm.atm_pressure_atm,
    bm.atm_composition,
    bm.surface_temp_k,
    bm.hydrosphere,

    b.surface_gravity               AS surface_gravity_g,
    b.escape_velocity_kms,
    b.t_eq_k,

    i.spectral                      AS star_spectral,
    e.luminosity                    AS star_luminosity,
    e.temperature                   AS star_temp_k,
    e.mass                          AS star_mass_ms

FROM Species sp
JOIN Bodies b          ON b.body_id  = sp.homeworld_body_id
LEFT JOIN BodyMutable bm ON bm.body_id = b.body_id
JOIN IndexedIntegerDistinctStars i ON i.star_id = b.orbit_star_id
LEFT JOIN DistinctStarsExtended e  ON e.star_id = b.orbit_star_id
WHERE sp.homeworld_body_id IS NOT NULL
ORDER BY sp.species_id
"""


def fetch_homeworlds(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(HOMEWORLD_QUERY).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Prose prompt assembly
# ---------------------------------------------------------------------------

def _star_description(row: dict) -> str:
    """Human-readable star context for the prompt."""
    spectral = row["star_spectral"] or "unknown"
    lum = row["star_luminosity"]
    temp = row["star_temp_k"]
    parts = [f"spectral type {spectral}"]
    if lum:
        if lum > 2.0:
            parts.append(f"luminosity {lum:.1f} L☉ (significantly brighter than Sol)")
        elif lum > 1.1:
            parts.append(f"luminosity {lum:.2f} L☉ (somewhat brighter than Sol)")
        elif lum > 0.9:
            parts.append(f"luminosity {lum:.2f} L☉ (near-solar)")
        elif lum > 0.5:
            parts.append(f"luminosity {lum:.2f} L☉ (dimmer than Sol)")
        else:
            parts.append(f"luminosity {lum:.2f} L☉ (much dimmer than Sol)")
    if temp:
        parts.append(f"surface temperature {temp:.0f} K")
    return ", ".join(parts)


def _planet_description(row: dict) -> str:
    """Human-readable planet context for the prompt."""
    parts = []
    if row["planet_mass_me"]:
        parts.append(f"mass {row['planet_mass_me']:.2f} Mₑ")
    if row["planet_radius_re"]:
        parts.append(f"radius {row['planet_radius_re']:.2f} Rₑ")
    if row["orbit_au"]:
        parts.append(f"semi-major axis {row['orbit_au']:.3f} AU")
    if row["surface_gravity_g"]:
        parts.append(f"surface gravity {row['surface_gravity_g']:.2f} g")
    if row["escape_velocity_kms"]:
        parts.append(f"escape velocity {row['escape_velocity_kms']:.1f} km/s")
    if row["t_eq_k"]:
        parts.append(f"equilibrium temperature {row['t_eq_k']:.0f} K")
    if row["in_hz"]:
        parts.append("within habitable zone")
    return ", ".join(parts)


def _surface_description(row: dict) -> str:
    """Human-readable surface conditions for the prompt."""
    parts = []
    if row["atm_type"]:
        parts.append(f"atmosphere type: {row['atm_type']}")
    if row["atm_pressure_atm"] is not None:
        parts.append(f"surface pressure {row['atm_pressure_atm']:.2f} atm")
    if row["atm_composition"]:
        parts.append(f"dominant composition: {row['atm_composition']}")
    if row["surface_temp_k"]:
        c = row["surface_temp_k"] - 273.15
        parts.append(f"mean surface temperature {row['surface_temp_k']:.0f} K ({c:.0f} °C)")
    if row["hydrosphere"] is not None:
        parts.append(f"hydrosphere coverage {row['hydrosphere']*100:.0f}%")
    return ", ".join(parts)


def _species_context(row: dict) -> str:
    """Key species traits relevant to how they experience their homeworld."""
    parts = []
    if row["body_plan"]:
        parts.append(f"body plan: {row['body_plan']}")
    if row["locomotion"]:
        parts.append(f"locomotion: {row['locomotion']}")
    if row["avg_mass_kg"]:
        parts.append(f"mass: {row['avg_mass_kg']:.0f} kg")
    if row["atm_req"]:
        parts.append(f"atmosphere requirement: {row['atm_req']}")
    if row["temp_min_k"] and row["temp_max_k"]:
        lo = row["temp_min_k"] - 273.15
        hi = row["temp_max_k"] - 273.15
        parts.append(f"comfortable temperature range: {lo:.0f}–{hi:.0f} °C")
    if row["diet_type"]:
        parts.append(f"diet: {row['diet_type']}")
    if row["metabolic_rate"]:
        parts.append(f"metabolic rate: {row['metabolic_rate']}")
    return ", ".join(parts)


def build_prompt(row: dict) -> str:
    name = row["species_name"]
    return textwrap.dedent(f"""\
        You are writing an entry for a hard science fiction worldbuilding encyclopaedia.
        The writing style is that of a dry, precise external analyst — clear, slightly
        clinical, occasionally sardonic, with no filler phrases and no emotional register
        beyond the understated. Long sentences with subordinate clauses are fine.
        No bullet points. No headers. Continuous prose only.

        {STYLE_REFERENCE}

        ---

        Write 2–3 paragraphs describing the homeworld of the {name}. This section will
        be appended to an existing species article, so do not introduce the species —
        begin directly with the world itself. The section heading will be added separately;
        write only the body paragraphs.

        Cover: what kind of star it orbits and what that means for light and sky colour;
        the planet's gravity and what that implies for the landscape and the species'
        physique; the atmosphere and surface conditions; the hydrosphere. Where the
        physical parameters imply something specific about how the {name} evolved or
        live — a high-gravity body producing dense musculature, an orange sun shifting
        the colour palette of photosynthetic life, deep oceans as the primary biosphere —
        draw that connection explicitly. The description should feel like it was written
        by someone who has analysed the world from orbit and understands what the numbers
        mean for biology and culture, not someone describing a tourist destination.

        Species context (use to inform the description, do not list directly):
        {_species_context(row)}

        Homeworld star:
        {_star_description(row)}

        Homeworld planet:
        {_planet_description(row)}

        Surface conditions:
        {_surface_description(row)}
    """)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def generate_prose(client: anthropic.Anthropic, row: dict) -> str:
    prompt = build_prompt(row)
    message = client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def article_path(species_name: str) -> Path:
    return ARTICLES_DIR / f"{species_name.lower()}.md"


def append_to_article(path: Path, prose: str, dry_run: bool) -> None:
    section = f"\n\n---\n\n## Homeworld\n\n{prose}\n"
    if dry_run:
        print(f"\n{'='*60}")
        print(f"  {path.name}")
        print('='*60)
        print(section)
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(section)
        log.info("  Appended to %s", path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print generated prose to stdout without modifying files")
    parser.add_argument("--species", nargs="+", metavar="NAME",
                        help="Only process these species (default: all)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    rows = fetch_homeworlds(args.db)
    if not rows:
        raise SystemExit("No species with homeworld_body_id set. Run seed_homeworlds.py first.")

    if args.species:
        names = {n.lower() for n in args.species}
        rows = [r for r in rows if r["species_name"].lower() in names]
        if not rows:
            raise SystemExit(f"No matching species found for: {args.species}")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

    for row in rows:
        name = row["species_name"]
        path = article_path(name)
        if not path.exists():
            log.warning("Article not found for %s (%s) — skipping", name, path)
            continue

        log.info("Generating homeworld prose for %s...", name)
        prose = generate_prose(client, row)
        append_to_article(path, prose, args.dry_run)

    if not args.dry_run:
        log.info("Done.")


if __name__ == "__main__":
    main()
