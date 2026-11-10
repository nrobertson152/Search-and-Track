"""Simulation state: plain dataclasses, cross-referenced by id (see serialize.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Transponder:
    system: str = "none"                 # sif | atc | kremniy | none
    on: bool = True
    failed: bool = False
    codes: dict[str, str] = field(default_factory=dict)


@dataclass
class Waypoint:
    x: float
    y: float
    alt: float                           # m
    spd: float                           # m/s TAS
    action: str = ""                     # jam_on | jam_off | land | remove | orbit:<s> | descend


@dataclass
class Mission:
    kind: str = "route"                  # route | ghost | balloon
    waypoints: list[Waypoint] = field(default_factory=list)
    wp: int = 0
    on_intercept: str = "comply"         # comply | turn_away:<hdg> | evade | ignore
    intercepted: bool = False
    orbit_until: float = 0.0
    wander: float = 0.0                  # ghosts: erratic heading changes (deg/s)
    alt_day: float = 0.0                 # balloons: float altitude by day...
    alt_night: float = 0.0               # ...and after the gas cools at night
    agl: float = 0.0                     # terrain following: height above ground (m), 0 = off
    on_signal: str = ""                  # reaction to "follow me" signals: comply:<base> | ignore | evade | shots:<base>
    signaled: bool = False
    warned: bool = False                 # warning shots fired across the nose


@dataclass
class Aircraft:
    id: str
    type_id: str
    callsign: str
    side: str                            # blue | red | civil | neutral
    x: float = 0.0
    y: float = 0.0
    alt: float = 0.0
    hdg: float = 0.0
    spd: float = 0.0
    vs: float = 0.0
    fuel: float = 0.0
    state: str = "airborne"              # airborne | landed | destroyed | gone
    throttle: str = "cruise"             # cruise | mil | ab
    cmd_hdg: Optional[float] = None
    cmd_alt: Optional[float] = None
    cmd_spd: Optional[float] = None
    transponder: Transponder = field(default_factory=Transponder)
    mission: Optional[Mission] = None
    flight_id: str = ""
    home_base: str = ""
    weapons: dict[str, int] = field(default_factory=dict)
    jamming: bool = False
    jammer: str = ""
    jam_channel: int = -1                # -1 barrage; else spot channel
    jam_retune_t: float = 0.0
    flight_plan: str = ""
    kind: str = "aircraft"               # aircraft | ghost | debris | balloon
    rcs_scale: float = 1.0
    visible_to: list[str] = field(default_factory=list)
    t_spawn: float = 0.0
    t_end: float = -1.0
    destroyed_by: str = ""
    truth_label: str = ""                # what it really is (AAR / VID text)
    nationality: str = ""
    markings: str = ""
    # ---- battle missions
    group: str = ""                      # AirGroup id when the battle AI flies it
    damage: float = 0.0                  # 0 intact .. 1 destroyed
    homing: str = ""                     # anti-ship missile: ship it has locked
    aim: list[float] = field(default_factory=list)   # anti-ship missile: aim point [x, y]
    launcher: str = ""                   # anti-ship missile: who fired it
    evade_t: float = -1.0                # defensive manoeuvre against a missile until
    t_max: float = -1.0                  # anti-ship missile: self-destruct time
    route: list[list[float]] = field(default_factory=list)   # cruise missile: waypoints before the aim point
    pilot: str = ""                      # battles: who is flying it (BattleState.pilots)


@dataclass
class PendingOrder:
    t_apply: float
    hdg: Optional[float] = None
    alt: Optional[float] = None
    throttle: str = ""


@dataclass
class Flight:
    id: str
    callsign: str
    squadron_id: str
    base_id: str
    type_id: str
    n: int = 2
    members: list[str] = field(default_factory=list)
    state: str = "scrambling"            # scrambling airborne vector contact judy vid shadow attack rtb landed lost
    t_order: float = 0.0
    t_airborne: float = 0.0
    task: str = "intercept"              # intercept | id | shadow | cap | ram
    target: str = ""                     # system track id
    geometry: str = "lead"               # lead | stern | pursuit
    control: str = "voice"               # voice | datalink
    controller: str = ""                 # guidance radar site id (PVO) / "DC"
    auto: bool = True
    order_hdg: Optional[float] = None
    order_alt: Optional[float] = None
    order_throttle: str = "mil"
    last_vector_t: float = -999.0
    last_vec_hdg: float = -1.0
    last_vec_alt: float = -1.0
    pending: list[PendingOrder] = field(default_factory=list)
    weapons_free: bool = False
    special_release: bool = False
    contact: str = ""                    # truth id held on airborne radar
    contact_t: float = -1.0
    tally: bool = False
    vid_done: bool = False
    vid_report: str = ""
    bingo: bool = False
    cap_x: Optional[float] = None
    cap_y: Optional[float] = None
    rtb_base: str = ""
    pip_x: Optional[float] = None
    pip_y: Optional[float] = None
    pip_t: Optional[float] = None
    shots: int = 0
    kills: list[str] = field(default_factory=list)
    lost_contact_t: float = -1.0


@dataclass
class Squadron:
    id: str
    name: str
    base_id: str
    type_id: str
    callsign: str
    side: str = "blue"
    ready: dict[str, int] = field(default_factory=dict)   # alert minutes -> aircraft
    maint: int = 0
    airborne: int = 0
    lost: int = 0
    pilots: int = 8
    loadout: dict[str, int] = field(default_factory=dict)
    turnaround_min: float = 40.0
    recovering: list[float] = field(default_factory=list)
    upgrading: list[list[float]] = field(default_factory=list)   # [t_done, bucket_minutes]
    iff_codes: dict[str, str] = field(default_factory=dict)
    next_no: int = 1


@dataclass
class Airbase:
    id: str
    name: str
    x: float
    y: float
    elev: float = 0.0
    side: str = "blue"
    kind: str = "military"
    runway_ok: bool = True
    link: str = ""
    name_ru: str = ""
    carrier: str = ""                    # aircraft carrier: id of the ship the base sails with


@dataclass
class RadarSite:
    id: str
    name: str
    type_id: str
    x: float
    y: float
    elev: float
    mast_m: float = 20.0
    side: str = "blue"
    unit: str = ""
    status: str = "ok"                   # ok | degraded | down | maint
    az: float = 0.0
    rpm: float = 5.0
    mti: bool = False
    pfa_exp: float = 6.0
    channel: int = 0
    iff_on: bool = True
    link: str = ""
    bias_r: float = 0.0
    bias_az: float = 0.0
    gci: bool = False
    k_override: Optional[float] = None
    degraded_db: float = 0.0
    fail_t: float = -1.0
    repair_t: float = -1.0
    maint_until: float = -1.0
    company_no: int = 0
    company_tracks: dict[str, "CompanyTrack"] = field(default_factory=dict)
    name_ru: str = ""
    carrier: str = ""                    # airborne radar: id of the aircraft carrying it

    @property
    def h_ant(self) -> float:
        return self.elev + self.mast_m


@dataclass
class CompanyTrack:
    """A radar company's own target (manual reporting pipeline)."""
    no: str
    truth: str
    x: float
    y: float
    alt: Optional[float]
    t_seen: float
    t_next_report: float
    size: int = 1
    iff: str = ""
    hits: int = 1
    last_iff: str = ""


@dataclass
class HeightFinder:
    id: str
    site_id: str
    type_id: str
    status: str = "ok"
    az: float = 0.0
    queue: list[str] = field(default_factory=list)
    current: str = ""
    t_done: float = -1.0
    last_result: str = ""


@dataclass
class SamSite:
    id: str
    name: str
    type_id: str
    x: float
    y: float
    elev: float = 0.0
    side: str = "blue"
    unit: str = ""
    status: str = "ok"
    readiness_min: float = 0.0           # minutes to ready when alerted (0 = ready)
    t_ready: float = 0.0
    ready_missiles: int = 6
    reloads: int = 12
    reloading: list[float] = field(default_factory=list)
    assigned: str = ""                   # track id
    state: str = "idle"                  # idle search locked engaging assess
    lock: str = ""                       # truth entity id
    t_state: float = 0.0
    salvo_left: int = 0
    salvo_size: int = 3
    t_next_launch: float = 0.0
    des_x: float = 0.0
    des_y: float = 0.0
    des_alt: float = 0.0
    hold: bool = False
    auto: bool = False
    fired: int = 0
    link: str = ""
    last_result: str = ""
    fault_t: float = -1.0                # scripted fire-control fault until
    name_ru: str = ""
    carrier: str = ""                    # shipborne fire channel: id of the ship


@dataclass
class Missile:
    id: str
    type_id: str
    kind: str                            # sam | aam | bomarc
    owner: str
    side: str
    x: float
    y: float
    alt: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    target: str = ""                     # truth entity being guided on
    track: str = ""                      # BOMARC: track id until homing
    t_launch: float = 0.0
    homing: bool = False
    state: str = "flying"
    result: str = ""


@dataclass
class Report:
    """A plot (digital) or a target report (manual) delivered to a command post."""
    rid: int
    t: float                             # observation time
    t_arrive: float
    radar: str
    x: float
    y: float
    alt: Optional[float] = None
    alt_sigma: float = 0.0
    snr_db: float = 0.0
    size: int = 1
    iff: dict[str, str] = field(default_factory=dict)
    iff_garbled: bool = False
    truth: str = ""                      # hidden: entity id or "" for false alarm
    company: str = ""                    # manual pipeline: company target number
    grid: str = ""                       # manual pipeline: reported grid square
    strobe_az: Optional[float] = None    # bearing-only jam strobe report


@dataclass
class Track:
    id: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    alt: Optional[float] = None
    alt_src: str = ""
    alt_t: float = -1.0
    t_update: float = 0.0
    t_init: float = 0.0
    quality: int = 3
    hits: int = 1
    identity: str = "pending"
    id_t: float = -1.0
    id_basis: str = ""
    sources: dict[str, float] = field(default_factory=dict)
    company_keys: list[str] = field(default_factory=list)
    iff: dict[str, str] = field(default_factory=dict)
    iff_t: float = -1.0
    fp: str = ""
    size: int = 1
    history: list[list[float]] = field(default_factory=list)
    jammer: bool = False
    lost: bool = False
    t_lost: float = -1.0
    priority: int = 0
    truth_votes: dict[str, int] = field(default_factory=dict)
    hf_requested: bool = False
    alt_fails: int = 0
    adiz_t: float = -1.0
    note: str = ""
    reported: bool = False
    local: bool = False                  # guidance-point local track


@dataclass
class FlightPlan:
    id: str
    callsign: str
    type_id: str
    kind: str = "IFR"                    # IFR | DVFR | MIL
    route: list[list[float]] = field(default_factory=list)   # [x, y, t]
    alt: float = 0.0
    mode3: str = ""
    filed: bool = True
    note: str = ""


@dataclass
class Message:
    mid: int
    t: float
    t_deliver: float
    channel: str                          # radio voice tty datalink system
    sender: str
    text: str
    priority: int = 0                     # 0 routine 1 priority 2 flash
    ack: bool = False
    acked: bool = False
    delivered: bool = False
    ref: str = ""
    kind: str = "info"
    t_ack: float = -1.0


@dataclass
class Link:
    id: str
    name: str
    kind: str = "voice"                   # data voice tty radio
    up: bool = True
    delay_s: float = 5.0
    repair_t: float = -1.0


@dataclass
class Request:
    rid: int
    kind: str                             # declare_hostile engage weapons_status special_release ram readiness
    ref: str
    value: str
    t: float
    t_answer: float
    answered: bool = False
    granted: bool = False
    reason: str = ""


@dataclass
class HQState:
    name: str = "HQ"
    readiness: str = ""
    alert: str = ""
    weapons_status: str = "HOLD"
    credibility: float = 1.0
    pressure: float = 0.0
    requests: list[Request] = field(default_factory=list)
    hostile: list[str] = field(default_factory=list)        # tracks declared hostile by authority
    engage_ok: list[str] = field(default_factory=list)      # tracks cleared for engagement
    special_release: bool = False
    policy: dict[str, Any] = field(default_factory=dict)
    t_next_query: float = -1.0


@dataclass
class Objective:
    id: str
    text: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    points: int = 10
    status: str = "open"                  # open done failed
    t_status: float = -1.0
    hidden: bool = False
    penalty: int = 0


@dataclass
class Trigger:
    id: str
    cond: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    once: bool = True
    fired: bool = False
    t_fired: float = -1.0


@dataclass
class LogEntry:
    t: float
    cat: str
    text: str
    ref: str = ""


@dataclass
class WeatherCell:
    x: float
    y: float
    r: float
    intensity: float                      # 0..1
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class Weather:
    k_factor: float = 4.0 / 3.0
    wind_from: float = 270.0
    wind_kmh: float = 60.0
    ceiling_m: float = 3000.0
    visibility_km: float = 20.0
    night: bool = False
    sea_state: float = 3.0
    cells: list[WeatherCell] = field(default_factory=list)
    duct_radars: list[str] = field(default_factory=list)
    duct_k: float = 4.0


@dataclass
class Stats:
    first_plot: dict[str, float] = field(default_factory=dict)      # truth -> first delivered report
    first_track: dict[str, float] = field(default_factory=dict)     # truth -> first track
    first_id: dict[str, float] = field(default_factory=dict)        # truth -> first non-pending identity
    final_id: dict[str, str] = field(default_factory=dict)
    vid: dict[str, float] = field(default_factory=dict)
    adiz: dict[str, float] = field(default_factory=dict)
    sorties: int = 0
    missiles: int = 0
    aam_shots: int = 0
    kills: list[list[str]] = field(default_factory=list)            # [victim, shooter, side_of_victim]
    false_tracks: int = 0
    tracks_initiated: int = 0
    unacked_overdue: int = 0
    fuel_emergencies: int = 0
    reports_to_hq: int = 0
    truth_snaps: list[list[Any]] = field(default_factory=list)
    sim_kills: list[list[str]] = field(default_factory=list)          # exercise: [victim, shooter]
    forced: list[list[Any]] = field(default_factory=list)             # forced landings: [aircraft, base, t]
    locks: dict[str, float] = field(default_factory=dict)             # truth -> first fire-control lock


# ====================================================================== battle missions

@dataclass
class Ship:
    id: str
    name: str
    type_id: str
    side: str = "blue"
    x: float = 0.0
    y: float = 0.0
    hdg: float = 0.0
    spd: float = 0.0                     # m/s
    group: str = ""                      # task group; the guide steers the group's course
    guide: bool = False
    station_brg: float = 0.0             # station relative to the guide's heading (deg)...
    station_km: float = 0.0              # ...and distance
    route: list[list[float]] = field(default_factory=list)   # guide: [x, y] waypoints, cycled
    wp: int = 0
    speed_kn: float = 16.0
    hp: float = 100.0
    max_hp: float = 100.0
    state: str = "afloat"                # afloat | damaged | crippled | sunk
    chaff: int = 4
    t_chaff: float = -1.0
    emcon: bool = False                  # radars silent
    evading_until: float = -1.0
    hits: int = 0
    name_ru: str = ""


@dataclass
class AirGroup:
    """A formation flown by the battle AI (either side): a raid, an escort, a jammer, an AEW."""
    id: str
    name: str
    callsign: str
    side: str
    role: str                            # strike escort sweep cap recon ew awacs tanker intercept
    type_id: str
    n: int = 2
    members: list[str] = field(default_factory=list)
    base: str = ""                       # airbase id; "" = enters and leaves at the map edge
    entry: list[float] = field(default_factory=list)     # [x, y, alt] where it enters play
    exit: list[float] = field(default_factory=list)      # [x, y] where it leaves play
    state: str = "pending"               # pending outbound station attack egress rtb done
    t_launch: float = 1e12
    route: list[list[float]] = field(default_factory=list)   # [x, y, alt] transit waypoints
    wp: int = 0
    station: list[float] = field(default_factory=list)   # [x, y, alt, radius] orbit
    target: str = ""                     # strike: ship id or task group; escort: group id
    launch_km: float = 0.0               # strike: release range (0 = weapon maximum)
    commit_km: float = 60.0              # fighters: engage enemies this close to what they guard
    alt: float = 0.0
    spd_kmh: float = 0.0
    abort_frac: float = 0.5              # turn for home after losing this fraction
    released: bool = False
    t_state: float = 0.0
    air_target: str = ""                 # truth id of the aircraft being engaged
    t_next_shot: float = 0.0
    losses: int = 0
    kills: int = 0
    jam: bool = False                    # ew: jam once on station
    reported: bool = False               # recon: target reported
    trigger: str = ""                    # launched by a director phase / decision rather than a time
    aim: list[float] = field(default_factory=list)       # strike: where it believes the target is
    radio_t: float = 0.0
    note: str = ""


@dataclass
class Contact:
    """One side's knowledge of an enemy aircraft or ship (perception model)."""
    id: str                              # truth id
    x: float
    y: float
    alt: float = 0.0
    vx: float = 0.0                      # km/s
    vy: float = 0.0
    t: float = 0.0                       # last seen
    err_km: float = 1.0
    by: str = ""                         # sensor that holds it
    kind: str = "air"                    # air | ship
    t_first: float = 0.0
    passive: bool = False                # bearing-and-emitter fix only (ESM)


@dataclass
class Decision:
    """A call the commander has to make, with a timer and a default."""
    id: int
    t: float
    kind: str
    title: str
    text: str
    options: list[str] = field(default_factory=list)
    default: str = ""
    t_expire: float = 0.0
    ref: str = ""
    chosen: str = ""
    t_chosen: float = -1.0
    by: str = ""                         # player | staff | timeout
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Pilot:
    """A named airman of one of our squadrons; in a war he carries his record from battle to battle."""
    id: str
    name: str                            # "CDR Jack 'Hollywood' Harlan"
    squadron: str
    rank: str = ""
    surname: str = ""
    kills: int = 0                       # over the whole war
    sorties: int = 0
    status: str = "active"               # active | flying | rescued | missing | kia
    aircraft: str = ""                   # while flying
    note: str = ""                       # what happened to him tonight


@dataclass
class BattleState:
    active: bool = False
    spectator: bool = False
    post: str = ""                       # the control room's title
    post_sub: str = ""
    phase: int = -1
    phases: list[dict[str, Any]] = field(default_factory=list)
    t_phase: float = 0.0
    groups: dict[str, AirGroup] = field(default_factory=dict)
    red_air: dict[str, Contact] = field(default_factory=dict)          # red's picture of our aircraft
    surface: dict[str, dict[str, Contact]] = field(default_factory=dict)   # side -> ship -> contact
    red_sensors: list[dict[str, Any]] = field(default_factory=list)
    standing: dict[str, Any] = field(default_factory=dict)             # standing orders
    priority: list[str] = field(default_factory=list)                  # tracks the commander singled out
    decisions: list[Decision] = field(default_factory=list)
    decision_seq: int = 0
    reinforcements: list[dict[str, Any]] = field(default_factory=list)
    cap_stations: list[dict[str, Any]] = field(default_factory=list)
    events: list[list[Any]] = field(default_factory=list)              # [t, kind, text, ref, x, y, side, level]
    t_last_event: float = 0.0
    counters: dict[str, float] = field(default_factory=dict)
    red_plan: dict[str, Any] = field(default_factory=dict)
    defended: list[str] = field(default_factory=list)                  # own assets the enemy is after
    end_t: float = -1.0
    outcome: str = ""
    view: list[float] = field(default_factory=list)                     # [x, y, km across] at the start
    pilots: dict[str, Pilot] = field(default_factory=dict)              # our aircrew, by id
