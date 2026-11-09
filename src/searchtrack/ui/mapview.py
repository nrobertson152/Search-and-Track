"""Situation display (SAGE-style, US) and plotting board (PVO-style, USSR).

Both draw the same simulation state; they differ in what a commander of that
system would actually see: SAGE shows computer tracks at their current
smoothed positions, the PVO board shows discrete, time-stamped reports and a
pencilled extrapolation."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pygame

from ..sim import coverage, doctrine, tracking
from ..sim.geo import FT, KT, NM
from .theme import TEXT, Theme

ID_LETTER = {"pending": "P", "friend": "F", "unknown": "U", "suspect": "S", "hostile": "H", "faker": "K"}


def fmt_alt(theme: Theme, alt: Optional[float], short: bool = True) -> str:
    if alt is None:
        return "---"
    if theme.units == "imperial":
        return f"{alt / FT / 1000:.0f}" if short else f"{alt / FT:,.0f} ft"
    return f"{alt / 1000:.1f}" if short else f"{alt:,.0f} m"


def fmt_spd(theme: Theme, kmps: float) -> str:
    if theme.units == "imperial":
        return f"{kmps * 1000 / KT:.0f}kt"
    return f"{kmps * 3600:.0f}"


def fmt_rng(theme: Theme, km: float) -> str:
    return f"{km / NM:.0f} nm" if theme.units == "imperial" else f"{km:.0f} km"


def clock(world, t: float) -> str:
    hh, mm = (int(x) for x in world.start_clock[11:16].split(":"))
    tot = hh * 3600 + mm * 60 + int(t)
    return f"{(tot // 3600) % 24:02d}:{(tot // 60) % 60:02d}"


class MapView:
    def __init__(self, world, theme: Theme, rect: pygame.Rect):
        self.world = world
        self.theme = theme
        self.rect = rect
        ext = world.theater.extent
        self.cx = (ext[0] + ext[1]) / 2
        self.cy = (ext[2] + ext[3]) / 2
        self.scale = min(rect.w / (ext[1] - ext[0]), rect.h / (ext[3] - ext[2])) * 1.05
        self.layers = {"coverage": False, "raw": True, "zones": True, "labels": True, "history": True,
                       "sites": True, "rings": False, "truth": False}
        self.cov_alt = 3000.0
        self._base = None
        self._base_key = None
        self._cov = None
        self._cov_key = None
        self.drag = None
        self.light_gun: Optional[tuple[float, float]] = None
        self.hover_world = (0.0, 0.0)

    # ------------------------------------------------------------ transforms
    def w2s(self, x: float, y: float) -> tuple[int, int]:
        return (int(self.rect.centerx + (x - self.cx) * self.scale),
                int(self.rect.centery - (y - self.cy) * self.scale))

    def s2w(self, sx: float, sy: float) -> tuple[float, float]:
        return (self.cx + (sx - self.rect.centerx) / self.scale, self.cy - (sy - self.rect.centery) / self.scale)

    def zoom(self, f: float, about: tuple[int, int] | None = None) -> None:
        about = about or self.rect.center
        wx, wy = self.s2w(*about)
        self.scale = max(0.12, min(12.0, self.scale * f))
        nx, ny = self.s2w(*about)
        self.cx += wx - nx
        self.cy += wy - ny

    def center_on(self, x: float, y: float) -> None:
        self.cx, self.cy = x, y

    # ------------------------------------------------------------ input
    def handle(self, gui, events) -> Optional[tuple]:
        """Returns ('pick', world_xy, screen_xy) on a left click inside the map."""
        r = self.rect
        m = gui.mouse
        inside = r.collidepoint(m)
        if inside:
            self.hover_world = self.s2w(*m)
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button in (2, 3) and r.collidepoint(e.pos):
                self.drag = (e.pos, self.cx, self.cy)
            elif e.type == pygame.MOUSEBUTTONUP and e.button in (2, 3):
                self.drag = None
            elif e.type == pygame.MOUSEMOTION and self.drag:
                (px, py), cx, cy = self.drag
                self.cx = cx - (e.pos[0] - px) / self.scale
                self.cy = cy + (e.pos[1] - py) / self.scale
        if inside and gui.wheel:
            self.zoom(1.25 ** gui.wheel, m)
            gui.wheel = 0
        if inside and gui.released and not gui.consumed and r.collidepoint(gui.press_pos) \
                and math.hypot(m[0] - gui.press_pos[0], m[1] - gui.press_pos[1]) < 6:
            gui.consumed = True
            return ("pick", self.s2w(*m), m)
        return None

    def pick(self, sx: int, sy: int, radius: int = 14) -> Optional[tuple[str, str]]:
        w = self.world
        best, bd = None, radius
        for f in w.flights.values():
            if f.state in ("landed", "lost", "scrambling"):
                continue
            a = w.aircraft.get(f.members[0]) if f.members else None
            if a is None or a.state != "airborne":
                continue
            px, py = self.w2s(a.x, a.y)
            d = math.hypot(px - sx, py - sy)
            if d < bd:
                best, bd = ("flight", f.id), d
        for tk in w.tracks.values():
            px, py = self._track_pos(tk)
            d = math.hypot(px - sx, py - sy)
            if d < bd:
                best, bd = ("track", tk.id), d
        if best is None:
            for s in list(w.radars.values()) + list(w.sams.values()):
                px, py = self.w2s(s.x, s.y)
                d = math.hypot(px - sx, py - sy)
                if d < 10:
                    best = ("site" if s.id in w.radars else "sam", s.id)
        return best

    def _track_pos(self, tk) -> tuple[int, int]:
        if self.theme.map_style == "board":
            return self.w2s(tk.x, tk.y)
        px, py = tracking.predicted(tk, self.world.t)
        return self.w2s(px, py)

    # ------------------------------------------------------------ base layer
    def _nm(self, obj) -> str:
        """Russian lettering on the Soviet board (cosmetic), English elsewhere."""
        ru = obj.get("name_ru", "") if isinstance(obj, dict) else getattr(obj, "name_ru", "")
        name = obj["name"] if isinstance(obj, dict) else obj.name
        if ru and self.theme.faction == "USSR" and getattr(self, "lang_mode", "ru+en") != "en":
            return ru
        return name

    def _background(self) -> pygame.Surface:
        import numpy as np
        board = self.theme.map_style == "board"
        w, h = self.rect.size
        yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32))
        d = np.sqrt(((xx - w * 0.5) / (w * 0.6)) ** 2 + ((yy - h * 0.45) / (h * 0.6)) ** 2)
        f = np.clip(1.0 - d * 0.75, 0.0, 1.0)[..., None]
        rng = np.random.default_rng(3)
        if board:
            inner, outer = np.array((26, 50, 52), np.float32), np.array((7, 16, 18), np.float32)
            noise = rng.normal(0, 2.2, (w, h, 1)).astype(np.float32)
        else:
            inner, outer = np.array((5, 17, 20), np.float32), np.array((1, 4, 5), np.float32)
            noise = rng.normal(0, 0.8, (w, h, 1)).astype(np.float32)
        img = outer + (inner - outer) * f + noise
        return pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))

    def _build_base(self) -> pygame.Surface:
        th = self.theme
        w = self.world
        board = th.map_style == "board"
        if getattr(self, "_bg_src", None) is None or self._bg_src.get_size() != self.rect.size:
            self._bg_src = self._background()
        surf = self._bg_src.copy()
        ox, oy = self.rect.topleft

        def tp(x, y):
            sx, sy = self.w2s(x, y)
            return sx - ox, sy - oy

        # grid
        step = 100.0 if self.scale < 1.6 else 50.0
        if board:
            step = w.faction_def.grid_km * 10.0
        x0, y0 = self.s2w(ox, oy + self.rect.h)
        x1, y1 = self.s2w(ox + self.rect.w, oy)
        gx = math.floor((x0 + 1000.0) / step) * step - 1000.0
        while gx <= x1:
            pygame.draw.line(surf, th.grid, tp(gx, y0), tp(gx, y1), 1)
            gx += step
        gy = math.floor((y0 + 1000.0) / step) * step - 1000.0
        while gy <= y1:
            pygame.draw.line(surf, th.grid, tp(x0, gy), tp(x1, gy), 1)
            gy += step
        if board:
            # grid square letters
            gx = math.floor((x0 + 1000.0) / step) * step - 1000.0
            while gx <= x1:
                gy = math.floor((y0 + 1000.0) / step) * step - 1000.0
                while gy <= y1:
                    lab = tracking.grid_label(w, gx + 1, gy + 1)[0]
                    sx, sy = tp(gx + 4, gy + step - 4)
                    surf.blit(TEXT.render(lab, 16, (76, 128, 124), "eng"), (sx + 2, sy - 2))
                    gy += step
                gx += step
        mp = w.theater.map
        styles = [("rivers", (44, 82, 104) if board else (16, 46, 54), 1), ("lakes", th.map_line, 1),
                  ("states", (70, 92, 84) if board else (22, 62, 70), 1), ("borders", th.map_coast, 2),
                  ("coast", th.map_coast, 2 if board else 1)]
        for layer, col, wd in styles:
            for seg in mp.get(layer, []):
                if len(seg) < 4:
                    continue
                pts = [tp(seg[i], seg[i + 1]) for i in range(0, len(seg), 2)]
                pygame.draw.lines(surf, col, False, pts, wd)
        # cities
        for c in w.cities:
            sx, sy = tp(c["x"], c["y"])
            col = (176, 180, 150) if board else (70, 170, 170)
            pygame.draw.circle(surf, col, (sx, sy), 2 + c["size"], 0 if c["size"] >= 2 else 1)
            if self.layers["labels"]:
                surf.blit(TEXT.render(self._nm(c), 12 + (1 if c["size"] >= 2 else 0), col, "eng" if board else "ui"),
                          (sx + 6, sy - 8))
        # zones
        if self.layers["zones"]:
            for z in w.zones.values():
                col = (110, 90, 60) if z["kind"] == "adiz" else (90, 70, 70) if z["kind"] == "defended" else (70, 80, 80)
                if not board:
                    col = (90, 120, 40) if z["kind"] == "adiz" else (100, 60, 50) if z["kind"] == "defended" else (50, 70, 70)
                if z["shape"] == "circle":
                    sx, sy = tp(z["x"], z["y"])
                    _dashed_circle(surf, col, (sx, sy), int(z["r"] * self.scale))
                else:
                    pts = [tp(*p) for p in z["poly"]]
                    _dashed_poly(surf, col, pts)
                lx, ly = (tp(z["x"], z["y"]) if z["shape"] == "circle" else tp(*z["poly"][0]))
                surf.blit(TEXT.render(self._nm(z), 11, col, "eng_r" if board else "ui"), (lx + 4, ly + 4))
        return surf

    # ------------------------------------------------------------ draw
    def draw(self, screen: pygame.Surface, sel: dict, tr: float) -> None:
        th = self.theme
        w = self.world
        key = (round(self.cx, 2), round(self.cy, 2), round(self.scale, 4), self.layers["zones"], self.layers["labels"],
               self.rect.size, getattr(self, "lang_mode", ""))
        if key != self._base_key:
            self._base = self._build_base()
            self._base_key = key
            self._cov_key = None
        screen.blit(self._base, self.rect.topleft)
        screen.set_clip(self.rect)
        if self.layers["coverage"]:
            self._draw_coverage(screen)
        board = th.map_style == "board"
        # static sites
        if self.layers["sites"]:
            for s in w.radars.values():
                self._site(screen, s, sel)
            for b in w.airbases.values():
                if b.side != "blue":
                    continue
                sx, sy = self.w2s(b.x, b.y)
                col = th.map_coast if b.kind == "military" else th.map_line
                pygame.draw.line(screen, col, (sx - 6, sy + 3), (sx + 6, sy - 3), 3)
                if self.layers["labels"] and b.kind == "military":
                    screen.blit(TEXT.render(self._nm(b), 11, col, "eng_r" if board else "ui"), (sx + 8, sy + 5))
            for sm in w.sams.values():
                self._sam(screen, sm, sel)
        # range rings for selected radar
        if self.layers["rings"] and sel.get("site") in w.radars:
            s = w.radars[sel["site"]]
            rt = w.catalog.radars[s.type_id]
            sx, sy = self.w2s(s.x, s.y)
            step = 50 * NM if th.units == "imperial" else 50.0
            r = step
            while r <= rt.range_km:
                pygame.draw.circle(screen, th.phosphor_dim, (sx, sy), int(r * self.scale), 1)
                r += step
        # raw plots (SAGE shows unassociated radar returns)
        if self.layers["raw"] and not board:
            for p in w.plots[-400:]:
                age = w.t - p.t
                if age > 40:
                    continue
                sx, sy = self.w2s(p.x, p.y)
                c = _fade(th.phosphor, 1.0 - age / 45.0)
                pygame.draw.circle(screen, c, (sx, sy), 2)
        # jam strobes
        for st in w.strobes:
            site = w.radars.get(st.radar)
            if site is None or st.strobe_az is None:
                continue
            age = w.t - st.t
            sx, sy = self.w2s(site.x, site.y)
            rt = w.catalog.radars[site.type_id]
            a = math.radians(st.strobe_az)
            ex, ey = self.w2s(site.x + math.sin(a) * rt.range_km, site.y + math.cos(a) * rt.range_km)
            pygame.draw.line(screen, _fade(th.accent, max(0.0, 1.0 - age / 25.0) * 0.6), (sx, sy), (ex, ey), 1)
        # truth overlay (debug / after-action)
        if self.layers["truth"]:
            for a in w.radar_targets():
                sx, sy = self.w2s(a.x, a.y)
                pygame.draw.circle(screen, (255, 0, 255), (sx, sy), 3, 1)
                screen.blit(TEXT.render(a.callsign[:12], 9, (255, 0, 255), "ui"), (sx + 4, sy + 2))
        # tracks
        for tk in sorted(w.tracks.values(), key=lambda t: t.id == sel.get("track")):
            self._track(screen, tk, tk.id == sel.get("track"))
        # interceptors and missiles
        for f in w.flights.values():
            self._flight(screen, f, f.id == sel.get("flight"))
        for m in w.missiles.values():
            if m.state != "flying" or w.t < m.t_launch:
                continue
            sx, sy = self.w2s(m.x, m.y)
            ex, ey = self.w2s(m.x - m.vx / 1000.0 * 6, m.y - m.vy / 1000.0 * 6)
            pygame.draw.line(screen, th.alert, (sx, sy), (ex, ey), 1)
            pygame.draw.circle(screen, th.lamp_white, (sx, sy), 2)
        # light gun
        if self.light_gun and not board:
            sx, sy = self.w2s(*self.light_gun)
            r = 9 + int(3 * math.sin(pygame.time.get_ticks() / 150.0))
            pygame.draw.circle(screen, th.lamp_white, (sx, sy), r, 1)
            pygame.draw.line(screen, th.lamp_white, (sx - r - 4, sy), (sx - r + 3, sy))
            pygame.draw.line(screen, th.lamp_white, (sx + r - 3, sy), (sx + r + 4, sy))
        screen.set_clip(None)

    def annotate(self, screen: pygame.Surface, sel: dict) -> None:
        th = self.theme
        w = self.world
        lat, lon = w.theater.proj.inverse(*self.hover_world)
        txt = f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'} {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"
        tk = w.tracks.get(sel.get("track") or "")
        if tk is not None:
            px, py = tracking.predicted(tk, w.t)
            dx, dy = self.hover_world[0] - px, self.hover_world[1] - py
            txt += f"   from {tk.id}: {math.degrees(math.atan2(dx, dy)) % 360:03.0f}° {fmt_rng(th, math.hypot(dx, dy))}"
        TEXTC = th.text_dim
        screen.blit(TEXT.render(txt, 11, TEXTC, "ui"), (self.rect.x + 8, self.rect.bottom - 18))
        if self.layers["coverage"]:
            lab = f"COVERAGE {fmt_alt(th, self.cov_alt, False)} · 5 m² · Pd≥0.5 (bright = overlap)"
            screen.blit(TEXT.render(lab, 11, th.accent, "ui"), (self.rect.right - TEXT.width(lab, 11) - 10,
                                                                 self.rect.bottom - 18))

    def _draw_coverage(self, screen) -> None:
        w = self.world
        st = tuple((s.id, s.status, s.k_override, s.pfa_exp, s.rpm, s.degraded_db) for s in w.radars.values())
        key = (self._base_key, self.cov_alt, st, w.weather.k_factor)
        if key != self._cov_key:
            step = 6
            gw, gh = self.rect.w // step, self.rect.h // step
            sx = self.rect.x + (np.arange(gw) + 0.5) * step
            sy = self.rect.y + (np.arange(gh) + 0.5) * step
            SX, SY = np.meshgrid(sx, sy)
            X = self.cx + (SX - self.rect.centerx) / self.scale
            Y = self.cy - (SY - self.rect.centery) / self.scale
            cnt = coverage.horizontal(w, X, Y, self.cov_alt)
            img = np.zeros((gw, gh, 3), dtype=np.uint8)
            base = np.array(self.theme.phosphor if self.theme.map_style != "board" else (90, 160, 200))
            lvl = np.clip(cnt.T, 0, 3)[..., None] / 3.0
            img[:] = (base * lvl * 0.5).astype(np.uint8)
            small = pygame.surfarray.make_surface(img)
            self._cov = pygame.transform.smoothscale(small, self.rect.size)
            self._cov_key = key
        screen.blit(self._cov, self.rect.topleft, special_flags=pygame.BLEND_RGB_ADD)

    def _site(self, screen, s, sel) -> None:
        th = self.theme
        sx, sy = self.w2s(s.x, s.y)
        col = th.map_coast if s.status == "ok" else th.accent if s.status in ("degraded", "maint") else th.alert
        if sel.get("site") == s.id:
            col = th.lamp_white
        pts = [(sx, sy - 6), (sx + 5, sy + 4), (sx - 5, sy + 4)]
        pygame.draw.polygon(screen, col, pts, 1 if not s.gci else 0)
        if self.layers["labels"]:
            lab = self._nm(s).replace("Radar company ", "").replace(" guidance point", " GP")
            screen.blit(TEXT.render(lab, 11, col, "eng_r" if th.map_style == "board" else "ui"), (sx + 7, sy - 5))

    def _sam(self, screen, s, sel) -> None:
        th = self.theme
        w = self.world
        st = w.catalog.sams[s.type_id]
        sx, sy = self.w2s(s.x, s.y)
        ready = s.status == "ok" and w.t >= s.t_ready
        col = th.ok if ready else th.text_dim
        if s.state in ("locked", "engaging"):
            col = th.alert
        pygame.draw.line(screen, col, (sx, sy + 5), (sx, sy - 6), 2)
        pygame.draw.line(screen, col, (sx - 3, sy - 2), (sx, sy - 6), 2)
        pygame.draw.line(screen, col, (sx + 3, sy - 2), (sx, sy - 6), 2)
        if sel.get("sam") == s.id or s.state in ("locked", "engaging") or (st.homing_km <= 0 and self.layers["rings"]):
            _dashed_circle(screen, _fade(col, 0.7), (sx, sy), int(st.range_max_km * self.scale))
        if s.lock and s.state in ("locked", "engaging", "assess"):
            tgt = w.aircraft.get(s.lock)
            if tgt is not None and tgt.state == "airborne":
                tx, ty = self.w2s(tgt.x, tgt.y)
                pygame.draw.line(screen, _fade(th.alert, 0.6), (sx, sy), (tx, ty), 1)

    def _track(self, screen, tk, selected: bool) -> None:
        th = self.theme
        w = self.world
        board = th.map_style == "board"
        col = th.id_colors.get(tk.identity, th.phosphor)
        if tk.lost:
            col = _fade(col, 0.45)
        if not board:
            col = col if selected else _fade(col, 0.85)
        px, py = tracking.predicted(tk, w.t)
        sx, sy = self.w2s(px, py)
        if board:
            # pencilled history: every report a dot with its time
            pts = [self.w2s(h[1], h[2]) for h in tk.history]
            if len(pts) > 1:
                pygame.draw.lines(screen, col, False, pts, 2)
            for i, h in enumerate(tk.history):
                hx, hy = self.w2s(h[1], h[2])
                pygame.draw.circle(screen, col, (hx, hy), 3)
                if self.layers["history"] and (i % 2 == 0 or i == len(tk.history) - 1):
                    screen.blit(TEXT.render(clock(w, h[0]), 9, _fade(col, 0.8), "cyr"), (hx + 4, hy + 2))
            lx, ly = self.w2s(tk.x, tk.y)
            _dashed_line(screen, _fade(col, 0.7), (lx, ly), (sx, sy))
            ang = math.atan2(tk.vx, tk.vy)
            for da in (2.6, -2.6):
                pygame.draw.line(screen, col, (sx, sy), (sx + 8 * math.sin(ang + da), sy - 8 * math.cos(ang + da)), 2)
            r = 13 if selected else 11
            pygame.draw.circle(screen, col, (lx, ly), r, 2)
            screen.blit(TEXT.render(tk.id, 13, col, "cyr"), (lx + r + 3, ly - 16))
            age = w.t - tk.t_update
            sub = f"H {tk.alt / 1000:.1f}" if tk.alt is not None else "H ?"
            screen.blit(TEXT.render(f"{sub}  {clock(w, tk.t_update)}  ({age / 60:.0f}m)", 10, _fade(col, 0.85), "cyr"),
                        (lx + r + 3, ly))
            if tk.jammer:
                screen.blit(TEXT.render("ПОМЕХА", 10, th.accent, "cyr"), (lx + r + 3, ly + 13))
            if selected:
                pygame.draw.circle(screen, th.lamp_white, (lx, ly), r + 5, 1)
            return
        # SAGE: history trail, symbol, leader, data block
        if self.layers["history"]:
            for h in tk.history[-12:]:
                hx, hy = self.w2s(h[1], h[2])
                screen.set_at((hx, hy), _fade(col, 0.5))
                pygame.draw.circle(screen, _fade(col, 0.4), (hx, hy), 1)
        lead_s = 120.0
        ex, ey = self.w2s(px + tk.vx * lead_s, py + tk.vy * lead_s)
        pygame.draw.line(screen, col, (sx, sy), (ex, ey), 1)
        _symbol(screen, tk.identity if not tk.jammer else "jammer", (sx, sy), col, selected)
        l1 = f"{tk.id} {ID_LETTER.get(tk.identity, '?')}{' ?' if tk.lost else ''}"
        l2 = f"{fmt_alt(th, tk.alt)} {fmt_spd(th, math.hypot(tk.vx, tk.vy))}"
        bx, by = sx + 10, sy - 22
        screen.blit(TEXT.render(l1, 12, col, "crt"), (bx, by))
        screen.blit(TEXT.render(l2, 11, _fade(col, 0.9), "crt"), (bx, by + 13))
        if tk.size > 1:
            screen.blit(TEXT.render(f"x{tk.size}", 10, _fade(col, 0.9), "crt"), (bx, by + 25))
        if selected:
            pygame.draw.rect(screen, th.lamp_white, (sx - 11, sy - 11, 22, 22), 1)

    def _flight(self, screen, f, selected: bool) -> None:
        th = self.theme
        w = self.world
        if f.state in ("landed", "lost"):
            return
        if f.state == "scrambling":
            b = w.airbases[f.base_id]
            sx, sy = self.w2s(b.x, b.y)
            pygame.draw.circle(screen, th.lamp_blue if th.faction == "US" else th.id_colors["friend"], (sx, sy), 9, 1)
            screen.blit(TEXT.render(f"{f.callsign} ↑{max(0, f.t_airborne - w.t) / 60:.0f}m", 10, th.lamp_blue
                                    if th.faction == "US" else th.id_colors["friend"], "ui"), (sx + 10, sy + 6))
            return
        a = w.aircraft.get(f.members[0]) if f.members else None
        if a is None or a.state != "airborne":
            return
        col = (140, 200, 255) if th.faction == "US" else th.id_colors["friend"]
        if selected:
            col = th.lamp_white
        sx, sy = self.w2s(a.x, a.y)
        ang = math.radians(a.hdg)
        nose = (sx + 9 * math.sin(ang), sy - 9 * math.cos(ang))
        l = (sx + 6 * math.sin(ang + 2.5), sy - 6 * math.cos(ang + 2.5))
        r = (sx + 6 * math.sin(ang - 2.5), sy - 6 * math.cos(ang - 2.5))
        pygame.draw.polygon(screen, col, [nose, l, (sx, sy), r], 0)
        if f.pip_x is not None and f.target and f.state in ("vector", "contact", "judy"):
            px, py = self.w2s(f.pip_x, f.pip_y)
            _dashed_line(screen, _fade(col, 0.6), (sx, sy), (px, py))
            pygame.draw.line(screen, col, (px - 5, py - 5), (px + 5, py + 5), 1)
            pygame.draw.line(screen, col, (px - 5, py + 5), (px + 5, py - 5), 1)
        if f.state == "cap" and f.cap_x is not None:
            cx, cy = self.w2s(f.cap_x, f.cap_y)
            _dashed_circle(screen, _fade(col, 0.5), (cx, cy), int(20 * self.scale))
        fuel = a.fuel / max(w.catalog.aircraft[a.type_id].fuel_kg, 1) * 100
        tag = {"vector": "VEC", "contact": "CON", "judy": "JUDY", "shadow": "SHAD", "attack": "ATK", "rtb": "RTB",
               "hold": "HOLD", "cap": "CAP", "airborne": "AIR"}.get(f.state, f.state.upper())
        screen.blit(TEXT.render(f"{f.callsign}", 11, col, "crt" if th.faction == "US" else "cyr"), (sx + 10, sy - 8))
        screen.blit(TEXT.render(f"{tag} {fmt_alt(th, a.alt)} F{fuel:.0f}%{' B' if f.bingo else ''}", 10,
                                _fade(col, 0.85), "crt" if th.faction == "US" else "cyr"), (sx + 10, sy + 4))


# ---------------------------------------------------------------- drawing helpers

def _fade(c, f: float):
    f = max(0.0, min(1.0, f))
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


def _symbol(screen, ident: str, c, col, selected: bool) -> None:
    x, y = c
    if ident == "friend":
        pygame.draw.circle(screen, col, c, 6, 1)
    elif ident == "unknown":
        pygame.draw.rect(screen, col, (x - 6, y - 6, 12, 12), 1)
    elif ident == "pending":
        for dx, dy in ((-6, -6), (6, -6), (6, 6), (-6, 6)):
            pygame.draw.line(screen, col, (x + dx, y + dy), (x + dx * 0.4, y + dy), 1)
            pygame.draw.line(screen, col, (x + dx, y + dy), (x + dx, y + dy * 0.4), 1)
    elif ident in ("suspect", "hostile"):
        pts = [(x, y - 8), (x + 8, y), (x, y + 8), (x - 8, y)]
        pygame.draw.polygon(screen, col, pts, 1 if ident == "suspect" else 2)
        if ident == "hostile":
            pygame.draw.circle(screen, col, c, 2)
    elif ident == "faker":
        pygame.draw.circle(screen, col, c, 6, 1)
        pygame.draw.line(screen, col, (x - 4, y), (x + 4, y))
    elif ident == "jammer":
        for a in range(0, 180, 45):
            r = math.radians(a)
            pygame.draw.line(screen, col, (x - 8 * math.sin(r), y - 8 * math.cos(r)), (x + 8 * math.sin(r), y + 8 * math.cos(r)))
    else:
        pygame.draw.circle(screen, col, c, 4, 1)


def _dashed_line(screen, col, a, b, dash: int = 6) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1:
        return
    n = int(d / dash)
    for i in range(0, n, 2):
        p = (a[0] + dx * i / n, a[1] + dy * i / n)
        q = (a[0] + dx * min(i + 1, n) / n, a[1] + dy * min(i + 1, n) / n)
        pygame.draw.line(screen, col, p, q, 1)


def _dashed_poly(screen, col, pts) -> None:
    for a, b in zip(pts, pts[1:] + pts[:1]):
        _dashed_line(screen, col, a, b, 8)


def _dashed_circle(screen, col, c, r: int) -> None:
    if r < 3:
        return
    n = max(16, int(r / 4))
    for i in range(0, n, 2):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        pygame.draw.line(screen, col, (c[0] + r * math.sin(a0), c[1] - r * math.cos(a0)),
                         (c[0] + r * math.sin(a1), c[1] - r * math.cos(a1)), 1)
