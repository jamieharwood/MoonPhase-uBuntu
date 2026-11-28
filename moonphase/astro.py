"""Deterministic astronomy calculations.

A straight port of the ``org.iHarwood.MoonPhaseModule`` classes from the
original MoonPhase (Java / Spring Boot) project, so the desktop app shows the
same numbers as the web dashboard.  Everything here is pure Python with no
network access or GTK dependency, which keeps it easy to unit test.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

KM_PER_AU = 149_597_870.7
C_KM_S = 299_792.458
KM_PER_MILE = 1.60934

EARTH_MEAN_ANOMALY_J2000_DEG = 357.529
EARTH_MEAN_MOTION_DEG_PER_DAY = 0.98560028

DEFAULT_LATITUDE = 51.4769
DEFAULT_LONGITUDE = 0.0


# ── Date helpers ─────────────────────────────────────────────────────────────

def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_angle(deg: float) -> float:
    return ((deg % 360.0) + 360.0) % 360.0


def julian_day_number(day: int, month: int, year: int) -> int:
    """Integer Julian Day Number (noon-based), Gregorian/Julian aware."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    gregorian = year > 1582 or (year == 1582 and (month > 10 or (month == 10 and day >= 15)))
    if gregorian:
        return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083


def days_since_j2000(dt: datetime) -> float:
    dt = _utc(dt)
    jdn = julian_day_number(dt.day, dt.month, dt.year)
    frac = (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
    return jdn + frac - 2451545.0


def days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


# ── Julian dates and orbit helpers ──────────────────────────────────────────

JD_UNIX_EPOCH = 2440587.5
JD_J2000 = 2451545.0


def julian_date(dt: datetime) -> float:
    """Julian Date (UT) of an instant."""
    return JD_UNIX_EPOCH + _utc(dt).timestamp() / 86400.0


def centuries_since_j2000(jd: float) -> float:
    return (jd - JD_J2000) / 36525.0


def datetime_from_jd(jd: float) -> datetime:
    return datetime.fromtimestamp(round((jd - JD_UNIX_EPOCH) * 86400.0), tz=timezone.utc)


def solve_kepler(m: float, e: float) -> float:
    """Solve Kepler's equation E − e·sin E = M (radians) by Newton iteration."""
    ecc = m + e * math.sin(m)
    for _ in range(30):
        delta = (ecc - e * math.sin(ecc) - m) / (1.0 - e * math.cos(ecc))
        ecc -= delta
        if abs(delta) < 1e-12:
            break
    return ecc


def _norm(v) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _distance_between(p, q) -> float:
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def _sind(deg: float) -> float:
    return math.sin(math.radians(deg))


def _cosd(deg: float) -> float:
    return math.cos(math.radians(deg))


# ── Moon and Sun ephemeris ───────────────────────────────────────────────────
#
# Paul Schlyter, "How to compute planetary positions"
# (https://stjarnhimlen.se/comp/ppcomp.html): Keplerian lunar elements plus the
# principal perturbations (evection, variation, yearly equation, parallactic
# inequality, ...). Longitude is good to ~1–2 arcmin and distance to a few
# hundred km, enough to place new and full moon within minutes.

EARTH_RADIUS_KM = 6378.14
SYNODIC_MONTH = 29.530588853  # mean value, only used to seed root-finding


@dataclass(frozen=True)
class MoonSunPosition:
    """Geocentric ecliptic-of-date positions; angles in degrees."""
    moon_lon: float
    moon_lat: float
    moon_distance_km: float
    sun_lon: float
    sun_distance_km: float

    @property
    def elongation_longitude(self) -> float:
        """Moon − Sun ecliptic longitude in [0, 360): 0 = new moon, 180 = full moon."""
        return normalize_angle(self.moon_lon - self.sun_lon)

    @property
    def illuminated_fraction(self) -> float:
        cos_elong = _cosd(self.moon_lat) * _cosd(self.moon_lon - self.sun_lon)
        elong = math.acos(max(-1.0, min(1.0, cos_elong)))
        phase_angle = math.atan2(self.sun_distance_km * math.sin(elong),
                                 self.moon_distance_km - self.sun_distance_km * math.cos(elong))
        return (1.0 + math.cos(phase_angle)) / 2.0


def moon_sun_position(jd: float) -> MoonSunPosition:
    d = jd - 2451543.5  # Schlyter's day number: 2000 Jan 0.0 UT

    # Sun
    ws = 282.9404 + 4.70935e-5 * d
    es = 0.016709 - 1.151e-9 * d
    ms = normalize_angle(356.0470 + 0.9856002585 * d)
    e_sun = math.radians(ms) + es * _sind(ms) * (1.0 + es * _cosd(ms))
    xs = math.cos(e_sun) - es
    ys = math.sqrt(1.0 - es * es) * math.sin(e_sun)
    sun_dist_au = math.hypot(xs, ys)
    sun_lon = normalize_angle(math.degrees(math.atan2(ys, xs)) + ws)

    # Moon orbital elements
    node = 125.1228 - 0.0529538083 * d
    inc = 5.1454
    w = 318.0634 + 0.1643573223 * d
    a = 60.2666  # Earth radii
    e = 0.054900
    mm = normalize_angle(115.3654 + 13.0649929509 * d)
    ecc = solve_kepler(math.radians(mm), e)
    xv = a * (math.cos(ecc) - e)
    yv = a * math.sqrt(1.0 - e * e) * math.sin(ecc)
    v = math.degrees(math.atan2(yv, xv))
    r = math.hypot(xv, yv)
    vw = v + w
    xh = r * (_cosd(node) * _cosd(vw) - _sind(node) * _sind(vw) * _cosd(inc))
    yh = r * (_sind(node) * _cosd(vw) + _cosd(node) * _sind(vw) * _cosd(inc))
    zh = r * (_sind(vw) * _sind(inc))
    lon = math.degrees(math.atan2(yh, xh))
    lat = math.degrees(math.atan2(zh, math.hypot(xh, yh)))

    # Perturbations
    ls = ms + ws            # Sun mean longitude
    lm = mm + w + node      # Moon mean longitude
    dd = lm - ls            # mean elongation
    f = lm - node           # argument of latitude
    lon += (-1.274 * _sind(mm - 2 * dd)     # evection
            + 0.658 * _sind(2 * dd)         # variation
            - 0.186 * _sind(ms)             # yearly equation
            - 0.059 * _sind(2 * mm - 2 * dd)
            - 0.057 * _sind(mm - 2 * dd + ms)
            + 0.053 * _sind(mm + 2 * dd)
            + 0.046 * _sind(2 * dd - ms)
            + 0.041 * _sind(mm - ms)
            - 0.035 * _sind(dd)             # parallactic equation
            - 0.031 * _sind(mm + ms)
            - 0.015 * _sind(2 * f - 2 * dd)
            + 0.011 * _sind(mm - 4 * dd))
    lat += (-0.173 * _sind(f - 2 * dd)
            - 0.055 * _sind(mm - f - 2 * dd)
            - 0.046 * _sind(mm + f - 2 * dd)
            + 0.033 * _sind(f + 2 * dd)
            + 0.017 * _sind(2 * mm + f))
    r += -0.58 * _cosd(mm - 2 * dd) - 0.46 * _cosd(2 * dd)
    return MoonSunPosition(normalize_angle(lon), lat, r * EARTH_RADIUS_KM,
                           sun_lon, sun_dist_au * KM_PER_AU)


def _refine_phase(t: float, target_deg: float) -> float:
    """Newton iteration on the Moon − Sun longitude (≈12.19°/day)."""
    for _ in range(8):
        diff = normalize_angle(moon_sun_position(t).elongation_longitude - target_deg)
        if diff > 180.0:
            diff -= 360.0
        rate = (moon_sun_position(t + 0.01).elongation_longitude
                - moon_sun_position(t - 0.01).elongation_longitude)
        if rate < -180.0:
            rate += 360.0
        if rate > 180.0:
            rate -= 360.0
        step = diff / (rate / 0.02)
        t -= step
        if abs(step) < 1e-5:  # < 1 second
            break
    return t


def next_phase_jd(jd: float, target_deg: float) -> float:
    """JD of the next moment after ``jd`` when Moon − Sun longitude = target (0 new, 180 full)."""
    behind = normalize_angle(target_deg - moon_sun_position(jd).elongation_longitude)
    t = _refine_phase(jd + behind / 360.0 * SYNODIC_MONTH, target_deg)
    if t <= jd:
        t = _refine_phase(t + SYNODIC_MONTH, target_deg)
    return t


def previous_phase_jd(jd: float, target_deg: float) -> float:
    """JD of the most recent moment at or before ``jd`` with the given elongation."""
    ahead = normalize_angle(moon_sun_position(jd).elongation_longitude - target_deg)
    t = _refine_phase(jd - ahead / 360.0 * SYNODIC_MONTH, target_deg)
    if t > jd:
        t = _refine_phase(t - SYNODIC_MONTH, target_deg)
    return t


# ── Moon phase ───────────────────────────────────────────────────────────────

PHASE_NAMES = [
    "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
    "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
]
PHASE_ICONS = [
    "FullMoon", "wangmoon", "lqmoon", "wcmoon",
    "nwmoon", "wancrebmoon", "fqmoon", "wgmoon",
]
PHASE_ASCII = [
    ["       _..._     ", "     .:::::::.   ", "    :::::::::::  ", "    :::::::::::  ", "    `:::::::::'  ", "      `':::''    "],
    ["       _..._     ", "     .::::. `.   ", "    :::::::.  :  ", "    ::::::::  :  ", "    `::::::' .'  ", "      `'::'-'    "],
    ["       _..._     ", "     .::::  `.   ", "    ::::::    :  ", "    ::::::    :  ", "    `:::::   .'  ", "      `'::.-'    "],
    ["       _..._     ", "     .::'   `.   ", "    :::       :  ", "    :::       :  ", "    `::.     .'  ", "      `':..-'    "],
    ["       _..._     ", "     .'     `.   ", "    :         :  ", "    :         :  ", "    `.       .'  ", "      `-...-'    "],
    ["       _..._     ", "     .'   `::.   ", "    :       :::  ", "    :       :::  ", "    `.     .::'  ", "      `-..:''    "],
    ["       _..._     ", "     .'  ::::.   ", "    :    ::::::  ", "    :    ::::::  ", "    `.   :::::'  ", "      `-.::''    "],
    ["       _..._     ", "     .' .::::.   ", "    :  ::::::::  ", "    :  ::::::::  ", "    `. '::::::'  ", "      `-.::''    "],
]


@dataclass(frozen=True)
class MoonPhase:
    """True phase from the geocentric Sun and Moon positions, not a mean
    29.53-day cycle, so new and full moon land within minutes of the published times."""

    phase_fraction: float   # Moon − Sun longitude / 360°: 0 = new, 0.5 = full
    age_days_exact: float   # days since the previous true new moon
    illumination: float     # illuminated fraction 0–1
    jd: float               # moment of the calculation

    @classmethod
    def at(cls, dt: datetime) -> "MoonPhase":
        return cls.from_julian_date(julian_date(dt))

    @classmethod
    def from_julian_date(cls, jd: float) -> "MoonPhase":
        pos = moon_sun_position(jd)
        age = jd - previous_phase_jd(jd, 0.0)
        return cls(pos.elongation_longitude / 360.0, age, pos.illuminated_fraction, jd)

    @property
    def illumination_percent(self) -> int:
        return round(self.illumination * 100)

    @property
    def days_until_full_moon(self) -> int:
        """Days until the next full moon; 0 means within the last half day ("tonight")."""
        if self.jd - previous_phase_jd(self.jd, 180.0) < 0.5:
            return 0
        return round(next_phase_jd(self.jd, 180.0) - self.jd)

    @property
    def next_new_moon(self) -> datetime:
        return datetime_from_jd(next_phase_jd(self.jd, 0.0))

    @property
    def next_full_moon(self) -> datetime:
        return datetime_from_jd(next_phase_jd(self.jd, 180.0))

    @property
    def age_days(self) -> int:
        return round(self.age_days_exact)

    def _index(self) -> int:
        # Boundaries follow moonphases.co.uk (phase 0 = new moon), so a 95% moon
        # is still waxing gibbous rather than full.
        p = self.phase_fraction
        if p < 0.03 or p >= 0.97:
            return 4
        if p < 0.22:
            return 5
        if p < 0.28:
            return 6
        if p < 0.47:
            return 7
        if p < 0.53:
            return 0
        if p < 0.72:
            return 1
        if p < 0.78:
            return 2
        return 3

    @property
    def name(self) -> str:
        return PHASE_NAMES[self._index()]

    @property
    def icon(self) -> str:
        return PHASE_ICONS[self._index()]

    @property
    def ascii_art(self) -> list[str]:
        return PHASE_ASCII[self._index()]


# ── Distances ────────────────────────────────────────────────────────────────

def sun_distance_au(dt: datetime) -> float:
    d = days_since_j2000(dt)
    m = math.radians(normalize_angle(EARTH_MEAN_ANOMALY_J2000_DEG + EARTH_MEAN_MOTION_DEG_PER_DAY * d))
    return 1.00014 - 0.01671 * math.cos(m) - 0.00014 * math.cos(2 * m)


def sun_distance_min_max(dt: datetime) -> tuple[float, float]:
    start = _utc(dt).replace(hour=0, minute=0, second=0, microsecond=0)
    vals = [sun_distance_au(start + timedelta(days=i)) for i in range(days_in_year(start.year))]
    return min(vals), max(vals)


def moon_distance_km(dt: datetime) -> float:
    """Earth–Moon distance (centre to centre) from the lunar ephemeris."""
    return moon_sun_position(julian_date(dt)).moon_distance_km


# Extreme perigee / apogee distances (km).
MOON_DISTANCE_RANGE_KM = (356_400.0, 406_700.0)


# ── Planets ──────────────────────────────────────────────────────────────────
#
# JPL "Approximate Positions of the Planets" (E.M. Standish):
# https://ssd.jpl.nasa.gov/planets/approx_pos.html
# Each element (a, e, I, L, long. perihelion, long. node) is a value at J2000
# plus a rate per Julian century. Table 1 is used for 1800–2050 and Table 2a/2b
# (with the extra mean-anomaly terms for Jupiter–Neptune) outside that range.
# Kepler's equation is solved fully and positions are 3-D (J2000 ecliptic), so
# distances are good to roughly 0.001–0.01 AU.

_TABLE1_YEARS = (1800, 2050)


@dataclass(frozen=True)
class Planet:
    name: str
    table1: tuple          # a, e, I, L, varpi, Omega at J2000, then the six rates per century
    table2: tuple | None = None
    table2b: tuple | None = None   # b, c, s, f extra mean-anomaly terms

    def heliocentric_position(self, dt: datetime) -> tuple[float, float, float]:
        """Heliocentric position in AU, J2000 ecliptic frame."""
        dt = _utc(dt)
        t = centuries_since_j2000(julian_date(dt))
        use_table1 = self.table2 is None or _TABLE1_YEARS[0] <= dt.year <= _TABLE1_YEARS[1]
        el = self.table1 if use_table1 else self.table2
        a = el[0] + el[6] * t
        e = el[1] + el[7] * t
        inc = el[2] + el[8] * t
        mean_long = el[3] + el[9] * t
        varpi = el[4] + el[10] * t
        node = el[5] + el[11] * t
        arg_peri = varpi - node
        mean_anomaly = mean_long - varpi
        if not use_table1 and self.table2b is not None:
            b, c, s, f = self.table2b
            mean_anomaly += b * t * t + c * _cosd(f * t) + s * _sind(f * t)
        m = normalize_angle(mean_anomaly)
        if m > 180.0:
            m -= 360.0
        ecc = solve_kepler(math.radians(m), e)
        xp = a * (math.cos(ecc) - e)
        yp = a * math.sqrt(1.0 - e * e) * math.sin(ecc)
        cw, sw = _cosd(arg_peri), _sind(arg_peri)
        co, so = _cosd(node), _sind(node)
        ci, si = _cosd(inc), _sind(inc)
        x = (cw * co - sw * so * ci) * xp + (-sw * co - cw * so * ci) * yp
        y = (cw * so + sw * co * ci) * xp + (-sw * so + cw * co * ci) * yp
        z = (sw * si) * xp + (cw * si) * yp
        return x, y, z

    def heliocentric_au(self, dt: datetime) -> float:
        return _norm(self.heliocentric_position(dt))

    def geocentric_au(self, dt: datetime) -> float:
        """Distance from Earth (the Earth–Moon barycentre, ≤ 4,700 km off)."""
        return _distance_between(self.heliocentric_position(dt), EARTH.heliocentric_position(dt))


MERCURY = Planet(
    "Mercury",
    (0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593,
     0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081),
    (0.38709843, 0.20563661, 7.00559432, 252.25166724, 77.45771895, 48.33961819,
     0.00000000, 0.00002123, -0.00590158, 149472.67486623, 0.15940013, -0.12214182))
VENUS = Planet(
    "Venus",
    (0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255,
     0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418),
    (0.72332102, 0.00676399, 3.39777545, 181.97970850, 131.76755713, 76.67261496,
     -0.00000026, -0.00005107, 0.00043494, 58517.81560260, 0.05679648, -0.27274174))
EARTH = Planet(  # Earth–Moon barycentre
    "Earth",
    (1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0,
     0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0),
    (1.00000018, 0.01673163, -0.00054346, 100.46691572, 102.93005885, -5.11260389,
     -0.00000003, -0.00003661, -0.01337178, 35999.37306329, 0.31795260, -0.24123856))
MARS = Planet(
    "Mars",
    (1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891,
     0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343),
    (1.52371243, 0.09336511, 1.85181869, -4.56813164, -23.91744784, 49.71320984,
     0.00000097, 0.00009149, -0.00724757, 19140.29934243, 0.45223625, -0.26852431))
JUPITER = Planet(
    "Jupiter",
    (5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909,
     -0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106),
    (5.20248019, 0.04853590, 1.29861416, 34.33479152, 14.27495244, 100.29282654,
     -0.00002864, 0.00018026, -0.00322699, 3034.90371757, 0.18199196, 0.13024619),
    (-0.00012452, 0.06064060, -0.35635438, 38.35125000))
SATURN = Planet(
    "Saturn",
    (9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448,
     -0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794),
    (9.54149883, 0.05550825, 2.49424102, 50.07571329, 92.86136063, 113.63998702,
     -0.00003065, -0.00032044, 0.00451969, 1222.11494724, 0.54179478, -0.25015002),
    (0.00025899, -0.13434469, 0.87320147, 38.35125000))
URANUS = Planet(
    "Uranus",
    (19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503,
     -0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589),
    (19.18797948, 0.04685740, 0.77298127, 314.20276625, 172.43404441, 73.96250215,
     -0.00020455, -0.00001550, -0.00180155, 428.49512595, 0.09266985, 0.05739699),
    (0.00058331, -0.97731848, 0.17689245, 7.67025000))
NEPTUNE = Planet(
    "Neptune",
    (30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574,
     0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664),
    (30.06952752, 0.00895439, 1.77005520, 304.22289287, 46.68158724, 131.78635853,
     0.00006447, 0.00000818, 0.00022400, 218.46515314, 0.01009938, -0.00606302),
    (-0.00041348, 0.68346318, -0.10162547, 7.67025000))
# Pluto: the element set from the earlier edition of Table 1 (1800–2050), the
# last version that listed it.
PLUTO = Planet(
    "Pluto",
    (39.48211675, 0.24882730, 17.14001206, 238.92903833, 224.06891629, 110.30393684,
     -0.00031596, 0.00005170, 0.00004818, 145.20780515, -0.04062942, -0.01183482))


# ── Deep-space probes ────────────────────────────────────────────────────────
#
# Propagated from JPL Horizons heliocentric state vectors (J2000 ecliptic, AU and
# AU/day; CENTER=500@10, REF_PLANE=ECLIPTIC, OUT_UNITS=AU-D) under the Sun's
# gravity. Beyond the planets the Sun is the only significant force, so RK4
# integration of two-body motion (≤ 5-day steps) from one state vector stays
# within a few thousandths of an AU for decades either side of the epoch.
# Distance from Earth uses Earth's real position, so it carries the ±1 AU
# annual swing that a "heliocentric − 1 AU" shortcut misses.

_GM_SUN_AU3_D2 = 0.01720209895 ** 2
_MAX_STEP_DAYS = 5.0


def _derivative(s):
    r = math.sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2])
    k = -_GM_SUN_AU3_D2 / (r * r * r)
    return (s[3], s[4], s[5], k * s[0], k * s[1], k * s[2])


def _rk4(s, h):
    k1 = _derivative(s)
    k2 = _derivative([s[i] + k1[i] * h / 2 for i in range(6)])
    k3 = _derivative([s[i] + k2[i] * h / 2 for i in range(6)])
    k4 = _derivative([s[i] + k3[i] * h for i in range(6)])
    return [s[i] + h / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) for i in range(6)]


@dataclass(frozen=True)
class Spacecraft:
    name: str
    launch_jd: float
    epoch_jd: float
    state: tuple  # x, y, z [AU], vx, vy, vz [AU/day]

    def heliocentric_position(self, dt: datetime) -> tuple[float, float, float] | None:
        """Heliocentric position (AU, J2000 ecliptic), or None before launch."""
        jd = julian_date(dt)
        if jd < self.launch_jd:
            return None
        span = jd - self.epoch_jd
        steps = max(1, math.ceil(abs(span) / _MAX_STEP_DAYS))
        h = span / steps
        s = list(self.state)
        for _ in range(steps):
            s = _rk4(s, h)
        return s[0], s[1], s[2]

    def heliocentric_au(self, dt: datetime) -> float:
        p = self.heliocentric_position(dt)
        return 0.0 if p is None else _norm(p)

    def from_earth_au(self, dt: datetime) -> float:
        p = self.heliocentric_position(dt)
        return 0.0 if p is None else _distance_between(p, EARTH.heliocentric_position(dt))


_HORIZONS_EPOCH_JD = 2461041.5  # 2026-01-01 00:00 TDB

VOYAGER_1 = Spacecraft(  # Horizons target -31, launched 1977-09-05
    "Voyager 1", 2443391.5, _HORIZONS_EPOCH_JD,
    (-31.83641491929577, -134.6784911967567, 97.44481075134993,
     -0.001197151937928288, -0.00786107792125082, 0.005680005843310299))
VOYAGER_2 = Spacecraft(  # Horizons target -32, launched 1977-08-20
    "Voyager 2", 2443375.5, _HORIZONS_EPOCH_JD,
    (39.22753395002931, -103.9915540306074, -87.91866331046981,
     0.002427683334171075, -0.005395071892829595, -0.006538419567248777))
NEW_HORIZONS = Spacecraft(  # Horizons target -98, launched 2006-01-19
    "New Horizons", 2453754.5, _HORIZONS_EPOCH_JD,
    (20.00963528566975, -60.30445704637835, 2.212929493946444,
     0.003070495042525652, -0.007229267480329574, 0.0002845557285883782))

# James Webb flies a station-kept halo orbit around Sun–Earth L2 that can't be
# modelled offline, so its distance is fetched live (see fetchers.py); -1 means
# unavailable.
JWST_UNAVAILABLE = -1.0


# ── Earth ────────────────────────────────────────────────────────────────────

_GM_SUN = 1.32712440018e11


def earth_speed_km_s(sun_au: float) -> float:
    r_km = sun_au * KM_PER_AU
    return math.sqrt(_GM_SUN * (2.0 / r_km - 1.0 / KM_PER_AU))


def axial_tilt_deg(dt: datetime) -> float:
    return 23.439291 - 0.013004 * (days_since_j2000(dt) / 36525.0)


# ── Sun position, daylight, sunrise and sunset ───────────────────────────────
#
# NOAA solar calculator algorithm (Meeus, "Astronomical Algorithms",
# low-precision solar coordinates). Unlike a day-of-year approximation it tracks
# the calendar drift of the seasons, orbital eccentricity and the changing
# obliquity. Declination is good to ~0.01° and the equation of time to ~0.1 min,
# which puts sunrise and sunset within about a minute of almanac values.

# Altitude of the Sun's centre at official sunrise/sunset: upper limb on the
# horizon (semi-diameter ~16') plus standard refraction (~34').
SUNRISE_ALTITUDE_DEG = -0.833


def solar_position(dt: datetime) -> tuple[float, float]:
    """(declination in radians, equation of time in minutes) at an instant."""
    t = days_since_j2000(dt) / 36525.0
    mean_longitude = normalize_angle(280.46646 + t * (36000.76983 + t * 0.0003032))
    mean_anomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m = math.radians(mean_anomaly)
    centre = (math.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + math.sin(2 * m) * (0.019993 - 0.000101 * t)
              + math.sin(3 * m) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * t)
    apparent_longitude = math.radians(mean_longitude + centre - 0.00569 - 0.00478 * math.sin(omega))
    mean_obliquity = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliquity = math.radians(mean_obliquity + 0.00256 * math.cos(omega))
    declination = math.asin(math.sin(obliquity) * math.sin(apparent_longitude))
    y = math.tan(obliquity / 2.0) ** 2
    l0 = math.radians(mean_longitude)
    eot = (y * math.sin(2 * l0)
           - 2 * eccentricity * math.sin(m)
           + 4 * eccentricity * y * math.sin(m) * math.cos(2 * l0)
           - 0.5 * y * y * math.sin(4 * l0)
           - 1.25 * eccentricity * eccentricity * math.sin(2 * m))
    return declination, 4.0 * math.degrees(eot)


def _solar_position_on(d: date, hours_utc: float) -> tuple[float, float]:
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return solar_position(start + timedelta(seconds=round(hours_utc * 3600.0)))


def half_day_hours(latitude: float, declination: float) -> float:
    """Hours between solar noon and sunrise; 0 for polar night, 12 for midnight sun."""
    lat = math.radians(latitude)
    cos_h = ((math.sin(math.radians(SUNRISE_ALTITUDE_DEG)) - math.sin(lat) * math.sin(declination))
             / (math.cos(lat) * math.cos(declination)))
    if cos_h >= 1.0:
        return 0.0
    if cos_h <= -1.0:
        return 12.0
    return math.degrees(math.acos(cos_h)) / 15.0


def day_length_hours(d: date, latitude: float) -> float:
    """Sunrise to sunset, in hours (0 polar night, 24 midnight sun)."""
    declination, _ = _solar_position_on(d, 12.0)
    return 2.0 * half_day_hours(latitude, declination)


def day_length_min_max(latitude: float, dt: datetime | None = None) -> tuple[float, float]:
    """Shortest and longest day at this latitude (at the solstices)."""
    tilt = math.radians(axial_tilt_deg(dt or datetime.now(timezone.utc)))
    a = 2.0 * half_day_hours(latitude, tilt)
    b = 2.0 * half_day_hours(latitude, -tilt)
    return min(a, b), max(a, b)


def _format_hour(h: float) -> str:
    h = ((h % 24) + 24) % 24
    hours = int(h)
    minutes = round((h - hours) * 60)
    if minutes >= 60:
        hours += 1
        minutes -= 60
    if hours >= 24:
        hours -= 24
    return f"{hours:02d}:{minutes:02d}"


def _sun_event_hours(d: date, latitude: float, longitude: float, sunrise: bool) -> float | str:
    """UTC hours after midnight, refined once at the estimated event time."""
    offset = -longitude / 15.0
    t = 12.0 + offset
    for _ in range(2):
        declination, eot = _solar_position_on(d, t)
        half = half_day_hours(latitude, declination)
        if half <= 0.0:
            return "Polar Night"
        if half >= 12.0:
            return "Midnight Sun"
        noon = 12.0 + offset - eot / 60.0
        t = noon - half if sunrise else noon + half
    return t


def sunrise_sunset_utc(d: date, latitude: float, longitude: float) -> tuple[str, str]:
    out = []
    for rising in (True, False):
        h = _sun_event_hours(d, latitude, longitude, rising)
        out.append(h if isinstance(h, str) else _format_hour(h))
    return out[0], out[1]


# ── Light travel time ────────────────────────────────────────────────────────

def light_seconds(au: float) -> float:
    return au * KM_PER_AU / C_KM_S


def format_light_time(au: float) -> str:
    total = light_seconds(au)
    if total < 60:
        return f"{total:.0f}s"
    minutes = int(total / 60.0)
    secs = int(total % 60.0)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    return f"{minutes // 60}h {minutes % 60}m"


# ── Calendar events ──────────────────────────────────────────────────────────

def _next_annual(from_date: date, month: int, day: int) -> date:
    candidate = date(from_date.year, month, day)
    return candidate if from_date < candidate else date(from_date.year + 1, month, day)


def days_until(from_date: date, month: int, day: int) -> int:
    return (_next_annual(from_date, month, day) - from_date).days


EVENTS = {
    "Summer Solstice": (6, 21),
    "Winter Solstice": (12, 21),
    "Perihelion": (1, 3),
    "Aphelion": (7, 4),
}


# ── Snapshot ─────────────────────────────────────────────────────────────────

@dataclass
class Snapshot:
    """All dashboard values at an instant.  Field names match the original
    ``SnapshotDocument`` so history stored in MongoDB is interchangeable."""

    timestamp: datetime
    latitude: float
    longitude: float
    # Moon
    moonPhaseName: str = ""
    moonPhaseIcon: str = ""
    moonAsciiArt: list[str] = field(default_factory=list)
    moonPhaseFraction: float = 0.0
    moonIlluminationPercent: int = 0
    moonAgeDays: int = 0
    daysUntilFullMoon: int = 0
    moonDistanceKm: float = 0.0
    nextNewMoon: datetime | None = None
    nextFullMoon: datetime | None = None
    # Solar system (heliocentric AU except Mars/Jupiter/Saturn, geocentric as in the original)
    sunDistanceAu: float = 0.0
    mercuryDistanceAu: float = 0.0
    venusDistanceAu: float = 0.0
    marsDistanceAu: float = 0.0
    jupiterDistanceAu: float = 0.0
    saturnDistanceAu: float = 0.0
    uranusDistanceAu: float = 0.0
    neptuneDistanceAu: float = 0.0
    plutoDistanceAu: float = 0.0
    marsHelioAu: float = 0.0
    jupiterHelioAu: float = 0.0
    saturnHelioAu: float = 0.0
    lightTimes: dict[str, str] = field(default_factory=dict)
    # Probes
    voyager1DistanceAu: float = 0.0
    voyager2DistanceAu: float = 0.0
    voyager1HelioDistanceAu: float = 0.0
    voyager2HelioDistanceAu: float = 0.0
    newHorizonsDistanceAu: float = 0.0
    jamesWebbDistanceKm: float = JWST_UNAVAILABLE  # live only
    # Earth
    earthSpeedKmPerSec: float = 0.0
    earthSpeedKmPerHour: float = 0.0
    earthAxialTiltDegrees: float = 0.0
    daylightHours: float = 0.0
    sunriseTime: str = ""
    sunsetTime: str = ""
    auroraKpIndex: float = -1.0
    # Events
    daysUntilSummerSolstice: int = 0
    daysUntilWinterSolstice: int = 0
    daysUntilPerihelion: int = 0
    daysUntilAphelion: int = 0
    # LEO (filled from the network; -1 means unavailable)
    issAltitudeKm: float = -1.0
    tiangongAltitudeKm: float = -1.0
    hubbleAltitudeKm: float = -1.0
    starlinkSatelliteCount: int = -1
    kuiperSatelliteCount: int = -1
    totalSatellitesInOrbit: int = -1
    issCrew: int = -1
    totalPeopleInSpace: int = -1
    craftOccupancy: dict[str, int] = field(default_factory=dict)


def validate_lat(lat: float) -> float:
    return lat if -90 <= lat <= 90 else DEFAULT_LATITUDE


def validate_lon(lon: float) -> float:
    return lon if -180 <= lon <= 180 else DEFAULT_LONGITUDE


def compute(now: datetime | None = None, latitude: float = DEFAULT_LATITUDE,
            longitude: float = DEFAULT_LONGITUDE) -> Snapshot:
    """Compute every deterministic value (no network)."""
    now = _utc(now or datetime.now(timezone.utc))
    lat, lon = validate_lat(latitude), validate_lon(longitude)
    today = now.date()
    s = Snapshot(timestamp=now, latitude=lat, longitude=lon)

    mp = MoonPhase.at(now)
    s.moonPhaseName, s.moonPhaseIcon, s.moonAsciiArt = mp.name, mp.icon, mp.ascii_art
    s.moonPhaseFraction = mp.phase_fraction
    s.moonIlluminationPercent = mp.illumination_percent
    s.moonAgeDays = mp.age_days
    s.daysUntilFullMoon = mp.days_until_full_moon
    s.nextNewMoon = mp.next_new_moon
    s.nextFullMoon = mp.next_full_moon
    s.moonDistanceKm = moon_distance_km(now)

    s.sunDistanceAu = sun_distance_au(now)
    s.mercuryDistanceAu = MERCURY.heliocentric_au(now)
    s.venusDistanceAu = VENUS.heliocentric_au(now)
    s.marsDistanceAu = MARS.geocentric_au(now)
    s.jupiterDistanceAu = JUPITER.geocentric_au(now)
    s.saturnDistanceAu = SATURN.geocentric_au(now)
    s.marsHelioAu = MARS.heliocentric_au(now)
    s.jupiterHelioAu = JUPITER.heliocentric_au(now)
    s.saturnHelioAu = SATURN.heliocentric_au(now)
    s.uranusDistanceAu = URANUS.heliocentric_au(now)
    s.neptuneDistanceAu = NEPTUNE.heliocentric_au(now)
    s.plutoDistanceAu = PLUTO.heliocentric_au(now)

    s.voyager1HelioDistanceAu = VOYAGER_1.heliocentric_au(now)
    s.voyager2HelioDistanceAu = VOYAGER_2.heliocentric_au(now)
    s.voyager1DistanceAu = VOYAGER_1.from_earth_au(now)
    s.voyager2DistanceAu = VOYAGER_2.from_earth_au(now)
    s.newHorizonsDistanceAu = NEW_HORIZONS.from_earth_au(now)

    s.lightTimes = {
        "Mercury": format_light_time(s.mercuryDistanceAu),
        "Venus": format_light_time(s.venusDistanceAu),
        "Earth": format_light_time(s.sunDistanceAu),
        "Mars": format_light_time(s.marsHelioAu),
        "Jupiter": format_light_time(s.jupiterHelioAu),
        "Saturn": format_light_time(s.saturnHelioAu),
        "Uranus": format_light_time(s.uranusDistanceAu),
        "Neptune": format_light_time(s.neptuneDistanceAu),
        "Pluto": format_light_time(s.plutoDistanceAu),
        "Voyager 2": format_light_time(s.voyager2HelioDistanceAu),
        "Voyager 1": format_light_time(s.voyager1HelioDistanceAu),
    }

    s.earthSpeedKmPerSec = earth_speed_km_s(s.sunDistanceAu)
    s.earthSpeedKmPerHour = s.earthSpeedKmPerSec * 3600.0
    s.earthAxialTiltDegrees = axial_tilt_deg(now)
    s.daylightHours = day_length_hours(today, lat)
    s.sunriseTime, s.sunsetTime = sunrise_sunset_utc(today, lat, lon)

    s.daysUntilSummerSolstice = days_until(today, *EVENTS["Summer Solstice"])
    s.daysUntilWinterSolstice = days_until(today, *EVENTS["Winter Solstice"])
    s.daysUntilPerihelion = days_until(today, *EVENTS["Perihelion"])
    s.daysUntilAphelion = days_until(today, *EVENTS["Aphelion"])
    return s


def kp_activity(kp: float) -> str:
    if kp < 0:
        return "Unavailable"
    if kp < 2:
        return "Quiet"
    if kp < 4:
        return "Unsettled"
    if kp < 5:
        return "Active"
    return "Storm ⚡"
