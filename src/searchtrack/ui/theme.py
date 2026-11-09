"""Faction visual themes, fonts and cached text rendering."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pygame

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
FONT_FILES = {
    "ui": "IBMPlexMono-Regular.ttf",
    "ui_bold": "IBMPlexMono-SemiBold.ttf",
    "crt": "ShareTechMono-Regular.ttf",
    "cyr": "PTM55FT.ttf",
    "tty": "CourierPrime-Regular.ttf",
}


@dataclass
class Theme:
    name: str
    faction: str
    bg: tuple = (16, 18, 20)
    panel: tuple = (84, 92, 100)
    panel_hi: tuple = (122, 130, 138)
    panel_lo: tuple = (40, 44, 50)
    engraving: tuple = (226, 228, 220)
    engraving_dim: tuple = (160, 166, 168)
    glass: tuple = (8, 14, 14)
    text: tuple = (150, 255, 200)
    text_dim: tuple = (70, 150, 110)
    phosphor: tuple = (124, 255, 210)
    phosphor_dim: tuple = (40, 110, 90)
    map_line: tuple = (40, 120, 100)
    map_coast: tuple = (70, 170, 140)
    grid: tuple = (26, 60, 52)
    scope_flash: tuple = (210, 230, 255)
    scope_glow: tuple = (150, 255, 90)
    scope_bg: tuple = (4, 10, 6)
    accent: tuple = (255, 190, 60)
    alert: tuple = (255, 70, 60)
    ok: tuple = (80, 230, 110)
    lamp_amber: tuple = (255, 176, 40)
    lamp_red: tuple = (255, 60, 50)
    lamp_green: tuple = (70, 240, 110)
    lamp_white: tuple = (240, 240, 225)
    lamp_blue: tuple = (90, 170, 255)
    id_colors: dict = field(default_factory=dict)
    map_style: str = "sage"
    label_font: str = "crt"
    units: str = "imperial"
    title: str = ""
    subtitle: str = ""


US = Theme(
    name="ADC / SAGE", faction="US",
    id_colors={"pending": (150, 255, 210), "friend": (110, 210, 170), "unknown": (190, 255, 150),
               "suspect": (255, 220, 120), "hostile": (255, 120, 90), "faker": (150, 200, 255)},
    title="AIR DEFENSE COMMAND — SAGE DIRECTION CENTER", subtitle="BANGOR AIR DEFENSE SECTOR · DC-05",
)

USSR = Theme(
    name="PVO", faction="USSR",
    bg=(14, 18, 18), panel=(56, 92, 88), panel_hi=(92, 132, 126), panel_lo=(26, 44, 42),
    engraving=(236, 230, 204), engraving_dim=(170, 180, 164), glass=(10, 22, 24),
    text=(255, 196, 120), text_dim=(170, 120, 70), phosphor=(255, 200, 140), phosphor_dim=(120, 90, 60),
    map_line=(110, 120, 100), map_coast=(150, 150, 120), grid=(46, 84, 84),
    scope_flash=(255, 236, 190), scope_glow=(255, 150, 40), scope_bg=(10, 6, 2),
    id_colors={"pending": (235, 235, 225), "friend": (255, 95, 80), "unknown": (240, 210, 100),
               "suspect": (100, 175, 255), "hostile": (120, 190, 255), "faker": (200, 200, 200)},
    map_style="board", label_font="cyr", units="metric",
    title="ПВО СТРАНЫ — КОМАНДНЫЙ ПУНКТ 4-й ОА ПВО", subtitle="4th SEPARATE AIR DEFENSE ARMY · COMMAND POST",
)


def theme_for(faction: str) -> Theme:
    return USSR if faction == "USSR" else US


class Text:
    """Font and rendered-text cache."""

    def __init__(self):
        self._fonts: dict[tuple[str, int], pygame.font.Font] = {}
        self._cache: dict[tuple, pygame.Surface] = {}

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
            if len(self._cache) > 4000:
                self._cache.clear()
            s = self.font(kind, size).render(text, True, color)
            self._cache[key] = s
        return s

    def width(self, text: str, size: int = 13, kind: str = "ui") -> int:
        return self.font(kind, size).size(text)[0]

    def wrap(self, text: str, width: int, size: int = 13, kind: str = "ui") -> list[str]:
        out: list[str] = []
        f = self.font(kind, size)
        for para in text.split("\n"):
            if not para.strip():
                out.append("")
                continue
            indent = len(para) - len(para.lstrip(" "))
            words = para.split()
            line = " " * indent
            for w in words:
                cand = (line + " " + w) if line.strip() else (" " * indent + w)
                if f.size(cand)[0] <= width:
                    line = cand
                else:
                    if line.strip():
                        out.append(line)
                    line = " " * indent + w
            out.append(line)
        return out


TEXT = Text()
