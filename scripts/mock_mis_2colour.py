#!/usr/bin/env python3
"""
mock_mis_2colour.py — "run it yourself": a MOCK (classical) MIS on a small conflict
graph, coloured with TWO channels. No QPU, no data download — a self-contained
teaching version of the same iterated-MIS → graph-colouring idea in the deck.

Default instance is a ring of towers (an even cycle): each tower conflicts only with
its two neighbours, so it is 2-colourable and the mock MIS lands exactly two channels,
alternating around the ring. Pass --random N for a random unit-disk instance, where
two channels may NOT be enough — the honest "greedy colouring can need more" lesson.

    python scripts/mock_mis_2colour.py                 # ring of 10 towers -> 2 channels
    python scripts/mock_mis_2colour.py --n 14          # bigger ring
    python scripts/mock_mis_2colour.py --random 12     # random towers (may need >2)
"""

from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import towers as tw  # noqa: E402
import channels as ch  # noqa: E402

OUT = os.path.join(HERE, "results", "mock_mis_2colour.png")

# qBraid deck palette
BG, TEXT, MUTED = "#0a0a0b", "#ECE9E0", "#8A8580"
CH_COLORS = ["#9F6CFF", "#4ade80", "#ffb020", "#60a5fa", "#ff6fae"]  # ch1 purple, ch2 green, ...


def ring_instance(n=10):
    """n towers on a ring road; each conflicts with its two neighbours (even cycle
    when n is even -> 2-colourable)."""
    import networkx as nx

    G = nx.cycle_graph(n)
    pos = {i: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)}
    return G, pos


def random_instance(n=12, radius=0.46, seed=1):
    """n towers at random positions; conflict edge when within `radius` (unit-disk)."""
    import networkx as nx
    import numpy as np

    rng = np.random.default_rng(seed)
    P = rng.random((n, 2))
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(P[i, 0] - P[j, 0], P[i, 1] - P[j, 1]) < radius:
                G.add_edge(i, j)
    return G, {i: tuple(P[i]) for i in range(n)}


def mock_solve(G):
    """MOCK MIS: iterated classical MIS (stands in for the quantum device). Each round
    is one channel; nodes are deleted, not edges; repeat until every tower is coloured."""
    channels, channel_of, prov = ch.iterated_mis_coloring(G, solver="exact")
    return channels, channel_of, prov


def plot(G, pos, channels, channel_of, two_ok):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")
    for u, v in G.edges():
        style = "-" if channel_of[u] != channel_of[v] else ":"  # dotted = still-conflicting
        col = "#3a3a40" if channel_of[u] != channel_of[v] else "#ff5a5a"
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]], style, color=col, lw=1.6, zorder=1)
    for c, nodes in enumerate(channels):
        xs = [pos[i][0] for i in nodes]
        ys = [pos[i][1] for i in nodes]
        ax.scatter(
            xs,
            ys,
            s=520,
            c=CH_COLORS[c % len(CH_COLORS)],
            edgecolors="white",
            linewidths=1.4,
            zorder=3,
            label=f"channel {c+1} ({len(nodes)})",
        )
    for i in G.nodes():
        ax.text(
            pos[i][0],
            pos[i][1],
            str(i),
            color="#0a0a0b",
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            zorder=4,
        )
    title = f"Mock MIS → {len(channels)} channel(s)" + (
        "  ·  2 colours suffice ✓" if two_ok else "  ·  needs > 2 colours"
    )
    ax.set_title(title, color=TEXT, fontsize=15, loc="center", pad=16)
    leg = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=len(channels),
        frameon=False,
        fontsize=11,
        labelcolor=TEXT,
    )
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(OUT, dpi=140, facecolor=BG, bbox_inches="tight")
    print(f"figure -> {OUT}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--n", type=int, default=10, help="number of towers on the ring")
    ap.add_argument(
        "--random",
        type=int,
        metavar="N",
        default=None,
        help="use a random unit-disk instance of N towers instead of the ring",
    )
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    if args.random:
        G, pos = random_instance(args.random, seed=args.seed)
        kind = f"random unit-disk, {args.random} towers"
    else:
        G, pos = ring_instance(args.n)
        kind = f"ring road, {args.n} towers"

    channels, channel_of, prov = mock_solve(G)
    ok, problems = ch.verify_coloring(G, channel_of)
    chi = ch.chromatic_number(G)
    two_ok = len(channels) == 2

    print(
        f"instance     : {kind}  ({G.number_of_nodes()} nodes, {G.number_of_edges()} conflict edges)"
    )
    print(f"mock MIS runs: {[len(c) for c in channels]}  -> {len(channels)} channel(s)")
    for p in prov:
        print(f"  channel {p['channel']+1}: {p['size']} towers  [{p['source']}]")
    print(f"minimum possible (chromatic number): {chi}")
    print(f"two colours enough? {'YES' if two_ok else 'NO — this graph needs more'}")
    print(f"valid colouring   : {'YES — no conflict shares a channel' if ok else problems}")
    plot(G, pos, channels, channel_of, two_ok)


if __name__ == "__main__":
    main()
