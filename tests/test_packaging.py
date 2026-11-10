"""The AppImage recipe: the files appimagetool needs are present and consistent, and the
layout the AppImage relies on (code in src/, data and fonts beside it) still holds."""
import os
import re
import subprocess
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging" / "appimage"


def test_build_script_parses():
    subprocess.run(["bash", "-n", str(ROOT / "tools" / "build_appimage.sh")], check=True)


def test_apprun_starts_the_bundled_python():
    apprun = PKG / "AppRun"
    assert os.access(apprun, os.X_OK)
    text = apprun.read_text()
    assert '"$HERE/usr/python/bin/python3" -I -B -m searchtrack "$@"' in text


def test_desktop_entry_and_icon():
    entry = dict(line.split("=", 1) for line in (PKG / "searchtrack.desktop").read_text().splitlines()
                 if "=" in line)
    assert entry["Type"] == "Application" and entry["Categories"].startswith("Game;")
    icon = ROOT / "assets" / "icons" / f"{entry['Icon']}.png"
    assert pygame.image.load(str(icon)).get_size() == (256, 256)
    assert (ROOT / "assets" / "icons" / "searchtrack-64.png").exists()


def test_pins_satisfy_the_project_minimums():
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([0-9.]+)", (PKG / "requirements.txt").read_text(), re.M))
    mins = dict(re.findall(r'"([A-Za-z0-9_.-]+)>=([0-9.]+)', (ROOT / "pyproject.toml").read_text()))

    def v(s):
        return tuple(int(x) for x in s.split("."))
    for name in ("pygame-ce", "numpy"):
        assert v(pins[name]) >= v(mins[name]), name


def test_data_and_fonts_sit_beside_src():
    """The AppImage copies src/, data/ and assets/ side by side and points a .pth file at src/."""
    from searchtrack.sim.catalog import DATA_DIR
    from searchtrack.ui.theme import FONT_DIR
    assert DATA_DIR == ROOT / "data" and FONT_DIR == ROOT / "assets" / "fonts"
    site = Path("/AppDir/usr/python/lib/python3.12/site-packages")
    assert os.path.normpath(site / "../../../../share/searchtrack/src") == "/AppDir/usr/share/searchtrack/src"
    script = (ROOT / "tools" / "build_appimage.sh").read_text()
    assert 'echo "../../../../share/searchtrack/src" > "$SITE/searchtrack.pth"' in script
