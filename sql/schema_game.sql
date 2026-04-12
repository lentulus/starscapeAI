-- schema_game.sql
-- game.db — simulation state database.
-- Run via game.db.init_schema(conn).
-- starscape.db is never referenced here; cross-DB links are by convention (stored IDs only).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Singleton simulation clock and crash-safe resume point.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "GameState" (
    "state_id"              INTEGER PRIMARY KEY CHECK(state_id = 1),
    "current_tick"          INTEGER NOT NULL DEFAULT 0,
    "current_phase"         INTEGER NOT NULL DEFAULT 0,  -- 1-9; 0 = between ticks
    "started_at"            TEXT    NOT NULL,
    "last_committed_at"     TEXT    NOT NULL,
    "last_committed_tick"   INTEGER NOT NULL DEFAULT 0,
    "last_committed_phase"  INTEGER NOT NULL DEFAULT 0,
    "routes_complete"       INTEGER NOT NULL DEFAULT 0  -- 1 once all homeworlds linked
);

-- ---------------------------------------------------------------------------
-- World cache: derived from starscape.db at init; never recomputed at runtime.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "WorldPotential" (
    "body_id"         INTEGER PRIMARY KEY,
    "system_id"       INTEGER NOT NULL,
    "world_potential" INTEGER NOT NULL,
    "has_gas_giant"   INTEGER NOT NULL DEFAULT 0,
    "has_ocean"       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS "idx_worldpotential_system"
    ON "WorldPotential"("system_id");

-- ---------------------------------------------------------------------------
-- Intelligence: per-polity knowledge of each system.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "SystemIntelligence" (
    "intel_id"          INTEGER PRIMARY KEY,
    "polity_id"         INTEGER NOT NULL,  -- logical ref Polity.polity_id
    "system_id"         INTEGER NOT NULL,
    "knowledge_tier"    TEXT    NOT NULL CHECK(knowledge_tier IN ('passive','visited')),
    "first_visit_tick"  INTEGER,
    "last_visit_tick"   INTEGER,
    "gas_giant"         INTEGER,
    "ocean_body"        INTEGER,
    "world_potential"   INTEGER,
    "atm_type"          TEXT,
    "surface_temp_k"    REAL,
    "hydrosphere"       REAL,
    "habitable"         INTEGER,
    UNIQUE(polity_id, system_id)
);

CREATE INDEX IF NOT EXISTS "idx_intel_polity"
    ON "SystemIntelligence"("polity_id");

-- ---------------------------------------------------------------------------
-- Polities and inter-polity relationships.
-- TEMPORAL TABLE: append-only; all mutations INSERT new rows.
-- row_id is the physical PK; polity_id is the logical entity key.
-- Use Polity_head view for current state.
--
-- Point-in-time query example:
--   SELECT p.name, p.treasury_ru FROM Polity p
--   WHERE p.polity_id = 42
--     AND p.row_id = (
--         SELECT MAX(row_id) FROM Polity p2
--         WHERE p2.polity_id = 42 AND p2.tick <= 123
--     );
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "Polity" (
    "row_id"            INTEGER PRIMARY KEY,
    "polity_id"         INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"              INTEGER NOT NULL DEFAULT 0,
    "seq"               INTEGER NOT NULL DEFAULT 0,
    "species_id"        INTEGER NOT NULL,
    "name"              TEXT    NOT NULL,
    "capital_system_id" INTEGER,
    "treasury_ru"       REAL    NOT NULL DEFAULT 0.0,
    "expansionism"      REAL    NOT NULL,
    "aggression"        REAL    NOT NULL,
    "risk_appetite"     REAL    NOT NULL,
    "processing_order"  INTEGER NOT NULL,
    "founded_tick"      INTEGER NOT NULL DEFAULT 0,
    "jump_level"        INTEGER NOT NULL DEFAULT 10,
    "status"            TEXT    NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active','eliminated','vassal'))
);

CREATE INDEX IF NOT EXISTS "idx_polity_entity"
    ON "Polity"("polity_id");

CREATE VIEW IF NOT EXISTS "Polity_head" AS
    SELECT * FROM Polity WHERE row_id IN (
        SELECT MAX(row_id) FROM Polity GROUP BY polity_id
    );

CREATE TABLE IF NOT EXISTS "ContactRecord" (
    "row_id"            INTEGER PRIMARY KEY,
    "contact_id"        INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"              INTEGER NOT NULL DEFAULT 0,
    "seq"               INTEGER NOT NULL DEFAULT 0,
    "polity_a_id"       INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "polity_b_id"       INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "contact_tick"      INTEGER NOT NULL,
    "contact_system_id" INTEGER NOT NULL,
    "peace_weeks"       INTEGER NOT NULL DEFAULT 0,
    "at_war"            INTEGER NOT NULL DEFAULT 0,
    "map_shared"        INTEGER NOT NULL DEFAULT 0,
    CHECK(polity_a_id < polity_b_id)
);

CREATE INDEX IF NOT EXISTS "idx_contactrecord_entity"
    ON "ContactRecord"("contact_id");
CREATE INDEX IF NOT EXISTS "idx_contactrecord_polities"
    ON "ContactRecord"("polity_a_id", "polity_b_id");

CREATE VIEW IF NOT EXISTS "ContactRecord_head" AS
    SELECT * FROM ContactRecord WHERE row_id IN (
        SELECT MAX(row_id) FROM ContactRecord GROUP BY contact_id
    );

CREATE TABLE IF NOT EXISTS "WarRecord" (
    "war_id"            INTEGER PRIMARY KEY,
    "polity_a_id"       INTEGER NOT NULL,  -- logical ref Polity.polity_id
    "polity_b_id"       INTEGER NOT NULL,  -- logical ref Polity.polity_id
    "name"              TEXT    NOT NULL,
    "declared_tick"     INTEGER NOT NULL,
    "initiator_id"      INTEGER NOT NULL,  -- logical ref Polity.polity_id
    "ended_tick"        INTEGER
);

-- ---------------------------------------------------------------------------
-- System presence: foothold and control state per body per polity.
-- TEMPORAL TABLE: append-only; all mutations INSERT new rows.
-- row_id is the physical PK; presence_id is the logical entity key.
-- Use SystemPresence_head view for current state.
--
-- Point-in-time query example:
--   -- Who held system 12345 at tick 123?
--   SELECT p.name, sp.control_state, sp.development_level
--   FROM SystemPresence sp
--   JOIN Polity_head p ON p.polity_id = sp.polity_id
--   WHERE sp.system_id = 12345
--     AND sp.row_id = (
--         SELECT MAX(row_id) FROM SystemPresence sp2
--         WHERE sp2.presence_id = sp.presence_id AND sp2.tick <= 123
--     );
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "SystemPresence" (
    "row_id"                INTEGER PRIMARY KEY,
    "presence_id"           INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"                  INTEGER NOT NULL DEFAULT 0,
    "seq"                   INTEGER NOT NULL DEFAULT 0,
    "polity_id"             INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "system_id"             INTEGER NOT NULL,
    "body_id"               INTEGER NOT NULL,
    "control_state"         TEXT    NOT NULL
                            CHECK(control_state IN ('outpost','colony','controlled','contested')),
    "development_level"     INTEGER NOT NULL DEFAULT 0
                            CHECK(development_level BETWEEN 0 AND 5),
    "colonist_deliveries"   INTEGER NOT NULL DEFAULT 0,
    "has_shipyard"          INTEGER NOT NULL DEFAULT 0,
    "has_naval_base"        INTEGER NOT NULL DEFAULT 0,
    "growth_cycle_tick"     INTEGER,
    "established_tick"      INTEGER NOT NULL,
    "last_updated_tick"     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_presence_entity"
    ON "SystemPresence"("presence_id");
CREATE INDEX IF NOT EXISTS "idx_presence_polity"
    ON "SystemPresence"("polity_id");
CREATE INDEX IF NOT EXISTS "idx_presence_system"
    ON "SystemPresence"("system_id");

CREATE VIEW IF NOT EXISTS "SystemPresence_head" AS
    SELECT * FROM SystemPresence WHERE row_id IN (
        SELECT MAX(row_id) FROM SystemPresence GROUP BY presence_id
    );

-- ---------------------------------------------------------------------------
-- Fleets, squadrons, and hulls.
-- Fleet and Squadron are NOT temporal (normal UPDATE-based mutation).
-- Hull IS temporal: append-only; all mutations INSERT new rows.
-- row_id is the physical PK; hull_id is the logical entity key.
-- Use Hull_head view for current state.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "Fleet" (
    "fleet_id"              INTEGER PRIMARY KEY,
    "polity_id"             INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "name"                  TEXT    NOT NULL,
    "system_id"             INTEGER,
    "prev_system_id"        INTEGER,   -- origin of last jump; set by execute_jump
    "destination_system_id" INTEGER,
    "destination_tick"      INTEGER,
    "admiral_id"            INTEGER,   -- logical ref Admiral.admiral_id
    "supply_ticks"          INTEGER NOT NULL DEFAULT 0,
    "status"                TEXT    NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','in_transit','destroyed'))
);

CREATE INDEX IF NOT EXISTS "idx_fleet_system"
    ON "Fleet"("system_id");
CREATE INDEX IF NOT EXISTS "idx_fleet_polity"
    ON "Fleet"("polity_id");

-- Squadron: same-type warships grouped as the tactical unit in combat.
-- combat_role is set at the start of each engagement; may differ between battles.
CREATE TABLE IF NOT EXISTS "Squadron" (
    "squadron_id"   INTEGER PRIMARY KEY,
    "fleet_id"      INTEGER REFERENCES "Fleet"("fleet_id"),
    "polity_id"     INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "name"          TEXT    NOT NULL,
    "hull_type"     TEXT    NOT NULL CHECK(hull_type IN (
                        'capital','old_capital','cruiser','escort','sdb')),
    "combat_role"   TEXT    NOT NULL DEFAULT 'line_of_battle'
                    CHECK(combat_role IN ('screen','line_of_battle','reserve')),
    "system_id"     INTEGER,
    "status"        TEXT    NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','destroyed'))
);

CREATE INDEX IF NOT EXISTS "idx_squadron_fleet"
    ON "Squadron"("fleet_id");

-- Every ship individually tracked. TEMPORAL TABLE.
CREATE TABLE IF NOT EXISTS "Hull" (
    "row_id"                INTEGER PRIMARY KEY,
    "hull_id"               INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"                  INTEGER NOT NULL DEFAULT 0,
    "seq"                   INTEGER NOT NULL DEFAULT 0,
    "polity_id"             INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "name"                  TEXT    NOT NULL,
    "hull_type"             TEXT    NOT NULL CHECK(hull_type IN (
                                'capital','old_capital','cruiser','escort',
                                'troop','transport','colony_transport','scout','sdb')),
    "squadron_id"           INTEGER REFERENCES "Squadron"("squadron_id"),
    "fleet_id"              INTEGER REFERENCES "Fleet"("fleet_id"),
    "system_id"             INTEGER,
    "destination_system_id" INTEGER,
    "destination_tick"      INTEGER,
    "status"                TEXT    NOT NULL DEFAULT 'active'
                            CHECK(status IN (
                                'active','damaged','establishing',
                                'in_transit','destroyed')),
    "marine_designated"     INTEGER NOT NULL DEFAULT 0,
    "cargo_type"            TEXT    CHECK(cargo_type IN ('ru','colonists','army','sdb',NULL)),
    "cargo_id"              INTEGER,
    "establish_tick"        INTEGER,
    "created_tick"          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_hull_entity"
    ON "Hull"("hull_id");
CREATE INDEX IF NOT EXISTS "idx_hull_fleet"
    ON "Hull"("fleet_id");
CREATE INDEX IF NOT EXISTS "idx_hull_system"
    ON "Hull"("system_id");
CREATE INDEX IF NOT EXISTS "idx_hull_squadron"
    ON "Hull"("squadron_id");

CREATE VIEW IF NOT EXISTS "Hull_head" AS
    SELECT * FROM Hull WHERE row_id IN (
        SELECT MAX(row_id) FROM Hull GROUP BY hull_id
    );

-- ---------------------------------------------------------------------------
-- Admirals. TEMPORAL TABLE.
-- row_id is the physical PK; admiral_id is the logical entity key.
-- Use Admiral_head view for current state.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "Admiral" (
    "row_id"          INTEGER PRIMARY KEY,
    "admiral_id"      INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"            INTEGER NOT NULL DEFAULT 0,
    "seq"             INTEGER NOT NULL DEFAULT 0,
    "polity_id"       INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "name"            TEXT    NOT NULL,
    "tactical_factor" INTEGER NOT NULL CHECK(tactical_factor BETWEEN -3 AND 3),
    "fleet_id"        INTEGER,            -- logical ref Fleet.fleet_id
    "created_tick"    INTEGER NOT NULL,
    "retirement_tick" INTEGER NOT NULL,   -- tick at which this admiral retires
    "status"          TEXT    NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active','killed','captured','retired'))
);

CREATE INDEX IF NOT EXISTS "idx_admiral_entity"
    ON "Admiral"("admiral_id");

CREATE VIEW IF NOT EXISTS "Admiral_head" AS
    SELECT * FROM Admiral WHERE row_id IN (
        SELECT MAX(row_id) FROM Admiral GROUP BY admiral_id
    );

-- ---------------------------------------------------------------------------
-- Ground forces. TEMPORAL TABLE.
-- row_id is the physical PK; force_id is the logical entity key.
-- Use GroundForce_head view for current state.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "GroundForce" (
    "row_id"                INTEGER PRIMARY KEY,
    "force_id"              INTEGER NOT NULL,   -- logical entity key (non-unique)
    "tick"                  INTEGER NOT NULL DEFAULT 0,
    "seq"                   INTEGER NOT NULL DEFAULT 0,
    "polity_id"             INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "name"                  TEXT    NOT NULL,
    "unit_type"             TEXT    NOT NULL CHECK(unit_type IN ('army','garrison')),
    "strength"              INTEGER NOT NULL CHECK(strength BETWEEN 0 AND 6),
    "max_strength"          INTEGER NOT NULL DEFAULT 6,
    "system_id"             INTEGER,
    "body_id"               INTEGER,
    "embarked_hull_id"      INTEGER,            -- logical ref Hull.hull_id
    "marine_designated"     INTEGER NOT NULL DEFAULT 0,
    "occupation_duty"       INTEGER NOT NULL DEFAULT 0,
    "refit_ticks_remaining" INTEGER NOT NULL DEFAULT 0,
    "created_tick"          INTEGER NOT NULL,
    "last_updated_tick"     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_groundforce_entity"
    ON "GroundForce"("force_id");
CREATE INDEX IF NOT EXISTS "idx_groundforce_system"
    ON "GroundForce"("system_id");

CREATE VIEW IF NOT EXISTS "GroundForce_head" AS
    SELECT * FROM GroundForce WHERE row_id IN (
        SELECT MAX(row_id) FROM GroundForce GROUP BY force_id
    );

-- ---------------------------------------------------------------------------
-- Build and repair queues.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "BuildQueue" (
    "queue_id"      INTEGER PRIMARY KEY,
    "polity_id"     INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "system_id"     INTEGER NOT NULL,
    "hull_type"     TEXT    NOT NULL,
    "ticks_total"   INTEGER NOT NULL,
    "ticks_elapsed" INTEGER NOT NULL DEFAULT 0,
    "reserved_ru"   REAL    NOT NULL,
    "ordered_tick"  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS "RepairQueue" (
    "repair_id"     INTEGER PRIMARY KEY,
    "hull_id"       INTEGER NOT NULL,   -- logical ref Hull.hull_id
    "system_id"     INTEGER NOT NULL,
    "ticks_total"   INTEGER NOT NULL DEFAULT 4,
    "ticks_elapsed" INTEGER NOT NULL DEFAULT 0,
    "cost_ru"       REAL    NOT NULL
);

-- ---------------------------------------------------------------------------
-- Economy log: append-only; one row per system per tick.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "SystemEconomy" (
    "economy_id"    INTEGER PRIMARY KEY,
    "tick"          INTEGER NOT NULL,
    "polity_id"     INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "system_id"     INTEGER NOT NULL,
    "ru_produced"   REAL    NOT NULL,
    "ru_maintenance" REAL   NOT NULL,
    "ru_construction" REAL  NOT NULL,
    "treasury_after" REAL   NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_economy_tick"
    ON "SystemEconomy"("tick");

-- ---------------------------------------------------------------------------
-- Name pool: pre-generated names drawn at entity creation.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "NamePool" (
    "name_id"       INTEGER PRIMARY KEY,
    "species_id"    INTEGER NOT NULL,
    "name_type"     TEXT    NOT NULL CHECK(name_type IN (
                        'person','system','body','fleet','war','polity')),
    "name"          TEXT    NOT NULL,
    "used"          INTEGER NOT NULL DEFAULT 0,
    "used_by_id"    INTEGER,
    "used_tick"     INTEGER,
    UNIQUE(species_id, name_type, name)
);

CREATE INDEX IF NOT EXISTS "idx_namepool_available"
    ON "NamePool"(species_id, name_type, used);

-- ---------------------------------------------------------------------------
-- Place names: per-polity names for systems and bodies.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "PlaceName" (
    "name_id"       INTEGER PRIMARY KEY,
    "polity_id"     INTEGER NOT NULL,   -- logical ref Polity.polity_id
    "object_type"   TEXT    NOT NULL CHECK(object_type IN ('system','body')),
    "object_id"     INTEGER NOT NULL,
    "name"          TEXT    NOT NULL,
    "assigned_tick" INTEGER NOT NULL,
    UNIQUE(polity_id, object_type, object_id)
);

-- ---------------------------------------------------------------------------
-- Event log: append-only; authoritative history for LLM historian.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "GameEvent" (
    "event_id"      INTEGER PRIMARY KEY,
    "tick"          INTEGER NOT NULL,
    "phase"         INTEGER NOT NULL,
    "event_type"    TEXT    NOT NULL CHECK(event_type IN (
                        'contact','war_declared','combat','control_change',
                        'fleet_destroyed','disengage','pursuit','bombardment',
                        'colony_established','hull_built','jump_upgrade',
                        'admiral_commissioned','map_shared','summary','monthly_summary')),
    "polity_a_id"   INTEGER,  -- logical ref Polity.polity_id
    "polity_b_id"   INTEGER,  -- logical ref Polity.polity_id
    "system_id"     INTEGER,
    "body_id"       INTEGER,
    "admiral_id"    INTEGER,  -- logical ref Admiral.admiral_id
    "summary"       TEXT    NOT NULL,
    "detail"        TEXT
);

CREATE INDEX IF NOT EXISTS "idx_event_tick"
    ON "GameEvent"("tick");
CREATE INDEX IF NOT EXISTS "idx_event_type"
    ON "GameEvent"("event_type");

-- ---------------------------------------------------------------------------
-- Jump route graph — deduped record of every (from, to) pair actually jumped.
-- Canonical ordering: from_system_id < to_system_id eliminates A→B / B→A dupes.
-- Recording stops once all polity homeworlds form a single connected component
-- (GameState.routes_complete = 1).  Used to generate dot-file travel diagrams.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "JumpRoute" (
    "route_id"       INTEGER PRIMARY KEY,
    "from_system_id" INTEGER NOT NULL,
    "to_system_id"   INTEGER NOT NULL,
    "dist_pc"        REAL    NOT NULL,
    "from_x_mpc"     REAL    NOT NULL,
    "from_y_mpc"     REAL    NOT NULL,
    "from_z_mpc"     REAL    NOT NULL,
    "to_x_mpc"       REAL    NOT NULL,
    "to_y_mpc"       REAL    NOT NULL,
    "to_z_mpc"       REAL    NOT NULL,
    "first_tick"     INTEGER NOT NULL,
    UNIQUE(from_system_id, to_system_id)
);

CREATE INDEX IF NOT EXISTS "idx_jumproute_from"
    ON "JumpRoute"("from_system_id");
CREATE INDEX IF NOT EXISTS "idx_jumproute_to"
    ON "JumpRoute"("to_system_id");
