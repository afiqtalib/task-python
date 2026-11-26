import copy
import io
import sys
from pathlib import Path

import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claim_form.sample import SAMPLE_CLAIM  # noqa: E402


@pytest.fixture
def sample():
    return copy.deepcopy(SAMPLE_CLAIM)


@pytest.fixture
def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (240, 240, 240)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def two_page_pdf():
    buf = io.BytesIO()
    canvas = Canvas(buf)
    for n in (1, 2):
        canvas.drawString(72, 720, f"Attachment page {n}")
        canvas.showPage()
    canvas.save()
    return buf.getvalue()
