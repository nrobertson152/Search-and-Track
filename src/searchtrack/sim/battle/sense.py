"""What each side knows. Our air picture is the real one: radars, plots, tracks (tracking.py).
The enemy's air picture, and both sides' pictures of the other's ships, come from a lighter
sensor model built on the same physics: the radar horizon, a target's radar cross-section
(range goes with its fourth root), noise jamming that blinds the bearing it comes from, and
passive interception of radars that are switched on. A fleet that radiates gets found.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..flight import ground_velocity
from ..geo import angle_diff, bearing_deg, radar_horizon_km
from ..state import Contact
from .core import event

if TYPE_CHECKING:
    from ..world import World

SHIP_H = 30.0                       # height of a warship's superstructure above the sea (m)


def update(w: "World") -> None:
    _red_air(w)
    _surface(w, "red")
    _surface(w, w.own_side)
    _esm(w)
    _located(w)


# ------------------------------------------------------------------ sensors

def red_air_sensors(w: "World") -> list[tuple[str, float, float, float, float, float, float]]:
    """(name, x, y, antenna height m, range vs 5 m2 km, boresight or -1, half-cone deg)."""
    out = []
    for s in w.battle.red_sensors:
        out.append((s["name"], s["x"], s["y"], s["h"], s["range_km"], -1.0, 180.0))
    cat = w.catalog
    for sh in w.ships.values():
        if sh.side == w.own_side or sh.state in ("sunk", "crippled") or sh.emcon:
            continue
        for r in cat.ships[sh.type_id].radars:
            rt = cat.radars[r["type"]]
            out.append((sh.name, sh.x, sh.y, float(r.get("mast_m", 30.0)),
                        rt.ref_range_km * (5.0 / rt.ref_rcs_m2) ** 0.25, -1.0, 180.0))
    for a in w.aircraft.values():
        if a.state != "airborne" or a.side == w.own_side or a.side in ("civil", "neutral") or a.aim:
            continue
        at = cat.aircraft[a.type_id]
        if at.role == "awacs":
            out.append((a.callsign, a.x, a.y, a.alt, 330.0, -1.0, 180.0))
        elif at.ai_radar_km > 0:
            out.append((a.callsign, a.x, a.y, a.alt, at.ai_radar_km, a.hdg, at.ai_radar_cone))
    return out


def jam_factor(w: "World", sx: float, sy: float, tx: float, ty: float, jammers: list) -> float:
    """Noise jamming: a radar looking along a jammer's bearing sees only what burns through."""
    f = 1.0
    if not jammers:
        return f
    bt = bearing_deg(tx - sx, ty - sy)
    dt = math.hypot(tx - sx, ty - sy)
    for j in jammers:
        dj = math.hypot(j.x - sx, j.y - sy)
        if dj > 450.0:
            continue
        if abs(angle_diff(bearing_deg(j.x - sx, j.y - sy), bt)) < 12.0:
            burn = max(0.3, min(1.0, 0.3 + 0.7 * (dj / max(dt, 1.0) - 1.0) * 0.25)) if dt < dj else 0.3
            f = min(f, burn)
        else:
            f = min(f, 0.85)
    return f


def _rcs(w: "World", a) -> float:
    at = w.catalog.aircraft.get(a.type_id)
    return (at.rcs(90.0) if at else 5.0) * a.rcs_scale


def _red_air(w: "World") -> None:
    pic = w.battle.red_air
    sensors = red_air_sensors(w)
    jammers = [a for a in w.aircraft.values() if a.state == "airborne" and a.side == w.own_side and a.jamming]
    rng = w.rng
    for a in w.aircraft.values():
        if a.state != "airborne" or a.side != w.own_side or a.kind != "aircraft":
            continue
        rcs = max(_rcs(w, a), 0.05)
        seen, best_d = "", 0.0
        for name, sx, sy, h, r5, bore, cone in sensors:
            d = math.hypot(a.x - sx, a.y - sy)
            if d > r5 * 1.8:
                continue
            if bore >= 0 and abs(angle_diff(bearing_deg(a.x - sx, a.y - sy), bore)) > cone:
                continue
            if d > radar_horizon_km(h, a.alt):
                continue
            r = r5 * (rcs / 5.0) ** 0.25 * jam_factor(w, sx, sy, a.x, a.y, jammers)
            if a.alt < 300.0 and h < 2000.0:
                r *= 0.6                                         # sea clutter
            if d < r * 0.75 or (d < r and rng.random() < 0.5):
                seen, best_d = name, d
                break
        if seen:
            err = 0.5 + best_d * 0.008
            vx, vy = ground_velocity(w, a)
            c = pic.get(a.id)
            x, y = a.x + rng.gauss(0.0, err * 0.4), a.y + rng.gauss(0.0, err * 0.4)
            if c is None:
                pic[a.id] = Contact(a.id, x, y, a.alt, vx, vy, w.t, err, seen, "air", w.t)
            else:
                c.x, c.y, c.alt, c.vx, c.vy, c.t, c.err_km, c.by = x, y, a.alt, vx, vy, w.t, err, seen
    for k in [k for k, c in pic.items() if w.t - c.t > 45.0 or k not in w.aircraft
              or w.aircraft[k].state != "airborne"]:
        del pic[k]


def _surface(w: "World", side: str) -> None:
    """One side's picture of the other side's ships."""
    pic = w.battle.surface.setdefault(side, {})
    cat = w.catalog
    targets = [s for s in w.ships.values() if s.side != side and s.state != "sunk"]
    if not targets:
        pic.clear()
        return
    active: list[tuple[str, float, float, float, float]] = []      # name, x, y, h, range vs a cruiser
    passive: list[tuple[str, float, float, float, float]] = []     # ESM: name, x, y, h, range
    if side == w.own_side:
        for site in w.radars.values():
            if site.status in ("down", "maint"):
                continue
            rt = cat.radars[site.type_id]
            active.append((site.name, site.x, site.y, site.h_ant, min(rt.range_km, rt.ref_range_km * 4.0)))
        for sh in w.ships.values():
            if sh.side == side and sh.state not in ("sunk", "crippled"):
                passive.append((sh.name, sh.x, sh.y, 30.0, cat.ships[sh.type_id].esm_km))
    else:
        for s in w.battle.red_sensors:
            active.append((s["name"], s["x"], s["y"], s["h"], s["range_km"]))
        for sh in w.ships.values():
            if sh.side == side and sh.state not in ("sunk", "crippled") and not sh.emcon:
                active.append((sh.name, sh.x, sh.y, 35.0, 300.0))
    for a in w.aircraft.values():
        if a.state != "airborne" or a.side != side or a.aim:
            continue
        at = cat.aircraft[a.type_id]
        if at.surface_radar_km > 0:
            active.append((a.callsign, a.x, a.y, a.alt, at.surface_radar_km))
        if at.esm_km > 0:
            passive.append((a.callsign, a.x, a.y, a.alt, at.esm_km))
    for sh in targets:
        st = cat.ships[sh.type_id]
        size = (st.rcs_m2 / 10000.0) ** 0.25
        best = None
        for name, sx, sy, h, rng_km in active:
            d = math.hypot(sh.x - sx, sh.y - sy)
            if d <= min(rng_km * size, radar_horizon_km(h, SHIP_H)):
                if best is None or d < best[1]:
                    best = (name, d, False)
                if side != w.own_side and h > 500.0:
                    w.vars[f"emit_{name}"] = w.t                 # an airborne search radar is on the air
        radiating = not sh.emcon and sh.state not in ("crippled",)
        if best is None and radiating:
            for name, sx, sy, h, rng_km in passive:
                d = math.hypot(sh.x - sx, sh.y - sy)
                if d <= min(rng_km, radar_horizon_km(h, 40.0)):
                    best = (name, d, True)
                    break
        if best is None:
            continue
        name, d, is_passive = best
        err = 12.0 + d * 0.02 if is_passive else 1.0 + d * 0.006
        c = pic.get(sh.id)
        from math import cos, radians, sin
        vx, vy = sin(radians(sh.hdg)) * sh.spd / 1000.0, cos(radians(sh.hdg)) * sh.spd / 1000.0
        x, y = sh.x + w.rng.gauss(0.0, err * 0.3), sh.y + w.rng.gauss(0.0, err * 0.3)
        if c is None:
            pic[sh.id] = Contact(sh.id, x, y, 0.0, vx, vy, w.t, err, name, "ship", w.t, is_passive)
        elif is_passive and not c.passive and w.t - c.t < 120.0:
            c.t = w.t                                            # a fresh bearing confirms the older fix
        else:
            c.x, c.y, c.vx, c.vy, c.t, c.err_km, c.by, c.passive = x, y, vx, vy, w.t, err, name, is_passive
    for k in [k for k, c in pic.items() if w.t - c.t > 900.0 or k not in w.ships or w.ships[k].state == "sunk"]:
        del pic[k]


def _esm(w: "World") -> None:
    """Our ships and Hawkeyes hear enemy search radars come on the air."""
    for a in w.aircraft.values():
        if a.state != "airborne" or a.side == w.own_side or a.aim:
            continue
        if w.t - w.vars.get(f"emit_{a.callsign}", -1e9) > 10.0:
            continue
        key = f"esm_{a.group or a.id}"
        if w.t - w.vars.get(key, -1e9) < 400.0:
            continue
        at = w.catalog.aircraft[a.type_id]
        for o in list(w.ships.values()) + [x for x in w.aircraft.values() if x.side == w.own_side and
                                           x.state == "airborne" and w.catalog.aircraft[x.type_id].esm_km > 0]:
            if getattr(o, "side", "") != w.own_side or getattr(o, "state", "") in ("sunk",):
                continue
            esm = w.catalog.ships[o.type_id].esm_km if o.id in w.ships else w.catalog.aircraft[o.type_id].esm_km
            h = 30.0 if o.id in w.ships else o.alt
            d = math.hypot(a.x - o.x, a.y - o.y)
            if d <= min(esm, radar_horizon_km(h, a.alt)):
                w.vars[key] = w.t
                brg = bearing_deg(a.x - o.x, a.y - o.y)
                who = o.name if o.id in w.ships else o.callsign
                event(w, "esm", f"ESM: {at.name.split(' (')[0]} search radar on the air, bearing {brg:03.0f} "
                                f"from {who}", a.id, a.x, a.y, a.side, 2)
                break


def _located(w: "World") -> None:
    """The enemy has found our task group when its picture has held a ship of it for a while."""
    b = w.battle
    rp = b.red_plan
    if rp.get("located"):
        return
    enemy = "red" if w.own_side == "blue" else "blue"
    pic = b.surface.get(enemy, {})
    tgt = rp.get("target", "")
    for sid, c in pic.items():
        sh = w.ships.get(sid)
        if sh is None or (tgt and sh.group != tgt and sh.id != tgt):
            continue
        held = w.t - c.t_first
        if (held >= (150.0 if c.passive else 75.0)) and w.t - c.t < 30.0:
            rp["located"] = True
            rp["t_located"] = w.t
            rp["by"] = c.by
            event(w, "located", f"The enemy has found the task group ({c.by} holds {sh.name})", sh.id, sh.x, sh.y,
                  enemy, -1)
            if c.by.startswith("BEAR") or "BEAR" in c.by:
                event(w, "esm", f"ESM: burst transmission from {c.by} — they have our position", sh.id,
                      sh.x, sh.y, w.own_side, 2)
            return
