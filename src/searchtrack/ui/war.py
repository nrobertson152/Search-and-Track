"""The war room: a short war of battles fought by the same forces, night after night."""
from __future__ import annotations

import pygame

from ..sim import war
from .campaign import load_career, save_career
from .scenes import R, Scene, _desk_surface
from .theme import TEXT, theme_for

INK = (40, 34, 26)
RED_INK = (150, 34, 26)
BLUE_INK = (30, 60, 150)


def load_war(app, cid: str) -> dict:
    st = load_career(app).get("war", {}).get(cid)
    return st if isinstance(st, dict) and st.get("id") == cid else war.new_state(cid)


def save_war(app, state: dict) -> None:
    data = load_career(app)
    data.setdefault("war", {})[state["id"]] = state
    save_career(app, data)


class WarScene(Scene):
    def __init__(self, app, faction: str):
        super().__init__(app)
        self.faction = faction
        self.theme = theme_for(faction)
        self.desk = _desk_surface(faction, 71)
        self.wars = war.campaigns(faction)
        self.cid = self.wars[0]["id"] if self.wars else ""
        self.papers: dict = {}
        self.st = load_war(app, self.cid) if self.cid else {}
        self.meta = {s["id"]: s for s in _scenarios()}
        app.audio.play("tty")

    def _paper(self, key, size, seed):
        from .cinema import paper
        if key not in self.papers:
            tint = (232, 226, 206) if self.faction == "US" else (226, 222, 200)
            self.papers[key] = paper(size, tint, seed=seed, age=1.1)
        return self.papers[key]

    def draw(self, screen):
        gui = self.app.gui
        th = self.theme
        gui.set_theme(th)
        screen.blit(self.desk, (0, 0))
        ru = self.faction == "USSR"
        if not self.wars:
            gui.label((60, 60), "No war has been written for this side yet.", 20, (226, 220, 200), "eng")
            if gui.button(R(60, 820, 160, 40), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
                self.app.pop()
            return
        c = next(x for x in self.wars if x["id"] == self.cid)
        st = self.st
        cur = war.current(st)
        gui.label((60, 26), "THE WAR", 30, (226, 220, 200), "title")
        gui.label((62, 70), "Battles fought one after another by the same forces. What is lost stays lost.", 14,
                  (190, 184, 160), "eng_r")
        # ---- the war diary: one line per battle
        pr = R(50, 110, 700, 690)
        screen.blit(self._paper("diary", pr.size, 13), pr.topleft)
        x0 = pr.x + 34
        gui.label((x0, pr.y + 22), "WAR DIARY" if not ru else "COMBAT LOG", 15, RED_INK, "eng")
        gui.label((x0, pr.y + 46), c["title"].upper(), 28, INK, "title")
        gui.wrapped(R(x0, pr.y + 94, pr.w - 68, 120), c.get("summary", ""), 14, (70, 60, 46), "eng_r", line_h=19)
        y = pr.y + 230
        for i, m in enumerate(c.get("mission", [])):
            done = i < len(st["results"])
            now = cur is not None and i == st["mission"]
            r = R(x0 - 8, y, pr.w - 52, 70)
            if now:
                pygame.draw.rect(screen, (250, 244, 222), r)
                pygame.draw.rect(screen, (200, 60, 40), r, 2)
            gui.label((x0, y + 8), m.get("title", m["scenario"]), 20, INK if (done or now) else (130, 122, 104),
                      "title")
            if done:
                res = st["results"][i]
                col = BLUE_INK if res["outcome"] == "VICTORY" else RED_INK if res["outcome"] == "DEFEAT" else INK
                gui.label((x0, y + 40), f"{res['outcome']}  ·  {res['score']}/{res['total']}", 15, col, "eng")
            elif now:
                gui.label((x0, y + 40), "NEXT — the forces below are what you will fight it with", 13,
                          (120, 60, 40), "eng_r")
            else:
                gui.label((x0, y + 40), "not yet", 13, (130, 122, 104), "eng_r")
            y += 82
        if st.get("over"):
            from .cinema import stamp
            oc = st.get("outcome") or war.war_outcome(st) or "OVER"
            col = (30, 60, 150) if oc == "VICTORY" else (170, 30, 26)
            img = stamp(oc, col, 34, -7, "THE WAR" if not ru else "THE CAMPAIGN", seed=5)
            screen.blit(img, (pr.right - img.get_width() - 30, pr.bottom - img.get_height() - 30))
            if st.get("note"):
                gui.wrapped(R(x0, pr.bottom - 150, pr.w - 330, 120), st["note"], 14, RED_INK, "eng_r", line_h=19)
        # ---- the order of battle as it stands
        ob = R(800, 110, 750, 470)
        screen.blit(self._paper("oob", ob.size, 17), ob.topleft)
        ox = ob.x + 30
        gui.label((ox, ob.y + 22), "ORDER OF BATTLE — WHAT IS LEFT", 15, RED_INK, "eng")
        yy = ob.y + 54
        for line in war.summary(st, self.faction):
            for ln in TEXT.wrap(line, ob.w - 60, 14, "eng_r"):
                gui.label((ox, yy), ln, 14, INK, "eng_r")
                yy += 20
            yy += 8
            if yy > ob.bottom - 30:
                break
        # ---- the next battle
        if cur is not None:
            meta = self.meta.get(cur["scenario"], {})
            nx = R(800, 600, 750, 180)
            pygame.draw.rect(screen, (0, 0, 0), nx.move(3, 4))
            pygame.draw.rect(screen, (214, 208, 188), nx)
            gui.label((nx.x + 20, nx.y + 12), meta.get("subtitle", "")[:80], 13, (110, 60, 50), "eng")
            gui.label((nx.x + 20, nx.y + 32), meta.get("title", cur["scenario"]), 24, INK, "title")
            gui.wrapped(R(nx.x + 20, nx.y + 70, nx.w - 40, 100), meta.get("summary", ""), 13, (60, 52, 40), "eng_r",
                        line_h=18)
            if gui.button(R(1310, 806, 240, 48), "BRIEFING >>", color=th.lamp_green, size=14):
                self._start()
        if gui.button(R(800, 806, 200, 44), "NEW WAR" if st["results"] else "START OVER", size=13,
                      tip="Begin the war again with full forces"):
            self.st = war.new_state(self.cid)
            save_war(self.app, self.st)
        if gui.button(R(60, 820, 160, 40), "BACK", size=13) or any(e.key == pygame.K_ESCAPE for e in gui.keys):
            self.app.pop()

    def _start(self) -> None:
        from .scenes import BriefingScene
        st = self.st
        w = war.build_world(st)
        self.app.campaign = None
        self.app.war = st["id"]
        self.app.push(BriefingScene(self.app, world=w))


def _scenarios():
    from ..sim import scenario
    return scenario.list_scenarios()


def book_battle(app, world) -> None:
    """A battle of the war has ended: book it into the war's order of battle."""
    cid = getattr(app, "war", None)
    if not cid:
        return
    st = load_war(app, cid)
    if war.current(st) is None:
        return
    war.advance(st, world)
    save_war(app, st)
