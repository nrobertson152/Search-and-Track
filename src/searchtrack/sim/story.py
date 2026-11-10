"""The war's story: the pages read between the battles.

A war's campaign file carries pages -- teletypes, letters, newspaper pages, reports -- for its
opening (`intro`), for each mission (`at` = before, after, or next: written after this mission
about the one to come) and for the end (`epilogue`). The night a `vital` ship is lost, the
campaign's `lost` pages are told instead of that battle's own after-pages, which assume she came
through it. A page can be written for one outcome only (`when`: victory, draw, defeat, mercy,
hard, fallen, ace, vital_lost, over; at the end war_victory, war_draw, war_defeat, mercy_war,
hard_war, ended_early, mercy_N and hard_N for battle N; `no_` or `not_` in front turns any of
them round), and its text can name what really happened:
{ace} and {ace_kills} are the war's best pilot so far, {fallen} the aircrews killed in the last
battle, {lost} and {kills} the aircraft lost and shot down, {ships_lost} the ships, {mercy} how
many times mercy was shown. The war also writes pages of its own: the letters to the families
of the fallen, the honours list, the roll of the dead.

Everything here is plain data in and plain data out; the war room shows it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .world import World

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
KINDS = ("teletype", "letter", "newspaper", "report", "diary")


def date_of(w: "World") -> str:
    iso = getattr(w, "start_clock", "") or ""
    try:
        y, mo, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
        return f"{d} {MONTHS[mo - 1]} {y}"
    except (ValueError, IndexError):
        return ""


def mission_pages(m: Optional[dict[str, Any]], at: str) -> list[dict[str, Any]]:
    if not m:
        return []
    return [p for p in m.get("page", []) if p.get("at", "before") == at]


def _ok(p: dict[str, Any], flags: dict[str, bool]) -> bool:
    when = p.get("when", "any")
    conds = [when] if isinstance(when, str) else list(when)
    for c in conds:
        if c in ("any", ""):
            continue
        neg = c.startswith("no_") or c.startswith("not_")
        key = c.split("_", 1)[1] if neg else c
        if bool(flags.get(key, False)) == neg:
            return False
    return True


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return "—"


def fill(text: str, ctx: dict[str, Any]) -> str:
    try:
        return text.format_map(_Blank(ctx))
    except (ValueError, IndexError):
        return text


def pages(items: list[dict[str, Any]], ctx: dict[str, Any], flags: Optional[dict[str, bool]] = None,
          check: bool = True) -> list[dict[str, Any]]:
    """The pages of a list that apply to what happened, with the names filled in."""
    out = []
    for p in items:
        if check and not _ok(p, flags or {}):
            continue
        kind = p.get("kind", "teletype")
        out.append({"kind": kind if kind in KINDS else "teletype", "title": fill(p.get("title", ""), ctx),
                    "from": fill(p.get("from", ""), ctx), "to": fill(p.get("to", ""), ctx),
                    "date": fill(p.get("date", ctx.get("date", "")), ctx), "text": fill(p.get("text", ""), ctx).strip()})
    return out


# ------------------------------------------------------------------ the names

def _names(roster: list[dict], ids: list[str]) -> list[dict]:
    by = {r["id"]: r for r in roster}
    return [by[i] for i in ids if i in by]


def _join(names: list[str]) -> str:
    if not names:
        return "no one"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def best(roster: list[dict], alive: bool = False) -> Optional[dict]:
    rs = [r for r in roster if r.get("kills", 0) > 0 and (not alive or r.get("status") != "kia")]
    return max(rs, key=lambda r: (r["kills"], r["id"])) if rs else None


def context(state: dict[str, Any], c: dict[str, Any], w: Optional["World"], tonight: dict) -> dict[str, Any]:
    roster = state.get("roster", [])
    ace = best(roster)
    ctx: dict[str, Any] = dict(c.get("cast", {}))
    ctx.update({"war": c.get("title", ""), "mercy": state.get("mercy", 0),
                "ace": ace["name"] if ace else "nobody yet", "ace_short": _short(ace) if ace else "nobody",
                "ace_kills": ace["kills"] if ace else 0, "ace_unit": ace.get("unit", "") if ace else ""})
    if w is not None:
        from .battle.core import outcome
        b = w.battle
        own, foe = w.own_side, ("red" if w.own_side == "blue" else "blue")
        lost = sum(1 for _, _, s in w.stats.kills if s == own)
        kills = sum(1 for v, _, s in w.stats.kills if s == foe and v in w.aircraft and not w.aircraft[v].aim)
        sunk = [s.name for s in w.ships.values() if s.side == own and s.state in ("sunk", "crippled")]
        fallen = _names(roster, tonight.get("fallen", []))
        top = _names(roster, [tonight["best"]]) if tonight.get("best") else []
        ctx.update({"date": date_of(w), "outcome": b.outcome or outcome(w), "lost": lost, "kills": kills,
                    "ships_lost": _join(sunk) if sunk else "none", "fallen": _join([r["name"] for r in fallen]),
                    "fallen_n": len(fallen), "missing_n": len(tonight.get("missing", [])),
                    "rescued_n": len(tonight.get("rescued", [])),
                    "best": top[0]["name"] if top else "nobody", "best_short": _short(top[0]) if top else "nobody",
                    "best_kills": tonight.get("best_n", 0), "battle": w.title})
    return ctx


def _short(r: dict) -> str:
    return f"{r.get('rank', '')} {r.get('surname', '')}".strip() or r.get("name", "")


# ------------------------------------------------------------------ the pages the war writes itself

def aircrew_pages(state: dict[str, Any], w: "World", tonight: dict, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    us = w.faction == "US"
    roster = state.get("roster", [])
    out = []
    lines = []
    for r in _names(roster, tonight.get("aces", [])):
        lines.append(f"{'ACE' if us else 'FIVE VICTORIES'}: {r['name']}, {r.get('unit', '')} — {r['kills']} kills.")
    for rid, med in tonight.get("medals", []):
        r = next((x for x in roster if x["id"] == rid), None)
        if r is not None:
            lines.append(f"{med}: {r['name']} ({r.get('unit', '')}).")
    for r in _names(roster, tonight.get("promoted", [])):
        lines.append(f"Promoted in the field: {r['name']}.")
    for r in _names(roster, state.get("found", [])):
        lines.append(f"Found alive: {r['name']} ({r.get('unit', '')}), missing since {r.get('lost', 'the last battle')}.")
    dead = _names(roster, tonight.get("fallen", []))
    miss = _names(roster, tonight.get("missing", []))
    saved = _names(roster, tonight.get("rescued", []))
    if dead:
        lines.append("Killed in action: " + _join([r["name"] for r in dead]) + ".")
    if miss:
        lines.append("Missing: " + _join([r["name"] for r in miss]) + ".")
    if saved:
        lines.append("Shot down and recovered: " + _join([r["name"] for r in saved]) + ".")
    if lines:
        out.append({"kind": "report", "title": "AIRCREW — CASUALTIES AND AWARDS" if us else
                    "FLYING PERSONNEL — LOSSES AND DECORATIONS", "from": ctx.get("personnel") or
                    ("Air Wing Personnel Office" if us else "Political Department"), "to": "", "date": ctx.get("date", ""), "text": "\n".join(lines)})
    if dead:
        r = dead[0]
        co = _commander(roster, r)
        out.append(_letter(us, r, co, ctx, len(dead)))
    return out


def _seat(rec: dict) -> int:
    try:
        return int(rec["id"].rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 999


def _commander(roster: list[dict], fallen: dict) -> Optional[dict]:
    """The senior surviving officer of the squadron: the commanding officer, or whoever took his place."""
    mates = [x for x in roster if x["squadron"] == fallen["squadron"] and x["id"] != fallen["id"]
             and x.get("status") != "kia"]
    return min(mates, key=_seat) if mates else None


def formal(name: str) -> str:
    """'CDR Jack 'Hollywood' Harlan' -> 'CDR Jack Harlan': no call signs in a letter to a family."""
    if "'" in name:
        a, _, rest = name.partition(" '")
        _, _, b = rest.partition("' ")
        return f"{a} {b}".strip() if b else name
    return name


def _letter(us: bool, r: dict, co: Optional[dict], ctx: dict, n: int) -> dict[str, Any]:
    name = formal(r["name"])
    first = name.replace(r.get("rank", ""), "", 1).strip()
    first = first.split(" ")[0] if first else r.get("surname", "")
    unit = r.get("unit", "the squadron")
    sign = (formal(co["name"]) + (", commanding" if us else ", commander")) if co else \
        ("The Commanding Officer" if us else "The Regiment Commander")
    kills = r.get("kills", 0)
    navy = r.get("rank") in ("ENS", "LTJG", "LT", "LCDR", "CDR", "CAPT")
    if us:
        k = (f" He had shot down {kills} enemy aircraft, and every one of them was a bomber that did not reach "
             f"{'the ships' if navy else 'its target'}." if kills else
             f" He was flying to protect {'the ships' if navy else 'the bases'}, and he did.")
        many = "He was the only one we lost that night." if n == 1 else f"He was one of {n} we lost that night."
        text = (f"To the family of {name},\n\nIt is my sad duty to tell you that {first} was killed in action on "
                f"{ctx.get('date', 'the night of the battle')}, flying with {unit}.{k}\n\n{many} I knew him as a "
                f"fine officer and a better {'shipmate' if navy else 'friend'}, the kind of man the others watched "
                f"when things went bad. Nobody in this squadron will forget him.\n\nThe "
                f"{'Navy' if navy else 'Air Force'} will tell you more when it can. I wanted you to hear it from us "
                f"first.")
        title = "A LETTER HOME"
    else:
        k = (f" He destroyed {kills} enemy aircraft." if kills else "")
        text = (f"To the family of {name},\n\nWith deep sorrow the command of {unit} informs you that your son "
                f"died the death of the brave on {ctx.get('date', 'the night of the battle')}, defending the air "
                f"borders of the Motherland.{k}\n\nHe was a disciplined officer and a true comrade. His fellow pilots "
                f"have asked me to tell you that he did not turn back.\n\nHis memory will be kept in the regiment.")
        title = "NOTICE TO THE FAMILY"
    return {"kind": "letter", "title": title, "from": sign, "to": "", "date": ctx.get("date", ""), "text": text}


def closing_pages(state: dict[str, Any], c: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """The honours list and the roll of the dead, when the war is over."""
    us = c.get("faction", "US") == "US"
    roster = state.get("roster", [])
    out = []
    top = sorted((r for r in roster if r.get("kills", 0) > 0), key=lambda r: (-r["kills"], r["id"]))[:6]
    if top:
        lines = []
        for r in top:
            meds = _medal_line(r.get("medals", []))
            dead = " (killed in action)" if r.get("status") == "kia" else ""
            lines.append(f"{r['name']}, {r.get('unit', '')} — {r['kills']} kill{'s' if r['kills'] != 1 else ''}"
                         f"{dead}{'. ' + meds if meds else ''}")
        out.append({"kind": "report", "title": "HONOURS OF THE WAR" if us else "DECORATED FOR THE WAR",
                    "from": c.get("cast", {}).get("admiral", ""), "to": "", "date": "", "text": "\n".join(lines)})
    dead = state.get("fallen", [])
    missing = [r for r in roster if r.get("status") == "missing"]
    ships = state.get("ships_lost", [])
    if dead or missing or ships:
        lines = [f"{formal(d['name'])}, {d['unit']} — {d['date']}" for d in dead]
        if missing:
            back = state.get("mercy", 0) > 0
            lines += [""] if lines else []
            lines.append(("Missing, returned by the other side after the ceasefire: " if back else
                          "Missing, never found: ") + _join([formal(r["name"]) for r in missing]) + ".")
        if ships:
            lines += [""] if lines else []
            lines.append("Ships: " + _join([f"{s['name']} ({s['state']}, {s['date']})" for s in ships]) + ".")
        out.append({"kind": "report", "title": "IN MEMORIAM" if us else "ETERNAL MEMORY", "from": "", "to": "",
                    "date": "", "text": "\n".join(lines)})
    return out


def _medal_line(meds: list[str]) -> str:
    seen: dict[str, int] = {}
    for m in meds:
        seen[m] = seen.get(m, 0) + 1
    return ", ".join(f"{m} ×{n}" if n > 1 else m for m, n in seen.items())


def every_page(c: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """All the pages a war can show, whatever happens (for the manual's screenshots and the tests)."""
    items = list(c.get("intro", []))
    for m in c.get("mission", []):
        items += m.get("page", [])
    items += c.get("lost", []) + c.get("epilogue", [])
    return pages(items, ctx, check=False)

