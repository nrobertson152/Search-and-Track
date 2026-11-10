"""The war as a story: peace and the FLASH, mercy, the ceasefire, named aircrews carried from one battle
to the next, and the pages read between the battles."""
import math

import pytest

from searchtrack.sim import scenario, story, war
from searchtrack.sim.battle import director, staff


def _run(w, seconds):
    end = w.t + seconds
    while w.t < end and not w.ended:
        w.step(1.0)


def test_peace_holds_fire_until_the_flash():
    w = scenario.build_world("us_battle_prologue", seed=7)
    w.battle.spectator = True
    assert w.battle.standing["roe"] == "peace" and w.hq.weapons_status == "HOLD"
    before = 0.0
    while not w.vars.get("war") and w.t < 25 * 60:
        before = w.battle.counters.get("air_shots_blue", 0.0)
        w.step(1.0)
    assert w.vars.get("war"), "the FLASH never came"
    assert before == 0.0                                           # not one shot before it
    escorts = [e for e in w.battle.events if e[1] == "commit" and "escort" in e[2]]
    assert escorts, "nobody went out to meet the BEARs"
    assert any(e[1] == "intercepted" for e in w.battle.events)
    hold = next(o for o in w.objectives if o.kind == "hold_fire")
    assert hold.status == "done"
    _run(w, 240)
    assert w.battle.counters.get("air_shots_blue", 0.0) > 0       # the escorts became the hunters


def test_mercy_lets_the_shadowers_go_home():
    w = scenario.build_world("us_battle_prologue", seed=7)
    w.battle.spectator = True
    w.battle.phases = [ph for ph in w.battle.phases if ph.get("id") != "flash"]   # the FLASH comes from the test
    while not (w.vars.get("intercepted_bear1") and w.vars.get("intercepted_bear2")) and w.t < 19 * 60:
        w.step(1.0)
    director.start_war(w, spare=["bear1", "bear2"], text="test")
    assert w.vars.get("mercy") == 1.0
    for gid in ("bear1", "bear2"):
        g = w.battle.groups[gid]
        assert g.state in ("egress", "done", "pending")
    on_them = [fl for fl in w.flights.values()
               if fl.target and fl.target in w.tracks and staff.spared(w, w.tracks[fl.target])]
    assert not on_them, "our fighters are still on the BEARs"
    _run(w, 300)
    assert w.battle.groups["bear1"].losses == 0 and w.battle.groups["bear2"].losses == 0


def test_ceasefire_silences_both_sides_and_an_order_can_break_it():
    w = scenario.build_world("us_battle_finale", seed=4)
    w.battle.spectator = True
    _run(w, 30)
    director.act(w, {"do": "launch", "groups": ["backfire_a"]})
    _run(w, 60)
    director.ceasefire(w, "test")
    assert w.battle.standing["roe"] == "ceasefire" and w.hq.weapons_status == "HOLD"
    assert all(g.state in ("egress", "pending", "done") for g in w.battle.groups.values() if g.side == "red")
    assert all(not a.jamming for a in w.aircraft.values() if a.side == "red" and a.state == "airborne")
    shots = w.battle.counters.get("air_shots_blue", 0.0)
    director.act(w, {"do": "launch", "groups": ["stray"]})
    _run(w, 200)
    assert w.battle.counters.get("air_shots_blue", 0.0) == shots   # nobody fires at the straggler on his own
    director.engage_groups(w, ["stray"], "test")
    cleared = [t for t in w.tracks.values() if not t.lost and director.cleared(w, t)]
    assert all(t.id in w.hq.engage_ok and t.identity == "hostile" for t in cleared)


def test_a_spared_straggler_ditches_and_the_crew_is_picked_up():
    w = scenario.build_world("us_battle_finale", seed=4)
    w.battle.spectator = True
    _run(w, 10)
    director.ceasefire(w, "test")
    director.act(w, {"do": "launch", "groups": ["stray"]})
    _run(w, 30)
    director.spare_groups(w, ["stray"])
    assert w.vars.get("mercy") == 1.0
    _run(w, 1500)
    assert w.vars.get("ditched_stray")
    ditch = [e for e in w.battle.events if e[1] == "ditched"]
    assert ditch and "helicopters" in ditch[0][2]


def test_after_s_delays_an_action():
    w = scenario.build_world("us_battle_bering", seed=2)
    director.act(w, {"do": "say", "text": "later", "after_s": 30.0})
    assert not any(e[2] == "later" for e in w.battle.events)
    _run(w, 40)
    assert any(e[2] == "later" for e in w.battle.events)


def test_every_pilot_has_a_name_of_his_own():
    w = scenario.build_world("us_battle_bering", seed=1)
    names = [p.surname for p in w.battle.pilots.values()]
    assert names and len(names) == len(set(names))
    flying = [a for a in w.aircraft.values() if a.pilot]
    assert flying and all(w.battle.pilots[a.pilot].status == "flying" for a in flying)


def test_the_war_remembers_its_aircrews():
    st = war.new_state("northern_war_us")
    assert st["inbox"] and st["inbox"][0]["kind"] == "teletype"   # the war opens with its papers
    w = war.build_world(st, seed=3)
    assert w.scenario_id == "us_battle_prologue"
    pilots = sorted(w.battle.pilots.values(), key=lambda p: p.id)
    ace, dead = pilots[0], pilots[1]
    ace.kills, dead.status, dead.note = 5, "kia", "killed"
    w.vars[f"pk_{ace.id}"] = 5.0
    w.battle.outcome = "VICTORY"
    st["inbox"] = []
    war.advance(st, w)
    rec = {r["id"]: r for r in st["roster"]}
    assert rec[ace.id]["kills"] == 5 and rec[ace.id]["medals"]
    assert rec[dead.id]["status"] == "kia" and st["fallen"][0]["id"] == dead.id
    kinds = [p["kind"] for p in st["inbox"]]
    titles = [p["title"] for p in st["inbox"]]
    assert "letter" in kinds                                     # to the family of the fallen
    assert any("AIRCREW" in t for t in titles)
    assert all("{" not in p["text"] for p in st["inbox"])        # every name filled in
    w2 = war.build_world(st, seed=4)
    assert w2.scenario_id == "us_battle_bering"
    assert w2.battle.pilots[ace.id].kills == 5
    assert w2.battle.pilots[dead.id].status == "kia"
    assert not any(a.pilot == dead.id for a in w2.aircraft.values())


@pytest.mark.parametrize("hit", [True, False])
def test_the_letters_know_whether_the_radar_was_destroyed(hit):
    """The radar operator writes home from the company the Americans did or did not destroy."""
    st = war.new_state("northern_war_su")
    st["mission"], st["inbox"] = 1, []
    w = war.build_world(st, seed=3)
    assert w.scenario_id == "su_battle_kola"
    if hit:
        w.vars["dead_rlr_teriberka"] = 1.0
    w.battle.outcome = "DRAW"
    war.advance(st, w)
    letters = [p["text"] for p in st["inbox"] if p["title"] == "A LETTER HOME"]
    assert len(letters) == 1
    assert ("will not turn again" in letters[0]) == hit and ("shot them down" in letters[0]) == (not hit)
    assert ("rlr_teriberka" in st["oob"]["sites"]) == hit


def test_story_pages_choose_by_outcome_and_fill_in_names():
    items = [{"kind": "newspaper", "title": "WIN", "text": "{best} got {best_kills}", "when": "victory"},
             {"kind": "diary", "title": "LOSS", "text": "lost {lost}", "when": "defeat"},
             {"kind": "letter", "title": "KIND", "text": "spared {nobody}", "when": ["mercy", "no_defeat"]}]
    ctx = {"best": "LT Navarro", "best_kills": 3, "lost": 2}
    got = story.pages(items, ctx, {"victory": True, "mercy": True})
    assert [p["title"] for p in got] == ["WIN", "KIND"]
    assert got[0]["text"] == "LT Navarro got 3" and got[1]["text"] == "spared —"
    assert story.formal("CDR Jack 'Hollywood' Harlan") == "CDR Jack Harlan"


@pytest.mark.parametrize("cid", ["northern_war_us", "northern_war_su"])
def test_campaign_pages_are_complete(cid):
    import re
    c = war.campaign(cid)
    assert len(c["mission"]) == 5
    ids = {s["id"] for s in scenario.list_scenarios()}
    assert all(m["scenario"] in ids for m in c["mission"])
    known = set(c.get("cast", {})) | {"war", "mercy", "ace", "ace_short", "ace_kills", "ace_unit", "date", "outcome",
                                      "lost", "kills", "ships_lost", "fallen", "fallen_n", "missing_n", "rescued_n",
                                      "best", "best_short", "best_kills", "battle"}
    raw = list(c.get("intro", [])) + [p for m in c["mission"] for p in m.get("page", [])] + c.get("epilogue", []) \
        + c.get("lost", [])
    for p in raw:
        for field in ("text", "title", "from", "to", "date"):
            for name in re.findall(r"\{(\w+)\}", p.get(field, "")):
                assert name in known, f"{p.get('title')}: unknown name {{{name}}}"
        assert p.get("at", "before") in ("before", "after", "next")
    pages = story.every_page(c, story.context(war.new_state(cid), c, None, {}))
    assert len(pages) >= 20
    assert all(p["kind"] in story.KINDS and p["text"] for p in pages)


def test_missile_endgame_does_not_overshoot_a_crossing_target(monkeypatch):
    from searchtrack.sim import sam
    from searchtrack.sim.battle import combat
    from searchtrack.sim.flight import ground_velocity
    from searchtrack.sim.state import Missile
    w = scenario.build_world("us_battle_bering", seed=1)
    w.rng.random = lambda: 0.0                                   # every warhead that fuzes kills
    hits = []
    monkeypatch.setattr(combat, "hit", lambda world, tgt, cause, shooter: hits.append(tgt.id))
    tgt = next(a for a in w.aircraft.values() if a.side == "blue" and a.state == "airborne")
    for k in range(4):
        tgt.hdg, tgt.spd, tgt.vs, tgt.state = 0.0, 220.0, 0.0, "airborne"
        m = Missile(id=f"MT{k}", type_id="AIM-7F", kind="aam", owner="test", side="red", x=tgt.x - 8.0,
                    y=tgt.y + 1.0 + 0.5 * k, alt=tgt.alt, target=tgt.id, t_launch=w.t)
        m.vx, m.vy = 700.0, 0.0                                  # coming in from the beam, 90 degrees off
        for _ in range(40):
            sam.missile_step(w, m, 1.0)
            vx, vy = ground_velocity(w, tgt)
            tgt.x += vx
            tgt.y += vy
            if m.state != "flying":
                break
    assert len(hits) >= 3, hits


def test_air_launched_cruise_missiles_leave_in_a_stream():
    w = scenario.build_world("us_battle_alaska", seed=2)
    w.battle.spectator = True
    w.battle.standing["fighters"] = "manual"                    # nobody goes after the BEAR
    w.battle.cap_stations = []
    for sq in w.squadrons.values():
        sq.ready = {k: 0 for k in sq.ready}
    while not w.battle.groups["bear_r1"].released and w.t < 15 * 60:
        w.step(1.0)
    ms = [a for a in w.aircraft.values() if a.type_id == "AS-15" and a.state == "airborne"]
    assert len(ms) == 6
    gaps = sorted(math.hypot(a.x - b.x, a.y - b.y) for a in ms for b in ms if a.id < b.id)
    assert gaps[0] > 1.0                                         # no two in the same radar cell


def test_interlude_shows_every_page(monkeypatch, tmp_path):
    import pygame
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from searchtrack.ui.app import App
    from searchtrack.ui.interlude import InterludeScene
    app = App(headless=True, sound=False)
    try:
        for cid, fac in (("northern_war_us", "US"), ("northern_war_su", "USSR")):
            c = war.campaign(cid)
            pages = story.every_page(c, story.context(war.new_state(cid), c, None, {}))
            sc = InterludeScene(app, fac, pages)
            app.push(sc)
            for i in range(len(pages)):
                sc.i, sc.shown = i, 1e9
                app.frame([], mouse=(0, 0))
            assert app.scene is sc
            app.pop()
    finally:
        pygame.quit()
