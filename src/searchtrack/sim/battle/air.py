"""Air groups flown by the battle AI, for either side.

Every group has a role and works from its own side's picture: a raid flies to where its
side believes the target is and releases from outside the defences; escorts stay with the
raid and turn on fighters that come for it; sweeps hunt the other side's radar aircraft;
recon finds the fleet and shadows it; jammers hold a stand-off orbit; early-warning aircraft
orbit and pull back when fighters come for them. All of them watch their fuel, turn back
when the formation has been cut up, defend against missiles and go home when empty.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..flight import cruise_speed, fuel_flow
from ..geo import bearing_deg, heading_vec
from ..state import AirGroup, Aircraft, RadarSite, Transponder
from ..tracking import predicted, truth_of
from . import combat, naval
from .core import alt_of, counter, event, spec_xy

if TYPE_CHECKING:
    from ..world import World

ROLE_WEIGHT = {"awacs": 3.0, "ew": 2.6, "strike": 2.4, "bomber": 2.4, "recon": 2.2, "tanker": 1.6,
               "interceptor": 1.0, "fighter": 1.0, "patrol": 1.5}


# ------------------------------------------------------------------ setup

def add_group(w: "World", spec: dict) -> AirGroup:
    at = w.catalog.aircraft[spec["type"]]
    side = spec.get("side", "red")
    role = spec.get("role", {"interceptor": "sweep", "bomber": "strike"}.get(at.role, at.role))
    g = AirGroup(id=spec["id"], name=spec.get("name", spec["id"]), callsign=spec.get("callsign", spec["id"].upper()),
                 side=side, role=role, type_id=at.id, n=int(spec.get("n", 1)), base=spec.get("base", ""),
                 target=spec.get("target", ""), launch_km=float(spec.get("launch_km", 0.0)),
                 commit_km=float(spec.get("commit_km", 70.0)), alt=alt_of(spec, at.cruise_alt_m),
                 spd_kmh=float(spec.get("kmh", 0.0)), abort_frac=float(spec.get("abort_frac", 0.5)),
                 jam=bool(spec.get("jam", role == "ew")), trigger=spec.get("trigger", ""), note=spec.get("note", ""))
    if "entry" in spec:
        x, y = spec_xy(w, spec["entry"])
        g.entry = [x, y, alt_of(spec["entry"], g.alt)]
    if "exit" in spec:
        g.exit = list(spec_xy(w, spec["exit"]))
    g.route = [[*spec_xy(w, p), alt_of(p, g.alt)] for p in spec.get("route", [])]
    if "station" in spec:
        s = spec["station"]
        g.station = [*spec_xy(w, s), alt_of(s, g.alt), float(s.get("r_km", 25.0))]
    if "t_min" in spec:
        g.t_launch = float(spec["t_min"]) * 60.0
    elif not g.trigger:
        g.t_launch = 0.0
    g.aim = list(spec_xy(w, spec["aim"])) if "aim" in spec else []
    w.vars[f"loadout_{g.id}"] = 0.0
    if spec.get("weapons") is not None:
        w.battle.red_plan.setdefault("loadouts", {})[g.id] = dict(spec["weapons"])
    if spec.get("radar"):
        rt = w.catalog.radars[spec["radar"]]
        rid = f"{g.id}-R"
        site = RadarSite(id=rid, name=f"{g.callsign} ({at.id})", type_id=rt.id, x=0.0, y=0.0, elev=0.0, mast_m=0.0,
                         unit=g.name, status="down", az=w.rng.uniform(0, 360), rpm=rt.rpm, mti=rt.mti,
                         link=spec.get("link", ""), carrier=f"{g.id}-1", bias_r=0.0, bias_az=0.0)
        site.fail_t = 1e12
        w.radars[rid] = site
    w.battle.groups[g.id] = g
    return g


def _home(w: "World", g: AirGroup) -> tuple[float, float]:
    if g.base and g.base in w.airbases:
        b = w.airbases[g.base]
        return b.x, b.y
    if g.exit:
        return g.exit[0], g.exit[1]
    if g.entry:
        return g.entry[0], g.entry[1]
    return 0.0, 0.0


def launch(w: "World", g: AirGroup) -> None:
    at = w.catalog.aircraft[g.type_id]
    if g.entry:
        x, y, alt = g.entry                 # already airborne when the battle opens, or entering at the edge
    elif g.base and g.base in w.airbases:
        b = w.airbases[g.base]
        if not b.runway_ok:
            g.state = "done"
            event(w, "abort", f"{g.name}: cannot launch — {b.name} out of action", g.id, b.x, b.y, g.side, 1)
            return
        x, y, alt = b.x, b.y, 300.0
    else:
        x, y, alt = 0.0, 0.0, g.alt
    tx, ty = (g.route[0][0], g.route[0][1]) if g.route else (g.station[0], g.station[1]) if g.station else \
        (g.aim[0], g.aim[1]) if g.aim else (x + 1.0, y)
    hdg = bearing_deg(tx - x, ty - y)
    loadout = w.battle.red_plan.get("loadouts", {}).get(g.id, at.weapons)
    if g.side == w.own_side:
        valid = w.hq.policy.get("mode1_valid", ["00"])
        codes = {"1": valid[0], "2": "4100", "3": f"{4600 + w.next_id('m3') % 100:04d}"}
        tr = Transponder("sif", True, False, codes)
    else:
        tr = Transponder(at.transponder, at.transponder != "none", False, {"period": "WAR"})
    hx, hy = heading_vec(hdg)
    for i in range(g.n):
        aid = f"{g.id}-{i + 1}"
        ox, oy = _slot(g, i, hdg)
        ac = Aircraft(id=aid, type_id=at.id, callsign=g.callsign if g.n == 1 else f"{g.callsign}-{i + 1}",
                      side=g.side, x=x + ox, y=y + oy, alt=alt, hdg=hdg,
                      spd=cruise_speed(at, max(alt, 3000.0)), fuel=at.fuel_kg, transponder=Transponder(
                          tr.system, tr.on, tr.failed, dict(tr.codes)), weapons=dict(loadout), jammer=at.jammer,
                      group=g.id, home_base=g.base, t_spawn=w.t, truth_label=at.name,
                      nationality="USSR" if g.side == "red" and w.faction == "US" else "",
                      markings="red star" if g.side == "red" and w.faction == "US" else "")
        ac.cmd_alt, ac.cmd_hdg = g.alt, hdg
        w.aircraft[aid] = ac
        g.members.append(aid)
    g.state, g.t_state = "outbound", w.t
    counter(w, f"sorties_{g.side}", g.n)
    if g.side == w.own_side:
        event(w, "launch", f"{g.name} airborne ({g.n}× {at.id})", g.id, x, y, g.side, 1)
        _radio(w, g, "airborne" if w.faction == "US" else "Airborne.")
    else:
        event(w, "launch", f"[enemy] {g.name} ({g.n}× {at.id}) entering", g.id, x, y, g.side, -1)


def _slot(g: AirGroup, i: int, hdg: float) -> tuple[float, float]:
    """Formation position of member i relative to the leader (km)."""
    if i == 0:
        return 0.0, 0.0
    spacing = 6.0 if g.role == "strike" else 2.0 if g.role in ("sweep", "escort", "cap", "intercept") else 3.0
    row = (i + 1) // 2
    side = 1.0 if i % 2 else -1.0
    hx, hy = heading_vec(hdg)
    px, py = hy, -hx                                   # to the right of the heading
    along, across = -spacing * row * 0.55, side * spacing * row
    return hx * along + px * across, hy * along + py * across


def _radio(w: "World", g: AirGroup, text: str, priority: int = 0) -> None:
    if g.side != w.own_side:
        return
    from ..doctrine import send
    send(w, "radio", g.callsign, text, priority, False, g.id, "radio")


# ------------------------------------------------------------------ per tick

def members(w: "World", g: AirGroup) -> list[Aircraft]:
    out = []
    for mid in g.members:
        a = w.aircraft.get(mid)
        if a is not None and a.state == "airborne" and a.group == g.id:
            out.append(a)
    return out


def group_step(w: "World", g: AirGroup, dt: float) -> None:
    if g.state == "done":
        return
    if g.state == "pending":
        if not g.trigger and w.t >= g.t_launch:
            launch(w, g)
        return
    ms = members(w, g)
    if not ms:
        if g.state not in ("rtb",):
            if g.losses >= g.n:
                event(w, "group_lost", f"{g.name}: all {g.n} aircraft lost", g.id, side=g.side,
                      level=2 if g.side == w.own_side else -1)
        g.state = "done"
        return
    lead = ms[0]
    at = w.catalog.aircraft[g.type_id]
    if g.state in ("outbound", "station", "attack") and not g.released and g.role in ("strike", "recon", "ew") \
            and g.n > 1 and g.losses >= max(1, math.ceil(g.n * g.abort_frac)):
        g.state, g.t_state = "egress", w.t
        event(w, "abort", f"{g.name} has lost {g.losses} of {g.n} and turns back", g.id, lead.x, lead.y, g.side,
              2 if g.side == w.own_side else 1)
        _radio(w, g, "taking losses, aborting" if w.faction == "US" else "Heavy losses, returning.", 1)
    if g.state not in ("egress", "rtb") and _bingo(w, g, lead, at):
        g.state, g.t_state = "egress", w.t
        _radio(w, g, "bingo, RTB" if w.faction == "US" else "Fuel at minimum, returning.")
        for a in ms:
            a.jamming = False
    if g.role in ("sweep", "escort", "cap", "intercept") and g.state not in ("egress", "rtb") and not _armed(ms, w):
        g.state, g.t_state = "egress", w.t
        _radio(w, g, "winchester, RTB" if w.faction == "US" else "Weapons expended, returning.")
    if g.state in ("egress", "rtb"):
        _egress(w, g, ms, lead)
        _formation(w, g, ms, lead)
        return
    r = g.role
    free = False
    if r == "strike":
        _strike(w, g, ms, lead, at)
    elif r == "escort":
        free = _escort(w, g, ms, lead)
    elif r in ("sweep", "cap", "intercept"):
        free = _fighter(w, g, ms, lead)
    elif r == "recon":
        _recon(w, g, ms, lead, at)
    else:
        _orbit(w, g, ms, lead)
    if not free:
        _formation(w, g, ms, lead)


def _armed(ms: list[Aircraft], w: "World") -> bool:
    for a in ms:
        for wid, n in a.weapons.items():
            if n > 0 and w.catalog.weapons[wid].kind in combat.AAM_KINDS and w.catalog.weapons[wid].kind != "gun":
                return True
    return False


def _bingo(w: "World", g: AirGroup, lead: Aircraft, at) -> bool:
    if at.role == "missile":
        return False
    hx, hy = _home(w, g)
    d = math.hypot(hx - lead.x, hy - lead.y)
    v = cruise_speed(at, 9000.0) / 1000.0
    need = d / max(v, 0.05) * fuel_flow(at, "cruise", 9000.0) / 60.0 + 0.1 * at.fuel_kg
    return lead.fuel < need


def _fly(a: Aircraft, x: float, y: float, alt: float, throttle: str = "cruise", spd: Optional[float] = None) -> None:
    a.cmd_hdg = bearing_deg(x - a.x, y - a.y)
    a.cmd_alt = alt
    a.throttle = throttle
    a.cmd_spd = spd


def _orbit_at(a: Aircraft, x: float, y: float, alt: float, r: float) -> None:
    d = math.hypot(x - a.x, y - a.y)
    brg = bearing_deg(x - a.x, y - a.y)
    a.cmd_hdg = brg if d > r else (brg + 75.0) % 360.0
    a.cmd_alt = alt
    a.throttle = "cruise"
    a.cmd_spd = None


def _formation(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft) -> None:
    for i, a in enumerate(ms):
        if a is lead:
            continue
        ox, oy = _slot(g, i, lead.hdg)
        tx, ty = lead.x + ox, lead.y + oy
        d = math.hypot(tx - a.x, ty - a.y)
        if d > 25.0:                            # far out of position: fly back to the slot
            _fly(a, tx, ty, lead.alt, "mil")
            continue
        f = min(1.0, 0.2 + 0.05 * d)            # ease into the slot rather than jump
        a.x += (tx - a.x) * f
        a.y += (ty - a.y) * f
        a.alt += (lead.alt - a.alt) * 0.3
        if a.evade_t <= w.t:
            a.hdg, a.spd, a.vs = lead.hdg, lead.spd, lead.vs
            a.cmd_hdg, a.cmd_alt, a.cmd_spd, a.throttle = lead.cmd_hdg, lead.cmd_alt, lead.cmd_spd, lead.throttle
        a.fuel = min(a.fuel, lead.fuel + 300.0)
        a.jamming = lead.jamming


def _egress(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft) -> None:
    hx, hy = _home(w, g)
    d = math.hypot(hx - lead.x, hy - lead.y)
    for a in ms[:1]:
        _fly(a, hx, hy, g.alt if d > 120.0 else 1500.0, "cruise")
    if d < 8.0:
        landing = bool(g.base and g.base in w.airbases and w.airbases[g.base].runway_ok)
        for a in ms:
            a.state = "landed" if landing else "gone"
            a.jamming = False
        g.state = "done"
        where = w.airbases[g.base].name if landing else "out of the area"
        if g.side == w.own_side:
            event(w, "home", f"{g.name} {'recovered aboard ' + where if landing else 'left the area'}", g.id,
                  hx, hy, g.side, 0)
        else:
            event(w, "home", f"[enemy] {g.name} left the area ({len(ms)} of {g.n})", g.id, hx, hy, g.side, -1)


# ------------------------------------------------------------------ pictures

def known_enemy_air(w: "World", side: str) -> list[tuple[Aircraft, float, float, float, float, float]]:
    """Enemy aircraft this side knows about: (truth, x, y, alt, vx, vy) from its own picture."""
    out = []
    if side == w.own_side:
        for trk in w.tracks.values():
            if trk.lost or trk.identity not in ("hostile", "suspect"):
                continue
            a = w.aircraft.get(truth_of(trk) or "")
            if a is None or a.state != "airborne":
                continue
            px, py = predicted(trk, w.t)
            out.append((a, px, py, trk.alt if trk.alt is not None else a.alt, trk.vx, trk.vy))
    else:
        for c in w.battle.red_air.values():
            a = w.aircraft.get(c.id)
            if a is None or a.state != "airborne":
                continue
            age = w.t - c.t
            out.append((a, c.x + c.vx * age, c.y + c.vy * age, c.alt, c.vx, c.vy))
    return out


def pick_air_target(w: "World", g: AirGroup, cx: float, cy: float, radius: float,
                    fighters_first: bool = False) -> Optional[tuple]:
    best, bscore = None, 0.0
    for item in known_enemy_air(w, g.side):
        a, x, y = item[0], item[1], item[2]
        if a.aim or a.kind != "aircraft" or a.side in ("civil", "neutral", g.side):
            continue
        d = math.hypot(x - cx, y - cy)
        if d > radius:
            continue
        role = combat.role_of(w, a)
        wgt = ROLE_WEIGHT.get(role, 1.0)
        if fighters_first and role in ("interceptor", "fighter"):
            wgt *= 3.0
        score = wgt / (1.0 + d / 40.0)
        if score > bscore:
            best, bscore = item, score
    return best


def _engage(w: "World", g: AirGroup, ms: list[Aircraft], item: tuple) -> None:
    tgt, x, y, alt, vx, vy = item
    if g.air_target != tgt.id:
        g.air_target = tgt.id
        if g.side == w.own_side:
            _radio(w, g, f"committing on {tgt.callsign or 'bandit'}" if w.faction == "US" else "Attacking.")
    for a in ms:
        at = w.catalog.aircraft[a.type_id]
        d = math.hypot(tgt.x - a.x, tgt.y - a.y)
        sees = at.ai_radar_km > 0 and d < at.ai_radar_km * 1.1
        if sees:
            tvx, tvy = combat.truth_velocity(w, tgt)
            combat.steer_attack(w, a, tgt.x, tgt.y, tgt.alt, tvx, tvy)
            wid = combat.try_shot(w, a, tgt, g.id)
            if wid is not None:
                wt = w.catalog.weapons[wid]
                if g.side == w.own_side:
                    _radio(w, g, f"fox, {wt.name.split()[0]}" if w.faction == "US" else f"Launch, {wt.name}.", 1)
                    event(w, "aam", f"{g.callsign}: {wt.name} away at {tgt.callsign}", g.id, a.x, a.y, g.side, 1)
                else:
                    event(w, "aam", f"[enemy] {a.callsign} fired {wt.name} at {tgt.callsign}", g.id, a.x, a.y,
                          g.side, -1)
        else:
            combat.steer_attack(w, a, x, y, alt, vx, vy)


# ------------------------------------------------------------------ roles

def _strike(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft, at) -> None:
    aim, have_fix, ship = _strike_aim(w, g, lead, at)
    if aim is not None:
        g.aim = [aim[0], aim[1]]
    wid = next((k for k, n in lead.weapons.items() if n > 0 and w.catalog.weapons[k].kind == "asm"), None)
    if wid is None:
        g.state = "egress"
        return
    wt = w.catalog.weapons[wid]
    reach = g.launch_km or wt.max_km * 0.92
    if g.wp < len(g.route):
        x, y, alt = g.route[g.wp]
        if math.hypot(x - lead.x, y - lead.y) < 15.0:
            g.wp += 1
        _fly(lead, x, y, alt, "cruise")
        if not g.aim:
            return
    if not g.aim:
        hx, hy = heading_vec(lead.hdg)
        _fly(lead, lead.x + hx * 50.0, lead.y + hy * 50.0, g.alt)
        return
    d = math.hypot(g.aim[0] - lead.x, g.aim[1] - lead.y)
    if g.wp >= len(g.route):
        dash = at.ff_ab > 0 and d < reach + 60.0
        _fly(lead, g.aim[0], g.aim[1], g.alt, "ab" if dash else "mil" if d < reach + 300.0 else "cruise")
    if d <= reach and have_fix and not g.released:
        _release(w, g, ms, wid, ship)
    elif d < reach * 0.4 and not g.released:
        _release(w, g, ms, wid, ship)            # pressed in this far: fire at the best estimate


def _strike_aim(w: "World", g: AirGroup, lead: Aircraft, at) -> tuple[Optional[tuple], bool, str]:
    """Where the raid believes its target is, and whether that fix is good enough to fire on."""
    pic = w.battle.surface.get(g.side, {})
    best, bscore = None, -1.0
    for sid, c in pic.items():
        sh = w.ships.get(sid)
        if sh is None or sh.state == "sunk":
            continue
        if g.target and sh.group != g.target and sh.id != g.target:
            continue
        st = w.catalog.ships[sh.type_id]
        score = st.rcs_m2 / (1.0 + (w.t - c.t) / 120.0)
        if score > bscore:
            best, bscore = (sid, c), score
    if best is None:
        aim = tuple(g.aim) if g.aim else (tuple(w.battle.red_plan.get("brief", [])) or None
                                          if g.side != w.own_side else None)
        return aim, False, ""
    sid, c = best
    age = w.t - c.t
    x, y = c.x + c.vx * age, c.y + c.vy * age
    return (x, y), (age < 150.0 and c.err_km < 30.0), sid


def _release(w: "World", g: AirGroup, ms: list[Aircraft], wid: str, ship: str) -> None:
    wt = w.catalog.weapons[wid]
    n = 0
    for a in ms:
        cnt = a.weapons.get(wid, 0)
        for k in range(cnt):
            jitter = w.rng.gauss(0.0, 2.5)
            hx, hy = heading_vec(bearing_deg(g.aim[0] - a.x, g.aim[1] - a.y) + 90.0)
            naval.launch_asm(w, a, wid, (g.aim[0] + hx * jitter * (k + 1), g.aim[1] + hy * jitter * (k + 1)), g.id)
            n += 1
        a.weapons[wid] = 0
    g.released = True
    g.state, g.t_state = "egress", w.t
    counter(w, f"raids_released_{g.side}")
    if g.side == w.own_side:
        event(w, "asm_launch", f"{g.name}: {n} {wt.name.split(' (')[0]} away at the {ship and w.ships[ship].name or 'target'}",
              g.id, ms[0].x, ms[0].y, g.side, 2)
        _radio(w, g, f"{n} {wt.id} away, egressing" if w.faction == "US" else f"{n} missiles launched.", 1)
    else:
        event(w, "asm_launch", f"[enemy] {g.name} released {n} {wt.id}", g.id, ms[0].x, ms[0].y, g.side, -1)


def _escort(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft) -> bool:
    esc = w.battle.groups.get(g.target)
    eld = members(w, esc)[0] if esc is not None and esc.state not in ("done", "pending") and members(w, esc) \
        else None
    cx, cy = (eld.x, eld.y) if eld is not None else (lead.x, lead.y)
    item = pick_air_target(w, g, cx, cy, g.commit_km, fighters_first=True)
    if item is not None:
        _engage(w, g, ms, item)
        return True
    g.air_target = ""
    if eld is None:
        if esc is not None and esc.state in ("done", "egress"):
            g.state = "egress"
        elif g.route and g.wp < len(g.route):
            x, y, alt = g.route[g.wp]
            if math.hypot(x - lead.x, y - lead.y) < 15.0:
                g.wp += 1
            _fly(lead, x, y, alt)
        return False
    hx, hy = heading_vec(eld.hdg)
    tx, ty = eld.x + hx * 15.0, eld.y + hy * 15.0
    behind = (tx - lead.x) * hx + (ty - lead.y) * hy
    _fly(lead, tx, ty, eld.alt + 1000.0, "mil" if behind > 5.0 else "cruise")
    if esc.state == "egress" and behind < 30.0:
        g.state = "egress"
    return False


def _fighter(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft) -> bool:
    cx, cy = (g.station[0], g.station[1]) if g.station else (lead.x, lead.y)
    radius = g.commit_km + (g.station[3] if g.station else 0.0)
    item = pick_air_target(w, g, cx, cy, radius)
    if item is None and g.role == "sweep":
        item = pick_air_target(w, g, lead.x, lead.y, g.commit_km)
    if item is not None:
        _engage(w, g, ms, item)
        return True
    g.air_target = ""
    if g.wp < len(g.route):
        x, y, alt = g.route[g.wp]
        if math.hypot(x - lead.x, y - lead.y) < 15.0:
            g.wp += 1
        _fly(lead, x, y, alt, "cruise")
    elif g.station:
        _orbit_at(lead, g.station[0], g.station[1], g.station[2], g.station[3])
        g.state = "station"
    else:
        g.state = "egress"
    return False


def _threatened(w: "World", g: AirGroup, x: float, y: float, km: float) -> Optional[Aircraft]:
    for item in known_enemy_air(w, g.side):
        a = item[0]
        if combat.role_of(w, a) in ("interceptor", "fighter") and math.hypot(item[1] - x, item[2] - y) < km:
            return a
    return None


def _recon(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft, at) -> None:
    pic = w.battle.surface.get(g.side, {})
    mine = [(sid, c) for sid, c in pic.items() if c.by == lead.callsign and w.t - c.t < 60.0]
    if mine and not g.reported:
        first = min(c.t_first for _, c in mine)
        if w.t - first > 45.0:
            g.reported = True
            event(w, "recon", f"[enemy] {g.name} reports the task group's position", g.id, lead.x, lead.y,
                  g.side, -1)
    threat = _threatened(w, g, lead.x, lead.y, 90.0)
    if threat is not None and g.state != "egress":
        hx, hy = _home(w, g)
        _fly(lead, hx, hy, g.alt, "mil")             # run for it, then come back
        return
    if mine:
        sid, c = max(mine, key=lambda sc: w.catalog.ships[w.ships[sc[0]].type_id].rcs_m2)
        stand = at.surface_radar_km * 0.8
        d = math.hypot(c.x - lead.x, c.y - lead.y)
        brg = bearing_deg(c.x - lead.x, c.y - lead.y)
        lead.cmd_hdg = (brg + (90.0 if d < stand else 60.0 if d < stand * 1.15 else 0.0)) % 360.0
        lead.cmd_alt, lead.throttle, lead.cmd_spd = g.alt, "cruise", None
        g.state = "station"
        return
    if g.wp < len(g.route):
        x, y, alt = g.route[g.wp]
        if math.hypot(x - lead.x, y - lead.y) < 15.0:
            g.wp += 1
        _fly(lead, x, y, alt)
    elif g.aim or w.battle.red_plan.get("brief"):
        x, y = g.aim or w.battle.red_plan["brief"]
        _fly(lead, x, y, g.alt)
    else:
        g.state = "egress"


def _orbit(w: "World", g: AirGroup, ms: list[Aircraft], lead: Aircraft) -> None:
    if g.wp < len(g.route):
        x, y, alt = g.route[g.wp]
        if math.hypot(x - lead.x, y - lead.y) < 15.0:
            g.wp += 1
        _fly(lead, x, y, alt)
        return
    if not g.station:
        g.state = "egress"
        return
    sx, sy, alt, r = g.station
    if g.role in ("ew", "awacs"):
        threat = _threatened(w, g, lead.x, lead.y, 75.0 if g.role == "ew" else 110.0)
        if threat is not None and (g.side != w.own_side or g.role == "ew"):
            hx, hy = _home(w, g)
            _fly(lead, hx, hy, alt, "mil")             # fall back toward home while fighters are close
            return
    _orbit_at(lead, sx, sy, alt, r)
    on = math.hypot(sx - lead.x, sy - lead.y) < r * 1.6
    if on and g.state != "station":
        g.state = "station"
        if g.role == "ew" and g.jam:
            if g.side == w.own_side:
                event(w, "jam", f"{g.name} on station, jamming", g.id, lead.x, lead.y, g.side, 1)
            else:
                event(w, "jam", f"[enemy] {g.name} on station, jammers on", g.id, lead.x, lead.y, g.side, -1)
        elif g.role == "awacs" and g.side == w.own_side:
            event(w, "aew", f"{g.name} on station", g.id, lead.x, lead.y, g.side, 1)
    if g.role == "ew":
        for a in ms:
            a.jamming = bool(g.jam and on)


# ------------------------------------------------------------------ the enemy commander

def red_command(w: "World") -> None:
    """Groups that wait for a reason: interceptors that scramble when intruders come near.
    Once every raid has fired or turned back, the enemy's support aircraft go home too."""
    b = w.battle
    enemy = "red" if w.own_side == "blue" else "blue"
    strikes = [g for g in b.groups.values() if g.side == enemy and g.role == "strike"]
    if strikes and all(g.state in ("done", "egress") for g in strikes):
        t0 = b.red_plan.setdefault("t_raids_over", w.t)
        if w.t - t0 > 240.0 and not b.red_plan.get("withdrawn"):
            b.red_plan["withdrawn"] = True
            for g in b.groups.values():
                if g.side == enemy and g.state in ("outbound", "station", "attack"):
                    g.state, g.t_state = "egress", w.t
                    for a in members(w, g):
                        a.jamming = False
            event(w, "withdraw", "The enemy is pulling back his shadowers and jammers", "", side=enemy, level=1)
    for g in b.groups.values():
        if g.state != "pending" or g.trigger != "threat":
            continue
        cx, cy = (g.station[0], g.station[1]) if g.station else _home(w, g)
        radius = g.commit_km + (g.station[3] if g.station else 0.0)
        for item in known_enemy_air(w, g.side):
            if math.hypot(item[1] - cx, item[2] - cy) < radius and not item[0].aim:
                g.trigger = ""
                g.t_launch = w.t + 60.0                 # alert crews: a minute to get airborne
                event(w, "scramble", f"[{'enemy' if g.side != w.own_side else 'own'}] {g.name} scrambling",
                      g.id, cx, cy, g.side, -1 if g.side != w.own_side else 1)
                break

