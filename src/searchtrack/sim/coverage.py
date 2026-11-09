"""Vectorised radar coverage prediction for display overlays and the
vertical coverage diagram (same physics as radar.evaluate, minus clutter and
jamming which depend on the instantaneous situation)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from .catalog import SWERLING1_SNR_DB_PD50_PFA6
from .geo import EARTH_R_KM
from .radar import integrated_snr_db, pd_swerling1

if TYPE_CHECKING:
    from .world import World


def _snr_grid(rt, slant_km: np.ndarray, rcs: float, rpm: float, degraded: float) -> np.ndarray:
    ref = integrated_snr_db(rt, 100.0, rcs, rpm) - degraded
    return ref - 40.0 * np.log10(np.maximum(slant_km, 0.5) / 100.0)


def _lobing_grid(rt, h_ant: float, h_t: np.ndarray, r_km: np.ndarray, rho: float = 0.7) -> np.ndarray:
    if not rt.lobing:
        return np.zeros_like(r_km)
    delta = 4.0 * math.pi * max(h_ant, 1.0) * np.maximum(h_t, 1.0) / (rt.wavelength_m * np.maximum(r_km, 0.2) * 1000.0)
    f2 = 1.0 + rho * rho - 2.0 * rho * np.cos(delta)
    return np.clip(20.0 * np.log10(np.maximum(f2, 1e-4)), -30.0, 12.0)


def horizontal(world: "World", xs: np.ndarray, ys: np.ndarray, alt_m: float, rcs: float = 5.0,
               sites: list | None = None) -> np.ndarray:
    """Number of radars predicting Pd >= 0.5 at each (x, y) for a target at alt_m."""
    count = np.zeros(xs.shape, dtype=np.int16)
    for site in (sites if sites is not None else world.radars.values()):
        if site.status in ("down", "maint"):
            continue
        rt = world.catalog.radars[site.type_id]
        k = site.k_override or world.weather.k_factor
        mask = world.mask_for(site)
        dx, dy = xs - site.x, ys - site.y
        gr = np.hypot(dx, dy)
        el = np.arctan(((alt_m - site.h_ant) / 1000.0 - gr * gr / (2 * k * EARTH_R_KM)) / np.maximum(gr, 1e-3))
        az = (np.degrees(np.arctan2(dx, dy)) % 360.0)
        ai = (az / 360.0 * mask.n_az).astype(int) % mask.n_az
        ri = np.minimum((gr / mask.dr).astype(int), mask.n_r - 1)
        ob = mask.mask[ai, ri]
        slant = np.sqrt(gr * gr + ((alt_m - site.h_ant) / 1000.0) ** 2)
        snr = _snr_grid(rt, slant, rcs, site.rpm, site.degraded_db) + _lobing_grid(rt, site.h_ant, np.full_like(gr, alt_m), slant)
        thr = SWERLING1_SNR_DB_PD50_PFA6 + (site.pfa_exp - 6.0) * 0.9
        ok = (gr <= rt.range_km) & (el > ob) & (np.degrees(el) <= rt.el_max_deg) & (snr >= thr)
        count += ok
    return count


def vertical(world: "World", site, az_deg: float, rmax_km: float, hmax_m: float, nr: int = 120, nh: int = 70,
             rcs: float = 5.0, margin: bool = False) -> np.ndarray:
    """Pd over a range-height grid along one azimuth. Shape (nh, nr); row 0 = highest altitude."""
    rt = world.catalog.radars[site.type_id]
    k = site.k_override or world.weather.k_factor
    mask = world.mask_for(site)
    r = (np.arange(nr) + 0.5) * rmax_km / nr
    h = (np.arange(nh)[::-1] + 0.5) * hmax_m / nh
    R, H = np.meshgrid(r, h)
    el = np.arctan(((H - site.h_ant) / 1000.0 - R * R / (2 * k * EARTH_R_KM)) / R)
    ai = int(az_deg / 360.0 * mask.n_az) % mask.n_az
    ri = np.minimum((R / mask.dr).astype(int), mask.n_r - 1)
    ob = mask.mask[ai, ri]
    slant = np.sqrt(R * R + ((H - site.h_ant) / 1000.0) ** 2)
    sea = bool(mask.sea[ai, min(int(20.0 / mask.dr), mask.n_r - 1)])
    snr = _snr_grid(rt, slant, rcs, site.rpm, site.degraded_db) + _lobing_grid(rt, site.h_ant, H, slant, 0.9 if sea else 0.55)
    pfa = 10.0 ** (-site.pfa_exp)
    pd = pfa ** (1.0 / (1.0 + 10.0 ** (snr / 10.0)))
    visible = (el > ob) & (np.degrees(el) <= rt.el_max_deg) & (R <= rt.range_km)
    if margin:
        thr = SWERLING1_SNR_DB_PD50_PFA6 + (site.pfa_exp - 6.0) * 0.9
        return np.where(visible, snr - thr, -99.0)
    return np.where(visible, pd, 0.0)
