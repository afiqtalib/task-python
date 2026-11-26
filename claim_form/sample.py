"""Sample data - based on DBT_Claim_Afiq_102026.pdf (trimmed to two trips)."""
from __future__ import annotations

_DBKL_TRAINING = "Office > Institut Latihan Dewan Bandaraya Kuala Lumpur > Office"

SAMPLE_CLAIM = {
    "name": "MUHAMMAD",
    "dept": "EPPP",
    "month": 10,
    "year": 2026,
    "vehicle_no": "DBS 2580",
    "vehicle_model": "HONDA",
    "vehicle_type": "motorcycle",
    "travel": [
        {"date": "2026-10-27", "location": _DBKL_TRAINING, "start": "09:00", "finish": "18:00", "distance": "32"},
        {"date": "2026-10-29", "location": "Office > Menara DBKL 3 > Office", "start": "09:00", "finish": "18:00",
         "distance": "19"},
    ],
    "entertainment": [],
    "parking": [],
    "subsistence": [],
    "misc": [
        {"date": "2026-10-20", "description": "MEDICAL BILL", "amount": "75.00"},
    ],
    "options": {"include_travel_sheet": True},
}
