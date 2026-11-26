"""DBT Technologies logo as vector geometry.

Nine flat-top hexagons in a 1-2-3-2-1 diamond; the side-by-side hexagons of the
three middle rows are joined by a bar. The proportions were fitted pixel by
pixel to the logo printed on the original claim form.

Units are arbitrary "logo units", origin at the centre, y pointing down.
Used by both the PDF renderer and the web page (header + favicon).
"""
from __future__ import annotations

import math

COLOR = "#60D4D3"
BACKGROUND = "#F8F8F8"  # the original logo sits on a very light grey box

R = 8.0       # hexagon circumradius (flat-top: width 2R, height sqrt(3)R)
DX = 11.775   # horizontal half-step between neighbouring hexagons
DY = 10.95    # vertical step between rows
BAR = 4.05    # thickness of the joining bars
PAD_Y = 1.5   # background box padding above/below the hexagons

HALF_W = 2 * DX + R
HALF_H = 2 * DY + R * math.sqrt(3) / 2
BOX_HALF_H = HALF_H + PAD_Y

CENTRES = (
    (0.0, -2 * DY),
    (-DX, -DY), (DX, -DY),
    (-2 * DX, 0.0), (0.0, 0.0), (2 * DX, 0.0),
    (-DX, DY), (DX, DY),
    (0.0, 2 * DY),
)
BARS = (  # (x1, y1, x2, y2)
    (-DX, -DY - BAR / 2, DX, -DY + BAR / 2),
    (-2 * DX, -BAR / 2, 2 * DX, BAR / 2),
    (-DX, DY - BAR / 2, DX, DY + BAR / 2),
)


def hexagons() -> list[list[tuple[float, float]]]:
    return [
        [(x + R * math.cos(math.radians(a)), y + R * math.sin(math.radians(a))) for a in range(0, 360, 60)]
        for x, y in CENTRES
    ]


def svg(background: bool = False) -> str:
    """Stand-alone SVG markup of the logo."""
    w, h = 2 * HALF_W, 2 * BOX_HALF_H
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-HALF_W:.2f} {-BOX_HALF_H:.2f} {w:.2f} {h:.2f}">'
    ]
    if background:
        parts.append(f'<rect x="{-HALF_W:.2f}" y="{-BOX_HALF_H:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{BACKGROUND}"/>')
    parts.append(f'<g fill="{COLOR}">')
    for poly in hexagons():
        parts.append('<polygon points="' + " ".join(f"{x:.3f},{y:.3f}" for x, y in poly) + '"/>')
    for x1, y1, x2, y2 in BARS:
        parts.append(f'<rect x="{x1:.3f}" y="{y1:.3f}" width="{x2 - x1:.3f}" height="{y2 - y1:.3f}"/>')
    parts.append("</g></svg>")
    return "".join(parts)
