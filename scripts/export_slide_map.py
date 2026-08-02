#!/usr/bin/env python3
"""
export_slide_map.py — slide-ready qBraid-style map of the Sukhumvit district with the
90 cell-tower / atom sites (and the coverage graph handed to Aquila) overlaid.

High-resolution PNG on the offline CartoDB dark basemap, tuned for a presentation
slide (large markers, readable BTS labels, required attribution).

    python scripts/export_slide_map.py                 # -> results/sukhumvit_90_map.png
    python scripts/export_slide_map.py --no-graph      # towers only, no coverage edges
    python scripts/export_slide_map.py --scale 1.5     # even higher resolution
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import sleepcells as sc          # noqa: E402
import sleepwidgets as sw       # noqa: E402

INST = os.path.join(HERE, "results", "sukhumvit_90.json")
BP = os.path.join(HERE, "data", "sukhumvit_basemap.png")
BJ = os.path.join(HERE, "data", "sukhumvit_basemap.json")
OUT = os.path.join(HERE, "results", "sukhumvit_90_map.png")


def export(show_graph=True, scale=1.0):
    import plotly.graph_objects as go
    inst = sc.load_instance(INST)
    lon = inst["coords_lonlat"][:, 0]
    lat = inst["coords_lonlat"][:, 1]
    edges = list(inst["graph"].edges())

    uri, W, H, ext, attr = sw._basemap(BP, BJ)
    px, py = sw._project(lon, lat, ext, W, H)

    fig = go.Figure(sw._base_figure(uri, W, H, attr, height=H))

    QB_PURPLE = sw.ACCENT              # qBraid accent purple (#a06bff)
    QB_PURPLE_BRIGHT = "#c4a1ff"       # lighter core so it pops on the dark map
    if show_graph:                                  # coverage-overlap graph
        ex, ey = sw._edge_xy(px, py, edges)
        fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", hoverinfo="skip",
                                 line=dict(color="rgba(160,107,255,0.45)", width=2.2)))
    # atom sites: soft glow halo + bright core (qBraid purple)
    fig.add_trace(go.Scatter(x=px, y=py, mode="markers", hoverinfo="skip",
                             marker=dict(size=58, color=QB_PURPLE, opacity=0.18)))
    fig.add_trace(go.Scatter(x=px, y=py, mode="markers", hoverinfo="skip",
                             marker=dict(size=24, color=QB_PURPLE_BRIGHT,
                                         line=dict(color="white", width=1.3))))
    # BTS stations for orientation (bigger + readable labels)
    import numpy as np
    bx, by, names = [], [], []
    for name, blat, blon in sw._BTS:
        p, q = sw._project(blon, blat, ext, W, H)
        bx.append(float(np.ravel(p)[0])); by.append(float(np.ravel(q)[0])); names.append(name)
    fig.add_trace(go.Scatter(x=bx, y=by, mode="markers+text", text=names,
                             textposition="top right", hoverinfo="skip",
                             textfont=dict(color=sw.BTS_TXT, size=20, family=sw.FONT),
                             marker=dict(size=15, color="rgba(0,0,0,0)",
                                         line=dict(color=sw.BTS, width=2.4))))
    # bump the attribution so it stays legible at export size
    fig.layout.annotations[0].font.size = 15

    fig.write_image(OUT, width=W, height=H, scale=scale)
    print(f"saved -> {OUT}   ({int(W*scale)} x {int(H*scale)} px, "
          f"{'with' if show_graph else 'no'} coverage graph)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-graph", action="store_true", help="towers only (no coverage edges)")
    ap.add_argument("--scale", type=float, default=1.0, help="resolution multiplier")
    args = ap.parse_args()
    export(show_graph=not args.no_graph, scale=args.scale)


if __name__ == "__main__":
    main()
