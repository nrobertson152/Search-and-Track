"""Operator consoles. Every control issues a simulation Command or changes a
display setting; every number shown is read from the simulation."""
from __future__ import annotations

import math

import numpy as np
import pygame

from ..sim import coverage, doctrine, gci, ident, tracking
from ..sim.geo import FT, NM, bearing_deg
from ..sim.radar import predict_coverage, snr_for_pd
from .mapview import clock, fmt_alt, fmt_rng, fmt_spd
from .theme import TEXT

R = pygame.Rect

TECH_NOTES = """RADAR RANGE EQUATION
Received echo power falls with the fourth power of range: double the distance and the signal drops 12 dB. The game computes signal-to-noise from transmitter power, antenna gain, wavelength, the target's radar cross-section for its current aspect, and receiver noise. A calibration loss anchors each radar to its documented detection range.

INTEGRATION AND SCAN RATE
While the beam sweeps across a target it collects several pulses (PRF × beamwidth ÷ rotation rate). Faster rotation gives more frequent updates but fewer pulses per look, so less signal.

FLUCTUATION (SWERLING I)
A real aircraft's echo flickers from scan to scan as its aspect changes. Near maximum range a target may paint on one sweep and vanish on the next.

THRESHOLD
The operator's detection threshold trades sensitivity against false alarms. Pfa 1e-4 finds weaker targets but fills the scope with noise and false plots; 1e-8 is clean but deaf.

RADAR HORIZON
Microwaves travel in nearly straight lines, bent slightly by the atmosphere (the 4/3-Earth model). A radar 100 m up sees a target at 300 m only out to about 110 km, however powerful it is. Low flyers hide below the horizon.

TERRAIN MASKING
Mountains cast radar shadows. Each site's horizon profile is computed from real terrain (ETOPO1, 10 arc-minute).

LOBING (VHF RADARS)
Long-wavelength radars receive the direct echo and one reflected off the ground. The two interfere, forming lobes with gaps between them, and coverage is poor at very low angles.

CLUTTER AND MTI
Ground and sea echoes swamp targets at short range. Moving Target Indication cancels stationary echoes, but also cancels targets with no radial speed (flying across the beam: the "tangential notch") and targets at blind speeds, multiples of λ·PRF/2.

JAMMING
A noise jammer in the main beam paints a bright strobe along its bearing. Targets on that bearing are masked until "burn-through" at close range. Strobes from two radars can be crossed to locate the jammer. Spot jammers can be escaped by changing frequency channel.

HEIGHT
Search radars measure range and bearing only. US sites use nodding height finders, which are accurate but serve one track at a time. Soviet V-beam radars estimate altitude on every scan, but coarsely.
"""


def _ident_color(scene, ident_):
    return scene.theme.id_colors.get(ident_, scene.theme.text)


class Console:
    name = ""
    key = ""

    def draw(self, gui, r: R, scene) -> None:  # pragma: no cover - interface
        raise NotImplementedError


# ====================================================================== TRACKS
class TracksConsole(Console):
    name = "TRACKS"

    def __init__(self):
        self.merge_from = ""

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "SURVEILLANCE & IDENTIFICATION", "track console")
        tracks = sorted(w.tracks.values(), key=lambda t: (t.lost, {"hostile": 0, "suspect": 1, "unknown": 2,
                                                                  "pending": 3}.get(t.identity, 5), t.id))
        cols = [("TRK", 56), ("IDENT", 104), ("ALT", 52), ("SPD", 62), ("HDG", 40), ("Q", 22), ("IFF", 82),
                ("AGE", 46), ("NOTE", 120)]
        rows, colors = [], []
        sel_i = -1
        for i, t in enumerate(tracks):
            if t.id == scene.sel.get("track"):
                sel_i = i
            verdict, _ = ident.iff_assessment(w, t)
            iff = ",".join(f"{k}:{v}" for k, v in t.iff.items()) if (t.iff and w.t - t.iff_t < 180) else "—"
            note = ("JAM " if t.jammer else "") + t.note + (" LOST" if t.lost else "")
            rows.append([t.id, doctrine.id_label(w, t.identity), fmt_alt(th, t.alt), fmt_spd(th, math.hypot(t.vx, t.vy)),
                         f"{bearing_deg(t.vx, t.vy):03.0f}", str(t.quality), iff, f"{(w.t - t.t_update):.0f}s", note])
            colors.append(_ident_color(scene, t.identity) if not t.lost else th.text_dim)
        hit = gui.table("tracks", R(inner.x, inner.y, inner.w, 250), cols, rows, sel_i, colors)
        if hit is not None:
            scene.select("track", tracks[hit].id)
        y = inner.y + 258
        trk = w.tracks.get(scene.sel.get("track") or "")
        if trk is None:
            gui.wrapped(R(inner.x, y, inner.w, 120),
                        "Select a track on the display or in the list.\n\n"
                        + ("Light gun: click a return on the situation display or the scope, then INITIATE (I)." if us else
                           "Targets are entered automatically from radar-company reports."), 12, th.engraving_dim)
            if us and gui.button(R(inner.x, y + 90, 170, 26), "INITIATE TRACK (I)", tip="Initiate a track on the "
                                 "unassociated returns at the light-gun position."):
                scene.initiate()
            return
        rec, basis = ident.recommend(w, trk)
        hdr = R(inner.x, y, inner.w, 24)
        gui.glass(hdr, bezel=False)
        gui.label((hdr.x + 8, hdr.y + 1), f"{trk.id}", 18, _ident_color(scene, trk.identity), "ui_bold")
        gui.crt((hdr.x + 92, hdr.y + 4), f"{doctrine.id_label(w, trk.identity)}   recommended: "
                f"{doctrine.id_label(w, rec)}", 13)
        gui.crt_overlay(hdr, strength=0.5)
        y += 32
        bw = (inner.w - 10) // 6
        for i, idn in enumerate(["friend", "unknown", "suspect", "hostile", "faker", "pending"]):
            label = doctrine.id_label(w, idn)
            tip = {"hostile": "Requires higher authority unless weapons are FREE. Use REQUEST HOSTILE.",
                   "suspect": "Foreign military aircraft not (yet) declared hostile.",
                   "faker": "Exercise aircraft simulating a hostile."}.get(idn)
            if gui.button(R(inner.x + i * (bw + 2), y, bw, 24), label, lit=trk.identity == idn,
                          color=_ident_color(scene, idn), tip=tip, size=11):
                scene.cmd("identity", track=trk.id, ident=idn)
        y += 30
        acts = [("HEIGHT (H)", "height", "Queue on the nearest free height finder (priority).") if w.hfs else None,
                ("REPORT", "report", "Pass this track to higher HQ."),
                ("DROP", "drop", "Drop the track (use for false or phantom returns)."),
                ("MERGE", "merge", "Merge two tracks: press MERGE on the first, select the second, press MERGE again."),
                ("CENTER", "center", "Center the situation display on this track.")]
        acts = [a for a in acts if a]
        bw = (inner.w - 8) // len(acts)
        for i, (lab, kind, tip) in enumerate(acts):
            lit = kind == "merge" and bool(self.merge_from)
            if gui.button(R(inner.x + i * (bw + 2), y, bw, 24), lab, lit=lit, tip=tip, size=11):
                if kind == "height":
                    scene.cmd("height", track=trk.id)
                elif kind == "report":
                    scene.cmd("report", track=trk.id)
                elif kind == "drop":
                    scene.cmd("drop_track", track=trk.id)
                elif kind == "center":
                    scene.map.center_on(*tracking.predicted(trk, w.t))
                elif kind == "merge":
                    if self.merge_from and self.merge_from != trk.id:
                        scene.cmd("merge", track=self.merge_from, into=trk.id)
                        self.merge_from = ""
                    else:
                        self.merge_from = trk.id
                        scene.toast(f"Merge: now select the track to merge {trk.id} into")
        y += 32
        # evidence
        verdict, iff_txt = ident.iff_assessment(w, trk)
        lines = [(f"IFF/SIF: {iff_txt}", th.text)]
        if us:
            for m in ident.correlate(w, trk)[:3]:
                ok = "WITHIN" if m.within else "outside"
                lines.append((f"  plan {m.callsign:<16} dT {m.dt_min:+5.1f} min  {m.dist_nm:5.1f} nm  "
                              f"(±5 min/{m.tol_nm:.0f} nm) {ok}{' SIF✓' if m.code_ok else ''}",
                              th.ok if m.within else th.text_dim))
            if not any(True for _ in ident.correlate(w, trk)[:1]):
                lines.append(("  no flight plan within 3× tolerance", th.text_dim))
        vid = w.vid_reports.get(trk.id)
        if vid:
            lines.append((f"VISUAL: {vid[1]}", th.accent))
        lines.append((f"Basis of current ID: {trk.id_basis or '—'}", th.text_dim))
        alt_age = f"{(w.t - trk.alt_t) / 60:.0f} min" if trk.alt_t >= 0 else "—"
        src = {"HF": "height finder", "VB": "V-beam estimate", "VID": "pilot report", "MODEC": "Mode C"}.get(trk.alt_src, "none")
        lines.append((f"Altitude {fmt_alt(th, trk.alt, False)} ({src}, {alt_age} old)"
                      f"{'  HF queued' if trk.hf_requested else ''}{f'  {trk.alt_fails} height failures' if trk.alt_fails else ''}",
                      th.text))
        last = f"last data {clock(w, trk.t_update)} ({(w.t - trk.t_update) / 60:.1f} min ago)"
        srcs = sorted(trk.sources, key=lambda k: -trk.sources[k])
        names = [w.radars[k].name.replace("Radar company ", "").replace(" guidance point", " GP")
                 if k in w.radars else k for k in srcs]
        src_txt = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
        lines.append((f"Data: {last}; {len(srcs)} radar(s): {src_txt}; raid size {trk.size}", th.text))
        if trk.adiz_t >= 0:
            lines.append((f"ADIZ penetration {clock(w, trk.adiz_t)}", th.accent))
        gui.readout(R(inner.x, y, inner.w, len(lines) * 16 + 8), lines)
        y += len(lines) * 16 + 16
        # coverage analysis
        gui.eng((inner.x, y), "COVERAGE ANALYSIS", 12)
        gui.label((inner.x + inner.w - 2, y + 2), "predicted detectability at the track's estimated position", 10,
                  th.engraving_dim, "eng_r", "right")
        y += 22
        px, py = tracking.predicted(trk, w.t)
        alt = trk.alt if trk.alt is not None else 6000.0
        rows = []
        for s in w.radars.values():
            bd = predict_coverage(w, s, px, py, alt, trk.vx * 1000, trk.vy * 1000, "B707" if trk.size else "B707")
            if bd.limit == "range":
                continue
            rows.append((bd.pd, [s.name[:22], fmt_rng(th, bd.ground_km), f"{bd.pd:4.2f}", f"{bd.sinr_db:5.1f}",
                                 bd.explain()]))
        rows.sort(key=lambda r: -r[0])
        hit = gui.table("cov", R(inner.x, y, inner.w, max(60, inner.bottom - y)),
                        [("RADAR", 160), ("RANGE", 66), ("Pd", 44), ("SINR", 50), ("LIMIT / REASON", 250)],
                        [r[1] for r in rows[:12]], -1, size=11, row_h=16)
        gui.tip(R(inner.x, y, inner.w, 20), "Assumes an airliner-sized target at the track's altitude "
                "(6,000 m if unknown). Clutter and jamming are evaluated at the current instant.")


# ====================================================================== WEAPONS
class WeaponsConsole(Console):
    name = "WEAPONS"

    def __init__(self):
        self.n = 2
        self.task = "id"
        self.geom = "lead"
        self.sq = ""

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "WEAPONS DIRECTION", "interceptors")
        sqs = list(w.squadrons.values())
        rows = []
        for q in sqs:
            alert = " ".join(f"{k}m:{v}" for k, v in sorted(q.ready.items(), key=lambda kv: float(kv[0])) if v) or "—"
            rows.append([q.name, w.airbases[q.base_id].name, q.type_id, alert, str(q.airborne), str(q.pilots),
                         str(len(q.recovering))])
        sel_i = next((i for i, q in enumerate(sqs) if q.id == self.sq), 0)
        if sqs and not self.sq:
            self.sq = sqs[0].id
        hit = gui.table("sq", R(inner.x, inner.y, inner.w, 104),
                        [("SQUADRON", 130), ("BASE", 120), ("TYPE", 72), ("ALERT (min:acft)", 132), ("AIR", 34),
                         ("PLT", 34), ("RCV", 34)], rows, sel_i)
        if hit is not None:
            self.sq = sqs[hit].id
        y = inner.y + 110
        tsel = scene.sel.get("track") or ""
        x = inner.x
        for n in (1, 2):
            if gui.button(R(x, y, 34, 24), f"×{n}", lit=self.n == n, tip="Number of aircraft to launch"):
                self.n = n
            x += 36
        x += 4
        tasks = [("intercept", "INTERCEPT"), ("id", "ID PASS"), ("shadow", "SHADOW"), ("cap", "CAP")]
        for k, lab in tasks:
            tip = {"intercept": "Commit to attack geometry (weapons still need clearance).",
                   "id": "Stern approach for a visual identification pass.",
                   "shadow": "Identify and follow.", "cap": "Orbit over a point."}[k]
            if gui.button(R(x, y, 74, 24), lab, lit=self.task == k, tip=tip, size=10):
                self.task = k
            x += 76
        x += 4
        for k, lab in (("lead", "LEAD"), ("stern", "STERN"), ("pursuit", "PURSUIT")):
            tip = {"lead": "Lead-collision course: fastest intercept, head-on/beam attack.",
                   "stern": "Stern conversion: roll out behind the target (rear-aspect weapons).",
                   "pursuit": "Point at the target: simple, slow, burns fuel."}[k]
            if gui.button(R(x, y, 60, 24), lab, lit=self.geom == k, tip=tip, size=10):
                self.geom = k
            x += 62
        y += 30
        lab = f"SCRAMBLE ON {tsel}" if tsel else "SCRAMBLE (NO TARGET)"
        if gui.button(R(inner.x, y, 220, 26), lab, color=th.lamp_red, tip="Order the squadron's alert aircraft "
                      "airborne. Delay depends on alert state (5-minute alert ≈ 3-4 min)."):
            if scene.cmd("scramble", squadron=self.sq, n=self.n, task=self.task, track=tsel, geometry=self.geom)[0]:
                scene.audio.play("klaxon")
        q = w.squadrons.get(self.sq)
        if q is not None:
            fastest = min((float(k) for k, v in q.ready.items() if v), default=None)
            bucket = sorted({float(k) for k in q.ready})
            target_b = next((b for b in bucket if fastest is not None and b < fastest), bucket[0] if bucket else 5.0)
            if gui.button(R(inner.x + 226, y, 170, 26), "RAISE ALERT +1",
                          tip=f"Bring one aircraft up to {bucket[0] if bucket else 5:g}-minute alert (takes time, tires crews)."):
                scene.cmd("readiness", squadron=q.id, bucket=bucket[0] if bucket else 5.0, n=1)
        y += 34
        fls = [f for f in w.flights.values() if f.state not in ("landed",)]
        rows, colors = [], []
        sel_i = -1
        for i, f in enumerate(fls):
            lead = gci.lead_of(w, f)
            fuel = f"{lead.fuel / w.catalog.aircraft[f.type_id].fuel_kg * 100:.0f}%" if lead else "—"
            wpn = sum(v for v in lead.weapons.values()) if lead else 0
            st = f.state.upper() + (" BINGO" if f.bingo else "")
            if f.state == "scrambling":
                st = f"T-{max(0, f.t_airborne - w.t) / 60:.1f}m"
            rows.append([f.callsign, f.type_id, st, f.target or "—", fuel, str(wpn),
                         ("DL" if f.control == "datalink" else "VOX") + ("" if f.auto else " MAN")])
            colors.append(th.alert if f.bingo else th.text)
            if f.id == scene.sel.get("flight"):
                sel_i = i
        hit = gui.table("fl", R(inner.x, y, inner.w, 132),
                        [("FLIGHT", 92), ("TYPE", 70), ("STATE", 120), ("TARGET", 64), ("FUEL", 50), ("WPN", 40),
                         ("CTL", 80)], rows, sel_i, colors)
        if hit is not None:
            scene.select("flight", fls[hit].id)
        y += 138
        fl = w.flights.get(scene.sel.get("flight") or "")
        if fl is None or fl.state in ("landed", "lost"):
            gui.wrapped(R(inner.x, y, inner.w, 100), "Select a flight. Commit it on a track, choose the geometry, and "
                        "watch the predicted intercept point (X) on the display. Weapons can only be released "
                        "under the current rules of engagement.", 12, th.engraving_dim)
            return
        lead = gci.lead_of(w, fl)
        at = w.catalog.aircraft[fl.type_id]
        info = [f"{fl.callsign}  {at.name}  ×{fl.n}   state {fl.state.upper()}   task {fl.task.upper()} / {fl.geometry.upper()}"]
        if lead is not None:
            need = gci.rtb_fuel(w, lead)
            info.append(f"Alt {fmt_alt(th, lead.alt, False)}  hdg {lead.hdg:03.0f}  TAS {lead.spd * 3.6:.0f} km/h  "
                        f"fuel {lead.fuel:.0f} kg (RTB needs {need:.0f})")
            trk = w.tracks.get(fl.target)
            if trk is not None:
                px, py = tracking.predicted(trk, w.t)
                d = math.hypot(px - lead.x, py - lead.y)
                if fl.state in ("contact", "judy", "vid", "shadow", "attack"):
                    tti = "pilot steering on own radar/visual"
                else:
                    tti = f"{(fl.pip_t - w.t) / 60:.1f} min" if fl.pip_t and fl.pip_t > w.t else "no collision solution"
                info.append(f"Target {trk.id}: {fmt_rng(th, d)}  PIP {tti}  contact {'YES' if fl.contact else 'no'}"
                            f"  tally {'YES' if fl.tally else 'no'}  VID {'YES' if fl.vid_done else 'no'}")
            ctrl = ("SAGE data link" if fl.control == "datalink" else "voice") if us else \
                f"guidance point {w.radars[fl.controller].name if fl.controller in w.radars else '—'}"
            info.append(f"Control: {ctrl}, {'computer' if fl.auto else 'manual'} vectors.  Weapons "
                        f"{'FREE' if fl.weapons_free else 'HOLD'}.  Load: "
                        + ", ".join(f"{v}×{k}" for k, v in lead.weapons.items() if v))
        gui.readout(R(inner.x, y, inner.w, len(info) * 16 + 8), info)
        y += len(info) * 16 + 16
        b = 2
        bw = (inner.w - 6 * b) // 7
        row = [("ASSIGN", lambda: scene.cmd("assign", flight=fl.id, track=scene.sel.get("track") or "",
                                            task=self.task, geometry=self.geom), "Commit on the selected track"),
               ("INTCPT", lambda: scene.cmd("task", flight=fl.id, task="intercept"), "Task: intercept"),
               ("ID PASS", lambda: scene.cmd("task", flight=fl.id, task="id"), "Task: visual identification"),
               ("SHADOW", lambda: scene.cmd("task", flight=fl.id, task="shadow"), "Task: identify and shadow"),
               ("CAP", lambda: scene.cmd("task", flight=fl.id, task="cap"), "Orbit here"),
               ("AUTO" if not fl.auto else "MANUAL", lambda: scene.cmd("auto", flight=fl.id, on=not fl.auto),
                "Toggle computer vs manual vectors"),
               ("RTB", lambda: scene.cmd("rtb", flight=fl.id), "Return to nearest base")]
        for i, (lab, fn, tip) in enumerate(row):
            lit = (lab == "INTCPT" and fl.task == "intercept") or (lab == "ID PASS" and fl.task == "id") or \
                  (lab == "SHADOW" and fl.task == "shadow") or (lab == "CAP" and fl.task == "cap")
            if gui.button(R(inner.x + i * (bw + b), y, bw, 24), lab, lit=lit, tip=tip, size=11):
                fn()
        y += 30
        hdg = fl.order_hdg if fl.order_hdg is not None else (lead.hdg if lead else 0.0)
        alt = fl.order_alt or 9000.0
        dalt = 1000 * FT if us else 500.0
        row2 = [("HDG −15", lambda: scene.cmd("vector", flight=fl.id, hdg=hdg - 15)),
                ("HDG +15", lambda: scene.cmd("vector", flight=fl.id, hdg=hdg + 15)),
                ("ALT −", lambda: scene.cmd("vector", flight=fl.id, alt=max(300.0, alt - 2 * dalt))),
                ("ALT +", lambda: scene.cmd("vector", flight=fl.id, alt=alt + 2 * dalt)),
                ("BUSTER" if fl.order_throttle != "ab" else "GATE OFF",
                 lambda: scene.cmd("throttle", flight=fl.id, throttle="mil" if fl.order_throttle == "ab" else "ab")),
                ("WPN FREE" if not fl.weapons_free else "WPN HOLD",
                 lambda: scene.cmd("weapons_free", flight=fl.id, on=not fl.weapons_free))]
        if us:
            row2.append(("DATALINK" if fl.control != "datalink" else "VOICE",
                         lambda: scene.cmd("control", flight=fl.id, mode="voice" if fl.control == "datalink" else "datalink")))
        else:
            gps = [s.id for s in w.radars.values() if s.gci]

            def next_gp():
                if gps:
                    i = (gps.index(fl.controller) + 1) % len(gps) if fl.controller in gps else 0
                    scene.cmd("controller", flight=fl.id, site=gps[i])
            row2.append(("GUID. PT", next_gp))
        tips = {"HDG −15": "Manual vector: turn left 15°", "HDG +15": "Manual vector: turn right 15°",
                "ALT −": "Manual vector: descend", "ALT +": "Manual vector: climb",
                "BUSTER": "Afterburner: faster, but fuel burns 3-5× faster",
                "WPN FREE": "Clear the flight to fire (checked against the rules of engagement)",
                "DATALINK": "Fly the intercept by SAGE data link (F-106 only)",
                "GUID. PT": "Hand the flight to the next guidance point"}
        for i, (lab, fn) in enumerate(row2):
            lit = (lab == "GATE OFF") or (lab == "WPN HOLD")
            if gui.button(R(inner.x + i * (bw + b), y, bw, 24), lab, lit=lit, tip=tips.get(lab), size=11,
                          color=th.lamp_red if lab == "WPN HOLD" else None):
                fn()
        y += 30
        if us and lead is not None and any(w.catalog.weapons[k].special for k, v in lead.weapons.items() if v):
            if gui.button(R(inner.x, y, 200, 24), "SPECIAL WPNS ARM" if not fl.special_release else "SPECIAL SAFE",
                          lit=fl.special_release, color=th.lamp_red,
                          tip="Arm nuclear air-to-air rockets — only after special-weapons release by higher authority."):
                scene.cmd("special", flight=fl.id, on=not fl.special_release)
        if not us and w.hq.engage_ok and fl.task != "ram":
            if gui.button(R(inner.x + 210, y, 200, 24), "ORDER RAMMING", color=th.lamp_red,
                          tip="A desperate measure. Needs permission from the command post (COMMS → REQUEST RAM)."):
                scene.cmd("task", flight=fl.id, task="ram")


# ====================================================================== MISSILES
class MissilesConsole(Console):
    name = "MISSILES"

    def __init__(self):
        self.key_on = False

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "MISSILE CONTROL", "surface-to-air")
        sams = list(w.sams.values())
        if not sams:
            gui.wrapped(inner, "No missile units assigned in this scenario.", 13, th.engraving_dim)
            return
        rows, colors = [], []
        sel_i = -1
        for i, s in enumerate(sams):
            st = w.catalog.sams[s.type_id]
            ready = "READY" if w.t >= s.t_ready else (f"{(s.t_ready - w.t) / 60:.0f} min" if s.t_ready < 1e8 else "NOT ALERTED")
            rows.append([s.name[:26], st.id, ready if s.status == "ok" else s.status.upper(),
                         f"{s.ready_missiles}/{s.reloads}", s.state.upper() + (" HOLD" if s.hold else ""),
                         s.assigned or "—", s.last_result[:16]])
            colors.append(th.alert if s.state in ("locked", "engaging") else th.text)
            if s.id == scene.sel.get("sam"):
                sel_i = i
        hit = gui.table("sams", R(inner.x, inner.y, inner.w, 170),
                        [("UNIT", 170), ("TYPE", 70), ("STATUS", 86), ("MSL", 46), ("STATE", 92), ("TGT", 52),
                         ("LAST", 70)], rows, sel_i, colors)
        if hit is not None:
            scene.select("sam", sams[hit].id)
        y = inner.y + 178
        s = w.sams.get(scene.sel.get("sam") or "")
        if s is None:
            gui.wrapped(R(inner.x, y, inner.w, 200),
                        ("Nike Hercules batteries belong to the Army: designations go through the AADCP (Missile Master), "
                         "which holds fire if our fighters are near the target. BOMARC is flown by the AN/FSQ-7 and launched "
                         "with the Senior Director's key — it is nuclear-armed and needs special-weapons release.") if us else
                        ("S-75 battalions acquire the strongest return inside their gate around the designated position. "
                         "A stale designation may find nothing — or the wrong aircraft. IFF protects only aircraft answering "
                         "on the current code."), 12, th.engraving_dim)
            return
        st = w.catalog.sams[s.type_id]
        info = [f"{s.name} — {st.name}", f"Envelope: {st.range_min_km:.0f}–{st.range_max_km:.0f} km, "
                f"{st.alt_min_m:,.0f}–{st.alt_max_m:,.0f} m; missile {st.missile_mps:.0f} m/s; salvo {s.salvo_size}; "
                f"reload {st.reload_min:.0f} min",
                f"Fire control: {s.state.upper()}" + (f", locked on a return {math.hypot(w.aircraft[s.lock].x - s.x, w.aircraft[s.lock].y - s.y):.0f} km out"
                                                      if s.lock in w.aircraft and w.aircraft[s.lock].state == 'airborne' else "")]
        if s.reloading:
            info.append(f"Reloading: next missile in {(min(s.reloading) - w.t) / 60:.1f} min")
        gui.readout(R(inner.x, y, inner.w, len(info) * 16 + 8), info)
        y += len(info) * 16 + 16
        tsel = scene.sel.get("track") or ""
        bw = (inner.w - 10) // 5
        if st.homing_km <= 0:
            row = [(f"DESIGNATE {tsel}" if tsel else "DESIGNATE", lambda: scene.cmd("sam_assign", site=s.id, track=tsel),
                    "Pass the selected track to this unit"),
                   ("HOLD FIRE" if not s.hold else "RELEASE", lambda: scene.cmd("sam_hold", site=s.id, on=not s.hold),
                    "Hold or release fire"),
                   ("CANCEL", lambda: scene.cmd("sam_cancel", site=s.id), "Cancel the designation"),
                   (f"SALVO {s.salvo_size}", lambda: scene.cmd("sam_salvo", site=s.id, n=s.salvo_size % st.salvo + 1),
                    "Missiles per engagement"),
                   ("AUTO RE-ENG" if not s.auto else "RE-ENG ON ORDER", lambda: scene.cmd("sam_auto", site=s.id, on=not s.auto),
                    "Automatic re-engagement after a salvo (wasteful against debris)")]
            for i, (lab, fn, tip) in enumerate(row):
                if gui.button(R(inner.x + i * (bw + 2), y, bw, 26), lab, lit=(lab == "RELEASE" or lab == "RE-ENG ON ORDER"),
                              tip=tip, size=11):
                    fn()
            y += 32
            if w.t < s.t_ready and gui.button(R(inner.x, y, 220, 26), "BRING TO READINESS",
                                              tip=f"Alert the unit: ready in {s.readiness_min:.0f} minutes."):
                scene.cmd("sam_alert", site=s.id)
        else:
            self.key_on = gui.toggle(R(inner.x, y, 220, 30), "SENIOR DIRECTOR'S KEY", self.key_on,
                                     tip="Arm the BOMARC launch circuit.")
            if gui.button(R(inner.x + 240, y, 180, 30), f"LAUNCH ON {tsel or '—'}", color=th.lamp_red,
                          tip="SAGE guides the BOMARC to the track, then its seeker homes on the nearest return."):
                if not w.hq.special_release:
                    scene.toast("BOMARC is nuclear-armed: special-weapons release required")
                else:
                    scene.cmd("bomarc", site=s.id, track=tsel, key=self.key_on)
            y += 40
        flying = [m for m in w.missiles.values() if m.owner == s.id and m.state == "flying"]
        done = [m for m in w.missiles.values() if m.owner == s.id and m.state == "done"][-6:]
        lines = [f"{m.id}: in flight {w.t - m.t_launch:.0f}s, alt {m.alt:,.0f} m" for m in flying] + \
                [f"{m.id}: {m.result}" for m in done]
        gui.log("msl", R(inner.x, y, inner.w, max(40, inner.bottom - y)), [(ln, th.text) for ln in lines] or
                [("No missiles in flight.", th.text_dim)])


# ====================================================================== RADAR NET
class RadarNetConsole(Console):
    name = "RADAR NET"

    def __init__(self):
        self._vc = None
        self._vc_key = None

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "RADAR NETWORK & TECHNICAL", "sites, settings, coverage")
        sites = list(w.radars.values())
        rows, colors = [], []
        sel_i = -1
        for i, s in enumerate(sites):
            ln = w.links.get(s.link)
            rows.append([s.name[:24], s.type_id, s.status.upper(), "ON" if s.mti else "off", f"1e-{s.pfa_exp:.0f}",
                         f"{s.rpm:g}", str(s.channel + 1), ("UP" if (ln is None or ln.up) else "DOWN")])
            colors.append(th.text if s.status == "ok" else th.accent if s.status in ("degraded", "maint") else th.alert)
            if s.id == scene.sel.get("site"):
                sel_i = i
        hit = gui.table("radars", R(inner.x, inner.y, inner.w, 156),
                        [("SITE", 166), ("TYPE", 86), ("STAT", 66), ("MTI", 36), ("Pfa", 46), ("RPM", 40),
                         ("CH", 28), ("LINE", 50)], rows, sel_i, colors, size=11, row_h=16)
        if hit is not None:
            scene.select("site", sites[hit].id)
            scene.scope.set_site(sites[hit].id)
        y = inner.y + 162
        s = w.radars.get(scene.sel.get("site") or "")
        if s is None:
            s = sites[0] if sites else None
            if s is None:
                return
            scene.sel["site"] = s.id
        rt = w.catalog.radars[s.type_id]
        colw = inner.w // 2 - 6
        lx = inner.x
        # ---- left: controls
        gui.label((lx, y), s.name_ru if (gui.ussr and gui.lang_mode != "en" and s.name_ru) else s.name, 14,
                  th.engraving, "eng")
        gui.label((lx, y + 17), f"{rt.name_ru if (gui.ussr and rt.name_ru) else rt.id} · {rt.band} {rt.freq_mhz:.0f} MHz "
                  f"{rt.peak_kw:,.0f} kW {rt.pulse_us:g} µs PRF {rt.prf:.0f} · {rt.az_beam_deg:g}°", 11,
                  th.engraving_dim, "eng_r")
        yy = y + 34
        if rt.mti:
            v = gui.toggle(R(lx, yy, 140, 26), "MTI", s.mti, tip="Moving Target Indication: cancels clutter, but also "
                           "tangential targets and targets at blind speeds.")
            if v != s.mti:
                scene.cmd("radar_mti", site=s.id, on=v)
        v = gui.toggle(R(lx + 150, yy, 140, 26), "IFF INTERR.", s.iff_on, tip="IFF/SIF interrogator.")
        if v != s.iff_on:
            scene.cmd("radar_iff", site=s.id, on=v)
        yy += 34
        k = gui.knob(R(lx, yy, 140, 34), "THRESHOLD", f"Pfa 1E-{s.pfa_exp:.0f}",
                     tip="Detection threshold. Lower (1E-4) = more sensitive, more false alarms.")
        if k:
            scene.cmd("radar_pfa", site=s.id, exp=s.pfa_exp - k)
        opts = rt.rpm_options or [rt.rpm]
        k = gui.knob(R(lx + 150, yy, 140, 34), "ANTENNA", f"{s.rpm:g} RPM",
                     tip="Faster rotation: more frequent updates, fewer pulses on target (less range).")
        if k and len(opts) > 1:
            i = opts.index(s.rpm) if s.rpm in opts else 0
            scene.cmd("radar_rpm", site=s.id, rpm=opts[(i + k) % len(opts)])
        yy += 42
        if rt.channels > 1:
            k = gui.knob(R(lx, yy, 140, 34), "FREQ CHANNEL", f"CH {s.channel + 1}/{rt.channels}",
                         tip="Change frequency to escape a spot jammer (it will re-tune after a while).")
            if k:
                scene.cmd("radar_channel", site=s.id, channel=(s.channel + k) % rt.channels)
        if gui.button(R(lx + 150, yy + 4, 140, 26), "MAINT 30 MIN",
                      tip="Preventive maintenance: off the air now, fewer failures later."):
            scene.cmd("radar_maint", site=s.id, minutes=30)
        yy += 44
        jam = 0.0
        from ..sim.radar import jam_to_noise_db
        for jac, jt, jbrg, jr in w.active_jammers(s):
            jam = max(jam, jam_to_noise_db(rt, jt, jr, False, jac.jam_channel < 0 or jac.jam_channel == s.channel))
        pw = 0.0 if s.status in ("down", "maint") else 10 ** (-s.degraded_db / 10.0)
        gui.meter(R(lx, yy, 90, 58), pw, "TX POWER", tip="Transmitter output relative to rated power.")
        gui.meter(R(lx + 100, yy, 90, 58), min(1.0, max(0.0, jam) / 30.0), "NOISE/JAM", danger=0.5,
                  tip="Receiver noise rise from sidelobe jamming (J/N).")
        gui.lamp((lx + 214, yy + 14), th.lamp_green if s.status == "ok" else th.lamp_red, True, label=s.status.upper())
        if s.gci:
            gui.lamp((lx + 214, yy + 40), th.lamp_amber, True, label="GUIDANCE PT")
        yy += 66
        hfs = [h for h in w.hfs.values() if h.site_id == s.id]
        for h in hfs:
            gui.readout(R(lx, yy, colw, 36), [f"{h.type_id}: {'BUSY ' + h.current if h.current else 'IDLE'}  "
                                              f"queue {len(h.queue)}", (f"last: {h.last_result or '—'}", th.text_dim)],
                        11)
            yy += 44
        if us:
            yy = max(yy, inner.bottom - 64)
            gui.eng((lx, yy), "AN/FSQ-7 DUPLEX", 12)
            for i, side in enumerate(("A", "B")):
                st = w.duplex.get(side, "?")
                col = th.lamp_green if st == "active" else th.lamp_amber if st == "standby" else th.lamp_red
                gui.lamp((lx + 10 + i * 100, yy + 26), col, True, label=f"{side}: {st.upper()}")
            if w.duplex_until > w.t:
                gui.annunciator(R(lx + 200, yy + 44, 90, 16), f"SWITCH {w.duplex_until - w.t:.0f}s", th.lamp_red, True,
                                blink=True, size=10)
            if gui.button(R(lx + 200, yy + 14, 90, 26), "SWITCH", color=th.lamp_red,
                          tip="Switch the standby computer on line (≈45 s with tracking frozen)."):
                scene.cmd("switchover")
        else:
            yy = max(yy, inner.bottom - 50)
            down = [ln.name for ln in w.links.values() if not ln.up]
            gui.eng((lx, yy), "TELEPHONE LINES", 12)
            gui.readout(R(lx, yy + 18, colw, 22), [("all lines up" if not down else "DOWN: " + ", ".join(down),
                                                     th.text if not down else th.alert)], 11)
        # ---- right: vertical coverage diagram and radar equation
        rx = inner.x + colw + 12
        trk = w.tracks.get(scene.sel.get("track") or "")
        az = bearing_deg(trk.x - s.x, trk.y - s.y) if trk is not None else 90.0
        hmax = 24000.0
        key = (s.id, round(az), s.status, s.pfa_exp, s.rpm, s.degraded_db, s.k_override)
        vr = R(rx, y, colw, 190)
        if key != self._vc_key:
            mg = coverage.vertical(w, s, az, rt.range_km, hmax, 140, 80, margin=True)
            base = np.array(th.scope_glow, dtype=float)
            lvl = np.clip((mg + 4.0) / 34.0, 0.0, 1.0)
            lvl = np.where(mg >= 0.0, 0.25 + 0.75 * lvl, lvl * 0.35)
            img = (lvl[..., None] * base).astype(np.uint8)
            surf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
            self._vc = pygame.transform.smoothscale(surf, (vr.w - 30, vr.h - 26))
            self._vc_key = key
        gui.glass(vr)
        gui.screen.blit(self._vc, (vr.x + 26, vr.y + 4))
        gui.label((vr.x + 28, vr.y + 4), f"VERTICAL COVERAGE · AZ {az:03.0f}° · 5 m²", 10, th.text)
        for frac in (0.25, 0.5, 0.75):
            hy = vr.y + 4 + (vr.h - 26) * (1 - frac)
            gui.label((vr.x + 2, hy - 6), fmt_alt(th, hmax * frac), 9, th.text_dim)
        gui.label((vr.right - 4, vr.bottom - 18), fmt_rng(th, rt.range_km), 9, th.text_dim, align="right")
        if trk is not None:
            px, py = tracking.predicted(trk, w.t)
            d = math.hypot(px - s.x, py - s.y)
            if trk.alt is not None and d < rt.range_km:
                mx = vr.x + 26 + (vr.w - 30) * d / rt.range_km
                my = vr.y + 4 + (vr.h - 26) * (1 - trk.alt / hmax)
                pygame.draw.circle(gui.screen, th.lamp_white, (int(mx), int(my)), 4, 1)
        gui.crt_overlay(vr, strength=0.7)
        gui.tip(vr, "Where this radar can see a 5 m² target (brightness = probability of detection) along the bearing "
                "to the selected track. Black wedges: below the horizon, behind terrain, or lobing nulls (VHF).")
        y2 = vr.bottom + 8
        if trk is not None:
            px, py = tracking.predicted(trk, w.t)
            bd = predict_coverage(w, s, px, py, trk.alt if trk.alt is not None else 6000.0, trk.vx * 1000, trk.vy * 1000, "B707")
            def db(v):
                return " —" if v <= -98 else f"{v:+.1f}"
            lines = [f"RADAR EQUATION: {trk.id}",
                     f"slant range   {fmt_rng(th, bd.slant_km)}",
                     f"elev/mask     {bd.elev_deg:+.2f}° / {bd.mask_deg:+.2f}°",
                     f"RCS (aspect)  {bd.rcs_m2:.1f} m² (airliner)",
                     f"S/N integr.   {bd.snr_db:.1f} dB",
                     f"  lobing      {db(bd.lobing_db)} dB",
                     f"clutter C/N   {db(bd.cnr_db)} dB",
                     f"  MTI resp.   {db(bd.mti_db)} dB @ {bd.v_radial:+.0f} m/s",
                     f"jamming J/N   {db(bd.jn_db)} dB",
                     f"S/(N+C+J)     {bd.sinr_db:.1f} dB",
                     f"threshold     {snr_for_pd(0.5, 10 ** -s.pfa_exp):.1f} dB (Pd 0.5)",
                     f"Pd {bd.pd:4.2f}: {bd.explain().upper()}"]
        else:
            lines = ["RADAR EQUATION", "Select a track to see this radar's full", "detection budget against it."]
        gui.readout(R(rx, y2, colw, min(inner.bottom - y2, len(lines) * 15 + 10)),
                    [(ln[:46], th.text if i else th.accent) for i, ln in enumerate(lines)], 11)


# ====================================================================== COMMS
class CommsConsole(Console):
    name = "COMMS"

    def __init__(self):
        self.filter = "all"

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "COMMUNICATIONS", "radio · telephone · teletype")
        x = inner.x
        for f, lab in (("all", "ALL"), ("radio", "RADIO"), ("voice", "VOICE"), ("tty", "TELETYPE"), ("system", "ALERTS")):
            if gui.button(R(x, inner.y, 84, 24), lab, lit=self.filter == f):
                self.filter = f
            x += 86
        pend = [m for m in w.messages if m.ack and not m.acked and m.delivered]
        if gui.button(R(inner.right - 120, inner.y, 120, 24), f"ACK ALL ({len(pend)})", lit=bool(pend),
                      color=th.lamp_amber, tip="Acknowledge every message waiting for acknowledgement (A)."):
            scene.cmd("ack_all")
        cols = {"radio": th.lamp_blue, "voice": th.engraving, "tty": th.text, "system": th.lamp_amber,
                "datalink": th.text_dim}
        msgs = [m for m in w.messages if m.delivered and (self.filter == "all" or m.channel == self.filter)][-300:]
        lines = []
        for m in msgs:
            mark = "! " if (m.ack and not m.acked) else ""
            col = th.alert if m.priority >= 2 else cols.get(m.channel, th.text)
            lines.append((f"{clock(w, m.t_deliver)} {mark}{m.sender}: {m.text}", col))
        gui.log("comms", R(inner.x, inner.y + 30, inner.w, inner.h - 210), lines, 12,
                "cyr" if not us else "ui")
        y = inner.bottom - 172
        gui.eng((inner.x, y), "REQUESTS TO HIGHER AUTHORITY", 13)
        y += 22
        tsel = scene.sel.get("track") or ""
        bw = (inner.w - 8) // 4
        reqs = [("HOSTILE " + (tsel or "—"), "declare_hostile", "Ask for this track to be declared hostile."),
                ("ENGAGE " + (tsel or "—"), "engage", "Ask for authority to engage this track."),
                ("REPORT " + (tsel or "—"), "report", "Report this track to HQ.")]
        if not us:
            reqs.append(("RAM " + (tsel or "—"), "ram", "Ask permission to order a ramming attack."))
        else:
            reqs.append(("SPECIAL REL.", "special_release", "Request release of nuclear air-defense weapons."))
        for i, (lab, kind, tip) in enumerate(reqs):
            if gui.button(R(inner.x + i * (bw + 2), y, bw, 26), lab, tip=tip, size=11):
                if kind == "report":
                    scene.cmd("report", track=tsel)
                elif kind == "special_release":
                    scene.cmd("request", kind=kind)
                else:
                    scene.cmd("request", kind=kind, track=tsel)
        y += 30
        row = [("WEAPONS TIGHT", "weapons_status", "TIGHT"), ("WEAPONS FREE", "weapons_status", "FREE"),
               ("WEAPONS HOLD", "weapons_status", "HOLD")]
        if us:
            row.append(("ADW RED", "alert", "RED"))
        else:
            row.append(("READINESS FULL", "readiness", "FULL"))
        for i, (lab, kind, val) in enumerate(row):
            if gui.button(R(inner.x + i * (bw + 2), y, bw, 26), lab, size=11,
                          color=th.lamp_red if val in ("FREE", "RED") else None,
                          tip="Requests go to higher authority; the answer takes minutes and depends on the evidence."):
                scene.cmd("request", kind=kind, value=val)
        y += 32
        pending = [rq for rq in w.hq.requests if not rq.answered]
        txt = "; ".join(f"{rq.kind} {rq.ref or rq.value} (~{max(0, rq.t_answer - w.t) / 60:.0f} min)" for rq in pending)
        gui.readout(R(inner.x, y, inner.w, 40), [(f"Pending: {txt or 'none'}", th.text),
                                                 (f"HQ: {w.hq.name}   weapons {w.hq.weapons_status}   credibility "
                                                  f"{w.hq.credibility:.2f}", th.text_dim)], 11)


# ====================================================================== INTEL
class IntelConsole(Console):
    name = "INTEL"

    def __init__(self):
        self.tab = "brief"

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        inner = gui.panel(r, "INTELLIGENCE", "briefing · threats · notes")
        x = inner.x
        for t, lab in (("brief", "BRIEFING"), ("intel", "REPORTS"), ("threat", "AIRCRAFT"), ("tech", "TECH NOTES")):
            if gui.button(R(x, inner.y, 110, 24), lab, lit=self.tab == t):
                self.tab = t
            x += 112
        body = R(inner.x, inner.y + 32, inner.w, inner.h - 32)
        gui.glass(body)
        b = body.inflate(-14, -10)
        kind = "tty" if w.faction == "US" else "cyr"
        if self.tab == "brief":
            gui.wrapped(b, w.briefing.strip(), 13, th.text, kind, scroll_id="brief")
        elif self.tab == "intel":
            txt = "\n\n".join(f"{t.upper()}\n{x}" for t, x in w.intel) or "No intelligence reports."
            gui.wrapped(b, txt, 13, th.text, kind, scroll_id="intel")
        elif self.tab == "threat":
            seen = sorted({a.type_id for a in w.aircraft.values() if a.kind == "aircraft"} |
                          {q.type_id for q in w.squadrons.values()})
            parts = []
            for tid in seen:
                at = w.catalog.aircraft[tid]
                parts.append(f"{at.name} [{at.provenance}]\n  ceiling {fmt_alt(th, at.ceiling_m, False)}"
                             f"{' (zoom ' + fmt_alt(th, at.zoom_ceiling_m, False) + ')' if at.zoom_ceiling_m else ''}, "
                             f"max Mach {at.max_mach:g}, cruise {at.cruise_kmh:.0f} km/h at {fmt_alt(th, at.cruise_alt_m, False)}\n"
                             f"  RCS nose/beam/tail {at.rcs_nose:g}/{at.rcs_beam:g}/{at.rcs_tail:g} m²"
                             f"{'; airborne radar ' + str(int(at.ai_radar_km)) + ' km' if at.ai_radar_km else ''}"
                             f"{'; look-down: no' if at.ai_radar_km and not at.lookdown else ''}\n  {at.notes}")
            gui.wrapped(b, "\n\n".join(parts), 12, th.text, "ui", scroll_id="threat")
        else:
            gui.wrapped(b, TECH_NOTES, 12, th.text, "ui", scroll_id="tech")


# ====================================================================== STATUS
class StatusConsole(Console):
    name = "STATUS"

    def draw(self, gui, r, scene):
        w = scene.world
        th = scene.theme
        us = w.faction == "US"
        inner = gui.panel(r, "STATUS & LOGISTICS", "readiness · automation · objectives")
        y = inner.y
        hq = w.hq
        gui.readout(R(inner.x, y - 2, inner.w - 118, 24), [f"{hq.name}:  {hq.readiness}   {'ADW ' + hq.alert if us else ''}"
                                                           f"   WEAPONS {hq.weapons_status}"], 13)
        gui.meter(R(inner.right - 100, y - 4, 96, 56), hq.credibility, "HQ CONFIDENCE",
                  tip="Falls when you ignore orders, leave alerts unacknowledged or make unfounded requests.")
        y += 40
        gui.eng((inner.x, y), "POSITIONS (automation)", 12)
        y += 22
        pos = [("surveil", "SURVEILLANCE", "AI operators initiate tracks from persistent returns."),
               ("ident", "IDENTIFICATION", "AI technicians apply safe IDs (friend by IFF/flight plan, else unknown)."),
               ("height", "HEIGHT", "Automatic height-finder requests for tracks of interest."),
               ("tech", "TECHNICAL", "Technicians perform computer switchover on failure.")]
        for i, (k, lab, tip) in enumerate(pos):
            if k == "height" and not w.hfs:
                continue
            if k == "tech" and not us:
                continue
            v = gui.toggle(R(inner.x + (i % 2) * 230, y + (i // 2) * 30, 220, 28), lab, w.automation.get(k, False), tip=tip)
            if v != w.automation.get(k, False):
                scene.cmd("automation", position=k, on=v)
        y += 66
        gui.eng((inner.x, y), "OBJECTIVES", 12)
        y += 20
        for o in w.objectives:
            if o.hidden:
                continue
            col = th.lamp_green if o.status == "done" else th.lamp_red if o.status == "failed" else th.lamp_amber
            gui.lamp((inner.x + 8, y + 8), col, o.status != "open" or True, radius=5)
            gui.label((inner.x + 20, y), o.text[:80], 13, th.engraving if o.status == "open" else th.engraving_dim,
                      "eng_r")
            y += 18
        y += 8
        gui.eng((inner.x, y), "AIRBASES & SQUADRONS", 12)
        y += 20
        sq_lines = []
        for q in w.squadrons.values():
            b = w.airbases[q.base_id]
            alert = sum(q.ready.values())
            sq_lines.append(f"{q.name[:20]:<20} {b.name[:16]:<16} alert {alert:>2}  air {q.airborne:>2}  "
                            f"rcv {len(q.recovering)}  plt {q.pilots}")
        st = w.stats
        sq_lines.append((f"Tracks {st.tracks_initiated} ({st.false_tracks} false) · sorties {st.sorties} · AAM {st.aam_shots}"
                         f" · SAM {st.missiles} · reports {st.reports_to_hq} · late acks {st.unacked_overdue}", th.text_dim))
        hgt = min(len(sq_lines) * 15 + 10, inner.bottom - 40 - y)
        if hgt > 20:
            gui.readout(R(inner.x, y, inner.w, hgt), sq_lines, 11)
        y = inner.bottom - 30
        if gui.button(R(inner.x, y, 140, 28), "SAVE (F5)", tip="Save the current shift."):
            scene.app.save_game()
        if gui.button(R(inner.x + 146, y, 140, 28), "LOAD (F9)", tip="Load the saved shift."):
            scene.app.load_game()
        if gui.button(R(inner.x + 292, y, 160, 28), "END SHIFT", color=th.lamp_red,
                      tip="End the scenario now and go to the after-action report."):
            scene.end_shift()
