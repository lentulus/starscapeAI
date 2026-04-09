# Version 1 — Implementation Notes

*Backing design for `game.md`. To be expanded once the game design is stable.*

---

## Status

`design` — game design in progress. Do not implement until `game.md` is
marked stable.

---

## Placeholder: tables required

Derived from the game design. Detail TBD.

| Table | Purpose |
|---|---|
| `Polity` | Political actors; one per species at start except Humans |
| `SystemPresence` | Control state per system per polity; append-only log |
| `ShipClass` | Hull blueprints: ratings, costs, build time |
| `Ship` | Individual hulls (scouts/couriers) |
| `Fleet` | Named groups of ships at a location |
| `FleetComposition` | Ship counts per class within a fleet |
| `GroundForce` | Strength, location, embarked fleet |
| `SystemEconomy` | RU output per system per tick; append-only |
| `GameEvent` | Full event log for LLM historian |

---

## Placeholder: open implementation questions

- Fleet movement: in-system transit time vs instantaneous within a system?
- Shipyard: is it a flag on a SystemPresence row, or its own table?
- How many starting human polities? Fixed in init script or derived from
  `faction_tendency`?
- Maintenance failure: degrade combat rating immediately or after N missed ticks?
- `GameEvent` schema: structured columns vs JSON payload for the summary field?
