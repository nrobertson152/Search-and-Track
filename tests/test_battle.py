"""Battle missions: the autonomous forces, the director, strikes on the ground and the staff."""
import math

from searchtrack.sim import scenario
from searchtrack.sim.battle import air, director, land, staff
from searchtrack.sim.battle.core import spec_xy


def _quiet_defences(w):
    """No fighters, no missile battalions: let the weapons under test arrive unopposed."""
    for s in w.sams.values():
        s.status = "down"
    for sq in w.squadrons.values():
        sq.ready = {k: 0 for k in sq.ready}
    for g in w.battle.groups.values():
        g.state = "done"
    w.battle.cap_stations = []
    w.battle.phases = []                           # no story: the battle does not end on its own
    w.triggers = []


def _run(w, seconds):
    end = w.t + seconds
    while w.t < end and not w.ended:
        w.step(1.0)


def test_battle_is_deterministic():
    a = scenario.build_world("us_battle_bering", seed=11)
    b = scenario.build_world("us_battle_bering", seed=11)
    for w in (a, b):
        w.battle.spectator = True
        _run(w, 900)
    assert [e[:4] for e in a.battle.events] == [e[:4] for e in b.battle.events]
    assert a.battle.counters == b.battle.counters


def test_spectator_staff_answers_decisions():
    w = scenario.build_world("us_battle_bering", seed=3)
    w.battle.spectator = True
    _run(w, 120)
    emcon = [d for d in w.battle.decisions if d.kind == "emcon"]
    assert emcon and emcon[0].chosen and emcon[0].by != "player"


def test_tomahawks_fly_their_route_and_crater_a_runway():
    w = scenario.build_world("su_battle_kola", seed=5)
    _quiet_defences(w)
    kx, ky = w.airbases["kilpyavr"].x, w.airbases["kilpyavr"].y
    n = land.salvo(w, {"weapon": "TLAM-C", "n": 2, "from": {"x": kx - 60.0, "y": ky + 20.0},
                       "route": [{"x": kx - 25.0, "y": ky + 10.0}], "targets": ["kilpyavr"], "stream_km": 4.0})
    assert n == 2
    ms = [a for a in w.aircraft.values() if a.type_id == "TLAM-C"]
    assert all(m.route for m in ms)
    _run(w, 420)
    assert all(m.state == "gone" for m in ms)
    hits = [e for e in w.battle.events if e[1] == "ground_hit" and e[3] == "kilpyavr"]
    assert hits, "the runway was not hit"
    assert not w.airbases["kilpyavr"].runway_ok
    # the craters get filled in again
    _run(w, 3000)
    assert w.airbases["kilpyavr"].runway_ok


def test_low_flying_cruise_missile_follows_the_terrain():
    w = scenario.build_world("su_battle_kola", seed=5)
    _quiet_defences(w)
    land.salvo(w, {"weapon": "TLAM-C", "n": 1, "from": {"lat": 69.25, "lon": 29.5}, "targets": ["monchegorsk"]})
    m = next(a for a in w.aircraft.values() if a.type_id == "TLAM-C")
    agl = []
    for _ in range(240):
        w.step(1.0)
        if m.state == "airborne":
            agl.append(m.alt - w.ground_height(m.x, m.y))
    assert agl and max(agl[30:]) < 400.0          # it never climbs above the hills it hides behind


def _harm_at(w, ref, x, y):
    shooter = next(a for a in w.aircraft.values() if a.side == "blue")
    shooter.side = "red"                           # borrow an airframe as the launch platform
    shooter.x, shooter.y, shooter.alt = x + 50.0, y + 10.0, 8000.0
    return land.launch(w, shooter, "AGM-88A", (x, y), "test", "red", homing=ref)


def test_harm_kills_a_radar_that_keeps_radiating():
    w = scenario.build_world("su_battle_kola", seed=8)
    _quiet_defences(w)
    site = w.radars["rlr_teriberka"]
    hit = 0
    for _ in range(4):
        site.status, site.repair_t = "ok", -1.0
        w.vars.pop("dead_rlr_teriberka", None)
        m = _harm_at(w, "R:rlr_teriberka", site.x, site.y)
        for _ in range(200):
            w.step(1.0)
            if m.state != "airborne":
                break
        assert m.state == "gone"
        hit += site.status == "down"
    assert hit >= 2


def test_battalion_switches_off_for_an_incoming_harm():
    w = scenario.build_world("su_battle_kola", seed=9)
    _quiet_defences(w)
    s = w.sams["zrdn_severomorsk"]
    s.status, s.state = "ok", "locked"
    real = w.rng.random
    w.rng.random = lambda: 0.0                     # this crew always hears it coming
    m = _harm_at(w, "S:zrdn_severomorsk", s.x, s.y)
    for _ in range(200):
        w.step(1.0)
        if any(e[1] == "shutdown" for e in w.battle.events):
            break
    w.rng.random = real
    assert any(e[1] == "shutdown" for e in w.battle.events)
    assert s.status == "down" and not land.emitter_state(w, m.homing)[2]
    heard = w.vars[f"arm_{m.id}"]
    w.step(1.0)
    assert w.vars.get(f"arm_{m.id}", heard) == heard   # the missile has lost the emitter: it coasts on memory
    _run(w, 120)
    assert s.status == "ok" or land.is_destroyed(w, s.id) or f"sam_repair_{s.id}" in w.vars


def test_strike_without_a_fix_presses_in_closer():
    w = scenario.build_world("us_battle_bering", seed=2)
    g = w.battle.groups["backfire_a"]
    air.launch(w, g)
    lead = air.members(w, g)[0]
    aim, quality, ship = air._strike_aim(w, g, lead, w.catalog.aircraft[g.type_id])
    assert quality == "brief" and aim is not None and not ship


def test_runway_and_radar_objectives():
    w = scenario.build_world("su_battle_kola", seed=4)
    obj = {o.id: o for o in w.objectives}
    for bid in ("kilpyavr", "monchegorsk"):
        w.airbases[bid].runway_ok = False
    assert director.objective(w, obj["runways"], False) is None       # two closed: still allowed
    w.airbases["severomorsk3"].runway_ok = False
    assert director.objective(w, obj["runways"], False) == "failed"
    for rid in ("rlr_rybachy", "rlr_teriberka", "rlr_kovdor"):
        land.hit_installation(w, rid, "test", heavy=10.0)
    assert director.objective(w, obj["radars"], False) == "failed"


def test_pvo_battle_aircraft_answer_kremniy_and_hostile_zone_rules():
    w = scenario.build_world("su_battle_kola", seed=6)
    a50 = air.members(w, w.battle.groups["a50"]) or None
    if not a50:
        _run(w, 2)
        a50 = air.members(w, w.battle.groups["a50"])
    assert a50[0].transponder.system == "kremniy"
    hy = w.battle.red_plan.get("hostile_y")
    assert hy is not None and hy > spec_xy(w, {"lat": 70.0, "lon": 33.0})[1]


def test_kola_battle_moves_through_its_phases():
    w = scenario.build_world("su_battle_kola", seed=1941)
    w.battle.spectator = True
    _run(w, 30 * 60)
    assert w.battle.phase >= 2
    assert w.battle.counters.get("fired_TLAM-C", 0) == 16
    assert any(e[1] in ("ground_hit", "vampire_kill") for e in w.battle.events)
    assert any(e[1] == "commit" for e in w.battle.events)
    classes = {staff.classify(w, t) for t in w.tracks.values()}
    assert "unknown" in classes or "missile" in classes
    assert all(math.isfinite(a.x) and math.isfinite(a.y) for a in w.aircraft.values())
