"""Faction visual themes, fonts and cached text rendering.

Each faction is a physically different room:

* US — an Air Defense Command direction center: warm putty-and-olive consoles
  with brown trim, black phenolic nameplates, square lamp pushbuttons with
  milky lenses, cyan-white Charactron/P7 displays.
* USSR — a PVO command post: slate hammer-tone enamel, light-grey CRT housings,
  white keycaps with yellow and green backlit keys, Cyrillic engraving, amber
  long-persistence PPI and a back-lit plexiglass plotting board.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pygame

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
FONT_FILES = {
    "ui": "IBMPlexMono-Regular.ttf",          # CRT data text (Latin + Cyrillic)
    "ui_bold": "IBMPlexMono-SemiBold.ttf",
    "crt": "ShareTechMono-Regular.ttf",       # digits / LED (Latin only)
    "cyr": "PTM55FT.ttf",                     # Soviet typewriter / CRT text
    "tty": "CourierPrime-Regular.ttf",        # teleprinter (Latin only)
    "eng": "PT_Sans-Narrow-Web-Bold.ttf",     # panel engraving (Latin + Cyrillic)
    "eng_r": "PT_Sans-Narrow-Web-Regular.ttf",
    "title": "Oswald-Variable.ttf",           # condensed display (Latin + Cyrillic)
    "title_ru": "RussoOne-Regular.ttf",       # Soviet display face
    "typewriter": "SpecialElite-Regular.ttf",  # worn typewriter (Latin only)
}


@dataclass
class Theme:
    name: str
    faction: str
    # room & paint
    bg: tuple = (12, 12, 10)
    panel: tuple = (122, 117, 97)
    panel_hi: tuple = (158, 152, 129)
    panel_lo: tuple = (64, 60, 48)
    trim: tuple = (62, 50, 38)
    panel_style: str = "plastic"           # plastic (rounded, putty) | enamel (hammer-tone)
    plate: tuple = (18, 17, 16)            # nameplate body
    plate_text: tuple = (236, 232, 218)
    engraving: tuple = (30, 27, 22)        # silk-screen on the panel
    engraving_dim: tuple = (74, 68, 56)
    # pushbuttons
    key_style: str = "lens"                # lens (square lamp button) | keycap (skirted key)
    key_face: tuple = (150, 145, 126)
    key_hi: tuple = (184, 178, 158)
    key_lo: tuple = (88, 84, 70)
    key_legend: tuple = (34, 30, 24)
    key_legend_dim: tuple = (96, 90, 76)
    key_lit: tuple = (255, 196, 96)
    # CRT housings and glass
    bezel: tuple = (88, 74, 56)
    bezel_hi: tuple = (122, 106, 84)
    bezel_lo: tuple = (38, 31, 24)
    glass: tuple = (5, 15, 17)
    text: tuple = (140, 232, 238)
    text_dim: tuple = (62, 138, 148)
    phosphor: tuple = (150, 240, 245)
    phosphor_dim: tuple = (50, 120, 130)
    map_line: tuple = (46, 118, 128)
    map_coast: tuple = (92, 196, 206)
    grid: tuple = (22, 58, 64)
    scope_flash: tuple = (225, 238, 255)
    scope_glow: tuple = (170, 255, 110)
    scope_bg: tuple = (3, 9, 5)
    accent: tuple = (255, 196, 80)
    alert: tuple = (255, 84, 64)
    ok: tuple = (110, 235, 150)
    lamp_amber: tuple = (255, 178, 52)
    lamp_red: tuple = (255, 64, 48)
    lamp_green: tuple = (90, 240, 120)
    lamp_white: tuple = (246, 242, 226)
    lamp_blue: tuple = (110, 180, 255)
    id_colors: dict = field(default_factory=dict)
    map_style: str = "sage"
    label_font: str = "eng"
    units: str = "imperial"
    title: str = ""
    subtitle: str = ""
    data_font: str = "ui"                  # font for CRT/table text
    doc_font: str = "typewriter"           # orders and briefings
    title_font: str = "title"
    room_tint: tuple = (26, 18, 8)         # warm or cool light falloff in the room
    housing_ink: tuple = (226, 218, 196)   # lettering on the display housings
    housing_ink_dim: tuple = (168, 156, 132)


US = Theme(
    name="ADC / SAGE", faction="US",
    id_colors={"pending": (160, 240, 245), "friend": (110, 205, 215), "unknown": (200, 255, 170),
               "suspect": (255, 220, 120), "hostile": (255, 120, 90), "faker": (160, 200, 255)},
    title="AIR DEFENSE COMMAND — SAGE DIRECTION CENTER", subtitle="BANGOR AIR DEFENSE SECTOR · DC-05",
)

USSR = Theme(
    name="PVO", faction="USSR",
    bg=(8, 10, 12), panel=(48, 56, 64), panel_hi=(82, 92, 102), panel_lo=(22, 26, 30), trim=(132, 134, 128),
    panel_style="enamel", plate=(30, 34, 38), plate_text=(232, 234, 228),
    engraving=(226, 228, 222), engraving_dim=(146, 154, 160),
    key_style="keycap", key_face=(206, 208, 202), key_hi=(238, 240, 234), key_lo=(132, 134, 130),
    key_legend=(40, 44, 50), key_legend_dim=(120, 124, 128), key_lit=(250, 204, 74),
    bezel=(146, 146, 138), bezel_hi=(184, 184, 176), bezel_lo=(70, 70, 66),
    glass=(9, 10, 9), text=(255, 192, 112), text_dim=(170, 118, 66), phosphor=(255, 200, 140),
    phosphor_dim=(120, 88, 56), map_line=(120, 128, 110), map_coast=(160, 168, 140), grid=(52, 70, 74),
    scope_flash=(255, 238, 196), scope_glow=(255, 150, 40), scope_bg=(10, 6, 2),
    accent=(250, 204, 74), ok=(110, 220, 130),
    id_colors={"pending": (235, 235, 225), "friend": (255, 95, 80), "unknown": (240, 210, 100),
               "suspect": (100, 175, 255), "hostile": (120, 190, 255), "faker": (200, 200, 200)},
    map_style="board", label_font="eng", units="metric", data_font="cyr", doc_font="cyr", title_font="title_ru",
    title="PVO STRANY — ARMY COMMAND POST", subtitle="4th SEPARATE AIR DEFENSE ARMY",
    room_tint=(4, 10, 18), housing_ink=(36, 40, 46), housing_ink_dim=(70, 76, 82),
)


def theme_for(faction: str) -> Theme:
    return USSR if faction == "USSR" else US


class Text:
    """Font and rendered-text cache."""

    def __init__(self):
        self._fonts: dict[tuple[str, int], pygame.font.Font] = {}
        self._cache: dict[tuple, pygame.Surface] = {}
        self._wraps: dict[tuple, tuple] = {}

    def reset(self) -> None:
        self._fonts.clear()
        self._cache.clear()
        self._wraps.clear()

    def font(self, kind: str, size: int) -> pygame.font.Font:
        key = (kind, size)
        f = self._fonts.get(key)
        if f is None:
            path = FONT_DIR / FONT_FILES.get(kind, FONT_FILES["ui"])
            try:
                f = pygame.font.Font(str(path), size)
            except (FileNotFoundError, OSError):
                f = pygame.font.Font(None, size + 4)
            self._fonts[key] = f
        return f

    def render(self, text: str, size: int = 13, color=(255, 255, 255), kind: str = "ui") -> pygame.Surface:
        key = (text, size, color, kind)
        s = self._cache.get(key)
        if s is None:
            if len(self._cache) > 6000:
                self._cache.clear()
            if self._spaced(text, size, kind):
                s = self._render_spaced(text, size, color, kind)
            else:
                s = self.font(kind, size).render(text, True, color)
            self._cache[key] = s
        return s

    # The narrow engraving face has a 2 px word space at panel sizes, which runs words together
    # ("COMPANYLINES"); small panel lettering is set word by word with a wider space instead.
    @staticmethod
    def _spaced(text: str, size: int, kind: str) -> bool:
        return kind in ("eng", "eng_r") and size <= 16 and " " in text

    @staticmethod
    def _gap(size: int) -> int:
        return max(3, round(size * 0.3))

    def _render_spaced(self, text: str, size: int, color, kind: str) -> pygame.Surface:
        f = self.font(kind, size)
        words = text.split(" ")
        surfs = [f.render(w, True, color) if w else None for w in words]
        S = pygame.Surface((max(1, self.width(text, size, kind)), f.size(text)[1]), pygame.SRCALPHA)
        x = 0
        for i, w in enumerate(surfs):
            if i:
                x += self._gap(size)
            if w is not None:
                S.blit(w, (x, 0), special_flags=pygame.BLEND_RGBA_MAX)
                x += w.get_width()
        return S

    def width(self, text: str, size: int = 13, kind: str = "ui") -> int:
        f = self.font(kind, size)
        if self._spaced(text, size, kind):
            words = text.split(" ")
            return sum(f.size(w)[0] for w in words if w) + self._gap(size) * (len(words) - 1)
        return f.size(text)[0]

    def wrap(self, text: str, width: int, size: int = 13, kind: str = "ui") -> list[str]:
        key = (text, width, size, kind)
        hit = self._wraps.get(key)
        if hit is not None:
            return list(hit)
        out = self._wrap(text, width, size, kind)
        if len(self._wraps) > 3000:
            self._wraps.clear()
        self._wraps[key] = tuple(out)
        return out

    def _wrap(self, text: str, width: int, size: int = 13, kind: str = "ui") -> list[str]:
        out: list[str] = []
        for para in text.split("\n"):
            if not para.strip():
                out.append("")
                continue
            indent = len(para) - len(para.lstrip(" "))
            words = para.split()
            line = " " * indent
            for w in words:
                cand = (line + " " + w) if line.strip() else (" " * indent + w)
                if self.width(cand, size, kind) <= width:
                    line = cand
                else:
                    if line.strip():
                        out.append(line)
                    line = " " * indent + w
            out.append(line)
        return out


TEXT = Text()
