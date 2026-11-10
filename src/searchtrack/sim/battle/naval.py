"""Ships at sea: steaming in formation, evasive turns, chaff and close-in guns, damage and
sinking; anti-ship missiles from launch to impact; the enemy's shipborne missile fire.

Anti-ship missiles are aircraft entities (role "missile"): radars see them, trackers track
them, SAMs and fighters can shoot them down. Their seeker locks the strongest return it finds
near the aim point -- usually the biggest ship, not necessarily the one the shooter meant.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..geo import angle_diff, bearing_deg, heading_vec
from ..state import Aircraft, Missile, RadarSite, SamSite, Ship, Transponder
from .core import KN, counter, event, spec_xy

GROUND_PROFILES = ("terrain", "arm", "glide")          # land.py flies these

if TYPE_CHECKING:
    from ..world import World


# ------------------------------------------------------------------ ships

def add_ship(w: "World", spec: dict) -> Ship:
    st = w.catalog.ships[spec["type"]]
    x, y = spec_xy(w, spec) if ("x" in spec or "lat" in spec) else (0.0, 0.0)
    side = spec.get("side", "blue")
    station = spec.get("station", [0.0, 0.0])
    sh = Ship(id=spec["id"], name=spec.get("name", spec["id"]), type_id=st.id, side=side, x=x, y=y,
              hdg=float(spec.get("course", 0.0)), speed_kn=float(spec.get("speed_kn", st.cruise_kn)),
              group=spec.get("group", ""), guide=bool(spec.get("guide", False)),
              station_brg=float(station[0]), station_km=float(station[1]), hp=st.hp, max_hp=st.hp,
              chaff=st.chaff, name_ru=spec.get("name_ru", ""))
    sh.spd = sh.speed_kn * KN
    sh.route = [list(spec_xy(w, p)) for p in spec.get("route", [])]
    if sh.station_km > 0 and not sh.guide:
        guide = next((o for o in w.ships.values() if o.group == sh.group and o.guide), None)
        if guide is not None:
            hx, hy = heading_vec(guide.hdg + sh.station_brg)
            sh.x, sh.y, sh.hdg = guide.x + hx * sh.station_km, guide.y + hy * sh.station_km, guide.hdg
    w.ships[sh.id] = sh
    if side == w.own_side:
        for i, r in enumerate(st.radars):
            rt = w.catalog.radars[r["type"]]
            rid = f"{sh.id}-R{i + 1}"
            w.radars[rid] = RadarSite(id=rid, name=f"{sh.name} {rt.id}", type_id=rt.id, x=sh.x, y=sh.y, elev=0.0,
                                      mast_m=float(r.get("mast_m", 30.0)), unit=sh.name, status="ok",
                                      az=w.rng.uniform(0, 360), rpm=rt.rpm, mti=rt.mti, link=spec.get("link", ""),
                                      carrier=sh.id, bias_r=0.0, bias_az=0.0)
    for i, m in enumerate(st.sams):
        sst = w.catalog.sams[m["type"]]
        sid = f"{sh.id}-M{i + 1}"
        w.sams[sid] = SamSite(id=sid, name=f"{sh.name} · {sst.id}", type_id=sst.id, x=sh.x, y=sh.y, elev=25.0,
                              side=side, unit=sh.name, readiness_min=0.0, t_ready=0.0,
                              ready_missiles=int(m.get("missiles", sst.launchers)), reloads=0, salvo_size=sst.salvo,
                              auto=True, carrier=sh.id)
    return sh


def carry(w: "World") -> None:
    """Fire channels and flight decks sail with their ships."""
    for s in w.sams.values():
        if s.carrier:
            sh = w.ships.get(s.carrier)
            if sh is None:
                continue
            s.x, s.y = sh.x, sh.y
            if sh.state in ("sunk", "crippled") and s.status == "ok":
                s.status = "down"
                s.state, s.lock, s.assigned = "idle", "", ""
    for b in w.airbases.values():
        if b.carrier:
            sh = w.ships.get(b.carrier)
            if sh is None:
                continue
            b.x, b.y = sh.x, sh.y
            deck = sh.state in ("afloat", "damaged") and sh.hp > sh.max_hp * 0.45
            if b.runway_ok and not deck:
                event(w, "deck", f"{sh.name}: flight deck out of action — aircraft divert ashore", sh.id, sh.x, sh.y,
                      sh.side, 2)
            b.runway_ok = deck


def guide_of(w: "World", sh: Ship):
    if not sh.group or sh.guide:
        return None
    g = next((o for o in w.ships.values() if o.group == sh.group and o.guide and o.state != "sunk"), None)
    if g is None:             # the guide is gone: the biggest survivor takes over
        alive = [o for o in w.ships.values() if o.group == sh.group and o.state != "sunk"]
        if alive:
            g = max(alive, key=lambda o: w.catalog.ships[o.type_id].hp)
            g.guide = True
            if g is not sh and not g.route:
                g.route = list(next((o.route for o in w.ships.values() if o.group == sh.group and o.route), []))
            return None if g is sh else g
    return g


def ship_step(w: "World", sh: Ship, dt: float) -> None:
    if sh.state == "sunk":
        return
    st = w.catalog.ships[sh.type_id]
    vmax = st.max_kn * KN * {"afloat": 1.0, "damaged": 0.55, "crippled": 0.0}.get(sh.state, 1.0)
    want_hdg, want_spd = sh.hdg, sh.speed_kn * KN
    guide = guide_of(w, sh)
    if guide is None:
        if sh.route:
            tx, ty = sh.route[sh.wp % len(sh.route)]
            if math.hypot(tx - sh.x, ty - sh.y) < 4.0:
                sh.wp += 1
                tx, ty = sh.route[sh.wp % len(sh.route)]
            want_hdg = bearing_deg(tx - sh.x, ty - sh.y)
    else:
        hx, hy = heading_vec(guide.hdg + sh.station_brg)
        px, py = guide.x + hx * sh.station_km, guide.y + hy * sh.station_km
        d = math.hypot(px - sh.x, py - sh.y)
        if d > 1.2:
            want_hdg = bearing_deg(px - sh.x, py - sh.y)
            want_spd = guide.spd + min(d, 12.0) * 1.0
        else:
            want_hdg, want_spd = guide.hdg, guide.spd
    if sh.evading_until > w.t and sh.state != "crippled":
        want_spd = vmax
        want_hdg = (want_hdg + (40.0 if int(sh.evading_until) % 2 else -40.0)) % 360.0
    want_spd = min(want_spd, vmax)
    turn = (0.8 if st.kind == "carrier" else 1.4) * dt
    sh.hdg = (sh.hdg + max(-turn, min(turn, angle_diff(want_hdg, sh.hdg)))) % 360.0
    acc = 0.12 * dt
    sh.spd = max(0.0, sh.spd + max(-acc * 2, min(acc, want_spd - sh.spd)))
    hx, hy = heading_vec(sh.hdg)
    sh.x += hx * sh.spd * dt / 1000.0
    sh.y += hy * sh.spd * dt / 1000.0


def damage_ship(w: "World", sh: Ship, dmg: float, cause: str, by: str = "") -> None:
    if sh.state == "sunk":
        return
    old = sh.state
    sh.hp -= dmg
    sh.hits += 1
    frac = sh.hp / max(sh.max_hp, 1.0)
    sh.state = "sunk" if sh.hp <= 0 else "crippled" if frac < 0.25 else "damaged" if frac < 0.65 else "afloat"
    counter(w, f"ship_hits_{sh.side}")
    how = {"afloat": "damage contained", "damaged": "fires burning, speed reduced",
           "crippled": "dead in the water, burning", "sunk": "SINKING"}[sh.state]
    event(w, "ship_hit", f"{sh.name} HIT by {cause} — {how}", sh.id, sh.x, sh.y, sh.side, 3)
    if sh.state == "sunk" and old != "sunk":
        counter(w, f"ships_sunk_{sh.side}")
        sh.spd = 0.0
        event(w, "sunk", f"{sh.name} HAS SUNK", sh.id, sh.x, sh.y, sh.side, 3)
        for sq in w.squadrons.values():           # aircraft still on the deck go down with her
            if sq.base_id == sh.id and sum(sq.ready.values()):
                lost = sum(sq.ready.values())
                sq.ready = {k: 0 for k in sq.ready}
                sq.lost += lost
                counter(w, f"aircraft_lost_{sh.side}", lost)
        for site in w.radars.values():
            if site.carrier == sh.id:
                site.status, site.fail_t = "down", 1e12
    elif sh.state == "crippled" and old != "crippled":
        for site in w.radars.values():
            if site.carrier == sh.id:
                site.status, site.fail_t = "down", 1e12


# ------------------------------------------------------------------ anti-ship missiles

def launch_asm(w: "World", shooter: Aircraft, wid: str, aim: tuple[float, float], owner: str) -> Aircraft:
    wt = w.catalog.weapons[wid]
    mt = w.catalog.aircraft[wt.missile]
    n = w.next_id("asm")
    hdg = bearing_deg(aim[0] - shooter.x, aim[1] - shooter.y)
    v = mt.cruise_kmh / 3600.0
    m = Aircraft(id=f"V{n}", type_id=mt.id, callsign=f"{wt.id} {n}", side=shooter.side, x=shooter.x, y=shooter.y,
                 alt=max(shooter.alt - 150.0, 60.0), hdg=hdg, spd=max(shooter.spd, 220.0), fuel=mt.fuel_kg,
                 throttle="mil", transponder=Transponder("none", False), truth_label=mt.name,
                 nationality=shooter.nationality, aim=[aim[0], aim[1]], launcher=owner,
                 t_max=w.t + wt.max_km * 1.5 / max(v, 0.05) + 60.0, t_spawn=w.t)
    m.cmd_hdg, m.cmd_alt = hdg, mt.cruise_alt_m
    w.aircraft[m.id] = m
    counter(w, f"asm_{shooter.side}")
    return m


def ship_salvo(w: "World", a: dict) -> int:
    """A ship fires its anti-ship missiles at where its side believes the target group is.
    A ship that is crippled or sunk fires nothing; nor does one that never got a fix."""
    from types import SimpleNamespace
    sh = w.ships.get(a["ship"])
    if sh is None or sh.state in ("sunk", "crippled") or w.battle.counters.get(f"salvo_{sh.id}", 0) > 0:
        return 0                                     # out of action, or already fired her one salvo
    pic = w.battle.surface.get(sh.side, {})
    tgt = a.get("target", "")
    fresh = float(a.get("fix_age_s", 240.0))
    best = None
    for sid, c in pic.items():
        o = w.ships.get(sid)
        if o is None or o.state == "sunk" or (tgt and o.group != tgt and o.id != tgt) or w.t - c.t > fresh:
            continue
        st = w.catalog.ships[o.type_id]
        if best is None or st.rcs_m2 > best[0]:
            best = (st.rcs_m2, c)
    if best is None:
        if a.get("need_fix", True):
            if not w.vars.get(f"salvo_hold_{sh.id}"):
                w.vars[f"salvo_hold_{sh.id}"] = 1.0
                event(w, "salvo_hold", f"{sh.name} holds her missiles: no fresh fix on the target", sh.id, sh.x,
                      sh.y, sh.side, 1 if sh.side == w.own_side else -1)
            return 0
        aim = tuple(w.battle.red_plan.get("brief", [sh.x, sh.y]))
    else:
        c = best[1]
        age = w.t - c.t
        aim = (c.x + c.vx * age, c.y + c.vy * age)
    wt = w.catalog.weapons[a["weapon"]]
    n = int(a.get("n", 8))
    shooter = SimpleNamespace(x=sh.x, y=sh.y, alt=200.0, spd=250.0, nationality="", side=sh.side)
    for k in range(n):
        j = w.rng.gauss(0.0, 3.0)
        launch_asm(w, shooter, wt.id, (aim[0] + j, aim[1] - j), sh.id)
    counter(w, f"salvo_{sh.id}")
    lvl = 3 if sh.side != w.own_side else 2
    txt = f"{sh.name} fires {n} {wt.name.split(' (')[0]}" if sh.side == w.own_side else \
        f"ESM: missile launches from the {sh.name} group — {n} {wt.name.split(' (')[0]} inbound"
    event(w, "ship_salvo", txt, sh.id, sh.x, sh.y, w.own_side if sh.side != w.own_side else sh.side, lvl)
    return n


def _dive_km(mt) -> float:
    """Distance a high-flying missile covers while it dives onto the target."""
    t_dive = mt.cruise_alt_m / max(mt.climb_mps * 0.6, 50.0)
    return t_dive * mt.cruise_kmh / 3600.0 * 1.05


def asm_guidance(w: "World", dt: float) -> None:
    cat = w.catalog
    for m in list(w.aircraft.values()):
        if m.state != "airborne" or not m.aim:
            continue
        mt = cat.aircraft[m.type_id]
        if mt.profile in GROUND_PROFILES:
            continue
        if w.t > m.t_max > 0:
            m.state = "gone"
            event(w, "asm_miss", f"{m.callsign}: fuel exhausted, fell into the sea", m.id, m.x, m.y, m.side, 0)
            continue
        tgt = w.ships.get(m.homing) if m.homing else None
        if tgt is not None and tgt.state == "sunk":
            m.homing, tgt = "", None
        if tgt is None:
            ax, ay = m.aim
            if math.hypot(ax - m.x, ay - m.y) < mt.seeker_km * 1.4:
                best, bs = None, 0.0
                taken: dict[str, int] = {}
                if mt.seeker_share:
                    for o in w.aircraft.values():
                        if o.state == "airborne" and o.homing and o.launcher == m.launcher:
                            taken[o.homing] = taken.get(o.homing, 0) + 1
                for sh in w.ships.values():
                    if sh.side == m.side or sh.state == "sunk":
                        continue
                    d = math.hypot(sh.x - m.x, sh.y - m.y)
                    off = abs(angle_diff(bearing_deg(sh.x - m.x, sh.y - m.y), m.hdg))
                    if d > mt.seeker_km or off > 50.0:
                        continue
                    da = math.hypot(sh.x - ax, sh.y - ay)            # the seeker searches around its aim point
                    score = cat.ships[sh.type_id].rcs_m2 * (0.3 if w.t - sh.t_chaff < 50.0 else 1.0) / \
                        (1.0 + (da / 25.0) ** 2) / (1.0 + taken.get(sh.id, 0) / 2.0)
                    if score > bs:
                        best, bs = sh, score
                if best is not None:
                    m.homing, tgt = best.id, best
            tx, ty = (tgt.x, tgt.y) if tgt is not None else (ax, ay)
        else:
            tx, ty = tgt.x, tgt.y
        d = math.hypot(tx - m.x, ty - m.y)
        m.cmd_hdg = bearing_deg(tx - m.x, ty - m.y)
        if mt.profile == "sea_skim":
            m.cmd_alt = 15.0 if d > 4.0 or tgt is None else 6.0
        else:
            dk = _dive_km(mt)
            m.cmd_alt = mt.cruise_alt_m if d > dk else max(0.0, mt.cruise_alt_m * (d / dk) ** 1.3)
        m.cmd_spd = None
        m.throttle = "mil"


def asm_impacts(w: "World") -> None:
    for m in list(w.aircraft.values()):
        if m.state != "airborne" or not m.aim:
            continue
        if w.catalog.aircraft[m.type_id].profile in GROUND_PROFILES:
            continue
        sh = w.ships.get(m.homing) if m.homing else None
        step_km = m.spd / 1000.0 * 1.2
        if sh is not None:
            d = math.hypot(sh.x - m.x, sh.y - m.y)
            if d < max(0.5, step_km) and m.alt < 1200.0:
                _terminal(w, m, sh)
        elif math.hypot(m.aim[0] - m.x, m.aim[1] - m.y) < step_km and m.alt < 300.0:
            m.state = "gone"
            event(w, "asm_miss", f"{m.callsign} found no target and went into the sea", m.id, m.x, m.y, m.side, 0)


def _terminal(w: "World", m: Aircraft, sh: Ship) -> None:
    cat = w.catalog
    mt = cat.aircraft[m.type_id]
    st = cat.ships[sh.type_id]
    fast = m.spd > 600.0
    m.state = "gone"
    if sh.state not in ("crippled", "sunk"):
        for k in range(min(st.ciws, 2)):
            if w.rng.random() < (0.2 if fast else 0.42):
                counter(w, f"ciws_kills_{sh.side}")
                event(w, "ciws", f"{sh.name}: close-in guns destroy an incoming {mt.id} at the last moment", sh.id,
                      sh.x, sh.y, sh.side, 2)
                return
    if w.t - sh.t_chaff < 60.0 and w.rng.random() < (0.12 if fast else 0.28):
        event(w, "chaff", f"{m.callsign} decoyed by chaff from {sh.name}", sh.id, sh.x, sh.y, sh.side, 1)
        return
    dmg = mt.warhead_kg * 0.09 * w.rng.uniform(0.75, 1.25)
    counter(w, f"asm_hits_{m.side}")
    damage_ship(w, sh, dmg, mt.name.split(" anti")[0], m.launcher)


def ship_defense(w: "World") -> None:
    """Chaff and evasive turns when missiles come in."""
    if w.tick % 3:
        return
    threats: dict[str, float] = {}
    for m in w.aircraft.values():
        if m.state != "airborne" or not m.aim or w.catalog.aircraft[m.type_id].profile in ("terrain", "glide"):
            continue
        for sh in w.ships.values():
            if sh.side == m.side or sh.state == "sunk":
                continue
            d = math.hypot(sh.x - m.x, sh.y - m.y)
            if m.homing == sh.id or d < 60.0:
                threats[sh.id] = min(threats.get(sh.id, 1e9), d)
    for sid, d in threats.items():
        sh = w.ships[sid]
        if d < 90.0 and sh.evading_until < w.t:
            sh.evading_until = w.t + 120.0
        if d < 35.0 and sh.chaff > 0 and w.t - sh.t_chaff > 40.0:
            sh.chaff -= 1
            sh.t_chaff = w.t
            event(w, "chaff", f"{sh.name} fires chaff", sh.id, sh.x, sh.y, sh.side, 0)


# ------------------------------------------------------------------ the enemy's shipborne SAMs

def red_sam_step(w: "World", site: SamSite, dt: float) -> None:
    """Fire channels of the side the player does not command: they find their own targets."""
    from ..sam import _in_envelope, _los
    st = w.catalog.sams[site.type_id]
    t = w.t
    sh = w.ships.get(site.carrier) if site.carrier else None
    if site.status != "ok" or (sh is not None and sh.state in ("sunk", "crippled")):
        return
    tgt = w.aircraft.get(site.lock) if site.lock else None
    valid = tgt is not None and tgt.state == "airborne" and \
        math.hypot(tgt.x - site.x, tgt.y - site.y) <= st.fc_range_km and _los(site, tgt)
    if site.state in ("idle", "search") or (site.state == "locked" and not valid):
        from .sense import jam_factor
        jammers = [a for a in w.aircraft.values() if a.state == "airborne" and a.jamming and a.side != site.side]
        best, bscore = None, 0.0
        locks: dict[str, int] = {}
        for o in w.sams.values():
            if o.side == site.side and o.lock:
                locks[o.lock] = locks.get(o.lock, 0) + 1
        for a in w.aircraft.values():
            if a.state != "airborne" or a.kind != "aircraft" or a.side in (site.side, "civil", "neutral"):
                continue
            d = math.hypot(a.x - site.x, a.y - site.y)
            if d > st.fc_range_km or not (st.alt_min_m <= a.alt <= st.alt_max_m) or not _los(site, a):
                continue
            if jammers and d > st.fc_range_km * jam_factor(w, site.x, site.y, a.x, a.y, jammers) * 0.7:
                continue                                         # the fire-control radar is jammed on that bearing
            if locks.get(a.id, 0) >= (3 if a.aim else 2) or not _in_envelope(w, site, st, a):
                continue
            score = (4.0 if a.aim else 1.0) / max(d, 1.0)
            if score > bscore:
                best, bscore = a, score
        if best is not None:
            site.lock, site.state, site.t_state = best.id, "locked", t
        else:
            site.lock, site.state = "", "idle"
        return
    if site.state == "locked":
        if t - site.t_state < st.acq_time_s:
            return
        if site.ready_missiles > 0 and _in_envelope(w, site, st, tgt):
            site.state, site.t_state = "engaging", t
            site.salvo_left = min(site.salvo_size, site.ready_missiles)
            site.t_next_launch = t
        return
    if site.state == "engaging":
        if site.salvo_left > 0 and t >= site.t_next_launch and site.ready_missiles > 0 and valid:
            m = Missile(id=f"M{w.next_id('msl')}", type_id=site.type_id, kind="sam", owner=site.id, side=site.side,
                        x=site.x, y=site.y, alt=site.elev + 10.0, target=tgt.id, t_launch=t)
            m.vz = 60.0
            w.missiles[m.id] = m
            site.ready_missiles -= 1
            site.fired += 1
            site.salvo_left -= 1
            site.t_next_launch = t + st.salvo_interval_s
            counter(w, f"sam_shots_{site.side}")
            if site.salvo_left == 0 or site.fired == 1:
                event(w, "sam_launch", f"{site.unit or site.name} fires {st.id} at {tgt.callsign or 'a target'}",
                      site.id, site.x, site.y, site.side, 1)
        if site.salvo_left <= 0 or site.ready_missiles <= 0 or not valid:
            site.state, site.t_state = "assess", t
        return
    if site.state == "assess":
        if any(m.owner == site.id and m.state == "flying" for m in w.missiles.values()):
            return
        site.state = "locked" if valid else "idle"
        site.t_state = t - st.acq_time_s
