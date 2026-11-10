import math

from searchtrack.sim import commands, ident, scenario, tracking
from searchtrack.sim.state import FlightPlan, Report, Track


def _w():
    return scenario.build_world("us_training_intercept")


def test_alpha_beta_converges_on_constant_velocity():
    w = _w()
    trk = Track(id="T", x=0, y=0, t_update=0.0)
    for k in range(1, 30):
        t = k * 12.0
        tracking.update_track(w, trk, Report(k, t, t, "charleston", 0.2 * t, 0.0), manual=False)
    assert abs(trk.vx - 0.2) < 0.01 and abs(trk.vy) < 0.01


def test_light_gun_initiation_needs_returns():
    w = _w()
    ok, _ = commands.run(w, "initiate", x=0.0, y=0.0)
    assert not ok
    w.plots.append(Report(1, 0.0, 0.0, "charleston", 10.0, 10.0))
    w.plots.append(Report(2, 12.0, 12.0, "charleston", 12.0, 10.0))
    ok, msg = commands.run(w, "initiate", x=11.0, y=10.0)
    assert ok and w.tracks


def test_flight_plan_tolerances():
    w = _w()
    w.t = 1000.0
    fp = FlightPlan("fp1", "TEST 1", "B707", route=[[0.0, 0.0, 0.0], [200.0, 0.0, 1000.0]])
    w.flight_plans = {"fp1": fp}
    on = Track(id="A", x=200.0, y=5.0)       # on time, 2.7 nm off route
    late = Track(id="B", x=120.0, y=0.0)     # 400 s behind plan (6.7 min) -> outside +-5 min
    off = Track(id="C", x=200.0, y=60.0)     # 32 nm off route
    assert ident.correlate(w, on)[0].within
    assert not ident.correlate(w, late)[0].within
    m = ident.correlate(w, off)
    assert not m or not m[0].within


def test_hostile_requires_authority():
    w = _w()
    w.tracks["A001"] = Track(id="A001", x=0, y=0)
    ok, msg = commands.run(w, "identity", track="A001", ident="hostile")
    assert not ok and "authority" in msg.lower()
    ok, _ = commands.run(w, "identity", track="A001", ident="unknown")
    assert ok and w.tracks["A001"].identity == "unknown"


def test_weapons_free_rejected_under_hold():
    w = _w()
    w.tracks["A001"] = Track(id="A001", x=0, y=0, identity="unknown")
    ok, msg, fid = __import__("searchtrack.sim.gci", fromlist=["x"]).scramble(w, "75fis", 2, "intercept", "A001")
    assert ok
    ok, msg = commands.run(w, "weapons_free", flight=fid, on=True)
    assert not ok and "HOLD" in msg.upper()
