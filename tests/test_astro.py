"""Unit tests for the calculation engine (no GTK or network needed).

Run with:  python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from moonphase import astro, fetchers, history  # noqa: E402

UTC = timezone.utc


class JulianDay(unittest.TestCase):
    def test_j2000(self):
        self.assertEqual(astro.julian_day_number(1, 1, 2000), 2451545)
        self.assertAlmostEqual(astro.days_since_j2000(datetime(2000, 1, 1, 12, tzinfo=UTC)), 0.0)


class Moon(unittest.TestCase):
    def test_known_full_and_new_moons(self):
        # Full moon 2024-04-23 23:49 UTC; new moon 2024-04-08 18:21 UTC (total eclipse)
        full = astro.MoonPhase.at(datetime(2024, 4, 23, 23, 49, tzinfo=UTC))
        self.assertEqual(full.name, "Full Moon")
        self.assertGreaterEqual(full.illumination_percent, 98)
        new = astro.MoonPhase.at(datetime(2024, 4, 8, 18, 21, tzinfo=UTC))
        self.assertEqual(new.name, "New Moon")
        self.assertLessEqual(new.illumination_percent, 2)

    def test_phase_cycle_and_ascii(self):
        names = set()
        for d in range(30):
            mp = astro.MoonPhase.at(datetime(2025, 1, 1 + d if d < 31 else 1, tzinfo=UTC))
            names.add(mp.name)
            self.assertEqual(len(mp.ascii_art), 6)
            self.assertTrue(0 <= mp.days_until_full_moon <= 30)
        self.assertEqual(len(names), 8)


class Calendar(unittest.TestCase):
    def test_solstice_days(self):
        self.assertEqual(astro.days_until(date(2026, 6, 11), 6, 21), 10)
        self.assertEqual(astro.days_until(date(2026, 12, 1), 12, 21), 20)
        self.assertEqual(astro.days_until(date(2026, 6, 21), 6, 21), 365)  # rolls to next year


class Earth(unittest.TestCase):
    def test_tilt(self):
        self.assertAlmostEqual(astro.axial_tilt_deg(datetime(2000, 1, 1, 12, tzinfo=UTC)), 23.439291, places=3)

    def test_daylight(self):
        self.assertEqual(astro.day_length_hours(date(2026, 12, 21), 89.0), 0.0)
        self.assertEqual(astro.day_length_hours(date(2026, 6, 21), 89.0), 24.0)
        self.assertTrue(16 < astro.day_length_hours(date(2026, 6, 21), 51.4769) < 18)
        self.assertTrue(7 < astro.day_length_hours(date(2026, 12, 21), 51.4769) < 9)
        lo, hi = astro.day_length_min_max(51.4769)
        self.assertTrue(0 < lo < 12 < hi < 24)

    def test_speed_range(self):
        self.assertTrue(29.2 < astro.earth_speed_km_s(1.0167) < 29.4)
        self.assertTrue(30.2 < astro.earth_speed_km_s(0.9833) < 30.4)


class Distances(unittest.TestCase):
    def test_ranges(self):
        now = datetime(2026, 11, 21, 12, tzinfo=UTC)
        self.assertTrue(0.983 < astro.sun_distance_au(now) < 1.017)
        self.assertTrue(363_000 < astro.moon_distance_km(now) < 406_000)
        self.assertTrue(0.3 < astro.MARS.geocentric_au(now) < 2.7)
        self.assertEqual(astro.format_light_time(1.0), "8m 19s")


class Fetchers(unittest.TestCase):
    def test_parse_kp(self):
        self.assertEqual(fetchers.parse_latest_kp([{"estimated_kp": 1.0}, {"estimated_kp": 2.33}]), 2.33)
        self.assertEqual(fetchers.parse_latest_kp([]), -1.0)
        self.assertEqual(fetchers.parse_latest_kp(None), -1.0)

    def test_iss_altitude(self):
        line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50125391563537"
        self.assertTrue(400 < fetchers.altitude_from_tle_line2(line2) < 440)

    def test_people(self):
        p = fetchers.parse_people({"number": 3, "people": [
            {"spacecraft": "ISS", "iss": True}, {"spacecraft": "ISS", "iss": True},
            {"spacecraft": "Tiangong", "iss": False}]})
        self.assertEqual((p.total, p.iss_crew), (3, 2))
        self.assertEqual(p.crafts, {"ISS ★": 2, "Tiangong": 1})


class History(unittest.TestCase):
    def test_sqlite_dedupe_query_backfill(self):
        with tempfile.TemporaryDirectory() as d:
            store = history.SqliteHistory(os.path.join(d, "h.sqlite3"))
            s = astro.compute(datetime(2026, 11, 21, 1, tzinfo=UTC))
            self.assertTrue(store.save(s))
            self.assertFalse(store.save(astro.compute(datetime(2026, 11, 21, 5, tzinfo=UTC))))
            self.assertTrue(store.save(astro.compute(datetime(2026, 11, 21, 13, tzinfo=UTC))))
            self.assertEqual(len(store.query("moonIlluminationPercent", None)), 2)
            added = history.backfill(store, 3, 51.5, 0.0)
            self.assertGreaterEqual(added, 4)
            csv_text = history.to_csv("sunDistanceAu", store.query("sunDistanceAu", None))
            self.assertTrue(csv_text.startswith("timestamp,sunDistanceAu"))
            store.clear()
            self.assertEqual(store.count(), 0)


if __name__ == "__main__":
    unittest.main()
