"""Receipts / supporting documents appended after the form pages."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable, Sequence

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .. import config
from ..images import ImageError, flatten_to_rgb, open_image
from ..models import ValidationError

PAGE_MARGIN = 24.0  # pt around attached images
MAX_IMAGE_SIDE = 2200  # px - keeps phone photos sharp but the PDF small


@dataclass(frozen=True)
class Attachment:
    filename: str
    kind: str  # "image" | "pdf"
    data: bytes


def _open_pdf(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ImageError("PDF is password protected")
        if len(reader.pages) == 0:
            raise ImageError("PDF has no pages")
        return reader
    except ImageError:
        raise
    except (PdfReadError, ValueError, OSError, KeyError, TypeError) as exc:
        raise ImageError("file is not a valid PDF") from exc


def read_uploads(files: Iterable) -> list[Attachment]:
    """Validate uploaded files (werkzeug ``FileStorage``) and load them in order."""
    uploads = [f for f in files if f is not None and f.filename]
    if len(uploads) > config.MAX_ATTACHMENTS:
        raise ValidationError({"attachments": f"Attach at most {config.MAX_ATTACHMENTS} files."})

    errors: dict[str, str] = {}
    attachments: list[Attachment] = []
    for index, upload in enumerate(uploads):
        name = PurePath(upload.filename).name
        ext = PurePath(name).suffix.lower()
        key = f"attachments.{index}"
        if ext not in config.ATTACHMENT_EXTENSIONS:
            errors[key] = f"{name}: only PDF, JPG, PNG or WEBP files can be attached."
            continue
        data = upload.read(config.MAX_ATTACHMENT_BYTES + 1)
        if len(data) > config.MAX_ATTACHMENT_BYTES:
            errors[key] = f"{name}: larger than {config.MAX_ATTACHMENT_MB} MB."
            continue
        if not data:
            errors[key] = f"{name}: file is empty."
            continue
        kind = "pdf" if ext == ".pdf" else "image"
        try:
            _open_pdf(data) if kind == "pdf" else open_image(data)
        except ImageError as exc:
            errors[key] = f"{name}: {exc}."
            continue
        attachments.append(Attachment(name, kind, data))

    if errors:
        raise ValidationError(errors)
    return attachments


def image_to_pdf(data: bytes) -> bytes:
    """One A4 page (orientation follows the photo) with the image fitted and centred."""
    img = flatten_to_rgb(open_image(data))
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    jpeg = io.BytesIO()
    img.save(jpeg, "JPEG", quality=85, optimize=True)
    jpeg.seek(0)

    page_w, page_h = landscape(A4) if img.width > img.height else A4
    scale = min((page_w - 2 * PAGE_MARGIN) / img.width, (page_h - 2 * PAGE_MARGIN) / img.height)
    w, h = img.width * scale, img.height * scale

    out = io.BytesIO()
    canvas = Canvas(out, pagesize=(page_w, page_h), pageCompression=1)
    canvas.drawImage(ImageReader(jpeg), (page_w - w) / 2, (page_h - h) / 2, w, h)
    canvas.showPage()
    canvas.save()
    return out.getvalue()


def merge(form_pdf: bytes, attachments: Sequence[Attachment]) -> bytes:
    """Append attachments (in the given order) after the form pages."""
    form_reader = PdfReader(io.BytesIO(form_pdf))
    writer = PdfWriter()
    writer.append(form_reader, import_outline=False)
    for attachment in attachments:
        source = image_to_pdf(attachment.data) if attachment.kind == "image" else attachment.data
        writer.append(_open_pdf(source), import_outline=False)

    metadata = {k: str(v) for k, v in (form_reader.metadata or {}).items()}
    if metadata:
        writer.add_metadata(metadata)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
