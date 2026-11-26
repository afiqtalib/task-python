from __future__ import annotations

from typing import Sequence

from ..models import Claim
from .attachments import Attachment, merge, read_uploads
from .renderer import render_form

__all__ = ["Attachment", "build_claim_pdf", "read_uploads", "render_form"]


def build_claim_pdf(claim: Claim, attachments: Sequence[Attachment] = ()) -> bytes:
    """Form pages followed by any receipts, as a single PDF."""
    form_pdf = render_form(claim)
    return merge(form_pdf, attachments) if attachments else form_pdf
