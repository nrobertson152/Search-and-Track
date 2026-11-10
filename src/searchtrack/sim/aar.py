"""After-action report: evaluation of detection, identification, interception,
expenditure and consequences, built from simulation state and the event log."""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from . import doctrine, scenario

if TYPE_CHECKING:
    from .world import World


def _fmt(world: "World", t: float | None) -> str:
    if t is None:
        return "—"
    return f"T+{int(t // 60):02d}:{int(t % 60):02d}"


def build(world: "World") -> dict[str, Any]:
    got, total, grade = scenario.score(world)
    rep: dict[str, Any] = {
        "title": world.title, "faction": world.faction, "result": world.result or "in progress",
        "reason": world.end_reason, "score": got, "total": total, "grade": grade,
        "objectives": [{"text": o.text, "status": o.status, "points": o.points, "penalty": o.penalty,
                        "t": _fmt(world, o.t_status if o.t_status >= 0 else None)}
                       for o in world.objectives if not (o.hidden and o.status == "open")],
    }
    st = world.stats
    rows = []
    for ac in world.aircraft.values():
        if ac.kind not in ("aircraft", "ghost", "balloon") or ac.flight_id:
            continue
        aid = ac.id
        fid = st.first_id.get(aid)
        ref = st.adiz.get(aid, st.first_track.get(aid))
        why = ""
        if aid not in st.first_track:
            reasons = Counter(bd.limit for (sid, tid), (_, bd) in world.last_eval.items() if tid == aid and bd.limit)
            if reasons:
                why = ", ".join(f"{doctrine_reason(r)} ×{n}" for r, n in reasons.most_common(3))
            else:
                why = "never in radar coverage"
        rows.append({
            "truth": f"{ac.callsign} ({ac.truth_label})", "side": ac.side, "kind": ac.kind,
            "first_plot": _fmt(world, st.first_plot.get(aid)), "first_track": _fmt(world, st.first_track.get(aid)),
            "adiz": _fmt(world, st.adiz.get(aid)), "first_id": _fmt(world, fid),
            "id_delay_s": (fid - ref) if (fid is not None and ref is not None) else None,
            "final_id": doctrine.id_label(world, st.final_id.get(aid, "")) if aid in st.final_id else "—",
            "vid": _fmt(world, st.vid.get(aid)), "fate": ac.state if ac.state != "airborne" else "in flight",
            "why_untracked": why,
        })
    rep["identification"] = rows
    rep["flights"] = [{"callsign": f.callsign, "type": f.type_id, "task": f.task, "target": f.target or "—",
                       "vid": f.vid_done, "shots": f.shots, "kills": len(f.kills), "state": f.state}
                      for f in world.flights.values()]
    rep["expenditure"] = {"sorties": st.sorties, "aam_shots": st.aam_shots, "sam_missiles": st.missiles,
                          "fuel_emergencies": st.fuel_emergencies, "tracks_initiated": st.tracks_initiated,
                          "false_tracks": st.false_tracks}
    from .battle.combat import unit_name
    kills = []
    for victim, shooter, side in st.kills:
        ac = world.aircraft.get(victim)
        label = f"{ac.callsign} ({ac.truth_label})" if ac else victim
        kills.append({"victim": label, "by": unit_name(world, shooter) if shooter else "—", "side": side})
    rep["consequences"] = {"kills": kills, "civil_losses": int(world.vars.get("civil_losses", 0)),
                           "fratricide": int(world.vars.get("fratricide", 0))}
    rep["command"] = {"unacked_overdue": st.unacked_overdue, "reports_to_hq": st.reports_to_hq,
                      "hq_credibility": round(world.hq.credibility, 2),
                      "requests": [{"kind": r.kind, "ref": r.ref, "granted": r.granted, "reason": r.reason,
                                    "t": _fmt(world, r.t)} for r in world.hq.requests]}
    rep["timeline"] = [{"t": _fmt(world, e.t), "cat": e.cat, "text": e.text} for e in world.log
                       if e.cat in ("cmd", "id", "weapon", "result", "scenario") and not e.text.startswith("[truth]")]
    if world.battle.active:
        rep["battle"] = battle_summary(world)
        rep["timeline"] = [{"t": _fmt(world, e[0]), "cat": e[1], "text": e[2].replace("[enemy] ", "ENEMY: ")}
                           for e in world.battle.events if e[7] >= 1 or e[1] in ("launch", "asm_launch", "located")]
    return rep


def battle_summary(world: "World") -> dict[str, Any]:
    """What the battle cost each side, what was fired and what got through."""
    b = world.battle
    c = b.counters
    own = world.own_side
    foe = "red" if own == "blue" else "blue"
    lost_types: dict[str, Counter] = {own: Counter(), foe: Counter()}
    for victim, shooter, side in world.stats.kills:
        ac = world.aircraft.get(victim)
        if ac is None or ac.aim or side not in lost_types:
            continue
        at = world.catalog.aircraft.get(ac.type_id)
        lost_types[side][at.name.split(" (")[0] if at else ac.type_id] += 1

    def fmt(cnt: Counter) -> str:
        return ", ".join(f"{n}× {k}" for k, n in cnt.most_common()) or "none"
    ships = {own: [], foe: []}
    for s in world.ships.values():
        if s.side in ships and s.state != "afloat":
            ships[s.side].append(f"{s.name} ({s.state})")
    summary = [
        f"Our losses: {fmt(lost_types[own])}",
        f"Enemy losses: {fmt(lost_types[foe])}",
        f"Our ships: {', '.join(ships[own]) or 'all undamaged'}",
        f"Enemy ships: {', '.join(ships[foe]) or 'all undamaged'}",
        f"Anti-ship missiles at us: {int(c.get(f'asm_{foe}', 0))} fired, {int(c.get(f'asm_killed_{foe}', 0))} shot "
        f"down, {int(c.get(f'ciws_kills_{own}', 0))} stopped by close-in guns, {int(c.get(f'asm_hits_{foe}', 0))} hits",
        f"Our anti-ship missiles: {int(c.get(f'asm_{own}', 0))} fired, {int(c.get(f'asm_hits_{own}', 0))} hits",
        f"Air-to-air missiles: ours {int(c.get(f'aam_shots_{own}', 0))}, theirs {int(c.get(f'aam_shots_{foe}', 0))}",
    ]
    from .pilots import night
    summary += night(world)
    decisions = [f"{_fmt(world, d.t)} {d.title}: {d.chosen}{' (staff)' if d.by != 'player' else ''}"
                 for d in b.decisions if d.chosen]
    return {"outcome": b.outcome, "summary": summary, "decisions": decisions,
            "counters": {k: v for k, v in c.items()}}


def doctrine_reason(limit: str) -> str:
    from .radar import DetectionBreakdown
    return DetectionBreakdown("", "", limit=limit).explain()


def as_text(rep: dict[str, Any]) -> str:
    out = [f"AFTER-ACTION REPORT — {rep['title']}", f"Result: {rep['result']}  ({rep['reason']})",
           f"Evaluation: {rep['grade']}  {rep['score']}/{rep['total']} points", "", "OBJECTIVES"]
    for o in rep["objectives"]:
        mark = {"done": "[+]", "failed": "[x]", "open": "[ ]"}[o["status"]]
        out.append(f"  {mark} {o['text']}  ({o['points']} pts{', penalty ' + str(o['penalty']) if o['penalty'] and o['status'] == 'failed' else ''}) {o['t']}")
    out += ["", "DETECTION & IDENTIFICATION (truth revealed)"]
    for r in rep["identification"]:
        d = f"{r['id_delay_s'] / 60:.1f} min" if r["id_delay_s"] is not None else "—"
        out.append(f"  {r['truth']:<44} plot {r['first_plot']} track {r['first_track']} ID {r['final_id']:<12} "
                   f"delay {d:<8} VID {r['vid']} {r['fate']}")
        if r["why_untracked"]:
            out.append(f"      not tracked: {r['why_untracked']}")
    e = rep["expenditure"]
    out += ["", f"EXPENDITURE: {e['sorties']} sorties, {e['aam_shots']} air-to-air, {e['sam_missiles']} SAMs; "
                f"{e['tracks_initiated']} tracks ({e['false_tracks']} false)"]
    c = rep["consequences"]
    out.append(f"CONSEQUENCES: civil losses {c['civil_losses']}, fratricide {c['fratricide']}")
    for k in c["kills"]:
        out.append(f"  destroyed: {k['victim']} by {k['by']}")
    return "\n".join(out)
