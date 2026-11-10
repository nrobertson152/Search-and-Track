"""Our battle staff: the officers who run the routine so the commander can command.

Every few seconds the staff identifies new tracks by the battle's rules, ranks the threats,
commits interceptors on the worst of them (as far out as the standing posture allows, while
keeping a reserve on deck), keeps the combat air patrols manned and relieved, turns flights
toward fighters that come for them, gives every missile fire channel a target and keeps the
radar aircraft out of reach. All of it works from our track picture, so whatever the radars
miss, the staff misses too.

The commander decides what the staff cannot: standing orders, priorities, and the calls
that come up as decisions with a deadline (taken by the staff when the commander does not
answer, and always in spectator mode).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional

from .. import commands, gci, orders
from ..geo import bearing_deg
from ..state import Decision
from ..tracking import predicted, truth_of
from .core import counter, event

if TYPE_CHECKING:
    from ..world import World

THREAT_WEIGHT = {"strike": 3.0, "bomber": 3.0, "recon": 2.6, "ew": 2.2, "awacs": 1.8, "interceptor": 1.2,
                 "fighter": 1.2, "patrol": 1.5, "tanker": 1.0, "unknown": 1.5, "cruise": 2.4}
CRUISE_MPS = 330.0                  # a missile track slower than this is a cruise missile: fighters can hunt it
REACH_KM = {"aggressive": 950.0, "balanced": 600.0, "defensive": 320.0}


def spared(w: "World", trk) -> bool:
    """One of the aircraft the commander let go home (see director.spare_groups)."""
    from .director import spared as _spared
    return _spared(w, trk)


# ------------------------------------------------------------------ classification

def classify(w: "World", trk) -> str:
    """What the staff believes a track is: kinematics at first, type once it has been watched."""
    spd = math.hypot(trk.vx, trk.vy) * 1000.0
    a = w.aircraft.get(truth_of(trk) or "")
    if a is not None and a.kind == "debris":
        return "debris"                      # falling, slowing: the 3-D radars see it come down
    if a is not None and a.aim:
        return "missile" if (spd > 300.0 or w.t - trk.t_init > 15.0) else "unknown"
    if spd > 1050.0 and a is not None and not trk.jammer and w.t - trk.t_init > 20.0:
        return "missile"                     # jamming and clutter make wild speeds on false tracks: ignore those
    if a is not None and w.t - trk.t_init > 25.0:
        at = w.catalog.aircraft.get(a.type_id)
        if at is not None:
            return {"bomber": "strike"}.get(at.role, at.role)
    return "unknown"


def defended_points(w: "World", aew: bool = True) -> list[tuple[float, float]]:
    pts = [(s.x, s.y) for s in w.ships.values() if s.side == w.own_side and s.state != "sunk"]
    for g in w.battle.groups.values():
        if aew and g.side == w.own_side and g.role == "awacs" and g.members:
            a = w.aircraft.get(g.members[0])
            if a is not None and a.state == "airborne":
                pts.append((a.x, a.y))
    for bid in w.battle.defended:
        b = w.airbases.get(bid)
        if b is not None:
            pts.append((b.x, b.y))
    return pts or [(0.0, 0.0)]


# ------------------------------------------------------------------ the routine

def step(w: "World") -> None:
    b = w.battle
    if w.tick % 15 == 0:                          # the watch officer acknowledges the routine traffic
        from ..doctrine import acknowledge
        for m in w.messages[-300:]:
            if m.ack and not m.acked and m.delivered and w.t - m.t_deliver > 25.0:
                acknowledge(w, m.mid)
    _emcon(w)
    _identify(w)
    _cap(w)
    rules = b.standing.get("roe", "war")
    if b.standing.get("fighters", "auto") == "auto":
        if rules == "war":
            _commit(w)
            _recall(w)                            # in peacetime nobody shoots: escorts go wherever the stranger goes
        elif rules == "peace":
            _escorts(w)
    if rules == "war":
        _self_defense(w)
    if b.standing.get("sam", "FREE") != "HOLD" or rules == "ceasefire":
        _sams(w, missiles_only=rules != "war")
    _aew(w)
    if w.tick % 3 == 0:
        _intercepts(w)


def _escorts(w: "World") -> None:
    """Peacetime: every stranger coming our way gets a pair of fighters on its tail -- identify it,
    escort it, show it the flag. Nobody fires."""
    from .. import commands
    b = w.battle
    if w.tick % 3:
        return
    pts = defended_points(w)
    if not pts:
        return
    reach = 380.0
    done = 0
    own = _controlled(w)
    for trk in sorted(w.tracks.values(), key=lambda t: t.id):
        if done >= 2:
            break
        if trk.lost or trk.identity not in ("hostile", "suspect") or own_correlation(w, trk, own):
            continue                              # only strangers the battle rules have marked
        if classify(w, trk) in ("missile", "debris"):
            continue
        px, py = predicted(trk, w.t)
        d = min(math.hypot(px - x, py - y) for x, y in pts)
        if d > reach and trk.id not in b.priority:
            continue
        if any(fl.target == trk.id and fl.state not in ("landed", "lost") for fl in w.flights.values()):
            continue
        if _company(w, trk, px, py, own):
            continue                              # a second track on a stranger who already has company
        if w.t - w.vars.get(f"esc_{trk.id}", -1e9) < 150.0:
            continue                              # sent someone a moment ago: give them time to find him
        ok, msg = commands.run(w, "quick", track=trk.id, order="shadow", n=2)
        if not ok:
            continue
        w.vars[f"esc_{trk.id}"] = w.t
        done += 1
        callsign = "fighters"
        for fl in w.flights.values():
            if fl.target == trk.id and fl.state not in ("landed", "lost"):
                callsign = fl.callsign
                fl.order_throttle = "ab"          # burners out to the stranger, then match his speed
        event(w, "commit", f"{callsign} sent to intercept and escort {trk.id} ({d:.0f} km out) — weapons tight",
              trk.id, px, py, w.own_side, 1)


def _company(w: "World", trk, px: float, py: float, own: list) -> bool:
    """Already escorted: another track with an escort on it within a few km, or one of our
    fighters on a target sitting right there."""
    near = 12.0 + math.hypot(trk.vx, trk.vy) * 25.0   # a fast mover's tracks lag and split further apart
    for fl in w.flights.values():
        if not fl.target or fl.target == trk.id or fl.state in ("landed", "lost", "rtb"):
            continue
        o = w.tracks.get(fl.target)
        if o is not None and not o.lost:
            ox, oy = predicted(o, w.t)
            if math.hypot(ox - px, oy - py) < near:
                return True
        lead = gci.lead_of(w, fl)
        if lead is not None and fl.contact and math.hypot(lead.x - px, lead.y - py) < 8.0:
            return True
    return False


ALONGSIDE_US = {
    "recon": "tail gunner's waving at us — cameras up in the blisters, they're shooting the whole formation",
    "patrol": "crew's at the windows taking pictures, sonobuoy chutes in the back",
    "elint": "antenna farm on the belly, they're listening to everything we radiate",
    "ew": "jammer pods on the wingtips, just sitting there humming",
    "interceptor": "four big missiles under the belly — he's watching me watch him",
    "fighter": "carrying a full load of missiles, he's flying good formation on us",
    "strike": "missiles on the pylons — that's a live load, not training rounds",
    "bomber": "big as a house — and that's a live load under the wings",
}
ALONGSIDE_SU = {
    "recon": "Crew is photographing us through the window. Antennas everywhere.",
    "patrol": "Patrol aircraft, low over the water. The crew waved.",
    "elint": "Electronic reconnaissance aircraft. Listening to our radars.",
    "ew": "Jamming aircraft, pods under the wings.",
    "interceptor": "Fighter, full missile load. He is holding formation on us.",
    "fighter": "Fighter, missiles on the rails. He sees us.",
    "strike": "Strike aircraft with weapons on the pylons. Live load.",
    "bomber": "Bomber, weapons under the wings.",
}


def _nick(name: str) -> str:
    """"Tu-95RTs (BEAR D)" -> "BEAR D"."""
    if "(" in name and ")" in name:
        return name[name.index("(") + 1:name.index(")")]
    return name


def _intercepts(w: "World") -> None:
    """Which of the enemy's groups have had one of our fighters alongside (for the peacetime objectives)."""
    b = w.battle
    if b.standing.get("roe", "war") != "peace":
        return                                    # in a war, being alongside is not an intercept
    own = [a for a in w.aircraft.values() if a.side == w.own_side and a.state == "airborne" and a.kind == "aircraft"
           and not a.aim and a.flight_id]
    if not own:
        return
    for g in b.groups.values():
        if g.side == w.own_side or g.state in ("pending", "done") or w.vars.get(f"intercepted_{g.id}"):
            continue
        for mid in g.members:
            m = w.aircraft.get(mid)
            if m is None or m.state != "airborne":
                continue
            near = [a for a in own if math.hypot(a.x - m.x, a.y - m.y) < 6.0 and abs(a.alt - m.alt) < 2500.0]
            if not near:
                continue
            w.vars[f"intercepted_{g.id}"] = w.t
            fl = w.flights.get(near[0].flight_id)
            at = w.catalog.aircraft.get(g.type_id)
            role = at.role if at is not None else "unknown"
            what = _nick(at.name) if at is not None else g.name
            cs = fl.callsign if fl is not None else "our fighters"
            if w.faction == "US":
                txt = f"{cs} alongside the {what} — {ALONGSIDE_US.get(role, 'we have him')}"
            else:
                txt = f"{cs} alongside the {what}. {ALONGSIDE_SU.get(role, 'Holding formation.')}"
            event(w, "intercepted", txt, g.id, m.x, m.y, w.own_side, 2)
            break


def _emcon(w: "World") -> None:
    on = bool(w.battle.standing.get("emcon", False))
    for sh in w.ships.values():
        if sh.side == w.own_side and sh.emcon != on:
            sh.emcon = on


def _controlled(w: "World") -> list:
    """Our aircraft whose positions the combat center knows from data link and control."""
    out = []
    for a in w.aircraft.values():
        if a.state != "airborne" or a.side != w.own_side or a.kind != "aircraft" or a.aim:
            continue
        if (a.flight_id and a.flight_id in w.flights) or (a.group and a.group in w.battle.groups):
            out.append(a)
    return out


def own_correlation(w: "World", trk, own: list) -> Optional[str]:
    """The track sits on one of our controlled aircraft and moves with it."""
    from ..flight import ground_velocity
    px, py = predicted(trk, w.t)
    spd = math.hypot(trk.vx, trk.vy)
    wild = spd > 1.0                         # no aircraft does 1000 m/s: the velocity is bad data, not a fast mover
    for a in own:
        d = min(math.hypot(a.x - px, a.y - py), math.hypot(a.x - trk.x, a.y - trk.y))
        if d > 6.0:
            continue
        vx, vy = ground_velocity(w, a)
        if abs(math.hypot(vx, vy) - spd) > 0.2 and w.t - trk.t_init > 8.0 and not wild:
            continue                         # something much faster (or slower) passing close by
        if d < 3.0 or math.hypot(vx - trk.vx, vy - trk.vy) < 0.25 or w.t - trk.t_init < 15.0:
            return a.callsign
    return None


def _identify(w: "World") -> None:
    from ..ident import iff_assessment, recommend
    b = w.battle
    hx = b.red_plan.get("hostile_x")
    hy = b.red_plan.get("hostile_y")
    vamp = []
    own = _controlled(w)
    on_target: dict[str, list] = {}
    for a in own:
        fl = w.flights.get(a.flight_id) if a.flight_id else None
        if fl is not None and fl.target:
            on_target.setdefault(fl.target, []).append(a)
    for trk in w.tracks.values():
        if trk.lost:
            continue
        cls = classify(w, trk)
        seen = w.vid_reports.get(trk.id)
        if seen is not None and seen[0] not in (w.own_side, "civil", "neutral") and cls != "debris":
            if trk.identity != "hostile":         # the pilot alongside has seen the red stars
                w.set_identity(trk.id, "hostile", f"VID: {seen[1]}", authority=True)
            continue
        if trk.identity in ("pending", "unknown", "hostile") and trk.id not in b.priority and cls != "missile":
            escorts = on_target.get(trk.id, [])  # our fighters sitting on it are not it
            mine = own_correlation(w, trk, [a for a in own if a not in escorts] if escorts else own)
            if mine is not None and iff_assessment(w, trk)[0] != "invalid":
                if trk.identity != "friend":
                    w.set_identity(trk.id, "friend", f"own aircraft {mine} (data link)", authority=True)
                continue
        if trk.identity in ("pending", "unknown"):
            rec, basis = recommend(w, trk)
            if rec == "friend":
                continue
            spd = math.hypot(trk.vx, trk.vy) * 1000.0
            age = w.t - trk.t_init
            why = ""
            if cls == "missile" or spd > 650.0 or (spd > 420.0 and age > 20.0):
                why = "fast mover, no IFF"
            elif trk.jammer:
                why = "jamming"
            elif ((hx is not None and trk.x < hx) or (hy is not None and trk.y > hy)) and age > 40.0:
                why = "no IFF, inbound from enemy territory"
            elif rec in ("suspect", "hostile"):
                why = basis
            if why:
                w.set_identity(trk.id, "hostile", f"battle rules: {why}", authority=True)
        if trk.identity == "hostile" and cls == "missile" and not w.vars.get(f"vamp_{trk.id}"):
            w.vars[f"vamp_{trk.id}"] = 1.0
            vamp.append(trk)
    if vamp:
        counter(w, "vampires_seen", len(vamp))
        b.red_plan.setdefault("vamp_new", []).extend(t.id for t in vamp)
    new = [w.tracks[t] for t in b.red_plan.get("vamp_new", []) if t in w.tracks and not w.tracks[t].lost]
    if new and w.t - w.vars.get("vamp_alert_t", -1e9) >= 25.0:
        pts = defended_points(w)
        trk = new[0]
        px, py = predicted(trk, w.t)
        cx, cy = min(pts, key=lambda p: math.hypot(p[0] - px, p[1] - py))
        brg = bearing_deg(px - cx, py - cy)
        d = math.hypot(px - cx, py - cy)
        first = w.t - w.vars.get("vamp_alert_t", -1e9) > 120.0
        w.vars["vamp_alert_t"] = w.t
        b.red_plan["vamp_new"] = []
        n = sum(1 for t in w.tracks.values() if not t.lost and w.vars.get(f"vamp_{t.id}"))
        many = 's' if len(new) > 1 else ''
        head = "VAMPIRE VAMPIRE" if w.faction == "US" else "MISSILE ATTACK"
        txt = f"{head} — {len(new)} new missile{many} bearing {brg:03.0f}, {d:.0f} km — {n} in the air"
        event(w, "vampire", txt, trk.id, px, py, w.own_side, 3 if first else 2)


def _assigned_strength(w: "World", tid: str) -> int:
    n = 0
    for fl in w.flights.values():
        if fl.target == tid and fl.state not in ("landed", "lost", "rtb"):
            n += max(1, sum(1 for m in fl.members if m in w.aircraft and w.aircraft[m].state == "airborne")
                     if fl.members else fl.n)
    return n


def _alert_aircraft(w: "World") -> int:
    return sum(gci.available(sq) for sq in w.squadrons.values()
               if sq.base_id in w.airbases and w.airbases[sq.base_id].runway_ok)


def sam_danger(w: "World", x: float, y: float, margin: float = 25.0) -> Optional[str]:
    """Inside the missile envelope of an enemy ship we know about?"""
    pic = w.battle.surface.get(w.own_side, {})
    for sid, c in pic.items():
        sh = w.ships.get(sid)
        if sh is None:
            continue
        reach = max((w.catalog.sams[m["type"]].range_max_km for m in w.catalog.ships[sh.type_id].sams), default=0.0)
        age = w.t - c.t
        if reach and math.hypot(c.x + c.vx * age - x, c.y + c.vy * age - y) < reach + margin + c.err_km:
            return sh.name
    return None


def _hvaa_threats(w: "World") -> dict[str, float]:
    """Hostile fighters closing on our radar aircraft: they come first."""
    out: dict[str, float] = {}
    for g in w.battle.groups.values():
        if g.side != w.own_side or g.role != "awacs" or not g.members:
            continue
        a = w.aircraft.get(g.members[0])
        if a is None or a.state != "airborne":
            continue
        for trk in w.tracks.values():
            if trk.lost or trk.identity != "hostile" or classify(w, trk) not in ("interceptor", "fighter"):
                continue
            px, py = predicted(trk, w.t)
            d = math.hypot(px - a.x, py - a.y)
            if d < 260.0:
                out[trk.id] = min(out.get(trk.id, 1e9), d)
    return out


def _commit(w: "World") -> None:
    b = w.battle
    pts = defended_points(w, aew=False)          # reach is measured from what we defend, not from the radar aircraft
    reach = REACH_KM.get(b.standing.get("posture", "balanced"), 600.0)
    hvaa = _hvaa_threats(w)
    cand = []
    for trk in w.tracks.values():
        if trk.lost or trk.identity not in ("hostile", "suspect"):
            continue
        cls = classify(w, trk)
        if cls == "missile" and math.hypot(trk.vx, trk.vy) * 1000.0 < CRUISE_MPS and w.t - trk.t_init > 20.0:
            cls = "cruise"                   # subsonic and low: an interceptor with look-down radar can catch it
        if cls in ("missile", "debris") or spared(w, trk):
            continue
        px, py = predicted(trk, w.t)
        d = min(math.hypot(px - x, py - y) for x, y in pts)
        if cls == "cruise" and d > 260.0 and trk.id not in b.priority:
            continue
        prio = trk.id in b.priority or trk.id in hvaa
        if d > reach and not prio:
            continue
        if d > 250.0 and not prio and cls in ("strike", "bomber", "recon", "ew", "patrol") and \
                _opening(trk, px, py, pts):
            continue                         # a raider going home far out is not worth the fuel
        if cls in ("interceptor", "fighter") and not prio and \
                d > (reach if b.standing.get("posture") == "aggressive" else 230.0):
            continue                         # a fighter sweep far out is bait: keep the interceptors for bombers
        if sam_danger(w, px, py) and trk.id not in b.priority:
            continue                         # not into the S-300F: let them come out
        need = 1 if cls == "cruise" else 2
        have = _assigned_strength(w, trk.id)
        if have >= need:
            continue
        score = THREAT_WEIGHT.get(cls, 1.5) * (1.0 + 300.0 / (d + 60.0)) + (10.0 if prio else 0.0)
        cand.append((score, trk, cls, d, need - have))
    cand.sort(key=lambda c: -c[0])
    done = 0
    for score, trk, cls, d, short in cand:
        if done >= 3:
            break
        keep = 0.0 if (trk.id in hvaa or cls in ("strike",)) else 260.0
        pick, why = orders.interceptor(w, trk.id, keep_cap_km=keep)
        if pick is None:
            continue
        if pick.kind == "squadron":
            urgent = cls in ("strike", "recon") and d < 450.0
            if _alert_aircraft(w) - short < int(b.standing.get("reserve", 2)) and not urgent \
                    and trk.id not in b.priority:
                continue
        ok, msg = commands.run(w, "quick", track=trk.id, order="intercept", n=min(2, max(1, short)))
        if not ok:
            continue
        done += 1
        callsign = "fighters"
        for fl in w.flights.values():
            if fl.target == trk.id and fl.state not in ("landed", "lost"):
                callsign = fl.callsign
                if not fl.weapons_free:
                    commands.run(w, "weapons_free", flight=fl.id, on=True)
        event(w, "commit", f"{callsign} committed on {trk.id} ({cls}, {d:.0f} km out)", trk.id, *predicted(trk, w.t),
              w.own_side, 1)


def _opening(trk, px: float, py: float, pts: list) -> bool:
    """The track is moving away from the nearest point we defend."""
    cx, cy = min(pts, key=lambda p: math.hypot(p[0] - px, p[1] - py))
    return (px - cx) * trk.vx + (py - cy) * trk.vy > 0.0 and math.hypot(trk.vx, trk.vy) > 0.05


def _cap(w: "World") -> None:
    b = w.battle
    for fl in w.flights.values():                  # surge and recalled flights orbit their patrol point
        if fl.task == "cap" and not fl.target and fl.cap_x is not None and fl.state in ("airborne", "vector", "hold"):
            fl.state = "cap"
    for st in b.cap_stations:
        if not st.get("on", True):
            continue
        fl = w.flights.get(st["flight"]) if st["flight"] else None
        alive = fl is not None and fl.state not in ("landed", "lost", "rtb")
        if alive and fl.task != "cap":
            tgt = w.tracks.get(fl.target) if fl.target else None
            key = f"caplost_{fl.id}"
            if tgt is None or tgt.lost or fl.state == "hold":
                w.vars.setdefault(key, w.t)
                if tgt is None or w.t - w.vars[key] >= 45.0:     # a flickering track is not a lost one
                    w.vars.pop(key, None)
                    fl.task, fl.target, fl.contact = "cap", "", ""     # job done: back to the station
                    w.radio(fl, f"returning to {st['name']}" if w.faction == "US" else "Returning to patrol.")
            else:
                w.vars.pop(key, None)
        if alive and fl.task == "cap" and not fl.target and fl.state in ("airborne", "vector", "hold"):
            fl.state = "cap"
        if alive and fl.task == "cap":
            fl.cap_x, fl.cap_y, fl.order_alt = st["x"], st["y"], st["alt"]
        rl = w.flights.get(st["relief"]) if st["relief"] else None
        rl_alive = rl is not None and rl.state not in ("landed", "lost", "rtb")
        if rl_alive:
            if rl.task == "cap" and not rl.target and rl.state in ("airborne", "vector"):
                rl.state = "cap"
            lead = gci.lead_of(w, rl)
            if lead is not None and math.hypot(lead.x - st["x"], lead.y - st["y"]) < 40.0:
                if alive and fl.task == "cap":
                    gci.begin_rtb(w, fl)
                    w.radio(fl, "relieved on station, RTB" if w.faction == "US" else "Relieved. Returning.")
                st["flight"], st["relief"] = rl.id, ""
            continue
        need = not alive
        if alive and fl.task == "cap":
            lead = gci.lead_of(w, fl)
            at = w.catalog.aircraft[fl.type_id]
            if lead is not None and lead.fuel < at.fuel_kg * 0.42:
                need = True
        if not need:
            continue
        sq = w.squadrons.get(st["squadron"])
        if sq is None or gci.available(sq) <= 0:
            continue
        base = w.airbases.get(sq.base_id)
        if base is None or not base.runway_ok:
            continue
        hdg = bearing_deg(st["x"] - base.x, st["y"] - base.y)
        ok, msg, fid = gci.scramble(w, sq.id, st["n"], "cap", hdg=hdg, alt=st["alt"])
        if not ok:
            continue
        nf = w.flights[fid]
        nf.cap_x, nf.cap_y = st["x"], st["y"]
        nf.weapons_free = True
        if alive:
            st["relief"] = fid
            event(w, "cap", f"{nf.callsign} launching to relieve {fl.callsign} on {st['name']}", fid, base.x, base.y,
                  w.own_side, 0)
        else:
            st["flight"] = fid
            event(w, "cap", f"{nf.callsign} launching for {st['name']}", fid, base.x, base.y, w.own_side, 1)


def _recall(w: "World") -> None:
    """Flights chasing a target into a known missile envelope are told to break off."""
    for fl in w.flights.values():
        if fl.state in ("landed", "lost", "rtb", "scrambling") or not fl.target:
            continue
        trk = w.tracks.get(fl.target)
        lead = gci.lead_of(w, fl)
        if trk is None or lead is None or fl.target in w.battle.priority:
            continue
        px, py = predicted(trk, w.t)
        ship = sam_danger(w, px, py, margin=10.0)
        if ship and sam_danger(w, lead.x, lead.y, margin=60.0):
            fl.target, fl.contact = "", ""
            fl.task, fl.state = "cap", "cap"
            fl.cap_x, fl.cap_y = lead.x + (lead.x - px) * 0.3, lead.y + (lead.y - py) * 0.3
            w.radio(fl, f"breaking off, {ship} missile zone" if w.faction == "US" else "Breaking off: ship SAM zone.", 1)
            event(w, "recall", f"{fl.callsign} breaks off: target inside {ship}'s missile envelope", fl.id,
                  lead.x, lead.y, w.own_side, 1)


def _self_defense(w: "World") -> None:
    """A flight that has fighters coming for it turns to fight them."""
    fighters = []
    for trk in w.tracks.values():
        if not trk.lost and trk.identity == "hostile" and classify(w, trk) in ("interceptor", "fighter") \
                and not sam_danger(w, *predicted(trk, w.t)):
            fighters.append(trk)
    if not fighters:
        return
    for fl in list(w.flights.values()):
        if fl.state in ("landed", "lost", "rtb", "scrambling") or fl.task not in ("intercept", "cap"):
            continue
        cur = w.tracks.get(fl.target) if fl.target else None
        if cur is not None and classify(w, cur) in ("interceptor", "fighter"):
            continue
        if w.t - w.vars.get(f"selfdef_{fl.id}", -1e9) < 60.0:
            continue
        lead = gci.lead_of(w, fl)
        if lead is None or not any(n > 0 for n in lead.weapons.values()):
            continue
        if cur is not None and not cur.lost and classify(w, cur) in ("strike", "bomber", "recon", "ew") and \
                math.hypot(cur.x - lead.x, cur.y - lead.y) < 90.0:
            continue                         # nearly in range of the archer: shoot it, let others take the escort
        near = min(fighters, key=lambda t: math.hypot(t.x - lead.x, t.y - lead.y))
        px, py = predicted(near, w.t)
        if math.hypot(px - lead.x, py - lead.y) > 55.0:
            continue
        if _assigned_strength(w, near.id) >= 4:
            continue                         # two flights on one pair of fighters is enough
        w.vars[f"selfdef_{fl.id}"] = w.t
        ok, _ = commands.run(w, "assign", flight=fl.id, track=near.id, task="intercept", geometry="lead")
        if ok:
            fl.weapons_free = True
            w.radio(fl, f"bandits closing, engaging {near.id}" if w.faction == "US" else "Fighters closing, attacking.",
                    1)
            event(w, "commit", f"{fl.callsign} turns to engage fighters ({near.id})", fl.id, lead.x, lead.y,
                  w.own_side, 1)


def _sams(w: "World", missiles_only: bool = False) -> None:
    b = w.battle
    tight = b.standing.get("sam", "FREE") == "TIGHT"
    ships = defended_points(w)
    load: dict[str, int] = {}
    for s in w.sams.values():
        if s.side == w.own_side and s.assigned:
            load[s.assigned] = load.get(s.assigned, 0) + 1
    live = []
    for trk in w.tracks.values():
        if trk.lost or trk.identity not in ("hostile",):
            continue
        cls = classify(w, trk)
        if cls == "debris" or (cls != "missile" and spared(w, trk)):
            continue
        px, py = predicted(trk, w.t)
        near_ship = min((math.hypot(px - x, py - y) for x, y in ships), default=1e9)
        if tight and cls != "missile" and near_ship > 60.0:
            continue
        if missiles_only and cls != "missile":
            continue                                 # ceasefire: only what is already coming at us
        live.append((trk, cls, px, py, near_ship))
    for site in w.sams.values():
        if site.side != w.own_side or site.status != "ok" or site.hold or w.t < site.t_ready:
            continue
        cur = w.tracks.get(site.assigned) if site.assigned else None
        if cur is not None and not cur.lost and site.state != "idle":
            continue
        if site.state in ("engaging", "assess") or site.ready_missiles <= 0:
            continue
        st = w.catalog.sams[site.type_id]
        if st.homing_km > 0:
            continue                                 # BOMARC needs the key
        silent = bool(site.carrier and site.carrier in w.ships and w.ships[site.carrier].emcon)
        best, bscore = None, 0.0
        for trk, cls, px, py, near_ship in live:
            d = math.hypot(px - site.x, py - site.y)
            if d > min(st.fc_range_km, st.range_max_km * 2.0):
                continue
            if silent and not (cls == "missile" and d < 30.0):
                continue                             # emission control: only a missile closing on the ship
            if trk.alt is not None and not (st.alt_min_m * 0.5 <= trk.alt <= st.alt_max_m * 1.1):
                continue
            cap = 3 if cls == "missile" else 2
            if load.get(trk.id, 0) >= cap:
                continue
            score = (8.0 if cls == "missile" else 1.0) * (1.0 + 100.0 / (near_ship + 10.0)) / (1.0 + d / 30.0)
            if score > bscore:
                best, bscore = trk, score
        if best is not None:
            ok, _ = commands.run(w, "sam_assign", site=site.id, track=best.id)
            if ok:
                site.auto = True
                load[best.id] = load.get(best.id, 0) + 1


def _aew(w: "World") -> None:
    """Fighters coming for the radar aircraft: ask the commander to pull it back."""
    b = w.battle
    fighters = [t for t in w.tracks.values() if not t.lost and t.identity == "hostile"
                and classify(w, t) in ("interceptor", "fighter")]
    for g in b.groups.values():
        if g.side != w.own_side or g.role != "awacs" or g.state in ("pending", "done", "egress"):
            continue
        a = w.aircraft.get(g.members[0]) if g.members else None
        if a is None or a.state != "airborne":
            continue
        near = [t for t in fighters if math.hypot(t.x - a.x, t.y - a.y) < 230.0]
        home = b.red_plan.get("aew_home", {}).get(g.id)
        if home is not None and g.station and not any(math.hypot(t.x - home[0], t.y - home[1]) < 320.0
                                                      for t in fighters):
            key = f"aew_clear_{g.id}"             # the threat has gone: back to the station it left
            w.vars.setdefault(key, w.t)
            if w.t - w.vars[key] >= 240.0:
                g.station = list(home)
                del b.red_plan["aew_home"][g.id]
                w.vars.pop(key, None)
                event(w, "aew", f"{g.name} back on its station — the fighters that drove it off are gone", g.id,
                      level=1)
        elif home is not None:
            w.vars.pop(f"aew_clear_{g.id}", None)
        if not near:
            continue
        if any(d.kind == "aew" and d.ref == g.id and (not d.chosen or w.t - d.t_chosen < 360.0)
               for d in b.decisions):
            continue
        ask(w, "aew", f"{g.callsign} THREATENED",
            f"{len(near)} hostile fighter track{'s' if len(near) > 1 else ''} within 230 km of {g.name}. "
            f"Pull the radar aircraft back toward the fleet (the picture to the west thins out), "
            f"or hold the station and trust the fighters?",
            ["PULL BACK", "HOLD STATION"], "PULL BACK", 40.0, g.id,
            {"PULL BACK": [{"do": "aew_withdraw", "group": g.id}], "HOLD STATION": []})


# ------------------------------------------------------------------ decisions

def ask(w: "World", kind: str, title: str, text: str, options: list[str], default: str, timeout_s: float,
        ref: str = "", effects: Optional[dict[str, list]] = None, data: Optional[dict[str, Any]] = None) -> Decision:
    b = w.battle
    b.decision_seq += 1
    timeout_s *= w.vars.get("decision_time", 1.0)          # difficulty: more (or less) time to think
    d = Decision(id=b.decision_seq, t=w.t, kind=kind, title=title, text=text, options=list(options), default=default,
                 t_expire=w.t + timeout_s, ref=ref, data=dict(data or {}, effects=dict(effects or {})))
    b.decisions.append(d)
    event(w, "decision", f"DECISION: {title}", ref, level=0 if b.spectator else 2)
    return d


def decide(w: "World", did: int, option: str, by: str = "player") -> tuple[bool, str]:
    from . import director
    d = next((x for x in w.battle.decisions if x.id == did), None)
    if d is None:
        return False, "no such decision"
    if d.chosen:
        return False, f"already decided: {d.chosen}"
    if option not in d.options:
        return False, f"options are {', '.join(d.options)}"
    d.chosen, d.t_chosen, d.by = option, w.t, by
    for a in d.data.get("effects", {}).get(option, []):
        director.act(w, a)
    who = {"player": "", "staff": " (staff)", "timeout": " (no answer — staff's call)"}.get(by, "")
    event(w, "decided", f"{d.title}: {option}{who}", d.ref, level=1)
    return True, f"{d.title}: {option}"


def decisions_step(w: "World") -> None:
    b = w.battle
    for d in b.decisions:
        if d.chosen:
            continue
        if b.spectator:
            decide(w, d.id, d.default, "staff")
        elif w.t >= d.t_expire:
            decide(w, d.id, d.default, "timeout")


def pending(w: "World") -> list[Decision]:
    return [d for d in w.battle.decisions if not d.chosen]
