"""The operator's manual: every chapter parses and typesets, the GitHub mirror is
current, and the manual can be read from the title screen."""
import subprocess
import sys
from pathlib import Path

import pygame

from searchtrack.ui.manual import load_manual, parse, render_sheet

ROOT = Path(__file__).resolve().parents[1]


def test_chapters_parse_and_typeset():
    from searchtrack.ui.theme import TEXT
    pygame.font.init()
    TEXT.reset()                     # fonts from an earlier test's pygame session are dead
    chapters = load_manual()
    assert len(chapters) >= 10
    for ch in chapters:
        assert ch.title and ch.subtitle, ch.key
        assert ch.sections, f"{ch.key} has no sections"
        sheet, anchors = render_sheet(ch, 700, ussr=False)
        assert sheet.get_height() > 200
        assert set(anchors) == set(ch.sections)
        render_sheet(ch, 700, ussr=True)


def test_markdown_subset():
    ch = parse("# T\n\n> sub\n\n## A\nOne **two** `F1`.\n- x\n1. y\n\n| K | V |\n|---|---|\n| `I` | init |\n")
    kinds = [b[0] for b in ch.blocks]
    assert ch.title == "T" and ch.subtitle == "sub"
    assert kinds == ["h2", "p", "li", "ol", "table"]
    assert ch.blocks[-1][1] == [["K", "V"], ["`I`", "init"]]


def test_controls_chapter_lists_every_console_key():
    from searchtrack.ui.lesson import CONSOLE_TABS
    text = (ROOT / "data" / "manual" / "02-controls.md").read_text(encoding="utf-8")
    for tab in CONSOLE_TABS:
        assert f"`{tab.split()[-1]}`" in text, tab


def test_docs_mirror_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "sync_manual.py"), "--check"], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_manual_from_the_title_screen(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from searchtrack.ui.app import App
    from searchtrack.ui.manual import ManualScene
    from tests.test_ui_smoke import press
    app = App(headless=True, sound=False)
    try:
        press(app, "OPERATOR'S MANUAL")
        sc = app.scene
        assert isinstance(sc, ManualScene)
        press(app, "CHAPTER 4")
        assert sc.ci == 3
        sec = sc.chapters[3].sections[-1]
        press(app, f"SECTION {sec}")
        assert sc.scroll > 0
        app.frame([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0, unicode="")], mouse=(0, 0))
        assert sc.ci == 4 and sc.scroll == 0
        press(app, "BACK")
        assert not isinstance(app.scene, ManualScene)
    finally:
        pygame.quit()
