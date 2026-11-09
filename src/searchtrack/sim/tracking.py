"""Reporting pipelines (SAGE digital link vs PVO manual reporting) and the
track manager (association, alpha-beta filtering, initiation, drops, fusion,
jam-strobe triangulation)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .geo import bearing_deg, heading_vec
from .state import CompanyTrack, Report, Track

if TYPE_CHECKING:
    from .world import World

CYR = "АБВГДЕЖИКЛМНПРСТУФХЦЧШЭЮЯ"


# ------------------------------------------------------------------ pipelines

def route_reports(world: "World", site, reports: list[Report]) -> None:
    fd = world.faction_def
    link = world.links.get(site.link)
    link_up = link is None or link.up
    if site.gci:
        for r in reports:
            ingest(world, Report(**{**r.__dict__}), local=site.id)
    if fd.pipeline == "digital":
        if not link_up:
            return
        delay = link.delay_s if link else fd.link_delay_s
        for r in reports:
            r.t_arrive = r.t + delay + world.rng.uniform(0.0, 1.5)
            world.inbox.append(r)
    else:
        manual_company(world, site, reports, link_up)


def grid_label(world: "World", x: float, y: float) -> str:
    g = world.faction_def.grid_km
    big = g * 10.0
    xi = math.floor((x + 1000.0) / big)
    yi = math.floor((y + 1000.0) / big)
    sx = int(((x + 1000.0) % big) // g)
    sy = int(((y + 1000.0) % big) // g)
    fx = ((x + 1000.0) % g) / g
    fy = ((y + 1000.0) % g) / g
    snail = 1 + int(fx * 3) + 3 * (2 - int(fy * 3))
    return f"{CYR[(xi + 3 * yi) % len(CYR)]}{sx}{sy}-{snail}"


def quantize(world: "World", x: float, y: float) -> tuple[float, float]:
    g = world.faction_def.grid_km / 3.0
    return (math.floor(x / g) + 0.5) * g, (math.floor(y / g) + 0.5) * g


def manual_company(world: "World", site, reports: list[Report], link_up: bool) -> None:
    fd = world.faction_def
    rng = world.rng
    t = world.t
    lo, hi = fd.report_delay_s
    for r in reports:
        if r.strobe_az is not None:
            if link_up:
                r.t_arrive = t + rng.uniform(lo, hi) * 0.5
                world.inbox.append(r)
            continue
        if not r.truth and rng.random() > 0.25:
            continue  # operators reject most noise specks by eye
        best: Optional[CompanyTrack] = None
        bd = 14.0
        for ct in site.company_tracks.values():
            d = math.hypot(ct.x - r.x, ct.y - r.y)
            if d < bd:
                best, bd = ct, d
        if best is not None:
            best.hits += 1
            best.x, best.y, best.t_seen = r.x, r.y, r.t
            best.alt = r.alt if r.alt is not None else best.alt
            best.size = r.size
            reply = r.iff.get("period", "") if r.iff else ""
            best.iff = reply if (reply and reply == best.last_iff) else ("" if not reply else best.iff)
            best.last_iff = reply
        elif len(site.company_tracks) < fd.company_capacity:
            site.company_no += 1
            no = f"{site.id[-2:].upper()}{site.company_no:02d}"
            site.company_tracks[no] = CompanyTrack(no, r.truth, r.x, r.y, r.alt, r.t,
                                                   t + rng.uniform(15.0, 45.0), r.size,
                                                   r.iff.get("period", "") if r.iff else "")
        else:
            world.vars[f"overload_{site.id}"] = world.vars.get(f"overload_{site.id}", 0.0) + 1.0
    period = 60.0 / max(site.rpm, 0.5)
    for no in list(site.company_tracks):
        ct = site.company_tracks[no]
        if t - ct.t_seen > 3.0 * period + 30.0:
            del site.company_tracks[no]
            continue
        if ct.hits < 2:
            continue      # operators wait for a second paint before telephoning a target in
        if t >= ct.t_next_report:
            ct.t_next_report = t + fd.report_interval_s * rng.uniform(0.85, 1.15)
            if not link_up:
                continue
            qx, qy = quantize(world, ct.x, ct.y)
            if rng.random() < fd.report_error_rate:
                g = fd.grid_km
                qx += rng.choice([-g, g, 0.0])
                qy += rng.choice([-g, g]) if qx == quantize(world, ct.x, ct.y)[0] else 0.0
            alt = None if ct.alt is None else round(ct.alt / 500.0) * 500.0
            iff = {"period": ct.iff} if ct.iff else {}
            world.inbox.append(Report(world.next_id("rep"), ct.t_seen, t + rng.uniform(lo, hi), site.id,
                                      qx, qy, alt, 1500.0 if alt is not None else 0.0, 15.0, ct.size,
                                      iff, False, ct.truth, ct.no, grid_label(world, qx, qy)))


# ------------------------------------------------------------------ track manager

def deliver(world: "World") -> None:
    t = world.t
    due = [r for r in world.inbox if r.t_arrive <= t]
    if not due:
        return
    world.inbox = [r for r in world.inbox if r.t_arrive > t]
    for r in sorted(due, key=lambda r: (r.t_arrive, r.rid)):
        ingest(world, r)


def predicted(trk: Track, t: float) -> tuple[float, float]:
    dt = t - trk.t_update
    return trk.x + trk.vx * dt, trk.y + trk.vy * dt


def _gate(trk: Track, manual: bool, age: float) -> float:
    base = 26.0 if manual else 6.0
    spd = math.hypot(trk.vx, trk.vy)
    return base + min(age, 600.0) * spd * (0.12 if manual else 0.06) + (2.0 if trk.quality < 3 else 0.0)


def ingest(world: "World", r: Report, local: str = "") -> None:
    if local:
        tracks = world.local_tracks.setdefault(local, {})
        plots = world.local_plots.setdefault(local, [])
    else:
        tracks, plots = world.tracks, world.plots
    if r.strobe_az is not None:
        if not local:
            world.strobes.append(r)
        return
    if r.truth and not local:
        world.stats.first_plot.setdefault(r.truth, world.t)
    manual = world.faction_def.pipeline == "manual" and not local
    trk: Optional[Track] = None
    key = f"{r.radar}:{r.company}" if r.company else ""
    if manual and key:
        for tk in tracks.values():
            if key in tk.company_keys and not tk.lost:
                trk = tk
                break
    if trk is None:
        best, bscore = None, 1.0
        for tk in tracks.values():
            if tk.lost and world.t - tk.t_lost > 90.0:
                continue
            px, py = predicted(tk, r.t)
            d = math.hypot(px - r.x, py - r.y)
            g = _gate(tk, manual, r.t - tk.t_update)
            if d < g and d / g < bscore:
                best, bscore = tk, d / g
        trk = best
        if trk is not None and key and key not in trk.company_keys:
            trk.company_keys.append(key)
    if trk is not None:
        update_track(world, trk, r, manual)
        return
    if manual and r.company:
        new_track(world, tracks, r, None, local)
    else:
        plots.append(r)


def update_track(world: "World", trk: Track, r: Report, manual: bool) -> None:
    dt = r.t - trk.t_update
    trk.sources[r.radar] = world.t
    if r.truth or not trk.truth_votes:
        k = r.truth or "-"
        trk.truth_votes[k] = trk.truth_votes.get(k, 0) + 1
    if r.iff:
        trk.iff = dict(r.iff)
        trk.iff_t = world.t
    if dt <= 0.5:
        return
    px, py = trk.x + trk.vx * dt, trk.y + trk.vy * dt
    rx, ry = r.x - px, r.y - py
    if manual:
        a, b = (0.55, 0.12) if trk.hits >= 4 else (0.65, 0.35)
        if trk.hits < 2 and dt > 20.0:
            trk.vx, trk.vy = (r.x - trk.x) / dt, (r.y - trk.y) / dt   # two-point start
            spd = math.hypot(trk.vx, trk.vy)
            if spd > 1.2:
                trk.vx, trk.vy = trk.vx / spd * 1.2, trk.vy / spd * 1.2
            trk.x, trk.y, trk.t_update = r.x, r.y, r.t
            trk.hits += 1
            trk.quality = min(7, trk.quality + 1)
            world.on_track_update(trk)
            return
    else:
        a = 0.65 if trk.hits < 4 else 0.45
        b = 0.4 if trk.hits < 4 else 0.15
    if dt < 4.0:
        # near-simultaneous report from another radar: refine position only
        a *= 0.5
        b = 0.0
    trk.x = px + a * rx
    trk.y = py + a * ry
    if b > 0.0:
        dvx, dvy = b * rx / dt, b * ry / dt
        dv = math.hypot(dvx, dvy)
        lim = 0.12 if trk.hits >= 4 else 0.4
        if dv > lim:
            dvx, dvy = dvx / dv * lim, dvy / dv * lim
        trk.vx += dvx
        trk.vy += dvy
    spd = math.hypot(trk.vx, trk.vy)
    if spd > 1.2:
        trk.vx, trk.vy = trk.vx / spd * 1.2, trk.vy / spd * 1.2
    if trk.lost:
        trk.lost = False
        world.log_event("track", f"Track {trk.id} reacquired", trk.id)
    trk.t_update = r.t
    trk.hits += 1
    trk.quality = min(7, trk.quality + 1)
    if r.alt is not None and not (trk.alt_src in ("HF", "MODEC", "VID") and world.t - trk.alt_t < 300.0):
        trk.alt = r.alt if trk.alt is None or trk.alt_src != "VB" else trk.alt * 0.6 + r.alt * 0.4
        trk.alt_src, trk.alt_t = "VB", world.t
    trk.size = max(1, round(0.7 * trk.size + 0.3 * r.size)) if trk.hits > 2 else max(trk.size, r.size)
    if not trk.history or r.t - trk.history[-1][0] >= (30.0 if manual else 10.0):
        trk.history.append([round(r.t, 1), round(trk.x, 2), round(trk.y, 2)])
        if len(trk.history) > 40:
            trk.history.pop(0)
    world.on_track_update(trk)


def new_track(world: "World", tracks: dict, r: Report, prev: Optional[Report], local: str = "") -> Track:
    tid = world.next_track_id(local)
    trk = Track(id=tid, x=r.x, y=r.y, t_update=r.t, t_init=world.t, quality=3, local=bool(local))
    if prev is not None and r.t - prev.t > 1.0:
        trk.vx = (r.x - prev.x) / (r.t - prev.t)
        trk.vy = (r.y - prev.y) / (r.t - prev.t)
    trk.sources[r.radar] = world.t
    if r.alt is not None:
        trk.alt, trk.alt_src, trk.alt_t = r.alt, "VB", world.t
    if r.iff:
        trk.iff, trk.iff_t = dict(r.iff), world.t
    trk.size = r.size
    trk.truth_votes[r.truth or "-"] = 1
    if r.company:
        trk.company_keys.append(f"{r.radar}:{r.company}")
    trk.history.append([round(r.t, 1), round(r.x, 2), round(r.y, 2)])
    tracks[tid] = trk
    if not local:
        world.stats.tracks_initiated += 1
        if r.truth:
            world.stats.first_track.setdefault(r.truth, world.t)
        else:
            world.stats.false_tracks += 1
        world.log_event("track", f"Track {tid} initiated", tid)
        world.on_track_update(trk)
    return trk


def initiate_at(world: "World", x: float, y: float, radius: float = 12.0) -> Optional[Track]:
    """Light-gun initiation: build a track from recent unassociated plots near (x, y)."""
    near = sorted((p for p in world.plots if math.hypot(p.x - x, p.y - y) <= radius),
                  key=lambda p: p.t)
    if not near:
        return None
    last = near[-1]
    prev = None
    for p in reversed(near[:-1]):
        if last.t - p.t > 4.0 and math.hypot(last.x - p.x, last.y - p.y) <= 1.3 * (last.t - p.t) + 4.0:
            prev = p
            break
    used = {id(last), id(prev)} if prev else {id(last)}
    world.plots = [p for p in world.plots if id(p) not in used]
    trk = new_track(world, world.tracks, last, prev)
    return trk


def auto_initiate(world: "World", plots: list[Report], tracks: dict, local: str = "",
                  min_hits: int = 3, latency: float = 0.0) -> None:
    if len(plots) < min_hits:
        return
    used: set[int] = set()
    ps = sorted(plots, key=lambda p: -p.t)
    for p in ps:
        if p.rid in used or world.t - p.t < latency:
            continue
        chain = [p]
        for q in ps:
            if q.rid in used or q is p:
                continue
            last = chain[-1]
            dtq = last.t - q.t
            if 3.0 < dtq < 45.0 and math.hypot(last.x - q.x, last.y - q.y) <= 1.25 * dtq + 3.5:
                chain.append(q)
                if len(chain) >= min_hits:
                    break
        if len(chain) >= min_hits:
            for c in chain:
                used.add(c.rid)
            head = chain[0]
            if any(not tk.lost and math.hypot(*(a - b for a, b in zip(predicted(tk, head.t), (head.x, head.y)))) < 9.0
                   for tk in tracks.values()):
                continue      # an existing track is already there: plots were stragglers
            new_track(world, tracks, chain[0], chain[-1], local)
            for q in ps:
                if q.rid not in used and abs(q.t - head.t) < 30.0 and math.hypot(q.x - head.x, q.y - head.y) < 8.0:
                    used.add(q.rid)   # same target seen by another radar
    if used:
        plots[:] = [p for p in plots if p.rid not in used]


def maintain(world: "World") -> None:
    t = world.t
    manual = world.faction_def.pipeline == "manual"
    lo, hi = world.faction_def.report_delay_s
    for local, tracks in [("", world.tracks)] + list(world.local_tracks.items()):
        is_manual = manual and not local
        drop = (world.faction_def.report_interval_s * 2.5 + hi) if is_manual else (40.0 if local else 75.0)
        for tid in list(tracks):
            trk = tracks[tid]
            age = t - trk.t_update
            if trk.lost:
                if t - trk.t_lost > 150.0:
                    del tracks[tid]
                    if not local:
                        world.on_track_removed(tid)
                continue
            if age > drop * 0.5:
                trk.quality = max(0, min(trk.quality, int(7 * (1.0 - age / drop))))
            if age > drop:
                trk.lost = True
                trk.t_lost = t
                if not local:
                    world.on_track_lost(trk)
    if world.automation.get("surveil"):
        _merge_duplicates(world, manual)
    keep = 900.0 if manual else 60.0
    world.plots = [p for p in world.plots if t - p.t < keep]
    for local, plots in world.local_plots.items():
        plots[:] = [p for p in plots if t - p.t < 45.0]
        auto_initiate(world, plots, world.local_tracks.setdefault(local, {}), local, min_hits=2)
    world.strobes = [s for s in world.strobes if t - s.t < 25.0]
    triangulate(world)


def triangulate(world: "World") -> None:
    latest: dict[str, list[Report]] = {}
    for s in world.strobes:
        latest.setdefault(s.radar, []).append(s)
    radars = list(latest)
    pts: list[tuple[float, float]] = []
    for i in range(len(radars)):
        for j in range(i + 1, len(radars)):
            for a in latest[radars[i]][-3:]:
                for b in latest[radars[j]][-3:]:
                    p = _intersect(a.x, a.y, a.strobe_az, b.x, b.y, b.strobe_az)
                    if p is not None:
                        pts.append(p)
    clusters: list[list[tuple[float, float]]] = []
    for p in pts:
        for c in clusters:
            if math.hypot(c[0][0] - p[0], c[0][1] - p[1]) < 50.0:
                c.append(p)
                break
        else:
            clusters.append([p])
    for c in clusters:
        x = sum(p[0] for p in c) / len(c)
        y = sum(p[1] for p in c) / len(c)
        trk = None
        for tk in world.tracks.values():
            if tk.jammer and math.hypot(tk.x - x, tk.y - y) < 70.0:
                trk = tk
                break
        if trk is None:
            tid = world.next_track_id("")
            trk = Track(id=tid, x=x, y=y, t_update=world.t, t_init=world.t, quality=2, jammer=True,
                        identity="pending")
            trk.history.append([world.t, x, y])
            world.tracks[tid] = trk
            world.stats.tracks_initiated += 1
            world.log_event("track", f"Jam strobe triangulation: jammer track {tid}", tid)
            world.alert(f"JAMMING — strobes triangulated, jammer track {tid}", ref=tid, priority=1)
        else:
            dt = max(world.t - trk.t_update, 1.0)
            trk.vx = 0.7 * trk.vx + 0.3 * (x - trk.x) / dt
            trk.vy = 0.7 * trk.vy + 0.3 * (y - trk.y) / dt
            trk.x, trk.y = 0.5 * trk.x + 0.5 * x, 0.5 * trk.y + 0.5 * y
            trk.t_update = world.t
            trk.quality = min(5, trk.quality + 1)
            trk.lost = False


def _intersect(x1, y1, a1, x2, y2, a2) -> Optional[tuple[float, float]]:
    d1 = heading_vec(a1)
    d2 = heading_vec(a2)
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < math.sin(math.radians(15.0)):
        return None
    t1 = ((x2 - x1) * d2[1] - (y2 - y1) * d2[0]) / den
    t2 = ((x2 - x1) * d1[1] - (y2 - y1) * d1[0]) / den
    if t1 <= 5.0 or t2 <= 5.0 or t1 > 600.0 or t2 > 600.0:
        return None
    return x1 + d1[0] * t1, y1 + d1[1] * t1


def truth_of(trk: Track) -> str:
    if not trk.truth_votes:
        return ""
    k = max(trk.truth_votes.items(), key=lambda kv: kv[1])[0]
    return "" if k == "-" else k


def track_bearing_range(trk: Track, x: float, y: float) -> tuple[float, float]:
    return bearing_deg(trk.x - x, trk.y - y), math.hypot(trk.x - x, trk.y - y)


def _merge_duplicates(world: "World", manual: bool) -> None:
    """Correlation operators merge two tracks that are clearly the same target."""
    lim = 18.0 if manual else 6.0
    live = [t for t in world.tracks.values() if not t.lost and not t.jammer and t.hits >= 3]
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.id not in world.tracks or b.id not in world.tracks:
                continue
            ax, ay = predicted(a, world.t)
            bx, by = predicted(b, world.t)
            if math.hypot(ax - bx, ay - by) > lim or math.hypot(a.vx - b.vx, a.vy - b.vy) > 0.06:
                continue
            if a.alt is not None and b.alt is not None and abs(a.alt - b.alt) > 3000.0:
                continue
            keep, drop = (a, b) if (a.t_init, a.id) <= (b.t_init, b.id) else (b, a)
            key = f"dup_{keep.id}_{drop.id}"
            world.vars[key] = world.vars.get(key, 0.0) + 1.0
            if world.vars[key] < 30:          # must persist for ~30 s
                continue
            for k, v in drop.truth_votes.items():
                keep.truth_votes[k] = keep.truth_votes.get(k, 0) + v
            keep.company_keys.extend(drop.company_keys)
            keep.sources.update(drop.sources)
            if keep.identity == "pending" and drop.identity != "pending":
                keep.identity, keep.id_basis = drop.identity, drop.id_basis
            if keep.alt is None and drop.alt is not None:
                keep.alt, keep.alt_src, keep.alt_t = drop.alt, drop.alt_src, drop.alt_t
            for lst in (world.hq.engage_ok, world.hq.hostile):
                if drop.id in lst and keep.id not in lst:
                    lst.append(keep.id)
            del world.tracks[drop.id]
            world.on_track_removed(drop.id)
            for fl in world.flights.values():
                if fl.target == drop.id:
                    fl.target = keep.id
            for s in world.sams.values():
                if s.assigned == drop.id:
                    s.assigned = keep.id
            world.log_event("track", f"Duplicate track {drop.id} merged into {keep.id}", keep.id)
