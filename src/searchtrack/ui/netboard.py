"""Mimic board of the air-defense network: every radar, line, airfield and
missile unit as a lamp on a back-lit schematic, with data pulses flowing along
the circuits that are up. Faults, jamming, maintenance and cut lines show at a
glance; clicking a node selects it for the consoles."""
from __future__ import annotations

import math

import pygame

from .theme import TEXT

R = pygame.Rect


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _fit(text: str, size: int, kind: str, width: int) -> str:
    if TEXT.width(text, size, kind) <= width:
        return text
    while len(text) > 2 and TEXT.width(text + "…", size, kind) > width:
        text = text[:-1]
    return text.rstrip() + "…"


class NetBoard:
    def __init__(self, world, theme, rect: pygame.Rect):
        self.world = world
        self.theme = theme
        self.rect = rect
        self.nodes: list[tuple[pygame.Rect, str, str]] = []     # rect, kind, id
        self._bg = None
        self.t = 0.0

    @property
    def ussr(self) -> bool:
        return self.world.faction == "USSR"

    def palette(self):
        if self.ussr:
            return dict(bg=(6, 12, 10), grid=(14, 26, 22), line=(54, 196, 118), line_dim=(26, 80, 52),
                        lamp=(255, 150, 46), ok=(90, 230, 120), bad=(255, 60, 44), warn=(255, 196, 60),
                        text=(226, 232, 214), text_dim=(120, 150, 130), tile=(16, 26, 22))
        return dict(bg=(5, 9, 14), grid=(12, 22, 30), line=(84, 204, 226), line_dim=(30, 80, 96),
                    lamp=(255, 186, 70), ok=(110, 236, 160), bad=(255, 70, 52), warn=(255, 206, 80),
                    text=(224, 236, 240), text_dim=(110, 140, 150), tile=(12, 20, 28))

    def _background(self) -> pygame.Surface:
        p = self.palette()
        r = self.rect
        s = pygame.Surface(r.size)
        s.fill(p["bg"])
        for x in range(0, r.w, 24):
            pygame.draw.line(s, p["grid"], (x, 0), (x, r.h))
        for y in range(0, r.h, 24):
            pygame.draw.line(s, p["grid"], (0, y), (r.w, y))
        # edge-lit acrylic: brighter near the top edge
        glow = pygame.Surface(r.size, pygame.SRCALPHA)
        for i in range(60):
            pygame.draw.line(glow, (*p["line"], max(0, 22 - i // 3)), (0, i), (r.w, i))
        s.blit(glow, (0, 0))
        return s

    def _name(self, obj) -> str:
        return obj.name

    # ------------------------------------------------------------ geometry helpers
    def _wire(self, s, pts, col, width=2, dashed=False):
        if dashed:
            for a, b in zip(pts, pts[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                n = max(1, int(L // 10))
                for k in range(0, n, 2):
                    p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                    p1 = (a[0] + (b[0] - a[0]) * min(n, k + 1) / n, a[1] + (b[1] - a[1]) * min(n, k + 1) / n)
                    pygame.draw.line(s, col, p0, p1, width)
        else:
            pygame.draw.lines(s, col, False, pts, width)

    def _pulses(self, s, pts, col, speed: float, phase: float, toward_end: bool = True):
        segs = list(zip(pts, pts[1:]))
        lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
        total = sum(lens)
        if total < 1:
            return
        spacing = 46.0
        off = (self.t * speed + phase) % spacing
        d = off
        while d < total:
            dd = d if toward_end else total - d
            acc = 0.0
            for (a, b), L in zip(segs, lens):
                if acc + L >= dd:
                    f = (dd - acc) / max(L, 1e-6)
                    x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                    pygame.draw.circle(s, _mix(col, (255, 255, 255), 0.6), (int(x), int(y)), 2)
                    break
                acc += L
            d += spacing

    def _lamp(self, gui, c, col, on=True, blink=False, r=5):
        gui.lamp(c, col, on, radius=r, blink=blink)

    def _tile(self, gui, rr: pygame.Rect, title: str, sub: str, col, p, sel: bool = False) -> None:
        s = gui.screen
        pygame.draw.rect(s, p["tile"], rr, border_radius=3)
        pygame.draw.rect(s, _mix(col, p["tile"], 0.35) if not sel else (255, 255, 255), rr, 1 if not sel else 2,
                         border_radius=3)
        gui.label((rr.x + 18, rr.y + 2), _fit(title, 12, "eng", rr.w - 22), 12, p["text"], "eng")
        if sub:
            gui.label((rr.x + 18, rr.y + 17), _fit(sub, 10, "eng_r", rr.w - 22), 10, p["text_dim"], "eng_r")

    # ------------------------------------------------------------ draw
    def draw(self, gui, sel: dict, dt: float) -> None:
        self.t += dt
        w = self.world
        r = self.rect
        p = self.palette()
        s = gui.screen
        if self._bg is None or self._bg.get_size() != r.size:
            self._bg = self._background()
        s.blit(self._bg, r.topleft)
        s.set_clip(r)
        self.nodes = []
        title = "МНЕМОСХЕМА СИСТЕМЫ ОПОВЕЩЕНИЯ И УПРАВЛЕНИЯ" if self.ussr and gui.lang_mode != "en" else \
            "SECTOR STATUS BOARD — SURVEILLANCE · COMMUNICATIONS · WEAPONS"
        gui.label((r.x + 18, r.y + 12), title, 16, p["text"], "eng")
        if self.ussr and gui.lang_mode == "ru+en":
            gui.label((r.x + 18, r.y + 32), "NETWORK MIMIC BOARD — WARNING AND CONTROL SYSTEM", 10, p["text_dim"], "eng_r")
        # ---- the command node
        # A wide board (the SAGE display) puts the missile units along the bottom; the tall PVO
        # plotting board stacks them under the fighter regiments in the right-hand column.
        wide = r.w >= 900
        cw = 240 if wide else 196
        cmd_w = 220 if wide else 150
        cx, cy = r.centerx, r.y + int(r.h * 0.40)
        cmd = R(cx - cmd_w // 2, cy - 34, cmd_w, 68)
        hq = R(cx - 100, r.y + 62, 200, 40)
        pygame.draw.rect(s, p["tile"], cmd, border_radius=5)
        pygame.draw.rect(s, p["line"], cmd, 2, border_radius=5)
        if self.ussr:
            head = "КП ОА ПВО" if gui.lang_mode != "en" else "ARMY COMMAND POST"
            hs = 16 if TEXT.width(head, 16, "eng") <= cmd.w - 12 else 13
            gui.label((cmd.centerx, cmd.y + 6 + (16 - hs) // 2), head, hs, p["text"], "eng", "center")
            gui.label((cmd.centerx, cmd.y + 28), "command post · plotting board", 10, p["text_dim"], "eng_r", "center")
        else:
            gui.label((cmd.centerx, cmd.y + 6), "DIRECTION CENTER · AN/FSQ-7", 15, p["text"], "eng", "center")
            for i, side in enumerate(("A", "B")):
                st = w.duplex.get(side, "?")
                col = p["ok"] if st == "active" else p["warn"] if st == "standby" else p["bad"]
                self._lamp(gui, (cmd.x + 70 + i * 80, cmd.y + 44), col, True, blink=st not in ("active", "standby"))
                gui.label((cmd.x + 80 + i * 80, cmd.y + 37), f"{side} {st.upper()[:4]}", 11, p["text"], "eng")
        # HQ
        pygame.draw.rect(s, p["tile"], hq, border_radius=4)
        pygame.draw.rect(s, p["line"], hq, 1, border_radius=4)
        gui.label((hq.centerx, hq.y + 4), w.hq.name[:28], 13, p["text"], "eng", "center")
        ws = w.hq.weapons_status
        wcol = p["ok"] if ws == "HOLD" else p["warn"] if ws == "TIGHT" else p["bad"]
        gui.label((hq.centerx, hq.y + 21), f"{w.hq.readiness} · {('ADW ' + w.hq.alert + ' · ') if w.hq.alert else ''}"
                  f"WEAPONS {ws}", 10, wcol, "eng_r", "center")
        pend = [rq for rq in w.hq.requests if not rq.answered]
        self._wire(s, [(cx, hq.bottom), (cx, cmd.y)], p["line"], 3)
        self._pulses(s, [(cx, cmd.y), (cx, hq.bottom)], p["line"], 30.0, 0.0)
        if pend:
            self._pulses(s, [(cx + 6, cmd.y), (cx + 6, hq.bottom)], p["warn"], 18.0, 11.0)
            gui.label((cx + 14, hq.bottom + 8), f"{len(pend)} REQUEST(S) PENDING", 10, p["warn"], "eng_r")
        # ---- radars (left)
        radars = list(w.radars.values())
        top, bot = r.y + 120, r.bottom - 30
        n = max(1, len(radars))
        step = min(64, (bot - top) / n)
        bus_x = r.x + 16 + cw + (44 if wide else 18)
        for i, site in enumerate(radars):
            y = int(top + step * i + step / 2)
            rr = R(r.x + 16, y - 16, cw, 32)
            ln = w.links.get(site.link)
            link_up = ln is None or ln.up
            jammed = bool(w.active_jammers(site))
            if site.status in ("down",):
                col = p["bad"]
            elif site.status in ("degraded", "maint") or jammed:
                col = p["warn"]
            else:
                col = p["ok"]
            rt = w.catalog.radars[site.type_id]
            sub = f"{rt.id} · {site.status.upper()}" + \
                  (" · JAM" if jammed else "") + (" · MTI" if site.mti else "")
            self._tile(gui, rr, self._name(site), sub, col, p, sel.get("site") == site.id)
            self._lamp(gui, (rr.x + 9, rr.y + 9), col, True, blink=site.status == "down" or jammed, r=4)
            if site.gci:
                self._lamp(gui, (rr.x + 9, rr.y + 23), p["lamp"], True, r=3)
            hfs = [h for h in w.hfs.values() if h.site_id == site.id]
            for k, h in enumerate(hfs):
                hc = p["lamp"] if h.current else p["ok"] if h.status == "ok" else p["bad"]
                self._lamp(gui, (rr.right - 10 - k * 12, rr.y + 9), hc, True, r=3)
            pts = [(rr.right, y), (bus_x, y), (bus_x, cy), (cmd.x, cy)]
            if link_up and site.status != "down":
                self._wire(s, pts[:2], p["line"], 2)
                self._pulses(s, pts[:2], p["line"], 40.0 if (ln is None or ln.delay_s < 30) else 12.0, i * 13.0)
            else:
                self._wire(s, pts[:2], p["bad"] if not link_up else p["line_dim"], 2, dashed=True)
                if not link_up:
                    self._lamp(gui, ((rr.right + bus_x) // 2, y), p["bad"], True, blink=True, r=4)
            self.nodes.append((rr, "site", site.id))
        if radars:
            ys = [int(top + step * i + step / 2) for i in range(len(radars))]
            self._wire(s, [(bus_x, min(ys + [cy])), (bus_x, max(ys + [cy]))], p["line"], 3)
            self._wire(s, [(bus_x, cy), (cmd.x, cy)], p["line"], 3)
            self._pulses(s, [(bus_x, cy), (cmd.x, cy)], p["line"], 40.0, 3.0)
        # ---- airfields & squadrons (right)
        sqs = list(w.squadrons.values())
        sams = list(w.sams.values())
        right = len(sqs) + (0 if wide else len(sams))
        bus2 = r.right - 16 - cw - (44 if wide else 18)
        top2 = r.y + 120
        limit2 = (r.y + r.h * 0.62) if wide else (r.bottom - 24)
        step2 = min(78, (limit2 - top2) / max(1, right))
        ys2 = []
        for i, q in enumerate(sqs):
            y = int(top2 + step2 * i + step2 / 2)
            ys2.append(y)
            base = w.airbases.get(q.base_id)
            rr = R(r.right - 16 - cw, y - 22, cw, 44)
            ln = w.links.get(base.link) if base else None
            link_up = ln is None or ln.up
            alert = sum(q.ready.values())
            col = p["ok"] if alert and link_up else p["warn"] if link_up else p["bad"]
            self._tile(gui, rr, q.name, f"{self._name(base) if base else ''} · {q.type_id}", col, p)
            self._lamp(gui, (rr.x + 9, rr.y + 9), col, True, blink=not link_up, r=4)
            # alert board: aircraft per readiness bucket
            x = rr.x + 18
            for k, v in sorted(q.ready.items(), key=lambda kv: float(kv[0])):
                gui.label((x, rr.y + 29), f"{float(k):g}'", 10, p["text_dim"], "eng_r")
                gui.label((x + 20, rr.y + 27), str(v), 13, p["lamp"] if v else p["text_dim"], "crt")
                x += 40
            if q.airborne:
                gui.label((rr.right - 8, rr.y + 27), f"AIR {q.airborne}", 11, p["ok"], "eng", "right")
            pts = [(rr.x, y), (bus2, y)]
            if link_up:
                self._wire(s, pts, p["line"], 2)
                self._pulses(s, pts, p["line"], 26.0, i * 7.0, toward_end=False)
            else:
                self._wire(s, pts, p["bad"], 2, dashed=True)
                self._lamp(gui, ((rr.x + bus2) // 2, y), p["bad"], True, blink=True, r=4)
            self.nodes.append((rr, "squadron", q.id))
        if not wide:
            for i, sm in enumerate(sams):
                y = int(top2 + step2 * (len(sqs) + i) + step2 / 2)
                ys2.append(y)
                rr = R(r.right - 16 - cw, y - 23, cw, 46)
                link_up, col = self._sam_tile(gui, rr, sm, sel, p)
                pts = [(rr.x, y), (bus2, y)]
                if link_up:
                    self._wire(s, pts, p["line"], 2)
                    self._pulses(s, pts, p["line"], 20.0, i * 9.0)
                else:
                    self._wire(s, pts, p["bad"], 2, dashed=True)
                    self._lamp(gui, ((rr.x + bus2) // 2, y), p["bad"], True, blink=True, r=4)
                self.nodes.append((rr, "sam", sm.id))
        if ys2:
            self._wire(s, [(bus2, min(ys2 + [cy])), (bus2, max(ys2 + [cy]))], p["line"], 3)
            self._wire(s, [(cmd.right, cy), (bus2, cy)], p["line"], 3)
            self._pulses(s, [(cmd.right, cy), (bus2, cy)], p["line"], 26.0, 5.0)
        # ---- missile units (bottom)
        if sams and wide:
            busy = r.bottom - 120
            gap = min(250, (r.w - 40) // max(1, len(sams)))
            x0 = cx - gap * (len(sams) - 1) / 2
            self._wire(s, [(cx, cmd.bottom), (cx, busy)], p["line"], 3)
            xs = [int(x0 + gap * i) for i in range(len(sams))]
            self._wire(s, [(min(xs + [cx]), busy), (max(xs + [cx]), busy)], p["line"], 3)
            for i, sm in enumerate(sams):
                x = xs[i]
                rr = R(x - min(110, gap // 2 - 6), busy + 40, min(220, gap - 12), 46)
                link_up, col = self._sam_tile(gui, rr, sm, sel, p)
                pts = [(x, busy), (x, rr.y)]
                if link_up:
                    self._wire(s, pts, p["line"], 2)
                    self._pulses(s, pts, p["line"], 20.0, i * 9.0)
                else:
                    self._wire(s, pts, p["bad"], 2, dashed=True)
                self.nodes.append((rr, "sam", sm.id))
            self._pulses(s, [(cx, cmd.bottom), (cx, busy)], p["line"], 20.0, 1.0)
        # ---- message traffic counters
        unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
        lines_down = [ln for ln in w.links.values() if not ln.up]
        jam_sites = sum(1 for st in w.radars.values() if w.active_jammers(st))
        cells = [(f"TRACKS {sum(1 for t in w.tracks.values() if not t.lost):>3}", p["text"]),
                 (f"UNACK {unacked:>2}", p["bad"] if unacked else p["text"]),
                 (f"LINES DOWN {len(lines_down)}", p["bad"] if lines_down else p["text"]),
                 (f"JAMMED {jam_sites}", p["warn"] if jam_sites else p["text"])]
        if wide:
            info = R(cmd.x - 10, cmd.bottom + 16, cmd.w + 20, 52)
            spots = [(10, 6), (120, 6), (10, 26), (120, 26)]
        else:
            info = R(cmd.x, cmd.bottom + 16, cmd.w, 90)
            spots = [(10, 6), (10, 26), (10, 46), (10, 66)]
        pygame.draw.rect(s, p["tile"], info, border_radius=3)
        pygame.draw.rect(s, p["line_dim"], info, 1, border_radius=3)
        for (txt, col), (dx, dy) in zip(cells, spots):
            gui.label((info.x + dx, info.y + dy), txt, 12, col, "eng")
        s.set_clip(None)

    def _sam_tile(self, gui, rr, sm, sel, p):
        w = self.world
        st = w.catalog.sams[sm.type_id]
        ln = w.links.get(sm.link)
        link_up = ln is None or ln.up
        ready = w.t >= sm.t_ready
        col = p["bad"] if sm.status != "ok" or not link_up else p["ok"] if ready else p["warn"]
        if sm.state in ("locked", "engaging"):
            col = p["lamp"]
        self._tile(gui, rr, self._name(sm), f"{st.id} · {sm.ready_missiles} msl · {sm.state.upper()}", col, p,
                   sel.get("sam") == sm.id)
        self._lamp(gui, (rr.x + 9, rr.y + 9), col, True, blink=sm.state == "engaging", r=4)
        return link_up, col

    def pick(self, pos) -> tuple[str, str] | None:
        for rr, kind, oid in self.nodes:
            if rr.collidepoint(pos):
                return kind, oid
        return None
