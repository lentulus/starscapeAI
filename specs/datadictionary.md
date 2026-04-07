# Data Dictionary

All tables are in the SQLite database at `/Volumes/Data/starscape4/sqllite_database/starscape.db`
unless otherwise noted. Ordered alphabetically by field name.

| Field | Units | Table(s) | Description |
|-------|-------|----------|-------------|
| `absmag` | mag (absolute) | `IndexedIntegerDistinctStars` | Absolute visual magnitude Mv; lower = brighter = more massive on the main sequence |
| `age` | years | `DistinctStarsExtended` | Estimated main-sequence lifetime: t ≈ 10¹⁰ × M/L; lower bound for evolved stars |
| `argument_periapsis` | radians | `StarOrbits`, `Bodies` | Argument of periapsis ω; uniform on [0, 2π) |
| `body_id` | — | `Bodies` | Unique integer identifier for a planet or moon |
| `body_type` | — | `Bodies` | `'planet'` (orbits a star) or `'moon'` (orbits a planet) |
| `ci` | mag (B−V) | `IndexedIntegerDistinctStars` | B−V color index; stored as TEXT, parsed to float at read time |
| `eccentricity` | — | `StarOrbits`, `Bodies` | Orbital eccentricity e ∈ [0, 0.97); drawn from thermal distribution f(e)=2e |
| `epoch` | game ticks (weeks) | `StarOrbits`, `Bodies` | Game time at which `mean_anomaly` is defined; 0 = game start |
| `hip` | — | `IndexedIntegerDistinctStars` | Hipparcos catalogue identifier; may be NULL for generated companion stars |
| `inclination` | radians | `StarOrbits`, `Bodies` | Orbital inclination i ∈ [0, π); drawn from isotropic sphere: i = arccos(uniform(−1,1)) |
| `in_hz` | — | `Bodies` | 1 if planet's semi-major axis falls within the host star's HZ (0.95–1.67 × √L AU); 0 outside; NULL for moons |
| `longitude_ascending_node` | radians | `StarOrbits`, `Bodies` | Longitude of the ascending node Ω; uniform on [0, 2π) |
| `luminosity` | L☉ | `DistinctStarsExtended` | Bolometric luminosity derived from absolute magnitude: L = 10^((4.83 − Mv) / 2.5) |
| `mass` | M☉ (stars), Mₑ (bodies) | `DistinctStarsExtended`, `Bodies` | Stellar mass from piecewise MS mass-luminosity relation (Duric 2004); −1 signals error in `DistinctStarsExtended`. Planet/moon mass in Earth masses. |
| `mean_anomaly` | radians | `StarOrbits`, `Bodies` | Mean anomaly M₀ at `epoch`; uniform on [0, 2π). Propagate as M(t) = M₀ + n·(t − epoch) |
| `orbit_body_id` | — | `Bodies` | FK → `Bodies.body_id`; parent planet for moons; NULL for planets |
| `orbit_star_id` | — | `Bodies` | FK → `IndexedIntegerDistinctStars.star_id`; host star for planets; NULL for moons |
| `possible_tidal_lock` | — | `Bodies` | 1 if planet/moon is within the estimated tidal-lock zone of its host star or parent planet; 0 if not; NULL for belts and planetoids |
| `primary_star_id` | — | `StarOrbits` | `star_id` of the most massive star in the system; the reference frame for orbital calculations |
| `radius` | R☉ (stars), Rₑ (bodies) | `DistinctStarsExtended`, `Bodies` | Stellar radius via Stefan-Boltzmann; planet/moon radius in Earth radii |
| `semi_major_axis` | AU | `StarOrbits`, `Bodies` | Semi-major axis a; AU for both stellar companions and planets/moons |
| `source` | — | `IndexedIntegerDistinctStars` | Provenance tag for the spectral value (e.g. `'catalogue'`, `'derived'`) |
| `spectral` | — | `IndexedIntegerDistinctStars` | Spectral type string (e.g. `G5V`, `K3III`); derived from B−V and Mv by `fill_spectral.py` |
| `star_id` | — | `IndexedIntegerDistinctStars`, `DistinctStarsExtended`, `StarOrbits` | Unique integer identifier for a star; primary key in most tables |
| `system_id` | — | `IndexedIntegerDistinctStars` | Groups stars belonging to the same physical system; shared by all members of a multiple system |
| `temperature` | K | `DistinctStarsExtended` | Effective temperature; derived via Ballesteros B−V formula, spectral-type interpolation, or mass-based estimate (see `temp_source`) |
| `temp_source` | — | `DistinctStarsExtended` | Provenance of the temperature value: `'bv'` (Ballesteros), `'spectral:<type>'` (interpolated), `'mass_est'` (last-resort), or NULL on error |
| `x` | milliparsecs | `IndexedIntegerDistinctSystems` | ICRS equatorial Cartesian X — points toward RA 0h, Dec 0° (vernal equinox direction); integer; 1 mpc = 206.265 AU |
| `y` | milliparsecs | `IndexedIntegerDistinctSystems` | ICRS equatorial Cartesian Y — points toward RA 6h, Dec 0°; integer |
| `z` | milliparsecs | `IndexedIntegerDistinctSystems` | ICRS equatorial Cartesian Z — points toward Dec +90° (ICRS north celestial pole); integer. Note: this is **not** galactic north; use the `eq_to_galactic_mpc()` transform in `galaxy.py` to obtain the true height above the galactic plane |
