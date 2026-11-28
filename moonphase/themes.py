"""Colour themes, ported from the MoonPhase web dashboard's theme menu.

Each palette overrides libadwaita's named colours, so every standard widget
follows it, plus a few app-specific ones (the Moon colour and the chart line).
"System" applies nothing and follows the desktop's light/dark preference.

The web app names several palettes after space organisations. Orbitly is
published in the Snap Store, so here they have neutral names and make no
reference to any organisation.

Pure Python with no GTK dependency, so it can be unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM = "system"


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    dark: bool
    bg: str            # window background
    card: str          # card background
    border: str
    fg: str            # primary text
    fg_dim: str        # secondary text
    accent: str        # accent / highlight
    moon: str          # illumination figure, phase name and phase strip
    red: str           # errors, storm warnings
    header_bg: str
    header_fg: str
    rule: str          # header bottom border, e.g. "3px solid #ff2e97"
    radius: int        # card corner radius (px)
    font: str          # CSS font-family list


MONO = '"Courier New", Courier, monospace'
SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif'

THEMES: list[Theme] = [
    Theme("classic", "Classic", True, "#030a1a", "#071526", "#0d2a4a", "#c8dff0", "#7aa8cc",
          "#00d4ff", "#f0e68c", "#ff4444", "#030a1a", "#00d4ff", "1px solid #0d2a4a", 8, MONO),
    Theme("light", "Light", False, "#f0f4f8", "#ffffff", "#c0d4eb", "#1a2e45", "#3a6a9a",
          "#005fa3", "#000000", "#bb2222", "#f0f4f8", "#005fa3", "1px solid #c0d4eb", 8, MONO),
    Theme("monochrome", "Monochrome", True, "#000000", "#0a0a0a", "#2a2a2a", "#ffffff", "#9a9a9a",
          "#ffffff", "#ffffff", "#ff5a5a", "#000000", "#ffffff", "1px solid #ffffff", 0, SANS),
    Theme("mission", "Mission Blue", False, "#eef2f7", "#ffffff", "#d3dce8", "#1b1b1b", "#3e4c63",
          "#0b3d91", "#0b3d91", "#fc3d21", "#0b3d91", "#ffffff", "4px solid #fc3d21", 2, SANS),
    Theme("sky", "Sky", True, "#061525", "#0c243c", "#1d4e78", "#e7f4fb", "#8eb8d0",
          "#5ec8ef", "#d7f1fb", "#ff6b6b", "#00205b", "#ffffff", "3px solid #7ed0f2", 6, SANS),
    Theme("neon", "Neon", True, "#050505", "#111111", "#2c2c2c", "#ffffff", "#b3b3b3",
          "#ff2e97", "#ffd0ea", "#ff4d6a", "#000000", "#ffffff", "3px solid #ff2e97", 0, SANS),
    Theme("daylight", "Daylight", False, "#f3f5f7", "#ffffff", "#d5dde6", "#1c2430", "#4d5d70",
          "#004b87", "#004b87", "#c0392b", "#004b87", "#ffffff", "4px solid #e87722", 2, SANS),
    Theme("indigo", "Indigo", True, "#07101c", "#0e1c30", "#1e3d66", "#e8f2ff", "#9bb4d4",
          "#3ec6ff", "#d6ebff", "#ef4135", "#001e60", "#ffffff", "3px solid #3ec6ff", 4, SANS),
    Theme("copper", "Copper", True, "#161210", "#221c19", "#3d322b", "#f6eee8", "#c2aea0",
          "#e07a3d", "#f0c7a8", "#e05a4f", "#100e0c", "#f6eee8", "3px solid #e07a3d", 2, SANS),
    Theme("gold", "Gold", True, "#070b16", "#12182b", "#2a3658", "#f8f3e4", "#cbb98a",
          "#f5c518", "#ffe27a", "#ff6b5a", "#070b16", "#ffe27a", "3px solid #f5c518", 10, SANS),
]
BY_KEY = {t.key: t for t in THEMES}

# Menu order: follow the desktop first, then the palettes.
CHOICES: list[tuple[str, str]] = [(SYSTEM, "Follow System")] + [(t.key, t.label) for t in THEMES]


def get(key: str) -> Theme | None:
    """The palette for a key, or None for 'system' and unknown keys."""
    return BY_KEY.get(key)


def rgb(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _luminance(hex_colour: str) -> float:
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_colour(hex_colour: str) -> str:
    """Black or white, whichever reads better on the given background."""
    return "#000000" if _luminance(hex_colour) > 0.4 else "#ffffff"


def css(theme: Theme) -> str:
    """GTK CSS that applies a palette over libadwaita's named colours."""
    t = theme
    accent_fg = on_colour(t.accent)
    return f"""
@define-color accent_color {t.accent};
@define-color accent_bg_color {t.accent};
@define-color accent_fg_color {accent_fg};
@define-color destructive_color {t.red};
@define-color destructive_bg_color {t.red};
@define-color error_color {t.red};
@define-color window_bg_color {t.bg};
@define-color window_fg_color {t.fg};
@define-color view_bg_color {t.bg};
@define-color view_fg_color {t.fg};
@define-color headerbar_bg_color {t.header_bg};
@define-color headerbar_fg_color {t.header_fg};
@define-color headerbar_backdrop_color {t.header_bg};
@define-color headerbar_border_color {t.border};
@define-color card_bg_color {t.card};
@define-color card_fg_color {t.fg};
@define-color card_shade_color {t.border};
@define-color dialog_bg_color {t.card};
@define-color dialog_fg_color {t.fg};
@define-color popover_bg_color {t.card};
@define-color popover_fg_color {t.fg};
window, window * {{ font-family: {t.font}; }}
toolbarview > .top-bar, toolbarview > .top-bar headerbar, headerbar {{
  background-color: {t.header_bg}; color: {t.header_fg}; box-shadow: none; }}
toolbarview > .top-bar {{ border-bottom: {t.rule}; }}
toolbarview > .top-bar headerbar .dim-label {{ color: {t.header_fg}; opacity: 0.8; }}
.mp-card {{ border-radius: {t.radius}px; border: 1px solid {t.border}; box-shadow: none; }}
.mp-key, .mp-stat-key, .mp-hero-label, .mp-note, .dim-label {{ color: {t.fg_dim}; opacity: 1; }}
.mp-moon {{ color: {t.moon}; }}
.mp-card-title {{ color: {t.accent}; }}
progressbar.mp-cycle progress {{ background-color: {t.moon}; }}
"""
