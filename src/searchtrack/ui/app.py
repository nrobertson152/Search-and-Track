"""Application shell: window, main loop, scene stack, save/load."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pygame

from ..sim import autoplay, scenario
from ..sim.world import load_json, save_json
from .audio import Audio
from .gui import Gui
from .theme import US, theme_for

W, H = 1600, 900


def data_home() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "searchtrack"


class App:
    def __init__(self, headless: bool = False, sound: bool = True, fullscreen: bool = False):
        pygame.init()
        from .theme import FONT_DIR, TEXT
        TEXT._fonts.clear()       # fonts die with pygame.quit(); start clean
        TEXT._cache.clear()
        pygame.display.set_caption("Search and Track — Cold War Air Defense")
        icon = FONT_DIR.parent / "icons" / "searchtrack-64.png"
        if icon.exists() and not headless:
            try:
                pygame.display.set_icon(pygame.image.load(str(icon)))
            except pygame.error:
                pass
        flags = 0 if headless else (pygame.SCALED | pygame.RESIZABLE | (pygame.FULLSCREEN if fullscreen else 0))
        try:
            self.screen = pygame.display.set_mode((W, H), flags, vsync=0 if headless else 1)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H), flags)
        self.settings = self.load_settings()
        self.audio = Audio(enabled=sound and not headless)
        self.audio.volume = float(self.settings.get("volume", 0.7))
        self.gui = Gui(self.screen, US, self.audio)
        self.gui.lang_mode = "en"     # every console and screen is in English; only the PVO board is lettered in Russian
        self.scenes: list = []
        self.campaign = None          # faction whose career the current watch belongs to
        self.running = True
        self.clock = pygame.time.Clock()
        self.clock_t = 0.0
        self.dt = 0.016
        from .scenes import TitleScene
        self.push(TitleScene(self))

    # ------------------------------------------------------------ scenes
    @property
    def scene(self):
        return self.scenes[-1]

    def push(self, s) -> None:
        self.scenes.append(s)

    def pop(self) -> None:
        if len(self.scenes) > 1:
            self.scenes.pop()
            th = getattr(self.scene, "theme", None)
            if th is not None:
                self.gui.set_theme(th)

    def replace_all(self, s) -> None:
        self.scenes = [self.scenes[0], s]

    def start_briefing(self, sid: str) -> None:
        from .scenes import BriefingScene
        self.push(BriefingScene(self, sid))

    def start_command(self, world) -> None:
        from .scenes import CommandScene
        self.replace_all(CommandScene(self, world))
        self.audio.play("buzz")

    def start_debrief(self, world) -> None:
        from .campaign import record_result
        from .scenes import DebriefScene
        on_done = (lambda f=world.faction: self.back_to_campaign(f)) if self.campaign else None
        d = DebriefScene(self, world, on_done=on_done)
        if not world.scenario_id.startswith("alert_"):
            record_result(self, world, d.rep)
        self.replace_all(d)

    def back_to_campaign(self, faction: str) -> None:
        from .campaign import CampaignScene
        self.to_title()
        self.push(CampaignScene(self, faction))

    def to_title(self) -> None:
        self.scenes = self.scenes[:1]
        self.gui.set_theme(theme_for(self.scenes[0].faction))

    # ------------------------------------------------------------ persistence
    DEFAULTS = {"board": "ru", "volume": 0.7, "music": 0.5, "focus": 2, "film": True, "auto_slow": True,
                "difficulty": "regular"}

    def load_settings(self) -> dict:
        st = dict(self.DEFAULTS)
        try:
            st.update(json.loads((data_home() / "settings.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        return st

    def save_settings(self) -> None:
        try:
            data_home().mkdir(parents=True, exist_ok=True)
            (data_home() / "settings.json").write_text(json.dumps(self.settings, indent=1), encoding="utf-8")
        except OSError:
            pass

    def save_dir(self) -> Path:
        d = data_home() / "saves"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def has_save(self) -> bool:
        return (data_home() / "saves" / "quicksave.json").exists()

    def save_game(self) -> None:
        from .scenes import CommandScene
        sc = self.scene
        if not isinstance(sc, CommandScene):
            return
        p = self.save_dir() / "quicksave.json"
        p.write_text(save_json(sc.world), encoding="utf-8")
        sc.toast(f"Saved: {p.name} (T+{sc.world.t / 60:.0f} min)")

    def load_game(self) -> None:
        p = data_home() / "saves" / "quicksave.json"
        if not p.exists():
            self.flash("No saved shift")
            return
        try:
            world = load_json(p.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as e:
            self.flash(f"Save could not be loaded: {e}")
            return
        self.start_command(world)
        self.scene.render_t = world.t
        self.scene.toast(f"Loaded {world.title} at T+{world.t / 60:.0f} min")

    def flash(self, msg: str) -> None:
        if hasattr(self.scene, "toast"):
            self.scene.toast(msg)
        else:
            print(msg)

    def toggle_sound(self) -> None:
        self.audio.volume = 0.0 if self.audio.volume > 0 else 0.7
        self.settings["volume"] = self.audio.volume
        self.save_settings()

    # ------------------------------------------------------------ loop
    def frame(self, events, mouse=None) -> None:
        self.gui.begin(events, mouse if mouse is not None else pygame.mouse.get_pos(), self.dt)
        sc = self.scene
        sc.handle(events)
        sc.update(self.dt)
        sc.draw(self.screen)
        self.gui.end()

    def run(self) -> None:
        while self.running:
            self.dt = min(self.clock.tick(60) / 1000.0, 0.1)
            self.clock_t += self.dt
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
            self.frame(events)
            pygame.display.flip()
        pygame.quit()


def screenshot(path: str, sid: str | None, seconds: float, console: int, mode: str, select_first: bool,
               faction: str | None = None, scene: str = "command", autoplay_on: bool = True,
               coverage: bool = False) -> None:
    """Render one frame of a scenario after `seconds` of play (testing / documentation)."""
    app = App(headless=True, sound=False)
    if scene == "title":
        if faction:
            app.scene.faction = faction
        app.scene.t = 8.0                 # let the subtitle finish typing
        for _ in range(3):
            app.frame([])
    elif scene == "briefing":
        app.start_briefing(sid)
        app.scene.t = 100.0
        app.frame([])
    elif scene == "manual":
        from .manual import ManualScene
        from .theme import theme_for
        app.gui.set_theme(theme_for(faction or "US"))
        app.push(ManualScene(app, None, chapter=console))
        app.scene.scroll = seconds if seconds < 5000 else 0
        for _ in range(2):
            app.frame([])
    elif scene in ("campaign", "alert", "operations"):
        from .campaign import AlertDutyScene, CampaignScene
        from .scenes import OperationsScene
        f = faction or "US"
        app.push({"campaign": CampaignScene, "alert": AlertDutyScene}.get(scene, lambda a, fa: OperationsScene(a, fa))(app, f))
        for _ in range(2):
            app.frame([])
    else:
        world = scenario.build_world(sid)
        from ..sim.student import Student
        pupil = Student(world) if any(tr.id.startswith("lesson_") for tr in world.triggers) else None
        while world.t < seconds and not world.ended:
            if autoplay_on and pupil is not None:
                pupil.act()
            elif autoplay_on and world.tick % 10 == 0:
                autoplay.think(world)
            world.step()
        if scene == "debrief":
            if not world.ended:
                scenario.end(world, "screenshot")
            app.start_debrief(world)
            app.frame([])
        else:
            app.start_command(world)
            sc = app.scene
            sc.render_t = world.t
            sc.ci = console
            sc.mode = mode
            sc.speed_i = 0
            sc.map.layers["coverage"] = coverage
            if select_first:
                trk = next((t for t in world.tracks.values() if not t.lost and t.identity in ("unknown", "suspect", "hostile")),
                           next(iter(world.tracks.values()), None))
                if trk is not None:
                    sc.sel["track"] = trk.id
                fl = next((f for f in world.flights.values() if f.state not in ("landed", "lost")), None)
                if fl is not None:
                    sc.sel["flight"] = fl.id
                sam = next(iter(world.sams), None)
                if sam:
                    sc.sel["sam"] = sam
            if mode == "scope":
                # let the phosphor fill: render a full antenna revolution of paints
                site = world.radars[sc.scope.site_id]
                sc.scope.last_t = world.t - 60.0 / site.rpm - 0.5
                for _ in range(2):
                    app.frame([])
            for _ in range(2):
                app.frame([])
    pygame.image.save(app.screen, path)
    pygame.quit()
