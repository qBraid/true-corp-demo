#!/usr/bin/env python3
"""
run_channel_assignment.py — iterated-MIS channel plan for the 90-atom Sukhumvit
instance, seeding channel 1 with the REAL Aquila-measured MIS.

Channel 1 is the executed QuEra Aquila result (the 34-tower independent set (co-channel group));
channels 2..N are solved classically on the residual subgraph (each round could
equally be another Aquila submission). Produces a full frequency-reuse plan, checks
it is a valid colouring, and reports the greedy-vs-lower-bound gap.

    python scripts/run_channel_assignment.py            # run + save + summarise
    python scripts/run_channel_assignment.py --display  # + render the channel map PNG
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import towers as tw  # noqa: E402
import channels as ch  # noqa: E402

INSTANCE = os.path.join(HERE, "results", "sukhumvit_90.json")
QPU = os.path.join(HERE, "results", "headline_qpu_90_results.json")
OUT = os.path.join(HERE, "results", "channel_assignment_90.json")
OUT_FIG = os.path.join(HERE, "results", "channel_assignment_90.png")


def _qpu_channel_one(inst):
    """Round-1 independent set = the executed Aquila MIS (blockade-rejected)."""
    res = tw.load_results(QPU)
    sel, _ret, _tot, _defect = tw.decode_shots(res["shots"], inst["n_atoms"], policy="postselect")
    best, _viol, _nvalid = tw.best_valid_set(sel, inst["graph"])
    return best


def run():
    inst = tw.load_instance(INSTANCE)
    G = inst["graph"]
    qpu_mis = _qpu_channel_one(inst)

    channels, channel_of, prov = ch.iterated_mis_coloring(G, first_set=qpu_mis, solver="exact")
    ok, problems = ch.verify_coloring(G, channel_of)
    lb = ch.clique_lower_bound(G)
    chi = ch.chromatic_number(G)  # exact optimum (ILP-baseline)
    overspend = len(channels) - chi

    print(f"conflict graph : {G.number_of_nodes()} towers, {G.number_of_edges()} conflict edges")
    print(f"channels used  : {len(channels)}  (iterated-MIS, greedy)")
    print(f"optimal        : {chi}  (exact chromatic number; clique floor omega = {lb})")
    print(
        f"overspend      : {overspend}  "
        + (
            "(greedy is optimal here)"
            if overspend == 0
            else f"(greedy used {overspend} channel(s) more than necessary)"
        )
    )
    print(f"round sizes    : {[len(c) for c in channels]}")
    for p in prov:
        print(
            f"  channel {p['channel']+1}: {p['size']:2d} towers  [{p['source']:>22s}]  "
            f"(residual before: {p['residual_nodes']}n / {p['residual_edges']}e)"
        )
    print(
        f"valid colouring: {'YES — every tower one channel, no conflict shares a frequency' if ok else problems}"
    )

    out = {
        "instance": "sukhumvit_90",
        "n_atoms": inst["n_atoms"],
        "n_channels": len(channels),
        "chromatic_number": chi,
        "overspend": overspend,
        "clique_lower_bound": lb,
        "round_sizes": [len(c) for c in channels],
        "channels": [[int(v) for v in c] for c in channels],
        "channel_of": {str(k): int(v) for k, v in channel_of.items()},
        "provenance": prov,
        "valid": bool(ok),
        "coords_lonlat": [[float(x), float(y)] for x, y in inst["coords_lonlat"]],
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"saved -> {OUT}")
    return inst, channels, channel_of


def display(inst, channels, channel_of):
    """Validation figure: towers coloured by channel, conflict edges faint."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    lon = inst["coords_lonlat"][:, 0]
    lat = inst["coords_lonlat"][:, 1]
    G = inst["graph"]
    palette = ["#e4002b", "#22e0a6", "#a06bff", "#ffb020", "#4aa3ff", "#ff6fae", "#8ce06a"]
    fig, ax = plt.subplots(figsize=(8, 7))
    fig.patch.set_facecolor("#0b0f14")
    ax.set_facecolor("#0b0f14")
    for u, v in G.edges():
        ax.plot([lon[u], lon[v]], [lat[u], lat[v]], color="#33404f", lw=0.5, zorder=1)
    for c, nodes in enumerate(channels):
        ax.scatter(
            lon[nodes],
            lat[nodes],
            s=70,
            c=palette[c % len(palette)],
            edgecolors="white",
            linewidths=0.5,
            zorder=3,
            label=f"channel {c+1}  ({len(nodes)})",
        )
    ax.set_title(
        f"Frequency-reuse plan — {len(channels)} channels, "
        f"{G.number_of_nodes()} towers (channel 1 = Aquila)",
        color="white",
        loc="left",
        fontsize=12,
    )
    ax.legend(
        facecolor="#11161d", edgecolor="none", labelcolor="white", fontsize=9, loc="upper right"
    )
    ax.tick_params(colors="#8a94a3")
    [s.set_color("#33404f") for s in ax.spines.values()]
    fig.tight_layout()
    fig.savefig(OUT_FIG, dpi=120, facecolor=fig.get_facecolor())
    print(f"figure -> {OUT_FIG}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--display", action="store_true", help="render the channel-map PNG")
    args = ap.parse_args()
    inst, channels, channel_of = run()
    if args.display:
        display(inst, channels, channel_of)


if __name__ == "__main__":
    main()
