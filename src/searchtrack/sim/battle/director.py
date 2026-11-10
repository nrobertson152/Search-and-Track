"""The mission director: phases, pacing, and the battle's own conditions and actions.

A battle is written as a few phases (the search, the electronic attack, the raid, the
counterstrike...). Each phase opens no earlier than its `earliest_min`; it opens when its
`when` condition comes true, or when the battle has been quiet for `quiet_s` seconds (so
the story moves on instead of idling), and at the latest at `latest_min`. Opening a phase
launches groups, poses decisions to the commander and changes the situation; everything
after that -- who finds whom, who gets through -- is simulation, not script.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .. import doctrine
from .core import event, spec_xy

if TYPE_CHECKING:
    from ..state import Objective
    from ..world import World


def step(w: "World") -> None:
    b = w.battle
    if w.tick % 2 or b.phase + 1 >= len(b.phases):
        return
    nxt = b.phases[b.phase + 1]
    t_min = w.t / 60.0
    if t_min < float(nxt.get("earliest_min", 0.0)):
        return
    go = "when" not in nxt
    if not go:
        from ..scenario import cond
        go = cond(w, nxt["when"])
    if not go and "latest_min" in nxt and t_min >= float(nxt["latest_min"]):
        go = True
    if not go and nxt.get("quiet_s") and w.t - max(b.t_last_event, b.t_phase) >= float(nxt["quiet_s"]):
        go = True
    if go:
        start_phase(w, b.phase + 1)


def start_phase(w: "World", i: int) -> None:
    b = w.battle
    b.phase, b.t_phase = i, w.t
    ph = b.phases[i]
    event(w, "phase", ph.get("name", f"PHASE {i + 1}"), ph.get("id", ""), level=3)
    if ph.get("text"):
        doctrine.send(w, "tty", ph.get("sender", w.hq.name), ph["text"], 1, False, "", "info")
    for a in ph.get("actions", []):
        act(w, a)


# ------------------------------------------------------------------ actions

ACTIONS = {"launch", "group", "decision", "standing", "reinforcement", "reinforce", "aew_withdraw", "fleet", "ready",
           "located", "end_battle", "surge", "cap_station", "salvo"}


def act(w: "World", a: dict) -> None:
    from . import air, staff
    from ..scenario import act as scenario_act
    b = w.battle
    k = a["do"]
    if k == "launch":
        for gid in a.get("groups", [a.get("group")]):
            g = b.groups.get(gid)
            if g is not None and g.state == "pending":
                g.trigger = ""
                g.t_launch = w.t + float(a.get("delay_s", 0.0))
    elif k == "group":
        g = b.groups[a["group"]]
        for key in ("jam", "target", "commit_km", "launch_km", "abort_frac", "role"):
            if key in a:
                setattr(g, key, a[key])
        if "station" in a:
            s = a["station"]
            g.station = [*spec_xy(w, s), float(s.get("alt_m", g.station[2] if g.station else g.alt)),
                         float(s.get("r_km", 25.0))]
        if "state" in a:
            g.state = a["state"]
    elif k == "decision":
        staff.ask(w, a.get("kind", "scripted"), a["title"], a["text"], list(a["options"]), a.get("default",
                  a["options"][0]), float(a.get("timeout_s", 60.0)), a.get("ref", ""), dict(a.get("effects", {})))
    elif k == "standing":
        for key in ("posture", "fighters", "sam", "emcon", "reserve"):
            if key in a:
                b.standing[key] = a[key]
                event(w, "standing", f"Standing order: {key.upper()} {str(a[key]).upper()}", "", level=1)
    elif k == "reinforcement":
        for r in b.reinforcements:
            if r["id"] == a["id"] and not r["available"]:
                r["available"] = True
                event(w, "reinforce", f"Reinforcements available: {r.get('name', r['id'])}", r["id"], level=2)
                if a.get("ask", True) and not b.spectator:
                    staff.ask(w, "reinforce", f"REQUEST {r.get('name', r['id']).upper()}?",
                              r.get("text", "Higher command can send reinforcements."), ["REQUEST", "NOT NOW"],
                              a.get("default", "REQUEST"), float(a.get("timeout_s", 90.0)), r["id"],
                              {"REQUEST": [{"do": "reinforce", "id": r["id"]}], "NOT NOW": []})
                elif b.spectator:
                    act(w, {"do": "reinforce", "id": r["id"]})
    elif k == "reinforce":
        call_reinforcement(w, a["id"])
    elif k == "aew_withdraw":
        g = b.groups.get(a["group"])
        if g is not None and g.station:
            hx, hy = air._home(w, g)
            sx, sy = g.station[0], g.station[1]
            d = math.hypot(hx - sx, hy - sy)
            f = min(1.0, float(a.get("km", 110.0)) / max(d, 1.0))
            w.vars[f"aew_station_{g.id}"] = 1.0
            g.station = [sx + (hx - sx) * f, sy + (hy - sy) * f, g.station[2], g.station[3]]
            home = "the fleet" if g.base in w.airbases and w.airbases[g.base].carrier else "its base"
            event(w, "aew", f"{g.name} falls back {a.get('km', 110):.0f} km toward {home}", g.id, level=1)
    elif k == "fleet":
        for sh in w.ships.values():
            if sh.group == a["group"] and sh.guide:
                if "route" in a:
                    sh.route = [list(spec_xy(w, p)) for p in a["route"]]
                    sh.wp = 0
                if "speed_kn" in a:
                    sh.speed_kn = float(a["speed_kn"])
        if "speed_kn" in a:
            for sh in w.ships.values():
                if sh.group == a["group"]:
                    sh.speed_kn = float(a["speed_kn"])
    elif k == "ready":
        sq = w.squadrons[a["squadron"]]
        for key, v in a.get("move", {}).items():               # e.g. {"15": "5"}: bring alert crews forward
            n = sq.ready.get(key, 0)
            if n:
                sq.ready[key] = 0
                sq.ready[v] = sq.ready.get(v, 0) + n
        for key, v in a.get("add", {}).items():
            sq.ready[key] = sq.ready.get(key, 0) + int(v)
            sq.pilots += int(v)
    elif k == "surge":
        surge(w, a)
    elif k == "cap_station":
        for st in b.cap_stations:
            if st["id"] == a["id"]:
                st["x"], st["y"] = spec_xy(w, a)
                if "alt_m" in a:
                    st["alt"] = float(a["alt_m"])
                event(w, "cap", f"{st['name']} moves to its new station", st["id"], st["x"], st["y"], w.own_side, 1)
    elif k == "located":
        b.red_plan["located"] = True
        b.red_plan["t_located"] = w.t
    elif k == "salvo":
        from . import land
        land.salvo(w, a)
    elif k == "end_battle":
        b.end_t = w.t + float(a.get("delay_s", 30.0))
    else:
        scenario_act(w, a)


def surge(w: "World", a: dict) -> int:
    """Launch the ready alert aircraft in pairs to a forward patrol point on the threat axis."""
    from .. import gci
    from ..geo import bearing_deg
    x, y = spec_xy(w, a)
    alt = float(a.get("alt_m", 9000.0))
    n_fl = 0
    for sqid in a.get("squadrons", []):
        sq = w.squadrons.get(sqid)
        if sq is None:
            continue
        base = w.airbases.get(sq.base_id)
        if base is None or not base.runway_ok:
            continue
        for _ in range(int(a.get("max_flights", 3))):
            if gci.available(sq) < 1 or int(w.battle.standing.get("reserve", 0)) >= sum(
                    gci.available(q) for q in w.squadrons.values()):
                break
            ok, msg, fid = gci.scramble(w, sq.id, 2, "cap", hdg=bearing_deg(x - base.x, y - base.y), alt=alt)
            if not ok:
                break
            fl = w.flights[fid]
            fl.cap_x, fl.cap_y, fl.weapons_free = x, y, True
            n_fl += 1
    if n_fl:
        event(w, "surge", f"Surge: {n_fl} flight{'s' if n_fl > 1 else ''} launching to the threat axis", "", x, y,
              w.own_side, 2)
    return n_fl


def call_reinforcement(w: "World", rid: str) -> tuple[bool, str]:
    b = w.battle
    r = next((x for x in b.reinforcements if x["id"] == rid), None)
    if r is None:
        return False, "no such reinforcement"
    if not r["available"]:
        return False, "not available yet"
    if r["called"]:
        return False, "already on the way"
    r["called"] = True
    for a in r.get("actions", []):
        act(w, a)
    event(w, "reinforce", f"{r.get('name', rid)}: on the way", rid, level=2)
    return True, f"{r.get('name', rid)} requested"


# ------------------------------------------------------------------ conditions

def cond(w: "World", c: dict) -> Optional[bool]:
    """Battle conditions for triggers and phases; None if the type is not a battle condition."""
    b = w.battle
    t = c.get("type")
    if t == "located":
        return bool(b.red_plan.get("located"))
    if t == "phase":
        return b.phase >= int(c["at_least"])
    if t == "group":
        g = b.groups.get(c["group"])
        return g is not None and g.state in c["is"]
    if t == "group_losses":
        g = b.groups.get(c["group"])
        return g is not None and g.losses >= int(c.get("n", 1))
    if t == "released":
        return any(b.groups[gid].released for gid in c["groups"] if gid in b.groups)
    if t == "counter":
        return b.counters.get(c["name"], 0.0) >= float(c.get("n", 1))
    if t == "ship":
        sh = w.ships.get(c["ship"])
        if sh is None:
            return False
        if "is" in c:
            return sh.state in c["is"]
        return sh.hp / max(sh.max_hp, 1.0) < float(c.get("below", 0.5))
    if t == "decision":
        return any(d.kind == c.get("kind", d.kind) and (d.title == c["title"] if "title" in c else True)
                   and d.chosen == c["chosen"] for d in b.decisions)
    if t == "vampires":
        n = sum(1 for a in w.aircraft.values() if a.state == "airborne" and a.aim
                and a.side == c.get("side", "red"))
        return n >= int(c.get("n", 1))
    if t == "quiet":
        return w.t - b.t_last_event >= float(c.get("s", 120.0))
    if t == "standing":
        return b.standing.get(c["key"]) in c["is"]
    if t == "installation":
        from . import land
        return land.is_destroyed(w, c["id"]) if c.get("is", "out") == "destroyed" else land.is_out(w, c["id"])
    return None


# ------------------------------------------------------------------ objectives

def objective(w: "World", o: "Objective", final: bool) -> Optional[str]:
    """Battle objective kinds: returns 'done', 'failed', or None (still open / not ours)."""
    b = w.battle
    p = o.params
    k = o.kind
    if k == "ship_survives":
        sh = w.ships.get(p["ship"])
        if sh is None or sh.state == "sunk" or (p.get("strict") and sh.state == "crippled"):
            return "failed"
        return "done" if final else None
    if k == "ships_survive":
        lost = sum(1 for s in w.ships.values() if s.side == w.own_side and s.state == "sunk")
        if lost > int(p.get("max", 0)):
            return "failed"
        return "done" if final else None
    if k == "kill_fraction":
        n = sum(b.groups[g].n for g in p["groups"] if g in b.groups)
        lost = sum(b.groups[g].losses for g in p["groups"] if g in b.groups)
        if n and lost / n >= float(p.get("frac", 0.5)):
            return "done"
        return "failed" if final else None
    if k == "kill_before_release":
        gs = [b.groups[g] for g in p["groups"] if g in b.groups]
        if gs and all(g.state == "done" and not g.released for g in gs if g.state != "pending") and \
                all(g.state != "pending" for g in gs) and not any(g.released for g in gs):
            return "done"
        if any(g.released for g in gs) and sum(1 for g in gs if g.released) >= int(p.get("max_released", 1)):
            return "failed"
        return "failed" if final else None
    if k == "sink":
        hit = sum(1 for s in p["ships"] if s in w.ships and w.ships[s].state in ("sunk", "crippled"))
        if hit >= int(p.get("n", 1)):
            return "done"
        return "failed" if final else None
    if k == "deny_location":
        if b.red_plan.get("located") and b.red_plan.get("t_located", 0.0) < float(p.get("before_min", 1e9)) * 60.0:
            return "failed"
        return "done" if final or w.t >= float(p.get("before_min", 1e9)) * 60.0 else None
    if k == "protect_group":
        g = b.groups.get(p["group"])
        if g is not None and g.losses >= g.n:
            return "failed"
        return "done" if final else None
    if k == "lose_at_most":
        if b.counters.get(f"aircraft_lost_{w.own_side}", 0.0) > float(p.get("n", 6)):
            return "failed"
        return "done" if final else None
    if k == "hold_area":                     # a ship stays on its patrol line until a given time
        sh = w.ships.get(p["ship"])
        x, y = spec_xy(w, p)
        if sh is None or sh.state in ("sunk", "crippled") or \
                math.hypot(sh.x - x, sh.y - y) > float(p.get("r_km", 60.0)):
            return "failed"
        return "done" if final or w.t >= float(p.get("until_min", 45.0)) * 60.0 else None
    if k == "runways":                       # never more than max_closed of these airfields shut at once
        closed = sum(1 for bid in p["bases"] if bid in w.airbases and not w.airbases[bid].runway_ok)
        if closed > int(p.get("max_closed", 1)):
            return "failed"
        return "done" if final else None
    if k == "radars_survive":
        from . import land
        sites = p.get("sites") or [r.id for r in w.radars.values() if not r.carrier]
        if sum(1 for r in sites if land.is_destroyed(w, r)) > int(p.get("max_destroyed", 0)):
            return "failed"
        return "done" if final else None
    if k == "missiles_stopped":              # shot down before they reached their targets
        fired = sum(b.counters.get(f"fired_{m}", 0.0) for m in p["types"])
        killed = sum(b.counters.get(f"killed_{m}", 0.0) for m in p["types"])
        planned = float(p.get("planned", 0.0))
        if planned and killed >= planned * float(p.get("frac", 0.5)):
            return "done"
        if final:
            return "done" if fired and killed / fired >= float(p.get("frac", 0.5)) else "failed"
        return None
    return None
