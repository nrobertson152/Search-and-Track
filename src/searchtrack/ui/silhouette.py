"""Top-view aircraft silhouettes generated from a handful of real dimensions
(length, span, wing sweep, planform, tail and engine layout). Used for the
recognition cards, the reconnaissance photographs in briefings and the
cinematic screens. No artwork is copied: every outline is computed."""
from __future__ import annotations

import math

import pygame

# L, S in metres; sweep = leading-edge sweep in degrees; wing_pos = leading edge of the wing root as a fraction
# of length from the nose; root = root chord / L; taper = tip chord / root chord; fw = fuselage width / L.
SPECS: dict[str, dict] = {
    # --- US interceptors and aircraft
    "F-106A": dict(L=21.6, S=11.7, sweep=60, kind="delta", wing_pos=0.42, root=0.52, fw=0.07, tail=None),
    "F-102A": dict(L=20.8, S=11.6, sweep=60, kind="delta", wing_pos=0.44, root=0.50, fw=0.07, tail=None),
    "F-101B": dict(L=20.5, S=12.1, sweep=36, wing_pos=0.40, root=0.30, taper=0.45, fw=0.08,
                   tail=dict(span=0.55, pos=0.86, root=0.10, sweep=40)),
    "F-4E": dict(L=19.2, S=11.7, sweep=45, wing_pos=0.40, root=0.30, taper=0.30, fw=0.10,
                 tail=dict(span=0.50, pos=0.86, root=0.11, sweep=40)),
    "F-15A": dict(L=19.4, S=13.0, sweep=45, wing_pos=0.40, root=0.32, taper=0.25, fw=0.14,
                  tail=dict(span=0.66, pos=0.83, root=0.13, sweep=45), fins=2),
    "B-52G": dict(L=48.5, S=56.4, sweep=35, wing_pos=0.34, root=0.20, taper=0.33, fw=0.06,
                  tail=dict(span=0.30, pos=0.88, root=0.08, sweep=35), pods=[0.30, 0.60], pod_twin=True),
    "B-47E": dict(L=33.5, S=35.4, sweep=35, wing_pos=0.35, root=0.17, taper=0.35, fw=0.06,
                  tail=dict(span=0.35, pos=0.88, root=0.09, sweep=35), pods=[0.30, 0.75], pod_twin=False),
    "KC-135A": dict(L=41.5, S=39.9, sweep=35, wing_pos=0.36, root=0.18, taper=0.30, fw=0.08,
                    tail=dict(span=0.33, pos=0.88, root=0.09, sweep=35), pods=[0.35, 0.65]),
    "E-3A": dict(L=46.6, S=44.4, sweep=35, wing_pos=0.36, root=0.18, taper=0.30, fw=0.08,
                 tail=dict(span=0.33, pos=0.88, root=0.09, sweep=35), pods=[0.35, 0.65], dome=0.20),
    "P-2H": dict(L=27.9, S=31.6, sweep=3, wing_pos=0.38, root=0.14, taper=0.45, fw=0.07,
                 tail=dict(span=0.33, pos=0.88, root=0.08, sweep=5), props=[0.25], pods=[0.62]),
    "U-2C": dict(L=15.1, S=24.4, sweep=4, wing_pos=0.40, root=0.16, taper=0.35, fw=0.07,
                 tail=dict(span=0.32, pos=0.88, root=0.08, sweep=10)),
    "SR-71A": dict(L=32.7, S=16.9, sweep=52, kind="delta", wing_pos=0.40, root=0.55, fw=0.05, tail=None,
                   nacelles=0.42, chines=True),
    "C172": dict(L=8.2, S=11.0, sweep=0, wing_pos=0.30, root=0.18, taper=0.75, fw=0.12,
                 tail=dict(span=0.30, pos=0.86, root=0.13, sweep=8), props=[0.0], nose_prop=True),
    # --- airliners
    "B707": dict(L=46.6, S=44.4, sweep=35, wing_pos=0.36, root=0.18, taper=0.30, fw=0.08,
                 tail=dict(span=0.33, pos=0.88, root=0.09, sweep=35), pods=[0.35, 0.65]),
    "B747": dict(L=70.6, S=59.6, sweep=37, wing_pos=0.36, root=0.19, taper=0.27, fw=0.09,
                 tail=dict(span=0.37, pos=0.88, root=0.09, sweep=35), pods=[0.38, 0.68]),
    "DC-10": dict(L=55.5, S=50.4, sweep=35, wing_pos=0.38, root=0.18, taper=0.28, fw=0.10,
                  tail=dict(span=0.36, pos=0.88, root=0.09, sweep=35), pods=[0.38], tail_engine=True),
    "DC-7C": dict(L=34.2, S=38.8, sweep=4, wing_pos=0.34, root=0.14, taper=0.45, fw=0.09,
                  tail=dict(span=0.33, pos=0.88, root=0.09, sweep=8), props=[0.25, 0.48]),
    "L-1049": dict(L=34.6, S=37.5, sweep=4, wing_pos=0.36, root=0.14, taper=0.45, fw=0.09,
                   tail=dict(span=0.36, pos=0.88, root=0.08, sweep=4), props=[0.25, 0.48]),
    "Viscount": dict(L=26.1, S=28.6, sweep=3, wing_pos=0.36, root=0.15, taper=0.45, fw=0.11,
                     tail=dict(span=0.36, pos=0.86, root=0.10, sweep=8), props=[0.22, 0.46]),
    "CV-440": dict(L=24.8, S=32.1, sweep=3, wing_pos=0.36, root=0.15, taper=0.45, fw=0.11,
                   tail=dict(span=0.38, pos=0.86, root=0.10, sweep=8), props=[0.28]),
    "Il-14": dict(L=22.3, S=31.7, sweep=3, wing_pos=0.36, root=0.16, taper=0.45, fw=0.11,
                  tail=dict(span=0.40, pos=0.86, root=0.10, sweep=8), props=[0.28]),
    "Il-18": dict(L=35.9, S=37.4, sweep=3, wing_pos=0.36, root=0.15, taper=0.45, fw=0.09,
                  tail=dict(span=0.33, pos=0.88, root=0.09, sweep=8), props=[0.25, 0.50]),
    "Tu-104": dict(L=38.9, S=34.5, sweep=35, wing_pos=0.38, root=0.20, taper=0.35, fw=0.08,
                   tail=dict(span=0.34, pos=0.88, root=0.09, sweep=40), root_engines=True),
    "Tu-134": dict(L=37.1, S=29.0, sweep=35, wing_pos=0.38, root=0.17, taper=0.35, fw=0.08,
                   tail=dict(span=0.34, pos=0.90, root=0.09, sweep=40), rear_engines=True),
    "Il-62": dict(L=53.1, S=43.2, sweep=35, wing_pos=0.40, root=0.17, taper=0.30, fw=0.08,
                  tail=dict(span=0.30, pos=0.92, root=0.08, sweep=40), rear_engines=True),
    "An-2": dict(L=12.7, S=18.2, sweep=0, wing_pos=0.25, root=0.18, taper=1.0, fw=0.12,
                 tail=dict(span=0.40, pos=0.86, root=0.13, sweep=0), props=[0.0], nose_prop=True),
    # --- Soviet military
    "Tu-95M": dict(L=46.2, S=50.1, sweep=35, wing_pos=0.36, root=0.16, taper=0.40, fw=0.07,
                   tail=dict(span=0.30, pos=0.88, root=0.08, sweep=35), props=[0.28, 0.58], contra=True),
    "Tu-95MS": dict(L=49.5, S=50.1, sweep=35, wing_pos=0.36, root=0.16, taper=0.40, fw=0.07,
                    tail=dict(span=0.30, pos=0.88, root=0.08, sweep=35), props=[0.28, 0.58], contra=True),
    "Tu-16": dict(L=34.8, S=33.0, sweep=35, wing_pos=0.38, root=0.20, taper=0.35, fw=0.07,
                  tail=dict(span=0.34, pos=0.88, root=0.09, sweep=42), root_engines=True),
    "M-4": dict(L=47.7, S=50.5, sweep=35, wing_pos=0.38, root=0.18, taper=0.35, fw=0.06,
                tail=dict(span=0.34, pos=0.88, root=0.09, sweep=40), root_engines=True),
    "MiG-17PF": dict(L=11.3, S=9.6, sweep=45, wing_pos=0.38, root=0.28, taper=0.45, fw=0.12,
                     tail=dict(span=0.36, pos=0.86, root=0.12, sweep=45)),
    "MiG-19PM": dict(L=13.0, S=9.0, sweep=55, wing_pos=0.40, root=0.30, taper=0.35, fw=0.11,
                     tail=dict(span=0.40, pos=0.86, root=0.12, sweep=55)),
    "MiG-21PF": dict(L=14.5, S=7.2, sweep=57, kind="delta", wing_pos=0.45, root=0.40, fw=0.08,
                     tail=dict(span=0.40, pos=0.88, root=0.10, sweep=57)),
    "Su-9": dict(L=18.5, S=8.4, sweep=60, kind="delta", wing_pos=0.46, root=0.40, fw=0.08,
                 tail=dict(span=0.38, pos=0.88, root=0.10, sweep=55)),
    "Su-15TM": dict(L=19.6, S=9.4, sweep=60, kind="delta", wing_pos=0.46, root=0.36, fw=0.10,
                    tail=dict(span=0.40, pos=0.88, root=0.10, sweep=55)),
    "Yak-28P": dict(L=21.6, S=12.5, sweep=45, wing_pos=0.40, root=0.22, taper=0.40, fw=0.07,
                    tail=dict(span=0.38, pos=0.86, root=0.10, sweep=45), pods=[0.45]),
    "Tu-128": dict(L=30.1, S=17.5, sweep=55, wing_pos=0.42, root=0.27, taper=0.30, fw=0.09,
                   tail=dict(span=0.42, pos=0.86, root=0.11, sweep=55)),
    "MiG-25PD": dict(L=19.8, S=14.0, sweep=42, wing_pos=0.44, root=0.30, taper=0.30, fw=0.16,
                     tail=dict(span=0.60, pos=0.84, root=0.13, sweep=50), fins=2),
    "MiG-31": dict(L=22.7, S=13.5, sweep=41, wing_pos=0.44, root=0.30, taper=0.30, fw=0.15,
                   tail=dict(span=0.60, pos=0.84, root=0.13, sweep=50), fins=2),
    "Mi-8": dict(L=18.2, S=21.3, kind="heli", fw=0.13),
    "BALLOON": dict(L=20.0, S=20.0, kind="balloon"),
    "GENETRIX": dict(L=30.0, S=30.0, kind="balloon"),
    "AS-15": dict(L=6.0, S=3.1, sweep=10, wing_pos=0.45, root=0.12, taper=0.8, fw=0.09,
                  tail=dict(span=0.6, pos=0.9, root=0.08, sweep=30)),
}

_ROLE_FALLBACK = {"interceptor": "MiG-19PM", "bomber": "Tu-16", "recon": "U-2C", "airliner": "B707",
                  "transport": "Il-14", "light": "C172", "tanker": "KC-135A", "balloon": "BALLOON"}


def spec_for(type_id: str, role: str = "") -> dict:
    if type_id in SPECS:
        return SPECS[type_id]
    for k in SPECS:
        if type_id.startswith(k.split("-")[0] + "-") and k.split("-")[0] in ("MiG", "Su", "Tu", "Yak", "F", "B"):
            if k.startswith(type_id[:5]):
                return SPECS[k]
    return SPECS[_ROLE_FALLBACK.get(role, "B707")]


def _fuselage(L, fw):
    hw = fw * L / 2
    pts = []
    for k in range(13):
        f = k / 12
        y = -L / 2 + f * L
        if f < 0.16:
            w = hw * math.sin(f / 0.16 * math.pi / 2) ** 0.8
        elif f > 0.78:
            w = hw * (0.35 + 0.65 * (1 - (f - 0.78) / 0.22))
        else:
            w = hw
        pts.append((w, y))
    return [(x, y) for x, y in pts] + [(-x, y) for x, y in reversed(pts)]


def _surface(L, b, y_le, c_r, taper, sweep, x0, delta=False):
    """One right-hand lifting surface; returns polygon (mirrored by the caller)."""
    t = math.tan(math.radians(sweep))
    if delta:
        y_te = y_le + c_r
        tip_c = max(0.04 * c_r, 0.02 * L)
        return [(x0, y_le), (b, y_te - tip_c), (b, y_te), (x0, y_te)]
    c_t = c_r * taper
    y_tip = y_le + (b - x0) * t
    return [(x0, y_le), (b, y_tip), (b, y_tip + c_t), (x0, y_le + c_r)]


def polygons(sp: dict) -> tuple[list, list, list]:
    """(filled polygons, filled circles [(x, y, r)], lines [((x0, y0), (x1, y1))]) in metres, nose up."""
    L, S = sp["L"], sp["S"]
    polys, circles, lines = [], [], []
    kind = sp.get("kind", "swept")
    if kind == "balloon":
        circles.append((0.0, 0.0, S / 2))
        circles.append((0.0, S * 0.75, S * 0.06))
        lines.append(((0.0, S / 2), (0.0, S * 0.70)))
        return polys, circles, lines
    if kind == "heli":
        fw = sp.get("fw", 0.12)
        polys.append(_fuselage(L * 0.75, fw * 1.6))
        polys.append([(0.25, L * 0.3), (0.25, L * 0.55), (-0.25, L * 0.55), (-0.25, L * 0.3)])
        circles.append((0.0, -L * 0.05, S / 2))
        return polys, circles, lines
    fw = sp.get("fw", 0.08)
    polys.append(_fuselage(L, fw))
    x0 = fw * L / 2 * 0.8
    b = S / 2
    y_le = -L / 2 + sp.get("wing_pos", 0.38) * L
    c_r = sp.get("root", 0.2) * L
    delta = kind == "delta"
    right = _surface(L, b, y_le, c_r, sp.get("taper", 0.35), sp.get("sweep", 30), x0, delta)
    polys.append(right)
    polys.append([(-x, y) for x, y in right])
    if sp.get("chines"):
        ch = [(x0 * 0.3, -L * 0.47), (x0 * 1.6, -L * 0.30), (x0 * 2.6, y_le), (x0, y_le + c_r * 0.3)]
        polys.append(ch)
        polys.append([(-x, y) for x, y in ch])
    tl = sp.get("tail")
    if tl:
        tb = tl["span"] * S / 2
        ty = -L / 2 + tl["pos"] * L - tl["root"] * L * 0.6
        tr = _surface(L, tb, ty, tl["root"] * L, 0.4, tl.get("sweep", 35), x0 * 0.6)
        polys.append(tr)
        polys.append([(-x, y) for x, y in tr])
    t = math.tan(math.radians(sp.get("sweep", 30)))

    def le_at(frac):
        xx = x0 + (b - x0) * frac
        return xx, y_le + (xx - x0) * t

    for frac in sp.get("pods", []):
        xx, yy = le_at(frac)
        pl, pw = 0.11 * L, 0.035 * L * (1.6 if sp.get("pod_twin") else 1.0)
        for sgn in (1, -1):
            polys.append([(sgn * xx - pw / 2, yy - pl * 0.55), (sgn * xx + pw / 2, yy - pl * 0.55),
                          (sgn * xx + pw / 2, yy + pl * 0.45), (sgn * xx - pw / 2, yy + pl * 0.45)])
    for frac in sp.get("props", []):
        if sp.get("nose_prop"):
            lines.append(((-S * 0.11, -L / 2 - 0.2), (S * 0.11, -L / 2 - 0.2)))
            continue
        xx, yy = le_at(frac)
        nl, nw = 0.16 * L, 0.03 * L
        rad = max(1.5, 0.045 * S)
        for sgn in (1, -1):
            polys.append([(sgn * xx - nw / 2, yy - nl * 0.35), (sgn * xx + nw / 2, yy - nl * 0.35),
                          (sgn * xx + nw / 2, yy + nl * 0.65), (sgn * xx - nw / 2, yy + nl * 0.65)])
            lines.append(((sgn * xx - rad, yy - nl * 0.38), (sgn * xx + rad, yy - nl * 0.38)))
            if sp.get("contra"):
                lines.append(((sgn * xx - rad, yy - nl * 0.44), (sgn * xx + rad, yy - nl * 0.44)))
    if sp.get("root_engines"):
        for sgn in (1, -1):
            polys.append([(sgn * x0, y_le - 0.04 * L), (sgn * x0 * 2.2, y_le + 0.02 * L),
                          (sgn * x0 * 2.2, y_le + c_r * 0.9), (sgn * x0, y_le + c_r)])
    if sp.get("rear_engines"):
        for sgn in (1, -1):
            px = sgn * fw * L * 0.75
            polys.append([(px - 0.02 * L, L * 0.22), (px + 0.02 * L, L * 0.22), (px + 0.02 * L, L * 0.38),
                          (px - 0.02 * L, L * 0.38)])
    if sp.get("tail_engine"):
        polys.append([(-0.025 * L, L * 0.3), (0.025 * L, L * 0.3), (0.025 * L, L * 0.48), (-0.025 * L, L * 0.48)])
    if sp.get("nacelles"):
        xx, yy = le_at(sp["nacelles"])
        for sgn in (1, -1):
            polys.append([(sgn * xx, yy - 0.16 * L), (sgn * xx + 0.032 * L, yy - 0.06 * L),
                          (sgn * xx + 0.032 * L, L * 0.52), (sgn * xx - 0.032 * L, L * 0.52),
                          (sgn * xx - 0.032 * L, yy - 0.06 * L)])
    if sp.get("fins", 1) == 2 and tl:
        for sgn in (1, -1):
            lines.append(((sgn * x0 * 1.6, L * 0.25), (sgn * x0 * 1.6, L * 0.47)))
    if sp.get("dome"):
        circles.append((0.0, L * 0.12, sp["dome"] * S / 2))
    return polys, circles, lines


def render(type_id: str, role: str, size: int, color=(230, 230, 230), heading: float = 0.0,
           aa: int = 3, outline=None) -> pygame.Surface:
    """Silhouette fitted into a size×size box, nose pointing along `heading` (degrees, 0 = up)."""
    sp = spec_for(type_id, role)
    polys, circles, lines = polygons(sp)
    ext = max(sp["L"], sp["S"]) * 1.12
    big = size * aa
    k = big / ext
    S = pygame.Surface((big, big), pygame.SRCALPHA)
    c = big / 2
    heli = sp.get("kind") == "heli"
    if heli:
        for x, y, r in circles:
            pygame.draw.circle(S, (*color, 70), (c + x * k, c + y * k), max(1, r * k))
            pygame.draw.circle(S, (*color, 200), (c + x * k, c + y * k), max(1, r * k), aa)
            for a in (45, 135):
                ra = math.radians(a)
                pygame.draw.line(S, (*color, 255), (c + x * k - math.cos(ra) * r * k, c + y * k - math.sin(ra) * r * k),
                                 (c + x * k + math.cos(ra) * r * k, c + y * k + math.sin(ra) * r * k), aa * 2)
    for poly in polys:
        pygame.draw.polygon(S, (*color, 255), [(c + x * k, c + y * k) for x, y in poly])
    for x, y, r in ([] if heli else circles):
        pygame.draw.circle(S, (*color, 255), (c + x * k, c + y * k), max(1, r * k))
        if sp.get("kind") == "balloon":
            pygame.draw.circle(S, (*[max(0, v - 70) for v in color], 255), (c + x * k, c + y * k), max(1, r * k), aa)
    for (x0, y0), (x1, y1) in lines:
        pygame.draw.line(S, (*color, 255), (c + x0 * k, c + y0 * k), (c + x1 * k, c + y1 * k), max(1, aa))
    if heading:
        S = pygame.transform.rotate(S, -heading)
    out = pygame.transform.smoothscale(S, (S.get_width() // aa, S.get_height() // aa))
    return out
