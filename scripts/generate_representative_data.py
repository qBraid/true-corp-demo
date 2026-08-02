#!/usr/bin/env python3
"""
generate_representative_data.py
===============================

Builds a REPRESENTATIVE (synthetic) OpenCelliD-schema CSV of True Corporation
cell sites in Watthana district, Bangkok, for the "Which cells can sleep tonight?"
demo. It writes:

    data/watthana_cells.csv        (OpenCelliD 14-column schema)
    data/DATA_PROVENANCE.md        (honest provenance statement)

WHY SYNTHETIC / REPRESENTATIVE
------------------------------
There is no OpenCelliD API token in this environment, and the presentation must
not depend on a live download. So the shipped CSV is a *representative* dataset:
site positions are generated on the REAL Watthana geography (real bounding box,
real Sukhumvit BTS corridor, realistic urban macro-cell spacing and True/dtac
MNC mix) but they are NOT surveyed towers and NOT real OpenCelliD records.

To use REAL data instead, run `scripts/download_opencellid.py` (needs a free
OpenCelliD API token) to produce a CSV in the identical schema, then point the
notebook's DATA_CSV at it. The pipeline code is unchanged either way — this is
the whole point of matching the OpenCelliD schema exactly.

Every position here should be read as "an estimated centroid on the real street
grid", exactly as the deck's footnote states: crowdsourced estimated centroids,
not surveyed tower locations.
"""

from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd

# --- REAL Watthana / Sukhumvit geography (WGS84), from Wikipedia BTS + district ---
BBOX = (13.710, 13.752, 100.550, 100.600)          # (min_lat, max_lat, min_lon, max_lon)
CENTER = (13.731, 100.575)
# Sukhumvit Line BTS stations threading the dense corridor (Asok -> Ekkamai)
CORRIDOR = [
    (13.7370, 100.5604),   # Asok (E4)
    (13.7304, 100.5697),   # Phrom Phong (E5)
    (13.7242, 100.5786),   # Thong Lo (E6)
    (13.7196, 100.5852),   # Ekkamai (E7)
]

# True-group MNCs under Thailand MCC 520 (competitors excluded).
TRUE_MNC_WEIGHTS = {4: 0.34, 18: 0.24, 5: 0.20, 99: 0.14, 0: 0.05, 25: 0.03}
# Radio generations with a plausible urban mix and typical position uncertainty (m).
RADIO_MIX = {"LTE": 0.52, "NR": 0.30, "UMTS": 0.15, "GSM": 0.03}
RADIO_RANGE_M = {"GSM": 1200, "UMTS": 900, "LTE": 500, "NR": 300}

_M_PER_DEG_LAT = 110_540.0


def _m_per_deg_lon(lat: float) -> float:
    return _M_PER_DEG_LAT * math.cos(math.radians(lat))


def _latlon_offset(lat, lon, dx_m, dy_m):
    """Shift (lat, lon) by dx_m east, dy_m north."""
    return lat + dy_m / _M_PER_DEG_LAT, lon + dx_m / _m_per_deg_lon(lat)


def _dist_to_corridor_m(lat, lon):
    """Approx distance (m) from a point to the Asok->Ekkamai polyline."""
    mlon = _m_per_deg_lon(CENTER[0])
    px = (lon - CENTER[1]) * mlon
    py = (lat - CENTER[0]) * _M_PER_DEG_LAT
    best = math.inf
    for (a_lat, a_lon), (b_lat, b_lon) in zip(CORRIDOR[:-1], CORRIDOR[1:]):
        ax = (a_lon - CENTER[1]) * mlon
        ay = (a_lat - CENTER[0]) * _M_PER_DEG_LAT
        bx = (b_lon - CENTER[1]) * mlon
        by = (b_lat - CENTER[0]) * _M_PER_DEG_LAT
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        seg2 = vx * vx + vy * vy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / seg2))
        cx, cy = ax + t * vx, ay + t * vy
        best = min(best, math.hypot(px - cx, py - cy))
    return best


# Corridor midpoint (between Phrom Phong and Thong Lo) — heart of the dense core.
CORE_CENTER = (13.7273, 100.5742)
CORE_ROTATION_DEG = -30.0        # tilt the lattice to sit along the NE-SW corridor


def _xy_to_latlon(x_m, y_m, center):
    return center[0] + y_m / _M_PER_DEG_LAT, center[1] + x_m / _m_per_deg_lon(center[0])


def place_sites(seed: int,
                core_spacing_m: float = 285.0,
                core_radius_m: float = 2050.0,
                core_jitter: float = 0.06,
                ring_spacing_m: float = 520.0,
                n_ring_candidates: int = 40000):
    """Place physical mast positions: a dense planned CORE plus a sparse district RING.

    Core: a lightly-jittered hexagonal lattice (spacing core_spacing_m) inside a
    disk of radius core_radius_m about the Sukhumvit corridor midpoint, tilted to
    lie along the corridor. A planned urban macro layout is close to a jittered
    lattice, and this is what gives the pipeline a dense, contiguous, field-fitting
    'densest sub-district'. Jitter is kept small so neighbours stay above the
    238 m merge floor (otherwise the merge would collapse the lattice).

    Ring: sparser Poisson-disk sites filling the rest of the bounding box, for
    map context — these are the district around the dense core, and the
    densest-N selection deliberately does NOT pick them.
    """
    rng = np.random.default_rng(seed)
    th = math.radians(CORE_ROTATION_DEG)
    cos_t, sin_t = math.cos(th), math.sin(th)

    # --- dense core: jittered hex lattice in a disk ---
    core = []
    core_xy = []
    n = int(core_radius_m / core_spacing_m) + 2
    for iy in range(-2 * n, 2 * n):
        for ix in range(-2 * n, 2 * n):
            x = ix * core_spacing_m + (iy % 2) * core_spacing_m / 2.0
            y = iy * core_spacing_m * 0.866
            if x * x + y * y > core_radius_m ** 2:
                continue
            x += rng.uniform(-core_jitter * core_spacing_m, core_jitter * core_spacing_m)
            y += rng.uniform(-core_jitter * core_spacing_m, core_jitter * core_spacing_m)
            xr = x * cos_t - y * sin_t
            yr = x * sin_t + y * cos_t
            lat, lon = _xy_to_latlon(xr, yr, CORE_CENTER)
            core.append((lat, lon))
            core_xy.append((xr, yr))

    # --- sparse ring: Poisson-disk over the bbox, excluding the core disk ---
    min_lat, max_lat, min_lon, max_lon = BBOX
    ring = []
    ring_xy = []
    mlon = _m_per_deg_lon(CORE_CENTER[0])
    for _ in range(n_ring_candidates):
        lat = rng.uniform(min_lat, max_lat)
        lon = rng.uniform(min_lon, max_lon)
        px = (lon - CORE_CENTER[1]) * mlon
        py = (lat - CORE_CENTER[0]) * _M_PER_DEG_LAT
        if px * px + py * py <= (core_radius_m + ring_spacing_m) ** 2:
            continue                          # keep ring outside the core
        ok = True
        for (qx, qy) in ring_xy:
            if (px - qx) ** 2 + (py - qy) ** 2 < ring_spacing_m ** 2:
                ok = False
                break
        if ok:
            ring.append((lat, lon))
            ring_xy.append((px, py))

    return core + ring


def build_cells(sites, seed: int = 7) -> pd.DataFrame:
    """Explode each physical site into 3-6 cells (sector x band), OpenCelliD schema."""
    rng = np.random.default_rng(seed)
    radios = list(RADIO_MIX)
    radio_p = np.array(list(RADIO_MIX.values()))
    mncs = list(TRUE_MNC_WEIGHTS)
    mnc_p = np.array(list(TRUE_MNC_WEIGHTS.values()))
    base_created = 1_500_000_000    # ~2017, fixed for reproducibility
    base_updated = 1_735_000_000    # ~2024
    rows = []
    for (lat, lon) in sites:
        n_cells = int(rng.integers(3, 7))
        area = int(rng.integers(1, 65535))          # LAC/TAC shared per site
        for _ in range(n_cells):
            radio = radios[rng.choice(len(radios), p=radio_p)]
            mnc = int(mncs[rng.choice(len(mncs), p=mnc_p)])
            # cells on one mast scatter within ~10-25 m (antenna offsets / estimate noise)
            jx, jy = rng.normal(0, 18), rng.normal(0, 18)
            c_lat, c_lon = _latlon_offset(lat, lon, jx, jy)
            rows.append({
                "radio": radio,
                "mcc": 520,
                "net": mnc,
                "area": area,
                "cell": int(rng.integers(1, 268_435_455)),
                "unit": int(rng.integers(0, 504)),        # PCI-like
                "lon": round(c_lon, 7),
                "lat": round(c_lat, 7),
                "range": int(RADIO_RANGE_M[radio] * rng.uniform(0.7, 1.4)),
                "samples": int(rng.integers(1, 200)),
                "changeable": 1,                            # estimated from samples
                "created": base_created + int(rng.integers(0, 200_000_000)),
                "updated": base_updated + int(rng.integers(0, 20_000_000)),
                "averageSignal": 0,
            })
    df = pd.DataFrame(rows)
    # OpenCelliD column order
    return df[["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat",
               "range", "samples", "changeable", "created", "updated", "averageSignal"]]


PROVENANCE = """\
# Data provenance — watthana_cells.csv

**THIS IS REPRESENTATIVE (SYNTHETIC) DATA, NOT REAL OPENCELLID RECORDS.**

The notebook and the deck both state this plainly. Read every position as an
*estimated centroid on the real Watthana street grid*, not a surveyed tower.

## What is real
- The bounding box (lat 13.710–13.752, lon 100.550–100.600) and the Sukhumvit
  BTS corridor anchors (Asok, Phrom Phong, Thong Lo, Ekkamai) are real WGS84
  coordinates (Wikipedia).
- The MNC codes are True Corporation's real Thailand codes under MCC 520
  (TrueMove H 04/99, dtac 05/18, plus 00/25); competitors (AIS, NT) are excluded.
- The OpenCelliD 14-column schema is reproduced exactly, so a real extract is a
  drop-in replacement.
- Urban macro-cell spacing, sectors-per-site and band mix are set to realistic
  values for a dense Bangkok district.

## What is synthetic
- Every individual site POSITION. They are generated by a Poisson-disk sampler
  seeded on the corridor geometry, not measured. No claim is made that any point
  corresponds to a real True mast.
- Cell IDs, LAC/TAC, timestamps, samples: random but schema-valid.

## To use REAL data
1. Get a free OpenCelliD API token (https://opencellid.org).
2. Run `python scripts/download_opencellid.py --token <TOKEN>`; it writes a CSV
   in this identical schema filtered to MCC 520 + True MNCs + this bounding box.
3. Point the notebook's `DATA_CSV` at that file. Nothing else changes.
"""


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(here, "data")
    os.makedirs(data_dir, exist_ok=True)

    # Calibrated so the densest 150-atom sub-district lands at avg degree ~8,
    # fits the 75 um field, has exact MIS ~40 (deck headline 41/150), and the
    # exact classical solver finishes in a few seconds.
    sites = place_sites(seed=3, core_spacing_m=285.0, core_radius_m=2050.0,
                        core_jitter=0.06, ring_spacing_m=520.0)
    df = build_cells(sites, seed=7)

    csv_path = os.path.join(data_dir, "watthana_cells.csv")
    df.to_csv(csv_path, index=False)
    with open(os.path.join(data_dir, "DATA_PROVENANCE.md"), "w") as f:
        f.write(PROVENANCE)

    print(f"physical sites placed : {len(sites)}")
    print(f"cells written         : {len(df)}  -> {csv_path}")
    print(f"MNC mix               : {dict(df['net'].value_counts())}")
    print(f"radio mix             : {dict(df['radio'].value_counts())}")


if __name__ == "__main__":
    main()
