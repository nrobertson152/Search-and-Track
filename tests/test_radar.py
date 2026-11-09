import math

import pytest

from searchtrack.sim import radar
from searchtrack.sim.catalog import SWERLING1_SNR_DB_PD50_PFA6, load_catalog
from searchtrack.sim.radar import (blind_speed, integrated_snr_db, jam_to_noise_db, lobing_db, mti_response_db,
                                   pd_swerling1, snr_for_pd)


@pytest.fixture(scope="module")
def cat():
    return load_catalog()


def test_calibration_anchor(cat):
    for rt in cat.radars.values():
        snr = integrated_snr_db(rt, rt.ref_range_km, rt.ref_rcs_m2)
        assert snr == pytest.approx(SWERLING1_SNR_DB_PD50_PFA6, abs=1e-6)
        assert pd_swerling1(snr, 1e-6) == pytest.approx(0.5, abs=1e-6)


def test_range_fourth_power_and_rcs(cat):
    rt = cat.radars["AN/FPS-20A"]
    assert integrated_snr_db(rt, 100, 10) - integrated_snr_db(rt, 200, 10) == pytest.approx(12.04, abs=0.01)
    assert integrated_snr_db(rt, 100, 100) - integrated_snr_db(rt, 100, 10) == pytest.approx(10.0, abs=1e-6)


def test_faster_scan_fewer_pulses(cat):
    rt = cat.radars["AN/FPS-20A"]
    assert integrated_snr_db(rt, 200, 10, rpm=10.0) < integrated_snr_db(rt, 200, 10, rpm=5.0)


def test_swerling_monotonic_and_threshold_tradeoff():
    pds = [pd_swerling1(s, 1e-6) for s in range(0, 30, 2)]
    assert all(a < b for a, b in zip(pds, pds[1:]))
    assert pd_swerling1(12.0, 1e-4) > pd_swerling1(12.0, 1e-8)   # lower threshold -> more detections
    assert snr_for_pd(0.5, 1e-6) == pytest.approx(SWERLING1_SNR_DB_PD50_PFA6, abs=1e-6)


def test_mti_notch_and_blind_speed(cat):
    rt = cat.radars["AN/FPS-20A"]
    assert mti_response_db(rt, 0.0) <= -29.0
    assert mti_response_db(rt, blind_speed(rt)) <= -29.0
    assert mti_response_db(rt, blind_speed(rt) * 0.5) > 0.0
    assert blind_speed(rt) == pytest.approx(rt.wavelength_m * rt.prf / 2)


def test_vhf_lobing_has_nulls_and_low_angle_loss(cat):
    rt = cat.radars["P-10"]
    vals = [lobing_db(rt, 30.0, h, 150.0, 0.9) for h in range(200, 12000, 100)]
    assert min(vals) < -15.0 and max(vals) > 4.0
    assert lobing_db(rt, 30.0, 50.0, 200.0, 0.9) < -15.0   # very low target: poor VHF coverage
    assert lobing_db(cat.radars["AN/FPS-20A"], 30.0, 50.0, 200.0, 0.9) == 0.0


def test_jamming_mainlobe_vs_sidelobe(cat):
    rt = cat.radars["AN/FPS-20A"]
    jt = cat.jammers["ECM-BARRAGE-LS"]
    main = jam_to_noise_db(rt, jt, 200.0, True, True)
    side = jam_to_noise_db(rt, jt, 200.0, False, True)
    assert main - side == pytest.approx(-rt.sidelobe_db)
    assert main > 20.0                                  # strobe
    assert jam_to_noise_db(cat.radars["P-10"], jt, 200.0, True, True) == -99.0   # out of band
    spot = cat.jammers["ECM-SPOT-L"]
    assert jam_to_noise_db(rt, spot, 200.0, True, False) == -99.0              # radar changed channel


def test_detection_breakdown_explains_horizon_and_detects_high_target():
    from searchtrack.sim import scenario
    from searchtrack.sim.state import Aircraft
    w = scenario.build_world("us_training_intercept")
    site = w.radars["charleston"]
    rt = w.catalog.radars[site.type_id]
    low = Aircraft(id="lo", type_id="B707", callsign="", side="civil", x=site.x + 250, y=site.y, alt=300.0, hdg=270, spd=200)
    high = Aircraft(id="hi", type_id="B707", callsign="", side="civil", x=site.x + 150, y=site.y, alt=10000.0, hdg=270, spd=200)
    bd_low = radar.evaluate(w, site, rt, low, rng_draw=None)
    bd_high = radar.evaluate(w, site, rt, high, rng_draw=None)
    assert bd_low.limit in ("horizon", "terrain") and not bd_low.detected
    assert bd_high.detected and bd_high.pd > 0.9
    assert "horizon" in bd_low.explain() or "terrain" in bd_low.explain()


def test_coverage_grids_reflect_horizon_and_lobing():
    import numpy as np
    from searchtrack.sim import coverage, scenario
    w = scenario.build_world("us_training_intercept")
    site = w.radars["bucks_harbor"]
    xs = np.array([[site.x + 150.0, site.x + 330.0]])
    ys = np.array([[site.y, site.y]])
    low = coverage.horizontal(w, xs, ys, 500.0, sites=[site])
    high = coverage.horizontal(w, xs, ys, 12000.0, sites=[site])
    assert low[0, 1] == 0 and high[0, 0] == 1           # low target beyond horizon not covered
    v = coverage.vertical(w, site, 120.0, 370.0, 20000.0, 60, 40)
    assert v.shape == (40, 60) and v[-1, -1] == 0.0       # low & far: below horizon
    w2 = scenario.build_world("su_training_guidance")
    vh = coverage.vertical(w2, w2.radars["rlr_tagil"], 200.0, 300.0, 20000.0, 120, 80)
    col = vh[:, 40]
    assert (col < 0.2).sum() > 3 and (col > 0.8).sum() > 3  # VHF lobes: alternating holes and peaks
