# Star Viewer — Specification and Implementation Plan

A standalone Python script that queries the Starscape 5 databases and renders
selected stars as an interactive 3D dot plot in a browser tab.

---

## How a Python Program Runs "in a Browser"

The short answer: it doesn't actually run in the browser. Here is what really
happens.

**The chain of events**

1. You run a normal Python script on your Mac with `uv run scripts/star_viewer.py`.
2. The script queries SQLite and builds a data structure in memory (x, y, z
   coordinates, labels, colours — whatever you want to show).
3. It hands that data to the Plotly library, which serialises it into a single
   self-contained HTML file. That file contains:
   - The star data embedded as a JSON blob (text).
   - A copy of the Plotly.js rendering engine (a ~3 MB JavaScript file).
   - A thin wrapper that wires the two together.
4. Plotly calls `webbrowser.open()` — the standard Python library that tells
   your operating system to open a file in whatever browser is set as default.
5. The browser opens the HTML file from your local filesystem (`file:///tmp/…`).
   Nothing is sent over the internet. No server is running. The page is
   entirely local.
6. Plotly.js renders the 3D scatter plot using WebGL (the browser's GPU
   pipeline). Mouse drag rotates, scroll zooms, hover shows labels.

**The key distinction from a web app**

A web app requires a running server that the browser talks to over HTTP.
This tool has no server. The browser is being used purely as a rendering
surface — the same role a desktop window would play, but with a more capable
3D renderer already built in. When you close the browser tab, the tool is done.
The Python script exits after opening the file; it does not stay running.

**Why this works for our use case**

- No network, no firewall concerns, no install for the end user beyond Python.
- Plotly.js is bundled into the HTML on first run; subsequent offline use works.
- The HTML file is a record of the view — you can save it, share it, or reopen
  it weeks later without re-running the Python script.

---

## Data sources

| Data | Table | Database |
|---|---|---|
| System positions (mpc, ICRS Cartesian) | `IndexedIntegerDistinctSystems` | `starscape.db` |
| Spectral type, B-V colour index | `IndexedIntegerDistinctStars` | `starscape.db` |
| Luminosity, temperature, mass | `DistinctStarsExtended` | `starscape.db` |
| Polity name, capital system | `Polity_head` | `game.db` |
| Which systems a polity has visited | `SystemIntelligence` | `game.db` |
| Which systems a polity has a presence in | `SystemPresence_head` | `game.db` |
| Place names assigned to systems | `PlaceName` | `game.db` |

Coordinates are stored as **milliparsecs** (integer). Divide by 1000 to get
parsecs. 1 parsec ≈ 3.26 light-years.

Star colour from spectral type / B-V index follows the standard mapping:
O→blue-violet, B→blue-white, A→white, F→yellow-white, G→yellow, K→orange,
M→red.

---

## Phased delivery

### Phase 1 — Static list viewer (cut 1)

**Goal:** A working tool you can run today with zero UI design.

**Input:** A list of system IDs on the command line.

**Output:** A browser tab opens with a 3D scatter plot. Drag to rotate,
scroll to zoom, hover to see system ID and coordinates. Script exits.

**Script:** `scripts/star_viewer.py`

**Invocation:**
```
uv run scripts/star_viewer.py 898454 1066934 918040 1036727
```

**Data fetched per system:**
- x, y, z (converted from mpc to pc)
- spectral type → dot colour
- system_id → hover label

**Dependencies added:**
```
uv add plotly
```

**Scope limit:** No game.db. No names. No polity data. Hardcoded marker size.
Axes labelled in parsecs. One colour per spectral class.

**Acceptance:** Opens browser, shows dots, rotates smoothly, hover works.

---

### Phase 2 — Named systems and polity overlay

**Goal:** Make the display meaningful — show what each system is and who
controls it.

**New inputs:**
- `--game` flag pointing to game.db (defaults to the standard path)
- `--polity N` to highlight one polity's known systems without listing IDs

**New display elements:**
- Dot label: place name if known, otherwise `sys-{id}`
- Dot colour: polity colour if a presence exists; spectral class colour if
  only visited; grey if unvisited (passive intel only)
- Dot size: larger for systems with a presence than bare visits
- Legend identifying each polity by name and colour

**Invocation examples:**
```
# Show all systems known to polity 1
uv run scripts/star_viewer.py --polity 1

# Show specific systems with game context
uv run scripts/star_viewer.py --game /path/to/game.db 898454 1066934
```

**Acceptance:** Homeworlds and colonies visually distinct from scouted systems.
Legend matches polity names from game.db.

---

### Phase 3 — Jump network overlay

**Goal:** Show which systems are jump-connected at a given range, so you can
see the shape of each polity's expansion corridor.

**New inputs:**
- `--jump-range N` draw edges between all displayed systems within N parsecs
  of each other
- `--polity-jumps` draw only edges that connect systems both known to the
  selected polity (uses the existing JumpRoute table if populated, otherwise
  computes on the fly)

**New display elements:**
- Thin lines (Plotly `Scatter3d` with `mode='lines'`) between connected pairs
- Line colour matches the polity or is neutral grey for unowned connections
- Edges are semi-transparent so dots remain readable

**Acceptance:** Jump corridors visible; isolated star clusters identifiable.

---

### Phase 4 — Selection UI

**Goal:** Replace command-line system ID lists with an interactive filter panel
so you can explore without re-running the script.

**Approach:** Plotly Dash — a thin Python web framework that adds interactive
widgets (dropdowns, sliders, checkboxes) to Plotly charts and runs a local
server. Unlike Phase 1–3, Dash keeps Python alive to respond to widget events;
the browser tab makes HTTP requests to `localhost`.

**New inputs (all via browser UI, no command-line args needed):**
- Polity selector (multi-select dropdown)
- Knowledge tier filter: all / visited / presence only
- Parsec radius slider: show all systems within R pc of a chosen system
- Spectral class filter checkboxes (O B A F G K M)
- Jump range slider for edge overlay

**New dependency:**
```
uv add dash
```

**Architecture change:** Script no longer exits after opening the browser. It
runs a local server on `localhost:8050`, which the browser connects to. Closing
the terminal kills the server.

**Acceptance:** All filters update the 3D plot without reloading the page.
Performance acceptable with up to ~500 displayed systems.

---

### Phase 5 — Galactic context shell

**Goal:** Show the selected subset against a faint background of the full
stellar neighbourhood, so corridors and voids in the simulation space are
visible.

**Approach:** Load a random sample of ~2000 nearby background stars (within
200 pc of the displayed selection centroid) as very small, very faint grey
dots behind the highlighted selection. Plotly renders all points in one
WebGL pass, so 2000 + a few dozen is still instant.

**New inputs:**
- `--context` flag to enable background shell
- `--context-radius N` (default 200 pc)

**Acceptance:** Simulation space visually placed in the broader galaxy;
voids and dense clusters in the Hipparcos data are visible.

---

## Key parameters

| Parameter | Value | Notes |
|---|---|---|
| Coordinate unit in DB | milliparsecs (integer) | Divide by 1000 for display |
| Coordinate system | ICRS Cartesian | x toward galactic anticentre, z toward galactic north |
| Default Plotly port (Phase 4+) | 8050 | `localhost:8050` |
| Background sample size (Phase 5) | ~2000 stars | Performance headroom remains ample |

---

## Files created

| File | Purpose |
|---|---|
| `scripts/star_viewer.py` | Main viewer script (all phases, feature-flagged) |
| `specs/viewer/viewer_spec.md` | This document |
