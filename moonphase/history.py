"""Historical snapshot storage.

Two interchangeable back ends:

* ``SqliteHistory`` (default) – a local file in ``~/.local/share/moonphase``.
* ``MongoHistory`` – the ``snapshots`` collection used by the original
  MoonPhase web app, so both apps can share one history.  Needs ``pymongo``
  (``sudo apt install python3-pymongo``).

As in the original, at most one snapshot is stored per 12-hour UTC window.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import astro

log = logging.getLogger(__name__)

# (key, label, group) – the numeric fields of the original SnapshotDocument.
METRICS: list[tuple[str, str, str]] = [
    ("moonIlluminationPercent", "Illumination (%)", "Moon"),
    ("moonAgeDays", "Moon Age (days)", "Moon"),
    ("moonDistanceKm", "Moon Distance (km)", "Moon"),
    ("daysUntilFullMoon", "Days Until Full Moon", "Moon"),
    ("daylightHours", "Daylight Hours", "Moon"),
    ("sunDistanceAu", "Sun → Earth (AU)", "Solar System"),
    ("mercuryDistanceAu", "Sun → Mercury (AU)", "Solar System"),
    ("venusDistanceAu", "Sun → Venus (AU)", "Solar System"),
    ("marsDistanceAu", "Earth → Mars (AU)", "Solar System"),
    ("jupiterDistanceAu", "Earth → Jupiter (AU)", "Solar System"),
    ("saturnDistanceAu", "Earth → Saturn (AU)", "Solar System"),
    ("uranusDistanceAu", "Sun → Uranus (AU)", "Solar System"),
    ("neptuneDistanceAu", "Sun → Neptune (AU)", "Solar System"),
    ("plutoDistanceAu", "Sun → Pluto (AU)", "Solar System"),
    ("voyager1HelioDistanceAu", "Sun → Voyager 1 (AU)", "Solar System"),
    ("voyager2HelioDistanceAu", "Sun → Voyager 2 (AU)", "Solar System"),
    ("voyager1DistanceAu", "Earth → Voyager 1 (AU)", "Deep Space"),
    ("voyager2DistanceAu", "Earth → Voyager 2 (AU)", "Deep Space"),
    ("newHorizonsDistanceAu", "Earth → New Horizons (AU)", "Deep Space"),
    ("earthSpeedKmPerSec", "Orbital Speed (km/s)", "Earth"),
    ("earthSpeedKmPerHour", "Orbital Speed (km/h)", "Earth"),
    ("earthAxialTiltDegrees", "Axial Tilt (°)", "Earth"),
    ("auroraKpIndex", "Aurora Kp Index", "Earth"),
    ("issAltitudeKm", "ISS Altitude (km)", "Near Earth"),
    ("tiangongAltitudeKm", "Tiangong Altitude (km)", "Near Earth"),
    ("hubbleAltitudeKm", "Hubble Altitude (km)", "Near Earth"),
    ("starlinkSatelliteCount", "Starlink Satellites", "Near Earth"),
    ("kuiperSatelliteCount", "Kuiper Satellites", "Near Earth"),
    ("totalSatellitesInOrbit", "Total in Orbit", "Near Earth"),
    ("issCrew", "ISS Crew", "Near Earth"),
    ("totalPeopleInSpace", "People in Space", "Near Earth"),
    ("daysUntilSummerSolstice", "Days to Summer Solstice", "Upcoming Events"),
    ("daysUntilWinterSolstice", "Days to Winter Solstice", "Upcoming Events"),
    ("daysUntilPerihelion", "Days to Perihelion", "Upcoming Events"),
    ("daysUntilAphelion", "Days to Aphelion", "Upcoming Events"),
]
METRIC_KEYS = [m[0] for m in METRICS]
MAX_POINTS = 500


def half_day_window(ts: datetime) -> tuple[datetime, datetime]:
    ts = ts.astimezone(timezone.utc)
    start = ts.replace(hour=0 if ts.hour < 12 else 12, minute=0, second=0, microsecond=0)
    return start, start + timedelta(hours=12)


def snapshot_to_doc(s: astro.Snapshot, ts: datetime | None = None) -> dict:
    doc = {k: getattr(s, k) for k in METRIC_KEYS}
    doc["timestamp"] = (ts or s.timestamp).astimezone(timezone.utc)
    return doc


def to_csv(metric: str, points: list[tuple[datetime, float]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", metric])
    for ts, v in points:
        w.writerow([ts.strftime("%Y-%m-%dT%H:%M:%SZ"), v])
    return buf.getvalue()


class SqliteHistory:
    name = "Local (SQLite)"

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        cols = ", ".join(f'"{k}" REAL' for k in METRIC_KEYS)
        self._db.execute(f"CREATE TABLE IF NOT EXISTS snapshots (timestamp TEXT PRIMARY KEY, {cols})")
        self._db.commit()

    @staticmethod
    def _iso(ts: datetime) -> str:
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def save(self, s: astro.Snapshot, ts: datetime | None = None, dedupe: bool = True) -> bool:
        doc = snapshot_to_doc(s, ts)
        start, end = half_day_window(doc["timestamp"])
        with self._lock:
            if dedupe:
                row = self._db.execute(
                    "SELECT 1 FROM snapshots WHERE timestamp >= ? AND timestamp < ? LIMIT 1",
                    (self._iso(start), self._iso(end))).fetchone()
                if row:
                    return False
            keys = ["timestamp"] + METRIC_KEYS
            vals = [self._iso(doc["timestamp"])] + [doc[k] for k in METRIC_KEYS]
            self._db.execute(
                f"INSERT OR REPLACE INTO snapshots ({', '.join(chr(34) + k + chr(34) for k in keys)}) "
                f"VALUES ({', '.join('?' * len(keys))})", vals)
            self._db.commit()
        return True

    def query(self, metric: str, days: int | None) -> list[tuple[datetime, float]]:
        if metric not in METRIC_KEYS:
            raise ValueError(metric)
        sql = f'SELECT timestamp, "{metric}" FROM snapshots'
        args: tuple = ()
        if days:
            sql += " WHERE timestamp >= ?"
            args = (self._iso(datetime.now(timezone.utc) - timedelta(days=days)),)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        args += (MAX_POINTS,)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        out = [(datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc), v)
               for t, v in rows if v is not None]
        return list(reversed(out))

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM snapshots")
            self._db.commit()

    def prune(self, retention_days: int) -> None:
        if retention_days > 0:
            cutoff = self._iso(datetime.now(timezone.utc) - timedelta(days=retention_days))
            with self._lock:
                self._db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,))
                self._db.commit()


class MongoHistory:
    name = "MongoDB"

    def __init__(self, uri: str, database: str = "moonphase"):
        import pymongo  # optional dependency

        self._client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
        self._client.admin.command("ping")
        db = self._client.get_default_database(default=database)
        self._col = db["snapshots"]
        self._col.create_index("timestamp")

    def save(self, s: astro.Snapshot, ts: datetime | None = None, dedupe: bool = True) -> bool:
        doc = snapshot_to_doc(s, ts)
        if dedupe:
            start, end = half_day_window(doc["timestamp"])
            if self._col.find_one({"timestamp": {"$gte": start, "$lt": end}}, {"_id": 1}):
                return False
        self._col.insert_one(doc)
        return True

    def query(self, metric: str, days: int | None) -> list[tuple[datetime, float]]:
        if metric not in METRIC_KEYS:
            raise ValueError(metric)
        flt: dict = {metric: {"$exists": True}}
        if days:
            flt["timestamp"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}
        cur = self._col.find(flt, {"timestamp": 1, metric: 1}).sort("timestamp", -1).limit(MAX_POINTS)
        out = [(d["timestamp"], float(d[metric])) for d in cur]
        return list(reversed(out))

    def count(self) -> int:
        return self._col.estimated_document_count()

    def clear(self) -> None:
        self._col.delete_many({})

    def prune(self, retention_days: int) -> None:
        if retention_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            self._col.delete_many({"timestamp": {"$lt": cutoff}})


def backfill(store, days: int, latitude: float, longitude: float) -> int:
    """Populate past snapshots (00:01 and 12:01 UTC) with deterministic values.
    LEO and aurora values cannot be reconstructed, so they are stored as 0."""
    days = max(1, min(365, days))
    now = datetime.now(timezone.utc)
    added = 0
    for d in range(days, 0, -1):
        day = (now - timedelta(days=d)).replace(minute=1, second=0, microsecond=0)
        for hour in (0, 12):
            ts = day.replace(hour=hour)
            s = astro.compute(ts, latitude, longitude)
            for k in ("issAltitudeKm", "tiangongAltitudeKm", "hubbleAltitudeKm", "auroraKpIndex",
                      "starlinkSatelliteCount", "kuiperSatelliteCount", "totalSatellitesInOrbit",
                      "issCrew", "totalPeopleInSpace"):
                setattr(s, k, 0)
            if store.save(s, ts, dedupe=True):
                added += 1
    return added
