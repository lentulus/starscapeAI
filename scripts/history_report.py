"""history_report.py — Post-run history digest for Starscape 5.

Produces a human-readable narrative report from game.db, suitable for
reading directly or handing to an LLM historian.  Run by hand after a
completed simulation session.

Usage:
    uv run scripts/history_report.py
    uv run scripts/history_report.py --output history.txt
    uv run scripts/history_report.py --game /path/to/game.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_SIM_EPOCH = date(2526, 4, 12)  # tick 0 = 12 April 2526

GAME_DB = Path("/Volumes/Data/starscape4/sqllite_database/games/game.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date(tick: int) -> str:
    return (_SIM_EPOCH + timedelta(weeks=tick)).strftime("%d %b %Y")


def _years(ticks: int) -> str:
    y = ticks / 52
    return f"{y:.1f} yr"


def _ru(v: float) -> str:
    if v >= 0:
        return f"+{v:,.0f} RU"
    return f"{v:,.0f} RU"


def _sep(char: str = "═", width: int = 70) -> str:
    return char * width


def _header(title: str) -> str:
    bar = _sep()
    return f"\n{bar}\n  {title}\n{bar}\n"


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_gamestate(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM GameState LIMIT 1").fetchone()


def load_polities(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM Polity_head ORDER BY polity_id"
    ).fetchall()


def load_presences(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT sp.*, COALESCE(wp.world_potential, 0) AS world_potential
        FROM   SystemPresence_head sp
        LEFT JOIN WorldPotential wp ON wp.body_id = sp.body_id
        ORDER  BY sp.polity_id, sp.presence_id
        """
    ).fetchall()


def load_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM GameEvent
        WHERE  event_type != 'monthly_summary'
        ORDER  BY tick, phase, rowid
        """
    ).fetchall()


def load_monthly_samples(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """One monthly summary row per simulated year (every 52 ticks)."""
    return conn.execute(
        """
        SELECT tick, summary FROM GameEvent
        WHERE  event_type = 'monthly_summary'
          AND  tick % 52 = 0
        ORDER  BY tick
        """
    ).fetchall()


def load_hulls_by_polity(conn: sqlite3.Connection) -> dict[int, dict[str, int]]:
    """Return {polity_id: {hull_type: count}} for non-destroyed hulls."""
    rows = conn.execute(
        """
        SELECT polity_id, hull_type, COUNT(*) as cnt
        FROM   Hull_head
        WHERE  status != 'destroyed'
        GROUP  BY polity_id, hull_type
        """
    ).fetchall()
    result: dict[int, dict[str, int]] = defaultdict(dict)
    for r in rows:
        result[r["polity_id"]][r["hull_type"]] = r["cnt"]
    return result


def load_admirals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM Admiral ORDER BY admiral_id"
    ).fetchall()


def load_treasury_arc(conn: sqlite3.Connection, polity_id: int) -> dict:
    """Return {start, min, max, end} treasury for a polity."""
    row = conn.execute(
        """
        SELECT
            (SELECT treasury_ru FROM Polity WHERE polity_id=? ORDER BY row_id ASC  LIMIT 1) as start_t,
            MIN(treasury_ru) as min_t,
            MAX(treasury_ru) as max_t,
            (SELECT treasury_ru FROM Polity WHERE polity_id=? ORDER BY row_id DESC LIMIT 1) as end_t
        FROM Polity WHERE polity_id=?
        """,
        (polity_id, polity_id, polity_id),
    ).fetchone()
    return {
        "start": row["start_t"] or 0,
        "min":   row["min_t"]   or 0,
        "max":   row["max_t"]   or 0,
        "end":   row["end_t"]   or 0,
    }


def load_budget_shortfalls(conn: sqlite3.Connection) -> dict[int, int]:
    """Return {polity_id: count_of_shortfall_events}."""
    rows = conn.execute(
        """
        SELECT polity_a_id, COUNT(*) as n
        FROM   GameEvent WHERE event_type = 'budget_shortfall'
        GROUP  BY polity_a_id
        """
    ).fetchall()
    return {r["polity_a_id"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def section_run_header(gs: sqlite3.Row, polities: list, presences: list, events: list) -> str:
    last_tick  = gs["last_committed_tick"]
    start_date = _date(0)
    end_date   = _date(last_tick)
    n_polities = len(polities)
    active     = sum(1 for p in polities if p["status"] == "active")
    eliminated = sum(1 for p in polities if p["status"] == "eliminated")
    n_events   = len(events)

    lines = [
        "STARSCAPE 5 — HISTORY REPORT",
        "",
        f"  Simulation span : {start_date}  →  {end_date}",
        f"  Ticks run       : {last_tick:,}  ({_years(last_tick)})",
        f"  Polities        : {n_polities} started  |  {active} active  |  {eliminated} eliminated",
        f"  Presences       : {len(presences)} at run end",
        f"  Significant events recorded : {n_events}",
    ]
    return "\n".join(lines)


def section_polity_roster(polities: list, presences: list, hulls_by_polity: dict) -> str:
    out = [_header("POLITY ROSTER — FINAL STATE")]

    # Group presences by polity
    pres_by_polity: dict[int, list] = defaultdict(list)
    for pr in presences:
        pres_by_polity[pr["polity_id"]].append(pr)

    # Species grouping label (infer from name prefix)
    def species_tag(name: str) -> str:
        parts = name.split()
        if len(parts) >= 2:
            return parts[0]
        return name

    col = "{:<30s}  {:>8s}  {:>9s}  {:>7s}  {:>5s}  {}"
    out.append(col.format("Polity", "Treasury", "Presences", "Hulls", "Jump", "Status"))
    out.append("  " + "-" * 66)

    for p in polities:
        pid   = p["polity_id"]
        pres  = pres_by_polity[pid]
        hmap  = hulls_by_polity.get(pid, {})
        n_hulls = sum(hmap.values())
        treas = p["treasury_ru"]
        sign  = "+" if treas >= 0 else ""
        pres_summary = f"{len(pres)} ({', '.join(sorted({pr['control_state'] for pr in pres}))})"
        out.append(col.format(
            p["name"],
            f"{sign}{treas:,.0f}",
            pres_summary,
            str(n_hulls),
            f"J{p['jump_level']}",
            p["status"],
        ))

    return "\n".join(out)


def section_contacts_and_wars(
    events: list,
    polities: list,
    presences: list,
) -> str:
    out = [_header("CONTACTS & WARS")]

    polity_name: dict[int, str] = {p["polity_id"]: p["name"] for p in polities}
    capital: dict[int, int] = {}
    for pr in presences:
        if pr["control_state"] == "controlled":
            capital.setdefault(pr["polity_id"], pr["system_id"])

    contact_events = [e for e in events if e["event_type"] == "contact"]
    war_events     = [e for e in events if e["event_type"] == "war_declared"]

    # ---- Contacts ----
    if contact_events:
        out.append("FIRST CONTACTS\n")
        for e in contact_events:
            a = polity_name.get(e["polity_a_id"], f"polity {e['polity_a_id']}")
            b = polity_name.get(e["polity_b_id"], f"polity {e['polity_b_id']}")
            sys_str = f" at system {e['system_id']}" if e["system_id"] else ""
            out.append(f"  {_date(e['tick'])} (tick {e['tick']:,})")
            out.append(f"    {a}  ↔  {b}{sys_str}")
            out.append("")
    else:
        out.append("  No first contacts recorded.\n")

    # ---- Wars ----
    if war_events:
        out.append("WARS\n")

        # Find all pairs at war
        war_pairs: set[frozenset] = set()
        for e in war_events:
            war_pairs.add(frozenset([e["polity_a_id"], e["polity_b_id"]]))

        for pair in sorted(war_pairs, key=lambda p: min(p)):
            ids = sorted(pair)
            a_name = polity_name.get(ids[0], str(ids[0]))
            b_name = polity_name.get(ids[1], str(ids[1]))

            # Find declaration tick
            decl = next(
                (e for e in war_events
                 if set([e["polity_a_id"], e["polity_b_id"]]) == set(ids)),
                None,
            )
            decl_tick = decl["tick"] if decl else "?"
            initiator  = polity_name.get(decl["polity_a_id"], "?") if decl else "?"

            out.append(f"  ── {a_name}  vs  {b_name} ──")
            if decl:
                out.append(f"  Declared : {_date(decl_tick)} (tick {decl_tick:,})  by {initiator}")

            # Collect relevant events
            war_related = [
                e for e in events
                if e["event_type"] in ("combat", "bombardment", "fleet_destroyed",
                                       "disengage", "pursuit", "control_change")
                and e["polity_a_id"] in ids and (e["polity_b_id"] is None or e["polity_b_id"] in ids)
            ]

            # Summarise bombardments (can be very numerous)
            bombards = [e for e in war_related if e["event_type"] == "bombardment"]
            non_bomb = [e for e in war_related if e["event_type"] != "bombardment"]

            if bombards:
                b_systems = {e["system_id"] for e in bombards}
                b_start   = min(e["tick"] for e in bombards)
                b_end     = max(e["tick"] for e in bombards)
                sys_str   = ", ".join(f"system {s}" for s in sorted(b_systems) if s)
                out.append(
                    f"  Bombardment campaign: {_date(b_start)} – {_date(b_end)}"
                    f"  ({len(bombards)} rounds, {sys_str})"
                )

            for e in non_bomb:
                label = e["event_type"].replace("_", " ").title()
                sys_str = f" at system {e['system_id']}" if e["system_id"] else ""
                out.append(f"    {_date(e['tick'])}  {label}{sys_str}")
                if e["summary"]:
                    # Trim to 80 chars for readability
                    out.append(f"      {e['summary'][:80]}")

            out.append("")
    else:
        out.append("  No wars declared.\n")

    return "\n".join(out)


def section_colony_chronicle(events: list, polities: list, presences: list) -> str:
    out = [_header("COLONY CHRONICLE")]

    polity_name: dict[int, str] = {p["polity_id"]: p["name"] for p in polities}

    colony_events = [e for e in events if e["event_type"] == "colony_established"]
    events_by_polity: dict[int, list] = defaultdict(list)
    for e in colony_events:
        events_by_polity[e["polity_a_id"]].append(e)

    pres_by_polity: dict[int, list] = defaultdict(list)
    for pr in presences:
        pres_by_polity[pr["polity_id"]].append(pr)

    for p in polities:
        pid  = p["polity_id"]
        evts = events_by_polity.get(pid, [])
        pres = pres_by_polity.get(pid, [])

        out.append(f"  {p['name']}  ({len(pres)} presence{'s' if len(pres) != 1 else ''} at run end)\n")

        pres_by_sys: dict[int, sqlite3.Row] = {pr["system_id"]: pr for pr in pres}

        for e in evts:
            sys_id = e["system_id"]
            current = pres_by_sys.get(sys_id)
            if current:
                state = current["control_state"]
                dev   = current["development_level"]
                pot   = current["world_potential"]
                state_str = f"→ {state}/dev{dev}/pot{pot} at run end"
            else:
                state_str = "→ no longer held"

            label = "homeworld" if e["tick"] == 0 else "outpost established"
            out.append(
                f"    {_date(e['tick'])} (tick {e['tick']:>4,})"
                f"  system {sys_id:>10}  {label:<22s}  {state_str}"
            )
        out.append("")

    return "\n".join(out)


def section_fleet_summary(polities: list, hulls_by_polity: dict) -> str:
    out = [_header("FLEET COMPOSITION — FINAL STATE")]

    hull_order = ["capital", "old_capital", "cruiser", "escort", "sdb",
                  "troop", "transport", "colony_transport", "scout"]

    for p in polities:
        pid  = p["polity_id"]
        hmap = hulls_by_polity.get(pid, {})
        if not hmap:
            continue
        parts = []
        for ht in hull_order:
            n = hmap.get(ht, 0)
            if n:
                short = {
                    "capital": "CAP", "old_capital": "OCAP", "cruiser": "CRU",
                    "escort": "ESC", "sdb": "SDB", "troop": "TRP",
                    "transport": "TRN", "colony_transport": "CT", "scout": "SCT",
                }.get(ht, ht[:3].upper())
                parts.append(f"{n}×{short}")
        out.append(f"  {p['name']:<30s}  {',  '.join(parts)}")

    return "\n".join(out)


def section_economic_narrative(polities: list, hulls_by_polity: dict, shortfalls: dict) -> str:
    out = [_header("ECONOMIC NARRATIVE — PER POLITY")]

    # Production formula constants (must match game/economy.py)
    CTRL_MULT = {"outpost": 0.20, "colony": 0.55, "controlled": 1.00, "contested": 0.35}
    DEV_MULT  = {0: 0.5, 1: 0.7, 2: 0.9, 3: 1.0, 4: 1.2, 5: 1.5}
    MAINT     = {
        "capital": 2.0, "old_capital": 1.5, "cruiser": 1.0,
        "escort": 0.5, "sdb": 0.5, "troop": 0.5,
        "transport": 0.5, "colony_transport": 0.5, "scout": 0.1,
    }

    for p in polities:
        pid  = p["polity_id"]
        arc  = p["_arc"]
        hmap = hulls_by_polity.get(pid, {})
        sf   = shortfalls.get(pid, 0)

        maint_total = sum(MAINT.get(ht, 0.5) * cnt for ht, cnt in hmap.items())
        prod_total  = p["_prod"]
        net         = prod_total - maint_total

        out.append(f"  {p['name']}")
        out.append(f"    Starting treasury : {arc['start']:>8,.0f} RU")
        out.append(f"    Peak treasury     : {arc['max']:>8,.0f} RU")
        out.append(f"    End treasury      : {arc['end']:>8,.0f} RU")
        out.append(f"    Production (end)  : {prod_total:>7.1f} RU/tick")
        out.append(f"    Maintenance (end) : {maint_total:>7.1f} RU/tick")
        out.append(f"    Net (end)         : {net:>+7.1f} RU/tick")
        if sf:
            out.append(f"    Budget shortfalls : {sf} scrapping events")
        out.append("")

    return "\n".join(out)


def section_admiral_record(admirals: list, polities: list) -> str:
    out = [_header("ADMIRAL SERVICE RECORDS")]

    polity_name = {p["polity_id"]: p["name"] for p in polities}

    # Group by polity
    by_polity: dict[int, list] = defaultdict(list)
    for a in admirals:
        by_polity[a["polity_id"]].append(a)

    for p in polities:
        pid = p["polity_id"]
        ads = by_polity.get(pid)
        if not ads:
            continue
        out.append(f"  {p['name']}")
        for a in sorted(ads, key=lambda x: x["admiral_id"]):
            tf   = a["tactical_factor"]
            tf_s = f"{tf:+d}" if tf != 0 else "±0"
            created = _date(a["created_tick"])
            if a["status"] == "retired":
                ret  = a["retirement_tick"]
                serv = ret - a["created_tick"]
                out.append(
                    f"    {a['name']:<16s}  TF{tf_s}  "
                    f"commissioned {created}  retired {_date(ret)}  ({_years(serv)} service)"
                )
            else:
                out.append(
                    f"    {a['name']:<16s}  TF{tf_s}  "
                    f"commissioned {created}  still serving"
                )
        out.append("")

    return "\n".join(out)


def section_events_timeline(events: list, polities: list) -> str:
    out = [_header("SIGNIFICANT EVENTS — FULL TIMELINE")]
    out.append("  (Excludes monthly summaries and routine hull builds)\n")

    polity_name = {p["polity_id"]: p["name"] for p in polities}

    skip_types = {"hull_built", "monthly_summary"}
    notable = [e for e in events if e["event_type"] not in skip_types]

    if not notable:
        out.append("  None recorded.")
        return "\n".join(out)

    prev_year = None
    for e in notable:
        year = int((_SIM_EPOCH + timedelta(weeks=e["tick"])).year)
        if year != prev_year:
            out.append(f"\n  ── {year} ──")
            prev_year = year

        a = polity_name.get(e["polity_a_id"], "")
        b = polity_name.get(e["polity_b_id"], "")
        actors = f"{a}" + (f" / {b}" if b else "")
        label  = e["event_type"].replace("_", " ")
        out.append(
            f"  {_date(e['tick'])}  {label:<18s}  {actors:<40s}  {e['summary'][:60]}"
        )

    return "\n".join(out)


def section_yearly_digest(conn: sqlite3.Connection) -> str:
    out = [_header("AGGREGATE YEARLY DIGEST")]
    out.append(
        "  (Aggregate treasury, fleet size, and presences across all polities)\n"
    )
    out.append(f"  {'Year':<6}  {'Date':<12}  {'Treasury':>12}  {'Fleets':>7}  {'Presences':>10}")
    out.append("  " + "-" * 55)

    samples = conn.execute(
        """
        SELECT tick, summary FROM GameEvent
        WHERE  event_type = 'monthly_summary'
          AND  tick % 52 = 0
        ORDER  BY tick
        """
    ).fetchall()

    for row in samples:
        tick = row["tick"]
        # Parse: "month_end treasury=NRU fleets=N presences=N polities=N"
        parts = dict(p.split("=") for p in row["summary"].split() if "=" in p)
        treasury  = parts.get("treasury", "?").replace("RU", "")
        fleets    = parts.get("fleets", "?")
        presences = parts.get("presences", "?")
        yr = int((_SIM_EPOCH + timedelta(weeks=tick)).year)
        out.append(
            f"  {yr:<6}  {_date(tick):<12}  {treasury:>12}  {fleets:>7}  {presences:>10}"
        )

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",   default=str(GAME_DB), help="Path to game.db")
    parser.add_argument("--output", default=None,         help="Write to file instead of stdout")
    args = parser.parse_args()

    db_path = Path(args.game)
    if not db_path.exists():
        sys.exit(f"game.db not found at {db_path}")

    conn     = _open(db_path)
    gs       = load_gamestate(conn)
    polities = load_polities(conn)
    presences = load_presences(conn)
    events   = load_events(conn)
    hulls    = load_hulls_by_polity(conn)
    admirals = load_admirals(conn)
    shortfalls = load_budget_shortfalls(conn)

    # Attach treasury arc and end production to each polity row for convenience.
    # (sqlite3.Row is read-only; build a list of dicts instead.)
    CTRL_MULT = {"outpost": 0.20, "colony": 0.55, "controlled": 1.00, "contested": 0.35}
    DEV_MULT  = {0: 0.5, 1: 0.7, 2: 0.9, 3: 1.0, 4: 1.2, 5: 1.5}

    pres_by_polity: dict[int, list] = defaultdict(list)
    for pr in presences:
        pres_by_polity[pr["polity_id"]].append(pr)

    polity_dicts = []
    for p in polities:
        pid  = p["polity_id"]
        arc  = load_treasury_arc(conn, pid)
        pres = pres_by_polity[pid]
        prod = sum(
            pr["world_potential"]
            * CTRL_MULT.get(pr["control_state"], 0)
            * DEV_MULT.get(pr["development_level"], 1.0)
            for pr in pres
        )
        d = dict(p)
        d["_arc"]  = arc
        d["_prod"] = prod
        polity_dicts.append(d)

    # Render sections
    sections = [
        section_run_header(gs, polities, presences, events),
        section_polity_roster(polities, presences, hulls),
        section_contacts_and_wars(events, polities, presences),
        section_colony_chronicle(events, polities, presences),
        section_fleet_summary(polities, hulls),
        section_economic_narrative(polity_dicts, hulls, shortfalls),
        section_admiral_record(admirals, polities),
        section_yearly_digest(conn),
        section_events_timeline(events, polities),
    ]

    report = "\n".join(sections) + "\n"

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)

    conn.close()


if __name__ == "__main__":
    main()
