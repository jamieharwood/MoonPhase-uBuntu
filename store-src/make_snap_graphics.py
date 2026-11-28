"""Renders the Snap Store icon, featured banner and screenshots into store/snap/.

Run from the repo root:  python3 store-src/make_snap_graphics.py
Inputs: the app's SVG icon, two raw window captures (store-src/capture-*.png, taken with
`import -window` on X11) and the Barlow fonts (SIL OFL) also used by the Android watch face.
"""
import math
import random

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

OUT = "store/snap"
SVG = "data/io.github.jamieharwood.MoonPhase.svg"
FONT = "store-src/barlow_semibold.ttf"
FONT_MED = "store-src/barlow_medium.ttf"
SKY_TOP, SKY_BOTTOM = (11, 31, 63), (3, 10, 26)  # the icon's own sky gradient
INK, GREY, MOON = (236, 236, 236), (160, 172, 190), (244, 227, 166)


def render_svg(size):
    """The app icon as a transparent RGBA image, `size` px square."""
    pb = GdkPixbuf.Pixbuf.new_from_file_at_size(SVG, size, size)  # librsvg's pixbuf loader
    mode = "RGBA" if pb.get_has_alpha() else "RGB"
    return Image.frombytes(mode, (pb.get_width(), pb.get_height()), pb.get_pixels(),
                           "raw", mode, pb.get_rowstride()).convert("RGBA")


def sky(w, h, seed=7):
    """Night-sky gradient with a scatter of stars."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOTTOM)))
    rnd = random.Random(seed)
    for _ in range(w * h // 2600):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r = rnd.choice([1, 1, 1, 2, 2, 3])
        v = rnd.randrange(120, 255)
        d.ellipse([x - r / 2, y - r / 2, x + r / 2, y + r / 2], fill=(v, v, min(255, v + 10)))
    return img


def icon():
    # The store shows the icon on light and dark pages, so keep the round icon on transparency.
    render_svg(512).save(f"{OUT}/icon-512.png")
    render_svg(256).save(f"{OUT}/icon-256.png")


def banner():
    # Snap Store featured banner: 3:1, 720x240 to 4320x1440, under 2 MB.
    w, h = 2160, 720
    img = sky(w, h)
    # A faint orbit arc around the moon, like the watch face's dial.
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy, r = 1640, 360, 250
    gd.ellipse([cx - r - 90, cy - r - 90, cx + r + 90, cy + r + 90], outline=(120, 145, 190, 150), width=4)
    glow = glow.filter(ImageFilter.GaussianBlur(1.5))
    img.paste(glow, (0, 0), glow)
    moon = render_svg(2 * r + 40)
    # Drop the icon's own sky disc: keep only the bright crescent.
    px = moon.load()
    for y in range(moon.height):
        for x in range(moon.width):
            rr, gg, bb, aa = px[x, y]
            if aa and rr < 120:
                px[x, y] = (rr, gg, bb, 0)
    img.paste(moon, (cx - moon.width // 2, cy - moon.height // 2), moon)

    d = ImageDraw.Draw(img)
    d.text((150, 196), "Orbitly", font=ImageFont.truetype(FONT, 190), fill=INK)
    d.text((158, 420), "The Moon, the Sun and the sky above you,", font=ImageFont.truetype(FONT_MED, 52), fill=GREY)
    d.text((158, 486), "at a glance on your Ubuntu desktop", font=ImageFont.truetype(FONT_MED, 52), fill=GREY)
    img.save(f"{OUT}/banner.png", optimize=True)


def window_only(path):
    """Cut the window out of an X11 capture and give it back its rounded corners."""
    raw = Image.open(path).convert("RGB")
    box = raw.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
    win = raw.crop(box)
    radius = 24
    mask = Image.new("L", win.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, win.width - 1, win.height - 1], radius, fill=255)
    out = win.convert("RGBA")
    out.putalpha(mask)
    return out


def screenshot(src, name):
    # Window on the icon's sky, with a soft shadow; 16:10-ish, under 2 MB.
    win = window_only(src)
    scale = 1600 / win.width
    win = win.resize((round(win.width * scale), round(win.height * scale)), Image.LANCZOS)
    pad_x, pad_y = 120, 90
    w, h = win.width + 2 * pad_x, win.height + 2 * pad_y
    bg = sky(w, h, seed=len(name)).convert("RGBA")
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [pad_x, pad_y + 14, pad_x + win.width, pad_y + win.height + 14], 24, fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    bg = Image.alpha_composite(bg, shadow)
    bg.paste(win, (pad_x, pad_y), win)
    bg.convert("RGB").save(f"{OUT}/{name}.png", optimize=True)


if __name__ == "__main__":
    icon()
    banner()
    screenshot("store-src/capture-overview.png", "screenshot-1-overview")
    screenshot("store-src/capture-history.png", "screenshot-2-history")
