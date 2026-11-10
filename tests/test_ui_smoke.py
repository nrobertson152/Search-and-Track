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
    press(app, "SELECT PVO")
    assert app.scene.faction == "USSR"
    press(app, "SCENARIOS")
    app.scene.sel_id = "su_may_day"
    press(app, "BRIEFING")
    press(app, "TAKE THE WATCH")
    sc = app.scene
    assert isinstance(sc, CommandScene) and sc.theme.map_style == "board"
    for _ in range(3):
        app.frame([], mouse=(0, 0))
    # the PVO command post is its own room: board keys under the board, the cabinet on the right
    for label in ("BOARD", "RADAR SCOPE", "NETWORK", "ADVANCE", "8×", "<", ">", "RANGE", "MENU"):
        assert label in app.gui.drawn, label
    assert app.gui.drawn["ADVANCE"].x > sc.L.display.right       # in the cabinet, not over the board
    assert sc.L.console.right < sc.L.display.x                    # the operator's desk is on the left


def right_click(app, pos):
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=pos)], mouse=pos)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=pos)], mouse=pos)


def test_right_click_orders_send_the_nearest_interceptor(app):
    from searchtrack.ui.scenes import CommandScene
    press(app, "SELECT PVO")
    press(app, "SCENARIOS")
    app.scene.sel_id = "su_may_day"
    press(app, "BRIEFING")
    press(app, "TAKE THE WATCH")
    sc = app.scene
    assert isinstance(sc, CommandScene)
    w = sc.world
    while not any(t.identity in ("unknown", "suspect", "hostile") and not t.lost for t in w.tracks.values()):
        w.step()
    sc.render_t = w.t
    trk = next(t for t in w.tracks.values() if t.identity in ("unknown", "suspect", "hostile") and not t.lost)
    sc.map.center_on(trk.x, trk.y)
    app.frame([], mouse=(0, 0))
    before = len(w.flights)
    right_click(app, sc.map.w2s(trk.x, trk.y))
    assert sc.ctx and sc.sel.get("track") == trk.id
    assert "ORDER ID PASS" in app.gui.drawn and "ID PASS" not in sc.ctx["title"]
    click(app, app.gui.drawn["ORDER ID PASS"].center)
    assert sc.ctx is None
    assert len(w.flights) == before + 1 or any(f.target == trk.id for f in w.flights.values())
    fl = next(f for f in w.flights.values() if f.target == trk.id)
    assert fl.task == "id" and fl.geometry == "stern"
    # a second order on the same track re-tasks the flight that is already on it
    right_click(app, sc.map.w2s(trk.x, trk.y))
    click(app, app.gui.drawn["ORDER INTERCEPT"].center)
    assert fl.task == "intercept" and sum(1 for f in w.flights.values() if f.target == trk.id) == 1
    # a click elsewhere closes the menu without acting
    right_click(app, sc.map.w2s(trk.x, trk.y))
    click(app, (sc.L.display.x + 5, sc.L.display.bottom - 5))
    assert sc.ctx is None
