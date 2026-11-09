# Technical Architecture

## 1. Layers

```
┌──────────────────────────────── searchtrack.ui (pygame-ce) ───────────────────────────────┐
│ scenes: title → briefing → command center → debrief                                       │
│ consoles: situation display, PPI scope, tracks, weapons, missiles, radar/tech, comms, ... │
│ widgets: lamps, pushbuttons, rotary switches, meters, lists, teletype   │ audio synth │ CRT │
└───────────────▲───────────────────────────────────────────────┬──────────────────────────┘
                │ reads state (never mutates)                    │ issues Command objects
┌───────────────┴───────────────────────────────────────────────▼──────────────────────────┐
│                         searchtrack.sim (pure Python + numpy, headless)                    │
│ World (state)  ── systems run in a fixed order each tick ──  CommandProcessor              │
│ geo · terrain · radar · reporting · tracking · ident · aircraft · pilot · intercept · gci │
│ weapons · sam · comms · doctrine/authority · scenario/triggers · objectives · eventlog    │
└───────────────▲──────────────────────────────────────────────────────────────────────────┘
                │ loads
┌───────────────┴───────────────┐
│ data/ (TOML): radars, aircraft, weapons, sams, factions, theaters, scenarios               │
│ data/theaters/<id>/ map.json (Natural Earth crop), terrain.npz (ETOPO crop)               │
└───────────────────────────────┘
```

**Rule:** `searchtrack.sim` never imports pygame. CI enforces this with a test.

## 2. State model

- All simulation state lives in `@dataclass` objects reachable from `World`.
- **Cross-references are ids** (`str`/`int`), never object pointers. Lookups go through registries (`world.aircraft[id]`, `world.radars[id]`, ...).
- Static definitions (radar types, aircraft types) are loaded from data into a `Catalog`. State refers to them by type id; definitions are never copied into the save.
- Derived caches (terrain grids, horizon masks, map geometry) are marked transient and rebuilt on load.

This makes save/load a **generic dataclass serializer** (`sim/serialize.py`) driven by type hints, with no hand-written per-class code.

## 3. Time and determinism

- Fixed tick `DT = 1.0 s` of game time. The UI accumulates `real_dt × compression` and steps the world while `render_time > world.time`. The simulation is therefore always up to one tick *ahead* of what is drawn.
- Events inside a tick carry exact timestamps: radar paints are timestamped at the instant the sweep crosses the target's azimuth. The PPI reveals them as the drawn sweep passes, so the scope is exact even though the simulation ticks at 1 s.
- One seeded `random.Random` per world. Its state is saved. Iteration over registries uses insertion order (Python dicts preserve it), so a scenario plus seed plus command log reproduces a run exactly. Tests rely on this.

## 4. Tick order

```
1. commands      apply queued player Commands (validated against doctrine/ROE)
2. scenario      evaluate triggers → actions (spawn flights, failures, messages, weather)
3. ai            pilots (interceptors), mission AI (threats, civil), HQ authority AI
4. kinematics    aircraft & missiles move (energy model, fuel)
5. sensors       radars sweep → paints → plots; height finders; IFF interrogation
6. reporting     plots enter faction pipelines (digital link or manual reports) → deliveries
7. tracking      association, filtering, initiation, drops, fusion; strobe triangulation
8. control       GCI computes vectors (data link / voice), SAM fire control
9. weapons       launches, missile flight, fuzing, kills, debris
10. comms        message delivery, acknowledgements, escalation of unacknowledged alerts
11. evaluation   objectives, statistics, truth snapshots for after-action replay
```

## 5. Commands

Every player action is a `Command` with a `kind` and parameters, for example:

- `InitiateTrack`, `SetIdentity`, `RequestHeight`
- `Scramble`, `AssignIntercept`, `Vector`
- `SetRadarMTI`, `SamAssign`
- `RequestAuthority`, `Ack`, `SetReadiness`

`CommandProcessor.execute` validates the command (existence, doctrine, ROE, authority, link availability) and returns `(ok, reason)`. The reason is shown to the player. Commands and results go to the event log, which is the basis of the after-action review and of replays.

## 6. Radar detection pipeline (per radar, per tick)

1. Antenna azimuth advances `Δaz = 6·rpm·DT` degrees. The candidates are entities whose bearing lies in the swept sector and that are inside the instrumented range (cheap planar check).
2. For each candidate: compute the elevation angle with curvature (k-factor) and compare it with `horizon_mask[az_bin, range_bin]` (precomputed running maximum of the terrain elevation angle). The cone of silence comes from the maximum elevation.
3. Compute SNR (dB) from the radar equation: aspect RCS, integration gain over `n = PRF·θ_az/(6·rpm)` pulses, lobing factor (VHF), calibration loss.
4. Clutter: if the cell is inside the clutter footprint, apply MTI (improvement factor, notch on low radial speed, blind speeds) or signal-to-clutter limitation.
5. Interference: sum the J/N of active jammers (mainlobe/sidelobe gain, channel match). The result is SINR.
6. Swerling I: `Pd = Pfa ** (1/(1+SINR_lin))`, then draw from the world RNG. Sub-threshold paints within 6 dB are kept for the PPI only.
7. False alarms: Poisson with mean `Pfa × cells_in_sector`, plus clutter residue.

Every evaluation produces a `DetectionBreakdown` (all terms plus the limiting factor). It feeds the Coverage Analysis tool and the after-action "why missed" annotations.

## 7. Faction pipelines

- `DigitalLink` (SAGE): plots are delivered after `link_delay` (a few seconds) while the line is up; the computer associates them automatically.
- `ManualReporting` (PVO 1960): each radar company tracks targets locally (operator capacity limit) and reports each target every `report_interval`. Reports reach the command post after a chain-dependent delay with jitter. Positions are quantized to a grid square plus a digit, and there is a small chance of a transcription error.

Both deliver `Report` objects to the same `TrackManager`, so the rest of the stack is shared.

## 8. UI architecture

- `ui/app.py`: window (logical 1600×900, `SCALED|RESIZABLE`), main loop, scene stack, time accumulator.
- `ui/theme.py`: faction themes (palettes, fonts, label language, phosphor colours).
- `ui/widgets.py`: a retained-mode widget tree with hit-testing, hover and tooltips. Hardware-styled controls are drawn procedurally.
- `ui/consoles/*.py`: each console is a widget subtree bound to the world and the command processor.
- `ui/scope.py`: PPI renderer. A phosphor surface decays each frame with `BLEND_RGB_MULT`; paints are stamped as azimuth-elongated blips with glow sprites; the sweep has an afterglow wedge.
- `ui/situation.py`: map renderer. A cached base layer (coastlines, borders, grid) is rebuilt only on pan/zoom; dynamic layers are drawn per frame.
- `ui/audio.py`: tones, static, teletype clatter and bells synthesized with numpy at startup (no audio assets).

## 9. Data files

TOML, one record per table entry, each with `id`, `name`, `provenance` (`historical` / `approximate` / `fictional`) and `notes`. Theaters hold the projection origin, sites, cities, zones (ADIZ, border, sector) and file references for map and terrain. Scenarios hold forces, traffic, threats, triggers, objectives, briefing and intel.

`tools/build_theater.py` crops Natural Earth GeoJSON and the ETOPO grid into compact per-theater files (simplified polylines in projected km, int16 terrain).

## 10. Testing

pytest, headless, in CI on Ubuntu with Python 3.10 and 3.12. Coverage targets:

- Geometry and horizon math against closed-form values.
- Radar equation scaling (R⁴, RCS) and Swerling monotonicity.
- MTI notch and blind speeds; jamming burn-through.
- Kinematics limits (ceiling, climb, fuel).
- Intercept solutions (collision triangle, unreachable targets).
- Tracking association and initiation; flight-plan correlation tolerances.
- ROE/authority validation.
- Serializer round-trip of a running world; determinism (same seed and commands give an identical state hash).
- Autoplay of each scenario to completion without exceptions.
- The "sim never imports pygame" rule.

## 11. Performance budget

Target: 32× compression with about 60 aircraft and 15 radars on a 2015-era laptop.

- Simulation ≤ 4 ms per tick.
- Rendering ≤ 12 ms per frame at 60 fps.
- Horizon masks are 360 azimuth × 200 range bins per radar, computed with numpy in a few milliseconds.

## 12. Packaging (planned)

1. `pip install .` → `searchtrack` entry point.
2. PyInstaller one-folder build → AppImage for Linux and a zip for Windows.
3. Optional Flatpak manifest.

There are no network calls anywhere in the code.
