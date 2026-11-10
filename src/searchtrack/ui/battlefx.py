"""The battle on the display: tactical symbols, ships, weapons in flight, explosions, the
phase banners and decision cards, the follow camera and the commander's battle console.

Everything drawn from the battle is 2-D and drawn on top of the ordinary situation display
(SAGE scope or PVO plotting board), in the display's own style. What the player sees is what
the side knows: our ships and aircraft from data link, the enemy from our tracks and our
surface picture. The umpire view (spectator mode) shows the truth of both sides.
"""
from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Optional

import pygame
from pygame import Rect

from ..sim import tracking
from ..sim.battle import staff as bstaff
from .theme import TEXT

if TYPE_CHECKING:
    from .mapview import MapView

R = Rect

IDC = {"friend": (110, 196, 255), "hostile": (255, 84, 62), "suspect": (255, 150, 60), "unknown": (255, 214, 90),
       "pending": (226, 232, 232), "faker": (200, 160, 255), "neutral": (120, 230, 130)}
IDC_PVO = {"friend": (255, 95, 80), "hostile": (110, 180, 255), "suspect": (150, 200, 255),
           "unknown": (240, 210, 100), "pending": (235, 235, 225), "faker": (200, 200, 200),
           "neutral": (150, 230, 150)}
CLASS_LABEL = {"strike": "BOMBER", "bomber": "BOMBER", "interceptor": "FIGHTER", "fighter": "FIGHTER",
               "recon": "RECON", "ew": "JAMMER", "awacs": "AEW", "missile": "VAMPIRE", "tanker": "TANKER",
               "unknown": "", "debris": "DEBRIS", "patrol": "PATROL", "airliner": "CIVIL", "transport": "CIVIL"}
CLASS_LETTER = {"strike": "B", "bomber": "B", "interceptor": "F", "fighter": "F", "recon": "R", "ew": "J",
                "awacs": "W", "tanker": "K", "patrol": "P", "missile": "", "unknown": "", "debris": ""}


def _fade(c, f: float):
    f = max(0.0, min(1.0, f))
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


def _mix(a, b, f: float):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _dash(screen, col, a, b, dash: int = 6, width: int = 1) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = max(1, int(math.hypot(dx, dy) / dash))
    for k in range(0, n, 2):
        p0 = (a[0] + dx * k / n, a[1] + dy * k / n)
        p1 = (a[0] + dx * min(n, k + 1) / n, a[1] + dy * min(n, k + 1) / n)
        pygame.draw.line(screen, col, p0, p1, width)


def _dash_circle(screen, col, c, r: int, seg: int = 48) -> None:
    if r < 4:
        return
    for k in range(0, seg, 2):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        pygame.draw.line(screen, col, (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0)),
                         (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1)), 1)


# ---------------------------------------------------------------- symbols (NATO-style frames)

def air_frame(screen, x: int, y: int, ident: str, col, s: int = 9, width: int = 2) -> None:
    """Air track frames: friend dome, hostile tent, unknown clover, neutral box, all open below."""
    if ident == "friend":
        pygame.draw.arc(screen, col, (x - s, y - s, 2 * s, 2 * s), 0.0, math.pi, width)
        pygame.draw.line(screen, col, (x - s, y), (x - s, y + 2), width)
        pygame.draw.line(screen, col, (x + s - 1, y), (x + s - 1, y + 2), width)
    elif ident in ("hostile", "suspect", "faker"):
        pts = [(x - s, y + 3), (x, y - s - 1), (x + s, y + 3)]
        pygame.draw.lines(screen, col, False, pts, width + (0 if ident == "hostile" else -1))
    elif ident == "neutral":
        pygame.draw.lines(screen, col, False, [(x - s, y + 3), (x - s, y - s), (x + s, y - s), (x + s, y + 3)], width)
    else:
        h = s // 2 + 1
        for cx, cy, a0, a1 in ((x - h, y - 1, math.pi * 0.5, math.pi * 1.05), (x, y - h, 0.0, math.pi),
                               (x + h, y - 1, -0.05, math.pi * 0.5)):
            pygame.draw.arc(screen, col, (cx - h, cy - h, 2 * h, 2 * h), a0, a1, max(1, width - 1))


def surface_frame(screen, x: int, y: int, ident: str, col, s: int = 10, width: int = 2, fill=None) -> None:
    if ident == "friend":
        if fill is not None:
            pygame.draw.circle(screen, fill, (x, y), s)
        pygame.draw.circle(screen, col, (x, y), s, width)
    elif ident in ("hostile", "suspect"):
        pts = [(x, y - s - 2), (x + s + 2, y), (x, y + s + 2), (x - s - 2, y)]
        if fill is not None:
            pygame.draw.polygon(screen, fill, pts)
        pygame.draw.polygon(screen, col, pts, width)
    else:
        pygame.draw.rect(screen, col, (x - s, y - s, 2 * s, 2 * s), width)


def ship_glyph(screen, x: int, y: int, hdg: float, col, size: float = 6.0) -> None:
    a = math.radians(hdg)
    fx, fy = math.sin(a), -math.cos(a)
    px, py = -fy, fx
    pts = [(x + fx * size, y + fy * size), (x + px * size * 0.35 - fx * size * 0.7, y + py * size * 0.35 - fy * size * 0.7),
           (x - px * size * 0.35 - fx * size * 0.7, y - py * size * 0.35 - fy * size * 0.7)]
    pygame.draw.polygon(screen, col, pts)


def vampire_glyph(screen, x: int, y: int, vx: float, vy: float, col, t: float) -> None:
    a = math.atan2(vx, vy)
    fx, fy = math.sin(a), -math.cos(a)
    px, py = -fy, fx
    pts = [(x + fx * 8, y + fy * 8), (x - fx * 5 + px * 4, y - fy * 5 + py * 4), (x - fx * 2, y - fy * 2),
           (x - fx * 5 - px * 4, y - fy * 5 - py * 4)]
    pygame.draw.polygon(screen, col, pts)
    if int(t * 4) % 2:
        pygame.draw.circle(screen, col, (x, y), 11, 1)


# ---------------------------------------------------------------- the overlay

class BattleFX:
    def __init__(self, scene):
        self.scene = scene
        self.world = scene.world
        self.seen = 0
        self.fx: list[dict] = []
        self.trails: dict[str, deque] = {}
        self.banner: Optional[tuple[str, str, float]] = None
        self.follow = ""
        self.umpire = False
        self.flash = 0.0
        self.slow_prev: Optional[int] = None
        self.slow_until = 0.0
        self.clock = 0.0
        self.log: deque = deque(maxlen=200)          # what the commander sees (no umpire-only events)
        self.pvo = scene.world.faction == "USSR"
        b = scene.world.battle
        for i, ev in enumerate(b.events):             # a battle in progress (a loaded game): log it, replay
            if ev[0] >= scene.world.t - 8.0:          # only the last few seconds' explosions
                self.seen = i
                break
            if ev[7] >= 0:
                self.log.append(ev)
        else:
            self.seen = len(b.events)
        if b.view:
            mv = scene.map
            mv.center_on(b.view[0], b.view[1])
            mv.scale = mv.rect.w / max(b.view[2], 50.0)
            mv._base_key = None

    # ------------------------------------------------------------ per frame
    def update(self, dt: float) -> None:
        self.clock += dt
        w = self.world
        b = w.battle
        evs = b.events[self.seen:]
        self.seen = len(b.events)
        for ev in evs:
            self._on_event(ev)
        self.fx = [f for f in self.fx if self.clock - f["t0"] < f["dur"]]
        self.flash = max(0.0, self.flash - dt * 0.8)
        for m in w.missiles.values():
            if m.state == "flying" and w.t >= m.t_launch:
                tr = self.trails.setdefault(m.id, deque(maxlen=14))
                if not tr or math.hypot(tr[-1][0] - m.x, tr[-1][1] - m.y) > 0.4:
                    tr.append((m.x, m.y))
        for a in w.aircraft.values():
            if a.aim and a.state == "airborne":
                tr = self.trails.setdefault(a.id, deque(maxlen=18))
                if not tr or math.hypot(tr[-1][0] - a.x, tr[-1][1] - a.y) > 0.8:
                    tr.append((a.x, a.y))
        if len(self.trails) > 400:
            live = {m.id for m in w.missiles.values() if m.state == "flying"} | \
                   {a.id for a in w.aircraft.values() if a.aim and a.state == "airborne"}
            self.trails = {k: v for k, v in self.trails.items() if k in live}
        if self.follow:
            pos = self.unit_pos(self.follow)
            if pos is None:
                self.follow = ""
            else:
                self.scene.map.center_on(*pos)
        self._auto_slow()

    def _visible(self, ev) -> bool:
        return ev[7] >= 0 or self.umpire or self.world.battle.spectator

    def _on_event(self, ev) -> None:
        t, kind, text, ref, x, y, side, level = ev
        w = self.world
        if level >= 0:
            self.log.append(ev)
        if not self._visible(ev):
            return
        audio = self.scene.audio
        own = side == w.own_side
        if kind == "phase":
            ph = w.battle.phases[w.battle.phase] if 0 <= w.battle.phase < len(w.battle.phases) else {}
            self.banner = (text, ph.get("text", "")[:140], self.clock)
            audio.play("bell")
        elif kind == "decision" and not w.battle.spectator:
            audio.play("alert")
        elif kind == "vampire" and level >= 3:
            self.flash = 1.0
            audio.play("klaxon", 0.8)
        elif kind == "vampire":
            self.flash = max(self.flash, 0.5)
            audio.play("beep")
        if x is None or y is None:
            return
        if kind == "kill":
            self.fx.append(dict(kind="boom", x=x, y=y, t0=self.clock, dur=2.2, big=False, own=own,
                                label="SPLASH" if not own else text.split(" (")[0].replace("SPLASH — ", "")))
            audio.play("boom", 0.5 if not own else 0.7)
        elif kind == "vampire_kill":
            self.fx.append(dict(kind="pop", x=x, y=y, t0=self.clock, dur=1.0))
            audio.play("pop", 0.5)
        elif kind == "ship_hit":
            self.fx.append(dict(kind="boom", x=x, y=y, t0=self.clock, dur=3.2, big=True, own=own, label="HIT"))
            self.flash = max(self.flash, 0.8 if own else 0.0)
            audio.play("boom", 1.0)
        elif kind == "sunk":
            self.fx.append(dict(kind="ring", x=x, y=y, t0=self.clock, dur=4.0, label="SUNK", own=own))
        elif kind == "ciws":
            self.fx.append(dict(kind="tracer", x=x, y=y, t0=self.clock, dur=0.9, seed=int(t * 7) % 97))
            audio.play("buzz", 0.4)
        elif kind == "chaff":
            self.fx.append(dict(kind="chaff", x=x, y=y, t0=self.clock, dur=6.0, seed=int(t * 13) % 89))
        elif kind in ("aam", "sam_launch", "asm_launch") and (own or self.umpire):
            self.fx.append(dict(kind="flash", x=x, y=y, t0=self.clock, dur=0.6))
            if own:
                audio.play("launch", 0.35)
        elif kind == "damaged":
            self.fx.append(dict(kind="pop", x=x, y=y, t0=self.clock, dur=1.2))

    def _auto_slow(self) -> None:
        sc = self.scene
        if not sc.app.settings.get("auto_slow", True) or sc.speed_i == 0:
            return
        hot = any(f["kind"] in ("boom",) and self.clock - f["t0"] < 0.1 for f in self.fx) or self.flash >= 0.99
        if hot:
            self.slow_until = self.clock + 18.0
            if sc.advancing:
                sc.advancing = False
            if sc.speed_i > 2:
                self.slow_prev = sc.speed_i if self.slow_prev is None else self.slow_prev
                sc.speed_i = 2
        elif self.slow_prev is not None and self.clock > self.slow_until:
            sc.speed_i = self.slow_prev
            self.slow_prev = None

    # ------------------------------------------------------------ unit lookup
    def unit_pos(self, uid: str) -> Optional[tuple[float, float]]:
        w = self.world
        if uid in w.ships:
            s = w.ships[uid]
            return (s.x, s.y) if s.state != "sunk" else None
        g = w.battle.groups.get(uid)
        if g is not None:
            for mid in g.members:
                a = w.aircraft.get(mid)
                if a is not None and a.state == "airborne" and a.group == g.id:
                    return a.x, a.y
            return None
        fl = w.flights.get(uid)
        if fl is not None:
            for mid in fl.members:
                a = w.aircraft.get(mid)
                if a is not None and a.state == "airborne":
                    return a.x, a.y
            return None
        a = w.aircraft.get(uid)
        if a is not None and a.state == "airborne":
            return a.x, a.y
        return None

    def pick(self, mv: "MapView", sx: int, sy: int) -> Optional[tuple[str, str]]:
        w = self.world
        best, bd = None, 13.0
        for s in w.ships.values():
            if s.side != w.own_side and not self.umpire:
                continue
            px, py = mv.w2s(s.x, s.y)
            d = math.hypot(px - sx, py - sy)
            if d < bd:
                best, bd = ("ship", s.id), d
        if not self.umpire:
            for sid, c in w.battle.surface.get(w.own_side, {}).items():
                px, py = mv.w2s(c.x, c.y)
                d = math.hypot(px - sx, py - sy)
                if d < bd:
                    best, bd = ("ship", sid), d
        for g in w.battle.groups.values():
            if g.side != w.own_side and not self.umpire:
                continue
            pos = self.unit_pos(g.id)
            if pos is None:
                continue
            px, py = mv.w2s(*pos)
            d = math.hypot(px - sx, py - sy)
            if d < bd:
                best, bd = ("group", g.id), d
        return best

    # ------------------------------------------------------------ the map
    def colors(self) -> dict:
        return IDC_PVO if self.pvo else IDC

    def draw_map(self, screen, mv: "MapView", sel: dict) -> None:
        w = self.world
        b = w.battle
        C = self.colors()
        t = self.clock
        board = mv.theme.map_style == "board"
        font = "cyr" if board else "crt"
        # ---- enemy ships we know about, with their missile threat rings
        pic = b.surface.get(w.own_side, {})
        for sid, c in pic.items():
            sh = w.ships.get(sid)
            if sh is None or (self.umpire and sh.side != w.own_side):
                continue
            st = w.catalog.ships[sh.type_id]
            age = w.t - c.t
            x, y = c.x + c.vx * age, c.y + c.vy * age
            px, py = mv.w2s(x, y)
            col = C["hostile"]
            reach = max((w.catalog.sams[m["type"]].range_max_km for m in st.sams), default=0.0)
            if reach:
                _dash_circle(screen, _fade(col, 0.45), (px, py), int(reach * mv.scale))
            if c.err_km > 4.0:
                _dash_circle(screen, _fade(col, 0.3), (px, py), int(c.err_km * mv.scale), 24)
            surface_frame(screen, px, py, "hostile", _fade(col, 0.6 if age > 300 else 1.0), 8, 2)
            ship_glyph(screen, px, py, sh.hdg, col, 5)
            lab = (st.nato_name or st.name) + (" ?" if c.passive else "") + ("" if age < 120 else f" {age / 60:.0f}m")
            screen.blit(TEXT.render(lab, 11, col, font), (px + 13, py - 7))
        # ---- ships (ours always; theirs in the umpire view)
        for sh in w.ships.values():
            if sh.side != w.own_side and not self.umpire:
                continue
            self._ship(screen, mv, sh, sel.get("ship") == sh.id, font)
        # ---- weapons in flight with smoke trails
        for m in w.missiles.values():
            if m.state != "flying" or w.t < m.t_launch:
                continue
            if m.side != w.own_side and not self.umpire:
                continue
            tr = self.trails.get(m.id)
            hot = (255, 250, 220) if m.side == w.own_side else (255, 120, 90)
            if tr and len(tr) > 1:
                pts = [mv.w2s(*p) for p in tr] + [mv.w2s(m.x, m.y)]
                for i in range(len(pts) - 1):
                    f = (i + 1) / len(pts)
                    pygame.draw.line(screen, _fade((200, 200, 190), 0.25 + 0.5 * f), pts[i], pts[i + 1], 1)
            sx, sy = mv.w2s(m.x, m.y)
            pygame.draw.circle(screen, hot, (sx, sy), 2)
        # ---- tracks (our picture), aggregated into raids when zoomed out
        self._tracks(screen, mv, sel, C, font, board)
        # ---- our aircraft (data link)
        for fl in w.flights.values():
            self._flight(screen, mv, fl, sel.get("flight") == fl.id, C, font)
        for g in b.groups.values():
            if g.side == w.own_side or self.umpire:
                self._group(screen, mv, g, sel.get("group") == g.id, C, font)
        # ---- SAM lock lines from our fire channels
        for s in w.sams.values():
            if s.side != w.own_side or not s.lock or s.state not in ("locked", "engaging", "assess"):
                continue
            tgt = w.aircraft.get(s.lock)
            if tgt is None or tgt.state != "airborne":
                continue
            a, c = mv.w2s(s.x, s.y), mv.w2s(tgt.x, tgt.y)
            _dash(screen, _fade(C["hostile"], 0.55 if s.state != "engaging" else 0.9), a, c, 5)
        self._effects(screen, mv)

    def _ship(self, screen, mv, sh, selected: bool, font: str) -> None:
        w = self.world
        C = self.colors()
        sx, sy = mv.w2s(sh.x, sh.y)
        own = sh.side == w.own_side
        base = C["friend"] if own else C["hostile"]
        if sh.state == "sunk":
            col = (90, 96, 100)
            pygame.draw.line(screen, col, (sx - 7, sy - 7), (sx + 7, sy + 7), 2)
            pygame.draw.line(screen, col, (sx - 7, sy + 7), (sx + 7, sy - 7), 2)
            screen.blit(TEXT.render(sh.name, 10, col, font), (sx + 12, sy - 6))
            return
        col = {"afloat": base, "damaged": (255, 190, 70), "crippled": (255, 90, 60)}.get(sh.state, base)
        st = w.catalog.ships[sh.type_id]
        big = st.kind in ("carrier", "cruiser")
        s = 10 if big else 8
        if sh.state in ("damaged", "crippled"):
            fl = 0.6 + 0.4 * math.sin(self.clock * 9.0 + hash(sh.id) % 7)
            glow = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 120, 30, int(70 * fl)), (20, 20), 16)
            pygame.draw.circle(glow, (255, 200, 80, int(110 * fl)), (20, 20), 7)
            screen.blit(glow, (sx - 20, sy - 20))
            for k in range(3):                        # smoke drifting downwind
                ph = (self.clock * 0.35 + k / 3.0) % 1.0
                wx, wy = math.sin(math.radians(w.weather.wind_from + 180)), -math.cos(math.radians(w.weather.wind_from + 180))
                pygame.draw.circle(screen, _fade((120, 120, 115), 0.6 * (1 - ph)),
                                   (int(sx + wx * 24 * ph), int(sy + wy * 24 * ph)), int(3 + 6 * ph), 1)
        surface_frame(screen, sx, sy, "friend" if own else "hostile", col, s, 2,
                      fill=_fade(col, 0.18) if not own or True else None)
        ship_glyph(screen, sx, sy, sh.hdg, col, s * 0.7)
        if st.kind == "carrier":
            pygame.draw.line(screen, col, (sx - s + 3, sy + s + 3), (sx + s - 3, sy + s + 3), 2)
        if selected:
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), s + 6, 1)
        if mv.scale > 0.35 or big or selected:
            lab = sh.name.replace("USS ", "")
            screen.blit(TEXT.render(lab, 11, col, font), (sx + s + 4, sy - 7))
            hp = max(0.0, sh.hp / sh.max_hp)
            pygame.draw.rect(screen, (20, 24, 26), (sx + s + 4, sy + 6, 30, 3))
            pygame.draw.rect(screen, col, (sx + s + 4, sy + 6, int(30 * hp), 3))
        if selected:
            for m in st.sams[:1]:
                rng = w.catalog.sams[m["type"]].range_max_km
                _dash_circle(screen, _fade(col, 0.5), (sx, sy), int(rng * mv.scale))

    def _tracks(self, screen, mv, sel, C, font, board) -> None:
        w = self.world
        items = []
        for tk in w.tracks.values():
            if tk.lost and w.t - tk.t_lost > 30.0:
                continue
            ident = tk.identity
            if ident == "friend" and bstaff.own_correlation(w, tk, bstaff._controlled(w)) is not None:
                continue                                  # our own aircraft: drawn from data link
            cls = bstaff.classify(w, tk)
            if cls == "debris" and tk.id != sel.get("track"):
                continue
            px, py = tracking.predicted(tk, w.t)
            sx, sy = mv.w2s(px, py)
            items.append([tk, cls, sx, sy, ident])
        # aggregate hostile raids when they crowd together on the screen
        groups: list[list] = []
        for it in sorted(items, key=lambda i: i[0].id):
            tk, cls, sx, sy, ident = it
            if ident in ("hostile", "suspect") and cls not in ("missile",) and tk.id != sel.get("track"):
                for gp in groups:
                    if gp[0][1] == cls and gp[0][4] == ident and math.hypot(gp[0][2] - sx, gp[0][3] - sy) < 16:
                        gp.append(it)
                        break
                else:
                    groups.append([it])
            else:
                groups.append([it])
        for gp in groups:
            tk, cls, sx, sy, ident = gp[0]
            self._track(screen, mv, tk, cls, ident, sx, sy, len(gp), tk.id == sel.get("track"), C, font,
                        tk.id in w.battle.priority)

    def _track(self, screen, mv, tk, cls, ident, sx, sy, n, selected, C, font, prio) -> None:
        w = self.world
        col = C.get(ident, C["pending"])
        if tk.lost:
            col = _fade(col, 0.5)
        lead_s = 90.0 if cls != "missile" else 30.0
        ex, ey = mv.w2s(tk.x + tk.vx * (w.t - tk.t_update + lead_s), tk.y + tk.vy * (w.t - tk.t_update + lead_s))
        pygame.draw.line(screen, _fade(col, 0.8), (sx, sy), (ex, ey), 1)
        if cls == "missile" and ident in ("hostile", "suspect"):
            tr = self.trails.get(tracking.truth_of(tk) or "")
            if tr and len(tr) > 1:
                pts = [mv.w2s(*p) for p in tr]
                for i in range(len(pts) - 1):
                    pygame.draw.line(screen, _fade(col, 0.2 + 0.5 * i / len(pts)), pts[i], pts[i + 1], 2)
            vampire_glyph(screen, sx, sy, tk.vx, tk.vy, col, self.clock)
            if mv.scale > 0.45 or selected:
                screen.blit(TEXT.render("VAMPIRE", 10, col, font), (sx + 10, sy - 14))
        else:
            air_frame(screen, sx, sy, ident, col, 9, 2)
            letter = CLASS_LETTER.get(cls, "")
            if letter:
                img = TEXT.render(letter, 10, col, "eng")
                screen.blit(img, (sx - img.get_width() // 2, sy - 9))
            elif tk.jammer:
                for k in range(3):
                    pygame.draw.line(screen, col, (sx - 4 + k * 4, sy - 7), (sx - 6 + k * 4, sy - 1), 1)
            lab = tk.id + (f" ×{n}" if n > 1 else (f" ×{tk.size}" if tk.size > 1 else ""))
            sub = CLASS_LABEL.get(cls, "")
            if ident == "friend" and not sub:
                sub = "FRIEND"
            show = selected or prio or n > 1 or mv.scale > 0.5 or cls in ("strike", "recon", "ew", "awacs")
            if show:
                screen.blit(TEXT.render(lab, 11, col, font), (sx + 11, sy - 16))
                if sub:
                    screen.blit(TEXT.render(sub, 9, _fade(col, 0.85), "eng"), (sx + 11, sy - 3))
        if prio:
            r = 15 + int(2 * math.sin(self.clock * 5))
            pygame.draw.circle(screen, (255, 240, 120), (sx, sy), r, 1)
        if selected:
            pygame.draw.rect(screen, (255, 255, 255), (sx - 13, sy - 13, 26, 26), 1)

    def _flight(self, screen, mv, fl, selected, C, font) -> None:
        w = self.world
        if fl.state in ("landed", "lost"):
            return
        col = C["friend"] if not selected else (255, 255, 255)
        if fl.state == "scrambling":
            b = w.airbases.get(fl.base_id)
            if b is None:
                return
            sx, sy = mv.w2s(b.x, b.y)
            screen.blit(TEXT.render(f"{fl.callsign} ↑{max(0, fl.t_airborne - w.t) / 60:.0f}m", 10, _fade(col, 0.85),
                                    font), (sx + 14, sy + 8))
            return
        a = w.aircraft.get(fl.members[0]) if fl.members else None
        if a is None or a.state != "airborne":
            return
        sx, sy = mv.w2s(a.x, a.y)
        hx, hy = math.sin(math.radians(a.hdg)), -math.cos(math.radians(a.hdg))
        pygame.draw.line(screen, _fade(col, 0.7), (sx, sy), (sx + hx * 16, sy + hy * 16), 1)
        air_frame(screen, sx, sy, "friend", col, 8, 2)
        img = TEXT.render("F", 10, col, "eng")
        screen.blit(img, (sx - img.get_width() // 2, sy - 8))
        if fl.target and fl.state in ("vector", "contact", "judy", "attack"):
            trk = w.tracks.get(fl.target)
            if trk is not None:
                tx, ty = mv.w2s(*tracking.predicted(trk, w.t))
                _dash(screen, _fade(col, 0.45), (sx, sy), (tx, ty), 7)
        if fl.state == "cap" and fl.cap_x is not None and mv.scale > 0.3:
            cx, cy = mv.w2s(fl.cap_x, fl.cap_y)
            _dash_circle(screen, _fade(col, 0.35), (cx, cy), int(20 * mv.scale), 32)
        if mv.scale > 0.3 or selected:
            fuel = a.fuel / max(w.catalog.aircraft[a.type_id].fuel_kg, 1) * 100
            tag = {"vector": "VEC", "contact": "CON", "judy": "JUDY", "attack": "ATK", "rtb": "RTB", "hold": "HOLD",
                   "cap": "CAP", "airborne": "AIR"}.get(fl.state, fl.state.upper())
            n = sum(1 for m in fl.members if m in w.aircraft and w.aircraft[m].state == "airborne")
            screen.blit(TEXT.render(f"{fl.callsign}{' ×' + str(n) if n > 1 else ''}", 11, col, font), (sx + 10, sy - 15))
            screen.blit(TEXT.render(f"{tag} F{fuel:.0f}%", 9, _fade(col, 0.8), font), (sx + 10, sy - 2))
        if self.follow == fl.id:
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 16, 1)

    def _group(self, screen, mv, g, selected, C, font) -> None:
        w = self.world
        pos = self.unit_pos(g.id)
        if pos is None:
            return
        own = g.side == w.own_side
        col = (C["friend"] if own else C["hostile"]) if not selected else (255, 255, 255)
        sx, sy = mv.w2s(*pos)
        lead = w.aircraft.get(g.members[0])
        hdg = lead.hdg if lead is not None else 0.0
        hx, hy = math.sin(math.radians(hdg)), -math.cos(math.radians(hdg))
        pygame.draw.line(screen, _fade(col, 0.7), (sx, sy), (sx + hx * 16, sy + hy * 16), 1)
        air_frame(screen, sx, sy, "friend" if own else "hostile", col, 9, 2)
        letter = CLASS_LETTER.get(g.role if g.role != "escort" else "fighter",
                                  {"sweep": "F", "intercept": "F", "cap": "F"}.get(g.role, ""))
        if g.role == "awacs":
            pygame.draw.ellipse(screen, col, (sx - 5, sy - 7, 10, 5), 1)
        elif letter:
            img = TEXT.render(letter, 10, col, "eng")
            screen.blit(img, (sx - img.get_width() // 2, sy - 9))
        if g.station and g.state == "station" and g.role in ("awacs", "ew") and mv.scale > 0.25:
            cx, cy = mv.w2s(g.station[0], g.station[1])
            _dash_circle(screen, _fade(col, 0.3), (cx, cy), int(g.station[3] * mv.scale), 32)
        n = sum(1 for m in g.members if m in w.aircraft and w.aircraft[m].state == "airborne"
                and w.aircraft[m].group == g.id)
        screen.blit(TEXT.render(f"{g.callsign}{' ×' + str(n) if n > 1 else ''}", 11, col, font), (sx + 11, sy - 15))
        tag = {"station": "ON STA", "outbound": "OUTBD", "egress": "EGRESS", "attack": "ATTACK"}.get(g.state,
                                                                                                    g.state.upper())
        if lead is not None and lead.jamming:
            tag += " · JAM"
        screen.blit(TEXT.render(tag, 9, _fade(col, 0.8), font), (sx + 11, sy - 2))
        if self.follow == g.id:
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 17, 1)

    def _effects(self, screen, mv) -> None:
        t = self.clock
        for f in self.fx:
            age = (t - f["t0"]) / f["dur"]
            sx, sy = mv.w2s(f["x"], f["y"])
            k = f["kind"]
            if k == "boom":
                big = f.get("big")
                rmax = 46 if big else 26
                flash = max(0.0, 1.0 - age * 4.0)
                if flash > 0:
                    glow = pygame.Surface((rmax * 2 + 4, rmax * 2 + 4), pygame.SRCALPHA)
                    c = rmax + 2
                    pygame.draw.circle(glow, (255, 170, 60, int(140 * flash)), (c, c), int(rmax * (0.4 + age * 1.5)))
                    pygame.draw.circle(glow, (255, 250, 220, int(230 * flash)), (c, c), int(rmax * 0.25 + 4))
                    screen.blit(glow, (sx - c, sy - c), special_flags=pygame.BLEND_RGB_ADD)
                ring = int(rmax * (0.3 + age * 1.4))
                pygame.draw.circle(screen, _fade((255, 200, 120), 1.0 - age), (sx, sy), ring, 1)
                for i in range(10 if big else 7):                         # sparks
                    a = i * 2.4 + f["x"] * 3.1
                    d = rmax * age * (0.7 + 0.5 * ((i * 37) % 10) / 10.0)
                    pygame.draw.circle(screen, _fade((255, 220, 140), 1.0 - age),
                                       (int(sx + math.cos(a) * d), int(sy + math.sin(a) * d)), 1)
                if f.get("label"):
                    col = (255, 236, 160) if not f.get("own") else (255, 110, 90)
                    img = TEXT.render(f["label"], 13 if big else 11, _fade(col, 1.0 - age * 0.8), "eng")
                    screen.blit(img, (sx - img.get_width() // 2, sy - 30 - int(age * 18)))
            elif k == "pop":
                r = int(4 + 12 * age)
                pygame.draw.circle(screen, _fade((255, 255, 230), 1.0 - age), (sx, sy), r, 1)
                pygame.draw.circle(screen, _fade((255, 240, 200), 1.0 - age), (sx, sy), 2)
            elif k == "ring":
                r = int(10 + 50 * age)
                col = (150, 210, 255) if not f.get("own") else (255, 120, 90)
                pygame.draw.circle(screen, _fade(col, 1.0 - age), (sx, sy), r, 2)
                img = TEXT.render(f.get("label", ""), 14, _fade(col, 1.0 - age * 0.7), "eng")
                screen.blit(img, (sx - img.get_width() // 2, sy + 16))
            elif k == "tracer":
                for i in range(6):
                    a = (f["seed"] * 0.37 + i * 0.9) % (2 * math.pi)
                    d0, d1 = 6 + i * 2, 14 + i * 3
                    pygame.draw.line(screen, _fade((255, 230, 140), 1.0 - age),
                                     (sx + math.cos(a) * d0, sy + math.sin(a) * d0),
                                     (sx + math.cos(a) * d1, sy + math.sin(a) * d1), 1)
            elif k == "chaff":
                for i in range(14):
                    a = (f["seed"] * 0.71 + i * 1.7) % (2 * math.pi)
                    d = 4 + 16 * age * (0.5 + (i % 5) / 5.0)
                    screen.set_at((int(sx + math.cos(a) * d), int(sy + math.sin(a) * d)),
                                  _fade((200, 210, 215), 1.0 - age))
            elif k == "flash":
                pygame.draw.circle(screen, _fade((255, 250, 210), 1.0 - age), (sx, sy), int(3 + 5 * age), 1)

    # ------------------------------------------------------------ overlays on the display
    def draw_overlay(self, gui, scene, r: Rect) -> None:
        w = self.world
        b = w.battle
        s = gui.screen
        th = scene.theme
        # status plate, top left
        ph = b.phases[b.phase].get("name", "") if 0 <= b.phase < len(b.phases) else "STAND BY"
        own = w.own_side
        enemy = "red" if own == "blue" else "blue"
        cnt = b.counters
        ships = [x for x in w.ships.values() if x.side == own]
        afloat = sum(1 for x in ships if x.state != "sunk")
        air = sum(1 for a in w.aircraft.values() if a.state == "airborne" and a.side == own and a.kind == "aircraft"
                  and not a.aim and (a.flight_id or a.group))
        vamp = sum(1 for t in w.tracks.values() if not t.lost and t.identity == "hostile"
                   and bstaff.classify(w, t) == "missile")
        lines = [(ph, (255, 236, 170)),
                 (f"OWN: {air} airborne · {afloat}/{len(ships)} ships · {int(cnt.get(f'aircraft_lost_{own}', 0))} lost",
                  IDC["friend"] if not self.pvo else IDC_PVO["friend"]),
                 (f"ENEMY: {int(cnt.get(f'aircraft_lost_{enemy}', 0))} shot down"
                  f"{' · ' + str(int(cnt.get(f'ships_sunk_{enemy}', 0))) + ' ships sunk' if cnt.get(f'ships_sunk_{enemy}') else ''}",
                  IDC["hostile"] if not self.pvo else IDC_PVO["hostile"])]
        if vamp:
            lines.append((f"VAMPIRES: {vamp} inbound", (255, 90, 70) if int(self.clock * 3) % 2 else (255, 200, 160)))
        if b.spectator:
            lines.append(("SPECTATING — the staff commands" + (" · UMPIRE VIEW" if self.umpire else ""),
                          (200, 220, 230)))
        wmax = max(TEXT.width(t, 12, "eng") for t, _ in lines) + 20
        plate = R(r.x + 10, r.y + 10, wmax, len(lines) * 17 + 10)
        bg = pygame.Surface(plate.size, pygame.SRCALPHA)
        bg.fill((0, 0, 0, 150))
        s.blit(bg, plate.topleft)
        pygame.draw.rect(s, (90, 100, 104), plate, 1)
        for i, (txt, col) in enumerate(lines):
            gui.label((plate.x + 10, plate.y + 6 + i * 17), txt, 12 if i else 13, col, "eng")
        if self.follow:
            gui.label((r.centerx, r.bottom - 40), f"FOLLOWING {self._uname(self.follow)} — click FOLLOW again to stop",
                      11, (255, 255, 255), "eng", "center", shadow=True)
        # vampire alarm: the display's edges flash red
        if self.flash > 0.02:
            edge = pygame.Surface(r.size, pygame.SRCALPHA)
            a = int(110 * self.flash * (0.6 + 0.4 * math.sin(self.clock * 14)))
            for k in range(8):
                pygame.draw.rect(edge, (255, 30, 20, max(0, a - k * 13)), edge.get_rect().inflate(-k * 6, -k * 6), 3)
            s.blit(edge, r.topleft)
        self._banner(gui, r)
        self._decision(gui, scene, r)
        self._unit_card(gui, scene, r)

    def _banner(self, gui, r: Rect) -> None:
        if self.banner is None:
            return
        text, sub, t0 = self.banner
        age = self.clock - t0
        if age > 5.5:
            self.banner = None
            return
        a = min(1.0, age * 2.5, (5.5 - age) * 1.2)
        s = gui.screen
        band = R(r.x, r.y + r.h // 2 - 50, r.w, 100)
        bg = pygame.Surface(band.size, pygame.SRCALPHA)
        bg.fill((0, 0, 0, int(170 * a)))
        s.blit(bg, band.topleft)
        col = _fade((255, 232, 160), a)
        pygame.draw.line(s, col, (band.x + 40, band.y + 6), (band.right - 40, band.y + 6), 1)
        pygame.draw.line(s, col, (band.x + 40, band.bottom - 7), (band.right - 40, band.bottom - 7), 1)
        img = TEXT.render(text, 34, col, "title" if not self.pvo else "title_ru")
        s.blit(img, (band.centerx - img.get_width() // 2, band.y + 12))
        if sub:
            sub = sub if len(sub) < 120 else sub[:117] + "…"
            img = TEXT.render(sub, 13, _fade((220, 220, 210), a), "eng_r")
            s.blit(img, (band.centerx - img.get_width() // 2, band.y + 66))

    def _decision(self, gui, scene, r: Rect) -> None:
        w = self.world
        pend = bstaff.pending(w)
        if not pend or w.battle.spectator:
            return
        d = pend[0]
        s = gui.screen
        width = min(560, r.w - 40)
        lines = TEXT.wrap(d.text, width - 28, 13, "eng_r")
        h = 70 + len(lines) * 17 + 40
        card = R(r.centerx - width // 2, r.y + 54, width, h)
        bg = pygame.Surface(card.size, pygame.SRCALPHA)
        bg.fill((12, 14, 16, 225))
        s.blit(bg, card.topleft)
        pulse = 0.6 + 0.4 * math.sin(self.clock * 4)
        pygame.draw.rect(s, _fade((255, 200, 80), pulse), card, 2)
        gui.label((card.x + 14, card.y + 10), "DECISION" + (f"  (+{len(pend) - 1} more)" if len(pend) > 1 else ""), 11,
                  (255, 200, 80), "eng")
        gui.label((card.x + 14, card.y + 26), d.title, 18, (255, 244, 220), "eng")
        for i, ln in enumerate(lines):
            gui.label((card.x + 14, card.y + 52 + i * 17), ln, 13, (220, 224, 220), "eng_r")
        left = max(0.0, d.t_expire - w.t)
        tot = max(1.0, d.t_expire - d.t)
        bar = R(card.x + 14, card.bottom - 50, card.w - 28, 4)
        pygame.draw.rect(s, (40, 44, 46), bar)
        pygame.draw.rect(s, (255, 200, 80) if left / tot > 0.3 else (255, 90, 60), (bar.x, bar.y, int(bar.w * left / tot),
                                                                                   bar.h))
        gui.label((bar.right, bar.y - 16), f"staff decides in {left:.0f} s: {d.default}", 10, (170, 176, 170), "eng_r",
                  "right")
        n = len(d.options)
        bw = (card.w - 28 - (n - 1) * 8) // n
        for i, opt in enumerate(d.options):
            br = R(card.x + 14 + i * (bw + 8), card.bottom - 40, bw, 30)
            if gui.button(br, opt, lit=opt == d.default, size=12, key=f"DECIDE {opt}",
                          color=(255, 200, 80) if opt == d.default else None):
                scene.cmd("decide", decision=d.id, option=opt)

    def _uname(self, uid: str) -> str:
        w = self.world
        if uid in w.ships:
            return w.ships[uid].name
        if uid in w.battle.groups:
            return w.battle.groups[uid].callsign
        if uid in w.flights:
            return w.flights[uid].callsign
        return uid

    def unit_story(self, uid: str, n: int = 8) -> list[tuple[float, str]]:
        """What this unit has done: battle events and log entries about it or its aircraft."""
        w = self.world
        refs = {uid}
        if uid in w.battle.groups:
            refs |= set(w.battle.groups[uid].members)
        if uid in w.flights:
            refs |= set(w.flights[uid].members)
        out = []
        for e in w.log[-1500:]:
            if e.ref in refs and e.cat in ("battle", "weapon", "result", "id") and not e.text.startswith("[enemy]"):
                out.append((e.t, e.text))
        for m in w.messages[-400:]:
            if m.ref in refs and m.delivered and m.kind == "radio":
                out.append((m.t_deliver, f"“{m.text}”"))
        out.sort(key=lambda x: x[0])
        return out[-n:]

    def _unit_card(self, gui, scene, r: Rect) -> None:
        w = self.world
        sel = scene.sel
        uid = sel.get("ship") or sel.get("group") or sel.get("flight") or ""
        if not uid:
            return
        rows: list[tuple[str, tuple]] = []
        title, sub = uid, ""
        own = True
        if uid in w.ships:
            sh = w.ships[uid]
            own = sh.side == w.own_side
            if not own and not self.umpire:
                c = w.battle.surface.get(w.own_side, {}).get(uid)
                if c is None:
                    return
                st = w.catalog.ships[sh.type_id]
                title, sub = st.nato_name or "SURFACE CONTACT", f"{'passive bearing fix' if c.passive else 'radar contact'}" \
                    f" · ±{c.err_km:.0f} km · seen {max(0, w.t - c.t) / 60:.0f} min ago by {c.by}"
                rows.append((f"Missile envelope {max((w.catalog.sams[m['type']].range_max_km for m in st.sams), default=0):.0f} km",
                             (255, 150, 120)))
            else:
                st = w.catalog.ships[sh.type_id]
                title, sub = sh.name, f"{st.name} · {sh.state.upper()} · hull {max(0, sh.hp) / sh.max_hp * 100:.0f}%"
                rows.append((f"{sh.spd / 0.5144:.0f} kn, course {sh.hdg:03.0f} · chaff {sh.chaff} · hits {sh.hits}",
                             (200, 210, 214)))
                sams = [s for s in w.sams.values() if s.carrier == sh.id]
                if sams:
                    rows.append((f"Missiles {sum(s.ready_missiles for s in sams)} · channels "
                                 f"{sum(1 for s in sams if s.state in ('locked', 'engaging'))}/{len(sams)} engaged",
                                 (200, 210, 214)))
        elif uid in w.battle.groups:
            g = w.battle.groups[uid]
            own = g.side == w.own_side
            at = w.catalog.aircraft[g.type_id]
            ms = [w.aircraft[m] for m in g.members if m in w.aircraft and w.aircraft[m].state == "airborne"
                  and w.aircraft[m].group == g.id]
            title, sub = g.name, f"{len(ms)}/{g.n} × {at.name} · {g.role.upper()} · {g.state.upper()}"
            if ms:
                fuel = ms[0].fuel / at.fuel_kg * 100
                wpn = ", ".join(f"{n}× {k}" for k, n in sorted(ms[0].weapons.items()) if n) or "no weapons"
                rows.append((f"Fuel {fuel:.0f}% · {wpn}", (200, 210, 214)))
            rows.append((f"Kills {g.kills} · losses {g.losses}" + (" · released" if g.released else ""),
                         (200, 210, 214)))
        elif uid in w.flights:
            fl = w.flights[uid]
            at = w.catalog.aircraft[fl.type_id]
            ms = [w.aircraft[m] for m in fl.members if m in w.aircraft and w.aircraft[m].state == "airborne"]
            title, sub = fl.callsign, f"{len(ms)}× {at.name} · {fl.task.upper()} · {fl.state.upper()}" + \
                (f" on {fl.target}" if fl.target else "")
            if ms:
                fuel = ms[0].fuel / at.fuel_kg * 100
                wpn = ", ".join(f"{n}× {k}" for k, n in sorted(ms[0].weapons.items()) if n) or "winchester"
                rows.append((f"Fuel {fuel:.0f}%{' BINGO' if fl.bingo else ''} · {wpn}", (200, 210, 214)))
            sq = w.squadrons.get(fl.squadron_id)
            if sq is not None:
                rows.append((f"{sq.name} · shots {fl.shots} · kills {len(fl.kills)}", (200, 210, 214)))
        else:
            return
        story = self.unit_story(uid) if (own or self.umpire) else []
        s = gui.screen
        width = 430
        h = 54 + len(rows) * 16 + (len(story) * 15 + 18 if story else 0) + 34
        card = R(r.x + 10, r.bottom - h - 26, width, h)
        bg = pygame.Surface(card.size, pygame.SRCALPHA)
        bg.fill((8, 10, 12, 215))
        s.blit(bg, card.topleft)
        pygame.draw.rect(s, (110, 120, 124), card, 1)
        gui.label((card.x + 10, card.y + 8), title, 15, (255, 244, 220), "eng")
        gui.label((card.x + 10, card.y + 28), sub[:84], 11, (190, 200, 204), "eng_r")
        y = card.y + 46
        for txt, col in rows:
            gui.label((card.x + 10, y), txt[:80], 11, col, "eng_r")
            y += 16
        if story:
            gui.label((card.x + 10, y + 2), "ITS STORY", 10, (255, 200, 80), "eng")
            y += 18
            from .mapview import clock
            for t, txt in story:
                gui.label((card.x + 10, y), f"{clock(w, t)}  {txt}"[:86], 10, (176, 186, 188), "eng_r")
                y += 15
        bw = 96
        if gui.button(R(card.right - bw - 8, card.bottom - 32, bw, 24), "FOLLOW", lit=self.follow == uid, size=11,
                      key="UNIT FOLLOW", tip="Keep the display centred on this unit"):
            self.follow = "" if self.follow == uid else uid
        if gui.button(R(card.right - 2 * bw - 14, card.bottom - 32, bw, 24), "CENTER", size=11, key="UNIT CENTER"):
            pos = self.unit_pos(uid)
            if pos is not None:
                scene.map.center_on(*pos)
        if gui.button(R(card.x + 8, card.bottom - 32, 70, 24), "CLOSE", size=11, key="UNIT CLOSE"):
            for k in ("ship", "group", "flight"):
                scene.sel.pop(k, None)
            if self.follow == uid:
                self.follow = ""


# ---------------------------------------------------------------- the battle console

class BattleConsole:
    """BATTLE F7: standing orders, the commander's decisions, forces, objectives and the log."""
    name = "BATTLE"
    key = ""

    def draw(self, gui, r: Rect, scene) -> None:
        from .mapview import clock
        w = scene.world
        b = w.battle
        th = scene.theme
        fxv = scene.battle_fx
        inner = gui.panel(r, "BATTLE STAFF", b.post_sub or "commander's console")
        x0, y = inner.x, inner.y
        ph = b.phases[b.phase].get("name", "") if 0 <= b.phase < len(b.phases) else "STAND BY"
        gui.label((x0, y), ph, 14, th.accent, "eng")
        gui.label((inner.right, y + 2), f"{clock(w, w.t)}  ·  T+{w.t / 60:.0f} min", 12, th.engraving_dim, "eng_r",
                  "right")
        y += 22
        # ---- decisions waiting
        pend = bstaff.pending(w)
        if pend and not b.spectator:
            for d in pend[:2]:
                gui.label((x0, y), f"DECISION: {d.title}", 12, (255, 200, 80), "eng")
                gui.label((inner.right, y), f"{max(0, d.t_expire - w.t):.0f} s", 11, (255, 200, 80), "eng_r", "right")
                y += 17
                bw = (inner.w - (len(d.options) - 1) * 6) // len(d.options)
                for i, opt in enumerate(d.options):
                    if gui.button(R(x0 + i * (bw + 6), y, bw, 24), opt, lit=opt == d.default, size=10,
                                  key=f"CONSOLE {d.id} {opt}"):
                        scene.cmd("decide", decision=d.id, option=opt)
                y += 30
        # ---- standing orders
        gui.eng((x0, y), "STANDING ORDERS", 12)
        y += 18
        st = b.standing
        rows = [("POSTURE", "posture", [("AGGRESSIVE", "aggressive"), ("BALANCED", "balanced"), ("DEFENSIVE", "defensive")],
                 "How far out the staff sends fighters: 950, 600 or 320 km from what we defend."),
                ("FIGHTERS", "fighters", [("AUTO COMMIT", "auto"), ("MANUAL", "manual")],
                 "AUTO: the staff commits interceptors on its own. MANUAL: only your orders."),
                ("MISSILES", "sam", [("FREE", "FREE"), ("TIGHT", "TIGHT"), ("HOLD", "HOLD")],
                 "FREE: fire channels take any hostile in range. TIGHT: only missiles and close threats."),
                ("RADARS", "emcon", [("RADIATE", False), ("SILENT", True)],
                 "Emission control: silent ships cannot be heard by ESM, nor see for themselves.")]
        lw = 78
        for lab, key, opts, tip in rows:
            gui.label((x0, y + 5), lab, 11, th.engraving_dim, "eng")
            bw = (inner.w - lw - (len(opts) - 1) * 4) // len(opts)
            for i, (olab, val) in enumerate(opts):
                rr = R(x0 + lw + i * (bw + 4), y, bw, 24)
                if gui.button(rr, olab, lit=st.get(key) == val, size=10, key=f"STANDING {key} {olab}", tip=tip,
                              color=th.lamp_red if (key == "emcon" and val) else None):
                    if st.get(key) != val:
                        scene.cmd("standing", key=key, value=val)
            y += 28
        gui.label((x0, y + 5), "RESERVE", 11, th.engraving_dim, "eng")
        if gui.button(R(x0 + lw, y, 30, 24), "−", size=12, key="RESERVE -", tip="Interceptors kept on deck/alert"):
            scene.cmd("standing", key="reserve", value=max(0, int(st.get("reserve", 2)) - 1))
        gui.label((x0 + lw + 44, y + 4), f"{int(st.get('reserve', 2))} kept on alert", 12, th.engraving, "eng")
        if gui.button(R(x0 + lw + 160, y, 30, 24), "+", size=12, key="RESERVE +"):
            scene.cmd("standing", key="reserve", value=min(12, int(st.get("reserve", 2)) + 1))
        if b.priority:
            gui.label((x0 + lw + 200, y + 5), "PRIORITY: " + " ".join(b.priority[:4]), 11, (255, 236, 120), "eng")
        else:
            gui.label((x0 + lw + 200, y + 5), "right-click a track: PRIORITY", 10, th.engraving_dim, "eng_r")
        y += 32
        # ---- reinforcements
        avail = [x for x in b.reinforcements if x["available"]]
        for rf in avail[:2]:
            lab = rf.get("name", rf["id"])
            if rf["called"]:
                gui.label((x0, y + 5), f"{lab}: on the way", 11, th.ok, "eng")
            elif gui.button(R(x0, y, inner.w, 24), f"REQUEST: {lab.upper()}", size=10, key=f"REINFORCE {rf['id']}",
                            color=th.lamp_amber, tip=rf.get("text", "")):
                scene.cmd("reinforce", id=rf["id"])
            y += 28
        # ---- forces
        gui.eng((x0, y), "FORCES", 12)
        y += 18
        own = w.own_side
        ready = {}
        for sq in w.squadrons.values():
            for k, v in sq.ready.items():
                ready[k] = ready.get(k, 0) + v
        airborne = sum(1 for fl in w.flights.values() if fl.state not in ("landed", "lost", "scrambling")
                       for m in fl.members if m in w.aircraft and w.aircraft[m].state == "airborne")
        alert = " · ".join(f"{v}@{k}'" for k, v in sorted(ready.items(), key=lambda kv: float(kv[0])) if v) or "none"
        gui.label((x0, y), f"Interceptors airborne {airborne} · on alert {alert}", 11, th.engraving, "eng_r")
        y += 16
        ships = [s for s in w.ships.values() if s.side == own]
        cx = x0
        for s in ships:
            col = {"afloat": (110, 196, 255), "damaged": (255, 190, 70), "crippled": (255, 90, 60),
                   "sunk": (90, 96, 100)}[s.state]
            name = s.name.replace("USS ", "")
            wdt = TEXT.width(name, 10, "eng_r") + 10
            if cx + wdt > inner.right:
                cx, y = x0, y + 22
            gui.label((cx, y), name, 10, col, "eng_r")
            pygame.draw.rect(gui.screen, (24, 28, 30), (cx, y + 13, wdt - 10, 3))
            pygame.draw.rect(gui.screen, col, (cx, y + 13, int((wdt - 10) * max(0, s.hp) / s.max_hp), 3))
            cx += wdt
        y += 22
        cls_n: dict[str, int] = {}
        for t in w.tracks.values():
            if not t.lost and t.identity in ("hostile", "suspect"):
                c = CLASS_LABEL.get(bstaff.classify(w, t), "") or "UNK"
                cls_n[c] = cls_n.get(c, 0) + 1
        known = " · ".join(f"{n} {c}" for c, n in sorted(cls_n.items(), key=lambda kv: -kv[1])) or "nothing"
        gui.label((x0, y), f"Hostile tracks: {known}", 11, (255, 140, 120), "eng_r")
        y += 20
        # ---- objectives
        gui.eng((x0, y), "OBJECTIVES", 12)
        y += 18
        for o in w.objectives:
            if o.hidden:
                continue
            mark, col = {"done": ("✓", th.ok), "failed": ("✗", th.alert)}.get(o.status, ("·", th.engraving_dim))
            gui.label((x0, y), mark, 12, col, "ui")
            gui.label((x0 + 16, y), o.text, 11, col if o.status != "open" else th.engraving, "eng_r")
            y += 15
        y += 6
        # ---- view
        bw = (inner.w - 8) // 3
        if gui.button(R(x0, y, bw, 24), "TAKE COMMAND" if b.spectator else "SPECTATE", size=10, key="SPECTATOR",
                      lit=b.spectator, tip="Spectator mode: the staff commands everything and takes every decision."):
            scene.cmd("spectator", on=not b.spectator)
        if gui.button(R(x0 + bw + 4, y, bw, 24), "UMPIRE VIEW", size=10, key="UMPIRE", lit=fxv.umpire,
                      enabled=b.spectator or w.ended, tip="Show both sides as they really are (spectator mode)."):
            fxv.umpire = not fxv.umpire
        uid = scene.sel.get("ship") or scene.sel.get("group") or scene.sel.get("flight") or ""
        if gui.button(R(x0 + 2 * (bw + 4), y, bw, 24), "FOLLOW", size=10, key="CONSOLE FOLLOW", lit=bool(fxv.follow),
                      enabled=bool(uid) or bool(fxv.follow), tip="Keep the selected unit in the middle of the display"):
            fxv.follow = "" if fxv.follow else uid
        y += 32
        # ---- the battle log
        lines = []
        for ev in list(fxv.log)[-60:]:
            if ev[7] < 1 and not fxv.umpire:
                continue
            col = (255, 110, 90) if ev[7] >= 3 else (255, 200, 120) if ev[7] == 2 else th.text_dim
            if ev[6] == w.own_side and ev[1] in ("kill", "ship_hit", "sunk", "group_lost"):
                col = (255, 120, 100)
            lines.append((f"{clock(w, ev[0])} {ev[2].replace('[enemy] ', '')}", col))
        if inner.bottom - y > 40:
            gui.log("battlelog", R(x0, y, inner.w, inner.bottom - y), lines, 11, "cyr" if th.faction != "US" else "ui")
