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
