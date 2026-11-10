"""Draw the application icon: a radar scope with a sweep, its afterglow and three paints.

    python tools/make_icon.py        # writes assets/icons/searchtrack.png (256 px) and searchtrack-64.png

The icon is generated, like every other image in the game; the PNGs are committed so
that packaging does not need to run this.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "icons"
N = 1024                      # drawn large, then scaled down for clean edges


def phosphor(n: int) -> np.ndarray:
    """Intensity of the scope face, 0..1, for an n×n canvas."""
    c = (n - 1) / 2.0
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    dx, dy = x - c, c - y
    r = np.hypot(dx, dy) / (n * 0.43)                     # 1.0 at the edge of the face
    theta = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
    sweep = 58.0
    behind = (sweep - theta) % 360.0                       # degrees since the beam passed
    glow = np.exp(-behind / 55.0) * 0.55
    glow += np.exp(-behind / 4.0) * 0.6                    # the bright leading edge
    rings = sum(np.exp(-((r - k) / 0.006) ** 2) * 0.22 for k in (0.25, 0.5, 0.75))
    cross = (np.exp(-(dx / 3.0) ** 2) + np.exp(-(dy / 3.0) ** 2)) * 0.10
    rng = np.random.default_rng(7)
    speckle = (rng.random((n, n)) ** 30) * 0.5 * np.exp(-behind / 120.0)
    face = glow + rings + cross + speckle
    for br, bt, size, k in ((0.58, 30.0, 0.022, 1.0), (0.80, 352.0, 0.020, 0.55), (0.36, 230.0, 0.024, 0.35)):
        bx = c + br * n * 0.43 * math.sin(math.radians(bt))
        by = c - br * n * 0.43 * math.cos(math.radians(bt))
        d = np.hypot(x - bx, y - by) / (n * size)
        face += np.exp(-d ** 2) * 1.4 * k
    face *= r <= 1.0
    return np.clip(face, 0.0, 1.6)


def draw(n: int = N) -> pygame.Surface:
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = n // 2
    # bezel: a turned steel ring
    for i in range(48):
        f = i / 47.0
        col = [int(a + (b - a) * f) for a, b in zip((118, 124, 120), (34, 38, 36))]
        pygame.draw.circle(s, (*col, 255), (c, c), int(n * 0.49) - i)
    pygame.draw.circle(s, (20, 22, 21, 255), (c, c), int(n * 0.445))
    for a in (45, 135, 225, 315):                          # four screws in the bezel
        sx = c + int(n * 0.468 * math.sin(math.radians(a)))
        sy = c - int(n * 0.468 * math.cos(math.radians(a)))
        pygame.draw.circle(s, (150, 154, 150, 255), (sx, sy), n // 70)
        pygame.draw.line(s, (60, 62, 60, 255), (sx - n // 90, sy), (sx + n // 90, sy), max(1, n // 300))
    # the tube face
    face = phosphor(n)
    dark = np.array((5, 16, 13), np.float32)
    lit = np.array((120, 255, 205), np.float32)
    hot = np.array((235, 255, 245), np.float32)
    f = face[..., None]
    rgb = dark + (lit - dark) * np.clip(f, 0, 1) + (hot - lit) * np.clip(f - 1.0, 0, 0.6) / 0.6
    img = pygame.surfarray.make_surface(np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 0, 2)))
    # bloom: blur by scaling down and back up, then add
    small = pygame.transform.smoothscale(img, (n // 16, n // 16))
    bloom = pygame.transform.smoothscale(small, (n, n))
    img.blit(bloom, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    mask = pygame.Surface((n, n), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), int(n * 0.43))
    tube = pygame.Surface((n, n), pygame.SRCALPHA)
    tube.blit(img, (0, 0))                                 # opaque copy, then cut to the circle
    tube.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(tube, (0, 0))
    # glass reflection
    hl = pygame.Surface((n, n), pygame.SRCALPHA)
    pygame.draw.ellipse(hl, (255, 255, 255, 26), pygame.Rect(int(n * 0.2), int(n * 0.14), int(n * 0.42), int(n * 0.22)))
    s.blit(hl, (0, 0))
    pygame.draw.circle(s, (0, 0, 0, 160), (c, c), int(n * 0.43), max(2, n // 128))
    return s


def main() -> None:
    pygame.display.init()
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw()
    for size, name in ((256, "searchtrack.png"), (64, "searchtrack-64.png")):
        pygame.image.save(pygame.transform.smoothscale(big, (size, size)), str(OUT / name))
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
