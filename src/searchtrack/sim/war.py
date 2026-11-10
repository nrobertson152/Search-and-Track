"""The war: battles fought one after another by the same forces.

A war (data/campaigns/*.toml) is a short run of battle missions. Between them the order of
battle carries over. Aircraft shot down stay lost until replacements arrive; ships are
patched up only partly, and a ship that was crippled is in the dockyard; radars that were
wrecked stay wrecked. The enemy's losses carry over too: a regiment cut in half on the first
day comes back at half strength on the second, and an enemy cruiser put out of action fires
no missiles the next night. Some missions branch on how the last battle went, and a war ends
early if the force loses what it cannot fight without.

Everything here works on plain dictionaries, so the career file can store a war in progress.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from . import scenario
from .catalog import load_toml

if TYPE_CHECKING:
    from .world import World


def campaign_dir() -> Path:
    return scenario.scenario_dir().parent / "campaigns"


def campaigns(faction: Optional[str] = None) -> list[dict[str, Any]]:
    out = []
    for p in sorted(campaign_dir().glob("*.toml")):
        d = load_toml(p)
        if faction is None or d.get("faction") == faction:
            out.append(d)
    out.sort(key=lambda d: d.get("order", 50))
    return out


def campaign(cid: str) -> dict[str, Any]:
    return load_toml(campaign_dir() / f"{cid}.toml")


def new_state(cid: str) -> dict[str, Any]:
    return {"id": cid, "mission": 0, "results": [], "oob": {"ships": {}, "groups": {}, "squadrons": {},
                                                             "sites": []}, "over": False, "outcome": "", "note": ""}


def current(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The mission to fly next (after any branch on the last battle's outcome), or None when the war is over."""
    if state.get("over"):
        return None
    c = campaign(state["id"])
    i = int(state.get("mission", 0))
    if i >= len(c.get("mission", [])):
        return None
    m = dict(c["mission"][i])
    if state.get("results") and "branch" in m:
        m["scenario"] = m["branch"].get(state["results"][-1]["outcome"], m["scenario"])
    return m


def build_world(state: dict[str, Any], seed: Optional[int] = None) -> "World":
    m = current(state)
    if m is None:
        raise ValueError("the war is over")
    w = scenario.build_world(m["scenario"], seed=seed, assumed=False)
    apply(w, state.get("oob", {}))
    w.vars["war_mission"] = float(state.get("mission", 0))
    return w


# ------------------------------------------------------------------ the order of battle carried over

def _remove_ship(w: "World", sid: str) -> None:
    w.ships.pop(sid, None)
    for k in [k for k, s in w.sams.items() if s.carrier == sid]:
        del w.sams[k]
    for k in [k for k, r in w.radars.items() if r.carrier == sid]:
        del w.radars[k]
    if sid in w.airbases and w.airbases[sid].carrier:
        del w.airbases[sid]
        for sq in w.squadrons.values():
            if sq.base_id == sid:
                sq.ready = {k: 0 for k in sq.ready}
    w.battle.red_plan["vital"] = [v for v in w.battle.red_plan.get("vital", []) if v != sid]


def _shrink(sq, n: int) -> int:
    """Take n aircraft out of a squadron, from the slowest readiness first. Returns how many were taken."""
    taken = 0
    for k in sorted(sq.ready, key=lambda k: -float(k)):
        while n > taken and sq.ready[k] > 0:
            sq.ready[k] -= 1
            taken += 1
    sq.pilots = max(0, sq.pilots - taken)
    return taken


def apply(w: "World", oob: dict[str, Any]) -> None:
    """Fit a freshly built battle to the forces that are left."""
    b = w.battle
    for sid, rec in oob.get("ships", {}).items():
        sh = w.ships.get(sid)
        if sh is None:
            continue
        if rec["state"] in ("sunk", "crippled"):
            _remove_ship(w, sid)
            continue
        sh.hp = sh.max_hp * max(0.05, min(1.0, float(rec["hp_frac"])))
        frac = sh.hp / sh.max_hp
        sh.state = "damaged" if frac < 0.65 else "afloat"
        sh.hits = int(rec.get("hits", 0))
    for gid, rec in oob.get("groups", {}).items():
        g = b.groups.get(gid)
        if g is None:
            continue
        g.n = max(0, g.n - int(rec.get("lost", 0)))
        if g.n == 0:
            g.state = "done"
    for sqid, rec in oob.get("squadrons", {}).items():
        sq = w.squadrons.get(sqid)
        if sq is not None and int(rec.get("lost", 0)) > 0:
            _shrink(sq, int(rec["lost"]))
    for site in oob.get("sites", []):
        w.vars[f"dead_{site}"] = 1.0
        if site in w.radars:
            r = w.radars[site]
            r.status, r.repair_t, r.fail_t = "down", -1.0, 1e12
        if site in w.sams:
            w.sams[site].status = "down"
            w.sams[site].ready_missiles = 0
    # objectives about ships that are not here any more cannot be fought for
    own_ships = any(s.side == w.own_side for s in w.ships.values())
    keep = []
    for o in w.objectives:
        p = o.params
        ships = [p["ship"]] if "ship" in p else list(p.get("ships", []))
        if ships and not any(s in w.ships for s in ships):
            continue
        if not own_ships and o.kind in ("deny_location", "ships_survive", "hold_area"):
            continue
        keep.append(o)
    w.objectives = keep


def extract(w: "World") -> dict[str, Any]:
    """This battle's losses, ready to be added to the war's order of battle."""
    out: dict[str, Any] = {"ships": {}, "groups": {}, "squadrons": {}, "sites": []}
    for sh in w.ships.values():
        out["ships"][sh.id] = {"state": sh.state, "hp_frac": round(max(0.0, sh.hp) / max(sh.max_hp, 1.0), 3),
                               "hits": sh.hits, "side": sh.side, "name": sh.name}
    for g in w.battle.groups.values():
        out["groups"][g.id] = {"lost": g.losses, "side": g.side, "name": g.name}
    for sq in w.squadrons.values():
        lost = int(w.battle.counters.get(f"sq_lost_{sq.id}", 0.0)) + sq.lost
        out["squadrons"][sq.id] = {"lost": lost, "name": sq.name, "side": sq.side}
    out["sites"] = sorted(k[5:] for k, v in w.vars.items() if k.startswith("dead_") and v)
    return out


def advance(state: dict[str, Any], w: "World") -> dict[str, Any]:
    """Book a finished battle into the war and patch the force up for the next one."""
    from .battle.core import outcome as battle_outcome
    c = campaign(state["id"])
    m = current(state) or {}
    got, total, _ = scenario.score(w)
    oc = w.battle.outcome or battle_outcome(w)
    state["results"].append({"scenario": w.scenario_id, "title": m.get("title", w.title), "outcome": oc,
                             "score": int(got), "total": int(total)})
    ex = extract(w)
    oob = state["oob"]
    for sid, rec in ex["ships"].items():
        oob["ships"][sid] = rec
    for gid, rec in ex["groups"].items():
        old = oob["groups"].get(gid, {"lost": 0})
        oob["groups"][gid] = {**rec, "lost": int(old.get("lost", 0)) + int(rec["lost"])}
    for qid, rec in ex["squadrons"].items():
        old = oob["squadrons"].get(qid, {"lost": 0})
        oob["squadrons"][qid] = {**rec, "lost": int(old.get("lost", 0)) + int(rec["lost"])}
    oob["sites"] = sorted(set(oob.get("sites", [])) | set(ex["sites"]))
    # between the battles: the yards and the replacement pools
    repair = float(m.get("repair", c.get("repair", 0.15)))
    for rec in oob["ships"].values():
        if rec["state"] in ("afloat", "damaged"):
            rec["hp_frac"] = round(min(1.0, rec["hp_frac"] + repair), 3)
            rec["state"] = "damaged" if rec["hp_frac"] < 0.65 else "afloat"
    for qid, n in m.get("replacements", {}).items():
        if qid in oob["squadrons"]:
            oob["squadrons"][qid]["lost"] = max(0, oob["squadrons"][qid]["lost"] - int(n))
    state["mission"] = int(state.get("mission", 0)) + 1
    for sid in m.get("requires", []):
        rec = oob["ships"].get(sid)
        if rec is not None and rec["state"] in ("sunk", "crippled"):
            state["over"] = True
            state["note"] = m.get("requires_text", f"{rec.get('name', sid)} is lost: the war is over for this force.")
    if state["mission"] >= len(c.get("mission", [])):
        state["over"] = True
    if state["over"]:
        state["outcome"] = war_outcome(state)
    return state


def war_outcome(state: dict[str, Any]) -> str:
    res = state.get("results", [])
    if not res:
        return ""
    pct = sum(r["score"] for r in res) / max(1, sum(r["total"] for r in res))
    if state.get("note") or pct < 0.4:
        return "DEFEAT"
    return "VICTORY" if pct >= 0.65 else "DRAW"


def summary(state: dict[str, Any], faction: str) -> list[str]:
    """What is left of the force, in a few lines for the war room."""
    oob = state.get("oob", {})
    own = "blue"
    lines = []
    sq = [f"{r['name']}: {r['lost']} lost" for r in oob.get("squadrons", {}).values()
          if r.get("side", own) == own and r.get("lost")]
    if sq:
        lines.append("Aircraft: " + "; ".join(sq))
    ships = [f"{r['name']} {r['state']}" + (f" ({r['hp_frac'] * 100:.0f}%)" if r["state"] == "damaged" else "")
             for r in oob.get("ships", {}).values() if r.get("side") == own and r["state"] != "afloat"]
    if ships:
        lines.append("Ships: " + ", ".join(ships))
    foe = [f"{r['name']} −{r['lost']}" for r in oob.get("groups", {}).values()
           if r.get("side") != own and r.get("lost")]
    if foe:
        lines.append("Enemy losses carried over: " + ", ".join(foe[:6]))
    foe_ships = [f"{r['name']} {r['state']}" for r in oob.get("ships", {}).values()
                 if r.get("side") != own and r["state"] != "afloat"]
    if foe_ships:
        lines.append("Enemy ships: " + ", ".join(foe_ships))
    if oob.get("sites"):
        lines.append(f"Ground sites destroyed: {len(oob['sites'])}")
    return lines or ["The force is intact."]
