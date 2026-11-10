import math

import pytest

from searchtrack.sim import intercept
from searchtrack.sim.catalog import load_catalog
from searchtrack.sim.flight import climb_rate, max_speed


def test_collision_triangle():
    # target 100 km north moving east at 0.2 km/s; interceptor at origin, 0.3 km/s
    sol = intercept.lead_collision(0, 100, 0.2, 0, 0, 0, 0.3)
    assert sol.method == "lead"
    tx, ty = 0 + 0.2 * sol.t, 100
    assert math.hypot(tx, ty) == pytest.approx(0.3 * sol.t, rel=1e-6)
    assert 0 < sol.hdg < 90


def test_unreachable_target_falls_back_to_pursuit():
    sol = intercept.lead_collision(0, 50, 0, 0.5, 0, 0, 0.2)   # faster target running away
    assert sol.method == "pursuit" and math.isinf(sol.t)


def test_stern_aim_is_behind_target():
    sol = intercept.stern_aim(0, 100, 0.2, 0, 0, 0, 0.3)
    assert sol.x < 0.2 * sol.t + 1e-6 or sol.method != "stern"


def test_performance_limits():
    cat = load_catalog()
    su9 = cat.aircraft["Su-9"]
    u2 = cat.aircraft["U-2C"]
    assert su9.zoom_ceiling_m < u2.cruise_alt_m          # the historical problem of 1960
    assert climb_rate(su9, su9.ceiling_m, "ab") == pytest.approx(0.0)
    assert max_speed(cat.aircraft["F-106A"], 12000) > max_speed(cat.aircraft["F-101B"], 12000)


def test_interceptor_cannot_exceed_zoom_ceiling_and_burns_fuel():
    from searchtrack.sim import scenario
    from searchtrack.sim.flight import step_aircraft
    from searchtrack.sim.state import Aircraft
    w = scenario.build_world("us_training_intercept")
    at = w.catalog.aircraft["F-101B"]
    ac = Aircraft(id="x", type_id="F-101B", callsign="T", side="blue", x=0, y=0, alt=12000, hdg=0, spd=500,
                  fuel=at.fuel_kg, throttle="ab", cmd_alt=25000)
    for _ in range(900):
        step_aircraft(w, ac, 1.0)
    assert ac.alt <= at.zoom_ceiling_m + 1.0
    assert ac.fuel < at.fuel_kg
