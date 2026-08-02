"""
sleepcells.py — core pipeline for "Which cells can sleep tonight?"

Maps a real cellular-network coverage problem (which sites can be put to sleep at
3 a.m. without opening a coverage hole) onto Maximum Independent Set (MIS) on a
unit-disk graph, and from there onto QuEra's Aquila neutral-atom processor via an
Analog Hamiltonian Simulation (AHS) sweep.

This module is the single source of truth for the demo. The companion notebook
`which_cells_can_sleep.ipynb` embeds the same functions inline so it is fully
self-contained; the offline scripts in scripts/ import from here.

Honesty note baked into the code: the MIS formulation is a *conservative*
relaxation of the true "minimum dominating set" energy-optimum. Independent set
guarantees a valid coverage certificate (no two sleeping cells are neighbours, so
every sleeping cell's area stays covered by an awake neighbour) but may leave
savings unclaimed. See `verify_independent_set` and the module docstrings.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Sequence

import networkx as nx
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. SCALE MAPPING  — Sukhumvit onto the chip
#    Derived by fixing the Rydberg blockade radius to the coverage-overlap
#    threshold. Nothing here is tuned to flatter the hardware: 8.4 um is simply
#    where rubidium's blockade sits at full Rabi drive.
# ---------------------------------------------------------------------------

# Top-of-notebook knob. If a district does not fit the field of view, change this.
COVERAGE_OVERLAP_M = 500.0          # two sites "mutually cover" within this many metres

BLOCKADE_RADIUS_UM = 8.4            # R_b = (C6 / Omega)^(1/6) at Omega_max
SCALE_M_PER_UM = COVERAGE_OVERLAP_M / BLOCKADE_RADIUS_UM      # ~= 59.5 m per um

MIN_SEPARATION_UM = 4.0             # Aquila hard floor on atom separation
MERGE_THRESHOLD_M = MIN_SEPARATION_UM * SCALE_M_PER_UM        # ~= 238 m
FIELD_UM = 75.0                     # Aquila field of view (short side); verify live
FIELD_M = FIELD_UM * SCALE_M_PER_UM                          # ~= 4.5 km

# ---------------------------------------------------------------------------
# 2. DEVICE FACTS  — QuEra Aquila (verified against AWS Braket / QuEra specs).
#    Live-queryable via qBraid read-only: numberQubits=256, shots (1,1000),
#    pricing 30 credits/task + 1 credit/shot. The physics constants below are
#    NOT exposed through qBraid read-only and are taken from published specs.
# ---------------------------------------------------------------------------

AQUILA_DEVICE_ID = "aws:quera:qpu:aquila"     # confirmed live on qBraid (NOT "quera_aquila")
AQUILA_MAX_ATOMS = 256
AQUILA_SHOTS_MAX = 1000                        # hard per-task ceiling (minShots=1)

OMEGA_MAX = 1.57e7          # rad/s  (~2.5 MHz); must start and end at 0 rad/s
DELTA_START = -2 * math.pi * 5e6    # rad/s  (negative -> trivial all-down ground state)
DELTA_END = +2 * math.pi * 5e6      # rad/s  (positive -> MIS is the ground state)
T_TOTAL = 4.0e-6           # s  (4 us, coherence-limited hard ceiling)
T_RAMP = 0.3e-6            # s  (Omega ramp up / down)


# ===========================================================================
# 3. DATA PIPELINE  — OpenCelliD-style cells -> physical sites -> mergeable atoms
# ===========================================================================

# True Corporation (post-dtac-merger) mobile network codes under Thailand MCC 520.
# Verified separately; competitors (AIS 520-01/03, NT) are excluded.
THAILAND_MCC = 520
# TrueMove H + merged dtac families under the post-2023-merger True Corporation.
# 04/99 = TrueMove H (Real Future), 05/18 = dtac (DTAC Network / TAC), 00 = CAT-hosted
# TrueMove H, 25 = True Corp legacy. Competitors excluded: AIS = {01,03,23}, NT = {02,15,47}.
TRUE_GROUP_MNCS = (0, 4, 5, 18, 25, 99)


def load_cells(csv_path: str) -> pd.DataFrame:
    """Load an OpenCelliD-schema CSV.

    Expected columns (OpenCelliD export order):
        radio, mcc, net, area, cell, unit, lon, lat, range, samples,
        changeable, created, updated, averageSignal
    lon/lat are WGS84 degrees; range is metres; created/updated are unix seconds.
    """
    df = pd.read_csv(csv_path)
    required = {"radio", "mcc", "net", "lon", "lat"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required OpenCelliD columns: {sorted(missing)}")
    return df


def filter_cells(
    df: pd.DataFrame,
    mcc: int = THAILAND_MCC,
    mncs: Iterable[int] = TRUE_GROUP_MNCS,
    bbox: tuple[float, float, float, float] | None = None,
) -> pd.DataFrame:
    """Filter to one operator group inside a lat/lon bounding box.

    bbox = (min_lat, max_lat, min_lon, max_lon).
    """
    m = df["mcc"] == mcc
    m &= df["net"].isin(list(mncs))
    if bbox is not None:
        min_lat, max_lat, min_lon, max_lon = bbox
        m &= df["lat"].between(min_lat, max_lat)
        m &= df["lon"].between(min_lon, max_lon)
    return df.loc[m].reset_index(drop=True)


# --- local planar coordinates (equirectangular; fine for a ~5 km district) ---

_M_PER_DEG_LAT = 110_540.0


def latlon_to_local_m(lat, lon, ref_lat: float, ref_lon: float):
    """Equirectangular projection to local ENU metres about (ref_lat, ref_lon)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    m_per_deg_lon = _M_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    x = (lon - ref_lon) * m_per_deg_lon
    y = (lat - ref_lat) * _M_PER_DEG_LAT
    return np.column_stack([x, y])


@dataclass
class Sites:
    """A set of physical cell sites in local metres, with provenance counts."""
    xy_m: np.ndarray                 # (n, 2) local metres
    lat: np.ndarray                  # (n,) original degrees (for map plots)
    lon: np.ndarray
    n_cells: int                     # cells that fed into these sites
    cell_counts: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def n(self) -> int:
        return len(self.xy_m)


def _greedy_cluster(xy: np.ndarray, radius_m: float) -> list[list[int]]:
    """Single-linkage-ish greedy clustering: assign each point to an existing
    cluster whose seed is within radius_m, else start a new cluster. Order-stable.
    """
    clusters: list[list[int]] = []
    seeds: list[np.ndarray] = []
    for i, p in enumerate(xy):
        placed = False
        for c, s in enumerate(seeds):
            if math.hypot(p[0] - s[0], p[1] - s[1]) <= radius_m:
                clusters[c].append(i)
                # keep seed as running centroid for stability
                seeds[c] = xy[clusters[c]].mean(axis=0)
                placed = True
                break
        if not placed:
            clusters.append([i])
            seeds.append(p.copy())
    return clusters


def cluster_cells_to_sites(
    df: pd.DataFrame, ref_lat: float, ref_lon: float, radius_m: float = 50.0
) -> Sites:
    """Cluster many cells (sector x band) that share one physical mast into sites.

    Returns Sites with n_cells recorded so the notebook can print 'cells -> sites'.
    """
    xy = latlon_to_local_m(df["lat"].values, df["lon"].values, ref_lat, ref_lon)
    clusters = _greedy_cluster(xy, radius_m)
    centroids = np.array([xy[c].mean(axis=0) for c in clusters])
    lat_c = np.array([df["lat"].values[c].mean() for c in clusters])
    lon_c = np.array([df["lon"].values[c].mean() for c in clusters])
    counts = np.array([len(c) for c in clusters])
    return Sites(xy_m=centroids, lat=lat_c, lon=lon_c, n_cells=len(df), cell_counts=counts)


def merge_close_sites(sites: Sites, threshold_m: float = MERGE_THRESHOLD_M) -> Sites:
    """Merge sites closer than threshold_m (the 4 um atom-separation floor in metres).

    Required by hardware: two atoms cannot sit closer than ~4 um, so after
    scaling every pair of atoms must be >= 4 um apart. A greedy single-linkage
    pass does NOT guarantee that (two clusters' centroids can still land inside
    the floor), so we merge agglomeratively: repeatedly fuse the closest pair
    (count-weighted centroid) until the minimum pairwise distance clears the
    threshold. The postcondition — min pairwise distance >= threshold_m — is what
    makes the downstream `assert_valid_register` pass. Reports the reduced count
    so the notebook can print 'sites -> atoms'.
    """
    from scipy.spatial.distance import pdist, squareform

    xy = sites.xy_m.astype(float).copy()
    lat = sites.lat.astype(float).copy()
    lon = sites.lon.astype(float).copy()
    w = sites.cell_counts.astype(float).copy()
    if len(w) == 0:
        w = np.ones(len(xy))

    while len(xy) > 1:
        D = squareform(pdist(xy))
        np.fill_diagonal(D, np.inf)
        i, j = np.unravel_index(np.argmin(D), D.shape)
        if D[i, j] >= threshold_m:
            break
        wi, wj = w[i], w[j]
        new_xy = (xy[i] * wi + xy[j] * wj) / (wi + wj)
        new_lat = (lat[i] * wi + lat[j] * wj) / (wi + wj)
        new_lon = (lon[i] * wi + lon[j] * wj) / (wi + wj)
        keep = [k for k in range(len(xy)) if k not in (i, j)]
        xy = np.vstack([xy[keep], new_xy])
        lat = np.append(lat[keep], new_lat)
        lon = np.append(lon[keep], new_lon)
        w = np.append(w[keep], wi + wj)

    return Sites(xy_m=xy, lat=lat, lon=lon, n_cells=sites.n_cells,
                 cell_counts=w.astype(int))


def select_densest(sites: Sites, k: int, overlap_m: float = COVERAGE_OVERLAP_M) -> Sites:
    """Take the k-site densest CONTIGUOUS sub-district (not a random sample).

    Seed = site with the most neighbours within overlap_m; grow by taking the k
    nearest sites to that seed, which keeps the selection spatially contiguous.
    """
    if k >= sites.n:
        return sites
    xy = sites.xy_m
    # local degree = number of neighbours within one coverage-overlap radius
    deg = np.zeros(sites.n, dtype=int)
    for i in range(sites.n):
        d = np.hypot(xy[:, 0] - xy[i, 0], xy[:, 1] - xy[i, 1])
        deg[i] = int(np.sum(d <= overlap_m)) - 1
    # Seed from the CENTROID of the densest quartile (robust and central) rather
    # than a single max-degree node, which can sit on an edge and drag the
    # k-nearest selection off to one side, inflating the bounding box.
    thresh = np.quantile(deg, 0.75)
    core_mask = deg >= thresh
    seed_xy = xy[core_mask].mean(axis=0)
    d_seed = np.hypot(xy[:, 0] - seed_xy[0], xy[:, 1] - seed_xy[1])
    idx = np.sort(np.argsort(d_seed)[:k])
    return Sites(xy_m=xy[idx], lat=sites.lat[idx], lon=sites.lon[idx],
                 n_cells=sites.n_cells, cell_counts=sites.cell_counts[idx])


def build_graph(sites: Sites, overlap_m: float = COVERAGE_OVERLAP_M) -> nx.Graph:
    """Unit-disk coverage graph: an edge between two sites within overlap_m.

    An edge means 'these two mutually cover': if both slept, the overlap region
    could open a hole, so at most one of an edge's endpoints may sleep. That is
    exactly the independent-set constraint.
    """
    xy = sites.xy_m
    G = nx.Graph()
    G.add_nodes_from(range(sites.n))
    n = sites.n
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(xy[i, 0] - xy[j, 0], xy[i, 1] - xy[j, 1]) <= overlap_m:
                G.add_edge(i, j)
    return G


def _min_bbox_rotation(xy: np.ndarray) -> float:
    """Angle (rad) that minimises the LARGER side of the axis-aligned bbox.

    We minimise max(width, height) rather than area, because Aquila's field of
    view is the binding square-ish constraint. Scans 0..90 deg by convex-hull
    edge directions plus a fine grid — cheap and robust for tens of points.
    """
    pts = xy - xy.mean(axis=0)
    best_angle, best_span = 0.0, math.inf
    angles = np.linspace(0, math.pi / 2, 181)
    try:
        hull = _convex_hull(pts)
        edges = np.diff(np.vstack([hull, hull[:1]]), axis=0)
        edge_angles = np.arctan2(edges[:, 1], edges[:, 0]) % (math.pi / 2)
        angles = np.unique(np.concatenate([angles, edge_angles]))
    except Exception:
        pass
    for a in angles:
        c, s = math.cos(a), math.sin(a)
        R = np.array([[c, -s], [s, c]])
        r = pts @ R.T
        span = max(np.ptp(r[:, 0]), np.ptp(r[:, 1]))
        if span < best_span:
            best_span, best_angle = span, a
    return best_angle


def _convex_hull(points: np.ndarray) -> np.ndarray:
    """Andrew's monotone chain convex hull (ccw)."""
    pts = sorted(map(tuple, points))
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


@dataclass
class Register:
    """Atom register: positions in micrometres and in metres (Aquila schema)."""
    coords_um: np.ndarray            # (n, 2) micrometres, origin at min-corner
    scale_m_per_um: float
    rotation_rad: float

    @property
    def coords_m(self) -> np.ndarray:
        return self.coords_um * 1e-6

    @property
    def n(self) -> int:
        return len(self.coords_um)


def snap_to_aquila(coords_um: np.ndarray, row_min_um: float = MIN_SEPARATION_UM,
                   x_min_um: float = MIN_SEPARATION_UM, resolution_um: float = 0.1) -> np.ndarray:
    """Snap a register onto Aquila's ROW lattice — a hard hardware constraint.

    Aquila requires that for any two atoms the *y*-separation is either exactly 0
    (same row) or at least ~4 µm (distinct rows), and that every coordinate lies on
    a 0.1 µm grid. Continuous positions violate this and the QPU rejects the task
    (the local simulator does not, so it never catches it). We therefore:

      1. quantise y into rows spaced >= row_min_um apart (atoms within a row share y);
      2. within each row, push atoms apart so x-gaps are >= x_min_um;
      3. keep everything on the resolution grid (integer arithmetic, no float drift).

    Cross-row pairs are automatically >= row_min_um apart in Euclidean distance
    (their y differs by >= row_min_um), so the radial-minimum is satisfied too.
    All work is done in integer grid units to avoid rounding a valid separation
    back below the floor.
    """
    res = resolution_um
    R = int(round(row_min_um / res))
    X = int(round(x_min_um / res))
    xy = np.asarray(coords_um, dtype=float)
    ix = np.round(xy[:, 0] / res).astype(np.int64)
    iy = np.round(xy[:, 1] / res).astype(np.int64)
    n = len(ix)

    # 1. rows: walk atoms bottom-up; join the current row if within R, else open a new one
    rows: list[int] = []
    row_of = np.zeros(n, dtype=int)
    for idx in np.argsort(iy, kind="stable"):
        y = int(iy[idx])
        if not rows or y >= rows[-1] + R:
            rows.append(y)
        iy[idx] = rows[-1]
        row_of[idx] = len(rows) - 1

    # 2. within-row x spacing: sort by x, push right to keep gaps >= X
    for r in range(len(rows)):
        members = sorted(np.where(row_of == r)[0], key=lambda i: ix[i])
        last = None
        for i in members:
            if last is not None and ix[i] < last + X:
                ix[i] = last + X
            last = int(ix[i])

    return np.column_stack([ix * res, iy * res])


def affine_to_atoms(sites: Sites, scale_m_per_um: float = SCALE_M_PER_UM) -> Register:
    """Translate to origin, rotate to minimise the bounding box, scale to um, and
    snap onto Aquila's legal row lattice.

    The rotation fits the field of view; the snap makes the register physically
    submittable (rows >= 4 um apart, 0.1 um grid). Snapping perturbs positions by
    up to a few um, so the coverage graph must afterwards be built from the SNAPPED
    register (see `build_graph_from_register`) — that way the classical solver and
    the QPU solve exactly the same instance.
    """
    xy = sites.xy_m.astype(float)
    xy = xy - xy.mean(axis=0)
    ang = _min_bbox_rotation(xy)
    c, s = math.cos(ang), math.sin(ang)
    R = np.array([[c, -s], [s, c]])
    xy_rot = xy @ R.T
    xy_rot = xy_rot - xy_rot.min(axis=0)          # origin at min corner
    coords_um = xy_rot / scale_m_per_um
    coords_um = snap_to_aquila(coords_um)         # enforce Aquila row / spacing / resolution
    coords_um = coords_um - coords_um.min(axis=0)  # re-origin after snapping
    return Register(coords_um=coords_um, scale_m_per_um=scale_m_per_um, rotation_rad=ang)


def build_graph_from_register(reg: Register, overlap_m: float = COVERAGE_OVERLAP_M) -> nx.Graph:
    """Coverage graph from the ACTUAL atom register (what the QPU physically solves).

    Edge iff two atoms are within the blockade-equivalent of overlap_m: the network
    distance is the um distance times the scale, so the threshold in um is
    overlap_m / scale (= the blockade radius, ~8.4 um at 500 m).
    """
    thr_um = overlap_m / reg.scale_m_per_um
    xy = reg.coords_um
    n = len(xy)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(xy[i, 0] - xy[j, 0], xy[i, 1] - xy[j, 1]) <= thr_um:
                G.add_edge(i, j)
    return G


def assert_valid_register(
    reg: Register, min_sep_um: float = MIN_SEPARATION_UM, field_um: float = FIELD_UM,
    row_min_um: float = MIN_SEPARATION_UM, resolution_um: float = 0.1
) -> dict:
    """Fail loudly unless the register satisfies EVERY Aquila hardware constraint.

    Checks, in order (these are exactly what the QPU validates server-side):
      * radial: every pair of atoms is >= min_sep_um apart (Euclidean);
      * rows:   every pair's y-separation is 0 or >= row_min_um (the constraint a
                real job hit — the local simulator does not enforce it);
      * grid:   every coordinate lies on the resolution_um grid;
      * field:  the bounding box fits the field of view.
    Returns the measured quantities for printing.
    """
    xy = reg.coords_um
    n = len(xy)
    dmin = math.inf
    y_violation = None
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = xy[i, 0] - xy[j, 0], xy[i, 1] - xy[j, 1]
            dmin = min(dmin, math.hypot(dx, dy))
            ady = abs(dy)
            if 1e-6 < ady < row_min_um - 1e-6:            # y-sep neither 0 nor >= floor
                y_violation = y_violation or (i, j, ady)
    width, height = float(np.ptp(xy[:, 0])), float(np.ptp(xy[:, 1]))
    off_grid = float(np.max(np.abs(xy - np.round(xy / resolution_um) * resolution_um)))

    if dmin < min_sep_um - 1e-6:
        raise AssertionError(
            f"Min atom separation {dmin:.3f} um < {min_sep_um} um floor. "
            f"Increase MERGE_THRESHOLD_M or COVERAGE_OVERLAP_M."
        )
    if y_violation is not None:
        i, j, ady = y_violation
        raise AssertionError(
            f"Atoms {i},{j} have y-separation {ady:.3f} um — Aquila requires 0 or "
            f">= {row_min_um} um. The register must be snapped to rows (snap_to_aquila)."
        )
    if off_grid > 1e-6:
        raise AssertionError(
            f"Coordinates off the {resolution_um} um grid by {off_grid:.4f} um."
        )
    if not (width <= field_um + 1e-6 and height <= field_um + 1e-6):
        raise AssertionError(
            f"Register {width:.1f} x {height:.1f} um exceeds field {field_um} um. "
            f"Reduce COVERAGE_OVERLAP_M or pick a smaller sub-district."
        )
    n_rows = len(np.unique(np.round(xy[:, 1] / resolution_um).astype(int)))
    return {"min_sep_um": dmin, "width_um": width, "height_um": height,
            "n": n, "n_rows": n_rows}


# ===========================================================================
# 4. AHS PROGRAM  — the quasi-adiabatic MIS sweep
# ===========================================================================

def build_ahs_program(
    reg: Register,
    omega_max: float = OMEGA_MAX,
    delta_start: float = DELTA_START,
    delta_end: float = DELTA_END,
    t_total: float = T_TOTAL,
    t_ramp: float = T_RAMP,
    weights: Sequence[float] | None = None,
):
    """Build the Aquila AHS program for the MIS sweep.

    Omega(t): 0 -> omega_max over t_ramp, hold, -> 0 over t_ramp   (starts/ends at 0)
    Delta(t): delta_start (neg) -> delta_end (pos), monotonic
    phi(t):   0 throughout

    At large negative detuning the ground state is all-atoms-down (trivial). At
    large positive detuning the ground state of the Rydberg Hamiltonian IS the
    maximum independent set of the unit-disk graph. The sweep carries the system
    from one to the other; infeasible configurations are forbidden by the
    blockade, so there is no penalty term to tune.

    Coordinates are emitted in METRES (Decimal), per the Braket AHS schema —
    despite the docs describing micrometres. `weights` enables (optional) local
    detuning for weighted MIS; default None -> localDetuning=[]. Local detuning is
    an experimental Braket Direct capability and is OFF by default here.
    """
    from braket.ahs import (
        AnalogHamiltonianSimulation,
        AtomArrangement,
        DrivingField,
    )
    from braket.timings.time_series import TimeSeries

    register = AtomArrangement()
    for x_um, y_um in reg.coords_um:
        x_m = Decimal(str(round(float(x_um) * 1e-6, 9)))
        y_m = Decimal(str(round(float(y_um) * 1e-6, 9)))
        register.add([x_m, y_m])

    omega = TimeSeries()
    omega.put(0.0, 0.0)
    omega.put(t_ramp, omega_max)
    omega.put(t_total - t_ramp, omega_max)
    omega.put(t_total, 0.0)                       # must end at 0 rad/s

    detuning = TimeSeries()
    detuning.put(0.0, delta_start)
    detuning.put(t_total, delta_end)              # monotonic sweep

    phase = TimeSeries()
    phase.put(0.0, 0.0)
    phase.put(t_total, 0.0)

    drive = DrivingField(amplitude=omega, detuning=detuning, phase=phase)
    ahs = AnalogHamiltonianSimulation(register=register, hamiltonian=drive)

    if weights is not None:
        # Weighted-MIS path (default OFF): static per-site h_k pattern in [0,1],
        # only the overall magnitude is time-dependent. Left as a one-flag hook.
        from braket.ahs import LocalDetuning
        w = np.asarray(weights, dtype=float)
        w = w / (w.max() if w.max() > 0 else 1.0)
        mag = TimeSeries()
        mag.put(0.0, 0.0)
        mag.put(t_total, delta_end)
        local = LocalDetuning.from_lists(
            times=[0.0, t_total], values=[0.0, delta_end], pattern=list(w)
        )
        ahs = AnalogHamiltonianSimulation(
            register=register, hamiltonian=drive + local
        )
    return ahs


# ===========================================================================
# 5. RESULT DECODING  — the inverted bit semantics
# ===========================================================================

def rydberg_selected(pre_sequence: Sequence[int], post_sequence: Sequence[int]) -> list[int]:
    """Return the indices of atoms that are IN the independent set (cells that sleep).

    Aquila result bit semantics are INVERTED from intuition:
      pre_sequence[k]:  0 = trap empty,           1 = atom loaded
      post_sequence[k]: 0 = Rydberg OR site empty, 1 = ground state
    An atom is excited to Rydberg (i.e. selected into the independent set) iff it
    was loaded AND ended up NOT in the ground state:
        selected  <=>  pre[k] == 1 and post[k] == 0
    """
    return [k for k in range(len(pre_sequence))
            if pre_sequence[k] == 1 and post_sequence[k] == 0]


def is_fully_loaded(pre_sequence: Sequence[int]) -> bool:
    """True if every trap site loaded an atom this shot (for post-selection)."""
    return all(p == 1 for p in pre_sequence)


def decode_shots(measurements, n_atoms: int, policy: str = "postselect"):
    """Decode a list of AHS shot results into independent-set indicator arrays.

    policy = 'postselect' : keep only fully-loaded shots (recommended headline).
    policy = 'defect'     : keep all shots, treat empty sites as not-selected.

    Returns (selections, retained, total, defect_rate) where selections is a list
    of index-lists (one per retained shot).
    """
    total = len(measurements)
    selections = []
    empties = 0
    for m in measurements:
        pre = list(m.pre_sequence)
        post = list(m.post_sequence)
        empties += sum(1 for p in pre if p == 0)
        if policy == "postselect" and not is_fully_loaded(pre):
            continue
        selections.append(rydberg_selected(pre, post))
    retained = len(selections)
    defect_rate = empties / (total * n_atoms) if total and n_atoms else 0.0
    return selections, retained, total, defect_rate


# ===========================================================================
# 6. CLASSICAL BASELINES  — expected to WIN on these sizes
# ===========================================================================

def greedy_mis(G: nx.Graph) -> list[int]:
    """Min-degree-first greedy independent set."""
    H = G.copy()
    S: list[int] = []
    while H.number_of_nodes() > 0:
        v = min(H.nodes, key=lambda x: H.degree(x))
        S.append(v)
        H.remove_nodes_from(list(H.neighbors(v)) + [v])
    return sorted(S)


def randomized_greedy_mis(G: nx.Graph, restarts: int = 200, seed: int = 0) -> list[int]:
    """Best of many randomised min-degree-first greedy runs."""
    rng = np.random.default_rng(seed)
    best: list[int] = []
    for _ in range(restarts):
        H = G.copy()
        S: list[int] = []
        while H.number_of_nodes() > 0:
            degs = dict(H.degree())
            mind = min(degs.values())
            cands = [v for v, d in degs.items() if d == mind]
            v = int(rng.choice(cands))
            S.append(v)
            H.remove_nodes_from(list(H.neighbors(v)) + [v])
        if len(S) > len(best):
            best = sorted(S)
    return best


class _Timeout(Exception):
    pass


def exact_mis(G: nx.Graph, timeout_s: float = 20.0) -> tuple[list[int] | None, float, bool]:
    """Exact MIS via MAXIMUM clique on the complement graph.

    Uses `networkx.max_weight_clique` (branch-and-bound for the maximum clique)
    on the complement — MIS(G) == max-clique(complement(G)). This is the exact
    optimum, and it is what the honest scoreboard benchmarks against.

    Returns (best_set_or_None, wall_seconds, completed). Wrapped in a SIGALRM
    timeout (Unix; qBraid Lab is Linux). If it does not finish within timeout_s
    — which can happen for large, dense instances — returns (None, dt, False).
    A solver that cannot finish in the time budget is itself a reportable result.
    """
    import signal

    comp = nx.complement(G)
    t0 = time.perf_counter()
    completed = True
    best: list[int] | None = None

    have_alarm = hasattr(signal, "SIGALRM")
    old_handler = None
    if have_alarm and timeout_s and timeout_s > 0:
        def _handler(signum, frame):
            raise _Timeout()
        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        clique, _ = nx.max_weight_clique(comp, weight=None)
        best = sorted(clique)
    except _Timeout:
        completed = False
    finally:
        if have_alarm and timeout_s and timeout_s > 0:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
    dt = time.perf_counter() - t0
    return best, dt, completed


# ===========================================================================
# 7. COVERAGE CERTIFICATE + MONEY MODEL
# ===========================================================================

def verify_independent_set(G: nx.Graph, S: Iterable[int]) -> bool:
    """True iff S is a valid independent set (no two sleeping cells are neighbours).

    This is the coverage certificate: because no edge lies inside S, every
    sleeping cell has all its coverage-overlap neighbours awake.
    """
    S = set(S)
    for u, v in G.edges():
        if u in S and v in S:
            return False
    return True


# --- Money-model constants. True's OWN published numbers where possible; the
#     two physical levers (SITE_POWER_KW, LOW_TRAFFIC_HOURS) are flagged as
#     assumptions in the notebook's assumptions block. ---
TARIFF_THB_PER_KWH = 4.69      # implied by True's 2023 AI/ML saving: 42,000 MWh booked as THB 197M
GRID_TCO2E_PER_MWH = 0.45      # implied by True: 64,000 MWh -> 28,800 tCO2e avoided
SITE_POWER_KW = 4.0            # ASSUMPTION — biggest lever; True's network team can replace it
RADIO_SHARE = 0.60            # radio share of a site's draw; rest is cooling/baseband/transmission
DEEP_SLEEP_SAVING = 0.70      # Vodafone UK + Ericsson, London 2025 (deep sleep, low-traffic hours)
LOW_TRAFFIC_HOURS = 6.0       # ASSUMPTION — our modelling of the night window (not a 3GPP constant)
# "One Network" integrated base stations (True's own 17,000+ figure). True's total
# post-merger site count has been cited higher (~30,000); using 17,000 is the
# CONSERVATIVE choice — the larger number would roughly double every baht below.
NATIONAL_SITES = 17_000


def money_model(
    n_asleep: int,
    n_sites_district: int,
    site_power_kw: float = SITE_POWER_KW,
    radio_share: float = RADIO_SHARE,
    deep_sleep_saving: float = DEEP_SLEEP_SAVING,
    low_traffic_hours: float = LOW_TRAFFIC_HOURS,
    tariff: float = TARIFF_THB_PER_KWH,
    grid_factor: float = GRID_TCO2E_PER_MWH,
    national_sites: int = NATIONAL_SITES,
) -> dict:
    """Energy, baht and CO2 saved by sleeping n_asleep sites, plus national extrapolation.

    Energy saved per sleeping site per night (kWh):
        site_power_kw * radio_share * deep_sleep_saving * low_traffic_hours
    Only the RADIO share is put to sleep; cooling/baseband/transmission stay on.
    """
    kwh_per_site_night = site_power_kw * radio_share * deep_sleep_saving * low_traffic_hours
    district_kwh_night = kwh_per_site_night * n_asleep
    district_kwh_year = district_kwh_night * 365
    district_thb_year = district_kwh_year * tariff
    district_tco2e_year = district_kwh_year / 1000.0 * grid_factor

    extrapolation = national_sites / n_sites_district if n_sites_district else 0.0
    national_kwh_year = district_kwh_year * extrapolation
    national_thb_year = district_thb_year * extrapolation
    national_tco2e_year = district_tco2e_year * extrapolation
    return {
        "kwh_per_site_night": kwh_per_site_night,
        "district_kwh_year": district_kwh_year,
        "district_thb_year": district_thb_year,
        "district_tco2e_year": district_tco2e_year,
        "extrapolation_factor": extrapolation,
        "national_kwh_year": national_kwh_year,
        "national_thb_year": national_thb_year,
        "national_tco2e_year": national_tco2e_year,
    }


def sensitivity_table(
    n_sites_district: int,
    incremental_points=(0.10, 0.15, 0.25),
    **money_kwargs,
) -> pd.DataFrame:
    """National baht/year across incremental-sleep deltas vs per-cell rules.

    Each row: an extra X percentage points of sites put to sleep beyond what
    simple per-cell rules already achieve, and the resulting national THB/year.
    """
    rows = []
    for pts in incremental_points:
        extra_sites = pts * n_sites_district
        m = money_model(extra_sites, n_sites_district, **money_kwargs)
        rows.append({
            "incremental_sleep_points": f"+{int(pts*100)} pts",
            "extra_sites_district": round(extra_sites, 1),
            "national_THB_per_year": round(m["national_thb_year"], 0),
            "national_MWh_per_year": round(m["national_kwh_year"] / 1000.0, 0),
            "national_tCO2e_per_year": round(m["national_tco2e_year"], 0),
        })
    return pd.DataFrame(rows)


# ===========================================================================
# 8. PRICING (qBraid credits) — for the budget/scoreboard, matches live device
# ===========================================================================
CREDITS_PER_TASK = 30
CREDITS_PER_SHOT = 1


def task_credits(shots: int) -> int:
    """qBraid credit cost of one Aquila task at the given shot count."""
    return CREDITS_PER_TASK + CREDITS_PER_SHOT * shots


# ===========================================================================
# 9. INSTANCE + RESULT I/O  — so pre-runs replay without a QPU
# ===========================================================================

import json


def _json_default(o):
    """Coerce numpy scalar/array types so json.dump never chokes on them."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


class Shot:
    """A single AHS shot in the Aquila result schema (pre/post sequences).

    Mirrors braket's ShotResult so `decode_shots` works identically on both a
    live QPU/simulator result and a loaded-from-disk pre-run.
    """
    __slots__ = ("pre_sequence", "post_sequence", "status")

    def __init__(self, pre_sequence, post_sequence, status="Success"):
        self.pre_sequence = list(pre_sequence)
        self.post_sequence = list(post_sequence)
        self.status = status


def save_instance(path, name, sub: "Sites", reg: Register, G: nx.Graph,
                  classical: dict, provenance: dict) -> None:
    """Serialise an instance (atoms, graph, classical solutions) to JSON."""
    data = {
        "name": name,
        "n_atoms": reg.n,
        "provenance": provenance,
        "coords_um": reg.coords_um.tolist(),
        "coords_lonlat": np.column_stack([sub.lon, sub.lat]).tolist(),
        "xy_m_local": sub.xy_m.tolist(),
        "edges": [list(map(int, e)) for e in G.edges()],
        "scale_m_per_um": reg.scale_m_per_um,
        "rotation_rad": reg.rotation_rad,
        "coverage_overlap_m": COVERAGE_OVERLAP_M,
        "classical": classical,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=_json_default)


def load_instance(path) -> dict:
    """Load an instance JSON; rebuilds numpy arrays and the networkx graph."""
    with open(path) as f:
        d = json.load(f)
    d["coords_um"] = np.array(d["coords_um"], dtype=float)
    d["coords_lonlat"] = np.array(d["coords_lonlat"], dtype=float)
    d["xy_m_local"] = np.array(d["xy_m_local"], dtype=float)
    G = nx.Graph()
    G.add_nodes_from(range(d["n_atoms"]))
    G.add_edges_from([tuple(e) for e in d["edges"]])
    d["graph"] = G
    return d


def save_results(path, instance_name, n_atoms, source, tasks, note="") -> None:
    """Serialise pre-run shot results.

    source: one of
      'LOCAL_AHS_SIM'          — real Braket local Rydberg simulation (honest QPU stand-in)
      'SIMULATED_STANDIN'      — phenomenological stand-in (NOT a quantum sim; for sizes the
                                 local simulator cannot reach). Replace with QPU pre-run data.
      'QPU'                    — real Aquila measurement (written by the collection code)
    tasks: list of dicts {task_id, shots, measurements:[{pre:[...], post:[...]}, ...]}
    """
    data = {
        "instance": instance_name,
        "n_atoms": n_atoms,
        "device": AQUILA_DEVICE_ID,
        "source": source,
        "note": note,
        "tasks": tasks,
    }
    with open(path, "w") as f:
        json.dump(data, f, default=_json_default)


def load_results(path) -> dict:
    """Load pre-run results; returns dict with a flat `shots` list of Shot objects."""
    with open(path) as f:
        d = json.load(f)
    shots = []
    for t in d["tasks"]:
        for m in t["measurements"]:
            shots.append(Shot(m["pre"], m["post"]))
    d["shots"] = shots
    return d


def is_simulated(results: dict) -> bool:
    """True unless the results came from the real QPU. Drives the notebook banner."""
    return results.get("source") != "QPU"


def register_from_instance(inst: dict) -> Register:
    """Rebuild a Register from a loaded instance dict (for re-running the sweep)."""
    return Register(
        coords_um=np.asarray(inst["coords_um"], dtype=float),
        scale_m_per_um=inst["scale_m_per_um"],
        rotation_rad=inst["rotation_rad"],
    )


# ===========================================================================
# 10. REPORTING  — the printed blocks the demo shows (tied to the constants)
# ===========================================================================

def print_scale_table() -> None:
    """The scale table: Sukhumvit rendered on the chip (chip units vs network units)."""
    print(f"{'quantity':30s}{'chip':>12s}{'network':>16s}")
    print("-" * 58)
    print(f"{'blockade radius / overlap':30s}{BLOCKADE_RADIUS_UM:>10.1f} µm{COVERAGE_OVERLAP_M:>13.0f} m")
    print(f"{'min atom spacing / merge':30s}{MIN_SEPARATION_UM:>10.1f} µm{MERGE_THRESHOLD_M:>13.0f} m")
    print(f"{'field of view':30s}{FIELD_UM:>10.1f} µm{FIELD_M/1000:>11.2f} km")
    print(f"{'scale factor':30s}{'':>12s}{SCALE_M_PER_UM:>11.1f} m/µm")


def print_assumptions() -> None:
    """The consolidated assumptions block — every figure below rests on these."""
    print("=" * 74)
    print("ASSUMPTIONS  ·  'Which cells can sleep tonight?'")
    print("=" * 74)
    print("SCALE MAPPING (nothing tuned to flatter the hardware):")
    print(f"  coverage overlap        {COVERAGE_OVERLAP_M:6.0f} m   <-> blockade radius {BLOCKADE_RADIUS_UM} µm")
    print(f"  scale factor            {SCALE_M_PER_UM:6.1f} m per µm")
    print(f"  min site merge distance {MERGE_THRESHOLD_M:6.0f} m   <-> min atom spacing {MIN_SEPARATION_UM} µm")
    print(f"  field of view           {FIELD_M/1000:6.2f} km  <-> {FIELD_UM} µm (narrower than a human hair)")
    print("  → 4.5 km of Sukhumvit, rendered in an area narrower than a hair. We did NOT tune")
    print("    the blockade radius to match — that is where rubidium happens to sit.")
    print("-" * 74)
    print("ASSUMPTIONS (flagged where not a measured or published constant):")
    print(f"  [assumed] site power        {SITE_POWER_KW:4.1f} kW      — largest lever on the money model")
    print(f"            radio share       {RADIO_SHARE:4.0%}        — rest is cooling / baseband / transmission")
    print(f"            deep-sleep saving {DEEP_SLEEP_SAVING:4.0%}        — Vodafone UK + Ericsson, London 2025")
    print(f"  [assumed] low-traffic window {LOW_TRAFFIC_HOURS:4.1f} h     — night window (not a 3GPP constant)")
    print(f"            tariff            {TARIFF_THB_PER_KWH:4.2f} THB/kWh — implied by True (42,000 MWh = THB 197M, 2023)")
    print(f"            grid intensity    {GRID_TCO2E_PER_MWH:4.2f} tCO2e/MWh — implied by True (64,000 MWh -> 28,800 tCO2e)")
    print(f"            national sites    {NATIONAL_SITES:,}      — True 'One Network' integrated (conservative vs ~30,000)")
    print("-" * 74)
    print("HONESTY CONSTRAINTS:")
    print("  • MIS is a CONSERVATIVE relaxation of the true optimum (complement of a minimum")
    print("    dominating set). It guarantees feasibility but may leave savings unclaimed.")
    print("  • Coverage is modelled as UNIFORM-RADIUS disks. Real radii vary by band, tilt, class.")
    print("  • Positions are a REAL OpenCelliD extract (MCC 520, True-group MNCs) — crowdsourced")
    print("    estimated centroids, NOT surveyed tower locations (data © OpenCelliD, CC-BY-SA 4.0).")
    print("  • NO quantum advantage is claimed anywhere. On these sizes, classical wins.")
    print("=" * 74)


def print_merge_counts(sites: "Sites", atoms: "Sites", df=None) -> None:
    """The explicit site-merge counts: cells -> sites -> atoms, with the min spacing."""
    from scipy.spatial.distance import pdist
    print("SITE-MERGE COUNTS (printed explicitly):")
    print(f"  {sites.n_cells:>4} cells  ->  {sites.n:>4} sites  ->  {atoms.n:>4} atoms")
    if df is not None:
        radio_mix = {k: int(v) for k, v in df["radio"].value_counts().items()}
        print(f"  radio mix : {radio_mix}")
        print(f"  True MNCs : {sorted(int(x) for x in df['net'].unique())}   (MCC {THAILAND_MCC})")
    print(f"  after merge, closest two atoms are {pdist(atoms.xy_m).min():.0f} m apart "
          f"(floor {MERGE_THRESHOLD_M:.0f} m)")


def print_result_summary(best, n_atoms, G, exact_size, retained, total, defect) -> bool:
    """Headline read-out for a decoded result: |S|, coverage certificate, ratio.

    Returns whether the coverage certificate passed.
    """
    ok = verify_independent_set(G, best)
    print(f"Atom loading is probabilistic: post-selected {retained}/{total} fully-loaded shots "
          f"(defect rate {defect:.1%}).")
    print(f"Best sleep set over retained shots : |S| = {len(best)} of {n_atoms} "
          f"({len(best)/n_atoms:.0%} of the district asleep)")
    print(f"COVERAGE CERTIFICATE               : "
          f"{'COVERAGE VERIFIED — no two sleeping cells are neighbours' if ok else 'FAILED'}")
    print(f"Approximation ratio (best / exact {exact_size}) : {len(best)/exact_size:.2f}")
    return ok


def print_standin_banner(results: dict) -> None:
    """Loud banner making the results' provenance unmistakable (sim vs real QPU)."""
    if is_simulated(results):
        print("!" * 74)
        print(f"!!  RESULTS SOURCE: {results['source']}  —  simulator stand-in, NOT a QPU measurement")
        print("!" * 74)
    else:
        print(f"RESULTS SOURCE: {results['source']}  (Aquila QPU measurement)")


def print_money(best_size: int, n_sites_district: int) -> None:
    """The money model: per-site energy, this district, and the national sensitivity table."""
    m = money_model(best_size, n_sites_district)
    print("MONEY MODEL")
    print(f"  energy saved per sleeping site per night : "
          f"{SITE_POWER_KW}kW × {RADIO_SHARE:.0%} radio × {DEEP_SLEEP_SAVING:.0%} deep-sleep × "
          f"{LOW_TRAFFIC_HOURS:.0f}h = {m['kwh_per_site_night']:.1f} kWh")
    print(f"  this district ({best_size} asleep)     : "
          f"{m['district_kwh_year']/1000:,.0f} MWh/yr · ฿{m['district_thb_year']/1e6:,.2f}M/yr · "
          f"{m['district_tco2e_year']:,.0f} tCO2e/yr")
    print("\nNATIONAL SENSITIVITY — extra cells slept vs per-cell rules (extrapolation printed):")
    print(f"  (district {n_sites_district} sites -> national {NATIONAL_SITES:,} sites, factor "
          f"×{NATIONAL_SITES/n_sites_district:.0f})")
    for _, r in sensitivity_table(n_sites_district).iterrows():
        print(f"    {r['incremental_sleep_points']:>8s} :  ฿{r['national_THB_per_year']/1e6:>5.0f} M/yr   "
              f"{r['national_MWh_per_year']:>7,.0f} MWh/yr   {r['national_tCO2e_per_year']:>6,.0f} tCO2e/yr")
    print("\n" + "=" * 74)
    print("Every baht of this is reachable TODAY with a classical solver. Quantum's")
    print("contribution to this number in 2026 is ZERO. The reason to run it on quantum")
    print("hardware is to measure the gap — see the next section.")
    print("=" * 74)
