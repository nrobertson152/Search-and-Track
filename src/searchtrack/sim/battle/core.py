"""Battle setup from the scenario, the per-tick hooks, battle events and the end."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ..state import Airbase, Ship

if TYPE_CHECKING:
    from ..world import World

KN = 0.514444                        # m/s per knot

DEFAULT_STANDING: dict[str, Any] = {
    "posture": "balanced",           # aggressive | balanced | defensive: how far out fighters are committed
    "fighters": "auto",              # auto | manual: the staff commits interceptors on its own
    "sam": "FREE",                   # FREE | TIGHT | HOLD: missile units fire on their own
    "emcon": False,                  # ships' radars silent
    "reserve": 2,                    # interceptors the staff keeps on deck / on alert
}

# event levels: 0 log only, 1 notable, 2 important (alert, slows the clock), 3 critical (banner)


def event(w: "World", kind: str, text: str, ref: str = "", x: Optional[float] = None, y: Optional[float] = None,
          side: str = "", level: int = 1) -> None:
    """Something happened that the display, the log and the unit stories should know about."""
    b = w.battle
    b.events.append([round(w.t, 1), kind, text, ref, None if x is None else round(x, 2),
                     None if y is None else round(y, 2), side, level])
    if level >= 1 and kind not in ("phase",):
        b.t_last_event = w.t
    w.log_event("battle", text, ref)


def enemy_of(side: str) -> str:
    return "red" if side == "blue" else "blue"


def spec_xy(w: "World", spec: Any) -> tuple[float, float]:
    """A position given as {lat, lon} or {x, y} or [x, y]."""
    if isinstance(spec, (list, tuple)):
        return float(spec[0]), float(spec[1])
    if "lat" in spec:
        return w.theater.xy(spec["lat"], spec["lon"])
    return float(spec["x"]), float(spec["y"])


def alt_of(spec: dict, default: float = 0.0) -> float:
    if "alt_m" in spec:
        return float(spec["alt_m"])
    if "alt_ft" in spec:
        return float(spec["alt_ft"]) * 0.3048
    return default


def counter(w: "World", key: str, n: float = 1.0) -> None:
    w.battle.counters[key] = w.battle.counters.get(key, 0.0) + n


# ------------------------------------------------------------------ setup

def setup(w: "World", sc: dict) -> None:
    from . import air, naval
    bd = sc.get("battle", {})
    b = w.battle
    b.active = True
    b.spectator = bool(bd.get("spectator", False))
    b.post, b.post_sub = bd.get("post", ""), bd.get("post_sub", "")
    b.standing = dict(DEFAULT_STANDING, **bd.get("standing", {}))
    b.phases = [dict(p) for p in bd.get("phase", [])]
    b.defended = list(bd.get("defended", []))
    b.red_plan = {"target": bd.get("red_target", ""), "located": False, "t_located": -1.0}
    if "hostile_west_of_lon" in bd:
        lat = bd.get("hostile_line_lat", w.theater.proj.lat0)
        b.red_plan["hostile_x"] = w.theater.xy(lat, bd["hostile_west_of_lon"])[0]
    if "hostile_north_of_lat" in bd:
        b.red_plan["hostile_y"] = w.theater.xy(bd["hostile_north_of_lat"], w.theater.proj.lon0)[1]
    if "brief_target" in bd:
        b.red_plan["brief"] = list(spec_xy(w, bd["brief_target"]))
    b.red_plan["vital"] = list(bd.get("vital", []))
    if "view" in bd:
        vx, vy = spec_xy(w, bd["view"])
        b.view = [vx, vy, float(bd["view"].get("km", 900.0))]
    for s in bd.get("red_sensor", []):
        x, y = spec_xy(w, s)
        b.red_sensors.append({"name": s.get("name", "radar"), "x": x, "y": y, "h": float(s.get("mast_m", 30.0)),
                              "range_km": float(s.get("range_km", 300.0))})
    for sq in w.squadrons.values():
        w.vars[f"sq_strength_{sq.id}"] = float(sum(sq.ready.values()) + sq.maint)
    for spec in sc.get("ship", []):
        naval.add_ship(w, spec)
    for sh in w.ships.values():
        st = w.catalog.ships[sh.type_id]
        if st.kind == "carrier" and sh.id not in w.airbases:
            w.airbases[sh.id] = Airbase(sh.id, sh.name, sh.x, sh.y, 20.0, sh.side, "carrier", True, "",
                                        carrier=sh.id)
    for spec in sc.get("group", []):
        air.add_group(w, spec)
    for c in bd.get("cap", []):
        x, y = spec_xy(w, c)
        b.cap_stations.append({"id": c["id"], "name": c.get("name", c["id"]), "x": x, "y": y,
                               "alt": alt_of(c, 9000.0), "squadron": c["squadron"], "n": int(c.get("n", 2)),
                               "flight": "", "relief": "", "on": bool(c.get("on", True))})
    for st in b.cap_stations:
        c = next(c for c in bd.get("cap", []) if c["id"] == st["id"])
        if c.get("airborne"):
            _airborne_cap(w, st, float(c.get("fuel_frac", 0.8)))
    for r in bd.get("reinforcement", []):
        b.reinforcements.append(dict(r, available=bool(r.get("available", False)), called=False))
    if bd.get("war", True):
        w.hq.weapons_status = bd.get("weapons_status", "FREE")
        w.vars["war"] = 1.0


def _airborne_cap(w: "World", st: dict, fuel_frac: float) -> None:
    """A combat air patrol already on station when the battle opens."""
    from .. import gci
    from ..geo import heading_vec
    ok, msg, fid = gci.scramble(w, st["squadron"], st["n"], "cap", alt=st["alt"])
    if not ok:
        return
    fl = w.flights[fid]
    gci.launch(w, fl)
    fl.t_airborne = w.t
    at = w.catalog.aircraft[fl.type_id]
    for i, mid in enumerate(fl.members):
        a = w.aircraft[mid]
        hx, hy = heading_vec(90.0 * i)
        a.x, a.y, a.alt = st["x"] + hx * 1.5 * i, st["y"] + hy * 1.5 * i, st["alt"]
        a.spd, a.fuel = 230.0, at.fuel_kg * fuel_frac
    fl.state, fl.cap_x, fl.cap_y, fl.order_alt, fl.weapons_free = "cap", st["x"], st["y"], st["alt"], True
    st["flight"] = fid


# ------------------------------------------------------------------ the tick

def pre_step(w: "World", dt: float) -> None:
    """Before aircraft move: director, commanders, air groups, ships."""
    from . import air, director, naval, staff
    director.step(w)
    naval.carry(w)
    for sh in list(w.ships.values()):
        naval.ship_step(w, sh, dt)
    for g in list(w.battle.groups.values()):
        air.group_step(w, g, dt)
    if w.tick % 5 == 2:
        air.red_command(w)
    if w.tick % 3 == 0:
        staff.step(w)
    staff.decisions_step(w)
    for site in list(w.sams.values()):
        if site.side != w.own_side:
            naval.red_sam_step(w, site, dt)


def mid_step(w: "World", dt: float) -> None:
    """After the fighter controllers have given their orders, before aircraft move."""
    from . import combat, land, naval
    combat.evasion_step(w)
    naval.asm_guidance(w, dt)
    land.guidance(w, dt)


def post_step(w: "World", dt: float) -> None:
    """After everything moved and the radars swept."""
    from . import land, naval, sense
    naval.asm_impacts(w)
    land.impacts(w)
    land.step(w)
    naval.ship_defense(w)
    if w.tick % 4 == 0:
        sense.update(w)
    _check_end(w)


# ------------------------------------------------------------------ the end

def _check_end(w: "World") -> None:
    b = w.battle
    if w.ended:
        return
    if w.t >= w.duration - 1.5:
        finish(w)
        return
    if b.end_t > 0:
        if w.t >= b.end_t:
            finish(w)
        return
    for sid in b.red_plan.get("vital", []):
        sh = w.ships.get(sid)
        if sh is not None and sh.state == "sunk":
            event(w, "end", f"{sh.name} has gone down. The battle is lost.", sh.id, sh.x, sh.y, sh.side, 3)
            b.end_t = w.t + 45.0
            return
    if b.phases and b.phase >= len(b.phases) - 1 and w.t - b.t_phase > 180.0:
        if _quiet(w):
            event(w, "end", "The last raiders are leaving. Recovering aircraft; the battle is over.", "", level=2)
            b.end_t = w.t + 60.0


def _quiet(w: "World") -> bool:
    enemy = "red" if w.own_side == "blue" else "blue"
    for g in w.battle.groups.values():
        if g.side == enemy and g.state not in ("done", "pending", "egress", "rtb"):
            return False
        if g.side != enemy and g.role == "strike" and g.state in ("outbound", "attack"):
            return False
    for ac in w.aircraft.values():
        if ac.state == "airborne" and ac.aim:          # anti-ship missiles still flying
            return False
    return all(m.state != "flying" for m in w.missiles.values())


def outcome(w: "World") -> str:
    from ..scenario import score
    got, total, _ = score(w)
    pct = got / max(total, 1)
    if any(w.ships[s].state == "sunk" for s in w.battle.red_plan.get("vital", []) if s in w.ships):
        return "DEFEAT"
    return "VICTORY" if pct >= 0.7 else "DRAW" if pct >= 0.4 else "DEFEAT"


def finish(w: "World") -> None:
    from ..scenario import end
    b = w.battle
    if w.ended:
        return
    end(w, "Battle over", "complete")
    b.outcome = outcome(w)
    event(w, "end", f"BATTLE OVER — {b.outcome}", "", level=3)


def own_ships(w: "World") -> list[Ship]:
    return [s for s in w.ships.values() if s.side == w.own_side and s.state != "sunk"]
