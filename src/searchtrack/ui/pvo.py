"""The PVO command post: the same simulation as the SAGE direction center, in a different room.

An operator's desk on the left; the wall plotting board in the middle, edge-lit glass in a
riveted steel frame rather than a cathode-ray tube; on the right the guidance-point cabinet
with a Moscow-time wall clock, the signal lamps, the live scope of the selected guidance
point and the switchboard of radar-company lines. Messages arrive on teleprinter tape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pygame
from pygame import Rect

from .theme import TEXT

R = Rect


@dataclass(frozen=True)
class Layout:
    pvo: bool
    display: Rect                  # situation display / plotting board / scope / network
    tabs: Rect                     # console selector keys
    console: Rect                  # operator console
    ticker: Rect                   # message line (LED ticker or teleprinter tape)
    housing: Optional[Rect] = None  # SAGE display console housing
    strip: Optional[Rect] = None    # PVO: keys under the board
    cabinet: Optional[Rect] = None  # PVO: guidance-point cabinet
    pip: Optional[Rect] = None      # PVO: the cabinet's live scope


US_LAYOUT = Layout(False, display=R(22, 70, 954, 690), tabs=R(1000, 58, 596, 30), console=R(1000, 94, 596, 770),
                   ticker=R(8, 870, 1584, 26), housing=R(4, 56, 990, 808))
PVO_LAYOUT = Layout(True, display=R(624, 24, 650, 768), tabs=R(8, 8, 588, 30), console=R(4, 44, 596, 820),
                    ticker=R(8, 872, 1278, 24), strip=R(606, 808, 684, 58), cabinet=R(1296, 0, 304, 900),
                    pip=R(1309, 326, 278, 278))

WALL = (24, 28, 30)
STEEL = (92, 98, 100)
STEEL_HI = (150, 156, 156)
STEEL_LO = (40, 44, 46)
CREAM = (236, 232, 214)
INK = (28, 28, 26)
RED_PLATE = (122, 28, 22)
SPEEDS_LAB = ["II", "1×", "2×", "4×", "8×", "16×", "32×"]


# ------------------------------------------------------------------ static surfaces
def _room(size) -> pygame.Surface:
    w, h = size
    rng = np.random.default_rng(19)
    n = rng.normal(0, 3.0, (w, h)).astype(np.float32)
    yy = np.linspace(0, 1, h, dtype=np.float32)[None, :]
    base = np.array(WALL, np.float32)[None, None, :] * (0.85 + 0.25 * (1 - yy))[..., None]
    img = np.clip(base + n[..., None], 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(img)


def _riveted_frame(size, inner: Rect) -> pygame.Surface:
    """Steel frame of the plotting board, with rivets; the inside is transparent."""
    S = pygame.Surface(size, pygame.SRCALPHA)
    body = S.get_rect()
    pygame.draw.rect(S, STEEL_LO, body, border_radius=6)
    for i in range(10):
        f = i / 9.0
        col = tuple(int(a + (b - a) * f) for a, b in zip(STEEL_HI, STEEL))
        pygame.draw.rect(S, col, body.inflate(-2 - i, -2 - i), 1, border_radius=6)
    pygame.draw.rect(S, STEEL, body.inflate(-20, -20))
    pygame.draw.rect(S, STEEL_LO, inner.inflate(10, 10))
    pygame.draw.rect(S, (14, 16, 16), inner.inflate(4, 4))
    pygame.draw.rect(S, (0, 0, 0, 0), inner)
    step = 46
    for x in range(body.x + 14, body.right - 10, step):
        for y in (body.y + 8, body.bottom - 9):
            pygame.draw.circle(S, STEEL_LO, (x + 1, y + 1), 3)
            pygame.draw.circle(S, STEEL_HI, (x, y), 3)
    for y in range(body.y + 14 + step // 2, body.bottom - 14, step):
        for x in (body.x + 8, body.right - 9):
            pygame.draw.circle(S, STEEL_LO, (x + 1, y + 1), 3)
            pygame.draw.circle(S, STEEL_HI, (x, y), 3)
    return S


def _glass(size) -> pygame.Surface:
    """Edge-lit acrylic: light pools along the edges and a soft diagonal reflection."""
    w, h = size
    xs = np.linspace(0, 1, w, dtype=np.float32)[:, None]
    ys = np.linspace(0, 1, h, dtype=np.float32)[None, :]
    edge = np.minimum(np.minimum(xs, 1 - xs) * w, np.minimum(ys, 1 - ys) * h)
    glow = np.exp(-edge / 26.0) * 46.0
    streak = np.exp(-((xs * 0.8 - ys + 0.15) / 0.06) ** 2) * 16.0 + np.exp(-((xs * 0.8 - ys + 0.32) / 0.02) ** 2) * 10.0
    a = np.clip(glow + streak, 0, 90)
    S = pygame.Surface(size, pygame.SRCALPHA)
    S.fill((200, 236, 230, 0))
    alpha = pygame.surfarray.pixels_alpha(S)
    alpha[:, :] = a.astype(np.uint8)
    del alpha
    return S


# ------------------------------------------------------------------ the room
def back(gui, scene) -> None:
    """Wall, desk and cabinet body, drawn before the displays."""
    L = scene.L
    s = gui.screen
    s.blit(gui.cached(("pvo_room", s.get_size()), lambda: _room(s.get_size())), (0, 0))
    gui.panel(R(0, 0, 604, 900), screws=True)                     # operator's desk
    gui.panel(L.cabinet, screws=True)                              # guidance-point cabinet
    pygame.draw.rect(s, (0, 0, 0), L.display)


def board_finish(gui, scene, r: Rect) -> None:
    """Glass over the plotting board instead of a phosphor and scanlines."""
    gui.screen.blit(gui.cached(("pvo_glass", r.w, r.h), lambda: _glass(r.size)), r.topleft)


def board_frame(gui, scene) -> None:
    L = scene.L
    s = gui.screen
    fr = L.display.inflate(36, 36)
    fr.height = L.strip.y - fr.y - 2
    inner = Rect(L.display.x - fr.x, L.display.y - fr.y, L.display.w, L.display.h)
    s.blit(gui.cached(("pvo_frame", fr.size), lambda: _riveted_frame(fr.size, inner)), fr.topleft)
    title = {"map": "PLOTTING BOARD · AIR SITUATION", "scope": "GUIDANCE POINT SCOPE",
             "net": "WARNING AND CONTROL NETWORK"}[scene.mode]
    t = TEXT.render(title, 11, CREAM, "eng")
    plate = R(fr.centerx - t.get_width() // 2 - 12, fr.y + 3, t.get_width() + 24, 15)
    pygame.draw.rect(s, RED_PLATE, plate, border_radius=2)
    pygame.draw.rect(s, (60, 12, 10), plate, 1, border_radius=2)
    s.blit(t, (plate.x + 12, plate.y))


def strip(gui, scene) -> None:
    """Keys on the board's sill: what the board shows and which layers are drawn."""
    th = scene.theme
    w = scene.world
    r = scene.L.strip
    gui.panel(r, screws=False)
    x, y = r.x + 10, r.y + 6
    for m, lab in (("map", "BOARD"), ("scope", "RADAR SCOPE"), ("net", "NETWORK")):
        if gui.button(R(x, y, 98, 26), lab, lit=scene.mode == m, size=11,
                      tip="M cycles the board: plotting board / guidance-point scope / network"):
            scene.mode = m
        x += 101
    x += 10
    lay = scene.map.layers
    for key, lab, tip in (("coverage", "COVERAGE", "Predicted radar coverage at the selected altitude (C)"),
                          ("zones", "ZONES", "Zones and the army's boundary"), ("labels", "LABELS", "Names on the board"),
                          ("history", "HISTORY", "Reported positions with their times"),
                          ("rings", "RINGS", "Range rings and missile engagement rings")):
        if gui.button(R(x, y, 64, 26), lab, lit=lay[key], size=10, tip=tip):
            lay[key] = not lay[key]
            if key in ("zones", "labels"):
                scene.map._base_key = None
        x += 66
    y2 = r.y + 36
    gui.eng((r.x + 12, y2 + 2), "COVERAGE ALTITUDE", 11, color=th.engraving, strip=False)
    x = r.x + 140
    if gui.button(R(x, y2, 34, 18), "DN", size=9, tip="Coverage altitude down ([)"):
        scene._cov_alt(-1)
    gui.label((x + 44, y2 + 1), f"{scene.map.cov_alt:,.0f} m", 12, th.engraving, "eng")
    if gui.button(R(x + 118, y2, 34, 18), "UP", size=9, tip="Coverage altitude up (])"):
        scene._cov_alt(1)
    nt = sum(1 for t in w.tracks.values() if not t.lost)
    gui.lamp((r.right - 196, y2 + 9), th.lamp_green, True, radius=5)
    gui.eng((r.right - 186, y2 + 2), "BOARD LIT", 11, color=th.engraving, strip=False)
    gui.eng((r.right - 92, y2 + 2), "TARGETS", 11, color=th.engraving, strip=False)
    gui.led(R(r.right - 40, y2 - 1, 30, 20), f"{nt:02d}", (255, 64, 36), 15)


# ------------------------------------------------------------------ the cabinet
def _clock_face(radius: int) -> pygame.Surface:
    d = radius * 2 + 16
    S = pygame.Surface((d * 2, d * 2), pygame.SRCALPHA)       # drawn at 2x, scaled down for smooth edges
    c = (d, d)
    R2 = radius * 2
    pygame.draw.circle(S, (12, 12, 12), (c[0] + 4, c[1] + 6), R2 + 16)
    for i in range(16):
        f = i / 15.0
        col = tuple(int(a + (b - a) * f) for a, b in zip((200, 204, 204), (90, 94, 96)))
        pygame.draw.circle(S, col, c, R2 + 16 - i)
    pygame.draw.circle(S, CREAM, c, R2)
    for k in range(60):
        a = math.radians(k * 6)
        r0 = R2 - (22 if k % 5 == 0 else 10)
        wdt = 5 if k % 5 == 0 else 2
        pygame.draw.line(S, INK, (c[0] + r0 * math.sin(a), c[1] - r0 * math.cos(a)),
                         (c[0] + (R2 - 4) * math.sin(a), c[1] - (R2 - 4) * math.cos(a)), wdt)
    f = TEXT.font("eng", int(R2 * 0.22))
    for h in range(1, 13):
        a = math.radians(h * 30)
        t = f.render(str(h), True, INK)
        rr = R2 * 0.70
        S.blit(t, (c[0] + rr * math.sin(a) - t.get_width() / 2, c[1] - rr * math.cos(a) - t.get_height() / 2))
    lab = TEXT.font("eng_r", int(R2 * 0.11)).render("MOSCOW TIME", True, (90, 86, 76))
    S.blit(lab, (c[0] - lab.get_width() / 2, c[1] + R2 * 0.30))
    return pygame.transform.smoothscale(S, (d, d))


def _hand(s, c, ang_deg: float, length: float, width: int, col, tail: float = 0.0) -> None:
    a = math.radians(ang_deg)
    dx, dy = math.sin(a), -math.cos(a)
    px, py = -dy, dx
    tip = (c[0] + dx * length, c[1] + dy * length)
    back_ = (c[0] - dx * tail, c[1] - dy * tail)
    pts = [(back_[0] + px * width, back_[1] + py * width), (tip[0] + px * width * 0.3, tip[1] + py * width * 0.3),
           (tip[0] - px * width * 0.3, tip[1] - py * width * 0.3), (back_[0] - px * width, back_[1] - py * width)]
    pygame.draw.polygon(s, (0, 0, 0, 90), [(x + 2, y + 3) for x, y in pts])
    pygame.draw.polygon(s, col, pts)


def wall_clock(gui, scene, c, radius: int) -> None:
    from .mapview import clock
    s = gui.screen
    face = gui.cached(("pvo_clock", radius), lambda: _clock_face(radius))
    s.blit(face, (c[0] - face.get_width() // 2, c[1] - face.get_height() // 2))
    hh, mm = (int(v) for v in clock(scene.world, scene.render_t).split(":"))
    ss = int(scene.render_t) % 60
    _hand(s, c, (hh % 12 + mm / 60.0) * 30.0, radius * 0.52, 4, INK, 8)
    _hand(s, c, (mm + ss / 60.0) * 6.0, radius * 0.80, 3, INK, 10)
    a = math.radians(ss * 6.0)
    pygame.draw.line(s, (196, 30, 24), (c[0] - 12 * math.sin(a), c[1] + 12 * math.cos(a)),
                     (c[0] + radius * 0.86 * math.sin(a), c[1] - radius * 0.86 * math.cos(a)), 2)
    pygame.draw.circle(s, (196, 30, 24), c, 4)


def cabinet(gui, scene) -> None:
    th = scene.theme
    w = scene.world
    s = gui.screen
    cab = scene.L.cabinet
    x0 = cab.x + 12
    # unit plate
    plate = R(x0, 10, cab.w - 24, 40)
    pygame.draw.rect(s, (0, 0, 0), plate.move(1, 2), border_radius=3)
    pygame.draw.rect(s, RED_PLATE, plate, border_radius=3)
    pygame.draw.rect(s, (70, 14, 10), plate, 1, border_radius=3)
    head = (w.hq.name if w.battle.active and w.hq.name else th.subtitle).upper()
    gui.label((plate.centerx, plate.y + 3), head, 13, CREAM, "eng", "center")
    title = w.title.upper()
    while TEXT.width(title, 11, "eng_r") > plate.w - 12 and len(title) > 8:
        title = title[:-2]
    gui.label((plate.centerx, plate.y + 22), title, 11, (226, 200, 190), "eng_r", "center")
    # wall clock and the elapsed watch
    wall_clock(gui, scene, (cab.x + 92, 128), 66)
    gui.eng((cab.x + 178, 74), "WATCH", 11, color=th.engraving, strip=False)
    gui.led(R(cab.x + 178, 92, 104, 30), f"+{int(scene.render_t // 60):03d}", (255, 64, 36), 22)
    gui.eng((cab.x + 178, 130), "MIN", 10, color=th.engraving_dim, strip=False)
    if gui.button(R(cab.x + 178, 150, 104, 30), "MENU", size=12, tip="Esc"):
        scene.menu = True
    # time keys
    y = 206
    gui.eng((x0, y - 2), "TIME", 11, color=th.engraving, strip=False)
    bw = 40
    for i, lab in enumerate(SPEEDS_LAB):
        rr = R(x0 + 44 + (i % 4) * (bw + 4), y + (i // 4) * 30 - 6, bw, 26)
        if gui.button(rr, lab, lit=scene.speed_i == i and not scene.advancing, size=11,
                      tip="Pause" if i == 0 else f"Time compression {lab}"):
            scene.set_speed(i)
    adv = R(x0 + 44 + 3 * (bw + 4), y + 24, bw * 1 + 0, 26)
    adv.width = cab.right - 12 - adv.x
    if gui.button(adv, "ADVANCE", lit=scene.advancing, size=10, color=th.lamp_amber,
                  tip="Run fast until something needs you (Enter)"):
        scene.toggle_advance()
    # signal lamps
    y = 270
    hq = w.hq
    down = sum(1 for ln in w.links.values() if not ln.up)
    unacked = sum(1 for m in w.messages if m.ack and not m.acked and m.delivered)
    lamps = [("READINESS", hq.readiness or "—", th.lamp_red if hq.readiness == "FULL" else th.lamp_amber, True, False),
             ("FIRE", {"HOLD": "FORBIDDEN", "TIGHT": "LIMITED", "FREE": "PERMITTED"}.get(hq.weapons_status,
                                                                                   hq.weapons_status),
              {"HOLD": th.lamp_green, "TIGHT": th.lamp_amber, "FREE": th.lamp_red}.get(hq.weapons_status, th.lamp_white),
              True, hq.weapons_status == "FREE"),
             ("LINES", "OK" if not down else f"{down} DOWN", th.lamp_green if not down else th.lamp_red, True, bool(down)),
             ("ACK", str(unacked), th.lamp_red, unacked > 0, unacked > 0)]
    cw = (cab.w - 24) // len(lamps)
    for i, (lab, val, col, on, blink) in enumerate(lamps):
        cx = x0 + cw * i + cw // 2
        gui.lamp((cx, y + 12), col, on, radius=10, blink=blink, tip=f"{lab}: {val}")
        gui.label((cx, y + 27), lab, 10, th.engraving, "eng", "center")
        gui.label((cx, y + 39), val, 9, th.engraving_dim, "eng_r", "center")
        if lab == "ACK" and unacked and gui.clicked(R(cx - 14, y - 2, 28, 28)):
            scene.cmd("ack_all")
    # the guidance-point scope
    pip = scene.L.pip
    pygame.draw.rect(s, (14, 14, 13), pip.inflate(10, 10), border_radius=8)
    scene.draw_pip(gui)
    y = pip.bottom + 10
    if gui.button(R(x0, y, 30, 26), "<", size=12, tip="Previous radar (,)"):
        scene._cycle_radar(-1)
    site = w.radars.get(scene.scope.site_id)
    ro = R(x0 + 34, y + 1, cab.w - 24 - 68 - 70, 24)
    nm = f"{short_name(site.name)} {site.type_id}" if site else "—"
    gui.readout(ro, [_clip(nm, 11, "ui", ro.w - 12)], 11)
    if gui.button(R(cab.right - 12 - 30 - 70, y, 30, 26), ">", size=12, tip="Next radar (.)"):
        scene._cycle_radar(1)
    if gui.button(R(cab.right - 12 - 66, y, 66, 26), "RANGE", size=10, tip="Scope range (R)"):
        scene.scope.cycle_range(1)
        scene.pip.cycle_range(1)
    # radar-company lines: a switchboard of lamps
    y += 34
    gui.eng((x0, y), "RADAR COMPANY LINES", 11, color=th.engraving, strip=False)
    y += 18
    colw = (cab.w - 24) // 2
    items = []
    for st in w.radars.values():
        link = w.links.get(st.link)
        bad = st.status == "down" or (link is not None and not link.up)
        col = th.lamp_red if bad else th.lamp_amber if st.status in ("degraded", "maint") else th.lamp_green
        items.append((short_name(st.name), "", col, bad, st.id == scene.scope.site_id,
                      lambda sid=st.id: scene.select("site", sid), f"{st.name} ({st.type_id}): {st.status}"))
    y = _lamp_rows(gui, scene, x0, y, colw, items, 2, 21)
    # forces: fighter regiments and missile battalions
    y += 8
    bottom = cab.bottom - 14
    sams = list(w.sams.values())
    cols = [x0] if not sams else [x0, x0 + colw]
    cw = (cab.w - 24) if not sams else colw
    wi = next((i for i, c in enumerate(scene.consoles) if c.name == "WEAPONS"), 1)
    mi = next((i for i, c in enumerate(scene.consoles) if c.name == "MISSILES"), 2)
    regs = []
    for q in w.squadrons.values():
        ready = sum(q.ready.values())
        col = th.lamp_green if ready else th.lamp_amber if q.airborne or q.recovering else th.lamp_red
        regs.append((q.name, f"{ready}+{q.airborne}", col, False, scene.consoles[wi].sq == q.id and scene.ci == wi,
                     lambda qid=q.id: _open_squadron(scene, wi, qid),
                     f"{q.name}: {ready} on alert, {q.airborne} airborne, {len(q.recovering)} turning round"))
    gui.eng((cols[0], y), "FIGHTER REGIMENTS", 11, color=th.engraving, strip=False)
    nrow = max(1, (bottom - y - 18) // 20)
    _lamp_rows(gui, scene, cols[0], y + 18, cw, regs[:nrow], 1, 20)
    if sams:
        bats = []
        for m in sams:
            ok = m.status == "ok"
            busy = m.state in ("locked", "engaging")
            col = th.lamp_red if not ok else th.lamp_amber if busy or w.t < m.t_ready else th.lamp_green
            bats.append((short_name(m.name), str(m.ready_missiles), col, busy, scene.sel.get("sam") == m.id and scene.ci == mi,
                         lambda sid=m.id: _open_sam(scene, mi, sid),
                         f"{m.name} ({m.type_id}): {m.state}, {m.ready_missiles} missiles on the rails"))
        gui.eng((cols[1], y), "MISSILE BATTALIONS", 11, color=th.engraving, strip=False)
        _lamp_rows(gui, scene, cols[1], y + 18, cw, bats[:nrow], 1, 20)


def short_name(name: str) -> str:
    return (name.replace("Radar company ", "").replace(" guidance point", " GP").replace(" Guidance Point", " GP")
            .replace("Fighter regiment ", "").replace("SAM battalion ", "").replace("SAM site ", ""))


def _clip(text: str, size: int, kind: str, width: int) -> str:
    if TEXT.width(text, size, kind) <= width:
        return text
    while len(text) > 2 and TEXT.width(text + "…", size, kind) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _lamp_rows(gui, scene, x, y, colw, items, ncols, rh) -> int:
    """Rows of lamp + name (+ count) on the cabinet; clicking a row calls its action. Returns the y below."""
    s = gui.screen
    rows = (len(items) + ncols - 1) // max(1, ncols)
    for i, (name, count, col, blink, sel, act, tip) in enumerate(items):
        rr = R(x + (i // rows) * colw, y + (i % rows) * rh, colw - 6, rh - 3)
        pygame.draw.rect(s, (52, 58, 60) if sel else (16, 18, 18), rr, border_radius=3)
        if sel:
            pygame.draw.rect(s, CREAM, rr, 1, border_radius=3)
        gui.lamp((rr.x + 10, rr.centery), col, True, radius=5, blink=blink)
        cw = TEXT.width(count, 11, "ui") + 6 if count else 0
        size = 11 if TEXT.width(name, 11, "eng_r") <= rr.w - 24 - cw else 10
        gui.label((rr.x + 20, rr.centery - 7), _clip(name, size, "eng_r", rr.w - 24 - cw), size,
                  CREAM if sel else (190, 192, 186), "eng_r")
        if count:
            gui.label((rr.right - 5, rr.centery - 7), count, 11, (255, 196, 110), "ui", align="right")
        gui.tip(rr, tip)
        if gui.clicked(rr):
            act()
    return y + rows * rh


def _open_squadron(scene, wi: int, qid: str) -> None:
    scene.consoles[wi].sq = qid
    scene.ci = wi


def _open_sam(scene, mi: int, sid: str) -> None:
    scene.select("sam", sid)
    scene.ci = mi


# ------------------------------------------------------------------ teleprinter tape
def tape(gui, scene) -> None:
    from .mapview import clock
    w = scene.world
    s = gui.screen
    r = scene.L.ticker
    pygame.draw.rect(s, (0, 0, 0), r.inflate(4, 4).move(1, 2))
    pygame.draw.rect(s, (226, 218, 190), r)
    for xx in range(r.x + 4, r.right, 9):                  # feed holes
        pygame.draw.circle(s, (176, 168, 140), (xx, r.y + 3), 1)
    msgs = [m for m in w.messages if m.delivered][-1:]
    for m in msgs:
        col = (150, 30, 20) if m.priority >= 2 else (34, 32, 28)
        txt = f"{clock(w, m.t_deliver)} {m.sender}: {m.text}".upper()
        gui.label((r.x + 10, r.y + 6), txt[:150], 12, col, "cyr")
    # the torn end of the tape
    pts = [(r.right - 1, r.y)] + [(r.right - 1 - (6 if k % 2 else 0), r.y + k * 4) for k in range(1, r.h // 4)] + \
          [(r.right - 1, r.bottom)]
    pygame.draw.lines(s, (150, 140, 116), False, pts, 1)
