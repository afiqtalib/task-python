"""Central configuration.

Everything printed on the PDF *and* everything the web form needs to know
(rates, row capacities, field limits) is defined here once, so the browser's
live totals and the generated PDF can never disagree.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Answered by /api/ping so the desktop launcher can recognise a running copy.
APP_ID = "dbt-claim-form"

# --------------------------------------------------------------------------
# Company / form identity (printed exactly as on the paper form)
# --------------------------------------------------------------------------
COMPANY_NAME = "DBT TECHNOLOGIES SDN BHD"
COMPANY_REG_NO = "(Co. No. 1061917-U)"
FORM_TITLE = "TRAVELLING & ENTERTAINMENT CLAIM FORM"

# Drop the official logo here (transparent PNG preferred) and it will be used
# instead of the built-in vector replica.
LOGO_FILE = BASE_DIR / "static" / "img" / "company-logo.png"

# Arial is what the original (Excel-exported) form uses. If the files are not
# present the renderer falls back to Helvetica, which has identical metrics.
FONT_REGULAR_FILE = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD_FILE = Path(r"C:\Windows\Fonts\arialbd.ttf")

# --------------------------------------------------------------------------
# Mileage policy (RM per KM)
# --------------------------------------------------------------------------
MOTORCYCLE_RATE = Decimal("0.50")
CAR_RATE = Decimal("0.70")
CAR_RATE_TIER_KM = Decimal("300")  # "CAR @ 1st 300 x 0.70 per KM"
# The printed form only states the car rate for the first 300 km.
# Confirm the rate beyond 300 km with HR / Finance and change it here.
CAR_RATE_BEYOND_TIER = Decimal("0.70")

VEHICLE_TYPES = ("motorcycle", "car")
DEFAULT_VEHICLE_TYPE = "motorcycle"

MONTHS = (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
)

# --------------------------------------------------------------------------
# Printed form capacity (number of lines on the paper form, per section).
# These are fixed by the layout of the original form - do not change.
# --------------------------------------------------------------------------
CAPACITY = {
    "travel": 23,
    "entertainment": 5,
    "parking": 23,
    "subsistence": 4,
    "misc": 11,
}

# --------------------------------------------------------------------------
# Input limits
# --------------------------------------------------------------------------
HEADER_FIELDS = {
    # key: (label, max length)
    "name": ("Name", 40),
    "dept": ("Department", 30),
    "vehicle_no": ("Vehicle no.", 15),
    "vehicle_model": ("Vehicle model", 30),
}
MAX_AMOUNT = Decimal("100000.00")   # per line, RM
MAX_DISTANCE = Decimal("5000")      # per trip, KM
MIN_YEAR, MAX_YEAR = 2000, 2100

MAX_ATTACHMENTS = 20
MAX_ATTACHMENT_MB = 15
MAX_ATTACHMENT_BYTES = MAX_ATTACHMENT_MB * 1024 * 1024
MAX_REQUEST_BYTES = 120 * 1024 * 1024
MAX_SIGNATURE_BYTES = 3 * 1024 * 1024
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
ATTACHMENT_EXTENSIONS = IMAGE_EXTENSIONS + (".pdf",)

# --------------------------------------------------------------------------
# Line-item sections. Drives the web form, the server-side parser and the
# summary letters (A-E) shown on page 1 of the PDF.
# --------------------------------------------------------------------------
_DATE = {"key": "date", "label": "Date", "type": "date"}
_AMOUNT = {"key": "amount", "label": "Amount (RM)", "type": "money", "placeholder": "0.00", "align": "right"}

SECTIONS = (
    {
        "key": "travel",
        "letter": "A",
        "title": "Travel details",
        "summary": "Travel claim",
        "hint": "One line per trip. Mileage is paid on the total distance.",
        "add_label": "Add trip",
        "columns": "9.6rem minmax(12rem, 1fr) 8.6rem 8.6rem 5.4rem",
        "blank_keys": ("date", "location", "distance"),
        "fields": (
            _DATE,
            {"key": "location", "label": "Location visited", "type": "text", "maxlength": 100,
             "placeholder": "Office > Destination > Office", "list": "location-options"},
            {"key": "start", "label": "Start", "type": "time"},
            {"key": "finish", "label": "Finish", "type": "time"},
            {"key": "distance", "label": "KM", "type": "distance", "placeholder": "0", "align": "right"},
        ),
    },
    {
        "key": "entertainment",
        "letter": "B",
        "title": "Entertainment",
        "summary": "Entertainment",
        "hint": "Client meals and hospitality.",
        "add_label": "Add entertainment",
        "columns": "9.6rem minmax(8rem, 0.7fr) minmax(10rem, 1fr) 7.2rem",
        "blank_keys": ("date", "client", "reason", "amount"),
        "fields": (
            _DATE,
            {"key": "client", "label": "Name of client", "type": "text", "maxlength": 30},
            {"key": "reason", "label": "Reason for entertainment", "type": "text", "maxlength": 100},
            _AMOUNT,
        ),
    },
    {
        "key": "parking",
        "letter": "C",
        "title": "Toll & parking fees",
        "summary": "Parking fees",
        "hint": "Toll and parking paid during claimable trips.",
        "add_label": "Add toll / parking",
        "columns": "9.6rem minmax(12rem, 1fr) 7.2rem",
        "blank_keys": ("date", "location", "amount"),
        "fields": (
            _DATE,
            {"key": "location", "label": "Location", "type": "text", "maxlength": 110, "list": "location-options"},
            _AMOUNT,
        ),
    },
    {
        "key": "subsistence",
        "letter": "D",
        "title": "Subsistence allowance",
        "summary": "Subsistence allowance",
        "hint": "Meal / outstation allowance.",
        "add_label": "Add allowance",
        "columns": "9.6rem minmax(12rem, 1fr) 7.2rem",
        "blank_keys": ("date", "reason", "amount"),
        "fields": (
            _DATE,
            {"key": "reason", "label": "Reasons for allowance claim", "type": "text", "maxlength": 110},
            _AMOUNT,
        ),
    },
    {
        "key": "misc",
        "letter": "E",
        "title": "Miscellaneous",
        "summary": "Miscellaneous",
        "hint": "Medical bills and other expenses.",
        "add_label": "Add expense",
        "columns": "9.6rem minmax(12rem, 1fr) 7.2rem",
        "blank_keys": ("date", "description", "amount"),
        "fields": (
            _DATE,
            {"key": "description", "label": "Description of expenses", "type": "text", "maxlength": 110},
            _AMOUNT,
        ),
    },
)

SECTION_BY_KEY = {s["key"]: s for s in SECTIONS}


def field_def(section: str, key: str) -> dict:
    for f in SECTION_BY_KEY[section]["fields"]:
        if f["key"] == key:
            return f
    raise KeyError(f"{section}.{key}")


def client_config() -> dict:
    """The subset of configuration the browser needs (JSON-serialisable)."""
    return {
        "months": MONTHS,
        "rates": {
            "motorcycle": str(MOTORCYCLE_RATE),
            "car": str(CAR_RATE),
            "carTierKm": str(CAR_RATE_TIER_KM),
            "carBeyondTier": str(CAR_RATE_BEYOND_TIER),
        },
        "headerFields": {k: {"label": v[0], "maxlength": v[1]} for k, v in HEADER_FIELDS.items()},
        "sections": [
            {
                "key": s["key"],
                "letter": s["letter"],
                "title": s["title"],
                "summary": s["summary"],
                "hint": s["hint"],
                "add_label": s["add_label"],
                "columns": s["columns"],
                "capacity": CAPACITY[s["key"]],
                "blankKeys": list(s["blank_keys"]),
                "fields": [dict(f) for f in s["fields"]],
            }
            for s in SECTIONS
        ],
        "attachments": {
            "max": MAX_ATTACHMENTS,
            "maxMb": MAX_ATTACHMENT_MB,
            "extensions": list(ATTACHMENT_EXTENSIONS),
        },
    }
