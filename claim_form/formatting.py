"""Value formatting exactly as it appears on the original claim form."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal


def fmt_date(value: date) -> str:
    """22/10/2026"""
    return value.strftime("%d/%m/%Y")


def fmt_time(value: time) -> str:
    """0900 H"""
    return f"{value:%H%M} H"


def fmt_number(value: Decimal) -> str:
    """Plain number without trailing zeros: 32 -> '32', 12.50 -> '12.5'."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def fmt_km_cell(value: Decimal) -> str:
    """Distance in a travel row: '32KM' (no space, as on the form)."""
    return f"{fmt_number(value)}KM"


def fmt_km_total(value: Decimal) -> str:
    """Total distance on page 1: '147 KM'."""
    return f"{fmt_number(value)} KM"


def fmt_money(value: Decimal) -> str:
    """'73.50', '1,234.50'"""
    return format(value, ",.2f")


def fmt_money_or_blank(value: Decimal) -> str:
    """Zero amounts are left blank on the form (e.g. B. ENTERTAINMENT)."""
    return "" if value == 0 else fmt_money(value)


def fmt_rate(value: Decimal) -> str:
    """'0.70'"""
    return format(value, ".2f")
