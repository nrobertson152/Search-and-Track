"""Doctrine, rules of engagement, higher-HQ authority and communications."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .state import Message, Request

if TYPE_CHECKING:
    from .world import World

ID_LABELS = {
    "US": {"pending": "PENDING", "friend": "FRIEND", "unknown": "UNKNOWN", "suspect": "SUSPECT",
           "hostile": "HOSTILE", "faker": "FAKER"},
    "USSR": {"pending": "ОБРАБ.", "friend": "СВОЙ", "unknown": "НЕОПОЗН.", "suspect": "ЧУЖОЙ",
             "hostile": "НАРУШИТЕЛЬ", "faker": "УЧЕБН."},
}
ID_LABELS_EN = {
    "US": ID_LABELS["US"],
    "USSR": {"pending": "PROCESSING", "friend": "OWN", "unknown": "UNIDENTIFIED", "suspect": "FOREIGN",
             "hostile": "VIOLATOR", "faker": "TRAINING"},
}


def id_label(world: "World", ident: str, english: bool = True) -> str:
    table = (ID_LABELS_EN if english else ID_LABELS).get(world.faction_def.id, ID_LABELS["US"])
    return table.get(ident, ident.upper())


# ------------------------------------------------------------------ comms

def send(world: "World", channel: str, sender: str, text: str, priority: int = 0, ack: bool = False,
         ref: str = "", kind: str = "info", delay: float = 0.0) -> Message:
    m = Message(world.next_id("msg"), world.t, world.t + delay, channel, sender, text, priority, ack,
                ref=ref, kind=kind)
    if delay <= 0.0:
        m.delivered = True
        if isinstance(world.new_messages, list):
            world.new_messages.append(m.mid)
    world.messages.append(m)
    if len(world.messages) > 1500:
        world.messages = [x for x in world.messages[-1200:]] + [x for x in world.messages[:-1200]
                                                                 if x.ack and not x.acked][-100:]
    return m


def comms_step(world: "World") -> None:
    t = world.t
    for m in world.messages:
        if not m.delivered and m.t_deliver <= t:
            m.delivered = True
            world.new_messages.append(m.mid)
        if m.ack and not m.acked and m.delivered and m.kind in ("alert", "order", "response") \
                and t - m.t_deliver > 150.0:
            m.kind = "overdue"
            world.stats.unacked_overdue += 1
            world.hq.credibility = max(0.0, world.hq.credibility - 0.03)
            send(world, "voice", world.hq.name, f"HQ awaiting acknowledgement: {m.text[:60]}", 1, False, m.ref,
                 "reminder")


def acknowledge(world: "World", mid: int) -> bool:
    for m in world.messages:
        if m.mid == mid and m.ack and not m.acked:
            m.acked = True
            m.t_ack = world.t
            return True
    return False


# ------------------------------------------------------------------ ROE

def can_engage_track(world: "World", trk) -> tuple[bool, str]:
    if trk is None:
        return False, "no track"
    hq = world.hq
    if trk.id in hq.engage_ok:
        return True, "engagement authorized by HQ"
    if world.exercise and trk.identity in ("faker", "hostile", "suspect"):
        return True, "exercise rules: simulated engagement"
    st = hq.weapons_status
    lab = id_label(world, trk.identity)
    if world.faction_def.id == "US":
        if st == "FREE" and trk.identity in ("hostile", "suspect", "unknown"):
            return True, "weapons FREE"
        if st == "TIGHT" and trk.identity == "hostile":
            return True, "weapons TIGHT, target hostile"
        return False, f"WEAPONS {st} — {trk.id} is {lab}; request engagement authority"
    if trk.identity == "hostile" and st in ("FREE", "TIGHT"):
        return True, "violator, fire permitted"
    return False, f"NO PERMISSION TO FIRE on {trk.id} ({lab}); request from command post"


def can_engage_site(world: "World", site) -> tuple[bool, str]:
    trk = world.tracks.get(site.assigned)
    ok, why = can_engage_track(world, trk)
    if not ok:
        return ok, why
    st = world.catalog.sams[site.type_id]
    if st.controller == "army":
        tgt = world.aircraft.get(site.lock)
        if tgt is not None:
            for a in world.aircraft.values():
                if a.side == world.own_side and a.flight_id and a.state == "airborne" and \
                        math.hypot(a.x - tgt.x, a.y - tgt.y) < 15.0:
                    return False, "AADCP: FRIENDLY FIGHTERS IN ENGAGEMENT ZONE — HOLD"
    return True, why


# ------------------------------------------------------------------ HQ authority

REQUEST_TEXT = {
    "declare_hostile": "Request hostile declaration on {ref}",
    "engage": "Request authority to engage {ref}",
    "weapons_status": "Request weapons status {value}",
    "special_release": "Request release of special (nuclear) air defense weapons",
    "ram": "Request permission to order ramming attack on {ref}",
    "alert": "Request Air Defense Warning {value}",
    "readiness": "Request readiness {value}",
}


def request(world: "World", kind: str, ref: str = "", value: str = "") -> Request:
    pol = world.hq.policy
    lo, hi = pol.get("response_s", [60.0, 180.0])
    if world.faction_def.id == "USSR":
        lo, hi = lo * 1.3, hi * 1.5
    req = Request(world.next_id("req"), kind, ref, value, world.t, world.t + world.rng.uniform(lo, hi))
    world.hq.requests.append(req)
    send(world, "voice", "SD" if world.faction_def.id == "US" else "ДЕЖУРНЫЙ", REQUEST_TEXT.get(kind, kind).format(ref=ref, value=value),
         0, False, ref, "request")
    world.log_event("cmd", REQUEST_TEXT.get(kind, kind).format(ref=ref, value=value), ref)
    return req


def _evidence_hostile(world: "World", track_id: str) -> tuple[bool, str]:
    trk = world.tracks.get(track_id)
    if trk is None:
        return False, "track no longer held"
    vid = world.vid_reports.get(track_id)
    truth = world.truth_of(trk)
    ac = world.aircraft.get(truth) if truth else None
    if vid and vid[0] not in ("civil", "neutral", world.own_side):
        return True, f"visually identified ({vid[1]})"
    if trk.jammer:
        return True, "track is an active jammer"
    if world.vars.get(f"hostile_act_{truth}", 0.0) > 0:
        return True, "hostile act reported"
    if vid:
        return False, f"visually identified as {vid[1]} — not hostile"
    if ac is not None and ac.side == "civil":
        return False, "insufficient evidence; no visual identification"
    return False, "insufficient evidence; obtain visual identification"


def decide(world: "World", req: Request) -> tuple[bool, str]:
    pol = world.hq.policy
    rule = pol.get(req.kind, "deny")
    if req.kind == "weapons_status":
        rule = pol.get(f"weapons_status_{req.value}", rule)
    if req.kind == "alert":
        rule = pol.get(f"alert_{req.value}", rule)
    if isinstance(rule, str) and rule.startswith("var:"):
        name = rule[4:]
        return (world.vars.get(name, 0.0) > 0, "situation warrants" if world.vars.get(name, 0.0) > 0
                else "situation does not warrant")
    if isinstance(rule, str) and rule.startswith("after:"):
        ok = world.t >= float(rule[6:])
        return ok, "approved" if ok else "not yet — maintain current posture"
    if rule == "grant":
        return True, "approved"
    if rule == "evidence":
        return _evidence_hostile(world, req.ref)
    if rule == "target:" or (isinstance(rule, str) and rule.startswith("target:")):
        allowed = rule.split(":", 1)[1].split(",")
        trk = world.tracks.get(req.ref)
        truth = world.truth_of(trk) if trk else ""
        ok = truth in allowed
        return ok, "approved — destroy the intruder" if ok else "denied — not the designated intruder"
    return False, "denied"


def hq_step(world: "World") -> None:
    hq = world.hq
    for req in hq.requests:
        if req.answered or world.t < req.t_answer:
            continue
        req.answered = True
        req.granted, req.reason = decide(world, req)
        verdict = "APPROVED" if req.granted else "DENIED"
        if req.granted:
            if req.kind == "declare_hostile":
                if req.ref not in hq.hostile:
                    hq.hostile.append(req.ref)
                world.set_identity(req.ref, "hostile", "declared hostile by HQ", authority=True)
            elif req.kind in ("engage", "ram"):
                if req.ref not in hq.engage_ok:
                    hq.engage_ok.append(req.ref)
                if req.kind == "engage" and world.faction_def.id == "USSR":
                    world.set_identity(req.ref, "hostile", "violator — fire permitted by CP", authority=True)
            elif req.kind == "weapons_status":
                hq.weapons_status = req.value
            elif req.kind == "special_release":
                hq.special_release = True
            elif req.kind == "alert":
                hq.alert = req.value
            elif req.kind == "readiness":
                hq.readiness = req.value
        else:
            truth = world.truth_of(world.tracks[req.ref]) if req.ref in world.tracks else ""
            ac = world.aircraft.get(truth) if truth else None
            if req.kind in ("declare_hostile", "engage") and ac is not None and ac.side in ("civil", world.own_side):
                hq.credibility = max(0.0, hq.credibility - 0.1)
        text = f"{verdict}: {REQUEST_TEXT.get(req.kind, req.kind).format(ref=req.ref, value=req.value)} — {req.reason}"
        send(world, "voice", hq.name, text, 2 if req.granted else 1, True, req.ref, "response")
        world.log_event("cmd", text, req.ref)
