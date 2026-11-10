"""Synthesized sound effects (no audio assets): relay clicks, alert tones,
scramble klaxon, teletype chatter, radio squelch, telephone bell/buzzer."""
from __future__ import annotations

import numpy as np
import pygame

RATE = 22050


def _env(n: int, attack: float = 0.005, release: float = 0.05) -> np.ndarray:
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.linspace(1, 0, r)
    return e


def _tone(freq: float, dur: float, kind: str = "sine") -> np.ndarray:
    t = np.arange(int(dur * RATE)) / RATE
    if kind == "square":
        return np.sign(np.sin(2 * np.pi * freq * t)) * 0.6
    if kind == "saw":
        return 2 * ((t * freq) % 1.0) - 1
    return np.sin(2 * np.pi * freq * t)


def _noise(dur: float, rng) -> np.ndarray:
    return rng.uniform(-1, 1, int(dur * RATE))


def _lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def synth_all() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(5)
    s = {}
    click = _noise(0.012, rng) * np.exp(-np.arange(int(0.012 * RATE)) / 40.0)
    thump = _tone(140, 0.03) * np.exp(-np.arange(int(0.03 * RATE)) / 120.0)
    s["click"] = np.concatenate([click * 0.5, thump[: len(thump)] * 0.35])
    beep = np.concatenate([_tone(880, 0.12) * _env(int(0.12 * RATE)), np.zeros(int(0.05 * RATE)),
                           _tone(660, 0.16) * _env(int(0.16 * RATE))])
    s["alert"] = np.tile(beep, 2) * 0.35
    sweep_t = np.arange(int(1.2 * RATE)) / RATE
    f = 380 + 260 * ((sweep_t * 1.6) % 1.0)
    s["klaxon"] = np.sign(np.sin(2 * np.pi * np.cumsum(f) / RATE)) * 0.18 * _env(len(sweep_t), 0.02, 0.1)
    tty = np.zeros(int(0.9 * RATE))
    for i in range(36):
        p = int(rng.uniform(0, 0.88) * RATE)
        n = int(0.006 * RATE)
        tty[p:p + n] += rng.uniform(-1, 1, n) * np.exp(-np.arange(n) / 25.0) * 0.6
    s["tty"] = _lowpass(tty, 3) * 0.6
    st = _lowpass(_noise(0.32, rng), 4) * _env(int(0.32 * RATE), 0.01, 0.12)
    s["static"] = st * 0.22
    s["beep"] = _tone(1000, 0.07) * _env(int(0.07 * RATE)) * 0.25
    bell_t = np.arange(int(0.9 * RATE)) / RATE
    bell = (np.sin(2 * np.pi * 980 * bell_t) + 0.5 * np.sin(2 * np.pi * 2450 * bell_t)) * np.exp(-bell_t * 5)
    trem = 0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 22 * bell_t))
    s["bell"] = bell * trem * 0.25
    s["buzz"] = _tone(120, 0.45, "square") * _env(int(0.45 * RATE), 0.01, 0.05) * 0.15
    key = _noise(0.05, rng) * np.exp(-np.arange(int(0.05 * RATE)) / 300.0)
    s["key"] = np.concatenate([key * 0.6, np.zeros(200), _tone(90, 0.06) * 0.3])
    w = _lowpass(_noise(1.4, rng), 12) * np.linspace(1, 0, int(1.4 * RATE)) ** 1.5
    s["launch"] = w * 0.5
    return s


class Audio:
    def __init__(self, enabled: bool = True):
        self.ok = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.volume = 0.7
        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            for name, arr in synth_all().items():
                a = np.clip(arr, -1, 1)
                st = (np.column_stack([a, a]) * 32000).astype(np.int16)
                self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(st))
            self.ok = True
        except (pygame.error, ValueError, OSError):
            self.ok = False

    def play(self, name: str, vol: float = 1.0) -> None:
        if not self.ok or self.volume <= 0:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            snd.set_volume(self.volume * vol)
            snd.play()
