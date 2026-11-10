# AGENTS.md

How work gets done on Search and Track. One page; keep it that way.

## Roles

- **Owner** (the human). Sets direction, approves merges to `main` and every release. Nothing ships without an explicit yes.
- **Builder** (Claude). Primary developer: designs, implements, tests and documents features on a branch, and opens the pull request.
- **Reviewer** (Codex / ChatGPT). Independent review of each pull request: correctness, determinism, scope creep, historical accuracy, and whether the tests prove what they claim. Reviews; does not push to the builder's branch.

## Workflow

1. Work happens on a branch (`feature/...`, or `vertical-slice` for the current milestone). Never commit straight to `main`.
2. Every change lands through a pull request with a summary, how it was tested, and screenshots for anything visible.
3. CI (`.github/workflows/ci.yml`) must be green: tests on Python 3.10 and 3.12, the manual mirror check, a headless screenshot run.
4. The reviewer comments; the builder answers or fixes; the owner merges.
5. Releases are tagged from `main` (`vX.Y.Z`) with a `CHANGELOG.md` entry, only on the owner's approval.

## Rules of the codebase

- **Offline, no telemetry, no network calls** at run time. Linux first.
- **The simulation is deterministic.** `src/searchtrack/sim` runs on a fixed 1 s tick from a seeded RNG, never reads the clock, and never imports the UI. All player actions go through `sim/commands.py`.
- **Save files are the simulation state.** New state goes in dataclass fields (serialized automatically); caches are `transient()`.
- **Data-driven.** Equipment, theaters, scenarios, lessons and the manual live in `data/`. Tag equipment numbers with their provenance.
- **Physics, not scripts.** Detections, kills and failures are computed; triggers only start events and set the scene.
- **Cosmetic localization only.** Soviet consoles show Russian legends (optional English strip); orders, radio, tooltips and the manual stay English. Buttons are keyed by their English label (`gui.drawn`), which tests and the instructor's highlights rely on.
- **Every training lesson must be completable by `sim/student.py`**; every new lesson condition needs a student rule.

## Commands

```sh
python -m pip install -e ".[dev]"
python -m pytest -q                                   # full suite, headless
python -m searchtrack --screenshot out.png --scenario <id> --seconds <t> [--mode scope|net] [--console N]
python -m searchtrack --screenshot out.png --scene title|briefing|debrief|campaign|alert|operations|manual
python tools/sync_manual.py                           # after editing data/manual
python tools/build_theater.py data/theaters/<id> --ne <natural-earth> --dem <etopo.nc>
```

## Done means

Tests pass, CI is green, new behaviour has a test, visible changes have a screenshot in the PR, the manual says how it works, and `CHANGELOG.md` says what changed.
