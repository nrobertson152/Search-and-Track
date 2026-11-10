"""Entry point: python -m searchtrack"""
from __future__ import annotations

import argparse
import os


def main() -> None:
    ap = argparse.ArgumentParser(prog="searchtrack", description="Search and Track — Cold War air defense")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--screenshot", metavar="PNG", help="render one frame to PNG and exit (headless)")
    ap.add_argument("--scenario", default="us_northern_vigil")
    ap.add_argument("--seconds", type=float, default=600.0, help="simulated time before the screenshot")
    ap.add_argument("--console", type=int, default=0)
    ap.add_argument("--mode", default="map", choices=["map", "scope", "net"])
    ap.add_argument("--scene", default="command", choices=["title", "briefing", "command", "debrief", "campaign", "alert", "operations"])
    ap.add_argument("--faction", default=None)
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--no-autoplay", action="store_true")
    args = ap.parse_args()
    if args.screenshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from .ui.app import screenshot
        screenshot(args.screenshot, args.scenario, args.seconds, args.console, args.mode, True, args.faction,
                   args.scene, not args.no_autoplay, args.coverage)
        return
    from .ui.app import App
    App(sound=not args.no_sound, fullscreen=args.fullscreen).run()


if __name__ == "__main__":
    main()
