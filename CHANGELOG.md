# Changelog

All notable changes to Search and Track. Versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] — unreleased (awaiting the owner's approval)

The whole game: two services, thirty years, sixteen watches, a career, a manual.

### Training and the manual
- Six instructor-led lessons, three per service: Intercept Fundamentals, Jamming and the Radar Scope, Rules of Engagement (NORAD); Guidance Point Drill, Missile Battalion Drill, Jamming Drill (PVO).
- The instructor's card: pinned to the display, it gives the next step, circles the controls to use on the consoles, rings the aircraft or site it means, and moves out of the way. Time compression drops to real time when the step changes.
- Lessons are data: `[[lesson]]` steps with a `done` condition, compiled into triggers. New conditions: height, flight, site, request, weapons status, simulated kill, interface events, skin tracks, elapsed time.
- A model student plays every lesson to completion in the test suite.
- The operator's manual: eleven chapters typed onto paper in the game, with contents, a section index and keyboard paging; mirrored in `docs/manual`.

### Campaign and Alert Duty
- Career campaign: watches unlock in historical order after the training; a persistent service record with rank, commendations and reprimands.
- Alert Duty: procedurally generated shifts on the historical orders of battle, with civil traffic on and off its plans, stragglers, lost light aircraft, probes, low intruders and equipment failures; QUIET, ROUTINE or BUSY.

### Eras, mechanics and content (1956–1987)
- Four new theaters (South Florida, Alaska, Kola, Baltic–Moscow) built from Natural Earth and ETOPO1.
- Equipment from the F-86D to the MiG-31 and E-3A; radars from the AN/FPS-20 to the FPS-117 and ST-68U; Nike, BOMARC, Hawk, S-25 through S-300PT.
- Airborne early warning with pulse-Doppler look-down and its notch; terrain-following cruise missiles; balloons with a day–night altitude cycle; forced-landing signals and warning shots; exercise rules with simulated kills; generated civil traffic.
- Ten historically inspired watches, from Genetrix (1956) to Red Square (1987), with newspaper headlines in the debrief.

### Look and feel
- Period hardware: lens keys and keycaps, jewel lamps, annunciators, seven-segment clocks, bat-handle toggles, chicken-head knobs; CRT bloom, scanlines and room light.
- Cosmetic localization: Soviet consoles engraved in Russian with an optional English strip; American consoles in English.
- A black-and-white newsreel title screen, an operations file of index cards and dossiers, typed briefings on the duty desk, a stamped after-action report with a truth replay.
- Map labels no longer pile onto each other: crowded names move or step aside for tracks.

### Fixes
- Request buttons on the Comms console work (command kind is positional-only).
- Pulse-Doppler losses are reported as the notch, not as clutter.
- Jammer tracks carry the jammer's identity for evaluation.

## [0.1.0] — vertical slice

- Deterministic simulation on a 1-second tick: radar equation and horizon, terrain masking, clutter and MTI, jamming, SAGE digital and PVO manual reporting pipelines, tracking, identification, interception, SAMs, HQ authority, communications and faults.
- pygame-ce interface with the situation display, radar scope and seven operator consoles for both services.
- Two training scenarios and two historical watches; save and load; headless tests.
