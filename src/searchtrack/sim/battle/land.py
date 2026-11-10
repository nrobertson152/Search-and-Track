"""Strikes on the ground: installations, land-attack cruise missiles, glide bombs and
anti-radiation missiles.

An installation is what the radar war is fought over -- a radar company, a missile
battalion's fire-control radar, an airfield's runway. Cruise missiles fly a preplanned route
low over the terrain and pop up onto a fixed point; glide bombs fall from the strike
aircraft onto it; anti-radiation missiles home on radars that are switched on and coast to
the last place they heard one if it goes quiet. What gets hit changes the battle: a radar
that is down leaves a hole in the picture, a cratered runway launches nobody until it is
filled in, a battalion without its radar fires no more. Missile crews know this: when an
anti-radiation missile is reported inbound they may switch off and wait.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..geo import bearing_deg, heading_vec
from ..state import Aircraft, Transponder
from .core import counter, event, spec_xy

if TYPE_CHECKING:
    from ..world import World

GROUND_PROFILES = ("terrain", "arm", "glide")    # handled here, not by the anti-ship code
LAND_KINDS = ("lam",)                            # weapon kinds that strike a fixed point


def profile_of(w: "World", m: Aircraft) -> str:
    mt = w.catalog.aircraft.get(m.type_id)
    return mt.profile if mt is not None else ""


def is_ground_weapon(w: "World", m: Aircraft) -> bool:
    return profile_of(w, m) in GROUND_PROFILES


# ------------------------------------------------------------------ installations

def installation(w: "World", iid: str) -> Optional[tuple[str, float, float, str, str]]:
    """(kind, x, y, name, side) of a fixed ground target, or None."""
    if iid in w.airbases and not w.airbases[iid].carrier:
        b = w.airbases[iid]
        return "airbase", b.x, b.y, b.name, b.side
    if iid in w.sams and not w.sams[iid].carrier:
        s = w.sams[iid]
        return "sam", s.x, s.y, s.unit or s.name, s.side
    if iid in w.radars and not w.radars[iid].carrier:
        r = w.radars[iid]
        return "radar", r.x, r.y, r.name, w.own_side
    return None


def installations(w: "World", side: str) -> list[tuple[str, str, float, float, str]]:
    """(kind, id, x, y, name) of a side's fixed ground targets."""
    out = []
    for iid in list(w.airbases) + list(w.sams) + list(w.radars):
        it = installation(w, iid)
        if it is not None and it[4] == side and (it[0] != "airbase" or w.airbases[iid].kind == "military"):
            out.append((it[0], iid, it[1], it[2], it[3]))
    return out


def is_out(w: "World", iid: str) -> bool:
    """Destroyed or out of action at the moment."""
    if iid in w.airbases:
        return not w.airbases[iid].runway_ok
    if iid in w.sams:
        return w.sams[iid].status != "ok"
    if iid in w.radars:
        return w.radars[iid].status == "down"
    return False


def is_destroyed(w: "World", iid: str) -> bool:
    return bool(w.vars.get(f"dead_{iid}"))


def hit_installation(w: "World", iid: str, weapon: str, heavy: float = 1.0, side_by: str = "") -> None:
    """A warhead lands on a radar, a missile battalion or a runway."""
    it = installation(w, iid)
    if it is None:
        return
    kind, x, y, name, side = it
    rng = w.rng
    t = w.t
    own = side == w.own_side
    counter(w, f"ground_hits_{side}")
    if kind == "airbase":
        b = w.airbases[iid]
        key = f"runway_{iid}"
        was_open = b.runway_ok
        if was_open or key not in w.vars:
            closed_until = t + rng.uniform(9.0, 15.0) * 60.0 * heavy
        else:                                          # more craters: the repair teams work in parallel
            closed_until = min(w.vars[key] + rng.uniform(2.0, 4.0) * 60.0 * heavy, t + 40.0 * 60.0)
        w.vars[key] = max(closed_until, w.vars.get(key, 0.0))
        b.runway_ok = False
        lost = 0
        for sq in w.squadrons.values():                # aircraft caught on the ground
            if sq.base_id == iid:
                for k in list(sq.ready):
                    if sq.ready[k] > 0 and rng.random() < 0.18 * heavy:
                        sq.ready[k] -= 1
                        sq.lost += 1
                        lost += 1
        if lost:
            counter(w, f"aircraft_lost_{side}", lost)
        mins = (w.vars[key] - t) / 60.0
        txt = f"{name.upper()} HIT by {weapon} — runway cratered, closed for about {mins:.0f} min" + \
            (f", {lost} aircraft destroyed on the ground" if lost else "")
        loud = was_open or t - w.vars.get(f"hitmsg_{iid}", -1e9) > 90.0
        w.vars[f"hitmsg_{iid}"] = t
        event(w, "ground_hit", txt if was_open else f"{name.upper()} hit again by {weapon} — "
              f"repairs now about {mins:.0f} min", iid, x, y, side, (3 if own else 1) if loud else 0)
        if was_open:
            counter(w, f"runway_cuts_{side}")
        return
    destroyed = rng.random() < 0.5 * heavy
    if kind == "sam":
        s = w.sams[iid]
        s.status = "down"
        s.state, s.lock, s.assigned, s.salvo_left = "idle", "", "", 0
        w.vars.pop(f"shut_{iid}", None)
        if destroyed:
            w.vars[f"dead_{iid}"] = 1.0
            s.ready_missiles = 0
            event(w, "ground_hit", f"{name.upper()} HIT by {weapon} — fire-control radar destroyed", iid, x, y, side,
                  3 if own else 1)
            counter(w, f"sams_destroyed_{side}")
        else:
            back = rng.uniform(10.0, 20.0)
            w.vars[f"sam_repair_{iid}"] = t + back * 60.0
            event(w, "ground_hit", f"{name.upper()} HIT by {weapon} — off the air, repairs about {back:.0f} min",
                  iid, x, y, side, 3 if own else 1)
        return
    r = w.radars[iid]
    for hf in w.hfs.values():
        if hf.site_id == iid and destroyed:
            hf.status = "down"
    r.status = "down"
    r.degraded_db = 0.0
    if destroyed:
        w.vars[f"dead_{iid}"] = 1.0
        r.repair_t = -1.0
        r.fail_t = 1e12
        event(w, "ground_hit", f"{name.upper()} HIT by {weapon} — radar destroyed", iid, x, y, side, 3 if own else 1)
        counter(w, f"radars_destroyed_{side}")
    else:
        back = rng.uniform(12.0, 25.0)
        r.repair_t = t + back * 60.0
        event(w, "ground_hit", f"{name.upper()} HIT by {weapon} — antenna damaged, off the air about {back:.0f} min",
              iid, x, y, side, 3 if own else 1)
    if own and w.faction == "USSR":
        w.alert(f"{r.name}: NO REPORTS — station hit", iid, 2)


def step(w: "World") -> None:
    """Repairs, and missile crews switching off when an anti-radiation missile comes for them."""
    t = w.t
    if w.tick % 5 == 0:
        for b in w.airbases.values():
            key = f"runway_{b.id}"
            if not b.runway_ok and key in w.vars and t >= w.vars[key]:
                del w.vars[key]
                b.runway_ok = True
                event(w, "repair", f"{b.name}: craters filled — runway open", b.id, b.x, b.y, b.side,
                      2 if b.side == w.own_side else 0)
        for s in w.sams.values():
            for key, what in ((f"sam_repair_{s.id}", "repaired"), (f"shut_{s.id}", "radiating again")):
                if key in w.vars and t >= w.vars[key]:
                    del w.vars[key]
                    if not is_destroyed(w, s.id) and s.status == "down" and \
                            not any(k in w.vars for k in (f"sam_repair_{s.id}", f"shut_{s.id}")):
                        s.status = "ok"
                        if s.side == w.own_side:
                            event(w, "repair", f"{s.unit or s.name}: {what}", s.id, s.x, s.y, s.side, 0)
    if w.tick % 3 == 1:
        _arm_drill(w)


def _arm_drill(w: "World") -> None:
    """ESM hears the missile's launch platform and the battalion goes off the air for a minute."""
    for m in w.aircraft.values():
        if m.state != "airborne" or not m.aim or not m.homing.startswith("S:"):
            continue
        sid = m.homing[2:]
        s = w.sams.get(sid)
        if s is None or s.status != "ok" or s.carrier:
            continue
        d = math.hypot(s.x - m.x, s.y - m.y)
        key = f"drill_{m.id}"
        if d > 35.0 or key in w.vars:
            continue
        w.vars[key] = 1.0
        if w.rng.random() < 0.55:
            s.status = "down"
            s.state, s.lock, s.salvo_left = "idle", "", 0
            w.vars[f"shut_{sid}"] = w.t + w.rng.uniform(45.0, 75.0)
            event(w, "shutdown", f"{s.unit or s.name}: anti-radiation missile inbound — radar OFF", sid, s.x, s.y,
                  s.side, 2 if s.side == w.own_side else 0)


# ------------------------------------------------------------------ emitters

def emitters(w: "World", side: str) -> list[tuple[str, float, float, float, str]]:
    """(ref, x, y, priority, label) of radars of `side` that are radiating right now."""
    out = []
    if side == w.own_side:
        for r in w.radars.values():
            if r.status not in ("ok", "degraded"):
                continue
            ac = w.aircraft.get(r.carrier) if r.carrier else None
            if ac is not None:
                continue                                   # airborne radars: not an ARM target here
            prio = 2.0 if r.carrier else 1.0
            out.append((f"R:{r.id}", r.x, r.y, prio, r.unit or r.name))
    for s in w.sams.values():
        if s.side != side or s.status != "ok":
            continue
        if s.state in ("locked", "engaging", "assess"):
            out.append((f"S:{s.id}", s.x, s.y, 4.0 if s.state == "engaging" else 3.0, s.unit or s.name))
        elif s.state == "search":
            out.append((f"S:{s.id}", s.x, s.y, 2.5, s.unit or s.name))
    if side != w.own_side:
        for sh in w.ships.values():
            if sh.side == side and not sh.emcon and sh.state not in ("sunk", "crippled"):
                out.append((f"H:{sh.id}", sh.x, sh.y, 1.5, sh.name))
    return out


def emitter_state(w: "World", ref: str) -> tuple[Optional[float], Optional[float], bool, str]:
    """Where an emitter is and whether it is on the air."""
    kind, iid = ref[:1], ref[2:]
    if kind == "R":
        r = w.radars.get(iid)
        if r is None:
            return None, None, False, ""
        return r.x, r.y, r.status in ("ok", "degraded"), r.unit or r.name
    if kind == "S":
        s = w.sams.get(iid)
        if s is None:
            return None, None, False, ""
        return s.x, s.y, s.status == "ok" and s.state != "idle", s.unit or s.name
    if kind == "H":
        sh = w.ships.get(iid)
        if sh is None:
            return None, None, False, ""
        return sh.x, sh.y, not sh.emcon and sh.state not in ("sunk", "crippled"), sh.name
    return None, None, False, ""


# ------------------------------------------------------------------ launching

def launch(w: "World", shooter: Optional[Aircraft], wid: str, aim: tuple[float, float], owner: str, side: str,
           homing: str = "", route: Optional[list] = None, start: Optional[tuple] = None,
           hdg: Optional[float] = None) -> Aircraft:
    """A land-attack missile, glide bomb or anti-radiation missile leaves its launcher."""
    wt = w.catalog.weapons[wid]
    mt = w.catalog.aircraft[wt.missile]
    n = w.next_id("asm")
    x, y, alt = (shooter.x, shooter.y, shooter.alt) if shooter is not None else start
    first = route[0] if route else aim
    hdg = bearing_deg(first[0] - x, first[1] - y) if hdg is None else hdg
    v = mt.cruise_kmh / 3600.0
    total = math.hypot(first[0] - x, first[1] - y)
    pts = (route or []) + [aim]
    for a, b in zip(pts, pts[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    spd0 = max(shooter.spd if shooter is not None else 0.0, mt.min_kmh / 3.6)
    m = Aircraft(id=f"V{n}", type_id=mt.id, callsign=f"{wt.id} {n}", side=side, x=x, y=y,
                 alt=max(alt - 100.0, 40.0) if mt.profile != "arm" else alt + 200.0, hdg=hdg, spd=spd0,
                 fuel=mt.fuel_kg, throttle="mil", transponder=Transponder("none", False), truth_label=mt.name,
                 nationality=shooter.nationality if shooter is not None else "", aim=[aim[0], aim[1]],
                 launcher=owner, homing=homing, t_max=w.t + total * 1.4 / max(v, 0.05) + 90.0, t_spawn=w.t)
    m.route = [list(p) for p in (route or [])]
    m.cmd_hdg, m.cmd_alt = hdg, (mt.cruise_alt_m if mt.profile != "glide" else m.alt)
    w.aircraft[m.id] = m
    counter(w, f"fired_{mt.id}")
    counter(w, f"{wt.kind}_{side}")
    if homing.startswith(("R:", "S:", "H:")):
        w.vars[f"arm_{m.id}"] = w.t
    return m


def salvo(w: "World", a: dict) -> int:
    """Ship- or submarine-launched cruise missiles arriving from beyond the map, in a stream."""
    side = a.get("side", "red" if w.own_side == "blue" else "blue")
    wid = a["weapon"]
    x0, y0 = spec_xy(w, a["from"])
    route = [list(spec_xy(w, p)) for p in a.get("route", [])]
    targets = [t for t in a.get("targets", []) if installation(w, t) is not None]
    if not targets:
        return 0
    n = int(a.get("n", len(targets)))
    gap = float(a.get("stream_km", 10.0))
    first = route[0] if route else installation(w, targets[0])[1:3]
    hdg = bearing_deg(first[0] - x0, first[1] - y0)
    hx, hy = heading_vec(hdg)
    for i in range(n):
        it = installation(w, targets[i % len(targets)])
        jit = w.rng.uniform(-0.25, 0.25)
        aim = (it[1] + jit, it[2] - jit)
        back = i * gap
        lat = w.rng.uniform(-4.0, 4.0)
        start = (x0 - hx * back + hy * lat, y0 - hy * back - hx * lat, 60.0)
        launch(w, None, wid, aim, a.get("owner", "salvo"), side, route=[list(p) for p in route], start=start,
               hdg=hdg)
    if side != w.own_side:
        event(w, "salvo", f"[enemy] {n} {wid} launched from beyond the horizon", "", x0, y0, side, -1)
    return n


# ------------------------------------------------------------------ in flight

def guidance(w: "World", dt: float) -> None:
    from ..flight import terrain_follow_alt
    cat = w.catalog
    for m in list(w.aircraft.values()):
        if m.state != "airborne" or not m.aim:
            continue
        mt = cat.aircraft[m.type_id]
        if mt.profile not in GROUND_PROFILES:
            continue
        if w.t > m.t_max > 0:
            m.state = "gone"
            event(w, "asm_miss", f"{m.callsign}: fuel exhausted, crashed short", m.id, m.x, m.y, m.side, 0)
            continue
        if mt.profile == "arm":
            _arm_guidance(w, m, mt)
            continue
        if m.route:
            tx, ty = m.route[0]
            if math.hypot(tx - m.x, ty - m.y) < 3.0:
                m.route.pop(0)
                continue
        else:
            tx, ty = m.aim
        d = math.hypot(m.aim[0] - m.x, m.aim[1] - m.y)
        m.cmd_hdg = bearing_deg(tx - m.x, ty - m.y)
        m.cmd_spd = None
        m.throttle = "mil"
        if mt.profile == "terrain":
            ground = w.ground_height(m.x, m.y)
            if m.route or d > 7.0:
                m.cmd_alt = terrain_follow_alt(w, m, mt.cruise_alt_m)
            elif d > 2.5:
                m.cmd_alt = ground + 300.0                    # pop up to find the aim point
            else:
                m.cmd_alt = ground                            # and dive
        else:                                                 # glide: a straight descent onto the aim point
            ground = w.ground_height(m.aim[0], m.aim[1])
            step = max(m.spd * dt / 1000.0, 0.05)
            m.cmd_alt = max(ground, m.alt - (m.alt - ground) * step / max(d, step))


def _arm_guidance(w: "World", m: Aircraft, mt) -> None:
    x, y, on, _ = emitter_state(w, m.homing)
    if x is not None and on:
        m.aim = [x, y]
        w.vars[f"arm_{m.id}"] = w.t
    d = math.hypot(m.aim[0] - m.x, m.aim[1] - m.y)
    m.cmd_hdg = bearing_deg(m.aim[0] - m.x, m.aim[1] - m.y)
    dive = max(mt.cruise_alt_m / 1000.0 * 2.2, 8.0)
    m.cmd_alt = mt.cruise_alt_m if d > dive else max(0.0, mt.cruise_alt_m * (d / dive) ** 1.2)
    m.cmd_spd = None
    m.throttle = "mil"


def impacts(w: "World") -> None:
    cat = w.catalog
    for m in list(w.aircraft.values()):
        if m.state != "airborne" or not m.aim:
            continue
        mt = cat.aircraft[m.type_id]
        if mt.profile not in GROUND_PROFILES or m.route:
            continue
        step_km = m.spd / 1000.0 * 1.3
        d = math.hypot(m.aim[0] - m.x, m.aim[1] - m.y)
        if d > max(0.6, step_km):
            continue
        ground = w.ground_height(m.x, m.y)
        if m.alt - ground > (2500.0 if mt.profile == "arm" else 600.0):
            continue
        m.state = "gone"
        if mt.profile == "arm":
            _arm_impact(w, m, mt)
        else:
            _warhead(w, m, mt)


def _warhead(w: "World", m: Aircraft, mt) -> None:
    ax, ay = m.aim
    best, bd = None, 2.0
    for iid in list(w.airbases) + list(w.sams) + list(w.radars):
        it = installation(w, iid)
        if it is None or it[4] == m.side:
            continue
        d = math.hypot(it[1] - ax, it[2] - ay)
        if d < bd:
            best, bd = iid, d
    name = mt.name.split(" (")[0]
    short = {"TLAM-C": "Tomahawk", "WALLEYE": "Walleye", "AS-15": "Kh-55"}.get(mt.id, mt.id)
    if best is None:
        event(w, "impact", f"{m.callsign} impacts in open ground", m.id, ax, ay, m.side, 0)
        return
    heavy = min(1.4, 0.6 + mt.warhead_kg / 900.0)
    if w.rng.random() < 0.88:
        counter(w, f"lam_hits_{m.side}")
        hit_installation(w, best, short, heavy)
    else:
        event(w, "impact", f"{name} falls wide of {installation(w, best)[3]}", m.id, ax, ay, m.side, 1)


def _arm_impact(w: "World", m: Aircraft, mt) -> None:
    heard = w.t - w.vars.pop(f"arm_{m.id}", -1e9)
    w.vars.pop(f"drill_{m.id}", None)
    x, y, on, label = emitter_state(w, m.homing)
    if x is None:
        return
    miss_km = math.hypot(x - m.x, y - m.y)
    p = 0.8 if (on and heard < 6.0) else 0.3 if heard < 40.0 else 0.08
    if miss_km > 1.5 or w.rng.random() > p:
        event(w, "impact", f"HARM misses {label} — the radar was off the air" if not on else
              f"Anti-radiation missile misses {label}", m.id, m.x, m.y, m.side, 1 if m.side != w.own_side else 0)
        return
    counter(w, f"arm_hits_{m.side}")
    kind, iid = m.homing[:1], m.homing[2:]
    if kind == "R" and iid in w.radars and w.radars[iid].carrier in w.ships:
        from .naval import damage_ship
        r = w.radars[iid]
        sh = w.ships[r.carrier]
        r.status, r.repair_t = "down", w.t + w.rng.uniform(15.0, 30.0) * 60.0
        event(w, "ground_hit", f"{sh.name}: {r.type_id} radar knocked out by an anti-radiation missile", iid,
              sh.x, sh.y, sh.side, 2)
        damage_ship(w, sh, mt.warhead_kg * 0.06, "anti-radiation missile", m.launcher)
        return
    if kind == "H":
        from .naval import damage_ship
        sh = w.ships[iid]
        damage_ship(w, sh, mt.warhead_kg * 0.09, "anti-radiation missile", m.launcher)
        for r in w.radars.values():
            if r.carrier == iid and r.status != "down" and w.rng.random() < 0.6:
                r.status, r.repair_t = "down", w.t + w.rng.uniform(15.0, 30.0) * 60.0
                event(w, "ground_hit", f"{sh.name}: {r.type_id} radar knocked out", iid, sh.x, sh.y, sh.side, 2)
                break
        return
    if kind == "S" and w.sams.get(iid) is not None and w.sams[iid].carrier:
        s = w.sams[iid]
        s.status = "down"
        s.state, s.lock = "idle", ""
        sh = w.ships.get(s.carrier)
        if sh is not None:
            from .naval import damage_ship
            damage_ship(w, sh, mt.warhead_kg * 0.09, "anti-radiation missile", m.launcher)
        return
    hit_installation(w, iid, "HARM", 0.9)
