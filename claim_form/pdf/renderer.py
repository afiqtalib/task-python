"""Pixel-faithful replica of the DBT Technologies T&E claim form.

Coordinates below are measured on the reference document rendered at
918 x 1298 px (A4 portrait) and converted to PDF points by :class:`Pen`.
Keeping the numbers in reference pixels makes every line, column and text
position directly comparable with the original form.

Pages
  1. Main form  - header, travel details, mileage, claim summary, signatures
  2. Details    - entertainment, toll & parking, subsistence, miscellaneous
  3. Travel sheet (optional) - travel details with the mileage breakdown
"""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .. import config, logo
from ..formatting import (
    fmt_date,
    fmt_km_cell,
    fmt_km_total,
    fmt_money,
    fmt_money_or_blank,
    fmt_number,
    fmt_rate,
    fmt_time,
)
from ..models import Claim, ExpenseEntry
from .fonts import fonts

PAGE_W, PAGE_H = A4
REF_W, REF_H = 918.0, 1298.0
SX, SY = PAGE_W / REF_W, PAGE_H / REF_H

# The source workbook prints at ~98 %: Arial 8 -> 7.84 pt, Arial 17 -> 16.66 pt.
_K = 0.98
FS_TITLE = 17 * _K
FS_REG_NO = 7 * _K
FS_BAND = 9 * _K
FS_LABEL = 8.5 * _K
FS_BODY = 8 * _K
FS_SIGN = 7.5 * _K
FS_ROLE = 7 * _K

LINE_GRID = 0.6
LINE_RULE = 0.6
LINE_FRAME = 1.3
BAND_FILL = HexColor("#D9D9D9")
CAP_CENTER = 0.358  # half of Arial's cap height: centres capitals on a row line

LEFT, RIGHT = 45.0, 879.0
MID = (LEFT + RIGHT) / 2


# ---------------------------------------------------------------------------
# Drawing primitive working in reference pixels
# ---------------------------------------------------------------------------
class Pen:
    def __init__(self, canvas: Canvas):
        self.c = canvas
        self.regular, self.bold = fonts()

    @staticmethod
    def x(px: float) -> float:
        return px * SX

    @staticmethod
    def y(px: float) -> float:
        return PAGE_H - px * SY

    def hline(self, x1: float, x2: float, y: float, width: float = LINE_GRID) -> None:
        self.c.setLineWidth(width)
        self.c.line(self.x(x1), self.y(y), self.x(x2), self.y(y))

    def vline(self, x: float, y1: float, y2: float, width: float = LINE_GRID) -> None:
        self.c.setLineWidth(width)
        self.c.line(self.x(x), self.y(y1), self.x(x), self.y(y2))

    def fill(self, x1: float, y1: float, x2: float, y2: float, color) -> None:
        self.c.setFillColor(color)
        self.c.rect(self.x(x1), self.y(y2), (x2 - x1) * SX, (y2 - y1) * SY, stroke=0, fill=1)
        self.c.setFillColor(black)

    def frame(self, top: float, bottom: float) -> None:
        self.c.setLineWidth(LINE_FRAME)
        self.c.rect(self.x(LEFT), self.y(bottom), (RIGHT - LEFT) * SX, (bottom - top) * SY, stroke=1, fill=0)

    def band(self, top: float, bottom: float, label: str) -> None:
        """Grey full-width title bar."""
        self.fill(LEFT, top, RIGHT, bottom, BAND_FILL)
        self.hline(LEFT, RIGHT, top)
        self.hline(LEFT, RIGHT, bottom)
        self.text(label, MID, (top + bottom) / 2, FS_BAND, bold=True, align="center")

    def text(self, s: str, x: float, cy: float, size: float, *, bold: bool = False,
             align: str = "left", max_width: float | None = None, underline: bool = False) -> float:
        """Draw ``s`` vertically centred on ``cy``. Returns the right edge (px)."""
        if not s:
            return x
        font = self.bold if bold else self.regular
        s, size = _fit(s, font, size, max_width * SX if max_width else None)
        baseline = self.y(cy) - size * CAP_CENTER
        return self.text_at(s, x, baseline, size, font, align=align, underline=underline)

    def text_at(self, s: str, x: float, baseline: float, size: float, font: str, *,
                align: str = "left", underline: bool = False) -> float:
        width = stringWidth(s, font, size)
        left = self.x(x)
        if align == "center":
            left -= width / 2
        elif align == "right":
            left -= width
        self.c.setFont(font, size)
        self.c.drawString(left, baseline, s)
        if underline:
            self.c.setLineWidth(0.55)
            self.c.line(left, baseline - size * 0.15, left + width, baseline - size * 0.15)
        return (left + width) / SX


def _fit(s: str, font: str, size: float, max_width: float | None) -> tuple[str, float]:
    """Shrink text to fit a cell (like Excel's shrink-to-fit), truncating as a last resort."""
    if max_width is None:
        return s, size
    width = stringWidth(s, font, size)
    if width <= max_width:
        return s, size
    min_size = max(size * 0.72, 5.2)
    shrunk = size * max_width / width
    if shrunk >= min_size:
        return s, shrunk
    while s and stringWidth(s + "…", font, min_size) > max_width:
        s = s[:-1]
    return s.rstrip() + "…", min_size


# ---------------------------------------------------------------------------
# Shared: letterhead + claimant details + travel table (pages 1 and 3)
# ---------------------------------------------------------------------------
INFO_ROWS = (175.0, 194.5, 214.0)
INFO_RULE_OFFSET = 9.5

T_COLS = (45.0, 137.0, 595.0, 661.0, 728.0, 879.0)
T_HEAD_TOP, T_HEAD_MID, T_HEAD_BOTTOM = 259.0, 278.0, 307.5
T_ROW_H = 19.25
T_ROWS = config.CAPACITY["travel"]
T_BODY_BOTTOM = T_HEAD_BOTTOM + T_ROWS * T_ROW_H      # 750.25
T_TOTAL_BOTTOM = T_BODY_BOTTOM + T_ROW_H               # 769.5


LOGO_CENTER = (221.5, 80.0)  # reference px
LOGO_WIDTH = 36.0            # reference px (width of the logo's background box)


def _draw_logo(pen: Pen) -> None:
    scale = LOGO_WIDTH / (2 * logo.HALF_W)  # reference px per logo unit
    cx, cy = LOGO_CENTER
    half_w, half_h = logo.HALF_W * scale, logo.BOX_HALF_H * scale

    if config.LOGO_FILE.is_file():  # optional official raster logo
        try:
            pen.c.drawImage(ImageReader(str(config.LOGO_FILE)), pen.x(cx - half_w), pen.y(cy + half_h),
                            2 * half_w * SX, 2 * half_h * SY, preserveAspectRatio=True, anchor="c", mask="auto")
            return
        except Exception:
            pass  # fall back to the vector logo

    pen.fill(cx - half_w, cy - half_h, cx + half_w, cy + half_h, HexColor(logo.BACKGROUND))
    color = HexColor(logo.COLOR)
    c = pen.c
    c.setFillColor(color)
    for polygon in logo.hexagons():
        path = c.beginPath()
        for i, (ux, uy) in enumerate(polygon):
            point = (pen.x(cx + ux * scale), pen.y(cy + uy * scale))
            path.moveTo(*point) if i == 0 else path.lineTo(*point)
        path.close()
        c.drawPath(path, stroke=0, fill=1)
    for x1, y1, x2, y2 in logo.BARS:
        pen.fill(cx + x1 * scale, cy + y1 * scale, cx + x2 * scale, cy + y2 * scale, color)
    c.setFillColor(black)


def _letterhead(pen: Pen, claim: Claim) -> None:
    _draw_logo(pen)
    baseline = pen.y(95.0) - FS_TITLE * CAP_CENTER
    end = pen.text_at(config.COMPANY_NAME, 274.0, baseline, FS_TITLE, pen.bold)
    pen.text_at(config.COMPANY_REG_NO, end + 4.0, baseline, FS_REG_NO, pen.regular)
    pen.hline(LEFT, RIGHT, 134.0)

    pen.band(134.0, 156.0, config.FORM_TITLE)

    left = (("NAME :", claim.name), ("DEPT :", claim.dept))
    right = (
        ("MONTH ENDING :", claim.month_name),
        ("VEHICLE NO :", claim.vehicle_no),
        ("VEHICLE MODEL :", claim.vehicle_model),
    )
    for (label, value), cy in zip(left, INFO_ROWS):
        pen.text(label, 146.0, cy, FS_LABEL, bold=True, align="right")
        pen.text(value, 149.0, cy, FS_LABEL, max_width=395.0 - 152.0)
        pen.hline(145.0, 395.0, cy + INFO_RULE_OFFSET, LINE_RULE)
    for (label, value), cy in zip(right, INFO_ROWS):
        pen.text(label, 613.0, cy, FS_LABEL, bold=True, align="right")
        pen.text(value, 616.0, cy, FS_LABEL, max_width=RIGHT - 620.0)
        pen.hline(612.0, RIGHT, cy + INFO_RULE_OFFSET, LINE_RULE)

    pen.band(237.0, T_HEAD_TOP, "TRAVEL DETAILS")


def _travel_table(pen: Pen, claim: Claim, total_label_value: str) -> None:
    c0, c1, c2, c3, c4, c5 = T_COLS
    head_cy = (T_HEAD_TOP + T_HEAD_BOTTOM) / 2
    pen.text("DATE", (c0 + c1) / 2, head_cy, FS_BODY, bold=True, align="center")
    pen.text("LOCATION VISITED", (c1 + c2) / 2, head_cy, FS_BODY, bold=True, align="center")
    pen.text("TIME", (c2 + c4) / 2, (T_HEAD_TOP + T_HEAD_MID) / 2, FS_BODY, bold=True, align="center")
    sub_cy = (T_HEAD_MID + T_HEAD_BOTTOM) / 2
    pen.text("START", (c2 + c3) / 2, sub_cy, FS_BODY, bold=True, align="center")
    pen.text("FINISH", (c3 + c4) / 2, sub_cy, FS_BODY, bold=True, align="center")
    for i, word in enumerate(("DISTANCE", "TRAVELLED", "(KM)")):
        pen.text(word, (c4 + c5) / 2, 267.0 + i * 12.0, FS_BODY, bold=True, align="center")

    # grid
    pen.hline(c2, c4, T_HEAD_MID)
    for i in range(T_ROWS + 1):
        pen.hline(LEFT, RIGHT, T_HEAD_BOTTOM + i * T_ROW_H)
    pen.hline(LEFT, RIGHT, T_TOTAL_BOTTOM)
    for x in (c1, c2, c4):
        pen.vline(x, T_HEAD_TOP, T_BODY_BOTTOM)
    pen.vline(c3, T_HEAD_MID, T_BODY_BOTTOM)
    pen.vline(c4, T_BODY_BOTTOM, T_TOTAL_BOTTOM)

    # rows
    for i, trip in enumerate(claim.travel[:T_ROWS]):
        cy = T_HEAD_BOTTOM + i * T_ROW_H + T_ROW_H / 2
        pen.text(fmt_date(trip.date), c0 + 3.5, cy, FS_BODY, max_width=c1 - c0 - 6)
        pen.text(trip.location, c1 + 4.0, cy, FS_BODY, max_width=c2 - c1 - 8)
        pen.text(fmt_time(trip.start), (c2 + c3) / 2, cy, FS_BODY, align="center")
        pen.text(fmt_time(trip.finish), (c3 + c4) / 2, cy, FS_BODY, align="center")
        pen.text(fmt_km_cell(trip.distance), (c4 + c5) / 2, cy, FS_BODY, align="center", max_width=c5 - c4 - 6)

    total_cy = (T_BODY_BOTTOM + T_TOTAL_BOTTOM) / 2
    pen.text("TOTAL (KM) TRAVELLED", c4 - 8.0, total_cy, FS_BODY, bold=True, align="right")
    pen.text(total_label_value, (c4 + c5) / 2, total_cy, FS_BODY, bold=True, align="center")


def _mileage_values(claim: Claim, empty: str) -> tuple[str, str]:
    """(car km, motorcycle km) - only the selected vehicle carries the distance."""
    km = fmt_money(claim.total_km) if claim.travel else empty
    return (km, empty) if claim.vehicle_type == "car" else (empty, km)


# ---------------------------------------------------------------------------
# Page 1 - main form
# ---------------------------------------------------------------------------
SUMMARY_ROWS_Y = (906.0, 925.4, 944.8, 964.2, 983.6)
SUMMARY_TOTAL_Y = 1003.0
SIG_TOP, SIG_BOTTOM = 1020.0, 1142.0
SIG_COLS = (45.0, 255.0, 460.0, 670.0, 879.0)


def _page_main(pen: Pen, claim: Claim) -> None:
    _letterhead(pen, claim)
    _travel_table(pen, claim, fmt_km_total(claim.total_km) if claim.travel else "")

    # ---- mileage claim rates
    pen.text("MILEAGE CLAIM RATES", MID, 784.0, FS_BODY, bold=True, align="center", underline=True)
    end = pen.text("CAR", 117.0, 803.0, FS_BODY, bold=True)
    pen.text(f" @ 1st {fmt_number(config.CAR_RATE_TIER_KM)} x {fmt_rate(config.CAR_RATE)} per KM",
             end, 803.0, FS_BODY)
    pen.text("MOTORCYCLE", 117.0, 823.0, FS_BODY, bold=True)

    car_km, moto_km = _mileage_values(claim, empty="")
    travel_claim = fmt_money(claim.travel_claim) if claim.travel else ""
    lines = (
        (f"KM X RM {fmt_rate(config.CAR_RATE)}", 803.0, 813.0, car_km),
        (f"KM X RM {fmt_rate(config.MOTORCYCLE_RATE)}", 823.0, 836.0, moto_km),
        ("TOTAL TRAVELLED CLAIM (RM)", 850.0, 859.0, travel_claim),
    )
    for label, cy, rule_y, value in lines:
        pen.text(label, 706.0, cy, FS_BODY, bold=True, align="right")
        pen.hline(715.0, RIGHT, rule_y, LINE_RULE)
        pen.text(value, 797.0, rule_y - 8.0, FS_BODY, align="center")

    # ---- claim summary
    pen.band(866.0, 889.0, "CLAIM SUMMARY")
    summary = (
        ("A. TRAVEL CLAIM", claim.travel_claim),
        ("B. ENTERTAINMENT", claim.entertainment_total),
        ("C. PARKING FEES", claim.parking_total),
        ("D. SUBSISTENCE ALLOWANCE", claim.subsistence_total),
        ("E. MISCELLANEOUS", claim.misc_total),
    )
    for (label, amount), cy in zip(summary, SUMMARY_ROWS_Y):
        _summary_line(pen, label, 116.0, cy, fmt_money_or_blank(amount))
    _summary_line(pen, "TOTAL CLAIM", 143.0, SUMMARY_TOTAL_Y, fmt_money(claim.total_claim))

    # ---- signatures
    pen.hline(LEFT, RIGHT, SIG_TOP)
    for x in SIG_COLS[1:-1]:
        pen.vline(x, SIG_TOP, SIG_BOTTOM)
    heads = ("PREPARE BY :", "CHECKED BY :", "APPROVED BY :", "(FOR HR DEPT. USE ONLY)")
    for x, head in zip(SIG_COLS, heads):
        pen.text(head, x + 5.0, 1031.0, FS_SIGN, bold=True)
    roles = ("TEAM LEADER/SUPERVISOR", "DEPARTMENT HEAD", "HR PERSONNEL")
    for (x1, x2), role in zip(zip(SIG_COLS[1:], SIG_COLS[2:]), roles):
        pen.text(role, (x1 + x2) / 2, 1119.0, FS_ROLE, bold=True, align="center")
    if claim.signature_png:
        _draw_signature(pen, claim.signature_png)

    pen.frame(45.0, SIG_BOTTOM)


def _summary_line(pen: Pen, label: str, label_x: float, cy: float, value: str) -> None:
    pen.text(label, label_x, cy, FS_LABEL, bold=True)
    pen.text("RM", 332.0, cy, FS_LABEL, bold=True)
    pen.hline(385.0, 595.0, cy + 9.5, LINE_RULE)
    pen.text(value, 490.0, cy, FS_LABEL, align="center")


def _draw_signature(pen: Pen, png: bytes) -> None:
    """Fit the signature inside the PREPARE BY box (below its caption)."""
    img = ImageReader(io.BytesIO(png))
    iw, ih = img.getSize()
    max_w, max_h = 180.0 * SX, 70.0 * SY
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    cx, cy = pen.x(150.0), pen.y(1080.0)
    pen.c.drawImage(img, cx - w / 2, cy - h / 2, w, h, mask="auto")


# ---------------------------------------------------------------------------
# Page 2 - entertainment / toll & parking / subsistence / miscellaneous
# ---------------------------------------------------------------------------
P2_TOP = 25.0
P2_BAND_H, P2_HEAD_H, P2_ROW_H, P2_GAP = 24.0, 22.0, 19.42, 9.0
AMOUNT_X1, AMOUNT_X2 = 753.0, 879.0

DETAIL_SECTIONS = (
    ("ENTERTAINMENT", "entertainment",
     ((45.0, 137.0, "DATE"), (137.0, 271.0, "NAME OF CLIENT"),
      (271.0, 753.0, "REASON FOR ENTERTAINMENT"), (753.0, 879.0, "AMOUNT")),
     "TOTAL ENTERTAINMENT CLAIM (RM)"),
    ("TOLL & PARKING FEES", "parking",
     ((45.0, 137.0, "DATE"), (137.0, 753.0, "LOCATION"), (753.0, 879.0, "AMOUNT")),
     "TOTAL PARKING FEES (RM)"),
    ("SUBSISTENCE ALLOWANCE", "subsistence",
     ((45.0, 137.0, "DATE"), (137.0, 753.0, "REASONS FOR ALLOWANCE CLAIM"), (753.0, 879.0, "AMOUNT")),
     "TOTAL SUBSISTENCE ALLOWANCE (RM)"),
    ("MISCELLANEOUS", "misc",
     ((45.0, 137.0, "DATE"), (137.0, 753.0, "DESCRIPTION OF EXPENSES"), (753.0, 879.0, "AMOUNT")),
     "TOTAL MISCELLANEOUS EXPENSES (RM)"),
)


def _page_details(pen: Pen, claim: Claim) -> None:
    y = P2_TOP
    for index, (title, key, cols, total_label) in enumerate(DETAIL_SECTIONS):
        if index:
            y += P2_GAP
        y = _detail_section(pen, y, title, cols, getattr(claim, key), config.CAPACITY[key],
                            total_label, claim.section_total(key))
    pen.frame(P2_TOP, y)


def _detail_section(pen: Pen, top: float, title: str, cols, rows: list[ExpenseEntry],
                    capacity: int, total_label: str, total: Decimal) -> float:
    pen.band(top, top + P2_BAND_H, title)
    head_top = top + P2_BAND_H
    body_top = head_top + P2_HEAD_H
    body_bottom = body_top + capacity * P2_ROW_H
    total_bottom = body_bottom + P2_ROW_H

    for x1, x2, label in cols:
        pen.text(label, (x1 + x2) / 2, (head_top + body_top) / 2, FS_BODY, bold=True, align="center")
    for i in range(capacity + 1):
        pen.hline(LEFT, RIGHT, body_top + i * P2_ROW_H)
    pen.hline(LEFT, RIGHT, total_bottom)
    for x1, _, _ in cols[1:]:
        pen.vline(x1, head_top, body_bottom)
    pen.vline(AMOUNT_X1, body_bottom, total_bottom)

    with_client = len(cols) == 4
    for i, row in enumerate(rows[:capacity]):
        cy = body_top + i * P2_ROW_H + P2_ROW_H / 2
        pen.text(fmt_date(row.date), 48.5, cy, FS_BODY, max_width=137.0 - 48.5 - 3)
        if with_client:
            pen.text(row.client, 141.0, cy, FS_BODY, max_width=271.0 - 141.0 - 4)
            pen.text(row.description, 275.0, cy, FS_BODY, max_width=AMOUNT_X1 - 275.0 - 4)
        else:
            pen.text(row.description, 141.0, cy, FS_BODY, max_width=AMOUNT_X1 - 141.0 - 4)
        pen.text(fmt_money(row.amount), (AMOUNT_X1 + AMOUNT_X2) / 2, cy, FS_BODY, align="center",
                 max_width=AMOUNT_X2 - AMOUNT_X1 - 6)

    total_cy = (body_bottom + total_bottom) / 2
    pen.text(total_label, AMOUNT_X1 - 8.0, total_cy, FS_BODY, bold=True, align="right")
    pen.text(fmt_money_or_blank(total), (AMOUNT_X1 + AMOUNT_X2) / 2, total_cy, FS_BODY, bold=True,
             align="center", max_width=AMOUNT_X2 - AMOUNT_X1 - 6)
    return total_bottom


# ---------------------------------------------------------------------------
# Page 3 - travel detail sheet
# ---------------------------------------------------------------------------
def _page_travel_sheet(pen: Pen, claim: Claim) -> None:
    _letterhead(pen, claim)
    _travel_table(pen, claim, fmt_money(claim.total_km))

    pen.text("MILEAGE CLAIM RATES", MID, 784.0, FS_BODY, bold=True, align="center")
    car_km, moto_km = _mileage_values(claim, empty="0")
    if not claim.travel:
        car_km = moto_km = "0"
    lines = (
        (f"CAR@1st {fmt_number(config.CAR_RATE_TIER_KM)}Km X RM {fmt_rate(config.CAR_RATE)} per Km",
         811.0, 821.0, car_km),
        (f"MOTORCYCLE X RM{fmt_rate(config.MOTORCYCLE_RATE)} per Km", 834.0, 844.0, moto_km),
        ("TOTAL TRAVELLED CLAIM (RM)", 857.0, 867.0, fmt_money(claim.travel_claim)),
    )
    for label, cy, rule_y, value in lines:
        pen.text(label, 680.0, cy, FS_BODY, bold=True, align="right")
        pen.hline(690.0, RIGHT, rule_y, LINE_RULE)
        pen.text(value, 872.0, rule_y - 8.0, FS_BODY, bold=True, align="right")

    pen.frame(45.0, 885.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_form(claim: Claim) -> bytes:
    """Render the claim form pages (no attachments) and return PDF bytes."""
    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=A4, pageCompression=1)
    canvas.setTitle(f"Travelling & Entertainment Claim - {claim.name} - {claim.month_name} {claim.year}")
    canvas.setAuthor(claim.name)
    canvas.setSubject(config.FORM_TITLE.title())
    canvas.setCreator("DBT Claim Form Generator")

    pen = Pen(canvas)
    _page_main(pen, claim)
    canvas.showPage()
    _page_details(pen, claim)
    canvas.showPage()
    if claim.include_travel_sheet:
        _page_travel_sheet(pen, claim)
        canvas.showPage()
    canvas.save()
    return buf.getvalue()
