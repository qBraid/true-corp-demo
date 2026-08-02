#!/usr/bin/env python3
"""
download_opencellid.py
======================

Fetch REAL OpenCelliD data for True Corporation cells in Watthana district and
write it in the exact schema the notebook expects — a drop-in replacement for
the representative `data/watthana_cells.csv`.

This script is intentionally SEPARATE from the notebook: the presentation must
not depend on a live download. Run it once, ahead of time, then point the
notebook's `DATA_CSV` at the output.

Usage
-----
    python scripts/download_opencellid.py --token YOUR_OPENCELLID_TOKEN \
        --out data/watthana_cells_real.csv

Get a free token at https://opencellid.org (Register -> API access). The free
tier allows the full-country CSV download used here.

What it does
------------
1. Downloads the Thailand (MCC 520) cell export: a gzipped CSV in the canonical
   OpenCelliD schema
   `radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal`.
2. Filters to True-group MNCs {0,4,5,18,25,99} and the Watthana bounding box.
3. Writes the filtered CSV (same schema, same column order).

If OpenCelliD changes its download URL, only `MCC_URL` below needs updating; the
schema and filtering are stable.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_token(cli_token: str | None) -> str:
    """Find the OpenCelliD token from --token, the OPEN_CELLID_TOKEN env var, or a
    local .env file (never echoed). The .env file is gitignored."""
    if cli_token:
        return cli_token
    if os.environ.get("OPEN_CELLID_TOKEN"):
        return os.environ["OPEN_CELLID_TOKEN"]
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith("OPEN_CELLID_TOKEN") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No OpenCelliD token found. Set OPEN_CELLID_TOKEN (env or .env) "
                     "or pass --token.")

# True-group MNCs under Thailand MCC 520 (competitors AIS/NT excluded).
TRUE_GROUP_MNCS = (0, 4, 5, 18, 25, 99)
# Watthana / Sukhumvit bounding box (min_lat, max_lat, min_lon, max_lon).
BBOX = (13.710, 13.752, 100.550, 100.600)
# OpenCelliD per-MCC download endpoint (token appended at call time).
MCC_URL = "https://opencellid.org/ocid/downloads?token={token}&type=mcc&file=520.csv.gz"

COLUMNS = ["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat",
           "range", "samples", "changeable", "created", "updated", "averageSignal"]


def download_mcc_csv(token: str) -> pd.DataFrame:
    url = MCC_URL.format(token=token)
    print(f"Downloading MCC 520 export from OpenCelliD ...", file=sys.stderr)
    # OpenCelliD rejects the default python-urllib User-Agent with HTTP 403.
    req = urllib.request.Request(url, headers={"User-Agent": "true-corp-demo/1.0 (quantum demo)"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read()
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
        df = pd.read_csv(gz, names=COLUMNS, header=None)
    # Some exports include a header row; drop it if present.
    if df.iloc[0]["radio"] == "radio":
        df = df.iloc[1:].reset_index(drop=True)
    for c in ["mcc", "net", "area", "cell", "unit", "range", "samples",
              "changeable", "created", "updated", "averageSignal"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    return df


def filter_true_watthana(df: pd.DataFrame) -> pd.DataFrame:
    min_lat, max_lat, min_lon, max_lon = BBOX
    m = df["mcc"] == 520
    m &= df["net"].isin(TRUE_GROUP_MNCS)
    m &= df["lat"].between(min_lat, max_lat)
    m &= df["lon"].between(min_lon, max_lon)
    return df.loc[m, COLUMNS].reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=None,
                    help="OpenCelliD API token (default: OPEN_CELLID_TOKEN env / .env)")
    ap.add_argument("--out", default="data/watthana_cells_real.csv",
                    help="output CSV path")
    args = ap.parse_args()

    df = download_mcc_csv(resolve_token(args.token))
    print(f"MCC 520 rows: {len(df):,}", file=sys.stderr)
    out = filter_true_watthana(df)
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out):,} True-group cells in Watthana -> {args.out}")
    print(f"  MNC counts: {dict(out['net'].value_counts())}")
    print(f"  radio counts: {dict(out['radio'].value_counts())}")
    print("Point the notebook's DATA_CSV at this file to use real positions.")


if __name__ == "__main__":
    main()
