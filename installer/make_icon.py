"""Draw the company logo (claim_form/logo.py) as a Windows .ico for the exe and installer.

Usage:  python installer/make_icon.py build/ClaimForm.ico
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claim_form import logo  # noqa: E402

SIZE = 256
SUPERSAMPLE = 4          # draw 4x larger, then shrink, for smooth edges
MARGIN = 0.94            # share of the icon width the logo fills
ICO_SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]


def render(size: int = SIZE) -> Image.Image:
    big = size * SUPERSAMPLE
    scale = big * MARGIN / (2 * logo.HALF_W)   # the logo is wider than it is tall
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def pt(x: float, y: float) -> tuple[float, float]:
        return big / 2 + x * scale, big / 2 + y * scale

    for poly in logo.hexagons():
        draw.polygon([pt(x, y) for x, y in poly], fill=logo.COLOR)
    for x1, y1, x2, y2 in logo.BARS:
        draw.rectangle([pt(x1, y1), pt(x2, y2)], fill=logo.COLOR)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/ClaimForm.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    render().save(out, format="ICO", sizes=ICO_SIZES)
    print(f"Icon written to {out}")
