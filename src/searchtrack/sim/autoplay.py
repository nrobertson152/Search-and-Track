"""A simple rule-based commander that plays any scenario through the command
interface. Used by the test-suite (every scenario must run to its end without
errors) and as a reference for how the commands fit together."""
from __future__ import annotations

import math

from . import commands, gci, ident, tracking
from .world import World


def _run(w: World, kind: str, /, **kw):
    return commands.run(w, kind, **kw)


def think(w: World) -> None:
    if w.ended:
        return
    _run(w, "ack_all")
    if w.faction_def.pipeline == "digital" and not w.automation.get("surveil") and w.c2_up():
        tracking.auto_initiate(w, w.plots, w.tracks, min_hits=3, latency=10.0)
    if "active" not in w.duplex.values() and w.duplex_until < 0 and w.faction == "US":
        _run(w, "switchover")
    busy = {f.target for f in w.flights.values() if f.state not in ("landed", "lost")}
    for trk in list(w.tracks.values()):
        if trk.lost:
            continue
        rec, basis = ident.recommend(w, trk)
        if w.exercise and trk.identity in ("pending", "unknown", "suspect") and rec in ("unknown", "pending", "suspect") \
                and not trk.iff and w.t - trk.t_init > 60:
            _run(w, "identity", track=trk.id, ident="faker")
            continue
        if trk.identity == "pending" or (trk.identity == "unknown" and rec != "unknown"):
            _run(w, "identity", track=trk.id, ident=rec if rec in ("friend", "unknown", "suspect") else "unknown")
        if trk.alt is None and not trk.hf_requested and w.hfs:
            _run(w, "height", track=trk.id)
        single_source = len(trk.sources) <= 1 and trk.alt_fails >= 2 and not trk.iff
        if single_source and w.t - trk.t_init > 400:
            _run(w, "drop_track", track=trk.id)
            continue
        if trk.identity in ("unknown", "suspect") and trk.id not in busy and trk.id not in w.vid_reports:
            sq = _nearest_squadron(w, trk)
            if sq is not None:
                ok, msg = _run(w, "scramble", squadron=sq.id, n=2, task="id", track=trk.id)
                if ok:
                    busy.add(trk.id)
        if w.faction == "USSR" and trk.identity == "suspect" and trk.id not in w.hq.engage_ok:
            if not any(r.ref == trk.id and r.kind == "engage" for r in w.hq.requests):
                _run(w, "request", kind="engage", track=trk.id)
        if trk.identity == "faker" and w.exercise and trk.id not in busy:
            sq = _nearest_squadron(w, trk)
            if sq is not None:
                ok, msg = _run(w, "scramble", squadron=sq.id, n=2, task="intercept", track=trk.id)
                if ok:
                    busy.add(trk.id)
        free = w.hq.weapons_status == "FREE" and w.faction == "US" and trk.identity in ("suspect", "hostile") \
            and not trk.iff
        if free and trk.id not in busy:
            sq = _nearest_squadron(w, trk)
            if sq is not None and _run(w, "scramble", squadron=sq.id, n=2, task="intercept", track=trk.id)[0]:
                busy.add(trk.id)
        if trk.id in w.hq.engage_ok or trk.identity == "hostile" or (w.exercise and trk.identity == "faker") or free:
            for s in w.sams.values():
                st = w.catalog.sams[s.type_id]
                if st.homing_km > 0 or s.assigned:
                    continue
                if math.hypot(trk.x - s.x, trk.y - s.y) < st.acq_range_km:
                    _run(w, "sam_assign", site=s.id, track=trk.id)
            for f in w.flights.values():
                if f.target == trk.id and not f.weapons_free and f.state not in ("landed", "lost"):
                    _run(w, "weapons_free", flight=f.id, on=True)
                if (w.exercise or free) and f.target == trk.id and f.task != "intercept" and \
                        f.state not in ("landed", "lost"):
                    _run(w, "task", flight=f.id, task="intercept")
        if not trk.reported and trk.identity in ("suspect", "hostile"):
            _run(w, "report", track=trk.id)
    for f in list(w.flights.values()):
        if f.state in ("landed", "lost", "scrambling", "rtb"):
            continue
        trk = w.tracks.get(f.target)
        if f.vid_done and (trk is None or trk.id not in w.hq.engage_ok):
            vid = w.vid_reports.get(f.target)
            if vid and trk is not None:
                _run(w, "identity", track=trk.id, ident="friend" if vid[0] in ("civil", "blue", "neutral") else "suspect")
            _run(w, "rtb", flight=f.id)
        elif not f.target and f.state == "hold":
            _run(w, "rtb", flight=f.id)


def _nearest_squadron(w: World, trk):
    best, bd = None, math.inf
    for sq in w.squadrons.values():
        if gci.available(sq) <= 0:
            continue
        b = w.airbases[sq.base_id]
        d = math.hypot(b.x - trk.x, b.y - trk.y)
        if d < bd and d < 700:
            best, bd = sq, d
    return best


def play(w: World, max_s: float | None = None, think_every: int = 10) -> World:
    limit = w.duration if max_s is None else min(max_s, w.duration)
    while not w.ended and w.t < limit:
        if w.tick % think_every == 0:
            think(w)
        w.step()
    return w
