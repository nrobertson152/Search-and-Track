import pathlib
import subprocess
import sys

import pytest

from searchtrack.sim import commands, scenario, world as worldmod
from searchtrack.sim.serialize import state_hash

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_save_load_roundtrip_continues_identically():
    a = scenario.build_world("us_training_intercept", seed=7)
    for _ in range(300):
        a.step()
    text = worldmod.save_json(a)
    b = worldmod.load_json(text)
    assert state_hash(a) == state_hash(b)
    for _ in range(300):
        a.step()
        b.step()
    assert state_hash(a) == state_hash(b)


def test_determinism_same_seed_same_commands():
    def run():
        w = scenario.build_world("us_training_intercept", seed=11)
        for i in range(400):
            if i == 150:
                tgt = w.aircraft.get("target")
                if tgt:
                    commands.run(w, "initiate", x=tgt.x, y=tgt.y, radius=30)
            w.step()
        return state_hash(w)
    assert run() == run()


def test_sim_never_imports_pygame():
    code = ("import sys; sys.path.insert(0, 'src'); import searchtrack.sim.world, searchtrack.sim.commands, "
            "searchtrack.sim.scenario; import searchtrack.sim.aar; print('pygame' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_every_command_kind_is_documented():
    assert {"initiate", "identity", "height", "scramble", "assign", "vector", "weapons_free", "sam_assign",
            "radar_mti", "radar_pfa", "switchover", "request", "ack"} <= set(commands.kinds())
