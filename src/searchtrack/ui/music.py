"""Synthesized adaptive music: no recordings, only numpy.

Each side has its own score, built from a few loops of the same length that start together and
keep running together, so the music can thicken or thin out without ever jumping:

    pad    -- the chords, always there (US: detuned analogue strings; PVO: a low choir)
    pulse  -- a bass ostinato and ticking hats: something is out there
    drive  -- drums and a running arpeggio: missiles in the air
    theme  -- the melody, on the title screen (US: electric piano; PVO: bells)

The command scene sets an intensity from what the picture shows (0 calm, 1 tension, 2 combat)
and the layers cross-fade toward it over a few seconds.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pygame

from .audio import RATE

BPM = 84.0
BEAT = 60.0 / BPM
BARS = 8
LOOP_S = BARS * 4 * BEAT
LAYERS = ("pad", "pulse", "drive", "theme")


def _f(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def _adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = max(1, int(a * RATE)), max(1, int(d * RATE)), max(1, int(r * RATE))
    e = np.full(n, s, np.float32)
    e[:a_n] = np.linspace(0.0, 1.0, a_n)[: n]
    if a_n < n:
        k = min(d_n, n - a_n)
        e[a_n:a_n + k] = np.linspace(1.0, s, d_n)[:k]
    if r_n < n:
        e[-r_n:] *= np.linspace(1.0, 0.0, r_n)
    return e


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float32) / RATE


def _place(buf: np.ndarray, start_s: float, x: np.ndarray, gain: float = 1.0) -> None:
    """Mix x into the loop at start_s, wrapping round the end so the loop joins seamlessly."""
    i = int(start_s * RATE) % len(buf)
    n = len(x)
    first = min(n, len(buf) - i)
    buf[i:i + first] += x[:first] * gain
    if first < n:
        rest = x[first:]
        buf[:len(rest)] += rest * gain


# ------------------------------------------------------------------ voices

def _strings(freq: float, dur: float, rng) -> np.ndarray:
    """Detuned analogue strings: three saws, harmonics rolled off for warmth."""
    n = int(dur * RATE)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for det in (-0.006, 0.0, 0.0065):
        f = freq * (1.0 + det)
        ph = rng.uniform(0, 2 * np.pi)
        for k in range(1, 9):
            if f * k > RATE * 0.45:
                break
            out += np.sin(2 * np.pi * f * k * t + ph * k) * (1.0 / k) * math.exp(-k / 6.0)
    return out * _adsr(n, 0.9, 0.6, 0.8, 1.2) * 0.18


def _choir(freq: float, dur: float, rng) -> np.ndarray:
    """A low 'ah': sines with a slow vibrato, the middle harmonics lifted like a vowel."""
    n = int(dur * RATE)
    t = _t(n)
    vib = 1.0 + 0.004 * np.sin(2 * np.pi * rng.uniform(4.5, 5.5) * t + rng.uniform(0, 6))
    out = np.zeros(n, np.float32)
    weights = (1.0, 0.75, 0.65, 0.5, 0.35, 0.25, 0.15, 0.1)
    for k, wgt in enumerate(weights, 1):
        out += np.sin(2 * np.pi * freq * k * np.cumsum(vib) / RATE) * wgt
    return out * _adsr(n, 1.2, 0.8, 0.85, 1.4) * 0.16


def _bass(freq: float, dur: float) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    x = np.zeros(n, np.float32)
    for k in range(1, 6):
        x += np.sin(2 * np.pi * freq * k * t) / k
    return x * np.exp(-t * 7.0) * _adsr(n, 0.004, 0.05, 1.0, 0.03) * 0.5


def _epiano(freq: float, dur: float) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    x = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 3.0) + \
        0.25 * np.sin(2 * np.pi * 3.01 * freq * t) * np.exp(-t * 5.0) + \
        0.12 * np.sin(2 * np.pi * 4.02 * freq * t) * np.exp(-t * 8.0)
    return x * np.exp(-t * 1.6) * _adsr(n, 0.004, 0.1, 1.0, 0.25) * 0.4


def _bell(freq: float, dur: float) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    x = np.zeros(n, np.float32)
    for ratio, amp, decay in ((0.56, 0.5, 0.9), (0.92, 0.6, 1.1), (1.0, 1.0, 1.4), (1.19, 0.35, 2.0),
                              (1.71, 0.3, 2.6), (2.0, 0.4, 2.4), (2.74, 0.2, 3.5), (3.0, 0.15, 4.0)):
        x += np.sin(2 * np.pi * freq * ratio * t) * amp * np.exp(-t * decay)
    return x * _adsr(n, 0.002, 0.05, 1.0, 0.3) * 0.22


def _arp(freq: float, dur: float) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    tri = 2.0 / np.pi * np.arcsin(np.sin(2 * np.pi * freq * t))
    return (tri * 0.7 + 0.3 * np.sin(2 * np.pi * 2 * freq * t)) * np.exp(-t * 9.0) * 0.22


def _kick(rng) -> np.ndarray:
    n = int(0.35 * RATE)
    t = _t(n)
    f = 45.0 + 85.0 * np.exp(-t * 28.0)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 9.0) * 0.9


def _snare(rng) -> np.ndarray:
    n = int(0.25 * RATE)
    t = _t(n)
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    noise = np.convolve(noise, np.ones(3) / 3, mode="same")
    return (noise * np.exp(-t * 18.0) * 0.5 + np.sin(2 * np.pi * 185 * t) * np.exp(-t * 25.0) * 0.4) * 0.8


def _hat(rng, open_: bool = False) -> np.ndarray:
    n = int((0.18 if open_ else 0.05) * RATE)
    t = _t(n)
    noise = np.diff(rng.uniform(-1, 1, n + 1)).astype(np.float32)
    return noise * np.exp(-t * (14.0 if open_ else 70.0)) * 0.6


def _timpani(freq: float, rng) -> np.ndarray:
    n = int(1.2 * RATE)
    t = _t(n)
    f = freq * (1.0 + 0.08 * np.exp(-t * 10.0))
    body = np.sin(2 * np.pi * np.cumsum(f) / RATE) + 0.4 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / RATE)
    hit = rng.uniform(-1, 1, n).astype(np.float32) * np.exp(-t * 40.0) * 0.3
    return (body * np.exp(-t * 3.0) + hit) * 0.55


# ------------------------------------------------------------------ the two scores

SCORES = {
    # chords as MIDI notes, two bars each; melody as (beat, midi, beats)
    "US": {
        "chords": [(50, 53, 57, 62), (46, 50, 53, 58), (48, 52, 55, 60), (45, 48, 52, 57)],   # Dm Bb C Am
        "melody": [(0, 74, 1.5), (1.5, 77, 0.5), (2, 76, 2), (4, 72, 1), (5, 74, 3), (8, 74, 1.5), (9.5, 70, 0.5),
                   (10, 72, 2), (12, 69, 4), (16, 74, 1.5), (17.5, 77, 0.5), (18, 79, 2), (20, 77, 1), (21, 76, 3),
                   (24, 76, 1.5), (25.5, 74, 0.5), (26, 72, 2), (28, 69, 4)],
        "pad": "strings", "lead": "epiano",
    },
    "USSR": {
        "chords": [(45, 52, 57, 60), (50, 57, 62, 65), (52, 56, 59, 64), (45, 52, 57, 60)],   # Am Dm E Am
        "melody": [(0, 69, 2), (2, 72, 1), (3, 71, 1), (4, 64, 4), (8, 74, 2), (10, 72, 1), (11, 71, 1),
                   (12, 69, 4), (16, 76, 2), (18, 74, 1), (19, 72, 1), (20, 71, 2), (22, 68, 2), (24, 69, 6)],
        "pad": "choir", "lead": "bell",
    },
}


def render(faction: str, seed: int = 11) -> dict[str, np.ndarray]:
    """All the layers of one side's score, each exactly LOOP_S long."""
    sc = SCORES.get(faction, SCORES["US"])
    rng = np.random.default_rng(seed)
    n = int(LOOP_S * RATE)
    L = {k: np.zeros(n, np.float32) for k in LAYERS}
    bar = 4 * BEAT
    for i in range(BARS // 2):
        chord = sc["chords"][i % len(sc["chords"])]
        t0 = i * 2 * bar
        for m in chord:
            v = _strings(_f(m), 2 * bar + 1.0, rng) if sc["pad"] == "strings" else _choir(_f(m - 12 if m > 55 else m),
                                                                                           2 * bar + 1.2, rng)
            _place(L["pad"], t0, v)
        root = chord[0] - 12
        for b in range(16):                                   # eighth-note bass ostinato over two bars
            note = root + (12 if b % 8 in (3, 6) else 0) if faction == "US" else root + (7 if b % 4 == 2 else 0)
            _place(L["pulse"], t0 + b * BEAT / 2, _bass(_f(note), BEAT / 2 + 0.05), 0.9 if b % 2 == 0 else 0.6)
        for b in range(32 if faction == "US" else 16):        # running arpeggio
            step = BEAT / 4 if faction == "US" else BEAT / 2
            tones = list(chord) + [chord[1] + 12, chord[2] + 12]
            m = tones[(b * 3 + b // 4) % len(tones)] + (12 if faction == "US" else 0)
            _place(L["drive"], t0 + b * step, _arp(_f(m), step * 1.6), 0.8)
    for beat in range(BARS * 4):                              # percussion
        t0 = beat * BEAT
        if faction == "US":
            if beat % 4 in (0, 2):
                _place(L["drive"], t0, _kick(rng))
            if beat % 4 in (1, 3):
                _place(L["drive"], t0, _snare(rng), 0.8)
            _place(L["pulse"], t0, _hat(rng), 0.7)
            _place(L["pulse"], t0 + BEAT / 2, _hat(rng), 0.45)
        else:
            if beat % 4 == 0:
                _place(L["drive"], t0, _timpani(_f(33), rng))
            if beat % 4 == 2:
                _place(L["drive"], t0, _timpani(_f(28), rng), 0.8)
            if beat % 2 == 1:
                _place(L["drive"], t0 + BEAT / 2, _snare(rng), 0.45)
            _place(L["pulse"], t0, _hat(rng, beat % 4 == 3), 0.5)
    lead = _epiano if sc["lead"] == "epiano" else _bell
    for b, m, length in sc["melody"]:
        _place(L["theme"], b * BEAT, lead(_f(m), length * BEAT + (0.6 if lead is _epiano else 2.5)))
    for k in L:                                               # each layer to a common loudness
        peak = float(np.max(np.abs(L[k]))) or 1.0
        L[k] = L[k] / peak * {"pad": 0.45, "pulse": 0.5, "drive": 0.6, "theme": 0.6}[k]
    return L


# ------------------------------------------------------------------ playback

MIXES = {
    "title": {"pad": 1.0, "pulse": 0.25, "drive": 0.0, "theme": 1.0},
    "brief": {"pad": 0.8, "pulse": 0.0, "drive": 0.0, "theme": 0.35},
    0: {"pad": 0.75, "pulse": 0.0, "drive": 0.0, "theme": 0.0},
    1: {"pad": 0.8, "pulse": 0.85, "drive": 0.0, "theme": 0.0},
    2: {"pad": 0.65, "pulse": 0.9, "drive": 1.0, "theme": 0.0},
    "end": {"pad": 0.7, "pulse": 0.0, "drive": 0.0, "theme": 0.6},
}


class Music:
    def __init__(self, audio, volume: float = 0.5):
        self.ok = bool(getattr(audio, "ok", False))
        self.volume = volume
        self.sounds: dict[str, dict[str, pygame.mixer.Sound]] = {}
        self.channels: list = []
        self.faction: Optional[str] = None
        self.mix: dict[str, float] = {k: 0.0 for k in LAYERS}
        self.level: dict[str, float] = {k: 0.0 for k in LAYERS}
        self.mode = None
        if self.ok:
            try:
                pygame.mixer.set_num_channels(16)
                pygame.mixer.set_reserved(len(LAYERS))
                self.channels = [pygame.mixer.Channel(i) for i in range(len(LAYERS))]
            except pygame.error:
                self.ok = False

    def _load(self, faction: str) -> dict[str, pygame.mixer.Sound]:
        if faction not in self.sounds:
            out = {}
            for k, arr in render(faction).items():
                a = np.clip(arr, -1.0, 1.0)
                st = (np.column_stack([a, a]) * 30000).astype(np.int16)
                out[k] = pygame.sndarray.make_sound(np.ascontiguousarray(st))
            self.sounds[faction] = out
        return self.sounds[faction]

    def play(self, faction: str, mode="title") -> None:
        """Start (or keep) a side's score and set the mix: 'title', 'brief', 'end' or an intensity 0-2."""
        if not self.ok:
            return
        self.mode = mode
        self.mix = dict(MIXES.get(mode, MIXES[0]))
        if faction == self.faction and any(ch.get_busy() for ch in self.channels):
            return
        try:
            snds = self._load(faction)
            for ch, k in zip(self.channels, LAYERS):
                ch.stop()
            for ch, k in zip(self.channels, LAYERS):
                ch.set_volume(0.0)
                ch.play(snds[k], loops=-1)
            self.level = {k: 0.0 for k in LAYERS}
            self.faction = faction
        except pygame.error:
            self.ok = False

    def set_intensity(self, level: int) -> None:
        if self.mode in (0, 1, 2) and level != self.mode:
            self.mode = level
            self.mix = dict(MIXES[level])

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, float(v)))

    def stop(self) -> None:
        for ch in self.channels:
            ch.fadeout(800)
        self.faction = None

    def update(self, dt: float) -> None:
        if not self.ok or self.faction is None:
            return
        rate = dt / 3.5                                      # a few seconds to cross-fade
        for ch, k in zip(self.channels, LAYERS):
            cur = self.level[k]
            tgt = self.mix.get(k, 0.0)
            cur += max(-rate, min(rate, tgt - cur))
            self.level[k] = cur
            ch.set_volume(cur * self.volume * 0.6)


def intensity(world) -> int:
    """How the picture feels: 2 when weapons are in the air or things are being shot down,
    1 when there is something hostile or unknown out there, else 0."""
    b = world.battle
    if b.active:
        recent = any(e[0] > world.t - 40.0 and e[1] in ("kill", "ship_hit", "vampire", "ground_hit")
                     for e in b.events[-30:])
        if recent or any(m.state == "flying" for m in world.missiles.values()) or \
                any(a.state == "airborne" and a.aim for a in world.aircraft.values()):
            return 2
    elif any(m.state == "flying" for m in world.missiles.values()):
        return 2
    if any(not t.lost and t.identity in ("hostile", "suspect", "unknown") for t in world.tracks.values()):
        return 1
    return 0
