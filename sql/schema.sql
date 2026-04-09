-- starscape5 schema
-- Run once to initialise the database.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Example table — replace with your own schema.
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    payload   TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Planets and moons.
-- Planets orbit a star (orbit_star_id set, orbit_body_id NULL).
-- Moons orbit a planet (orbit_body_id set, orbit_star_id NULL).
-- Physical: mass in Earth masses, radius in Earth radii.
-- Orbital elements in AU (semi_major_axis) and radians (angles).
-- density and gravity are derived on the fly: not stored.
CREATE TABLE IF NOT EXISTS "Bodies" (
    "body_id"          INTEGER PRIMARY KEY,
    "body_type"        TEXT    NOT NULL CHECK(body_type IN ('planet','moon','belt','planetoid')),
    "mass"             REAL,    -- Earth masses (Mₑ)
    "radius"           REAL,    -- Earth radii (Rₑ)
    "orbit_star_id"    INTEGER REFERENCES "IndexedIntegerDistinctStars"("star_id"),
    "orbit_body_id"    INTEGER REFERENCES "Bodies"("body_id"),
    "semi_major_axis"  REAL    NOT NULL,  -- AU
    "eccentricity"     REAL    NOT NULL,
    "inclination"      REAL    NOT NULL,  -- radians
    "longitude_ascending_node" REAL NOT NULL,  -- radians
    "argument_periapsis"       REAL NOT NULL,  -- radians
    "mean_anomaly"     REAL    NOT NULL,  -- radians at epoch
    "epoch"            INTEGER NOT NULL DEFAULT 0,
    "in_hz"            INTEGER,            -- 1 if in host star HZ, 0 if not, NULL for moons
    "possible_tidal_lock" INTEGER,         -- 1 if within tidal-lock zone, 0 if not, NULL for belts/planetoids
    "planet_class"     TEXT,               -- 'rocky'|'small_gg'|'medium_gg'|'large_gg'; NULL for moons/belts/planetoids
    "has_rings"        INTEGER,            -- 1 if planet has rings, 0 if not; NULL for non-planets
    "comp_metallic"    REAL,               -- fraction of belt mass that is metallic; NULL for non-belts
    "comp_carbonaceous" REAL,              -- fraction of belt mass that is carbonaceous/icy; NULL for non-belts
    "comp_stony"       REAL,               -- fraction of belt mass that is stony/silicate; NULL for non-belts
    "span_inner_au"    REAL,               -- inner edge of 80%-mass belt span (AU); NULL for non-belts
    "span_outer_au"    REAL,               -- outer edge of 80%-mass belt span (AU); NULL for non-belts
    "surface_gravity"  REAL,               -- g-units (1 = Earth); NULL until generate_atmosphere.py run
    "escape_velocity_kms" REAL,            -- km/s; NULL until generate_atmosphere.py run
    "t_eq_k"           REAL,               -- blackbody equilibrium temperature (K); NULL until generate_atmosphere.py run
    CHECK (
        (orbit_star_id IS NOT NULL AND orbit_body_id IS NULL) OR
        (orbit_star_id IS NULL     AND orbit_body_id IS NOT NULL)
    )
);

-- Keplerian orbital elements for companion stars in multiple systems.
-- One row per companion; primary stars (most massive) have no row.
-- semi_major_axis in AU; angles in radians; epoch in game-time units (0 = game start).
-- Position at game time t: M(t) = mean_anomaly + n*(t - epoch), n = 2π/period.
CREATE TABLE IF NOT EXISTS "StarOrbits" (
    "star_id"                  INTEGER PRIMARY KEY,  -- orbiting companion
    "primary_star_id"          INTEGER NOT NULL,     -- most massive star in system (stationary)
    "semi_major_axis"          REAL    NOT NULL,     -- AU
    "eccentricity"             REAL    NOT NULL,     -- [0, 1)
    "inclination"              REAL    NOT NULL,     -- radians
    "longitude_ascending_node" REAL    NOT NULL,     -- radians
    "argument_periapsis"       REAL    NOT NULL,     -- radians
    "mean_anomaly"             REAL    NOT NULL,     -- radians, defined at epoch
    "epoch"                    INTEGER NOT NULL DEFAULT 0  -- game time of mean_anomaly definition
);

-- Sophont species definitions.
-- One row per species; static for the ~4×10⁴ year simulation horizon.
-- Physical stats describe species averages; caste variation is not modelled here.
-- homeworld_body_id is NULL until the homeworld body is seeded in Bodies.
-- body_plan vocab extended beyond the original spec to cover hand-authored species.
CREATE TABLE IF NOT EXISTS "Species" (
    -- Identity
    "species_id"          INTEGER PRIMARY KEY,
    "name"                TEXT    NOT NULL UNIQUE,
    "homeworld_body_id"   INTEGER REFERENCES "Bodies"("body_id"),

    -- Physical description
    "body_plan"           TEXT    CHECK(body_plan IN (
                              'bilateral','radial','colonial','amorphous','exotic',
                              'centauroid','cephalopod','avian','vermiform','draconic')),
    "locomotion"          TEXT    CHECK(locomotion IN (
                              'bipedal','quadrupedal','sessile','aquatic','aerial','mixed',
                              'hexapedal','jet_aquatic','winged_flight','arboreal','vermiform')),
    "avg_mass_kg"         REAL,
    "avg_height_m"        REAL,
    "lifespan_years"      REAL,

    -- Environmental tolerances
    "temp_min_k"          REAL,
    "temp_max_k"          REAL,
    "pressure_min_atm"    REAL,
    "pressure_max_atm"    REAL,
    "atm_req"             TEXT    CHECK(atm_req IN (
                              'n2o2','co2','methane','any','vacuum','reducing','aquatic')),

    -- Diet and metabolism
    "diet_type"           TEXT    CHECK(diet_type IN (
                              'herbivore','carnivore','omnivore','detritivore',
                              'chemotroph','phototroph','parasitic','parasite')),
    "diet_flexibility"    REAL    CHECK(diet_flexibility BETWEEN 0.0 AND 1.0),
    "metabolic_rate"      TEXT    CHECK(metabolic_rate IN ('low','medium','high','very_high','variable')),

    -- Reproduction
    "repro_strategy"      TEXT    CHECK(repro_strategy IN ('r_strategist','k_strategist')),
    "gestation_years"     REAL,
    "maturity_years"      REAL,
    "offspring_per_cycle" REAL,
    "repro_cycles_per_life" REAL,

    -- Behavioural disposition (0.0–1.0)
    "risk_appetite"       REAL    CHECK(risk_appetite BETWEEN 0.0 AND 1.0),
    "aggression"          REAL    CHECK(aggression BETWEEN 0.0 AND 1.0),
    "expansionism"        REAL    CHECK(expansionism BETWEEN 0.0 AND 1.0),
    "xenophilia"          REAL    CHECK(xenophilia BETWEEN 0.0 AND 1.0),
    "adaptability"        REAL    CHECK(adaptability BETWEEN 0.0 AND 1.0),

    -- Social cohesion and fracture risk (0.0–1.0)
    "social_cohesion"     REAL    CHECK(social_cohesion BETWEEN 0.0 AND 1.0),
    "hierarchy_tolerance" REAL    CHECK(hierarchy_tolerance BETWEEN 0.0 AND 1.0),
    "faction_tendency"    REAL    CHECK(faction_tendency BETWEEN 0.0 AND 1.0),
    "grievance_memory"    REAL    CHECK(grievance_memory BETWEEN 0.0 AND 1.0)
);

-- Mutable atmospheric and hydrospheric state for planets and moons.
-- One row per body; updated each tick as atmosphere/climate evolves or terraforming progresses.
-- Only populated for rocky planets and moons (gas giants have no meaningful surface).
-- Populated by generate_atmosphere.py; updated in-place by the simulation engine.
CREATE TABLE IF NOT EXISTS "BodyMutable" (
    "body_id"          INTEGER PRIMARY KEY REFERENCES "Bodies"("body_id"),
    "atm_type"         TEXT,    -- 'none'|'trace'|'thin'|'standard'|'dense'|'corrosive'|'exotic'
    "atm_pressure_atm" REAL,    -- surface pressure in Earth atmospheres; 0.0 for none
    "atm_composition"  TEXT,    -- dominant gas tag: 'none'|'co2'|'n2o2'|'methane'|'h2so4'|'mixed'
    "surface_temp_k"   REAL,    -- post-greenhouse surface temperature (K)
    "hydrosphere"      REAL,    -- ocean/ice fraction 0.0–1.0; NULL if corrosive or no atmosphere
    "epoch"            INTEGER NOT NULL DEFAULT 0  -- game tick of last update
);
