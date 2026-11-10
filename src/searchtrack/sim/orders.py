"""One-click orders: the duty officer picks the unit, the commander picks the job.

The player says what should happen to a track — intercept it, identify it, shadow it, put
missiles on it — and this module chooses who does it: the free interceptor already in the
air that can reach the target soonest, or the squadron that can, counting its alert state;
the ready missile unit with the target inside its acquisition range. It then issues the
ordinary commands, so doctrine, communications and rules of engagement still apply: a
weapons release still needs clearance, a cut line still stops the order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from . import gci, intercept
from .flight import mil_speed
from .tracking import predicted

if TYPE_CHECKING:
    from .world import World

TASKS = ("intercept", "id", "shadow")
FREE_STATES = ("airborne", "vector", "cap", "hold")


@dataclass
class Pick:
    kind: str           # "flight" | "squadron" | "sam"
    id: str
    eta_s: float        # time until the unit can be on (or firing at) the target
    why: str = ""


def _eta(world: "World", x: float, y: float, alt: float, type_id: str, trk) -> Optional[float]:
    at = world.catalog.aircraft[type_id]
    v = mil_speed(at, max(alt, 6000.0)) / 1000.0
    px, py = predicted(trk, world.t)
    return intercept.collision_time(px, py, trk.vx, trk.vy, x, y, v)


def _flight_ok(world: "World", fl, track_id: str) -> bool:
    if fl.state not in FREE_STATES and not (fl.target == track_id and fl.state not in ("rtb", "landed", "lost")):
        return False
    if fl.target and fl.target != track_id and fl.task != "cap" and fl.target in world.tracks \
            and not world.tracks[fl.target].lost:
        return False                       # busy with another target
    lead = gci.lead_of(world, fl)
    if lead is None:
        return False
    return lead.fuel > gci.rtb_fuel(world, lead) * 1.6


def interceptor(world: "World", track_id: str, keep_cap_km: float = 0.0) -> tuple[Optional[Pick], str]:
    """The quickest way to put an interceptor on the track. With keep_cap_km, a fighter on a
    combat air patrol is only pulled off its station for a target within that distance of it."""
    trk = world.tracks.get(track_id)
    if trk is None or trk.lost:
        return None, "no such track"
    for fl in world.flights.values():          # a flight already on it is re-tasked, not doubled up
        if fl.target == track_id and fl.state not in ("rtb", "landed", "lost"):
            return Pick("flight", fl.id, 0.0, f"{fl.callsign} is already on {track_id}"), "already assigned"
    best: Optional[Pick] = None
    px, py = predicted(trk, world.t)
    for fl in world.flights.values():
        if not _flight_ok(world, fl, track_id):
            continue
        if keep_cap_km > 0 and fl.task == "cap" and fl.cap_x is not None and \
                math.hypot(px - fl.cap_x, py - fl.cap_y) > keep_cap_km:
            continue
        lead = gci.lead_of(world, fl)
        t = _eta(world, lead.x, lead.y, lead.alt, fl.type_id, trk)
        if t is not None and (best is None or t < best.eta_s):
            best = Pick("flight", fl.id, t, f"{fl.callsign} airborne, {t / 60:.0f} min to the target")
    reasons = []
    for sq in world.squadrons.values():
        base = world.airbases.get(sq.base_id)
        if base is None:
            continue
        link = world.links.get(base.link)
        if gci.available(sq) <= 0 or sq.pilots <= 0:
            reasons.append(f"{sq.name}: nothing on alert")
            continue
        if not base.runway_ok or (link is not None and not link.up):
            reasons.append(f"{sq.name}: {'runway closed' if not base.runway_ok else 'line down'}")
            continue
        ready = min(float(k) for k, v in sq.ready.items() if v > 0)
        t = _eta(world, base.x, base.y, 6000.0, sq.type_id, trk)
        if t is None:
            reasons.append(f"{sq.name}: cannot catch it (too fast, opening)")
            continue
        t += ready * 60.0 * 0.7 + 120.0        # alert state, then the climb out
        if best is None or t < best.eta_s:
            best = Pick("squadron", sq.id, t, f"{sq.name} from {base.name}, {t / 60:.0f} min to the target")
    if best is None:
        return None, "; ".join(reasons[:3]) or "no interceptor can reach it"
    return best, best.why


def missile_unit(world: "World", track_id: str) -> tuple[Optional[Pick], str]:
    """The ready missile unit best placed to engage the track (BOMARC needs the key)."""
    trk = world.tracks.get(track_id)
    if trk is None or trk.lost:
        return None, "no such track"
    if not world.sams:
        return None, "no missile units in this sector"
    px, py = predicted(trk, world.t)
    best: Optional[Pick] = None
    reasons = []
    for s in world.sams.values():
        st = world.catalog.sams[s.type_id]
        if st.homing_km > 0:
            continue
        d = math.hypot(px - s.x, py - s.y)
        link = world.links.get(s.link)
        if s.assigned == track_id and s.state in ("search", "locked", "engaging"):
            return None, f"{s.name} is already engaging {track_id}"
        if s.status != "ok":
            reasons.append(f"{s.name}: {s.status}")
        elif link is not None and not link.up:
            reasons.append(f"{s.name}: line down")
        elif s.assigned and s.assigned != track_id and s.assigned in world.tracks:
            reasons.append(f"{s.name}: engaging {s.assigned}")
        elif s.ready_missiles <= 0:
            reasons.append(f"{s.name}: no missiles on the rails")
        elif d > st.acq_range_km * 1.3:
            continue
        else:
            wait = max(0.0, s.t_ready - world.t)
            score = d / 10.0 + wait          # nearer and readier is better
            if best is None or score < best.eta_s:
                best = Pick("sam", s.id, score, f"{s.name}, {d:.0f} km")
    if best is None:
        return None, "; ".join(reasons[:3]) or "no missile unit has it in range"
    return best, best.why
