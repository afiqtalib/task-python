# DBT T&E Claim Form Generator

Web form that produces the **DBT Technologies Travelling & Entertainment Claim Form** as a PDF,
laid out 1:1 like the original (`DBT_Claim_Afiq_102026.pdf`).

## Run

Double-click **`run.bat`** — it creates the environment on first run and opens <http://127.0.0.1:5000>.

Manual:

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

## How it works

1. **Fill in** the claim (or click **Load sample data**). Totals update live; the draft is saved in the browser.
2. **Generate claim** — the PDF is shown on the page for review (nothing is downloaded yet).
3. **Attach proofs** (medical bills, receipts — PDF/JPG/PNG/WEBP), **drag ⠿ to reorder**, then
   **Merge & download**: claim pages first, proofs after, in the order shown.

PDF pages: 1 main form · 2 entertainment / toll & parking / subsistence / miscellaneous ·
3 travel detail sheet (optional) · then the attached proofs.

## Configuration — `claim_form/config.py`

| Setting | Default | Notes |
|---|---|---|
| `MOTORCYCLE_RATE` | RM 0.50/km | |
| `CAR_RATE` / `CAR_RATE_TIER_KM` | RM 0.70/km, first 300 km | as printed on the form |
| `CAR_RATE_BEYOND_TIER` | RM 0.70/km | **not stated on the form — confirm with HR** |
| `CAPACITY` | 23 / 5 / 23 / 4 / 11 lines | rows on the printed form, per section |
| `LOGO_FILE` | `static/img/company-logo.png` | optional; by default the vector logo in `claim_form/logo.py` is drawn |

## Project layout

```
app.py                     Flask routes: /, /api/sample, /api/generate, /api/merge
claim_form/config.py       rates, capacities, field limits (shared by UI and PDF)
claim_form/models.py       validation + Decimal calculations (ROUND_HALF_UP)
claim_form/logo.py         company logo geometry (PDF, page header, favicon)
claim_form/pdf/renderer.py the 1:1 form layout (ReportLab, Arial)
claim_form/pdf/attachments.py  proof upload checks, image->page, merge (pypdf)
templates/, static/        the web form (plain HTML/CSS/JS, no build step)
tests/                     pytest suite
```

## Tests

```bat
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```
