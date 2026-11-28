"""Application entry point."""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .config import APP_ID  # noqa: E402


class MoonPhaseApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._about)
        self.add_action(about)
        quit_ = Gio.SimpleAction.new("quit", None)
        quit_.connect("activate", lambda *_: self.quit())
        self.add_action(quit_)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("win.refresh", ["F5", "<Ctrl>r"])
        self.set_accels_for_action("win.preferences", ["<Ctrl>comma"])

    def do_activate(self):
        if not self.window:
            from .window import MainWindow

            self.window = MainWindow(self)
        self.window.present()

    def _about(self, *_):
        dlg = Adw.AboutWindow(
            transient_for=self.window,
            application_name="Orbitly",
            application_icon=APP_ID,
            developer_name="Jamie Harwood",
            version=__version__,
            website="https://github.com/jamieharwood/MoonPhase-uBuntu",
            issue_url="https://github.com/jamieharwood/MoonPhase-uBuntu/issues",
            license_type=Gtk.License.MIT_X11,
            comments="Moon phase, solar system distances, deep-space probes, "
                     "Earth and LEO data, as a native Ubuntu app.",
        )
        dlg.present()


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return MoonPhaseApp().run(argv if argv is not None else sys.argv)
