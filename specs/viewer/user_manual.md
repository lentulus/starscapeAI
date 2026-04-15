# Star Viewer — User Manual

`scripts/star_viewer.py` renders selected Starscape 5 systems as an
interactive 3D dot plot in a browser tab.  The output is a self-contained
HTML file that works on any machine with Chrome, Firefox, or Safari —
no Python, no internet, no server required after the file is generated.

---

## Requirements

- `uv` installed and project dependencies up to date (`uv add plotly` was
  run when Phase 1.5 was built — nothing further needed)
- `starscape.db` on the external drive (star positions + spectral types)
- `game.db` on the external drive (polity/intel context, jump routes) —
  optional; viewer works without it but with less information

---

## Running the viewer

All commands are run from the project root:

```sh
uv run scripts/star_viewer.py [options] [SYSTEM_ID ...]
```

### Mode 1 — Questionnaire (no arguments)

```sh
uv run scripts/star_viewer.py
```

Presents a menu:

```
=== Starscape 5 Star Viewer ===

Select systems to display:
  [1] Enter system IDs manually
  [2] All systems known to a polity
  [3] All systems within N parsecs of an anchor system

Choice [1/2/3]:
```

Option 2 (polity) then asks which polity and which knowledge tier.
Option 3 asks for an anchor system ID and a radius in parsecs.

### Mode 2 — Explicit system IDs

```sh
uv run scripts/star_viewer.py 898454 1066934 918040
```

Displays exactly those systems.  Game context (tier, polity, place name)
is added automatically if game.db is present.

### Mode 3 — Polity filter (non-interactive)

```sh
uv run scripts/star_viewer.py --polity 1
uv run scripts/star_viewer.py --polity 1 --tier visited
uv run scripts/star_viewer.py --polity 9 --tier presence
```

`--tier` options:

| Value | Systems shown |
|---|---|
| `all` (default) | All systems the polity has any knowledge of (passive scan + visited + presence) |
| `visited` | Systems the polity has physically surveyed, plus any with a presence |
| `presence` | Only systems where the polity has an outpost, colony, or controlled world |

### Mode 4 — Radius search

```sh
uv run scripts/star_viewer.py --radius 898454 25
```

Shows all systems within 25 parsecs of system 898454.  Uses exact
Euclidean distance, not a bounding box approximation.

---

## Options

| Flag | Description |
|---|---|
| `--save FILE` | Write the HTML to FILE and open it.  Without this flag, a temp file is used (survives until reboot). |
| `--no-routes` | Suppress jump route lines even when game.db is present. |
| `--star-db PATH` | Override default starscape.db path. |
| `--game-db PATH` | Override default game.db path. |

### Saving for later or sharing

```sh
uv run scripts/star_viewer.py --polity 1 --save ~/Desktop/kreeth_tick1500.html
```

The saved file is entirely self-contained (~3–5 MB).  You can:
- Reopen it any time without re-running the script
- Send it to another machine and open it in a browser
- Keep dated copies as a record of simulation progress

---

## Browser controls

### Mouse

| Action | Effect |
|---|---|
| Left-drag | Rotate the scene |
| Right-drag | Pan |
| Scroll | Zoom in / out |
| Hover over a dot | Show system info card |

### Button bar (top-left of plot)

**Row 1 — Camera presets**

| Button | View |
|---|---|
| ⟳ Perspective | Angled view, good for 3D structure |
| Top (XY) | Looking straight down the Z axis — galactic plane view |
| Front (XZ) | Looking along the Y axis |
| Side (YZ) | Looking along the X axis |

The camera can be freely dragged after clicking a preset.

**Row 2 — Route toggle** *(only appears when jump routes are drawn)*

| Button | Effect |
|---|---|
| Routes on | Show jump route lines (default) |
| Routes off | Hide jump route lines — useful when they clutter a dense view |

**Row 3 — Marker size**

| Button | Dot size |
|---|---|
| · Small | Compact — good for dense views with many systems |
| ● Medium | Default |
| ⬤ Large | Easier to pick individual systems when count is low |

### Legend (right side)

One entry per spectral class.  **Click any entry to hide or show that
class.**  Double-click to isolate it (hide all others).  This is useful
for filtering to just G and K stars, for example.

---

## What the dots mean

### Colour — spectral class

| Colour | Class | Description |
|---|---|---|
| Blue-violet | O | Very hot, massive, short-lived |
| Blue-white | B | Hot blue stars |
| White-blue | A | White stars (Sirius-type) |
| Yellow-white | F | Slightly cooler than the sun |
| Yellow | G | Sun-like |
| Orange | K | Cooler orange dwarfs |
| Red | M | Red dwarfs — most common in the galaxy |
| Violet | W | Wolf-Rayet (rare) |
| Grey | ? | Spectral type not determined |

### Shape — knowledge tier *(game.db required)*

| Shape | Tier | Meaning |
|---|---|---|
| ◆ Diamond | Presence | Polity has an outpost, colony, or controlled world here |
| ● Filled circle | Visited | A scout has surveyed this system |
| ○ Hollow circle | Passive | System is known from passive scan only (position, no survey) |

When no game.db context is available (e.g. explicit system IDs with no
game.db present, or systems unknown to any polity), all markers are
filled circles.

### Hover card

Hovering over a dot shows:
- **System name** (from PlaceName if assigned, otherwise `sys-{id}`)
- Spectral type
- Coordinates in parsecs (X, Y, Z)
- Knowledge tier
- Control state and polity name (if a presence exists)
- World potential (if surveyed)
- Habitable flag (if surveyed)

---

## Jump routes *(game.db required)*

Thin blue lines connect systems where actual jumps have occurred during
the simulation.  Only routes where **both endpoints are in the current
view** are drawn — routes leading outside the displayed set are not shown.

Route count is shown in the title bar and in the legend entry
("Jump routes (N)").  Click the legend entry to hide/show all routes,
or use the "Routes off" button.

Use `--no-routes` to suppress them entirely when the view is too dense.

---

## Practical limits

Performance depends on the number of points (dots) and route line
segments rendered by the browser's WebGL engine.

| Systems | Routes | Expected behaviour |
|---|---|---|
| < 500 | any | Instant, smooth |
| 500–5 000 | < 5 000 | Smooth rotation; hover may take ~0.5 s |
| 5 000–15 000 | < 10 000 | Rotation smooth; hover noticeably slower |
| 15 000–50 000 | any | Rotation may stutter; hover very slow — use `--no-routes` and disable hover by not interacting |
| > 50 000 | — | Not recommended for Plotly; switch to Vispy (Phase 3+ tooling) |

HTML file size is approximately 3 MB (Plotly.js engine, fixed) plus
roughly 1 KB per displayed system.  A 5 000-system view produces an
~8 MB HTML file.

The full 2.47 M star catalog cannot be rendered in Plotly.  For galaxy-
scale views, the Phase 5 plan uses a random subsample (~2 000 background
stars) as context behind a highlighted selection.

---

## Polity reference

| ID | Name |
|---|---|
| 1 | Kreeth Dominion |
| 2 | Vashori Compact |
| 3 | Kraathi Crusade |
| 4 | Nakhavi Reach |
| 5 | Skharri Pride |
| 6 | Vaelkhi Choth |
| 7 | Shekhari Exchange |
| 8 | Golvhaan Reach |
| 9 | Nhaveth Court A |
| 10 | Nhaveth Court B |
| 11 | Nhaveth Court C |
| 12 | Vardhek Roidhunate |
| 13 | Oceania |
| 14 | Eurasia |
| 15 | Eastasia |

---

## Common examples

```sh
# All 11 homeworlds
uv run scripts/star_viewer.py \
  898454 1066934 918040 1036727 911133 \
  1158848 1061677 987309 1130253 942565 1157617

# Everything Kreeth knows, with jump network
uv run scripts/star_viewer.py --polity 1

# Only Kreeth colonies and outposts
uv run scripts/star_viewer.py --polity 1 --tier presence

# 25 pc neighbourhood of Earth's homeworld system
uv run scripts/star_viewer.py --radius 898454 25

# Save a snapshot for the archive
uv run scripts/star_viewer.py --polity 14 \
  --save ~/Desktop/eurasia_tick$(date +%s).html

# Dense radius view — suppress routes, smaller dots
uv run scripts/star_viewer.py --radius 898454 50 --no-routes --save /tmp/dense.html
# Then use "· Small" button in browser
```

---

*Last updated: Phase 1.5 — jump routes, terminal questionnaire, in-browser camera and size controls.*
