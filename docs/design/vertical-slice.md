# Vertical Slice Definition

The slice proves the core: one shared simulation, two factions with different information architectures, and a full detect → track → identify → intercept → decide loop with consequences.

## Content

| Item | US | USSR |
|---|---|---|
| Theater | Gulf of Maine / Bangor Air Defense Sector (Maine, New Hampshire, Massachusetts, New Brunswick, Nova Scotia) | Middle Urals (Sverdlovsk, Chelyabinsk, Perm) |
| Era | October 1962 (SAGE, F-101B/F-106A, BOMARC, Nike Hercules) | 1 May 1960 (manual reporting, P-30/P-10, MiG-19, Su-9, S-75) |
| Training | *Intercept Fundamentals*: one unknown, one interceptor pair, an instructor overlay | *Guidance Point Drill*: a manual-reporting intercept |
| Scenario | *Northern Vigil*: routine traffic, an off-plan airliner, a DVFR light aircraft, a returning SAC bomber with IFF trouble, a Bear probe with jamming, an anomalous-propagation false alarm, an equipment failure | *May Day Overflight*: a high-altitude reconnaissance aircraft crosses the area; interceptors can't reach it; SAM battalions must be cued with stale data; IFF code changeover; political pressure; debris |

Both scenarios are **historically inspired** and their specific events are fictional (see the research notes for what is historical).

## Systems in the slice

- Real coastlines and terrain; radar horizon, terrain masking, lobing, clutter/MTI, Swerling fluctuation, noise jamming, anomalous propagation.
- PPI scope with phosphor persistence for any radar; situation display (US) and plotting board (USSR).
- Track initiation (light gun / auto), α-β tracking, multi-radar fusion, height finders (US), V-beam altitude (USSR).
- IFF/SIF codes with code periods; flight-plan correlation with NORAD tolerances; visual ID.
- Interceptor scramble from alert states; lead-collision / stern / VID / shadow geometry; data link and voice control; airborne radar contact; fuel and bingo; recovery.
- SAM batteries: S-75, Nike Hercules, BOMARC; engagement envelopes; acquisition by the strongest return in the gate; missiles as simulated entities; debris.
- Communications: teletype, voice, alerts needing acknowledgement, link failures.
- HQ authority: weapons status, hostile declaration and engagement permission requests, with delays and evidence-based answers.
- Technical console: radar settings with real effects, radar-equation readout, vertical coverage diagram, AN/FSQ-7 duplex.
- After-action report: timeline, identification timeliness, intercepts, expenditure, consequences, grade.
- Save/load; time compression with automatic slowdown on alerts; synthesized audio.

## Acceptance criteria

1. Both scenarios and both training missions can be completed (win or lose) from the UI.
2. `pytest` passes headless, including autoplay of every scenario to its end.
3. Every control on every console changes simulation state or issues a command. No dead buttons.
4. For any tracked target, the Coverage Analysis explains each radar's predicted detectability.
5. Saving and loading in the middle of a scenario continues the scenario identically (state-hash test).
