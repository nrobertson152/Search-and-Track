"""A model student: reads the instructor's current step and does what it asks.

Used by the tests to prove every training lesson can be completed, and by
``--student`` demo runs. It works from each step's ``done`` condition, so a
lesson authored with a new condition needs a matching rule here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import commands, scenario

if TYPE_CHECKING:
    from .world import World


def _truth_track(w: "World", ac: str, skin: bool = False):
    if skin:
        tr = scenario._skin_tracks(w, ac)
        return max(tr, key=lambda t: t.t_update) if tr else None
    for a in scenario._truth_ids(w, ac):
        trk = w.track_for_truth(a)
        if trk is not None and not trk.lost:
            return trk
    return None


def _is_ac(w: "World", ref: str) -> bool:
    return bool(ref) and (ref in w.aircraft or any(k.startswith(ref + "-") for k in w.aircraft))


class Student:
    def __init__(self, world: "World"):
        self.w = world
        self.last = -1.0
        self.subject = "target"      # the aircraft the lesson is about (last one named)

    def _note(self, c: dict) -> None:
        if c.get("ac"):
            self.subject = c["ac"]
        for x in c.get("of", []):
            self._note(x)

    def act(self) -> None:
        w = self.w
        if not w.lesson or w.lesson.get("final") or w.t - self.last < 5.0:
            return
        self.last = w.t
        if _is_ac(w, w.lesson.get("mark", "")):
            self.subject = w.lesson["mark"]
        cond = w.lesson.get("done")
        if cond:
            self._note(cond)
            self._do(cond)

    # ------------------------------------------------------------ rules
    def _do(self, c: dict) -> None:
        w = self.w
        t = c.get("type")
        if t in ("all",):
            for x in c["of"]:
                if not scenario.cond(w, x):
                    self._do(x)
        elif t == "any":
            if not any(scenario.cond(w, x) for x in c["of"]):
                self._do(c["of"][0])
        elif t == "tracked":
            if w.faction_def.pipeline == "manual":
                return
            for a in scenario._truth_ids(w, c["ac"]):
                ac = w.aircraft[a]
                if ac.state == "airborne":
                    commands.run(w, "initiate", x=ac.x, y=ac.y, radius=15.0)
        elif t == "height":
            trk = _truth_track(w, c["ac"])
            if trk is not None:
                commands.run(w, "height", track=trk.id)
        elif t == "identity":
            trk = _truth_track(w, c["ac"], c.get("skin", False))
            if trk is not None and trk.identity not in c["is"]:
                ok, _ = commands.run(w, "identity", track=trk.id, ident=c["is"][0])
                if not ok and c["is"][0] == "hostile":
                    commands.run(w, "request", kind="declare_hostile", track=trk.id)
        elif t == "scrambled":
            trk = _truth_track(w, self.subject, True) or _truth_track(w, self.subject)
            sq = w.lesson.get("squadron") or next(iter(w.squadrons))
            commands.run(w, "scramble", squadron=sq, n=2, task=w.lesson.get("task", "id"),
                         track=trk.id if trk else "", geometry="stern")
        elif t == "flight":
            for f in list(w.flights.values()):
                if f.state in ("landed", "lost"):
                    continue
                if c.get("state") == "rtb" or c.get("task") == "rtb":
                    commands.run(w, "rtb", flight=f.id)
                if "weapons_free" in c:
                    commands.run(w, "weapons_free", flight=f.id, on=c["weapons_free"])
                if c.get("task") and c["task"] != "rtb":
                    commands.run(w, "task", flight=f.id, task=c["task"])
        elif t == "flights_home":
            for f in list(w.flights.values()):
                if f.state not in ("landed", "lost", "rtb"):
                    commands.run(w, "rtb", flight=f.id)
        elif t == "ui":
            commands.run(w, "ui_event", name=c["event"])
        elif t == "site":
            sid = c["site"]
            if c["attr"] == "channel":
                commands.run(w, "radar_channel", site=sid, channel=(w.radars[sid].channel + 1) % 3)
            elif c["attr"] == "mti":
                commands.run(w, "radar_mti", site=sid, on=bool(c.get("value", True)))
            elif c["attr"] == "assigned":
                trk = _truth_track(w, self.subject)
                if trk is not None:
                    commands.run(w, "sam_assign", site=sid, track=trk.id)
            elif c["attr"] == "hold":
                commands.run(w, "sam_hold", site=sid, on=bool(c.get("value", False)))
        elif t == "request":
            trk = _truth_track(w, self.subject)
            pending = any(r.kind == c["kind"] and not r.answered for r in w.hq.requests)
            if not pending:
                commands.run(w, "request", kind=c["kind"], track=trk.id if trk else "",
                             value=c.get("value", ""))
        elif t == "weapons_status":
            if not any(r.kind == "weapons_status" and not r.answered for r in w.hq.requests):
                commands.run(w, "request", kind="weapons_status", value=c["is"][0])
        elif t == "sim_killed":
            for site in w.sams.values():
                if site.assigned and not site.auto:
                    commands.run(w, "sam_auto", site=site.id, on=True)
        # time, vid, sam_fired, var, since ...: wait


def run_lesson(world: "World", limit_s: float | None = None) -> "World":
    """Play a training scenario with the model student until it ends."""
    st = Student(world)
    end = world.duration if limit_s is None else limit_s
    while not world.ended and world.t < end:
        st.act()
        world.step(1.0)
    return world
