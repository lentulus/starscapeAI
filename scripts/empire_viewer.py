"""empire_viewer.py — Empire map for Starscape 5.

Shows every system that any polity occupies (SystemPresence), coloured by
polity, with distinct glyphs for homeworlds and markers for battle sites
(bombardment events).  Jump routes are drawn between displayed systems.

Output is a fully self-contained HTML file (~3 MB Plotly.js bundled).
Works on any machine with a browser, no Python or internet required.

Usage:
    uv run scripts/empire_viewer.py
    uv run scripts/empire_viewer.py --save ~/Desktop/empire.html
    uv run scripts/empire_viewer.py --no-routes
    uv run scripts/empire_viewer.py --game-db PATH --star-db PATH
"""

from __future__ import annotations

import argparse
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
_BG = "#0a0a14"   # deep space background

# One colour per polity_id — chosen for contrast on a dark background
# Human polities (13–15) get cool tones; alien polities get warm/vivid tones.
_POLITY_COLOUR: dict[int, str] = {
    1:  "#4fc3f7",  # Kreeth Dominion     — sky blue
    2:  "#81c784",  # Vashori Compact      — green
    3:  "#ef5350",  # Kraathi Crusade      — red
    4:  "#ff8a65",  # Nakhavi Reach        — coral orange
    5:  "#ba68c8",  # Skharri Pride        — purple
    6:  "#4dd0e1",  # Vaelkhi Choth        — cyan
    7:  "#f48fb1",  # Shekhari Exchange    — pink
    8:  "#a1887f",  # Golvhaan Reach       — warm brown
    9:  "#fff59d",  # Nhaveth Court A      — pale yellow
    10: "#ffd54f",  # Nhaveth Court B      — amber
    11: "#ffb300",  # Nhaveth Court C      — gold
    12: "#90a4ae",  # Vardhek Roidhunate   — slate
    13: "#26c6da",  # Oceania              — teal
    14: "#ef9a9a",  # Eurasia              — rose
    15: "#ce93d8",  # Eastasia             — lavender
}
_DEFAULT_COLOUR = "#cccccc"   # fallback for unknown polity IDs

# Marker symbols
_SYM_HOMEWORLD = "square"     # ■ homeworld / capital
_SYM_PRESENCE  = "circle"     # ● ordinary presence
_SYM_BATTLE    = "cross"      # ✕ bombardment site


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

def fetch_polities(game_conn: sqlite3.Connection) -> dict[int, dict]:
    """Return {polity_id: {name, capital_system_id}} for all polities."""
    rows = game_conn.execute(
        "SELECT polity_id, name, capital_system_id FROM Polity_head"
    ).fetchall()
    return {
        r["polity_id"]: {
            "name": r["name"],
            "capital": r["capital_system_id"],
        }
        for r in rows
    }


def fetch_presences(game_conn: sqlite3.Connection) -> list[dict]:
    """Return current presences (head view): system_id, polity_id, control_state."""
    rows = game_conn.execute(
        """
        SELECT sp.system_id, sp.polity_id, sp.control_state
        FROM   SystemPresence_head sp
        ORDER  BY sp.polity_id, sp.system_id
        """
    ).fetchall()
    return [
        {
            "system_id":     r["system_id"],
            "polity_id":     r["polity_id"],
            "control_state": r["control_state"],
        }
        for r in rows
    ]


def fetch_bombardment_sites(game_conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Return {system_id: [summary, ...]} for all bombardment events."""
    rows = game_conn.execute(
        "SELECT system_id, summary FROM GameEvent "
        "WHERE event_type = 'bombardment' AND system_id IS NOT NULL"
    ).fetchall()
    result: dict[int, list[str]] = {}
    for r in rows:
        result.setdefault(r["system_id"], []).append(r["summary"])
    return result


def fetch_place_names(
    game_conn: sqlite3.Connection,
    system_ids: set[int],
) -> dict[int, str]:
    """Return {system_id: place_name} for named systems."""
    if not system_ids:
        return {}
    ph = ",".join("?" * len(system_ids))
    try:
        rows = game_conn.execute(
            f"SELECT object_id, name FROM PlaceName "
            f"WHERE object_type = 'system' AND object_id IN ({ph})",
            list(system_ids),
        ).fetchall()
        return {r["object_id"]: r["name"] for r in rows}
    except sqlite3.OperationalError:
        return {}


def fetch_star_positions(
    star_conn: sqlite3.Connection,
    system_ids: set[int],
) -> dict[int, dict]:
    """Return {system_id: {x_pc, y_pc, z_pc, spectral}} for each system."""
    if not system_ids:
        return {}
    ids = list(system_ids)
    ph  = ",".join("?" * len(ids))
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
        ids,
    ).fetchall()
    return {
        r["system_id"]: {
            "x": r["x_pc"],
            "y": r["y_pc"],
            "z": r["z_pc"],
            "spectral": (r["spectral"] or "?").strip(),
        }
        for r in rows
    }


def fetch_waypoint_systems(
    game_conn: sqlite3.Connection,
    occupied_ids: set[int],
) -> list[tuple[int, float, float, float]]:
    """Return (system_id, x_pc, y_pc, z_pc) for systems that appear in
    JumpRoute but have no presence — visited waypoints along the network.
    Uses coordinates embedded in JumpRoute; no star-db join needed."""
    if not occupied_ids:
        return []
    ph  = ",".join("?" * len(occupied_ids))
    ids = list(occupied_ids)
    rows = game_conn.execute(
        f"""
        SELECT DISTINCT from_system_id AS system_id,
               from_x_mpc * {_MPC_TO_PC} AS x_pc,
               from_y_mpc * {_MPC_TO_PC} AS y_pc,
               from_z_mpc * {_MPC_TO_PC} AS z_pc
        FROM   JumpRoute
        WHERE  to_system_id   IN ({ph})
          AND  from_system_id NOT IN ({ph})
        UNION
        SELECT DISTINCT to_system_id AS system_id,
               to_x_mpc * {_MPC_TO_PC} AS x_pc,
               to_y_mpc * {_MPC_TO_PC} AS y_pc,
               to_z_mpc * {_MPC_TO_PC} AS z_pc
        FROM   JumpRoute
        WHERE  from_system_id IN ({ph})
          AND  to_system_id   NOT IN ({ph})
        """,
        ids + ids + ids + ids,
    ).fetchall()
    return [(r["system_id"], r["x_pc"], r["y_pc"], r["z_pc"]) for r in rows]


def fetch_jump_routes(
    game_conn: sqlite3.Connection,
    occupied_ids: set[int],
) -> list[tuple[float, float, float, float, float, float]]:
    """Return (fx,fy,fz,tx,ty,tz) in parsecs for routes where AT LEAST ONE
    endpoint is an occupied system.  This shows the full jump network that
    connects the empire even when the path passes through unoccupied systems.
    Coordinates are embedded in JumpRoute so no star-db join is needed."""
    if not occupied_ids:
        return []
    ph  = ",".join("?" * len(occupied_ids))
    ids = list(occupied_ids)
    rows = game_conn.execute(
        f"""
        SELECT from_x_mpc * {_MPC_TO_PC} AS fx,
               from_y_mpc * {_MPC_TO_PC} AS fy,
               from_z_mpc * {_MPC_TO_PC} AS fz,
               to_x_mpc   * {_MPC_TO_PC} AS tx,
               to_y_mpc   * {_MPC_TO_PC} AS ty,
               to_z_mpc   * {_MPC_TO_PC} AS tz
        FROM   JumpRoute
        WHERE  from_system_id IN ({ph})
           OR  to_system_id   IN ({ph})
        """,
        ids + ids,
    ).fetchall()
    return [(r["fx"], r["fy"], r["fz"], r["tx"], r["ty"], r["tz"]) for r in rows]


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def build_figure(
    presences:       list[dict],
    polities:        dict[int, dict],
    star_positions:  dict[int, dict],
    place_names:     dict[int, str],
    bombardments:    dict[int, list[str]],
    waypoints:       list[tuple[int, float, float, float]],
    routes:          list[tuple],
    tick:            int,
) -> go.Figure:
    """Build the empire 3D scatter figure."""

    # Set of homeworld system IDs across all polities
    homeworlds: set[int] = {
        p["capital"] for p in polities.values() if p["capital"] is not None
    }

    # Group presences by polity
    by_polity: dict[int, list[dict]] = {}
    for pres in presences:
        by_polity.setdefault(pres["polity_id"], []).append(pres)

    traces: list[go.BaseTraceType] = []

    # One trace per polity
    for polity_id in sorted(by_polity):
        pname  = polities.get(polity_id, {}).get("name", f"Polity {polity_id}")
        colour = _POLITY_COLOUR.get(polity_id, _DEFAULT_COLOUR)
        group  = by_polity[polity_id]

        xs, ys, zs, labels, symbols = [], [], [], [], []
        for pres in group:
            sid  = pres["system_id"]
            pos  = star_positions.get(sid)
            if pos is None:
                continue  # position data missing — skip

            xs.append(pos["x"])
            ys.append(pos["y"])
            zs.append(pos["z"])

            # Symbol: square for homeworld, circle for everything else
            symbols.append(_SYM_HOMEWORLD if sid in homeworlds else _SYM_PRESENCE)

            # Hover label
            name = place_names.get(sid, f"sys-{sid}")
            lines = [f"<b>{name}</b>"]
            lines.append(f"polity: {pname}")
            lines.append(f"control: {pres['control_state'] or '—'}")
            lines.append(f"spectral: {pos['spectral']}")
            lines.append(f"({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}) pc")
            if sid in homeworlds:
                lines.append("<b>★ HOMEWORLD</b>")
            if sid in bombardments:
                lines.append(f"<b>💥 BATTLE SITE ({len(bombardments[sid])} bombardment(s))</b>")
                for s in bombardments[sid]:
                    lines.append(f"  · {s}")
            labels.append("<br>".join(lines))

        if not xs:
            continue

        traces.append(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="markers",
            name=pname,
            marker=dict(
                size=8,
                color=colour,
                symbol=symbols,
                line=dict(width=0.8, color="rgba(255,255,255,0.5)"),
                opacity=0.92,
            ),
            text=labels,
            hovertemplate="%{text}<extra></extra>",
        ))

    # Waypoint systems — visited but unoccupied nodes in the jump network
    if waypoints:
        wx = [w[1] for w in waypoints]
        wy = [w[2] for w in waypoints]
        wz = [w[3] for w in waypoints]
        wlabels = [f"sys-{w[0]}<br>waypoint (visited, no presence)" for w in waypoints]
        traces.append(go.Scatter3d(
            x=wx, y=wy, z=wz,
            mode="markers",
            name=f"Waypoints ({len(waypoints)})",
            marker=dict(
                size=3,
                color="rgba(255, 255, 255, 0.55)",
                symbol="circle",
                line=dict(width=0),
            ),
            text=wlabels,
            hovertemplate="%{text}<extra></extra>",
        ))

    # Battle sites — separate trace so they appear in the legend and can be toggled
    battle_sids = [
        sid for sid in bombardments
        if sid in star_positions
    ]
    if battle_sids:
        bx, by_, bz, blabels = [], [], [], []
        for sid in battle_sids:
            pos  = star_positions[sid]
            name = place_names.get(sid, f"sys-{sid}")
            bx.append(pos["x"])
            by_.append(pos["y"])
            bz.append(pos["z"])
            events = bombardments[sid]
            lines  = [f"<b>{name}</b>", "<b>BATTLE SITE</b>"]
            for s in events:
                lines.append(f"· {s}")
            blabels.append("<br>".join(lines))

        traces.append(go.Scatter3d(
            x=bx, y=by_, z=bz,
            mode="markers",
            name=f"Battle sites ({len(battle_sids)})",
            marker=dict(
                size=14,
                color="rgba(255, 80, 40, 0.0)",     # transparent fill
                symbol=_SYM_BATTLE,
                line=dict(width=2.5, color="rgba(255, 80, 40, 0.90)"),
                opacity=1.0,
            ),
            text=blabels,
            hovertemplate="%{text}<extra></extra>",
        ))
    battle_trace_index = len(traces) - 1 if battle_sids else None

    # Jump routes — single trace with None separators
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
            line=dict(color="rgba(160, 180, 255, 0.18)", width=1),
            hoverinfo="skip",
        ))
    route_trace_index = len(traces) - 1 if routes else None

    # Count totals
    n_systems  = len({p["system_id"] for p in presences})
    n_polities = len(by_polity)
    title = (
        f"Starscape 5 — Empire Map · {n_systems} occupied systems · "
        f"{n_polities} polities · tick {tick}"
    )

    # In-browser controls
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
    ]

    y_offset = 1.05

    # Row 2: route toggle (only when routes drawn)
    if route_trace_index is not None:
        updatemenus.append(dict(
            type="buttons",
            direction="right",
            showactive=True,
            active=0,
            x=0.0, y=y_offset,
            xanchor="left", yanchor="top",
            bgcolor="#1a1a2e",
            bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(label="Routes on",  method="restyle",
                     args=[{"visible": True},  [route_trace_index]]),
                dict(label="Routes off", method="restyle",
                     args=[{"visible": False}, [route_trace_index]]),
            ],
        ))
        y_offset -= 0.08

    # Row 3: marker size
    updatemenus.append(dict(
        type="buttons",
        direction="right",
        showactive=True,
        active=1,
        x=0.0, y=y_offset,
        xanchor="left", yanchor="top",
        bgcolor="#1a1a2e",
        bordercolor="#444466",
        font=dict(color="white", size=11),
        buttons=[
            dict(label="· Small",  method="restyle", args=[{"marker.size": 5}]),
            dict(label="● Medium", method="restyle", args=[{"marker.size": 8}]),
            dict(label="⬤ Large",  method="restyle", args=[{"marker.size": 12}]),
        ],
    ))

    annotations = [
        dict(
            text="■ homeworld  ● presence  ✕ battle site",
            x=1.0, y=0.01,
            xref="paper", yref="paper",
            xanchor="right", yanchor="bottom",
            showarrow=False,
            font=dict(color="#888899", size=10),
        )
    ]

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=title, font=dict(color="white", size=14)),
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
            font=dict(color="white", size=11),
            bgcolor=_BG,
            bordercolor="#333355",
            borderwidth=1,
            title=dict(text="Polity<br><sup>(click to hide)</sup>",
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
        description="Starscape 5 — Empire map: all occupied systems by polity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--star-db", default=str(STARSCAPE_DB), metavar="PATH",
                        help=f"Path to starscape.db (default: {STARSCAPE_DB})")
    parser.add_argument("--game-db", default=str(GAME_DB), metavar="PATH",
                        help=f"Path to game.db (default: {GAME_DB})")
    parser.add_argument("--save", metavar="FILE",
                        help="Save HTML to FILE (also opens browser).")
    parser.add_argument("--no-routes", action="store_true",
                        help="Suppress jump route lines.")
    args = parser.parse_args()

    star_path = Path(args.star_db)
    game_path = Path(args.game_db)

    if not star_path.exists():
        sys.exit(f"starscape.db not found: {star_path}")
    if not game_path.exists():
        sys.exit(f"game.db not found: {game_path}")

    print("Loading empire data...")
    star_conn = _open(star_path)
    game_conn = _open(game_path)

    polities     = fetch_polities(game_conn)
    presences    = fetch_presences(game_conn)
    bombardments = fetch_bombardment_sites(game_conn)

    # Get current tick
    tick_row = game_conn.execute(
        "SELECT last_committed_tick AS t FROM GameState ORDER BY state_id DESC LIMIT 1"
    ).fetchone()
    tick = tick_row["t"] if tick_row and tick_row["t"] else 0

    if not presences:
        sys.exit("No presences found in game.db — has the simulation run yet?")

    displayed_ids = {p["system_id"] for p in presences}
    # Also include bombardment sites even if no longer occupied
    displayed_ids |= {sid for sid in bombardments}

    print(f"  {len(presences)} presence records across "
          f"{len(displayed_ids)} systems, "
          f"{len(polities)} polities")
    print(f"  {len(bombardments)} bombardment site(s)")

    star_positions = fetch_star_positions(star_conn, displayed_ids)
    place_names    = fetch_place_names(game_conn, displayed_ids)
    waypoints      = fetch_waypoint_systems(game_conn, displayed_ids)
    routes         = [] if args.no_routes else fetch_jump_routes(game_conn, displayed_ids)

    star_conn.close()
    game_conn.close()

    print(f"  {len(waypoints)} waypoint system(s) (visited, no presence)")
    if routes:
        print(f"  {len(routes)} jump route(s)")

    print("Building figure...")
    fig = build_figure(
        presences=presences,
        polities=polities,
        star_positions=star_positions,
        place_names=place_names,
        bombardments=bombardments,
        waypoints=waypoints,
        routes=routes,
        tick=tick,
    )
    _render(fig, Path(args.save) if args.save else None)


if __name__ == "__main__":
    main()
