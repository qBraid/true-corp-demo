#!/usr/bin/env python3
"""
export_channel_map.py — slide-ready qBraid map of the 90 towers coloured by the
QPU-measured frequency channel. Dots only, NO edges. Same basemap/style as
export_slide_map.py, on the offline CartoDB dark basemap.

    python scripts/export_channel_map.py                    # -> results/sukhumvit_90_channels.png
    python scripts/export_channel_map.py --no-legend        # dots only, no legend
    python scripts/export_channel_map.py --scale 1.5        # higher resolution
    python scripts/export_channel_map.py --assign results/channel_assignment_90.json  # classical plan
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import widgets as wg  # noqa: E402

BP = os.path.join(HERE, "data", "sukhumvit_basemap.png")
BJ = os.path.join(HERE, "data", "sukhumvit_basemap.json")
DEFAULT_ASSIGN = os.path.join(HERE, "results", "channel_assignment_90_qpu.json")
OUT = os.path.join(HERE, "results", "sukhumvit_90_channels.png")


def export(assign_path, scale=1.0, legend=True):
    import numpy as np
    import plotly.graph_objects as go

    d = json.load(open(assign_path))
    coords = np.asarray(d["coords_lonlat"], float)
    channels = [list(c) for c in d["channels"]]
    palette = wg.CHANNEL_PALETTE

    uri, W, H, ext, attr = wg._basemap(BP, BJ)
    px, py = wg._project(coords[:, 0], coords[:, 1], ext, W, H)

    fig = go.Figure(wg._base_figure(uri, W, H, attr, height=H))
    # one glow + one core trace per channel (dots only — no coverage edges)
    for c, nodes in enumerate(channels):
        col = palette[c % len(palette)]
        fig.add_trace(
            go.Scatter(
                x=px[nodes],
                y=py[nodes],
                mode="markers",
                hoverinfo="skip",
                showlegend=False,
                marker=dict(size=52, color=col, opacity=0.16),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=px[nodes],
                y=py[nodes],
                mode="markers",
                hoverinfo="skip",
                name=f"channel {c+1}  ({len(nodes)})",
                showlegend=legend,
                marker=dict(size=24, color=col, line=dict(color="white", width=1.3)),
            )
        )
    # BTS stations for orientation
    bx, by, names = [], [], []
    for name, blat, blon in wg._BTS:
        p, q = wg._project(blon, blat, ext, W, H)
        bx.append(float(np.ravel(p)[0]))
        by.append(float(np.ravel(q)[0]))
        names.append(name)
    fig.add_trace(
        go.Scatter(
            x=bx,
            y=by,
            mode="markers+text",
            text=names,
            showlegend=False,
            textposition="top right",
            hoverinfo="skip",
            textfont=dict(color=wg.BTS_TXT, size=20, family=wg.FONT),
            marker=dict(size=15, color="rgba(0,0,0,0)", line=dict(color=wg.BTS, width=2.4)),
        )
    )
    fig.layout.annotations[0].font.size = 15
    if legend:
        fig.update_layout(
            showlegend=True,
            legend=dict(
                x=0.985,
                y=0.985,
                xanchor="right",
                yanchor="top",
                bgcolor="rgba(11,15,20,0.78)",
                bordercolor="#33404f",
                borderwidth=1,
                font=dict(color=wg.TEXT, size=22, family=wg.FONT),
                itemsizing="constant",
                tracegroupgap=2,
            ),
        )

    fig.write_image(OUT, width=W, height=H, scale=scale)
    n_ch = len(channels)
    print(
        f"saved -> {OUT}   ({int(W*scale)} x {int(H*scale)} px, {n_ch} channels, "
        f"source={d.get('source', 'n/a')})"
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--assign", default=DEFAULT_ASSIGN, help="channel-assignment JSON")
    ap.add_argument("--no-legend", action="store_true", help="dots only, no legend")
    ap.add_argument("--scale", type=float, default=1.0, help="resolution multiplier")
    args = ap.parse_args()
    export(args.assign, scale=args.scale, legend=not args.no_legend)


if __name__ == "__main__":
    main()
