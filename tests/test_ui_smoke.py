"""Drive the real interface headless: every step is a simulated mouse click on a
button found by its label, so dead or mis-wired controls fail the test."""
import pygame
import pytest

from searchtrack.ui.app import App


def click(app, pos):
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)], mouse=pos)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)], mouse=pos)


def press(app, label_start):
    app.frame([], mouse=(0, 0))
    for label, r in app.gui.drawn.items():
        if label.startswith(label_start):
            click(app, r.center)
            return label
    raise AssertionError(f"no button starting with {label_start!r}; have {sorted(app.gui.drawn)}")


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    a = App(headless=True, sound=False)
    yield a
    pygame.quit()


def test_full_training_loop_through_the_ui(app):
    from searchtrack.ui.scenes import BriefingScene, CommandScene
    from searchtrack.ui.scenes import OperationsScene
    press(app, "TRAINING")
    ops = app.scene
    assert isinstance(ops, OperationsScene)
    assert ops.sel_id == "us_training_intercept"
    press(app, "BRIEFING")
    assert isinstance(app.scene, BriefingScene)
    press(app, "TAKE THE WATCH")
    sc = app.scene
    assert isinstance(sc, CommandScene)
    w = sc.world
    while not w.plots or w.t < 150:
        w.step()
    sc.render_t = w.t
    p = w.plots[-1]
    click(app, sc.map.w2s(p.x, p.y))            # light gun on the return
    assert sc.map.light_gun is not None
    press(app, "INITIATE")
    assert w.tracks, "light-gun initiation through the UI failed"
    tid = next(iter(w.tracks))
    sc.sel["track"] = tid
    press(app, "UNKNOWN")
    assert w.tracks[tid].identity == "unknown"
    press(app, "WEAPONS")
    press(app, "SCRAMBLE ON")
    assert w.flights, "scramble through the UI failed"
    for label in ("MISSILES", "RADAR", "COMMS", "INTEL", "STATUS", "TRACKS"):
        press(app, label)                       # every console draws without error
    press(app, "RADAR SCOPE")
    assert sc.mode == "scope"
    press(app, "STATUS")
    press(app, "SAVE")
    assert app.has_save()


def test_soviet_title_and_board(app):
    from searchtrack.ui.scenes import CommandScene
    press(app, "SELECT ПВО")
    assert app.scene.faction == "USSR"
    press(app, "SCENARIOS")
    app.scene.sel_id = "su_may_day"
    press(app, "BRIEFING")
    press(app, "TAKE THE WATCH")
    sc = app.scene
    assert isinstance(sc, CommandScene) and sc.theme.map_style == "board"
    for _ in range(3):
        app.frame([], mouse=(0, 0))
