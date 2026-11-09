"""Static equipment and doctrine definitions loaded from data/*.toml.

Definitions are never saved with the game; state refers to them by id.
Every definition carries ``provenance`` (historical / approximate / fictional).
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

SWERLING1_SNR_DB_PD50_PFA6 = 10.0 * math.log10(math.log(1e-6) / math.log(0.5) - 1.0)  # ~12.77 dB


@dataclass
class RadarType:
    id: str
    name: str
    name_ru: str = ""
    nation: str = ""
    role: str = "search"            # search | height | acq | fc
    band: str = "L"
    freq_mhz: float = 1300.0
    peak_kw: float = 1000.0
    pulse_us: float = 2.0
    prf: float = 400.0
    rpm: float = 5.0
    rpm_options: list[float] = field(default_factory=list)
    az_beam_deg: float = 1.5
    el_beam_deg: float = 3.0         # height finders: vertical beamwidth
    el_max_deg: float = 20.0
    gain_db: float = 34.0
    nf_db: float = 8.0
    sidelobe_db: float = -25.0
    ref_range_km: float = 300.0      # documented performance: Pd=0.5 at this range...
    ref_rcs_m2: float = 10.0         # ...against this RCS (calibration anchor)
    range_km: float = 370.0          # instrumented range
    mti: bool = False
    mti_if_db: float = 20.0          # MTI improvement factor
    mti_range_km: float = 90.0
    stagger: bool = False
    lobing: bool = False             # strong ground-reflection lobing (VHF)
    channels: int = 1
    freq_agile: bool = False
    height: str = "none"             # none | vbeam | nod
    height_sigma_m0: float = 300.0
    height_sigma_per_km: float = 2.0
    range_sigma_km: float = 0.5
    az_sigma_deg: float = 0.3
    iff: bool = True
    iff_range_km: float = 300.0
    clutter_db: float = -20.0        # land sigma0 at low grazing (dB m2/m2)
    weather_sens: float = 0.5        # 0 (VHF) .. 1 (S-band) relative precipitation response
    nod_cpm: float = 20.0
    slew_dps: float = 20.0
    mtbf_h: float = 200.0
    mttr_min: float = 45.0
    introduced: int = 1950
    nato_name: str = ""
    provenance: str = "approximate"
    notes: str = ""
    cal_loss_db: float = 0.0         # derived

    @property
    def wavelength_m(self) -> float:
        return 299.792458 / self.freq_mhz

    @property
    def pulses_per_dwell(self) -> float:
        return max(1.0, self.prf * self.az_beam_deg / (6.0 * self.rpm))


@dataclass
class AircraftType:
    id: str
    name: str
    name_ru: str = ""
    nation: str = ""
    role: str = "airliner"           # interceptor bomber recon airliner transport light tanker
    rcs_nose: float = 10.0
    rcs_beam: float = 30.0
    rcs_tail: float = 15.0
    cruise_kmh: float = 800.0
    cruise_alt_m: float = 9000.0
    max_mach: float = 0.85           # at optimum altitude
    max_kmh_sl: float = 900.0        # at sea level
    min_kmh: float = 250.0
    ceiling_m: float = 12000.0       # static (service) ceiling
    zoom_ceiling_m: float = 0.0      # 0 = no zoom capability beyond ceiling
    climb_mps: float = 10.0          # sea-level max climb
    accel_mps2: float = 1.5
    turn_dps: float = 3.0
    fuel_kg: float = 20000.0
    ff_cruise: float = 50.0          # kg/min
    ff_mil: float = 70.0
    ff_ab: float = 0.0
    ai_radar_km: float = 0.0         # airborne radar range vs 5 m2 target (0 = none)
    ai_radar_cone: float = 60.0
    lookdown: bool = False
    weapons: dict[str, int] = field(default_factory=dict)
    datalink: str = ""               # sage | lazur | ""
    transponder: str = "none"        # sif | kremniy | atc | none
    silhouette: str = ""
    provenance: str = "approximate"
    notes: str = ""

    def rcs(self, aspect_deg: float) -> float:
        """Aspect angle 0 = nose-on, 90 = beam, 180 = tail."""
        a = abs(aspect_deg) % 360.0
        if a > 180.0:
            a = 360.0 - a
        if a <= 90.0:
            w = (1 - math.cos(math.radians(a * 2))) / 2  # 0 -> 1
            return self.rcs_nose * (1 - w) + self.rcs_beam * w
        w = (1 - math.cos(math.radians((a - 90) * 2))) / 2
        return self.rcs_beam * (1 - w) + self.rcs_tail * w


@dataclass
class WeaponType:
    id: str
    name: str
    kind: str = "aam_radar"          # aam_radar aam_ir aam_beam rocket gun nuclear_rocket
    min_km: float = 1.0
    max_km: float = 8.0
    aspect: str = "all"              # all | rear | front
    pk: float = 0.5
    salvo: int = 2
    special: bool = False            # nuclear: needs release authority
    lethal_m: float = 30.0
    provenance: str = "approximate"
    notes: str = ""


@dataclass
class SamType:
    id: str
    name: str
    name_ru: str = ""
    nation: str = ""
    controller: str = "pvo"          # pvo | army | sage
    acq_radar: str = ""
    acq_range_km: float = 150.0
    fc_range_km: float = 60.0
    range_min_km: float = 8.0
    range_max_km: float = 30.0
    alt_min_m: float = 500.0
    alt_max_m: float = 22000.0
    missile_mps: float = 900.0
    boost_s: float = 5.0
    max_flight_s: float = 50.0
    cruise_alt_m: float = 0.0        # BOMARC-style cruise missile altitude
    homing_km: float = 0.0           # terminal seeker acquisition range (BOMARC)
    lethal_m: float = 60.0
    pk: float = 0.6
    launchers: int = 6
    salvo: int = 3
    salvo_interval_s: float = 6.0
    reload_min: float = 12.0
    acq_time_s: float = 20.0
    iff: bool = False
    special: bool = False
    provenance: str = "approximate"
    notes: str = ""


@dataclass
class JammerType:
    id: str
    name: str
    mode: str = "barrage"            # barrage | spot
    bands: list[str] = field(default_factory=list)
    erp_dbw_mhz: float = 10.0        # effective radiated power density
    retune_s: float = 60.0
    provenance: str = "approximate"
    notes: str = ""


@dataclass
class FactionDef:
    id: str
    name: str
    short: str
    pipeline: str = "digital"        # digital | manual
    identities: list[str] = field(default_factory=list)
    id_time_limit_s: float = 300.0
    readiness_levels: list[str] = field(default_factory=list)
    weapons_status: list[str] = field(default_factory=list)
    track_prefix: str = ""
    track_digits: int = 3
    report_interval_s: float = 60.0
    report_delay_s: list[float] = field(default_factory=lambda: [60.0, 240.0])
    grid_km: float = 10.0
    report_error_rate: float = 0.02
    company_capacity: int = 6
    link_delay_s: float = 3.0
    auto_initiate: bool = False
    own_color: str = "blue"
    notes: str = ""


@dataclass
class Catalog:
    radars: dict[str, RadarType] = field(default_factory=dict)
    aircraft: dict[str, AircraftType] = field(default_factory=dict)
    weapons: dict[str, WeaponType] = field(default_factory=dict)
    sams: dict[str, SamType] = field(default_factory=dict)
    jammers: dict[str, JammerType] = field(default_factory=dict)
    factions: dict[str, FactionDef] = field(default_factory=dict)
    data_dir: Path = DATA_DIR


def build(cls: type, raw: dict[str, Any]):
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(raw) - names
    if unknown:
        raise ValueError(f"{cls.__name__} {raw.get('id')}: unknown keys {sorted(unknown)}")
    return cls(**raw)


def calibrate_radar(rt: RadarType) -> None:
    """Set cal_loss_db so that Pd = 0.5 (Swerling I, Pfa 1e-6) at the reference
    range and RCS. Physical parameters then provide correct *scaling*."""
    from .radar import integrated_snr_db  # local import to avoid cycle

    rt.cal_loss_db = 0.0
    raw = integrated_snr_db(rt, rt.ref_range_km, rt.ref_rcs_m2)
    rt.cal_loss_db = raw - SWERLING1_SNR_DB_PD50_PFA6


def load_catalog(data_dir: Path | None = None) -> Catalog:
    d = Path(data_dir) if data_dir else DATA_DIR
    cat = Catalog(data_dir=d)
    spec = [("radars.toml", "radar", RadarType, cat.radars),
            ("aircraft.toml", "aircraft", AircraftType, cat.aircraft),
            ("weapons.toml", "weapon", WeaponType, cat.weapons),
            ("sams.toml", "sam", SamType, cat.sams),
            ("jammers.toml", "jammer", JammerType, cat.jammers),
            ("factions.toml", "faction", FactionDef, cat.factions)]
    for fname, key, cls, target in spec:
        raw = tomllib.loads((d / fname).read_text(encoding="utf-8"))
        for entry in raw.get(key, []):
            obj = build(cls, entry)
            if obj.id in target:
                raise ValueError(f"duplicate {key} id {obj.id}")
            target[obj.id] = obj
    for rt in cat.radars.values():
        calibrate_radar(rt)
    return cat


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))
