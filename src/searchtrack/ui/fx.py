"""Cheap CPU 'CRT' effects: scanlines, vignette, glow stamps."""
from __future__ import annotations

import math

import pygame


def scanlines(size: tuple[int, int], alpha: int = 34, gap: int = 3) -> pygame.Surface:
    s = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(0, size[1], gap):
        pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (size[0], y))
    return s


def vignette(size: tuple[int, int], strength: int = 150) -> pygame.Surface:
    import numpy as np
    w, h = size
    y, x = np.ogrid[:h, :w]
    nx = (x - w / 2) / (w / 2)
    ny = (y - h / 2) / (h / 2)
    d = np.sqrt(nx * nx * 0.85 + ny * ny * 0.95)
    a = (np.clip((d - 0.55) / 0.6, 0, 1) ** 1.8 * strength).astype(np.uint8)
    s = pygame.Surface(size, pygame.SRCALPHA)
    s.fill((0, 0, 0, 255))
    pygame.surfarray.pixels_alpha(s)[:] = a.T
    return s


def glow_stamp(radius: int, color: tuple[int, int, int], core: float = 0.35) -> pygame.Surface:
    """Soft additive dot: bright core with gaussian-like halo."""
    d = radius * 2 + 1
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    for i in range(radius, 0, -1):
        f = i / radius
        a = int(255 * math.exp(-3.2 * f * f))
        c = tuple(min(255, int(v * (0.25 + 0.75 * (1 - f)))) for v in color)
        pygame.draw.circle(s, (*c, a), (radius, radius), i)
    pygame.draw.circle(s, (*color, 255), (radius, radius), max(1, int(radius * core)))
    return s
