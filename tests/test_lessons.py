"""Training lessons: every instructor-led lesson can be completed step by step,
and the instructor's card points at controls that really exist."""
import pygame
import pytest

from searchtrack.sim import scenario
from searchtrack.sim.student import Student, run_lesson
from searchtrack.sim.world import load_json, save_json

LESSONS = [s["id"] for s in scenario.list_scenarios() if s["kind"] == "training"]


def test_there_are_three_lessons_per_side():
    assert sum(1 for s in LESSONS if s.startswith("us_")) == 3
    assert sum(1 for s in LESSONS if s.startswith("su_")) == 3


@pytest.mark.parametrize("sid", LESSONS)
def test_model_student_completes_every_lesson(sid):
    w = scenario.build_world(sid)
    n = sum(1 for tr in w.triggers if tr.id.startswith("lesson_") and tr.id[7:].isdigit())
    assert n >= 5, "a lesson needs real steps"
    seen = []
    st = Student(w)
    while not w.ended and w.t < w.duration:
        st.act()
        w.step(1.0)
        k = w.lesson.get("step")
        if k and (not seen or seen[-1] != k):
            seen.append(k)
    assert w.result == "complete", (sid, w.lesson.get("title"), w.end_reason)
    assert seen == sorted(seen) and seen[-1] == n, seen       # steps advance in order, none repeated
    assert w.lesson.get("final")
    got, total, _ = scenario.score(w)
    assert got == total, [(o.text, o.status) for o in w.objectives]


def test_lesson_state_survives_save_and_load():
    w = scenario.build_world("us_training_intercept")
    st = Student(w)
    while w.vars.get("lesson_step", 0) < 3:
        st.act()
        w.step(1.0)
    w2 = load_json(save_json(w))
    assert w2.lesson["title"] == w.lesson["title"]
    run_lesson(w2)
    assert w2.result == "complete"


def test_steps_wait_for_their_predecessor():
    """Doing step 3's job first must not skip the card past steps 1 and 2."""
    w = scenario.build_world("us_training_intercept")
    while not w.lesson:
        w.step(1.0)
    w.vars["ui_mode_scope"] = 1.0
    for _ in range(5):
        w.step(1.0)
    assert w.lesson["step"] == 1


def test_card_circles_controls_on_the_console(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from searchtrack.ui.app import App
    app = App(headless=True, sound=False)
    try:
        w = scenario.build_world("us_training_intercept")
        while not w.lesson:
            w.step(1.0)
        app.start_command(w)
        sc = app.scene
        app.frame([], mouse=(0, 0))
        assert sc.lesson.rect is not None                      # the card is up
        assert "INITIATE TRACK (I)" in app.gui.highlight
        rects = app.gui.highlighted()
        assert rects and app.gui.drawn["INITIATE TRACK (I)"] in rects
        # step 4 wants the WEAPONS console: its tab is circled until it is opened
        st = Student(w)
        while w.vars.get("lesson_step", 0) < 4:
            st.act()
            w.step(1.0)
        app.frame([], mouse=(0, 0))
        assert "WEAPONS F2" in app.gui.highlight
        sc.ci = 1
        app.frame([], mouse=(0, 0))
        assert "WEAPONS F2" not in app.gui.highlight
        scramble = [r for k, r in app.gui.drawn.items() if k.startswith("SCRAMBLE")]
        assert scramble and scramble[0] in app.gui.highlighted()
        assert w.vars.get("ui_console_weapons", 0) >= 1       # the instructor saw the console change
        # clicking the card header folds it and does not reach the display
        hdr = sc.lesson.header.center
        app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=hdr)], mouse=hdr)
        app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=hdr)], mouse=hdr)
        assert sc.lesson.collapsed and sc.map.light_gun is None
    finally:
        pygame.quit()
