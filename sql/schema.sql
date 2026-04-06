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
