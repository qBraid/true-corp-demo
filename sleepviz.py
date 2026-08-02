"""
sleepviz.py — presentation figures for "Which cells can sleep tonight?"

All matplotlib lives here so the notebook cells stay thin: build data with
`sleepcells`, then hand it to one high-level figure function. Two layers:

  low-level   draw onto a caller-supplied Axes   (plot_sites, plot_register,
              shot_histogram, wallclock)          — composable, return the Axes
  high-level  build a whole Figure and show it    (district_and_graph, three_panel,
                                                    payoff_map, scoreboard)

High-level builders build the Figure and call plt.show() once (they return None),
so a notebook cell displays exactly one figure whether or not it also prints text.
Scripts that need a Figure object compose the low-level helpers onto their own Axes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np

import sleepcells as sc


# ---------------------------------------------------------------------------
# House style — True red on white
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Style:
    true_red: str = "#e4002b"      # asleep / brand accent
    ink: str = "#1a1a1a"           # text, classical optimum
    awake: str = "#c9ccd1"         # awake sites
    edge: str = "#e6a9b4"          # coverage edges
    quantum: str = "#00843d"       # quantum best / future target
    classical: str = "#1a4fd6"     # classical curve
    field_box: str = "#bbbbbb"
    note: str = "#8a8f96"


STYLE = Style()


def apply_style() -> None:
    """Set the notebook-wide matplotlib defaults. Call once in setup."""
    plt.rcParams.update({
        "figure.dpi": 110, "font.size": 11, "axes.edgecolor": "#cccccc",
        "axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "axes.facecolor": "white",
    })


def _geo_aspect(lat) -> float:
    """Latitude-correct aspect so a map is not stretched east-west."""
    return 1.0 / math.cos(math.radians(float(np.mean(lat))))


# ---------------------------------------------------------------------------
# Low-level: draw onto a given Axes
# ---------------------------------------------------------------------------
def _draw_edges(ax, xs, ys, edges):
    for i, j in edges:
        ax.plot([xs[i], xs[j]], [ys[i], ys[j]], "-", color=STYLE.edge,
                lw=0.6, alpha=0.5, zorder=1)


def _draw_nodes(ax, xs, ys, selected, s):
    sel = set(selected or [])
    awake = [k for k in range(len(xs)) if k not in sel]
    ax.scatter([xs[k] for k in awake], [ys[k] for k in awake], s=s, c=STYLE.awake,
               edgecolors="white", linewidths=0.5, zorder=2, label="awake")
    if sel:
        ax.scatter([xs[k] for k in sel], [ys[k] for k in sel], s=s + 18, c=STYLE.true_red,
                   edgecolors="white", linewidths=0.6, zorder=3, label="asleep")


def plot_sites(ax, lon, lat, selected=None, edges=None, show_edges=True,
               title="", s=42, legend=True):
    """Scatter sites on a lon/lat map; `selected` (asleep) in red, edges faint."""
    lon = np.asarray(lon, float); lat = np.asarray(lat, float)
    if edges and show_edges:
        _draw_edges(ax, lon, lat, edges)
    _draw_nodes(ax, lon, lat, selected, s)
    ax.set_title(title, fontsize=12, color=STYLE.ink, loc="left")
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_aspect(_geo_aspect(lat))
    if legend and selected:
        ax.legend(loc="upper right", frameon=False, fontsize=9)
    return ax


def plot_register(ax, coords_um, edges=None, selected=None, title="", s=45,
                  show_field=False):
    """Scatter the atom register in micrometres; optionally show the field box."""
    x, y = np.asarray(coords_um)[:, 0], np.asarray(coords_um)[:, 1]
    if edges:
        _draw_edges(ax, x, y, edges)
    _draw_nodes(ax, x, y, selected, s)
    if show_field:                                    # full field box (atoms fill it)
        import matplotlib.patches as mpatches
        ax.set_xlim(-4, sc.FIELD_UM + 4); ax.set_ylim(-4, sc.FIELD_UM + 4)
        ax.add_patch(mpatches.Rectangle((0, 0), sc.FIELD_UM, sc.FIELD_UM, fill=False,
                     ec=STYLE.field_box, ls="--", lw=1.0))
    else:                                             # auto-scale so atoms fill the panel
        pad = 0.12 * max(np.ptp(x), np.ptp(y)) + 1.5
        ax.set_xlim(x.min() - pad, x.max() + pad); ax.set_ylim(y.min() - pad, y.max() + pad)
        ax.text(0.02, 0.98, f"atoms span {max(np.ptp(x), np.ptp(y)):.0f} µm "
                f"of the {sc.FIELD_UM:.0f} µm field", transform=ax.transAxes,
                va="top", fontsize=8.5, color=STYLE.note)
    ax.set_title(title, fontsize=12, color=STYLE.ink, loc="left")
    ax.set_xlabel("x (µm)"); ax.set_ylabel("y (µm)"); ax.set_aspect("equal")
    return ax


def shot_histogram(ax, sizes, optimum, best, title=""):
    """Independent-set size distribution across shots, optimum & best marked."""
    sizes = list(sizes)
    ax.hist(sizes, bins=range(min(sizes), max(sizes) + 2), color=STYLE.true_red,
            alpha=0.85, edgecolor="white")
    ax.axvline(optimum, color=STYLE.ink, ls="--", lw=1.6, label=f"classical optimum = {optimum}")
    ax.axvline(best, color=STYLE.quantum, ls="-", lw=1.6, label=f"quantum best = {best}")
    ax.set_xlabel("independent-set size |S| per shot"); ax.set_ylabel("shots")
    ax.set_title(title, fontsize=12, color=STYLE.ink, loc="left")
    ax.legend(frameon=False, fontsize=9)
    return ax


def wallclock(ax, scale_pts, aquila_today_s, future_s, title=""):
    """Classical exact-solve time (grows) vs Aquila's flat, shot-rate-limited line."""
    ks = [p[0] for p in scale_pts]; ts = [p[1] for p in scale_pts]
    ax.semilogy(ks, ts, "o-", color=STYLE.classical, lw=2, label="classical exact (per instance)")
    ax.axhline(aquila_today_s, color=STYLE.true_red, lw=2,
               label=f"Aquila today ≈ {aquila_today_s:.0f} s  (1000 shots ÷ shot rate)")
    ax.axhline(future_s, color=STYLE.quantum, lw=2, ls="--", label="1000 atoms @ 1 kHz (target)")
    ax.set_ylim(1e-3, 1e3)
    ax.set_xlabel("sites"); ax.set_ylabel("wall-clock per instance (s, log)")
    ax.set_title(title, fontsize=12, color=STYLE.ink, loc="left")
    ax.legend(frameon=True, framealpha=0.9, edgecolor="none", fontsize=8.3, loc="lower right")
    return ax


# ---------------------------------------------------------------------------
# High-level: build a whole Figure from sleepcells objects
# ---------------------------------------------------------------------------
def district_and_graph(atoms: "sc.Sites", sub: "sc.Sites", edges):
    """Two-panel WHAT figure: the whole district, and the densest coverage graph."""
    fig, ax = plt.subplots(1, 2, figsize=(14, 6.2))
    plot_sites(ax[0], atoms.lon, atoms.lat, show_edges=False,
               title=f"Watthana sites  ·  {atoms.n} atoms after merge")
    plot_sites(ax[1], sub.lon, sub.lat, edges=edges,
               title=f"Coverage graph  ·  densest {sub.n}, {len(edges)} edges, "
                     f"avg degree {2*len(edges)/sub.n:.1f}")
    fig.tight_layout()
    plt.show()          # display once; low-level helpers stay composable


def three_panel(inst: dict, reg: "sc.Register", G):
    """Three-panel HOW figure: same shape as sites, as a graph, and as atoms."""
    lon = inst["coords_lonlat"][:, 0]; lat = inst["coords_lonlat"][:, 1]
    edges = list(G.edges())
    fig, ax = plt.subplots(1, 3, figsize=(16, 5.4))
    plot_sites(ax[0], lon, lat, show_edges=False, legend=False, title="Sukhumvit sites")
    plot_sites(ax[1], lon, lat, edges=edges, legend=False, title="Coverage graph")
    plot_register(ax[2], reg.coords_um, edges=edges,
                  title=f"Atom register  ·  1 µm = {sc.SCALE_M_PER_UM:.0f} m")
    fig.tight_layout()
    plt.show()          # display once; low-level helpers stay composable


def payoff_map(inst: dict, selected, title=None):
    """The money shot: the district with the measured sleeping cells highlighted."""
    lon = inst["coords_lonlat"][:, 0]; lat = inst["coords_lonlat"][:, 1]
    edges = list(inst["graph"].edges())
    if title is None:
        title = (f"Which cells can sleep tonight — {len(selected)} of {inst['n_atoms']} "
                 f"asleep, coverage verified")
    fig, ax = plt.subplots(figsize=(7.4, 6.6))
    plot_sites(ax, lon, lat, selected=selected, edges=edges, title=title, s=48)
    fig.tight_layout()
    plt.show()          # display once; low-level helpers stay composable


def scoreboard(sizes, optimum, best, scale_pts, aquila_today_s, future_s, retained=None):
    """Two-panel RESULT-2 figure: shot histogram + honest wall-clock comparison."""
    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    tag = f" ({retained} retained)" if retained is not None else ""
    shot_histogram(ax[0], sizes, optimum, best, title=f"Aquila 150-atom shot distribution{tag}")
    wallclock(ax[1], scale_pts, aquila_today_s, future_s,
              title="Classical wins today — Aquila's flat line sits ABOVE it")
    fig.tight_layout()
    plt.show()          # display once; low-level helpers stay composable
