"""The instructor's card: training steps pinned to the display, with the
controls to use circled on the console and the object of interest marked
on the situation display or the scope."""
from __future__ import annotations

import math

import pygame
from pygame import Rect

from . import cinema
from .theme import TEXT

INK = (36, 32, 26)
INK_DIM = (96, 88, 72)
RED = (168, 34, 26)
GREEN = (40, 120, 60)

CONSOLE_TABS = ["TRACKS F1", "WEAPONS F2", "MISSILES F3", "RADAR F4", "COMMS F6", "INTEL F7", "STATUS F8"]
CONSOLE_INDEX = {n.split()[0]: i for i, n in enumerate(CONSOLE_TABS)}
MODE_KEYS = {"map": "SITUATION", "scope": "RADAR SCOPE", "net": "NETWORK"}


class LessonCard:
    W = 440

    def __init__(self, scene):
        self.scene = scene
        self.collapsed = False
        self.rect: Rect | None = None
        self.header: Rect | None = None
        self.seen_step = None
        self.flash_t = -99.0
        self.corner = 0                   # 0 TL, 1 TR, 2 BL, 3 BR of the display
        self.mark_screen: tuple[int, int] | None = None

    # ------------------------------------------------------------ input
    def handle(self, gui) -> None:
        """Clicks on the card never fall through to the display; the header folds it."""
        if self.rect is None or not gui.released or gui.consumed:
            return
        if self.rect.collidepoint(gui.mouse) and self.rect.collidepoint(gui.press_pos):
            gui.consumed = True
            if self.header is not None and self.header.collidepoint(gui.mouse):
                self.collapsed = not self.collapsed
                if gui.audio:
                    gui.audio.play("click")

    # ------------------------------------------------------------ highlights
    def highlights(self, scene) -> set[str]:
        ls = scene.world.lesson
        if not ls or ls.get("final"):
            return set()
        hl = set(ls.get("highlight", []))
        con = ls.get("console")
        if con and con in CONSOLE_INDEX and scene.ci != CONSOLE_INDEX[con]:
            hl.add(CONSOLE_TABS[CONSOLE_INDEX[con]])
        mode = ls.get("mode")
        if mode and scene.mode != mode:
            hl.add(MODE_KEYS[mode])
        return hl

    # ------------------------------------------------------------ marks on the display
    def _mark_pos(self, scene):
        w = scene.world
        ref = scene.world.lesson.get("mark")
        if not ref:
            return None
        for coll in (w.airbases, w.radars, w.sams):
            if ref in coll:
                o = coll[ref]
                return o.x, o.y
        ids = [ref] if ref in w.aircraft else [k for k in w.aircraft if k.startswith(ref + "-")]
        for aid in ids:
            ac = w.aircraft[aid]
            if ac.state == "airborne":
                return ac.x, ac.y
        return None

    def draw_mark(self, gui, scene) -> None:
        self.mark_screen = None
        ls = scene.world.lesson
        if not ls or ls.get("final") or self.collapsed:
            return
        pos = self._mark_pos(scene)
        if pos is None:
            return
        if scene.mode == "map":
            sx, sy = scene.map.w2s(*pos)
            clip = scene.map.rect
        elif scene.mode == "scope":
            sc = scene.scope
            site = scene.world.radars.get(sc.site_id)
            if site is None:
                return
            dx, dy = pos[0] - site.x, pos[1] - site.y
            rng = math.hypot(dx, dy)
            if rng > sc.range_km:
                return
            px, py = sc.to_px(math.degrees(math.atan2(dx, dy)), rng)
            sx, sy = sc.center[0] - sc.R + px, sc.center[1] - sc.R + py
            clip = sc.rect
        else:
            return
        if not clip.collidepoint(sx, sy):
            return
        self.mark_screen = (sx, sy)
        s = gui.screen
        t = gui.time
        old = s.get_clip()
        s.set_clip(clip)
        col = (255, 214, 96)
        for k in range(2):
            ph = (t * 0.8 + k * 0.5) % 1.0
            rad = int(14 + ph * 30)
            a = 1.0 - ph
            c = tuple(int(v * a) for v in col)
            pygame.draw.circle(s, c, (sx, sy), rad, 2)
        pygame.draw.circle(s, col, (sx, sy), 12, 2)
        lab = ls.get("mark_label", "")
        if scene.world.faction == "USSR" and gui.lang_mode != "en" and ls.get("mark_label_ru"):
            lab = ls["mark_label_ru"]
        if lab:
            lx, ly = sx + 20, sy - 30
            pygame.draw.line(s, col, (sx + 9, sy - 9), (lx, ly + 10), 1)
            w = TEXT.width(lab, 12, "eng") + 12
            box = Rect(lx, ly, w, 20)
            pygame.draw.rect(s, (0, 0, 0), box)
            pygame.draw.rect(s, col, box, 1)
            s.blit(TEXT.render(lab, 12, col, "eng"), (lx + 6, ly + 2))
        s.set_clip(old)

    # ------------------------------------------------------------ the card
    def _origin(self, area: Rect, h: int) -> tuple[int, int]:
        """Keep the card in a corner of the display, away from what it points at."""
        spots = [(area.x + 16, area.y + 14), (area.right - self.W - 16, area.y + 14),
                 (area.x + 16, area.bottom - h - 34), (area.right - self.W - 16, area.bottom - h - 34)]
        m = self.mark_screen
        if m is not None and Rect(*spots[self.corner], self.W, h).inflate(80, 80).collidepoint(m):
            self.corner = max(range(4), key=lambda i: math.hypot(spots[i][0] + self.W / 2 - m[0],
                                                                 spots[i][1] + h / 2 - m[1]))
        return spots[self.corner]

    def draw(self, gui, scene, area: Rect) -> None:
        w = scene.world
        ls = w.lesson
        if not ls:
            self.rect = None
            return
        step = (ls.get("step", 0), ls.get("of", 0), ls.get("title", ""))
        if step != self.seen_step:
            if self.seen_step is not None:
                self.flash_t = gui.time
                self.collapsed = False
            self.seen_step = step
        ussr = w.faction == "USSR"
        body_kind = "cyr" if ussr else "typewriter"
        bsize = 14 if ussr else 15
        width = self.W
        inner_w = width - 36
        text = ls.get("text", "")
        lines = TEXT.wrap(text, inner_w, bsize, body_kind) if text else []
        act = ls.get("action", "")
        act_lines = TEXT.wrap(act, inner_w - 22, 14, "eng") if act else []
        head_h = 34
        if self.collapsed:
            h = head_h + 6
        else:
            h = head_h + 30 + len(lines) * (bsize + 4) + (len(act_lines) * 18 + 12 if act_lines else 0) + 14
        x, y = self._origin(area, h)
        r = Rect(x, y, width, h)
        self.rect = r
        self.header = Rect(x, y, width, head_h)
        s = gui.screen
        # shadow, paper, paper clip
        sh = pygame.Surface((width, h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 110))
        s.blit(sh, (x + 5, y + 7))
        paper = gui.cached(("lesson_paper", width, h, ussr),
                           lambda: cinema.paper((width, h), (226, 222, 204) if ussr else (236, 228, 200),
                                                seed=23 if ussr else 17, age=0.6))
        s.blit(paper, r)
        pygame.draw.rect(s, (120, 110, 90), r, 1)
        # header band
        band = Rect(x, y, width, head_h - 6)
        pygame.draw.rect(s, (52, 64, 74) if ussr else (64, 70, 48), band)
        pygame.draw.line(s, RED, (x, band.bottom), (r.right - 1, band.bottom), 2)
        if ussr and gui.lang_mode != "en":
            main, strip = "РУКОВОДИТЕЛЬ ЗАНЯТИЯ", "INSTRUCTOR"
        else:
            main, strip = "INSTRUCTOR", ""
        gx = x + 30
        gui.label((gx, y + 4), main, 17, (238, 234, 220), "eng")
        if strip and gui.lang_mode == "ru+en":
            gui.label((gx + TEXT.width(main, 17, "eng") + 8, y + 9), strip, 11, (180, 184, 176), "eng_r")
        n, of = ls.get("step", 0), ls.get("of", 0)
        if of:
            bx = r.right - 40 - of * 13
            for i in range(of):
                cell = Rect(bx + i * 13, y + 9, 10, 10)
                done = i + 1 < n or ls.get("final")
                cur = i + 1 == n and not ls.get("final")
                pygame.draw.rect(s, (238, 234, 220), cell, 1)
                if done:
                    pygame.draw.rect(s, (238, 234, 220), cell.inflate(-4, -4))
                elif cur:
                    pul = 0.5 + 0.5 * math.sin(gui.time * 5)
                    pygame.draw.rect(s, (255, int(160 + 80 * pul), 60), cell.inflate(-4, -4))
            lab = (f"ЭТАП {n} ИЗ {of}" if ussr and gui.lang_mode != "en" else f"STEP {n} OF {of}")
            if not self.collapsed:
                gui.label((r.right - 16, y + head_h + 3), lab, 13, INK_DIM, "eng", align="right")
        # fold arrow
        ax, ay = x + 14, y + 14
        pts = [(ax - 5, ay - 3), (ax + 5, ay - 3), (ax, ay + 4)] if not self.collapsed else \
            [(ax - 3, ay - 5), (ax - 3, ay + 5), (ax + 4, ay)]
        pygame.draw.polygon(s, (238, 234, 220), pts)
        if not self.collapsed:
            cy = y + head_h
            gui.label((x + 18, cy), ls.get("title", "").upper(), 19, INK, "eng")
            cy += 28
            for ln in lines:
                gui.label((x + 18, cy), ln, bsize, INK, body_kind)
                cy += bsize + 4
            if act_lines:
                cy += 6
                tri = [(x + 18, cy + 3), (x + 18, cy + 15), (x + 28, cy + 9)]
                pygame.draw.polygon(s, RED, tri)
                for i, ln in enumerate(act_lines):
                    gui.label((x + 36, cy + i * 18), ln, 14, RED, "eng")
        # step completed: a check stamp that fades out
        age = gui.time - self.flash_t
        if 0 <= age < 1.6 and not ls.get("final"):
            a = int(255 * min(1.0, (1.6 - age) / 0.6))
            st = gui.cached(("lesson_ok", ussr), lambda: cinema.stamp("ВЫПОЛНЕНО" if ussr else "DONE",
                                                                    GREEN, 22, -8.0, seed=5))
            st.set_alpha(a)
            s.blit(st, (r.right - st.get_width() - 14, r.y + head_h + 4))
            st.set_alpha(255)
        if ls.get("final"):
            st = gui.cached(("lesson_final", ussr), lambda: cinema.stamp(
                "ЗАЧЁТ" if ussr else "LESSON COMPLETE", RED, 24, -7.0,
                sub="EXERCISE PASSED" if not ussr else "PASSED", seed=9))
            s.blit(st, (r.right - st.get_width() - 10, r.bottom - st.get_height() - 4))
        # the clip
        cx = x + width - 30
        pygame.draw.rect(s, (150, 150, 146), Rect(cx, y - 8, 14, 30), 2, border_radius=6)
        pygame.draw.rect(s, (190, 190, 184), Rect(cx + 3, y - 4, 8, 22), 1, border_radius=4)
