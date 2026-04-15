#!/usr/bin/env python3
"""find_min_jump.py — Minimum jump range for full stellar graph connectivity.

Approach
--------
This is a **minimum-bottleneck spanning tree** problem.  The smallest jump
range d that connects every star into a single graph equals the longest edge
in the MST of the stellar point cloud.

Algorithm
~~~~~~~~~
1. Load every system position (x, y, z mpc → convert to pc).
2. For each system, find its k nearest neighbours using a scipy cKDTree.
3. Collect all unique kNN edges; sort by distance.  This is Kruskal input.
4. Sweep through sorted edges, maintaining a Union-Find:
   - At each integer-parsec milestone, snapshot:
       components  — number of connected components
       isolates    — components of size 1 (stars with no reachable neighbour)
       giant_size  — stars in the largest single component
       giant_pct   — percentage of all stars in that component
5. The exact minimum jump = distance of the edge that reduces components to 1.

Why kNN instead of query_pairs(r)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
query_pairs(r) at large r returns O(n · ρ · r³) pairs.  For 2.47M stars and
r = 20 pc the result can exceed 10 billion pairs — far too large to sort or
store.

kNN with k neighbours generates exactly k·n/2 unique edges regardless of
radius.  For a well-distributed 3D point cloud, the MST always uses edges
within the kNN neighbourhood; k = 40 is sufficient for typical stellardistributions.  If the sweep ends with > 1 component, increase --knn.

Usage
-----
    uv run scripts/find_min_jump.py
    uv run scripts/find_min_jump.py --min-pc 2 --max-pc 30 --knn 60
    uv run scripts/find_min_jump.py --step 0.5      # half-parsec steps
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

_DEFAULT_DB = "/Volumes/Data/starscape4/starscape.db"
_DEFAULT_KNN = 40
_DEFAULT_MIN_PC = 3.0
_DEFAULT_MAX_PC = 100.0
_DEFAULT_STEP = 1.0


# ---------------------------------------------------------------------------
# Union-Find (path-halving + union by rank)
# ---------------------------------------------------------------------------

class UnionFind:
    """Disjoint-set forest with path-halving and union by rank."""

    __slots__ = ("parent", "rank", "size", "n_components")

    def __init__(self, n: int) -> None:
        self.parent = np.arange(n, dtype=np.int32)
        self.rank   = np.zeros(n, dtype=np.int8)
        self.size   = np.ones(n, dtype=np.int32)
        self.n_components = n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path halving
            x = self.parent[x]
        return int(x)

    def union(self, x: int, y: int) -> bool:
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        # Union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        self.size[px] += self.size[py]
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        self.n_components -= 1
        return True

    def component_stats(self) -> tuple[int, int, int]:
        """Return (n_components, n_isolates, giant_size).

        n_components is tracked incrementally; isolates and giant require
        a scan over root nodes only (roots are where parent[i] == i).
        """
        # Roots are nodes whose parent is themselves.
        is_root = self.parent == np.arange(len(self.parent), dtype=np.int32)
        root_sizes = self.size[is_root]
        isolates = int(np.sum(root_sizes == 1))
        giant    = int(root_sizes.max()) if len(root_sizes) else 0
        return self.n_components, isolates, giant


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        sys.exit("scipy is required: uv add scipy")

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db",      default=_DEFAULT_DB,
                    help="Path to starscape.db")
    ap.add_argument("--min-pc",  type=float, default=_DEFAULT_MIN_PC,
                    help="Start of reporting range (pc, default 3)")
    ap.add_argument("--max-pc",  type=float, default=_DEFAULT_MAX_PC,
                    help="Upper bound for sweep (pc, default 100)")
    ap.add_argument("--step",    type=float, default=_DEFAULT_STEP,
                    help="Reporting step size (pc, default 1)")
    ap.add_argument("--knn",     type=int,   default=_DEFAULT_KNN,
                    help="k nearest neighbours per star (default 40)")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"Database not found: {db_path}")

    # ------------------------------------------------------------------
    # 1. Load positions
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    print(f"Loading positions from {db_path} ...", flush=True)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT system_id, x, y, z FROM IndexedIntegerDistinctSystems"
        " ORDER BY system_id"
    ).fetchall()
    conn.close()

    n = len(rows)
    print(f"  {n:,} systems loaded in {time.perf_counter() - t0:.1f}s", flush=True)

    # Store system_id for reference; convert mpc → pc in float32.
    sys_ids = np.array([r[0] for r in rows], dtype=np.int32)
    coords  = np.array([[r[1], r[2], r[3]] for r in rows], dtype=np.float32) / 1000.0

    # ------------------------------------------------------------------
    # 2. Build KD-tree
    # ------------------------------------------------------------------
    t1 = time.perf_counter()
    print(f"Building KD-tree ({n:,} points) ...", flush=True)
    tree = cKDTree(coords)
    print(f"  Done in {time.perf_counter() - t1:.1f}s", flush=True)

    # ------------------------------------------------------------------
    # 3. k-NN query
    # ------------------------------------------------------------------
    k = min(args.knn + 1, n)   # +1 because index 0 is always the point itself
    t2 = time.perf_counter()
    print(f"Querying {args.knn}-NN for every star ...", flush=True)
    dist_arr, idx_arr = tree.query(coords, k=k, workers=-1)
    # dist_arr shape: (n, k); idx_arr shape: (n, k)
    # Column 0 is distance 0 (self) — skip it.
    print(f"  Done in {time.perf_counter() - t2:.1f}s", flush=True)

    # ------------------------------------------------------------------
    # 4. Build sorted edge list  (i < j to avoid duplicates)
    # ------------------------------------------------------------------
    t3 = time.perf_counter()
    print("Building edge list ...", flush=True)

    # Vectorised: for each star i, for each neighbour j > i, emit (dist, i, j)
    # Shape tricks to avoid Python loops:
    n_idx = np.arange(n, dtype=np.int32)[:, None]  # (n, 1)
    # Mask: neighbour index > self index (avoids duplicate edges)
    mask = idx_arr[:, 1:] > n_idx           # (n, k-1)
    i_vals = np.broadcast_to(n_idx, (n, k - 1))[mask].astype(np.int32)
    j_vals = idx_arr[:, 1:][mask].astype(np.int32)
    d_vals = dist_arr[:, 1:][mask].astype(np.float32)

    # Sort by distance
    order  = np.argsort(d_vals, kind="stable")
    d_vals = d_vals[order]
    i_vals = i_vals[order]
    j_vals = j_vals[order]

    n_edges = len(d_vals)
    print(f"  {n_edges:,} unique edges, max kNN dist = {float(d_vals[-1]):.2f} pc "
          f"in {time.perf_counter() - t3:.1f}s", flush=True)

    # ------------------------------------------------------------------
    # 5. Kruskal sweep with milestone reporting
    # ------------------------------------------------------------------
    uf = UnionFind(n)
    edge_ptr = 0

    milestones = np.arange(args.min_pc,
                           args.max_pc + args.step / 2.0,
                           args.step)

    # Header
    print()
    print(f"{'jump_pc':>8}  {'components':>12}  {'isolates':>10}  "
          f"{'giant_size':>12}  {'giant_pct':>10}")
    print("-" * 60)

    exact_min_jump: float | None = None
    last_components = n

    for target_pc in milestones:
        # Consume all edges with distance <= target_pc
        while edge_ptr < n_edges and d_vals[edge_ptr] <= target_pc:
            uf.union(int(i_vals[edge_ptr]), int(j_vals[edge_ptr]))
            edge_ptr += 1

        n_comp, isolates, giant = uf.component_stats()
        pct = 100.0 * giant / n

        print(f"{target_pc:>8.1f}  {n_comp:>12,}  {isolates:>10,}  "
              f"{giant:>12,}  {pct:>9.3f}%", flush=True)

        # Record first time we reach a single component
        if n_comp == 1 and exact_min_jump is None:
            # Binary-search the exact crossing point within the last step
            lo = target_pc - args.step
            # Find the actual edge that closed the last component
            # (it's the edge just before edge_ptr that reduced components to 1)
            # We already consumed it; reconstruct from the sorted edge array.
            # Walk back to find the edge that merged the last two components.
            # This is a bit tricky with our incremental approach, so we report
            # the milestone as an upper bound.
            exact_min_jump = target_pc
            break

        last_components = n_comp

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print()
    if exact_min_jump is not None:
        # Find precise crossing: scan backward in d_vals from edge_ptr
        # to find the edge that merged the last two components.
        # Re-run a lightweight final sweep on just the last step's edges.
        step_start = np.searchsorted(d_vals,
                                     exact_min_jump - args.step,
                                     side="right")
        step_end   = edge_ptr

        # Rebuild Union-Find up to the start of the last step, then find
        # the exact edge.  This is fast since we only redo the last step.
        uf2 = UnionFind(n)
        for ei in range(step_start):
            uf2.union(int(i_vals[ei]), int(j_vals[ei]))
        # Also replay everything before step_start using the main uf
        # (just replay step_start..step_end one at a time watching for 1 comp)
        precise_jump: float | None = None
        for ei in range(step_start, step_end):
            uf2.union(int(i_vals[ei]), int(j_vals[ei]))
            if uf2.n_components == 1:
                precise_jump = float(d_vals[ei])
                break

        if precise_jump is not None:
            a_idx = int(i_vals[np.searchsorted(d_vals, precise_jump)])
            b_idx = int(j_vals[np.searchsorted(d_vals, precise_jump)])
            a_id  = int(sys_ids[a_idx])
            b_id  = int(sys_ids[b_idx])
            print(f"Minimum jump for full connectivity: {precise_jump:.4f} pc")
            print(f"  Final bridging edge: system {a_id} ↔ system {b_id}")
        else:
            print(f"Minimum jump for full connectivity: ≤ {exact_min_jump:.1f} pc "
                  f"(increase --step for precision)")
    else:
        n_comp, isolates, giant = uf.component_stats()
        pct = 100.0 * giant / n
        print(f"Graph NOT fully connected at {args.max_pc:.1f} pc.")
        print(f"  Components remaining: {n_comp:,}")
        print(f"  Isolates (size-1):    {isolates:,}")
        print(f"  Giant component:      {giant:,} stars ({pct:.2f}%)")
        print()
        print("Options:")
        print(f"  Increase --max-pc (current: {args.max_pc})")
        print(f"  Increase --knn (current: {args.knn}) — ensures MST edges are captured")
        print()
        if edge_ptr >= n_edges:
            # Exhausted all kNN edges — components remain because kNN was too small
            print("  WARNING: all kNN edges consumed but graph still disconnected.")
            print("  The remaining components have no mutual kNN links.")
            print(f"  Increase --knn beyond {args.knn} to find longer MST edges.")

    print(f"\nTotal wall time: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
