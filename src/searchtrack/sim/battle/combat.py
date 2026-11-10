"""Air combat for the battle AI: which missile a pilot can use on whom, missiles away, the
defensive break against an incoming missile, and what a hit does to a big aircraft.

Our own interceptors keep their ground-controlled attack logic (gci); these rules fly the
enemy's fighters and our battle-AI escorts, and the evasion and damage rules apply to all.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..flight import ground_velocity
from ..geo import angle_diff, bearing_deg, heading_vec
from ..state import Aircraft, Mission, Missile, Waypoint
from .core import counter, event

if TYPE_CHECKING:
    from ..world import World

AAM_KINDS = ("aam_radar", "aam_ir", "aam_beam", "rocket", "gun")
BIG_ROLES = ("bomber", "strike", "recon", "awacs", "ew", "tanker", "patrol", "airliner", "transport")


def role_of(w: "World", ac: Aircraft) -> str:
    if ac.aim:
        return "missile"
    at = w.catalog.aircraft.get(ac.type_id)
    return at.role if at else "unknown"


def unit_name(w: "World", uid: str) -> str:
    """A readable name for a shooter: a group, a flight, a missile unit or a ship."""
    b = w.battle
    if uid in b.groups:
        return b.groups[uid].callsign
    if uid in w.flights:
        return w.flights[uid].callsign
    if uid in w.sams:
        s = w.sams[uid]
        return s.unit or s.name
    if uid in w.ships:
        return w.ships[uid].name
    if uid in w.aircraft:
        return w.aircraft[uid].callsign or uid
    return uid


# ------------------------------------------------------------------ shooting

def answers_iff(w: "World", shooter: Aircraft, tgt: Aircraft) -> bool:
    """The shooter's interrogator gets a friendly reply: no shot."""
    tr = tgt.transponder
    return tgt.side == shooter.side and tr.on and not tr.failed and tr.system != "none"


def best_shot(w: "World", shooter: Aircraft, tgt: Aircraft) -> Optional[str]:
    if answers_iff(w, shooter, tgt):
        return None
    cat = w.catalog
    at = cat.aircraft[shooter.type_id]
    d = math.hypot(tgt.x - shooter.x, tgt.y - shooter.y)
    d3 = math.hypot(d, (tgt.alt - shooter.alt) / 1000.0)
    aspect = abs(angle_diff(bearing_deg(shooter.x - tgt.x, shooter.y - tgt.y), tgt.hdg))   # 180 = behind it
    off = abs(angle_diff(bearing_deg(tgt.x - shooter.x, tgt.y - shooter.y), shooter.hdg))
    tt = cat.aircraft.get(tgt.type_id)
    rcs = (tt.rcs(90.0) if tt else 5.0) * tgt.rcs_scale
    radar_km = at.ai_radar_km * (max(rcs, 0.1) / 5.0) ** 0.25
    for wid, cnt in sorted(shooter.weapons.items(), key=lambda kv: -cat.weapons[kv[0]].max_km):
        if cnt <= 0:
            continue
        wt = cat.weapons[wid]
        if wt.kind not in AAM_KINDS or wt.special:
            continue
        reach = wt.max_km * (0.8 if wt.max_km > 30 else 1.0)       # long shots are taken inside the no-escape zone
        if not (wt.min_km <= d3 <= reach):
            continue
        if wt.aspect == "rear" and aspect < 110.0:
            continue
        if abs(tgt.alt - shooter.alt) > 2500.0 + wt.max_km * 70.0:
            continue
        if wt.kind in ("aam_radar", "aam_beam"):
            if radar_km <= 0 or off > at.ai_radar_cone or d > radar_km:
                continue
        elif off > 45.0:
            continue
        return wid
    return None


def fire(w: "World", shooter: Aircraft, tgt: Aircraft, wid: str, owner: str, n: int = 1) -> int:
    cat = w.catalog
    wt = cat.weapons[wid]
    cnt = shooter.weapons.get(wid, 0)
    if cnt <= 0:
        return 0
    if wt.kind == "gun":
        shooter.weapons[wid] = cnt - 1
        d = math.hypot(tgt.x - shooter.x, tgt.y - shooter.y)
        p = min(0.85, wt.pk * max(0.15, min(1.2, 1.25 - d / max(wt.max_km, 0.1))))
        counter(w, f"aam_shots_{shooter.side}")
        if w.rng.random() < p:
            hit(w, tgt, f"gunfire from {unit_name(w, owner)}", owner)
        return 1
    shots = min(cnt, n)
    shooter.weapons[wid] = cnt - shots
    hx, hy = heading_vec(shooter.hdg)
    for i in range(shots):
        m = Missile(id=f"M{w.next_id('msl')}", type_id=wid, kind="aam", owner=owner, side=shooter.side,
                    x=shooter.x, y=shooter.y, alt=shooter.alt, target=tgt.id, t_launch=w.t + i * 1.5)
        spd = shooter.spd + 400.0
        m.vx, m.vy = hx * spd, hy * spd
        w.missiles[m.id] = m
    counter(w, f"aam_shots_{shooter.side}", shots)
    return shots


def try_shot(w: "World", shooter: Aircraft, tgt: Aircraft, owner: str) -> Optional[str]:
    """Fire if this pilot has a missile for the geometry and is not still guiding the last one."""
    key = f"aishot_{shooter.id}"
    if w.t < w.vars.get(key, -1.0):
        return None
    wid = best_shot(w, shooter, tgt)
    if wid is None:
        return None
    wt = w.catalog.weapons[wid]
    big = role_of(w, tgt) in BIG_ROLES
    n = 2 if (big and wt.max_km > 30.0) else 1
    shots = fire(w, shooter, tgt, wid, owner, n)
    if shots:
        w.vars[key] = w.t + (5.0 if wt.kind == "gun" else 9.0 if wt.kind == "aam_ir" else 14.0)
        return wid
    return None


# ------------------------------------------------------------------ the defensive break

def evasion_step(w: "World") -> None:
    threats: dict[str, tuple[Missile, float]] = {}
    for m in w.missiles.values():
        if m.state != "flying" or w.t < m.t_launch or not m.target:
            continue
        tgt = w.aircraft.get(m.target)
        if tgt is None or tgt.state != "airborne" or tgt.aim:
            continue
        d = math.hypot(m.x - tgt.x, m.y - tgt.y)
        if d < (28.0 if m.kind == "aam" else 40.0) and (tgt.id not in threats or d < threats[tgt.id][1]):
            threats[tgt.id] = (m, d)
    for aid, (m, d) in threats.items():
        a = w.aircraft[aid]
        at = w.catalog.aircraft[a.type_id]
        if a.evade_t < w.t - 4.0:
            if a.side == w.own_side:
                event(w, "defend", f"{a.callsign}: missile inbound — defending", aid, a.x, a.y, a.side, 1)
            counter(w, f"defends_{a.side}")
        a.evade_t = w.t + 6.0
        brg_m = bearing_deg(m.x - a.x, m.y - a.y)
        turn = 1.0 if angle_diff(brg_m, a.hdg) < 0 else -1.0
        a.cmd_hdg = (brg_m + 90.0 * turn) % 360.0                   # put the missile on the beam
        if at.role in BIG_ROLES:
            a.throttle = "mil"
        else:
            a.cmd_alt = max(a.alt - 2500.0, 300.0)                  # and dive into the clutter
            a.throttle = "ab" if at.ff_ab > 0 else "mil"
        a.cmd_spd = None


def evade_factor(w: "World", tgt: Aircraft, m: Missile) -> float:
    """How much a defensive break (chaff, flares, notching) spoils a missile's aim."""
    f = 1.0
    if tgt.evade_t > w.t:
        f = 0.8 if role_of(w, tgt) in BIG_ROLES else 0.55
        if m.kind == "aam":
            wt = w.catalog.weapons.get(m.type_id)
            if wt is not None and wt.kind == "aam_ir":
                f *= 0.85
    if m.kind != "aam" and tgt.spd > 500.0:                         # SAMs against supersonic missiles
        f *= max(0.5, min(1.0, 1.3 - tgt.spd / 1600.0))
    if m.kind != "aam" and tgt.alt - w.ground_height(tgt.x, tgt.y) < 80.0:   # skimmers: clutter and multipath
        f *= 0.6
    return f


# ------------------------------------------------------------------ hits and losses

def hit(w: "World", tgt: Aircraft, cause: str, shooter: str) -> None:
    """A warhead went off close enough. Big aircraft sometimes survive, badly hurt."""
    if tgt.state != "airborne":
        return
    if role_of(w, tgt) in BIG_ROLES and tgt.damage < 0.5 and w.rng.random() < 0.3:
        tgt.damage = 0.6
        counter(w, f"damaged_{tgt.side}")
        event(w, "damaged", f"{tgt.callsign} hit by {cause} — still flying, turning for home", tgt.id, tgt.x, tgt.y,
              tgt.side, 2 if tgt.side == w.own_side else 1)
        send_home(w, tgt)
        return
    w.destroy(tgt.id, cause, shooter=shooter)


def send_home(w: "World", ac: Aircraft) -> None:
    """A damaged aircraft leaves its formation and limps home on its own."""
    g = w.battle.groups.get(ac.group)
    home = None
    if g is not None:
        if ac.id in g.members:
            g.members.remove(ac.id)
        g.losses += 1
        if g.base and g.base in w.airbases:
            b = w.airbases[g.base]
            home = (b.x, b.y, "land")
        elif g.exit:
            home = (g.exit[0], g.exit[1], "remove")
        elif g.entry:
            home = (g.entry[0], g.entry[1], "remove")
    if home is None:
        home = (ac.x, ac.y, "remove")
    ac.group = ""
    ac.mission = Mission(kind="route", waypoints=[Waypoint(home[0], home[1], max(ac.alt, 3000.0), ac.spd * 0.7,
                                                           home[2])])


def on_destroyed(w: "World", ac: Aircraft, cause: str, shooter: str) -> None:
    """Called by World.destroy: book-keeping and the event the display shows."""
    role = role_of(w, ac)
    at = w.catalog.aircraft.get(ac.type_id)
    g = w.battle.groups.get(ac.group)
    if g is not None:
        g.losses += 1
    sg = w.battle.groups.get(shooter)
    if sg is not None:
        sg.kills += 1
    if ac.side == "civil":
        return
    by = unit_name(w, shooter) if shooter else cause
    if role == "missile":
        counter(w, f"asm_killed_{ac.side}")
        counter(w, f"killed_{ac.type_id}")
        event(w, "vampire_kill", f"{at.id if at else 'missile'} shot down by {by}", ac.id, ac.x, ac.y, ac.side, 1)
        return
    counter(w, f"aircraft_lost_{ac.side}")
    counter(w, f"lost_{ac.side}_{role}")
    name = at.name.split(" (")[0] if at else ac.type_id
    lvl = 2 if (ac.side == w.own_side or role in BIG_ROLES) else 1
    head = "SPLASH" if w.faction == "US" else "TARGET DESTROYED"
    event(w, "kill", f"{head} — {ac.callsign} ({name}) shot down by {by}", ac.id, ac.x, ac.y, ac.side, lvl)
    fl = w.flights.get(shooter)
    if fl is not None and w.faction_def.id == "US":
        w.radio(fl, f"splash one {name.split()[0]}", 1)


def steer_attack(w: "World", a: Aircraft, tgt_x: float, tgt_y: float, tgt_alt: float, tvx: float, tvy: float) -> None:
    """Lead-collision steering on a target, unless the pilot is busy defending."""
    from ..intercept import lead_collision
    if a.evade_t > w.t:
        return
    at = w.catalog.aircraft[a.type_id]
    sol = lead_collision(tgt_x, tgt_y, tvx, tvy, a.x, a.y, max(a.spd, 150.0) / 1000.0)
    a.cmd_hdg = sol.hdg
    a.cmd_alt = max(300.0, min(tgt_alt, max(at.zoom_ceiling_m, at.ceiling_m)))
    a.throttle = "ab" if at.ff_ab > 0 else "mil"
    a.cmd_spd = None


def truth_velocity(w: "World", a: Aircraft) -> tuple[float, float]:
    return ground_velocity(w, a)
