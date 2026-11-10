# Tracks and Identification

> Turning returns into tracks, and tracks into answers

## Two pipelines

**SAGE (US).** Each radar sends its plots to the AN/FSQ-7 over a data line, a few seconds late. The computer associates new plots with existing tracks. Plots it cannot associate show as small raw returns; you start a track by placing the light gun on one and pressing INITIATE (or `I`). With the surveillance position automated, the computer starts tracks itself.

**PVO plotting board.** Radar companies report their targets by telephone, each with a company number, a grid square and the time of observation. Each report reaches the board 2½ to 4½ minutes after it was seen, rounded to a 10 km grid square. The board allots a target number and joins the marks into a track. The dashed line extrapolates the last reports: that is where the target probably is now. A guidance point's scope shows the truth in real time, for the area it covers.

## Keeping tracks clean

A track has a quality (how well its reports fit) and an age. Tracks that are not updated go stale and are dropped.

- **DROP** false tracks: anaprop ghosts, clutter, a lone false alarm.
- **MERGE** duplicates: two radars, each with a small registration error, can produce two tracks on one aircraft. Press MERGE on the first, select the second, press MERGE again.
- **REPORT** a track to higher headquarters when it matters to them.
- Formations show as one return with an estimated raid size.

## Identities

| SAGE | PVO | Meaning |
|---|---|---|
| PENDING | PROCESSING | Not yet assessed |
| FRIEND | OWN | Explained: valid IFF, a flight plan, a schedule, or seen to be friendly |
| UNKNOWN | UNIDENTIFIED | Not explained; must be identified |
| SUSPECT | FOREIGN | Foreign military, not declared hostile |
| HOSTILE | VIOLATOR | Declared by higher authority |
| FAKER | TRAINING | Exercise aircraft simulating the enemy |

You set identities yourself, except HOSTILE: that needs higher authority, or weapons FREE.

## Evidence

The Tracks console lists the evidence for the selected track and recommends an identity. The decision is yours.

- **IFF/SIF.** A valid code for the current period is good evidence of a friend. No reply proves nothing: civil aircraft and failed transponders give no reply either.
- **Flight plans (US).** Inside the ADIZ, a track is correlated with filed plans: it must be within **±5 minutes** of the plan's estimate and within **10 nm over land or 20 nm over water** of its route. Outside tolerance, it is an unknown, however innocent it probably is.
- **Schedules (PVO).** Aeroflot dispatch publishes civil schedules; a track that matches one is probably that flight.
- **Behaviour.** Speed, altitude and course. A slow track at airliner altitude on an airway is probably an airliner. A fast one heading for a city is not.
- **Visual identification.** The best evidence there is, and the slowest.

## The coverage analysis

For the selected track, the Tracks console lists each radar that should see it: range, probability of detection, signal-to-interference, and the limiting reason when it fails (horizon, terrain, clutter, MTI, notch, jamming, range). Use it to tell a low flyer from a lost track, and to decide which radar to fix first.

## Automation

Four positions can be manned by the computer or by you: surveillance (starting tracks), identification, height requests and the technical position (radar settings and faults). Training lessons switch some off so you do the work yourself. Alert Duty and the campaign leave most of them on; what remains is judgement.
