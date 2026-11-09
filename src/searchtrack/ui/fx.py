"""Cheap CPU image effects: CRT scanlines, vignette, phosphor bloom, room
lighting, and a black-and-white film look (grain, dust, scratches, flicker,
gate weave) for the cinematic screens."""
from __future__ import annotations

import math
import random

import numpy as np
import pygame


def scanlines(size: tuple[int, int], alpha: int = 34, gap: int = 3) -> pygame.Surface:
    s = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(0, size[1], gap):
        pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (size[0], y))
    return s


def vignette(size: tuple[int, int], strength: int = 150, color=(0, 0, 0)) -> pygame.Surface:
    w, h = size
    y, x = np.ogrid[:h, :w]
    nx = (x - w / 2) / (w / 2)
    ny = (y - h / 2) / (h / 2)
    d = np.sqrt(nx * nx * 0.85 + ny * ny * 0.95)
    a = (np.clip((d - 0.55) / 0.6, 0, 1) ** 1.8 * strength).astype(np.uint8)
    s = pygame.Surface(size, pygame.SRCALPHA)
    s.fill((*color, 255))
    pygame.surfarray.pixels_alpha(s)[:] = a.T
    return s


def room_light(size: tuple[int, int], tint=(26, 18, 8), strength: float = 1.0) -> pygame.Surface:
    """Light falloff of a dim operations room: edges sink into tinted darkness,
    the top is lit by the ceiling lamps, the bottom by the consoles' glow."""
    w, h = size
    y, x = np.ogrid[:h, :w]
    nx = (x - w / 2) / (w / 2)
    ny = (y - h * 0.42) / (h / 2)
    d = np.sqrt(nx * nx * 0.7 + ny * ny * 0.9)
    a = np.clip((d - 0.7) / 0.7, 0, 1) ** 1.5 * 170 * strength
    s = pygame.Surface(size, pygame.SRCALPHA)
    s.fill((*tint, 255))
    pygame.surfarray.pixels_alpha(s)[:] = np.clip(a, 0, 255).astype(np.uint8).T
    return s


def bloom(screen: pygame.Surface, rect: pygame.Rect, gain: int = 120, down: int = 4) -> None:
    """Phosphor halation: blur a downscaled copy of the region and add it back."""
    rect = rect.clip(screen.get_rect())
    if rect.w < 16 or rect.h < 16:
        return
    sub = screen.subsurface(rect)
    w, h = max(2, rect.w // down), max(2, rect.h // down)
    small = pygame.transform.smoothscale(sub, (w, h))
    small = pygame.transform.smoothscale(small, (max(2, w // 2), max(2, h // 2)))
    big = pygame.transform.smoothscale(small, rect.size)
    big.fill((gain, gain, gain), special_flags=pygame.BLEND_MULT)
    screen.blit(big, rect.topleft, special_flags=pygame.BLEND_ADD)


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


class Film:
    """Black-and-white newsreel look applied on top of a finished frame."""

    def __init__(self, size: tuple[int, int], seed: int = 3, grain: int = 26):
        self.size = size
        self.rng = random.Random(seed)
        w, h = size
        nrng = np.random.default_rng(seed)
        self.frames = []
        gw, gh = w // 2, h // 2
        for _ in range(6):
            n = nrng.normal(0, 1, (gw, gh))
            light = pygame.Surface((gw, gh), pygame.SRCALPHA)
            light.fill((255, 255, 255, 255))
            pygame.surfarray.pixels_alpha(light)[:] = np.clip(n * grain, 0, 255).astype(np.uint8)
            dark = pygame.Surface((gw, gh), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 255))
            pygame.surfarray.pixels_alpha(dark)[:] = np.clip(-n * grain * 1.2, 0, 255).astype(np.uint8)
            light = pygame.transform.scale(light, size)
            dark = pygame.transform.scale(dark, size)
            light.blit(dark, (0, 0))
            self.frames.append(light)
        self.vig = vignette(size, 210)
        self.i = 0
        self.t = 0.0
        self.scratches: list[list[float]] = []
        self.dust: list[list[float]] = []

    def apply(self, screen: pygame.Surface, dt: float, flicker: float = 0.06) -> None:
        self.t += dt
        self.i = (self.i + 1) % len(self.frames)
        w, h = self.size
        # flicker of the projector lamp
        f = 1.0 - flicker * (0.5 + 0.5 * math.sin(self.t * 37.0) * math.sin(self.t * 11.3))
        f -= self.rng.random() * flicker * 0.5
        k = int(255 * max(0.0, min(1.0, f)))
        screen.fill((k, k, k), special_flags=pygame.BLEND_MULT)
        screen.blit(self.frames[self.i], (0, 0))
        # dust and hairs
        if self.rng.random() < 0.35:
            self.dust.append([self.rng.uniform(0, w), self.rng.uniform(0, h), self.rng.uniform(1, 3), 2.0,
                              self.rng.random() < 0.5])
        self.dust = [d for d in self.dust if d[3] > 0]
        for d in self.dust:
            d[3] -= 1
            col = (240, 240, 240) if d[4] else (10, 10, 10)
            pygame.draw.circle(screen, col, (int(d[0]), int(d[1])), int(d[2]))
        # vertical scratches
        if self.rng.random() < 0.02:
            self.scratches.append([self.rng.uniform(0, w), self.rng.uniform(0.3, 1.6)])
        for s in self.scratches:
            s[1] -= dt
            s[0] += self.rng.uniform(-2, 2)
            pygame.draw.line(screen, (200, 200, 200), (s[0], 0), (s[0] + self.rng.uniform(-3, 3), h), 1)
        self.scratches = [s for s in self.scratches if s[1] > 0]
        screen.blit(self.vig, (0, 0))

    def weave(self) -> tuple[int, int]:
        """Small frame jitter of the film gate."""
        return (int(round(math.sin(self.t * 2.1) * 1.2 + self.rng.uniform(-0.6, 0.6))),
                int(round(math.sin(self.t * 1.3) * 1.5 + self.rng.uniform(-0.6, 0.6))))
