"""system_viewer.py — 2D orrery for Starscape 5 planetary systems.

Renders planet orbits and current positions (at the simulation's live tick)
for any system in the starscape.db catalog.  Bodies are displayed in the
ecliptic plane projection using the full 3D Keplerian rotation (ω, i, Ω)
projected onto x–y.

Physics
  Mean anomaly at current tick: M(t) = M₀ + 2π(t − epoch) / P_ticks
  P (years) = √(a³ / M_central)  — Kepler's third law, a in AU, M in M☉
  Kepler's equation solved by Newton iteration (robust for e → 1).
  Coordinates in AU, star(s) at origin.

Usage:
    uv run scripts/system_viewer.py 898454
    uv run scripts/system_viewer.py 898454 --moons
    uv run scripts/system_viewer.py 898454 --tick 1500
    uv run scripts/system_viewer.py 898454 --save ~/Desktop/sol.html
    uv run scripts/system_viewer.py --list-homeworlds
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
# Paths and constants
# ---------------------------------------------------------------------------

STARSCAPE_DB = Path("/Volumes/Data/starscape4/starscape.db")
GAME_DB      = Path("/Volumes/Data/starscape4/game.db")

WEEKS_PER_YEAR     = 365.25 / 7.0   # 52.178 weeks per year
EARTH_TO_SOLAR     = 1.0 / 332946.0  # Earth masses → solar masses
_TWO_PI            = 2.0 * math.pi
_BG                = "#0a0a14"

# Planet class → marker fill colour
_CLASS_COLOUR: dict[str, str] = {
    "rocky":       "#c8874a",
    "super_earth": "#b87c4a",
    "desert":      "#d4a26a",
    "ocean":       "#4aadad",
    "small_gg":    "#6fa8d4",
    "medium_gg":   "#4a7fb5",
    "large_gg":    "#2c5fa0",
    "ice_giant":   "#7ec8c8",
}
_DEFAULT_PLANET_COLOUR = "#999999"

# Spectral class → star dot colour (same palette as star_viewer)
_STAR_COLOUR: dict[str, str] = {
    "O": "#9eb0ff", "B": "#b7caff", "A": "#d8e2ff",
    "F": "#fff4e8", "G": "#ffdf80", "K": "#ffb347",
    "M": "#ff6060", "W": "#c0a0ff",
}
_COMPANION_ORBIT_COLOUR = "rgba(200,200,200,0.25)"
_BELT_FILL_COLOUR       = "rgba(160,140,100,0.20)"
_BELT_LINE_COLOUR       = "rgba(160,140,100,0.50)"
_MOON_COLOUR            = "#808080"


# ---------------------------------------------------------------------------
# Orbital mechanics
# ---------------------------------------------------------------------------

def solve_kepler(M: float, e: float, tol: float = 1e-10) -> float:
    """Solve Kepler's equation M = E − e·sin(E) for eccentric anomaly E.

    Newton–Raphson iteration.  Initial guess handles high-eccentricity
    orbits (e up to ~0.999) by starting at π when M > π.
    """
    M = M % _TWO_PI
    E = math.pi if e > 0.8 and M > math.pi else M
    for _ in range(100):
        dE = (M - E + e * math.sin(E)) / (1.0 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E


def true_anomaly(E: float, e: float) -> float:
    """Eccentric anomaly → true anomaly."""
    return 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(E / 2.0),
        math.sqrt(1.0 - e) * math.cos(E / 2.0),
    )


def _pf_to_xy(
    r: float, nu: float,
    omega: float, Omega: float, inc: float,
) -> tuple[float, float]:
    """Perifocal position (r, ν) → ecliptic-plane (x, y) in AU.

    Standard rotation: Rz(Ω) · Rx(i) · Rz(ω) applied to the perifocal frame,
    then z component is dropped for the 2D projection.
    """
    x_pf = r * math.cos(nu)
    y_pf = r * math.sin(nu)
    co, so = math.cos(omega), math.sin(omega)
    cO, sO = math.cos(Omega), math.sin(Omega)
    ci      = math.cos(inc)
    x = (cO * co - sO * so * ci) * x_pf + (-cO * so - sO * co * ci) * y_pf
    y = (sO * co + cO * so * ci) * x_pf + (-sO * so + cO * co * ci) * y_pf
    return x, y


def _orbital_period_ticks(a: float, M_central_solar: float) -> float:
    """Orbital period in game ticks (weeks)."""
    return math.sqrt(a ** 3 / max(M_central_solar, 1e-6)) * WEEKS_PER_YEAR


def current_xy(
    a: float, e: float,
    omega: float, Omega: float, inc: float,
    M0: float, epoch: int,
    M_central_solar: float, tick: int,
) -> tuple[float, float]:
    """x, y position of body at the given game tick."""
    P = _orbital_period_ticks(a, M_central_solar)
    M = M0 + _TWO_PI * (tick - epoch) / P
    E = solve_kepler(M, e)
    nu = true_anomaly(E, e)
    r = a * (1.0 - e ** 2) / (1.0 + e * math.cos(nu))
    return _pf_to_xy(r, nu, omega, Omega, inc)


def orbit_xy(
    a: float, e: float,
    omega: float, Omega: float, inc: float,
    n: int = 300,
) -> tuple[list[float], list[float]]:
    """x, y arrays tracing the full orbit ellipse (for Plotly line trace)."""
    xs, ys = [], []
    for k in range(n + 1):
        nu = -math.pi + _TWO_PI * k / n
        r = a * (1.0 - e ** 2) / (1.0 + e * math.cos(nu))
        x, y = _pf_to_xy(r, nu, omega, Omega, inc)
        xs.append(x)
        ys.append(y)
    return xs, ys


def belt_polygon_xy(
    a_in: float, a_out: float, e: float,
    omega: float, Omega: float, inc: float,
    n: int = 200,
) -> tuple[list[float], list[float]]:
    """Closed polygon tracing outer edge then inner edge in reverse.
    Plotly fill='toself' then renders this as a donut annulus.
    """
    xs, ys = [], []
    for k in range(n + 1):
        nu = -math.pi + _TWO_PI * k / n
        r = a_out * (1.0 - e ** 2) / (1.0 + e * math.cos(nu))
        x, y = _pf_to_xy(r, nu, omega, Omega, inc)
        xs.append(x)
        ys.append(y)
    for k in range(n, -1, -1):
        nu = -math.pi + _TWO_PI * k / n
        r = a_in * (1.0 - e ** 2) / (1.0 + e * math.cos(nu))
        x, y = _pf_to_xy(r, nu, omega, Omega, inc)
        xs.append(x)
        ys.append(y)
    return xs, ys


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def get_current_tick(game_path: Path) -> int | None:
    if not game_path.exists():
        return None
    try:
        conn = _open(game_path)
        row = conn.execute(
            "SELECT last_committed_tick FROM GameState "
            "ORDER BY state_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return int(row["last_committed_tick"]) if row else None
    except Exception:
        return None


def get_place_name(game_path: Path, system_id: int) -> str | None:
    if not game_path.exists():
        return None
    try:
        conn = _open(game_path)
        row = conn.execute(
            "SELECT name FROM PlaceName "
            "WHERE object_type='system' AND object_id=?",
            (system_id,),
        ).fetchone()
        conn.close()
        return row["name"] if row else None
    except Exception:
        return None


def fetch_system_stars(conn: sqlite3.Connection, system_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.star_id, s.spectral,
               COALESCE(dse.mass, 1.0)        AS mass,
               COALESCE(dse.luminosity, 1.0)  AS luminosity,
               COALESCE(dse.temperature, 5778) AS temperature,
               COALESCE(dse.radius, 1.0)      AS radius
        FROM   IndexedIntegerDistinctStars s
        LEFT JOIN DistinctStarsExtended dse ON dse.star_id = s.star_id
        WHERE  s.system_id = ?
        """,
        (system_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_companion_orbits(
    conn: sqlite3.Connection, primary_id: int
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT so.star_id, so.semi_major_axis, so.eccentricity, so.inclination,
               so.longitude_ascending_node, so.argument_periapsis,
               so.mean_anomaly, so.epoch,
               s.spectral,
               COALESCE(dse.mass, 1.0) AS mass
        FROM   StarOrbits so
        JOIN   IndexedIntegerDistinctStars s ON s.star_id = so.star_id
        LEFT JOIN DistinctStarsExtended dse  ON dse.star_id = so.star_id
        WHERE  so.primary_star_id = ?
        """,
        (primary_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_bodies(conn: sqlite3.Connection, star_ids: list[int]) -> list[dict]:
    ph = ",".join("?" * len(star_ids))
    rows = conn.execute(
        f"""
        SELECT body_id, body_type, planet_class, mass, radius,
               semi_major_axis, eccentricity, inclination,
               longitude_ascending_node, argument_periapsis,
               mean_anomaly, epoch, orbit_star_id,
               in_hz, t_eq_k, possible_tidal_lock, has_rings,
               span_inner_au, span_outer_au
        FROM   Bodies
        WHERE  orbit_star_id IN ({ph})
        ORDER  BY semi_major_axis
        """,
        star_ids,
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_moons(conn: sqlite3.Connection, planet_ids: list[int]) -> list[dict]:
    if not planet_ids:
        return []
    ph = ",".join("?" * len(planet_ids))
    rows = conn.execute(
        f"""
        SELECT body_id, body_type, mass, radius,
               semi_major_axis, eccentricity, inclination,
               longitude_ascending_node, argument_periapsis,
               mean_anomaly, epoch, orbit_body_id, t_eq_k
        FROM   Bodies
        WHERE  orbit_body_id IN ({ph})
        ORDER  BY orbit_body_id, semi_major_axis
        """,
        planet_ids,
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Hover text builders
# ---------------------------------------------------------------------------

def _period_label(a: float, M: float) -> str:
    P = math.sqrt(a ** 3 / max(M, 1e-6))
    if P < 1.0:
        return f"{P*365.25:.0f} d"
    if P < 100.0:
        return f"{P:.2f} yr"
    return f"{P:.0f} yr"


def _planet_hover(b: dict, M_star: float) -> str:
    cls   = b["planet_class"] or b["body_type"] or "?"
    a     = b["semi_major_axis"]
    e     = b["eccentricity"]
    lines = [f"<b>body {b['body_id']}</b> ({cls})"]
    lines.append(f"a = {a:.3f} AU   e = {e:.3f}")
    lines.append(f"period: {_period_label(a, M_star)}")
    if b.get("t_eq_k"):
        lines.append(f"T_eq = {b['t_eq_k']:.0f} K")
    if b.get("in_hz"):
        lines.append("<b>★ habitable zone</b>")
    if b.get("possible_tidal_lock"):
        lines.append("tidal lock possible")
    if b.get("has_rings"):
        lines.append("has rings")
    if b.get("mass"):
        lines.append(f"mass = {b['mass']:.2f} M⊕   radius = {b['radius']:.2f} R⊕")
    return "<br>".join(lines)


def _belt_hover(b: dict) -> str:
    lines = [f"<b>body {b['body_id']}</b> (belt)"]
    inner = b.get("span_inner_au")
    outer = b.get("span_outer_au")
    if inner is not None and outer is not None:
        lines.append(f"span: {inner:.2f} – {outer:.2f} AU")
    comp = b.get("composition")
    if comp:
        lines.append(f"composition: {comp}")
    lines.append(f"centre a = {b['semi_major_axis']:.2f} AU   e = {b['eccentricity']:.3f}")
    return "<br>".join(lines)


def _moon_hover(m: dict, M_planet_solar: float) -> str:
    a = m["semi_major_axis"]
    lines = [f"<b>moon {m['body_id']}</b>"]
    lines.append(f"a = {a:.4f} AU ({a*215:.0f} R⊕)")
    lines.append(f"period: {_period_label(a, M_planet_solar)}")
    if m.get("t_eq_k"):
        lines.append(f"T_eq = {m['t_eq_k']:.0f} K")
    if m.get("mass"):
        lines.append(f"mass = {m['mass']:.3f} M⊕")
    return "<br>".join(lines)


def _star_hover(s: dict) -> str:
    sp = (s["spectral"] or "?").strip()
    lines = [f"<b>star {s['star_id']}</b>"]
    lines.append(f"spectral: {sp}")
    lines.append(f"mass = {s['mass']:.2f} M☉")
    lines.append(f"T = {s['temperature']:.0f} K")
    lines.append(f"L = {s['luminosity']:.2f} L☉   R = {s['radius']:.2f} R☉")
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Figure builder
# ---------------------------------------------------------------------------

def build_figure(
    system_id: int,
    system_label: str,
    stars: list[dict],
    bodies: list[dict],
    moons: list[dict],
    companion_orbits: list[dict],
    show_moons: bool,
    tick: int,
) -> go.Figure:

    traces: list[go.BaseTraceType] = []
    seen_classes: set[str] = set()   # for legend dedup
    moon_trace_indices: list[int] = []

    primary_star = stars[0]
    M_primary    = float(primary_star["mass"])

    # ------------------------------------------------------------------
    # 1. Companion star orbits + dots
    # ------------------------------------------------------------------
    for comp in companion_orbits:
        a, e, inc = comp["semi_major_axis"], comp["eccentricity"], comp["inclination"]
        om, Om    = comp["argument_periapsis"], comp["longitude_ascending_node"]
        M0, ep    = comp["mean_anomaly"], comp["epoch"]
        M_both    = M_primary + float(comp["mass"])

        ox, oy = orbit_xy(a, e, om, Om, inc)
        traces.append(go.Scatter(
            x=ox, y=oy, mode="lines",
            line=dict(color=_COMPANION_ORBIT_COLOUR, width=1, dash="dot"),
            hoverinfo="skip",
            showlegend=False,
        ))

        cx, cy = current_xy(a, e, om, Om, inc, M0, ep, M_both, tick)
        sp  = (comp["spectral"] or "?").strip()
        col = _STAR_COLOUR.get(sp[0].upper() if sp else "?", "#ffffff")
        traces.append(go.Scatter(
            x=[cx], y=[cy], mode="markers",
            name="Companion star",
            marker=dict(size=14, color=col, symbol="star",
                        line=dict(width=1, color="white")),
            text=[f"<b>companion {comp['star_id']}</b><br>"
                  f"spectral: {sp}<br>"
                  f"a = {a:.1f} AU   e = {e:.3f}<br>"
                  f"mass = {comp['mass']:.2f} M☉"],
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        ))

    # ------------------------------------------------------------------
    # 2. Belts — donut polygons
    # ------------------------------------------------------------------
    for b in bodies:
        if b["body_type"] != "belt":
            continue
        a_in  = b["span_inner_au"] or b["semi_major_axis"] * 0.97
        a_out = b["span_outer_au"] or b["semi_major_axis"] * 1.03
        e     = b["eccentricity"]
        om, Om, inc = b["argument_periapsis"], b["longitude_ascending_node"], b["inclination"]

        bx, by = belt_polygon_xy(a_in, a_out, e, om, Om, inc)
        first_belt = "Belt" not in seen_classes
        seen_classes.add("Belt")
        traces.append(go.Scatter(
            x=bx, y=by,
            mode="lines",
            fill="toself",
            fillcolor=_BELT_FILL_COLOUR,
            line=dict(color=_BELT_LINE_COLOUR, width=0.5),
            name="Belt",
            legendgroup="Belt",
            showlegend=first_belt,
            text=[_belt_hover(b)] * len(bx),
            hovertemplate="%{text}<extra></extra>",
            hoveron="fills+points",
        ))

    # ------------------------------------------------------------------
    # 3. Planet orbit ellipses + dots
    # ------------------------------------------------------------------
    # Build a lookup: orbit_star_id → stellar mass (solar)
    star_mass_by_id = {s["star_id"]: float(s["mass"]) for s in stars}
    for comp in companion_orbits:
        star_mass_by_id[comp["star_id"]] = float(comp["mass"])

    planet_ids   = []
    planet_pos   = {}   # body_id → (x, y) for moon placement

    for b in bodies:
        if b["body_type"] != "planet":
            continue

        planet_ids.append(b["body_id"])
        cls    = b["planet_class"] or "unknown"
        colour = _CLASS_COLOUR.get(cls, _DEFAULT_PLANET_COLOUR)
        a, e   = b["semi_major_axis"], b["eccentricity"]
        om, Om, inc = b["argument_periapsis"], b["longitude_ascending_node"], b["inclination"]
        M0, ep = b["mean_anomaly"], b["epoch"]
        M_star = star_mass_by_id.get(b["orbit_star_id"], M_primary)

        # Orbit ellipse — convert #rrggbb to rgba with low opacity
        ox, oy = orbit_xy(a, e, om, Om, inc)
        r_int = int(colour[1:3], 16)
        g_int = int(colour[3:5], 16)
        b_int = int(colour[5:7], 16)
        orbit_colour = f"rgba({r_int},{g_int},{b_int},0.35)"
        traces.append(go.Scatter(
            x=ox, y=oy, mode="lines",
            line=dict(color=orbit_colour, width=1),
            hoverinfo="skip",
            showlegend=False,
            legendgroup=cls,
        ))

        # Current position
        px, py = current_xy(a, e, om, Om, inc, M0, ep, M_star, tick)
        planet_pos[b["body_id"]] = (px, py)

        first_of_class = cls not in seen_classes
        seen_classes.add(cls)

        dot_size = 8 + min(4, int(math.log10(max(b["mass"] or 1, 1)) * 2))
        traces.append(go.Scatter(
            x=[px], y=[py], mode="markers",
            name=cls,
            legendgroup=cls,
            showlegend=first_of_class,
            marker=dict(
                size=dot_size,
                color=colour,
                line=dict(width=0.8, color="rgba(255,255,255,0.5)"),
            ),
            text=[_planet_hover(b, M_star)],
            hovertemplate="%{text}<extra></extra>",
        ))

        # Rings indicator — small faint halo
        if b.get("has_rings"):
            ring_r = dot_size / 2 + 3
            traces.append(go.Scatter(
                x=[px], y=[py], mode="markers",
                marker=dict(size=dot_size + 8, color="rgba(0,0,0,0)",
                            line=dict(width=1.5, color="rgba(200,180,100,0.6)")),
                hoverinfo="skip", showlegend=False,
            ))

    # ------------------------------------------------------------------
    # 4. Moons (if requested)
    # ------------------------------------------------------------------
    if show_moons and moons:
        moon_trace_start = len(traces)
        for m in moons:
            pid = m["orbit_body_id"]
            if pid not in planet_pos:
                continue
            ppx, ppy = planet_pos[pid]

            # Find parent planet mass for period calculation
            parent_mass_solar = next(
                (b["mass"] or 1.0) * EARTH_TO_SOLAR
                for b in bodies if b["body_id"] == pid
            ) if any(b["body_id"] == pid for b in bodies) else EARTH_TO_SOLAR

            a, e    = m["semi_major_axis"], m["eccentricity"]
            om, Om  = m["argument_periapsis"], m["longitude_ascending_node"]
            inc     = m["inclination"]
            M0, ep  = m["mean_anomaly"], m["epoch"]

            # Orbit ellipse relative to parent
            ox, oy = orbit_xy(a, e, om, Om, inc)
            ox = [x + ppx for x in ox]
            oy = [y + ppy for y in oy]
            traces.append(go.Scatter(
                x=ox, y=oy, mode="lines",
                line=dict(color="rgba(128,128,128,0.25)", width=0.5),
                hoverinfo="skip", showlegend=False,
                legendgroup="Moon",
            ))

            # Current position
            mx, my = current_xy(a, e, om, Om, inc, M0, ep, parent_mass_solar, tick)
            first_moon = "Moon" not in seen_classes
            seen_classes.add("Moon")
            traces.append(go.Scatter(
                x=[ppx + mx], y=[ppy + my], mode="markers",
                name="Moon",
                legendgroup="Moon",
                showlegend=first_moon,
                marker=dict(size=4, color=_MOON_COLOUR,
                            line=dict(width=0, color="rgba(0,0,0,0)")),
                text=[_moon_hover(m, parent_mass_solar)],
                hovertemplate="%{text}<extra></extra>",
            ))
        moon_trace_indices = list(range(moon_trace_start, len(traces)))

    # ------------------------------------------------------------------
    # 5. Primary star(s) at origin
    # ------------------------------------------------------------------
    for s in stars:
        # Companion stars are already plotted above; the primary is at (0, 0)
        # Skip stars that appear in companion_orbits
        comp_ids = {c["star_id"] for c in companion_orbits}
        if s["star_id"] in comp_ids:
            continue
        sp  = (s["spectral"] or "?").strip()
        col = _STAR_COLOUR.get(sp[0].upper() if sp else "?", "#ffffff")
        traces.append(go.Scatter(
            x=[0.0], y=[0.0], mode="markers",
            name=f"Star ({sp})",
            marker=dict(size=18, color=col, symbol="star",
                        line=dict(width=1, color="rgba(255,255,255,0.5)")),
            text=[_star_hover(s)],
            hovertemplate="%{text}<extra></extra>",
            showlegend=True,
        ))

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    n_planets  = sum(1 for b in bodies if b["body_type"] == "planet")
    n_belts    = sum(1 for b in bodies if b["body_type"] == "belt")
    n_moons    = len(moons)

    title_parts = [f"System {system_id}"]
    if system_label:
        title_parts = [system_label]
    title_parts.append(
        f"{n_planets} planet{'s' if n_planets != 1 else ''}"
        + (f"  ·  {n_belts} belt{'s' if n_belts != 1 else ''}" if n_belts else "")
        + (f"  ·  {n_moons} moon{'s' if n_moons != 1 else ''}" if n_moons else "")
        + f"  ·  tick {tick}"
    )

    # Determine axis range from max SMA
    planet_smas = [b["semi_major_axis"] for b in bodies if b["body_type"] == "planet"]
    comp_smas   = [c["semi_major_axis"] for c in companion_orbits]
    all_smas    = planet_smas + comp_smas
    max_sma     = max(all_smas) * 1.15 if all_smas else 10.0
    inner_limit = min((a for a in planet_smas if a > 0), default=1.0) * 0.5
    inner_zoom  = min(5.0, max_sma * 0.2)

    updatemenus = [
        # Zoom presets
        dict(
            type="buttons", direction="right",
            showactive=True, active=0,
            x=0.0, y=1.12, xanchor="left", yanchor="top",
            bgcolor="#1a1a2e", bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(label="Full system", method="relayout",
                     args=[{"xaxis.range": [-max_sma, max_sma],
                            "yaxis.range": [-max_sma, max_sma]}]),
                dict(label=f"Inner (< {inner_zoom:.0f} AU)", method="relayout",
                     args=[{"xaxis.range": [-inner_zoom, inner_zoom],
                            "yaxis.range": [-inner_zoom, inner_zoom]}]),
                dict(label="Reset", method="relayout",
                     args=[{"xaxis.autorange": True, "yaxis.autorange": True}]),
            ],
        ),
        # Moon toggle (only rendered when moons are present)
        *([dict(
            type="buttons", direction="right",
            showactive=True, active=0 if show_moons else 1,
            x=0.0, y=1.04, xanchor="left", yanchor="top",
            bgcolor="#1a1a2e", bordercolor="#444466",
            font=dict(color="white", size=11),
            buttons=[
                dict(label="Moons on", method="restyle",
                     args=[{"visible": True}, moon_trace_indices]),
                dict(label="Moons off", method="restyle",
                     args=[{"visible": False}, moon_trace_indices]),
            ],
        )] if moon_trace_indices else []),
    ]

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text="<br>".join(title_parts),
            font=dict(color="white", size=14),
        ),
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        xaxis=dict(
            title="AU", color="white", gridcolor="#1a1a32",
            zeroline=True, zerolinecolor="#333355", zerolinewidth=1,
            scaleanchor="y", scaleratio=1,
            range=[-max_sma, max_sma],
        ),
        yaxis=dict(
            title="AU", color="white", gridcolor="#1a1a32",
            zeroline=True, zerolinecolor="#333355", zerolinewidth=1,
            range=[-max_sma, max_sma],
        ),
        legend=dict(
            font=dict(color="white", size=11),
            bgcolor=_BG, bordercolor="#333355", borderwidth=1,
            title=dict(text="Body class", font=dict(color="#888899")),
        ),
        updatemenus=updatemenus,
        margin=dict(l=60, r=20, t=90, b=60),
        width=900, height=900,
        annotations=[dict(
            text="Positions computed at simulation tick · "
                 "Orbits projected onto ecliptic plane",
            x=0.5, y=-0.07, xref="paper", yref="paper",
            xanchor="center", showarrow=False,
            font=dict(color="#555577", size=10),
        )],
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
# Helpers
# ---------------------------------------------------------------------------

def _list_homeworlds(star_conn: sqlite3.Connection) -> None:
    """Print homeworld system IDs from the OB data constants."""
    homeworld_ids = [
        898454, 1066934, 918040, 1036727, 911133,
        1158848, 1061677, 987309, 1130253, 942565, 1157617,
    ]
    print("\nHomeworld systems:")
    for sid in homeworld_ids:
        row = star_conn.execute(
            "SELECT spectral FROM IndexedIntegerDistinctStars WHERE system_id = ? LIMIT 1",
            (sid,),
        ).fetchone()
        sp = row["spectral"].strip() if row and row["spectral"] else "?"
        bcount = star_conn.execute(
            """SELECT COUNT(*) AS n FROM Bodies
               WHERE orbit_star_id IN (
                 SELECT star_id FROM IndexedIntegerDistinctStars WHERE system_id = ?)
               AND body_type = 'planet'""",
            (sid,),
        ).fetchone()["n"]
        print(f"  {sid:>10d}  {sp:<8}  {bcount} planets")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Starscape 5 — 2D orrery for a planetary system.",
    )
    parser.add_argument("system_id", nargs="?", type=int,
                        help="System ID to display.")
    parser.add_argument("--moons", action="store_true",
                        help="Show moon orbits and positions.")
    parser.add_argument("--tick", type=int, default=None,
                        help="Game tick for position calculation "
                             "(default: current live tick from game.db, "
                             "or 0 if game.db unavailable).")
    parser.add_argument("--save", metavar="FILE",
                        help="Save HTML to FILE (also opens browser).")
    parser.add_argument("--star-db", default=str(STARSCAPE_DB), metavar="PATH")
    parser.add_argument("--game-db", default=str(GAME_DB), metavar="PATH")
    parser.add_argument("--list-homeworlds", action="store_true",
                        help="Print homeworld system IDs and exit.")
    args = parser.parse_args()

    star_path = Path(args.star_db)
    game_path = Path(args.game_db)

    if not star_path.exists():
        sys.exit(f"starscape.db not found: {star_path}")

    star_conn = _open(star_path)

    if args.list_homeworlds:
        _list_homeworlds(star_conn)
        star_conn.close()
        return

    if args.system_id is None:
        parser.print_help()
        sys.exit("\nProvide a system_id, or use --list-homeworlds.")

    system_id = args.system_id

    # Tick resolution
    if args.tick is not None:
        tick = args.tick
        tick_source = f"--tick {tick}"
    else:
        live = get_current_tick(game_path)
        tick = live if live is not None else 0
        tick_source = f"live tick {tick}" if live else "tick 0 (no game.db)"
    print(f"Computing positions at {tick_source}")

    # Place name from game.db (if any)
    place = get_place_name(game_path, system_id)
    label = place or f"sys-{system_id}"

    # Load star data
    stars = fetch_system_stars(star_conn, system_id)
    if not stars:
        sys.exit(f"System {system_id} not found in starscape.db.")

    star_ids = [s["star_id"] for s in stars]
    print(f"System {system_id} ({label}): "
          f"{len(stars)} star(s)  —  "
          + ", ".join(
              f"{(s['spectral'] or '?').strip()} {s['mass']:.2f}M☉"
              for s in stars
          ))

    # Companion star orbital data (relative to primary)
    primary_id       = stars[0]["star_id"]
    companion_orbits = fetch_companion_orbits(star_conn, primary_id)
    if companion_orbits:
        for c in companion_orbits:
            print(f"  companion star {c['star_id']}: "
                  f"a={c['semi_major_axis']:.1f} AU  e={c['eccentricity']:.3f}")

    # Bodies
    bodies = fetch_bodies(star_conn, star_ids)
    planets = [b for b in bodies if b["body_type"] == "planet"]
    belts   = [b for b in bodies if b["body_type"] == "belt"]
    print(f"  {len(planets)} planet(s)  {len(belts)} belt(s)")

    # Moons
    planet_ids = [b["body_id"] for b in planets]
    moons = fetch_moons(star_conn, planet_ids)
    if moons:
        print(f"  {len(moons)} moon(s)"
              + (" (showing)" if args.moons else " (use --moons to show)"))

    star_conn.close()

    fig = build_figure(
        system_id=system_id,
        system_label=label,
        stars=stars,
        bodies=bodies,
        moons=moons,
        companion_orbits=companion_orbits,
        show_moons=args.moons,
        tick=tick,
    )
    _render(fig, Path(args.save) if args.save else None)


if __name__ == "__main__":
    main()
