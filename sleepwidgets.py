"""
sleepwidgets.py — polished, dark, qBraid-themed interactive views of the Aquila result
=======================================================================================

Two ipywidgets + Plotly widgets for the live demo. Both overlay REAL coordinates on
the offline CartoDB dark basemap (no live tiles) and use Plotly ``FigureWidget`` for
smooth marker transitions, driven by ipywidgets controls.

    pipeline_view(inst, basemap_png, basemap_json)
        3-state reveal:  ① District  →  ② real cell towers  →  ③ atom sites + graph.

    sleep_view(inst, asleep, basemap_png, basemap_json)
        2-state result:  all towers lit  →  the MIS towers power down (asleep),
        the awake towers stay lit and keep coverage. `asleep` = the verified sleep set.

Nothing here is imported by the presentation notebook; it is a standalone showpiece.
"""

from __future__ import annotations

import base64
import json as _json
import math

import numpy as np

# --------------------------------------------------------------------------
# qBraid dark theme  (asleep = True red, matches the slides; teal = awake/covering;
# purple = qBraid UI accent)
# --------------------------------------------------------------------------
BG        = "#0b0f14"   # near-black, slightly cool
CARD_TOP  = "#0e141b"
ASLEEP    = "#e4002b"   # True red — the MIS / cells that sleep
ASLEEP_HI = "#ff5a76"
AWAKE     = "#22e0a6"   # teal — awake, still covering
AWAKE_DIM = "#39424f"   # powered-down grey
TOWER     = "#ff5a76"   # lit cell tower
EDGE      = "rgba(228,0,43,0.30)"
BTS       = "#6fd0e0"
BTS_TXT   = "#a8e6f1"
ACCENT    = "#a06bff"   # qBraid purple
TEXT      = "#e8edf4"
MUTED     = "#8a94a3"
FONT      = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial"

# Sukhumvit Line BTS stations, for orientation (name, lat, lon).
_BTS = [("Asok", 13.7370, 100.5604), ("Phrom Phong", 13.7304, 100.5697),
        ("Thong Lo", 13.7242, 100.5786), ("Ekkamai", 13.7196, 100.5852)]


# --------------------------------------------------------------------------
# Basemap + Web-Mercator projection (identical math to sleepviz._lonlat_to_px,
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
    return px, H - py_top          # flip to bottom-origin for Plotly


def _base_figure(uri, W, H, attribution, height):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.update_layout(
        images=[dict(source=uri, xref="x", yref="y", x=0, y=0, sizex=W, sizey=H,
                     xanchor="left", yanchor="bottom", sizing="stretch", layer="below")],
        xaxis=dict(range=[0, W], visible=False, constrain="domain"),
        yaxis=dict(range=[0, H], visible=False, scaleanchor="x", scaleratio=1),
        paper_bgcolor=BG, plot_bgcolor=BG, height=height,
        margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        font=dict(family=FONT, color=TEXT), dragmode="pan", hovermode="closest",
    )
    fig.add_annotation(x=0.004, y=0.012, xref="paper", yref="paper", text=attribution,
                       showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(size=9, color=MUTED))
    return fig


def _bts_traces(ext, W, H):
    import plotly.graph_objects as go
    xs, ys, names = [], [], []
    for name, blat, blon in _BTS:
        bx, by = _project(blon, blat, ext, W, H)
        xs.append(float(np.ravel(bx)[0])); ys.append(float(np.ravel(by)[0])); names.append(name)
    marker = go.Scatter(x=xs, y=ys, mode="markers+text", text=names,
                        textposition="top right", textfont=dict(color=BTS_TXT, size=10),
                        marker=dict(size=8, color="rgba(0,0,0,0)",
                                    line=dict(color=BTS, width=1.4)),
                        hoverinfo="skip", name="BTS")
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
.qb-card {{ background: radial-gradient(120% 100% at 0% 0%, {CARD_TOP} 0%, {BG} 60%);
  border:1px solid #1b2431; border-radius:16px; padding:18px 20px 12px;
  font-family:{FONT}; color:{TEXT}; max-width:960px;
  box-shadow:0 10px 44px rgba(0,0,0,.5); }}
.qb-card .qb-h {{ font-size:19px; font-weight:650; letter-spacing:.2px; margin:2px 0 4px;
  display:flex; align-items:center; gap:9px; }}
.qb-card .qb-h::before {{ content:''; width:9px; height:9px; border-radius:50%;
  background:{ACCENT}; box-shadow:0 0 12px {ACCENT}; }}
.qb-card .qb-sub {{ color:{MUTED}; font-size:12.5px; margin:0 0 12px 18px; }}
.qb-card .qb-cap {{ color:#aeb8c6; font-size:13.5px; line-height:1.5; margin:12px 2px 4px;
  border-left:2px solid {ACCENT}; padding-left:11px; min-height:22px; }}
.qb-card .widget-toggle-buttons .widget-toggle-button,
.qb-card .widget-toggle-buttons button, .qb-card button.jupyter-button {{
  background:#131a23 !important; color:#c2ccd9 !important; border:1px solid #223046 !important;
  border-radius:10px !important; font-family:{FONT} !important; font-weight:550 !important;
  margin-right:7px !important; padding:6px 14px !important; box-shadow:none !important;
  transition:all .18s ease !important; }}
.qb-card .widget-toggle-buttons button:hover, .qb-card button.jupyter-button:hover {{
  border-color:{ACCENT} !important; color:{TEXT} !important; }}
.qb-card .widget-toggle-buttons button.mod-active, .qb-card button.mod-active {{
  background:linear-gradient(180deg,{ACCENT},#7d49e0) !important; color:#fff !important;
  border-color:{ACCENT} !important; box-shadow:0 0 16px rgba(160,107,255,.45) !important; }}
"""


def _shell(title, subtitle, controls, fig, caption):
    import ipywidgets as W
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

    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=EDGE, width=1),
                             hoverinfo="skip", opacity=0.0, name="coverage"))
    fig.add_trace(go.Scatter(x=px, y=py, mode="markers", hoverinfo="skip", name="glow",
                             marker=dict(size=24, color=ASLEEP, opacity=0.0)))
    fig.add_trace(go.Scatter(
        x=px, y=py, mode="markers", name="towers",
        marker=dict(size=9, color=TOWER, opacity=0.0, line=dict(color="white", width=0.6)),
        customdata=list(range(len(lon))),
        hovertemplate="site %{customdata}<br>%{text}<extra></extra>",
        text=[f"{a:.4f}, {b:.4f}" for a, b in zip(lat, lon)]))
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
    glow_op  = 0.20 if state >= 2 else 0.0
    core_op  = 1.0 if state >= 1 else 0.0
    core_sz  = 12 if state >= 2 else 9
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
        f"<b>{n} real cell-tower sites</b> from OpenCelliD (LTE / UMTS only — GSM stays awake as "
        "the 2G floor). These are crowdsourced estimated positions.",
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
    return _shell("From district to atoms",
                  "How Sukhumvit becomes a problem QuEra Aquila can solve.",
                  toggle, fig, cap)


# --------------------------------------------------------------------------
# WIDGET 2 — result reveal:  all towers lit  ->  MIS asleep, awake highlighted
# --------------------------------------------------------------------------
def build_sleep_traces(fig, inst, asleep, ext, W, H):
    """Traces: [0]=edges [1]=awake-halo [2]=awake-core [3]=asleep-core [4]=BTS."""
    import plotly.graph_objects as go
    lon = inst["coords_lonlat"][:, 0]
    lat = inst["coords_lonlat"][:, 1]
    px, py = _project(lon, lat, ext, W, H)
    edges = list(inst["graph"].edges())
    ex, ey = _edge_xy(px, py, edges)
    asleep = set(int(i) for i in asleep)
    awake = [i for i in range(len(lon)) if i not in asleep]
    aslp = sorted(asleep)

    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=EDGE, width=1),
                             hoverinfo="skip", opacity=0.35, name="coverage"))
    fig.add_trace(go.Scatter(x=px[awake], y=py[awake], mode="markers", name="awake-halo",
                             marker=dict(size=30, color=AWAKE, opacity=0.0), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=px[awake], y=py[awake], mode="markers", name="awake",
                             marker=dict(size=10, color=TOWER, opacity=1.0,
                                         line=dict(color="white", width=0.6)),
                             hovertemplate="AWAKE — keeps covering<extra></extra>"))
    fig.add_trace(go.Scatter(x=px[aslp], y=py[aslp], mode="markers", name="asleep",
                             marker=dict(size=10, color=TOWER, opacity=1.0,
                                         line=dict(color="white", width=0.6)),
                             hovertemplate="ASLEEP — safe to switch off<extra></extra>"))
    fig.add_trace(_bts_traces(ext, W, H))
    return len(awake), len(aslp)


def _sleep_apply(fig, state, animate=True):
    """State 0 = all lit; State 1 = 3 a.m.: asleep powered down, awake highlighted."""
    with _apply_ctx(fig, animate):
        if state == 0:
            fig.data[1].marker.opacity = 0.0
            fig.data[2].marker.color = TOWER; fig.data[2].marker.size = 10
            fig.data[3].marker.color = TOWER; fig.data[3].marker.size = 10
            fig.data[3].marker.opacity = 1.0
        else:
            fig.data[1].marker.opacity = 0.16          # coverage halo on the awake ones
            fig.data[2].marker.color = AWAKE; fig.data[2].marker.size = 13
            fig.data[3].marker.color = AWAKE_DIM; fig.data[3].marker.size = 6
            fig.data[3].marker.opacity = 0.30          # powered down


def sleep_view(inst, asleep, basemap_png, basemap_json, height=560):
    import plotly.graph_objects as go
    import ipywidgets as W
    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.FigureWidget(_base_figure(uri, Wpx, Hpx, attr, height))
    n_awake, n_asleep = build_sleep_traces(fig, inst, asleep, ext, Wpx, Hpx)
    total = n_awake + n_asleep

    opts = [("🌆  All towers lit", 0), ("🌙  3 a.m. — sleep set", 1)]
    caps = [
        f"<b>{total} cell towers, all drawing power.</b> Every site is on — as the network runs "
        "today, all night, even when almost nobody is connected.",
        f"<b>{n_asleep} of {total} towers switch off</b> (dimmed) — the QuEra Aquila sleep set. "
        f"The <span style='color:{AWAKE}'>{n_awake} awake towers</span> (glowing) still cover the "
        "whole district: <b>no two sleeping cells are neighbours — coverage verified.</b>",
    ]
    toggle = W.ToggleButtons(options=opts, value=0)
    toggle.add_class("widget-toggle-buttons")
    cap = W.HTML(_cap(caps[0]))

    def _on(change):
        _sleep_apply(fig, change["new"])
        cap.value = _cap(caps[change["new"]])
    toggle.observe(_on, names="value")
    _sleep_apply(fig, 0, animate=False)
    return _shell("Which cells can sleep tonight",
                  f"Measured on QuEra Aquila — a provably valid sleep set of {n_asleep} of {total}.",
                  toggle, fig, cap)


# --------------------------------------------------------------------------
# Static export (for headless verification): plain go.Figure at a given state
# --------------------------------------------------------------------------
def _static_pipeline(inst, basemap_png, basemap_json, state, height=560):
    import plotly.graph_objects as go
    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.Figure(_base_figure(uri, Wpx, Hpx, attr, height))
    build_pipeline_traces(fig, inst, ext, Wpx, Hpx)
    _pipeline_apply(fig, state, animate=False)
    return fig


def _static_sleep(inst, asleep, basemap_png, basemap_json, state, height=560):
    import plotly.graph_objects as go
    uri, Wpx, Hpx, ext, attr = _basemap(basemap_png, basemap_json)
    fig = go.Figure(_base_figure(uri, Wpx, Hpx, attr, height))
    build_sleep_traces(fig, inst, asleep, ext, Wpx, Hpx)
    _sleep_apply(fig, state, animate=False)
    return fig
