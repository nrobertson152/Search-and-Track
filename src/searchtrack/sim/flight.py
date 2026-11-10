"""Aircraft point-mass kinematics (energy-limited climb, zoom, fuel) and
scripted mission behaviour for non-player aircraft (traffic, threats, ghosts)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .catalog import AircraftType
from .geo import G, angle_diff, bearing_deg, heading_vec, isa_density_ratio, mach_to_tas
from .state import Aircraft, Waypoint

if TYPE_CHECKING:
    from .world import World


def max_speed(at: AircraftType, alt: float) -> float:
    """Full-power TAS (m/s) at altitude: blend from sea-level limit to Mach limit."""
    v_sl = at.max_kmh_sl / 3.6
    v_hi = mach_to_tas(at.max_mach, max(alt, 11000.0))
    w = min(1.0, max(0.0, alt / 11000.0))
    v = v_sl * (1 - w) + max(v_hi, v_sl * 0.9) * w
    if alt > at.ceiling_m * 0.85:  # thrust falls off approaching the ceiling
        v *= max(0.75, 1.0 - (alt - at.ceiling_m * 0.85) / (at.ceiling_m * 0.6))
    return v


def mil_speed(at: AircraftType, alt: float) -> float:
    if at.ff_ab <= 0:
        return max_speed(at, alt)
    return min(max_speed(at, alt), mach_to_tas(0.92, alt))


def cruise_speed(at: AircraftType, alt: float) -> float:
    v = at.cruise_kmh / 3.6
    if alt < at.cruise_alt_m:
        v *= 0.75 + 0.25 * alt / max(at.cruise_alt_m, 1.0)
    return min(v, max_speed(at, alt))


def min_speed(at: AircraftType, alt: float) -> float:
    return at.min_kmh / 3.6 / math.sqrt(max(isa_density_ratio(alt), 0.05)) * 0.6 + at.min_kmh / 3.6 * 0.4


def climb_rate(at: AircraftType, alt: float, throttle: str) -> float:
    frac = max(0.0, 1.0 - alt / max(at.ceiling_m, 1.0))
    c = at.climb_mps * frac ** 0.7
    if at.ff_ab > 0:
        c *= {"ab": 1.0, "mil": 0.45, "cruise": 0.25}.get(throttle, 0.45)
    else:
        c *= {"ab": 1.0, "mil": 1.0, "cruise": 0.5}.get(throttle, 1.0)
    return max(c, 0.0)


def fuel_flow(at: AircraftType, throttle: str, alt: float) -> float:
    """kg/s; lower at altitude for jets."""
    base = {"cruise": at.ff_cruise, "mil": at.ff_mil, "ab": at.ff_ab or at.ff_mil}.get(throttle, at.ff_cruise)
    return base / 60.0 * (0.55 + 0.45 * isa_density_ratio(alt) ** 0.5)


def wind_vector(world: "World", alt: float) -> tuple[float, float]:
    w = world.weather
    spd = w.wind_kmh / 3.6 * min(1.6, 0.4 + alt / 9000.0)
    hx, hy = heading_vec(w.wind_from)
    return -hx * spd, -hy * spd  # wind blows *from* wind_from


def step_aircraft(world: "World", ac: Aircraft, dt: float) -> None:
    if ac.state != "airborne":
        return
    if ac.kind == "debris":
        ac.spd *= 0.96 ** dt
        ac.vs = max(ac.vs - 9.0 * dt, -220.0)
        ac.alt += ac.vs * dt
        ac.rcs_scale *= 0.985 ** dt
        hx, hy = heading_vec(ac.hdg)
        ac.x += hx * ac.spd * dt / 1000.0
        ac.y += hy * ac.spd * dt / 1000.0
        if ac.alt <= world.ground_height(ac.x, ac.y) or (0 <= ac.t_end <= world.t):
            ac.state = "gone"
        return
    at = world.catalog.aircraft[ac.type_id]
    # ---- heading
    if ac.cmd_hdg is not None:
        turn = at.turn_dps * (0.55 + 0.45 * isa_density_ratio(ac.alt) ** 0.5)
        d = angle_diff(ac.cmd_hdg, ac.hdg)
        ac.hdg = (ac.hdg + max(-turn * dt, min(turn * dt, d))) % 360.0
    # ---- altitude / energy
    ceiling = at.ceiling_m
    zoom = max(at.zoom_ceiling_m, ceiling)
    target_alt = ac.cmd_alt if ac.cmd_alt is not None else ac.alt
    if ac.fuel <= 0.0 and ac.kind == "aircraft":
        target_alt = -1000.0  # flame-out glide
        ac.throttle = "cruise"
    vmin = min_speed(at, ac.alt)
    if target_alt > ac.alt + 1.0:
        if ac.alt < ceiling:
            ac.vs = min(climb_rate(at, ac.alt, ac.throttle), (target_alt - ac.alt) / dt)
        elif ac.alt < zoom and ac.spd > vmin * 1.1:
            # zoom: trade kinetic for potential energy
            dh = min((target_alt - ac.alt), zoom - ac.alt, 60.0 * dt, (ac.spd ** 2 - (vmin * 1.05) ** 2) / (2 * G))
            ac.vs = max(dh, 0.0) / dt
            ac.spd = math.sqrt(max((vmin * 1.05) ** 2, ac.spd ** 2 - 2 * G * ac.vs * dt))
        else:
            ac.vs = -8.0 if ac.alt > ceiling else 0.0
    elif target_alt < ac.alt - 1.0:
        ac.vs = max(-max(at.climb_mps * 0.6, 12.0), (target_alt - ac.alt) / dt)
    else:
        ac.vs = 0.0 if ac.alt <= ceiling else -5.0
    ac.alt = max(ac.alt + ac.vs * dt, 0.0)
    # ---- speed
    if ac.throttle == "ab" and at.ff_ab > 0:
        vmax = max_speed(at, ac.alt)
    elif ac.throttle in ("mil", "ab"):
        vmax = mil_speed(at, ac.alt)
    else:
        vmax = max(cruise_speed(at, ac.alt), min(ac.cmd_spd or 0.0, mil_speed(at, ac.alt)))
    if ac.fuel <= 0.0:
        vmax = vmin * 1.2
    want = ac.cmd_spd if ac.cmd_spd is not None else vmax
    want = max(vmin, min(want, vmax))
    if ac.alt <= zoom and not (ac.alt > ceiling and ac.vs > 0):
        acc = at.accel_mps2 * (1.0 if ac.throttle == "ab" else 0.6)
        ac.spd += max(-acc * 1.5 * dt, min(acc * dt, want - ac.spd))
        ac.spd -= max(ac.vs, 0.0) * G / max(ac.spd, 50.0) * dt * 0.15  # climbing costs a little speed
    ac.spd = max(ac.spd, vmin * 0.95)
    # ---- fuel
    if ac.kind == "aircraft" and at.fuel_kg > 0:
        ac.fuel = max(0.0, ac.fuel - fuel_flow(at, ac.throttle, ac.alt) * dt)
    # ---- position (air velocity + wind)
    hx, hy = heading_vec(ac.hdg)
    wx, wy = wind_vector(world, ac.alt)
    ac.x += (hx * ac.spd + wx) * dt / 1000.0
    ac.y += (hy * ac.spd + wy) * dt / 1000.0
    if ac.alt <= world.ground_height(ac.x, ac.y) and ac.fuel <= 0.0:
        world.destroy(ac.id, "fuel exhaustion", crash=True)


def ground_velocity(world: "World", ac: Aircraft) -> tuple[float, float]:
    """Ground velocity in km/s."""
    hx, hy = heading_vec(ac.hdg)
    if ac.kind == "debris":
        return hx * ac.spd / 1000.0, hy * ac.spd / 1000.0
    wx, wy = wind_vector(world, ac.alt)
    return (hx * ac.spd + wx) / 1000.0, (hy * ac.spd + wy) / 1000.0


# ---------------------------------------------------------------- missions

def step_mission(world: "World", ac: Aircraft, dt: float) -> None:
    m = ac.mission
    if m is None or ac.state != "airborne" or ac.flight_id:
        return
    if m.kind == "ghost":
        rng = world.rng
        base = ac.hdg
        if m.wp < len(m.waypoints):
            wp = m.waypoints[m.wp]
            base = bearing_deg(wp.x - ac.x, wp.y - ac.y)
            if math.hypot(wp.x - ac.x, wp.y - ac.y) < 8.0:
                m.wp += 1
        if ac.cmd_hdg is None or rng.random() < 0.06 * dt:
            ac.cmd_hdg = (base + rng.uniform(-m.wander, m.wander)) % 360.0
            ac.cmd_spd = max(60.0, min(240.0, ac.spd + rng.uniform(-50.0, 50.0)))
            ac.cmd_alt = max(1500.0, min(12000.0, ac.alt + rng.uniform(-2500.0, 2500.0)))
        return
    if m.kind == "balloon":
        wx, wy = wind_vector(world, ac.alt)
        ac.hdg = bearing_deg(wx, wy)
        ac.spd = 0.0
        ac.cmd_hdg, ac.cmd_spd = ac.hdg, 0.0
        if m.alt_day > 0.0:
            ac.cmd_alt = balloon_altitude(world, m)
        elif m.waypoints:
            ac.cmd_alt = m.waypoints[0].alt
        return
    if m.orbit_until > world.t:
        ac.cmd_hdg = (ac.hdg + 3.0 * dt) % 360.0
        return
    if m.wp >= len(m.waypoints):
        return
    wp: Waypoint = m.waypoints[m.wp]
    dx, dy = wp.x - ac.x, wp.y - ac.y
    d = math.hypot(dx, dy)
    if m.kind != "ghost":
        ac.cmd_hdg = bearing_deg(dx, dy)
        ac.cmd_alt = wp.alt
        ac.cmd_spd = wp.spd
        if m.agl > 0.0 and wp.alt <= 1000.0:
            ac.cmd_alt = terrain_follow_alt(world, ac, m.agl)
    if d < max(3.0, ac.spd * dt / 1000.0 * 2.5):
        _waypoint_action(world, ac, wp)
        m.wp += 1
        if m.wp >= len(m.waypoints) and ac.state == "airborne" and m.kind == "route":
            ac.state = "gone"
            world.log_event("sys", f"{ac.callsign} left the area", ac.id)


def balloon_altitude(world: "World", m) -> float:
    """Float altitude of a free balloon: high by day, sinking after sunset as the gas cools,
    ballast drops keep it from falling below the night floor; rises again after sunrise."""
    h = world.local_hour()
    rise, sets = 8.5, 17.0           # winter Urals, local solar time
    if rise + 1.5 <= h <= sets:
        f = 1.0
    elif sets < h < sets + 3.0:
        f = 1.0 - (h - sets) / 3.0
    elif rise <= h < rise + 1.5:
        f = (h - rise) / 1.5
    else:
        f = 0.0
    return m.alt_night + (m.alt_day - m.alt_night) * f


def terrain_follow_alt(world: "World", ac: Aircraft, agl: float) -> float:
    """Terrain-following: clear the highest ground within ~6 km ahead by `agl` metres."""
    hx, hy = heading_vec(ac.hdg)
    terr = world.theater.terrain
    top = 0.0
    for k in (0.0, 1.5, 3.0, 4.5, 6.0):
        top = max(top, terr.height(ac.x + hx * k, ac.y + hy * k))
    return top + agl


def signal_to_land(world: "World", ac: Aircraft, fl_callsign: str) -> str:
    """An intercepted aircraft reacts to "follow me" signals. Returns a short pilot report."""
    m = ac.mission
    if m is None:
        return "no reaction"
    beh = m.on_signal or ("comply" if ac.side == "civil" else "ignore")
    if beh.startswith("shots:") and not m.warned:
        return "no reaction to wing-rocking or lights"
    if beh.startswith("shots:"):
        beh = "comply:" + beh.split(":", 1)[1]
    if beh.startswith("comply"):
        if m.signaled:
            return "following us"
        base = beh.split(":", 1)[1] if ":" in beh else ""
        b = world.airbases.get(base) or min(world.airbases.values(), default=None,
                                              key=lambda bb: math.hypot(bb.x - ac.x, bb.y - ac.y))
        if b is None:
            return "no airfield"
        m.signaled = True
        m.on_intercept = "comply"
        m.waypoints = m.waypoints[:m.wp] + [Waypoint(b.x, b.y, 300.0, max(ac.spd * 0.6, 60.0), "land;forced")]
        world.log_event("scenario", f"{ac.callsign} acknowledged signals and is following to {b.name}", ac.id)
        return f"he is lowering his gear and following us to {b.name}"
    if beh == "evade":
        ac.cmd_hdg = (ac.hdg + world.rng.choice([-80.0, 80.0])) % 360.0
        if m.wp < len(m.waypoints):
            m.waypoints[m.wp].alt = max(150.0, ac.alt - 3000.0)
        return "he is turning away and descending"
    return "no reaction to signals"


def _waypoint_action(world: "World", ac: Aircraft, wp: Waypoint) -> None:
    for act in filter(None, wp.action.split(";")):
        if act == "jam_on":
            ac.jamming = True
        elif act == "jam_off":
            ac.jamming = False
        elif act in ("land", "remove"):
            ac.state = "landed" if act == "land" else "gone"
            if act == "land" and "forced" in wp.action:
                b = min(world.airbases.values(), default=None, key=lambda bb: math.hypot(bb.x - ac.x, bb.y - ac.y))
                world.stats.forced.append([ac.id, b.id if b else "", world.t])
                world.vars[f"forced_{ac.id}"] = 1.0
                world.alert(f"{ac.callsign} has landed at {b.name if b else 'the airfield'} under escort", ac.id, 1)
        elif act.startswith("orbit:"):
            ac.mission.orbit_until = world.t + float(act.split(":")[1])
        elif act.startswith("var:"):
            name = act.split(":")[1]
            world.vars[name] = world.vars.get(name, 0.0) + 1.0
        elif act == "transponder_off":
            ac.transponder.on = False
        elif act == "transponder_on":
            ac.transponder.on = True


def react_to_intercept(world: "World", ac: Aircraft) -> None:
    """Called when an interceptor completes a visual identification pass."""
    m = ac.mission
    if m is None or m.intercepted:
        return
    m.intercepted = True
    beh = m.on_intercept
    if beh.startswith("turn_away"):
        hdg = float(beh.split(":")[1]) if ":" in beh else (ac.hdg + 180.0) % 360.0
        hx, hy = heading_vec(hdg)
        m.waypoints = m.waypoints[:m.wp] + [Waypoint(ac.x + hx * 900.0, ac.y + hy * 900.0, ac.alt, ac.spd)]
        world.log_event("scenario", f"{ac.callsign} turned away after intercept", ac.id)
    elif beh == "evade":
        ac.cmd_hdg = (ac.hdg + world.rng.choice([-70.0, 70.0])) % 360.0
        if m.wp < len(m.waypoints):
            m.waypoints[m.wp].alt = max(300.0, ac.alt - 4000.0)
