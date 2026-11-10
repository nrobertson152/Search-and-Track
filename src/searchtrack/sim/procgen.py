"""Procedural "Alert Duty" watches.

A generated watch borrows the order of battle of a historical scenario (its
radars, lines, airfields, squadrons, missile units and command rules) and
builds everything else fresh from a seed: time of day, weather, civil traffic
and three to five incidents drawn from a library suited to the faction and
the era. Threat entry points are taken from where the historical scenario's
own intruders came from, so every sector keeps its geography of danger."""
from __future__ import annotations

import copy
import math
import random
from typing import Any

from .scenario import list_scenarios, load_scenario
from .world import catalog, theater

# era-appropriate foreign aircraft for each side's incidents
INTRUDERS = {
    "US": {1950: ["Tu-95M", "Tu-16"], 1960: ["Tu-95M", "Tu-16"], 1970: ["Tu-95M", "Tu-16"], 1980: ["Tu-95MS", "Tu-95M"]},
    "USSR": {1950: ["B-47E", "RC-135V"], 1960: ["RC-135V", "B-47E", "U-2C"], 1970: ["RC-135V", "P-3C"],
             1980: ["RC-135V", "P-3C", "SR-71A"]},
}
LIGHT = ["C172"]
INCIDENTS = ["probe", "straggler", "lost_light", "intruder", "equipment", "line", "probe", "straggler"]


def bases_for(faction: str) -> list[dict[str, Any]]:
    """Historical scenarios whose forces can host an alert duty watch."""
    return [s for s in list_scenarios() if s["faction"] == faction and s["kind"] == "scenario"]


def _era(year: int) -> int:
    return 1950 if year < 1960 else 1960 if year < 1970 else 1970 if year < 1980 else 1980


def _latlon_of(th, x: float, y: float) -> tuple[float, float]:
    return th.proj.inverse(x, y)


def generate(base_id: str, seed: int, difficulty: int = 2) -> dict[str, Any]:
    base = load_scenario(base_id)
    rng = random.Random(seed)
    th = theater(base["theater"])
    cat = catalog()
    faction = base["faction"]
    year = int(base.get("start", "1962")[:4])
    era = _era(year)
    night = rng.random() < 0.5
    hour = rng.choice([1, 3, 22, 23]) if night else rng.choice([9, 11, 13, 15])
    date = base.get("start", "1962-10-24T00:00:00")[:10]
    sc: dict[str, Any] = {
        "id": f"alert_{base_id}_{seed}", "title": "Alert Duty",
        "subtitle": f"{th.name.split('—')[-1].strip()} · watch no. {seed % 10000:04d}",
        "summary": "A generated watch on a historical order of battle.",
        "faction": faction, "kind": "alert", "theater": base["theater"],
        "start": f"{date}T{hour:02d}:{rng.randint(0, 59):02d}:00", "tz": base.get("tz", "Z"),
        "duration_min": 90 + 15 * difficulty, "seed": seed, "reliability": base.get("reliability", 3.0) * (1.4 - 0.15 * difficulty),
        "sun_offset_h": base.get("sun_offset_h", 0.0),
    }
    for key in ("automation", "link", "radar", "airbase", "squadron", "sam", "faction_override", "photo", "era"):
        if key in base:
            sc[key] = copy.deepcopy(base[key])
    hq = copy.deepcopy(base.get("hq", {}))
    pol = hq.setdefault("policy", {})
    pol.update({"declare_hostile": "evidence", "engage": "deny", "ram": "deny", "special_release": "deny"})
    for k in list(pol):
        if k.startswith(("weapons_status_", "alert_")):
            pol[k] = "deny"
    hq["weapons_status"] = "HOLD"
    sc["hq"] = hq
    # weather
    sc["weather"] = {"k_factor": rng.choice([1.333, 1.333, 1.333, 1.6]), "wind_from": rng.uniform(0, 360),
                     "wind_kmh": rng.uniform(20, 110), "ceiling_m": rng.choice([600.0, 1500.0, 3000.0, 6000.0]),
                     "visibility_km": rng.choice([5.0, 15.0, 30.0]), "night": night, "sea_state": rng.uniform(1, 5)}
    ex = th.cfg["projection"]["extent_km"]
    cells = []
    for _ in range(rng.randint(0, 3)):
        lat, lon = _latlon_of(th, rng.uniform(ex[0], ex[1]) * 0.8, rng.uniform(ex[2], ex[3]) * 0.8)
        cells.append({"lat": lat, "lon": lon, "r_km": rng.uniform(15, 40), "intensity": rng.uniform(0.3, 0.8),
                      "move_kmh": rng.uniform(10, 40), "move_to": rng.uniform(0, 360)})
    sc["weather"]["cells"] = cells
    # civil traffic between the theater's larger cities
    cities = [c for c in th.cfg.get("city", []) if c.get("size", 1) >= 2]
    own_cities = cities[:]
    if len(cities) >= 2:
        pairs = []
        for i, a in enumerate(cities):
            near = sorted(cities, key=lambda c: (c["lat"] - a["lat"]) ** 2 + (c["lon"] - a["lon"]) ** 2)[1:3]
            pairs += [[a["name"], b["name"]] for b in near]
        sc["traffic"] = [{"count": 6 + 2 * difficulty, "routes": pairs, "t_window": [0.0, sc["duration_min"] * 48.0],
                          "off_plan": 0.08 + 0.04 * difficulty, "transponder": "atc" if faction == "US" else "none",
                          "plans": faction == "US"}]
    # entry points: where the historical intruders came from
    entries = []
    for f in base.get("flight", []):
        if f.get("side") in ("red", "neutral") and "start" in f and f.get("kind", "aircraft") == "aircraft":
            entries.append((f["start"]["lat"], f["start"]["lon"]))
    if not entries:
        entries = [_latlon_of(th, ex[0] * 0.95, rng.uniform(ex[2], ex[3]) * 0.5)]
    own_bases = [b for b in th.cfg.get("airbase", []) if b.get("kind") == "military" and
                 any(a.get("site") == b["id"] for a in base.get("airbase", []))]
    targets = own_bases + own_cities
    flights, triggers, objectives = [], [], []
    tz_zone = next((z["id"] for z in th.cfg.get("zone", []) if z.get("kind") == "territory"), None)
    foreign_zone = next((z["id"] for z in th.cfg.get("zone", []) if z.get("kind") == "foreign"), None)
    n_inc = 3 + (difficulty >= 2) + (difficulty >= 3)
    kinds = rng.sample(INCIDENTS, k=min(n_inc, len(INCIDENTS)))
    t_slot = sc["duration_min"] * 60.0 / (n_inc + 1)
    for i, kind in enumerate(kinds):
        t0 = t_slot * (i + 0.5) + rng.uniform(-300, 300)
        fid = f"inc{i + 1}"
        if kind == "probe":
            lat, lon = rng.choice(entries)
            lat += rng.uniform(-0.5, 0.5)
            lon += rng.uniform(-0.8, 0.8)
            tgt = rng.choice(targets) if targets else {"lat": th.cfg["projection"]["lat0"], "lon": th.cfg["projection"]["lon0"]}
            typ = rng.choice([t for t in INTRUDERS[faction][era] if t in cat.aircraft])
            at = cat.aircraft[typ]
            # approach two thirds of the way, then turn back out
            mlat, mlon = lat + (tgt["lat"] - lat) * 0.6, lon + (tgt["lon"] - lon) * 0.6
            alt = min(at.cruise_alt_m, at.ceiling_m * 0.9)
            flights.append({"id": fid, "type": typ, "callsign": "PROBE", "side": "red", "spawn_t": max(60.0, t0),
                            "truth_label": at.name, "markings": "foreign military markings",
                            "nationality": "USSR" if faction == "US" else "US", "on_intercept": "turn_away",
                            "start": {"lat": lat, "lon": lon, "alt_m": alt, "kmh": at.cruise_kmh},
                            "route": [{"lat": mlat, "lon": mlon, "alt_m": alt, "kmh": at.cruise_kmh},
                                      {"lat": lat, "lon": lon, "alt_m": alt, "kmh": at.cruise_kmh, "action": "remove"}],
                            "transponder": {"system": "kremniy" if faction == "US" else "sif",
                                            "codes": {"period": "X"} if faction == "US" else {"3": "4100"}}})
            objectives.append({"id": f"{fid}_vid", "text": f"Intercept and visually identify the probing {typ}",
                               "kind": "vid", "params": {"ac": fid}, "points": 20})
            objectives.append({"id": f"{fid}_alive", "text": "Peacetime: do not engage the probe",
                               "kind": "not_destroyed", "params": {"ac": fid}, "points": 5, "penalty": 40})
        elif kind == "straggler" and len(cities) >= 2:
            a, b = rng.sample(cities, 2)
            typ = rng.choice([t for t in ("DC-7C", "B707", "Il-18", "Tu-104", "Tu-134", "L-1049", "DC-10")
                              if t in cat.aircraft and ((faction == "US") == (cat.aircraft[t].nation != "USSR"))]
                             or ["B707"])
            at = cat.aircraft[typ]
            alt = at.cruise_alt_m * 0.8
            code = f"{rng.randint(1, 7)}{rng.randint(0, 7)}{rng.randint(0, 7)}{rng.randint(0, 7)}"
            f = {"id": fid, "type": typ, "callsign": "STRAGGLER" if faction == "US" else "AEROFLOT", "side": "civil",
                 "spawn_t": max(60.0, t0), "truth_label": f"{at.name} (off its flight plan)",
                 "markings": "civil airliner",
                 "start": {"lat": a["lat"], "lon": a["lon"], "alt_m": alt, "kmh": at.cruise_kmh},
                 "route": [{"lat": b["lat"], "lon": b["lon"], "alt_m": 900.0, "kmh": at.cruise_kmh * 0.7,
                            "action": "land"}]}
            if faction == "US":
                f["transponder"] = {"system": "atc", "codes": {"3": code}}
                f["flight_plan"] = {"kind": "IFR", "mode3": code, "delay_min": rng.choice([-1, 1]) * rng.uniform(7, 15)}
            else:
                f["transponder"] = {"system": "none"}
            flights.append(f)
            objectives.append({"id": f"{fid}_id", "text": f"Identify the straggling {typ} correctly",
                               "kind": "identify", "params": {"ac": fid, "correct": ["friend"],
                                                              "wrong": ["suspect", "hostile"], "from": "track"},
                               "points": 15})
        elif kind == "lost_light" and targets:
            tgt = rng.choice(targets)
            lat, lon = tgt["lat"] + rng.uniform(-1.2, 1.2), tgt["lon"] + rng.uniform(-1.8, 1.8)
            flights.append({"id": fid, "type": "C172", "callsign": "LIGHT", "side": "civil", "spawn_t": max(60.0, t0),
                            "truth_label": "light aircraft, lost, no flight plan", "markings": "civil registration",
                            "fuel_frac": 2.0, "on_signal": f"comply:{own_bases[0]['id']}" if own_bases else "comply",
                            "start": {"lat": lat, "lon": lon, "alt_m": 600.0, "kmh": 190.0},
                            "route": [{"lat": tgt["lat"], "lon": tgt["lon"], "alt_m": 300.0, "kmh": 180.0,
                                       "action": "land"}],
                            "transponder": {"system": "none"}})
            objectives.append({"id": f"{fid}_vid", "text": "Visually identify the low, slow unknown",
                               "kind": "vid", "params": {"ac": fid}, "points": 15})
            objectives.append({"id": f"{fid}_alive", "text": "Do not fire on the lost light aircraft",
                               "kind": "not_destroyed", "params": {"ac": fid}, "points": 5, "penalty": 40})
        elif kind == "intruder" and targets:
            lat, lon = rng.choice(entries)
            tgt = rng.choice(own_bases or targets)
            typ = "MiG-17F" if faction == "US" and "MiG-17F" in cat.aircraft else "C172"
            if faction == "USSR":
                typ = rng.choice([t for t in ("C172", "B707") if t in cat.aircraft])
            at = cat.aircraft[typ]
            low = 150.0 if at.role != "airliner" else at.cruise_alt_m * 0.9
            flights.append({"id": fid, "type": typ, "callsign": "INTRUDER", "side": "civil" if at.role in ("light", "airliner")
                            else "neutral", "spawn_t": max(60.0, t0), "truth_label": f"{at.name} (unauthorized flight)",
                            "markings": "foreign markings", "fuel_frac": 2.0, "on_intercept": "comply",
                            "on_signal": f"comply:{(own_bases or [{'id': ''}])[0]['id']}",
                            "start": {"lat": lat + rng.uniform(-0.3, 0.3), "lon": lon + rng.uniform(-0.3, 0.3),
                                      "alt_m": low, "kmh": at.cruise_kmh},
                            "route": [{"lat": tgt["lat"], "lon": tgt["lon"], "alt_m": low, "kmh": at.cruise_kmh,
                                       "action": "land"}],
                            "transponder": {"system": "none"}})
            if tz_zone:
                objectives.append({"id": f"{fid}_trk", "text": "Track the intruder before it reaches the coast or border",
                                   "kind": "tracked_before_zone", "params": {"ac": fid, "zone": tz_zone}, "points": 15})
            objectives.append({"id": f"{fid}_vid", "text": "Identify the intruder visually", "kind": "vid",
                               "params": {"ac": fid}, "points": 15})
            objectives.append({"id": f"{fid}_alive", "text": "Do not destroy the intruder without authority",
                               "kind": "not_destroyed", "params": {"ac": fid}, "points": 5, "penalty": 30})
        elif kind == "equipment" and base.get("radar"):
            r = rng.choice([r for r in base["radar"] if "site" in r] or base["radar"])
            if "site" in r:
                triggers.append({"id": f"{fid}_fail", "cond": {"type": "time", "t": max(300.0, t0)},
                                 "actions": [{"do": "radar_status", "site": r["site"], "status": "down",
                                              "minutes": rng.uniform(15, 45),
                                              "text": "RADAR FAILURE — TRANSMITTER OFF THE AIR, TECHNICIANS DISPATCHED"}]})
        elif kind == "line" and base.get("link"):
            ln = rng.choice(base["link"])
            triggers.append({"id": f"{fid}_line", "cond": {"type": "time", "t": max(300.0, t0)},
                             "actions": [{"do": "link", "id": ln["id"], "up": False, "minutes": rng.uniform(10, 35),
                                          "text": f"{ln.get('name', ln['id']).upper()} DOWN"}]})
    triggers.insert(0, {"id": "open", "cond": {"type": "time", "t": 5.0},
                        "actions": [{"do": "message", "channel": "tty", "sender": hq.get("name", "HQ"), "ack": True,
                                     "kind": "order", "text": "ROUTINE ALERT DUTY. PEACETIME RULES. IDENTIFY EVERY "
                                     "TRACK, REPORT VIOLATIONS, HOLD FIRE UNLESS AUTHORIZED."}]})
    objectives += [{"id": "civil", "text": "No civil losses", "kind": "no_civil_losses", "points": 10, "penalty": 30},
                   {"id": "fratricide", "text": "No fratricide", "kind": "no_fratricide", "points": 5, "penalty": 30},
                   {"id": "ready", "text": "Hand over at least two interceptors on alert", "kind": "keep_ready",
                    "params": {"min": 2}, "points": 5}]
    sc["flight"] = flights
    sc["trigger"] = triggers
    sc["objective"] = objectives
    phrases = {"probe": "foreign reconnaissance probing the border", "straggler": "airliners off their flight plans",
               "lost_light": "a lost light aircraft", "intruder": "an unauthorized low-level flight"}
    kinds_txt = ", ".join(sorted({phrases[k] for k in kinds if k in phrases}))
    sc["briefing"] = (f"ALERT DUTY — {th.name.upper()}\n\nA routine watch on the {year} order of battle. "
                      f"{'Night' if night else 'Day'} shift; ceiling {sc['weather']['ceiling_m']:.0f} m, "
                      f"visibility {sc['weather']['visibility_km']:.0f} km, wind {sc['weather']['wind_kmh']:.0f} km/h "
                      f"from {sc['weather']['wind_from']:03.0f}°.\n\nPEACETIME RULES. Weapons HOLD. Identify every "
                      f"track. Report violations to higher command. Expect equipment trouble.\n\nThe intelligence "
                      f"summary mentions possible {kinds_txt or 'routine traffic'}.")
    sc["summary"] = sc["briefing"].split("\n\n")[1]
    return sc
