"""The synthesized score: every layer one loop long, seamless, and mixed by intensity."""
import numpy as np
import pygame

from searchtrack.ui import music


def test_layers_are_one_loop_long_and_not_silent():
    for faction in ("US", "USSR"):
        layers = music.render(faction)
        assert set(layers) == set(music.LAYERS)
        n = int(music.LOOP_S * music.RATE)
        for k, v in layers.items():
            assert len(v) == n and np.isfinite(v).all()
            assert 0.2 < float(np.abs(v).max()) <= 0.61, k
            assert float(np.sqrt((v ** 2).mean())) > 0.02, k


def test_scores_differ_between_the_sides():
    us, su = music.render("US"), music.render("USSR")
    assert not np.allclose(us["pad"], su["pad"])


def test_mixer_crossfades_toward_the_intensity():
    pygame.mixer.quit()
    from searchtrack.ui.audio import Audio
    a = Audio(enabled=True)
    if not a.ok:
        return                                       # no audio device at all: nothing to play on
    m = music.Music(a, 0.5)
    m.play("US", 0)
    assert m.faction == "US" and m.mix["drive"] == 0.0
    m.set_intensity(2)
    for _ in range(300):
        m.update(0.05)
    assert m.level["drive"] > 0.95 and m.level["theme"] == 0.0
    m.set_intensity(0)
    m.update(0.05)
    assert m.level["drive"] < 1.0
    m.stop()
    pygame.mixer.quit()


def test_intensity_reads_the_picture():
    from searchtrack.sim import scenario
    w = scenario.build_world("us_battle_bering", seed=1)
    assert music.intensity(w) == 0
    w.battle.events.append([w.t, "kill", "x", "", 0.0, 0.0, "red", 2])
    assert music.intensity(w) == 2
