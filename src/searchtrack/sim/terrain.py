"""Terrain grid, per-radar horizon masks and ground-clutter visibility.

A horizon mask stores, for every azimuth bin and range bin, the maximum
apparent elevation angle of the terrain (or sea surface) *closer* to the radar
than that range, on an effective Earth of radius k*R. A target is in line of
sight iff its own apparent elevation angle exceeds the mask value at its range.
This single test captures the smooth-Earth radar horizon and terrain masking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geo import DEFAULT_K, EARTH_R_KM


class Terrain:
    def __init__(self, elev: np.ndarray, x0: float, y0: float, spacing: float):
        self.elev = np.asarray(elev, dtype=np.float32)
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.sp = float(spacing)
        self.ny, self.nx = self.elev.shape

    @classmethod
    def load(cls, path: Path) -> "Terrain":
        d = np.load(path)
        return cls(d["elev"], float(d["x0"]), float(d["y0"]), float(d["spacing"]))

    @classmethod
    def flat(cls, elev_m: float = 0.0, half_km: float = 1000.0, spacing: float = 10.0) -> "Terrain":
        n = int(2 * half_km / spacing) + 1
        return cls(np.full((n, n), elev_m, dtype=np.float32), -half_km, -half_km, spacing)

    def height_np(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        fj = (np.asarray(x) - self.x0) / self.sp
        fi = (np.asarray(y) - self.y0) / self.sp
        outside = (fj < 0) | (fi < 0) | (fj > self.nx - 1) | (fi > self.ny - 1)
        fj = np.clip(fj, 0, self.nx - 1.001)
        fi = np.clip(fi, 0, self.ny - 1.001)
        j0 = fj.astype(int)
        i0 = fi.astype(int)
        dj = fj - j0
        di = fi - i0
        e = self.elev
        h = (e[i0, j0] * (1 - di) * (1 - dj) + e[i0, j0 + 1] * (1 - di) * dj
             + e[i0 + 1, j0] * di * (1 - dj) + e[i0 + 1, j0 + 1] * di * dj)
        return np.where(outside, 0.0, h)

    def height(self, x: float, y: float) -> float:
        return float(self.height_np(np.array([x]), np.array([y]))[0])

    def is_sea(self, x: float, y: float) -> bool:
        return self.height(x, y) <= 0.0


@dataclass
class HorizonMask:
    n_az: int
    dr: float
    n_r: int
    k: float
    mask: np.ndarray          # (n_az, n_r) radians: max obstruction angle before range bin
    clutter: np.ndarray       # (n_az, n_r) sigma0 dB of visible ground, -999 where none
    sea: np.ndarray           # (n_az, n_r) bool: visible cell is sea

    def bins(self, az_deg: float, r_km: float) -> tuple[int, int]:
        i = int(az_deg / 360.0 * self.n_az) % self.n_az
        j = min(int(r_km / self.dr), self.n_r - 1)
        return i, j

    def obstruction(self, az_deg: float, r_km: float) -> float:
        i, j = self.bins(az_deg, r_km)
        return float(self.mask[i, j])

    def clutter_db(self, az_deg: float, r_km: float) -> float:
        i, j = self.bins(az_deg, r_km)
        return float(self.clutter[i, j])

    def clutter_is_sea(self, az_deg: float, r_km: float) -> bool:
        i, j = self.bins(az_deg, r_km)
        return bool(self.sea[i, j])


def compute_mask(terrain: Terrain, x: float, y: float, h_ant_m: float, max_range_km: float,
                 land_sigma0_db: float = -20.0, sea_state: float = 3.0, k: float = DEFAULT_K,
                 n_az: int = 360, dr: float = 2.0, near_exclusion_km: float = 8.0) -> HorizonMask:
    n_r = int(math.ceil(max_range_km / dr)) + 1
    az = np.radians((np.arange(n_az) + 0.5) * 360.0 / n_az)
    r = (np.arange(n_r) + 0.5) * dr
    xs = x + r[None, :] * np.sin(az)[:, None]
    ys = y + r[None, :] * np.cos(az)[:, None]
    h = terrain.height_np(xs, ys)
    hs = np.maximum(h, 0.0)
    phi = np.arctan(((hs - h_ant_m) / 1000.0 - r[None, :] ** 2 / (2.0 * k * EARTH_R_KM)) / r[None, :])
    near = r < near_exclusion_km
    phi_obs = phi.copy()
    phi_obs[:, near] = -math.pi / 2  # site assumed on local high point
    running = np.maximum.accumulate(phi_obs, axis=1)
    mask = np.concatenate([np.full((n_az, 1), -math.pi / 2), running[:, :-1]], axis=1).astype(np.float32)
    visible = phi >= mask - 1e-5
    is_sea = h <= 0.0
    # land: rougher (higher) terrain scatters more; sea: grows with grazing angle and sea state
    rough = np.clip((hs - 150.0) / 600.0, 0.0, 1.0) * 6.0
    land_db = land_sigma0_db + rough
    graze = np.clip(-phi, 1e-4, 0.2)
    sea_db = np.clip(-52.0 + 4.0 * sea_state + 10.0 * np.log10(graze / 0.01), -75.0, -28.0)
    sig = np.where(is_sea, sea_db, land_db)
    clutter = np.where(visible, sig, -999.0).astype(np.float32)
    clutter[:, near & (r < 1.0)] = -999.0
    return HorizonMask(n_az=n_az, dr=dr, n_r=n_r, k=k, mask=mask, clutter=clutter, sea=(visible & is_sea))
