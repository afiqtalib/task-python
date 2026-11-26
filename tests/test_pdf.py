import base64
import io

from PIL import Image, ImageDraw
from pypdf import PdfReader

from claim_form import build_claim_pdf, parse_claim
from claim_form.pdf.attachments import Attachment


def _text(pdf: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]


def test_sample_pdf_content(sample):
    pdf = build_claim_pdf(parse_claim(sample))
    pages = _text(pdf)
    assert len(pages) == 3

    p1 = pages[0]
    for expected in [
        "DBT TECHNOLOGIES SDN BHD", "(Co. No. 1061917-U)", "TRAVELLING & ENTERTAINMENT CLAIM FORM",
        "NAME :", "MUHAMMAD", "DEPT :", "EPPP", "MONTH ENDING :", "OCTOBER", "VEHICLE NO :", "DBS 2580",
        "VEHICLE MODEL :", "HONDA", "27/10/2026", "29/10/2026",
        "Office > Institut Latihan Dewan Bandaraya Kuala Lumpur > Office", "Office > Menara DBKL 3 > Office",
        "0900 H", "1800 H", "32KM", "19KM", "TOTAL (KM) TRAVELLED", "51 KM",
        "MILEAGE CLAIM RATES", "@ 1st 300 x 0.70 per KM", "KM X RM 0.70", "KM X RM 0.50", "51.00",
        "TOTAL TRAVELLED CLAIM (RM)", "25.50", "A. TRAVEL CLAIM", "E. MISCELLANEOUS", "75.00",
        "TOTAL CLAIM", "100.50", "PREPARE BY :", "TEAM LEADER/SUPERVISOR", "DEPARTMENT HEAD",
        "(FOR HR DEPT. USE ONLY)", "HR PERSONNEL",
    ]:
        assert expected in p1, expected
    for removed in ("22/10/2026", "23/10/2026", "26/10/2026", "0959 H"):
        assert removed not in p1, removed

    p2 = pages[1]
    for expected in ["ENTERTAINMENT", "TOLL & PARKING FEES", "SUBSISTENCE ALLOWANCE", "MISCELLANEOUS",
                     "20/10/2026", "MEDICAL BILL", "TOTAL MISCELLANEOUS EXPENSES (RM)", "75.00"]:
        assert expected in p2, expected

    p3 = pages[2]
    for expected in ["CAR@1st 300Km X RM 0.70 per Km", "MOTORCYCLE X RM0.50 per Km", "51.00", "25.50"]:
        assert expected in p3, expected


def test_travel_sheet_is_optional(sample):
    sample["options"]["include_travel_sheet"] = False
    assert len(_text(build_claim_pdf(parse_claim(sample)))) == 2


def test_attachments_are_appended_in_order(sample, png_bytes, two_page_pdf):
    claim = parse_claim(sample)
    pdf = build_claim_pdf(claim, [
        Attachment("bill.pdf", "pdf", two_page_pdf),
        Attachment("receipt.png", "image", png_bytes),
    ])
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 3 + 2 + 1
    assert "Attachment page 1" in reader.pages[3].extract_text()
    assert "Attachment page 2" in reader.pages[4].extract_text()
    # landscape photo -> landscape page
    box = reader.pages[5].mediabox
    assert float(box.width) > float(box.height)
    assert reader.metadata.title.startswith("Travelling & Entertainment Claim")


def test_long_text_and_large_values_render(sample):
    sample["travel"][0]["location"] = ("Office > " + "Wisma Very Long Destination Name " * 4)[:91] + " > Office"
    assert len(sample["travel"][0]["location"]) == 100  # the maximum the form accepts
    sample["misc"][0]["amount"] = "99999.99"
    pdf = build_claim_pdf(parse_claim(sample))
    pages = _text(pdf)
    assert "> Office" in pages[0]  # shrunk to fit, not cut off
    assert "99,999.99" in pages[1]


def test_signature_is_embedded(sample):
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(40, 150), (200, 40), (380, 160), (560, 60)], fill=(20, 30, 60, 255), width=6)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    sample["signature"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    claim = parse_claim(sample)
    assert claim.signature_png
    pdf = build_claim_pdf(claim)
    assert len(PdfReader(io.BytesIO(pdf)).pages[0].images) == 1


def test_blank_signature_is_ignored(sample):
    buf = io.BytesIO()
    Image.new("RGBA", (300, 100), (0, 0, 0, 0)).save(buf, "PNG")
    sample["signature"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    assert parse_claim(sample).signature_png is None
