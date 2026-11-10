"""The aircrew: every interceptor in a battle is flown by someone with a name.

Each of our squadrons gets a roster. A scramble puts the best-scoring pilots who are free into
the lead seats; a kill is credited to the flight leader; a pilot who is shot down ejects and is
picked up, goes missing, or is killed. In a war the roster carries over from battle to battle,
so the aces of the first night fly again on the second -- or do not.

The fates are drawn from a hash of the pilot and the moment, not from the world's random
stream, so naming the crews changes nothing about how the battle itself goes.
"""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING, Optional

from .state import Pilot

if TYPE_CHECKING:
    from .world import World

US_FIRST = ["Jack", "Mike", "Dave", "Tom", "Rick", "Steve", "Jim", "Bill", "Dan", "Mark", "Paul", "Chris", "Gary",
            "Joe", "Ray", "Ken", "Ed", "Tony", "Frank", "Carl", "Luis", "Andre", "Pete", "Walt", "Hank", "Sam",
            "Ben", "Greg", "Neil", "Ron", "Doug", "Vic"]
US_LAST = ["Harlan", "Novak", "Brooks", "Delgado", "Kowalski", "Reyes", "Whitaker", "Sullivan", "Ito", "Marsh",
           "Petersen", "Coleman", "Okafor", "Bianchi", "Haskins", "Lindqvist", "Morales", "Shaw", "Duquette",
           "Garrity", "Holloway", "Kincaid", "Mercer", "Nakamura", "O'Brien", "Pruitt", "Quinlan", "Rafferty",
           "Stroud", "Tanaka", "Vasquez", "Wexler", "Yates", "Zabriskie", "Abernathy", "Castellano", "Bennett",
           "Carver", "Dawson", "Ellison", "Fletcher", "Grady", "Hendricks", "Ingram", "Jensen", "Keller", "Lambert",
           "McCall", "Nolan", "Ortega", "Prescott", "Rourke", "Sandoval", "Thornton", "Underwood", "Vance", "Walsh",
           "Brennan", "Caldwell", "Dempsey", "Esposito", "Flynn", "Gallagher", "Hayes", "Iverson", "Jaworski",
           "Kaminski", "Larkin", "Maddox", "Navarro", "Olsen", "Pappas", "Quigley", "Ramirez", "Schultz",
           "Takahashi", "Upton", "Voss", "Whitfield", "Zimmerman", "Barlow", "Conley", "Doyle", "Everett", "Farrell",
           "Griffin", "Hollis", "Jarvis", "Kendrick", "Lowell", "Monroe", "Osborne", "Rhodes", "Sutton", "Tolliver",
           "Vaughn", "Winslow", "Washington", "Jefferson", "Begay"]
US_CALL = ["Hollywood", "Spud", "Gator", "Hoss", "Rooster", "Bones", "Tex", "Moose", "Flash", "Doc", "Sly", "Mongo",
           "Zipper", "Ripper", "Jester", "Dutch", "Fang", "Nails", "Elvis", "Hawk"]
SU_FIRST = ["Dmitri", "Sergei", "Andrei", "Viktor", "Nikolai", "Alexei", "Igor", "Yuri", "Oleg", "Pavel", "Mikhail",
            "Vladimir", "Gennady", "Valery", "Anatoly", "Boris", "Konstantin", "Ruslan", "Timur", "Arkady", "Leonid",
            "Stanislav", "Vitaly", "Grigory"]
SU_LAST = ["Lebedev", "Sokolov", "Kuznetsov", "Morozov", "Volkov", "Zaitsev", "Belov", "Orlov", "Kovalenko",
           "Tkachenko", "Gusev", "Isayev", "Karimov", "Nazarov", "Abdullaev", "Melnik", "Rudenko", "Shevchuk",
           "Yakovlev", "Fedorov", "Gromov", "Panin", "Sorokin", "Tarasov", "Ulyanov", "Vorobyov", "Zhukovsky",
           "Ermakov", "Lysenko", "Bondar", "Grishin", "Davydov", "Belyaev", "Chernov", "Demin", "Egorov", "Filatov",
           "Gorbunov", "Ilyin", "Kalinin", "Larionov", "Makarov", "Nikitin", "Osipov", "Polyakov", "Savelyev",
           "Titov", "Utkin", "Vlasov", "Zuev", "Aksyonov", "Bykov", "Danilov", "Efimov", "Frolov", "Golubev",
           "Ignatov", "Kiselyov", "Lapin", "Noskov", "Ovchinnikov", "Pavlov", "Rybakov", "Semenov", "Trofimov",
           "Vinogradov", "Zakharov", "Akhmetov", "Baranov", "Sidorenko", "Savchenko", "Kravchuk", "Bogdanov",
           "Mamedov", "Gareyev", "Kim", "Avakyan", "Beridze", "Petrauskas", "Ozolins", "Tsoi", "Yusupov"]
US_RANKS = {"navy": ["CDR", "LCDR", "LCDR", "LT", "LT", "LT", "LTJG", "LTJG"],
            "air": ["Lt Col", "Maj", "Maj", "Capt", "Capt", "Capt", "1st Lt", "1st Lt"]}
SU_RANKS = ["Lt Col", "Major", "Major", "Captain", "Captain", "Sr Lt", "Sr Lt", "Lt"]


def _h(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def make_pilot(w: "World", sq, i: int, taken: set) -> Pilot:
    """Pilot number i of a squadron; his surname is not one already in the battle."""
    us = w.faction == "US"
    navy = us and (sq.base_id in w.airbases and w.airbases[sq.base_id].carrier or "VF" in sq.name.upper())
    k = _h(f"{w.scenario_id.split('_')[0]}:{sq.id}:{i}")
    firsts = US_FIRST if us else SU_FIRST
    first = firsts[k % len(firsts)]
    pool = US_LAST if us else SU_LAST
    j = (k >> 8) % len(pool)
    for _ in range(len(pool)):
        if pool[j] not in taken:
            break
        j = (j + 1) % len(pool)
    taken.add(pool[j])
    ranks = (US_RANKS["navy" if navy else "air"] if us else SU_RANKS)
    rank = ranks[min(i, len(ranks) - 1)]
    nick = f" '{US_CALL[(k >> 16) % len(US_CALL)]}'" if us and i < 4 else ""
    return Pilot(id=f"{sq.id}:{i}", name=f"{rank} {first}{nick} {pool[j]}", squadron=sq.id, rank=rank,
                 surname=pool[j])


def roster_for(w: "World", sq, n: Optional[int] = None, taken: Optional[set] = None) -> list[Pilot]:
    """A squadron's pilots, the same every time for the same squadron of the same scenario."""
    n = n or max(sq.pilots, sum(sq.ready.values()) + sq.maint, 4)
    taken = taken if taken is not None else {p.surname for p in w.battle.pilots.values()}
    return [make_pilot(w, sq, i, taken) for i in range(n)]


def ensure_roster(w: "World") -> None:
    """Every own squadron gets its pilots (a war installs its own roster before this runs)."""
    b = w.battle
    have = {p.squadron for p in b.pilots.values()}
    taken = {p.surname for p in b.pilots.values()}
    for sq in w.squadrons.values():
        if sq.side == w.own_side and sq.id not in have:
            for p in roster_for(w, sq, taken=taken):
                b.pilots[p.id] = p


def short(p: Pilot) -> str:
    """'CDR Harlan' -- rank and surname, for the radio log."""
    return f"{p.rank} {p.surname}".strip() or p.name


def ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh",
            8: "eighth", 9: "ninth", 10: "tenth"}.get(n, f"{n}th")


def crew(w: "World", fl) -> None:
    """Seat pilots in a flight that is about to take off: the best free pilots of the squadron lead."""
    b = w.battle
    if not b.active:
        return
    ensure_roster(w)
    free = [p for p in b.pilots.values() if p.squadron == fl.squadron_id and p.status == "active"]
    free.sort(key=lambda p: (-p.kills, p.id))
    for mid in fl.members:
        a = w.aircraft.get(mid)
        if a is None or a.pilot:
            continue
        if free:
            p = free.pop(0)
        else:                                          # the roster is used up: a replacement from the pool
            sq = w.squadrons.get(fl.squadron_id)
            i = sum(1 for q in b.pilots.values() if q.squadron == fl.squadron_id)
            if sq is not None:
                p = make_pilot(w, sq, i, {q.surname for q in b.pilots.values()})
                p.note = "replacement"
            else:
                p = Pilot(id=f"{fl.squadron_id}:{i}", name="replacement pilot", squadron=fl.squadron_id)
            b.pilots[p.id] = p
        p.status, p.aircraft = "flying", a.id
        p.sorties += 1
        a.pilot = p.id


def landed(w: "World", a) -> None:
    p = w.battle.pilots.get(a.pilot) if a.pilot else None
    if p is not None and p.status == "flying":
        p.status, p.aircraft = "active", ""


def credit(w: "World", shooter: str, victim) -> Optional[Pilot]:
    """A kill by one of our flights goes to its leader."""
    from .battle.core import event
    b = w.battle
    fl = w.flights.get(shooter)
    if fl is None or not fl.members or victim.aim or victim.kind != "aircraft":
        return None
    a = next((w.aircraft[m] for m in fl.members if m in w.aircraft and w.aircraft[m].state == "airborne"), None)
    a = a or w.aircraft.get(fl.members[0])
    p = b.pilots.get(a.pilot) if a is not None and a.pilot else None
    if p is None:
        return None
    p.kills += 1
    if p.kills == 5:
        us = w.faction == "US"
        event(w, "ace", f"{'ACE' if us else 'FIVE VICTORIES'}: {p.name} ({fl.callsign}) has five kills",
              fl.id, a.x, a.y, w.own_side, 2)
    return p


def shot_down(w: "World", a) -> str:
    """One of ours is down: does the pilot get out, and is he found?"""
    p = w.battle.pilots.get(a.pilot) if a.pilot else None
    if p is None:
        return ""
    k = _h(f"{p.id}:{int(w.t)}:{a.id}") % 100
    over_land = w.ground_height(a.x, a.y) > 1.0
    if k < 52:
        p.status, p.note = "rescued", "ejected and was picked up"
    elif k < 72:
        p.status, p.note = "missing", "ejected; not found yet" if not over_land else "ejected over the tundra"
    else:
        p.status, p.note = "kia", "killed"
    p.aircraft = ""
    return {"rescued": f"{short(p)} ejected — rescue is on the way",
            "missing": f"{short(p)} ejected — no contact on the beacon",
            "kia": f"no chute seen from {short(p)}"}[p.status]


def top(w_or_pilots, n: int = 3) -> list[Pilot]:
    pilots = w_or_pilots.battle.pilots.values() if hasattr(w_or_pilots, "battle") else w_or_pilots
    return sorted((p for p in pilots if p.kills > 0), key=lambda p: (-p.kills, p.id))[:n]
