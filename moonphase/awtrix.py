"""Optional push of metrics to an Awtrix pixel clock (``/api/custom``)."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .astro import Snapshot

log = logging.getLogger(__name__)


def build_pushes(s: Snapshot) -> list[tuple[str, str, str]]:
    """(app name, text, icon) tuples – same set the original app pushes."""
    p = [
        ("marsDistanceAu", f"{s.marsDistanceAu:.1f}au", "MARS"),
        ("jupiterDistanceAu", f"{s.jupiterDistanceAu:.1f}au", "JUPITER"),
        ("saturnDistanceAu", f"{s.saturnDistanceAu:.1f}au", "SATURN"),
        ("CurrentDayLength", f"{s.daylightHours:.1f}hrs", "DAYLENGTH"),
        ("voyager1", f"V1:{s.voyager1DistanceAu:.0f}au", "VOYAGER"),
        ("voyager2", f"V2:{s.voyager2DistanceAu:.0f}au", "VOYAGER"),
        ("newhorizons", f"NH:{s.newHorizonsDistanceAu:.0f}au", "NEWHORIZONS"),
        ("summersolstice", f"{s.daysUntilSummerSolstice}d", "SUMMER"),
        ("wintersolstice", f"{s.daysUntilWinterSolstice}d", "WINTER"),
        ("perihelion", f"{s.daysUntilPerihelion}d", "PERIHELION"),
        ("aphelion", f"{s.daysUntilAphelion}d", "PERIHELION"),
        ("earthSpeed", f"{s.earthSpeedKmPerSec:.1f}km/s", "EARTH"),
        ("moonDistance", f"{s.moonDistanceKm:,.0f}km", "MOON"),
        ("lightMars", "Lt:" + s.lightTimes.get("Mars", ""), "LIGHT"),
        ("lightJupiter", "Lt:" + s.lightTimes.get("Jupiter", ""), "LIGHT"),
        ("moonphase", s.moonPhaseName, s.moonPhaseIcon),
        ("moonillumination", f"{s.moonIlluminationPercent}%", s.moonPhaseIcon),
        ("fullmoon", f"{s.daysUntilFullMoon}d", s.moonPhaseIcon),
    ]
    if s.auroraKpIndex >= 0:
        label = f"⚡Kp{s.auroraKpIndex:.1f}" if s.auroraKpIndex >= 5 else f"Kp{s.auroraKpIndex:.1f}"
        p.append(("auroraKp", label, "AURORA"))
    return p


def push_all(host: str, s: Snapshot) -> int:
    """POST every metric; returns the number that succeeded."""
    ok = 0
    base = host.rstrip("/") + "/api/custom?name="
    for name, text, icon in build_pushes(s):
        body = json.dumps({"name": name, "text": text, "save": "true", "effect": "", "icon": icon}).encode()
        req = urllib.request.Request(base + urllib.parse.quote(name), data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                ok += 200 <= res.status < 300
        except Exception as exc:  # noqa: BLE001
            log.warning("Awtrix push %s failed: %s", name, exc)
            break  # device unreachable – don't hammer it
    return ok
