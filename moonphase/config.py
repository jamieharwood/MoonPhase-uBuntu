"""User settings, stored as JSON in ``$XDG_CONFIG_HOME/moonphase/config.json``.

Environment variables with the same names as the original app
(``LATITUDE``, ``LONGITUDE``, ``AWTRIXHOSTNAME``, ``SPRING_DATA_MONGODB_URI``)
override the stored values when set.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from . import astro

APP_ID = "io.github.jamieharwood.MoonPhase"


def _xdg(var: str, fallback: str) -> str:
    return os.path.join(os.environ.get(var) or os.path.expanduser(fallback), "moonphase")


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config")
DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Settings:
    latitude: float = astro.DEFAULT_LATITUDE
    longitude: float = astro.DEFAULT_LONGITUDE
    units: str = "au"                     # au | km | mi
    moon_style: str = "drawn"             # drawn | ascii
    history_enabled: bool = True
    history_backend: str = "sqlite"       # sqlite | mongodb
    mongodb_uri: str = "mongodb://localhost:27017/moonphase"
    history_retention_days: int = 0
    notifications: bool = True
    awtrix_enabled: bool = False
    awtrix_host: str = "http://moonclock.local"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            with open(CONFIG_FILE, encoding="utf-8") as fh:
                for k, v in json.load(fh).items():
                    if hasattr(s, k):
                        setattr(s, k, v)
        except (OSError, ValueError):
            pass
        env = os.environ
        try:
            if env.get("LATITUDE"):
                s.latitude = float(env["LATITUDE"])
            if env.get("LONGITUDE"):
                s.longitude = float(env["LONGITUDE"])
        except ValueError:
            pass
        if env.get("AWTRIXHOSTNAME"):
            s.awtrix_host = env["AWTRIXHOSTNAME"]
        if env.get("SPRING_DATA_MONGODB_URI"):
            s.mongodb_uri = env["SPRING_DATA_MONGODB_URI"]
        s.latitude = astro.validate_lat(float(s.latitude))
        s.longitude = astro.validate_lon(float(s.longitude))
        return s

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        os.replace(tmp, CONFIG_FILE)
