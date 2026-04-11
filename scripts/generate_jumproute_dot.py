"""generate_jumproute_dot.py — Render the JumpRoute travel graph as a Graphviz .dot file.

Each node is a system that appears in at least one recorded jump route.
Node label shows:
  - system_id
  - position rounded to nearest parsec (x, y, z)
  - primary star spectral type (brightest star in system)
  - controlling polity name, or 'contested' / 'unclaimed'

Edges carry the jump distance in parsecs.

Usage:
    uv run scripts/generate_jumproute_dot.py              # → jumproutes.dot
    uv run scripts/generate_jumproute_dot.py -o travel.dot
    dot -Tsvg jumproutes.dot -o jumproutes.svg
    dot -Tpdf jumproutes.dot -o jumproutes.pdf
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

STARSCAPE_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
GAME_DB      = Path("game.db")

# Graphviz fillcolors cycled by polity_id (index into list)
_POLITY_COLORS = [
    "#AED6F1",  # light blue
    "#A9DFBF",  # light green
    "#F9E79F",  # light yellow
    "#F5CBA7",  # light orange
    "#D7BDE2",  # light purple
    "#FADBD8",  # light red/pink
    "#A2D9CE",  # teal
    "#F0B27A",  # amber
    "#ABB2B9",  # grey
    "#F1948A",  # salmon
    "#82E0AA",  # mint
]
_UNCLAIMED_COLOR  = "#FFFFFF"
_CONTESTED_COLOR  = "#E74C3C"  # red


def _dict_conn(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def load_routes(gconn: sqlite3.Connection) -> list[sqlite3.Row]:
    return gconn.execute(
        """
        SELECT from_system_id, to_system_id, dist_pc,
               from_x_mpc, from_y_mpc, from_z_mpc,
               to_x_mpc,   to_y_mpc,   to_z_mpc
        FROM JumpRoute
        ORDER BY from_system_id, to_system_id
        """
    ).fetchall()


def build_system_positions(
    routes: list[sqlite3.Row],
) -> dict[int, tuple[int, int, int]]:
    """Extract (x,y,z) in parsecs (rounded) for every system in the route graph."""
    positions: dict[int, tuple[int, int, int]] = {}
    for r in routes:
        for sid, xm, ym, zm in (
            (r["from_system_id"], r["from_x_mpc"], r["from_y_mpc"], r["from_z_mpc"]),
            (r["to_system_id"],   r["to_x_mpc"],   r["to_y_mpc"],   r["to_z_mpc"]),
        ):
            if sid not in positions:
                positions[sid] = (round(xm / 1000), round(ym / 1000), round(zm / 1000))
    return positions


def load_spectral(
    sconn: sqlite3.Connection, system_ids: set[int]
) -> dict[int, str]:
    """Return primary star spectral type per system (brightest = min absmag)."""
    if not system_ids:
        return {}
    placeholders = ",".join("?" * len(system_ids))
    rows = sconn.execute(
        f"""
        SELECT system_id, spectral
        FROM   IndexedIntegerDistinctStars
        WHERE  system_id IN ({placeholders})
        ORDER  BY absmag ASC
        """,
        list(system_ids),
    ).fetchall()
    # First row per system_id wins (lowest absmag = brightest = primary)
    result: dict[int, str] = {}
    for r in rows:
        sid = r["system_id"]
        if sid not in result:
            result[sid] = r["spectral"] or "?"
    return result


def load_polity_control(
    gconn: sqlite3.Connection, system_ids: set[int]
) -> tuple[dict[int, str], dict[int, str]]:
    """Return (control_map, color_map) for each system.

    control_map: system_id → polity name or 'contested' or 'unclaimed'
    color_map:   system_id → hex fill color
    """
    if not system_ids:
        return {}, {}

    placeholders = ",".join("?" * len(system_ids))

    # Get all presences with polity name and best development_level
    rows = gconn.execute(
        f"""
        SELECT sp.system_id, sp.polity_id, p.name,
               MAX(sp.development_level) AS max_dev,
               sp.control_state
        FROM   SystemPresence sp
        JOIN   Polity p ON p.polity_id = sp.polity_id
        WHERE  sp.system_id IN ({placeholders})
        GROUP  BY sp.system_id, sp.polity_id
        ORDER  BY sp.system_id, max_dev DESC
        """,
        list(system_ids),
    ).fetchall()

    # Also get homeworld capitals to label home systems
    homeworlds = {
        r["capital_system_id"]: r["polity_id"]
        for r in gconn.execute(
            "SELECT polity_id, capital_system_id FROM Polity "
            "WHERE capital_system_id IS NOT NULL"
        ).fetchall()
    }

    # Assign a stable color index per polity_id
    polity_color: dict[int, str] = {}
    color_idx = 0
    for r in gconn.execute(
        "SELECT polity_id FROM Polity ORDER BY polity_id"
    ).fetchall():
        polity_color[r["polity_id"]] = _POLITY_COLORS[color_idx % len(_POLITY_COLORS)]
        color_idx += 1

    # Aggregate per system
    from collections import defaultdict
    by_system: dict[int, list[tuple[int, str, int]]] = defaultdict(list)
    for r in rows:
        by_system[r["system_id"]].append((r["polity_id"], r["name"], r["max_dev"]))

    control_map: dict[int, str] = {}
    color_map:   dict[int, str] = {}

    for sid in system_ids:
        presences = by_system.get(sid, [])
        if not presences:
            control_map[sid] = "unclaimed"
            color_map[sid]   = _UNCLAIMED_COLOR
        elif len(presences) == 1:
            pid, name, _ = presences[0]
            label = name
            if sid in homeworlds:
                label += " ★"
            control_map[sid] = label
            color_map[sid]   = polity_color.get(pid, _UNCLAIMED_COLOR)
        else:
            # Multiple polities → contested; use color of most-developed one
            pid_top = presences[0][0]
            control_map[sid] = "contested"
            color_map[sid]   = _CONTESTED_COLOR

    # Mark homeworlds that were never visited (still unclaimed) — rare but possible
    for sid, pid in homeworlds.items():
        if sid in system_ids and sid not in by_system:
            control_map[sid] = gconn.execute(
                "SELECT name FROM Polity WHERE polity_id = ?", (pid,)
            ).fetchone()["name"] + " ★"
            color_map[sid] = polity_color.get(pid, _UNCLAIMED_COLOR)

    return control_map, color_map


def _dot_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_dot(
    routes: list[sqlite3.Row],
    positions: dict[int, tuple[int, int, int]],
    spectral:  dict[int, str],
    control:   dict[int, str],
    color_map: dict[int, str],
) -> str:
    lines: list[str] = []
    lines.append("graph jumproutes {")
    lines.append('    graph [overlap=false, splines=true, bgcolor="#1a1a2e"];')
    lines.append('    node [shape=box, style=filled, fontname="Courier", fontsize=9, '
                 'color="#cccccc", fontcolor="#222222"];')
    lines.append('    edge [fontname="Courier", fontsize=8, color="#888888", fontcolor="#aaaaaa"];')
    lines.append("")

    system_ids = sorted(positions)
    for sid in system_ids:
        x, y, z = positions[sid]
        spec   = spectral.get(sid, "?")
        ctrl   = control.get(sid, "unclaimed")
        fill   = color_map.get(sid, _UNCLAIMED_COLOR)
        label  = _dot_escape(f"{sid}\\n({x},{y},{z})pc\\n{spec}\\n{ctrl}")
        lines.append(f'    {sid} [label="{label}", fillcolor="{fill}"];')

    lines.append("")
    for r in routes:
        dist = r["dist_pc"]
        lines.append(
            f'    {r["from_system_id"]} -- {r["to_system_id"]} '
            f'[label="{dist:.1f}"];'
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default="jumproutes.dot",
                        help="Output .dot file (default: jumproutes.dot)")
    parser.add_argument("--game-db", default=str(GAME_DB),
                        help=f"Path to game.db (default: {GAME_DB})")
    parser.add_argument("--starscape-db", default=str(STARSCAPE_DB),
                        help=f"Path to starscape.db (default: {STARSCAPE_DB})")
    args = parser.parse_args()

    game_path = Path(args.game_db)
    star_path = Path(args.starscape_db)

    if not game_path.exists():
        sys.exit(f"game.db not found at {game_path}")
    if not star_path.exists():
        sys.exit(f"starscape.db not found at {star_path} — is the drive mounted?")

    gconn = _dict_conn(game_path)
    sconn = _dict_conn(star_path)

    routes = load_routes(gconn)
    if not routes:
        sys.exit("JumpRoute table is empty — run the simulation first.")

    positions  = build_system_positions(routes)
    system_ids = set(positions)

    print(f"Systems in route graph: {len(system_ids)}")
    print(f"Jump routes:            {len(routes)}")

    spectral          = load_spectral(sconn, system_ids)
    control, color_map = load_polity_control(gconn, system_ids)

    dot = render_dot(routes, positions, spectral, control, color_map)

    out = Path(args.output)
    out.write_text(dot, encoding="utf-8")
    print(f"Written: {out}  ({out.stat().st_size // 1024} KB)")
    print(f"Render:  dot -Tsvg {out} -o {out.stem}.svg")

    gconn.close()
    sconn.close()


if __name__ == "__main__":
    main()
