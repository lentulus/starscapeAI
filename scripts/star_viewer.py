"""star_viewer.py — Interactive 3D star map for Starscape 5.

Phase 1.5: terminal questionnaire selects what to display; self-contained
HTML output has in-browser camera presets and marker-size controls.

Selection modes
  • No args → terminal questionnaire (system IDs / polity / radius)
  • Positional args → display those system IDs directly (Phase 1 compatible)
  • --polity N [--tier all|visited|presence] → display polity knowledge
  • --radius SYSTEM_ID PARSECS → display systems within radius

In-browser controls (no server required — pure JavaScript in the HTML)
  • Camera presets: Perspective / Top / Front / Side
  • Marker size: Small / Medium / Large
  • Legend: click spectral class to show/hide (Plotly built-in)

Output is a fully self-contained HTML (~3 MB, Plotly.js bundled).
Works on any machine with a browser, no Python or internet required.

Usage:
    uv run scripts/star_viewer.py                       # questionnaire
    uv run scripts/star_viewer.py 898454 1066934        # explicit IDs
    uv run scripts/star_viewer.py --polity 1 --tier visited
    uv run scripts/star_viewer.py --radius 898454 25
    uv run scripts/star_viewer.py --save ~/Desktop/map.html
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import tempfile
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

STARSCAPE_DB = Path("/Volumes/Data/starscape4/starscape.db")
GAME_DB      = Path("/Volumes/Data/starscape4/game.db")

_MPC_TO_PC = 1.0 / 1000.0

# Spectral class → colour (approximate blackbody tint, dark-background friendly)
_SPECTRAL_COLOUR: dict[str, str] = {
    "O": "#9eb0ff",   # blue-violet
    "B": "#b7caff",   # blue-white
    "A": "#d8e2ff",   # white-blue
    "F": "#fff4e8",   # yellow-white
    "G": "#ffdf80",   # yellow (sun-like)
    "K": "#ffb347",   # orange
    "M": "#ff6060",   # red
    "W": "#c0a0ff",   # Wolf-Rayet — violet
    "?": "#888888",   # unknown
}

# Knowledge tier → marker symbol (3D scatter supports these)
_TIER_SYMBOL: dict[str, str] = {
    "presence": "diamond",      # colony/outpost/controlled — largest visual weight
    "visited":  "circle",       # surveyed
    "passive":  "circle-open",  # passive scan only — hollow
    "unknown":  "circle",       # no game.db data
}

_BG = "#0a0a14"   # deep space background


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _try_open_game(path: Path) -> sqlite3.Connection | None:
    if path.exists():
        return _open(path)
    return None


# ---------------------------------------------------------------------------
# Data selection
# ---------------------------------------------------------------------------

def fetch_polities(game_conn: sqlite3.Connection) -> list[dict]:
    rows = game_conn.execute(
        "SELECT polity_id, name FROM Polity GROUP BY polity_id ORDER BY polity_id"
    ).fetchall()
    return [{"id": r["polity_id"], "name": r["name"]} for r in rows]


def select_by_polity(
    game_conn: sqlite3.Connection,
    polity_id: int,
    tier: str,           # "all" | "visited" | "presence"
) -> list[int]:
    """Return system_ids for a polity filtered by knowledge tier."""
    if tier == "presence":
        rows = game_conn.execute(
            "SELECT DISTINCT system_id FROM SystemPresence WHERE polity_id = ?",
            (polity_id,),
        ).fetchall()
    elif tier == "visited":
        rows = game_conn.execute(
            """
            SELECT DISTINCT system_id FROM SystemIntelligence
            WHERE polity_id = ? AND knowledge_tier = 'visited'
            UNION
            SELECT DISTINCT system_id FROM SystemPresence WHERE polity_id = ?
            """,
            (polity_id, polity_id),
        ).fetchall()
    else:  # all
        rows = game_conn.execute(
            "SELECT DISTINCT system_id FROM SystemIntelligence WHERE polity_id = ?",
            (polity_id,),
        ).fetchall()
    return [r["system_id"] for r in rows]


def select_by_radius(
    star_conn: sqlite3.Connection,
    anchor_id: int,
    radius_pc: float,
) -> list[int]:
    """Return system_ids within radius_pc of anchor_id (exact Euclidean distance)."""
    anchor = star_conn.execute(
        "SELECT x, y, z FROM IndexedIntegerDistinctSystems WHERE system_id = ?",
        (anchor_id,),
    ).fetchone()
    if anchor is None:
        print(f"Anchor system {anchor_id} not found.", file=sys.stderr)
        return []

    ax, ay, az = anchor["x"], anchor["y"], anchor["z"]
    radius_mpc = radius_pc * 1000.0

    # Bounding box pre-filter — much cheaper than scanning all 2.47M rows
    rows = star_conn.execute(
        """
        SELECT system_id, x, y, z
        FROM   IndexedIntegerDistinctSystems
        WHERE  x BETWEEN ? AND ?
          AND  y BETWEEN ? AND ?
          AND  z BETWEEN ? AND ?
        """,
        (ax - radius_mpc, ax + radius_mpc,
         ay - radius_mpc, ay + radius_mpc,
         az - radius_mpc, az + radius_mpc),
    ).fetchall()

    # Exact distance filter
    result = []
    for r in rows:
        dist = math.sqrt((r["x"]-ax)**2 + (r["y"]-ay)**2 + (r["z"]-az)**2)
        if dist <= radius_mpc:
            result.append(r["system_id"])
    return result


# ---------------------------------------------------------------------------
# Data enrichment
# ---------------------------------------------------------------------------

def fetch_jump_routes(
    game_conn: sqlite3.Connection | None,
    displayed_ids: set[int],
) -> list[tuple[float, float, float, float, float, float]]:
    """Return (fx, fy, fz, tx, ty, tz) in parsecs for routes where both
    endpoints are in displayed_ids.  Uses coordinates embedded in JumpRoute."""
    if game_conn is None or not displayed_ids:
        return []
    ph = ",".join("?" * len(displayed_ids))
    ids = list(displayed_ids)
    rows = game_conn.execute(
        f"""
        SELECT from_system_id, to_system_id,
               from_x_mpc * {_MPC_TO_PC} AS fx,
               from_y_mpc * {_MPC_TO_PC} AS fy,
               from_z_mpc * {_MPC_TO_PC} AS fz,
               to_x_mpc   * {_MPC_TO_PC} AS tx,
               to_y_mpc   * {_MPC_TO_PC} AS ty,
               to_z_mpc   * {_MPC_TO_PC} AS tz
        FROM   JumpRoute
        WHERE  from_system_id IN ({ph})
          AND  to_system_id   IN ({ph})
        """,
        ids + ids,
    ).fetchall()
    return [(r["fx"], r["fy"], r["fz"], r["tx"], r["ty"], r["tz"]) for r in rows]


def fetch_star_positions(
    star_conn: sqlite3.Connection,
    system_ids: list[int],
) -> list[dict]:
    """Position and spectral type for each system_id."""
    if not system_ids:
        return []
    ph = ",".join("?" * len(system_ids))
    rows = star_conn.execute(
        f"""
        SELECT s.system_id,
               s.x * {_MPC_TO_PC} AS x_pc,
               s.y * {_MPC_TO_PC} AS y_pc,
               s.z * {_MPC_TO_PC} AS z_pc,
               st.spectral
        FROM   IndexedIntegerDistinctSystems s
        LEFT JOIN IndexedIntegerDistinctStars st ON st.system_id = s.system_id
        WHERE  s.system_id IN ({ph})
        """,
        system_ids,
    ).fetchall()

    stars = []
    for r in rows:
        sp = (r["spectral"] or "?").strip()
        cls = sp[0].upper() if sp else "?"
        stars.append({
            "system_id": r["system_id"],
            "x": r["x_pc"], "y": r["y_pc"], "z": r["z_pc"],
            "spectral": sp,
            "cls": cls,
            "colour": _SPECTRAL_COLOUR.get(cls, _SPECTRAL_COLOUR["?"]),
        })

    found = {s["system_id"] for s in stars}
    missing = set(system_ids) - found
    if missing:
        print(f"Warning: {len(missing)} system ID(s) not found in starscape.db",
              file=sys.stderr)
    return stars


def fetch_game_context(
    game_conn: sqlite3.Connection | None,
    system_ids: list[int],
) -> dict[int, dict]:
    """Return per-system game context: tier, place name, control state."""
    if game_conn is None or not system_ids:
        return {}
    ph = ",".join("?" * len(system_ids))

    # Intelligence tier
    intel_rows = game_conn.execute(
        f"SELECT system_id, knowledge_tier, world_potential, habitable "
        f"FROM SystemIntelligence WHERE system_id IN ({ph})",
        system_ids,
    ).fetchall()
    ctx: dict[int, dict] = {}
    for r in intel_rows:
        ctx[r["system_id"]] = {
            "tier": r["knowledge_tier"],
            "world_potential": r["world_potential"],
            "habitable": r["habitable"],
            "control_state": None,
            "polity_name": None,
            "place_name": None,
        }

    # Presence (overwrites tier to "presence" if any presence exists)
    pres_rows = game_conn.execute(
        f"""
        SELECT sp.system_id, sp.control_state, p.name AS polity_name
        FROM   SystemPresence sp
        JOIN   Polity p ON p.polity_id = sp.polity_id
        WHERE  sp.system_id IN ({ph})
        """,
        system_ids,
    ).fetchall()
    for r in pres_rows:
        sid = r["system_id"]
        if sid not in ctx:
            ctx[sid] = {"tier": "presence", "world_potential": None,
                        "habitable": None, "control_state": None,
                        "polity_name": None, "place_name": None}
        ctx[sid]["tier"] = "presence"
        ctx[sid]["control_state"] = r["control_state"]
        ctx[sid]["polity_name"] = r["polity_name"]

    # Place names (table may be empty)
    try:
        name_rows = game_conn.execute(
            f"SELECT object_id, name FROM PlaceName "
            f"WHERE object_type = 'system' AND object_id IN ({ph})",
            system_ids,
        ).fetchall()
        for r in name_rows:
            if r["object_id"] in ctx:
                ctx[r["object_id"]]["place_name"] = r["name"]
    except sqlite3.OperationalError:
        pass   # table schema mismatch — skip names

    return ctx


def _hover_label(star: dict, ctx: dict | None) -> str:
    """Build multi-line hover string for a star."""
    sid = star["system_id"]
    name = (ctx or {}).get("place_name") or f"sys-{sid}"
    lines = [f"<b>{name}</b>"]
    lines.append(f"spectral: {star['spectral']}")
    lines.append(f"({star['x']:.1f}, {star['y']:.1f}, {star['z']:.1f}) pc")
    if ctx:
        tier = ctx.get("tier", "unknown")
        lines.append(f"tier: {tier}")
        if ctx.get("control_state"):
            lines.append(f"control: {ctx['control_state']}")
        if ctx.get("polity_name"):
            lines.append(f"polity: {ctx['polity_name']}")
        wp = ctx.get("world_potential")
        if wp:
            lines.append(f"world potential: {wp}")
        if ctx.get("habitable"):
            lines.append("habitable: yes")
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Terminal questionnaire
# ---------------------------------------------------------------------------

def _ask(prompt_text: str, valid: list[str] | None = None) -> str:
    """Prompt with optional validation loop."""
    while True:
        try:
            answer = input(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if valid is None or answer in valid:
            return answer
        print(f"  Please enter one of: {', '.join(valid)}")


def run_questionnaire(
    star_conn: sqlite3.Connection,
    game_conn: sqlite3.Connection | None,
) -> tuple[list[int], str]:
    """Interactive selection. Returns (system_ids, description_string)."""
    print()
    print("=== Starscape 5 Star Viewer ===")
    print()

    modes = ["1", "2", "3"] if game_conn else ["1", "3"]
    mode_lines = [
        "  [1] Enter system IDs manually",
    ]
    if game_conn:
        mode_lines.append("  [2] All systems known to a polity")
    mode_lines.append("  [3] All systems within N parsecs of an anchor system")
    print("Select systems to display:")
    for line in mode_lines:
        print(line)
    print()

    mode = _ask(f"Choice [{'/'.join(modes)}]: ", modes)

    if mode == "1":
        raw = _ask("System IDs (space-separated): ")
        try:
            ids = [int(t) for t in raw.split()]
        except ValueError:
            sys.exit("Invalid system IDs — must be integers.")
        if not ids:
            sys.exit("No IDs provided.")
        return ids, f"{len(ids)} explicit system IDs"

    if mode == "2":
        polities = fetch_polities(game_conn)
        print()
        print("Available polities:")
        for p in polities:
            print(f"  {p['id']:3d}. {p['name']}")
        print()
        pid_str = _ask("Polity number: ")
        try:
            pid = int(pid_str)
        except ValueError:
            sys.exit("Invalid polity number.")
        names = {p["id"]: p["name"] for p in polities}
        if pid not in names:
            sys.exit(f"No polity with ID {pid}.")

        print()
        print("Knowledge tier:")
        print("  [1] All known systems (visited + passive scan)")
        print("  [2] Surveyed systems (visited + any presence)")
        print("  [3] Systems with a presence only (outpost / colony / controlled)")
        print()
        tier_choice = _ask("Tier [1/2/3]: ", ["1", "2", "3"])
        tier_map = {"1": "all", "2": "visited", "3": "presence"}
        tier = tier_map[tier_choice]

        ids = select_by_polity(game_conn, pid, tier)
        desc = f"{names[pid]} — {tier} — {len(ids)} systems"
        print(f"\nFound {len(ids)} systems.")
        return ids, desc

    # mode == "3"
    anchor_str = _ask("\nAnchor system ID: ")
    try:
        anchor_id = int(anchor_str)
    except ValueError:
        sys.exit("Invalid system ID.")
    radius_str = _ask("Radius in parsecs: ")
    try:
        radius_pc = float(radius_str)
    except ValueError:
        sys.exit("Invalid radius.")

    ids = select_by_radius(star_conn, anchor_id, radius_pc)
    desc = f"{len(ids)} systems within {radius_pc:.0f} pc of sys-{anchor_id}"
    print(f"\nFound {len(ids)} systems.")
    return ids, desc


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def build_figure(
    stars: list[dict],
    game_ctx: dict[int, dict],
    routes: list[tuple],
    title_suffix: str = "",
) -> go.Figure:
    """Build a Plotly 3D scatter figure with in-browser controls."""

    # Group by spectral class; within each group store per-point symbol from tier
    by_cls: dict[str, list[dict]] = {}
    for s in stars:
        by_cls.setdefault(s["cls"], []).append(s)

    traces = []
    for cls in sorted(by_cls):
        group = by_cls[cls]
        colour = _SPECTRAL_COLOUR.get(cls, _SPECTRAL_COLOUR["?"])

        symbols = []
        labels  = []
        for s in group:
            ctx = game_ctx.get(s["system_id"])
            tier = ctx["tier"] if ctx else "unknown"
            symbols.append(_TIER_SYMBOL.get(tier, "circle"))
            labels.append(_hover_label(s, ctx))

        traces.append(go.Scatter3d(
            x=[s["x"] for s in group],
            y=[s["y"] for s in group],
            z=[s["z"] for s in group],
            mode="markers",
            name=f"Class {cls}",
            marker=dict(
                size=7,
                color=colour,
                symbol=symbols,
                line=dict(width=0.4, color="rgba(255,255,255,0.4)"),
                opacity=0.9,
            ),
            text=labels,
            hovertemplate="%{text}<extra></extra>",
        ))

    # Jump route trace — one Scatter3d line trace using None separators
    # between segments so Plotly draws them as disconnected lines.
    if routes:
        rx: list[float | None] = []
        ry: list[float | None] = []
        rz: list[float | None] = []
        for fx, fy, fz, tx, ty, tz in routes:
            rx += [fx, tx, None]
            ry += [fy, ty, None]
            rz += [fz, tz, None]
        traces.append(go.Scatter3d(
            x=rx, y=ry, z=rz,
            mode="lines",
            name=f"Jump routes ({len(routes)})",
            line=dict(color="rgba(120, 160, 255, 0.20)", width=1),
            hoverinfo="skip",
        ))

    n = len(stars)
    title = f"Starscape 5 — {n} system{'s' if n != 1 else ''}"
    if title_suffix:
        title += f"  ·  {title_suffix}"

    # In-browser controls — pure Plotly JavaScript, no server needed
    updatemenus = [
        # Row 1: camera presets
        dict(
            type="buttons",
            direction="right",
            showactive=False,
            x=0.0, y=1.13,
            xanchor="left", yanchor="top",
            bgcolor="#1a1a2e",
            bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(
                    label="⟳ Perspective",
                    method="relayout",
                    args=[{"scene.camera.eye": {"x": 1.5, "y": 1.5, "z": 1.0},
                           "scene.camera.up":  {"x": 0,   "y": 0,   "z": 1}}],
                ),
                dict(
                    label="Top (XY)",
                    method="relayout",
                    args=[{"scene.camera.eye": {"x": 0.001, "y": 0.001, "z": 2.5},
                           "scene.camera.up":  {"x": 0,     "y": 1,     "z": 0}}],
                ),
                dict(
                    label="Front (XZ)",
                    method="relayout",
                    args=[{"scene.camera.eye": {"x": 0.001, "y": 2.5, "z": 0.001},
                           "scene.camera.up":  {"x": 0,     "y": 0,   "z": 1}}],
                ),
                dict(
                    label="Side (YZ)",
                    method="relayout",
                    args=[{"scene.camera.eye": {"x": 2.5, "y": 0.001, "z": 0.001},
                           "scene.camera.up":  {"x": 0,   "y": 0,     "z": 1}}],
                ),
            ],
        ),
        # Row 2: route toggle (only shown when routes exist)
        *([dict(
            type="buttons",
            direction="right",
            showactive=True,
            active=0,   # Routes on by default
            x=0.0, y=1.05,
            xanchor="left", yanchor="top",
            bgcolor="#1a1a2e",
            bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(label="Routes on",  method="restyle",
                     args=[{"visible": True},  [-1]]),
                dict(label="Routes off", method="restyle",
                     args=[{"visible": False}, [-1]]),
            ],
        )] if routes else []),
        # Row 3 (or 2 if no routes): marker size
        dict(
            type="buttons",
            direction="right",
            showactive=True,
            active=1,   # Medium is default
            x=0.0, y=0.97 if routes else 1.05,
            xanchor="left", yanchor="top",
            bgcolor="#1a1a2e",
            bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(label="· Small",  method="restyle", args=[{"marker.size": 4}]),
                dict(label="● Medium", method="restyle", args=[{"marker.size": 7}]),
                dict(label="⬤ Large",  method="restyle", args=[{"marker.size": 11}]),
            ],
        ),
    ]

    # Symbol legend annotation (game context only)
    annotations = []
    if game_ctx:
        annotations.append(dict(
            text="◆ presence  ● visited  ○ passive",
            x=1.0, y=0.01,
            xref="paper", yref="paper",
            xanchor="right", yanchor="bottom",
            showarrow=False,
            font=dict(color="#888899", size=10),
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=title, font=dict(color="white", size=15)),
        paper_bgcolor=_BG,
        scene=dict(
            bgcolor=_BG,
            xaxis=dict(title="X (pc)", color="white",
                       gridcolor="#1e1e3a", showbackground=False),
            yaxis=dict(title="Y (pc)", color="white",
                       gridcolor="#1e1e3a", showbackground=False),
            zaxis=dict(title="Z (pc)", color="white",
                       gridcolor="#1e1e3a", showbackground=False),
            aspectmode="data",
        ),
        legend=dict(
            font=dict(color="white"),
            bgcolor=_BG,
            title=dict(text="Spectral class<br><sup>(click to hide)</sup>",
                       font=dict(color="#888899")),
        ),
        updatemenus=updatemenus,
        annotations=annotations,
        margin=dict(l=0, r=0, t=80, b=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _render(fig: go.Figure, save_path: Path | None) -> None:
    if save_path:
        fig.write_html(str(save_path), include_plotlyjs=True)
        print(f"Saved: {save_path}")
        webbrowser.open(save_path.as_uri())
    else:
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            tmp = Path(f.name)
        fig.write_html(str(tmp), include_plotlyjs=True)
        print(f"Opening: {tmp}")
        webbrowser.open(tmp.as_uri())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Starscape 5 — 3D star viewer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "system_ids", nargs="*", type=int, metavar="SYSTEM_ID",
        help="System IDs to display (omit to run the questionnaire).",
    )
    parser.add_argument("--polity", type=int, metavar="N",
                        help="Display all systems known to polity N.")
    parser.add_argument(
        "--tier", choices=["all", "visited", "presence"], default="all",
        help="Knowledge tier filter when using --polity (default: all).",
    )
    parser.add_argument(
        "--radius", nargs=2, metavar=("SYSTEM_ID", "PARSECS"),
        help="Display all systems within PARSECS of SYSTEM_ID.",
    )
    parser.add_argument("--star-db", default=str(STARSCAPE_DB), metavar="PATH",
                        help=f"Path to starscape.db (default: {STARSCAPE_DB})")
    parser.add_argument("--game-db", default=str(GAME_DB), metavar="PATH",
                        help=f"Path to game.db (default: {GAME_DB})")
    parser.add_argument("--save", metavar="FILE",
                        help="Save HTML to FILE (also opens browser).")
    parser.add_argument("--no-routes", action="store_true",
                        help="Suppress jump route lines even when game.db is present.")
    args = parser.parse_args()

    star_path = Path(args.star_db)
    if not star_path.exists():
        sys.exit(f"starscape.db not found: {star_path}")

    star_conn = _open(star_path)
    game_conn = _try_open_game(Path(args.game_db))
    if game_conn is None and (args.polity or args.tier != "all"):
        sys.exit(f"game.db not found at {args.game_db} — cannot filter by polity.")

    # --- Determine system IDs ---
    desc = ""
    if args.system_ids:
        system_ids = args.system_ids
        desc = f"{len(system_ids)} explicit system IDs"
    elif args.polity:
        system_ids = select_by_polity(game_conn, args.polity, args.tier)
        desc = f"polity {args.polity} — {args.tier} — {len(system_ids)} systems"
    elif args.radius:
        anchor_id = int(args.radius[0])
        radius_pc = float(args.radius[1])
        system_ids = select_by_radius(star_conn, anchor_id, radius_pc)
        desc = f"{len(system_ids)} systems within {radius_pc:.0f} pc of sys-{anchor_id}"
    else:
        # Interactive questionnaire
        system_ids, desc = run_questionnaire(star_conn, game_conn)

    if not system_ids:
        sys.exit("No systems selected.")

    print(f"\nFetching data for {len(system_ids)} system(s)...")
    displayed = set(system_ids)
    stars    = fetch_star_positions(star_conn, system_ids)
    game_ctx = fetch_game_context(game_conn, system_ids)
    routes   = [] if args.no_routes else fetch_jump_routes(game_conn, displayed)
    star_conn.close()
    if game_conn:
        game_conn.close()

    if not stars:
        sys.exit("No matching systems found in starscape.db.")

    if routes:
        print(f"Drawing {len(routes)} jump route(s).")

    fig = build_figure(stars, game_ctx, routes, title_suffix=desc)
    _render(fig, Path(args.save) if args.save else None)


if __name__ == "__main__":
    main()
