"""Tactical replay: the whole engagement again on the 2-D display, from the truth snapshots
the simulation keeps (every 5 s in a battle) and the battle's event log.

Positions are interpolated between snapshots; explosions, launches and sinkings come back as
the timeline passes their events. Scrub the timeline, jump from event to event, change the
playback speed, and choose between the truth and what was on our scope.
"""
from __future__ import annotations

import math

import pygame
from pygame import Rect

from . import fx
from .battlefx import IDC, IDC_PVO, _fade, air_frame, ship_glyph, surface_frame
from .mapview import MapView, clock
from .theme import TEXT, theme_for

R = Rect
SPEEDS = [5, 15, 30, 60, 120]


class ReplayScene:
    def __init__(self, app, world):
        self.app = app
        self.world = world
        self.theme = theme_for(world.faction)
        app.gui.set_theme(self.theme)
        self.map = MapView(world, self.theme, R(16, 64, 1150, 770))
        b = world.battle
        if b.view:
            self.map.center_on(b.view[0], b.view[1])
            self.map.scale = self.map.rect.w / max(b.view[2], 50.0)
        self.snaps = world.stats.truth_snaps
        self.t = float(self.snaps[0][0]) if self.snaps else 0.0
        self.t_end = float(self.snaps[-1][0]) if self.snaps else 0.0
        self.playing = True
        self.speed_i = 2
        self.truth = True
        self.fx: list[dict] = []
        self.ev_i = 0
        self.idx = 0
        self.names = {a.id: a.callsign for a in world.aircraft.values()}
        self.types = {a.id: a.type_id for a in world.aircraft.values()}
        self.events = [e for e in b.events if e[7] >= 0 or True]
        self.marks = [e for e in self.events if e[7] >= 2 or e[1] in ("kill", "ship_hit", "sunk", "phase")]
        app.audio.play("tty")

    # ------------------------------------------------------------ the scene interface
    def handle(self, events):
        gui = self.app.gui
        for e in gui.keys:
            if e.key == pygame.K_ESCAPE:
                self.app.pop()
                return
            if e.key == pygame.K_SPACE:
                self.playing = not self.playing
        self.map.handle(gui, events)

    def update(self, dt):
        if not self.snaps:
            return
        if self.playing:
            self.t = min(self.t_end, self.t + dt * SPEEDS[self.speed_i])
            if self.t >= self.t_end:
                self.playing = False
        # events crossed by the playhead come back as effects
        while self.ev_i < len(self.events) and self.events[self.ev_i][0] <= self.t:
            e = self.events[self.ev_i]
            self.ev_i += 1
            if e[4] is None or self.t - e[0] > 20.0:
                continue
            if e[1] in ("kill", "ship_hit", "sunk", "vampire_kill"):
                self.fx.append(dict(kind=e[1], x=e[4], y=e[5], t0=e[0], side=e[6], text=e[2]))
                if e[1] in ("kill", "ship_hit") and self.playing:
                    self.app.audio.play("boom", 0.4)
        self.fx = [f for f in self.fx if 0 <= self.t - f["t0"] < 12.0]

    def _seek(self, t: float) -> None:
        self.t = max(0.0, min(self.t_end, t))
        self.ev_i = next((i for i, e in enumerate(self.events) if e[0] > self.t), len(self.events))
        self.fx = []

    def _frame(self):
        """The two snapshots around the playhead and the blend between them."""
        snaps = self.snaps
        i = self.idx
        if i >= len(snaps) - 1 or snaps[i][0] > self.t or snaps[i + 1][0] < self.t:
            lo, hi = 0, len(snaps) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if snaps[mid][0] <= self.t:
                    lo = mid
                else:
                    hi = mid - 1
            i = lo
            self.idx = i
        a = snaps[i]
        b = snaps[min(i + 1, len(snaps) - 1)]
        f = 0.0 if b[0] == a[0] else (self.t - a[0]) / (b[0] - a[0])
        return a, b, max(0.0, min(1.0, f))

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        w = self.world
        gui.set_theme(th)
        screen.fill((10, 12, 14))
        mv = self.map
        mr = mv.rect
        mv.draw_base_only(screen)
        C = IDC_PVO if w.faction == "USSR" else IDC
        own = w.own_side
        screen.set_clip(mr)
        if self.snaps:
            a, b, f = self._frame()
            nxt = {x[0]: x for x in b[1]}
            # trails: the last minute of every aircraft's path
            i0 = max(0, self.idx - 12)
            trails: dict[str, list] = {}
            for s in self.snaps[i0: self.idx + 1]:
                for x in s[1]:
                    trails.setdefault(x[0], []).append(mv.w2s(x[1], x[2]))
            if self.truth:
                for x in a[1]:
                    aid, ax, ay, alt, side, kind = x
                    if kind == "debris":
                        continue
                    y2 = nxt.get(aid)
                    if y2 is not None:
                        ax, ay = ax + (y2[1] - ax) * f, ay + (y2[2] - ay) * f
                    sx, sy = mv.w2s(ax, ay)
                    col = C["friend"] if side == own else C["hostile"] if side in ("red", "blue") else C["neutral"]
                    tr = trails.get(aid, [])
                    if len(tr) > 1:
                        pygame.draw.lines(screen, _fade(col, 0.35), False, tr + [(sx, sy)], 1)
                    missile = self.types.get(aid, "") in w.catalog.aircraft and \
                        w.catalog.aircraft[self.types[aid]].role == "missile"
                    if missile:
                        pygame.draw.circle(screen, (255, 230, 200) if side != own else (230, 240, 255), (sx, sy), 3)
                        continue
                    air_frame(screen, sx, sy, "friend" if side == own else "hostile" if side in ("red", "blue")
                              else "neutral", col, 7, 2)
                    if mv.scale > 0.35:
                        screen.blit(TEXT.render(self.names.get(aid, aid)[:12], 9, _fade(col, 0.85), "ui"),
                                    (sx + 8, sy - 12))
            else:
                for tid, x, y, idn in a[2]:
                    sx, sy = mv.w2s(x, y)
                    col = C.get(idn, C["pending"])
                    air_frame(screen, sx, sy, idn, col, 7, 2)
                    screen.blit(TEXT.render(tid, 9, _fade(col, 0.85), "ui"), (sx + 8, sy - 12))
            if len(a) > 3:                       # battles: ships and weapons in flight
                nxs = {x[0]: x for x in b[3]} if len(b) > 3 else {}
                for sid, x, y, hdg, side, state in a[3]:
                    y2 = nxs.get(sid)
                    if y2 is not None:
                        x, y = x + (y2[1] - x) * f, y + (y2[2] - y) * f
                    if side != own and not self.truth:
                        continue
                    sx, sy = mv.w2s(x, y)
                    col = C["friend"] if side == own else C["hostile"]
                    if state == "sunk":
                        col = (90, 96, 100)
                    elif state == "damaged":
                        col = (255, 190, 70)
                    elif state == "crippled":
                        col = (255, 90, 60)
                    surface_frame(screen, sx, sy, "friend" if side == own else "hostile", col, 8, 2)
                    ship_glyph(screen, sx, sy, hdg, col, 5)
                    sh = w.ships.get(sid)
                    if sh is not None and mv.scale > 0.3:
                        screen.blit(TEXT.render(sh.name.replace("USS ", ""), 9, col, "ui"), (sx + 11, sy - 6))
                if self.truth:
                    for mid, x, y, side, kind in a[4]:
                        sx, sy = mv.w2s(x, y)
                        pygame.draw.circle(screen, (255, 250, 220) if side == own else (255, 140, 110), (sx, sy), 2)
            # explosions coming back with their events
            for e in self.fx:
                age = (self.t - e["t0"]) / 12.0
                sx, sy = mv.w2s(e["x"], e["y"])
                big = e["kind"] in ("ship_hit", "sunk")
                r = int((10 if not big else 18) + (30 if big else 18) * min(1.0, age * 3))
                col = (255, 200, 120) if e["side"] != own else (255, 110, 90)
                pygame.draw.circle(screen, _fade(col, 1.0 - age), (sx, sy), r, 2 if big else 1)
                if age < 0.15:
                    pygame.draw.circle(screen, _fade((255, 250, 220), 1.0 - age * 6), (sx, sy), max(2, r // 3))
                if e["kind"] in ("kill", "ship_hit", "sunk") and age < 0.6:
                    lab = "SUNK" if e["kind"] == "sunk" else "HIT" if e["kind"] == "ship_hit" else "SPLASH"
                    img = TEXT.render(lab, 11, _fade(col, 1.0 - age * 1.5), "eng")
                    screen.blit(img, (sx - img.get_width() // 2, sy - r - 14))
        screen.set_clip(None)
        fx.bloom(screen, mr, 60)
        gui.crt_overlay(mr, strength=0.4)
        pygame.draw.rect(screen, (90, 96, 100), mr.inflate(4, 4), 1)
        # ---- header
        gui.label((16, 14), f"REPLAY — {w.title.upper()}", 26, (232, 226, 206), "title")
        outcome = w.battle.outcome or w.result.upper()
        gui.label((mr.right, 22), f"{clock(w, self.t)}  ·  T+{self.t / 60:.1f} min  ·  {outcome}", 14,
                  (210, 204, 186), "eng", "right")
        # ---- timeline with event marks
        tl = R(mr.x + 230, mr.bottom + 20, mr.w - 230, 26)
        pygame.draw.rect(screen, (30, 32, 34), tl, border_radius=3)
        if self.t_end > 0:
            for e in self.marks:
                mx = tl.x + int(tl.w * e[0] / self.t_end)
                col = (255, 110, 90) if e[6] == w.own_side and e[1] in ("kill", "ship_hit", "sunk") else \
                    (255, 220, 140) if e[1] != "phase" else (140, 200, 255)
                pygame.draw.line(screen, col, (mx, tl.y + 3), (mx, tl.bottom - 3), 1)
            px = tl.x + int(tl.w * self.t / self.t_end)
            pygame.draw.rect(screen, (255, 236, 170), (tl.x, tl.y + 11, px - tl.x, 4))
            pygame.draw.rect(screen, (240, 236, 220), (px - 4, tl.y - 3, 8, tl.h + 6), border_radius=2)
            if gui.down and tl.inflate(0, 12).collidepoint(gui.mouse):
                self._seek((gui.mouse[0] - tl.x) / tl.w * self.t_end)
        x = mr.x
        if gui.button(R(x, mr.bottom + 16, 52, 34), "II" if self.playing else ">", lit=self.playing, size=13,
                      key="REPLAY PLAY", tip="Play / pause (space)"):
            self.playing = not self.playing
            if self.t >= self.t_end:
                self._seek(0.0)
        if gui.button(R(x + 56, mr.bottom + 16, 52, 34), f"×{SPEEDS[self.speed_i]}", size=12, key="REPLAY SPEED",
                      tip="Playback speed"):
            self.speed_i = (self.speed_i + 1) % len(SPEEDS)
        if gui.button(R(x + 112, mr.bottom + 16, 52, 34), ">>|", size=12, key="REPLAY NEXT",
                      tip="Jump to the next important event"):
            nxt_e = next((e for e in self.marks if e[0] > self.t + 1.0), None)
            if nxt_e is not None:
                self._seek(nxt_e[0] - 8.0)
                self.playing = True
        if gui.button(R(x + 168, mr.bottom + 16, 56, 34), "TRUTH" if self.truth else "SCOPE", lit=self.truth, size=11,
                      key="REPLAY VIEW", tip="Truth (both sides as they were) or our tracks only"):
            self.truth = not self.truth
        # ---- events so far
        pr = R(mr.right + 16, mr.y, 1600 - mr.right - 32, mr.h)
        gui.glass(pr)
        gui.label((pr.x + 8, pr.y + 6), "EVENTS", 13, (255, 200, 120), "eng")
        lines = [e for e in self.events[: self.ev_i] if e[7] >= 1 or (e[7] == -1 and e[1] in
                                                                       ("launch", "asm_launch", "located", "recon"))]
        y = pr.bottom - 18
        for e in reversed(lines[-60:]):
            txt = f"{clock(w, e[0])} {e[2].replace('[enemy] ', 'ENEMY: ')}"
            col = (255, 110, 90) if e[7] >= 3 else (255, 210, 150) if e[7] == 2 else (160, 176, 180)
            for ln in reversed(TEXT.wrap(txt, pr.w - 16, 11, "ui")[:2]):
                screen.blit(TEXT.render(ln, 11, col, "ui"), (pr.x + 8, y))
                y -= 14
            if y < pr.y + 30:
                break
        if gui.button(R(1600 - 176, 846, 160, 40), "CLOSE", size=13, key="REPLAY CLOSE"):
            self.app.pop()
