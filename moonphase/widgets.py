"""Custom Cairo-drawn widgets: the moon graphic and the history chart."""

from __future__ import annotations

import math
import random
from datetime import datetime

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gtk  # noqa: E402

TAU = 2 * math.pi


class CairoWidget(Gtk.Widget):
    """Widget drawn with pycairo.

    Draws into an in-memory image surface and hands GTK a texture, so it
    works without the optional ``python3-gi-cairo`` bridge.
    """

    def __init__(self, width: int = -1, height: int = -1):
        super().__init__()
        self.set_size_request(width, height)

    def do_snapshot(self, snapshot):
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        scale = max(1, self.get_scale_factor())
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
        cr = cairo.Context(surf)
        cr.scale(scale, scale)
        self.draw(cr, w, h)
        surf.flush()
        tex = Gdk.MemoryTexture.new(w * scale, h * scale, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                    GLib.Bytes.new(bytes(surf.get_data())), surf.get_stride())
        rect = Graphene.Rect()
        rect.init(0, 0, w, h)
        snapshot.append_texture(tex, rect)

    def draw(self, cr, w, h):
        raise NotImplementedError


class MoonView(CairoWidget):
    """A moon disc with craters, a terminator matching the phase fraction,
    faint earthshine and a gently twinkling starfield."""

    def __init__(self, size: int = 220):
        super().__init__(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.phase = 0.0
        rnd = random.Random(42)
        self._stars = [(rnd.random(), rnd.random(), rnd.uniform(0.4, 1.4), rnd.uniform(0, TAU))
                       for _ in range(70)]
        self._craters = [(-0.35, -0.30, 0.16), (0.30, -0.42, 0.10), (0.18, 0.05, 0.22),
                         (-0.20, 0.38, 0.13), (0.48, 0.30, 0.09), (-0.55, 0.05, 0.08),
                         (-0.05, -0.62, 0.07), (0.05, 0.62, 0.06)]
        self._t = 0.0
        self._timer = GLib.timeout_add(100, self._tick)
        self.connect("unrealize", self._on_unrealize)

    def _on_unrealize(self, *_):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self):
        self._t += 0.1
        if self.get_mapped():
            self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def set_phase(self, fraction: float):
        self.phase = fraction % 1.0
        self.queue_draw()

    def draw(self, cr, w, h):
        # Sky
        cr.set_source_rgb(0.02, 0.04, 0.10)
        _rounded(cr, 0, 0, w, h, 12)
        cr.fill()
        for x, y, r, ph in self._stars:
            a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self._t * 1.7 + ph))
            cr.set_source_rgba(1, 1, 0.95, a)
            cr.arc(x * w, y * h, r, 0, TAU)
            cr.fill()

        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.36
        # Lit disc with maria / craters
        cr.set_source_rgb(0.93, 0.90, 0.80)
        cr.arc(cx, cy, r, 0, TAU)
        cr.fill()
        for dx, dy, cr_ in self._craters:
            cr.set_source_rgba(0.62, 0.60, 0.55, 0.55)
            cr.arc(cx + dx * r, cy + dy * r, cr_ * r, 0, TAU)
            cr.fill()

        # Shadow = disc minus lit region (even-odd fill)
        p = self.phase
        tx = math.cos(TAU * p)          # terminator x-scale: +1 new … -1 full
        side = 1 if p < 0.5 else -1     # waxing lit on the right (N. hemisphere)
        cr.new_path()
        cr.arc(cx, cy, r, 0, TAU)
        cr.close_path()
        n = 64
        for i in range(n + 1):           # limb: top -> bottom on lit side
            t = -math.pi / 2 + math.pi * i / n
            x, y = r * math.cos(t), r * math.sin(t)
            fn = cr.move_to if i == 0 else cr.line_to
            fn(cx + side * x, cy + y)
        for i in range(n + 1):           # terminator: bottom -> top
            t = math.pi / 2 - math.pi * i / n
            x, y = tx * r * math.cos(t), r * math.sin(t)
            cr.line_to(cx + side * x, cy + y)
        cr.close_path()
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.set_source_rgba(0.03, 0.05, 0.10, 0.88)
        cr.fill()
        cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        # Soft glow
        cr.set_source_rgba(1, 0.97, 0.85, 0.15)
        cr.set_line_width(3)
        cr.arc(cx, cy, r + 1.5, 0, TAU)
        cr.stroke()


def _rounded(cr, x, y, w, h, rad):
    cr.new_sub_path()
    cr.arc(x + w - rad, y + rad, rad, -math.pi / 2, 0)
    cr.arc(x + w - rad, y + h - rad, rad, 0, math.pi / 2)
    cr.arc(x + rad, y + h - rad, rad, math.pi / 2, math.pi)
    cr.arc(x + rad, y + rad, rad, math.pi, 1.5 * math.pi)
    cr.close_path()


class HistoryChart(CairoWidget):
    """Minimal line chart for (datetime, value) points."""

    def __init__(self):
        super().__init__(-1, 260)
        self.set_hexpand(True)
        self.points: list[tuple[datetime, float]] = []
        self.label = ""
        self.message = "No history yet"

    def set_data(self, points, label: str, message: str = "No history yet"):
        self.points, self.label, self.message = points, label, message
        self.queue_draw()

    def draw(self, cr, w, h):
        fg = self.get_color()
        cr.select_font_face("Sans")
        cr.set_font_size(11)
        if len(self.points) < 1:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            ext = cr.text_extents(self.message)
            cr.move_to((w - ext.width) / 2, h / 2)
            cr.show_text(self.message)
            return
        vals = [v for _, v in self.points]
        lo, hi = min(vals), max(vals)
        if math.isclose(lo, hi):
            pad = abs(lo) * 0.01 or 1.0
            lo, hi = lo - pad, hi + pad
        left, right, top, bottom = 70, 16, 14, 34
        pw, ph = w - left - right, h - top - bottom
        t0 = self.points[0][0].timestamp()
        t1 = self.points[-1][0].timestamp()
        span = (t1 - t0) or 1.0

        def xy(ts, v):
            x = left + (ts.timestamp() - t0) / span * pw if len(self.points) > 1 else left + pw / 2
            return x, top + (hi - v) / (hi - lo) * ph

        # Grid + y labels
        cr.set_line_width(1)
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            y = top + (hi - v) / (hi - lo) * ph
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
            cr.move_to(left, y)
            cr.line_to(left + pw, y)
            cr.stroke()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.7)
            txt = _fmt(v)
            ext = cr.text_extents(txt)
            cr.move_to(left - 8 - ext.width, y + 4)
            cr.show_text(txt)
        # x labels (first, middle, last)
        idxs = sorted({0, len(self.points) // 2, len(self.points) - 1})
        for i in idxs:
            ts = self.points[i][0]
            x, _ = xy(ts, lo)
            txt = ts.strftime("%d %b %y")
            ext = cr.text_extents(txt)
            x = min(max(x - ext.width / 2, left), left + pw - ext.width)
            cr.move_to(x, h - 12)
            cr.show_text(txt)
        # Area + line
        accent = (0.21, 0.52, 0.89)
        cr.move_to(*xy(*self.points[0]))
        for ts, v in self.points[1:]:
            cr.line_to(*xy(ts, v))
        path = cr.copy_path()
        cr.set_source_rgb(*accent)
        cr.set_line_width(2)
        cr.stroke()
        cr.append_path(path)
        cr.line_to(xy(self.points[-1][0], lo)[0], top + ph)
        cr.line_to(xy(self.points[0][0], lo)[0], top + ph)
        cr.close_path()
        cr.set_source_rgba(*accent, 0.15)
        cr.fill()
        if len(self.points) <= 60:
            cr.set_source_rgb(*accent)
            for ts, v in self.points:
                cr.arc(*xy(ts, v), 2.5, 0, TAU)
                cr.fill()


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 100_000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.3f}"
    return f"{v:.4f}"
