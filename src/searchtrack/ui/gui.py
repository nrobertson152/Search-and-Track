"""Immediate-mode widgets drawn as period hardware: painted metal panels,
engraved placards, illuminated pushbuttons, toggle switches, lamps, rotary
selectors, analog meters, CRT glass and scrolling tables."""
from __future__ import annotations

import math
import random

import pygame

from .theme import TEXT, Theme

Rect = pygame.Rect


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Gui:
    def __init__(self, screen: pygame.Surface, theme: Theme, audio=None):
        self.screen = screen
        self.theme = theme
        self.audio = audio
        self.mouse = (0, 0)
        self.down = False
        self.pressed = False       # went down this frame
        self.released = False      # went up this frame
        self.rpressed = False
        self.wheel = 0
        self.press_pos = (0, 0)
        self.keys: list[pygame.event.Event] = []
        self.tooltip: tuple[str, tuple[int, int]] | None = None
        self.scroll: dict[str, int] = {}
        self.time = 0.0
        self.consumed = False
        self.drawn: dict[str, Rect] = {}      # label -> rect of buttons drawn this frame (tests, tutorials)
        self._texture = self._make_texture()

    # ------------------------------------------------------------ frame
    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._texture = self._make_texture()

    def begin(self, events: list[pygame.event.Event], mouse: tuple[int, int], dt: float) -> None:
        self.time += dt
        self.mouse = mouse
        self.pressed = self.released = self.rpressed = False
        self.wheel = 0
        self.keys = []
        self.tooltip = None
        self.consumed = False
        self.drawn = {}
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.down = True
                self.pressed = True
                self.press_pos = e.pos
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                self.down = False
                self.released = True
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                self.rpressed = True
            elif e.type == pygame.MOUSEWHEEL:
                self.wheel += e.y
            elif e.type == pygame.KEYDOWN:
                self.keys.append(e)

    def clicked(self, r: Rect) -> bool:
        if self.consumed or not self.released:
            return False
        if r.collidepoint(self.mouse) and r.collidepoint(self.press_pos):
            self.consumed = True
            if self.audio:
                self.audio.play("click")
            return True
        return False

    def hover(self, r: Rect) -> bool:
        return r.collidepoint(self.mouse)

    def tip(self, r: Rect, text: str | None) -> None:
        if text and r.collidepoint(self.mouse):
            self.tooltip = (text, self.mouse)

    def end(self) -> None:
        if self.tooltip:
            self._draw_tooltip(*self.tooltip)

    # ------------------------------------------------------------ surfaces
    def _make_texture(self) -> pygame.Surface:
        rnd = random.Random(7)
        t = pygame.Surface((128, 128))
        base = self.theme.panel
        t.fill(base)
        for _ in range(2600):
            x, y = rnd.randrange(128), rnd.randrange(128)
            d = rnd.randint(-9, 9)
            c = tuple(max(0, min(255, v + d)) for v in base)
            t.set_at((x, y), c)
        return t

    def panel(self, r: Rect, title: str = "", sub: str = "", screws: bool = True) -> Rect:
        s = self.screen
        th = self.theme
        s.set_clip(r)
        for x in range(r.x, r.right, 128):
            for y in range(r.y, r.bottom, 128):
                s.blit(self._texture, (x, y))
        s.set_clip(None)
        pygame.draw.line(s, th.panel_hi, r.topleft, (r.right - 1, r.y), 2)
        pygame.draw.line(s, th.panel_hi, r.topleft, (r.x, r.bottom - 1), 2)
        pygame.draw.line(s, th.panel_lo, (r.x, r.bottom - 1), (r.right - 1, r.bottom - 1), 2)
        pygame.draw.line(s, th.panel_lo, (r.right - 1, r.y), (r.right - 1, r.bottom - 1), 2)
        if screws and r.w > 60 and r.h > 40:
            for cx, cy in ((r.x + 7, r.y + 7), (r.right - 8, r.y + 7), (r.x + 7, r.bottom - 8), (r.right - 8, r.bottom - 8)):
                pygame.draw.circle(s, th.panel_lo, (cx, cy), 4)
                pygame.draw.circle(s, th.panel_hi, (cx - 1, cy - 1), 3)
                pygame.draw.line(s, th.panel_lo, (cx - 2, cy - 2), (cx + 1, cy + 1), 1)
        inner = r.inflate(-12, -12)
        if title:
            self.placard((r.x + 16, r.y + 6), title, sub)
            inner = Rect(r.x + 8, r.y + 30, r.w - 16, r.h - 38)
        return inner

    def placard(self, pos, title: str, sub: str = "") -> None:
        th = self.theme
        kind = "ui_bold"
        txt = TEXT.render(title, 13, th.engraving, kind)
        sh = TEXT.render(title, 13, th.panel_lo, kind)
        self.screen.blit(sh, (pos[0] + 1, pos[1] + 1))
        self.screen.blit(txt, pos)
        if sub:
            w = txt.get_width()
            self.screen.blit(TEXT.render(sub, 11, th.engraving_dim, "ui"), (pos[0] + w + 10, pos[1] + 2))

    def glass(self, r: Rect, color=None) -> None:
        th = self.theme
        pygame.draw.rect(self.screen, th.panel_lo, r.inflate(6, 6), border_radius=6)
        pygame.draw.rect(self.screen, (0, 0, 0), r.inflate(2, 2), border_radius=4)
        pygame.draw.rect(self.screen, color or th.glass, r, border_radius=3)

    # ------------------------------------------------------------ text
    def label(self, pos, text: str, size: int = 13, color=None, kind: str = "ui", align: str = "left",
              shadow: bool = False) -> int:
        color = color or self.theme.engraving
        surf = TEXT.render(text, size, color, kind)
        x, y = pos
        if align == "right":
            x -= surf.get_width()
        elif align == "center":
            x -= surf.get_width() // 2
        if shadow:
            self.screen.blit(TEXT.render(text, size, (0, 0, 0), kind), (x + 1, y + 1))
        self.screen.blit(surf, (x, y))
        return surf.get_width()

    def crt(self, pos, text: str, size: int = 13, color=None, align: str = "left") -> int:
        kind = "cyr" if self.theme.faction == "USSR" else "ui"
        return self.label(pos, text, size, color or self.theme.text, kind, align)

    def wrapped(self, r: Rect, text: str, size: int = 13, color=None, kind: str = "ui", line_h: int | None = None,
                scroll_id: str | None = None) -> int:
        lines = TEXT.wrap(text, r.w - 4, size, kind)
        lh = line_h or size + 5
        off = 0
        if scroll_id:
            total = len(lines) * lh
            off = self._scroll(scroll_id, r, total)
        self.screen.set_clip(r)
        y = r.y - off
        for ln in lines:
            if y > r.bottom:
                break
            if y + lh >= r.y:
                self.label((r.x + 2, y), ln, size, color or self.theme.text, kind)
            y += lh
        self.screen.set_clip(None)
        return len(lines) * lh

    def _scroll(self, sid: str, r: Rect, total: int, to_end: bool = False) -> int:
        maxoff = max(0, total - r.h)
        off = self.scroll.get(sid, maxoff if to_end else 0)
        if self.hover(r) and self.wheel:
            off -= self.wheel * 40
            self.wheel = 0
        off = max(0, min(off, maxoff))
        self.scroll[sid] = off
        if maxoff > 0:
            bar_h = max(20, int(r.h * r.h / max(total, 1)))
            by = r.y + int((r.h - bar_h) * off / maxoff)
            pygame.draw.rect(self.screen, self.theme.text_dim, (r.right - 4, by, 3, bar_h))
        return off

    # ------------------------------------------------------------ controls
    def button(self, r: Rect, text: str, lit: bool = False, enabled: bool = True, tip: str | None = None,
               color=None, size: int = 12) -> bool:
        th = self.theme
        s = self.screen
        self.drawn[text] = r
        lamp = color or th.lamp_amber
        hov = enabled and self.hover(r)
        face = _mix(th.panel_lo, (0, 0, 0), 0.35)
        pygame.draw.rect(s, (0, 0, 0), r.move(1, 2), border_radius=3)
        if lit:
            pulse = 0.85 + 0.15 * math.sin(self.time * 3.0)
            fill = _mix(face, lamp, 0.55 * pulse)
        else:
            fill = _mix(face, th.panel_hi, 0.18 if hov else 0.06)
        pygame.draw.rect(s, fill, r, border_radius=3)
        pygame.draw.rect(s, th.panel_hi if not lit else lamp, r, 1, border_radius=3)
        tcol = (20, 14, 6) if lit else (th.engraving if enabled else th.engraving_dim)
        self.label((r.centerx, r.centery - size // 2 - 2), text, size, tcol, "ui_bold", "center")
        self.tip(r, tip)
        return enabled and self.clicked(r)

    def toggle(self, r: Rect, text: str, value: bool, tip: str | None = None) -> bool:
        th = self.theme
        s = self.screen
        sw = Rect(r.x, r.y + (r.h - 22) // 2, 14, 22)
        pygame.draw.rect(s, (0, 0, 0), sw.inflate(4, 4), border_radius=4)
        pygame.draw.rect(s, (60, 62, 64), sw, border_radius=3)
        lever_y = sw.y + 3 if value else sw.bottom - 11
        pygame.draw.rect(s, (210, 210, 205), (sw.x + 2, lever_y, sw.w - 4, 8), border_radius=2)
        self.lamp((sw.right + 9, r.centery), th.lamp_green, value, radius=4)
        self.label((sw.right + 18, r.centery - 8), text, 12, th.engraving)
        self.tip(r, tip)
        if self.clicked(r):
            return not value
        return value

    def lamp(self, c, color, on: bool = True, radius: int = 6, blink: bool = False, tip: str | None = None,
             label: str = "") -> None:
        s = self.screen
        if blink and on:
            on = math.sin(self.time * 7.0) > -0.2
        pygame.draw.circle(s, (0, 0, 0), c, radius + 2)
        if on:
            g = int(radius * 2.2)
            glow = pygame.Surface((g * 2, g * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, 26), (g, g), g)
            pygame.draw.circle(glow, (*color, 30), (g, g), int(g * 0.7))
            s.blit(glow, (c[0] - g, c[1] - g))
            pygame.draw.circle(s, color, c, radius)
            pygame.draw.circle(s, _mix(color, (255, 255, 255), 0.6), (c[0] - radius // 3, c[1] - radius // 3),
                               max(1, radius // 3))
        else:
            pygame.draw.circle(s, _mix(color, (0, 0, 0), 0.78), c, radius)
        if label:
            self.label((c[0] + radius + 8, c[1] - 8), label, 11, self.theme.engraving)
        if tip:
            self.tip(Rect(c[0] - radius, c[1] - radius, radius * 2, radius * 2), tip)

    def knob(self, r: Rect, label: str, value: str, tip: str | None = None) -> int:
        """Rotary selector: click the left half to step down, right half to step up (or use the wheel)."""
        th = self.theme
        s = self.screen
        c = (r.x + r.h // 2, r.centery)
        rad = r.h // 2 - 2
        pygame.draw.circle(s, (0, 0, 0), (c[0] + 1, c[1] + 2), rad + 1)
        pygame.draw.circle(s, (40, 40, 42), c, rad)
        pygame.draw.circle(s, (90, 90, 94), c, rad, 2)
        ang = (sum(map(ord, value)) % 7) / 7.0 * 4.5 - 2.25
        pygame.draw.line(s, (230, 230, 220), c, (c[0] + rad * 0.8 * math.sin(ang), c[1] - rad * 0.8 * math.cos(ang)), 3)
        self.label((r.x + r.h + 6, r.y + 1), label, 11, th.engraving_dim)
        self.label((r.x + r.h + 6, r.y + r.h // 2), value, 12, th.engraving, "ui_bold")
        self.tip(r, tip)
        step = 0
        if self.hover(r) and self.wheel:
            step = 1 if self.wheel > 0 else -1
            self.wheel = 0
        elif self.clicked(r):
            step = -1 if self.mouse[0] < r.x + r.h // 2 else 1
        return step

    def meter(self, r: Rect, value: float, label: str, tip: str | None = None, danger: float = 1.1) -> None:
        th = self.theme
        s = self.screen
        pygame.draw.rect(s, (0, 0, 0), r.inflate(4, 4), border_radius=4)
        pygame.draw.rect(s, (232, 226, 205), r, border_radius=3)
        c = (r.centerx, r.bottom - 6)
        rad = min(r.w // 2 - 6, r.h - 14)
        for i in range(11):
            a = math.radians(-60 + i * 12)
            p1 = (c[0] + rad * math.sin(a), c[1] - rad * math.cos(a))
            p2 = (c[0] + (rad - (7 if i % 5 == 0 else 4)) * math.sin(a), c[1] - (rad - (7 if i % 5 == 0 else 4)) * math.cos(a))
            col = (190, 40, 30) if i / 10 >= danger else (30, 30, 30)
            pygame.draw.line(s, col, p1, p2, 2 if i % 5 == 0 else 1)
        v = max(0.0, min(1.05, value))
        a = math.radians(-60 + v * 120)
        pygame.draw.line(s, (20, 20, 20), c, (c[0] + (rad - 2) * math.sin(a), c[1] - (rad - 2) * math.cos(a)), 2)
        pygame.draw.circle(s, (20, 20, 20), c, 3)
        self.label((r.centerx, r.y + 2), label, 10, (40, 40, 40), "ui_bold", "center")
        self.tip(r, tip)

    def table(self, sid: str, r: Rect, cols: list[tuple[str, int]], rows: list[list[str]], selected: int = -1,
              colors: list | None = None, size: int = 12, row_h: int = 18) -> int | None:
        """Scrollable selectable table drawn on CRT glass. Returns clicked row index."""
        th = self.theme
        self.glass(r)
        x = r.x + 6
        kind = "cyr" if th.faction == "USSR" else "ui"
        for name, w in cols:
            self.label((x, r.y + 3), name, size - 1, th.text_dim, kind)
            x += w
        body = Rect(r.x, r.y + row_h + 4, r.w, r.h - row_h - 6)
        off = self._scroll(sid, body, len(rows) * row_h)
        hit = None
        self.screen.set_clip(body)
        for i, row in enumerate(rows):
            y = body.y + i * row_h - off
            if y + row_h < body.y or y > body.bottom:
                continue
            rr = Rect(r.x + 2, y, r.w - 8, row_h)
            if i == selected:
                pygame.draw.rect(self.screen, _mix(th.glass, th.text, 0.22), rr)
            elif self.hover(rr) and self.hover(body):
                pygame.draw.rect(self.screen, _mix(th.glass, th.text, 0.08), rr)
            x = r.x + 6
            col = (colors[i] if colors and i < len(colors) and colors[i] else th.text)
            for (name, w), cell in zip(cols, row):
                txt = str(cell)
                while TEXT.width(txt, size, kind) > w - 6 and len(txt) > 1:
                    txt = txt[:-1]
                self.label((x, y + 1), txt, size, col, kind)
                x += w
            if self.hover(body) and self.clicked(rr):
                hit = i
        self.screen.set_clip(None)
        return hit

    def log(self, sid: str, r: Rect, lines: list[tuple[str, tuple]], size: int = 12, kind: str = "ui",
            follow: bool = True) -> None:
        self.glass(r)
        inner = r.inflate(-10, -8)
        wrapped: list[tuple[str, tuple]] = []
        for text, col in lines:
            for ln in TEXT.wrap(text, inner.w - 8, size, kind):
                wrapped.append((ln, col))
        lh = size + 4
        total = len(wrapped) * lh
        key = sid
        prev_total = self.scroll.get(key + "#t", 0)
        if follow and total != prev_total and self.scroll.get(key, 0) >= max(0, prev_total - inner.h) - lh:
            self.scroll[key] = max(0, total - inner.h)
        self.scroll[key + "#t"] = total
        off = self._scroll(key, inner, total, to_end=True)
        self.screen.set_clip(inner)
        y = inner.y - off
        for ln, col in wrapped:
            if y > inner.bottom:
                break
            if y + lh >= inner.y:
                self.label((inner.x, y), ln, size, col, kind)
            y += lh
        self.screen.set_clip(None)

    def _draw_tooltip(self, text: str, pos) -> None:
        th = self.theme
        lines = TEXT.wrap(text, 340, 12, "ui")
        w = max(TEXT.width(ln, 12) for ln in lines) + 16
        h = len(lines) * 16 + 10
        sw, sh = self.screen.get_size()
        x = min(pos[0] + 16, sw - w - 4)
        y = min(pos[1] + 18, sh - h - 4)
        box = Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (0, 0, 0), box.move(2, 3), border_radius=3)
        pygame.draw.rect(self.screen, (238, 232, 206), box, border_radius=3)
        pygame.draw.rect(self.screen, (90, 80, 60), box, 1, border_radius=3)
        for i, ln in enumerate(lines):
            self.label((x + 8, y + 5 + i * 16), ln, 12, (30, 26, 20))
