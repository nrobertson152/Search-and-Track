"""Immediate-mode widgets drawn as period hardware.

Everything the player touches is a physical control: painted panels with
nameplates and screws, square lamp pushbuttons with milky lenses (US) or
skirted keycaps with backlit legends (USSR), jewel lamps, annunciator tiles,
bat-handle toggles, chicken-head selectors, analog meters, LED windows and
CRT glass with scanlines and reflections of the room's ceiling lights.

Complex pieces are rendered once into cached surfaces keyed by size and state,
so a full console costs little per frame."""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

from . import lang
from .theme import TEXT, Theme

Rect = pygame.Rect


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _scale(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def _legend_ink(c) -> tuple:
    """Dark legend colour that reads on a lit lens of colour c."""
    return _mix(c, (0, 0, 0), 0.82)


def _vgrad(w: int, h: int, top, bottom) -> pygame.Surface:
    s = pygame.Surface((max(1, w), max(1, h)))
    for y in range(h):
        pygame.draw.line(s, _mix(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return s


def _rounded_mask(surf: pygame.Surface, radius: int) -> None:
    """Make the corners of an SRCALPHA surface transparent."""
    w, h = surf.get_size()
    m = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(m, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    surf.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)


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
        self.highlight: set[str] = set()      # labels the instructor wants pointed out
        self.lang_mode = "en"                 # legends are English; the PVO plotting board keeps its Russian lettering
        self._cache: dict[tuple, pygame.Surface] = {}
        self._texture = self._make_texture()

    # ------------------------------------------------------------ frame
    def set_theme(self, theme: Theme) -> None:
        if theme is self.theme:
            return
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
        self.highlight = set()
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
        if self.highlight:
            self._draw_highlights()
        if self.tooltip:
            self._draw_tooltip(*self.tooltip)

    def cached(self, key: tuple, make) -> pygame.Surface:
        s = self._cache.get(key)
        if s is None:
            if len(self._cache) > 1500:
                self._cache.clear()
            s = make()
            self._cache[key] = s
        return s

    # ------------------------------------------------------------ language
    def tr(self, text: str) -> tuple[str, str]:
        return lang.legend(text, self.theme.faction, self.lang_mode)

    @property
    def ussr(self) -> bool:
        return self.theme.faction == "USSR"

    # ------------------------------------------------------------ paint
    def _make_texture(self) -> pygame.Surface:
        th = self.theme
        rng = np.random.default_rng(7 if th.panel_style == "plastic" else 11)
        n = 256
        base = np.array(th.panel, dtype=np.float32)
        if th.panel_style == "enamel":
            # hammer-tone: soft cells plus dimples
            low = rng.normal(0, 1, (24, 24)).astype(np.float32)
            low_s = pygame.surfarray.make_surface(np.repeat(((low - low.min()) / np.ptp(low) * 255)[:, :, None], 3, 2)
                                                  .astype(np.uint8))
            low_big = pygame.transform.smoothscale(low_s, (n, n))
            cells = pygame.surfarray.array3d(low_big)[:, :, 0].astype(np.float32) / 255.0 - 0.5
            fine = rng.normal(0, 1, (n, n)).astype(np.float32)
            v = cells * 9.0 + fine * 2.2
        else:
            low = rng.normal(0, 1, (12, 12)).astype(np.float32)
            low_s = pygame.surfarray.make_surface(np.repeat(((low - low.min()) / np.ptp(low) * 255)[:, :, None], 3, 2)
                                                  .astype(np.uint8))
            mott = pygame.surfarray.array3d(pygame.transform.smoothscale(low_s, (n, n)))[:, :, 0].astype(np.float32) / 255.0 - 0.5
            fine = rng.normal(0, 1, (n, n)).astype(np.float32)
            v = mott * 6.0 + fine * 3.0
        arr = np.clip(base[None, None, :] + v[:, :, None], 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(arr)

    def _panel_surface(self, w: int, h: int) -> pygame.Surface:
        th = self.theme
        rad = 9 if th.panel_style == "plastic" else 3
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(0, w, 256):
            for y in range(0, h, 256):
                s.blit(self._texture, (x, y))
        # light falls from above: subtle vertical shading
        shade = _vgrad(w, h, (255, 255, 255), (150, 150, 150))
        s.blit(shade, (0, 0), special_flags=pygame.BLEND_MULT)
        # bevel
        if th.panel_style == "plastic":
            pygame.draw.rect(s, th.trim, (0, 0, w, h), 3, border_radius=rad)
            pygame.draw.line(s, th.panel_hi, (rad, 3), (w - rad, 3), 2)
            pygame.draw.line(s, _scale(th.panel_hi, 0.95), (3, rad), (3, h - rad), 1)
            pygame.draw.line(s, th.panel_lo, (rad, h - 4), (w - rad, h - 4), 2)
            pygame.draw.line(s, th.panel_lo, (w - 4, rad), (w - 4, h - rad), 1)
        else:
            pygame.draw.rect(s, (12, 14, 16), (0, 0, w, h), 2, border_radius=rad)
            pygame.draw.line(s, th.panel_hi, (2, 2), (w - 3, 2), 1)
            pygame.draw.line(s, th.panel_hi, (2, 2), (2, h - 3), 1)
            pygame.draw.line(s, th.panel_lo, (2, h - 3), (w - 3, h - 3), 1)
            pygame.draw.line(s, th.panel_lo, (w - 3, 2), (w - 3, h - 3), 1)
        _rounded_mask(s, rad)
        return s

    def panel(self, r: Rect, title: str = "", sub: str = "", screws: bool = True) -> Rect:
        th = self.theme
        surf = self.cached(("panel", th.name, r.w, r.h), lambda: self._panel_surface(r.w, r.h))
        self.screen.blit(surf, r.topleft)
        if screws and r.w > 60 and r.h > 40:
            for cx, cy in ((r.x + 9, r.y + 9), (r.right - 10, r.y + 9), (r.x + 9, r.bottom - 10),
                           (r.right - 10, r.bottom - 10)):
                self.screw((cx, cy))
        inner = r.inflate(-14, -14)
        if title:
            self.placard((r.x + 22, r.y + 7), title, sub)
            inner = Rect(r.x + 10, r.y + 34, r.w - 20, r.h - 44)
        return inner

    def screw(self, c, radius: int = 4) -> None:
        th = self.theme
        s = self.screen
        ang = ((c[0] * 73 + c[1] * 151) % 180) * math.pi / 180.0
        pygame.draw.circle(s, _scale(th.panel_lo, 0.7), (c[0] + 1, c[1] + 1), radius + 1)
        pygame.draw.circle(s, _mix(th.panel_hi, (200, 200, 196), 0.4), c, radius)
        pygame.draw.circle(s, _scale(th.panel_hi, 0.75), c, radius, 1)
        dx, dy = math.cos(ang) * (radius - 1), math.sin(ang) * (radius - 1)
        col = _scale(th.panel_lo, 0.6)
        pygame.draw.line(s, col, (c[0] - dx, c[1] - dy), (c[0] + dx, c[1] + dy), 1)
        if th.panel_style == "plastic":     # Phillips
            pygame.draw.line(s, col, (c[0] + dy, c[1] - dx), (c[0] - dy, c[1] + dx), 1)

    def placard(self, pos, title: str, sub: str = "") -> int:
        """Nameplate: black engraved phenolic (US) or white paint (USSR). Returns width used."""
        th = self.theme
        has_cyr = any("Ѐ" <= ch <= "ӿ" for ch in title)
        if self.ussr and not has_cyr:
            main, strip = self.tr(title)
            if strip:
                sub = strip + (" · " + sub if sub else "")
            title = main
        x, y = pos
        if th.panel_style == "plastic":
            txt = TEXT.render(title.upper(), 13, th.plate_text, "eng")
            pr = Rect(x - 8, y - 2, txt.get_width() + 16, 21)
            pygame.draw.rect(self.screen, (0, 0, 0), pr.move(1, 2), border_radius=2)
            pygame.draw.rect(self.screen, th.plate, pr, border_radius=2)
            pygame.draw.line(self.screen, (70, 66, 60), (pr.x + 2, pr.y + 1), (pr.right - 3, pr.y + 1))
            self.screen.blit(txt, (x, y))
            for sx in (pr.x + 3, pr.right - 4):
                pygame.draw.circle(self.screen, (120, 116, 108), (sx, pr.centery), 1)
            w = pr.w
            if sub:
                self.screen.blit(TEXT.render(sub, 12, th.engraving_dim, "eng_r"), (pr.right + 10, y + 2))
            return w
        txt = TEXT.render(title, 15, th.engraving, "eng")
        self.screen.blit(TEXT.render(title, 15, (0, 0, 0), "eng"), (x + 1, y + 1))
        self.screen.blit(txt, (x, y - 1))
        if sub:
            self.screen.blit(TEXT.render(sub.upper(), 11, th.engraving_dim, "eng_r"), (x + txt.get_width() + 12, y + 3))
        return txt.get_width()

    def eng(self, pos, text: str, size: int = 12, color=None, align: str = "left", strip: bool = True) -> int:
        """Engraved/silk-screened panel lettering (Russian on Soviet panels)."""
        th = self.theme
        main, en = self.tr(text)
        col = color or th.engraving
        w = self.label(pos, main, size, col, "eng", align)
        if strip and en and en != main and align == "left":
            self.label((pos[0] + w + 6, pos[1] + max(0, size - 11) // 2 + 2), en, max(8, size - 3),
                       th.engraving_dim, "eng_r")
        return w

    # ------------------------------------------------------------ glass
    def glass(self, r: Rect, color=None, bezel: bool = True) -> None:
        th = self.theme
        s = self.screen
        if bezel:
            outer = r.inflate(14, 14)
            pygame.draw.rect(s, (0, 0, 0), outer.move(0, 2), border_radius=9)
            pygame.draw.rect(s, th.bezel, outer, border_radius=9)
            pygame.draw.rect(s, th.bezel_hi, outer, 1, border_radius=9)
            pygame.draw.line(s, th.bezel_hi, (outer.x + 8, outer.y + 1), (outer.right - 9, outer.y + 1))
            pygame.draw.line(s, th.bezel_lo, (outer.x + 8, outer.bottom - 2), (outer.right - 9, outer.bottom - 2))
            pygame.draw.rect(s, th.bezel_lo, r.inflate(6, 6), border_radius=7)
        pygame.draw.rect(s, (0, 0, 0), r.inflate(2, 2), border_radius=6)
        pygame.draw.rect(s, color or th.glass, r, border_radius=6)

    def _overlay_surface(self, w: int, h: int, scan: bool, strength: float) -> pygame.Surface:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        a = np.zeros((w, h), dtype=np.float32)
        if scan:
            a[:, ::3] += 20
        yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32))
        nx = (xx - w / 2) / (w / 2)
        ny = (yy - h / 2) / (h / 2)
        d = np.sqrt(nx * nx * 0.9 + ny * ny * 1.1)
        a += np.clip((d - 0.62) / 0.6, 0, 1) ** 1.6 * 150 * strength
        dark = np.clip(a, 0, 255).astype(np.uint8)
        s.fill((0, 0, 0, 255))
        pygame.surfarray.pixels_alpha(s)[:] = dark
        # reflections of the room: a soft diagonal sheen and two ceiling strip lights
        refl = pygame.Surface((w, h), pygame.SRCALPHA)
        ra = np.zeros((w, h), dtype=np.float32)
        band = np.exp(-(((xx * 0.55 + yy) - (w * 0.12)) / (w * 0.10 + 1)) ** 2) * 12 * strength
        ra += band * np.clip(1.0 - yy / (h * 0.8), 0, 1)
        for k, (y0, x0, x1) in enumerate(((0.10, 0.08, 0.52), (0.17, 0.60, 0.95))):
            cy = y0 * h + 0.05 * h * ((xx / w) - 0.5) ** 2 * 4      # slightly curved with the glass
            inside = (xx > x0 * w) & (xx < x1 * w)
            ra += np.where(inside, np.exp(-((yy - cy) / 2.2) ** 2) * (16 - 5 * k) * strength, 0)
        refl.fill((235, 240, 245, 255))
        pygame.surfarray.pixels_alpha(refl)[:] = np.clip(ra, 0, 255).astype(np.uint8)
        s.blit(refl, (0, 0))
        return s

    def crt_overlay(self, r: Rect, scan: bool = True, strength: float = 1.0) -> None:
        surf = self.cached(("ovl", r.w, r.h, scan, round(strength, 2)),
                           lambda: self._overlay_surface(r.w, r.h, scan, strength))
        self.screen.blit(surf, r.topleft)

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
        return self.label(pos, text, size, color or self.theme.text, self.theme.data_font, align)

    def wrapped(self, r: Rect, text: str, size: int = 13, color=None, kind: str = "ui", line_h: int | None = None,
                scroll_id: str | None = None) -> int:
        lines = TEXT.wrap(text, r.w - 8, size, kind)
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

    # ------------------------------------------------------------ pushbuttons
    def _key_surface(self, w: int, h: int, lit: bool, lampc, hov: bool, press: bool, enabled: bool) -> pygame.Surface:
        th = self.theme
        pad = 10
        S = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        body = Rect(pad, pad, w, h)
        if lit:
            for i in range(6, 0, -1):          # glow spilling onto the panel
                g = body.inflate(i * 3, i * 3)
                pygame.draw.rect(S, (*lampc, int(9 + (6 - i) * 4)), g, border_radius=6 + i)
        if th.key_style == "lens":
            pygame.draw.rect(S, (0, 0, 0, 200), body.move(0, 2), border_radius=3)
            pygame.draw.rect(S, (24, 20, 16), body, border_radius=3)
            pygame.draw.line(S, (66, 58, 48), (body.x + 3, body.y + 1), (body.right - 4, body.y + 1))
            lens = body.inflate(-6, -6).move(0, 1 if press else 0)
            if lit:
                top = _mix(lampc, (255, 255, 255), 0.45)
                bot = _scale(lampc, 0.78)
            elif enabled:
                top = _mix(th.key_hi, (255, 255, 255), 0.12 if hov else 0.0)
                bot = th.key_lo
            else:
                top, bot = _scale(th.key_hi, 0.62), _scale(th.key_lo, 0.6)
            g = _vgrad(lens.w, lens.h, top, bot)
            S.blit(g, lens.topleft)
            if lit:      # hot centre of the bulb
                hot = pygame.Surface(lens.size, pygame.SRCALPHA)
                pygame.draw.ellipse(hot, (255, 255, 240, 70), hot.get_rect().inflate(-lens.w * 0.3, -lens.h * 0.2))
                S.blit(hot, lens.topleft)
            pygame.draw.rect(S, _scale(bot, 0.55), lens, 1)
            pygame.draw.line(S, (255, 255, 255, 60), (lens.x + 1, lens.y + 1), (lens.right - 2, lens.y + 1))
        else:
            dy = 2 if press else 0
            pygame.draw.rect(S, (0, 0, 0, 150), body.move(0, 3), border_radius=5)
            skirt = _scale(lampc, 0.62) if lit else (th.key_lo if enabled else _scale(th.key_lo, 0.7))
            pygame.draw.rect(S, skirt, body.move(0, dy), border_radius=5)
            face = Rect(body.x + 3, body.y + 1 + dy, body.w - 6, body.h - 6)
            if lit:
                top = _mix(lampc, (255, 255, 255), 0.42)
                bot = _scale(lampc, 0.9)
            elif enabled:
                top = _mix(th.key_hi, (255, 255, 255), 0.25 if hov else 0.0)
                bot = th.key_face
            else:
                top, bot = _scale(th.key_hi, 0.66), _scale(th.key_face, 0.62)
            g = _vgrad(face.w, face.h, top, bot)
            fs = pygame.Surface(face.size, pygame.SRCALPHA)
            fs.blit(g, (0, 0))
            _rounded_mask(fs, 4)
            S.blit(fs, face.topleft)
            pygame.draw.rect(S, (255, 255, 255, 90), face, 1, border_radius=4)
        return S

    def button(self, r: Rect, text: str, lit: bool = False, enabled: bool = True, tip: str | None = None,
               color=None, size: int = 12) -> bool:
        th = self.theme
        self.drawn[text] = r
        lampc = color or th.key_lit
        hov = enabled and self.hover(r)
        press = hov and self.down and r.collidepoint(self.press_pos)
        if lit:
            pulse = 0.92 + 0.08 * math.sin(self.time * 3.0)
            lampc = _scale(lampc, pulse) if color is not None else lampc
            lampc = tuple(int(v) // 8 * 8 for v in lampc)          # quantize for the surface cache
        surf = self.cached(("key", th.name, r.w, r.h, lit, lampc, hov, press, enabled),
                           lambda: self._key_surface(r.w, r.h, lit, lampc, hov, press, enabled))
        self.screen.blit(surf, (r.x - 10, r.y - 10))
        main, strip = self.tr(text)
        if lit:
            ink = _legend_ink(lampc)
        else:
            ink = th.key_legend if enabled else th.key_legend_dim
        dy = (2 if press else 0) if th.key_style == "keycap" else (1 if press else 0)
        face_h = r.h - (6 if th.key_style == "keycap" else 6)
        two = bool(strip) and face_h >= 20
        fsize = size + 1
        maxw = r.w - 10
        while fsize > 8 and TEXT.width(main, fsize, "eng") > maxw:
            fsize -= 1
        cy = r.y + (1 if th.key_style == "keycap" else 3) + face_h // 2 + dy
        if two:
            ssize = max(7, min(9, fsize - 3))
            while ssize > 6 and TEXT.width(strip, ssize, "eng_r") > maxw:
                ssize -= 1
            th_main = TEXT.font("eng", fsize).get_height()
            th_sub = TEXT.font("eng_r", ssize).get_height()
            top = cy - (th_main + th_sub - 4) // 2
            self.label((r.centerx, top), main, fsize, ink, "eng", "center")
            self.label((r.centerx, top + th_main - 4), strip, ssize, _mix(ink, lampc if lit else th.key_face, 0.35),
                       "eng_r", "center")
        else:
            hgt = TEXT.font("eng", fsize).get_height()
            self.label((r.centerx, cy - hgt // 2), main, fsize, ink, "eng", "center")
        if strip and not two and tip is None:
            tip = strip
        elif strip and not two:
            tip = f"{strip} — {tip}"
        self.tip(r, tip)
        return enabled and self.clicked(r)

    # ------------------------------------------------------------ lamps & indicators
    def _jewel(self, radius: int, color, on: bool) -> pygame.Surface:
        g = int(radius * 3.2) if on else radius + 3
        S = pygame.Surface((g * 2 + 1, g * 2 + 1), pygame.SRCALPHA)
        c = (g, g)
        if on:
            for i in range(10, 0, -1):
                rr = radius + (g - radius) * i / 10
                pygame.draw.circle(S, (*color, int(4 + (10 - i) * 3.2)), c, int(rr))
        pygame.draw.circle(S, (16, 16, 16), c, radius + 2)
        pygame.draw.circle(S, (96, 96, 92), c, radius + 2, 1)
        if on:
            for i in range(radius, 0, -1):
                f = i / radius
                pygame.draw.circle(S, _mix(_mix(color, (255, 255, 255), 0.65), color, f ** 0.7), c, i)
        else:
            pygame.draw.circle(S, _scale(color, 0.26), c, radius)
            pygame.draw.circle(S, _scale(color, 0.4), (c[0], c[1] + 1), max(1, radius - 2))
        # facets and specular
        pygame.draw.circle(S, (255, 255, 255, 150 if on else 70), (c[0] - radius // 3, c[1] - radius // 3),
                           max(1, radius // 3))
        return S

    def lamp(self, c, color, on: bool = True, radius: int = 6, blink: bool = False, tip: str | None = None,
             label: str = "", ink=None) -> None:
        if blink and on:
            on = math.sin(self.time * 7.0) > -0.2
        col = tuple(int(v) for v in color[:3])
        surf = self.cached(("jewel", radius, col, on), lambda: self._jewel(radius, col, on))
        self.screen.blit(surf, (c[0] - surf.get_width() // 2, c[1] - surf.get_height() // 2))
        if label:
            self.eng((c[0] + radius + 8, c[1] - 8), label, 12, color=ink, strip=False)
            if self.ussr:
                tip = tip or label
        if tip:
            self.tip(Rect(c[0] - radius - 2, c[1] - radius - 2, radius * 2 + 4 + (80 if label else 0), radius * 2 + 4), tip)

    def annunciator(self, r: Rect, text: str, color, on: bool, blink: bool = False, tip: str | None = None,
                    size: int = 11) -> None:
        """Back-lit legend tile, as on caution/warning panels."""
        if blink and on:
            on = math.sin(self.time * 6.5) > -0.3
        col = tuple(int(v) for v in color[:3])
        key = ("ann", r.w, r.h, col, on)

        def make():
            pad = 8
            S = pygame.Surface((r.w + pad * 2, r.h + pad * 2), pygame.SRCALPHA)
            body = Rect(pad, pad, r.w, r.h)
            if on:
                for i in range(5, 0, -1):
                    pygame.draw.rect(S, (*col, 8 + (5 - i) * 5), body.inflate(i * 3, i * 3), border_radius=4 + i)
            pygame.draw.rect(S, (10, 10, 10), body.inflate(4, 4), border_radius=3)
            if on:
                g = _vgrad(r.w, r.h, _mix(col, (255, 255, 255), 0.35), _scale(col, 0.8))
            else:
                g = _vgrad(r.w, r.h, _mix(_scale(col, 0.18), (40, 40, 40), 0.6), _scale(col, 0.12))
            S.blit(g, body.topleft)
            pygame.draw.line(S, (255, 255, 255, 50), (body.x + 1, body.y + 1), (body.right - 2, body.y + 1))
            return S
        surf = self.cached(key, make)
        self.screen.blit(surf, (r.x - 8, r.y - 8))
        ink = _legend_ink(col) if on else _mix(_scale(col, 0.4), (90, 90, 90), 0.5)
        lines = []
        for part in text.split("\n"):
            main, _ = self.tr(part)
            lines.append(main)
        lh = size + 2
        y0 = r.centery - (len(lines) * lh) // 2 - 1
        for i, ln in enumerate(lines):
            fs = size
            while fs > 7 and TEXT.width(ln, fs, "eng") > r.w - 6:
                fs -= 1
            self.label((r.centerx, y0 + i * lh), ln, fs, ink, "eng", "center")
        if self.ussr and tip is None:
            tip = text.replace("\n", " ")
        self.tip(r, tip)

    def led(self, r: Rect, text: str, color, size: int = 26, ghost: str | None = None, align: str = "left") -> None:
        """Seven-segment style window: unlit segments ghost behind the digits."""
        s = self.screen
        pygame.draw.rect(s, (0, 0, 0), r.inflate(6, 6), border_radius=4)
        pygame.draw.rect(s, _scale(color, 0.06), r, border_radius=3)
        gh = ghost if ghost is not None else "".join("8" if ch.isdigit() else ch for ch in text)
        x = r.x + 8 if align == "left" else r.right - 8 - TEXT.width(text, size, "crt")
        y = r.centery - TEXT.font("crt", size).get_height() // 2
        self.label((x, y), gh, size, _scale(color, 0.16), "crt")
        gcol = _scale(color, 0.35)
        glow = self.cached(("ledglow", text, size, gcol),
                           lambda: TEXT.font("crt", size).render(text, True, gcol, (0, 0, 0)))
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            s.blit(glow, (x + ox, y + oy), special_flags=pygame.BLEND_ADD)
        self.label((x, y), text, size, color, "crt")

    # ------------------------------------------------------------ switches & knobs
    def toggle(self, r: Rect, text: str, value: bool, tip: str | None = None) -> bool:
        th = self.theme
        s = self.screen
        self.drawn[text] = r
        c = (r.x + 11, r.centery)
        # hex nut and bushing
        pts = [(c[0] + 9 * math.cos(math.pi / 6 + k * math.pi / 3), c[1] + 9 * math.sin(math.pi / 6 + k * math.pi / 3))
               for k in range(6)]
        pygame.draw.polygon(s, (0, 0, 0), [(x + 1, y + 2) for x, y in pts])
        pygame.draw.polygon(s, (150, 150, 146), pts)
        pygame.draw.polygon(s, (90, 90, 86), pts, 1)
        pygame.draw.circle(s, (70, 70, 68), c, 5)
        # bat handle
        tip_y = c[1] - 12 if value else c[1] + 12
        pygame.draw.line(s, (20, 20, 20), (c[0] + 1, c[1] + 1), (c[0] + 1, tip_y + 1), 5)
        pygame.draw.line(s, (196, 196, 190), c, (c[0], tip_y), 4)
        pygame.draw.circle(s, (226, 226, 220), (c[0], tip_y), 3)
        pygame.draw.line(s, (250, 250, 246), (c[0] - 1, c[1]), (c[0] - 1, tip_y), 1)
        on_l = "ВКЛ" if self.ussr and self.lang_mode != "en" else "ON"
        self.label((r.x + 24, r.y - 1), on_l, 9, th.engraving_dim, "eng_r")
        self.lamp((r.x + 32, r.centery + 5), th.lamp_green, value, radius=4)
        self.eng((r.x + 44, r.centery - 8), text, 12)
        self.tip(r, tip)
        if self.clicked(r):
            if self.audio:
                self.audio.play("switch")
            return not value
        return value

    def knob(self, r: Rect, label: str, value: str, tip: str | None = None, pos: float | None = None,
             ink=None) -> int:
        """Chicken-head selector: click the left half to step down, right half to step up (or use the wheel)."""
        th = self.theme
        s = self.screen
        self.drawn[label] = r
        rad = r.h // 2 - 2
        c = (r.x + r.h // 2, r.centery + 1)
        if pos is None:
            pos = (sum(map(ord, value)) % 7) / 6.0
        ang = -2.3 + 4.6 * max(0.0, min(1.0, pos))
        for k in range(7):          # detent marks
            a = -2.3 + 4.6 * k / 6
            p1 = (c[0] + (rad + 2) * math.sin(a), c[1] - (rad + 2) * math.cos(a))
            p2 = (c[0] + (rad + 5) * math.sin(a), c[1] - (rad + 5) * math.cos(a))
            pygame.draw.line(s, ink or th.engraving_dim, p1, p2, 1)
        pygame.draw.circle(s, (0, 0, 0), (c[0] + 1, c[1] + 2), rad)
        pygame.draw.circle(s, (34, 32, 30), c, rad)
        pygame.draw.circle(s, (70, 68, 64), c, rad, 1)
        # pointer body
        ux, uy = math.sin(ang), -math.cos(ang)
        tipp = (c[0] + ux * (rad + 3), c[1] + uy * (rad + 3))
        tail = (c[0] - ux * rad * 0.6, c[1] - uy * rad * 0.6)
        px, py = -uy, ux
        poly = [tipp, (c[0] + px * 4, c[1] + py * 4), tail, (c[0] - px * 4, c[1] - py * 4)]
        pygame.draw.polygon(s, (16, 16, 16), poly)
        pygame.draw.line(s, (236, 232, 220), c, tipp, 2)
        self.eng((r.x + r.h + 8, r.y - 1), label, 11, ink or th.engraving_dim, strip=False)
        win = Rect(r.x + r.h + 8, r.y + r.h // 2 - 2, max(60, r.w - r.h - 12), 16)
        pygame.draw.rect(s, (0, 0, 0), win.inflate(2, 2), border_radius=2)
        pygame.draw.rect(s, th.glass, win, border_radius=2)
        self.label((win.x + 4, win.y), value, 12, th.text, th.data_font)
        if self.ussr:
            tip = (tip + " — " if tip else "") + label
        self.tip(r, tip)
        step = 0
        if self.hover(r) and self.wheel:
            step = 1 if self.wheel > 0 else -1
            self.wheel = 0
        elif self.clicked(r):
            step = -1 if self.mouse[0] < c[0] else 1
        return step

    def meter(self, r: Rect, value: float, label: str, tip: str | None = None, danger: float = 1.1) -> None:
        th = self.theme
        s = self.screen
        pygame.draw.rect(s, (0, 0, 0), r.inflate(6, 6), border_radius=4)
        pygame.draw.rect(s, (24, 24, 22), r.inflate(4, 4), border_radius=4)
        face = (236, 230, 208) if not self.ussr else (226, 228, 222)
        pygame.draw.rect(s, face, r, border_radius=3)
        c = (r.centerx, r.bottom - 5)
        rad = min(r.w // 2 - 6, r.h - 12)
        for i in range(11):
            a = math.radians(-55 + i * 11)
            ln = 7 if i % 5 == 0 else 4
            p1 = (c[0] + rad * math.sin(a), c[1] - rad * math.cos(a))
            p2 = (c[0] + (rad - ln) * math.sin(a), c[1] - (rad - ln) * math.cos(a))
            col = (190, 40, 30) if i / 10 >= danger else (30, 30, 30)
            pygame.draw.line(s, col, p1, p2, 2 if i % 5 == 0 else 1)
        if danger < 1.0:
            pts = [(c[0] + (rad + 1) * math.sin(math.radians(-55 + 110 * f)),
                    c[1] - (rad + 1) * math.cos(math.radians(-55 + 110 * f))) for f in np.linspace(danger, 1.0, 8)]
            if len(pts) > 1:
                pygame.draw.lines(s, (200, 50, 40), False, pts, 2)
        v = max(0.0, min(1.05, value))
        a = math.radians(-55 + v * 110)
        pygame.draw.line(s, (90, 90, 88), (c[0] + 1, c[1] + 1), (c[0] + 1 + (rad - 2) * math.sin(a),
                                                                c[1] + 1 - (rad - 2) * math.cos(a)), 1)
        pygame.draw.line(s, (20, 20, 20), c, (c[0] + (rad - 2) * math.sin(a), c[1] - (rad - 2) * math.cos(a)), 2)
        pygame.draw.circle(s, (20, 20, 20), c, 3)
        main, _ = self.tr(label)
        self.label((r.centerx, r.y + 2), main, 10, (40, 40, 40), "eng", "center")
        glare = pygame.Surface((r.w, r.h // 2), pygame.SRCALPHA)
        glare.fill((255, 255, 255, 26))
        s.blit(glare, r.topleft)
        if self.ussr:
            tip = (tip + " — " if tip else "") + label
        self.tip(r, tip)

    # ------------------------------------------------------------ data on glass
    def table(self, sid: str, r: Rect, cols: list[tuple[str, int]], rows: list[list[str]], selected: int = -1,
              colors: list | None = None, size: int = 12, row_h: int = 18) -> int | None:
        """Scrollable selectable table drawn on CRT glass. Returns clicked row index."""
        th = self.theme
        self.drawn["TABLE " + sid] = r
        self.glass(r)
        x = r.x + 6
        kind = th.data_font
        for name, w in cols:
            hname = lang.head(name, th.faction, self.lang_mode)
            self.label((x, r.y + 3), hname, size - 1, th.text_dim, kind)
            if hname != name:
                self.tip(Rect(x, r.y + 2, w, row_h), name)
            x += w
        pygame.draw.line(self.screen, _scale(th.text_dim, 0.6), (r.x + 4, r.y + row_h + 2), (r.right - 6, r.y + row_h + 2))
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
        self.crt_overlay(r, strength=0.8)
        return hit

    def log(self, sid: str, r: Rect, lines: list[tuple[str, tuple]], size: int = 12, kind: str = "ui",
            follow: bool = True) -> None:
        self.glass(r)
        inner = r.inflate(-12, -10)
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
        self.crt_overlay(r, strength=0.8)

    def readout(self, r: Rect, lines: list[tuple[str, tuple] | str], size: int = 12) -> None:
        """Small CRT window of status lines."""
        th = self.theme
        self.glass(r, bezel=False)
        y = r.y + 4
        self.screen.set_clip(r)
        for ln in lines:
            txt, col = (ln, th.text) if isinstance(ln, str) else ln
            self.label((r.x + 6, y), txt, size, col, th.data_font)
            y += size + 4
        self.screen.set_clip(None)
        self.crt_overlay(r, strength=0.6)

    # ------------------------------------------------------------ decoration
    def cable(self, pts: list[tuple[int, int]], color=(150, 52, 34), width: int = 7, coiled: bool = True) -> None:
        s = self.screen
        if len(pts) < 2:
            return
        pygame.draw.lines(s, (0, 0, 0), False, [(x + 1, y + 3) for x, y in pts], width + 2)
        pygame.draw.lines(s, _scale(color, 0.55), False, pts, width)
        pygame.draw.lines(s, color, False, [(x, y - 1) for x, y in pts], max(1, width - 3))
        if coiled:
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                L = math.hypot(x1 - x0, y1 - y0)
                if L < 1:
                    continue
                ux, uy = (x1 - x0) / L, (y1 - y0) / L
                px, py = -uy, ux
                for k in range(int(L // 4)):
                    cx, cy = x0 + ux * k * 4, y0 + uy * k * 4
                    pygame.draw.line(s, _scale(color, 0.4), (cx + px * width * 0.5, cy + py * width * 0.5),
                                     (cx - px * width * 0.5 + ux * 2, cy - py * width * 0.5 + uy * 2), 1)

    # ------------------------------------------------------------ overlays
    def highlighted(self) -> list[Rect]:
        """Rects of the controls the instructor is pointing at (``LABEL*`` matches a prefix)."""
        out = []
        for lab in self.highlight:
            if lab.endswith("*"):
                out.extend(r for k, r in self.drawn.items() if k.startswith(lab[:-1]))
            elif lab in self.drawn:
                out.append(self.drawn[lab])
        return out

    def _draw_highlights(self) -> None:
        pulse = 0.5 + 0.5 * math.sin(self.time * 5.0)
        col = _mix((255, 230, 120), (255, 120, 40), pulse)
        for r in self.highlighted():
            g = int(6 + pulse * 4)
            box = r.inflate(g, g)
            pygame.draw.rect(self.screen, (0, 0, 0), box.move(1, 2), 3, border_radius=6)
            pygame.draw.rect(self.screen, col, box, 3, border_radius=6)
            # corner ticks, like a grease-pencil circle on the console glass
            for cx, cy, dx, dy in ((box.x, box.y, 1, 1), (box.right, box.y, -1, 1),
                                   (box.x, box.bottom, 1, -1), (box.right, box.bottom, -1, -1)):
                pygame.draw.line(self.screen, col, (cx - dx * 6, cy), (cx - dx * 12, cy), 2)
                pygame.draw.line(self.screen, col, (cx, cy - dy * 6), (cx, cy - dy * 12), 2)

    def _draw_tooltip(self, text: str, pos) -> None:
        lines = TEXT.wrap(text, 360, 12, "ui")
        w = max(TEXT.width(ln, 12) for ln in lines) + 18
        h = len(lines) * 16 + 12
        sw, sh = self.screen.get_size()
        x = min(pos[0] + 16, sw - w - 4)
        y = min(pos[1] + 18, sh - h - 4)
        box = Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (0, 0, 0), box.move(3, 4), border_radius=2)
        pygame.draw.rect(self.screen, (236, 230, 204), box, border_radius=2)
        pygame.draw.rect(self.screen, (120, 108, 84), box, 1, border_radius=2)
        pygame.draw.line(self.screen, (200, 70, 50), (box.x + 6, box.y + 4), (box.x + 6, box.bottom - 5), 1)
        for i, ln in enumerate(lines):
            self.label((x + 12, y + 6 + i * 16), ln, 12, (34, 30, 24))
