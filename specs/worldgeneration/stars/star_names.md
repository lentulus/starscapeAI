# Concept: Assign names to stars and systems.

## Overview
-- initial names are in the starscape db as hygdata_v42.  Query select hip, proper, bf, gl  from hygdata_v42 where hip is not null and (proper is not NULL or bf is not null or gl is not null).
-- The same star may have multiple names.
-- The name will vary by species and polity and change over time.  Provide species and time keys; all provided initial names are Human and starting time.
-- The initialization data will reside in the starscape master database, but in the simulation phase will be moved to "game" data
-- Names with a / will be parsed as multiple names with the / as a separator
-- A bf name will have two parts separated by a space, eg Tau Phe.  If the first part contrains numbers and letter, split them and enter as two names.  For example, "21Alp And" becomes "21 And" and "Alp And"
-- star_id is sol
-- this is a separate table related by star_id

## Scope
in: Name table initiallization and game database initialization




## Key Decisions
- {Decision and rationale}
- {Alternative considered and why it was rejected}

## Open Questions
- [ ] {Question} — owner: {name}, due: {date}

