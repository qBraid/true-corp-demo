"""
widgets.py — polished, dark, qBraid-themed interactive views of the Aquila result
=================================================================================

Interactive ipywidgets + Plotly views for the live demo. Both overlay REAL
coordinates on the offline CartoDB dark basemap (no live tiles) and use Plotly
``FigureWidget`` for smooth marker transitions, driven by ipywidgets controls.

    pipeline_view(inst, basemap_png, basemap_json)
        3-state reveal:  District  ->  real cell towers  ->  atom sites + graph.

    channel_stepper_view(assignment, edges, basemap_png, basemap_json)
        Step through the frequency-reuse plan one channel (one MIS) at a time.
"""

from __future__ import annotations

import base64
import json as _json
import math

import numpy as np

# --------------------------------------------------------------------------
# qBraid dark theme  (channel 1 = True red, matches the slides; teal = channel 2;
# purple = qBraid UI accent)
# --------------------------------------------------------------------------
BG = "#0b0f14"  # near-black, slightly cool
CARD_TOP = "#0e141b"
RED = "#e4002b"  # True red, channel 1 / the highlighted MIS
RED_HI = "#ff5a76"
TEAL = "#22e0a6"  # teal, channel 2
TEAL_DIM = "#39424f"  # dimmed grey
TOWER = "#ff5a76"  # lit cell tower
EDGE = "rgba(228,0,43,0.30)"
BTS = "#6fd0e0"
BTS_TXT = "#a8e6f1"
ACCENT = "#a06bff"  # qBraid purple
TEXT = "#e8edf4"
MUTED = "#8a94a3"
FONT = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial"

# Sukhumvit Line BTS stations, for orientation (name, lat, lon).
_BTS = [
    ("Asok", 13.7370, 100.5604),
    ("Phrom Phong", 13.7304, 100.5697),
    ("Thong Lo", 13.7242, 100.5786),
    ("Ekkamai", 13.7196, 100.5852),
]


# --------------------------------------------------------------------------
# Basemap + Web-Mercator projection (identical math to viz._lonlat_to_px,
# but returns Plotly y with a BOTTOM origin so points sit on the image).
# --------------------------------------------------------------------------
def _basemap(basemap_png: str, basemap_json: str):
    from PIL import Image

    meta = _json.load(open(basemap_json))
    with open(basemap_png, "rb") as f:
        uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    W, H = Image.open(basemap_png).size
    ext = (meta["west"], meta["east"], meta["south"], meta["north"])
    return uri, W, H, ext, meta.get("attribution", "© OpenStreetMap © CARTO")


def _project(lon, lat, ext, W, H):
    west, east, south, north = ext
    merc = lambda a: math.log(math.tan(math.pi / 4 + math.radians(a) / 2))
    mn, ms = merc(north), merc(south)
    px = (np.asarray(lon, float) - west) / (east - west) * W
    py_top = (mn - np.array([merc(v) for v in np.atleast_1d(lat)])) / (mn - ms) * H
    return px, H - py_top  # flip to bottom-origin for Plotly


def _base_figure(uri, W, H, attribution, height):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        images=[
            dict(
                source=uri,
                xref="x",
                yref="y",
                x=0,
                y=0,
                sizex=W,
                sizey=H,
                xanchor="left",
                yanchor="bottom",
                sizing="stretch",
                layer="below",
            )
        ],
        xaxis=dict(range=[0, W], visible=False, constrain="domain"),
        yaxis=dict(range=[0, H], visible=False, scaleanchor="x", scaleratio=1),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        font=dict(family=FONT, color=TEXT),
        dragmode="pan",
        hovermode="closest",
    )
    fig.add_annotation(
        x=0.004,
        y=0.012,
        xref="paper",
        yref="paper",
        text=attribution,
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(size=9, color=MUTED),
    )
    return fig


def _bts_traces(ext, W, H):
    import plotly.graph_objects as go

    xs, ys, names = [], [], []
    for name, blat, blon in _BTS:
        bx, by = _project(blon, blat, ext, W, H)
        xs.append(float(np.ravel(bx)[0]))
        ys.append(float(np.ravel(by)[0]))
        names.append(name)
    marker = go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=names,
        textposition="top right",
        textfont=dict(color=BTS_TXT, size=10),
        marker=dict(size=8, color="rgba(0,0,0,0)", line=dict(color=BTS, width=1.4)),
        hoverinfo="skip",
        name="BTS",
    )
    return marker


def _edge_xy(px, py, edges):
    ex, ey = [], []
    for a, b in edges:
        ex += [px[a], px[b], None]
        ey += [py[a], py[b], None]
    return ex, ey


# --------------------------------------------------------------------------
# Styled shell (dark card + qBraid-themed controls)
# --------------------------------------------------------------------------
_CSS = f"""
.qb-card {{ background: var(--jp-layout-color1, {CARD_TOP});
  border:1px solid var(--jp-border-color2, #1b2431); border-radius:16px; padding:18px 20px 12px;
  font-family:{FONT}; color:var(--jp-ui-font-color1, {TEXT}); max-width:960px;
  box-shadow:0 8px 34px rgba(0,0,0,.30); }}
.qb-card .qb-h {{ font-size:19px; font-weight:650; letter-spacing:.2px; margin:2px 0 4px;
  color:var(--jp-ui-font-color0, {TEXT}); display:flex; align-items:center; gap:9px; }}
.qb-card .qb-h::before {{ content:''; width:9px; height:9px; border-radius:50%; flex:0 0 auto;
  background:{ACCENT}; box-shadow:0 0 12px {ACCENT}; }}
.qb-card .qb-sub {{ color:var(--jp-ui-font-color2, {MUTED}); font-size:12.5px; margin:0 0 12px 18px; }}
.qb-card .qb-cap {{ color:var(--jp-ui-font-color1, #aeb8c6); font-size:13.5px; line-height:1.5;
  margin:12px 2px 4px; border-left:2px solid {ACCENT}; padding-left:11px; min-height:22px; }}
.qb-card .widget-toggle-buttons .widget-toggle-button,
.qb-card .widget-toggle-buttons button, .qb-card button.jupyter-button {{
  background:#131a23 !important; color:#c2ccd9 !important; border:1px solid #223046 !important;
  border-radius:10px !important; font-family:{FONT} !important; font-weight:550 !important;
  margin-right:7px !important; padding:6px 16px !important; box-shadow:none !important;
  text-align:center !important; display:inline-flex !important;
  align-items:center !important; justify-content:center !important;
  transition:all .18s ease !important; }}
.qb-card .widget-toggle-buttons button:hover, .qb-card button.jupyter-button:hover {{
  border-color:{ACCENT} !important; color:{TEXT} !important; }}
.qb-card .widget-toggle-buttons button.mod-active, .qb-card button.mod-active {{
  background:linear-gradient(180deg,{ACCENT},#7d49e0) !important; color:#fff !important;
  border-color:{ACCENT} !important; box-shadow:0 0 16px rgba(160,107,255,.45) !important; }}
"""


def _shell(title, subtitle, controls, fig, caption):
    import ipywidgets as W

    controls.layout.margin = "0 0 16px 0"  # breathing room between buttons and the map
    css = W.HTML(f"<style>{_CSS}</style>")
    head = W.HTML(f"<div class='qb-h'>{title}</div><div class='qb-sub'>{subtitle}</div>")
    box = W.VBox([css, head, controls, fig, caption])
    box.add_class("qb-card")
    return box


def _cap(html):
    return f"<div class='qb-cap'>{html}</div>"


# --------------------------------------------------------------------------
# WIDGET 1 — pipeline reveal:  District -> cell towers -> atom sites + graph
# --------------------------------------------------------------------------
def build_pipeline_traces(fig, inst, ext, W, H):
    """Add the four data traces (edges, glow, core towers, BTS) at state-0 styling.
    Trace order: [0]=edges [1]=glow [2]=core [3]=BTS."""
    import plotly.graph_objects as go

    lon = inst["coords_lonlat"][:, 0]
    lat = inst["coords_lonlat"][:, 1]
    px, py = _project(lon, lat, ext, W, H)
    edges = list(inst["graph"].edges())
    ex, ey = _edge_xy(px, py, edges)

    fig.add_trace(
        go.Scatter(
            x=ex,
            y=ey,
            mode="lines",
            line=dict(color=EDGE, width=1),
            hoverinfo="skip",
            opacity=0.0,
            name="coverage",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=px,
            y=py,
            mode="markers",
            hoverinfo="skip",
            name="glow",
            marker=dict(size=24, color=RED, opacity=0.0),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=px,
            y=py,
            mode="markers",
            name="towers",
            marker=dict(size=9, color=TOWER, opacity=0.0, line=dict(color="white", width=0.6)),
            customdata=list(range(len(lon))),
            hovertemplate="site %{customdata}<br>%{text}<extra></extra>",
            text=[f"{a:.4f}, {b:.4f}" for a, b in zip(lat, lon)],
        )
    )
    fig.add_trace(_bts_traces(ext, W, H))
    return len(lon), len(edges)


def _apply_ctx(fig, animate):
    """Context manager that animates on a FigureWidget, batches on a widget, or is a
    no-op on a plain go.Figure (used for static export)."""
    import contextlib

    if animate and hasattr(fig, "batch_animate"):
        return fig.batch_animate(duration=560, easing="cubic-in-out")
    if hasattr(fig, "batch_update"):
        return fig.batch_update()
    return contextlib.nullcontext()


def _pipeline_apply(fig, state, animate=True):
    """State 0 = district, 1 = towers, 2 = atoms + coverage graph."""
    edges_op = 1.0 if state >= 2 else 0.0
    glow_op = 0.20 if state >= 2 else 0.0
    core_op = 1.0 if state >= 1 else 0.0
    core_sz = 12 if state >= 2 else 9
    with _apply_ctx(fig, animate):
        fig.data[0].opacity = edges_op
        fig.data[1].marker.opacity = glow_op
        fig.data[2].marker.opacity = core_op
        fig.data[2].marker.size = core_sz


def pipeline_view(inst, basemap_png, basemap_json, height=560):
    import plotly.graph_objects as go
    import ipywidgets as W

    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.FigureWidget(_base_figure(uri, Wpx, Hpx, attr, height))
    n, m = build_pipeline_traces(fig, inst, ext, Wpx, Hpx)

    steps = [("①  District", 0), ("②  Cell towers", 1), ("③  Atom sites + graph", 2)]
    caps = [
        "<b>Watthana / Sukhumvit</b> — the slice of True's network we model. Blue rings are "
        "Sukhumvit-Line BTS stations, for orientation.",
        f"<b>{n} real cell-tower sites</b> from OpenCelliD (LTE / UMTS only; GSM is the 2G "
        "floor, excluded). These are crowdsourced estimated positions.",
        f"<b>{n} atoms, {m} coverage edges.</b> An edge joins two sites whose coverage overlaps "
        "(≤ 500 m). This is the <i>exact</i> unit-disk graph we hand to QuEra Aquila.",
    ]
    toggle = W.ToggleButtons(options=steps, value=0)
    toggle.add_class("widget-toggle-buttons")
    cap = W.HTML(_cap(caps[0]))

    def _on(change):
        _pipeline_apply(fig, change["new"])
        cap.value = _cap(caps[change["new"]])

    toggle.observe(_on, names="value")
    _pipeline_apply(fig, 0, animate=False)
    return _shell(
        "From district to atoms",
        "How Sukhumvit becomes a problem QuEra Aquila can solve.",
        toggle,
        fig,
        cap,
    )


# --------------------------------------------------------------------------
# WIDGET 3 — channel stepper: reveal the frequency-reuse plan one channel at a time
# --------------------------------------------------------------------------
CHANNEL_PALETTE = [RED, TEAL, ACCENT, "#ffb020", "#4aa3ff", "#ff6fae", "#8ce06a"]


def _residual_edge_xy(edges, revealed, px, py):
    """Line coords for conflicts still unresolved: both endpoints not yet on a channel."""
    ex, ey = [], []
    for u, v in edges:
        if u not in revealed and v not in revealed:
            ex += [px[u], px[v], None]
            ey += [py[u], py[v], None]
    return ex, ey


def build_channel_traces(fig, coords, edges, channels, ext, W, H):
    """Traces: [0]=residual conflict edges, [1]=grey base (all towers),
    [2..2+C-1]=one coloured trace per channel.

    Initialised to the OPENING state (channel 1 revealed, edges = the residual after
    channel 1) so a freshly-created FigureWidget PAINTS channel 1 red on first render —
    property changes pushed before display don't always reach the frontend."""
    import plotly.graph_objects as go

    px, py = _project(coords[:, 0], coords[:, 1], ext, W, H)
    revealed0 = set(channels[0]) if channels else set()
    ex0, ey0 = _residual_edge_xy(edges, revealed0, px, py)
    fig.add_trace(
        go.Scatter(
            x=ex0,
            y=ey0,
            mode="lines",
            name="conflicts",
            line=dict(color="rgba(150,160,175,0.40)", width=1),
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=px,
            y=py,
            mode="markers",
            name="unassigned",
            hoverinfo="skip",
            marker=dict(
                size=8, color="#55606f", opacity=0.9, line=dict(color="#0b0f14", width=0.5)
            ),
        )
    )
    for c, nodes in enumerate(channels):
        col = CHANNEL_PALETTE[c % len(CHANNEL_PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=px[nodes],
                y=py[nodes],
                mode="markers",
                name=f"channel {c+1}",
                marker=dict(
                    size=12,
                    color=col,
                    opacity=(1.0 if c == 0 else 0.0),
                    line=dict(color="white", width=0.6),
                ),
                hovertemplate=f"channel {c+1}<extra></extra>",
            )
        )
    return px, py


def _channel_apply(fig, k, edges, channels, px, py, animate=True):
    """Show channels 1..k: reveal their coloured towers, thin the residual conflicts."""
    revealed = set(v for c in range(k) for v in channels[c])
    ex, ey = _residual_edge_xy(edges, revealed, px, py)
    with _apply_ctx(fig, animate):
        fig.data[0].x = ex
        fig.data[0].y = ey
        for c in range(len(channels)):
            fig.data[2 + c].marker.opacity = 1.0 if c < k else 0.0


def channel_stepper_view(assignment, edges, basemap_png, basemap_json, height=560):
    """Step through a frequency-reuse plan one channel at a time on the dark map.

    assignment : the loaded channel-assignment dict (channels, coords_lonlat, ...).
    edges      : the conflict-graph edges (list of [u, v]) — for the residual overlay.
    """
    import numpy as np
    import plotly.graph_objects as go
    import ipywidgets as W

    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    coords = np.asarray(assignment["coords_lonlat"], float)
    channels = [list(c) for c in assignment["channels"]]
    N = len(channels)
    total = sum(len(c) for c in channels)
    edges = [tuple(e) for e in edges]

    fig = go.FigureWidget(_base_figure(uri, Wpx, Hpx, attr, height))
    px, py = build_channel_traces(fig, coords, edges, channels, ext, Wpx, Hpx)

    def residual_after(k):
        revealed = set(v for c in range(k) for v in channels[c])
        return sum(1 for u, v in edges if u not in revealed and v not in revealed)

    src = assignment.get("source", "")
    chi = assignment.get("chromatic_number")
    opts = [(f"{'▶ ' if k == 1 else '+'} ch {k}", k) for k in range(1, N + 1)]
    steps_caps = []
    for k in range(1, N + 1):
        on = sum(len(channels[c]) for c in range(k))
        left = residual_after(k)
        note = (
            "<b>every conflict resolved</b> — the whole district runs on "
            f"<b>{N} frequencies</b>."
            if left == 0
            else f"<b>{left} conflicts still unresolved</b> among the {total-on} un-channelled towers."
        )
        col = CHANNEL_PALETTE[(k - 1) % len(CHANNEL_PALETTE)]
        steps_caps.append(
            f"Channels 1–{k} lit · <b>{on} of {total}</b> towers on "
            f"<span style='color:{col}'>{k} frequenc{'y' if k == 1 else 'ies'}</span>. {note}"
        )

    toggle = W.ToggleButtons(options=opts, value=1)
    toggle.add_class("widget-toggle-buttons")
    cap = W.HTML(_cap(steps_caps[0]))

    def _on(change):
        _channel_apply(fig, change["new"], edges, channels, px, py)
        cap.value = _cap(steps_caps[change["new"] - 1])

    toggle.observe(_on, names="value")
    _channel_apply(fig, 1, edges, channels, px, py, animate=False)

    opt = (
        ""
        if chi is None
        else (
            " · optimal is "
            + str(chi)
            + (" (greedy overspent by %d)" % (N - chi) if N > chi else " (optimal)")
        )
    )
    sub = (
        f"Repeated MIS → graph colouring. {N} channels"
        + opt
        + (" · every channel measured on Aquila" if src == "QPU_iterated" else "")
    )
    return _shell("Frequency reuse — one MIS per channel", sub, toggle, fig, cap)


# --------------------------------------------------------------------------
# Static export (for headless verification): plain go.Figure at a given state
# --------------------------------------------------------------------------
def _static_channel(assignment, edges, basemap_png, basemap_json, k, height=560):
    import numpy as np
    import plotly.graph_objects as go

    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.Figure(_base_figure(uri, Wpx, Hpx, attr, height))
    coords = np.asarray(assignment["coords_lonlat"], float)
    channels = [list(c) for c in assignment["channels"]]
    edges = [tuple(e) for e in edges]
    px, py = build_channel_traces(fig, coords, edges, channels, ext, Wpx, Hpx)
    _channel_apply(fig, k, edges, channels, px, py, animate=False)
    return fig


def _static_pipeline(inst, basemap_png, basemap_json, state, height=560):
    import plotly.graph_objects as go

    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.Figure(_base_figure(uri, Wpx, Hpx, attr, height))
    build_pipeline_traces(fig, inst, ext, Wpx, Hpx)
    _pipeline_apply(fig, state, animate=False)
    return fig


# --------------------------------------------------------------------------
# Teaching view: colour an abstract conflict graph (no basemap). Rendered as a
# plain Plotly figure with a client-side slider, so the colouring stays live in a
# saved notebook (no running kernel required).
# --------------------------------------------------------------------------
def _graph_layout(coords):
    """Atom coordinates (um) -> tidy unit-square x/y for a node-link plot."""
    c = np.asarray(coords, dtype=float)
    x, y = c[:, 0], c[:, 1]
    s = max(x.max() - x.min(), y.max() - y.min()) or 1.0
    return (x - x.min()) / s, (y - y.min()) / s


def _graph_canvas(height, title, subtitle):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(visible=False, range=[-0.08, 1.08], constrain="domain"),
        yaxis=dict(visible=False, range=[-0.08, 1.08], scaleanchor="x", scaleratio=1),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        height=height,
        margin=dict(l=14, r=14, t=58, b=14),
        showlegend=False,
        font=dict(family=FONT, color=TEXT),
        hovermode="closest",
        title=dict(
            text=f"{title}<br><span style='font-size:12.5px;color:{MUTED}'>{subtitle}</span>",
            x=0.02,
            xanchor="left",
            y=0.97,
            font=dict(size=17, color=TEXT),
        ),
    )
    return fig


def graph_view(coords, edges, height=430, title="The conflict graph"):
    """Static Plotly view of a conflict graph: towers as nodes, conflicts as edges."""
    import plotly.graph_objects as go

    x, y = _graph_layout(coords)
    edges = [tuple(e) for e in edges]
    subtitle = (
        f"{len(x)} towers, {len(edges)} conflicts. An edge means two towers "
        "overlap, so they cannot share a channel."
    )
    fig = _graph_canvas(height, title, subtitle)
    ex, ey = _edge_xy(x, y, edges)
    fig.add_trace(
        go.Scatter(
            x=ex,
            y=ey,
            mode="lines",
            hoverinfo="skip",
            line=dict(color="rgba(150,160,175,0.45)", width=1.3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers+text",
            text=[str(i) for i in range(len(x))],
            textposition="middle center",
            textfont=dict(color="#0b0f14", size=11),
            marker=dict(size=24, color=ACCENT, line=dict(color="white", width=1.2)),
            hovertemplate="tower %{text}<extra></extra>",
        )
    )
    return fig


def channel_graph_view(
    coords, edges, channels, height=470, title="Frequency reuse: one MIS per channel"
):
    """Live Plotly colouring of the conflict graph: a client-side slider reveals the
    channels one at a time (channel 1 = the MIS measured on the simulator)."""
    import plotly.graph_objects as go

    x, y = _graph_layout(coords)
    edges = [tuple(e) for e in edges]
    channels = [list(c) for c in channels]
    N = len(channels)
    total = sum(len(c) for c in channels)
    ex, ey = _edge_xy(x, y, edges)

    def subtitle(k):
        on = sum(len(channels[c]) for c in range(k))
        return (
            f"channels 1-{k} lit &middot; {on} of {total} towers on "
            f"{k} frequenc{'y' if k == 1 else 'ies'} &middot; every conflict resolved at {N}"
        )

    fig = _graph_canvas(height, title, subtitle(1))
    fig.add_trace(
        go.Scatter(
            x=ex,
            y=ey,
            mode="lines",
            hoverinfo="skip",
            line=dict(color="rgba(150,160,175,0.40)", width=1.2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            hoverinfo="skip",
            marker=dict(size=22, color="#55606f", line=dict(color="#0b0f14", width=1)),
        )
    )
    for c, nodes in enumerate(channels):
        col = CHANNEL_PALETTE[c % len(CHANNEL_PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=[x[i] for i in nodes],
                y=[y[i] for i in nodes],
                mode="markers+text",
                text=[str(i) for i in nodes],
                textposition="middle center",
                textfont=dict(color="#0b0f14", size=11),
                marker=dict(size=24, color=col, line=dict(color="white", width=1.4)),
                name=f"channel {c + 1}",
                hovertemplate=f"channel {c + 1}<extra></extra>",
                visible=(c == 0),
            )
        )

    steps = []
    for k in range(1, N + 1):
        vis = [True, True] + [c < k for c in range(N)]
        steps.append(
            dict(
                method="update",
                label=str(k),
                args=[
                    {"visible": vis},
                    {
                        "title.text": f"{title}<br><span style='font-size:12.5px;color:{MUTED}'>{subtitle(k)}</span>"
                    },
                ],
            )
        )
    fig.update_layout(
        sliders=[
            dict(
                active=0,
                x=0.02,
                y=0,
                len=0.96,
                pad=dict(t=34, b=4),
                currentvalue=dict(prefix="channels: ", font=dict(color=TEXT, size=13)),
                bgcolor="#1b2431",
                bordercolor="#33404f",
                borderwidth=1,
                tickcolor="#33404f",
                font=dict(color=TEXT),
                steps=steps,
            )
        ]
    )
    return fig
