"""DBT Technologies - Travelling & Entertainment claim form (web app).

Run:  python app.py      (or run.bat on Windows)
Then open http://127.0.0.1:5000

Flow
  1. POST /api/generate  form data            -> claim PDF (shown inline, not downloaded)
  2. POST /api/merge     form data + proofs   -> claim PDF + attachments, as a download
"""
from __future__ import annotations

import json
import logging
import os
from io import BytesIO

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from claim_form import config, logo
from claim_form.models import Claim, ValidationError, parse_claim
from claim_form.pdf import build_claim_pdf, read_uploads
from claim_form.sample import SAMPLE_CLAIM

log = logging.getLogger("claim_form")


def _read_payload() -> Claim:
    raw = request.form.get("payload", "")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ValidationError({"form": "The form data could not be read. Reload the page and try again."})
    return parse_claim(payload)


def _pdf_response(pdf: bytes, filename: str, *, download: bool) -> Response:
    response = send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=download,
        download_name=filename,
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Filename"] = filename
    return response


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_BYTES
    app.json.sort_keys = False

    @app.get("/")
    def index():
        return render_template("index.html", cfg=config.client_config())

    @app.get("/logo.svg")
    def logo_svg():
        """Company logo - same vector geometry as printed on the PDF."""
        return Response(logo.svg(), mimetype="image/svg+xml", headers={"Cache-Control": "no-cache"})

    @app.get("/api/ping")
    def ping():
        """Lets the desktop launcher recognise a copy of the app that is already running."""
        return jsonify(app=config.APP_ID)

    @app.get("/api/sample")
    def sample():
        return jsonify(SAMPLE_CLAIM)

    @app.post("/api/generate")
    def generate():
        """Step 1 - the claim form only, for on-screen review."""
        try:
            claim = _read_payload()
        except ValidationError as exc:
            return jsonify(errors=exc.errors), 422
        return _pdf_response(build_claim_pdf(claim), claim.filename, download=False)

    @app.post("/api/merge")
    def merge():
        """Step 2 - claim form followed by the uploaded proofs, in the order given."""
        errors: dict[str, str] = {}
        claim = attachments = None
        try:
            claim = _read_payload()
        except ValidationError as exc:
            errors.update(exc.errors)
        try:
            attachments = read_uploads(request.files.getlist("attachments"))
        except ValidationError as exc:
            errors.update(exc.errors)
        if errors:
            return jsonify(errors=errors), 422
        return _pdf_response(build_claim_pdf(claim, attachments), claim.filename, download=True)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_exc):
        mb = config.MAX_REQUEST_BYTES // (1024 * 1024)
        return jsonify(errors={"attachments": f"The upload is too large (max {mb} MB in total)."}), 413

    @app.errorhandler(500)
    def server_error(exc):
        log.exception("Unhandled error: %s", exc)
        return jsonify(errors={"form": "Something went wrong while creating the PDF. Please try again."}), 500

    return app


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
