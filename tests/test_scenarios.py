import pytest

from searchtrack.sim import aar, autoplay, scenario

IDS = [s["id"] for s in scenario.list_scenarios()]


def test_all_four_scenarios_present():
    assert {"us_training_intercept", "us_northern_vigil", "su_may_day", "su_training_guidance"} <= set(IDS)


@pytest.mark.parametrize("sid", IDS)
def test_scenario_autoplays_to_the_end(sid):
    w = scenario.build_world(sid)
    autoplay.play(w)
    if not w.ended:
        scenario.end(w, "test end")
    rep = aar.build(w)
    assert rep["total"] > 0
    assert all(o["status"] in ("done", "failed") for o in rep["objectives"])
    assert aar.as_text(rep)
