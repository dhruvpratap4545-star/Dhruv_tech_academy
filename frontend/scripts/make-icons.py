"""Derive the web icon set from the client's crest.

Run from anywhere when the logo changes; the generated files are committed:

    pip install Pillow && python frontend/scripts/make-icons.py

Pillow is deliberately not a project dependency. This runs by hand on the rare occasion the
brand changes, and nothing at build or run time needs it.

The source is `legacy/static/images/logo.png` — 500x500, 222 KB, and *fully opaque*: its
"RGBA" mode is a lie, the corners are solid white. Dropped straight into the header that
white square shows as a box around the crest on the navy sign-in panel and in dark mode.

So two things happen here:

1. **A circular alpha mask.** The artwork is a full-bleed circle touching all four edges at
   their midpoints, so a circle of radius 250 centred at (250, 250) inscribes it exactly —
   nothing of the crest is clipped, and only the white corners are removed. The mask is
   drawn at 4x and downscaled so the edge is anti-aliased rather than a staircase.
2. **Sized derivatives.** Serving the 222 KB original just to draw it at 32px would be a
   fifth of a megabyte on every page load.

One honest limitation of the result: the crest carries fine ring text ("PREMIUM ONLINE
DIGITAL EDUCATION"). Below roughly 48px that text stops being legible and what survives is
the silhouette — gold ring, navy mortarboard. That is inherent to an ornate crest, and the
answer is not to redraw a client's logo.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

# Repo root, two levels up from frontend/scripts/.
ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "legacy" / "static" / "images" / "logo.png"
OUT = ROOT / "frontend" / "public"

# 16 and 32 are the classic favicon pair; 48 is what Windows and some feed readers pick up;
# 180 is Apple's touch icon. 128 covers the header mark everywhere it appears, including
# 40px CSS on a 3x phone screen.
SIZES = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "favicon-48.png": 48,
    "logo-128.png": 128,
    "apple-touch-icon.png": 180,
}

SUPERSAMPLE = 4


def circular_alpha(image: Image.Image) -> Image.Image:
    """Return ``image`` with everything outside its inscribed circle made transparent."""
    size = image.size[0]
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)

    out = image.copy()
    out.putalpha(mask)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = circular_alpha(Image.open(SOURCE).convert("RGBA"))

    for name, size in SIZES.items():
        # LANCZOS: the crest is full of thin gold strokes, and a cheaper filter turns them
        # into mush well before the size alone would.
        resized = source.resize((size, size), Image.Resampling.LANCZOS)

        if name == "apple-touch-icon.png":
            # iOS composites a transparent touch icon onto black, which frames the crest
            # in a dark square on the home screen. Apple asks for an opaque image, so this
            # one gets the crest's own white disc extended to the corners.
            backdrop = Image.new("RGBA", resized.size, (255, 255, 255, 255))
            backdrop.alpha_composite(resized)
            resized = backdrop

        target = OUT / name
        resized.save(target, "PNG", optimize=True)
        print(f"  {name:24} {size:>4}px  {target.stat().st_size / 1024:6.1f} KB")

    # A multi-resolution .ico as well: some corporate browsers and Windows pinned sites
    # still ask for /favicon.ico by path, whatever the HTML says.
    ico = OUT / "favicon.ico"
    source.resize((256, 256), Image.Resampling.LANCZOS).save(
        ico, "ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print(f"  {'favicon.ico':24}  multi  {ico.stat().st_size / 1024:6.1f} KB")

    print(f"\n  source was {SOURCE.stat().st_size / 1024:.1f} KB, fully opaque")


if __name__ == "__main__":
    main()
