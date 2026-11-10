"""Scenes: title & faction select, briefing, command center, after-action."""
from __future__ import annotations

import math

import pygame

from ..sim import aar, commands, doctrine, scenario, tracking
from ..sim.world import DT
from .lesson import CONSOLE_TABS, LessonCard
from .manual import ManualScene
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
MENU_ITEMS = [
    ("CAMPAIGN", "A career at the scopes: the historical watches of your service, 1956–1987, in order."),
    ("SCENARIOS", "Any historical watch, with its own briefing, forces and objectives."),
    ("ALERT DUTY", "A procedurally generated shift: your sector, any era, and whatever the night brings."),
    ("TRAINING", "Instructor-led exercises that teach the core loop of each system."),
    ("CONTINUE", "Resume the saved shift."),
    ("OPERATOR'S MANUAL", "How the radars, the identification rules and the weapons really work."),
    ("SETTINGS", "Panel engraving, phosphor focus, film grain, sound."),
    ("QUIT", "Leave the bunker."),
]


def film_item(gui, r: pygame.Rect, label: str, text: str, size: int = 26, selected: bool = False,
              enabled: bool = True, font: str = "title", top: int | None = None) -> bool:
    """A title-card menu entry: white letters on black, inverted on hover or when selected."""
    gui.drawn[label] = r
    hov = enabled and gui.hover(r)
    s = gui.screen
    if selected or hov:
        pygame.draw.rect(s, (236, 236, 230) if selected else (70, 70, 68), r)
        col = (12, 12, 12) if selected else (250, 250, 246)
    else:
        col = (226, 226, 220) if enabled else (90, 90, 88)
    ty = r.y + top if top is not None else r.centery - TEXT.font(font, size).get_height() // 2
    gui.label((r.x + 14, ty), text, size, col, font)
    return enabled and gui.clicked(r)


class TitleScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.faction = "US"
        self.items = scenario.list_scenarios()
        self.sel_id = ""
        self.t = 0.0
        self.frame = pygame.Surface((W, H))
        self.film = fx.Film((W, H), grain=22)
        self.backdrops: dict[str, object] = {}
        self.hover_note = ""
        self.theme = theme_for(self.faction)

    def backdrop(self):
        bd = self.backdrops.get(self.faction)
        if bd is None:
            from ..sim.world import theater
            from .cinema import Backdrop
            th = theater("gulf_of_maine" if self.faction == "US" else "middle_urals")
            bd = Backdrop((W, H), th, self.faction, board=(0.04, 0.07, 0.66, 0.60))
            self.backdrops[self.faction] = bd
        return bd

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        gui = self.app.gui
        th = theme_for(self.faction)
        self.theme = th
        gui.set_theme(th)
        bd = self.backdrop()
        bd.draw(self.frame, self.app.dt)
        f = self.frame
        # the title over the controllers' desk
        glow = TEXT.font("title", 96).render("SEARCH AND TRACK", True, (90, 90, 90), (0, 0, 0))
        for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            f.blit(glow, (54 + ox, 700 + oy), special_flags=pygame.BLEND_ADD)
        f.blit(TEXT.render("SEARCH AND TRACK", 96, (246, 246, 240), "title"), (54, 700))
        n = int(self.t * 26)
        sub = "ПОИСК И СОПРОВОЖДЕНИЕ  ·  A COLD WAR AIR-DEFENSE COMMAND SIMULATOR  ·  1956–1987"
        f.blit(TEXT.render(sub[:n], 18, (210, 210, 204), "eng"), (60, 828))
        f.blit(TEXT.render("Two systems. One sky. Every return could be the start of the war — or a lost Cessna.",
                           15, (160, 160, 156), "eng_r"), (60, 856))
        if self.app.settings.get("film", True):
            self.film.apply(f, self.app.dt, 0.07)
            ox, oy = self.film.weave()
        else:
            ox, oy = 0, 0
        screen.fill((0, 0, 0))
        screen.blit(f, (ox, oy))
        # ---- menu card
        card = R(1120, 70, 440, 640)
        sh = pygame.Surface(card.size, pygame.SRCALPHA)
        sh.fill((0, 0, 0, 214))
        screen.blit(sh, card.topleft)
        pygame.draw.rect(screen, (200, 200, 194), card, 1)
        pygame.draw.rect(screen, (200, 200, 194), card.inflate(-8, -8), 1)
        gui.label((card.x + 22, card.y + 18), "SELECT YOUR SERVICE", 14, (160, 160, 154), "eng")
        y = card.y + 44
        for fid, a, b in (("US", "UNITED STATES", "NORAD · AIR DEFENSE COMMAND"),
                          ("USSR", "СССР · SOVIET UNION", "ВОЙСКА ПВО СТРАНЫ · PVO STRANY")):
            r = R(card.x + 20, y, card.w - 40, 58)
            if film_item(gui, r, "SELECT " + ("NORAD" if fid == "US" else "ПВО"), a, 24, self.faction == fid, top=2):
                self.faction = fid
                self.app.audio.play("key")
            col = (60, 60, 58) if self.faction == fid else (150, 150, 146)
            gui.label((r.x + 16, r.y + 37), b, 13, col, "eng_r")
            y += 64
        y += 14
        pygame.draw.line(screen, (120, 120, 116), (card.x + 22, y), (card.right - 22, y))
        y += 14
        note = ""
        for key, desc in MENU_ITEMS:
            r = R(card.x + 20, y, card.w - 40, 44)
            enabled = key != "CONTINUE" or self.app.has_save()
            if gui.hover(r):
                note = desc
            if film_item(gui, r, key, key, 28, enabled=enabled):
                self._choose(key)
            y += 50
        if note:
            for i, ln in enumerate(TEXT.wrap(note, card.w - 50, 13, "eng_r")[:3]):
                gui.label((card.x + 24, card.bottom - 62 + i * 17), ln, 13, (176, 176, 170), "eng_r")
        gui.label((W - 20, H - 22), "v1.0 · GPL-3.0 · offline, no telemetry", 11, (110, 110, 106), "eng_r", "right")

    def _choose(self, key: str) -> None:
        app = self.app
        from .campaign import AlertDutyScene, CampaignScene
        app.campaign = None
        if key == "SCENARIOS":
            app.push(OperationsScene(app, self.faction, "scenario"))
        elif key == "TRAINING":
            app.push(OperationsScene(app, self.faction, "training"))
        elif key == "CAMPAIGN":
            app.push(CampaignScene(app, self.faction))
        elif key == "ALERT DUTY":
            app.push(AlertDutyScene(app, self.faction))
        elif key == "CONTINUE":
            app.load_game()
        elif key == "OPERATOR'S MANUAL":
            app.push(ManualScene(app, self))
        elif key == "SETTINGS":
            app.push(SettingsScene(app, self))
        elif key == "QUIT":
            app.running = False


# ====================================================================== OPERATIONS FILE
class OperationsScene(Scene):
    """Scenario selection laid out as an operations file on a desk: era tabs,
    index cards, and the dossier of the selected watch."""

    def __init__(self, app, faction: str, kind: str = "scenario"):
        super().__init__(app)
        self.faction = faction
        self.kind = kind
        self.theme = theme_for(faction)
        self.items = [s for s in scenario.list_scenarios() if s["faction"] == faction and
                      (s["kind"] == "training") == (kind == "training")]
        self.items.sort(key=lambda s: (s["start"], s["order"]))
        self.sel_id = self.items[0]["id"] if self.items else ""
        self.desk = None
        self.cache: dict[str, pygame.Surface] = {}
        app.audio.play("tty")

    def _desk(self) -> pygame.Surface:
        if self.desk is None:
            import numpy as np
            from .cinema import noise_surface
            n = noise_surface((W, H), 5.0, 31, scale=3) + noise_surface((W, H), 9.0, 32, scale=40)
            base = 30.0 if self.faction == "US" else 26.0
            arr = np.clip(base + n, 0, 255)
            tint = (1.0, 0.92, 0.8) if self.faction == "US" else (0.86, 0.9, 0.95)
            img = np.stack([arr * tint[0], arr * tint[1], arr * tint[2]], axis=2)
            self.desk = pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))
            self.desk.blit(fx.vignette((W, H), 200), (0, 0))
        return self.desk

    def _dossier(self, it) -> pygame.Surface:
        key = it["id"]
        if key not in self.cache:
            from .cinema import framed_photo, paper, photo, stamp
            pr = pygame.Surface((800, 760), pygame.SRCALPHA)
            pg = paper((780, 740), (232, 226, 206) if self.faction == "US" else (226, 222, 200), seed=len(key))
            pr.blit(pg, (10, 10))
            ink = (40, 34, 26)
            ru = self.faction == "USSR"
            head = "СОВЕРШЕННО СЕКРЕТНО" if ru else "SECRET"
            hs = TEXT.render(head, 16, (150, 30, 24), "eng")
            pr.blit(hs, (400 - hs.get_width() // 2, 28))
            if ru:
                ex = TEXT.render("Экз. № 1 · TOP SECRET", 11, (110, 40, 30), "eng_r")
                pr.blit(ex, (400 - ex.get_width() // 2, 48))
            title = TEXT.render(it["title"].upper(), 30, ink, "title")
            pr.blit(title, (44, 74))
            pr.blit(TEXT.render(it["subtitle"], 16, (80, 70, 56), "typewriter" if not ru else "cyr"), (46, 118))
            types = it["photo"] or []
            if types:
                cat = __import__("searchtrack.sim.world", fromlist=["catalog"]).catalog()
                tl = [(t, cat.aircraft[t].role if t in cat.aircraft else "") for t in types]
                img = photo(tl, (380, 250), seed=len(key) * 7, night=it.get("night", False))
                ph = framed_photo(img, it.get("photo_caption", ""), angle=-2.5)
                pr.blit(ph, (380, 150))
            body = TEXT.wrap(it["summary"], 320 if types else 700, 15, "typewriter" if not ru else "cyr")
            y = 160
            for ln in body[:16]:
                pr.blit(TEXT.render(ln, 15, ink, "typewriter" if not ru else "cyr"), (46, y))
                y += 21
            y = max(y, 470) + 10
            facts = [f"THEATER    {it['theater'].replace('_', ' ').upper()}",
                     f"DATE       {it['start'][:10]}",
                     f"DURATION   {it['duration_min']} MIN" + ("   NIGHT" if it.get("night") else ""),
                     f"OBJECTIVES {it['n_objectives']}",
                     f"DIFFICULTY {'■' * int(it['difficulty'])}{'□' * (4 - int(it['difficulty']))}"]
            for ln in facts:
                pr.blit(TEXT.render(ln, 15, ink, "cyr"), (46, y))
                y += 22
            st = stamp("ДЛЯ СЛУЖЕБНОГО" if ru else "OPERATIONS", (160, 32, 26), 26, -9,
                       "FOR OFFICIAL USE" if ru else "NORAD · ADC", seed=len(key))
            pr.blit(st, (520, 560))
            self.cache[key] = pr
        return self.cache[key]

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        gui.set_theme(th)
        screen.blit(self._desk(), (0, 0))
        hdr = ("ОПЕРАТИВНЫЕ ЗАДАЧИ · OPERATIONS FILE" if self.faction == "USSR" else "OPERATIONS FILE") + \
            ("  —  TRAINING" if self.kind == "training" else "")
        gui.label((60, 30), hdr, 30, (226, 220, 200), "title")
        y = 96
        last_era = None
        for it in self.items:
            era = it["era"] if self.kind != "training" else "TRAINING"
            if era != last_era:
                gui.label((62, y), era.upper(), 16, (180, 170, 150), "eng")
                y += 26
                last_era = era
            r = R(60, y, 520, 70)
            sel = it["id"] == self.sel_id
            gui.drawn["CARD " + it["id"]] = r
            pygame.draw.rect(screen, (0, 0, 0), r.move(3, 4))
            pygame.draw.rect(screen, (238, 232, 212) if sel else (206, 200, 180), r)
            pygame.draw.line(screen, (190, 120, 110), (r.x, r.y + 22), (r.right, r.y + 22))
            ink = (30, 26, 20)
            gui.label((r.x + 12, r.y + 2), it["start"][:10] + "  ·  " + it["theater"].replace("_", " ").upper(), 13,
                      (110, 60, 50), "eng")
            gui.label((r.x + 12, r.y + 26), it["title"], 22, ink, "title")
            gui.label((r.right - 12, r.y + 2), it["kind"].upper(), 12, (110, 60, 50), "eng", "right")
            if sel:
                pygame.draw.rect(screen, (200, 60, 40), r, 3)
            if gui.clicked(r):
                self.sel_id = it["id"]
            y += 80
        cur = next((s for s in self.items if s["id"] == self.sel_id), None)
        if cur is not None:
            d = self._dossier(cur)
            screen.blit(d, (640, 40))
            if gui.button(R(1280, 806, 260, 44), "BRIEFING >>", color=th.lamp_green, size=15):
                self.app.start_briefing(cur["id"])
        if gui.button(R(60, 820, 160, 40), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
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
def _desk_surface(faction: str, seed: int = 31) -> pygame.Surface:
    import numpy as np
    from .cinema import noise_surface
    n = noise_surface((W, H), 5.0, seed, scale=3) + noise_surface((W, H), 9.0, seed + 1, scale=40)
    base = 30.0 if faction == "US" else 26.0
    arr = np.clip(base + n, 0, 255)
    tint = (1.0, 0.92, 0.8) if faction == "US" else (0.86, 0.9, 0.95)
    img = np.stack([arr * tint[0], arr * tint[1], arr * tint[2]], axis=2)
    d = pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))
    d.blit(fx.vignette((W, H), 200), (0, 0))
    return d


class BriefingScene(Scene):
    def __init__(self, app, sid: str = "", world=None, meta: dict | None = None):
        super().__init__(app)
        self.world = world if world is not None else scenario.build_world(sid)
        self.meta = meta or next((s for s in scenario.list_scenarios() if s["id"] == self.world.scenario_id), {})
        self.theme = theme_for(self.world.faction)
        self.t = 0.0
        self.desk = _desk_surface(self.world.faction)
        self.orders = None
        self.extras = None
        app.audio.play("tty")

    def update(self, dt):
        self.t += dt

    def _orders_paper(self) -> pygame.Surface:
        from .cinema import paper, stamp
        w = self.world
        ru = w.faction == "USSR"
        pg = paper((860, 830), (234, 228, 208) if not ru else (228, 224, 202), seed=7)
        ink = (40, 34, 26)
        head = "СОВЕРШЕННО СЕКРЕТНО · TOP SECRET" if ru else "TOP SECRET — OPERATIONAL IMMEDIATE"
        t = TEXT.render(head, 16, (150, 30, 24), "eng")
        pg.blit(t, (430 - t.get_width() // 2, 18))
        pg.blit(TEXT.render(w.title.upper(), 34, ink, "title"), (40, 46))
        pg.blit(TEXT.render(w.theater.name, 15, (90, 80, 64), "eng_r"), (42, 94))
        pygame.draw.line(pg, (120, 100, 80), (40, 120), (820, 120), 1)
        st = stamp("СЕКРЕТНО" if ru else "SECRET", (160, 32, 26), 28, 7, "SECRET" if ru else "", seed=3)
        pg.blit(st, (640, 30))
        return pg

    def draw(self, screen):
        gui = self.app.gui
        gui.set_theme(self.theme)
        th = self.theme
        w = self.world
        ru = w.faction == "USSR"
        screen.blit(self.desk, (0, 0))
        if self.orders is None:
            self.orders = self._orders_paper()
        screen.blit(self.orders, (34, 30))
        n = int(self.t * 170)
        text = w.briefing.strip()
        shown = text[:n] + ("_" if n < len(text) and int(self.t * 4) % 2 == 0 else "")
        kind = th.doc_font
        gui.wrapped(R(74, 162, 790, 690), shown, 15, (40, 34, 26), kind, line_h=21, scroll_id="brief")
        # right column: photograph, situation map, objectives card
        if self.extras is None:
            from .cinema import framed_photo, photo, situation_map
            types = self.meta.get("photo") or []
            ph = None
            if types:
                tl = [(t, w.catalog.aircraft[t].role if t in w.catalog.aircraft else "") for t in types]
                ph = framed_photo(photo(tl, (300, 186), seed=len(w.scenario_id) * 3, night=w.weather.night),
                                  self.meta.get("photo_caption", ""), angle=3.0)
            self.extras = (ph, situation_map(w, (560, 330)))
        ph, smap = self.extras
        pygame.draw.rect(screen, (0, 0, 0), R(920, 60, 560, 330).move(4, 5))
        screen.blit(smap, (920, 60))
        gui.label((930, 36), "SITUATION MAP · OWN FORCES" if not ru else "КАРТА ОБСТАНОВКИ · OWN FORCES", 13,
                  (200, 192, 170), "eng")
        if ph is not None:
            screen.blit(ph, (1250, 140))
        card = R(920, 410, 640, 300)
        pygame.draw.rect(screen, (0, 0, 0), card.move(4, 5))
        pygame.draw.rect(screen, (238, 234, 216), card)
        for yy in range(card.y + 34, card.bottom, 22):
            pygame.draw.line(screen, (190, 200, 214), (card.x, yy), (card.right, yy))
        pygame.draw.line(screen, (210, 120, 110), (card.x + 26, card.y), (card.x + 26, card.bottom))
        gui.label((card.x + 34, card.y + 8), "ЗАДАЧИ · OBJECTIVES" if ru else "OBJECTIVES", 15, (120, 40, 30), "eng")
        y = card.y + 36
        for o in w.objectives:
            if o.hidden:
                continue
            for ln in TEXT.wrap(f"{o.text} ({o.points})", card.w - 44, 13, "eng_r"):
                if y > card.bottom - 20:
                    break
                gui.label((card.x + 34, y), ln, 13, (36, 32, 26), "eng_r")
                y += 18
            y += 4
        # forces strip
        fr = R(920, 724, 640, 58)
        forces = ", ".join(f"{sum(q.ready.values())}× {q.type_id} ({q.name})" for q in w.squadrons.values())
        types = {}
        for s in w.radars.values():
            types[s.type_id] = types.get(s.type_id, 0) + 1
        gui.label((fr.x, fr.y), "FORCES: " + forces[:110], 12, (200, 192, 170), "eng_r")
        gui.label((fr.x, fr.y + 18), "RADARS: " + ", ".join(f"{v}× {k}" for k, v in types.items())[:110], 12,
                  (200, 192, 170), "eng_r")
        if w.sams:
            stt = {}
            for s in w.sams.values():
                stt[s.type_id] = stt.get(s.type_id, 0) + 1
            gui.label((fr.x, fr.y + 36), "MISSILES: " + ", ".join(f"{v}× {k}" for k, v in stt.items()), 12,
                      (200, 192, 170), "eng_r")
        if gui.button(R(1260, 806, 300, 54), "TAKE THE WATCH >>", color=th.lamp_green, size=15):
            self.app.start_command(self.world)
        if gui.button(R(920, 812, 150, 44), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
            self.app.pop()


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
        self.lesson = LessonCard(self)
        self._ui_seen = (self.mode, self.ci, self.scope.site_id, False)
        self._lesson_key = (world.lesson.get("step"), world.lesson.get("final"))

    # ------------------------------------------------------------ helpers used by consoles
    def select(self, kind: str, oid: str) -> None:
        self.sel[kind] = oid
        if kind == "site" and oid in self.world.radars:
            self.scope.set_site(oid)

    def cmd(self, kind: str, /, **args):
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
        self.lesson.handle(gui)
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
            key = (w.lesson.get("step"), w.lesson.get("final"))
            if key != self._lesson_key:
                self._lesson_key = key
                if self.speed_i > 1:          # a new instruction: back to real time to read it
                    self.speed_i = 1
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
    def _ui_events(self) -> None:
        """Tell the instructor which displays and consoles the student has opened."""
        w = self.world
        now = (self.mode, self.ci, self.scope.site_id, bool(self.map.layers.get("coverage")))
        if w.lesson and now != self._ui_seen:
            if now[0] != self._ui_seen[0]:
                commands.run(w, "ui_event", name="mode_" + now[0])
            if now[1] != self._ui_seen[1]:
                commands.run(w, "ui_event", name="console_" + CONSOLE_TABS[now[1]].split()[0])
            if now[2] != self._ui_seen[2] or (now[0] == "scope" and now[0] != self._ui_seen[0]):
                commands.run(w, "ui_event", name="scope_" + now[2])
            if now[3] and not self._ui_seen[3]:
                commands.run(w, "ui_event", name="coverage")
        self._ui_seen = now

    def draw(self, screen):
        gui = self.app.gui
        w = self.world
        th = self.theme
        self._ui_events()
        gui.highlight = self.lesson.highlights(self)
        screen.fill(th.bg)
        self._topbar(gui)
        self._housing(gui)
        mr = self.map.rect
        if self.mode == "map":
            self.map.lang_mode = gui.lang_mode
            self.map.draw(screen, self.sel, self.render_t)
            self._finish_display(gui, mr)
            self.map.annotate(screen, self.sel)
            self.lesson.draw_mark(gui, self)
        elif self.mode == "scope":
            pygame.draw.rect(screen, (0, 0, 0), mr)
            self.scope.lang_mode = gui.lang_mode
            self.scope.draw(screen, min(self.render_t, w.t), self.app.dt, self.speed)
            self._finish_display(gui, mr, scan=False)
            self.lesson.draw_mark(gui, self)
        else:
            self.net.draw(gui, self.sel, self.app.dt)
            self._finish_display(gui, mr, scan=True, bloom=90)
        self._display_strip(gui)
        # console selector: a row of lamp keys
        names = CONSOLE_TABS
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
        self.lesson.draw(gui, self, MAP_R)
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
GRADE_RU = {"5 — EXCELLENT": ("ОТЛИЧНО", "EXCELLENT"), "4 — GOOD": ("ХОРОШО", "GOOD"),
            "3 — SATISFACTORY": ("УДОВЛЕТВОРИТЕЛЬНО", "SATISFACTORY"),
            "2 — UNSATISFACTORY": ("НЕУДОВЛЕТВОРИТЕЛЬНО", "UNSATISFACTORY")}


def headlines(world, rep) -> list[tuple[str, str]]:
    """(headline, standfirst) for the newspaper clipping: scenario-defined ones first."""
    out = []
    for hl in world.headlines:
        try:
            if scenario.cond(world, hl.get("cond", {"type": "time", "t": 0})):
                if world.faction == "USSR" and hl.get("text_ru"):
                    out.append((hl["text_ru"], hl.get("sub", "")))
                else:
                    out.append((hl["text"], hl.get("sub", "")))
        except (KeyError, TypeError):
            continue
    c = rep["consequences"]
    if not out:
        if c["civil_losses"]:
            out.append(("AIRLINER DOWN — AIR DEFENSE UNDER FIRE" if world.faction == "US" else
                        "ГИБЕЛЬ ПАССАЖИРСКОГО САМОЛЁТА", "A civil aircraft was lost during the watch. An inquiry has been ordered."))
        elif c["fratricide"]:
            out.append(("FRIENDLY FIRE OVER THE SECTOR" if world.faction == "US" else "ОГОНЬ ПО СВОИМ",
                        "Own aircraft were lost to own weapons. The commander has been summoned."))
        elif c["kills"]:
            out.append(("INTRUDER DESTROYED" if world.faction == "US" else "НАРУШИТЕЛЬ ГРАНИЦЫ УНИЧТОЖЕН",
                        f"{len(c['kills'])} aircraft destroyed during the watch."))
    return out


class DebriefScene(Scene):
    def __init__(self, app, world, on_done=None):
        super().__init__(app)
        self.world = world
        self.theme = theme_for(world.faction)
        app.gui.set_theme(self.theme)
        self.rep = aar.build(world)
        self.map = MapView(world, self.theme, R(874, 84, 690, 500))
        self.snap_i = 0
        self.playing = True
        self.play_t = 0.0
        self.tab = "summary"
        self.desk = _desk_surface(world.faction, 41)
        self.paper = None
        self.news = headlines(world, self.rep)
        self.on_done = on_done
        app.audio.play("tty")

    def update(self, dt):
        snaps = self.world.stats.truth_snaps
        if self.playing and snaps:
            self.play_t += dt
            if self.play_t > 0.05:
                self.play_t = 0.0
                self.snap_i += 1
                if self.snap_i >= len(snaps) - 1:
                    self.snap_i = len(snaps) - 1
                    self.playing = False

    def _paper(self):
        from .cinema import paper, stamp
        w = self.world
        rep = self.rep
        ru = w.faction == "USSR"
        pg = paper((800, 840), (234, 228, 208) if not ru else (228, 224, 202), seed=13)
        ink = (40, 34, 26)
        t = TEXT.render("РАЗБОР · AFTER-ACTION REVIEW" if ru else "AFTER-ACTION REPORT", 16, (150, 30, 24), "eng")
        pg.blit(t, (400 - t.get_width() // 2, 16))
        pg.blit(TEXT.render(w.title.upper(), 32, ink, "title"), (36, 40))
        pg.blit(TEXT.render(f"{rep['score']} / {rep['total']} points · {rep['reason']}", 15, (80, 70, 56), "eng_r"),
                (38, 86))
        g = rep["grade"]
        good = rep["score"] >= rep["total"] * 0.55
        col = (30, 60, 150) if good else (170, 30, 26)
        if ru:
            main, sub = GRADE_RU.get(g, (g, ""))
        else:
            main, sub = g, "EVALUATION"
        st = stamp(main, col, 30, -6, sub, seed=5)
        pg.blit(st, (790 - st.get_width(), 52))
        pygame.draw.line(pg, (120, 100, 80), (36, 120), (764, 120), 1)
        return pg

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        w = self.world
        rep = self.rep
        gui.set_theme(th)
        screen.blit(self.desk, (0, 0))
        if self.paper is None:
            self.paper = self._paper()
        screen.blit(self.paper, (30, 30))
        ink = (40, 34, 26)
        x = 62
        for t, lab in (("summary", "SUMMARY"), ("ident", "DETECTION & ID"), ("timeline", "TIMELINE")):
            if gui.button(R(x, 162, 200, 34), lab, lit=self.tab == t, size=12):
                self.tab = t
            x += 210
        body = R(66, 212, 740, 640)
        if self.tab == "summary":
            lines = []
            for o in rep["objectives"]:
                mark = {"done": "[+]", "failed": "[x]", "open": "[ ]"}[o["status"]]
                pen = f"  (−{o['penalty']})" if o["status"] == "failed" and o["penalty"] else ""
                lines.append((f"{mark} {o['text']} — {o['points']} pts{pen}  {o['t']}",
                              (30, 90, 40) if o["status"] == "done" else (150, 30, 24)))
            e = rep["expenditure"]
            c = rep["consequences"]
            cm = rep["command"]
            lines += [("", ink), (f"Sorties {e['sorties']} · air-to-air shots {e['aam_shots']} · SAMs {e['sam_missiles']} · "
                                  f"tracks {e['tracks_initiated']} ({e['false_tracks']} false)", ink),
                      (f"Civil losses {c['civil_losses']} · fratricide {c['fratricide']} · overdue acknowledgements "
                       f"{cm['unacked_overdue']} · reports to HQ {cm['reports_to_hq']} · HQ confidence {cm['hq_credibility']}",
                       ink)]
            for k in c["kills"]:
                lines.append((f"  destroyed: {k['victim']} — by {k['by']}", (150, 30, 24)))
            for rq in cm["requests"]:
                lines.append((f"  request {rq['kind']} {rq['ref']} at {rq['t']}: {'granted' if rq['granted'] else 'denied'} — "
                              f"{rq['reason']}", (90, 80, 64)))
            self._typed(gui, body, lines, "deb_s")
        elif self.tab == "ident":
            lines = [("TRUTH (REVEALED)                       TRACK  ADIZ   ID      DELAY  FINAL       VID   FATE", (120, 40, 30))]
            for r in rep["identification"]:
                d = f"{r['id_delay_s'] / 60:.1f}m" if r["id_delay_s"] is not None else "—"
                lines.append((f"{r['truth'][:38]:<38} {r['first_track']:<6} {r['adiz']:<6} {r['first_id']:<7} {d:<6} "
                              f"{r['final_id']:<11} {r['vid']:<5} {r['fate']}", ink))
            for r in rep["identification"]:
                if r["why_untracked"]:
                    lines.append((f"{r['truth']}: never tracked — {r['why_untracked']}", (150, 30, 24)))
            self._typed(gui, body, lines, "deb_id", kind="ui", size=11)
        else:
            self._typed(gui, body, [(f"{e['t']} [{e['cat']}] {e['text']}", ink) for e in rep["timeline"]], "deb_t", size=12)
        # ---- truth replay device
        mr = self.map.rect
        gui.glass(mr, (0, 0, 0))
        if self.map._base_key is None:
            self.map._base = self.map._build_base()
            self.map._base_key = 1
        screen.blit(self.map._base, mr.topleft)
        snaps = w.stats.truth_snaps
        screen.set_clip(mr)
        if snaps:
            self.snap_i = max(0, min(self.snap_i, len(snaps) - 1))
            paths: dict[str, list] = {}
            sides = {}
            for t, acs, trs in snaps[: self.snap_i + 1]:
                for aid, x, y, alt, side, kind in acs:
                    paths.setdefault(aid, []).append(self.map.w2s(x, y))
                    sides[aid] = (side, kind)
            cols = {"blue": (120, 180, 255), "red": (255, 90, 80), "civil": (230, 230, 210), "neutral": (170, 170, 170)}
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
        fx.bloom(screen, mr, 90)
        gui.crt_overlay(mr)
        gui.label((mr.x, mr.y - 30), "TRUTH REPLAY — lines: what really flew · squares: your tracks", 14,
                  (210, 202, 180), "eng")
        if snaps:
            sr = R(mr.x + 60, mr.bottom + 22, mr.w - 60, 22)
            pygame.draw.rect(screen, (0, 0, 0), sr.inflate(4, 4), border_radius=3)
            pygame.draw.rect(screen, (40, 38, 34), sr, border_radius=3)
            fxp = sr.x + int(sr.w * self.snap_i / max(1, len(snaps) - 1))
            pygame.draw.rect(screen, th.accent, (sr.x, sr.y + 8, fxp - sr.x, 6))
            pygame.draw.rect(screen, (230, 226, 210), (fxp - 5, sr.y - 2, 10, sr.h + 4), border_radius=2)
            if gui.down and sr.inflate(0, 10).collidepoint(gui.mouse):
                self.snap_i = int((gui.mouse[0] - sr.x) / sr.w * (len(snaps) - 1))
                self.playing = False
            gui.label((sr.right, sr.bottom + 6), f"T+{snaps[self.snap_i][0] // 60:.0f} min", 12, (210, 202, 180), "eng",
                      align="right")
            if gui.button(R(mr.x, mr.bottom + 16, 50, 34), "II" if self.playing else ">", lit=self.playing, size=12,
                          tip="Play / pause the replay"):
                self.playing = not self.playing
                if self.snap_i >= len(snaps) - 1:
                    self.snap_i = 0
        # ---- newspaper clipping
        if self.news:
            from .cinema import paper
            np_r = R(874, 650, 690, 150)
            pg = paper(np_r.size, (220, 214, 194), seed=21, age=1.4)
            screen.blit(pg, np_r.topleft)
            mast = "ВЕСТНИК ПВО" if w.faction == "USSR" else "THE MORNING SENTINEL"
            gui.label((np_r.centerx, np_r.y + 6), mast, 14, (60, 54, 44), "title_ru" if w.faction == "USSR" else "title",
                      "center")
            pygame.draw.line(screen, (60, 54, 44), (np_r.x + 10, np_r.y + 28), (np_r.right - 10, np_r.y + 28), 2)
            head, sub = self.news[0]
            fs = 34
            while fs > 18 and TEXT.width(head, fs, "title") > np_r.w - 30:
                fs -= 2
            gui.label((np_r.centerx, np_r.y + 34), head, fs, (24, 20, 16), "title", "center")
            if sub:
                gui.label((np_r.centerx, np_r.y + 44 + fs), sub[:110], 13, (60, 54, 44), "eng_r", "center")
        by = 818
        if self.on_done is not None:
            if gui.button(R(1310, by, 254, 44), "CONTINUE", color=th.lamp_green, size=14, tip="Back to the campaign"):
                self.on_done()
        else:
            if gui.button(R(1310, by, 254, 44), "BACK TO TITLE", size=13):
                self.app.to_title()
        if gui.button(R(874, by, 200, 44), "SAVE REPORT", size=13,
                      tip="Write the report as a text file in the saves folder."):
            p = self.app.save_dir() / f"aar_{w.scenario_id}.txt"
            p.write_text(aar.as_text(rep), encoding="utf-8")
            self.app.flash(f"Report written to {p}")

    def _typed(self, gui, r, lines, sid, kind="eng_r", size=14):
        wrapped = []
        for text, col in lines:
            for ln in TEXT.wrap(text, r.w - 10, size, kind):
                wrapped.append((ln, col))
        lh = size + 6
        off = gui._scroll(sid, r, len(wrapped) * lh)
        gui.screen.set_clip(r)
        y = r.y - off
        for ln, col in wrapped:
            if r.y - lh <= y <= r.bottom:
                gui.label((r.x, y), ln, size, col, kind)
            y += lh
        gui.screen.set_clip(None)
