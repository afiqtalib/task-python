"""Image helpers: signature clean-up and safe image decoding."""
from __future__ import annotations

import base64
import binascii
import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from . import config

# Refuse decompression bombs early (a 60 MP photo is already very large).
Image.MAX_IMAGE_PIXELS = 60_000_000

_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,(?P<data>[A-Za-z0-9+/=\s]+)$")


class ImageError(ValueError):
    """Raised with a user-facing message when an image cannot be used."""


def open_image(data: bytes) -> Image.Image:
    """Decode and fully load an image, applying EXIF rotation (phone photos)."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError as exc:
        raise ImageError("image resolution is too large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageError("file is not a valid image") from exc
    return ImageOps.exif_transpose(img)


def flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Composite any transparency onto white and return an RGB image."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return img.convert("RGB")


def prepare_signature(data_url: str) -> bytes | None:
    """Turn a canvas/uploaded signature into a tightly-cropped transparent PNG.

    Light backgrounds (e.g. a photo of a signature on white paper) become
    transparent so the signature never hides the form's lines.
    Returns ``None`` when the image contains no ink.
    """
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ImageError("Signature must be a PNG, JPG or WEBP image.")
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", match.group("data")), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("Signature image is corrupted.") from exc
    if len(raw) > config.MAX_SIGNATURE_BYTES:
        raise ImageError("Signature image is too large (max 3 MB).")

    try:
        img = open_image(raw)
    except ImageError as exc:
        raise ImageError(f"Signature {exc}.") from exc

    rgb = flatten_to_rgb(img)
    # Ink strength from luminance: >= 225 is background, <= 150 is solid ink.
    gray = rgb.convert("L")
    alpha = gray.point(lambda v: 0 if v >= 225 else 255 if v <= 150 else int((225 - v) * 255 / 75))

    bbox = alpha.getbbox()
    if not bbox:
        return None

    pad = 6
    left, top, right, bottom = bbox
    bbox = (max(left - pad, 0), max(top - pad, 0), min(right + pad, rgb.width), min(bottom + pad, rgb.height))
    out = rgb.crop(bbox).convert("RGBA")
    out.putalpha(alpha.crop(bbox))
    out.thumbnail((900, 360), Image.LANCZOS)

    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
