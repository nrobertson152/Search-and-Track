"""Command processor: the only way the UI changes the simulation.

Every command is validated against existence, doctrine, ROE, authority and
communications; the result (ok, reason) is shown to the player and logged."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from . import doctrine, gci, orders, sam, tracking
from .world import World

Result = tuple[bool, str]


@dataclass
class Command:
    kind: str
    args: dict[str, Any] = field(default_factory=dict)


_HANDLERS: dict[str, Callable[..., Result]] = {}


def handler(name: str):
    def deco(fn):
        _HANDLERS[name] = fn
        return fn
    return deco


def execute(world: World, cmd: Command) -> Result:
    fn = _HANDLERS.get(cmd.kind)
    if fn is None:
        return False, f"unknown command {cmd.kind}"
    if world.ended and cmd.kind not in ("ack", "ack_all", "ui_event"):
        return False, "Scenario has ended"
    try:
        ok, msg = fn(world, **cmd.args)
    except KeyError as e:
        ok, msg = False, f"not found: {e}"
    if cmd.kind not in ("ack", "ack_all", "ui_event"):
        world.log_event("cmd", f"{'' if ok else 'REJECTED '}{cmd.kind}: {msg}", str(cmd.args.get("track", "")))
    return ok, msg


def run(world: World, kind: str, /, **args) -> Result:
    return execute(world, Command(kind, args))


def kinds() -> list[str]:
    return sorted(_HANDLERS)


# ------------------------------------------------------------------ surveillance / identification

@handler("initiate")
def _initiate(w: World, x: float, y: float, radius: float = 12.0) -> Result:
    if w.faction_def.pipeline == "manual":
        return False, "Targets are entered from radar company reports"
    if not w.c2_up():
        return False, "Computer off line — cannot initiate"
    trk = tracking.initiate_at(w, x, y, radius)
    if trk is None:
        return False, "No unassociated returns at light-gun position"
    return True, f"Track {trk.id} initiated"


@handler("drop_track")
def _drop(w: World, track: str) -> Result:
    trk = w.tracks.pop(track, None)
    if trk is None:
        return False, "no such track"
    truth = tracking.truth_of(trk)
    ac = w.aircraft.get(truth) if truth else None
    if ac is not None and ac.kind == "ghost":
        w.vars["ghosts_dropped"] = w.vars.get("ghosts_dropped", 0.0) + 1
    elif ac is not None and ac.kind == "aircraft":
        w.vars["real_dropped"] = w.vars.get("real_dropped", 0.0) + 1
    w.on_track_removed(track)
    for fl in w.flights.values():
        if fl.target == track:
            fl.target = ""
    return True, f"Track {track} dropped"


@handler("merge")
def _merge(w: World, track: str, into: str) -> Result:
    a, b = w.tracks.get(track), w.tracks.get(into)
    if a is None or b is None or a is b:
        return False, "select two different tracks"
    if math.hypot(a.x - b.x, a.y - b.y) > 60.0:
        return False, "tracks too far apart to be the same target"
    for k, v in a.truth_votes.items():
        b.truth_votes[k] = b.truth_votes.get(k, 0) + v
    b.company_keys.extend(a.company_keys)
    b.sources.update(a.sources)
    if b.alt is None and a.alt is not None:
        b.alt, b.alt_src, b.alt_t = a.alt, a.alt_src, a.alt_t
    if b.identity == "pending":
        b.identity = a.identity
    del w.tracks[track]
    w.on_track_removed(track)
    for fl in w.flights.values():
        if fl.target == track:
            fl.target = into
    return True, f"{track} merged into {into}"


@handler("identity")
def _identity(w: World, track: str, ident: str) -> Result:
    if ident not in ("pending", "friend", "unknown", "suspect", "hostile", "faker"):
        return False, "invalid identity"
    return w.set_identity(track, ident, "operator")


@handler("height")
def _height(w: World, track: str) -> Result:
    return w.request_height(track, front=True)


@handler("report")
def _report(w: World, track: str) -> Result:
    trk = w.tracks.get(track)
    if trk is None:
        return False, "no such track"
    trk.reported = True
    w.stats.reports_to_hq += 1
    alt = f"{trk.alt / 0.3048 / 1000:.0f}k ft" if (trk.alt is not None and w.faction == "US") else \
        (f"{trk.alt:,.0f} m" if trk.alt is not None else "alt unknown")
    spd = math.hypot(trk.vx, trk.vy) * 3600.0
    hdg = (math.degrees(math.atan2(trk.vx, trk.vy)) % 360.0)
    pos = tracking.grid_label(w, trk.x, trk.y) if w.faction_def.pipeline == "manual" else f"{trk.x:.0f}/{trk.y:.0f}"
    text = f"TRACK {trk.id} {doctrine.id_label(w, trk.identity)} AT {pos}, {alt}, HDG {hdg:03.0f}, {spd:.0f} KM/H, SIZE {trk.size}"
    doctrine.send(w, "voice", "SD" if w.faction == "US" else "DUTY OFFICER", "Reported to HQ: " + text, 0, False, track,
                  "report")
    return True, "Reported to higher HQ"


@handler("request")
def _request(w: World, kind: str, track: str = "", value: str = "") -> Result:
    if kind in ("declare_hostile", "engage", "ram") and track not in w.tracks:
        return False, "select a track"
    for r in w.hq.requests:
        if not r.answered and r.kind == kind and r.ref == track and r.value == value:
            return False, "request already pending with HQ"
    req = doctrine.request(w, kind, track, value)
    return True, f"Request sent to {w.hq.name}; answer expected in ~{(req.t_answer - w.t) / 60:.0f} min"


# ------------------------------------------------------------------ interceptors

@handler("scramble")
def _scramble(w: World, squadron: str, n: int = 2, task: str = "intercept", track: str = "",
              geometry: str = "lead") -> Result:
    if track and track not in w.tracks:
        return False, "no such track"
    ok, msg, _ = gci.scramble(w, squadron, n, task, track, geometry)
    return ok, msg


def _flight(w: World, flight: str):
    fl = w.flights.get(flight)
    if fl is None or fl.state in ("landed", "lost"):
        raise KeyError(flight)
    return fl


@handler("assign")
def _assign(w: World, flight: str, track: str, task: str = "", geometry: str = "") -> Result:
    fl = _flight(w, flight)
    if track not in w.tracks:
        return False, "no such track"
    fl.target = track
    fl.contact, fl.tally, fl.vid_done = "", False, False
    if task:
        fl.task = task
    if geometry:
        fl.geometry = geometry
    fl.auto = True
    if fl.state not in ("scrambling",):
        fl.state = "vector"
    return True, f"{fl.callsign} committed on {track} ({fl.task}, {fl.geometry})"


@handler("vector")
def _vector(w: World, flight: str, hdg: float | None = None, alt: float | None = None, throttle: str = "") -> Result:
    fl = _flight(w, flight)
    fl.auto = False
    if hdg is not None:
        fl.order_hdg = hdg % 360.0
    if alt is not None:
        fl.order_alt = alt
    if throttle:
        fl.order_throttle = throttle
    if fl.state == "scrambling":
        return True, f"{fl.callsign}: initial vector set"
    gci.issue_vector(w, fl, fl.order_hdg, fl.order_alt, fl.order_throttle or "mil", force=True)
    return True, f"{fl.callsign}: manual vector {fl.order_hdg or 0:03.0f}°"


@handler("auto")
def _auto(w: World, flight: str, on: bool = True) -> Result:
    fl = _flight(w, flight)
    fl.auto = on
    return True, f"{fl.callsign}: {'computer' if on else 'manual'} vectors"


@handler("task")
def _task(w: World, flight: str, task: str) -> Result:
    fl = _flight(w, flight)
    if task == "ram":
        if fl.target not in w.hq.engage_ok:
            return False, "Ramming requires permission from the command post (REQUEST RAM)"
    if task == "cap":
        lead = gci.lead_of(w, fl)
        if lead is not None:
            fl.cap_x, fl.cap_y = lead.x, lead.y
        fl.state = "cap"
    elif fl.state == "cap":
        fl.state = "vector"
    fl.task = task
    return True, f"{fl.callsign}: task {task.upper()}"


@handler("weapons_free")
def _wf(w: World, flight: str, on: bool = True) -> Result:
    fl = _flight(w, flight)
    if on:
        trk = w.tracks.get(fl.target)
        ok, why = doctrine.can_engage_track(w, trk)
        if not ok:
            return False, why
    fl.weapons_free = on
    if on:
        w.radio(fl, "cleared to fire, roger" if w.faction == "US" else "Understood, attack permitted.", 1)
    return True, f"{fl.callsign}: weapons {'FREE' if on else 'HOLD'}"


@handler("special")
def _special(w: World, flight: str, on: bool = True) -> Result:
    fl = _flight(w, flight)
    if on and not w.hq.special_release:
        return False, "Special weapons not released by higher authority"
    fl.special_release = on
    return True, f"{fl.callsign}: special weapons {'ARMED' if on else 'SAFE'}"


@handler("warning_shots")
def _warning_shots(w: World, flight: str) -> Result:
    fl = _flight(w, flight)
    c = w.aircraft.get(fl.contact) if fl.contact else None
    lead = gci.lead_of(w, fl)
    if c is None or lead is None or not fl.vid_done:
        return False, f"{fl.callsign}: must be alongside the target (visual contact) to fire a warning burst"
    if math.hypot(c.x - lead.x, c.y - lead.y) > 2.5:
        return False, f"{fl.callsign}: too far from the target for a warning burst"
    guns = [k for k, v in lead.weapons.items() if v and w.catalog.weapons[k].kind == "gun"]
    w.log_event("weapons", f"{fl.callsign} fired a warning burst near {c.callsign}", c.id)
    if c.mission is not None:
        seen = (not w.weather.night) or w.rng.random() < 0.55
        c.mission.warned = c.mission.warned or seen
    w.radio(fl, ("warning burst fired, tracers" if guns else "warning: no gun aboard, firing rockets wide")
            if w.faction_def.id == "US" else ("Fired a warning burst." if guns else "No cannon — fired rockets wide."),
            priority=1)
    return True, f"{fl.callsign}: warning burst fired"


@handler("rtb")
def _rtb(w: World, flight: str, base: str = "") -> Result:
    fl = _flight(w, flight)
    if fl.state == "scrambling":
        sq = w.squadrons[fl.squadron_id]
        sq.ready["5"] = sq.ready.get("5", 0) + fl.n
        sq.airborne -= fl.n
        sq.pilots += fl.n
        fl.state = "landed"
        return True, f"{fl.callsign}: scramble cancelled"
    gci.begin_rtb(w, fl, base)
    return True, f"{fl.callsign}: return to base"


@handler("cap")
def _cap(w: World, flight: str, x: float, y: float, alt: float | None = None) -> Result:
    fl = _flight(w, flight)
    fl.cap_x, fl.cap_y = x, y
    if alt is not None:
        fl.order_alt = alt
    fl.state, fl.task = "cap", "cap"
    return True, f"{fl.callsign}: CAP at {x:.0f}/{y:.0f}"


@handler("control")
def _control(w: World, flight: str, mode: str) -> Result:
    fl = _flight(w, flight)
    if mode == "datalink" and not w.datalink_ok(fl):
        return False, "Data link not available for this aircraft/computer state"
    fl.control = mode
    return True, f"{fl.callsign}: control by {mode.upper()}"


@handler("controller")
def _controller(w: World, flight: str, site: str) -> Result:
    fl = _flight(w, flight)
    if site not in w.radars or not w.radars[site].gci:
        return False, "not a guidance point"
    fl.controller = site
    return True, f"{fl.callsign} handed to guidance point {w.radars[site].name}"


@handler("throttle")
def _throttle(w: World, flight: str, throttle: str) -> Result:
    fl = _flight(w, flight)
    fl.order_throttle = throttle
    gci.issue_vector(w, fl, None, None, throttle, force=True)
    return True, f"{fl.callsign}: {'BUSTER' if throttle == 'ab' else throttle.upper()}"


@handler("readiness")
def _readiness(w: World, squadron: str, bucket: float, n: int = 1) -> Result:
    sq = w.squadrons[squadron]
    slower = sum(v for k, v in sq.ready.items() if float(k) > bucket) - len(sq.upgrading)
    n = min(n, slower)
    if n <= 0:
        return False, "No aircraft at lower readiness to upgrade"
    for i in range(n):
        prep = max(120.0, (min(float(k) for k, v in sq.ready.items() if float(k) > bucket and v > 0) - bucket) * 45.0)
        sq.upgrading.append([w.t + prep + i * 60.0, float(bucket)])
    return True, f"{sq.name}: {n} aircraft to {bucket:g}-minute readiness"


@handler("quick")
def _quick(w: World, track: str, order: str, n: int = 2) -> Result:
    """One-click order: the duty officer picks the unit (see sim/orders.py)."""
    if track not in w.tracks or w.tracks[track].lost:
        return False, "no such track"
    if order in orders.TASKS:
        pick, why = orders.interceptor(w, track)
        if pick is None:
            return False, f"No interceptor available — {why}"
        geometry = "lead" if order == "intercept" else "stern"
        if pick.kind == "flight" and w.flights[pick.id].target == track:
            fl = w.flights[pick.id]
            if fl.task == order:
                return False, f"{fl.callsign} is already on {track} ({order.upper()})"
            fl.geometry = geometry
            ok, msg = _task(w, flight=pick.id, task=order)
        elif pick.kind == "flight":
            ok, msg = _assign(w, flight=pick.id, track=track, task=order, geometry=geometry)
        else:
            ok, msg = _scramble(w, squadron=pick.id, n=n, task=order, track=track, geometry=geometry)
        return ok, msg
    if order == "missiles":
        pick, why = orders.missile_unit(w, track)
        if pick is None:
            return False, f"No missile unit available — {why}"
        s = w.sams[pick.id]
        if w.t < s.t_ready and s.t_ready > w.t + s.readiness_min * 60.0:
            _sam_alert(w, site=s.id)
        return _sam_assign(w, site=pick.id, track=track)
    return False, f"unknown order {order}"


# ------------------------------------------------------------------ battle command

@handler("decide")
def _decide(w: World, decision: int, option: str) -> Result:
    from .battle import staff
    return staff.decide(w, int(decision), option, "player")


@handler("standing")
def _standing(w: World, key: str, value) -> Result:
    if not w.battle.active:
        return False, "no battle in progress"
    allowed = {"posture": ("aggressive", "balanced", "defensive"), "fighters": ("auto", "manual"),
               "sam": ("FREE", "TIGHT", "HOLD"), "emcon": (True, False), "reserve": tuple(range(0, 13))}
    if key not in allowed or value not in allowed[key]:
        return False, f"standing order {key}: not {value}"
    w.battle.standing[key] = value
    from .battle.core import event
    event(w, "standing", f"Standing order: {key.upper()} {str(value).upper()}", "", level=1)
    return True, f"Standing order {key.upper()}: {str(value).upper()}"


@handler("priority")
def _priority(w: World, track: str, on: bool = True) -> Result:
    if track not in w.tracks:
        return False, "no such track"
    pr = w.battle.priority
    if on and track not in pr:
        pr.append(track)
    elif not on and track in pr:
        pr.remove(track)
    return True, f"{track}: {'PRIORITY TARGET — staff commits on it first' if on else 'priority cleared'}"


@handler("reinforce")
def _reinforce(w: World, id: str) -> Result:
    from .battle.director import call_reinforcement
    return call_reinforcement(w, id)


@handler("spectator")
def _spectator(w: World, on: bool) -> Result:
    if not w.battle.active:
        return False, "no battle in progress"
    w.battle.spectator = bool(on)
    return True, "Spectating: the staff commands both sides" if on else "You have the command"


# ------------------------------------------------------------------ missiles

@handler("sam_assign")
def _sam_assign(w: World, site: str, track: str) -> Result:
    s = w.sams[site]
    if track not in w.tracks:
        return False, "no such track"
    st = w.catalog.sams[s.type_id]
    if st.homing_km > 0:
        return False, "BOMARC is launched with the Senior Director's key (LAUNCH)"
    link = w.links.get(s.link)
    if link is not None and not link.up:
        return False, f"Line to {s.name} DOWN"
    trk = w.tracks[track]
    px, py = tracking.predicted(trk, w.t)
    if math.hypot(px - s.x, py - s.y) > st.acq_range_km * 1.3:
        return False, f"{track} beyond {s.name} acquisition range"
    s.assigned, s.state, s.lock, s.hold = track, "idle", "", False
    via = "via AADCP (Missile Master)" if st.controller == "army" else ""
    return True, f"{s.name}: target designation {track} {via}".strip()


@handler("sam_hold")
def _sam_hold(w: World, site: str, on: bool = True) -> Result:
    s = w.sams[site]
    s.hold = on
    if on and s.state == "engaging":
        s.salvo_left = 0
    return True, f"{s.name}: {'HOLD FIRE' if on else 'hold released'}"


@handler("sam_cancel")
def _sam_cancel(w: World, site: str) -> Result:
    s = w.sams[site]
    s.assigned, s.state, s.lock, s.salvo_left = "", "idle", "", 0
    return True, f"{s.name}: designation cancelled"


@handler("sam_auto")
def _sam_auto(w: World, site: str, on: bool = True) -> Result:
    w.sams[site].auto = on
    return True, f"{w.sams[site].name}: re-engagement {'AUTOMATIC' if on else 'ON ORDER'}"


@handler("sam_salvo")
def _sam_salvo(w: World, site: str, n: int) -> Result:
    s = w.sams[site]
    st = w.catalog.sams[s.type_id]
    s.salvo_size = max(1, min(n, st.salvo))
    return True, f"{s.name}: salvo {s.salvo_size}"


@handler("sam_alert")
def _sam_alert(w: World, site: str) -> Result:
    s = w.sams[site]
    if w.t >= s.t_ready:
        return False, f"{s.name} already at readiness"
    s.t_ready = min(s.t_ready, w.t + s.readiness_min * 60.0)
    return True, f"{s.name}: brought to readiness, ready in {s.readiness_min:.0f} min"


@handler("bomarc")
def _bomarc(w: World, site: str, track: str, key: bool = False) -> Result:
    s = w.sams[site]
    if not key:
        return False, "Senior Director's key not turned"
    trk = w.tracks.get(track)
    ok, why = doctrine.can_engage_track(w, trk)
    if not ok:
        return False, why
    if not w.c2_up():
        return False, "Computer off line — BOMARC requires SAGE guidance"
    return sam.bomarc_launch(w, s, track)


# ------------------------------------------------------------------ radar & technical

def _site(w: World, site: str):
    return w.radars[site]


@handler("radar_mti")
def _mti(w: World, site: str, on: bool) -> Result:
    s = _site(w, site)
    if not w.catalog.radars[s.type_id].mti:
        return False, f"{s.name} has no MTI"
    s.mti = on
    return True, f"{s.name}: MTI {'ON' if on else 'OFF'}"


@handler("radar_pfa")
def _pfa(w: World, site: str, exp: float) -> Result:
    s = _site(w, site)
    s.pfa_exp = max(3.0, min(9.0, exp))
    return True, f"{s.name}: threshold Pfa 1e-{s.pfa_exp:.1f}"


@handler("radar_rpm")
def _rpm(w: World, site: str, rpm: float) -> Result:
    s = _site(w, site)
    rt = w.catalog.radars[s.type_id]
    opts = rt.rpm_options or [rt.rpm]
    if rpm not in opts:
        return False, f"{s.name}: rpm options {opts}"
    s.rpm = rpm
    return True, f"{s.name}: antenna {rpm:g} rpm"


@handler("radar_channel")
def _channel(w: World, site: str, channel: int) -> Result:
    s = _site(w, site)
    rt = w.catalog.radars[s.type_id]
    if not 0 <= channel < rt.channels:
        return False, f"{s.name}: {rt.channels} channel(s)"
    s.channel = channel
    return True, f"{s.name}: frequency channel {channel + 1}"


@handler("radar_iff")
def _iff(w: World, site: str, on: bool) -> Result:
    s = _site(w, site)
    s.iff_on = on
    return True, f"{s.name}: IFF interrogator {'ON' if on else 'OFF'}"


@handler("radar_maint")
def _maint(w: World, site: str, minutes: float = 30.0) -> Result:
    s = _site(w, site)
    if s.status == "down":
        return False, f"{s.name} is down — repair crew already working"
    s.status = "maint"
    s.maint_until = w.t + minutes * 60.0
    return True, f"{s.name}: preventive maintenance, off the air {minutes:.0f} min"


@handler("switchover")
def _switch(w: World) -> Result:
    if w.faction != "US":
        return False, "No computer at this command post"
    return w.switchover()


@handler("automation")
def _automation(w: World, position: str, on: bool) -> Result:
    if position not in ("surveil", "ident", "height", "tech"):
        return False, "unknown position"
    w.automation[position] = on
    return True, f"{position.upper()} position: {'AUTOMATED' if on else 'MANUAL'}"


@handler("ack")
def _ack(w: World, mid: int) -> Result:
    return (True, "acknowledged") if doctrine.acknowledge(w, mid) else (False, "nothing to acknowledge")


@handler("ui_event")
def _ui_event(w: World, name: str) -> Result:
    """A console action the instructor watches for (switching displays and consoles)."""
    key = "ui_" + "".join(ch if ch.isalnum() else "_" for ch in name.lower())
    w.vars[key] = w.vars.get(key, 0.0) + 1.0
    return True, ""


@handler("ack_all")
def _ack_all(w: World) -> Result:
    n = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered and doctrine.acknowledge(w, m.mid))
    return True, f"{n} acknowledged"
