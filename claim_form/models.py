"""Claim domain model, calculations and request validation.

All money/distance arithmetic uses ``Decimal`` with ROUND_HALF_UP to the sen,
so totals are exact (no floating point drift).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

from . import config
from .images import ImageError, prepare_signature

CENT = Decimal("0.01")
ZERO = Decimal("0")

_NUMBER_RE = re.compile(r"^\d{1,9}(\.\d{1,2})?$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):?([0-5]\d)(:[0-5]\d)?$")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def mileage_claim(total_km: Decimal, vehicle_type: str) -> Decimal:
    """Mileage reimbursement for the month."""
    if total_km <= 0:
        return round_money(ZERO)
    if vehicle_type == "car":
        first = min(total_km, config.CAR_RATE_TIER_KM)
        beyond = total_km - first
        return round_money(first * config.CAR_RATE + beyond * config.CAR_RATE_BEYOND_TIER)
    return round_money(total_km * config.MOTORCYCLE_RATE)


class ValidationError(Exception):
    """Carries ``{field_path: message}``. Paths look like ``travel.2.distance``."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid claim data")
        self.errors = errors


@dataclass(frozen=True)
class TravelEntry:
    date: date
    location: str
    start: time
    finish: time
    distance: Decimal


@dataclass(frozen=True)
class ExpenseEntry:
    date: date
    description: str
    amount: Decimal
    client: str = ""  # entertainment only


@dataclass
class Claim:
    name: str
    dept: str
    month: int
    year: int
    vehicle_no: str
    vehicle_model: str
    vehicle_type: str
    travel: list[TravelEntry] = field(default_factory=list)
    entertainment: list[ExpenseEntry] = field(default_factory=list)
    parking: list[ExpenseEntry] = field(default_factory=list)
    subsistence: list[ExpenseEntry] = field(default_factory=list)
    misc: list[ExpenseEntry] = field(default_factory=list)
    signature_png: bytes | None = None
    include_travel_sheet: bool = True

    # ---- derived values -------------------------------------------------
    @property
    def month_name(self) -> str:
        return config.MONTHS[self.month - 1]

    @property
    def total_km(self) -> Decimal:
        return sum((t.distance for t in self.travel), ZERO)

    @property
    def travel_claim(self) -> Decimal:
        return mileage_claim(self.total_km, self.vehicle_type)

    def section_total(self, key: str) -> Decimal:
        rows: list[ExpenseEntry] = getattr(self, key)
        return round_money(sum((r.amount for r in rows), ZERO))

    @property
    def entertainment_total(self) -> Decimal:
        return self.section_total("entertainment")

    @property
    def parking_total(self) -> Decimal:
        return self.section_total("parking")

    @property
    def subsistence_total(self) -> Decimal:
        return self.section_total("subsistence")

    @property
    def misc_total(self) -> Decimal:
        return self.section_total("misc")

    @property
    def total_claim(self) -> Decimal:
        return (
            self.travel_claim
            + self.entertainment_total
            + self.parking_total
            + self.subsistence_total
            + self.misc_total
        )

    @property
    def filename(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", self.name).strip("_") or "Claim"
        return f"DBT_Claim_{slug}_{self.month:02d}{self.year}.pdf"


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self) -> None:
        self.errors: dict[str, str] = {}

    def error(self, path: str, message: str) -> None:
        self.errors.setdefault(path, message)

    @staticmethod
    def _raw(value: Any) -> str:
        return "" if value is None else str(value).strip()

    def text(self, value: Any, path: str, label: str, *, max_len: int,
             required: bool = True, upper: bool = False) -> str:
        text = " ".join(self._raw(value).split())  # collapse newlines / double spaces
        if upper:
            text = text.upper()
        if required and not text:
            self.error(path, f"{label} is required.")
        elif len(text) > max_len:
            self.error(path, f"{label} must be {max_len} characters or fewer.")
        return text

    def integer(self, value: Any, path: str, label: str, lo: int, hi: int) -> int:
        raw = self._raw(value)
        try:
            number = int(raw)
        except ValueError:
            self.error(path, f"{label} is required.")
            return lo
        if not lo <= number <= hi:
            self.error(path, f"{label} must be between {lo} and {hi}.")
            return lo
        return number

    def date(self, value: Any, path: str) -> date | None:
        raw = self._raw(value)
        if not raw:
            self.error(path, "Date is required.")
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt).date()
                break
            except ValueError:
                continue
        else:
            self.error(path, "Enter a valid date.")
            return None
        if not config.MIN_YEAR <= parsed.year <= config.MAX_YEAR:
            self.error(path, "Enter a valid date.")
            return None
        return parsed

    def time(self, value: Any, path: str, label: str) -> time | None:
        raw = self._raw(value)
        if not raw:
            self.error(path, f"{label} time is required.")
            return None
        match = _TIME_RE.match(raw)
        if not match:
            self.error(path, f"{label} time must look like 09:00.")
            return None
        return time(int(match.group(1)), int(match.group(2)))

    def decimal(self, value: Any, path: str, label: str, max_value: Decimal) -> Decimal | None:
        raw = self._raw(value).replace(",", "").replace(" ", "")
        if raw.upper().startswith("RM"):
            raw = raw[2:]
        if not raw:
            self.error(path, f"{label} is required.")
            return None
        if not _NUMBER_RE.match(raw):
            self.error(path, f"{label} must be a number with up to 2 decimals.")
            return None
        number = Decimal(raw)
        if number <= 0:
            self.error(path, f"{label} must be greater than 0.")
            return None
        if number > max_value:
            self.error(path, f"{label} cannot exceed {format(max_value, ',f')}.")
            return None
        return number


def _parse_section(p: _Parser, payload: dict, key: str,
                   parse_row: Callable[[_Parser, dict, str], Any]) -> list:
    raw_rows = payload.get(key) or []
    if not isinstance(raw_rows, list):
        p.error(key, "Invalid rows.")
        return []

    blank_keys = config.SECTION_BY_KEY[key]["blank_keys"]
    entries, used = [], 0
    for index, raw in enumerate(raw_rows):
        path = f"{key}.{index}"
        if not isinstance(raw, dict):
            p.error(path, "Invalid row.")
            continue
        # A line that has none of its meaningful fields filled is ignored.
        if all(not _Parser._raw(raw.get(k)) for k in blank_keys):
            continue
        used += 1
        errors_before = len(p.errors)
        entry = parse_row(p, raw, path)
        if len(p.errors) == errors_before:
            entries.append(entry)

    capacity = config.CAPACITY[key]
    if used > capacity:
        p.error(key, f"The printed form has room for {capacity} lines here; you entered {used}.")
    return entries


def _text_field(p: _Parser, raw: dict, path: str, section: str, key: str) -> str:
    f = config.field_def(section, key)
    return p.text(raw.get(key), f"{path}.{key}", f["label"], max_len=f["maxlength"])


def _travel_row(p: _Parser, raw: dict, path: str) -> TravelEntry:
    return TravelEntry(
        date=p.date(raw.get("date"), f"{path}.date"),
        location=_text_field(p, raw, path, "travel", "location"),
        start=p.time(raw.get("start"), f"{path}.start", "Start"),
        finish=p.time(raw.get("finish"), f"{path}.finish", "Finish"),
        distance=p.decimal(raw.get("distance"), f"{path}.distance", "Distance", config.MAX_DISTANCE),
    )


def _expense_row(section: str, text_key: str, with_client: bool = False):
    def parse(p: _Parser, raw: dict, path: str) -> ExpenseEntry:
        return ExpenseEntry(
            date=p.date(raw.get("date"), f"{path}.date"),
            client=_text_field(p, raw, path, section, "client") if with_client else "",
            description=_text_field(p, raw, path, section, text_key),
            amount=p.decimal(raw.get("amount"), f"{path}.amount", "Amount", config.MAX_AMOUNT),
        )
    return parse


def parse_claim(payload: Any) -> Claim:
    """Validate a JSON payload from the web form and build a :class:`Claim`.

    Raises :class:`ValidationError` with every problem found (not just the first).
    """
    if not isinstance(payload, dict):
        raise ValidationError({"form": "The form data could not be read."})

    p = _Parser()

    def header(key: str, required: bool = True) -> str:
        label, max_len = config.HEADER_FIELDS[key]
        return p.text(payload.get(key), key, label, max_len=max_len, required=required, upper=True)

    name = header("name")
    dept = header("dept")
    month = p.integer(payload.get("month"), "month", "Month", 1, 12)
    year = p.integer(payload.get("year"), "year", "Year", config.MIN_YEAR, config.MAX_YEAR)

    vehicle_type = _Parser._raw(payload.get("vehicle_type")).lower() or config.DEFAULT_VEHICLE_TYPE
    if vehicle_type not in config.VEHICLE_TYPES:
        p.error("vehicle_type", "Choose motorcycle or car.")
        vehicle_type = config.DEFAULT_VEHICLE_TYPE

    travel = _parse_section(p, payload, "travel", _travel_row)
    has_trips = any(
        isinstance(r, dict) and any(_Parser._raw(r.get(k)) for k in config.SECTION_BY_KEY["travel"]["blank_keys"])
        for r in (payload.get("travel") or [])
    )
    # Vehicle details only matter (and are only required) when mileage is claimed.
    vehicle_no = header("vehicle_no", required=has_trips)
    vehicle_model = header("vehicle_model", required=has_trips)

    entertainment = _parse_section(p, payload, "entertainment", _expense_row("entertainment", "reason", True))
    parking = _parse_section(p, payload, "parking", _expense_row("parking", "location"))
    subsistence = _parse_section(p, payload, "subsistence", _expense_row("subsistence", "reason"))
    misc = _parse_section(p, payload, "misc", _expense_row("misc", "description"))

    if not p.errors and not (travel or entertainment or parking or subsistence or misc):
        p.error("form", "Add at least one trip or expense before generating the PDF.")

    signature_png = None
    signature = payload.get("signature")
    if isinstance(signature, str) and signature.strip():
        try:
            signature_png = prepare_signature(signature)
        except ImageError as exc:
            p.error("signature", str(exc))

    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    include_travel_sheet = options.get("include_travel_sheet", True) is not False

    if p.errors:
        raise ValidationError(p.errors)

    return Claim(
        name=name,
        dept=dept,
        month=month,
        year=year,
        vehicle_no=vehicle_no,
        vehicle_model=vehicle_model,
        vehicle_type=vehicle_type,
        travel=travel,
        entertainment=entertainment,
        parking=parking,
        subsistence=subsistence,
        misc=misc,
        signature_png=signature_png,
        include_travel_sheet=include_travel_sheet,
    )
