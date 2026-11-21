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


# ── Moon phase ───────────────────────────────────────────────────────────────

SYNODIC_MONTH = 29.530588853
KNOWN_NEW_MOON_JD = 2451550.1

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
    phase_fraction: float  # [0, 1): 0 = new, 0.5 = full
    age_days_exact: float

    @classmethod
    def at(cls, dt: datetime) -> "MoonPhase":
        dt = _utc(dt)
        noon_jd = julian_day_number(dt.day, dt.month, dt.year)
        frac = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
        return cls.from_julian_date(noon_jd - 0.5 + frac)

    @classmethod
    def from_julian_date(cls, jd: float) -> "MoonPhase":
        p = (jd - KNOWN_NEW_MOON_JD) / SYNODIC_MONTH
        p -= math.floor(p)
        return cls(p, p * SYNODIC_MONTH)

    @property
    def illumination_percent(self) -> int:
        return round((1 - math.cos(2 * math.pi * self.phase_fraction)) / 2 * 100)

    @property
    def days_until_full_moon(self) -> int:
        return round(((0.5 - self.phase_fraction + 1.0) % 1.0) * SYNODIC_MONTH)

    @property
    def age_days(self) -> int:
        return round(self.age_days_exact)

    def _index(self) -> int:
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
    d = days_since_j2000(dt)
    m = normalize_angle(134.9634 + 13.0649929509 * d)
    return 384_400.0 - 21_000.0 * math.cos(math.radians(m))


MOON_DISTANCE_RANGE_KM = (384_400.0 - 21_000.0, 384_400.0 + 21_000.0)

_W_EARTH_DEG = 102.93735


@dataclass(frozen=True)
class Planet:
    name: str
    a_au: float
    e: float
    m0_deg: float
    n_deg_per_day: float
    lon_perihelion_deg: float

    def heliocentric_au(self, dt: datetime) -> float:
        d = days_since_j2000(dt)
        m = normalize_angle(self.m0_deg + self.n_deg_per_day * d)
        return self.a_au * (1.0 - self.e * math.cos(math.radians(m)))

    def geocentric_au(self, dt: datetime) -> float:
        d = days_since_j2000(dt)
        r_earth = sun_distance_au(dt)
        m_earth = normalize_angle(EARTH_MEAN_ANOMALY_J2000_DEG + EARTH_MEAN_MOTION_DEG_PER_DAY * d)
        long_earth = math.radians(m_earth + _W_EARTH_DEG)
        m_planet = normalize_angle(self.m0_deg + self.n_deg_per_day * d)
        r_planet = self.a_au * (1.0 - self.e * math.cos(math.radians(m_planet)))
        long_planet = math.radians(m_planet + self.lon_perihelion_deg)
        delta = abs(long_planet - long_earth)
        return math.sqrt(r_earth ** 2 + r_planet ** 2 - 2.0 * r_earth * r_planet * math.cos(delta))


MERCURY = Planet("Mercury", 0.38709927, 0.20563593, 174.7947670, 4.09233445, 29.12427)
VENUS = Planet("Venus", 0.72333566, 0.00677672, 50.37663, 1.60213034, 54.85229)
MARS = Planet("Mars", 1.523679, 0.0934, 19.3870, 0.5240207766, 336.04084)
JUPITER = Planet("Jupiter", 5.2026, 0.0489, 20.0202, 0.0831294, 14.75385)
SATURN = Planet("Saturn", 9.5549, 0.0557, 317.0207, 0.0334442, 92.43194)
URANUS = Planet("Uranus", 19.18916464, 0.04716771, 142.238599, 0.01176904, 96.93735)
NEPTUNE = Planet("Neptune", 30.06992276, 0.00858587, 256.228347, 0.00598103, 276.33630)
PLUTO = Planet("Pluto", 39.48211675, 0.24882730, 14.53, 0.003975, 224.0)

# ── Deep-space probes (linear extrapolation from a 2024-01-01 reference) ─────

_PROBE_EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _au_per_day(km_s: float) -> float:
    return km_s * 86_400.0 / KM_PER_AU


def _days_since(epoch: datetime, dt: datetime) -> float:
    return int((_utc(dt) - epoch).total_seconds()) / 86_400.0


def voyager1_helio_au(dt: datetime) -> float:
    return 159.0 + _au_per_day(17.0) * _days_since(_PROBE_EPOCH, dt)


def voyager2_helio_au(dt: datetime) -> float:
    return 133.0 + _au_per_day(15.4) * _days_since(_PROBE_EPOCH, dt)


def new_horizons_helio_au(dt: datetime) -> float:
    return 58.0 + _au_per_day(13.8) * _days_since(_PROBE_EPOCH, dt)


def from_earth_au(helio_au: float) -> float:
    return max(0.0, abs(helio_au - 1.0))


_JWST_EPOCH = datetime(2022, 1, 24, tzinfo=timezone.utc)


def james_webb_km(dt: datetime) -> float:
    phase = 2.0 * math.pi * _days_since(_JWST_EPOCH, dt) / 180.0
    return 1_500_000.0 + 500_000.0 * math.sin(phase)


# ── Earth ────────────────────────────────────────────────────────────────────

_GM_SUN = 1.32712440018e11


def earth_speed_km_s(sun_au: float) -> float:
    r_km = sun_au * KM_PER_AU
    return math.sqrt(_GM_SUN * (2.0 / r_km - 1.0 / KM_PER_AU))


def axial_tilt_deg(dt: datetime) -> float:
    return 23.439291 - 0.013004 * (days_since_j2000(dt) / 36525.0)


_TILT = 23.44


def _declination(d: date) -> float:
    n = d.timetuple().tm_yday
    return math.radians(_TILT) * math.sin(2.0 * math.pi * (284 + n) / days_in_year(d.year))


def day_length_hours(d: date, latitude: float) -> float:
    x = -math.tan(math.radians(latitude)) * math.tan(_declination(d))
    if x >= 1.0:
        return 0.0
    if x <= -1.0:
        return 24.0
    return (24.0 / math.pi) * math.acos(x)


def day_length_min_max(latitude: float) -> tuple[float, float]:
    if abs(latitude) >= 66.5:
        return 0.0, 24.0
    lat = math.radians(latitude)

    def length(decl: float) -> float:
        x = -math.tan(lat) * math.tan(decl)
        if x >= 1.0:
            return 0.0
        if x <= -1.0:
            return 24.0
        return (24.0 / math.pi) * math.acos(x)

    a, b = length(math.radians(_TILT)), length(math.radians(-_TILT))
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


def _sun_times(d: date, latitude: float, longitude: float) -> tuple[str, str]:
    x = -math.tan(math.radians(latitude)) * math.tan(_declination(d))
    if x >= 1.0:
        return "Polar Night", "Polar Night"
    if x <= -1.0:
        return "Midnight Sun", "Midnight Sun"
    half = math.acos(x) * (12.0 / math.pi)
    b = math.radians(360.0 / 365.0 * (d.timetuple().tm_yday - 81))
    eot_h = (9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)) / 60.0
    noon = 12.0 - longitude / 15.0 - eot_h
    return _format_hour(noon - half), _format_hour(noon + half)


def sunrise_sunset_utc(d: date, latitude: float, longitude: float) -> tuple[str, str]:
    return _sun_times(d, latitude, longitude)


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
    jamesWebbDistanceKm: float = 0.0
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

    s.voyager1HelioDistanceAu = voyager1_helio_au(now)
    s.voyager2HelioDistanceAu = voyager2_helio_au(now)
    s.voyager1DistanceAu = from_earth_au(s.voyager1HelioDistanceAu)
    s.voyager2DistanceAu = from_earth_au(s.voyager2HelioDistanceAu)
    s.newHorizonsDistanceAu = from_earth_au(new_horizons_helio_au(now))
    s.jamesWebbDistanceKm = james_webb_km(now)

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
