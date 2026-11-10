# ADR 0001: Python + pygame-ce, with a headless simulation core

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** project owner, lead developer (Claude)

## Context

The game is a 2D, interface-heavy command simulator. Most of its complexity lives in a *simulation*: radar physics, tracking, intercept geometry, doctrine and scenario logic. That simulation must be deterministic, testable, data-driven and maintainable. Rendering needs are modest (vector-style CRT graphics, map polylines, text), but the interface is dense and must look like real equipment rather than a generic dashboard. Linux (Mint) comes first and Windows second. The game must run offline with no telemetry.

The owner's directive suggested Godot 4. The owner then said they would prefer not to use Godot, so the alternatives were re-evaluated on their merits.

## Options considered

| Option | Strengths | Weaknesses for this project |
|---|---|---|
| **Python + pygame-ce + numpy** | Readable, easy to change; pytest makes the simulation easy to test; numpy for terrain and vector math; tiny dependency set (LGPL + BSD); runs everywhere Python does; full control over the custom-drawn equipment look | No built-in UI toolkit; CPU rendering (no shaders by default); packaging needs PyInstaller or an AppImage |
| Godot 4 | Strong UI controls, GPU shaders, one-click export | Declined by the owner; GDScript testing is weaker; the simulation becomes coupled to the engine's scene tree unless carefully isolated |
| LÖVE (Lua) | GPU shaders, small runtime, easy distribution | Smaller ecosystem for numeric work and testing; Lua is less familiar to most contributors |
| Rust + egui/macroquad | Performance, single binary | Much slower iteration for a UI-heavy game; higher bar for contributors |
| C# + MonoGame/FNA | Proven 2D, good performance | Custom UI anyway; heavier toolchain |
| Web stack in Electron/Tauri | Superb UI tooling | Heavy runtime (Electron) or inconsistent WebKitGTK rendering (Tauri); doesn't feel like a normal Linux game |

## Decision

Use **Python 3.10+ with pygame-ce** (the actively developed community edition of pygame, same `import pygame` API) and **numpy**. Read TOML data files with the standard library (`tomllib`, with `tomli` on Python 3.10).

Structure the code as two layers:

1. `searchtrack.sim`: a pure-Python, deterministic simulation that **never imports pygame**. All state is plain dataclasses. Objects refer to each other by id, never by direct reference, which makes save/load a generic serializer. Every player action is a `Command` object handled by the simulation, so the UI cannot mutate state behind the simulation's back.
2. `searchtrack.ui`: pygame-ce rendering and input. It reads simulation state and issues commands. The equipment look (switches, lamps, meters, CRT scopes) is a small custom widget layer.

## Consequences

- **Testing:** the whole simulation runs headless under pytest and in CI. Scenarios can be auto-played to completion in tests.
- **Visuals:** CRT effects are done on the CPU. Phosphor persistence uses a decaying offscreen surface; glow uses pre-blurred sprite stamps (pygame-ce has a C-implemented `gaussian_blur`); scanlines and vignette are overlays drawn once. An optional GPU post-processing pass (moderngl) can be added later without touching the simulation.
- **Performance:** the simulation uses a fixed 1-second tick. Radar detection is evaluated only for targets inside the azimuth sector the antenna swept during that tick. Terrain horizon masks are precomputed per radar with numpy. Time compression up to 32× is the target on modest hardware.
- **Distribution:** ship as a pip-installable package (`python -m searchtrack`) first. A PyInstaller one-folder build wrapped as an AppImage (Linux) and a zip (Windows) is planned for releases.
- **Licensing:** pygame-ce is LGPL-2.1 and numpy is BSD. Both are compatible with the project's GPL-3.0. Fonts are SIL OFL and ship with their license texts. Map and terrain data are public domain. Sounds are synthesized at runtime, so no audio assets are needed.
