"""Interceptor operations: scramble, ground-controlled interception (data link
or voice, with delays), airborne radar contact, visual identification,
shadowing, weapons employment, ramming, fuel/bingo and recovery."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from . import flight as flight_mod, intercept
from .flight import cruise_speed, fuel_flow, ground_velocity, max_speed, mil_speed, react_to_intercept
from .geo import FT, angle_diff, bearing_deg, heading_vec, radar_horizon_km
from .state import Aircraft, Flight, Missile, PendingOrder, Transponder
from .tracking import predicted

if TYPE_CHECKING:
    from .world import World

DEFAULT_ALT = 9000.0


# ------------------------------------------------------------------ scramble

def available(sq) -> int:
    return sum(sq.ready.values())


def scramble(world: "World", sq_id: str, n: int, task: str, target: str = "", geometry: str = "lead",
             hdg: Optional[float] = None, alt: Optional[float] = None) -> tuple[bool, str, str]:
    sq = world.squadrons.get(sq_id)
    if sq is None:
        return False, "No such squadron", ""
    base = world.airbases[sq.base_id]
    if not base.runway_ok:
        return False, f"{base.name}: runway closed", ""
    link = world.links.get(base.link)
    if link is not None and not link.up:
        return False, f"Line to {base.name} is DOWN — order cannot be passed", ""
    if world.weather.ceiling_m < 150.0:
        return False, f"{base.name}: below scramble minimums", ""
    n = max(1, min(n, available(sq), sq.pilots))
    if available(sq) <= 0 or sq.pilots <= 0:
        return False, f"{sq.name}: no aircraft on alert", ""
    buckets = sorted(sq.ready, key=lambda k: float(k))
    delay = 0.0
    taken = 0
    for b in buckets:
        while sq.ready[b] > 0 and taken < n:
            sq.ready[b] -= 1
            taken += 1
            delay = max(delay, float(b) * 60.0 * world.rng.uniform(0.55, 0.85))
    sq.airborne += taken
    sq.pilots -= taken
    delay += (link.delay_s if link else 10.0)
    no = sq.next_no
    sq.next_no += 1
    callsign = f"{sq.callsign} {no:02d}" if world.faction_def.id == "US" else f"{sq.callsign}{no:02d}"
    fid = world.next_id("fl")
    at = world.catalog.aircraft[sq.type_id]
    control = "datalink" if (at.datalink == "sage" and world.faction_def.id == "US") else "voice"
    fl = Flight(id=f"FL{fid}", callsign=callsign, squadron_id=sq.id, base_id=base.id, type_id=sq.type_id,
                n=taken, t_order=world.t, t_airborne=world.t + delay, task=task, target=target,
                geometry=geometry, control=control, order_hdg=hdg, order_alt=alt,
                controller=world.default_controller(base.x, base.y))
    world.flights[fl.id] = fl
    world.stats.sorties += taken
    if target and target in world.tracks:
        world.tracks[target].note = (world.tracks[target].note + f" {callsign}").strip()
    world.log_event("weapon", f"SCRAMBLE {sq.name} x{taken} as {callsign} ({task}"
                              f"{' ' + target if target else ''}), airborne in ~{delay / 60:.0f} min", fl.id)
    return True, f"{callsign}: scramble ordered, {taken} aircraft, airborne ~{delay / 60:.1f} min", fl.id


def launch(world: "World", fl: Flight) -> None:
    sq = world.squadrons[fl.squadron_id]
    base = world.airbases[fl.base_id]
    at = world.catalog.aircraft[fl.type_id]
    first_hdg = fl.order_hdg
    if first_hdg is None and fl.target in world.tracks:
        trk = world.tracks[fl.target]
        px, py = predicted(trk, world.t)
        first_hdg = bearing_deg(px - base.x, py - base.y)
    for i in range(fl.n):
        tr = Transponder(system=at.transponder, on=True, codes=dict(world.squadron_codes(sq)))
        ac = Aircraft(id=f"{fl.id}-{i + 1}", type_id=fl.type_id, callsign=fl.callsign + ("" if i == 0 else f"-{i + 1}"),
                      side=world.own_side, x=base.x - 0.8 * i, y=base.y - 0.8 * i, alt=base.elev + 60.0,
                      hdg=first_hdg or 0.0, spd=110.0, fuel=at.fuel_kg, throttle="ab" if at.ff_ab else "mil",
                      transponder=tr, flight_id=fl.id, home_base=base.id, weapons=dict(sq.loadout),
                      t_spawn=world.t, truth_label=at.name, nationality=world.faction_def.short)
        world.aircraft[ac.id] = ac
        fl.members.append(ac.id)
    fl.state = "vector" if (fl.target or fl.order_hdg is not None) else "airborne"
    if fl.order_alt is None:
        fl.order_alt = DEFAULT_ALT
    for mid in fl.members:
        a = world.aircraft[mid]
        a.cmd_hdg = first_hdg
        a.cmd_alt = fl.order_alt
    world.radio(fl, "airborne" if world.faction_def.id == "US" else "Airborne, climbing.")


# ------------------------------------------------------------------ helpers

def lead_of(world: "World", fl: Flight) -> Optional[Aircraft]:
    for mid in fl.members:
        a = world.aircraft.get(mid)
        if a is not None and a.state == "airborne":
            return a
    return None


def radio_ok(world: "World", ac: Aircraft) -> bool:
    for site in world.radars.values():
        if site.side != world.own_side:
            continue
        if math.hypot(ac.x - site.x, ac.y - site.y) <= radar_horizon_km(site.h_ant, ac.alt) * 1.05 + 20.0:
            return True
    return False


def controller_estimate(world: "World", fl: Flight):
    trk = world.tracks.get(fl.target)
    if trk is None:
        return None
    if world.faction_def.pipeline == "manual" and fl.controller:
        site = world.radars.get(fl.controller)
        local = world.local_tracks.get(fl.controller, {})
        px, py = predicted(trk, world.t)
        best, bd = None, 45.0
        for lt in local.values():
            if lt.lost or world.t - lt.t_update > 25.0:
                continue
            lx, ly = predicted(lt, world.t)
            d = math.hypot(lx - px, ly - py)
            # guidance officers correlate by position and by what the army plot says
            if d < bd:
                best, bd = lt, d
        if best is not None and site is not None:
            lx, ly = predicted(best, world.t)
            return lx, ly, best.vx, best.vy, best.alt if best.alt is not None else trk.alt, 0.0, "local"
    px, py = predicted(trk, world.t)
    return px, py, trk.vx, trk.vy, trk.alt, world.t - trk.t_update, "system"


def issue_vector(world: "World", fl: Flight, hdg: Optional[float], alt: Optional[float], throttle: str,
                 force: bool = False) -> None:
    lead = lead_of(world, fl)
    if lead is None:
        return
    dl = fl.control == "datalink" and world.datalink_ok(fl)
    min_gap = 4.0 if dl else 40.0
    changed = (hdg is not None and abs(angle_diff(hdg, fl.last_vec_hdg)) > (3.0 if dl else 8.0)) or \
              (alt is not None and abs(alt - fl.last_vec_alt) > 450.0)
    if not force and not changed and world.t - fl.last_vector_t < min_gap * 3:
        return
    if not force and world.t - fl.last_vector_t < min_gap:
        return
    if not dl and not radio_ok(world, lead):
        if world.t - fl.last_vector_t > 90.0:
            world.log_event("comms", f"{fl.callsign} out of radio coverage", fl.id)
            fl.last_vector_t = world.t
        return
    delay = world.rng.uniform(1.0, 2.0) if dl else world.rng.uniform(3.0, 7.0)
    fl.pending.append(PendingOrder(world.t + delay, hdg, alt, throttle))
    fl.last_vector_t = world.t
    if hdg is not None:
        fl.last_vec_hdg = hdg
    if alt is not None:
        fl.last_vec_alt = alt
    if not dl and (changed or force):
        world.voice_vector(fl, hdg, alt, throttle)


def apply_pending(world: "World", fl: Flight) -> None:
    due = [p for p in fl.pending if p.t_apply <= world.t]
    if not due:
        return
    fl.pending = [p for p in fl.pending if p.t_apply > world.t]
    for p in due:
        for mid in fl.members:
            a = world.aircraft.get(mid)
            if a is None or a.state != "airborne":
                continue
            if p.hdg is not None:
                a.cmd_hdg = p.hdg
            if p.alt is not None:
                a.cmd_alt = p.alt
            if p.throttle:
                a.throttle = p.throttle if (p.throttle != "ab" or world.catalog.aircraft[a.type_id].ff_ab > 0) else "mil"


def nearest_base(world: "World", ac: Aircraft, prefer: str = "") -> tuple[str, float]:
    best, bd = prefer, math.inf
    for b in world.airbases.values():
        if b.side != world.own_side or not b.runway_ok or b.kind not in ("military", "carrier"):
            continue
        d = math.hypot(b.x - ac.x, b.y - ac.y)
        if b.id == prefer:
            d *= 0.85
        if d < bd:
            best, bd = b.id, d
    return best, (bd if best else 0.0)


def rtb_fuel(world: "World", ac: Aircraft) -> float:
    at = world.catalog.aircraft[ac.type_id]
    _, d = nearest_base(world, ac, ac.home_base)
    v = cruise_speed(at, max(ac.alt, 8000.0)) / 1000.0
    return d / max(v, 0.05) * fuel_flow(at, "cruise", 9000.0) + 0.08 * at.fuel_kg + 150.0


# ------------------------------------------------------------------ per tick

def flight_step(world: "World", fl: Flight, dt: float) -> None:
    if fl.state in ("landed", "lost"):
        return
    if fl.state == "scrambling":
        if world.t >= fl.t_airborne:
            launch(world, fl)
        return
    lead = lead_of(world, fl)
    if lead is None:
        fl.state = "lost"
        world.log_event("weapon", f"{fl.callsign}: no aircraft remaining", fl.id)
        return
    apply_pending(world, fl)
    at = world.catalog.aircraft[fl.type_id]
    # ---- fuel state
    if fl.state != "rtb":
        need = rtb_fuel(world, lead)
        if lead.fuel < need and not fl.bingo:
            fl.bingo = True
            world.stats.fuel_emergencies += 0
            world.radio(fl, "bingo fuel, RTB" if world.faction_def.id == "US" else "Fuel at minimum, returning to base.",
                        priority=1)
            begin_rtb(world, fl)
    if lead.fuel <= 0.0 and fl.state != "lost":
        world.stats.fuel_emergencies += 1
    if fl.state == "rtb":
        _rtb_step(world, fl, lead, at)
        _formation(world, fl, lead)
        return
    if fl.state == "cap":
        cx = fl.cap_x if fl.cap_x is not None else lead.x
        cy = fl.cap_y if fl.cap_y is not None else lead.y
        brg = bearing_deg(cx - lead.x, cy - lead.y)
        d = math.hypot(cx - lead.x, cy - lead.y)
        h = brg if d > 25.0 else (brg + 80.0) % 360.0
        issue_vector(world, fl, h, fl.order_alt, "cruise")
        _formation(world, fl, lead)
        return
    trk = world.tracks.get(fl.target) if fl.target else None
    contact = world.aircraft.get(fl.contact) if fl.contact else None
    if contact is not None and contact.state != "airborne":
        if contact.kind == "aircraft" and contact.state == "destroyed":
            world.radio(fl, "target destroyed" if world.faction_def.id == "US" else "Target destroyed.")
        fl.contact, contact, fl.tally = "", None, False
        fl.state = "vector"
    if fl.target and (trk is None or (trk.lost and contact is None)):
        # weapons director: if the target vanished into jamming, re-commit on the jammer track
        lx, ly = (predicted(trk, world.t) if trk is not None else (fl.pip_x or lead.x, fl.pip_y or lead.y))
        jam = min((t for t in world.tracks.values() if t.jammer and not t.lost and t.id != fl.target),
                  key=lambda t: math.hypot(t.x - lx, t.y - ly), default=None)
        if jam is not None and math.hypot(jam.x - lx, jam.y - ly) < 80.0:
            old = fl.target
            fl.target, fl.state = jam.id, "vector"
            trk = jam
            world.alert(f"{old} lost in jamming — {fl.callsign} re-committed on jammer track {jam.id}", jam.id, 0)
        else:
            if fl.state not in ("hold",):
                world.radio(fl, "lost target, request vector" if world.faction_def.id == "US"
                            else "Target lost. Request heading.")
            fl.state = "hold"
            fl.target = "" if trk is None else fl.target
    if fl.state == "hold" and trk is not None and not trk.lost:
        fl.state = "vector"
    # ---- guidance
    est = controller_estimate(world, fl) if fl.target else None
    if contact is None and est is not None and fl.state in ("vector", "airborne", "contact", "judy"):
        ex, ey, evx, evy, ealt, age, src = est
        if ealt is None:
            ealt = fl.order_alt or DEFAULT_ALT
        zoom = max(at.zoom_ceiling_m, at.ceiling_m)
        cmd_alt = min(ealt, zoom) if fl.auto else (fl.order_alt or ealt)
        if ealt > zoom + 300.0 and world.t - fl.lost_contact_t > 240.0:
            fl.lost_contact_t = world.t
            world.radio(fl, "unable — target above my ceiling" if world.faction_def.id == "US"
                        else f"Cannot reach target altitude. My ceiling {zoom / 1000:.1f} km.", priority=1)
        thr = fl.order_throttle
        vi = (max_speed(at, cmd_alt) if thr == "ab" else mil_speed(at, cmd_alt)) / 1000.0
        method = "stern" if fl.task in ("id", "shadow") else ("pursuit" if fl.task == "ram" else fl.geometry)
        sol = intercept.solve(method, ex, ey, evx, evy, lead.x, lead.y, vi)
        fl.pip_x, fl.pip_y = sol.x, sol.y
        fl.pip_t = world.t + sol.t if math.isfinite(sol.t) else None
        if fl.auto:
            issue_vector(world, fl, sol.hdg, cmd_alt, thr)
        fl.state = "vector" if fl.state in ("airborne",) else fl.state
    elif fl.state == "airborne" and fl.order_hdg is not None and fl.auto:
        issue_vector(world, fl, fl.order_hdg, fl.order_alt, fl.order_throttle)
    # ---- sensors
    _airborne_radar(world, fl, lead, at, est)
    contact = world.aircraft.get(fl.contact) if fl.contact else None
    if contact is not None:
        _terminal(world, fl, lead, at, contact, dt)
        _pilot_report(world, fl, lead, contact)
    _formation(world, fl, lead)


def _pilot_report(world: "World", fl: Flight, lead: Aircraft, c: Aircraft) -> None:
    """While the pilot holds the target, his reports (our fighter's position plus his
    range/bearing call) keep the target track alive at the direction center."""
    trk = world.tracks.get(fl.target)
    if trk is None or world.t - world.vars.get(f"prep_{fl.id}", -99.0) < 8.0:
        return
    world.vars[f"prep_{fl.id}"] = world.t
    from .state import Report
    from .tracking import update_track
    rep = Report(world.next_id("rep"), world.t, world.t, "PILOT", c.x + world.rng.gauss(0, 0.8),
                 c.y + world.rng.gauss(0, 0.8), None, 0.0, 20.0, 1, {}, False, c.id)
    update_track(world, trk, rep, manual=False)
    trk.lost = False
    if fl.tally:
        trk.alt, trk.alt_src, trk.alt_t = c.alt + world.rng.gauss(0, 150.0), "VID", world.t


def _airborne_radar(world: "World", fl: Flight, lead: Aircraft, at, est) -> None:
    if fl.contact:
        c = world.aircraft.get(fl.contact)
        if c is None or c.state != "airborne":
            fl.contact = ""
            return
        d = math.hypot(c.x - lead.x, c.y - lead.y)
        off = abs(angle_diff(bearing_deg(c.x - lead.x, c.y - lead.y), lead.hdg))
        rmax = _ai_range(world, at, lead, c) * 1.25 if at.ai_radar_km > 0 else 0.0
        vis = _visual_range(world, c)
        if (d > max(rmax, vis) * 1.1 or (off > at.ai_radar_cone + 25 and d > max(vis, 4.0))) and not fl.tally:
            key = f"lc_{fl.id}"
            world.vars[key] = world.vars.get(key, 0.0) + 1.0
            if world.vars[key] > 25.0 and fl.contact_t > 0 and world.t - fl.contact_t > 8.0:
                world.vars[key] = 0.0
                world.radio(fl, "lost contact" if world.faction_def.id == "US" else "Lost the target on radar.")
                fl.contact = ""
                fl.state = "vector"
        return
    if est is None:
        hx, hy = heading_vec(lead.hdg)      # pilot searches ahead on his own
        ex, ey = lead.x + hx * 30.0, lead.y + hy * 30.0
    else:
        ex, ey = est[0], est[1]
    best, bscore = None, math.inf
    for c in world.radar_targets():
        if c.kind not in ("aircraft", "debris") or c.flight_id == fl.id or c.state != "airborne":
            continue
        d = math.hypot(c.x - lead.x, c.y - lead.y)
        brg = bearing_deg(c.x - lead.x, c.y - lead.y)
        off = abs(angle_diff(brg, lead.hdg))
        rmax = _ai_range(world, at, lead, c) if (at.ai_radar_km > 0 and off <= at.ai_radar_cone) else 0.0
        vis = _visual_range(world, c)
        if d > max(rmax, vis) or abs(c.alt - lead.alt) > max(d * 1000.0 * 0.6, 1500.0):
            continue
        score = math.hypot(c.x - ex, c.y - ey)
        if score < bscore and score < (35.0 if est is not None else 60.0):
            best, bscore = c, score
    if best is not None and world.rng.random() < 0.45:
        fl.contact, fl.contact_t = best.id, world.t
        world.stats.locks.setdefault(best.id, world.t)
        world.vars[f"locked_{best.id}"] = 1.0
        if fl.state in ("vector", "airborne", "hold"):
            fl.state = "contact"
        d_nm = math.hypot(best.x - lead.x, best.y - lead.y) / 1.852
        if world.faction_def.id == "US":
            world.radio(fl, f"contact, {d_nm:.0f} miles")
        else:
            world.radio(fl, f"Target on radar, {d_nm * 1.852:.0f} km.")


def _ai_range(world: "World", at, lead: Aircraft, c: Aircraft) -> float:
    ct = world.catalog.aircraft.get(c.type_id)
    rcs = (ct.rcs(90.0) if ct else 5.0) * c.rcs_scale
    r = at.ai_radar_km * (max(rcs, 0.1) / 5.0) ** 0.25
    if c.alt < lead.alt - 600.0 and not at.lookdown:
        r *= 0.3 if c.alt < 2500.0 else 0.65    # no look-down: ground clutter fills the scope
    for j in world.radar_targets():
        if j.jamming and math.hypot(j.x - lead.x, j.y - lead.y) < 150.0:
            r *= 0.5
            break
    return r


def _visual_range(world: "World", c: Aircraft) -> float:
    ct = world.catalog.aircraft.get(c.type_id)
    big = (ct.rcs_beam if ct else 10.0) > 25.0
    base = 14.0 if big else 7.0
    if world.weather.night:
        base = 2.5 if big else 1.5
    return min(base, world.weather.visibility_km)


def _terminal(world: "World", fl: Flight, lead: Aircraft, at, c: Aircraft, dt: float) -> None:
    d = math.hypot(c.x - lead.x, c.y - lead.y)
    d3 = math.hypot(d, (c.alt - lead.alt) / 1000.0)
    cvx, cvy = ground_velocity(world, c)
    if fl.state == "contact" and world.t - fl.contact_t > 8.0:
        fl.state = "judy"
        world.radio(fl, "judy" if world.faction_def.id == "US" else "Target captured, attacking." if fl.weapons_free
                    else "Target captured, closing.")
    if not fl.tally and d <= _visual_range(world, c):
        fl.tally = True
        world.radio(fl, "tally ho" if world.faction_def.id == "US" else "Target in sight.")
    zoom = max(at.zoom_ceiling_m, at.ceiling_m)
    # pilot steers on his own radar/visual picture (no ground delay)
    if fl.state in ("contact", "judy", "vid", "shadow", "attack"):
        if fl.task in ("id", "shadow", "force_land") or (fl.task == "intercept" and not fl.weapons_free) or \
                world.sim_killed(c.id):
            ux, uy = (cvx, cvy)
            spd = math.hypot(ux, uy)
            if spd > 1e-6:
                ux, uy = ux / spd, uy / spd
            # trail point: inside VID distance until identified, then a comfortable shadow
            trail = (0.42 if world.weather.night else 1.1) if not fl.vid_done else 2.0
            if fl.task == "force_land":
                trail = 0.35                  # alongside, where the crew can see the signals
            tx, ty = c.x - ux * trail, c.y - uy * trail
            close = math.hypot(tx - lead.x, ty - lead.y)
            if close > 3.0:
                hdg = bearing_deg(tx - lead.x, ty - lead.y)
            else:
                # station-keeping: steer for a carrot ahead of the trail point so the
                # heading stays stable while we creep up into position
                hdg = bearing_deg(tx + ux * 2.0 - lead.x, ty + uy * 2.0 - lead.y)
            along = (tx - lead.x) * ux + (ty - lead.y) * uy
            for mid in fl.members[:1]:
                a = world.aircraft[mid]
                a.cmd_hdg = hdg
                a.cmd_alt = min(c.alt + (60.0 if not fl.vid_done else 150.0), zoom)
                a.cmd_spd = (c.spd + max(-45.0, min(along * 30.0, 120.0))) if close < 12.0 else None
        else:
            sol = intercept.lead_collision(c.x, c.y, cvx, cvy, lead.x, lead.y, max(lead.spd, 150.0) / 1000.0) \
                if fl.task != "ram" else intercept.pursuit(c.x, c.y, lead.x, lead.y)
            a = world.aircraft[fl.members[0]]
            a.cmd_hdg = sol.hdg
            a.cmd_alt = min(c.alt, zoom)
            a.cmd_spd = None
            a.throttle = "ab" if at.ff_ab else "mil"
    # ---- visual identification
    if fl.tally and not fl.vid_done and c.kind == "aircraft":
        need = 0.7 if world.weather.night else 1.9
        if d3 <= need:
            key = f"vid_{fl.id}_{c.id}"
            world.vars[key] = world.vars.get(key, 0.0) + dt
            if world.vars[key] >= (35.0 if world.weather.night else 18.0):
                _complete_vid(world, fl, c)
    elif fl.tally and not fl.vid_done and c.kind == "debris" and d3 <= 2.0:
        fl.vid_done = True
        world.radio(fl, "only debris here" if world.faction_def.id == "US" else "I see only falling debris.")
    if fl.vid_done and fl.state in ("contact", "judy", "vid"):
        fl.state = "shadow"
    # ---- "follow me": rock the wings and flash the lights alongside, at night with the landing lights
    key = f"sig_{fl.id}_{c.id}"
    if fl.task == "force_land" and d3 > 1.4 and world.vars.get(key, 0.0) > 0.0:
        world.vars[key] = max(0.0, world.vars[key] - 2.0 * dt)     # signals only work in steady formation
    if fl.task == "force_land" and fl.vid_done and c.kind == "aircraft" and d3 <= 1.4 and c.mission is not None \
            and not c.mission.signaled:
        world.vars[key] = world.vars.get(key, 0.0) + dt
        need_s = 120.0 if world.weather.night else 60.0
        if world.vars[key] >= need_s:
            world.vars[key] = -240.0          # try again in a few minutes if ignored
            rep = flight_mod.signal_to_land(world, c, fl.callsign)
            world.radio(fl, f"signals given — {rep}" if world.faction_def.id == "US" else f"Signals given: {rep}.",
                        priority=1)
    # ---- weapons
    if fl.task == "ram":
        _ram(world, fl, lead, c, d3)
    elif fl.weapons_free and c.kind == "aircraft":
        _attack(world, fl, lead, at, c, d3)


def _complete_vid(world: "World", fl: Flight, c: Aircraft) -> None:
    fl.vid_done = True
    ct = world.catalog.aircraft.get(c.type_id)
    name = c.truth_label or (ct.name if ct else "aircraft")
    text = name + (f", {c.markings}" if c.markings and not world.weather.night else "")
    if world.weather.night and world.rng.random() < 0.15:
        text = f"large aircraft, type uncertain (night)"
    trk = world.track_for_truth(c.id)
    if trk is not None:
        world.vid_reports[trk.id] = (c.side, text)
        if c.alt > 0:
            trk.alt, trk.alt_src, trk.alt_t = c.alt, "VID", world.t
    world.stats.vid.setdefault(c.id, world.t)
    if world.faction_def.id == "US":
        world.radio(fl, f"tally, one {text}", priority=1)
    else:
        world.radio(fl, f"Target identified: {text}.", priority=1)
    world.log_event("id", f"VID by {fl.callsign}: {text}", trk.id if trk else c.id)
    react_to_intercept(world, c)


def _attack(world: "World", fl: Flight, lead: Aircraft, at, c: Aircraft, d3: float) -> None:
    if world.sim_killed(c.id):
        return
    if c.side == world.own_side and fl.tally and d3 < 2.5:
        # the pilot can see it: one of ours. Break off and look again.
        if world.vars.get(f"ff_{fl.id}_{c.id}", 0.0) <= 0.0:
            world.vars[f"ff_{fl.id}_{c.id}"] = 1.0
            world.radio(fl, "that's a friendly, breaking off" if world.faction_def.id == "US" else
                        "This is our aircraft! Breaking off.", priority=1)
        fl.contact = ""
        return
    ok, why = world.can_engage_truth(c.id, fl)
    if not ok:
        return
    if world.battle.active and c.side == world.own_side and c.transponder.on and not c.transponder.failed \
            and c.transponder.system != "none":
        if world.vars.get(f"iffhold_{fl.id}_{c.id}", 0.0) <= 0.0:
            world.vars[f"iffhold_{fl.id}_{c.id}"] = 1.0
            world.radio(fl, "target squawks friendly, holding fire" if world.faction_def.id == "US" else
                        "Target answers our IFF. Holding fire.", priority=1)
        fl.contact = ""
        return
    key = f"atk_{fl.id}"
    if world.t < world.vars.get(key, -1.0):
        return
    if world.battle.active:
        # track-while-scan: two missiles on their way to this one, take the next target
        inflight = sum(1 for m in world.missiles.values()
                       if m.owner == fl.id and m.state == "flying" and m.target == c.id)
        if inflight >= 2:
            nxt = _next_target(world, fl, lead, at, c)
            if nxt is None:
                return
            fl.contact, c = nxt.id, nxt
            d3 = math.hypot(math.hypot(c.x - lead.x, c.y - lead.y), (c.alt - lead.alt) / 1000.0)
    aspect = abs(angle_diff(bearing_deg(lead.x - c.x, lead.y - c.y), c.hdg))  # 180 = shooter behind
    for wid, cnt in sorted(lead.weapons.items()):
        if cnt <= 0:
            continue
        wt = world.catalog.weapons[wid]
        if wt.kind == "asm":
            continue
        if wt.special and not (world.hq.special_release and fl.special_release):
            continue
        if not (wt.min_km <= d3 <= wt.max_km * (0.8 if wt.max_km > 30.0 else 1.0)):
            continue
        if wt.aspect == "rear" and aspect < 110.0:
            continue
        if wt.aspect == "front" and aspect > 70.0:
            continue
        if abs(c.alt - lead.alt) > 2500.0 + (wt.max_km * 70.0 if wt.max_km > 30.0 else 0.0):
            continue
        if wt.kind == "gun":
            # a gun burst is resolved at once: hit probability falls off with range
            lead.weapons[wid] = cnt - 1
            world.stats.aam_shots += 1
            fl.shots += 1
            fl.state = "attack"
            world.vars[key] = world.t + 6.0
            tvx, tvy = ground_velocity(world, c)
            slow = 2.2 if math.hypot(tvx, tvy) < 80.0 else 1.0      # a drifting balloon or a light aircraft
            p = min(0.9, wt.pk * slow * max(0.15, min(1.2, 1.25 - d3 / max(wt.max_km, 0.1))))
            hit = world.rng.random() < p
            world.radio(fl, ("guns, guns" if world.faction_def.id == "US" else "Firing cannon.") +
                        (" — hits!" if hit else ""), priority=1)
            world.log_event("weapon", f"{fl.callsign} fired a {wt.name} burst at {c.callsign or c.id}"
                            f"{' — hit' if hit else ' — missed'}", fl.id)
            if hit:
                world.destroy(c.id, f"gunfire from {fl.callsign}", fl.id)
            return
        shots = min(cnt, wt.salvo)
        lead.weapons[wid] = cnt - shots
        for i in range(shots):
            m = Missile(id=f"M{world.next_id('msl')}", type_id=wid, kind="aam", owner=fl.id, side=world.own_side,
                        x=lead.x, y=lead.y, alt=lead.alt, target=c.id, t_launch=world.t + i * 1.5)
            hx, hy = heading_vec(lead.hdg)
            spd = lead.spd + 500.0
            m.vx, m.vy = hx * spd, hy * spd
            world.missiles[m.id] = m
        fl.shots += shots
        world.stats.aam_shots += shots
        fl.state = "attack"
        world.vars[key] = world.t + (8.0 if world.battle.active and wt.max_km > 30.0 else 25.0)
        if world.battle.active:
            from .battle.core import counter, event
            counter(world, f"aam_shots_{world.own_side}", shots)
            event(world, "aam", f"{fl.callsign}: {shots}× {wt.name.split(' (')[0]} away at {c.callsign or 'a bandit'}",
                  fl.id, lead.x, lead.y, world.own_side, 1)
        world.radio(fl, f"fox, {shots} {wt.name}" if world.faction_def.id == "US" else f"Launch, {shots} missiles.",
                    priority=1)
        world.log_event("weapon", f"{fl.callsign} fired {shots}x {wt.name} at {c.callsign or c.id}", fl.id)
        return
    if not any(v > 0 for v in lead.weapons.values()) and world.t > world.vars.get(f"win_{fl.id}", -1):
        world.vars[f"win_{fl.id}"] = world.t + 1e9
        world.radio(fl, "winchester" if world.faction_def.id == "US" else "Weapons expended.")


def _next_target(world: "World", fl: Flight, lead: Aircraft, at, cur: Aircraft) -> Optional[Aircraft]:
    """Another enemy aircraft in the radar's field of view that is not yet being shot at."""
    best, bd = None, math.inf
    for c in world.radar_targets():
        if c.id == cur.id or c.kind != "aircraft" or c.side in (world.own_side, "civil", "neutral") or c.aim:
            continue
        d = math.hypot(c.x - lead.x, c.y - lead.y)
        off = abs(angle_diff(bearing_deg(c.x - lead.x, c.y - lead.y), lead.hdg))
        if off > at.ai_radar_cone or d > _ai_range(world, at, lead, c):
            continue
        if sum(1 for m in world.missiles.values() if m.owner == fl.id and m.state == "flying" and m.target == c.id) >= 2:
            continue
        dd = math.hypot(c.x - cur.x, c.y - cur.y)
        if dd < bd:
            best, bd = c, dd
    return best


def _ram(world: "World", fl: Flight, lead: Aircraft, c: Aircraft, d3: float) -> None:
    if d3 > 0.4:
        return
    key = f"ram_{fl.id}"
    if world.t < world.vars.get(key, -1.0):
        return
    world.vars[key] = world.t + 40.0
    rel = abs(lead.spd - c.spd)
    p = 0.4 if rel < 120.0 and abs(lead.alt - c.alt) < 250.0 else 0.05
    if world.rng.random() < p:
        world.destroy(c.id, f"rammed by {fl.callsign}")
        world.destroy(lead.id, "ramming", crash=True)
        world.radio(fl, "Ramming attack — contact!", priority=2)
    else:
        world.radio(fl, "Overshot — speed difference too great." if rel >= 120.0 else "Missed the ram pass.",
                    priority=1)


def begin_rtb(world: "World", fl: Flight, base: str = "") -> None:
    lead = lead_of(world, fl)
    if lead is None:
        return
    fl.state = "rtb"
    fl.rtb_base = base or nearest_base(world, lead, lead.home_base)[0] or lead.home_base
    fl.contact = ""
    fl.pending.clear()
    for mid in fl.members:
        a = world.aircraft.get(mid)
        if a is not None:
            a.cmd_spd = None
            a.throttle = "cruise"


def _rtb_step(world: "World", fl: Flight, lead: Aircraft, at) -> None:
    base = world.airbases.get(fl.rtb_base) or world.airbases[fl.base_id]
    d = math.hypot(base.x - lead.x, base.y - lead.y)
    for mid in fl.members:
        a = world.aircraft.get(mid)
        if a is None or a.state != "airborne":
            continue
        a.cmd_hdg = bearing_deg(base.x - a.x, base.y - a.y)
        a.cmd_alt = base.elev + 1500.0 if d < 110.0 else min(at.cruise_alt_m, 11000.0)
        a.throttle = "cruise"
    if d < 7.0:
        sq = world.squadrons[fl.squadron_id]
        landed = 0
        for mid in fl.members:
            a = world.aircraft.get(mid)
            if a is not None and a.state == "airborne":
                a.state = "landed"
                landed += 1
                sq.recovering.append(world.t + sq.turnaround_min * 60.0)
        sq.airborne = max(0, sq.airborne - landed)
        sq.pilots += landed
        fl.state = "landed"
        world.radio(fl, f"on the ground at {base.name}" if world.faction_def.id == "US" else f"Landed at {base.name}.")
        world.log_event("weapon", f"{fl.callsign} landed at {base.name}", fl.id)


def _formation(world: "World", fl: Flight, lead: Aircraft) -> None:
    hx, hy = heading_vec(lead.hdg)
    for i, mid in enumerate(fl.members):
        a = world.aircraft.get(mid)
        if a is None or a is lead or a.state != "airborne":
            continue
        off = 1.2 * i
        a.x = lead.x - hx * off + hy * off * 0.8
        a.y = lead.y - hy * off - hx * off * 0.8
        a.alt, a.hdg, a.spd, a.vs = lead.alt, lead.hdg, lead.spd, lead.vs
        a.cmd_hdg, a.cmd_alt, a.cmd_spd, a.throttle = lead.cmd_hdg, lead.cmd_alt, lead.cmd_spd, lead.throttle
        a.fuel = min(a.fuel, lead.fuel + 150.0)


def recover_squadrons(world: "World") -> None:
    for sq in world.squadrons.values():
        done = [r for r in sq.recovering if r <= world.t]
        if done:
            sq.recovering = [r for r in sq.recovering if r > world.t]
            key = max(sq.ready, key=lambda k: float(k)) if sq.ready else "60"
            sq.ready[key] = sq.ready.get(key, 0) + len(done)
