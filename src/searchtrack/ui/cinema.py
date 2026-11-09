"""Cinematic pieces in black and white: the plotting-room backdrop of the
title screen, reconnaissance photographs, paper, and rubber stamps.

Everything is drawn procedurally from the game's own data (theater
coastlines, aircraft silhouettes), then aged with grain and vignetting."""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

from . import silhouette
from .theme import TEXT

R = pygame.Rect


def _gray(v: float) -> tuple[int, int, int]:
    v = int(max(0, min(255, v)))
    return (v, v, v)


def noise_surface(size, sigma: float, seed: int, mean: float = 0.0, scale: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    w, h = size
    n = rng.normal(mean, sigma, (max(1, w // scale), max(1, h // scale))).astype(np.float32)
    if scale > 1:
        s = pygame.surfarray.make_surface(np.repeat(np.clip(n + 128, 0, 255).astype(np.uint8)[:, :, None], 3, 2))
        s = pygame.transform.smoothscale(s, size)
        n = pygame.surfarray.array3d(s)[:, :, 0].astype(np.float32) - 128
    return n


# ====================================================================== paper & stamps
def paper(size, tint=(232, 226, 204), seed: int = 1, age: float = 1.0) -> pygame.Surface:
    w, h = size
    base = np.array(tint, np.float32)[None, None, :]
    fib = noise_surface(size, 3.0, seed)[:, :, None]
    blot = noise_surface(size, 9.0 * age, seed + 1, scale=24)[:, :, None]
    yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32))
    edge = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    burn = np.clip(1.0 - edge / 40.0, 0, 1)[:, :, None] * 26 * age
    img = base + fib + blot * 0.6 - burn
    return pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))


def stamp(text: str, color=(170, 30, 26), size: int = 30, angle: float = -8.0, sub: str = "",
          seed: int = 2) -> pygame.Surface:
    """Rubber stamp impression: double border, uneven ink."""
    f = TEXT.font("eng", size)
    tw, th = f.size(text)
    sw = 0
    if sub:
        sw = TEXT.font("eng_r", max(10, size // 2)).size(sub)[0]
    W = max(tw, sw) + size
    H = th + size // 2 + (size // 2 + 4 if sub else 0)
    S = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(S, (*color, 255), S.get_rect(), 4, border_radius=6)
    pygame.draw.rect(S, (*color, 255), S.get_rect().inflate(-10, -10), 2, border_radius=4)
    S.blit(f.render(text, True, color), ((W - tw) // 2, size // 4))
    if sub:
        sf = TEXT.font("eng_r", max(10, size // 2))
        S.blit(sf.render(sub, True, color), ((W - sw) // 2, size // 4 + th - 2))
    a = pygame.surfarray.pixels_alpha(S)
    rng = np.random.default_rng(seed)
    ink = np.clip(rng.normal(0.85, 0.22, a.shape), 0.0, 1.0)
    blotch = noise_surface((W, H), 0.25, seed + 3, scale=8)
    ink *= np.clip(0.8 + blotch, 0.2, 1.0)
    a[:] = (a * ink).astype(np.uint8)
    del a
    return pygame.transform.rotozoom(S, angle, 1.0)


# ====================================================================== photographs
def photo(type_ids: list[tuple[str, str]], size=(360, 250), seed: int = 4, night: bool = False,
          sea: bool = True) -> pygame.Surface:
    """A grainy black-and-white air-to-air photograph of the given aircraft types
    [(type_id, role), ...] — the first is the subject, the rest escorts."""
    w, h = size
    rng = random.Random(seed)
    yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32))
    horizon = h * rng.uniform(0.62, 0.78)
    sky_top, sky_bot = (70.0, 160.0) if not night else (12.0, 46.0)
    img = sky_top + (sky_bot - sky_top) * np.clip(yy / horizon, 0, 1)
    clouds = noise_surface(size, 26.0, seed, scale=18) + noise_surface(size, 12.0, seed + 5, scale=6)
    img = img + np.clip(clouds, 0, None) * (0.9 if not night else 0.25) * np.clip(1.2 - yy / horizon, 0, 1)
    if sea:
        below = yy > horizon
        sea_v = (96.0 if not night else 20.0) - (yy - horizon) * 0.08 + noise_surface(size, 7.0, seed + 9, scale=2)
        img = np.where(below, sea_v, img)
    img = np.clip(img, 0, 255)
    surf = pygame.surfarray.make_surface(np.repeat(img.astype(np.uint8)[:, :, None], 3, 2))
    # aircraft: dark silhouettes seen slightly from below/side (rotated top-view, squashed vertically)
    for i, (tid, role) in enumerate(type_ids[:3]):
        sz = int(w * (0.62 if i == 0 else 0.26))
        hdg = rng.uniform(-110, -70) if i == 0 else rng.uniform(-100, -80)
        sil = silhouette.render(tid, role, sz, (20, 20, 22) if not night else (6, 6, 6), heading=hdg)
        sil = pygame.transform.smoothscale(sil, (sil.get_width(), max(4, int(sil.get_height() * rng.uniform(0.35, 0.55)))))
        if i == 0:
            pos = (w * 0.5 - sil.get_width() / 2 + rng.uniform(-20, 20), horizon * 0.42 - sil.get_height() / 2)
        else:
            pos = (w * rng.uniform(0.62, 0.8) - sil.get_width() / 2, horizon * rng.uniform(0.15, 0.3))
        surf.blit(sil, pos)
    # lens softness, grain and vignette
    soft = pygame.transform.smoothscale(pygame.transform.smoothscale(surf, (w // 2, h // 2)), (w, h))
    arr = pygame.surfarray.array3d(soft).astype(np.float32)
    arr += noise_surface(size, 14.0, seed + 11)[:, :, None]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    arr *= np.clip(1.15 - d * 0.45, 0.35, 1.0)[:, :, None]
    out = pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8))
    return out


def framed_photo(img: pygame.Surface, caption: str = "", seed: int = 1, angle: float = 0.0) -> pygame.Surface:
    w, h = img.get_size()
    S = pygame.Surface((w + 24, h + (54 if caption else 24)), pygame.SRCALPHA)
    S.fill((236, 232, 220, 255))
    S.blit(img, (12, 12))
    if caption:
        kind = "cyr" if any("\u0400" <= ch <= "\u04ff" for ch in caption) else "typewriter"
        lines = TEXT.wrap(caption, w, 12, kind)
        for i, ln in enumerate(lines[:2]):
            S.blit(TEXT.render(ln, 12, (50, 46, 40), kind), (12, h + 18 + i * 15))
    if angle:
        S = pygame.transform.rotozoom(S, angle, 1.0)
    return S


# ====================================================================== the plotting room
class Backdrop:
    """Black-and-white operations room: a back-lit plotting board carrying the
    theater map, plotters on the catwalk, and the controllers' desk below."""

    def __init__(self, size, theater, faction: str, seed: int = 7, board=(0.10, 0.08, 0.80, 0.58)):
        self.size = size
        self.faction = faction
        self.rng = random.Random(seed)
        W, H = size
        self.board_r = R(int(W * board[0]), int(H * board[1]), int(W * board[2]), int(H * board[3]))
        self.back = self._board(theater)
        self.front = self._foreground()
        self.tracks = self._tracks(theater)
        self.haze = self._haze()
        self.t = 0.0
        self.lamps = []
        for _ in range(46):
            x = self.rng.uniform(30, W - 30)
            y = H * 0.705 - math.sin(x / W * math.pi) * 18 + self.rng.uniform(6, 22)
            self.lamps.append((x, y, self.rng.random() < 0.3, self.rng.uniform(0.5, 2.5)))

    def _fit(self, theater):
        ex = theater.cfg["projection"]["extent_km"]
        x0, x1, y0, y1 = ex
        br = self.board_r.inflate(-30, -30)
        k = min(br.w / (x1 - x0), br.h / (y1 - y0))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        def tp(x, y):
            return (br.centerx + (x - cx) * k, br.centery - (y - cy) * k)
        return tp

    def _board(self, theater) -> pygame.Surface:
        W, H = self.size
        br = self.board_r
        yy, xx = np.meshgrid(np.arange(H, dtype=np.float32), np.arange(W, dtype=np.float32))
        # dark room, faint light spill around the board
        d_board = np.sqrt(((xx - br.centerx) / (br.w * 0.7)) ** 2 + ((yy - br.centery) / (br.h * 0.8)) ** 2)
        room = 10 + 34 * np.clip(1.2 - d_board, 0, 1) ** 2
        inside = (xx >= br.x) & (xx < br.right) & (yy >= br.y) & (yy < br.bottom)
        db = np.sqrt(((xx - br.centerx) / (br.w / 2)) ** 2 + ((yy - br.centery) / (br.h / 2)) ** 2)
        glass = 196 - 70 * np.clip(db, 0, 1.3) ** 1.5 + noise_surface(self.size, 4.0, 3, scale=3)
        img = np.where(inside, glass, room)
        surf = pygame.surfarray.make_surface(np.repeat(np.clip(img, 0, 255).astype(np.uint8)[:, :, None], 3, 2))
        # grid printed on the glass
        for gx in range(br.x, br.right, 48):
            pygame.draw.line(surf, _gray(150), (gx, br.y), (gx, br.bottom), 1)
        for gy in range(br.y, br.bottom, 48):
            pygame.draw.line(surf, _gray(150), (br.x, gy), (br.right, gy), 1)
        # the theater map in dark ink
        tp = self._fit(theater)
        surf.set_clip(br)
        for layer, col, wd in (("rivers", 132, 1), ("states", 120, 1), ("lakes", 70, 1), ("borders", 54, 2),
                               ("coast", 34, 2)):
            for seg in theater.map.get(layer, []):
                if len(seg) < 4:
                    continue
                pts = [tp(seg[i], seg[i + 1]) for i in range(0, len(seg), 2)]
                pygame.draw.lines(surf, _gray(col), False, pts, wd)
        for c in theater.cfg.get("city", []):
            x, y = theater.xy(c["lat"], c["lon"])
            sx, sy = tp(x, y)
            pygame.draw.circle(surf, _gray(40), (sx, sy), 3)
            nm = c.get("name_ru") if (self.faction == "USSR" and c.get("name_ru")) else c["name"]
            surf.blit(TEXT.render(nm.upper(), 13, _gray(52), "eng"), (sx + 6, sy - 8))
        surf.set_clip(None)
        # heavy frame and mullions
        pygame.draw.rect(surf, _gray(8), br.inflate(26, 26), 14)
        for k in (1, 2, 3):
            mx = br.x + br.w * k // 4
            pygame.draw.line(surf, _gray(14), (mx, br.y), (mx, br.bottom), 6)
        # placard over the board
        title = "4-я ОТДЕЛЬНАЯ АРМИЯ ПВО" if self.faction == "USSR" else "NORTH AMERICAN AIR DEFENSE"
        t = TEXT.render(title, 22, _gray(170), "eng")
        surf.blit(t, (br.centerx - t.get_width() // 2, br.y - 44))
        return surf

    def _foreground(self) -> pygame.Surface:
        """Static foreground drawn at twice the resolution and scaled down (anti-aliased silhouettes)."""
        W, H = self.size
        k = 2
        S = pygame.Surface((W * k, H * k), pygame.SRCALPHA)
        br = self.board_r
        ink = (6, 6, 6, 255)
        # light spilling from the board onto the floor in front of it
        spill = pygame.Surface((W * k, H * k), pygame.SRCALPHA)
        top = (br.bottom + 30) * k
        for y in range(top, int(H * 0.86) * k, 2):
            f = 1.0 - (y - top) / max(1, (H * 0.86 * k - top))
            a = int(115 * f ** 1.4)
            pygame.draw.line(spill, (150, 150, 150, a), ((br.x - 60) * k, y), ((br.right + 60) * k, y), 2)
        S.blit(spill, (0, 0))
        # catwalk with railing in front of the board
        cw = (br.bottom + 26) * k
        pygame.draw.rect(S, ink, ((br.x - 40) * k, cw, (br.w + 80) * k, 12 * k))
        pygame.draw.line(S, ink, ((br.x - 40) * k, cw - 36 * k), ((br.right + 40) * k, cw - 36 * k), 3 * k)
        for x in range(br.x - 40, br.right + 41, 56):
            pygame.draw.line(S, ink, (x * k, cw - 36 * k), (x * k, cw), 3 * k)
        # plotters on the catwalk, writing on the glass from behind
        for i, (fx, pose) in enumerate(((0.16, "write"), (0.38, "clip"), (0.63, "write"), (0.84, "phone"))):
            self._person(S, (br.x + br.w * fx) * k, cw, 1.05 * k, pose, flip=i % 2 == 1)
        # the controllers' console row: a dark slab with scope glows and lamps
        y_top = int(H * 0.705)
        pts = []
        for j in range(41):
            f = j / 40
            pts.append(((-20 + (W + 40) * f) * k, (y_top - math.sin(f * math.pi) * 18) * k))
        pygame.draw.polygon(S, (10, 10, 10, 255), pts + [((W + 20) * k, H * k + 10), (-20 * k, H * k + 10)])
        pygame.draw.lines(S, (70, 70, 70, 255), False, pts, 2 * k)
        for j in range(1, 9):              # glow of the scopes facing the controllers
            x = W * j / 9
            g = pygame.Surface((160 * k, 70 * k), pygame.SRCALPHA)
            for rr in range(10, 0, -1):
                pygame.draw.ellipse(g, (180, 180, 180, 4 + (10 - rr) * 2),
                                    g.get_rect().inflate(-rr * 14 * k // 2, -rr * 6 * k // 2))
            S.blit(g, ((x - 80) * k, (y_top - 48 - math.sin(x / W * math.pi) * 18) * k))
        # controllers seated with their backs to us, rim-lit by the board
        for fx, sc, yy in ((0.47, 1.35, 0.80), (0.64, 1.5, 0.82), (0.84, 1.42, 0.81)):
            x = W * fx
            self._seated(S, x * k, (H * yy) * k, sc * k)
        return pygame.transform.smoothscale(S, (W, H))

    @staticmethod
    def _person(S, x, base, sc, pose="write", flip=False):
        ink = (6, 6, 6, 255)
        s = -1 if flip else 1
        hip = base - 56 * sc
        sh = base - 104 * sc
        # legs (trousers)
        for d in (-1, 1):
            pygame.draw.polygon(S, ink, [(x + d * 2 * sc, hip), (x + d * 12 * sc, hip), (x + d * 10 * sc, base - 4 * sc),
                                         (x + d * 3 * sc, base - 4 * sc)])
            pygame.draw.ellipse(S, ink, (x + d * 6 * sc - 7 * sc, base - 7 * sc, 15 * sc, 7 * sc))
        # torso
        pygame.draw.polygon(S, ink, [(x - 19 * sc, sh + 3 * sc), (x + 19 * sc, sh + 3 * sc), (x + 15 * sc, hip + 4 * sc),
                                     (x - 15 * sc, hip + 4 * sc)])
        pygame.draw.circle(S, ink, (x - 15 * sc, sh + 7 * sc), 6 * sc)
        pygame.draw.circle(S, ink, (x + 15 * sc, sh + 7 * sc), 6 * sc)
        # neck and head
        pygame.draw.rect(S, ink, (x - 4 * sc, sh - 9 * sc, 8 * sc, 12 * sc))
        pygame.draw.ellipse(S, ink, (x - 9 * sc, sh - 30 * sc, 18 * sc, 23 * sc))
        # arms
        def arm(side, elbow, hand, w=6):
            a = (x + side * 17 * sc, sh + 6 * sc)
            pygame.draw.line(S, ink, a, elbow, int(w * sc))
            pygame.draw.line(S, ink, elbow, hand, int((w - 1) * sc))
            pygame.draw.circle(S, ink, hand, 3.5 * sc)
        if pose == "write":
            arm(s, (x + s * 30 * sc, sh - 10 * sc), (x + s * 34 * sc, sh - 44 * sc))
            arm(-s, (x - s * 22 * sc, sh + 30 * sc), (x - s * 20 * sc, hip - 2 * sc))
        elif pose == "clip":
            arm(s, (x + s * 24 * sc, sh + 30 * sc), (x + s * 8 * sc, sh + 40 * sc))
            arm(-s, (x - s * 24 * sc, sh + 30 * sc), (x - s * 6 * sc, sh + 42 * sc))
            pygame.draw.rect(S, ink, (x - 14 * sc, sh + 30 * sc, 26 * sc, 20 * sc))
        else:  # telephone headset, one hand at the earpiece
            arm(s, (x + s * 26 * sc, sh + 18 * sc), (x + s * 10 * sc, sh - 20 * sc))
            arm(-s, (x - s * 22 * sc, sh + 30 * sc), (x - s * 20 * sc, hip - 2 * sc))
            pygame.draw.line(S, ink, (x + s * 9 * sc, sh - 18 * sc), (x + s * 30 * sc, hip + 20 * sc), max(1, int(sc)))
        pygame.draw.arc(S, ink, (x - 11 * sc, sh - 33 * sc, 22 * sc, 18 * sc), 0.2, 2.9, max(1, int(2 * sc)))

    @staticmethod
    def _seated(S, x, y, sc):
        ink = (5, 5, 5, 255)
        rim = (120, 120, 116, 255)
        sh_y = y - 30 * sc
        # shoulders and back
        pygame.draw.ellipse(S, ink, (x - 50 * sc, sh_y - 14 * sc, 100 * sc, 70 * sc))
        pygame.draw.rect(S, ink, (x - 46 * sc, sh_y + 10 * sc, 92 * sc, 90 * sc))
        # head and neck with headset
        pygame.draw.rect(S, ink, (x - 9 * sc, sh_y - 28 * sc, 18 * sc, 24 * sc))
        head = pygame.Rect(0, 0, 38 * sc, 46 * sc)
        head.center = (x, sh_y - 44 * sc)
        pygame.draw.ellipse(S, ink, head)
        # rim light from the board above
        pygame.draw.arc(S, rim, head.inflate(2, 2), 0.6, 2.6, max(1, int(1.5 * sc)))
        pygame.draw.arc(S, rim, (x - 50 * sc, sh_y - 14 * sc, 100 * sc, 70 * sc), 0.5, 2.65, max(1, int(1.2 * sc)))
        pygame.draw.arc(S, (60, 60, 58, 255), head.inflate(10 * sc, -8 * sc).move(0, -6 * sc), 0.1, 3.04,
                        max(1, int(2 * sc)))
        pygame.draw.ellipse(S, ink, (head.x - 6 * sc, head.centery - 6 * sc, 9 * sc, 14 * sc))
        pygame.draw.ellipse(S, ink, (head.right - 3 * sc, head.centery - 6 * sc, 9 * sc, 14 * sc))

    def _tracks(self, theater):
        rng = self.rng
        br = self.board_r
        out = []
        for i in range(9):
            x0, y0 = rng.uniform(br.x + 40, br.right - 40), rng.uniform(br.y + 30, br.bottom - 30)
            ang = rng.uniform(0, 2 * math.pi)
            spd = rng.uniform(4, 11)
            out.append([x0, y0, ang, spd, rng.random() < 0.35, rng.uniform(0, 100)])
        return out

    def _haze(self) -> pygame.Surface:
        W, H = self.size
        n = noise_surface((W // 4, H // 4), 1.0, 21, scale=12)
        a = np.clip((n + 0.3) * 26, 0, 40).astype(np.uint8)
        s = pygame.Surface((W // 4, H // 4), pygame.SRCALPHA)
        s.fill((210, 210, 210, 255))
        pygame.surfarray.pixels_alpha(s)[:] = a
        return pygame.transform.smoothscale(s, (W, H))

    def draw(self, screen: pygame.Surface, dt: float) -> None:
        self.t += dt
        screen.blit(self.back, (0, 0))
        br = self.board_r
        screen.set_clip(br)
        for tr in self.tracks:
            x0, y0, ang, spd, hostile, ph = tr
            tt = self.t + ph
            # grease-pencil history: a dotted trail and the current symbol
            for k in range(7):
                px = x0 + math.cos(ang) * spd * (tt - k * 3.0) % br.w
                py = y0 + math.sin(ang) * spd * (tt - k * 3.0) * 0.6
                px = br.x + (px - br.x) % br.w
                py = br.y + (py - br.y) % br.h
                pygame.draw.circle(screen, _gray(30 + k * 12), (int(px), int(py)), 2 if k else 3)
                if k == 0:
                    if hostile:
                        pygame.draw.polygon(screen, _gray(15), [(px, py - 9), (px + 8, py + 6), (px - 8, py + 6)], 2)
                    else:
                        pygame.draw.circle(screen, _gray(15), (int(px), int(py)), 8, 2)
                    hx, hy = px + math.cos(ang) * 22, py + math.sin(ang) * 13
                    pygame.draw.line(screen, _gray(15), (px, py), (hx, hy), 2)
        screen.set_clip(None)
        screen.blit(self.front, (0, 0))
        # console lamps blinking on the desk
        for x, y, blink, rate in self.lamps:
            on = (not blink) or math.sin(self.t * rate * 3) > 0
            if on:
                pygame.draw.circle(screen, _gray(150), (int(x), int(y)), 1)
        drift = int((self.t * 6) % self.size[0])
        screen.blit(self.haze, (drift - self.size[0], 0))
        screen.blit(self.haze, (drift, 0))


def situation_map(world, size=(520, 360), seed: int = 5) -> pygame.Surface:
    """Printed situation map: the theater in ink with own radars, fields, missile sites and zones."""
    w, h = size
    surf = paper(size, (226, 222, 202) if world.faction == "US" else (222, 220, 200), seed=seed, age=0.6)
    th = world.theater
    ex = th.cfg["projection"]["extent_km"]
    x0, x1, y0, y1 = ex
    k = min((w - 30) / (x1 - x0), (h - 30) / (y1 - y0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def tp(x, y):
        return (w / 2 + (x - cx) * k, h / 2 - (y - cy) * k)
    ink = (52, 46, 38)
    for gx in range(int(x0 // 100) * 100, int(x1) + 1, 100):
        pygame.draw.line(surf, (200, 194, 172), tp(gx, y0), tp(gx, y1), 1)
    for gy in range(int(y0 // 100) * 100, int(y1) + 1, 100):
        pygame.draw.line(surf, (200, 194, 172), tp(x0, gy), tp(x1, gy), 1)
    for layer, col, wd in (("rivers", (140, 160, 176), 1), ("lakes", (120, 140, 160), 1), ("states", (170, 160, 140), 1),
                           ("borders", (120, 100, 90), 2), ("coast", ink, 1)):
        for seg in th.map.get(layer, []):
            if len(seg) >= 4:
                pygame.draw.lines(surf, col, False, [tp(seg[i], seg[i + 1]) for i in range(0, len(seg), 2)], wd)
    ru = world.faction == "USSR"
    for z in world.zones.values():
        col = (150, 60, 50)
        if z["shape"] == "circle":
            pygame.draw.circle(surf, col, tp(z["x"], z["y"]), max(2, int(z["r"] * k)), 1)
        else:
            pts = [tp(*p) for p in z["poly"]]
            if len(pts) > 1:
                pygame.draw.lines(surf, col, True, pts, 1)
    for c in world.cities:
        sx, sy = tp(c["x"], c["y"])
        pygame.draw.circle(surf, ink, (sx, sy), 2)
        if c["size"] >= 2:
            nm = c.get("name_ru") if (ru and c.get("name_ru")) else c["name"]
            surf.blit(TEXT.render(nm, 10, ink, "eng_r"), (sx + 4, sy - 6))
    blue = (30, 60, 140) if not ru else (170, 30, 26)
    for s in world.radars.values():
        sx, sy = tp(s.x, s.y)
        pygame.draw.polygon(surf, blue, [(sx, sy - 5), (sx + 4, sy + 3), (sx - 4, sy + 3)], 0 if s.gci else 1)
    for b in world.airbases.values():
        if b.side != "blue" or b.kind != "military":
            continue
        sx, sy = tp(b.x, b.y)
        pygame.draw.line(surf, blue, (sx - 6, sy + 3), (sx + 6, sy - 3), 3)
    for m in world.sams.values():
        sx, sy = tp(m.x, m.y)
        st = world.catalog.sams[m.type_id]
        pygame.draw.circle(surf, blue, (sx, sy), 3)
        pygame.draw.circle(surf, (*blue,), (sx, sy), max(3, int(st.range_max_km * k)), 1)
    pygame.draw.rect(surf, ink, surf.get_rect(), 1)
    return surf
