# Changelog

All notable changes to Search and Track. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased] — feature/fun-and-pvo

The Cold War turned hot: whole air battles fought by both sides, a war that remembers, music.

### Battles
- Battle missions: autonomous air groups (strike, escort, sweep, intercept, defence suppression, recon, jammers, radar aircraft) that fly on their own side's picture, watch their fuel, defend against missiles, abort when cut up and go home empty.
- Ships: formations, station keeping, evasive turns, chaff, close-in guns, damage states down to sinking; shipborne radars and missile channels on the picture; carriers as moving airfields.
- Missiles as aircraft: anti-ship (sea-skimming and high-diving, seekers that lock the strongest return; Granit salvos that share their targets), land-attack cruise missiles that follow the terrain, glide bombs, and anti-radiation missiles that home on radars that radiate.
- The ground war: radars knocked off the air or destroyed, missile battalions losing their fire-control radar, cratered runways and their repair; battalions switch off when an anti-radiation missile is inbound.
- Sensing for both sides: the radar horizon, cross-section, jamming, passive interception of radiating ships; emission control as a real choice.
- The battle staff: identification by battle rules, commitment by posture with a reserve, patrols manned and relieved, self-defence, missile channel assignment, radar aircraft that run from closing fighters.
- The director: phases opened by the situation, decisions with a timer and a default, reinforcements, objectives, a definitive end and VICTORY/DRAW/DEFEAT.
- The battle display: NATO-style frames, raid grouping, own flights and groups with their state, weapons in flight with trails, explosions, splash and hit markers, damage marks on the ground, a status plate, banners, decision cards, unit cards with each unit's story, follow, an umpire's view, auto-slowdown on hot events, ADVANCE.
- The BATTLE console: standing orders, reserve, priority targets (right-click PRIORITY), reinforcements, forces, objectives, spectate/take command, the battle log.
- Tactical replay from the debrief; the debrief's battle summary, decisions and newspaper.
- Four battles: The Outer Air Battle and The Second Raid (US), The Northern Bastion and The Second Strike (PVO).

### The war
- Wars (`data/campaigns`): battles fought one after another by the same forces; losses, repairs and replacements carried over for both sides; branches on outcome; a war ends early if the force loses what it cannot fight without. The war room shows the diary, the order of battle and the next battle.
- Scenarios can be written as changes to another scenario (`base`, `*_patch`, `*_add`, `*_drop`); a later battle played on its own starts from the losses it assumes.

### The PVO command post
- Its own room: the plotting board in the middle, the operator's desk on the left, a cabinet on the right with the wall clock, watch timer, time keys, lamps, a radar scope and the lines to every company, regiment and battalion.
- English on every console; Russian only on the plotting board.

### Orders, music, difficulty
- One-click orders on both sides: right-click a track to send the nearest suitable interceptor, or a flight for its orders.
- Synthesized adaptive music for each side (pad, pulse, drive, theme) cross-fading with the situation.
- Difficulty: recruit, regular, veteran.

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

### Packaging
- Linux AppImage: a single x86_64 file carrying its own Python 3.12, pygame-ce and numpy, for glibc 2.17 and newer. `tools/build_appimage.sh` builds it from pinned, checksummed downloads and smoke-tests it headless.
- The AppImage workflow builds it on every pull request and push to `main`, and attaches it to a draft release when a version tag is pushed.
- An application icon (a radar scope), also used for the game window.

### Fixes
- Request buttons on the Comms console work (command kind is positional-only).
- Pulse-Doppler losses are reported as the notch, not as clutter.
- Jammer tracks carry the jammer's identity for evaluation.

## [0.1.0] — vertical slice

- Deterministic simulation on a 1-second tick: radar equation and horizon, terrain masking, clutter and MTI, jamming, SAGE digital and PVO manual reporting pipelines, tracking, identification, interception, SAMs, HQ authority, communications and faults.
- pygame-ce interface with the situation display, radar scope and seven operator consoles for both services.
- Two training scenarios and two historical watches; save and load; headless tests.
