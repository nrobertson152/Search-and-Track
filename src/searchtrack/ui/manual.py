"""The operator's manual: chapters in data/manual/*.md, typed onto paper.

A small Markdown subset is supported: ``#`` title, ``>`` subtitle, ``##``
and ``###`` headings, paragraphs, ``-`` and ``1.`` lists, ``|`` tables,
``**bold**`` (typewriter overstrike) and ```code``` (keys, in red ink).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pygame
from pygame import Rect

from ..sim.catalog import DATA_DIR
from . import cinema
from .theme import TEXT

MANUAL_DIR = DATA_DIR / "manual"
INK = (34, 30, 24)
INK_DIM = (104, 96, 80)
RED = (160, 34, 26)
RULE = (150, 138, 112)


@dataclass
class Chapter:
    key: str
    title: str
    subtitle: str = ""
    blocks: list[tuple] = field(default_factory=list)

    @property
    def sections(self) -> list[str]:
        return [b[1] for b in self.blocks if b[0] == "h2"]


def parse(text: str, key: str = "") -> Chapter:
    ch = Chapter(key, key)
    para: list[str] = []
    table: list[list[str]] = []

    def flush():
        nonlocal para, table
        if para:
            ch.blocks.append(("p", " ".join(para)))
            para = []
        if table:
            ch.blocks.append(("table", table))
            table = []

    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("|"):
            if para:
                flush()
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            table.append(cells)
            continue
        if table:
            flush()
        if s.startswith("# "):
            flush()
            ch.title = s[2:].strip()
        elif s.startswith("> "):
            flush()
            if not ch.subtitle and not ch.blocks:
                ch.subtitle = s[2:].strip()
            else:
                ch.blocks.append(("quote", s[2:].strip()))
        elif s.startswith("### "):
            flush()
            ch.blocks.append(("h3", s[4:].strip()))
        elif s.startswith("## "):
            flush()
            ch.blocks.append(("h2", s[3:].strip()))
        elif s.startswith("- "):
            flush()
            ch.blocks.append(("li", s[2:].strip()))
        elif re.match(r"\d+\. ", s):
            flush()
            n, rest = s.split(". ", 1)
            ch.blocks.append(("ol", n, rest.strip()))
        else:
            para.append(s)
    flush()
    return ch


def load_manual(directory: Path = MANUAL_DIR) -> list[Chapter]:
    return [parse(p.read_text(encoding="utf-8"), p.stem) for p in sorted(directory.glob("*.md"))]


# ------------------------------------------------------------------ typesetting

def _segments(text: str) -> list[tuple[str, str]]:
    """Split inline markup into (text, style) runs: n normal, b bold, c code."""
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            out.append((part[2:-2], "b"))
        elif part.startswith("`"):
            out.append((part[1:-1], "c"))
        else:
            out.append((part, "n"))
    return out


def _cyrillic(word: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in word)


class Typesetter:
    """Lays a chapter out on one tall sheet of paper."""

    def __init__(self, width: int, body_kind: str, ussr: bool):
        self.w = width
        self.body = body_kind
        self.ussr = ussr
        self.size = 15 if body_kind == "typewriter" else 14
        self.lead = self.size + 7
        self.ops: list[tuple] = []          # (kind, x, y, payload...)
        self.anchors: dict[str, int] = {}
        self.y = 0

    # words with styles -> lines
    def _font_kind(self, word: str, style: str) -> str:
        if style == "c":
            return "eng"
        if self.body == "typewriter" and _cyrillic(word):
            return "cyr"
        return self.body

    def _wrap(self, text: str, width: int, size: int) -> list[list[tuple[str, str, int]]]:
        words: list[tuple[str, str]] = []
        for seg, style in _segments(text):
            parts = re.split(r"(\s+)", seg)
            for p in parts:
                if not p:
                    continue
                if p.isspace():
                    words.append((" ", "space"))
                else:
                    words.append((p, style))
        lines: list[list[tuple[str, str, int]]] = [[]]
        x = 0
        space = TEXT.width(" ", size, self.body)
        for wtext, style in words:
            if style == "space":
                if lines[-1]:
                    x += space
                continue
            ww = TEXT.width(wtext, size, self._font_kind(wtext, style)) + (6 if style == "c" else 0)
            if x + ww > width and lines[-1]:
                lines.append([])
                x = 0
            lines[-1].append((wtext, style, x))
            x += ww
        return lines

    def _emit_lines(self, lines, x0: int, size: int, color=INK) -> None:
        for ln in lines:
            for wtext, style, x in ln:
                self.ops.append(("word", x0 + x, self.y, wtext, style, size, color,
                                 self._font_kind(wtext, style)))
            self.y += size + 7

    def block(self, b: tuple) -> None:
        kind = b[0]
        if kind == "h2":
            self.y += 16
            self.anchors[b[1]] = self.y
            self.ops.append(("h2", 0, self.y, b[1]))
            self.y += 34
        elif kind == "h3":
            self.y += 8
            self.ops.append(("h3", 0, self.y, b[1]))
            self.y += 26
        elif kind == "p":
            self._emit_lines(self._wrap(b[1], self.w, self.size), 0, self.size)
            self.y += 9
        elif kind == "quote":
            self._emit_lines(self._wrap(b[1], self.w - 30, self.size), 24, self.size, INK_DIM)
            self.y += 9
        elif kind == "li":
            self.ops.append(("bullet", 8, self.y + self.size // 2 + 1))
            self._emit_lines(self._wrap(b[1], self.w - 26, self.size), 26, self.size)
            self.y += 4
        elif kind == "ol":
            self.ops.append(("num", 0, self.y, b[1] + "."))
            self._emit_lines(self._wrap(b[2], self.w - 30, self.size), 30, self.size)
            self.y += 4
        elif kind == "table":
            self._table(b[1])

    def _table(self, rows: list[list[str]]) -> None:
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        size = self.size - 1
        natural = [max(TEXT.width(re.sub(r"[*`]", "", r[c]), size, self.body) + 22 for r in rows) for c in range(ncol)]
        tot = sum(natural)
        widths = natural if tot <= self.w else [max(60, int(n * self.w / tot)) for n in natural]
        widths[-1] = self.w - sum(widths[:-1])
        self.y += 4
        top = self.y
        for i, r in enumerate(rows):
            cells = [self._wrap(r[c] if i or "`" in r[c] or not r[c] else f"**{r[c]}**", widths[c] - 16, size)
                     for c in range(ncol)]
            h = max(len(c) for c in cells) * (size + 7) + 8
            if i == 0:
                self.ops.append(("shade", 0, self.y, self.w, h))
            x = 0
            y0 = self.y
            for c in range(ncol):
                self.y = y0 + 4
                self._emit_lines(cells[c], x + 8, size)
                x += widths[c]
            self.y = y0 + h
            self.ops.append(("hrule", 0, self.y, self.w, 2 if i == 0 else 1))
        xs = [0]
        for wd in widths:
            xs.append(xs[-1] + wd)
        self.ops.append(("grid", top, self.y, xs[1:-1]))
        self.ops.append(("hrule", 0, top, self.w, 2))
        self.y += 14

    def chapter(self, ch: Chapter) -> None:
        for b in ch.blocks:
            self.block(b)


def render_sheet(ch: Chapter, width: int, ussr: bool) -> tuple[pygame.Surface, dict[str, int]]:
    """Typeset a chapter onto a transparent sheet (ink only); returns it and its section anchors."""
    body = "cyr" if ussr else "typewriter"
    ts = Typesetter(width, body, ussr)
    ts.chapter(ch)
    sheet = pygame.Surface((width, ts.y + 40), pygame.SRCALPHA)
    for op in ts.ops:
        k = op[0]
        if k == "word":
            _, x, y, text, style, size, color, kind = op
            if style == "c":
                tw = TEXT.width(text, size - 1, kind)
                box = Rect(x, y + 1, tw + 6, size + 3)
                pygame.draw.rect(sheet, (*RED, 40), box, border_radius=3)
                pygame.draw.rect(sheet, (*RED, 150), box, 1, border_radius=3)
                sheet.blit(TEXT.render(text, size - 1, RED, kind), (x + 3, y + 1))
            else:
                img = TEXT.render(text, size, color, kind)
                sheet.blit(img, (x, y))
                if style == "b":                      # typewriter overstrike
                    sheet.blit(img, (x + 1, y))
        elif k == "h2":
            _, x, y, text = op
            sheet.blit(TEXT.render(text.upper(), 19, INK, "eng"), (x, y))
            pygame.draw.line(sheet, RULE, (x, y + 27), (width, y + 27), 1)
        elif k == "h3":
            _, x, y, text = op
            sheet.blit(TEXT.render(text, 16, INK, "eng"), (x, y))
        elif k == "bullet":
            _, x, y = op
            pygame.draw.circle(sheet, INK, (x, y), 3)
        elif k == "num":
            _, x, y, text = op
            sheet.blit(TEXT.render(text, ts.size, INK, body), (x, y))
        elif k == "shade":
            _, x, y, w, h = op
            pygame.draw.rect(sheet, (*RULE, 60), Rect(x, y, w, h))
        elif k == "hrule":
            _, x, y, w, t = op
            pygame.draw.line(sheet, RULE, (x, y), (x + w, y), t)
        elif k == "grid":
            _, top, bottom, xs = op
            for gx in xs:
                pygame.draw.line(sheet, RULE, (gx, top), (gx, bottom), 1)
    return sheet, ts.anchors


# ------------------------------------------------------------------ the scene

W, H = 1600, 900


class ManualScene:
    """The manual on the desk: contents card, the typed page, a section index."""

    TOC = Rect(40, 50, 380, 800)
    PAGE = Rect(450, 28, 840, 846)
    SIDE = Rect(1316, 50, 250, 800)

    def __init__(self, app, back=None, chapter: int = 0):
        from .scenes import _desk_surface
        self.app = app
        self.back = back
        self.theme = getattr(back, "theme", app.gui.theme)
        self.ussr = self.theme.faction == "USSR"
        self.chapters = load_manual()
        self.ci = max(0, min(chapter, len(self.chapters) - 1))
        self.scroll = 0.0
        self.desk = _desk_surface(self.theme.faction, seed=57)
        self.view = Rect(self.PAGE.x + 62, self.PAGE.y + 176, self.PAGE.w - 124, self.PAGE.h - 236)
        self._sheets: dict[int, tuple[pygame.Surface, dict[str, int]]] = {}

    # ------------------------------------------------------------ helpers
    def sheet(self, i: int):
        if i not in self._sheets:
            self._sheets[i] = render_sheet(self.chapters[i], self.view.w, self.ussr)
        return self._sheets[i]

    def goto(self, i: int) -> None:
        if 0 <= i < len(self.chapters) and i != self.ci:
            self.ci = i
            self.scroll = 0.0
            if self.app.audio:
                self.app.audio.play("click")

    def max_scroll(self) -> float:
        return max(0.0, self.sheet(self.ci)[0].get_height() - self.view.h)

    def _ru(self, ru: str, en: str) -> tuple[str, str]:
        mode = self.app.gui.lang_mode
        if not self.ussr or mode == "en":
            return en, ""
        return ru, (en if mode == "ru+en" else "")

    # ------------------------------------------------------------ frame
    def handle(self, events) -> None:
        gui = self.app.gui
        for e in gui.keys:
            k = e.key
            if k == pygame.K_ESCAPE:
                self.app.pop()
                return
            if k in (pygame.K_RIGHT,):
                self.goto(self.ci + 1)
            elif k in (pygame.K_LEFT,):
                self.goto(self.ci - 1)
            elif k == pygame.K_DOWN:
                self.scroll += 44
            elif k == pygame.K_UP:
                self.scroll -= 44
            elif k == pygame.K_PAGEDOWN or k == pygame.K_SPACE:
                self.scroll += self.view.h - 60
            elif k == pygame.K_PAGEUP:
                self.scroll -= self.view.h - 60
            elif k == pygame.K_HOME:
                self.scroll = 0
            elif k == pygame.K_END:
                self.scroll = self.max_scroll()
        if gui.wheel and self.PAGE.collidepoint(gui.mouse):
            self.scroll -= gui.wheel * 66
            gui.wheel = 0
        self.scroll = max(0.0, min(self.max_scroll(), self.scroll))

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        gui = self.app.gui
        screen.blit(self.desk, (0, 0))
        self._contents(gui)
        self._page(gui)
        self._side(gui)

    # ------------------------------------------------------------ parts
    def _paper(self, gui, r: Rect, seed: int) -> pygame.Surface:
        tint = (222, 222, 210) if self.ussr else (236, 228, 200)
        return gui.cached(("manual_paper", r.w, r.h, seed, self.ussr),
                          lambda: cinema.paper((r.w, r.h), tint, seed=seed, age=0.7))

    def _sheet_shadow(self, screen, r: Rect) -> None:
        sh = pygame.Surface(r.size, pygame.SRCALPHA)
        sh.fill((0, 0, 0, 120))
        screen.blit(sh, (r.x + 7, r.y + 9))

    def _contents(self, gui) -> None:
        s = gui.screen
        r = self.TOC
        self._sheet_shadow(s, r)
        s.blit(self._paper(gui, r, 61), r)
        main, strip = self._ru("СОДЕРЖАНИЕ", "CONTENTS")
        gui.label((r.x + 28, r.y + 26), main, 24, INK, "eng")
        if strip:
            gui.label((r.x + 30 + TEXT.width(main, 24, "eng") + 10, r.y + 34), strip, 13, INK_DIM, "eng_r")
        pygame.draw.line(s, RED, (r.x + 24, r.y + 64), (r.right - 24, r.y + 64), 2)
        y = r.y + 82
        for i, ch in enumerate(self.chapters):
            row = Rect(r.x + 16, y - 4, r.w - 32, 52)
            cur = i == self.ci
            if cur:
                hl = pygame.Surface(row.size, pygame.SRCALPHA)
                hl.fill((160, 34, 26, 34))
                s.blit(hl, row)
                pygame.draw.polygon(s, RED, [(row.x + 2, row.y + 14), (row.x + 2, row.y + 30), (row.x + 11, row.y + 22)])
            elif row.collidepoint(gui.mouse):
                hl = pygame.Surface(row.size, pygame.SRCALPHA)
                hl.fill((60, 50, 30, 22))
                s.blit(hl, row)
            gui.label((row.x + 18, y + 2), f"{i + 1}", 20, RED if cur else INK_DIM, "eng")
            gui.label((row.x + 50, y + 2), ch.title.upper(), 17, INK, "eng")
            if ch.subtitle:
                sub = ch.subtitle if TEXT.width(ch.subtitle, 13, "eng_r") < row.w - 60 else \
                    ch.subtitle[:44].rsplit(" ", 1)[0] + "…"
                gui.label((row.x + 50, y + 24), sub, 13, INK_DIM, "eng_r")
            gui.drawn[f"CHAPTER {i + 1}"] = row
            if gui.clicked(row):
                self.goto(i)
            y += 56
        gui.label((r.x + 28, r.bottom - 34), "Left/Right: chapter   Up/Down, wheel, PgUp/PgDn: scroll   Esc: back",
                  12, INK_DIM, "eng_r")

    def _page(self, gui) -> None:
        s = gui.screen
        r = self.PAGE
        ch = self.chapters[self.ci]
        self._sheet_shadow(s, r)
        s.blit(self._paper(gui, r, 62 + self.ci), r)
        # running head
        head, strip = self._ru("НАСТАВЛЕНИЕ ОПЕРАТОРУ КОМАНДНОГО ПУНКТА", "OPERATOR'S MANUAL · DIRECTION CENTER WEAPONS ROOM")
        if not self.ussr:
            head = "OPERATOR'S MANUAL · DIRECTION CENTER WEAPONS ROOM"
        gui.label((r.x + 62, r.y + 24), head, 13, INK_DIM, "eng")
        if strip:
            gui.label((r.x + 62, r.y + 40), strip, 11, INK_DIM, "eng_r")
        stamp_text, stamp_sub = self._ru("ДСП", "FOR OFFICIAL USE ONLY")
        st = gui.cached(("manual_stamp", self.ussr, stamp_text),
                        lambda: cinema.stamp(stamp_text, RED, 20 if not self.ussr else 24, -6.0,
                                             sub=stamp_sub if self.ussr else "", seed=4))
        s.blit(st, (r.right - st.get_width() - 40, r.y + 16))
        # chapter title
        num, nstrip = self._ru(f"ГЛАВА {self.ci + 1}", f"CHAPTER {self.ci + 1}")
        gui.label((r.x + 62, r.y + 70), num, 16, RED, "eng")
        gui.label((r.x + 62, r.y + 92), ch.title.upper(), 34, INK, "title")
        if ch.subtitle:
            gui.label((r.x + 64, r.y + 140), ch.subtitle, 15, INK_DIM, "eng_r")
        pygame.draw.line(s, INK, (r.x + 62, r.y + 166), (r.right - 62, r.y + 166), 2)
        # the sheet, scrolled
        sheet, _ = self.sheet(self.ci)
        v = self.view
        s.blit(sheet, v.topleft, area=Rect(0, int(self.scroll), v.w, v.h))
        # fade the cut edges into the paper
        if self.scroll > 1:
            pygame.draw.line(s, RULE, (v.x, v.y - 2), (v.right, v.y - 2), 1)
        # scroll rail
        ms = self.max_scroll()
        if ms > 0:
            rail = Rect(r.right - 30, v.y, 6, v.h)
            pygame.draw.rect(s, (200, 190, 160), rail, border_radius=3)
            frac = v.h / (v.h + ms)
            th = max(30, int(rail.h * frac))
            ty = rail.y + int((rail.h - th) * self.scroll / ms)
            pygame.draw.rect(s, (130, 118, 90), Rect(rail.x, ty, rail.w, th), border_radius=3)
            if gui.down and Rect(rail.x - 8, rail.y, rail.w + 16, rail.h).collidepoint(gui.press_pos):
                self.scroll = max(0.0, min(ms, (gui.mouse[1] - rail.y - th / 2) / max(1, rail.h - th) * ms))
        # folio
        pages = max(1, round((sheet.get_height()) / max(1, v.h) + 0.49))
        cur = min(pages, int(self.scroll / max(1, v.h) + 1.0001))
        folio = f"{self.ci + 1}–{cur}"
        gui.label((r.centerx, r.bottom - 34), folio, 13, INK_DIM, "eng", align="center")

    def _side(self, gui) -> None:
        s = gui.screen
        r = self.SIDE
        ch = self.chapters[self.ci]
        _, anchors = self.sheet(self.ci)
        main, strip = self._ru("В ЭТОЙ ГЛАВЕ", "IN THIS CHAPTER")
        gui.label((r.x, r.y), main, 15, (220, 210, 186), "eng")
        if strip:
            gui.label((r.x, r.y + 20), strip, 11, (170, 160, 140), "eng_r")
        y = r.y + 46
        for name in ch.sections:
            row = Rect(r.x - 6, y - 3, r.w, 26)
            here = anchors.get(name, 0) <= self.scroll + 40 and all(
                anchors.get(o, 0) > self.scroll + 40 or anchors.get(o, 0) <= anchors.get(name, 0) for o in ch.sections)
            col = (250, 204, 120) if here else ((236, 228, 200) if row.collidepoint(gui.mouse) else (190, 182, 160))
            if here:
                pygame.draw.polygon(s, col, [(r.x, y + 5), (r.x, y + 15), (r.x + 7, y + 10)])
            gui.label((r.x + 14, y), name, 14, col, "eng_r")
            gui.drawn[f"SECTION {name}"] = row
            if gui.clicked(row):
                self.scroll = max(0.0, min(self.max_scroll(), anchors.get(name, 0) - 8))
            y += 28
        bw = 120
        if gui.button(Rect(r.x, r.bottom - 96, bw, 36), "< PREV", enabled=self.ci > 0, size=12):
            self.goto(self.ci - 1)
        if gui.button(Rect(r.x + bw + 10, r.bottom - 96, bw, 36), "NEXT >", enabled=self.ci < len(self.chapters) - 1,
                      size=12):
            self.goto(self.ci + 1)
        if gui.button(Rect(r.x, r.bottom - 50, 2 * bw + 10, 40), "BACK", size=13):
            self.app.pop()
