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
    kills = []
    for victim, shooter, side in st.kills:
        ac = world.aircraft.get(victim)
        label = f"{ac.callsign} ({ac.truth_label})" if ac else victim
        kills.append({"victim": label, "by": shooter, "side": side})
    rep["consequences"] = {"kills": kills, "civil_losses": int(world.vars.get("civil_losses", 0)),
                           "fratricide": int(world.vars.get("fratricide", 0))}
    rep["command"] = {"unacked_overdue": st.unacked_overdue, "reports_to_hq": st.reports_to_hq,
                      "hq_credibility": round(world.hq.credibility, 2),
                      "requests": [{"kind": r.kind, "ref": r.ref, "granted": r.granted, "reason": r.reason,
                                    "t": _fmt(world, r.t)} for r in world.hq.requests]}
    rep["timeline"] = [{"t": _fmt(world, e.t), "cat": e.cat, "text": e.text} for e in world.log
                       if e.cat in ("cmd", "id", "weapon", "result", "scenario") and not e.text.startswith("[truth]")]
    return rep


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
