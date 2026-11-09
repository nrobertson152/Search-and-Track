"""Scenes: title & faction select, briefing, command center, after-action."""
from __future__ import annotations

import math

import pygame

from ..sim import aar, commands, doctrine, scenario, tracking
from ..sim.world import DT
from .consoles import (CommsConsole, IntelConsole, MissilesConsole, RadarNetConsole, StatusConsole, TECH_NOTES,
                       TracksConsole, WeaponsConsole)
from .fx import scanlines, vignette
from .mapview import MapView, clock, fmt_alt
from .scope import Scope
from .theme import TEXT, US, USSR, theme_for

R = pygame.Rect
W, H = 1600, 900
SPEEDS = [0, 1, 2, 4, 8, 16, 32]

CONTROLS_HELP = """CONTROLS
Mouse: left-click selects tracks, flights and sites. On the US display, clicking empty space places the light gun. Right-drag pans the display; the wheel zooms.
Space: pause / resume.   + / − : time compression.   M: switch situation display ↔ radar scope.
F1 tracks · F2 weapons · F3 missiles · F4 radar net · F5 save · F6 comms · F7 intel · F8 status · F9 load
I: initiate a track at the light gun (US).   H: height request.   Tab: next track.   A: acknowledge all.
C: coverage overlay.   [ / ] : coverage altitude.   , / . : scope radar.   R: scope range.   Esc: menu.

THE CORE LOOP
1. Returns appear. Initiate a track (US) or wait for the target number from the radar companies (USSR).
2. Get an altitude: a height finder (US) or the V-beam estimate (USSR).
3. Identify: IFF, flight-plan correlation (US: ±5 min and 10/20 nm), behaviour, visual identification.
4. Commit interceptors: choose the task (ID pass / intercept / shadow) and the geometry, and watch the predicted intercept point and fuel.
5. Weapons only under the rules of engagement. Ask higher authority, and expect them to ask for evidence.
6. Keep the network healthy: radar faults, telephone lines, the AN/FSQ-7 duplex, alerts that need acknowledging.
"""


class Scene:
    def __init__(self, app):
        self.app = app

    def handle(self, events) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass


# ====================================================================== TITLE
class TitleScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.faction = "US"
        self.items = scenario.list_scenarios()
        self.sel_id = ""
        self.vig = vignette((W, H), 180)
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        gui = self.app.gui
        th = theme_for(self.faction)
        gui.set_theme(th) if gui.theme is not th else None
        screen.fill((10, 12, 12))
        # header
        hdr = R(20, 18, W - 40, 110)
        gui.panel(hdr)
        gui.label((hdr.x + 30, hdr.y + 14), "SEARCH AND TRACK", 44, th.engraving, "ui_bold", shadow=True)
        gui.label((hdr.x + 34, hdr.y + 70), "A Cold War air-defense command simulator · 1955–1990 · two systems, "
                  "one sky", 15, th.engraving_dim)
        gui.label((hdr.right - 30, hdr.y + 78), "v0.1 vertical slice", 12, th.engraving_dim, align="right")
        # faction panels
        fy = 150
        for i, (fid, tm, title, sub, blurb) in enumerate([
            ("US", US, "UNITED STATES — NORAD / AIR DEFENSE COMMAND", "SAGE semi-automatic ground environment",
             "Digital radar data every scan into the AN/FSQ-7. You initiate tracks with the light gun, correlate "
             "flight plans against NORAD tolerances, assign height finders, and fly F-106s by data link. "
             "Army Nike batteries answer to the Missile Master; BOMARC answers to your key."),
            ("USSR", USSR, "СССР — ВОЙСКА ПВО СТРАНЫ", "PVO Strany: Air Defense Forces of the Country",
             "Radar companies telephone their targets in; your plotting board is minutes behind the sky. Guidance "
             "points with their own radars control the interceptors. S-75 battalions, V-beam altitudes, monthly IFF "
             "codes — and a command chain that wants results.")]):
            pr = R(20 + i * (W // 2 - 10), fy, W // 2 - 30, 250)
            gui.set_theme(tm)
            inner = gui.panel(pr, title, sub)
            gui.wrapped(R(inner.x + 4, inner.y + 6, inner.w - 10, 140), blurb, 14, tm.engraving)
            if gui.button(R(inner.x + 4, inner.bottom - 40, 260, 34), "SELECT " + ("NORAD" if fid == "US" else "ПВО / PVO"),
                          lit=self.faction == fid, color=tm.lamp_amber if fid == "US" else tm.lamp_red, size=13):
                self.faction = fid
                self.sel_id = ""
        th = theme_for(self.faction)
        gui.set_theme(th)
        # scenario list
        lr = R(20, 420, W - 40, 400)
        inner = gui.panel(lr, "SCENARIOS" if self.faction == "US" else "ЗАДАЧИ · SCENARIOS",
                          "training missions first")
        items = [s for s in self.items if s["faction"] == self.faction]
        y = inner.y + 4
        for s in items:
            rr = R(inner.x, y, 640, 64)
            sel = s["id"] == self.sel_id
            gui.glass(rr, (30, 40, 40) if sel else None)
            gui.label((rr.x + 12, rr.y + 6), s["title"], 16, th.text, "ui_bold" if self.faction == "US" else "cyr")
            gui.label((rr.x + 12, rr.y + 28), s["subtitle"], 12, th.text_dim)
            gui.label((rr.right - 10, rr.y + 8), s["kind"].upper(), 11, th.accent, align="right")
            if gui.clicked(rr):
                self.sel_id = s["id"]
            y += 72
        cur = next((s for s in items if s["id"] == self.sel_id), None)
        side = R(inner.x + 660, inner.y + 4, inner.w - 664, inner.h - 60)
        gui.glass(side)
        if cur:
            gui.wrapped(side.inflate(-20, -16), cur["summary"], 15, th.text, "tty" if self.faction == "US" else "cyr")
        else:
            gui.wrapped(side.inflate(-20, -16), "Select a scenario.\n\nNew to the game? Start with the training "
                        "mission: an instructor walks you through the core loop.", 15, th.text_dim)
        by = inner.bottom - 44
        if gui.button(R(inner.x + 660, by, 220, 38), "BRIEFING >>", enabled=cur is not None, color=th.lamp_green, size=14):
            self.app.start_briefing(cur["id"])
        if gui.button(R(inner.x + 890, by, 180, 38), "LOAD SAVE", size=13, enabled=self.app.has_save()):
            self.app.load_game()
        if gui.button(R(inner.x + 1080, by, 160, 38), "MANUAL", size=13):
            self.app.push(ManualScene(self.app, self))
        if gui.button(R(inner.right - 120, by, 120, 38), "QUIT", size=13, color=th.lamp_red):
            self.app.running = False
        gui.label((20, H - 26), "Map data: Natural Earth (public domain). Terrain: ETOPO1 10′ (NOAA, via Fatiando a Terra). "
                  "Fonts: SIL OFL. Sounds synthesized. GPL-3.0.", 11, (110, 110, 100))
        screen.blit(self.vig, (0, 0))


# ====================================================================== MANUAL
class ManualScene(Scene):
    def __init__(self, app, back):
        super().__init__(app)
        self.back = back
        self.page = 0

    def draw(self, screen):
        gui = self.app.gui
        th = gui.theme
        screen.fill((10, 12, 12))
        inner = gui.panel(R(40, 30, W - 80, H - 60), "OPERATOR'S MANUAL", "Search and Track")
        pages = [CONTROLS_HELP, TECH_NOTES]
        for i, lab in enumerate(["CONTROLS & CORE LOOP", "RADAR & TECHNICAL NOTES"]):
            if gui.button(R(inner.x + i * 260, inner.y, 250, 28), lab, lit=self.page == i):
                self.page = i
        body = R(inner.x, inner.y + 40, inner.w, inner.h - 90)
        gui.glass(body)
        gui.wrapped(body.inflate(-24, -16), pages[self.page], 15, th.text, "tty", scroll_id=f"man{self.page}")
        if gui.button(R(inner.right - 160, inner.bottom - 40, 160, 34), "BACK", size=13) or \
                any(e.key == pygame.K_ESCAPE for e in gui.keys):
            self.app.pop()


# ====================================================================== BRIEFING
class BriefingScene(Scene):
    def __init__(self, app, sid: str):
        super().__init__(app)
        self.world = scenario.build_world(sid)
        self.theme = theme_for(self.world.faction)
        self.t = 0.0
        self.vig = vignette((W, H), 170)
        app.audio.play("tty")

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        gui = self.app.gui
        gui.set_theme(self.theme) if gui.theme is not self.theme else None
        th = self.theme
        w = self.world
        screen.fill((10, 12, 12))
        inner = gui.panel(R(30, 24, W - 60, H - 48), w.title.upper(), w.theater.name)
        paper = R(inner.x, inner.y, 900, inner.h - 10)
        pygame.draw.rect(screen, (226, 222, 204) if w.faction == "US" else (214, 210, 186), paper)
        for yy in range(paper.y + 30, paper.bottom, 32):
            pygame.draw.line(screen, (205, 200, 182), (paper.x, yy), (paper.right, yy))
        n = int(self.t * 160)
        text = w.briefing.strip()
        shown = text[:n] + ("_" if n < len(text) and int(self.t * 4) % 2 == 0 else "")
        gui.wrapped(paper.inflate(-40, -30), shown, 15, (40, 34, 26), "tty" if w.faction == "US" else "cyr")
        side = R(paper.right + 16, inner.y, inner.right - paper.right - 16, inner.h - 70)
        gui.glass(side)
        y = side.y + 12
        gui.label((side.x + 12, y), "OBJECTIVES", 14, th.engraving, "ui_bold")
        y += 26
        for o in w.objectives:
            if o.hidden:
                continue
            lines = TEXT.wrap(f"• {o.text} ({o.points})", side.w - 30, 13)
            for ln in lines:
                gui.label((side.x + 14, y), ln, 13, th.text)
                y += 18
            y += 4
        y += 10
        gui.label((side.x + 12, y), "FORCES", 14, th.engraving, "ui_bold")
        y += 24
        for q in w.squadrons.values():
            gui.label((side.x + 14, y), f"{q.name}: {sum(q.ready.values())} × {q.type_id} at {w.airbases[q.base_id].name}",
                      12, th.text)
            y += 17
        types = {}
        for s in w.radars.values():
            types[s.type_id] = types.get(s.type_id, 0) + 1
        gui.label((side.x + 14, y), "Radars: " + ", ".join(f"{v}× {k}" for k, v in types.items()), 12, th.text)
        y += 17
        if w.sams:
            st = {}
            for s in w.sams.values():
                st[s.type_id] = st.get(s.type_id, 0) + 1
            gui.label((side.x + 14, y), "Missiles: " + ", ".join(f"{v}× {k}" for k, v in st.items()), 12, th.text)
        by = inner.bottom - 50
        if gui.button(R(side.x, by, 220, 40), "TAKE THE WATCH >>", color=th.lamp_green, size=14):
            self.app.start_command(self.world)
        if gui.button(R(side.right - 140, by, 140, 40), "BACK", size=13):
            self.app.pop()
        screen.blit(self.vig, (0, 0))


# ====================================================================== COMMAND CENTER
class CommandScene(Scene):
    def __init__(self, app, world):
        super().__init__(app)
        self.world = world
        self.theme = theme_for(world.faction)
        app.gui.set_theme(self.theme)
        self.map = MapView(world, self.theme, R(8, 52, 980, 776))
        self.scope = Scope(world, self.theme, R(8, 52, 980, 776))
        self.mode = "map"
        self.consoles = [TracksConsole(), WeaponsConsole(), MissilesConsole(), RadarNetConsole(), CommsConsole(),
                         IntelConsole(), StatusConsole()]
        self.ci = 0
        self.sel = {"track": None, "flight": None, "site": next(iter(world.radars), None), "sam": None}
        self.speed_i = 1
        self.render_t = world.t
        self.toasts: list[tuple[float, str, tuple]] = []
        self.auto_slow = True
        self.menu = False
        self.ended_t = None
        self.scan = scanlines((980, 776), 26, 3)
        self.vig = vignette((980, 776), 140)
        self.audio = app.audio
        self.app = app
        self.fps = 0.0

    # ------------------------------------------------------------ helpers used by consoles
    def select(self, kind: str, oid: str) -> None:
        self.sel[kind] = oid
        if kind == "site" and oid in self.world.radars:
            self.scope.set_site(oid)

    def cmd(self, kind: str, **args):
        ok, msg = commands.run(self.world, kind, **args)
        self.toast(msg, ok)
        if not ok:
            self.audio.play("beep")
        return ok, msg

    def toast(self, msg: str, ok: bool = True) -> None:
        self.toasts.append((self.app.clock_t + 5.0, msg, self.theme.ok if ok else self.theme.alert))
        self.toasts = self.toasts[-4:]

    def initiate(self) -> None:
        lg = self.map.light_gun
        if lg is None:
            self.toast("Place the light gun first: click a return on the display", False)
            return
        self.cmd("initiate", x=lg[0], y=lg[1], radius=14.0 / max(self.map.scale, 0.2) + 6.0)

    def end_shift(self) -> None:
        scenario.end(self.world, "Shift ended by the commander", "ended")

    @property
    def speed(self) -> int:
        return SPEEDS[self.speed_i]

    # ------------------------------------------------------------ input
    def handle(self, events):
        gui = self.app.gui
        w = self.world
        for e in gui.keys:
            k = e.key
            if self.menu:
                if k == pygame.K_ESCAPE:
                    self.menu = False
                continue
            if k == pygame.K_ESCAPE:
                self.menu = True
            elif k == pygame.K_SPACE:
                self.speed_i = 0 if self.speed_i else 1
            elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.speed_i = min(len(SPEEDS) - 1, self.speed_i + 1)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.speed_i = max(0, self.speed_i - 1)
            elif pygame.K_F1 <= k <= pygame.K_F8 and k not in (pygame.K_F5,):
                idx = {pygame.K_F1: 0, pygame.K_F2: 1, pygame.K_F3: 2, pygame.K_F4: 3, pygame.K_F6: 4,
                       pygame.K_F7: 5, pygame.K_F8: 6}.get(k)
                if idx is not None:
                    self.ci = idx
            elif k == pygame.K_F5:
                self.app.save_game()
            elif k == pygame.K_F9:
                self.app.load_game()
            elif k == pygame.K_m:
                self.mode = "scope" if self.mode == "map" else "map"
            elif k == pygame.K_c:
                self.map.layers["coverage"] = not self.map.layers["coverage"]
            elif k == pygame.K_LEFTBRACKET:
                self._cov_alt(-1)
            elif k == pygame.K_RIGHTBRACKET:
                self._cov_alt(1)
            elif k == pygame.K_i and w.faction == "US":
                self.initiate()
            elif k == pygame.K_h and self.sel.get("track"):
                self.cmd("height", track=self.sel["track"])
            elif k == pygame.K_a:
                self.cmd("ack_all")
            elif k == pygame.K_TAB:
                ids = sorted(t.id for t in w.tracks.values() if not t.lost)
                if ids:
                    cur = self.sel.get("track")
                    self.sel["track"] = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
            elif k == pygame.K_COMMA:
                self._cycle_radar(-1)
            elif k == pygame.K_PERIOD:
                self._cycle_radar(1)
            elif k == pygame.K_r:
                self.scope.cycle_range(1)
        if self.menu:
            return
        if self.mode == "map":
            res = self.map.handle(gui, events)
            if res:
                _, (wx, wy), (sx, sy) = res
                hit = self.map.pick(sx, sy)
                if hit:
                    self.select(*hit)
                    if hit[0] == "track":
                        self.map.light_gun = None
                elif w.faction == "US":
                    self.map.light_gun = (wx, wy)
                    self.audio.play("click")
        else:
            if gui.released and not gui.consumed and self.scope.rect.collidepoint(gui.mouse) \
                    and self.scope.rect.collidepoint(gui.press_pos):
                pos = self.scope.to_world(*gui.mouse)
                if pos is not None:
                    gui.consumed = True
                    hit = None
                    for t in w.tracks.values():
                        px, py = tracking.predicted(t, w.t)
                        if math.hypot(px - pos[0], py - pos[1]) < self.scope.range_km * 0.02 + 2:
                            hit = t.id
                    if hit:
                        self.select("track", hit)
                    elif w.faction == "US":
                        self.map.light_gun = pos
                        self.audio.play("click")

    def _cov_alt(self, d: int) -> None:
        alts = [150.0, 500.0, 1500.0, 3000.0, 6000.0, 10000.0, 15000.0, 20000.0]
        i = min(range(len(alts)), key=lambda k: abs(alts[k] - self.map.cov_alt))
        self.map.cov_alt = alts[max(0, min(len(alts) - 1, i + d))]
        self.map.layers["coverage"] = True

    def _cycle_radar(self, d: int) -> None:
        ids = list(self.world.radars)
        if ids:
            i = ids.index(self.scope.site_id) if self.scope.site_id in ids else 0
            self.select("site", ids[(i + d) % len(ids)])

    # ------------------------------------------------------------ time
    def update(self, dt):
        w = self.world
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(dt, 1e-3))
        if self.menu:
            return
        if self.speed > 0 and not w.ended:
            self.render_t += dt * self.speed
            steps = 0
            while self.render_t > w.t and steps < 64 and not w.ended:
                w.step(DT)
                steps += 1
            if self.render_t > w.t + 2.0:
                self.render_t = w.t
            self._react()
        if w.ended:
            if self.ended_t is None:
                self.ended_t = self.app.clock_t
            elif self.app.clock_t - self.ended_t > 2.5:
                self.app.start_debrief(w)

    def _react(self) -> None:
        w = self.world
        if not w.new_messages:
            return
        mids = set(w.new_messages)
        w.new_messages.clear()
        for m in w.messages[-60:]:
            if m.mid not in mids:
                continue
            if m.channel == "system" and m.priority >= 1:
                self.audio.play("alert")
                if self.auto_slow and self.speed_i > 2:
                    self.speed_i = 1
                    self.toast("Time compression reduced: alert", True)
            elif m.channel == "radio":
                self.audio.play("static", 0.6)
            elif m.channel == "tty":
                self.audio.play("tty")
            elif m.channel == "voice" and m.priority >= 1:
                self.audio.play("buzz" if w.faction == "US" else "bell")
        # messages created directly (delivered immediately) are flagged here
    # ------------------------------------------------------------ draw
    def draw(self, screen):
        gui = self.app.gui
        w = self.world
        th = self.theme
        screen.fill(th.bg)
        self._new_msgs_scan()
        self._topbar(gui)
        mr = self.map.rect
        gui.glass(mr, (0, 0, 0))
        if self.mode == "map":
            self.map.draw(screen, self.sel, self.render_t)
            screen.blit(self.scan, mr.topleft)
            screen.blit(self.vig, mr.topleft)
            self.map.annotate(screen, self.sel)
        else:
            gui.panel(mr, screws=False)
            self.scope.draw(screen, min(self.render_t, w.t), self.app.dt, self.speed)
        self._display_strip(gui)
        # console selector
        names = ["TRACKS F1", "WEAPONS F2", "MISSILES F3", "RADAR F4", "COMMS F6", "INTEL F7", "STATUS F8"]
        bw = 596 // len(names)
        unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
        for i, n in enumerate(names):
            lit = i == self.ci
            lab = n if not (i == 4 and unacked) else f"COMMS !{unacked}"
            if gui.button(R(996 + i * bw, 52, bw - 3, 28), lab, lit=lit, size=10,
                          color=th.lamp_red if (i == 4 and unacked and not lit) else None):
                self.ci = i
        self.consoles[self.ci].draw(gui, R(996, 84, 596, 744), self)
        self._ticker(gui)
        if self.menu:
            self._menu(gui)

    def _new_msgs_scan(self) -> None:
        pass

    def _topbar(self, gui):
        w = self.world
        th = self.theme
        bar = R(0, 0, W, 46)
        gui.panel(bar, screws=False)
        gui.label((14, 5), th.title, 12, th.engraving, "cyr" if w.faction == "USSR" else "ui_bold")
        gui.label((14, 24), f"{w.title} — {th.subtitle}", 11, th.engraving_dim, "cyr" if w.faction == "USSR" else "ui")
        # clock (LED style)
        hh = clock(w, self.render_t)
        secs = int(self.render_t) % 60
        cr = R(560, 5, 190, 36)
        pygame.draw.rect(gui.screen, (0, 0, 0), cr, border_radius=4)
        led = (255, 70, 40) if w.faction == "USSR" else (255, 150, 50)
        gui.label((cr.x + 10, cr.y + 2), f"{hh}:{secs:02d}", 26, led, "crt")
        gui.label((cr.right - 8, cr.y + 4), w.clock_tz, 12, led, align="right")
        gui.label((cr.right - 8, cr.y + 19), f"T+{int(self.render_t // 60):02d}", 11, led, align="right")
        # time compression
        x = 762
        for i, s in enumerate(SPEEDS):
            lab = "II" if s == 0 else f"{s}×"
            if gui.button(R(x, 9, 40, 28), lab, lit=self.speed_i == i, size=11,
                          tip="Pause" if s == 0 else f"Time compression {s}×"):
                self.speed_i = i
            x += 42
        x += 8
        hq = w.hq
        unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
        lamps = []
        if w.faction == "US":
            lamps.append((th.lamp_white, hq.readiness, False, "Defense readiness condition"))
            adw = {"WHITE": th.lamp_white, "YELLOW": th.lamp_amber, "RED": th.lamp_red}.get(hq.alert, th.lamp_white)
            lamps.append((adw, f"ADW {hq.alert}", hq.alert == "RED", "Air Defense Warning (set by NORAD Region)"))
        else:
            lamps.append((th.lamp_red if hq.readiness == "FULL" else th.lamp_amber, f"READY {hq.readiness}", False,
                          "Combat readiness of the Air Defense Forces"))
        ws = {"HOLD": th.lamp_green, "TIGHT": th.lamp_amber, "FREE": th.lamp_red}.get(hq.weapons_status, th.lamp_white)
        lamps.append((ws, f"WPNS {hq.weapons_status}", False, "Weapons control status (set by higher authority)"))
        if w.faction == "US":
            up = w.c2_up()
            side = next((s for s, v in w.duplex.items() if v == "active"), "-")
            lamps.append((th.lamp_green if up else th.lamp_red, f"FSQ-7 {side}" if up else "FSQ-7 OFF", not up,
                          "AN/FSQ-7 duplex computer (RADAR console)"))
        lamps.append((th.lamp_red if unacked else (60, 20, 20), f"ACK {unacked}", unacked > 0,
                      "Messages awaiting acknowledgement (A)"))
        for col, lab, blink, tip in lamps:
            gui.lamp((x + 8, 23), col, True, blink=blink, label=lab, tip=tip)
            x += 30 + TEXT.width(lab, 11)
        if gui.button(R(W - 86, 9, 76, 28), "MENU", size=11, tip="Esc"):
            self.menu = True

    def _display_strip(self, gui):
        th = self.theme
        y = 834
        x = 8
        for m, lab in (("map", "SITUATION" if self.world.faction == "US" else "ПЛАНШЕТ BOARD"), ("scope", "RADAR SCOPE")):
            if gui.button(R(x, y, 128, 28), lab, lit=self.mode == m, size=11, tip="M toggles"):
                self.mode = m
            x += 130
        x += 10
        if self.mode == "map":
            lay = self.map.layers
            for key, lab, tip in (("coverage", "COVERAGE", "Predicted radar coverage at the selected altitude (C)"),
                                  ("raw", "RAW", "Unassociated radar returns"), ("zones", "ZONES", "ADIZ & defended areas"),
                                  ("labels", "LABELS", "Names"), ("history", "HISTORY", "Track history"),
                                  ("rings", "RINGS", "Range rings of the selected radar and SAM engagement rings")):
                if key == "raw" and self.world.faction != "US":
                    continue
                if gui.button(R(x, y, 72, 28), lab, lit=lay[key], size=10, tip=tip):
                    lay[key] = not lay[key]
                    if key in ("zones", "labels"):
                        self.map._base_key = None
                x += 74
            if gui.button(R(x, y, 30, 28), "DN", size=10, tip="Coverage altitude down ([)"):
                self._cov_alt(-1)
            gui.label((x + 34, y + 7), fmt_alt(th, self.map.cov_alt, False), 10, th.engraving)
            if gui.button(R(x + 104, y, 30, 28), "UP", size=10, tip="Coverage altitude up (])"):
                self._cov_alt(1)
        else:
            if gui.button(R(x, y, 34, 28), "<", size=12, tip="Previous radar (,)"):
                self._cycle_radar(-1)
            site = self.world.radars.get(self.scope.site_id)
            gui.label((x + 42, y + 6), site.name if site else "—", 12, th.engraving)
            if gui.button(R(x + 260, y, 34, 28), ">", size=12, tip="Next radar (.)"):
                self._cycle_radar(1)
            if gui.button(R(x + 304, y, 100, 28), "RANGE", size=11, tip="Cycle display range (R)"):
                self.scope.cycle_range(1)
        if self.world.faction == "US":
            if gui.button(R(988 - 124, y, 124, 28), "INITIATE (I)", size=11, lit=self.map.light_gun is not None,
                          tip="Initiate a track on returns at the light gun"):
                self.initiate()

    def _ticker(self, gui):
        th = self.theme
        w = self.world
        r = R(8, 868, W - 16, 28)
        gui.glass(r, (0, 0, 0))
        msgs = [m for m in w.messages if m.delivered][-2:]
        x = r.x + 8
        for m in msgs[-1:]:
            col = th.alert if m.priority >= 2 else th.lamp_blue if m.channel == "radio" else th.text
            txt = f"{clock(w, m.t_deliver)} {m.sender}: {m.text}"
            gui.label((x, r.y + 6), txt[:150], 12, col, "cyr" if w.faction == "USSR" else "ui")
        now = self.app.clock_t
        self.toasts = [t for t in self.toasts if t[0] > now]
        for i, (t_end, msg, col) in enumerate(reversed(self.toasts[-3:])):
            tr = R(996, 780 - i * 26, 596, 24)
            pygame.draw.rect(gui.screen, (0, 0, 0), tr, border_radius=3)
            pygame.draw.rect(gui.screen, col, tr, 1, border_radius=3)
            gui.label((tr.x + 8, tr.y + 4), msg[:84], 12, col)
        gui.label((W - 12, r.y + 7), f"{self.fps:3.0f} fps", 10, th.text_dim, align="right")

    def _menu(self, gui):
        th = self.theme
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 160))
        gui.screen.blit(s, (0, 0))
        inner = gui.panel(R(W // 2 - 200, 220, 400, 420), "MENU", "simulation paused")
        y = inner.y + 10
        for lab, fn in (("RESUME", lambda: setattr(self, "menu", False)), ("SAVE", self.app.save_game),
                        ("LOAD", self.app.load_game), ("MANUAL", lambda: self.app.push(ManualScene(self.app, self))),
                        ("AUTO-SLOW ON ALERTS: " + ("ON" if self.auto_slow else "OFF"),
                         lambda: setattr(self, "auto_slow", not self.auto_slow)),
                        ("SOUND: " + ("ON" if self.app.audio.volume > 0 else "OFF"), self.app.toggle_sound),
                        ("END SHIFT → DEBRIEF", self.end_shift), ("QUIT TO TITLE", self.app.to_title)):
            if gui.button(R(inner.x + 20, y, inner.w - 40, 36), lab, size=13):
                fn()
                if lab in ("SAVE", "END SHIFT → DEBRIEF"):
                    self.menu = False
            y += 44


# ====================================================================== DEBRIEF
class DebriefScene(Scene):
    def __init__(self, app, world):
        super().__init__(app)
        self.world = world
        self.theme = theme_for(world.faction)
        app.gui.set_theme(self.theme)
        self.rep = aar.build(world)
        self.map = MapView(world, self.theme, R(830, 84, 740, 560))
        self.snap_i = len(world.stats.truth_snaps) - 1
        self.tab = "summary"
        app.audio.play("tty")

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        w = self.world
        rep = self.rep
        screen.fill(th.bg)
        inner = gui.panel(R(14, 14, W - 28, H - 28), "AFTER-ACTION REPORT" if w.faction == "US" else
                          "РАЗБОР · AFTER-ACTION REVIEW", w.title)
        gui.label((inner.x + 4, inner.y + 2), f"{rep['grade']}", 30, th.accent if rep["score"] < rep["total"] * 0.55 else
                  th.ok, "ui_bold")
        gui.label((inner.x + 4, inner.y + 42), f"{rep['score']} / {rep['total']} points · {rep['reason']}", 14, th.engraving)
        x = inner.x + 520
        for t, lab in (("summary", "SUMMARY"), ("ident", "DETECTION & ID"), ("timeline", "TIMELINE")):
            if gui.button(R(x, inner.y + 6, 170, 30), lab, lit=self.tab == t):
                self.tab = t
            x += 174
        body = R(inner.x, inner.y + 70, 800, inner.h - 120)
        if self.tab == "summary":
            lines = []
            for o in rep["objectives"]:
                mark = {"done": "[+]", "failed": "[x]", "open": "[ ]"}[o["status"]]
                pen = f"  (−{o['penalty']})" if o["status"] == "failed" and o["penalty"] else ""
                lines.append((f"{mark} {o['text']} — {o['points']} pts{pen}  {o['t']}",
                              th.ok if o["status"] == "done" else th.alert))
            e = rep["expenditure"]
            c = rep["consequences"]
            cm = rep["command"]
            lines += [("", th.text), (f"Sorties {e['sorties']} · air-to-air shots {e['aam_shots']} · SAMs {e['sam_missiles']} · "
                                       f"tracks {e['tracks_initiated']} ({e['false_tracks']} false)", th.text),
                      (f"Civil losses {c['civil_losses']} · fratricide {c['fratricide']} · overdue acknowledgements "
                       f"{cm['unacked_overdue']} · reports to HQ {cm['reports_to_hq']} · HQ confidence {cm['hq_credibility']}",
                       th.text)]
            for k in c["kills"]:
                lines.append((f"  destroyed: {k['victim']} — by {k['by']}", th.accent))
            for rq in cm["requests"]:
                lines.append((f"  request {rq['kind']} {rq['ref']} at {rq['t']}: {'granted' if rq['granted'] else 'denied'} — "
                              f"{rq['reason']}", th.text_dim))
            gui.log("deb_s", body, lines, 13, "ui", follow=False)
        elif self.tab == "ident":
            rows = []
            for r in rep["identification"]:
                d = f"{r['id_delay_s'] / 60:.1f}m" if r["id_delay_s"] is not None else "—"
                rows.append([r["truth"][:40], r["first_track"], r["adiz"], r["first_id"], d, r["final_id"], r["vid"],
                             r["fate"]])
            gui.table("deb_id", R(body.x, body.y, body.w, 330), [("TRUTH (revealed)", 290), ("TRACK", 72), ("ADIZ", 72),
                                                                 ("ID", 72), ("DELAY", 56), ("FINAL", 100),
                                                                 ("VID", 72), ("FATE", 70)], rows, size=11)
            why = [(f"{r['truth']}: never tracked — {r['why_untracked']}", th.accent) for r in rep["identification"]
                   if r["why_untracked"]]
            gui.log("deb_why", R(body.x, body.y + 340, body.w, body.h - 340), why or
                    [("Every aircraft in the area was tracked at some point.", th.text)], 12)
        else:
            gui.log("deb_t", body, [(f"{e['t']} [{e['cat']}] {e['text']}", th.text) for e in rep["timeline"]], 12,
                    follow=False)
        # truth replay
        snaps = w.stats.truth_snaps
        mr = self.map.rect
        gui.glass(mr, (0, 0, 0))
        if self.map._base_key is None:
            self.map._base = self.map._build_base()
            self.map._base_key = 1
        screen.blit(self.map._base, mr.topleft)
        screen.set_clip(mr)
        if snaps:
            self.snap_i = max(0, min(self.snap_i, len(snaps) - 1))
            paths: dict[str, list] = {}
            sides = {}
            for t, acs, trs in snaps[: self.snap_i + 1]:
                for aid, x, y, alt, side, kind in acs:
                    paths.setdefault(aid, []).append(self.map.w2s(x, y))
                    sides[aid] = (side, kind)
            cols = {"blue": (120, 180, 255), "red": (255, 90, 80), "civil": (220, 220, 200), "neutral": (170, 170, 170)}
            for aid, pts in paths.items():
                side, kind = sides[aid]
                col = cols.get(side, (200, 200, 200)) if kind != "ghost" else (200, 120, 255)
                if len(pts) > 1:
                    pygame.draw.lines(screen, col, False, pts, 1)
            t, acs, trs = snaps[self.snap_i]
            for aid, x, y, alt, side, kind in acs:
                sx, sy = self.map.w2s(x, y)
                pygame.draw.circle(screen, cols.get(side, (200, 200, 200)), (sx, sy), 3)
                ac = w.aircraft.get(aid)
                gui.label((sx + 5, sy - 6), (ac.callsign if ac else aid)[:14], 10, cols.get(side, (200, 200, 200)))
            for tid, x, y, idn in trs:
                sx, sy = self.map.w2s(x, y)
                pygame.draw.rect(screen, th.id_colors.get(idn, th.text), (sx - 5, sy - 5, 10, 10), 1)
        screen.set_clip(None)
        gui.label((mr.x, mr.bottom + 6), "TRUTH REPLAY — lines: what really flew · squares: your tracks", 12, th.engraving)
        if snaps:
            sr = R(mr.x, mr.bottom + 28, mr.w, 22)
            pygame.draw.rect(screen, (0, 0, 0), sr)
            fx = sr.x + int(sr.w * self.snap_i / max(1, len(snaps) - 1))
            pygame.draw.rect(screen, th.accent, (fx - 4, sr.y, 8, sr.h))
            if gui.down and sr.collidepoint(gui.mouse):
                self.snap_i = int((gui.mouse[0] - sr.x) / sr.w * (len(snaps) - 1))
            gui.label((sr.right, sr.bottom + 4), f"T+{snaps[self.snap_i][0] // 60:.0f} min", 11, th.engraving, align="right")
        if gui.button(R(inner.right - 200, inner.bottom - 40, 200, 36), "BACK TO TITLE", size=13):
            self.app.to_title()
        if gui.button(R(inner.right - 410, inner.bottom - 40, 200, 36), "SAVE REPORT", size=13,
                      tip="Write the report as a text file in the saves folder."):
            p = self.app.save_dir() / f"aar_{w.scenario_id}.txt"
            p.write_text(aar.as_text(rep), encoding="utf-8")
            self.app.flash(f"Report written to {p}")
