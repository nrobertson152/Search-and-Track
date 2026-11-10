"""Mechanics added for the 1956-1987 eras: airborne radar, balloons, forced
landings, exercise kills, procedural watches, campaign bookkeeping."""
import math

import pygame
import pytest

from searchtrack.sim import commands, flight, procgen, radar, scenario, world as world_mod


def _step_until(w, t):
    while w.t < t and not w.ended:
        w.step()


def test_awacs_rides_its_aircraft_and_looks_down():
    w = scenario.build_world("us_bering_patrol")
    _step_until(w, 120)
    site = w.radars["darkstar_r"]
    ac = w.aircraft["awacs"]
    assert site.status == "ok" and abs(site.x - ac.x) < 1e-6 and site.h_ant == pytest.approx(ac.alt)
    rt = w.catalog.radars[site.type_id]
    # a low target 150 km out, flying radially: clutter is rejected by Doppler filtering
    low = world_mod.Aircraft(id="probe", type_id="Tu-95MS", callsign="P", side="red", x=site.x + 150.0, y=site.y,
                             alt=300.0, hdg=270.0, spd=200.0)
    bd = radar.evaluate(w, site, rt, low)
    assert bd.pd > 0.5, bd.explain()
    # the same target crossing the beam falls into the clutter notch
    low.hdg = 0.0
    bd = radar.evaluate(w, site, rt, low)
    assert bd.limit == "notch" and bd.pd < 0.1


def test_balloons_sink_at_night_and_climb_by_day():
    w = scenario.build_world("su_genetrix")
    m = w.aircraft["gx1-1"].mission
    night = flight.balloon_altitude(w, m)                    # 06:00 local, before sunrise
    w.t = 3.0 * 3600                                         # 09:00 local, sun up
    mid = flight.balloon_altitude(w, m)
    w.t = 5.0 * 3600                                         # 11:00 local
    day = flight.balloon_altitude(w, m)
    assert night == pytest.approx(m.alt_night) and day == pytest.approx(m.alt_day) and night < mid < day


def test_forced_landing_needs_warning_shots_then_succeeds():
    w = scenario.build_world("su_kola_airliner")
    fl = None
    shots = 0
    while w.t < 5400 and not w.stats.forced:
        w.step()
        trk = w.track_for_truth("airliner")
        if fl is None and trk is not None:
            assert commands.run(w, "scramble", squadron="kilp_iap", n=2, task="id", track=trk.id)[0]
            fl = list(w.flights)[-1]
        if fl and w.flights[fl].vid_done:
            if w.flights[fl].task != "force_land":
                commands.run(w, "task", flight=fl, task="force_land")
            ac = w.aircraft["airliner"]
            if not ac.mission.warned and w.vars.get(f"sig_{fl}_airliner", 0.0) < 0 and w.tick % 60 == 0:
                shots += commands.run(w, "warning_shots", flight=fl)[0]     # signals ignored: fire across the nose
    assert shots >= 1, "signals should have been ignored before the warning burst"
    assert w.stats.forced and w.stats.forced[0][0] == "airliner"


def test_exercise_kills_are_simulated():
    w = scenario.build_world("us_sky_shield")
    _step_until(w, 700)
    victim = next(a for a in w.aircraft.values() if a.side == "red" and a.state == "airborne")
    w.destroy(victim.id, "test", "FL1")
    assert victim.state == "airborne" and w.sim_killed(victim.id) and w.vars["sim_kills"] == 1


@pytest.mark.parametrize("base", ["us_northern_vigil", "su_red_square"])
def test_procedural_watch_plays_and_saves(base):
    sc = procgen.generate(base, 4242, difficulty=3)
    assert sc["flight"] and sc["objective"]
    w = scenario.build_world_from(sc)
    from searchtrack.sim import autoplay
    autoplay.play(w, max_s=1800)
    w2 = world_mod.load_json(world_mod.save_json(w))
    assert w2.t == w.t and set(w2.aircraft) == set(w.aircraft)


def test_campaign_records_a_watch(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from searchtrack.ui.app import App
    from searchtrack.ui.campaign import CampaignScene, load_career
    from searchtrack.ui.scenes import CommandScene, DebriefScene
    from tests.test_ui_smoke import press
    app = App(headless=True, sound=False)
    try:
        press(app, "CAMPAIGN")
        assert isinstance(app.scene, CampaignScene)
        press(app, "MISSION us_training_intercept")
        press(app, "BRIEFING")
        press(app, "TAKE THE WATCH")
        assert isinstance(app.scene, CommandScene)
        app.scene.end_shift()
        app.scene.ended_t = -100.0
        app.frame([], mouse=(0, 0))
        assert isinstance(app.scene, DebriefScene)
        assert "us_training_intercept" in load_career(app)["US"]["done"]
        press(app, "CONTINUE")
        assert isinstance(app.scene, CampaignScene)
    finally:
        pygame.quit()
