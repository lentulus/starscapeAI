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

-- Planets, moons, belts, and planetoids.
-- Planets orbit a star (orbit_star_id set, orbit_body_id NULL).
-- Moons orbit a planet (orbit_body_id set, orbit_star_id NULL).
-- Orbital elements in AU (semi_major_axis) and radians (angles).
-- All atmosphere/surface columns are initial generation values; the simulation
-- updates them in-place (no separate mutable table).
CREATE TABLE IF NOT EXISTS "Bodies" (
    "body_id"          INTEGER PRIMARY KEY,
    "body_type"        TEXT    NOT NULL CHECK(body_type IN ('planet','moon','belt','planetoid')),

    -- Legacy physical columns (seed_sol.py uses these; superseded by WBH chain below)
    "mass"             REAL,    -- Earth masses (Mₑ)
    "radius"           REAL,    -- Earth radii (Rₑ)

    -- Orbital elements
    "orbit_star_id"    INTEGER REFERENCES "IndexedIntegerDistinctStars"("star_id"),
    "orbit_body_id"    INTEGER REFERENCES "Bodies"("body_id"),
    "semi_major_axis"  REAL    NOT NULL,  -- AU
    "eccentricity"     REAL    NOT NULL,
    "inclination"      REAL    NOT NULL,  -- radians
    "longitude_ascending_node" REAL NOT NULL,  -- radians
    "argument_periapsis"       REAL NOT NULL,  -- radians
    "mean_anomaly"     REAL    NOT NULL,  -- radians at epoch
    "epoch"            INTEGER NOT NULL DEFAULT 0,

    -- Classification
    "in_hz"            INTEGER,  -- 1 if in host star HZ; 0 otherwise; NULL for moons
    "possible_tidal_lock" INTEGER,  -- legacy boolean; superseded by tidal_lock_status
    "planet_class"     TEXT,     -- 'rocky'|'small_gg'|'medium_gg'|'large_gg'
    "has_rings"        INTEGER,  -- 1/0; NULL for non-planets

    -- Legacy belt composition columns (superseded by BeltProfile)
    "comp_metallic"    REAL,
    "comp_carbonaceous" REAL,
    "comp_stony"       REAL,
    "span_inner_au"    REAL,
    "span_outer_au"    REAL,

    -- Legacy derived physical columns (superseded by WBH chain below)
    "surface_gravity"  REAL,
    "escape_velocity_kms" REAL,
    "t_eq_k"           REAL,

    -- -----------------------------------------------------------------------
    -- WBH generation columns
    -- -----------------------------------------------------------------------

    -- Provenance
    "generation_source" TEXT CHECK(generation_source IN ('procedural','continuation_seed','manual')),
    "orbit_num"        REAL,       -- WBH Orbit# (logarithmic AU scale)

    -- Size and physical properties
    "size_code"        TEXT,       -- UWP size: 0–F, S, GS, GM, GL
    "diameter_km"      REAL,       -- actual diameter in km
    "composition"      TEXT,       -- Exotic Ice / Mostly Ice / Mostly Rock / Rock and Metal / Mostly Metal / Compressed Metal
    "density"          REAL,       -- relative to Terra (5.514 g/cm³ = 1.0)
    "gravity_g"        REAL,       -- surface gravity in g  (density × diameter_km/12742)
    "mass_earth"       REAL,       -- mass in Earth masses
    "escape_vel_kms"   REAL,       -- escape velocity km/s

    -- Atmosphere (initial state; updated in-place by simulation)
    "atm_type"         TEXT CHECK(atm_type IN ('none','trace','thin','standard','dense','corrosive','exotic')),
    "atm_pressure_atm" REAL,       -- surface pressure in Earth atmospheres
    "atm_composition"  TEXT,       -- 'none'|'co2'|'n2o2'|'methane'|'h2so4'|'mixed'
    "surface_temp_k"   REAL,       -- post-greenhouse surface temperature (K)
    "hydrosphere"      REAL,       -- ocean/ice fraction 0.0–1.0; NULL if no liquid possible

    -- Atmosphere detail
    "albedo"           REAL,       -- Bond albedo
    "greenhouse_factor" REAL,      -- WBH greenhouse multiplier
    "atm_code"         TEXT,       -- UWP atmosphere code 0–H
    "pressure_bar"     REAL,       -- atmospheric pressure in bar
    "ppo_bar"          REAL,       -- O₂ partial pressure in bar
    "gases"            TEXT,       -- gas composition string e.g. 'N2:78,O2:21,Ar:1'

    -- Atmospheric taints (up to 3; all NULL if clean)
    "taint_type_1"     TEXT,       -- L/R/B/G/P/S/H
    "taint_severity_1" INTEGER,    -- 1–9
    "taint_persistence_1" INTEGER, -- 2–9
    "taint_type_2"     TEXT,
    "taint_severity_2" INTEGER,
    "taint_persistence_2" INTEGER,
    "taint_type_3"     TEXT,
    "taint_severity_3" INTEGER,
    "taint_persistence_3" INTEGER,

    -- Hydrographics
    "hydro_code"       INTEGER,    -- UWP 0–10
    "hydro_pct"        REAL,       -- 0.0–100.0

    -- Temperature
    "mean_temp_k"      REAL,       -- WBH mean surface temperature (K)
    "high_temp_k"      REAL,       -- WBH §High and Low Temperatures: expected high (K)
    "low_temp_k"       REAL,       -- WBH §High and Low Temperatures: expected low (K)

    -- Rotation
    "sidereal_day_hours" REAL,     -- rotation period in hours; negative = retrograde
    "solar_day_hours"  REAL,       -- solar day in hours; NULL for 1:1/3:2 locked
    "axial_tilt_deg"   REAL,       -- axial tilt in degrees (0–180)
    "tidal_lock_status" TEXT CHECK(tidal_lock_status IN ('none','3:2','1:1','slow_prograde','slow_retrograde')),

    -- Seismic
    "seismic_residual" REAL,
    "seismic_tidal"    REAL,
    "seismic_heating"  REAL,
    "seismic_total"    REAL,
    "tectonic_plates"  INTEGER,    -- NULL = geologically dead

    -- Biology
    "biomass_rating"   INTEGER,    -- 0 = none, 10 = garden world (WBH A); NULL = not evaluated
    "biocomplexity_rating" INTEGER, -- WBH p.129: 0 = no life, 1 = microbes … 9 = sophonts; NULL = not evaluated
    "native_sophants"  TEXT CHECK(native_sophants IN ('none','extinct','current')),
                                   -- NULL if biocomplexity < 8 (not evaluated)
    "biodiversity_rating" INTEGER, -- WBH p.130: 1–10+ species richness; 0 = no life; NULL = not evaluated
    "compatibility_rating" INTEGER, -- WBH pp.130-131: 0 = incompatible, 10 = full Terran compat; NULL = no life
    "resource_rating"  INTEGER,    -- WBH p.131: 2–12 (C); NULL for gas giants and belts

    -- Moon orbital geometry (moons only)
    "moon_PD"          REAL,       -- orbital radius in planetary diameters
    "hill_PD"          REAL,       -- Hill sphere limit in PD
    "roche_PD"         REAL,       -- Roche limit in PD

    -- -----------------------------------------------------------------------
    CHECK (
        (orbit_star_id IS NOT NULL AND orbit_body_id IS NULL) OR
        (orbit_star_id IS NULL     AND orbit_body_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS "idx_bodies_orbit_star" ON "Bodies"("orbit_star_id");
CREATE INDEX IF NOT EXISTS "idx_bodies_orbit_body" ON "Bodies"("orbit_body_id");

-- Required for the init_systems.py batch query (EXISTS subquery on system_id).
-- Without this index the EXISTS check does a full table scan per system.
CREATE INDEX IF NOT EXISTS "idx_stars_system_id"
    ON "IndexedIntegerDistinctStars"("system_id");

-- Required for efficient distance-ordered init_systems.py pagination.
-- dist2_mpc2 = x*x + y*y + z*z (squared distance from Sol in mpc²); populated
-- once at setup time.  ALTER + UPDATE + CREATE INDEX run once by hand (schema.sql
-- only creates the index).
CREATE INDEX IF NOT EXISTS "idx_systems_dist2"
    ON "IndexedIntegerDistinctSystems"("dist2_mpc2");

-- Checkpoint for init_systems.py: stores the highest dist2_mpc2 value whose
-- batch has been committed, so each new run resumes at the frontier rather than
-- re-scanning from zero.
CREATE TABLE IF NOT EXISTS "InitCheckpoint" (
    "key"   TEXT PRIMARY KEY,
    "value" INTEGER NOT NULL DEFAULT 0
);

-- Per-belt resource and composition profile (one row per belt body).
CREATE TABLE IF NOT EXISTS "BeltProfile" (
    "body_id"          INTEGER PRIMARY KEY REFERENCES "Bodies"("body_id") ON DELETE CASCADE,
    "span_orbit_num"   REAL,       -- belt half-width in Orbit# units
    "m_type_pct"       INTEGER,    -- metallic body percentage
    "s_type_pct"       INTEGER,    -- stony silicate percentage
    "c_type_pct"       INTEGER,    -- carbonaceous percentage
    "other_pct"        INTEGER,    -- other/ice percentage
    "bulk"             INTEGER,    -- belt density factor 1–12
    "resource_rating"  INTEGER,    -- mining resource value 0–10
    "size1_bodies"     INTEGER,    -- significant Size 1 body count
    "sizeS_bodies"     INTEGER     -- significant Size S body count
);

-- Keplerian orbital elements for companion stars in multiple systems.
-- One row per companion; primary stars have no row.
CREATE TABLE IF NOT EXISTS "StarOrbits" (
    "star_id"                  INTEGER PRIMARY KEY,
    "primary_star_id"          INTEGER NOT NULL,
    "semi_major_axis"          REAL    NOT NULL,  -- AU
    "eccentricity"             REAL    NOT NULL,
    "inclination"              REAL    NOT NULL,  -- radians
    "longitude_ascending_node" REAL    NOT NULL,  -- radians
    "argument_periapsis"       REAL    NOT NULL,  -- radians
    "mean_anomaly"             REAL    NOT NULL,  -- radians at epoch
    "epoch"                    INTEGER NOT NULL DEFAULT 0
);

-- Catalog star names derived from HYG data (hygdata_v42).
CREATE TABLE IF NOT EXISTS "StarName" (
    "id"         INTEGER PRIMARY KEY AUTOINCREMENT,
    "star_id"    INTEGER NOT NULL,
    "name"       TEXT    NOT NULL,
    "name_type"  TEXT    NOT NULL CHECK(name_type IN ('proper','bayer','flamsteed','gliese','custom')),
    "species_id" INTEGER DEFAULT NULL,
    "tick"       INTEGER NOT NULL DEFAULT 0,
    UNIQUE("star_id", "name", "name_type")
);
CREATE INDEX IF NOT EXISTS "idx_starname_star"   ON "StarName"("star_id");
CREATE INDEX IF NOT EXISTS "idx_starname_lookup" ON "StarName"("name");

-- Sophont species definitions.
CREATE TABLE IF NOT EXISTS "Species" (
    "species_id"          INTEGER PRIMARY KEY,
    "name"                TEXT    NOT NULL UNIQUE,
    "homeworld_body_id"   INTEGER REFERENCES "Bodies"("body_id"),
    "body_plan"           TEXT    CHECK(body_plan IN (
                              'bilateral','radial','colonial','amorphous','exotic',
                              'centauroid','cephalopod','avian','vermiform','draconic')),
    "locomotion"          TEXT    CHECK(locomotion IN (
                              'bipedal','quadrupedal','sessile','aquatic','aerial','mixed',
                              'hexapedal','jet_aquatic','winged_flight','arboreal','vermiform')),
    "avg_mass_kg"         REAL,
    "avg_height_m"        REAL,
    "lifespan_years"      REAL,
    "temp_min_k"          REAL,
    "temp_max_k"          REAL,
    "pressure_min_atm"    REAL,
    "pressure_max_atm"    REAL,
    "atm_req"             TEXT    CHECK(atm_req IN (
                              'n2o2','co2','methane','any','vacuum','reducing','aquatic')),
    "diet_type"           TEXT    CHECK(diet_type IN (
                              'herbivore','carnivore','omnivore','detritivore',
                              'chemotroph','phototroph','parasitic','parasite')),
    "diet_flexibility"    REAL    CHECK(diet_flexibility BETWEEN 0.0 AND 1.0),
    "metabolic_rate"      TEXT    CHECK(metabolic_rate IN ('low','medium','high','very_high','variable')),
    "repro_strategy"      TEXT    CHECK(repro_strategy IN ('r_strategist','k_strategist')),
    "gestation_years"     REAL,
    "maturity_years"      REAL,
    "offspring_per_cycle" REAL,
    "repro_cycles_per_life" REAL,
    "risk_appetite"       REAL    CHECK(risk_appetite BETWEEN 0.0 AND 1.0),
    "aggression"          REAL    CHECK(aggression BETWEEN 0.0 AND 1.0),
    "expansionism"        REAL    CHECK(expansionism BETWEEN 0.0 AND 1.0),
    "xenophilia"          REAL    CHECK(xenophilia BETWEEN 0.0 AND 1.0),
    "adaptability"        REAL    CHECK(adaptability BETWEEN 0.0 AND 1.0),
    "social_cohesion"     REAL    CHECK(social_cohesion BETWEEN 0.0 AND 1.0),
    "hierarchy_tolerance" REAL    CHECK(hierarchy_tolerance BETWEEN 0.0 AND 1.0),
    "faction_tendency"    REAL    CHECK(faction_tendency BETWEEN 0.0 AND 1.0),
    "grievance_memory"    REAL    CHECK(grievance_memory BETWEEN 0.0 AND 1.0)
);

-- Tracks which stars have had body generation attempted.
-- A row is written after every attempt (success or failure, including 0-body results).
-- Stars with no row have never been attempted.
CREATE TABLE IF NOT EXISTS "BodyGenerationStatus" (
    "star_id"      INTEGER PRIMARY KEY
                   REFERENCES "IndexedIntegerDistinctStars"("star_id"),
    "body_count"   INTEGER NOT NULL DEFAULT 0,  -- 0 = legitimately empty system
    "generated_at" INTEGER NOT NULL DEFAULT 0,  -- Unix timestamp of attempt
    "error"        TEXT DEFAULT NULL            -- NULL = success; message = failed (retry eligible)
);

-- Space velocity of each star system relative to the Sun (ICRS frame).
-- Populated by scripts/seed_system_velocities.py from hygdata_v42 vx/vy/vz columns.
-- Primary star (MIN star_id) is used when a system has multiple catalog entries.
-- Sol is inserted explicitly as 0,0,0 (no HYG row available).
CREATE TABLE IF NOT EXISTS "SystemVelocities" (
    "system_id"      INTEGER PRIMARY KEY
                     REFERENCES "IndexedIntegerDistinctSystems"("system_id"),
    "vx"             REAL NOT NULL,   -- pc/yr (parsecs per year, ICRS)
    "vy"             REAL NOT NULL,   -- pc/yr
    "vz"             REAL NOT NULL,   -- pc/yr
    "source_star_id" INTEGER,         -- star whose HYG row was used; NULL = synthetic or manual
    "velocity_source" TEXT CHECK(velocity_source IN ('catalog','synthetic','manual'))
                                      -- 'catalog' = from hygdata_v42; 'synthetic' = AVR model;
                                      -- 'manual' = hand-assigned (Sol = 0,0,0)
);

-- ---------------------------------------------------------------------------
-- Indexes on IndexedIntegerDistinctSystems (populated by Hipparcos pipeline).
-- idx_systems_xyz enables bounding-box neighbour queries in WorldFacadeImpl.
-- idx_systems_system_id makes the system_id column referenceable as a FK target.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS idx_systems_system_id ON IndexedIntegerDistinctSystems(system_id);
-- CREATE INDEX IF NOT EXISTS idx_systems_x   ON IndexedIntegerDistinctSystems (x);
-- CREATE INDEX IF NOT EXISTS idx_systems_xyz ON IndexedIntegerDistinctSystems (x, y, z);
