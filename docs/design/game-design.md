# Search and Track: Game Design Document

> *A Cold War air-defense command simulator. You run the room where the radar returns turn into decisions.*

## 1. Vision and pillars

The player commands an air-defense command post, either a NORAD/ADC SAGE Direction Center or a PVO Strany command post. Their job is to detect, track, identify and, if necessary, engage aircraft. Most nights are routine traffic and paperwork. Some nights are not.

**Pillars**

1. **One simulation, many windows.** Every console is a view onto, or a control for, the same simulation state. No decorative buttons and no fabricated numbers. If a meter moves, something in the model moved it.
2. **Explainable physics.** A missed detection always has a reason the player can learn: radar horizon, terrain, a lobing null, the MTI notch, clutter, jamming, a scan-to-scan fade or a threshold setting. The game shows its working.
3. **Decisions under honest uncertainty.** Uncertainty comes from the sensors, from latency and from doctrine, never from arbitrary hidden dice. The game gives enough information to decide well, but not enough to be certain.
4. **Two genuinely different systems.** The factions differ in how information flows and how authority works, not just in aircraft stats.
5. **Atmosphere through equipment.** The interface feels like 1950s–80s hardware: phosphor scopes, lamps, rotary switches, teletype, telephone buzzers.

## 2. The player's role and the core loop

The player is the **Senior Director** (US) or the **Operational Duty Officer** (USSR) for one sector or air-defense area during a shift. They can take over any operator position. The positions they are not attending are run by AI operators. Automation levels can be set per position, which is how the game scales from "learn the basics" to "do everything yourself".

**Core loop (minutes)**

1. Returns appear on radar → **initiate a track** (manually, or let surveillance operators auto-initiate).
2. Build the picture: **altitude** (assign a height finder, or read the V-beam estimate), speed and heading, IFF/SIF replies, flight-plan correlation.
3. **Identify**: friendly / unknown / hostile (plus faker/special), within the doctrinal time limit.
4. If unknown or suspicious → **commit a weapon**: scramble interceptors, pick an intercept geometry, vector them by data link or voice.
5. Execute: visual ID pass, shadow or escort, or engage *if* the rules of engagement and authority allow → manage fuel, recovery and readiness.
6. Report up the chain; respond to orders; keep the network healthy (radar faults, line outages, computer failover).

**Shift loop (an hour or more of game time, compressed):** routine traffic → an anomaly → escalation or de-escalation → after-action report.

**Campaign loop (days/months):** between shifts, spend limited resources on maintenance, training and modernization requests. Threats and eras evolve.

## 3. Factions

Both factions share the simulation. Faction **doctrine** and **equipment data** change how the same systems behave.

| Aspect | United States: NORAD / ADC (SAGE era) | Soviet Union: PVO Strany |
|---|---|---|
| Information flow | **Digital, near-real-time.** Radars send plots to the Direction Center every scan over phone lines. The computer associates them with tracks; operators initiate tracks with the light gun. | **Reported, delayed (1960).** Radar companies report targets by voice/teletype every ~60 s; delivery takes 1–5 min and positions are quantized to the PVO grid. Later eras: Vozdukh-1 automation cuts latency. |
| Main display | SAGE Situation Display: computer-generated symbols, track numbers, vectors, data blocks. | **Plotting board**: grid squares, discrete time-stamped plots, hand-lettered target numbers. Own forces in red, enemy in blue (Soviet convention). |
| Precision control | The Direction Center computes vectors centrally and sends them by data link (F-106 MA-1) or voice. | **Guidance points**, each with its own radar, control interceptors with real-time local data. The army command post decides; guidance points execute. |
| Altitude | Separate nodding height finders (FPS-6): accurate, but *assigned one track at a time*. | V-beam radars (P-20/P-30) give altitude on every scan, but coarse. Height finders come in later eras. |
| Identification | IFF/SIF modes plus **flight-plan correlation** against ADIZ tolerances (±5 min, 10/20 nm). Most civil traffic identifies itself; the hard cases are the exceptions. | Military IFF (monthly code changes). Foreign civil aircraft give **no compatible reply**. Identification leans on air-route schedules, behaviour and visual identification. |
| Weapons | Interceptors (F-101B, F-106A), **BOMARC** under SAGE control (Senior Director's key), Army **Nike** batteries under the AADCP/Missile Master, which may refuse an assignment to protect fighters. | Interceptors (MiG-17PF, MiG-19, Su-9), **S-75** battalions under PVO command. No automatic fighter/SAM deconfliction in 1960: IFF codes and orders are all that protect friendly fighters. |
| Authority | Weapons control status (HOLD/TIGHT/FREE) set by region/division; hostile declarations by authorized commanders; special weapons need release. | Highly centralized: firing permission comes from the army command post or Moscow, with political pressure and delays; the ramming order exists as a desperate option. |
| Failure modes | AN/FSQ-7 duplex failover (A/B side), phone-line outages, height-finder backlog, track-initiation workload. | Report backlog and errors, telephone line failures, IFF code changeover, debris confusing battle-damage assessment. |
| Look and sound | Console gray, cyan-green Charactron-style symbols, amber-green P7 PPI, English stencil labels, buzzers. | Turquoise-gray hammer-finish panels, orange-amber phosphor, red/blue grease pencil, bilingual Russian/English placards, bells. |

## 4. Systems

### 4.1 Radar (the defining system)

Each radar site has a type (data file) with transmitter power, frequency, pulse width, PRF, antenna beamwidth and rotation rate, elevation coverage, MTI, frequency channels, IFF interrogator, accuracy and reliability. Detection happens when the simulated antenna sweeps past a target:

1. **Geometry:** range, curvature-corrected elevation angle, cone of silence.
2. **Horizon and terrain:** a precomputed per-azimuth horizon profile from real terrain and the 4/3-Earth model. The k-factor changes with weather (ducting / sub-refraction).
3. **Signal:** radar equation with aspect-dependent RCS and pulse integration, plus a ground-reflection lobing factor for low-frequency radars.
4. **Clutter and MTI:** land/sea clutter footprint; MTI improvement factor vs zero-Doppler notch and blind speeds.
5. **Interference:** noise jamming (J/N, sidelobe vs mainlobe, frequency channel), chaff, weather.
6. **Decision:** Swerling I probability of detection against the operator-set false-alarm rate. Lower thresholds give more detections *and* more false plots.

Paints carry SNR. Sub-threshold paints appear faintly on the PPI but are not reported, so a sharp-eyed player can initiate a track on a faint blip by hand. The **Coverage Analysis** tool shows, for a track's estimated position, each radar's predicted detectability and the reason it would fail. The after-action truth replay shows the real reasons for every miss.

Player controls with real trade-offs: MTI on/off, detection threshold, antenna rotation rate (faster updates vs fewer pulses per dwell), frequency channel (escape spot jamming), scheduled maintenance (downtime now vs failure risk later).

### 4.2 Reporting and tracking

Each faction has its own reporting pipeline (Section 3). The track manager associates plots with tracks inside gates, smooths them with an α-β filter, keeps track quality and drops stale tracks. It fuses multiple radars, each with a small registration bias, so duplicate tracks can appear and the player can merge or split them. Formations show as single returns with an estimated raid size. Two or more jamming strobes can be triangulated into a jammer track.

### 4.3 Identification

Each track has candidate explanations: an IFF/SIF reply (by mode and code period), flight plans within tolerance, known friendly missions, behaviour (speed/altitude profile) and visual ID reports. The track console shows the evidence and the doctrinal recommendation. The player decides. Visual ID is affected by night and weather.

### 4.4 Aircraft and interception

Point-mass energy model: altitude-dependent maximum speed and climb, static vs zoom ceiling, turn-rate limit, and fuel flow by throttle (cruise / military / afterburner). Interceptors carry an airborne radar with limited range and **no look-down capability** in early eras.

The player picks the geometry:

- **Lead collision:** fastest, for forward-firing rockets and missiles.
- **Stern conversion:** for rear-aspect weapons and for safe identification passes.
- **Pursuit:** the fallback.
- **Shadow/escort.**

The ground computes the predicted intercept point, time to intercept, fuel at intercept and fuel to return. A late scramble, the wrong altitude or a poor vector has measurable consequences: no radar contact, a missed attack window, or a bingo-fuel return before the job is done.

### 4.5 Surface-to-air missiles

Site state machine: readiness → target designation → acquisition (the site radar locks the strongest return in its gate, *not* necessarily the intended aircraft) → engagement window → salvo → missile flight (simulated entities) → assessment → reload. Debris from a kill keeps painting for a while, so "target destroyed" is uncertain. Fratricide can emerge from geometry, IFF and timing; it is never scripted.

### 4.6 Communications

Messages travel on channels (radio, voice line, teletype, data link) that have delays, capacity and failures. Important alerts need acknowledgement. Orders to bases and sites travel over links that can be down.

### 4.7 Doctrine, ROE and authority

A higher-HQ AI owns the escalation ladder. The player *requests* changes: weapons status, hostile declaration, special-weapon release, airspace closure, ramming. HQ answers after a delay, based on evidence and the scenario's political state. Acting outside authority is possible in some cases, and it has consequences.

### 4.8 Readiness, logistics and reliability

Squadrons hold aircraft in alert states (5/15/30/60 min; Soviet readiness No. 1/2/3), maintenance and repair. Pilots and operators tire over a shift. Radars and the computer have failure rates; maintenance trades downtime for reliability. Fuel and weapons stocks are tracked per base.

## 5. Consoles (views onto the simulation)

| Console | Function |
|---|---|
| Situation Display / Plotting Board | Theater map, tracks, sites, zones, coverage overlays, weapons assignments |
| Radar Scope (PPI) | Raw video of a selected radar: sweep, persistence, clutter, strobes, range marks |
| Surveillance & Identification | Track list, evidence, flight plans, IFF, height requests, coverage analysis |
| Weapons Direction | Squadrons, scrambles, flights, intercept geometry, vectors, data link, RTB |
| Missile Control | SAM/BOMARC batteries, assignments, engagement status, reloads |
| Radar Network & Technical | Site status, settings, radar-equation readout, vertical coverage diagram, AN/FSQ-7 duplex panel |
| Communications | Teletype, voice log, alerts needing acknowledgement, reports and requests to HQ |
| Intelligence | Briefs, threat capabilities, developing situation, conflicting reports |
| Status & Logistics | Bases, aircraft availability, maintenance, crews, readiness ladder |
| Event Log / After-Action | Timeline, performance, decisions, consequences, truth replay |

## 6. Modes

- **Training:** guided lessons with an instructor overlay that reacts to what the player does (radar reading, track initiation, height finding, interception geometry, identification).
- **Historical-inspired scenarios:** authored shifts with briefings, objectives and branching events.
- **Endless operations:** procedurally generated traffic and incidents, with escalation over time.
- **Sandbox:** configure forces, weather, threats and conditions from the data files.
- **Campaign:** a career through eras. The command post persists between shifts and the network evolves.

Options: difficulty (threat behaviour, failure rates), realism (latency, fatigue, failure modes), automation per position, and time compression (1–32×) with automatic slowdown on alerts.

## 7. Campaign design (scoped deliberately)

The player is a sector/area commander, not a defense minister. Between shifts they get a **readiness budget** (maintenance hours, training slots) and can submit **modernization requests** to higher HQ. Approval depends on performance and politics, and arrival takes months. Era progression brings new equipment on historical schedules: FPS-27 and frequency diversity, BUIC, F-106 upgrades, AWACS; P-14/P-35, Vozdukh-1, Lazur, Su-15, S-200. Threats evolve alongside: high-altitude penetration → low-level penetration with ECM → cruise missiles.

**Challenged idea: open procurement shopping.** Free purchasing turns the game into a different genre and breaks historical texture. Requests through the chain of command keep the player in their role and make shortages part of the story.

## 8. Consequences and evaluation

Scores are not the point; the after-action report is. It evaluates detection and identification timeliness, intercept effectiveness, weapons expenditure, network health, and decisions taken against the information available at the time. Mistakes have weight: a civilian shootdown ends the scenario with an inquiry; fratricide is investigated; a false escalation costs credibility with HQ in the campaign.

## 9. Design decisions and challenged assumptions

- **"Numerous screens" vs usability:** solved with the *positions + automation* model. The player owns the decisions they choose to own; AI operators handle the rest, visibly and fallibly.
- **Realism vs boredom:** real air defense is hours of nothing. Event-driven time compression and procedurally varied routine traffic keep the pace without inventing drama.
- **Large raids:** a full nuclear war is not a satisfying game state. Large coordinated raids arrive mostly as **historically real mass exercises** (Sky Shield-style), with ECM and simulated weapons. War scenarios exist, but as rare, bleak set-pieces.
- **Soviet side without caricature:** the differences lie in information architecture, centralization, equipment and political authority, not in good vs evil.
- **Real tragedies:** scenarios are *inspired by* incidents, with fictionalized details, and treat loss of life seriously.

## 10. Features the brief did not list (and why they matter)

IFF code periods and changeover hazards; height-finder allocation; radar registration bias and duplicate tracks; cross-tell from neighbouring sectors; anomalous propagation; debris after kills; early interceptor radars that can't look down; night and weather limits on visual ID; crew fatigue; civil ATC coordination; an HQ authority model with delays; a truth-replay after-action review with explanations for every miss; accessibility (shape-coded symbology, CRT-effect toggles, pause at any time).

## 11. Vertical slice → roadmap

See [`vertical-slice.md`](vertical-slice.md) for the slice definition.

Afterwards, in priority order:

1. Endless operations generator.
2. RHI height-finder scope and BUIC degraded-mode play.
3. ECM-heavy exercise raid scenario.
4. Soviet 1978 coastal scenario (Su-15, Vozdukh-1M, foreign airliner identification).
5. Campaign framework.
6. Sandbox editor UI.
7. Additional eras and theaters.
