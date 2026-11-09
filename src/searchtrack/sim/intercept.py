"""Intercept geometry (units: km, km/s, seconds).

lead_collision: constant-velocity collision triangle (quadratic in time).
stern_aim:      aim at a point trailing the target, for rear-hemisphere
                attacks and safe visual-identification approaches.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .geo import bearing_deg


@dataclass
class Solution:
    hdg: float           # heading to fly (deg)
    t: float             # seconds to intercept (inf if pursuit)
    x: float             # predicted intercept point
    y: float
    method: str


def collision_time(px: float, py: float, vx: float, vy: float, ix: float, iy: float, vi: float) -> Optional[float]:
    dx, dy = px - ix, py - iy
    a = vx * vx + vy * vy - vi * vi
    b = 2.0 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    if abs(a) < 1e-12:
        if b >= 0:
            return None
        return -c / b
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    roots = sorted(r for r in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)) if r > 0)
    return roots[0] if roots else None


def lead_collision(px, py, vx, vy, ix, iy, vi) -> Solution:
    t = collision_time(px, py, vx, vy, ix, iy, vi)
    if t is None:
        return Solution(bearing_deg(px - ix, py - iy), math.inf, px, py, "pursuit")
    ax, ay = px + vx * t, py + vy * t
    return Solution(bearing_deg(ax - ix, ay - iy), t, ax, ay, "lead")


def stern_aim(px, py, vx, vy, ix, iy, vi, trail_km: float = 6.0, offset_km: float = 3.0) -> Solution:
    """Aim for a roll-out point behind and offset from the target; once close,
    convert to pursuit of a point just behind it."""
    spd = math.hypot(vx, vy)
    if spd < 1e-6:
        return lead_collision(px, py, vx, vy, ix, iy, vi)
    ux, uy = vx / spd, vy / spd
    # pick offset side nearest the interceptor
    side = 1.0 if (ix - px) * uy - (iy - py) * ux >= 0 else -1.0
    rx = px - ux * trail_km + uy * offset_km * side
    ry = py - uy * trail_km - ux * offset_km * side
    d = math.hypot(rx - ix, ry - iy)
    if d < 8.0:
        tx, ty = px - ux * 1.5, py - uy * 1.5
        return Solution(bearing_deg(tx - ix, ty - iy), d / max(vi - spd, 0.01), tx, ty, "stern-close")
    sol = lead_collision(rx, ry, vx, vy, ix, iy, vi)
    sol.method = "stern" if sol.method == "lead" else "pursuit"
    return sol


def pursuit(px, py, ix, iy) -> Solution:
    return Solution(bearing_deg(px - ix, py - iy), math.inf, px, py, "pursuit")


def solve(method: str, px, py, vx, vy, ix, iy, vi) -> Solution:
    if method == "stern":
        return stern_aim(px, py, vx, vy, ix, iy, vi)
    if method == "pursuit":
        return pursuit(px, py, ix, iy)
    return lead_collision(px, py, vx, vy, ix, iy, vi)
