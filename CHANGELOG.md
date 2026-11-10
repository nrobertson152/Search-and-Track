# Changelog

All notable changes to Search and Track. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased] — feature/war-story

The war becomes a story: five battles a side, from the last hours of peace to the ceasefire, told in its own papers, with aircrews who have names.

### The story
- Each war is five battles long. US: The Bear Watch (prologue), The Outer Air Battle, The Second Raid, Bears over the Pole (Alaska), The Last Night. PVO: Shadows on the Border (prologue), The Northern Bastion, The Second Strike, The Baltic Front, The Capital.
- Between the battles the war is told in teletypes, orders, intelligence summaries, letters home, the newspaper of the battle group or the army, reports and diaries — chosen by what happened (outcome, losses, mercy shown or not) and filled in with the real names of the aces and the fallen. An epilogue, the honours of the war and the roll of the dead at the end. A named cast on each side: an admiral and his air wing commander, a sailor writing home to San Diego; a general, a duty officer, a radar operator writing home to Samarkand.
- Reinforcements: before the second night USS Mobile Bay and USS Callaghan join the battle group and stay with it (campaign key `ship_join`). The Bear Watch's first raid is smaller (two BACKFIREs), and the carrier takes about five heavy missile hits to put out of action instead of three: in headless wars the battle group was being wiped out by the second night.
- Losing the carrier no longer ends the US war: the battles that need her are passed over, the night she goes down is told in pages of its own, the Eagles of Alaska still fight Bears over the Pole, and the ending knows she is gone; without her the war is a draw at best (campaign keys `vital`, `skip_without`, `lost`). The radar operator's letters know whether his radar was destroyed (`down_<site>` page conditions).
- The interlude: story pages typed out one by one on paper of their own (teletype strip, letter, notebook, memo, newspaper with a file photograph and the small news of the day); THE STORY SO FAR in the war room reads them again.

### Peace, the FLASH, the ceasefire and mercy
- Battles can start in peacetime: the staff escorts every stranger weapons tight; objectives for intercepting the shadowers and for not firing a shot. The FLASH turns escorts into hunters — or lets the shadowers go home.
- Ceasefires at a fixed hour: nobody fires at an aircraft, missile batteries defend only against weapons in flight, jammers fall silent, the raids turn back. A damaged straggler after the ceasefire: let it ditch (or escort it out), or order it shot down.
- Mercy is remembered: some of the missing come home, and the war's epilogue changes.

### The aircrews
- Every interceptor is flown by a named pilot with a rank; kills go to the flight leader, five make an ace; a pilot shot down is picked up, missing or killed. Names are unique across the battle.
- In a war the roster carries over; decorations from the Air Medal to the Navy Cross and from the Medal for Combat Merit to the Gold Star; field promotions; letters to the families of the fallen. The war room lists the aces and the fallen; a flight's card names its crew; the debrief names the pilot of the night.

### New battles and equipment
- Bears over the Pole: BEAR H regiments with AS-15s against Alaska's radar line and the Eagles at Galena and King Salmon, FOXHOUNDs hunting the Sentries, a third regiment over the top.
- The Baltic Front: F-111Fs at 60 m over the Gulf of Riga, F-4G Wild Weasels, EF-111A jammers, F-15C sweeps and B-52 cruise missiles against the Leningrad direction; Su-27s at Gromovo (new theater sites: Gromovo, S-300 Leningrad, S-125 Narva).
- Catalog: F-15C, F-111F, EF-111A, F-4G, Su-27, GBU-15 glide bomb, Kh-55 (the AS-15 now flies as a land-attack missile in battles), AIM-7M, R-27R, R-73, GSh-30-1; silhouettes for the new aircraft and the F-14A.

### Battle mechanics
- Missiles fly the last two seconds before the target in small steps and their warhead gets one chance per pass: no more kilometre-wide misses on non-manoeuvring targets from the 1 s step. Missiles are deadlier on both sides; The Second Strike's objectives were eased to match.
- Air-launched cruise missiles leave the launcher in a stream instead of a clump.
- Staff: a pilot's visual identification settles the track; the escort alongside is not mistaken for the stranger; a patrol flight rides out a flickering track; reach is measured from what is defended; raiders going home far out are left alone; radar aircraft return to station when the fighters that drove them off are gone.
- A wrecked radar or battalion stays wrecked when hit again; repeated hits are reported quietly.
- Director: any action can wait (`after_s`); new actions `war`, `ceasefire`, `spare`, `engage`, `say`; new objective kinds `hold_fire` and `intercept_groups`; the `stray` group role (ditches or leaves).

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
