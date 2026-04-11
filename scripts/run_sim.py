"""run_sim.py — Run or resume the Starscape 5 simulation.

Usage:
    uv run scripts/run_sim.py                  # 500 ticks
    uv run scripts/run_sim.py --ticks 100      # custom tick count
    uv run scripts/run_sim.py --resume         # resume existing game.db

Outputs a summary of significant events after the run completes.
Use caffeinate on macOS to prevent sleep:
    caffeinate -i uv run scripts/run_sim.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure src/ is on the path when run via uv
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from starscape5.game.db import open_game, init_schema
from starscape5.game.events import get_events
from starscape5.game.facade import GameFacadeImpl
from starscape5.game.init_game import init_game
from starscape5.game.state import read_gamestate
from starscape5.engine.simulation import run_simulation
from starscape5.world.db import open_world_ro, open_world_rw
from starscape5.world.impl import WorldFacadeImpl

STARSCAPE_DB = Path("/Volumes/Data/starscape4/sqllite_database/starscape.db")
GAME_DB      = Path("game.db")


def print_summary(conn, ticks_run: int, elapsed: float) -> None:
    events = get_events(conn)
    state  = read_gamestate(conn)

    wars      = sum(1 for e in events if e.event_type == "war_declared")
    combats   = sum(1 for e in events if e.event_type == "combat")
    colonies  = sum(1 for e in events if e.event_type == "colony_established")
    contacts  = sum(1 for e in events if e.event_type == "contact")
    summaries = sum(1 for e in events if e.event_type == "monthly_summary")

    years = state.last_committed_tick / 52

    print(f"\n{'='*60}")
    print(f"  Simulation complete")
    print(f"  Ticks: {state.last_committed_tick}  (~{years:.1f} years)")
    print(f"  Wall time: {elapsed:.1f}s  ({elapsed/max(ticks_run,1)*1000:.0f}ms/tick)")
    print(f"{'='*60}")
    print(f"  Wars declared:        {wars}")
    print(f"  Combat events:        {combats}")
    print(f"  First contacts:       {contacts}")
    print(f"  Colonies established: {colonies}")
    print(f"  Monthly summaries:    {summaries}")
    print(f"  Total events:         {len(events)}")
    print()

    recent = get_events(conn, limit=None)[-10:]
    if recent:
        print("Last 10 events:")
        for e in recent:
            print(f"  tick={e.tick:5d}  {e.event_type:<22s}  {e.summary[:70]}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks",  type=int,  default=500,
                        help="Number of ticks to run (default: 500)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing game.db instead of starting fresh")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-tick summaries")
    args = parser.parse_args()

    if not STARSCAPE_DB.exists():
        sys.exit(f"starscape.db not found at {STARSCAPE_DB} — is the drive mounted?")

    # Open world connections
    ro_conn = open_world_ro(STARSCAPE_DB)
    rw_conn = open_world_rw(STARSCAPE_DB)
    world   = WorldFacadeImpl(ro_conn, rw_conn)

    # Fresh start or resume
    fresh = not GAME_DB.exists() or not args.resume
    if fresh and GAME_DB.exists():
        print(f"Removing existing {GAME_DB} for fresh run...")
        GAME_DB.unlink()

    game_conn = open_game(GAME_DB)
    init_schema(game_conn)

    if fresh:
        print("Initialising game state...")
        init_game(game_conn, world)
        state = read_gamestate(game_conn)
        print(f"Game initialised. {args.ticks} ticks to run.")
    else:
        state = read_gamestate(game_conn)
        print(f"Resuming from tick {state.last_committed_tick} (phase {state.last_committed_phase}).")

    game = GameFacadeImpl(game_conn)

    print(f"Running {args.ticks} ticks... (Ctrl-C to pause safely)\n")
    t0 = time.monotonic()

    last_tick = run_simulation(
        game_conn, world, game,
        max_ticks=args.ticks,
        verbose=args.verbose,
    )

    elapsed = time.monotonic() - t0
    ticks_run = last_tick - state.last_committed_tick

    print_summary(game_conn, ticks_run, elapsed)

    game_conn.close()
    ro_conn.close()
    rw_conn.close()


if __name__ == "__main__":
    main()
