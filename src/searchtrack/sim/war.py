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

from . import scenario, story
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
    st = {"id": cid, "mission": 0, "results": [], "oob": {"ships": {}, "groups": {}, "squadrons": {},
                                                           "sites": []}, "over": False, "outcome": "", "note": "",
          "roster": [], "mercy": 0, "hard": 0, "fallen": [], "ships_lost": [], "inbox": [], "chronicle": []}
    try:
        c = campaign(cid)
    except (OSError, ValueError):
        return st
    ctx = _context(st, c, None, {})
    _queue(st, story.pages(c.get("intro", []), ctx))
    if c.get("mission"):
        _queue(st, story.pages(story.mission_pages(c["mission"][0], "before"), ctx))
    return st


def _lost(state: dict[str, Any], sid: str) -> bool:
    rec = state.get("oob", {}).get("ships", {}).get(sid)
    return rec is not None and rec.get("state") in ("sunk", "crippled")


def next_index(state: dict[str, Any], c: Optional[dict[str, Any]] = None) -> int:
    """The next mission that can still be fought: a battle that needs a ship the war has lost
    (`skip_without`) is passed over."""
    c = c or campaign(state["id"])
    ms = c.get("mission", [])
    i = int(state.get("mission", 0))
    while i < len(ms) and any(_lost(state, sid) for sid in ms[i].get("skip_without", [])):
        i += 1
    return i


def current(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The mission to fly next (after any branch on the last battle's outcome), or None when the war is over."""
    if state.get("over"):
        return None
    c = campaign(state["id"])
    i = next_index(state, c)
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
    sc = scenario.load_scenario(m["scenario"])
    joining = {s["id"]: dict(s) for s in list(state.get("joined", [])) + list(m.get("ship_join", []))}
    if joining:                                  # ships sent to reinforce the force stay with it
        groups = {s.get("group") for s in sc.get("ship", [])}
        have = {s.get("id") for s in sc.get("ship", [])}
        sc = {**sc, "ship": list(sc.get("ship", [])) +
              [s for s in joining.values() if s.get("group") in groups and s["id"] not in have]}
    w = scenario.build_world_from(sc, seed=seed, assumed=False)
    apply(w, state.get("oob", {}))
    install_roster(w, state)
    w.vars["war_mission"] = float(state.get("mission", 0))
    return w


# ------------------------------------------------------------------ the aircrews carried over

def install_roster(w: "World", state: dict[str, Any]) -> None:
    """The war's pilots replace the battle's default roster: the aces of the first night fly on the second,
    the dead do not, the ones fished out of the sea are back on the schedule."""
    from . import pilots as crew
    from .state import Pilot
    roster = state.get("roster") or []
    if not roster or not w.battle.active:
        return
    b = w.battle
    b.pilots = {}
    for rec in roster:
        st = rec.get("status", "active")
        b.pilots[rec["id"]] = Pilot(id=rec["id"], name=rec["name"], squadron=rec["squadron"], rank=rec.get("rank", ""),
                                    surname=rec.get("surname", ""), kills=int(rec.get("kills", 0)),
                                    sorties=int(rec.get("sorties", 0)),
                                    status="active" if st in ("active", "rescued", "flying") else st)
    crew.ensure_roster(w)                         # squadrons new to the war get pilots of their own
    for a in w.aircraft.values():                 # the patrols already airborne: crewed again from the war's roster
        a.pilot = ""
    for fl in w.flights.values():
        if fl.state not in ("landed", "lost") and fl.members:
            crew.crew(w, fl)


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
    mi = next_index(state, c)                    # which of the war's battles this was
    got, total, _ = scenario.score(w)
    oc = w.battle.outcome or battle_outcome(w)
    state["results"].append({"scenario": w.scenario_id, "title": m.get("title", w.title), "outcome": oc,
                             "score": int(got), "total": int(total), "date": story.date_of(w), "mission": mi})
    tonight = _book_aircrew(state, w)
    mercy_now = int(w.vars.get("mercy", 0.0))
    hard_now = 1 if (not mercy_now and any(d.kind in ("war", "mercy") and d.chosen for d in w.battle.decisions)) else 0
    state["mercy"] = int(state.get("mercy", 0)) + mercy_now
    if mercy_now:
        state.setdefault("mercy_log", []).append(mi)
    if hard_now:
        state.setdefault("hard_log", []).append(mi)
    state["hard"] = int(state.get("hard", 0)) + hard_now
    lost_before = {sid for sid in c.get("vital", []) if _lost(state, sid)}
    for sh in w.ships.values():
        if sh.side == w.own_side and sh.state in ("sunk", "crippled") and \
                not any(r["id"] == sh.id for r in state.setdefault("ships_lost", [])):
            state["ships_lost"].append({"id": sh.id, "name": sh.name, "state": sh.state, "date": story.date_of(w)})
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
    joined = state.setdefault("joined", [])
    joined += [dict(s) for s in m.get("ship_join", []) if not any(j["id"] == s["id"] for j in joined)]
    state["mission"] = int(state.get("mission", 0)) + 1
    for sid in m.get("requires", []):
        rec = oob["ships"].get(sid)
        if rec is not None and rec["state"] in ("sunk", "crippled"):
            state["over"] = True
            state["note"] = m.get("requires_text", f"{rec.get('name', sid)} is lost: the war is over for this force.")
    skip = next_index(state, c)
    if skip > state["mission"]:                  # battles that cannot be fought without what was lost
        state.setdefault("skipped", []).extend(range(state["mission"], skip))
        if not state.get("note"):
            state["note"] = c.get("lost_text", "")
        state["mission"] = skip
    if state["mission"] >= len(c.get("mission", [])):
        state["over"] = True
    if state["over"]:
        state["outcome"] = war_outcome(state)
    _between_battles(state, c)
    # ---- the story: what this battle meant, and what comes next
    flags = {"victory": oc == "VICTORY", "draw": oc == "DRAW", "defeat": oc == "DEFEAT", "mercy": mercy_now > 0,
             "hard": hard_now > 0, "fallen": bool(tonight["fallen"]), "ace": bool(tonight["aces"]),
             "vital_lost": any(_lost(state, sid) for sid in c.get("vital", [])), "over": bool(state.get("over"))}
    flags.update({f"down_{iid}": True for iid in state["oob"].get("sites", [])})   # radars and sites destroyed
    lost_now = [sid for sid in c.get("vital", []) if _lost(state, sid) and sid not in lost_before]
    ctx = _context(state, c, w, tonight)
    ctx.update(m.get("cast", {}))                # a battle can bring its own people
    if lost_now and c.get("lost"):              # the battle's own pages assume she came through it
        _queue(state, story.pages(c["lost"], ctx, flags))
    else:
        _queue(state, story.pages(story.mission_pages(m, "after"), ctx, flags))
    _queue(state, story.aircrew_pages(state, w, tonight, ctx))
    nxt = current(state)
    if nxt is not None:                          # what comes next: written after this mission, or before the next
        _queue(state, story.pages(story.mission_pages(m, "next"), ctx, flags))
        _queue(state, story.pages(story.mission_pages(nxt, "before"), ctx, flags))
    else:
        flags.update({"war_" + state["outcome"].lower(): True, "mercy_war": state.get("mercy", 0) > 0,
                      "hard_war": state.get("hard", 0) > 0, "ended_early": bool(state.get("note"))})
        flags.update({f"mercy_{i}": True for i in state.get("mercy_log", [])})
        flags.update({f"hard_{i}": True for i in state.get("hard_log", [])})
        _queue(state, story.pages(c.get("epilogue", []), ctx, flags))
        _queue(state, story.closing_pages(state, c, ctx))
    return state


def _queue(state: dict[str, Any], pages: list[dict[str, Any]]) -> None:
    state.setdefault("inbox", []).extend(pages)
    state.setdefault("chronicle", []).extend(pages)


def _context(state: dict[str, Any], c: dict[str, Any], w: Optional["World"], tonight: dict) -> dict[str, Any]:
    return story.context(state, c, w, tonight)


MEDALS = {"US": [(1, "Air Medal"), (2, "Distinguished Flying Cross"), (3, "Silver Star"), (5, "{cross}")],
          "USSR": [(1, "Medal for Combat Merit"), (2, "Order of the Red Star"), (3, "Order of the Red Banner"),
                   (5, "Gold Star, Hero of the Soviet Union")]}
LADDERS = [["ENS", "LTJG", "LT", "LCDR", "CDR", "CAPT"], ["2nd Lt", "1st Lt", "Capt", "Maj", "Lt Col", "Col"],
           ["Lt", "Sr Lt", "Captain", "Major", "Lt Col", "Colonel"]]


def _promote(rec: dict[str, Any]) -> bool:
    for lad in LADDERS:
        if rec.get("rank") in lad:
            i = lad.index(rec["rank"])
            if i + 1 >= len(lad):
                return False
            new = lad[i + 1]
            if rec["name"].startswith(rec["rank"] + " "):
                rec["name"] = new + rec["name"][len(rec["rank"]):]
            rec["rank"] = new
            return True
    return False


def _book_aircrew(state: dict[str, Any], w: "World") -> dict[str, list]:
    """The night's kills, medals, promotions and losses among the aircrews, into the war's roster."""
    us = w.faction == "US"
    old = {r["id"]: r for r in state.get("roster", [])}
    out, tonight = [], {"fallen": [], "missing": [], "rescued": [], "aces": [], "medals": [], "promoted": [],
                        "best": None}
    best_n = 0
    date = story.date_of(w)
    for p in w.battle.pilots.values():
        rec = dict(old.get(p.id, {}))
        before = int(rec.get("kills", 0))
        rec.update(id=p.id, name=p.name, squadron=p.squadron, rank=p.rank, surname=p.surname, kills=p.kills,
                   sorties=p.sorties, status="active" if p.status == "flying" else p.status)
        rec.setdefault("medals", [])
        if p.squadron in w.squadrons:
            rec["unit"] = w.squadrons[p.squadron].name
        n = p.kills - before
        if n > best_n:
            best_n, tonight["best"] = n, rec["id"]
        award = None
        for k, med in MEDALS["US" if us else "USSR"]:
            if n >= k:
                award = med
        if award:
            navy = any(rec.get("rank") == r for r in LADDERS[0])
            award = award.format(cross="Navy Cross" if navy else "Air Force Cross")
            rec["medals"].append(award)
            tonight["medals"].append((rec["id"], award))
        if before < 5 <= p.kills:
            tonight["aces"].append(rec["id"])
        if (n >= 3 or before < 5 <= p.kills) and p.status != "kia" and _promote(rec):
            tonight["promoted"].append(rec["id"])
        if p.note and p.status in ("kia", "missing", "rescued"):
            tonight[{"kia": "fallen", "missing": "missing", "rescued": "rescued"}[p.status]].append(rec["id"])
            if us and "Purple Heart" not in rec["medals"]:
                rec["medals"].append("Purple Heart")
            if p.status == "kia":
                rec["died"] = date
                state.setdefault("fallen", []).append({"id": rec["id"], "name": rec["name"],
                                                       "unit": rec.get("unit", rec["squadron"]), "date": date,
                                                       "kills": rec["kills"]})
            if p.status == "missing":
                rec["lost"] = date
        out.append(rec)
    tonight["best_n"] = best_n
    state["roster"] = out
    return tonight


def _between_battles(state: dict[str, Any], c: dict[str, Any]) -> None:
    """Some of the missing are found: by the rescue helicopters, a trawler, a reindeer herder. After a
    mercy shown, the other side gives a few back."""
    import zlib
    i = int(state.get("mission", 0))
    found = []
    for rec in state.get("roster", []):
        if rec.get("status") != "missing" or rec.get("lost") == (state["results"][-1].get("date") if
                                                                 state.get("results") else None):
            continue
        roll = zlib.crc32(f"{rec['id']}:{i}".encode()) % 100
        if roll < 30 + 25 * min(2, int(state.get("mercy", 0))):
            rec["status"] = "active"
            rec["found"] = True
            found.append(rec["id"])
    state["found"] = found


def war_outcome(state: dict[str, Any]) -> str:
    """VICTORY, DRAW or DEFEAT on the war's whole score; a war that lost what it could not fight without
    (the battles that needed it went unfought) is a DRAW at best."""
    res = state.get("results", [])
    if not res:
        return ""
    pct = sum(r["score"] for r in res) / max(1, sum(r["total"] for r in res))
    if pct < 0.4:
        return "DEFEAT"
    if state.get("note"):
        return "DRAW"
    return "VICTORY" if pct >= 0.65 else "DRAW"


def result_for(state: dict[str, Any], i: int) -> Optional[dict[str, Any]]:
    """The result of the war's battle i, or None if it has not been fought (or never will be)."""
    for k, r in enumerate(state.get("results", [])):
        if r.get("mission", k) == i:
            return r
    return None


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


def aircrew_lines(state: dict[str, Any], faction: str) -> list[tuple[str, tuple]]:
    """The best pilots and the dead, for the war room."""
    ink, red, blue = (40, 34, 26), (150, 34, 26), (30, 60, 150)
    roster = state.get("roster", [])
    if not roster:
        return [("Nobody has flown yet. The ready rooms are full." if faction == "US" else
                 "The regiments have not yet flown. Every pilot is at his post.", ink)]
    out = []
    top = sorted((r for r in roster if r.get("kills", 0) > 0), key=lambda r: (-r["kills"], r["id"]))[:4]
    for r in top:
        ace = (" — ACE" if faction == "US" else " — five victories") if r["kills"] >= 5 else ""
        dead = " (killed)" if r.get("status") == "kia" else " (missing)" if r.get("status") == "missing" else ""
        meds = story._medal_line(r.get("medals", []))
        out.append((f"{r['name']}, {r.get('unit', r['squadron'])}: {r['kills']} kill{'s' if r['kills'] != 1 else ''}"
                    f"{ace}{dead}" + (f" · {meds}" if meds else ""), blue if not dead else ink))
    if not top:
        out.append(("No kills yet.", ink))
    fallen = state.get("fallen", [])
    missing = [r for r in roster if r.get("status") == "missing"]
    if fallen:
        names = ", ".join(story.formal(f["name"]) for f in fallen[-4:])
        more = f" and {len(fallen) - 4} more" if len(fallen) > 4 else ""
        out.append((f"Killed in action ({len(fallen)}): {names}{more}", red))
    if missing:
        out.append((f"Missing ({len(missing)}): " + ", ".join(story.formal(r["name"]) for r in missing[:4]), red))
    if state.get("mercy"):
        out.append((f"Mercy shown: {state['mercy']} time{'s' if state['mercy'] != 1 else ''}", ink))
    return out

