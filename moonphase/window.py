"""Main application window."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import astro, awtrix, fetchers, history, themes, widgets  # noqa: E402
from .config import DATA_DIR, Settings  # noqa: E402
from .widgets import HistoryChart, MoonView, PhaseIcon  # noqa: E402

log = logging.getLogger(__name__)

UNITS = [("au", "AU"), ("km", "km"), ("mi", "mi")]
RANGES = [(7, "7 days"), (14, "14 days"), (30, "30 days"), (90, "90 days"), (365, "365 days"), (None, "All")]

CSS = b"""
.mp-card { padding: 14px 16px; }
.mp-card-title { font-weight: 700; font-size: 1.05em; }
.mp-key { opacity: 0.75; }
.mp-value { font-feature-settings: "tnum"; }
.mp-hero { font-size: 3em; font-weight: 800; font-feature-settings: "tnum"; }
.mp-hero-label { font-size: 0.75em; letter-spacing: 0.12em; opacity: 0.7; }
.mp-big { font-size: 1.35em; font-weight: 700; }
.mp-ascii { font-family: monospace; font-size: 1.1em; }
.mp-storm { color: @error_color; font-weight: 700; }
.mp-note { font-size: 0.85em; opacity: 0.7; }
progressbar.mp-cycle trough, progressbar.mp-cycle progress { min-height: 6px; }
"""

# Lunar-cycle strip, New → Full → New, as phase fractions.
PHASE_STRIP = [i / 8 for i in range(8)]
PHASE_FRACTION_BY_NAME = {"New Moon": 0.0, "Waxing Crescent": 0.125, "First Quarter": 0.25,
                          "Waxing Gibbous": 0.375, "Full Moon": 0.5, "Waning Gibbous": 0.625,
                          "Last Quarter": 0.75, "Waning Crescent": 0.875}


def _dist_from_au(au: float, units: str, decimals: int = 3) -> str:
    """Solar System or Deep Space distance stored in AU, in the chosen units.
    Planets get 3 decimals in AU, deep-space probes 1."""
    if au <= 0:
        return "—"
    if units == "km":
        return f"{au * astro.KM_PER_AU:,.0f} km"
    if units == "mi":
        return f"{au * astro.KM_PER_AU / astro.KM_PER_MILE:,.0f} mi"
    return f"{au:.{decimals}f} AU"


def _near_km(km: float, units: str) -> str:
    """Near-Earth distance stored in km (Moon, orbit altitudes, JWST). Never shown
    in AU, where 0.000003 AU means nothing: the AU setting falls back to km."""
    if km is None or km <= 0:
        return "—"
    if units == "mi":
        return f"{km / astro.KM_PER_MILE:,.0f} mi"
    return f"{km:,.0f} km"


def _moon_date(when, now: datetime | None = None) -> str:
    """'24 Dec · 26 days', 'Tomorrow · 25 Dec' or 'Tonight'."""
    if when is None:
        return "—"
    now = now or datetime.now(timezone.utc)
    days = round((when - now).total_seconds() / 86400)
    local = when.astimezone()
    label = f"{local.day} {local.strftime('%b')}"
    if days <= 0:
        return "Tonight"
    if days == 1:
        return f"Tomorrow · {label}"
    return f"{label} · {days} days"


def _num(v, fmt="{:,}") -> str:
    return "—" if v is None or v < 0 else fmt.format(v)


def _count(v) -> str:
    return f"{v:,}" if v is not None and v > 0 else "—"


class Card(Gtk.Box):
    def __init__(self, title: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.add_css_class("mp-card")
        self.set_valign(Gtk.Align.START)
        self.header = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label=title, xalign=0, hexpand=True)
        lbl.add_css_class("mp-card-title")
        self.header.append(lbl)
        self.append(self.header)
        self.grid = Gtk.Grid(column_spacing=16, row_spacing=6)
        self._rows: dict[str, tuple[Gtk.Label, ...]] = {}
        self._n = 0

    def use_grid(self):
        self.append(self.grid)

    def row(self, key: str, *cols: str, header: bool = False) -> tuple[Gtk.Label, ...]:
        labels = []
        for i, text in enumerate(cols):
            lab = Gtk.Label(label=text, xalign=0 if i == 0 else 1, hexpand=(i == 0))
            lab.add_css_class("mp-key" if i == 0 or header else "mp-value")
            if header:
                lab.add_css_class("caption-heading")
            lab.set_selectable(i > 0 and not header)
            self.grid.attach(lab, i, self._n, 1, 1)
            labels.append(lab)
        self._n += 1
        self._rows[key] = tuple(labels)
        return tuple(labels)

    def set(self, key: str, *values: str):
        labels = self._rows[key]
        for lab, v in zip(labels[1:], values):
            lab.set_label(v)

    def clear_rows(self):
        child = self.grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        self._rows.clear()
        self._n = 0


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Orbitly")
        self.set_default_size(1180, 860)
        self.app = app
        self.settings = Settings.load()
        self.live = fetchers.LiveData()
        self.snapshot: astro.Snapshot | None = None
        self.store = None
        self._busy = False
        self._last_saved_window = None
        self._notified: dict[str, float] = {}

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(self.get_display(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Theme palette, above the base styles so it can recolour them.
        self.theme_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(self.get_display(), self.theme_provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(self._build_header())
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self._build_cards())
        view.set_content(scroller)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self._apply_theme(self.settings.theme)
        self._open_history()
        self._recompute_local()
        self.refresh()
        GLib.timeout_add_seconds(60, self._on_minute)

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self) -> Adw.HeaderBar:
        hb = Adw.HeaderBar()
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh now (F5)")
        self.refresh_btn.connect("clicked", lambda *_: self.refresh(force=True))
        hb.pack_start(self.refresh_btn)
        self.spinner = Gtk.Spinner()
        hb.pack_start(self.spinner)

        self.units_dd = Gtk.DropDown.new_from_strings([u[1] for u in UNITS])
        self.units_dd.set_tooltip_text("Units for Solar System and Deep Space distances "
                                       "(near-Earth values use km or mi)")
        self.units_dd.set_selected([u[0] for u in UNITS].index(self.settings.units)
                                   if self.settings.units in dict(UNITS) else 0)
        self.units_dd.connect("notify::selected", self._on_units)

        menu = Gio.Menu()
        theme_menu = Gio.Menu()
        for key, label in themes.CHOICES:
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("win.theme", GLib.Variant.new_string(key))
            theme_menu.append_item(item)
        menu.append_submenu("Theme", theme_menu)
        menu.append("Preferences", "win.preferences")
        hist = Gio.Menu()
        hist.append("Populate Past…", "win.populate")
        hist.append("Export CSV…", "win.export")
        hist.append("Reset History…", "win.reset")
        menu.append_section(None, hist)
        menu.append("Keyboard Shortcuts", "win.show-help-overlay")
        menu.append("About Orbitly", "app.about")
        mb = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Main menu")
        hb.pack_end(mb)
        hb.pack_end(self.units_dd)
        self.status_lbl = Gtk.Label(css_classes=["dim-label", "caption"])
        hb.pack_end(self.status_lbl)

        current = self.settings.theme if self.settings.theme in dict(themes.CHOICES) else themes.SYSTEM
        theme_act = Gio.SimpleAction.new_stateful("theme", GLib.VariantType.new("s"),
                                                  GLib.Variant.new_string(current))
        theme_act.connect("change-state", self._on_theme)
        self.add_action(theme_act)

        for name, cb in (("preferences", self._show_prefs), ("populate", self._populate),
                         ("export", self._export_csv), ("reset", self._reset_history),
                         ("refresh", lambda *_: self.refresh(force=True))):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
        return hb

    # ── Cards ────────────────────────────────────────────────────────────────

    def _build_cards(self) -> Gtk.Widget:
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                           column_spacing=14, row_spacing=14, max_children_per_line=3,
                           min_children_per_line=1, valign=Gtk.Align.START)
        for side in ("top", "bottom", "start", "end"):
            getattr(flow, f"set_margin_{side}")(16)

        # Moon (hero)
        self.moon_card = Card("🌙 Moon Phase")
        self.moon_style = Gtk.ToggleButton(label="ASCII", tooltip_text="Show ASCII art instead of the drawn moon")
        self.moon_style.set_active(self.settings.moon_style == "ascii")
        self.moon_style.add_css_class("flat")
        self.moon_style.connect("toggled", self._on_moon_style)
        self.moon_card.header.append(self.moon_style)
        self.moon_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.moon_view = MoonView()
        self.ascii_lbl = Gtk.Label(css_classes=["mp-ascii"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.moon_stack.add_named(self.moon_view, "drawn")
        self.moon_stack.add_named(self.ascii_lbl, "ascii")
        self.moon_stack.set_visible_child_name(self.settings.moon_style)
        self.moon_card.append(self.moon_stack)
        self.illum_lbl = Gtk.Label(css_classes=["mp-hero", "mp-moon"])
        self.moon_card.append(self.illum_lbl)
        self.moon_card.append(Gtk.Label(label="ILLUMINATED", css_classes=["mp-hero-label"]))
        self.phase_lbl = Gtk.Label(css_classes=["mp-big", "mp-moon"])
        self.moon_card.append(self.phase_lbl)

        cycle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=4)
        cycle_head = Gtk.Box()
        cycle_head.append(Gtk.Label(label="Lunar cycle", xalign=0, hexpand=True, css_classes=["mp-key"]))
        self.cycle_day_lbl = Gtk.Label(xalign=1, css_classes=["mp-value"])
        cycle_head.append(self.cycle_day_lbl)
        cycle.append(cycle_head)
        self.cycle_bar = Gtk.ProgressBar(css_classes=["mp-cycle"])
        cycle.append(self.cycle_bar)
        strip = Gtk.Box(homogeneous=True)
        self.phase_icons = [PhaseIcon(p) for p in PHASE_STRIP]
        for icon in self.phase_icons:
            icon.set_halign(Gtk.Align.CENTER)
            strip.append(icon)
        cycle.append(strip)
        self.moon_card.append(cycle)
        for k in ("Next new moon", "Next full moon", "Distance"):
            self.moon_card.row(k, k, "")
        self.moon_card.use_grid()

        # Solar system (all distances from the Sun)
        self.sol_card = Card("☀️ Solar System")
        self.sol_card.row("_h", "Sun →", "Distance", "Light travel", header=True)
        for p in ("Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
            self.sol_card.row(p, p, "", "")
        self.sol_card.use_grid()

        # Earth
        self.earth_card = Card("🌍 Earth")
        for k in ("Orbital Speed", "Speed", "Daylight Hours", "Sunrise (UTC~)", "Sunset (UTC~)",
                  "Axial Tilt", "Aurora Kp Index", "Location"):
            self.earth_card.row(k, k, "")
        self.earth_card.use_grid()

        # Near Earth: stations, constellations and people in space (rows rebuilt on render)
        self.near_card = Card("🛰️ Near Earth")
        self.near_card.use_grid()
        self.crew_note = Gtk.Label(xalign=0, css_classes=["mp-note"], visible=False)
        self.near_card.append(self.crew_note)

        # Deep space (distances from Earth)
        self.deep_card = Card("🚀 Deep Space")
        for k in ("James Webb (L2)", "Voyager 1", "Voyager 2", "New Horizons"):
            self.deep_card.row(k, k, "")
        self.deep_card.use_grid()

        # Events
        self.events_card = Card("📅 Upcoming Events")
        self.events_card.use_grid()

        # History
        self.hist_card = Card("📊 Historical Data")
        controls = Gtk.Box(spacing=8)
        self._metric_keys = [m[0] for m in history.METRICS]
        self.metric_dd = Gtk.DropDown.new_from_strings([f"{m[2]} · {m[1]}" for m in history.METRICS])
        self.metric_dd.set_hexpand(True)
        self.metric_dd.set_enable_search(True)
        self.range_dd = Gtk.DropDown.new_from_strings([r[1] for r in RANGES])
        self.range_dd.set_selected(2)
        csv_btn = Gtk.Button(label="↓ CSV", tooltip_text="Export this metric as CSV")
        csv_btn.connect("clicked", self._export_csv)
        for w in (self.metric_dd, self.range_dd, csv_btn):
            controls.append(w)
        self.metric_dd.connect("notify::selected", lambda *_: self._load_chart())
        self.range_dd.connect("notify::selected", lambda *_: self._load_chart())
        self.hist_card.append(controls)
        self.chart = HistoryChart()
        self.hist_card.append(self.chart)
        self.hist_status = Gtk.Label(xalign=0, css_classes=["dim-label", "caption"])
        self.hist_card.append(self.hist_status)

        for c in (self.moon_card, self.sol_card, self.earth_card,
                  self.near_card, self.deep_card, self.events_card):
            c.set_size_request(340, -1)
            flow.append(c)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(flow)
        self.hist_card.set_margin_start(16)
        self.hist_card.set_margin_end(16)
        self.hist_card.set_margin_bottom(16)
        outer.append(self.hist_card)
        return outer

    # ── Data flow ────────────────────────────────────────────────────────────

    def _recompute_local(self):
        """Fast deterministic recompute, keeping last live values."""
        s = astro.compute(latitude=self.settings.latitude, longitude=self.settings.longitude)
        if self.snapshot:
            for k in ("auroraKpIndex", "jamesWebbDistanceKm", "issAltitudeKm", "tiangongAltitudeKm", "hubbleAltitudeKm",
                      "starlinkSatelliteCount", "kuiperSatelliteCount", "totalSatellitesInOrbit",
                      "issCrew", "totalPeopleInSpace", "craftOccupancy"):
                setattr(s, k, getattr(self.snapshot, k))
        self.snapshot = s
        self._render()

    def refresh(self, force: bool = False):
        if self._busy:
            self.toast("A refresh is already running")
            return
        self._busy = True
        self.spinner.start()
        self.refresh_btn.set_sensitive(False)
        if force:
            self.live.clear()
        settings = self.settings

        def work():
            s = astro.compute(latitude=settings.latitude, longitude=settings.longitude)
            err = None
            try:
                fetchers.apply_live(s, self.live)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
            pushed = None
            if settings.awtrix_enabled and settings.awtrix_host:
                pushed = awtrix.push_all(settings.awtrix_host, s)
            GLib.idle_add(self._refresh_done, s, err, pushed)

        threading.Thread(target=work, daemon=True).start()

    def _refresh_done(self, s, err, pushed):
        self._busy = False
        self.spinner.stop()
        self.refresh_btn.set_sensitive(True)
        self.snapshot = s
        self._render()
        self._save_history(s)
        self._maybe_notify(s)
        if err:
            self.toast(f"Live data error: {err}")
        if pushed is not None:
            self.toast(f"Pushed {pushed} metrics to Awtrix" if pushed else "Awtrix device unreachable")
        return GLib.SOURCE_REMOVE

    def _on_minute(self):
        if not self._busy:
            self._recompute_local()
            now = datetime.now(timezone.utc)
            # Live fetch twice a day at 00:01 / 12:01 UTC, like the original cron,
            # and also whenever the cached Kp value has expired.
            if (now.hour in (0, 12) and now.minute == 1) or now.minute % 15 == 0:
                self.refresh()
        return GLib.SOURCE_CONTINUE

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self):
        s = self.snapshot
        if not s:
            return
        u = self.settings.units

        # Moon
        self.illum_lbl.set_label(f"{s.moonIlluminationPercent}%")
        self.phase_lbl.set_label(s.moonPhaseName)
        self.moon_view.set_phase(s.moonPhaseFraction)
        self.ascii_lbl.set_label("\n".join(s.moonAsciiArt))
        self.cycle_day_lbl.set_label(f"Day {s.moonAgeDays} of {astro.SYNODIC_MONTH:.1f}")
        self.cycle_bar.set_fraction(max(0.0, min(1.0, s.moonAgeDays / astro.SYNODIC_MONTH)))
        current = PHASE_FRACTION_BY_NAME.get(s.moonPhaseName, s.moonPhaseFraction)
        for icon in self.phase_icons:
            icon.set_current(abs(icon.phase - current) < 1e-6)
        self.moon_card.set("Next new moon", _moon_date(s.nextNewMoon, s.timestamp))
        self.moon_card.set("Next full moon", _moon_date(s.nextFullMoon, s.timestamp))
        self.moon_card.set("Distance", _near_km(s.moonDistanceKm, u))

        # Solar system: Mars/Jupiter/Saturn *DistanceAu are Earth-relative (history,
        # Awtrix), so the Sun-relative card uses their heliocentric values.
        helio = {"Mercury": s.mercuryDistanceAu, "Venus": s.venusDistanceAu, "Earth": s.sunDistanceAu,
                 "Mars": s.marsHelioAu, "Jupiter": s.jupiterHelioAu, "Saturn": s.saturnHelioAu,
                 "Uranus": s.uranusDistanceAu, "Neptune": s.neptuneDistanceAu, "Pluto": s.plutoDistanceAu}
        for p, au in helio.items():
            self.sol_card.set(p, _dist_from_au(au, u), s.lightTimes.get(p, ""))

        # Earth
        e = self.earth_card
        if u == "mi":
            e.set("Orbital Speed", f"{s.earthSpeedKmPerSec / astro.KM_PER_MILE:.2f} mi/s")
            e.set("Speed", f"{s.earthSpeedKmPerHour / astro.KM_PER_MILE:,.0f} mph")
        else:
            e.set("Orbital Speed", f"{s.earthSpeedKmPerSec:.2f} km/s")
            e.set("Speed", f"{s.earthSpeedKmPerHour:,.0f} km/h")
        e.set("Daylight Hours", f"{s.daylightHours:.2f} h")
        e.set("Sunrise (UTC~)", s.sunriseTime)
        e.set("Sunset (UTC~)", s.sunsetTime)
        e.set("Axial Tilt", f"{s.earthAxialTiltDegrees:.3f}°")
        kp = s.auroraKpIndex
        e.set("Aurora Kp Index", "—" if kp < 0 else f"{kp:.2f} ({astro.kp_activity(kp)})")
        kp_lbl = e._rows["Aurora Kp Index"][1]
        (kp_lbl.add_css_class if kp >= 5 else kp_lbl.remove_css_class)("mp-storm")
        e.set("Location", f"{s.latitude:.4f}°, {s.longitude:.4f}°")

        # Near Earth: altitudes always in km (or mi), never AU
        n = self.near_card
        n.clear_rows()
        n.row("_h1", "Stations & telescopes", "Altitude", header=True)
        n.row("ISS", "ISS", _near_km(s.issAltitudeKm, u))
        n.row("Tiangong", "Tiangong", _near_km(s.tiangongAltitudeKm, u))
        n.row("Hubble", "Hubble", _near_km(s.hubbleAltitudeKm, u))
        n.row("_h2", "Constellations", "Satellites", header=True)
        n.row("Starlink", "Starlink", _count(s.starlinkSatelliteCount))
        n.row("Kuiper", "Amazon Kuiper", _count(s.kuiperSatelliteCount))
        if s.totalSatellitesInOrbit > 0:
            n.row("Total", "Total in orbit", _count(s.totalSatellitesInOrbit))
        n.row("_h3", "People in space", _count(s.totalPeopleInSpace), header=True)
        if s.craftOccupancy:
            for craft, count in s.craftOccupancy.items():
                n.row("craft" + craft, craft, str(count))
        else:
            n.row("_none", "Waiting for live data…" if self._busy else "Unavailable", "")
        self.crew_note.set_visible(s.issCrew > 0)
        self.crew_note.set_label(f"★ aboard the ISS · {s.issCrew} crew" if s.issCrew > 0 else "")

        # Deep space: distances from Earth
        d = self.deep_card
        d.set("James Webb (L2)", _near_km(s.jamesWebbDistanceKm, u))
        d.set("Voyager 1", _dist_from_au(s.voyager1DistanceAu, u, 1))
        d.set("Voyager 2", _dist_from_au(s.voyager2DistanceAu, u, 1))
        d.set("New Horizons", _dist_from_au(s.newHorizonsDistanceAu, u, 1))

        # Events, soonest first (the full moon lives on the Moon card)
        ev = self.events_card
        ev.clear_rows()
        events = sorted([("Summer Solstice", s.daysUntilSummerSolstice), ("Winter Solstice", s.daysUntilWinterSolstice),
                         ("Perihelion", s.daysUntilPerihelion), ("Aphelion", s.daysUntilAphelion)],
                        key=lambda x: x[1])
        for name, days in events:
            ev.row(name, name, "today" if days == 0 else f"{days} day{'s' if days != 1 else ''}")

        self.status_lbl.set_label("Updated " + s.timestamp.astimezone().strftime("%H:%M"))

    # ── History ──────────────────────────────────────────────────────────────

    def _open_history(self):
        self.store = None
        if not self.settings.history_enabled:
            self.hist_card.set_visible(False)
            return
        self.hist_card.set_visible(True)
        try:
            if self.settings.history_backend == "mongodb":
                self.store = history.MongoHistory(self.settings.mongodb_uri)
            else:
                self.store = history.SqliteHistory(os.path.join(DATA_DIR, "history.sqlite3"))
            self.store.prune(int(self.settings.history_retention_days or 0))
        except Exception as exc:  # noqa: BLE001
            log.warning("history unavailable: %s", exc)
            self.store = None
            self.hist_status.set_label(f"History unavailable: {exc}")
            self.chart.set_data([], "", "History store unavailable — check Preferences")
            return
        self._load_chart()

    def _save_history(self, s):
        if self.store:
            try:
                self.store.save(s)
            except Exception as exc:  # noqa: BLE001
                log.warning("history save failed: %s", exc)
            self._load_chart()

    def _current_metric(self):
        i = self.metric_dd.get_selected()
        return history.METRICS[i] if i < len(history.METRICS) else history.METRICS[0]

    def _load_chart(self):
        if not self.store:
            return
        key, label, _ = self._current_metric()
        days = RANGES[self.range_dd.get_selected()][0]
        try:
            pts = self.store.query(key, days)
            total = self.store.count()
        except Exception as exc:  # noqa: BLE001
            self.hist_status.set_label(f"History error: {exc}")
            return
        self.chart.set_data(pts, label)
        self.hist_status.set_label(f"{len(pts)} points shown · {total} snapshots stored in {self.store.name}")

    def _export_csv(self, *_):
        if not self.store:
            self.toast("History is not enabled")
            return
        key, _, _ = self._current_metric()
        days = RANGES[self.range_dd.get_selected()][0]
        dlg = Gtk.FileDialog(title="Export CSV", initial_name=f"moonphase-{key}.csv")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            data = history.to_csv(key, self.store.query(key, days))
            with open(f.get_path(), "w", encoding="utf-8") as fh:
                fh.write(data)
            self.toast(f"Saved {os.path.basename(f.get_path())}")

        dlg.save(self, None, done)

    def _populate(self, *_):
        if not self.store:
            self.toast("History is not enabled")
            return
        dlg = Adw.MessageDialog(transient_for=self, heading="Populate Past",
                                body="Backfill history with calculated values for the past N days. "
                                     "Live LEO and aurora values can't be reconstructed and are stored as 0.")
        spin = Gtk.SpinButton.new_with_range(1, 365, 1)
        spin.set_value(30)
        dlg.set_extra_child(spin)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("go", "Populate")
        dlg.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, r):
            if r != "go":
                return
            days = int(spin.get_value())
            store, lat, lon = self.store, self.settings.latitude, self.settings.longitude

            def work():
                n = history.backfill(store, days, lat, lon)
                GLib.idle_add(lambda: (self.toast(f"Added {n} historical snapshots"), self._load_chart()) and False)

            threading.Thread(target=work, daemon=True).start()

        dlg.connect("response", on_resp)
        dlg.present()

    def _reset_history(self, *_):
        if not self.store:
            self.toast("History is not enabled")
            return
        dlg = Adw.MessageDialog(transient_for=self, heading="Reset History?",
                                body=f"This permanently deletes every stored snapshot in {self.store.name}.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete All")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, r):
            if r == "delete":
                self.store.clear()
                self._load_chart()
                self.toast("History cleared")

        dlg.connect("response", on_resp)
        dlg.present()

    # ── Notifications ────────────────────────────────────────────────────────

    def _maybe_notify(self, s):
        if not self.settings.notifications:
            return
        alerts = []
        if s.auroraKpIndex >= 5:
            alerts.append(("aurora", "🌌 Aurora Alert — Geomagnetic Storm!",
                           f"Kp {s.auroraKpIndex:.1f}: visible aurora may be possible at mid-latitudes."))
        if s.daysUntilFullMoon == 0:
            alerts.append(("full0", "🌕 Full Moon Tonight!", f"{s.moonIlluminationPercent}% illuminated."))
        elif s.daysUntilFullMoon == 1:
            alerts.append(("full1", "🌔 Full Moon Tomorrow", f"{s.moonIlluminationPercent}% illuminated tonight."))
        for key, title, body in alerts:
            if time.time() - self._notified.get(key, 0) < 6 * 3600:
                continue
            self._notified[key] = time.time()
            n = Gio.Notification.new(title)
            n.set_body(body)
            self.app.send_notification(key, n)

    # ── Settings ─────────────────────────────────────────────────────────────

    def _on_units(self, dd, _p):
        self.settings.units = UNITS[dd.get_selected()][0]
        self.settings.save()
        self._render()

    def _on_theme(self, action, value):
        action.set_state(value)
        self.settings.theme = value.get_string()
        self.settings.save()
        self._apply_theme(self.settings.theme)

    def _apply_theme(self, key: str):
        """Apply a palette from themes.THEMES, or follow the desktop for 'system'."""
        theme = themes.get(key)
        manager = Adw.StyleManager.get_default()
        if theme is None:
            manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
            self.theme_provider.load_from_data(b"")
            widgets.PALETTE.update(moon=widgets.DEFAULT_MOON_RGB, chart=widgets.DEFAULT_CHART_RGB)
        else:
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK if theme.dark else Adw.ColorScheme.FORCE_LIGHT)
            self.theme_provider.load_from_data(themes.css(theme).encode())
            widgets.PALETTE.update(moon=themes.rgb(theme.moon), chart=themes.rgb(theme.accent))
        for icon in self.phase_icons:
            icon.queue_draw()
        self.chart.queue_draw()

    def _on_moon_style(self, btn):
        self.settings.moon_style = "ascii" if btn.get_active() else "drawn"
        self.moon_stack.set_visible_child_name(self.settings.moon_style)
        self.settings.save()

    def _show_prefs(self, *_):
        s = self.settings
        win = Adw.PreferencesWindow(transient_for=self, modal=True, title="Preferences")
        page = Adw.PreferencesPage()
        win.add(page)

        loc = Adw.PreferencesGroup(title="Location", description="Used for daylight, sunrise and sunset")
        lat = Adw.SpinRow.new_with_range(-90, 90, 0.0001)
        lat.set_title("Latitude")
        lat.set_subtitle("Positive = North")
        lat.set_digits(4)
        lat.set_value(s.latitude)
        lon = Adw.SpinRow.new_with_range(-180, 180, 0.0001)
        lon.set_title("Longitude")
        lon.set_subtitle("Positive = East")
        lon.set_digits(4)
        lon.set_value(s.longitude)
        loc.add(lat)
        loc.add(lon)
        page.add(loc)

        hist = Adw.PreferencesGroup(title="History")
        h_on = Adw.SwitchRow(title="Store history", active=s.history_enabled)
        backend = Adw.ComboRow(title="Storage", model=Gtk.StringList.new(["Local (SQLite)", "MongoDB"]))
        backend.set_selected(1 if s.history_backend == "mongodb" else 0)
        uri = Adw.EntryRow(title="MongoDB URI")
        uri.set_text(s.mongodb_uri)
        keep = Adw.SpinRow.new_with_range(0, 3650, 1)
        keep.set_title("Retention (days)")
        keep.set_subtitle("0 = keep everything")
        keep.set_value(s.history_retention_days)
        for r in (h_on, backend, uri, keep):
            hist.add(r)
        page.add(hist)

        other = Adw.PreferencesGroup(title="Integrations")
        notif = Adw.SwitchRow(title="Desktop notifications", subtitle="Aurora storms and full moon",
                              active=s.notifications)
        aw_on = Adw.SwitchRow(title="Push to Awtrix clock", active=s.awtrix_enabled)
        aw_host = Adw.EntryRow(title="Awtrix URL")
        aw_host.set_text(s.awtrix_host)
        for r in (notif, aw_on, aw_host):
            other.add(r)
        page.add(other)

        def on_close(*_):
            old_hist = (s.history_enabled, s.history_backend, s.mongodb_uri, s.history_retention_days)
            s.latitude, s.longitude = lat.get_value(), lon.get_value()
            s.history_enabled = h_on.get_active()
            s.history_backend = "mongodb" if backend.get_selected() == 1 else "sqlite"
            s.mongodb_uri = uri.get_text().strip()
            s.history_retention_days = int(keep.get_value())
            s.notifications = notif.get_active()
            s.awtrix_enabled = aw_on.get_active()
            s.awtrix_host = aw_host.get_text().strip()
            s.save()
            if old_hist != (s.history_enabled, s.history_backend, s.mongodb_uri, s.history_retention_days):
                self._open_history()
            self._recompute_local()
            return False

        win.connect("close-request", on_close)
        win.present()

    def toast(self, msg: str):
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=3))
