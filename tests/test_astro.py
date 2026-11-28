"""Unit tests for the calculation engine (no GTK or network needed).

Run with:  python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from moonphase import astro, fetchers, history, themes  # noqa: E402

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
        lo, hi = astro.MOON_DISTANCE_RANGE_KM
        self.assertTrue(lo < astro.moon_distance_km(now) < hi)
        self.assertTrue(0.3 < astro.MARS.geocentric_au(now) < 2.7)
        self.assertEqual(astro.format_light_time(1.0), "8m 19s")


# JPL Horizons (https://ssd.jpl.nasa.gov/horizons/), observer table, geocentric
# (CENTER=500@399): r = distance from Sun (AU), delta = distance from Earth (AU),
# illuminated %. Planet dates span both element tables (Table 1: 1800–2050,
# Table 2: 2075); spacecraft dates span 2020–2035 around the 2026 state vectors.
# These are the same reference values the MoonPhase web app is tested against.
HORIZONS = [
    ("Moon", "2000-01-01T12:00:00", 0.981872991987, 0.00268998925442, 23.00638),
    ("Moon", "2015-07-14T12:00:00", 1.014093364195, 0.00258893367913, 2.80715),
    ("Moon", "2026-11-27T23:28:00", 0.988335675755, 0.00242629346672, 84.11571),
    ("Moon", "2040-06-01T00:00:00", 1.014622416956, 0.00247864868104, 62.3655),
    ("Moon", "2075-03-15T00:00:00", 0.991853156389, 0.00251286916114, 4.01549),
    ("Sun", "2000-01-01T12:00:00", 0.0, 0.98332762652701, 100.0),
    ("Sun", "2015-07-14T12:00:00", 0.0, 1.01653722930979, 100.0),
    ("Sun", "2026-11-27T23:28:00", 0.0, 0.98668159281108, 100.0),
    ("Sun", "2040-06-01T00:00:00", 0.0, 1.01401203003873, 100.0),
    ("Sun", "2075-03-15T00:00:00", 0.0, 0.99416461269571, 100.0),
    ("Mercury", "2000-01-01T12:00:00", 0.466468841931, 1.41546946904999, 97.48652),
    ("Mercury", "2015-07-14T12:00:00", 0.309190162025, 1.24239600766868, 89.42002),
    ("Mercury", "2026-11-27T23:28:00", 0.378519674543, 1.16083625301682, 79.42448),
    ("Mercury", "2040-06-01T00:00:00", 0.420104868102, 0.79730382988487, 33.88215),
    ("Mercury", "2075-03-15T00:00:00", 0.419357052028, 1.34002851911789, 93.73588),
    ("Venus", "2000-01-01T12:00:00", 0.720212286809, 1.13757924245212, 75.80544),
    ("Venus", "2015-07-14T12:00:00", 0.727063246288, 0.41812775457853, 22.87572),
    ("Venus", "2026-11-27T23:28:00", 0.719887281313, 0.40643257821581, 25.20597),
    ("Venus", "2040-06-01T00:00:00", 0.720916066211, 1.73489962490728, 99.99888),
    ("Venus", "2075-03-15T00:00:00", 0.72679128062, 1.27090944065987, 81.25808),
    ("Mars", "2000-01-01T12:00:00", 1.391202576247, 1.84968786270204, 92.65057),
    ("Mars", "2015-07-14T12:00:00", 1.588259587485, 2.58663164091405, 99.77691),
    ("Mars", "2026-11-27T23:28:00", 1.621036289394, 1.20386500513761, 89.75553),
    ("Mars", "2040-06-01T00:00:00", 1.662191499153, 1.82338768718413, 91.73498),
    ("Mars", "2075-03-15T00:00:00", 1.385108951973, 2.37867167249401, 99.99085),
    ("Jupiter", "2000-01-01T12:00:00", 4.965377642079, 4.62117524331177, 99.07602),
    ("Jupiter", "2015-07-14T12:00:00", 5.377225371039, 6.20754388955521, 99.74263),
    ("Jupiter", "2026-11-27T23:28:00", 5.325365759933, 5.07976560617289, 99.15565),
    ("Jupiter", "2040-06-01T00:00:00", 5.446108558008, 5.16037454936609, 99.15835),
    ("Jupiter", "2075-03-15T00:00:00", 5.407321443042, 4.44813980830185, 99.92909),
    ("Saturn", "2000-01-01T12:00:00", 9.183858256403, 8.65279676096631, 99.78468),
    ("Saturn", "2015-07-14T12:00:00", 9.986643162591, 9.34477940561514, 99.83367),
    ("Saturn", "2026-11-27T23:28:00", 9.417060471932, 8.85272387588537, 99.8037),
    ("Saturn", "2040-06-01T00:00:00", 9.590117268223, 9.1311306095071, 99.76675),
    ("Saturn", "2075-03-15T00:00:00", 10.02644726861, 9.87098068694784, 99.75629),
    ("Uranus", "2000-01-01T12:00:00", 19.9240150244, 20.727171130885, 99.98055),
    ("Uranus", "2015-07-14T12:00:00", 19.99032142132, 19.9412638083133, 99.93529),
    ("Uranus", "2026-11-27T23:28:00", 19.43076834045, 18.4447497346863, 99.99991),
    ("Uranus", "2040-06-01T00:00:00", 18.56896819234, 19.2113531895362, 99.95691),
    ("Uranus", "2075-03-15T00:00:00", 19.45569681685, 19.7716814268018, 99.9422),
    ("Neptune", "2000-01-01T12:00:00", 30.12058818217, 31.024498221734, 99.996),
    ("Neptune", "2015-07-14T12:00:00", 29.96382363343, 29.2715099470401, 99.98418),
    ("Neptune", "2026-11-27T23:28:00", 29.87667954767, 29.4320638256214, 99.97797),
    ("Neptune", "2040-06-01T00:00:00", 29.81042658002, 30.6197572090097, 99.98976),
    ("Neptune", "2075-03-15T00:00:00", 29.96440392234, 29.5329657015062, 99.97736),
    ("Pluto", "2000-01-01T12:00:00", 30.22318615617, 31.0643527312227, 99.99308),
    ("Pluto", "2015-07-14T12:00:00", 32.90832829897, 31.9012331276215, 99.99955),
    ("Pluto", "2026-11-27T23:28:00", 35.65038403251, 36.1654464971515, 99.98629),
    ("Pluto", "2040-06-01T00:00:00", 39.10115251431, 38.8470547272902, 99.98412),
    ("Pluto", "2075-03-15T00:00:00", 46.34361095354, 47.2697102650016, 99.99851),
    ("Voyager 1", "2020-01-01T00:00:00", 147.8673484958, 148.605563056091, 99.99952),
    ("Voyager 1", "2024-01-01T00:00:00", 162.1186258501, 162.859045233514, 99.9996),
    ("Voyager 1", "2026-11-27T23:28:00", 172.4726207521, 173.264340821595, 99.99971),
    ("Voyager 1", "2030-01-01T00:00:00", 183.4854610277, 184.225761621311, 99.99969),
    ("Voyager 1", "2035-01-01T00:00:00", 201.2506300484, 201.994116220434, 99.99975),
    ("Voyager 2", "2020-01-01T00:00:00", 122.6759061005, 123.45125333803, 99.9994),
    ("Voyager 2", "2024-01-01T00:00:00", 135.3586174591, 136.122235415381, 99.99948),
    ("Voyager 2", "2026-11-27T23:28:00", 144.5821025366, 145.126611289025, 99.9992),
    ("Voyager 2", "2030-01-01T00:00:00", 154.4049823751, 155.15561907585, 99.99958),
    ("Voyager 2", "2035-01-01T00:00:00", 170.2696843896, 171.009897717743, 99.99964),
    ("New Horizons", "2020-01-01T00:00:00", 46.21582350257, 47.1916615967235, 99.99983),
    ("New Horizons", "2024-01-01T00:00:00", 57.83054644178, 58.8034435272464, 99.99985),
    ("New Horizons", "2026-11-27T23:28:00", 66.16268960782, 66.8851603769669, 99.99745),
    ("New Horizons", "2030-01-01T00:00:00", 74.96070702767, 75.9318217327052, 99.9999),
    ("New Horizons", "2035-01-01T00:00:00", 89.03964718231, 90.0081078701794, 99.99991),
]

PLANET_HELIO_REL = 0.002   # 0.2 %
PLANET_GEO_REL = 0.004     # 0.4 %
CRAFT_AU = 0.03
MOON_KM = 1_200
MOON_ILLUM_PCT = 1.0
SUN_AU = 0.0002

PLANETS = {p.name: p for p in (astro.MERCURY, astro.VENUS, astro.MARS, astro.JUPITER, astro.SATURN,
                               astro.URANUS, astro.NEPTUNE, astro.PLUTO)}
CRAFT = {c.name: c for c in (astro.VOYAGER_1, astro.VOYAGER_2, astro.NEW_HORIZONS)}


class EphemerisAccuracy(unittest.TestCase):
    def test_matches_horizons(self):
        failures = []

        def check(body, when, what, app, ref, tol):
            if abs(app - ref) > tol:
                failures.append(f"{body} {when} {what}: app {app:.6f} vs Horizons {ref:.6f} (tolerance {tol:.6f})")

        for body, when, r, delta, illum in HORIZONS:
            t = datetime.fromisoformat(when).replace(tzinfo=UTC)
            if body == "Sun":
                check(body, when, "distance", astro.sun_distance_au(t), delta, SUN_AU)
            elif body == "Moon":
                check(body, when, "km", astro.moon_distance_km(t), delta * astro.KM_PER_AU, MOON_KM)
                pos = astro.moon_sun_position(astro.julian_date(t))
                check(body, when, "illum %", pos.illuminated_fraction * 100, illum, MOON_ILLUM_PCT)
            elif body in CRAFT:
                craft = CRAFT[body]
                check(body, when, "from Sun", craft.heliocentric_au(t), r, CRAFT_AU)
                check(body, when, "from Earth", craft.from_earth_au(t), delta, CRAFT_AU)
            else:
                planet = PLANETS[body]
                check(body, when, "from Sun", planet.heliocentric_au(t), r, r * PLANET_HELIO_REL)
                check(body, when, "from Earth", planet.geocentric_au(t), delta, delta * PLANET_GEO_REL)
        self.assertEqual(failures, [], "\n".join(failures))

    def test_new_and_full_moon_times_match_horizons(self):
        # Moon − Sun ecliptic longitude 0° / 180° from Horizons quantity 31 at 2-minute steps.
        mp = astro.MoonPhase.at(datetime(2026, 11, 27, 23, 28, tzinfo=UTC))
        self.assertLessEqual(abs((mp.next_new_moon - datetime(2026, 12, 9, 0, 52, tzinfo=UTC)).total_seconds()), 15 * 60)
        self.assertLessEqual(abs((mp.next_full_moon - datetime(2026, 12, 24, 1, 28, tzinfo=UTC)).total_seconds()), 15 * 60)
        self.assertEqual(mp.name, "Waning Gibbous")
        self.assertLessEqual(abs(mp.illumination_percent - 84), 1)

    def test_probes_before_launch_are_zero(self):
        t = datetime(1970, 1, 1, tzinfo=UTC)
        self.assertEqual(astro.VOYAGER_1.heliocentric_au(t), 0.0)
        self.assertEqual(astro.NEW_HORIZONS.from_earth_au(t), 0.0)


class SunriseSunset(unittest.TestCase):
    """Almanac times for the Royal Observatory, Greenwich (official sunrise incl. refraction)."""

    LAT, LON = 51.4769, 0.0

    def assert_near(self, expected: str, actual: str, minutes: int = 2):
        def mins(hhmm):
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        self.assertLessEqual(abs(mins(expected) - mins(actual)), minutes, f"expected ~{expected}, got {actual}")

    def test_solstices(self):
        rise, sett = astro.sunrise_sunset_utc(date(2026, 6, 21), self.LAT, self.LON)
        self.assert_near("03:43", rise)
        self.assert_near("20:21", sett)
        rise, sett = astro.sunrise_sunset_utc(date(2026, 12, 21), self.LAT, self.LON)
        self.assert_near("08:04", rise)
        self.assert_near("15:53", sett)

    def test_western_longitude_is_later(self):
        a, _ = astro.sunrise_sunset_utc(date(2026, 3, 20), self.LAT, 0.0)
        b, _ = astro.sunrise_sunset_utc(date(2026, 3, 20), self.LAT, -15.0)
        self.assert_near(f"{int(a[:2]) + 1:02d}:{a[3:]}", b)

    def test_polar(self):
        self.assertEqual(astro.sunrise_sunset_utc(date(2026, 12, 21), 89.0, 0.0)[0], "Polar Night")
        self.assertEqual(astro.sunrise_sunset_utc(date(2026, 6, 21), 89.0, 0.0)[1], "Midnight Sun")

    def test_day_length_matches_almanac(self):
        tol = 3 / 60
        self.assertAlmostEqual(astro.day_length_hours(date(2026, 6, 21), self.LAT), 16 + 38 / 60, delta=tol)
        self.assertAlmostEqual(astro.day_length_hours(date(2026, 12, 21), self.LAT), 7 + 49 / 60, delta=tol)

    def test_same_date_differs_between_years(self):
        a = astro.day_length_hours(date(2025, 3, 1), self.LAT)
        b = astro.day_length_hours(date(2027, 3, 1), self.LAT)
        self.assertNotAlmostEqual(a, b, delta=1 / 3600)


class Fetchers(unittest.TestCase):
    def test_parse_kp(self):
        self.assertEqual(fetchers.parse_latest_kp([{"estimated_kp": 1.0}, {"estimated_kp": 2.33}]), 2.33)
        self.assertEqual(fetchers.parse_latest_kp([]), -1.0)
        self.assertEqual(fetchers.parse_latest_kp(None), -1.0)

    def test_iss_altitude(self):
        line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50125391563537"
        self.assertTrue(400 < fetchers.altitude_from_tle_line2(line2) < 440)

    def test_parse_jwst(self):
        body = {"result": "header\n$$SOE\n 2026-Nov-27 23:28, , ,  0.01136300827198,  0.0069837,\n$$EOE\nfooter"}
        self.assertAlmostEqual(fetchers.parse_jwst_km(body), 0.01136300827198 * astro.KM_PER_AU, places=3)
        self.assertEqual(fetchers.parse_jwst_km({"result": "no ephemeris"}), -1.0)
        self.assertEqual(fetchers.parse_jwst_km(None), -1.0)
        self.assertIn("COMMAND=%27-170%27", fetchers.jwst_url(datetime(2026, 11, 27, 23, 28, tzinfo=UTC)))

    def test_people(self):
        p = fetchers.parse_people({"number": 3, "people": [
            {"spacecraft": "ISS", "iss": True}, {"spacecraft": "ISS", "iss": True},
            {"spacecraft": "Tiangong", "iss": False}]})
        self.assertEqual((p.total, p.iss_crew), (3, 2))
        self.assertEqual(p.crafts, {"ISS ★": 2, "Tiangong": 1})


class Themes(unittest.TestCase):
    def test_choices(self):
        keys = [k for k, _ in themes.CHOICES]
        self.assertEqual(keys[0], themes.SYSTEM)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(themes.THEMES), 10)
        self.assertIsNone(themes.get(themes.SYSTEM))
        self.assertIsNone(themes.get("no-such-theme"))

    def test_no_organisation_names(self):
        banned = ("spacex", "nasa", "blue origin", "rocket lab", "ula", "arianespace", "relativity", "firefly")
        for t in themes.THEMES:
            for word in banned:
                self.assertNotIn(word, f"{t.key} {t.label}".lower().split() if word == "ula" else f"{t.key} {t.label}".lower())

    def test_css_and_contrast(self):
        for t in themes.THEMES:
            css = themes.css(t)
            self.assertIn(f"@define-color window_bg_color {t.bg};", css)
            self.assertEqual(css.count("{") , css.count("}"))
        self.assertEqual(themes.on_colour("#ffffff"), "#000000")
        self.assertEqual(themes.on_colour("#0b3d91"), "#ffffff")
        self.assertEqual(themes.rgb("#ff8000"), (1.0, 128 / 255, 0.0))


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
