"""Geodesy, projection and radar-geometry helpers.

The simulation runs on a flat x/y plane in kilometres produced by an azimuthal
equidistant projection centred on each theater (distances from the centre are
exact; elsewhere distortion is ~1-2 % at 700 km, acceptable for gameplay).
Earth curvature is reintroduced explicitly wherever it matters: radar horizon,
terrain masking and elevation angles, using an effective-Earth (k-factor) model.

Angles: bearings/headings are degrees clockwise from grid north (+y).
"""
from __future__ import annotations

import math

import numpy as np

EARTH_R_KM = 6371.0
DEFAULT_K = 4.0 / 3.0  # standard atmosphere refraction
FT = 0.3048            # metres per foot
NM = 1.852             # km per nautical mile
KT = 0.514444          # m/s per knot
G = 9.80665


class Projection:
    """Spherical azimuthal equidistant projection (km)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0 = lat0
        self.lon0 = lon0
        self._p0 = math.radians(lat0)
        self._l0 = math.radians(lon0)
        self._sp0 = math.sin(self._p0)
        self._cp0 = math.cos(self._p0)

    def forward(self, lat: float, lon: float) -> tuple[float, float]:
        p = math.radians(lat)
        dl = math.radians(lon) - self._l0
        cos_c = self._sp0 * math.sin(p) + self._cp0 * math.cos(p) * math.cos(dl)
        cos_c = max(-1.0, min(1.0, cos_c))
        c = math.acos(cos_c)
        k = 1.0 if c < 1e-12 else c / math.sin(c)
        x = EARTH_R_KM * k * math.cos(p) * math.sin(dl)
        y = EARTH_R_KM * k * (self._cp0 * math.sin(p) - self._sp0 * math.cos(p) * math.cos(dl))
        return x, y

    def forward_np(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = np.radians(lat)
        dl = np.radians(lon) - self._l0
        cos_c = np.clip(self._sp0 * np.sin(p) + self._cp0 * np.cos(p) * np.cos(dl), -1.0, 1.0)
        c = np.arccos(cos_c)
        with np.errstate(invalid="ignore", divide="ignore"):
            k = np.where(c < 1e-12, 1.0, c / np.sin(c))
        x = EARTH_R_KM * k * np.cos(p) * np.sin(dl)
        y = EARTH_R_KM * k * (self._cp0 * np.sin(p) - self._sp0 * np.cos(p) * np.cos(dl))
        return x, y

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        rho = math.hypot(x, y)
        if rho < 1e-9:
            return self.lat0, self.lon0
        c = rho / EARTH_R_KM
        sc, cc = math.sin(c), math.cos(c)
        lat = math.asin(cc * self._sp0 + (y * sc * self._cp0) / rho)
        lon = self._l0 + math.atan2(x * sc, rho * self._cp0 * cc - y * self._sp0 * sc)
        return math.degrees(lat), (math.degrees(lon) + 540.0) % 360.0 - 180.0

    def inverse_np(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rho = np.hypot(x, y)
        c = rho / EARTH_R_KM
        sc, cc = np.sin(c), np.cos(c)
        with np.errstate(invalid="ignore", divide="ignore"):
            lat = np.arcsin(np.clip(cc * self._sp0 + np.where(rho > 0, y * sc * self._cp0 / rho, 0.0), -1, 1))
        lon = self._l0 + np.arctan2(x * sc, rho * self._cp0 * cc - y * self._sp0 * sc)
        lat = np.where(rho < 1e-9, self._p0, lat)
        lon = np.where(rho < 1e-9, self._l0, lon)
        return np.degrees(lat), (np.degrees(lon) + 540.0) % 360.0 - 180.0


# ---------------------------------------------------------------- planar helpers

def bearing_deg(dx: float, dy: float) -> float:
    """Bearing of vector (dx, dy) in degrees clockwise from +y (north)."""
    return math.degrees(math.atan2(dx, dy)) % 360.0


def heading_vec(hdg_deg: float) -> tuple[float, float]:
    r = math.radians(hdg_deg)
    return math.sin(r), math.cos(r)


def angle_diff(a: float, b: float) -> float:
    """Signed smallest difference a - b in degrees, in (-180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def in_sector(az: float, start: float, sweep: float) -> bool:
    """True if azimuth az lies within [start, start+sweep) going clockwise."""
    if sweep >= 360.0:
        return True
    return (az - start) % 360.0 < sweep


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


# ---------------------------------------------------------------- curvature

def horizon_km(h_m: float, k: float = DEFAULT_K) -> float:
    """Distance to the radio horizon for an antenna/target at height h_m (metres ASL)."""
    return math.sqrt(max(0.0, 2.0 * k * EARTH_R_KM * h_m / 1000.0))


def radar_horizon_km(h_radar_m: float, h_target_m: float, k: float = DEFAULT_K) -> float:
    return horizon_km(h_radar_m, k) + horizon_km(h_target_m, k)


def elevation_angle(h_from_m: float, h_to_m: float, ground_km: float, k: float = DEFAULT_K) -> float:
    """Apparent elevation angle (radians) of a point at ground distance ground_km and
    height h_to_m, seen from height h_from_m, on an effective Earth of radius k*R."""
    if ground_km < 1e-6:
        return math.pi / 2 if h_to_m >= h_from_m else -math.pi / 2
    dh_km = (h_to_m - h_from_m) / 1000.0
    return math.atan((dh_km - ground_km * ground_km / (2.0 * k * EARTH_R_KM)) / ground_km)


def slant_range_km(ground_km: float, h_from_m: float, h_to_m: float) -> float:
    dh = (h_to_m - h_from_m) / 1000.0
    return math.sqrt(ground_km * ground_km + dh * dh)


# ---------------------------------------------------------------- atmosphere

def isa_density_ratio(alt_m: float) -> float:
    """sigma = rho/rho0 for the ISA troposphere/stratosphere (to 20 km+)."""
    if alt_m < 11000.0:
        t = 1.0 - 2.25577e-5 * alt_m
        return t ** 4.2559
    return 0.29708 * math.exp(-(alt_m - 11000.0) / 6341.6)


def speed_of_sound(alt_m: float) -> float:
    t = 288.15 - 0.0065 * min(alt_m, 11000.0)
    return 20.0468 * math.sqrt(t)


def mach_to_tas(mach: float, alt_m: float) -> float:
    return mach * speed_of_sound(alt_m)
