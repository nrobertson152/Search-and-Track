# Research Notes: Cold War Air Defense (1950s–1980s)

These notes collect what the simulation is built on. Each item is tagged:

- **[H]** historical: documented in the sources listed.
- **[A]** approximate: historically grounded, but the number or behaviour is an estimate, a simplification or a reconciliation of sources that disagree.
- **[F]** fictional: invented for gameplay, with the reason given.

The game data files (`data/*.toml`) carry the same `provenance` tag on every entry.

---

## 1. Two different philosophies of air defense

### United States: NORAD, Air Defense Command and SAGE

- **[H]** The SAGE system grouped radar stations into Air Defense Sectors. Each sector's Direction Center (DC) housed an IBM AN/FSQ-7. The machine filled a whole floor and was really two computers, an "A" side and a "B" side. [SAGE][sage-wiki]
- **[H]** The standby side copied data from the active side to keep switchover short, and a scheduled switchover took place every day. [AN/FSQ-7][fsq7]
- **[H]** Radar returns travelled over leased telephone lines to the DC in digital form (the FST-2 coordinate data transmitter). The DC also traded data with adjacent centers and passed a summary up to a Combat Center that supervised several sectors. [SAGE][sage-wiki]
- **[H]** The FSQ-7 computed predicted interception points for manned interceptors and for BOMARC missiles. Later improvements let it send guidance straight to fighter autopilots over the SAGE ground-to-air data link. [AN/FSQ-7][fsq7]
- **[H]** The F-106A's Hughes MA-1 fire-control system was built to work with SAGE. The aircraft could be flown by the system for much of an intercept. [SAGE radar notes][sage-radar]
- **[H]** In the weapons room, each Weapons Director supervised a team of about five intercept scopes. The Senior Director sat on a raised dais and was responsible for everything in the room. [CHM oral history][chm]
- **[H]** The Senior Director's keyed console carried the BOMARC fire button. [AN/FSQ-7][fsq7]
- **[H]** Bangor Air Defense Sector (DC-05, Topsham AFS, Maine) controlled F-101B interceptors at Dow AFB, F-106A interceptors at Loring AFB and the 30th Air Defense Missile Squadron (BOMARC) at Dow from 1959 to 1964. Its direction center also controlled Army air defense through the Army's AN/FSG-1 Missile Master. [Bangor ADS][bangor] [Topsham DC-05][topsham]
- **[H]** With SAGE, manual plotting and assignment of tracks to Nike batteries was eliminated. The Army Air Defense Command Post (AADCP) consoles at the DC took over. [Topsham DC-05][topsham]

**Design consequence:** the US player runs a *semi-automatic* system. The computer associates radar returns with tracks, smooths them, predicts intercept points and can fly interceptors by data link. Humans still initiate tracks, decide identity and authorize weapons. Information is fast and digital, but fragile in specific ways: a computer failover, failed phone lines, and track initiation workload.

### Soviet Union: PVO Strany

- **[H]** PVO Strany was a separate branch of the Soviet armed forces. It combined radio-technical troops (radars), fighter aviation and SAM troops. [M21 profile][m21]
- **[H]** In 1960 the command post of the 4th Separate Air Defense Army (Sverdlovsk) did not yet have the newly adopted *Vozdukh-1* automated control system. Working manually, it took 3–5 minutes for air-situation information to pass from a radar company to the army command post. [Military Review][milrev]
- **[H]** The Uragan family of automatic interception systems combined radar, a digital computer that plotted targets and computed intercept courses, SAZO IFF and an SPK command data link. [Uragan][uragan]
- **[H]** Later *Lazur* data links (Lazur-SM on Tu-128 and Su-15, working with Vozdukh-1M ground stations) sent guidance commands to interceptors in bursts on VHF/UHF, so voice was not needed unless the link failed. [GCI data links][gcilinks]
- **[H]** In the Vozdukh-1M era, the MiG-25P pilot flew the ground-guided phase by following director needles driven by Vozdukh-1M commands over the ARLS-M radio link. [MiG-25P weapon system][mig25p]
- **[A]** PVO interception doctrine relied on close ground control: the ground controller delivered a short-radar-range interceptor into a narrow attack position. VVS (frontal aviation) practice was more pilot-centric. The source here is a practitioner forum discussion, so it is used only as flavour. [DCS forum][dcsgci]

**Design consequence:** the Soviet player (in the 1960 slice) runs a *manual reporting network*. Radar companies report targets by voice and teletype at intervals. Reports arrive minutes late, quantized to a map grid, and occasionally wrong. The army plotting board therefore shows *where targets were*, not where they are. Real-time precision exists only at the guidance points, each with its own radar, that control the interceptors. Later eras bring Vozdukh automation and the Lazur data link, so the Soviet side modernizes along a different path than the US one.

---

## 2. Sensors

### US long-range radars (1950s–60s)

| Radar | Role | Key figures | Tag |
|---|---|---|---|
| AN/FPS-20 | L-band long-range search | 1250–1350 MHz; high-power configuration ≥2 MW peak (klystron); ~360 pps; 3.3 or 5 rpm normal [themilitarystandard FPS-20][fps20b]. Earlier FPS-3 heritage figures: 2×750 kW, 400 pps, 2 µs [FPS-20][fps20] | [H] |
| AN/FPS-6 | S-band nodding height finder | 2700–2900 MHz, 5 MW peak, 3.2° horizontal beam, nods at 20–30 cycles/min, elevation −2° to +32°, height accuracy about ±1000 ft, range-height indicator display [Rotor FPS-6][fps6rotor] [CANDE][fps6cande] | [H] |
| Height-finder workflow | | The DC pre-positions the height finder by azimuth through the FST-2. The operator finds the target on the RHI, sets a cursor on it and sends the altitude back [FortWiki FPS-90][fps90] | [H] |

### Soviet radars (1950s)

| Radar | NATO name | Band | Introduced | Notes | Tag |
|---|---|---|---|---|---|
| P-8 Volga | KNIFE REST A | VHF | 1950 | First Soviet circular-scan radar; 150–250 km; 70–75 kW; about 2 rpm [P-8][p8] [valka][p8valka] | [H] |
| P-10 | KNIFE REST B | VHF | 1953 | Frequency hopping; 200–250 km; 55–100 kW [P-10][p10] | [H] |
| P-12 Yenisei | SPOON REST | VHF | 1955 | Coherent radar with MTI [Russian radars][rusrad] | [H] |
| P-20 Periscope | TOKEN | E/F (S) | 1949 | V-beam radar [Russian radars][rusrad] | [H] |
| P-30 Khrustal | BIG MESH | E/F (S) | 1955 | Improved P-20, about 180 km, 1 MW, V-beam (altitude estimate without a separate height finder) [globalsecurity][bigmesh] | [H] |
| P-35 Saturn | BAR LOCK | E/F | 1958 | [Russian radars][rusrad] | [H] |

**[A]** The V-beam principle: one beam is vertical and the other slanted. Altitude follows from the azimuth difference at which the two beams see the target. The game models it as a coarse altitude estimate whose error grows with range. US practice used separate nodding height finders that are accurate but must be *assigned*, and that assignment is a scarce resource.

**[A]** VHF radars (P-8/P-10/P-12) are modelled with strong ground-reflection lobing. That gives long range at altitude, vertical gaps and poor low-level cover. Microwave radars (FPS-20, P-30) see more weather clutter but have smoother low coverage.

### Identification

- **[H]** NORAD flight-plan tolerances: an aircraft must be within ±5 minutes of its estimated time over a reporting point or ADIZ penetration point. It must also be within 10 nm of the route centreline for a domestic ADIZ, or 20 nm for a coastal ADIZ. NORAD used these tolerances to classify aircraft as friendly, unknown or hostile. [FAA AC 99-1 (1972)][ac991] [FAA AC 99-1A (1978)][ac991a]
- **[H]** Inbound foreign civil aircraft report at least one hour before ADIZ penetration. An air-filed VFR plan makes an aircraft subject to interception for identification. [FAA AIM 5-6][aim]
- **[H]** In the manual (Pinetree) system, the identification section had two minutes to correlate a new track and declare it hostile, friendly or unknown. [CANDE Pinetree][pinetree-id]
- **[H]** On 1 May 1960 Soviet MiG-19 IFF transponders had not yet been switched to the new monthly codes because of the holiday. A MiG-19 was therefore acquired as hostile by SAM operators. [Safronov][safronov] [U-2 incident][u2wiki]

---

## 3. Weapons

| System | Figures used | Tag |
|---|---|---|
| S-75 (SA-75 Dvina / S-75 Desna, 1957+) | One target per site at a time, up to three missiles guided at it; six launchers; reload ≈12 min. Early-variant envelope about 8–34 km range and 0.5–22/30 km altitude depending on missile [armyrecognition][sa2ar]. The 13D (V-750VN) missile was used at Sverdlovsk [HQ-2/S-75][s75b] | [H]/[A] |
| Fan Song (SNR-75) | Tracks the target and the missile's beacon and computes command guidance [APA][apa] | [H] |
| BOMARC A | SAGE-directed long-range SAM, guided by the FSQ-7 to a homing dive [AN/FSQ-7][fsq7] | [H] (envelope [A]) |
| Nike Hercules / Ajax | Army SAMs under AADCP / Missile Master coordination [Bangor ADS][bangor] | [H] (envelope [A]) |

---

## 4. Rules of engagement and readiness

- **[H]** In 1957 the CONAD division commander set the weapons-control status for the weapons in his sector. In Canada, normal conditions were "Discreet Fire" (engage specifically designated targets), with Weapons Tight or Weapons Free set as the situation required. [NORAD 1957 history][norad57]
- **[H]** The transition from peace to war ran through declarations: Maximum Readiness, Air Defense Readiness and Air Defense Emergency. [NORAD 1958 history][norad58]
- **[H]** From 1958 NORAD required two interceptors on five-minute alert at every base. [NORAD 1958 history][norad58]
- **[H]** In one ADC anecdote, a pilot recalled that opening bomb-bay doors counted as a hostile act only after an Air Defense Emergency had been declared. [27th Air Division][27ad]
- **[H]** Soviet forces had formal readiness stages, starting from *constant* combat readiness and rising through *increased* readiness. [CIA 1977][cia77]

**Game model [A]:** both sides get a readiness ladder and a weapons-control status, and the authority to change them sits with a higher-HQ AI. The US ladder is DEFCON, Air Defense Warning WHITE/YELLOW/RED, and weapons HOLD/TIGHT/FREE. The Soviet ladder is constant / increased / full combat readiness, plus per-unit readiness No. 1/2/3. Requests go up the chain and take time. The answer depends on evidence (VID reports, hostile acts, intelligence) and on politics.

---

## 5. Incidents that inspire scenarios

| Incident | What the simulation takes from it | Tag |
|---|---|---|
| **U-2 overflight, 1 May 1960 (Sverdlovsk).** The intruder was detected, lost and reacquired; the first SAM salvo failed because the target had left the engagement zone; one site fired only one missile because of a fire-control malfunction; an unarmed Su-9 was ordered to ram but could not reach ~21 km; 14 missiles were fired in total; a MiG-19 was shot down by friendly fire; the SAM command was unaware for more than 30 minutes that the U-2 was destroyed because debris looked like a continuing target [U-2 incident][u2wiki] [Powers][powers] [secretprojects][spu2] [Military Review][milrev] | High-altitude target beyond interceptor reach, command latency, SAM envelopes, IFF code changeover, debris confusing battle damage assessment, political pressure | [H] → scenario "May Day Overflight" [F] details |
| **Cuban Missile Crisis, Oct 1962.** ADC dispersed nuclear-armed interceptors to dispersal bases [Cuban Missile Crisis summary][cmc] | Heightened alert posture, special weapons requiring release authority | [H] → scenario "Northern Vigil, October 1962" [F] details |
| ADIZ identification of civil traffic | Flight-plan correlation tolerances, unknowns, visual identification passes | [H] |

Planned later scenarios (not in the vertical slice): Sky Shield-style mass exercise raids with ECM, a defector landing undetected, a straying airliner over a militarized coast, a low-and-slow light aircraft penetrating a dense network, and an anomalous-propagation false alarm.

---

## 6. Physics used by the simulation

These are standard textbook models. They are **[A]** in the sense that they are simplified for real-time play. Each is documented in-game under "Technical Notes".

- **Radar range equation** (pulse radar, peak-power form) with integration of the pulses that hit the target during one beam dwell. A per-radar *calibration loss* reproduces documented detection ranges.
- **Swerling I target fluctuation:** P_d = P_fa^(1/(1+SNR)). Targets fade in and out from scan to scan at long range.
- **4/3-Earth refraction** for the radar horizon. Anomalous propagation is modelled by changing the k-factor (ducting extends range and produces distant clutter).
- **Terrain masking** using the running maximum of the terrain elevation angle along each azimuth, from ETOPO 10′ data.
- **Ground-reflection lobing** for low-frequency radars (flat-earth two-ray model, smoothed).
- **MTI:** clutter attenuation, a zero-Doppler notch (tangential targets fade) and blind speeds at multiples of λ·PRF/2.
- **Noise jamming:** jam-to-noise from the jammer's effective radiated power density, the radar's sidelobe or mainlobe gain toward the jammer, and burn-through range.
- **Aircraft:** point-mass energy model with altitude-dependent climb and speed limits, static ceiling vs zoom ceiling, and fuel flow by throttle setting.
- **Intercept geometry:** lead-collision quadratic solution, stern-conversion roll-out point, pure pursuit fallback.

---

## Sources

[sage-wiki]: https://en.wikipedia.org/wiki/Semi-Automatic_Ground_Environment
[fsq7]: https://www.wikipedia.com/wiki/FSQ-7
[sage-radar]: https://website.thedbcooperforum.com/Sage-Radar
[chm]: https://archive.computerhistory.org/resources/access/text/2022/06/102792720-05-01-acc.pdf
[bangor]: https://wiki.riteme.site/wiki/Bangor_Air_Defense_Sector
[topsham]: https://fortwiki.com/Topsham_SAGE_Direction_Center_DC-05
[m21]: https://www.numbersoddities.nl/M21-profile.pdf
[milrev]: https://military-review.com/12486387-fight-in-the-sky-over-the-urals
[uragan]: https://en.wikipedia.org/wiki/Uragan_Soviet_automatic_air_defense_interception_system
[gcilinks]: https://forums.radioreference.com/threads/historic-gci-data-links.404491/
[mig25p]: https://www.secretprojects.co.uk/goto/post?id=758930
[dcsgci]: https://forum.dcs.world/topic/197624-proper-gci-implementation
[fps20]: https://en.wikipedia.org/wiki/AN/FPS-20_Early_Warning_Radar
[fps20b]: https://www.themilitarystandard.com/radar/radar-equipment/an-fps-20/
[fps6rotor]: https://radarpages.co.uk/mob/rotor/fps6.htm
[fps6cande]: https://candemuseum.org/sites/default/files/archives/Pinetreeline/misc/equip/misc12o.html
[fps90]: https://fortwiki.com/FPS-90
[p8]: https://en.wikipedia.org/wiki/P-8_radar
[p8valka]: https://www.armedconflicts.com/-t15780
[p10]: https://Www.wikipedia.org/wiki/P-10_radar
[rusrad]: https://en.wikipedia.org/wiki/Russian_air_surveillance_radars
[bigmesh]: https://www.globalsecurity.org/military/world/russia/big-mesh.htm
[ac991]: https://rosap.ntl.bts.gov/view/dot/68992/dot_68992_DS1.pdf
[ac991a]: https://rosap.ntl.bts.gov/view/dot/68993/dot_68993_DS1.pdf
[aim]: https://www.faa.gov/air_traffic/publications/atpubs/aim/aim0506.html
[pinetree-id]: https://candemuseum.org/sites/default/files/archives/Pinetreeline/articles/resartc.html
[safronov]: https://en.wikipedia.org/wiki/Sergei_Safronov_(fighter_pilot)
[u2wiki]: https://en.wikipedia.org/wiki/1960_U-2_incident
[powers]: https://en.wikipedia.com/wiki/Gary_Powers
[spu2]: https://secretprojects.co.uk/goto/post?id=663755
[sa2ar]: https://www.armyrecognition.com/9464
[s75b]: https://en.wikipedia.com/wiki/HQ-2
[apa]: https://ausairpower.net/APA-S-75-Volkhov.html
[norad57]: https://documents2.theblackvault.com/afhracollection/NORAD%20FOIA%20releases/1957%20Jul-Dec%20NORAD%20Historical%20Summary%20Pages%2078-85%20Partial%20declassification.pdf
[norad58]: https://documents2.theblackvault.com/afhracollection/NORAD%20FOIA%20releases/1958%20Jul-Dec%20NORAD%20Historical%20Summary%20Pages%2065,%20110-111%20FOIA%20Partial%20release%2017-R-045%20Doc.pdf
[27ad]: https://en.wikipedia.org/wiki/27th_Air_Division
[cia77]: https://cia.gov/readingroom/docs/1977-03-15.pdf
[cmc]: https://lemm.ee/comment/11834286

Map data: [Natural Earth](https://www.naturalearthdata.com/) (public domain). Terrain: ETOPO1-derived 10 arc-minute grid distributed by the [Fatiando a Terra project](https://github.com/fatiando-data/earth-topography-10arcmin) (NOAA ETOPO1, public domain).
