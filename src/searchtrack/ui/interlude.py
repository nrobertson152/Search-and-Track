"""Between the battles: the war's story, one page at a time.

Teletypes clatter out line by line, letters and diaries are typed by a tired hand, the
newspaper arrives already printed. Click (or SPACE) to finish a page or turn to the next;
ESC skips the rest.
"""
from __future__ import annotations

from typing import Callable, Optional

import pygame

from .scenes import R, Scene, _desk_surface
from .theme import TEXT, theme_for

INK = (36, 30, 24)
RED_INK = (150, 34, 26)
BLUE_INK = (34, 52, 120)
SPEED = {"teletype": 120.0, "letter": 75.0, "diary": 75.0, "report": 140.0, "newspaper": 100000.0}
SIZES = {"teletype": (820, 780), "letter": (880, 790), "diary": (880, 790), "report": (920, 790),
         "newspaper": (1180, 800)}
TINTS = {"teletype": (238, 232, 198), "letter": (240, 234, 220), "diary": (236, 232, 214), "report": (232, 228, 214),
         "newspaper": (228, 224, 208)}
BRIEF_US = ["WEATHER: Bering Sea, wind northwest 35 knots, seas 12 feet, snow showers. Flight deck temperature 28°F.",
            "MAIL CALL: the COD flies at 1400 if the weather holds. Letters to the post office by 1200.",
            "CHAPLAIN: services in the forecastle at 1900, all faiths. Coffee afterwards.",
            "SUPPLY: the ship's store is out of film, batteries and peanut butter. More on the next COD.",
            "SPORTS: the Sundowners lead the Eagles 4-2 in the hangar-bay basketball league, games postponed.",
            "BLOOD DRIVE: medical asks all hands with type O to report to sick bay after watch."]
BRIEF_SU = ["WEATHER: Kola Peninsula, snow showers, wind from the north-west 15 m/s, minus 6.",
            "IN THE REGIMENTS: the komsomol meeting of the 174th is postponed until after the alert.",
            "LETTERS: field post will be collected at 1200 at every company. Write to your families.",
            "SPORTS: the hockey match between the radar battalion and the air base is postponed.",
            "GOOD WORK: Private R. Karimov of the Teriberka company restored power to the radar in 40 minutes.",
            "CULTURE: the regiment's film evening will show 'Officers' when the alert is lifted."]


class InterludeScene(Scene):
    def __init__(self, app, faction: str, pages: list[dict], on_done: Optional[Callable[[], None]] = None,
                 start: int = 0, title: str = ""):
        super().__init__(app)
        self.faction = faction
        self.theme = theme_for(faction)
        self.desk = _desk_surface(faction, 83)
        self.pages = [p for p in pages if p.get("text") or p.get("title")]
        self.i = max(0, min(start, len(self.pages) - 1)) if self.pages else 0
        self.shown = 0.0
        self.on_done = on_done
        self.title = title
        self._cache: dict[int, tuple] = {}
        self._tick = 0.0
        app.audio.play("tty")

    # ------------------------------------------------------------ flow
    def _done(self) -> None:
        self.app.pop()
        if self.on_done is not None:
            self.on_done()

    def _next(self) -> None:
        if self.i + 1 >= len(self.pages):
            self._done()
            return
        self.i += 1
        self.shown = 0.0
        self.app.audio.play("tty" if self.pages[self.i].get("kind") == "teletype" else "switch")

    def update(self, dt: float) -> None:
        if not self.pages:
            return
        kind = self.pages[self.i].get("kind", "teletype")
        before = int(self.shown)
        self.shown += SPEED.get(kind, 100.0) * dt
        self._tick += dt
        if kind in ("letter", "diary", "report") and int(self.shown) > before and self._tick > 0.11 and \
                self.shown < self._layout(self.i)[1]:
            self._tick = 0.0
            self.app.audio.play("key")

    # ------------------------------------------------------------ layout
    def _layout(self, i: int) -> tuple[list, int, pygame.Surface]:
        """Lines to draw as (x, y, text, size, color, font), their total character count, the paper."""
        if i in self._cache:
            return self._cache[i]
        from .cinema import paper
        p = self.pages[i]
        kind = p.get("kind", "teletype")
        w, hmax = SIZES.get(kind, (900, 790))
        lines: list = []
        deco: list = []                                   # (kind, args) drawn on the paper once it is cut
        x0, y = 54, 48
        text = p.get("text", "")

        def add(s: str, size: int, color, font: str, gap: int = 6, width: int = w - 108, x: int = x0) -> None:
            nonlocal y
            if not s:
                y += size // 2 + gap
                return
            for ln in TEXT.wrap(s, width, size, font):
                lines.append((x, y, ln, size, color, font))
                y += size + gap

        if kind == "teletype":
            add(f"ZCZC  {p.get('date', '')}".upper(), 16, INK, "tty")
            add(f"FM {p.get('from', '')}".upper(), 16, INK, "tty")
            if p.get("to"):
                add(f"TO {p['to']}".upper(), 16, INK, "tty")
            add("", 16, INK, "tty")
            add(f"BT  {p.get('title', '')}".upper(), 18, RED_INK, "tty")
            add("", 16, INK, "tty")
            for para in text.split("\n"):
                add(para.upper(), 17, INK, "tty", 5)
            add("", 16, INK, "tty")
            add("BT  NNNN", 16, INK, "tty")
            deco.append(("sprockets", None))
        elif kind == "newspaper":
            title = p.get("title", "")
            tw = TEXT.width(title, 54, "title")
            lines.append(((w - tw) // 2, 26, title, 54, INK, "title"))
            sub = f"{p.get('from', '')} · {p.get('date', '')}"
            sw = TEXT.width(sub, 15, "eng")
            lines.append(((w - sw) // 2, 96, sub, 15, (90, 80, 64), "eng"))
            deco.append(("rules", None))
            paras = [s for s in text.split("\n") if s.strip()]
            y = 146
            add(paras[0] if paras else "", 40, INK, "title", 8, w - 100, 50)
            y += 8
            top = y
            col_w = int((w - 140) * 0.6)
            for para in paras[1:]:
                for ln in TEXT.wrap(para, col_w, 18, "eng_r"):
                    lines.append((50, y, ln, 18, (44, 38, 30), "eng_r"))
                    y += 25
                y += 12
            # a file photograph and the small news of the day, in the right-hand column
            px, pw = 50 + col_w + 40, w - (50 + col_w + 40) - 50
            deco.append(("photo", (px, top, pw, 230)))
            cap = "F-14A Tomcat (file photograph)" if self.faction == "US" else "Su-27 interceptor (file photograph)"
            lines.append((px, top + 238, cap, 13, (90, 80, 64), "eng_r"))
            yy = top + 270
            lines.append((px, yy, "IN BRIEF", 15, RED_INK, "eng"))
            yy += 24
            brief = BRIEF_US if self.faction == "US" else BRIEF_SU
            for item in brief[(i * 2) % len(brief):(i * 2) % len(brief) + 2]:
                for ln in TEXT.wrap(item, pw, 14, "eng_r"):
                    lines.append((px, yy, ln, 14, (60, 52, 40), "eng_r"))
                    yy += 19
                yy += 10
            deco.append(("column", (px - 20, top, max(y, yy))))
            y = max(y, yy)
        elif kind == "report":
            add((p.get("title", "") or "REPORT").upper(), 22, RED_INK, "eng", 10)
            deco.append(("hrule", y + 2))
            y += 14
            for lab, val in (("FROM", p.get("from")), ("TO", p.get("to")), ("DATE", p.get("date"))):
                if val:
                    add(f"{lab}:  {val}", 15, (70, 60, 48), "ui", 4)
            y += 12
            for para in text.split("\n"):
                add(para, 16, INK, "ui", 6)
        else:                                                      # letter, diary
            if kind == "diary":
                x0 = 96
                deco.append(("ruled", None))
            if p.get("date"):
                dw = TEXT.width(p["date"], 17, "typewriter")
                lines.append((w - 60 - dw, y, p["date"], 17, (70, 62, 52), "typewriter"))
                y += 40
            if kind == "diary" and p.get("title"):
                add(p["title"], 20, BLUE_INK, "typewriter", 12, w - x0 - 60, x0)
            for para in text.split("\n"):
                add(para, 18, (34, 36, 70) if kind == "letter" else (30, 34, 74), "typewriter", 8, w - x0 - 60, x0)
            if kind == "letter" and p.get("from"):
                y += 10
                add(f"— {p['from']}", 16, (80, 70, 60), "typewriter", 6, w - x0 - 260, x0 + 200)
        h = int(min(hmax, max(420, y + 56)))
        pg = paper((w, h), TINTS.get(kind, (232, 228, 210)), seed=31 + i * 7, age=1.2)
        for what, arg in deco:
            if what == "sprockets":
                for k in range(14, h - 10, 34):
                    pygame.draw.circle(pg, (196, 190, 160), (20, k), 5)
                    pygame.draw.circle(pg, (196, 190, 160), (w - 20, k), 5)
            elif what == "rules":
                pygame.draw.line(pg, INK, (40, 122), (w - 40, 122), 3)
                pygame.draw.line(pg, INK, (40, 128), (w - 40, 128), 1)
            elif what == "hrule":
                pygame.draw.line(pg, (120, 100, 80), (54, arg), (w - 54, arg), 1)
            elif what == "ruled":
                for k in range(110, h - 30, 30):
                    pygame.draw.line(pg, (170, 186, 214), (34, k + 22), (w - 34, k + 22), 1)
                pygame.draw.line(pg, (214, 140, 140), (78, 20), (78, h - 20), 1)
            elif what == "column":
                cx, y0, y1 = arg
                pygame.draw.line(pg, (120, 110, 90), (cx, y0), (cx, min(h - 40, y1)), 1)
            elif what == "photo":
                self._photo(pg, pygame.Rect(*arg), i)
        total = sum(len(ln[2]) for ln in lines)
        self._cache[i] = (lines, total, pg)
        return self._cache[i]

    def _photo(self, pg: pygame.Surface, r: pygame.Rect, i: int) -> None:
        """A grainy newspaper half-tone of an aircraft in a sky."""
        from . import silhouette
        sky = pygame.Surface(r.size)
        for yy in range(r.h):
            v = 120 + int(70 * yy / max(1, r.h))
            pygame.draw.line(sky, (v, v, v - 6), (0, yy), (r.w, yy))
        tid = ("F-14A", "interceptor") if self.faction == "US" else ("Su-27", "interceptor")
        sil = silhouette.render(tid[0], tid[1], int(r.h * 0.9), (28, 28, 30), heading=60.0 + 25 * (i % 3))
        sky.blit(sil, ((r.w - sil.get_width()) // 2, (r.h - sil.get_height()) // 2))
        dots = pygame.Surface(r.size, pygame.SRCALPHA)
        for yy in range(0, r.h, 3):                        # half-tone screen
            for xx in range((yy // 3) % 2, r.w, 3):
                dots.set_at((xx, yy), (255, 255, 255, 38))
        sky.blit(dots, (0, 0))
        pg.blit(sky, r.topleft)
        pygame.draw.rect(pg, INK, r, 2)

    # ------------------------------------------------------------ drawing
    def draw(self, screen) -> None:
        gui = self.app.gui
        gui.set_theme(self.theme)
        screen.blit(self.desk, (0, 0))
        if not self.pages:
            self._done()
            return
        lines, total, pg = self._layout(self.i)
        kind = self.pages[self.i].get("kind", "teletype")
        px = (1600 - pg.get_width()) // 2
        py = max(16, (870 - pg.get_height()) // 2 - 10)
        shadow = pygame.Surface(pg.get_size(), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 120))
        screen.blit(shadow, (px + 8, py + 10))
        screen.blit(pg, (px, py))
        left = int(self.shown)
        full = left >= total
        for x, y, text, size, col, font in lines:
            if left <= 0:
                break
            part = text[:left]
            left -= len(text)
            gui.label((px + x, py + y), part, size, col, font)
        # ---- controls
        gui.label((60, 862), self.title or ("THE WAR IN THE NORTH" if self.faction == "US" else "THE DEFENCE OF THE NORTH"),
                  13, (200, 192, 170), "eng")
        gui.label((800, 862), f"{self.i + 1} / {len(self.pages)}", 13, (200, 192, 170), "eng", align="center")
        last = self.i + 1 >= len(self.pages)
        nxt = gui.button(R(1360, 846, 190, 40), "CONTINUE >>" if last else "NEXT >>",
                         color=self.theme.lamp_green, size=13)
        if self.i > 0 and gui.button(R(1150, 846, 190, 40), "<< BACK", size=13):
            self.i -= 1
            self.shown = 1e9
        if gui.button(R(240, 850, 150, 32), "SKIP ALL", size=11, tip="Close the papers and go on"):
            self._done()
            return
        page_click = gui.released and pygame.Rect(px, py, *pg.get_size()).collidepoint(gui.mouse) and not gui.consumed
        keys = [e.key for e in gui.keys]
        if pygame.K_ESCAPE in keys:
            self._done()
            return
        if nxt or page_click or pygame.K_SPACE in keys or pygame.K_RETURN in keys or pygame.K_RIGHT in keys:
            if not full and not nxt:
                self.shown = 1e9
            else:
                self._next()
        elif pygame.K_LEFT in keys and self.i > 0:
            self.i -= 1
            self.shown = 1e9
