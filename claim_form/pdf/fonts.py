"""Font registration (Arial, as used by the original form; Helvetica fallback)."""
from __future__ import annotations

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .. import config

_registered: tuple[str, str] | None = None


def fonts() -> tuple[str, str]:
    """Return ``(regular, bold)`` font names, registering Arial on first use."""
    global _registered
    if _registered is None:
        try:
            if not (config.FONT_REGULAR_FILE.is_file() and config.FONT_BOLD_FILE.is_file()):
                raise FileNotFoundError
            pdfmetrics.registerFont(TTFont("ClaimArial", str(config.FONT_REGULAR_FILE)))
            pdfmetrics.registerFont(TTFont("ClaimArial-Bold", str(config.FONT_BOLD_FILE)))
            _registered = ("ClaimArial", "ClaimArial-Bold")
        except Exception:  # missing / unreadable font -> metric-compatible fallback
            _registered = ("Helvetica", "Helvetica-Bold")
    return _registered
