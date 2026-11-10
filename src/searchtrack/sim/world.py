"""World: the single simulation state shared by every console, plus the
fixed-order tick that advances it."""
from __future__ import annotations

import json
import math
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import doctrine, flight, gci, ident, radar, sam, tracking
from .catalog import Catalog, FactionDef, load_catalog, load_toml
from .geo import Projection
from .serialize import dumps, from_data, transient
from .state import (Aircraft, Airbase, BattleState, Flight, FlightPlan, HeightFinder, HQState, Link, LogEntry, Message,
                    Missile, Objective, RadarSite, Report, SamSite, Ship, Squadron, Stats, Track, Trigger, Weather)
from .terrain import HorizonMask, Terrain, compute_mask

DT = 1.0
SAVE_VERSION = 1
_CATALOG: Optional[Catalog] = None


def catalog() -> Catalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_catalog()
    return _CATALOG


class Theater:
    def __init__(self, theater_id: str, data_dir: Path):
        self.dir = data_dir / "theaters" / theater_id
        self.cfg = load_toml(self.dir / "theater.toml")
        self.id = theater_id
        self.name = self.cfg.get("name", theater_id)
        pj = self.cfg["projection"]
        self.proj = Projection(pj["lat0"], pj["lon0"])
        self.extent = pj["extent_km"]
        tpath = self.dir / "terrain.npz"
        self.terrain = Terrain.load(tpath) if tpath.exists() else Terrain.flat()
        self._map = None

    @property
    def map(self) -> dict:
        if self._map is None:
            p = self.dir / "map.json"
            self._map = json.loads(p.read_text()) if p.exists() else {}
        return self._map

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        return self.proj.forward(lat, lon)

    def site(self, kind: str, sid: str) -> dict:
        for s in self.cfg.get(kind, []):
            if s["id"] == sid:
                return s
        raise KeyError(f"theater {self.id}: no {kind} {sid}")


_THEATERS: dict[str, Theater] = {}


def theater(theater_id: str) -> Theater:
    if theater_id not in _THEATERS:
        _THEATERS[theater_id] = Theater(theater_id, catalog().data_dir)
    return _THEATERS[theater_id]


@dataclass
class World:
    scenario_id: str = ""
    title: str = ""
    faction: str = "US"
    theater_id: str = ""
    t: float = 0.0
    tick: int = 0
    duration: float = 7200.0
    start_clock: str = "1962-10-24T22:00:00"
    clock_tz: str = "Z"
    seed: int = 1
    rng_state: list[Any] = field(default_factory=list)
    own_side: str = "blue"
    aircraft: dict[str, Aircraft] = field(default_factory=dict)
    flights: dict[str, Flight] = field(default_factory=dict)
    squadrons: dict[str, Squadron] = field(default_factory=dict)
    airbases: dict[str, Airbase] = field(default_factory=dict)
    radars: dict[str, RadarSite] = field(default_factory=dict)
    hfs: dict[str, HeightFinder] = field(default_factory=dict)
    sams: dict[str, SamSite] = field(default_factory=dict)
    missiles: dict[str, Missile] = field(default_factory=dict)
    tracks: dict[str, Track] = field(default_factory=dict)
    local_tracks: dict[str, dict[str, Track]] = field(default_factory=dict)
    plots: list[Report] = field(default_factory=list)
    local_plots: dict[str, list[Report]] = field(default_factory=dict)
    inbox: list[Report] = field(default_factory=list)
    strobes: list[Report] = field(default_factory=list)
    flight_plans: dict[str, FlightPlan] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)
    links: dict[str, Link] = field(default_factory=dict)
    hq: HQState = field(default_factory=HQState)
    objectives: list[Objective] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)
    weather: Weather = field(default_factory=Weather)
    vars: dict[str, float] = field(default_factory=dict)
    vid_reports: dict[str, tuple[str, str]] = field(default_factory=dict)
    automation: dict[str, bool] = field(default_factory=dict)
    duplex: dict[str, str] = field(default_factory=lambda: {"A": "active", "B": "standby"})
    duplex_until: float = -1.0
    duplex_repair: dict[str, float] = field(default_factory=dict)
    zones: dict[str, dict[str, Any]] = field(default_factory=dict)
    cities: list[dict[str, Any]] = field(default_factory=list)
    pending_flights: dict[str, dict[str, Any]] = field(default_factory=dict)
    briefing: str = ""
    exercise: bool = False                # exercise rules: kills are simulated and scored
    faction_override: dict[str, Any] = field(default_factory=dict)
    sun_offset_h: float = 0.0             # local solar time minus scenario clock
    intel: list[list[str]] = field(default_factory=list)
    headlines: list[dict[str, Any]] = field(default_factory=list)
    lesson: dict[str, Any] = field(default_factory=dict)   # current instructor step (training)
    ids: dict[str, int] = field(default_factory=dict)
    ships: dict[str, Ship] = field(default_factory=dict)
    battle: BattleState = field(default_factory=BattleState)
    track_seq: int = 0
    reliability: float = 1.0
    ended: bool = False
    result: str = ""
    end_reason: str = ""
    # ---- transient (rebuilt on load)
    catalog: Catalog = transient()
    theater: Theater = transient()
    faction_def: FactionDef = transient()
    rng: random.Random = transient()
    masks: dict = transient(default_factory=dict)
    last_eval: dict = transient(default_factory=dict)
    paints: dict = transient(default_factory=dict)
    new_messages: list = transient(default_factory=list)

    # ------------------------------------------------------------ setup
    def attach_static(self) -> None:
        self.catalog = catalog()
        self.theater = theater(self.theater_id)
        self.faction_def = self.catalog.factions[self.faction]
        if self.faction_override:
            import dataclasses
            self.faction_def = dataclasses.replace(self.faction_def, **self.faction_override)
        self.rng = random.Random(self.seed)
        if self.rng_state:
            s = self.rng_state
            self.rng.setstate((s[0], tuple(s[1]), s[2]))
        self.masks = {}
        self.last_eval = {}
        self.paints = {sid: deque(maxlen=4000) for sid in self.radars}
        self.new_messages = []

    # ------------------------------------------------------------ helpers
    def next_id(self, kind: str) -> int:
        n = self.ids.get(kind, 0) + 1
        self.ids[kind] = n
        return n

    def next_track_id(self, local: str = "") -> str:
        if local:
            return f"{local[:3].upper()}{self.next_id('lt_' + local):02d}"
        self.track_seq += 1
        fd = self.faction_def
        start = int(self.hq.policy.get("track_start", 1))
        n = start + self.track_seq - 1
        return f"{fd.track_prefix}{n:0{fd.track_digits}d}"

    def log_event(self, cat: str, text: str, ref: str = "") -> None:
        self.log.append(LogEntry(round(self.t, 1), cat, text, ref))
        if len(self.log) > 6000:
            del self.log[:1000]

    def alert(self, text: str, ref: str = "", priority: int = 1) -> Message:
        return doctrine.send(self, "system", "ALERT", text, priority, priority >= 1, ref, "alert")

    def radio(self, fl: Flight, text: str, priority: int = 0) -> None:
        doctrine.send(self, "radio", fl.callsign, text, priority, False, fl.id, "radio")

    def unit_report(self, site, text: str, priority: int = 0) -> None:
        doctrine.send(self, "voice", site.name, text, priority, priority >= 2, site.id, "report")

    def voice_vector(self, fl: Flight, hdg, alt, throttle: str) -> None:
        if self.faction_def.id == "US":
            parts = [f"{fl.callsign}, vector {hdg:03.0f}" if hdg is not None else fl.callsign]
            if alt is not None:
                parts.append(f"angels {alt / 0.3048 / 1000:.0f}")
            if throttle == "ab":
                parts.append("buster")
        else:
            parts = [f"{fl.callsign}, heading {hdg:03.0f}" if hdg is not None else fl.callsign]
            if alt is not None:
                parts.append(f"altitude {alt:,.0f} m")
            if throttle == "ab":
                parts.append("afterburner")
        doctrine.send(self, "radio", "CONTROL", ", ".join(parts), 0, False, fl.id, "vector")

    def radar_targets(self):
        for ac in self.aircraft.values():
            if ac.state == "airborne":
                yield ac

    def ground_height(self, x: float, y: float) -> float:
        return max(0.0, self.theater.terrain.height(x, y))

    def is_sea(self, x: float, y: float) -> bool:
        return self.theater.terrain.height(x, y) <= 0.0

    def mask_for(self, site) -> Optional[HorizonMask]:
        k = site.k_override or self.weather.k_factor
        if site.carrier:
            # airborne radar: smooth-Earth horizon from the aircraft's altitude (position independent)
            hq = round(site.h_ant / 250.0) * 250.0
            key = ("air", site.type_id, hq, round(k, 3))
            m = self.masks.get(key)
            if m is None:
                rt = self.catalog.radars.get(site.type_id)
                m = compute_mask(Terrain.flat(0.0, half_km=(rt.range_km if rt else 400.0) + 60.0, spacing=8.0),
                                 0.0, 0.0, max(hq, 50.0), (rt.range_km if rt else 400.0) + 10.0,
                                 land_sigma0_db=rt.clutter_db if rt else -20.0, sea_state=self.weather.sea_state, k=k)
                self.masks[key] = m
            return m
        key = (site.id, round(k, 3))
        m = self.masks.get(key)
        if m is None:
            rt = self.catalog.radars.get(site.type_id)
            rng_km = (rt.range_km if rt else 200.0) + 10.0
            m = compute_mask(self.theater.terrain, site.x, site.y, site.h_ant, rng_km,
                             land_sigma0_db=rt.clutter_db if rt else -20.0, sea_state=self.weather.sea_state, k=k)
            self.masks[key] = m
        return m

    def active_jammers(self, site) -> list:
        out = []
        for ac in self.aircraft.values():
            if ac.state != "airborne" or not ac.jamming or not ac.jammer:
                continue
            jt = self.catalog.jammers.get(ac.jammer)
            if jt is None:
                continue
            dx, dy = ac.x - site.x, ac.y - site.y
            r = math.hypot(dx, dy)
            if r > 700.0:
                continue
            if jt.mode == "spot" and self.t >= ac.jam_retune_t:
                ac.jam_retune_t = self.t + jt.retune_s
                ac.jam_channel = self._spot_channel(ac)
            out.append((ac, jt, math.degrees(math.atan2(dx, dy)) % 360.0, r))
        return out

    def _spot_channel(self, ac: Aircraft) -> int:
        best, bd = 0, math.inf
        for s in self.radars.values():
            d = math.hypot(s.x - ac.x, s.y - ac.y)
            if d < bd:
                best, bd = s.channel, d
        return best

    def track_for_truth(self, truth: str) -> Optional[Track]:
        best = None
        for trk in self.tracks.values():
            if tracking.truth_of(trk) == truth:
                if best is None or (best.lost and not trk.lost) or (best.lost == trk.lost and trk.t_update > best.t_update):
                    best = trk
        return best

    def truth_of(self, trk: Track) -> str:
        return tracking.truth_of(trk)

    def default_controller(self, x: float, y: float) -> str:
        if self.faction_def.pipeline != "manual":
            return "DC"
        best, bd = "", math.inf
        for s in self.radars.values():
            if s.gci and s.status == "ok":
                d = math.hypot(s.x - x, s.y - y)
                if d < bd:
                    best, bd = s.id, d
        return best

    def squadron_codes(self, sq: Squadron) -> dict[str, str]:
        if self.faction_def.id == "US":
            valid = self.hq.policy.get("mode1_valid", ["00"])
            return {"1": sq.iff_codes.get("1", valid[0]), "2": sq.iff_codes.get("2", "4000")}
        return {"period": sq.iff_codes.get("period", self.hq.policy.get("iff_period", ""))}

    def c2_up(self) -> bool:
        if self.faction_def.id != "US":
            return True
        return "active" in self.duplex.values() and self.t >= self.duplex_until

    def datalink_ok(self, fl: Flight) -> bool:
        at = self.catalog.aircraft.get(fl.type_id)
        return bool(at and at.datalink == "sage" and self.faction_def.id == "US" and self.c2_up())

    def can_engage_truth(self, truth: str, fl: Flight) -> tuple[bool, str]:
        trk = self.tracks.get(fl.target) or self.track_for_truth(truth)
        return doctrine.can_engage_track(self, trk)

    def can_engage_site(self, site) -> tuple[bool, str]:
        return doctrine.can_engage_site(self, site)

    def set_identity(self, tid: str, ident_: str, basis: str = "", authority: bool = False) -> tuple[bool, str]:
        trk = self.tracks.get(tid)
        if trk is None:
            return False, "no such track"
        if ident_ == "hostile" and not authority and tid not in self.hq.hostile and self.hq.weapons_status != "FREE":
            return False, "Hostile declaration requires higher authority — use REQUEST"
        trk.identity = ident_
        trk.id_basis = basis
        if ident_ != "pending" and trk.id_t < 0:
            trk.id_t = self.t
        truth = tracking.truth_of(trk)
        if truth:
            if ident_ != "pending":
                self.stats.first_id.setdefault(truth, self.t)
            self.stats.final_id[truth] = ident_
        self.log_event("id", f"{tid} identified {doctrine.id_label(self, ident_)} ({basis})", tid)
        return True, f"{tid}: {doctrine.id_label(self, ident_)}"

    def request_height(self, tid: str, front: bool = False) -> tuple[bool, str]:
        trk = self.tracks.get(tid)
        if trk is None:
            return False, "no such track"
        if not self.hfs:
            return False, "No height finders — V-beam estimates only"
        best, bscore = None, math.inf
        for hf in self.hfs.values():
            site = self.radars[hf.site_id]
            rt = self.catalog.radars[hf.type_id]
            if hf.status != "ok" or site.status in ("down", "maint"):
                continue
            d = math.hypot(trk.x - site.x, trk.y - site.y)
            if d > rt.range_km:
                continue
            score = len(hf.queue) * 60.0 + d * 0.1 + (30.0 if hf.current else 0.0)
            if score < bscore:
                best, bscore = hf, score
        if best is None:
            return False, f"{tid}: no height finder in range"
        if tid in best.queue:
            best.queue.remove(tid)
        if front:
            best.queue.insert(0, tid)
        else:
            best.queue.append(tid)
        trk.hf_requested = True
        site = self.radars[best.site_id]
        return True, f"Height request {tid} → {site.name} (queue {len(best.queue)})"

    def sim_killed(self, victim: str) -> bool:
        return self.vars.get(f"simkill_{victim}", 0.0) > 0.0

    def local_hour(self, t: Optional[float] = None) -> float:
        """Local solar time of day (hours) at the theater."""
        hh, mm = (int(x) for x in self.start_clock[11:16].split(":"))
        return (hh + mm / 60.0 + self.sun_offset_h + ((self.t if t is None else t) / 3600.0)) % 24.0

    def destroy(self, victim: str, cause: str, shooter: str = "", crash: bool = False) -> None:
        ac = self.aircraft.get(victim)
        if ac is None or ac.state != "airborne":
            return
        if self.exercise and not crash:
            if self.sim_killed(victim):
                return
            if ac.side == "civil":
                self.vars["civil_losses"] = self.vars.get("civil_losses", 0.0) + 1
                self.alert(f"EXERCISE VIOLATION: simulated attack on CIVIL aircraft {ac.callsign}", victim, 2)
            self.vars[f"simkill_{victim}"] = 1.0
            self.stats.sim_kills.append([victim, shooter or cause])
            self.vars["sim_kills"] = self.vars.get("sim_kills", 0.0) + 1
            self.alert(f"EXERCISE: {ac.callsign} assessed KILLED by {shooter or cause} (simulated)", victim, 0)
            self.log_event("kill", f"Simulated kill: {ac.callsign} by {shooter or cause}", victim)
            return
        ac.state = "destroyed"
        ac.destroyed_by = cause
        if ac.kind != "aircraft":
            return
        deb = Aircraft(id=f"{victim}~D", type_id=ac.type_id, callsign=f"{ac.callsign} debris", side=ac.side,
                       x=ac.x, y=ac.y, alt=ac.alt, hdg=ac.hdg, spd=ac.spd * 0.75, vs=-10.0, kind="debris",
                       rcs_scale=0.6, t_spawn=self.t, t_end=self.t + 210.0, truth_label="debris")
        self.aircraft[deb.id] = deb
        for s in self.sams.values():
            if s.lock == victim:
                s.lock = deb.id
        own_shooter = shooter in self.sams or shooter in self.flights or shooter.startswith("FL")
        self.stats.kills.append([victim, shooter or cause, ac.side])
        if ac.side == "civil":
            self.vars["civil_losses"] = self.vars.get("civil_losses", 0.0) + 1
            self.alert(f"FLASH: CIVIL AIRCRAFT {ac.callsign} DESTROYED", victim, 2)
        elif ac.side == self.own_side and own_shooter:
            self.vars["fratricide"] = self.vars.get("fratricide", 0.0) + 1
            self.alert(f"FLASH: OWN AIRCRAFT {ac.callsign} DESTROYED BY OWN WEAPONS", victim, 2)
        elif ac.side == self.own_side:
            self.alert(f"{ac.callsign} lost ({cause})", victim, 1)
        self.vars[f"destroyed_{victim}"] = 1.0
        self.log_event("result", f"{ac.callsign or victim} destroyed — {cause}", victim)
        if self.battle.active:
            from .battle import combat
            combat.on_destroyed(self, ac, cause, shooter)
        for fl in self.flights.values():
            if fl.contact == victim:
                fl.contact = ""
                if shooter == fl.id:
                    fl.kills.append(victim)
                    self.radio(fl, "splash one" if self.faction_def.id == "US" else "Target destroyed.", 1)

    # ------------------------------------------------------------ callbacks from tracking
    def on_track_update(self, trk: Track) -> None:
        des = self.hq.policy.get("designated")
        if des and not trk.local and trk.id not in self.hq.engage_ok and tracking.truth_of(trk) in des:
            # higher command follows the violator on its own picture and re-designates it
            self.hq.engage_ok.append(trk.id)
            self.set_identity(trk.id, "hostile", "designated violator by higher command", authority=True)
            doctrine.send(self, "voice", self.hq.name, f"Target {trk.id} is the violator. Fire permitted.", 1, True,
                          trk.id, "order")

    def on_track_lost(self, trk: Track) -> None:
        assigned = any(fl.target == trk.id and fl.state not in ("landed", "lost") for fl in self.flights.values())
        if assigned or trk.identity in ("unknown", "suspect", "hostile"):
            self.alert(f"TRACK {trk.id} LOST ({doctrine.id_label(self, trk.identity)})", trk.id, 1)
        self.log_event("track", f"Track {trk.id} lost", trk.id)

    def on_track_removed(self, tid: str) -> None:
        for s in self.sams.values():
            if s.assigned == tid:
                s.assigned = ""
        for hf in self.hfs.values():
            if tid in hf.queue:
                hf.queue.remove(tid)

    # ------------------------------------------------------------ the tick
    def step(self, dt: float = DT) -> None:
        if self.ended:
            return
        from . import scenario
        scenario.update(self)
        if self.battle.active:
            from . import battle
            battle.pre_step(self, dt)
        for ac in list(self.aircraft.values()):
            flight.step_mission(self, ac, dt)
        for fl in list(self.flights.values()):
            gci.flight_step(self, fl, dt)
        if self.battle.active:
            battle.mid_step(self, dt)
        for ac in list(self.aircraft.values()):
            flight.step_aircraft(self, ac, dt)
        for m in list(self.missiles.values()):
            sam.missile_step(self, m, dt)
        for site in self.radars.values():
            if site.carrier:
                self._carry(site)
            self._reliability(site)
            paints, reps = radar.sweep(self, site, dt)
            if paints:
                self.paints.setdefault(site.id, deque(maxlen=4000)).extend(paints)
            tracking.route_reports(self, site, reps)
        for hf in self.hfs.values():
            radar.height_finder_step(self, hf)
        if self.c2_up():
            tracking.deliver(self)
        else:
            self.inbox = [r for r in self.inbox if self.t - r.t < 60.0]
        if self.automation.get("surveil") and self.faction_def.pipeline == "digital" and self.c2_up():
            tracking.auto_initiate(self, self.plots, self.tracks, min_hits=3, latency=12.0)
        tracking.maintain(self)
        if self.automation.get("ident"):
            ident.auto_identify(self)
        if self.automation.get("height") and self.tick % 5 == 0:
            self._auto_height()
        ident.check_adiz(self)
        for s in self.sams.values():
            sam.sam_step(self, s, dt)
        gci.recover_squadrons(self)
        if self.battle.active:
            battle.post_step(self, dt)
        self._upgrades()
        doctrine.comms_step(self)
        doctrine.hq_step(self)
        self._duplex_step()
        self._links_step()
        self._weather_step(dt)
        scenario.evaluate_objectives(self)
        if self.tick % (5 if self.battle.active else 10) == 0:
            self._snapshot()
        if self.tick % 60 == 0:
            self._cleanup()
        self.t += dt
        self.tick += 1
        if self.t >= self.duration and not self.ended:
            scenario.end(self, "Shift complete", "time")

    # ------------------------------------------------------------ subsystems
    def _carry(self, site: RadarSite) -> None:
        """Airborne radar rides with its aircraft; off the air if the aircraft is not airborne.
        Shipborne radar sails with its ship, and is silent under emission control."""
        sh = self.ships.get(site.carrier)
        if sh is not None:
            site.x, site.y, site.elev = sh.x, sh.y, 0.0
            off = sh.state in ("sunk", "crippled") or sh.emcon
            if off and site.status != "down":
                site.status, site.fail_t = "down", 1e12
            elif not off and site.status == "down" and site.fail_t >= 1e11:
                site.status, site.fail_t = "ok", -1.0
            return
        ac = self.aircraft.get(site.carrier)
        if ac is None or ac.state != "airborne":
            if site.status != "down":
                site.status = "down"
                site.fail_t = 1e12
                self.unit_report(site, "Airborne radar off station")
            return
        site.x, site.y, site.elev, site.mast_m = ac.x, ac.y, ac.alt, 0.0
        if site.status == "down" and site.fail_t >= 1e11:
            site.status = "ok"
            site.fail_t = -1.0
            self.unit_report(site, "Airborne radar on station")

    def _auto_height(self) -> None:
        for trk in self.tracks.values():
            if trk.lost or trk.hf_requested or trk.jammer:
                continue
            stale = trk.alt is None or (trk.alt_src not in ("HF", "VID", "MODEC") and self.t - trk.alt_t > 240.0) \
                or (trk.alt_src == "HF" and self.t - trk.alt_t > 600.0)
            interesting = trk.identity in ("pending", "unknown", "suspect", "hostile") or \
                any(fl.target == trk.id for fl in self.flights.values())
            if stale and interesting and trk.alt_fails < 3:
                self.request_height(trk.id)

    def _reliability(self, site: RadarSite) -> None:
        rt = self.catalog.radars[site.type_id]
        t = self.t
        if site.status == "maint":
            if t >= site.maint_until:
                site.status = "ok"
                site.degraded_db = 0.0
                site.fail_t = t + self.rng.expovariate(1.0 / (rt.mtbf_h * 3600.0 * self.reliability * 1.5))
                self.unit_report(site, "Maintenance complete — radar back on the air")
            return
        if site.fail_t < 0:
            site.fail_t = t + self.rng.expovariate(1.0 / (rt.mtbf_h * 3600.0 * self.reliability))
        if site.status in ("ok", "degraded") and t >= site.fail_t:
            if self.rng.random() < 0.5:
                site.status = "degraded"
                site.degraded_db = self.rng.choice([4.0, 6.0, 9.0])
                self.alert(f"{site.name}: transmitter degraded ({site.degraded_db:.0f} dB loss)", site.id, 1)
                site.fail_t = t + self.rng.expovariate(1.0 / (rt.mtbf_h * 3600.0 * self.reliability))
            else:
                site.status = "down"
                site.repair_t = t + rt.mttr_min * 60.0 * self.rng.uniform(0.6, 1.6)
                self.alert(f"{site.name}: RADAR DOWN — est. repair {rt.mttr_min:.0f} min", site.id, 1)
        if site.status == "down" and 0 <= site.repair_t <= t:
            site.status = "ok"
            site.degraded_db = 0.0
            site.repair_t = -1.0
            site.fail_t = t + self.rng.expovariate(1.0 / (rt.mtbf_h * 3600.0 * self.reliability))
            self.unit_report(site, "Radar restored to service", 1)

    def _upgrades(self) -> None:
        for sq in self.squadrons.values():
            done = [u for u in sq.upgrading if u[0] <= self.t]
            if not done:
                continue
            sq.upgrading = [u for u in sq.upgrading if u[0] > self.t]
            for _, bucket in done:
                key = _bucket_key(bucket)
                slower = sorted((k for k in sq.ready if float(k) > bucket and sq.ready[k] > 0), key=float)
                if slower:
                    sq.ready[slower[-1]] -= 1
                    sq.ready[key] = sq.ready.get(key, 0) + 1

    def _duplex_step(self) -> None:
        if self.faction_def.id != "US":
            return
        for side, t_rep in list(self.duplex_repair.items()):
            if self.t >= t_rep:
                self.duplex[side] = "standby"
                del self.duplex_repair[side]
                self.log_event("sys", f"AN/FSQ-7 {side}-side repaired, standby")
        if self.duplex_until >= 0 and self.t >= self.duplex_until:
            self.duplex_until = -1.0
            self.log_event("sys", "AN/FSQ-7 switchover complete")
            self.alert("SWITCHOVER COMPLETE — COMPUTER ON LINE", priority=0)
        if "active" not in self.duplex.values() and self.automation.get("tech") and self.duplex_until < 0:
            if self.vars.get("auto_switch_t", -1.0) < 0:
                self.vars["auto_switch_t"] = self.t + 25.0
            elif self.t >= self.vars["auto_switch_t"]:
                self.vars["auto_switch_t"] = -1.0
                self.switchover()

    def switchover(self) -> tuple[bool, str]:
        stby = [s for s, v in self.duplex.items() if v == "standby"]
        if not stby:
            return False, "No standby computer available"
        for s, v in self.duplex.items():
            if v == "active":
                self.duplex[s] = "standby"
        self.duplex[stby[0]] = "active"
        self.duplex_until = self.t + 45.0
        self.log_event("cmd", f"AN/FSQ-7 switchover to {stby[0]}-side")
        return True, f"Switchover to {stby[0]}-side in progress (≈45 s, tracking frozen)"

    def fail_computer(self, side: str = "") -> None:
        side = side or next((s for s, v in self.duplex.items() if v == "active"), "A")
        self.duplex[side] = "failed"
        self.duplex_repair[side] = self.t + self.rng.uniform(1800.0, 3600.0)
        self.alert(f"AN/FSQ-7 {side}-SIDE FAILURE — SWITCHOVER REQUIRED", priority=2)

    def _links_step(self) -> None:
        for ln in self.links.values():
            if not ln.up and 0 <= ln.repair_t <= self.t:
                ln.up = True
                ln.repair_t = -1.0
                self.alert(f"{ln.name} restored", priority=0)

    def _weather_step(self, dt: float) -> None:
        for c in self.weather.cells:
            c.x += c.vx * dt
            c.y += c.vy * dt

    def _snapshot(self) -> None:
        acs = [[a.id, round(a.x, 1), round(a.y, 1), round(a.alt), a.side, a.kind]
               for a in self.aircraft.values() if a.state == "airborne"]
        trs = [[k.id, round(k.x, 1), round(k.y, 1), k.identity] for k in self.tracks.values() if not k.lost]
        snap = [round(self.t), acs, trs]
        if self.battle.active:     # battles: ships and missiles too, for the replay
            snap.append([[s.id, round(s.x, 2), round(s.y, 2), round(s.hdg), s.side, s.state]
                         for s in self.ships.values()])
            snap.append([[m.id, round(m.x, 1), round(m.y, 1), m.side, m.kind]
                         for m in self.missiles.values() if m.state == "flying" and self.t >= m.t_launch])
        self.stats.truth_snaps.append(snap)

    def _cleanup(self) -> None:
        for mid in [m.id for m in self.missiles.values() if m.state == "done" and self.t - m.t_launch > 120.0]:
            del self.missiles[mid]
        for aid in [a.id for a in self.aircraft.values()
                    if a.kind == "debris" and a.state != "airborne"]:
            del self.aircraft[aid]


def _bucket_key(minutes: float) -> str:
    return f"{minutes:g}"


# ---------------------------------------------------------------- save / load

def save_json(world: World) -> str:
    world.rng_state = [list(x) if isinstance(x, tuple) else x for x in world.rng.getstate()]
    return json.dumps({"version": SAVE_VERSION, "world": json.loads(dumps(world))}, separators=(",", ":"))


def load_json(text: str) -> World:
    data = json.loads(text)
    if data.get("version") != SAVE_VERSION:
        raise ValueError(f"unsupported save version {data.get('version')}")
    w = from_data(World, data["world"])
    w.attach_static()
    return w
