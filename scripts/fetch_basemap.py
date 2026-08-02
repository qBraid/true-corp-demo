#!/usr/bin/env python3
"""
fetch_basemap.py
================

Fetch a real dark basemap of the Watthana / Sukhumvit region (CartoDB Dark Matter,
built on OpenStreetMap) tightly around the REAL cell-tower extent, and save it plus
its geographic bounds so the notebook can render the layered map OFFLINE.

Run once, ahead of the event (needs internet). Outputs:
    data/sukhumvit_basemap.png    stitched, cropped, downscaled dark map
    data/sukhumvit_basemap.json   {west, east, south, north}  (WGS84 bounds)

Basemap © OpenStreetMap contributors © CARTO. Tiles are fetched at a modest zoom
for a one-off; do not hammer the tile servers.
"""

from __future__ import annotations

import io
import json
import math
import os
import urllib.request

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.join(HERE, "src"))
import sleepcells as sc  # noqa: E402

CENTER = (13.731, 100.575)
ZOOM = 15
TILE = 512  # @2x retina tiles
TILE_URL = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png"
UA = {"User-Agent": "true-corp-demo/1.0 (quantum education demo)"}
MAX_WIDTH = 2600  # downscale target


def _xf(lon):
    return (lon + 180.0) / 360.0 * (2 ** ZOOM)


def _yf(lat):
    r = math.radians(lat)
    return (1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * (2 ** ZOOM)


def real_extent(margin=0.08):
    df = sc.load_cells(os.path.join(HERE, "data", "watthana_cells_real.csv"))
    fdf = sc.filter_cells(df)
    lon, lat = fdf["lon"].values, fdf["lat"].values
    mx = (lon.max() - lon.min()) * margin
    my = (lat.max() - lat.min()) * margin
    return (lon.min() - mx, lon.max() + mx, lat.min() - my, lat.max() + my)


def main():
    west, east, south, north = real_extent()
    x0, x1 = int(math.floor(_xf(west))), int(math.floor(_xf(east)))
    y0, y1 = int(math.floor(_yf(north))), int(math.floor(_yf(south)))
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    print(f"extent lon[{west:.4f},{east:.4f}] lat[{south:.4f},{north:.4f}] "
          f"-> {nx}x{ny} = {nx*ny} tiles at z{ZOOM}")

    canvas = Image.new("RGB", (nx * TILE, ny * TILE))
    for xi in range(x0, x1 + 1):
        for yi in range(y0, y1 + 1):
            url = TILE_URL.format(z=ZOOM, x=xi, y=yi)
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
                canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"),
                             ((xi - x0) * TILE, (yi - y0) * TILE))
            except Exception as e:
                print("  tile fail", xi, yi, repr(e)[:60])

    # crop to the exact geographic bbox
    L = (_xf(west) - x0) * TILE
    R = (_xf(east) - x0) * TILE
    T = (_yf(north) - y0) * TILE
    B = (_yf(south) - y0) * TILE
    crop = canvas.crop((int(L), int(T), int(R), int(B)))
    if crop.width > MAX_WIDTH:
        h = int(crop.height * MAX_WIDTH / crop.width)
        crop = crop.resize((MAX_WIDTH, h), Image.LANCZOS)

    out_png = os.path.join(HERE, "data", "sukhumvit_basemap.png")
    out_json = os.path.join(HERE, "data", "sukhumvit_basemap.json")
    crop.save(out_png)
    json.dump({"west": west, "east": east, "south": south, "north": north,
               "zoom": ZOOM, "attribution": "© OpenStreetMap contributors © CARTO"},
              open(out_json, "w"), indent=2)
    print(f"saved {out_png}  ({crop.size[0]}x{crop.size[1]})")


if __name__ == "__main__":
    main()
