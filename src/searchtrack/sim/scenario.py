"""Scenario loading (TOML → World), scripted triggers and objectives."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

from . import doctrine, ident
from .catalog import load_toml
from .geo import FT, KT, NM, bearing_deg, heading_vec
from .state import (Aircraft, Airbase, FlightPlan, HeightFinder, HQState, Link, Mission, Objective, RadarSite,
                    SamSite, Squadron, Stats, Transponder, Trigger, Waypoint, Weather, WeatherCell)
from .world import World, catalog, theater


def scenario_dir() -> Path:
    return catalog().data_dir / "scenarios"


def list_scenarios() -> list[dict[str, Any]]:
    out = []
    for p in sorted(scenario_dir().glob("*.toml")):
        d = load_toml(p)
        out.append({"id": d["id"], "title": d["title"], "faction": d["faction"], "kind": d.get("kind", "scenario"),
                    "subtitle": d.get("subtitle", ""), "summary": d.get("summary", ""), "order": d.get("order", 50),
                    "path": str(p), "start": d.get("start", ""), "theater": d.get("theater", ""),
                    "photo": list(d.get("photo", [])), "photo_caption": d.get("photo_caption", ""),
                    "difficulty": d.get("difficulty", 2), "era": d.get("era", d.get("start", "1960")[:3] + "0s"),
                    "duration_min": d.get("duration_min", 120), "n_objectives": len(d.get("objective", [])),
                    "campaign": d.get("campaign", True), "night": d.get("weather", {}).get("night", False)})
    out.sort(key=lambda s: (s["faction"], s["order"]))
    return out


def _alt(d: dict, key: str = "alt") -> float:
    if f"{key}_ft" in d:
        return d[f"{key}_ft"] * FT
    return float(d.get(f"{key}_m", d.get(key, 0.0)))


def _spd(d: dict) -> float:
    if "kt" in d:
        return d["kt"] * KT
    return float(d.get("kmh", 0.0)) / 3.6


def load_scenario(path_or_id: str) -> dict[str, Any]:
    p = Path(path_or_id)
    if not p.exists():
        p = scenario_dir() / f"{path_or_id}.toml"
    return load_toml(p)


def build_world(path_or_id: str, seed: Optional[int] = None) -> World:
    return build_world_from(load_scenario(path_or_id), seed)


def build_world_from(sc: dict[str, Any], seed: Optional[int] = None) -> World:
    th = theater(sc["theater"])
    w = World(scenario_id=sc["id"], title=sc["title"], faction=sc["faction"], theater_id=sc["theater"],
              duration=sc.get("duration_min", 120) * 60.0, start_clock=sc.get("start", "1962-10-24T22:00:00"),
              clock_tz=sc.get("tz", "Z"), seed=int(seed if seed is not None else sc.get("seed", 1)))
    w.faction_override = dict(sc.get("faction_override", {}))
    w.exercise = bool(sc.get("exercise", False))
    w.sun_offset_h = float(sc.get("sun_offset_h", 0.0))
    w.attach_static()
    w.briefing = sc.get("briefing", "")
    w.intel = [[i["title"], i["text"]] for i in sc.get("intel", [])]
    w.headlines = [dict(h) for h in sc.get("headline", [])]
    w.reliability = sc.get("reliability", 1.0)
    w.automation = dict({"surveil": True, "ident": True, "height": True, "tech": False}, **sc.get("automation", {}))
    w.own_side = "blue"
    # weather
    wd = sc.get("weather", {})
    w.weather = Weather(k_factor=wd.get("k_factor", 4.0 / 3.0), wind_from=wd.get("wind_from", 270.0),
                        wind_kmh=wd.get("wind_kmh", 60.0), ceiling_m=wd.get("ceiling_m", 3000.0),
                        visibility_km=wd.get("visibility_km", 20.0), night=wd.get("night", False),
                        sea_state=wd.get("sea_state", 3.0))
    for c in wd.get("cells", []):
        x, y = th.xy(c["lat"], c["lon"])
        hx, hy = heading_vec(c.get("move_to", 90.0))
        v = c.get("move_kmh", 30.0) / 3600.0
        w.weather.cells.append(WeatherCell(x, y, c.get("r_km", 25.0), c.get("intensity", 0.5), hx * v, hy * v))
    # HQ
    hd = sc.get("hq", {})
    w.hq = HQState(name=hd.get("name", "HQ"), readiness=hd.get("readiness", ""), alert=hd.get("alert", ""),
                   weapons_status=hd.get("weapons_status", "HOLD"), policy=dict(hd.get("policy", {})))
    # zones & cities
    for z in th.cfg.get("zone", []) + sc.get("zone", []):
        if z.get("shape", "poly") == "circle":
            x, y = th.xy(z["lat"], z["lon"])
            w.zones[z["id"]] = {"name": z["name"], "kind": z.get("kind", ""), "shape": "circle", "x": x, "y": y,
                                "r": z["r_km"], "name_ru": z.get("name_ru", "")}
        else:
            w.zones[z["id"]] = {"name": z["name"], "kind": z.get("kind", ""), "shape": "poly",
                                "poly": [list(th.xy(a, b)) for a, b in z["points"]], "name_ru": z.get("name_ru", "")}
    for c in th.cfg.get("city", []):
        x, y = th.xy(c["lat"], c["lon"])
        w.cities.append({"name": c["name"], "x": x, "y": y, "size": c.get("size", 1), "label": c.get("label", ""),
                         "name_ru": c.get("name_ru", "")})
    # links
    for ln in sc.get("link", []):
        w.links[ln["id"]] = Link(ln["id"], ln.get("name", ln["id"]), ln.get("kind", "voice"), ln.get("up", True),
                                 ln.get("delay_s", 5.0))
    # radars
    for i, r in enumerate(sc.get("radar", [])):
        rt = w.catalog.radars[r["type"]]
        if "carrier" in r:          # airborne radar riding on a scripted aircraft
            site = RadarSite(id=r["id"], name=r.get("name", r["id"]), type_id=r["type"], x=0.0, y=0.0, elev=0.0,
                             mast_m=0.0, unit=r.get("unit", ""), status="down", az=w.rng.uniform(0, 360),
                             rpm=r.get("rpm", rt.rpm), mti=r.get("mti", rt.mti), pfa_exp=r.get("pfa_exp", 6.0),
                             link=r.get("link", ""), bias_r=0.0, bias_az=0.0, gci=r.get("gci", False),
                             name_ru=r.get("name_ru", ""), carrier=r["carrier"])
            site.fail_t = 1e12
            w.radars[site.id] = site
            continue
        s = th.site("radar_site", r["site"])
        x, y = th.xy(s["lat"], s["lon"])
        site = RadarSite(id=r["site"], name=s["name"], type_id=r["type"], x=x, y=y, elev=s.get("elev_m", 100.0),
                         mast_m=s.get("mast_m", 20.0), unit=r.get("unit", s.get("unit", "")),
                         status=r.get("status", "ok"), az=w.rng.uniform(0, 360), rpm=r.get("rpm", rt.rpm),
                         mti=r.get("mti", rt.mti), pfa_exp=r.get("pfa_exp", 6.0), channel=r.get("channel", 0),
                         link=r.get("link", ""), bias_r=r.get("bias_r", w.rng.uniform(-0.6, 0.6)),
                         bias_az=r.get("bias_az", w.rng.uniform(-0.3, 0.3)), gci=r.get("gci", False),
                         name_ru=s.get("name_ru", ""))
        w.radars[site.id] = site
        for j, hft in enumerate(r.get("hf", [])):
            hid = f"{site.id}-HF{j + 1}"
            w.hfs[hid] = HeightFinder(hid, site.id, hft, az=w.rng.uniform(0, 360))
    # airbases & squadrons
    for b in sc.get("airbase", []):
        s = th.site("airbase", b["site"])
        x, y = th.xy(s["lat"], s["lon"])
        w.airbases[b["site"]] = Airbase(b["site"], s["name"], x, y, s.get("elev_m", 50.0), b.get("side", "blue"),
                                        s.get("kind", "military"), b.get("runway_ok", True), b.get("link", ""),
                                        name_ru=s.get("name_ru", ""))
    for q in sc.get("squadron", []):
        at = w.catalog.aircraft[q["type"]]
        w.squadrons[q["id"]] = Squadron(q["id"], q["name"], q["base"], q["type"], q["callsign"],
                                        ready={str(k): int(v) for k, v in q.get("ready", {}).items()},
                                        maint=q.get("maint", 0), pilots=q.get("pilots", 10),
                                        loadout=dict(q["loadout"] if "loadout" in q else at.weapons),
                                        turnaround_min=q.get("turnaround_min", 40.0),
                                        iff_codes=dict(q.get("iff_codes", {})))
    # SAMs
    for m in sc.get("sam", []):
        s = th.site("sam_site", m["site"])
        x, y = th.xy(s["lat"], s["lon"])
        st = w.catalog.sams[m["type"]]
        w.sams[m["site"]] = SamSite(m["site"], s["name"], m["type"], x, y, s.get("elev_m", 100.0), "blue",
                                    m.get("unit", s.get("unit", "")), readiness_min=m.get("readiness_min", 0.0),
                                    t_ready=m.get("readiness_min", 0.0) * 60.0 if m.get("alerted", True) else 1e9,
                                    ready_missiles=m.get("missiles", st.launchers), reloads=m.get("reloads", 6),
                                    salvo_size=m.get("salvo", st.salvo), auto=m.get("auto", False),
                                    link=m.get("link", ""), name_ru=s.get("name_ru", ""))
    # scripted flights and flight plans (plus generated civil traffic)
    flights = list(sc.get("flight", [])) + generate_traffic(w, th, sc.get("traffic", []))
    for f in flights:
        if "flight_plan" in f:
            _make_plan(w, th, f)
        if f.get("spawn", "time") == "trigger":
            w.pending_flights[f["id"]] = f
        else:
            w.pending_flights[f["id"]] = f
    for tr in sc.get("trigger", []):
        w.triggers.append(Trigger(tr["id"], tr.get("cond", {}), list(tr.get("actions", [])), tr.get("once", True)))
    for o in sc.get("objective", []):
        w.objectives.append(Objective(o["id"], o["text"], o["kind"], dict(o.get("params", {})), o.get("points", 10),
                                      hidden=o.get("hidden", False), penalty=o.get("penalty", 0)))
    w.vars.update({k: float(v) for k, v in sc.get("vars", {}).items()})
    w.log_event("sys", f"Scenario {w.title} started")
    _spawn_due(w)
    return w


TRAFFIC_TYPES = {
    "US": {1950: ["DC-7C", "L-1049", "Viscount", "CV-440"], 1960: ["B707", "DC-7C", "L-1049", "Viscount"],
           1970: ["B707", "B747", "DC-10"], 1980: ["B747", "DC-10", "B707"]},
    "USSR": {1950: ["Il-14", "Li-2"], 1960: ["Tu-104", "Il-14", "Il-18"], 1970: ["Tu-134", "Il-18", "Il-62"],
             1980: ["Tu-134", "Il-62", "Il-18"]},
}


def generate_traffic(w: World, th, specs: list[dict]) -> list[dict]:
    """Expand [[traffic]] blocks into scripted civil flights with flight plans and transponder codes.

    A block: { count, routes = [[from_city, to_city], ...], types = [...], alt_ft = [lo, hi] or alt_m,
    t_window = [t0, t1] seconds, off_plan = fraction flying late/early or off course, side, callsigns = [...],
    transponder = "atc" | "sif" | "none", squawk = "...", plan_kind = "IFR" }"""
    if not specs:
        return []
    import random as _random
    rng = _random.Random(w.seed * 7919 + 13)
    cities = {c["name"]: c for c in th.cfg.get("city", [])}
    for c in th.cfg.get("waypoint", []):
        cities[c["name"]] = c
    year = int(w.start_clock[:4])
    era = 1950 if year < 1960 else 1960 if year < 1970 else 1970 if year < 1980 else 1980
    out = []
    n_all = 0
    for spec in specs:
        types = spec.get("types") or TRAFFIC_TYPES.get(w.faction, TRAFFIC_TYPES["US"])[era]
        types = [t for t in types if t in w.catalog.aircraft] or ["B707"]
        calls = spec.get("callsigns", ["TCA", "AAL", "PAA", "EAL", "NWA", "UAL"] if w.faction == "US" else ["AEROFLOT"])
        t0, t1 = spec.get("t_window", [0.0, w.duration * 0.8])
        for i in range(int(spec.get("count", 4))):
            a, b = rng.choice(spec["routes"])
            ca, cb = cities[a], cities[b]
            if rng.random() < 0.5 and spec.get("both_ways", True):
                ca, cb = cb, ca
            typ = rng.choice(types)
            at = w.catalog.aircraft[typ]
            if "alt_ft" in spec:
                alt = rng.uniform(*spec["alt_ft"]) * FT
            else:
                alt = rng.uniform(*spec.get("alt_m", [at.cruise_alt_m * 0.75, at.cruise_alt_m]))
            alt = round(alt / 300.0) * 300.0
            kmh = at.cruise_kmh * rng.uniform(0.93, 1.02)
            n_all += 1
            cs_pref = rng.choice(calls)
            callsign = f"{cs_pref} {rng.randint(100, 989)}" if w.faction == "US" else f"{cs_pref} {rng.randint(1000, 9899)}"
            fid = f"tr{n_all:02d}"
            spawn_t = rng.uniform(t0, t1)
            # fly from just inside the theater edge if the city is outside the play area
            lat0, lon0 = ca["lat"], ca["lon"]
            lat1, lon1 = cb["lat"], cb["lon"]
            mid = (lat0 * 0.85 + lat1 * 0.15, lon0 * 0.85 + lon1 * 0.15)
            f = {"id": fid, "type": typ, "callsign": callsign, "side": spec.get("side", "civil"), "spawn_t": spawn_t,
                 "truth_label": f"{at.name}, {callsign}", "markings": spec.get("markings", "civil airliner"),
                 "start": {"lat": mid[0], "lon": mid[1], "alt_m": alt, "kmh": kmh},
                 "route": [{"lat": lat1, "lon": lon1, "alt_m": max(600.0, alt * 0.3) if spec.get("land", True)
                            else alt, "kmh": kmh * 0.8, "action": "land" if spec.get("land", True) else "remove"}]}
            tx = spec.get("transponder", "atc" if era >= 1960 or w.faction == "US" else "none")
            if tx != "none":
                code = spec.get("squawk") or f"{rng.randint(1, 7)}{rng.randint(0, 7)}{rng.randint(0, 7)}{rng.randint(0, 7)}"
                f["transponder"] = {"system": tx, "codes": {"3": code}}
            else:
                f["transponder"] = {"system": "none"}
            if spec.get("plans", True):
                fp = {"kind": spec.get("plan_kind", "IFR"), "mode3": f.get("transponder", {}).get("codes", {}).get("3", "")}
                if rng.random() < spec.get("off_plan", 0.12):
                    if rng.random() < 0.6:
                        fp["delay_min"] = rng.choice([-1, 1]) * rng.uniform(6.0, 14.0)
                    else:
                        fp["offset_nm"] = rng.choice([-1, 1]) * rng.uniform(14.0, 30.0)
                f["flight_plan"] = fp
            out.append(f)
    return out


def _route(th, f: dict) -> list[Waypoint]:
    wps = []
    for p in f["route"]:
        x, y = th.xy(p["lat"], p["lon"])
        wps.append(Waypoint(x, y, _alt(p), _spd(p) or _spd(f), p.get("action", "")))
    return wps


def _make_plan(w: World, th, f: dict) -> None:
    fp = f["flight_plan"]
    wps = _route(th, f)
    t = f.get("spawn_t", 0.0) + fp.get("delay_min", 0.0) * 60.0 * -1.0
    off = fp.get("offset_nm", 0.0) * NM
    pts = []
    x0, y0 = th.xy(f["start"]["lat"], f["start"]["lon"]) if "start" in f else (wps[0].x, wps[0].y)
    prev = (x0, y0)
    from .flight import wind_vector
    for wp in wps:
        d = math.hypot(wp.x - prev[0], wp.y - prev[1])
        brg = bearing_deg(wp.x - prev[0], wp.y - prev[1])
        ux, uy = heading_vec(brg)
        wx, wy = wind_vector(w, wp.alt)              # planned with the forecast wind
        gs = max(wp.spd + wx * ux + wy * uy, 30.0)
        t += d / (gs / 1000.0) * (1.0 + fp.get("speed_error", 0.0))
        hx, hy = heading_vec(brg + 90.0)
        pts.append([wp.x + hx * off, wp.y + hy * off, t])
        prev = (wp.x, wp.y)
    pts.insert(0, [x0, y0, f.get("spawn_t", 0.0) - fp.get("delay_min", 0.0) * 60.0])
    w.flight_plans[f["id"]] = FlightPlan(f["id"], fp.get("callsign", f["callsign"]), f["type"], fp.get("kind", "IFR"),
                                         pts, _alt(f.get("route", [{}])[0]) if f.get("route") else 0.0,
                                         fp.get("mode3", f.get("transponder", {}).get("codes", {}).get("3", "")),
                                         fp.get("filed", True), fp.get("note", ""))


def spawn_flight(w: World, f: dict) -> list[str]:
    th = w.theater
    at = w.catalog.aircraft[f["type"]]
    wps = _route(th, f) if "route" in f else []
    if "start" in f:
        x, y = th.xy(f["start"]["lat"], f["start"]["lon"])
        alt = _alt(f["start"]) or (wps[0].alt if wps else at.cruise_alt_m)
    else:
        x, y, alt = wps[0].x, wps[0].y, wps[0].alt
        wps = wps[1:] or wps
    spd = _spd(f.get("start", {})) or (wps[0].spd if wps else at.cruise_kmh / 3.6)
    src = w.aircraft.get(f.get("launch_from", ""))
    if src is not None:
        if src.state != "airborne":
            return []
        x, y, alt = src.x, src.y, max(src.alt - 300.0, 100.0)
    hdg = bearing_deg(wps[0].x - x, wps[0].y - y) if wps else f.get("hdg", 0.0)
    ids = []
    n = f.get("count", 1)
    for i in range(n):
        tr = f.get("transponder", {})
        aid = f["id"] if n == 1 else f"{f['id']}-{i + 1}"
        hx, hy = heading_vec(hdg + 90.0)
        bx, by = heading_vec(hdg)
        sep = f.get("spacing_km", 0.9)
        ox = hx * sep * i * (1 if i % 2 else -1) - bx * sep * 1.5 * i
        oy = hy * sep * i * (1 if i % 2 else -1) - by * sep * 1.5 * i
        ac = Aircraft(id=aid, type_id=f["type"], callsign=f.get("callsign", aid), side=f.get("side", "civil"),
                      x=x + ox, y=y + oy, alt=alt, hdg=hdg, spd=spd,
                      fuel=at.fuel_kg * f.get("fuel_frac", 0.8),
                      transponder=Transponder(tr.get("system", at.transponder), tr.get("on", True),
                                              tr.get("failed", False), dict(tr.get("codes", {}))),
                      mission=Mission(kind=f.get("mission", "route"),
                                      waypoints=[Waypoint(p.x + ox, p.y + oy, p.alt, p.spd, p.action if i == 0 else
                                                          p.action.replace("var:", "noop:")) for p in wps],
                                      on_intercept=f.get("on_intercept", "comply"), wander=f.get("wander", 0.0),
                                      alt_day=_alt(f, "alt_day") if ("alt_day_m" in f or "alt_day_ft" in f) else 0.0,
                                      alt_night=_alt(f, "alt_night") if ("alt_night_m" in f or "alt_night_ft" in f)
                                      else 0.0,
                                      agl=float(f.get("agl_m", 0.0)), on_signal=f.get("on_signal", "")),
                      jammer=f.get("jammer", ""), jamming=f.get("jamming", False),
                      flight_plan=f["id"] if "flight_plan" in f else "", kind=f.get("kind", "aircraft"),
                      rcs_scale=f.get("rcs_scale", 1.0), visible_to=list(f.get("visible_to", [])),
                      t_spawn=w.t, truth_label=f.get("truth_label", at.name), nationality=f.get("nationality", ""),
                      markings=f.get("markings", ""))
        ac.cmd_alt = alt
        w.aircraft[aid] = ac
        ids.append(aid)
    w.log_event("sys", f"[truth] {f.get('callsign', f['id'])} ({at.name}) entered play", f["id"])
    return ids


def _spawn_due(w: World) -> None:
    for fid in list(w.pending_flights):
        f = w.pending_flights[fid]
        if f.get("spawn", "time") == "time" and f.get("spawn_t", 0.0) <= w.t:
            del w.pending_flights[fid]
            spawn_flight(w, f)


# ---------------------------------------------------------------- triggers

def _truth_ids(w: World, ac: str) -> list[str]:
    if ac in w.aircraft:
        return [ac]
    return [k for k in w.aircraft if k.startswith(ac + "-")]


def cond(w: World, c: dict) -> bool:
    t = c.get("type", "time")
    if t == "time":
        return w.t >= c["t"]
    if t == "all":
        return all(cond(w, x) for x in c["of"])
    if t == "any":
        return any(cond(w, x) for x in c["of"])
    if t == "not":
        return not cond(w, c["c"])
    if t == "var":
        v = w.vars.get(c["name"], 0.0)
        return {"<": v < c["value"], "<=": v <= c["value"], ">": v > c["value"], ">=": v >= c["value"],
                "==": v == c["value"]}[c.get("op", ">=")]
    if t == "destroyed":
        return any(w.aircraft[a].state == "destroyed" for a in _truth_ids(w, c["ac"]))
    if t == "gone":
        ids = _truth_ids(w, c["ac"])
        return bool(ids) and all(w.aircraft[a].state in ("gone", "landed", "destroyed") for a in ids)
    if t == "spawned":
        return bool(_truth_ids(w, c["ac"]))
    if t == "in_zone":
        return any(w.aircraft[a].state == "airborne" and ident.zone_contains(w, c["zone"], w.aircraft[a].x,
                                                                              w.aircraft[a].y)
                   for a in _truth_ids(w, c["ac"]))
    if t == "near":
        x, y = (w.theater.xy(c["lat"], c["lon"]) if "lat" in c else (w.radars[c["site"]].x, w.radars[c["site"]].y))
        return any(w.aircraft[a].state == "airborne" and math.hypot(w.aircraft[a].x - x, w.aircraft[a].y - y) <= c["km"]
                   for a in _truth_ids(w, c["ac"]))
    if t == "vid":
        return any(a in w.stats.vid for a in _truth_ids(w, c["ac"]))
    if t == "tracked":
        return any(w.track_for_truth(a) is not None for a in _truth_ids(w, c["ac"]))
    if t == "identity":
        for a in _truth_ids(w, c["ac"]):
            trk = w.track_for_truth(a)
            if trk is not None and trk.identity in c["is"]:
                return True
        return False
    if t == "alert":
        return w.hq.alert == c["is"]
    if t == "sam_fired":
        return any(s.fired > 0 for s in w.sams.values()) if "site" not in c else w.sams[c["site"]].fired > 0
    if t == "scrambled":
        return w.stats.sorties >= c.get("n", 1)
    if t == "flights_home":
        return bool(w.flights) and all(f.state in ("landed", "lost") for f in w.flights.values())
    raise ValueError(f"unknown condition type {t}")


def act(w: World, a: dict) -> None:
    k = a["do"]
    if k == "message":
        doctrine.send(w, a.get("channel", "tty"), a.get("sender", w.hq.name), a["text"], a.get("priority", 0),
                      a.get("ack", False), a.get("ref", ""), a.get("kind", "info"), a.get("delay", 0.0))
    elif k == "spawn":
        f = w.pending_flights.pop(a["flight"], None)
        if f is not None:
            spawn_flight(w, f)
    elif k == "set_var":
        w.vars[a["name"]] = float(a["value"])
    elif k == "add_var":
        w.vars[a["name"]] = w.vars.get(a["name"], 0.0) + float(a.get("value", 1))
    elif k == "radar_status":
        site = w.radars[a["site"]]
        site.status = a["status"]
        if a["status"] == "down":
            site.repair_t = w.t + a.get("minutes", 30.0) * 60.0
        if a["status"] == "degraded":
            site.degraded_db = a.get("db", 6.0)
        if a.get("alert", True):
            w.alert(a.get("text", f"{site.name}: {a['status'].upper()}"), site.id, 1)
    elif k == "link":
        ln = w.links[a["id"]]
        ln.up = a.get("up", False)
        ln.repair_t = w.t + a["minutes"] * 60.0 if not ln.up and "minutes" in a else -1.0
        if a.get("alert", True):
            w.alert(a.get("text", f"{ln.name} {'RESTORED' if ln.up else 'DOWN'}"), ln.id, 1)
    elif k == "duct":
        w.weather.duct_radars = list(a.get("radars", []))
        for sid in w.radars:
            w.radars[sid].k_override = a.get("k", 4.0) if sid in w.weather.duct_radars and a.get("on", True) else None
    elif k == "hq":
        for key in ("weapons_status", "alert", "readiness"):
            if key in a:
                setattr(w.hq, key, a[key])
        if "policy" in a:
            w.hq.policy.update(a["policy"])
        if "pressure" in a:
            w.hq.pressure = a["pressure"]
    elif k == "authorize":
        des = w.hq.policy.setdefault("designated", [])
        for aid in _truth_ids(w, a["ac"]):
            if aid not in des:
                des.append(aid)
        for aid in _truth_ids(w, a["ac"]):
            trk = w.track_for_truth(aid)
            if trk is not None and trk.id not in w.hq.engage_ok:
                w.hq.engage_ok.append(trk.id)
                w.set_identity(trk.id, "hostile", a.get("basis", "designated violator by higher command"),
                               authority=True)
    elif k == "transponder":
        for aid in _truth_ids(w, a["ac"]):
            tr = w.aircraft[aid].transponder
            for key in ("on", "failed"):
                if key in a:
                    setattr(tr, key, a[key])
            tr.codes.update(a.get("codes", {}))
    elif k == "jam":
        for aid in _truth_ids(w, a["ac"]):
            w.aircraft[aid].jamming = a.get("on", True)
    elif k == "sam_fault":
        w.sams[a["site"]].fault_t = w.t + a.get("seconds", 120.0)
    elif k == "computer_fail":
        w.fail_computer(a.get("side", ""))
    elif k == "objective":
        for o in w.objectives:
            if o.id == a["id"] and o.status == "open":
                o.status, o.t_status = a["status"], w.t
                if a.get("hidden") is not None:
                    o.hidden = a["hidden"]
    elif k == "reveal":
        for o in w.objectives:
            if o.id == a["id"]:
                o.hidden = False
    elif k == "remove":
        for aid in _truth_ids(w, a["ac"]):
            w.aircraft[aid].state = "gone"
    elif k == "end":
        end(w, a.get("reason", "Scenario ended"), a.get("result", "complete"))
    elif k == "weather":
        for key in ("ceiling_m", "visibility_km", "night", "k_factor", "sea_state"):
            if key in a:
                setattr(w.weather, key, a[key])
    else:
        raise ValueError(f"unknown action {k}")


def update(w: World) -> None:
    _spawn_due(w)
    for tr in w.triggers:
        if tr.fired and tr.once:
            continue
        if cond(w, tr.cond):
            tr.fired, tr.t_fired = True, w.t
            for a in tr.actions:
                act(w, a)
            if not tr.once:
                tr.fired = False


# ---------------------------------------------------------------- objectives

END_PASS = {"not_destroyed", "no_civil_losses", "no_fratricide", "keep_out", "no_alert", "keep_ready", "max_in_zone",
            "own_keep_out",
            "max_missiles"}


def _set(w: World, o: Objective, status: str) -> None:
    if o.status != status:
        o.status, o.t_status = status, w.t
        if not o.hidden:
            msg = ("OBJECTIVE COMPLETE: " if status == "done" else "OBJECTIVE FAILED: ") + o.text
            doctrine.send(w, "system", "EVALUATION", msg, 1 if status == "failed" else 0, False, o.id, "objective")
        w.log_event("result", f"Objective {o.id} {status}: {o.text}", o.id)


def evaluate_objectives(w: World, final: bool = False) -> None:
    for o in w.objectives:
        if o.status != "open":
            continue
        p = o.params
        k = o.kind
        if k == "identify":
            for aid in _truth_ids(w, p["ac"]):
                trk = w.track_for_truth(aid)
                ref = w.stats.adiz.get(aid, w.stats.first_track.get(aid)) if p.get("from", "adiz") == "adiz" \
                    else w.stats.first_track.get(aid)
                if trk is not None and trk.identity in p["correct"]:
                    if ref is None or w.t - ref <= p.get("within_s", 1e9) or not p.get("strict_time", False):
                        _set(w, o, "done")
                elif trk is not None and trk.identity in p.get("wrong", []):
                    _set(w, o, "failed")
                elif ref is not None and p.get("strict_time", False) and w.t - ref > p.get("within_s", 1e9):
                    _set(w, o, "failed")
        elif k == "vid":
            if any(a in w.stats.vid for a in _truth_ids(w, p["ac"])):
                _set(w, o, "done")
            elif cond(w, {"type": "gone", "ac": p["ac"]}) and _truth_ids(w, p["ac"]):
                _set(w, o, "failed")
        elif k == "destroy":
            if cond(w, {"type": "destroyed", "ac": p["ac"]}):
                _set(w, o, "done")
            elif _truth_ids(w, p["ac"]) and (cond(w, {"type": "gone", "ac": p["ac"]}) or
                                             ("zone" in p and cond(w, {"type": "in_zone", "ac": p["ac"],
                                                                        "zone": p["zone"]}))):
                _set(w, o, "failed")
        elif k == "not_destroyed":
            if cond(w, {"type": "destroyed", "ac": p["ac"]}):
                _set(w, o, "failed")
        elif k == "no_civil_losses":
            if w.vars.get("civil_losses", 0) > 0:
                _set(w, o, "failed")
        elif k == "no_fratricide":
            if w.vars.get("fratricide", 0) > 0:
                _set(w, o, "failed")
        elif k == "keep_out":
            if _truth_ids(w, p["ac"]) and cond(w, {"type": "in_zone", "ac": p["ac"], "zone": p["zone"]}):
                if not p.get("unless_vid") or not any(a in w.stats.vid for a in _truth_ids(w, p["ac"])):
                    _set(w, o, "failed")
        elif k == "no_alert":
            if w.hq.alert == p["level"] and w.vars.get(p.get("unless_var", "_"), 0.0) <= 0:
                _set(w, o, "failed")
        elif k == "report":
            for aid in _truth_ids(w, p["ac"]):
                trk = w.track_for_truth(aid)
                t0 = w.stats.first_track.get(aid)
                if trk is not None and trk.reported:
                    _set(w, o, "done" if t0 is None or w.t - t0 <= p.get("within_s", 1e9) else "failed")
                elif t0 is not None and w.t - t0 > p.get("within_s", 1e9):
                    _set(w, o, "failed")
        elif k == "var":
            if cond(w, {"type": "var", **{kk: p[kk] for kk in ("name", "op", "value")}}):
                _set(w, o, "done")
        elif k == "forced_down":
            ids = _truth_ids(w, p["ac"])
            if any(fd[0] in ids and (not p.get("base") or fd[1] == p["base"]) for fd in w.stats.forced):
                _set(w, o, "done")
            elif ids and (cond(w, {"type": "destroyed", "ac": p["ac"]}) or cond(w, {"type": "gone", "ac": p["ac"]})):
                _set(w, o, "failed")
        elif k == "tracked_before_zone":
            ids = _truth_ids(w, p["ac"])
            if any(a in w.stats.first_track for a in ids):
                _set(w, o, "done")
            elif ids and cond(w, {"type": "in_zone", "ac": p["ac"], "zone": p["zone"]}):
                _set(w, o, "failed")
        elif k == "own_keep_out":
            for fl in w.flights.values():
                for mid in fl.members:
                    a = w.aircraft.get(mid)
                    if a is not None and a.state == "airborne" and ident.zone_contains(w, p["zone"], a.x, a.y):
                        _set(w, o, "failed")
                        break
        elif k == "sim_kills":
            if w.vars.get("sim_kills", 0.0) >= p.get("min", 1):
                _set(w, o, "done")
        elif k == "locked":
            if any(a in w.stats.locks for a in _truth_ids(w, p["ac"])):
                _set(w, o, "done")
            elif cond(w, {"type": "gone", "ac": p["ac"]}) and _truth_ids(w, p["ac"]):
                _set(w, o, "failed")
        elif k == "destroy_count":
            ids = [a for pref in p["ac"] for a in _truth_ids(w, pref)]
            n = sum(1 for a in ids if w.aircraft[a].state == "destroyed" or w.sim_killed(a))
            if n >= p.get("min", 1):
                _set(w, o, "done")
        elif k == "max_in_zone":
            ids = [a for pref in p["ac"] for a in _truth_ids(w, pref)]
            inside = sum(1 for a in ids if w.vars.get(f"inzone_{a}", 0.0) > 0)
            for a in ids:
                ac = w.aircraft[a]
                if ac.state == "airborne" and not w.sim_killed(a) and ident.zone_contains(w, p["zone"], ac.x, ac.y):
                    w.vars[f"inzone_{a}"] = 1.0
            if inside > p.get("max", 0):
                _set(w, o, "failed")
        elif k == "max_missiles":
            if w.stats.missiles > p.get("max", 9):
                _set(w, o, "failed")
        elif k == "keep_ready":
            if final:
                ready = sum(sum(q.ready.values()) for q in w.squadrons.values())
                _set(w, o, "done" if ready >= p.get("min", 2) else "failed")
            continue
        if final and o.status == "open":
            _set(w, o, "done" if k in END_PASS else "failed")


def end(w: World, reason: str, result: str = "complete") -> None:
    if w.ended:
        return
    evaluate_objectives(w, final=True)
    w.ended = True
    w.end_reason = reason
    w.result = result
    w.log_event("sys", f"Scenario ended: {reason}")


def score(w: World) -> tuple[int, int, str]:
    got = sum(o.points for o in w.objectives if o.status == "done")
    pen = sum(o.penalty for o in w.objectives if o.status == "failed")
    total = sum(o.points for o in w.objectives) or 1
    pct = (got - pen) / total
    if w.faction == "USSR":
        grade = "5 — EXCELLENT" if pct >= 0.85 else "4 — GOOD" if pct >= 0.7 else \
            "3 — SATISFACTORY" if pct >= 0.5 else "2 — UNSATISFACTORY"
    else:
        grade = "OUTSTANDING" if pct >= 0.9 else "EXCELLENT" if pct >= 0.75 else "SATISFACTORY" if pct >= 0.55 \
            else "MARGINAL" if pct >= 0.35 else "UNSATISFACTORY"
    return got - pen, total, grade
