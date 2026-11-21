"""Live data from public APIs (port of AuroraKpFetcher / LeoDataFetcher).

Uses only the standard library.  Every fetch fails soft: on any error the
value is -1 (or an empty mapping) so the UI can show "—".  Results are cached
in memory: Kp for 15 minutes, LEO / crew data for 6 hours, matching the
original application.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

USER_AGENT = "MoonPhase-Ubuntu/1.0"

KP_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
TLE_URL = "https://tle.ivanstanojevic.me/api/tle/{}"
GROUP_URL = "https://tle.ivanstanojevic.me/api/tle/?search={}&page-size=1"
TOTAL_URL = "https://tle.ivanstanojevic.me/api/tle/?page-size=1"
CREW_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"

ISS_NORAD, TIANGONG_NORAD, HUBBLE_NORAD = 25544, 48274, 20580
GM_EARTH = 3.986004418e14
EARTH_RADIUS_KM = 6371.0

KP_TTL = 15 * 60
LEO_TTL = 6 * 60 * 60


def _get_json(url: str, timeout: float = 15, attempts: int = 2):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                if 200 <= res.status < 300:
                    return json.loads(res.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - fail soft by design
            if attempt == attempts - 1:
                log.warning("fetch failed %s: %s", url, exc)
            else:
                time.sleep(1.5)
    return None


def parse_latest_kp(data) -> float:
    if not isinstance(data, list) or not data:
        return -1.0
    try:
        return float(data[-1].get("estimated_kp", -1.0))
    except (TypeError, ValueError, AttributeError):
        return -1.0


def altitude_from_tle_line2(line2: str) -> float:
    mean_motion = float(line2[52:63].strip())  # revs/day
    period = 86400.0 / mean_motion
    sma_m = (GM_EARTH * (period / (2 * math.pi)) ** 2) ** (1.0 / 3.0)
    return sma_m / 1000.0 - EARTH_RADIUS_KM


@dataclass
class People:
    total: int = -1
    iss_crew: int = -1
    crafts: dict[str, int] = field(default_factory=dict)


def parse_people(data) -> People:
    if not isinstance(data, dict):
        return People()
    total = int(data.get("number", -1))
    people = data.get("people")
    if not isinstance(people, list):
        return People(total, 0, {})
    counts: dict[str, int] = {}
    iss_craft: set[str] = set()
    for p in people:
        craft = p.get("spacecraft")
        if craft:
            counts[craft] = counts.get(craft, 0) + 1
            if p.get("iss"):
                iss_craft.add(craft)
    iss_crew = sum(counts[c] for c in iss_craft)
    crafts = {
        (f"{c} ★" if c in iss_craft else c): n
        for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
    }
    return People(total, iss_crew, crafts)


@dataclass
class Leo:
    iss_alt: float = -1.0
    tiangong_alt: float = -1.0
    hubble_alt: float = -1.0
    starlink: int = -1
    kuiper: int = -1
    total: int = -1
    people: People = field(default_factory=People)


class LiveData:
    """Thread-safe cached access to the live feeds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._kp: tuple[float, float] | None = None
        self._leo: tuple[Leo, float] | None = None

    def clear(self):
        with self._lock:
            self._kp = None
            self._leo = None

    def kp(self) -> float:
        with self._lock:
            if self._kp and time.time() - self._kp[1] < KP_TTL:
                return self._kp[0]
            value = parse_latest_kp(_get_json(KP_URL))
            self._kp = (value, time.time())
            return value

    def leo(self) -> Leo:
        with self._lock:
            if self._leo and time.time() - self._leo[1] < LEO_TTL:
                return self._leo[0]
            # The crew feed is a different host, so fetch it in parallel; the TLE
            # API rate-limits concurrent clients (HTTP 508), so query it serially.
            with ThreadPoolExecutor(max_workers=1) as pool:
                f_ppl = pool.submit(lambda: parse_people(_get_json(CREW_URL, 10)))
                leo = Leo(self._altitude(ISS_NORAD), self._altitude(TIANGONG_NORAD),
                          self._altitude(HUBBLE_NORAD), self._count(GROUP_URL.format("STARLINK")),
                          self._count(GROUP_URL.format("KUIPER")), self._count(TOTAL_URL))
                leo.people = f_ppl.result()
            self._leo = (leo, time.time())
            return leo

    @staticmethod
    def _altitude(norad: int) -> float:
        data = _get_json(TLE_URL.format(norad))
        try:
            return altitude_from_tle_line2(data["line2"])
        except Exception:  # noqa: BLE001
            return -1.0

    @staticmethod
    def _count(url: str) -> int:
        data = _get_json(url)
        try:
            return int(data.get("totalItems", -1))
        except Exception:  # noqa: BLE001
            return -1


def apply_live(snapshot, live: LiveData) -> None:
    """Fill the network-sourced fields of an ``astro.Snapshot`` in place."""
    snapshot.auroraKpIndex = live.kp()
    leo = live.leo()
    snapshot.issAltitudeKm = leo.iss_alt
    snapshot.tiangongAltitudeKm = leo.tiangong_alt
    snapshot.hubbleAltitudeKm = leo.hubble_alt
    snapshot.starlinkSatelliteCount = leo.starlink
    snapshot.kuiperSatelliteCount = leo.kuiper
    snapshot.totalSatellitesInOrbit = leo.total
    snapshot.issCrew = leo.people.iss_crew
    snapshot.totalPeopleInSpace = leo.people.total
    snapshot.craftOccupancy = dict(leo.people.crafts)
