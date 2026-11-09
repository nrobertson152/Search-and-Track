import math

import numpy as np
import pytest

from searchtrack.sim.geo import (Projection, angle_diff, bearing_deg, elevation_angle, horizon_km,
                                 radar_horizon_km, in_sector)
from searchtrack.sim.terrain import Terrain, compute_mask


def test_projection_roundtrip_and_distance():
    p = Projection(45.0, -68.0)
    for lat, lon in [(45.0, -68.0), (46.2, -65.5), (42.3, -71.0), (48.0, -60.0)]:
        x, y = p.forward(lat, lon)
        la, lo = p.inverse(x, y)
        assert la == pytest.approx(lat, abs=1e-7) and lo == pytest.approx(lon, abs=1e-7)
    # distance from centre is exact for azimuthal equidistant: 1 deg of latitude ~ 111.19 km
    x, y = p.forward(46.0, -68.0)
    assert math.hypot(x, y) == pytest.approx(111.19, rel=1e-3)


def test_bearings_and_sectors():
    assert bearing_deg(0, 1) == pytest.approx(0.0)
    assert bearing_deg(1, 0) == pytest.approx(90.0)
    assert bearing_deg(-1, 0) == pytest.approx(270.0)
    assert angle_diff(10, 350) == pytest.approx(20.0)
    assert in_sector(5.0, 350.0, 20.0) and not in_sector(15.0, 350.0, 20.0)


def test_radar_horizon_formula():
    # classic 4/3-earth: d[km] ~= 4.12 * sqrt(h[m])
    assert horizon_km(100.0) == pytest.approx(4.12 * 10.0, rel=0.01)
    assert radar_horizon_km(100.0, 10000.0) == pytest.approx(4.12 * (10 + 100), rel=0.01)


def test_flat_earth_mask_equals_smooth_horizon():
    t = Terrain.flat(0.0, half_km=600, spacing=5.0)
    m = compute_mask(t, 0.0, 0.0, 300.0, 500.0)
    # a target at 1,000 m: horizon = 71 + 130 = 201 km
    d = radar_horizon_km(300.0, 1000.0)
    for r in (d - 15.0, d + 15.0):
        el = elevation_angle(300.0, 1000.0, r)
        visible = el > m.obstruction(45.0, r)
        assert visible == (r < d)


def test_terrain_ridge_masks_low_target():
    elev = np.zeros((241, 241), dtype=np.float32)
    elev[:, 140:146] = 1500.0          # N-S ridge ~ 100 km east of the radar
    t = Terrain(elev, -600.0, -600.0, 5.0)
    m = compute_mask(t, 0.0, 0.0, 200.0, 300.0)
    el_low = elevation_angle(200.0, 1000.0, 150.0)
    el_high = elevation_angle(200.0, 9000.0, 150.0)
    assert el_low <= m.obstruction(90.0, 150.0)       # behind ridge: masked
    assert el_high > m.obstruction(90.0, 150.0)       # high target clears ridge
    assert elevation_angle(200.0, 1000.0, 150.0) > m.obstruction(270.0, 150.0)  # open side
    assert m.clutter_db(90.0, 99.0) > -900            # leading face of ridge is visible clutter
    assert m.clutter_db(90.0, 160.0) < -900           # shadowed ground behind ridge
