"""PPI radar scope with phosphor persistence.

Paints come straight from the simulation: each carries the instant the
antenna crossed the target, so a blip appears exactly as the drawn sweep
passes it, at a brightness set by its signal-to-noise ratio. Ground clutter,
noise grass, weather and jamming strobes are rendered from the same model
(clutter map from the terrain horizon mask, threshold and MTI settings)."""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

from ..sim.geo import NM, bearing_deg, heading_vec
from ..sim.radar import integrated_snr_db, snr_for_pd
from .fx import glow_stamp, scanlines
from .theme import TEXT, Theme


class Scope:
    def __init__(self, world, theme: Theme, rect: pygame.Rect, compact: bool = False):
        self.world = world
        self.theme = theme
        self.rect = rect
        self.compact = compact            # a small instrument tube: thin bezel, no legends
        self.D = min(rect.w, rect.h) - (34 if compact else 96)
        self.R = self.D // 2
        self.center = (rect.centerx, rect.centery) if compact else (rect.centerx, rect.centery + 14)
        self.site_id = next(iter(world.radars), "")
        self.range_km = 0.0
        self.glow = pygame.Surface((self.D, self.D))
        self.flash = pygame.Surface((self.D, self.D))
        self.last_t = world.t
        self.decay_acc = 0.0
        self.stamps = {r: glow_stamp(r, theme.scope_glow) for r in (2, 3, 4, 6)}
        self.fstamps = {r: glow_stamp(r, theme.scope_flash) for r in (2, 3, 4, 6)}
        self.clutter: dict[str, list] = {}
        self.rng = random.Random(3)
        self.scan = scanlines((self.D, self.D), 40, 3)
        self._mask = pygame.Surface((self.D, self.D), pygame.SRCALPHA)
        self._mask.fill((255, 255, 255, 0))
        pygame.draw.circle(self._mask, (255, 255, 255, 255), (self.R, self.R), self.R)
        self.comp = pygame.Surface((self.D, self.D), pygame.SRCALPHA)
        self.set_site(self.site_id)

    def set_site(self, sid: str) -> None:
        if sid not in self.world.radars:
            return
        self.site_id = sid
        rt = self.world.catalog.radars[self.world.radars[sid].type_id]
        opts = self.range_options()
        self.range_km = min(opts, key=lambda r: abs(r - min(rt.range_km, 370.0)))
        self.glow.fill((0, 0, 0))
        self.flash.fill((0, 0, 0))
        self.last_t = self.world.t

    def range_options(self) -> list[float]:
        if self.theme.units == "imperial":
            return [50 * NM, 100 * NM, 200 * NM]
        return [50.0, 100.0, 200.0, 300.0]

    def cycle_range(self, d: int) -> None:
        opts = self.range_options()
        i = min(range(len(opts)), key=lambda k: abs(opts[k] - self.range_km))
        self.range_km = opts[(i + d) % len(opts)]
        self.glow.fill((0, 0, 0))
        self.flash.fill((0, 0, 0))

    # ------------------------------------------------------------ helpers
    def to_px(self, az: float, r: float) -> tuple[int, int]:
        f = r / self.range_km * self.R
        a = math.radians(az)
        return int(self.R + f * math.sin(a)), int(self.R - f * math.cos(a))

    def to_world(self, sx: int, sy: int):
        site = self.world.radars[self.site_id]
        dx = (sx - self.center[0]) / self.R * self.range_km
        dy = -(sy - self.center[1]) / self.R * self.range_km
        if math.hypot(dx, dy) > self.range_km:
            return None
        return site.x + dx, site.y + dy

    def _clutter_for(self, site) -> list:
        key = f"{site.id}:{site.k_override}"
        c = self.clutter.get(key)
        if c is None:
            w = self.world
            rt = w.catalog.radars[site.type_id]
            m = w.mask_for(site)
            c = []
            r = (np.arange(m.n_r) + 0.5) * m.dr
            cell = r * 1000.0 * math.radians(rt.az_beam_deg) * 150.0 * rt.pulse_us
            ref = integrated_snr_db(rt, 100.0, 1.0)
            for i in range(m.n_az):
                s0 = m.clutter[i]
                ok = s0 > -900
                cnr = ref - 40 * np.log10(np.maximum(r, 0.5) / 100.0) + s0 + 10 * np.log10(np.maximum(cell, 1.0))
                sel = ok & (cnr > -3.0)
                c.append(list(zip(r[sel].tolist(), cnr[sel].tolist())))
            self.clutter[key] = c
        return c

    # ------------------------------------------------------------ draw
    def draw(self, screen: pygame.Surface, render_t: float, dt_real: float, speed: float) -> None:
        w = self.world
        th = self.theme
        site = w.radars.get(self.site_id)
        if site is None:
            return
        rt = w.catalog.radars[site.type_id]
        # persistence decay (real time)
        self.decay_acc += dt_real
        while self.decay_acc >= 0.1:
            self.decay_acc -= 0.1
            g = int(255 * 0.5 ** (0.1 / 3.5))
            fl = int(255 * 0.5 ** (0.1 / 0.35))
            self.glow.fill((g, g, g), special_flags=pygame.BLEND_MULT)
            self.glow.fill((1, 1, 1), special_flags=pygame.BLEND_SUB)
            self.flash.fill((fl, fl, fl), special_flags=pygame.BLEND_MULT)
            self.flash.fill((2, 2, 2), special_flags=pygame.BLEND_SUB)
        az_now = (site.az - 6.0 * site.rpm * (w.t - render_t)) % 360.0
        az_prev = (site.az - 6.0 * site.rpm * (w.t - self.last_t)) % 360.0
        swept = (az_now - az_prev) % 360.0 if render_t > self.last_t else 0.0
        if render_t - self.last_t >= 60.0 / site.rpm - 1e-6 or (swept < 1e-6 and render_t > self.last_t + 1.0):
            swept = 359.9
        up = site.status not in ("down", "maint")
        thr = snr_for_pd(0.5, 10 ** (-site.pfa_exp))
        if up and swept > 0:
            self._paint_new(site, rt, render_t, thr)
            self._paint_clutter(site, rt, az_prev, swept)
            self._paint_noise(site, rt, az_prev, swept)
        self.last_t = render_t
        # compose on an offscreen disc, then mask it round
        comp = self.comp
        comp.fill((*th.scope_bg, 255))
        comp.blit(self.glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        comp.blit(self.flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        c0 = (self.R, self.R)
        ring_col = tuple(int(v * 0.32) for v in th.scope_glow)
        step = 50 * NM if th.units == "imperial" else 50.0
        if self.range_km <= 100.0:
            step /= 2.0
        r = step
        while r <= self.range_km + 1e-6:
            pygame.draw.circle(comp, ring_col, c0, int(r / self.range_km * self.R), 1)
            r += step
        for a in range(0, 360, 30):
            ra = math.radians(a)
            pygame.draw.line(comp, ring_col, (c0[0] + self.R * 0.97 * math.sin(ra), c0[1] - self.R * 0.97 * math.cos(ra)),
                             (c0[0] + self.R * math.sin(ra), c0[1] - self.R * math.cos(ra)), 1)
        if up:
            for k in range(24, -1, -1):
                a = math.radians(az_now - k * 0.7)
                f = (1.0 - k / 25.0) ** 2.5
                col = tuple(int(v * (0.15 + 0.85 * f)) for v in (th.scope_flash if k == 0 else th.scope_glow))
                pygame.draw.line(comp, col, c0, (c0[0] + self.R * math.sin(a), c0[1] - self.R * math.cos(a)),
                                 2 if k == 0 else 1)
        comp.blit(self.scan, (0, 0))
        comp.blit(self._mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        cx, cy = self.center
        top = (cx - self.R, cy - self.R)
        screen.blit(comp, top)
        self._bezel(screen, site, rt, up)

    def _paint_new(self, site, rt, render_t, thr) -> None:
        paints = self.world.paints.get(site.id)
        if not paints:
            return
        new = []
        for p in reversed(paints):
            if p.t <= self.last_t:
                break
            if p.t <= render_t:
                new.append(p)
        bw = max(rt.az_beam_deg, 0.8)
        for p in new:
            if p.r > self.range_km and p.kind != "strobe":
                continue
            if p.kind == "strobe":
                inten = min(1.0, (p.snr - 6.0) / 30.0)
                n = int(40 * inten) + 10
                for _ in range(n):
                    rr = self.rng.random() * self.range_km
                    x, y = self.to_px(p.az + self.rng.uniform(-bw, bw) * 0.7, rr)
                    self._dot(x, y, 2, inten * 0.7)
                continue
            if p.kind == "weather":
                n = max(6, int(p.size * 0.8))
                for _ in range(n):
                    rr = p.r + self.rng.uniform(-p.size, p.size)
                    aa = p.az + math.degrees(self.rng.uniform(-p.size, p.size) / max(p.r, 1.0))
                    if 0 < rr < self.range_km:
                        x, y = self.to_px(aa, rr)
                        self._dot(x, y, 2, 0.25 + 0.4 * self.rng.random())
                continue
            inten = max(0.12, min(1.0, (p.snr - thr + 9.0) / 22.0))
            if p.sub:
                inten *= 0.45
            if p.kind == "false":
                x, y = self.to_px(p.az, p.r)
                self._dot(x, y, 2, inten * 0.8)
                continue
            rad = 3 if p.size <= 1 else 4
            steps = max(2, int(bw * 1.6))
            for i in range(steps):
                aa = p.az - bw / 2 + bw * i / max(steps - 1, 1)
                x, y = self.to_px(aa, p.r)
                self._dot(x, y, rad, inten)

    def _dot(self, x: int, y: int, r: int, inten: float) -> None:
        if not (0 <= x < self.D and 0 <= y < self.D):
            return
        rr = 2 if r <= 2 else 3 if r == 3 else 4
        st = self.stamps[rr]
        fs = self.fstamps[rr]
        g = st.copy()
        g.fill((int(255 * inten),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        self.glow.blit(g, (x - rr, y - rr), special_flags=pygame.BLEND_ADD)
        f = fs.copy()
        f.fill((int(255 * min(1.0, inten * 1.2)),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        self.flash.blit(f, (x - rr, y - rr), special_flags=pygame.BLEND_ADD)

    def _paint_clutter(self, site, rt, az0: float, swept: float) -> None:
        cl = self._clutter_for(site)
        n = len(cl)
        mti = site.mti and rt.mti
        i0 = int(az0 / 360.0 * n)
        i1 = int((az0 + swept) / 360.0 * n)
        thr = snr_for_pd(0.5, 10 ** (-site.pfa_exp))
        col = self.theme.scope_glow
        for i in range(i0, i1 + 1):
            for r, cnr in cl[i % n]:
                if r > self.range_km:
                    break
                cancelled = mti and r <= rt.mti_range_km
                level = cnr - site.degraded_db - (rt.mti_if_db if cancelled else 0.0)
                inten = (level - thr) / 40.0
                if inten <= 0.04 or self.rng.random() > (0.16 if cancelled else 0.4):
                    continue
                x, y = self.to_px((i + self.rng.random()) * 360.0 / n, r + self.rng.uniform(-1.0, 1.0))
                if 0 <= x < self.D and 0 <= y < self.D:
                    c = tuple(min(255, int(v * min(1.0, inten) * 0.8)) for v in col)
                    self.glow.fill(c, (x, y, 2, 2), special_flags=pygame.BLEND_ADD)

    def _paint_noise(self, site, rt, az0: float, swept: float) -> None:
        w = self.world
        jam = 0.0
        for jac, jt, jbrg, jr in w.active_jammers(site):
            from ..sim.radar import jam_to_noise_db
            j = jam_to_noise_db(rt, jt, jr, False, jac.jam_channel < 0 or jac.jam_channel == site.channel)
            jam = max(jam, j)
        dens = 18.0 * 10 ** ((6.0 - site.pfa_exp) * 0.45) + max(0.0, jam) * 6.0
        n = int(dens * swept / 6.0)
        col = self.theme.scope_glow
        for _ in range(min(n, 900)):
            a = az0 + self.rng.random() * swept
            r = self.rng.random() * self.range_km
            x, y = self.to_px(a, r)
            if 0 <= x < self.D and 0 <= y < self.D:
                k = self.rng.uniform(0.15, 0.45)
                self.glow.fill(tuple(int(v * k) for v in col), (x, y, 1, 1), special_flags=pygame.BLEND_ADD)

    def _bezel(self, screen, site, rt, up: bool) -> None:
        th = self.theme
        cx, cy = self.center
        if self.compact:
            # a Soviet instrument tube: black bakelite ring, white numerals at the quarters
            pygame.draw.circle(screen, (16, 16, 15), (cx, cy), self.R + 15, 14)
            pygame.draw.circle(screen, (96, 98, 94), (cx, cy), self.R + 15, 2)
            pygame.draw.circle(screen, (6, 6, 6), (cx, cy), self.R + 2, 3)
            for a in range(0, 360, 15):
                ra = math.radians(a)
                r0, r1 = self.R + 4, self.R + (11 if a % 90 == 0 else 7)
                pygame.draw.line(screen, (210, 208, 196), (cx + r0 * math.sin(ra), cy - r0 * math.cos(ra)),
                                 (cx + r1 * math.sin(ra), cy - r1 * math.cos(ra)), 1)
            if not up:
                t = TEXT.render(site.status.upper(), 14, th.alert, "eng")
                screen.blit(t, (cx - t.get_width() // 2, cy - 8))
            return
        pygame.draw.circle(screen, (24, 24, 26), (cx, cy), self.R + 22, 20)
        pygame.draw.circle(screen, (70, 70, 74), (cx, cy), self.R + 22, 2)
        pygame.draw.circle(screen, (8, 8, 8), (cx, cy), self.R + 2, 3)
        for a in range(0, 360, 10):
            ra = math.radians(a)
            r0 = self.R + 6
            r1 = self.R + (14 if a % 30 == 0 else 10)
            pygame.draw.line(screen, (200, 200, 190), (cx + r0 * math.sin(ra), cy - r0 * math.cos(ra)),
                             (cx + r1 * math.sin(ra), cy - r1 * math.cos(ra)), 1)
            if a % 30 == 0:
                s = TEXT.render(f"{a:03d}", 10, (210, 210, 200), "ui")
                rr = self.R + 30
                screen.blit(s, (cx + rr * math.sin(ra) - s.get_width() / 2, cy - rr * math.cos(ra) - 6))
        unit = "NM" if th.units == "imperial" else "KM"
        rng_val = self.range_km / NM if th.units == "imperial" else self.range_km
        ru = th.faction == "USSR" and getattr(self, "lang_mode", "ru+en") != "en"
        if ru:
            unit = "КМ"
            lines = [f"ИКО · {(site.name_ru or site.name).upper()}", f"{rt.name_ru or rt.name}",
                     f"ДАЛЬНОСТЬ {rng_val:.0f} {unit}   {site.rpm:g} ОБ/МИН   СДЦ {'ВКЛ' if site.mti else 'ВЫКЛ'}   "
                     f"ПОРОГ 1E-{site.pfa_exp:.1f}"]
            if not up:
                lines.append(f"*** {dict(down='ВЫКЛЮЧЕНА', maint='РЕГЛАМЕНТ', degraded='НЕИСПРАВНОСТЬ').get(site.status, site.status.upper())} ***")
        else:
            lines = [f"{site.name.upper()}", f"{rt.name}", f"RANGE {rng_val:.0f} {unit}   {site.rpm:g} RPM   "
                     f"MTI {'ON' if site.mti else 'OFF'}   Pfa 1E-{site.pfa_exp:.1f}"]
            if not up:
                lines.append(f"*** {site.status.upper()} ***")
        for i, ln in enumerate(lines):
            screen.blit(TEXT.render(ln, 13 if i else 15, th.text if i < 3 else th.alert,
                                    th.data_font if i else "eng"), (self.rect.x + 14, self.rect.y + 10 + i * 17))
        m = pygame.mouse.get_pos()
        if math.hypot(m[0] - cx, m[1] - cy) < self.R:
            dx, dy = m[0] - cx, cy - m[1]
            rr = math.hypot(dx, dy) / self.R * self.range_km
            brg = math.degrees(math.atan2(dx, dy)) % 360
            rv = rr / NM if th.units == "imperial" else rr
            txt = (f"АЗ {brg:03.0f}°  Д {rv:.0f} {unit}" if ru else f"BRG {brg:03.0f}°  RNG {rv:.0f} {unit}")
            screen.blit(TEXT.render(txt, 13, th.text, th.data_font), (self.rect.right - TEXT.width(txt, 13, th.data_font)
                                                                      - 14, self.rect.y + 10))
