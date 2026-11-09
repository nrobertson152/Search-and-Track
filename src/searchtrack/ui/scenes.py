"""Scenes: title & faction select, briefing, command center, after-action."""
from __future__ import annotations

import math

import pygame

from ..sim import aar, commands, doctrine, scenario, tracking
from ..sim.world import DT
from .consoles import (CommsConsole, IntelConsole, MissilesConsole, RadarNetConsole, StatusConsole, TECH_NOTES,
                       TracksConsole, WeaponsConsole)
from . import fx
from .fx import scanlines, vignette
from .mapview import MapView, clock, fmt_alt
from .netboard import NetBoard
from .scope import Scope
from .theme import TEXT, US, USSR, theme_for

R = pygame.Rect
W, H = 1600, 900
SPEEDS = [0, 1, 2, 4, 8, 16, 32]
HOUSING_R = R(4, 56, 990, 808)          # the main display console
MAP_R = R(22, 70, 954, 690)             # its tube
CONSOLE_R = R(1000, 94, 596, 770)       # the operator console on the right
TICKER_R = R(8, 870, 1584, 26)

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


# ====================================================================== SETTINGS
class SettingsScene(Scene):
    def __init__(self, app, back):
        super().__init__(app)
        self.back = back
        self.theme = getattr(back, "theme", app.gui.theme)

    def draw(self, screen):
        gui = self.app.gui
        th = gui.theme
        st = self.app.settings
        screen.fill(th.bg)
        inner = gui.panel(R(W // 2 - 360, 130, 720, 600), "SETTINGS", "stored in your data folder")
        y = inner.y + 16
        rows = [
            ("Soviet panel engraving", "labels", [("ru+en", "RUSSIAN + ENGLISH STRIP"), ("ru", "RUSSIAN ONLY"),
                                                   ("en", "ENGLISH")],
             "Cosmetic only: orders, radio, tooltips and the manual are always in English."),
            ("Phosphor focus (default)", "focus", [(0, "SHARP"), (1, "SOFT"), (2, "GLOW"), (3, "BLOOM")],
             "How much the display tubes bloom. SHARP is the fastest."),
            ("Film look on title and briefings", "film", [(True, "FILM GRAIN ON"), (False, "OFF")],
             "Black-and-white newsreel grain, dust and flicker."),
            ("Sound volume", "volume", [(0.0, "MUTE"), (0.35, "LOW"), (0.7, "NORMAL"), (1.0, "LOUD")],
             "Synthesized relays, teleprinters, klaxons and radio."),
        ]
        for title, key, opts, note in rows:
            gui.eng((inner.x + 10, y), title.upper(), 14, strip=False)
            gui.label((inner.x + 10, y + 22), note, 12, th.engraving_dim, "eng_r")
            x = inner.x + 10
            bw = (inner.w - 20) // len(opts) - 6
            for val, lab in opts:
                if gui.button(R(x, y + 44, bw, 34), lab, lit=st.get(key) == val, size=11):
                    st[key] = val
                    if key == "labels":
                        gui.lang_mode = val
                    elif key == "volume":
                        self.app.audio.volume = val
                    self.app.save_settings()
                x += bw + 6
            y += 112
        if gui.button(R(inner.right - 180, inner.bottom - 46, 170, 38), "BACK", size=13) or \
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
        self.map = MapView(world, self.theme, MAP_R.copy())
        self.scope = Scope(world, self.theme, MAP_R.copy())
        self.net = NetBoard(world, self.theme, MAP_R.copy())
        self.mode = "map"
        st = getattr(app, "settings", {})
        self.brightness = 1.0
        self.focus_i = int(st.get("focus", 2))
        self.bloom = [0, 70, 120, 170][self.focus_i]
        self.room = fx.room_light((W, H), self.theme.room_tint, 0.9)
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
                self.mode = {"map": "scope", "scope": "net", "net": "map"}[self.mode]
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
        if self.mode == "net":
            if gui.released and not gui.consumed and self.net.rect.collidepoint(gui.mouse):
                hit = self.net.pick(gui.mouse)
                if hit:
                    gui.consumed = True
                    kind, oid = hit
                    if kind == "site":
                        self.select("site", oid)
                        self.ci = 3
                    elif kind == "sam":
                        self.select("sam", oid)
                        self.ci = 2
                    elif kind == "squadron":
                        self.consoles[1].sq = oid
                        self.ci = 1
                    self.audio.play("click")
        elif self.mode == "map":
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
        self._topbar(gui)
        self._housing(gui)
        mr = self.map.rect
        if self.mode == "map":
            self.map.draw(screen, self.sel, self.render_t)
            self._finish_display(gui, mr)
            self.map.annotate(screen, self.sel)
        elif self.mode == "scope":
            pygame.draw.rect(screen, (0, 0, 0), mr)
            self.scope.lang_mode = gui.lang_mode
            self.scope.draw(screen, min(self.render_t, w.t), self.app.dt, self.speed)
            self._finish_display(gui, mr, scan=False)
        else:
            self.net.draw(gui, self.sel, self.app.dt)
            self._finish_display(gui, mr, scan=True, bloom=90)
        self._display_strip(gui)
        # console selector: a row of lamp keys
        names = ["TRACKS F1", "WEAPONS F2", "MISSILES F3", "RADAR F4", "COMMS F6", "INTEL F7", "STATUS F8"]
        bw = 596 // len(names)
        unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
        for i, n in enumerate(names):
            lit = i == self.ci
            lab = n if not (i == 4 and unacked) else f"COMMS !{unacked}"
            if gui.button(R(1000 + i * bw, 58, bw - 4, 30), lab, lit=lit, size=11,
                          color=th.lamp_red if (i == 4 and unacked and not lit) else None):
                self.ci = i
        self.consoles[self.ci].draw(gui, CONSOLE_R, self)
        self._ticker(gui)
        screen.blit(self.room, (0, 0))
        if self.menu:
            self._menu(gui)

    def _finish_display(self, gui, r, scan: bool = True, bloom: int | None = None) -> None:
        g = self.bloom if bloom is None else bloom
        if self.brightness != 1.0:
            k = int(255 * max(0.3, min(1.0, self.brightness)))
            gui.screen.fill((k, k, k), special_flags=pygame.BLEND_MULT, rect=r)
        if g > 0:
            fx.bloom(gui.screen, r, gain=int(g * max(0.5, self.brightness)))
        gui.crt_overlay(r, scan=scan, strength=1.0)
        # rounded tube corners
        pygame.draw.rect(gui.screen, (0, 0, 0), r.inflate(8, 8), 6, border_radius=18)

    def _housing(self, gui) -> None:
        th = self.theme
        s = gui.screen
        hr = HOUSING_R
        mr = self.map.rect
        surf = gui.cached(("housing", th.name, hr.w, hr.h), lambda: self._housing_surface(gui, hr, mr))
        s.blit(surf, hr.topleft)
        pygame.draw.rect(s, (0, 0, 0), mr)

    def _housing_surface(self, gui, hr, mr) -> pygame.Surface:
        th = self.theme
        S = pygame.Surface(hr.size, pygame.SRCALPHA)
        body = R(0, 0, hr.w, hr.h)
        rad = 16 if th.panel_style == "plastic" else 8
        pygame.draw.rect(S, th.bezel_lo, body, border_radius=rad)
        inner = body.inflate(-4, -4)
        g = pygame.Surface(inner.size, pygame.SRCALPHA)
        for y in range(inner.h):
            c = tuple(int(th.bezel_hi[k] + (th.bezel[k] - th.bezel_hi[k]) * min(1.0, y / 120.0)) for k in range(3))
            if y > inner.h - 90:
                c = tuple(int(v * (0.92 + 0.08 * (inner.h - y) / 90.0)) for v in c)
            pygame.draw.line(g, c, (0, y), (inner.w, y))
        m = pygame.Surface(inner.size, pygame.SRCALPHA)
        pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=rad - 2)
        g.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        S.blit(g, inner.topleft)
        # fine speckle
        rng = __import__("random").Random(5)
        for _ in range(hr.w * hr.h // 60):
            x, y = rng.randrange(4, hr.w - 4), rng.randrange(4, hr.h - 4)
            v = rng.choice((-10, -6, 6, 10))
            c = S.get_at((x, y))
            S.set_at((x, y), (max(0, min(255, c[0] + v)), max(0, min(255, c[1] + v)), max(0, min(255, c[2] + v)), c[3]))
        # screen recess
        rec = R(mr.x - hr.x, mr.y - hr.y, mr.w, mr.h)
        pygame.draw.rect(S, th.bezel_lo, rec.inflate(22, 22), border_radius=20)
        pygame.draw.rect(S, (14, 14, 12), rec.inflate(12, 12), border_radius=18)
        pygame.draw.rect(S, (0, 0, 0), rec.inflate(4, 4), border_radius=16)
        pygame.draw.line(S, th.bezel_hi, (rec.x - 6, rec.bottom + 11), (rec.right + 6, rec.bottom + 11), 1)
        # control strip below the tube
        strip = R(10, rec.bottom + 16, hr.w - 20, hr.h - rec.bottom - 24)
        pygame.draw.rect(S, th.bezel_lo, strip, border_radius=6)
        pygame.draw.rect(S, tuple(max(0, v - 18) for v in th.bezel), strip.inflate(-4, -4), border_radius=5)
        # corner screws
        for cx, cy in ((12, 12), (hr.w - 13, 12), (12, hr.h - 13), (hr.w - 13, hr.h - 13)):
            pygame.draw.circle(S, (0, 0, 0), (cx + 1, cy + 1), 5)
            pygame.draw.circle(S, tuple(min(255, v + 30) for v in th.bezel_hi), (cx, cy), 4)
            pygame.draw.line(S, th.bezel_lo, (cx - 3, cy), (cx + 3, cy), 1)
        # model plate on the top edge
        if self.world.faction == "US":
            txt = "AN/FSQ-7 · SITUATION DISPLAY CONSOLE OA-1008"
            col_bg, col_fg = (16, 15, 14), (230, 226, 210)
        else:
            txt = "ПЛАНШЕТ ОБСТАНОВКИ · ИКО · МНЕМОСХЕМА"
            col_bg, col_fg = (30, 34, 38), (230, 232, 226)
        t = __import__("searchtrack.ui.theme", fromlist=["TEXT"]).TEXT.render(txt, 11, col_fg, "eng")
        pr = R(hr.w // 2 - t.get_width() // 2 - 10, 1, t.get_width() + 20, 9)
        plate = R(pr.x, 0, pr.w, 10)
        pygame.draw.rect(S, col_bg, plate.inflate(0, 0).move(0, 0), border_radius=2)
        S.blit(t, (plate.x + 10, plate.y - 3))
        return S

    def _topbar(self, gui):
        w = self.world
        th = self.theme
        s = gui.screen
        bar = R(0, 0, W, 54)
        gui.panel(bar, screws=False)
        # unit nameplate
        if w.faction == "US":
            plate = R(10, 7, 520, 40)
            pygame.draw.rect(s, (0, 0, 0), plate.move(1, 2), border_radius=3)
            pygame.draw.rect(s, th.plate, plate, border_radius=3)
            pygame.draw.line(s, (74, 70, 64), (plate.x + 3, plate.y + 1), (plate.right - 4, plate.y + 1))
            gui.label((plate.x + 12, plate.y + 2), th.title, 15, th.plate_text, "eng")
            gui.label((plate.x + 12, plate.y + 21), f"{w.title.upper()} — {th.subtitle}", 11, (170, 166, 156), "eng_r")
            for sx in (plate.x + 5, plate.right - 6):
                pygame.draw.circle(s, (120, 116, 108), (sx, plate.centery), 2)
        else:
            gui.label((14, 5), th.title, 17, th.engraving, "eng", shadow=True)
            gui.label((14, 28), f"{w.title.upper()} — {th.subtitle}", 11, th.engraving_dim, "eng_r")
        # clock
        hh = clock(w, self.render_t)
        secs = int(self.render_t) % 60
        led = (255, 64, 36) if w.faction == "USSR" else (255, 120, 40)
        cr = R(542, 8, 196, 38)
        gui.led(cr, f"{hh}:{secs:02d}", led, 28)
        tz = "МСК" if (w.faction == "USSR" and gui.lang_mode != "en") else w.clock_tz
        sub = R(cr.right + 8, cr.y, 40, 38)
        pygame.draw.rect(gui.screen, (0, 0, 0), sub.inflate(4, 4), border_radius=3)
        gui.label((sub.centerx, sub.y + 1), tz, 12, led, "eng", "center")
        gui.label((sub.centerx, sub.y + 19), f"+{int(self.render_t // 60):02d}", 12, tuple(v // 2 for v in led), "crt",
                  "center")
        # time compression keys
        x = 784
        for i, sp in enumerate(SPEEDS):
            lab = "II" if sp == 0 else f"{sp}×"
            if gui.button(R(x, 10, 38, 34), lab, lit=self.speed_i == i, size=12,
                          tip="Pause" if sp == 0 else f"Time compression {sp}×"):
                self.speed_i = i
            x += 41
        x += 10
        hq = w.hq
        unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
        tiles = []
        if w.faction == "US":
            tiles.append(("DEFCON\n" + hq.readiness.replace("DEFCON", "").strip(), th.lamp_white, True, False,
                          "Defense readiness condition"))
            adw = {"WHITE": th.lamp_white, "YELLOW": th.lamp_amber, "RED": th.lamp_red}.get(hq.alert, th.lamp_white)
            tiles.append((f"ADW\n{hq.alert}", adw, True, hq.alert == "RED", "Air Defense Warning (set by NORAD Region)"))
        else:
            rd = {"FULL": "ПОЛНАЯ", "INCREASED": "ПОВЫШ.", "CONSTANT": "ПОСТОЯН."}.get(hq.readiness, hq.readiness)
            tiles.append((("БГ\n" + rd) if gui.lang_mode != "en" else f"READY\n{hq.readiness}",
                          th.lamp_red if hq.readiness == "FULL" else th.lamp_amber, True, False,
                          f"Combat readiness: {hq.readiness}"))
        ws = hq.weapons_status
        wcol = {"HOLD": th.lamp_green, "TIGHT": th.lamp_amber, "FREE": th.lamp_red}.get(ws, th.lamp_white)
        if w.faction == "USSR" and gui.lang_mode != "en":
            wl = {"HOLD": "ОГОНЬ\nЗАПРЕЩЁН", "TIGHT": "ОГОНЬ\nОГРАНИЧЕН", "FREE": "ОГОНЬ\nРАЗРЕШЁН"}.get(ws, ws)
        else:
            wl = f"WEAPONS\n{ws}"
        tiles.append((wl, wcol, True, ws == "FREE", f"Weapons control status: {ws} (set by higher authority)"))
        if w.faction == "US":
            up = w.c2_up()
            side = next((sd for sd, v in w.duplex.items() if v == "active"), "-")
            tiles.append((f"FSQ-7\n{side} ON LINE" if up else "FSQ-7\nOFF LINE", th.lamp_green if up else th.lamp_red,
                          True, not up, "AN/FSQ-7 duplex computer (RADAR console)"))
        else:
            down = sum(1 for ln in w.links.values() if not ln.up)
            tiles.append((("СВЯЗЬ\nНОРМА" if not down else f"ОБРЫВ\nЛИНИЙ {down}") if gui.lang_mode != "en" else
                          ("LINES\nOK" if not down else f"LINES\nDOWN {down}"),
                          th.lamp_green if not down else th.lamp_red, True, bool(down), "Telephone and telegraph lines"))
        ack_l = (f"КВИТ.\n{unacked}" if (w.faction == "USSR" and gui.lang_mode != "en") else f"ACK\n{unacked}")
        tiles.append((ack_l, th.lamp_red, unacked > 0, unacked > 0, "Messages awaiting acknowledgement (A)"))
        tw = (W - 96 - x) // len(tiles)
        for lab, col, on, blink, tip in tiles:
            gui.annunciator(R(x, 9, tw - 8, 36), lab, col, on, blink, tip=tip, size=11)
            x += tw
        if gui.button(R(W - 88, 10, 78, 34), "MENU", size=12, tip="Esc"):
            self.menu = True

    def _display_strip(self, gui):
        th = self.theme
        w = self.world
        mr = self.map.rect
        y = mr.bottom + 18
        x = mr.x
        modes = (("map", "SITUATION" if w.faction == "US" else "BOARD"), ("scope", "RADAR SCOPE"), ("net", "NETWORK"))
        for m, lab in modes:
            if gui.button(R(x, y, 112, 30), lab, lit=self.mode == m, size=11,
                          tip="M cycles the display: situation / radar scope / network board"):
                self.mode = m
            x += 116
        x += 14
        if self.mode == "map":
            lay = self.map.layers
            for key, lab, tip in (("coverage", "COVERAGE", "Predicted radar coverage at the selected altitude (C)"),
                                  ("raw", "RAW", "Unassociated radar returns"), ("zones", "ZONES", "ADIZ & defended areas"),
                                  ("labels", "LABELS", "Names on the display"), ("history", "HISTORY", "Track history"),
                                  ("rings", "RINGS", "Range rings of the selected radar and SAM engagement rings")):
                if key == "raw" and w.faction != "US":
                    continue
                if gui.button(R(x, y, 76, 30), lab, lit=lay[key], size=10, tip=tip):
                    lay[key] = not lay[key]
                    if key in ("zones", "labels"):
                        self.map._base_key = None
                x += 79
        elif self.mode == "scope":
            if gui.button(R(x, y, 34, 30), "<", size=12, tip="Previous radar (,)"):
                self._cycle_radar(-1)
            site = w.radars.get(self.scope.site_id)
            nm = (site.name_ru if (site and w.faction == "USSR" and site.name_ru and gui.lang_mode != "en") else
                  (site.name if site else "—"))
            win = R(x + 40, y + 2, 230, 26)
            gui.readout(win, [nm[:30]], 12)
            if gui.button(R(x + 276, y, 34, 30), ">", size=12, tip="Next radar (.)"):
                self._cycle_radar(1)
            if gui.button(R(x + 318, y, 96, 30), "RANGE", size=11, tip="Cycle display range (R)"):
                self.scope.cycle_range(1)
        else:
            gui.label((x, y + 6), "click a node to select it on the consoles", 12, th.housing_ink_dim, "eng_r")
        # second row: power and overload lamps, brightness and focus, coverage altitude, light gun
        y2 = y + 40
        x = mr.x + 4
        gui.lamp((x + 6, y2 + 9), th.lamp_green, True, radius=5)
        gui.eng((x + 16, y2 + 1), "POWER", 11, color=th.housing_ink, strip=False)
        nt = sum(1 for t in w.tracks.values() if not t.lost)
        over = nt > 18 or any(w.active_jammers(st) for st in list(w.radars.values())[:12])
        gui.lamp((x + 6, y2 + 27), th.lamp_red, over, radius=5, blink=over,
                 tip="Overload: heavy track load or jamming on the network")
        gui.eng((x + 16, y2 + 19), "OVERLOAD", 11, color=th.housing_ink, strip=False)
        x += 110
        k = gui.knob(R(x, y2, 150, 36), "BRIGHTNESS", f"{self.brightness * 100:.0f}%",
                     tip="Display brightness", pos=(self.brightness - 0.4) / 0.6, ink=th.housing_ink)
        if k:
            self.brightness = max(0.4, min(1.0, self.brightness + 0.1 * k))
        x += 160
        k = gui.knob(R(x, y2, 150, 36), "FOCUS", ["SHARP", "SOFT", "GLOW", "BLOOM"][self.focus_i],
                     tip="Spot focus: how much the phosphor blooms", pos=self.focus_i / 3, ink=th.housing_ink)
        if k:
            self.focus_i = max(0, min(3, self.focus_i + k))
            self.bloom = [0, 70, 120, 170][self.focus_i]
        x += 170
        if self.mode == "map":
            if gui.button(R(x, y2 + 2, 40, 30), "DN", size=10, tip="Coverage altitude down ([)"):
                self._cov_alt(-1)
            gui.readout(R(x + 46, y2 + 4, 84, 26), [fmt_alt(th, self.map.cov_alt, False)], 12)
            if gui.button(R(x + 136, y2 + 2, 40, 30), "UP", size=10, tip="Coverage altitude up (])"):
                self._cov_alt(1)
        if w.faction == "US":
            if gui.button(R(mr.right - 150, y2 + 2, 150, 30), "INITIATE (I)", size=11, lit=self.map.light_gun is not None,
                          tip="Initiate a track on returns at the light gun"):
                self.initiate()

    def _ticker(self, gui):
        th = self.theme
        w = self.world
        r = TICKER_R
        s = gui.screen
        msgs = [m for m in w.messages if m.delivered][-1:]
        if w.faction == "US":
            pygame.draw.rect(s, (0, 0, 0), r.inflate(4, 4).move(0, 1), border_radius=2)
            pygame.draw.rect(s, (232, 222, 178), r)
            for xx in range(r.x + 6, r.right, 14):
                pygame.draw.circle(s, (200, 190, 150), (xx, r.y + 3), 1)
            for m in msgs:
                col = (150, 30, 20) if m.priority >= 2 else (40, 34, 26)
                txt = f"{clock(w, m.t_deliver)}  {m.sender}: {m.text}"
                gui.label((r.x + 10, r.y + 5), txt[:150].upper(), 13, col, "typewriter")
        else:
            gui.glass(r, (4, 4, 3), bezel=False)
            for m in msgs:
                col = th.alert if m.priority >= 2 else th.lamp_blue if m.channel == "radio" else th.text
                txt = f"{clock(w, m.t_deliver)} {m.sender}: {m.text}"
                gui.label((r.x + 10, r.y + 5), txt[:160], 12, col, "cyr")
            gui.crt_overlay(r, strength=0.5)
        now = self.app.clock_t
        self.toasts = [t for t in self.toasts if t[0] > now]
        for i, (t_end, msg, col) in enumerate(reversed(self.toasts[-3:])):
            tr = R(1000, CONSOLE_R.bottom - 36 - i * 30, 596, 26)
            pygame.draw.rect(s, (0, 0, 0), tr.move(2, 3), border_radius=3)
            pygame.draw.rect(s, (16, 16, 14), tr, border_radius=3)
            pygame.draw.rect(s, col, tr, 1, border_radius=3)
            gui.label((tr.x + 10, tr.y + 5), msg[:84], 12, col)
        gui.label((W - 12, r.y + 7), f"{self.fps:3.0f} fps", 10, (120, 110, 90) if w.faction == "US" else th.text_dim,
                  align="right")

    def _menu(self, gui):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 170))
        gui.screen.blit(s, (0, 0))
        inner = gui.panel(R(W // 2 - 210, 190, 420, 480), "MENU", "simulation paused")
        y = inner.y + 12
        for lab, fn in (("RESUME", lambda: setattr(self, "menu", False)), ("SAVE", self.app.save_game),
                        ("LOAD", self.app.load_game),
                        ("OPERATOR'S MANUAL", lambda: self.app.push(ManualScene(self.app, self))),
                        ("SETTINGS", lambda: self.app.push(SettingsScene(self.app, self))),
                        ("AUTO-SLOW ON ALERTS: " + ("ON" if self.auto_slow else "OFF"),
                         lambda: setattr(self, "auto_slow", not self.auto_slow)),
                        ("SOUND: " + ("ON" if self.app.audio.volume > 0 else "OFF"), self.app.toggle_sound),
                        ("END SHIFT → DEBRIEF", self.end_shift), ("QUIT TO TITLE", self.app.to_title)):
            if gui.button(R(inner.x + 24, y, inner.w - 48, 38), lab, size=13,
                          color=gui.theme.lamp_red if lab.startswith(("END", "QUIT")) else None):
                fn()
                if lab in ("SAVE", "END SHIFT → DEBRIEF"):
                    self.menu = False
            y += 46


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
