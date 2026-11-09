#!/usr/bin/env python3
"""Build per-theater map and terrain files from public-domain source data.

Inputs (download once; not stored in the repo):
  * Natural Earth 1:10m GeoJSON  (https://github.com/nvkelso/natural-earth-vector, geojson/)
      ne_10m_coastline, ne_10m_admin_0_boundary_lines_land, ne_10m_lakes,
      ne_10m_admin_1_states_provinces_lines, ne_10m_rivers_lake_centerlines
  * ETOPO1-derived 10 arc-minute grid (netCDF4/HDF5)
      https://github.com/fatiando-data/earth-topography-10arcmin/releases/download/v1/earth-topography-10arcmin.nc
    Any higher-resolution lat/lon grid with variables longitude/latitude/topography
    (or lon/lat/z) can be substituted for better terrain masking.

Outputs (committed): data/theaters/<id>/map.json, data/theaters/<id>/terrain.npz

Usage:
  python tools/build_theater.py --ne DIR --dem FILE data/theaters/gulf_of_maine
Requires: numpy, h5py (dev only).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from searchtrack.sim.geo import Projection  # noqa: E402

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def douglas_peucker(pts: np.ndarray, tol: float) -> np.ndarray:
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        seg = q - p
        seg_len = np.hypot(*seg)
        sub = pts[a + 1:b]
        if seg_len < 1e-9:
            d = np.hypot(sub[:, 0] - p[0], sub[:, 1] - p[1])
        else:
            d = np.abs(seg[0] * (sub[:, 1] - p[1]) - seg[1] * (sub[:, 0] - p[0])) / seg_len
        i = int(np.argmax(d))
        if d[i] > tol:
            m = a + 1 + i
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return pts[keep]


def iter_lines(geom: dict):
    t = geom["type"]
    c = geom["coordinates"]
    if t == "LineString":
        yield c
    elif t == "MultiLineString":
        yield from c
    elif t == "Polygon":
        yield from c
    elif t == "MultiPolygon":
        for poly in c:
            yield from poly


def crop_layer(path: Path, proj: Projection, box: tuple[float, float, float, float],
               tol: float, prop_filter=None) -> list[list[float]]:
    x0, x1, y0, y1 = box
    out: list[list[float]] = []
    data = json.loads(path.read_text())
    lat0, lon0 = proj.lat0, proj.lon0
    for feat in data["features"]:
        props = feat.get("properties") or {}
        if prop_filter and not prop_filter(props):
            continue
        bb = feat.get("bbox")
        if bb and (bb[2] < lon0 - 25 or bb[0] > lon0 + 25 or bb[3] < lat0 - 15 or bb[1] > lat0 + 15):
            continue
        for line in iter_lines(feat["geometry"]):
            arr = np.asarray(line, dtype=float)
            if arr.ndim != 2 or len(arr) < 2:
                continue
            x, y = proj.forward_np(arr[:, 1], arr[:, 0])
            inside = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
            if not inside.any():
                continue
            # split into runs of inside points (keep one neighbour outside for continuity)
            idx = np.flatnonzero(inside)
            runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
            for run in runs:
                a = max(run[0] - 1, 0)
                b = min(run[-1] + 1, len(x) - 1)
                seg = np.column_stack([x[a:b + 1], y[a:b + 1]])
                seg = douglas_peucker(seg, tol)
                if len(seg) >= 2:
                    out.append([round(float(v), 1) for v in seg.ravel()])
    return out


def load_dem(path: Path):
    import h5py  # dev dependency

    with h5py.File(path, "r") as f:
        keys = set(f.keys())
        lon_k = "longitude" if "longitude" in keys else "lon"
        lat_k = "latitude" if "latitude" in keys else "lat"
        z_k = "topography" if "topography" in keys else "z"
        lon = f[lon_k][:].astype(float)
        lat = f[lat_k][:].astype(float)
        z = f[z_k][:].astype(np.float32)
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        z = z[::-1, :]
    return lon, lat, z


def bilinear(lon: np.ndarray, lat: np.ndarray, z: np.ndarray, qlon: np.ndarray, qlat: np.ndarray) -> np.ndarray:
    fi = np.interp(qlat, lat, np.arange(len(lat)))
    fj = np.interp(qlon, lon, np.arange(len(lon)))
    i0 = np.clip(np.floor(fi).astype(int), 0, len(lat) - 2)
    j0 = np.clip(np.floor(fj).astype(int), 0, len(lon) - 2)
    di = fi - i0
    dj = fj - j0
    z00 = z[i0, j0]
    z01 = z[i0, j0 + 1]
    z10 = z[i0 + 1, j0]
    z11 = z[i0 + 1, j0 + 1]
    return (z00 * (1 - di) * (1 - dj) + z01 * (1 - di) * dj + z10 * di * (1 - dj) + z11 * di * dj)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ne", required=True, type=Path, help="directory with Natural Earth 10m GeoJSON")
    ap.add_argument("--dem", required=True, type=Path, help="lat/lon elevation grid (netCDF4/HDF5)")
    ap.add_argument("theater", type=Path, help="theater directory containing theater.toml")
    args = ap.parse_args()

    cfg = tomllib.loads((args.theater / "theater.toml").read_text())
    pj = cfg["projection"]
    b = cfg["build"]
    proj = Projection(pj["lat0"], pj["lon0"])
    ext = pj["extent_km"]  # [xmin, xmax, ymin, ymax]
    m = 60.0
    box = (ext[0] - m, ext[1] + m, ext[2] - m, ext[3] + m)
    tol = b.get("simplify_km", 0.6)
    countries = set(b.get("state_lines_countries", []))

    layers = {
        "coast": crop_layer(args.ne / "ne_10m_coastline.geojson", proj, box, tol),
        "borders": crop_layer(args.ne / "ne_10m_admin_0_boundary_lines_land.geojson", proj, box, tol),
        "lakes": crop_layer(args.ne / "ne_10m_lakes.geojson", proj, box, tol,
                            lambda p: (p.get("scalerank") or p.get("SCALERANK") or 0) <= b.get("lake_max_rank", 6)),
        "states": crop_layer(args.ne / "ne_10m_admin_1_states_provinces_lines.geojson", proj, box, tol,
                             lambda p: (p.get("adm0_name") or p.get("ADM0_NAME")) in countries),
        "rivers": crop_layer(args.ne / "ne_10m_rivers_lake_centerlines.geojson", proj, box, tol * 1.5,
                             lambda p: (p.get("scalerank") or p.get("SCALERANK") or 99) <= b.get("river_max_rank", 6)),
    }
    out = {"theater": cfg.get("id", args.theater.name), "units": "km", "source": "Natural Earth 1:10m (public domain)"}
    out.update(layers)
    (args.theater / "map.json").write_text(json.dumps(out, separators=(",", ":")))

    lon, lat, z = load_dem(args.dem)
    sp = b.get("terrain_spacing_km", 4.0)
    xs = np.arange(ext[0], ext[1] + sp * 0.5, sp)
    ys = np.arange(ext[2], ext[3] + sp * 0.5, sp)
    gx, gy = np.meshgrid(xs, ys)
    qlat, qlon = proj.inverse_np(gx, gy)
    elev = bilinear(lon, lat, z, qlon, qlat)
    np.savez_compressed(args.theater / "terrain.npz", elev=np.round(elev).astype(np.int16),
                        x0=np.float64(xs[0]), y0=np.float64(ys[0]), spacing=np.float64(sp),
                        source=np.array("ETOPO1-derived 10 arc-minute (Fatiando a Terra); NOAA public domain"))
    sizes = {k: sum(len(s) // 2 for s in v) for k, v in layers.items()}
    print(f"{args.theater.name}: points {sizes}; terrain {elev.shape} "
          f"min {elev.min():.0f} max {elev.max():.0f} m; map.json {(args.theater / 'map.json').stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
