"""Career campaign with a service record, and the Alert Duty generator screen."""
from __future__ import annotations

import json
import random

import pygame

from ..sim import procgen, scenario
from .scenes import W, H, R, Scene, OperationsScene, _desk_surface
from .theme import TEXT, theme_for

RANKS = {
    "US": [(0, "Second Lieutenant"), (60, "First Lieutenant"), (160, "Captain"), (300, "Major"),
           (460, "Lieutenant Colonel"), (640, "Colonel")],
    "USSR": [(0, "Lieutenant"), (60, "Senior Lieutenant"), (160, "Captain"), (300, "Major"),
             (460, "Lieutenant Colonel"), (640, "Colonel")],
}


def career_path(app):
    from .app import data_home
    return data_home() / "career.json"


def load_career(app) -> dict:
    try:
        return json.loads(career_path(app).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_career(app, data: dict) -> None:
    p = career_path(app)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def campaign_missions(faction: str) -> list[dict]:
    items = [s for s in scenario.list_scenarios() if s["faction"] == faction and s["kind"] in ("scenario", "training")
             and s.get("campaign", True)]
    items.sort(key=lambda s: (s["kind"] != "training", s["order"] if s["kind"] == "training" else 0, s["start"],
                              s["order"]))
    return items


def rank_for(faction: str, points: int) -> str:
    r = RANKS[faction][0][1]
    for need, name in RANKS[faction]:
        if points >= need:
            r = name
    return r


def record_result(app, world, rep) -> None:
    """Store the best result for a scenario in the career file."""
    data = load_career(app)
    fac = data.setdefault(world.faction, {"done": {}})
    prev = fac["done"].get(world.scenario_id)
    entry = {"score": int(rep["score"]), "total": int(rep["total"]), "grade": rep["grade"],
             "civil": int(rep["consequences"]["civil_losses"]), "fratricide": int(rep["consequences"]["fratricide"])}
    if prev is None or entry["score"] > prev.get("score", -999):
        fac["done"][world.scenario_id] = entry
    save_career(app, data)


class CampaignScene(Scene):
    def __init__(self, app, faction: str):
        super().__init__(app)
        self.faction = faction
        self.theme = theme_for(faction)
        self.desk = _desk_surface(faction, 51)
        self.missions = campaign_missions(faction)
        self.sel = None
        self.paper = None

    def _state(self):
        data = load_career(self.app).get(self.faction, {"done": {}})
        done = data.get("done", {})
        points = sum(max(0, v.get("score", 0)) for v in done.values())
        unlocked = set()
        prev_done = True
        for m in self.missions:
            if prev_done:
                unlocked.add(m["id"])
            prev_done = m["id"] in done
        return done, points, unlocked

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        gui.set_theme(th)
        screen.blit(self.desk, (0, 0))
        done, points, unlocked = self._state()
        ru = self.faction == "USSR"
        # ---- service record (personnel file)
        from .cinema import paper, stamp
        if self.paper is None:
            self.paper = paper((560, 800), (226, 220, 196) if not ru else (222, 218, 196), seed=9, age=1.2)
        screen.blit(self.paper, (40, 50))
        ink = (40, 34, 26)
        gui.label((70, 70), "PERSONAL FILE · PVO OFFICER" if ru else "SERVICE RECORD — AF FORM 11", 15, (140, 40, 30), "eng")
        gui.label((70, 100), "Air defense controller", 26, ink, "title")
        gui.label((70, 140), rank_for(self.faction, points), 20, ink, "eng")
        gui.label((70, 168), f"Career points: {points}", 14, (90, 80, 64), "eng_r")
        y = 210
        gui.label((70, y), "WATCHES STOOD", 14, (140, 40, 30), "eng")
        y += 24
        good = 0
        for m in self.missions:
            r = done.get(m["id"])
            if r is None:
                continue
            ok = r["score"] >= r["total"] * 0.55
            good += ok
            gui.label((70, y), f"{m['start'][:10]}  {m['title'][:26]:<26}", 14, ink, "cyr")
            gui.label((500, y), f"{r['score']:>3}/{r['total']}", 14, ink, "cyr", "right")
            if r.get("civil") or r.get("fratricide"):
                gui.label((520, y), "!", 14, (170, 30, 26), "eng")
            y += 22
        if not done:
            gui.label((70, y), "— none yet —", 14, (110, 100, 84), "eng_r")
        if good >= 3:
            st = stamp("COMMENDATION", (30, 60, 150), 24, -8,
                       "ARMY COMMANDER" if ru else "AIR DEFENSE COMMAND", seed=3)
            screen.blit(st, (320, 720))
        if any(v.get("civil") for v in done.values()):
            st = stamp("REPRIMAND", (170, 30, 26), 24, 6, "PARTY COMMITTEE" if ru else "BOARD OF INQUIRY",
                       seed=4)
            screen.blit(st, (80, 730))
        # ---- the campaign: one card per watch, in historical order
        gui.label((640, 40), "CAREER — THE WATCHES OF YOUR SERVICE", 28,
                  (226, 220, 200), "title")
        y = 96
        for m in self.missions:
            r = R(640, y, 900, 60)
            lock = m["id"] not in unlocked
            res = done.get(m["id"])
            gui.drawn["MISSION " + m["id"]] = r
            col = (206, 200, 180) if not lock else (110, 106, 96)
            if self.sel == m["id"]:
                col = (238, 232, 212)
            pygame.draw.rect(screen, (0, 0, 0), r.move(3, 4))
            pygame.draw.rect(screen, col, r)
            gui.label((r.x + 12, r.y + 4), m["start"][:10] + "  ·  " + m["subtitle"][:70], 13, (110, 60, 50), "eng")
            gui.label((r.x + 12, r.y + 24), ("[LOCKED]  " if lock else "") + m["title"], 22, (30, 26, 20), "title")
            if res:
                gui.label((r.right - 14, r.y + 22), f"{res['grade'].split('—')[-1].strip()}  {res['score']}/{res['total']}",
                          16, (30, 60, 150) if res["score"] >= res["total"] * 0.55 else (170, 30, 26), "eng", "right")
            if not lock and gui.clicked(r):
                self.sel = m["id"]
            y += 68
        if self.sel:
            if gui.button(R(1300, 820, 240, 44), "BRIEFING >>", color=th.lamp_green, size=14):
                self.app.campaign = self.faction
                self.app.start_briefing(self.sel)
        if gui.button(R(640, 820, 160, 40), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
            self.app.pop()


class AlertDutyScene(Scene):
    def __init__(self, app, faction: str):
        super().__init__(app)
        self.faction = faction
        self.theme = theme_for(faction)
        self.desk = _desk_surface(faction, 61)
        self.bases = procgen.bases_for(faction)
        self.base = self.bases[0]["id"] if self.bases else ""
        self.difficulty = 2
        self.seed = random.randint(1000, 999999)
        self.preview = None

    def _generate(self):
        sc = procgen.generate(self.base, self.seed, self.difficulty)
        self.preview = sc
        return sc

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        gui.set_theme(th)
        screen.blit(self.desk, (0, 0))
        ru = self.faction == "USSR"
        gui.label((60, 30), "COMBAT ALERT DUTY" if ru else "ALERT DUTY", 30, (226, 220, 200), "title")
        gui.label((62, 74), "A generated watch on a historical order of battle. Every seed is a different night.", 14,
                  (190, 184, 160), "eng_r")
        y = 120
        gui.label((62, y), "SECTOR AND ERA", 15, (210, 200, 176), "eng")
        y += 28
        for b in self.bases:
            r = R(60, y, 560, 46)
            sel = b["id"] == self.base
            gui.drawn["BASE " + b["id"]] = r
            pygame.draw.rect(screen, (0, 0, 0), r.move(3, 4))
            pygame.draw.rect(screen, (238, 232, 212) if sel else (206, 200, 180), r)
            gui.label((r.x + 12, r.y + 4), b["start"][:4] + "  " + b["theater"].replace("_", " ").upper(), 13,
                      (110, 60, 50), "eng")
            gui.label((r.x + 12, r.y + 21), f"forces of “{b['title']}”", 16, (30, 26, 20), "eng_r")
            if sel:
                pygame.draw.rect(screen, (200, 60, 40), r, 3)
            if gui.clicked(r):
                self.base = b["id"]
                self.preview = None
            y += 54
        y += 10
        gui.label((62, y), "DIFFICULTY", 15, (210, 200, 176), "eng")
        for i, lab in enumerate(("QUIET", "ROUTINE", "BUSY")):
            if gui.button(R(200 + i * 140, y - 6, 130, 34), lab, lit=self.difficulty == i + 1, size=12):
                self.difficulty = i + 1
                self.preview = None
        y += 50
        gui.label((62, y), f"WATCH No. {self.seed}", 15, (210, 200, 176), "eng")
        if gui.button(R(260, y - 6, 160, 34), "NEW SEED", size=12):
            self.seed = random.randint(1000, 999999)
            self.preview = None
        if self.preview is None and self.base:
            self._generate()
        if self.preview is not None:
            from .cinema import paper
            pr = R(680, 60, 860, 720)
            pg = paper(pr.size, (232, 226, 206), seed=self.seed % 97)
            screen.blit(pg, pr.topleft)
            gui.wrapped(R(pr.x + 36, pr.y + 30, pr.w - 72, pr.h - 260), self.preview["briefing"], 15, (40, 34, 26),
                        th.doc_font, line_h=21)
            yy = pr.bottom - 220
            gui.label((pr.x + 36, yy), "OBJECTIVES", 15, (140, 40, 30), "eng")
            yy += 24
            for o in self.preview["objective"][:8]:
                gui.label((pr.x + 40, yy), f"• {o['text']} ({o['points']})", 13, (40, 34, 26), "eng_r")
                yy += 19
            if gui.button(R(1300, 806, 240, 48), "BRIEFING >>", color=th.lamp_green, size=14):
                from .scenes import BriefingScene
                w = scenario.build_world_from(self.preview)
                meta = {"photo": self.preview.get("photo", []), "photo_caption": "File photograph"}
                self.app.campaign = None
                self.app.push(BriefingScene(self.app, world=w, meta=meta))
        if gui.button(R(60, 820, 160, 40), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
            self.app.pop()
