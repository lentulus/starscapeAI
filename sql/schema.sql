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
