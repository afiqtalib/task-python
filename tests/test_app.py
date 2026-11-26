import io
import json

import pytest
from pypdf import PdfReader

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Load sample data" in body and "Generate claim" in body and "Merge &amp; download" in body


def test_logo_svg(client):
    res = client.get("/logo.svg")
    assert res.status_code == 200 and res.mimetype == "image/svg+xml"
    body = res.get_data(as_text=True)
    assert body.count("<polygon") == 9      # 1-2-3-2-1 hexagons
    assert body.count("<rect") == 3         # the three joining bars
    assert "#60D4D3" in body


def test_sample_endpoint(client, sample):
    assert client.get("/api/sample").get_json() == sample


def test_generate_returns_inline_pdf(client, sample):
    res = client.post("/api/generate", data={"payload": json.dumps(sample)})
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert res.headers["X-Filename"] == "DBT_Claim_MUHAMMAD_102026.pdf"
    assert res.headers["Content-Disposition"].startswith("inline")
    assert len(PdfReader(io.BytesIO(res.data)).pages) == 3


def test_generate_validation_errors(client, sample):
    sample["name"] = ""
    sample["misc"][0]["amount"] = "abc"
    res = client.post("/api/generate", data={"payload": json.dumps(sample)})
    assert res.status_code == 422
    assert set(res.get_json()["errors"]) == {"name", "misc.0.amount"}


def test_generate_rejects_garbage(client):
    res = client.post("/api/generate", data={"payload": "{not json"})
    assert res.status_code == 422 and "form" in res.get_json()["errors"]


def test_merge_downloads_claim_with_proofs_in_order(client, sample, png_bytes, two_page_pdf):
    res = client.post(
        "/api/merge",
        data={
            "payload": json.dumps(sample),
            "attachments": [(io.BytesIO(png_bytes), "medical-bill.png"), (io.BytesIO(two_page_pdf), "receipt.pdf")],
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    assert res.headers["Content-Disposition"].startswith("attachment")
    reader = PdfReader(io.BytesIO(res.data))
    assert len(reader.pages) == 3 + 1 + 2
    assert "Attachment page 1" in reader.pages[4].extract_text()


def test_merge_rejects_bad_files_with_their_position(client, sample, png_bytes):
    res = client.post(
        "/api/merge",
        data={
            "payload": json.dumps(sample),
            "attachments": [
                (io.BytesIO(png_bytes), "ok.png"),
                (io.BytesIO(b"not really a pdf"), "fake.pdf"),
                (io.BytesIO(b"MZ..."), "virus.exe"),
            ],
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 422
    errors = res.get_json()["errors"]
    assert set(errors) == {"attachments.1", "attachments.2"}
    assert errors["attachments.1"].startswith("fake.pdf:")
