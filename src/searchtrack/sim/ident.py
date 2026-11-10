"""Identification: IFF/SIF interpretation, flight-plan correlation against
NORAD tolerances, visual-ID evidence, doctrinal recommendations and the
automated identification operator."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .geo import NM
from .state import FlightPlan, Track

if TYPE_CHECKING:
    from .world import World

TIME_TOL_MIN = 5.0
LAND_TOL_NM = 10.0
WATER_TOL_NM = 20.0


def point_in_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def fp_position(fp: FlightPlan, t: float):
    r = fp.route
    if not r or t < r[0][2] or t > r[-1][2]:
        return None
    for a, b in zip(r, r[1:]):
        if a[2] <= t <= b[2]:
            f = (t - a[2]) / max(b[2] - a[2], 1e-6)
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
    return None


@dataclass
class FPMatch:
    fp: str
    callsign: str
    dt_min: float
    dist_nm: float
    tol_nm: float
    code_ok: bool
    within: bool


def correlate(world: "World", trk: Track, t: float | None = None) -> list[FPMatch]:
    """Compare a track with every filed flight plan: along-route time error and
    cross-track distance at the closest point of the planned route."""
    t = world.t if t is None else t
    over_water = world.is_sea(trk.x, trk.y)
    tol = WATER_TOL_NM if over_water else LAND_TOL_NM
    out: list[FPMatch] = []
    for fp in world.flight_plans.values():
        if not fp.filed or len(fp.route) < 2:
            continue
        best = None
        for a, b in zip(fp.route, fp.route[1:]):
            ax, ay, at = a
            bx, by, bt = b
            sx, sy = bx - ax, by - ay
            L2 = sx * sx + sy * sy
            u = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((trk.x - ax) * sx + (trk.y - ay) * sy) / L2))
            cx, cy = ax + sx * u, ay + sy * u
            d = math.hypot(trk.x - cx, trk.y - cy)
            tp = at + (bt - at) * u
            if best is None or d < best[0]:
                best = (d, tp)
        d_km, tp = best
        dt_min = (t - tp) / 60.0
        dist_nm = d_km / NM
        if dist_nm > tol * 3 or abs(dt_min) > TIME_TOL_MIN * 4:
            continue
        code_ok = bool(fp.mode3) and trk.iff.get("3") == fp.mode3
        within = dist_nm <= tol and abs(dt_min) <= TIME_TOL_MIN
        out.append(FPMatch(fp.id, fp.callsign, dt_min, dist_nm, tol, code_ok, within))
    out.sort(key=lambda m: (not m.within, not m.code_ok, m.dist_nm + abs(m.dt_min) * 3))
    return out


def iff_assessment(world: "World", trk: Track) -> tuple[str, str]:
    """Returns (verdict, text) where verdict in valid | invalid | none."""
    if not trk.iff or world.t - trk.iff_t > 180.0:
        return "none", "No IFF reply"
    if world.faction_def.id == "US":
        m1 = trk.iff.get("1")
        valid = world.hq.policy.get("mode1_valid", [])
        if m1 and m1 in valid:
            return "valid", f"SIF Mode 1 {m1} valid (military)"
        if m1:
            return "invalid", f"SIF Mode 1 {m1} NOT a current code"
        if trk.iff.get("3"):
            return "atc", f"Mode 3/A {trk.iff['3']} (ATC transponder)"
        return "none", "No IFF reply"
    code = trk.iff.get("period", "")
    current = world.hq.policy.get("iff_period", "")
    if code and code == current:
        return "valid", f"IFF reply: OWN (code {code})"
    if code:
        return "invalid", f"IFF reply on code {code} — not current ({current})"
    return "none", "No IFF reply"


def recommend(world: "World", trk: Track) -> tuple[str, str]:
    """Doctrinal identity recommendation and its basis (shown to the player)."""
    if trk.id in world.hq.hostile or trk.id in world.hq.engage_ok:
        return "hostile", "designated by higher command"
    if trk.jammer:
        return "suspect", "Active jamming source"
    vid = world.vid_reports.get(trk.id)
    if vid:
        side, text = vid
        if side in ("civil", "neutral"):
            return "friend", f"VID: {text}"
        if side == world.own_side:
            return "friend", f"VID: {text}"
        return "suspect", f"VID: {text}"
    verdict, txt = iff_assessment(world, trk)
    if verdict == "valid":
        return "friend", txt
    if world.faction_def.id == "US":
        m = correlate(world, trk)
        good = [x for x in m if x.within]
        if good:
            g = good[0]
            return "friend", (f"Flight plan {g.callsign}: dT {g.dt_min:+.1f} min, {g.dist_nm:.0f} nm "
                              f"(tol ±5 min/{g.tol_nm:.0f} nm){' SIF match' if g.code_ok else ''}")
        if m:
            g = m[0]
            return "unknown", (f"Nearest plan {g.callsign} OUTSIDE tolerance: dT {g.dt_min:+.1f} min, "
                               f"{g.dist_nm:.0f} nm")
        if verdict == "invalid":
            return "unknown", txt
        return "unknown", "No flight plan correlation"
    # PVO: civil schedule correlation, otherwise unidentified
    m = correlate(world, trk)
    good = [x for x in m if x.within]
    if good:
        return "friend", f"Civil schedule {good[0].callsign} (Aeroflot dispatch)"
    if verdict == "invalid":
        return "unknown", txt
    return "unknown", "No IFF; no schedule match"


def auto_identify(world: "World") -> None:
    """Automated identification technician: applies safe recommendations after
    a short processing delay. Never declares suspect/hostile on its own."""
    delay = 40.0 if world.faction_def.id == "US" else 90.0
    for trk in world.tracks.values():
        if trk.lost or trk.identity != "pending" or world.t - trk.t_init < delay:
            continue
        ident, basis = recommend(world, trk)
        if ident not in ("friend", "unknown"):
            ident = "unknown"
        world.set_identity(trk.id, ident, f"auto: {basis}")


def zone_contains(world: "World", zone_id: str, x: float, y: float) -> bool:
    z = world.zones.get(zone_id)
    if z is None:
        return False
    if z["shape"] == "circle":
        return math.hypot(x - z["x"], y - z["y"]) <= z["r"]
    return point_in_poly(x, y, z["poly"])


def check_adiz(world: "World") -> None:
    adiz = [zid for zid, z in world.zones.items() if z.get("kind") == "adiz"]
    if not adiz:
        return
    for trk in world.tracks.values():
        if trk.lost or trk.adiz_t >= 0:
            continue
        if any(zone_contains(world, z, trk.x, trk.y) for z in adiz):
            trk.adiz_t = world.t
            truth = world.truth_of(trk)
            if truth:
                world.stats.adiz.setdefault(truth, world.t)
            if trk.identity in ("pending", "unknown"):
                world.alert(f"{trk.id} PENETRATING ADIZ — identity {trk.identity.upper()}", ref=trk.id,
                            priority=1)
