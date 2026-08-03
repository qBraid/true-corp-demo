#!/usr/bin/env python3
"""
fetch_getinarea.py  —  full OpenCelliD getInArea extraction for Watthana / Sukhumvit
=====================================================================================

Collects the COMPLETE True-group cell set for the Watthana bounding box via the
OpenCelliD `getInArea` API, doing it the RIGHT way so there are no missing-tower
"bands":

  * the box is split into FINE tiles (each well under the 4,000,000 m² query limit
    AND small enough that a tile never has more cells than we can page through), and
  * every tile is paginated FULLY (offset 0, 50, 100, ... until a short page), with
    NO artificial offset cap (the earlier bug capped at offset 1000 and silently
    dropped the northern strip of every dense tile).

Run this from a connection that has getInArea quota left. The free limit is ~5000
requests/day and is enforced PER SOURCE IP — a carrier-grade-NAT hotspot is shared
by many users and is usually already exhausted, so prefer home broadband. If you
see `RATE_LIMITED` / `Daily limit ... exceeded`, wait for the reset (midnight UTC)
or switch to a non-shared connection.

Token: put it in the repo's `.env` as `OPEN_CELLID_TOKEN=...` (gitignored, never
committed), or pass `--token`. The token is never printed.

Usage:
    python scripts/fetch_getinarea.py                 # -> data/watthana_cells_real.csv
    python scripts/fetch_getinarea.py --tile-m 900    # finer tiles if a tile still truncates
    python scripts/fetch_getinarea.py --out data/foo.csv --token pk.XXXX
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- what we collect -------------------------------------------------------
MCC = 520  # Thailand
TRUE_GROUP_MNCS = (0, 4, 5, 18, 25, 99)  # True / dtac families
BBOX = (13.710, 13.752, 100.550, 100.600)  # (min_lat, max_lat, min_lon, max_lon)
COLUMNS = [
    "radio",
    "mcc",
    "net",
    "area",
    "cell",
    "unit",
    "lon",
    "lat",
    "range",
    "samples",
    "changeable",
    "created",
    "updated",
    "averageSignal",
]

_AREA_URL = (
    "https://opencellid.org/cell/getInArea?key={token}&BBOX={bbox}"
    "&mcc={mcc}&format=json&limit=50&offset={offset}"
)
_UA = {"User-Agent": "true-corp-demo/1.0 (quantum education demo)"}


def resolve_token(cli_token: str | None) -> str:
    """--token, then the .env FILE (source of truth, read fresh), then the env var."""
    if cli_token:
        return cli_token
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith("OPEN_CELLID_TOKEN") and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    if os.environ.get("OPEN_CELLID_TOKEN"):
        return os.environ["OPEN_CELLID_TOKEN"]
    raise SystemExit("No OpenCelliD token. Put OPEN_CELLID_TOKEN in .env or pass --token.")


def _fetch(token, la0, lo0, la1, lo1, offset):
    url = _AREA_URL.format(token=token, bbox=f"{la0},{lo0},{la1},{lo1}", mcc=MCC, offset=offset)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=60).read()
    return json.loads(raw.decode())


def collect(token: str, tile_m: float = 1000.0) -> pd.DataFrame:
    min_lat, max_lat, min_lon, max_lon = BBOX
    mlat = 111_000.0
    mlon = 111_000.0 * math.cos(math.radians((min_lat + max_lat) / 2))
    nlat = math.ceil((max_lat - min_lat) * mlat / tile_m)
    nlon = math.ceil((max_lon - min_lon) * mlon / tile_m)
    dlat = (max_lat - min_lat) / nlat
    dlon = (max_lon - min_lon) / nlon
    print(f"tiling {nlat} x {nlon} = {nlat*nlon} tiles (~{tile_m:.0f} m each), full pagination")

    seen: dict = {}
    calls = 0
    for i in range(nlat):
        for j in range(nlon):
            la0, la1 = min_lat + i * dlat, min_lat + (i + 1) * dlat
            lo0, lo1 = min_lon + j * dlon, min_lon + (j + 1) * dlon
            off, got = 0, 0
            while True:
                payload = _fetch(token, la0, lo0, la1, lo1, off)
                calls += 1
                if "error" in payload:
                    raise SystemExit(
                        f"\nOpenCelliD error after {calls} calls: {payload}\n"
                        "Likely rate-limited (per-IP). Retry later / another network."
                    )
                cells = payload.get("cells", [])
                for c in cells:
                    seen[(c["mnc"], c["lac"], c["cellid"])] = c
                got += len(cells)
                if len(cells) < 50:  # short page => tile exhausted
                    break
                off += 50
            print(
                f"  tile [{i+1:>2}/{nlat},{j+1:>2}/{nlon}] lat {la0:.4f}-{la1:.4f}: "
                f"{got:4d} cells (dedup total {len(seen)})",
                flush=True,
            )
    print(f"getInArea calls used: {calls}")

    rows = [
        dict(
            radio=c.get("radio", "") or "",
            mcc=c["mcc"],
            net=c["mnc"],
            area=c["lac"],
            cell=c["cellid"],
            unit=0,
            lon=c["lon"],
            lat=c["lat"],
            range=c.get("range", 0),
            samples=c.get("samples", 0),
            changeable=c.get("changeable", 1),
            created=0,
            updated=0,
            averageSignal=c.get("averageSignalStrength", 0),
        )
        for c in seen.values()
    ]
    return pd.DataFrame(rows)[COLUMNS]


def completeness_report(df: pd.DataFrame) -> None:
    """Print a latitude histogram — a smooth profile (no zero-gaps) means the fetch
    was NOT truncated at tile boundaries."""
    true_df = df[(df["mcc"] == MCC) & (df["net"].isin(TRUE_GROUP_MNCS))]
    print(f"\nTotal MCC {MCC} cells: {len(df):,}  |  True-group: {len(true_df):,}")
    print(f"  radio mix (True-group): {dict(true_df['radio'].value_counts())}")
    lats = true_df["lat"].values
    if len(lats):
        h, _ = np.histogram(lats, bins=14, range=(BBOX[0], BBOX[1]))
        print("  latitude histogram (should be smooth, NO 0-gaps):")
        print("   ", " ".join(f"{c:3d}" for c in h))
        if (h == 0).any():
            print("  ⚠  a 0-count band remains — lower --tile-m and re-run.")
        else:
            print("  ✓  no empty bands — extraction looks complete.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--token", default=None, help="OpenCelliD token (default: .env / env)")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "watthana_cells_real.csv"))
    ap.add_argument(
        "--tile-m",
        type=float,
        default=1000.0,
        help="tile side in metres (smaller = safer against truncation)",
    )
    ap.add_argument(
        "--true-only",
        action="store_true",
        help="save only True-group MNCs (default saves all MCC 520)",
    )
    args = ap.parse_args()

    t0 = time.time()
    df = collect(resolve_token(args.token), tile_m=args.tile_m)
    if args.true_only:
        df = df[df["net"].isin(TRUE_GROUP_MNCS)].reset_index(drop=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    completeness_report(df)
    print(f"\nwrote {len(df):,} rows -> {args.out}   ({time.time()-t0:.0f}s)")
    print(
        "Next: python scripts/prerun_experiments.py && python scripts/fetch_basemap.py "
        "&& python scripts/build_notebook.py"
    )


if __name__ == "__main__":
    main()
