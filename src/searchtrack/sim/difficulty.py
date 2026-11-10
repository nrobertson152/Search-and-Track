"""Difficulty: the same scenario with more or less help, applied once when a watch begins.

recruit  -- every crew position works on its own (tracking, identification, heights, maintenance),
            alert aircraft get airborne faster, battle decisions wait twice as long, and the enemy's
            raids come a quarter smaller.
regular  -- as written.
veteran  -- in the historical watches every position is yours to run by hand; in battles the
            decisions come with less time and the enemy's raids a quarter larger.

Nothing here touches the physics: detection, tracking and kill chances stay what they are.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

LEVELS = ("recruit", "regular", "veteran")


def apply(w: "World", level: str) -> None:
    if w.vars.get("difficulty_set"):
        return                                       # once only: a loaded game keeps its difficulty
    level = level if level in LEVELS else "regular"
    w.vars["difficulty_set"] = 1.0
    w.vars["difficulty"] = float(LEVELS.index(level))
    if level == "regular":
        return
    b = w.battle
    enemy = "red" if w.own_side == "blue" else "blue"
    if level == "recruit":
        w.automation = {k: True for k in ("surveil", "ident", "height", "tech")}
        w.vars["scramble_factor"] = 0.6
        w.vars["decision_time"] = 2.0
        scale = 0.75
    else:
        if not b.active:
            w.automation = {k: False for k in ("surveil", "ident", "height", "tech")}
        w.vars["decision_time"] = 0.7
        scale = 1.25
    for g in b.groups.values():
        if g.side == enemy and g.role == "strike" and g.state == "pending" and g.n > 1:
            g.n = max(1, int(math.floor(g.n * scale)) if scale < 1 else int(math.ceil(g.n * scale)))
