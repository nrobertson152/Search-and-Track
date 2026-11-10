"""Surface-to-air missile fire units and missile flight (SAM, AAM, BOMARC).

Fire control locks the *strongest return inside its acquisition gate* around
the designated position -- which is not necessarily the aircraft the
commander meant. Missiles are simulated entities guided on whatever the fire
control radar is tracking, so fratricide and wasted salvos on debris emerge
from geometry, IFF and timing rather than scripts."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .geo import bearing_deg, radar_horizon_km
from .intercept import collision_time
from .state import Missile, SamSite
from .tracking import predicted

if TYPE_CHECKING:
    from .world import World


def sam_step(world: "World", site: SamSite, dt: float) -> None:
    if site.side != world.own_side:
        return                       # the other side's fire channels are run by the battle AI
    st = world.catalog.sams[site.type_id]
    t = world.t
    if site.reloading:
        done = [r for r in site.reloading if r <= t]
        if done:
            site.reloading = [r for r in site.reloading if r > t]
            site.ready_missiles += len(done)
    if site.status != "ok" or t < site.t_ready:
        return
    trk = world.tracks.get(site.assigned) if site.assigned else None
    if site.state == "idle":
        if trk is not None:
            site.state, site.t_state = "search", t
            _designate(world, site, trk)
        return
    if site.state == "search":
        if trk is None:
            site.state = "idle"
            return
        _designate(world, site, trk)
        if t - site.t_state < st.acq_time_s:
            return
        tgt = _acquire(world, site, st, math.hypot(trk.vx, trk.vy))
        if tgt is None:
            if t - site.t_state > st.acq_time_s + 90.0:
                world.unit_report(site, "TARGET NOT FOUND IN ACQUISITION GATE", priority=1)
                site.t_state = t
            return
        site.lock = tgt.id
        site.state, site.t_state = "locked", t
        world.unit_report(site, f"TARGET ACQUIRED — TRACKING, range {math.hypot(tgt.x - site.x, tgt.y - site.y):.0f} km")
        return
    tgt = world.aircraft.get(site.lock)
    if site.state in ("locked", "engaging") and (tgt is None or tgt.state != "airborne"
                                                   or math.hypot(tgt.x - site.x, tgt.y - site.y) > st.fc_range_km
                                                   or not _los(site, tgt)):
        site.state, site.t_state = ("assess" if site.state == "engaging" else "search"), t
        if site.state == "search":
            world.unit_report(site, "LOST LOCK", priority=0)
        return
    if site.state == "locked":
        tr = tgt.transponder
        own_sif = tr.system == "sif" and tr.codes.get("1", "") in world.hq.policy.get("mode1_valid", [])
        if st.iff and tr.on and not tr.failed and (tr.system == "kremniy" or own_sif):
            if own_sif or tr.codes.get("period", "") == world.hq.policy.get("iff_period", ""):
                if world.t - site.t_state < 2.0:
                    world.unit_report(site, "LOCKED TARGET ANSWERS IFF — OWN AIRCRAFT. HOLDING.", priority=1)
                site.lock, site.state, site.t_state = "", "search", t
                return
        if site.hold:
            return
        ok, why = world.can_engage_site(site)
        if not ok:
            key = f"sam_wait_{site.id}"
            if world.vars.get(key, 0.0) < t:
                world.vars[key] = t + 120.0
                world.unit_report(site, f"READY TO FIRE — {why}", priority=1)
            return
        if site.fault_t > t:
            if world.vars.get(f"fault_{site.id}", 0.0) < t:
                world.vars[f"fault_{site.id}"] = t + 60.0
                world.unit_report(site, "FIRE CONTROL MALFUNCTION — LAUNCH INHIBITED", priority=1)
            return
        if _in_envelope(world, site, st, tgt):
            if site.ready_missiles <= 0:
                world.unit_report(site, "NO MISSILES READY")
                return
            site.state, site.t_state = "engaging", t
            site.salvo_left = min(site.salvo_size, site.ready_missiles)
            site.t_next_launch = t
        return
    if site.state == "engaging":
        if site.salvo_left > 0 and t >= site.t_next_launch and site.ready_missiles > 0:
            _launch(world, site, st, tgt)
            site.salvo_left -= 1
            site.t_next_launch = t + st.salvo_interval_s
        if site.salvo_left <= 0 or site.ready_missiles <= 0:
            site.state, site.t_state = "assess", t
        return
    if site.state == "assess":
        flying = any(m.owner == site.id and m.state == "flying" for m in world.missiles.values())
        if flying:
            return
        tgt = world.aircraft.get(site.lock)
        if tgt is not None and tgt.state == "airborne" and tgt.kind == "debris" and tgt.rcs_scale > 0.12:
            site.last_result = "TARGET STILL ON SCOPE"
            world.unit_report(site, "SALVO COMPLETE — TARGET STILL TRACKED (fragmenting?)", priority=1)
            site.state, site.t_state = "locked", t
            if not site.auto:
                site.hold = True
        elif tgt is not None and tgt.state == "airborne":
            site.last_result = "MISS"
            world.unit_report(site, "SALVO COMPLETE — TARGET CONTINUES", priority=1)
            site.state, site.t_state = "locked", t
            if not site.auto:
                site.hold = True
        else:
            site.last_result = "TARGET LOST FROM SCOPE"
            world.unit_report(site, "TARGET DISAPPEARED FROM SCOPE — POSSIBLE KILL", priority=1)
            site.state, site.lock, site.assigned = "idle", "", ""


def _designate(world: "World", site: SamSite, trk) -> None:
    px, py = predicted(trk, world.t)
    site.des_x, site.des_y = px, py
    site.des_alt = trk.alt if trk.alt is not None else -1.0


def _los(site: SamSite, tgt) -> bool:
    return math.hypot(tgt.x - site.x, tgt.y - site.y) <= radar_horizon_km(site.elev + 15.0, tgt.alt)


def _acquire(world: "World", site: SamSite, st, spd_kms: float = 0.0):
    best, bscore = None, 0.0
    gate = 9.0 + 12.0 * spd_kms              # fast targets: the track lags, the gate opens
    fast = spd_kms > 0.6
    for tgt in world.radar_targets():
        if tgt.kind == "ghost":
            continue
        d_site = math.hypot(tgt.x - site.x, tgt.y - site.y)
        if d_site > st.acq_range_km or not _los(site, tgt):
            continue
        d = math.hypot(tgt.x - site.des_x, tgt.y - site.des_y)
        if d > gate:
            continue
        if site.des_alt >= 0 and abs(tgt.alt - site.des_alt) > 4000.0 and not fast:
            continue
        at = world.catalog.aircraft.get(tgt.type_id)
        rcs = (at.rcs(90.0) if at else 3.0) * tgt.rcs_scale
        score = rcs / max(d_site, 1.0) ** 4 * 1e8 / (1.0 + d)
        if score > bscore and world.rng.random() < 0.8:
            best, bscore = tgt, score
    return best


def _in_envelope(world: "World", site: SamSite, st, tgt) -> bool:
    from .flight import ground_velocity
    vx, vy = ground_velocity(world, tgt)
    vm = st.missile_mps * 0.8 / 1000.0
    t_hit = collision_time(tgt.x, tgt.y, vx, vy, site.x, site.y, vm)
    if t_hit is None or t_hit > st.max_flight_s:
        return False
    ix, iy = tgt.x + vx * t_hit, tgt.y + vy * t_hit
    r = math.hypot(ix - site.x, iy - site.y)
    return st.range_min_km <= r <= st.range_max_km and st.alt_min_m <= tgt.alt <= st.alt_max_m


def _launch(world: "World", site: SamSite, st, tgt) -> None:
    m = Missile(id=f"M{world.next_id('msl')}", type_id=site.type_id, kind="bomarc" if st.homing_km > 0 else "sam",
                owner=site.id, side=site.side, x=site.x, y=site.y, alt=site.elev + 10.0,
                target=tgt.id if st.homing_km <= 0 else "", track=site.assigned, t_launch=world.t)
    m.vz = 50.0
    world.missiles[m.id] = m
    site.ready_missiles -= 1
    site.fired += 1
    world.stats.missiles += 1
    if site.reloads > 0:
        site.reloads -= 1
        site.reloading.append(world.t + st.reload_min * 60.0)
    world.unit_report(site, f"MISSILE AWAY ({site.fired} fired)", priority=1)
    world.log_event("weapon", f"{site.name} launched {st.name} at {site.assigned}", site.id)


def bomarc_launch(world: "World", site: SamSite, track_id: str) -> tuple[bool, str]:
    st = world.catalog.sams[site.type_id]
    if site.ready_missiles <= 0:
        return False, "No BOMARC ready"
    trk = world.tracks.get(track_id)
    if trk is None:
        return False, "No such track"
    m = Missile(id=f"M{world.next_id('msl')}", type_id=site.type_id, kind="bomarc", owner=site.id, side=site.side,
                x=site.x, y=site.y, alt=site.elev + 10.0, track=track_id, t_launch=world.t, vz=150.0)
    world.missiles[m.id] = m
    site.ready_missiles -= 1
    site.fired += 1
    world.stats.missiles += 1
    world.log_event("weapon", f"BOMARC launched from {site.name} at {track_id}", site.id)
    return True, f"{st.name} away from {site.name} — SAGE guidance on {track_id}"


# ------------------------------------------------------------------ missile flight

def missile_step(world: "World", m: Missile, dt: float) -> None:
    if m.state != "flying" or world.t < m.t_launch:
        return
    age = world.t - m.t_launch
    if m.kind == "aam":
        wt = world.catalog.weapons[m.type_id]
        speed = wt.speed_mps or (750.0 if wt.kind != "rocket" and wt.kind != "nuclear_rocket" else 650.0)
        max_t = wt.max_km / (speed / 1000.0) * 1.3 + 3.0
        lethal, pk, turn = wt.lethal_m, wt.pk, 22.0
    else:
        st = world.catalog.sams[m.type_id]
        speed = st.missile_mps * min(1.0, 0.25 + age / max(st.boost_s, 1.0))
        max_t = st.max_flight_s
        lethal, pk, turn = st.lethal_m, st.pk, 18.0 if m.kind == "sam" else 6.0
    if age > max_t:
        m.state, m.result = "done", "self-destruct"
        return
    from .geo import isa_density_ratio
    turn *= max(0.3, isa_density_ratio(m.alt) ** 0.5 * 1.6)      # thin air: control surfaces lose authority
    tgt = world.aircraft.get(m.target) if m.target else None
    if m.kind == "bomarc" and not m.homing:
        trk = world.tracks.get(m.track)
        st = world.catalog.sams[m.type_id]
        if trk is not None:
            px, py = predicted(trk, world.t)
            aim = (px, py, st.cruise_alt_m if math.hypot(px - m.x, py - m.y) > 40 else (trk.alt or st.cruise_alt_m))
        else:
            aim = (m.x + m.vx / 1000.0 * 10, m.y + m.vy / 1000.0 * 10, m.alt)
        for c in world.radar_targets():
            if c.kind == "aircraft" and c.side != m.side and math.hypot(c.x - m.x, c.y - m.y) < st.homing_km:
                m.target, m.homing = c.id, True
                tgt = c
                break
            if c.kind == "aircraft" and math.hypot(c.x - m.x, c.y - m.y) < st.homing_km * 0.5:
                m.target, m.homing = c.id, True   # seeker does not know friend from foe
                tgt = c
                break
        if not m.homing:
            _steer(m, aim[0], aim[1], aim[2], speed, turn, dt)
            return
    if tgt is None or tgt.state != "airborne":
        _steer(m, m.x + m.vx / 1000.0 * 5, m.y + m.vy / 1000.0 * 5, m.alt, speed, turn, dt)
        return
    from .flight import ground_velocity
    vx, vy = ground_velocity(world, tgt)
    t_go = collision_time(tgt.x, tgt.y, vx, vy, m.x, m.y, speed / 1000.0) or \
        math.hypot(tgt.x - m.x, tgt.y - m.y) / max(speed / 1000.0, 0.1)
    ax, ay = tgt.x + vx * t_go, tgt.y + vy * t_go
    p0 = (m.x, m.y, m.alt / 1000.0)
    q0 = (tgt.x, tgt.y, tgt.alt / 1000.0)
    _steer(m, ax, ay, tgt.alt + tgt.vs * t_go, speed, turn, dt)
    p1 = (m.x, m.y, m.alt / 1000.0)
    q1 = (tgt.x + vx * dt, tgt.y + vy * dt, (tgt.alt + tgt.vs * dt) / 1000.0)
    dmin = _closest(p0, p1, q0, q1) * 1000.0
    closing = math.sqrt((m.vx - vx * 1000.0) ** 2 + (m.vy - vy * 1000.0) ** 2 + (m.vz - tgt.vs) ** 2)
    lethal *= max(1.0, closing / 600.0)      # the proximity fuze's window grows with the closing speed
    if dmin < lethal * 3.0:
        p = pk * max(0.0, 1.0 - (dmin / (lethal * 3.0)) ** 2) * (1.3 if m.kind == "sam" else 1.0)
        if world.battle.active:
            from .battle.combat import evade_factor
            p *= evade_factor(world, tgt, m)
        if world.rng.random() < min(0.95, p):
            m.state = "done"
            if tgt.kind == "debris":
                m.result = "detonated on debris"
                world.log_event("weapon", f"Missile {m.id} detonated on debris", m.owner)
            else:
                m.result = "hit"
                if world.battle.active:
                    from .battle.combat import hit
                    hit(world, tgt, f"{m.type_id} from {m.owner}", m.owner)
                else:
                    world.destroy(tgt.id, f"{m.type_id} from {m.owner}", shooter=m.owner)
            return
    if age > 3.0 and _opening(p1, q1, m, vx, vy, tgt):
        m.state, m.result = "done", f"miss ({dmin:.0f} m)"


def _steer(m: Missile, ax: float, ay: float, aalt: float, speed: float, turn_dps: float, dt: float) -> None:
    dx, dy, dz = (ax - m.x) * 1000.0, (ay - m.y) * 1000.0, aalt - m.alt
    n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    want = (dx / n, dy / n, dz / n)
    cv = math.sqrt(m.vx ** 2 + m.vy ** 2 + m.vz ** 2) or 1.0
    cur = (m.vx / cv, m.vy / cv, m.vz / cv) if cv > 1.0 else want
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(cur, want))))
    ang = math.acos(dot)
    lim = math.radians(turn_dps * dt)
    if ang > lim and ang > 1e-6:
        f = lim / ang
        v = tuple(c + (w - c) * f for c, w in zip(cur, want))
        nv = math.sqrt(sum(c * c for c in v)) or 1.0
        cur = tuple(c / nv for c in v)
    else:
        cur = want
    m.vx, m.vy, m.vz = cur[0] * speed, cur[1] * speed, cur[2] * speed
    m.x += m.vx * dt / 1000.0
    m.y += m.vy * dt / 1000.0
    m.alt = max(0.0, m.alt + m.vz * dt)


def _closest(p0, p1, q0, q1) -> float:
    d0 = [q - p for p, q in zip(p0, q0)]
    dv = [(q1[i] - q0[i]) - (p1[i] - p0[i]) for i in range(3)]
    vv = sum(v * v for v in dv)
    s = 0.0 if vv < 1e-12 else max(0.0, min(1.0, -sum(a * b for a, b in zip(d0, dv)) / vv))
    return math.sqrt(sum((d0[i] + dv[i] * s) ** 2 for i in range(3)))


def _opening(p, q, m: Missile, vx: float, vy: float, tgt) -> bool:
    rx, ry, rz = (q[0] - p[0]) * 1000.0, (q[1] - p[1]) * 1000.0, q[2] * 1000.0 - p[2] * 1000.0
    rvx, rvy, rvz = vx * 1000.0 - m.vx, vy * 1000.0 - m.vy, tgt.vs - m.vz
    return rx * rvx + ry * rvy + rz * rvz > 0 and math.sqrt(rx * rx + ry * ry + rz * rz) > 1500.0


def engagement_zone(world: "World", site: SamSite) -> tuple[float, float]:
    st = world.catalog.sams[site.type_id]
    return st.range_min_km, st.range_max_km


def site_bearing(site: SamSite, x: float, y: float) -> float:
    return bearing_deg(x - site.x, y - site.y)
