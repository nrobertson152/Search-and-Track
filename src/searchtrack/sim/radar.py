"""Radar physics: range equation, fluctuation, lobing, clutter/MTI, jamming,
the per-tick antenna sweep, height finders and IFF.

Every detection attempt yields a DetectionBreakdown with all terms of the
budget and the limiting factor, so the game can explain *why*.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .catalog import JammerType, RadarType
from .geo import (angle_diff, bearing_deg, elevation_angle, heading_vec, in_sector,
                  slant_range_km)
from .state import Aircraft, HeightFinder, RadarSite, Report

if TYPE_CHECKING:
    from .world import World

FOUR_PI_CUBED_DB = 30.0 * math.log10(4.0 * math.pi)
KT0_DBW_HZ = -228.6 + 10.0 * math.log10(290.0)


# ------------------------------------------------------------------ budget terms

def noise_dbw(rt: RadarType) -> float:
    bw_hz = 1e6 / rt.pulse_us
    return KT0_DBW_HZ + 10.0 * math.log10(bw_hz) + rt.nf_db


def snr_single_db(rt: RadarType, r_km: float, rcs_m2: float) -> float:
    """Single-pulse SNR before calibration loss (peak-power radar equation)."""
    r_m = max(r_km, 0.05) * 1000.0
    lam = rt.wavelength_m
    pt = 10.0 * math.log10(rt.peak_kw * 1000.0)
    return (pt + 2.0 * rt.gain_db + 20.0 * math.log10(lam) + 10.0 * math.log10(max(rcs_m2, 1e-6))
            - FOUR_PI_CUBED_DB - 40.0 * math.log10(r_m) - noise_dbw(rt))


def integration_gain_db(rt: RadarType, rpm: Optional[float] = None) -> float:
    rpm = rpm or rt.rpm
    n = max(1.0, rt.prf * rt.az_beam_deg / (6.0 * rpm))
    return 8.0 * math.log10(n)          # non-coherent integration, ~n^0.8


def integrated_snr_db(rt: RadarType, r_km: float, rcs_m2: float, rpm: Optional[float] = None) -> float:
    return snr_single_db(rt, r_km, rcs_m2) + integration_gain_db(rt, rpm) - rt.cal_loss_db


def pd_swerling1(snr_db: float, pfa: float) -> float:
    s = 10.0 ** (snr_db / 10.0)
    return pfa ** (1.0 / (1.0 + s))


def snr_for_pd(pd: float, pfa: float) -> float:
    return 10.0 * math.log10(math.log(pfa) / math.log(pd) - 1.0)


def lobing_db(rt: RadarType, h_ant_m: float, h_t_m: float, r_km: float, rho: float) -> float:
    """Two-ray ground-reflection pattern factor F^4 in dB (flat-earth approximation)."""
    if not rt.lobing:
        return 0.0
    hr = max(h_ant_m, 1.0)
    ht = max(h_t_m, 1.0)
    delta = 4.0 * math.pi * hr * ht / (rt.wavelength_m * r_km * 1000.0)
    f2 = 1.0 + rho * rho - 2.0 * rho * math.cos(delta)
    return max(-30.0, min(12.0, 20.0 * math.log10(max(f2, 1e-4))))


def mti_response_db(rt: RadarType, v_radial: float) -> float:
    """Single delay-line canceller response, normalised to average gain 1.
    Gives both the zero-Doppler notch and blind speeds at n*lambda*PRF/2."""
    fd = 2.0 * v_radial / rt.wavelength_m
    resp = 2.0 * math.sin(math.pi * fd / rt.prf) ** 2
    if rt.stagger:
        resp = 0.5 * (resp + 2.0 * math.sin(math.pi * fd / (rt.prf * 0.82)) ** 2)
    return max(-30.0, 10.0 * math.log10(max(resp, 1e-3)))


def blind_speed(rt: RadarType) -> float:
    return rt.wavelength_m * rt.prf / 2.0


def jam_to_noise_db(rt: RadarType, jt: JammerType, r_j_km: float, mainlobe: bool,
                    channel_match: bool, degraded_db: float = 0.0) -> float:
    if rt.band not in jt.bands:
        return -99.0
    if jt.mode == "spot" and not channel_match and not rt.freq_agile:
        return -99.0
    if jt.mode == "spot" and rt.freq_agile:
        density = jt.erp_dbw_mhz - 10.0      # agile radar spreads the spot jammer's effect
    else:
        density = jt.erp_dbw_mhz
    bw_mhz = 1.0 / rt.pulse_us
    g = rt.gain_db if mainlobe else rt.gain_db + rt.sidelobe_db
    r_m = max(r_j_km, 0.1) * 1000.0
    j = density + 10.0 * math.log10(bw_mhz) + g + 20.0 * math.log10(rt.wavelength_m) \
        - 20.0 * math.log10(4.0 * math.pi) - 20.0 * math.log10(r_m)
    return j - noise_dbw(rt) - degraded_db


@dataclass
class DetectionBreakdown:
    radar: str
    target: str
    ground_km: float = 0.0
    slant_km: float = 0.0
    elev_deg: float = 0.0
    mask_deg: float = 0.0
    rcs_m2: float = 0.0
    snr_db: float = -99.0                # integrated, calibrated, incl. lobing
    lobing_db: float = 0.0
    cnr_db: float = -99.0                # clutter-to-noise after MTI
    mti_db: float = 0.0
    jn_db: float = -99.0
    sinr_db: float = -99.0
    pd: float = 0.0
    detected: bool = False
    limit: str = ""
    v_radial: float = 0.0

    def explain(self) -> str:
        names = {
            "": "detectable", "range": "beyond instrumented range", "horizon": "below radar horizon",
            "terrain": "masked by terrain", "cone": "in overhead cone of silence", "down": "radar not operating",
            "clutter": "lost in ground/sea clutter", "notch": "MTI zero-Doppler notch (tangential flight)",
            "blind": "MTI blind speed", "jamming": "masked by jamming", "weak": "signal too weak",
            "lobing": "in a ground-reflection lobing null", "fade": "target faded this scan (Swerling)",
        }
        return names.get(self.limit, self.limit)


def smooth_earth_obstruction(h_ant_m: float, gr_km: float, k: float) -> float:
    """Max apparent elevation of a sea-level smooth Earth closer than gr_km (radians)."""
    ha = max(h_ant_m, 1.0) / 1000.0
    d_h = math.sqrt(2.0 * k * 6371.0 * ha)
    r = min(gr_km, d_h)
    return math.atan((-ha - r * r / (2.0 * k * 6371.0)) / max(r, 1e-3))


def _sum_db(*terms: float) -> float:
    return 10.0 * math.log10(sum(10.0 ** (t / 10.0) for t in terms if t > -98.0) or 1e-10)


def evaluate(world: "World", site: RadarSite, rt: RadarType, tgt: Aircraft, *,
             rng_draw: Optional[float] = None, jammers: Optional[list] = None,
             x: Optional[float] = None, y: Optional[float] = None, alt: Optional[float] = None,
             vx: Optional[float] = None, vy: Optional[float] = None) -> DetectionBreakdown:
    """Full detection budget for one target. rng_draw=None -> prediction only."""
    tx = tgt.x if x is None else x
    ty = tgt.y if y is None else y
    ta = tgt.alt if alt is None else alt
    if vx is None or vy is None:
        hx, hy = heading_vec(tgt.hdg)
        vx, vy = hx * tgt.spd, hy * tgt.spd
    bd = DetectionBreakdown(site.id, tgt.id)
    dx, dy = tx - site.x, ty - site.y
    gr = math.hypot(dx, dy)
    bd.ground_km = gr
    bd.slant_km = slant_range_km(gr, site.h_ant, ta)
    if site.status in ("down", "maint"):
        bd.limit = "down"
        return bd
    if gr > rt.range_km:
        bd.limit = "range"
        return bd
    brg = bearing_deg(dx, dy)
    mask = world.mask_for(site)
    ghost = tgt.kind == "ghost"
    k = site.k_override or world.weather.k_factor
    el = elevation_angle(site.h_ant, ta, gr, k)
    bd.elev_deg = math.degrees(el)
    if not ghost:
        ob = mask.obstruction(brg, gr) if mask is not None else -math.pi / 2
        bd.mask_deg = math.degrees(ob)
        if el <= ob:
            # terrain if the obstruction is clearly above the smooth-Earth horizon
            bd.limit = "terrain" if ob > smooth_earth_obstruction(site.h_ant, gr, k) + math.radians(0.05) else "horizon"
            return bd
        if bd.elev_deg > rt.el_max_deg:
            bd.limit = "cone"
            return bd
    # aspect-dependent RCS
    at = world.catalog.aircraft.get(tgt.type_id)
    hdg = bearing_deg(vx, vy) if (vx or vy) else tgt.hdg
    aspect = angle_diff(bearing_deg(-dx, -dy), hdg)
    base_rcs = at.rcs(aspect) if at else 1.0
    rcs = base_rcs * tgt.rcs_scale
    bd.rcs_m2 = rcs
    snr = integrated_snr_db(rt, max(bd.slant_km, 0.2), rcs, site.rpm) - site.degraded_db
    if not ghost:
        sea = mask.clutter_is_sea(brg, gr * site.h_ant / max(site.h_ant + ta, 1.0)) if mask is not None else False
        bd.lobing_db = lobing_db(rt, site.h_ant, ta, max(bd.slant_km, 0.2), 0.9 if sea else 0.55)
        snr += bd.lobing_db
    # weather attenuation & rain clutter
    rain_db = -99.0
    for c in world.weather.cells:
        if math.hypot(tx - c.x, ty - c.y) < c.r:
            rain_db = max(rain_db, -15.0 + 45.0 * c.intensity * rt.weather_sens)
            snr -= 2.0 * c.intensity * rt.weather_sens
    bd.snr_db = snr
    # clutter & MTI
    bd.v_radial = (vx * dx + vy * dy) / max(gr, 1e-3)
    cnr = -99.0
    if mask is not None and not ghost:
        s0 = mask.clutter_db(brg, gr)
        if s0 > -900.0:
            cell_m2 = gr * 1000.0 * math.radians(rt.az_beam_deg) * 150.0 * rt.pulse_us
            cnr = integrated_snr_db(rt, max(gr, 0.5), 10.0 ** (s0 / 10.0) * cell_m2, site.rpm) - site.degraded_db
    mti_active = site.mti and rt.mti and gr <= rt.mti_range_km
    if mti_active:
        bd.mti_db = mti_response_db(rt, bd.v_radial)
        snr += bd.mti_db
        if cnr > -98.0:
            cnr -= rt.mti_if_db
        if rain_db > -98.0:
            rain_db -= rt.mti_if_db * 0.4
    bd.cnr_db = _sum_db(cnr, rain_db) if (cnr > -98.0 or rain_db > -98.0) else -99.0
    # jamming
    jn = -99.0
    for jam, jt, jbrg, jr in (jammers if jammers is not None else world.active_jammers(site)):
        main = abs(angle_diff(jbrg, brg)) <= rt.az_beam_deg * 0.75
        chan = jam.jam_channel < 0 or jam.jam_channel == site.channel
        j = jam_to_noise_db(rt, jt, jr, main, chan, site.degraded_db)
        jn = _sum_db(jn, j) if jn > -98.0 else j
    bd.jn_db = jn
    interference = _sum_db(0.0, bd.cnr_db, jn)
    bd.sinr_db = snr - interference
    pfa = 10.0 ** (-site.pfa_exp)
    bd.pd = pd_swerling1(bd.sinr_db, pfa)
    if rng_draw is not None:
        bd.detected = rng_draw < bd.pd
    else:
        bd.detected = bd.pd >= 0.5
    if not bd.detected:
        thr = snr_for_pd(0.5, pfa)
        if jn > 3.0 and jn >= bd.cnr_db and bd.snr_db > thr:
            bd.limit = "jamming"
        elif bd.cnr_db > 3.0 and bd.snr_db > thr:
            bd.limit = "clutter"
        elif mti_active and bd.mti_db < -8.0:
            bd.limit = "notch" if abs(bd.v_radial) < blind_speed(rt) * 0.5 else "blind"
        elif bd.sinr_db < thr - 1.0:
            bd.limit = "lobing" if bd.lobing_db < -6.0 else "weak"
        else:
            bd.limit = "fade"
    return bd


# ------------------------------------------------------------------ sweep

@dataclass
class Paint:
    t: float
    az: float
    r: float
    snr: float
    kind: str = "target"                  # target | false | strobe | weather | ghost
    size: int = 1
    sub: bool = False                     # below threshold (video only)


def sweep(world: "World", site: RadarSite, dt: float) -> tuple[list[Paint], list[Report]]:
    rt = world.catalog.radars[site.type_id]
    rng = world.rng
    t0 = world.t
    d_az = 6.0 * site.rpm * dt
    az0 = site.az
    site.az = (az0 + d_az) % 360.0
    paints: list[Paint] = []
    reports: list[Report] = []
    if site.status in ("down", "maint"):
        return paints, reports
    jammers = world.active_jammers(site)
    pfa = 10.0 ** (-site.pfa_exp)
    thr = snr_for_pd(0.5, pfa)
    deg_per_s = 6.0 * site.rpm
    hits: list[tuple[float, float, float, Aircraft, DetectionBreakdown]] = []
    for tgt in world.radar_targets():
        if tgt.kind == "ghost" and site.id not in tgt.visible_to:
            continue
        dx, dy = tgt.x - site.x, tgt.y - site.y
        gr = math.hypot(dx, dy)
        if gr > rt.range_km or gr < 0.5:
            continue
        brg = bearing_deg(dx, dy)
        if not in_sector(brg, az0, d_az):
            continue
        bd = evaluate(world, site, rt, tgt, rng_draw=rng.random(), jammers=jammers)
        world.last_eval[(site.id, tgt.id)] = (t0, bd)
        tp = t0 + ((brg - az0) % 360.0) / deg_per_s
        if bd.limit in ("range", "horizon", "terrain", "cone", "down"):
            continue
        if bd.detected:
            hits.append((tp, brg, gr, tgt, bd))
        elif bd.sinr_db > thr - 7.0:
            paints.append(Paint(tp, brg, gr, bd.sinr_db, "target", 1, True))
    # resolution: merge returns within one range cell and one beamwidth
    dr = max(0.15 * rt.pulse_us, 0.3)
    groups: list[list[tuple]] = []
    for h in sorted(hits, key=lambda h: h[2]):
        for g in groups:
            if abs(g[0][2] - h[2]) <= dr and abs(angle_diff(g[0][1], h[1])) <= rt.az_beam_deg:
                g.append(h)
                break
        else:
            groups.append([h])
    for g in groups:
        tp = sum(h[0] for h in g) / len(g)
        brg = g[0][1]
        gr = sum(h[2] for h in g) / len(g)
        tgt = max(g, key=lambda h: h[4].sinr_db)[3]
        snr = max(h[4].sinr_db for h in g)
        kind = "ghost" if tgt.kind == "ghost" else "target"
        paints.append(Paint(tp, brg, gr, snr, kind, len(g)))
        mr = gr + rng.gauss(0.0, rt.range_sigma_km) + site.bias_r
        ma = brg + rng.gauss(0.0, rt.az_sigma_deg) + site.bias_az
        hx, hy = heading_vec(ma)
        mx, my = site.x + hx * mr, site.y + hy * mr
        alt = None
        alt_sigma = 0.0
        if rt.height == "vbeam" and tgt.kind != "ghost":
            alt_sigma = rt.height_sigma_m0 + rt.height_sigma_per_km * gr
            alt = max(0.0, tgt.alt + rng.gauss(0.0, alt_sigma))
        elif rt.height == "vbeam":
            alt_sigma = rt.height_sigma_m0 + rt.height_sigma_per_km * gr
            alt = max(0.0, rng.uniform(1000.0, 12000.0))
        iff, garbled = interrogate(world, site, rt, tgt, gr, [h[3] for h in g])
        size_est = max(1, len(g) + (rng.choice([-1, 0, 0, 1]) if len(g) > 2 else 0))
        reports.append(Report(world.next_id("rep"), tp, tp, site.id, mx, my, alt, alt_sigma, snr,
                              size_est, iff, garbled, tgt.id))
    # false alarms (thermal noise crossings), more when MTI is off near clutter
    cells = (rt.range_km / max(0.15 * rt.pulse_us, 0.15)) * (d_az / rt.az_beam_deg)
    mean_fa = pfa * cells * (1.0 if (site.mti or not rt.mti) else 2.5)
    for _ in range(_poisson(rng, mean_fa)):
        a = (az0 + rng.random() * d_az) % 360.0
        r = rng.uniform(5.0, rt.range_km)
        tp = t0 + ((a - az0) % 360.0) / deg_per_s
        paints.append(Paint(tp, a, r, thr + rng.uniform(0.0, 3.0), "false"))
        hx, hy = heading_vec(a)
        alt = rng.uniform(500.0, 12000.0) if rt.height == "vbeam" else None
        reports.append(Report(world.next_id("rep"), tp, tp, site.id, site.x + hx * r, site.y + hy * r,
                              alt, 2000.0 if alt else 0.0, thr, 1, {}, False, ""))
    # weather paints
    if rt.weather_sens > 0.2:
        for c in world.weather.cells:
            dx, dy = c.x - site.x, c.y - site.y
            gr = math.hypot(dx, dy)
            if gr - c.r > rt.range_km:
                continue
            brg = bearing_deg(dx, dy)
            half = math.degrees(math.atan2(c.r, max(gr, 1.0)))
            if in_sector(brg, (az0 - half) % 360.0, d_az + 2 * half):
                tp = t0 + ((brg - az0) % 360.0) / deg_per_s
                paints.append(Paint(tp, brg, gr, 10.0 + 25.0 * c.intensity * rt.weather_sens, "weather",
                                    int(c.r)))
    # jamming strobes and bearing reports
    for jam, jt, jbrg, jr in jammers:
        if not in_sector(jbrg, az0, d_az):
            continue
        chan = jam.jam_channel < 0 or jam.jam_channel == site.channel
        jn = jam_to_noise_db(rt, jt, jr, True, chan, site.degraded_db)
        if jn > 6.0:
            tp = t0 + ((jbrg - az0) % 360.0) / deg_per_s
            paints.append(Paint(tp, jbrg, rt.range_km, jn, "strobe"))
            reports.append(Report(world.next_id("rep"), tp, tp, site.id, site.x, site.y, None, 0.0, jn,
                                  1, {}, False, jam.id, strobe_az=(jbrg + rng.gauss(0, rt.az_beam_deg * 0.4)) % 360))
    return paints, reports


def _poisson(rng, lam: float) -> int:
    if lam <= 0.0:
        return 0
    if lam > 30.0:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def interrogate(world: "World", site: RadarSite, rt: RadarType, tgt: Aircraft, gr: float,
                group: list[Aircraft]) -> tuple[dict[str, str], bool]:
    if not (site.iff_on and rt.iff) or gr > rt.iff_range_km or tgt.kind != "aircraft":
        return {}, False
    sysname = world.faction_def.id
    readable = ("sif", "atc") if sysname == "US" else ("kremniy",)
    tr = tgt.transponder
    if not tr.on or tr.failed or tr.system not in readable:
        return {}, False
    if world.rng.random() > 0.92:
        return {}, False
    codes = dict(tr.codes)
    if tr.system == "atc":
        codes = {k: v for k, v in codes.items() if k in ("3", "C")}
    garbled = False
    for other in world.radar_targets():
        if other is tgt or other.kind != "aircraft":
            continue
        if other.transponder.on and other.transponder.system in readable:
            if math.hypot(other.x - tgt.x, other.y - tgt.y) < 3.5 and world.rng.random() < 0.5:
                garbled = True
                break
    return codes, garbled


# ------------------------------------------------------------------ height finder

def height_finder_step(world: "World", hf: HeightFinder) -> None:
    site = world.radars[hf.site_id]
    rt = world.catalog.radars[hf.type_id]
    if hf.status != "ok" or site.status in ("down", "maint"):
        return
    t = world.t
    if not hf.current:
        while hf.queue:
            tid = hf.queue.pop(0)
            trk = world.tracks.get(tid)
            if trk is None or trk.lost:
                continue
            brg = bearing_deg(trk.x - site.x, trk.y - site.y)
            slew = abs(angle_diff(brg, hf.az)) / rt.slew_dps
            hf.current = tid
            hf.t_done = t + slew + 2.0 * 60.0 / rt.nod_cpm
            return
        return
    if t < hf.t_done:
        return
    tid, hf.current = hf.current, ""
    trk = world.tracks.get(tid)
    if trk is None:
        return
    trk.hf_requested = False
    brg = bearing_deg(trk.x - site.x, trk.y - site.y)
    rng_est = math.hypot(trk.x - site.x, trk.y - site.y)
    hf.az = brg
    best = None
    for tgt in world.radar_targets():
        if tgt.kind == "ghost":
            continue
        dx, dy = tgt.x - site.x, tgt.y - site.y
        gr = math.hypot(dx, dy)
        if gr > rt.range_km or abs(angle_diff(bearing_deg(dx, dy), brg)) > rt.az_beam_deg / 2:
            continue
        if abs(gr - rng_est) > 10.0:
            continue
        bd = evaluate(world, site, rt, tgt, rng_draw=world.rng.random())
        if bd.detected and (best is None or bd.sinr_db > best[1].sinr_db):
            best = (tgt, bd)
    if best is None:
        trk.alt_fails += 1
        hf.last_result = f"{tid}: NO HEIGHT"
        world.log_event("track", f"Height finder {site.name}: no height on {tid}", tid)
        return
    tgt, bd = best
    sigma = rt.height_sigma_m0 + rt.height_sigma_per_km * bd.ground_km
    alt = max(0.0, tgt.alt + world.rng.gauss(0.0, sigma))
    trk.alt, trk.alt_src, trk.alt_t = alt, "HF", t
    trk.alt_fails = 0
    hf.last_result = f"{tid}: {alt / 0.3048 / 1000:.0f},000 FT"
    world.log_event("track", f"Height {site.name}: {tid} at {alt / 0.3048:,.0f} ft", tid)


def predict_coverage(world: "World", site: RadarSite, x: float, y: float, alt: float,
                     vx: float, vy: float, type_id: str) -> DetectionBreakdown:
    """Deterministic detectability prediction for an assumed target (Coverage Analysis)."""
    rt = world.catalog.radars[site.type_id]
    probe = Aircraft(id="?", type_id=type_id, callsign="", side="", x=x, y=y, alt=alt,
                     hdg=bearing_deg(vx, vy) if (vx or vy) else 0.0, spd=math.hypot(vx, vy))
    return evaluate(world, site, rt, probe, rng_draw=None, vx=vx, vy=vy)
