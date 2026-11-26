from decimal import Decimal

import pytest

from claim_form import config
from claim_form.models import ValidationError, mileage_claim, parse_claim


def test_sample_totals(sample):
    claim = parse_claim(sample)
    assert len(claim.travel) == 2
    assert claim.total_km == Decimal("51")               # 32 + 19
    assert claim.travel_claim == Decimal("25.50")        # 51 km x RM0.50
    assert claim.entertainment_total == Decimal("0.00")
    assert claim.parking_total == Decimal("0.00")
    assert claim.subsistence_total == Decimal("0.00")
    assert claim.misc_total == Decimal("75.00")
    assert claim.total_claim == Decimal("100.50")
    assert claim.month_name == "OCTOBER"
    assert claim.filename == "DBT_Claim_MUHAMMAD_102026.pdf"


@pytest.mark.parametrize(
    "km, vehicle, expected",
    [
        ("147", "motorcycle", "73.50"),
        ("0.01", "motorcycle", "0.01"),     # 0.005 rounds half-up
        ("12.33", "motorcycle", "6.17"),    # 6.165 rounds half-up
        ("147", "car", "102.90"),
        ("300", "car", "210.00"),
    ],
)
def test_mileage(km, vehicle, expected):
    assert mileage_claim(Decimal(km), vehicle) == Decimal(expected)


def test_car_rate_beyond_tier(monkeypatch):
    monkeypatch.setattr(config, "CAR_RATE_BEYOND_TIER", Decimal("0.50"))
    # 300 x 0.70 + 50 x 0.50
    assert mileage_claim(Decimal("350"), "car") == Decimal("235.00")


def test_blank_rows_are_ignored(sample):
    sample["travel"].append({"date": "", "location": "", "start": "09:00", "finish": "18:00", "distance": ""})
    sample["misc"].append({"date": "", "description": "", "amount": ""})
    claim = parse_claim(sample)
    assert len(claim.travel) == 2 and len(claim.misc) == 1


def test_partial_row_reports_each_missing_field_with_its_index(sample):
    sample["travel"].insert(0, {"date": "", "location": "Office > KLCC > Office", "start": "09:00", "finish": "", "distance": ""})
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert set(exc.value.errors) == {"travel.0.date", "travel.0.finish", "travel.0.distance"}


@pytest.mark.parametrize("amount", ["-5", "abc", "1.234", "0", "0.00", "100000.01"])
def test_invalid_amounts(sample, amount):
    sample["misc"][0]["amount"] = amount
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert "misc.0.amount" in exc.value.errors


@pytest.mark.parametrize("amount, expected", [("1,234.5", "1234.50"), ("RM 75", "75.00"), (" 75.5 ", "75.50")])
def test_amount_normalisation(sample, amount, expected):
    sample["misc"][0]["amount"] = amount
    assert parse_claim(sample).misc_total == Decimal(expected)


def test_capacity_is_enforced(sample):
    row = sample["travel"][0]
    sample["travel"] = [dict(row) for _ in range(config.CAPACITY["travel"] + 1)]
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert "travel" in exc.value.errors


def test_vehicle_required_only_when_claiming_mileage(sample):
    sample["vehicle_no"] = ""
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert "vehicle_no" in exc.value.errors

    sample["travel"] = []
    sample["vehicle_model"] = ""
    claim = parse_claim(sample)
    assert claim.travel_claim == Decimal("0.00") and claim.total_claim == Decimal("75.00")


def test_header_is_upper_cased_and_trimmed(sample):
    sample["name"] = "  muhammad   afiq "
    sample["vehicle_no"] = "dbs 2580"
    claim = parse_claim(sample)
    assert claim.name == "MUHAMMAD AFIQ" and claim.vehicle_no == "DBS 2580"


def test_empty_claim_is_rejected(sample):
    for key in ("travel", "entertainment", "parking", "subsistence", "misc"):
        sample[key] = []
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert "form" in exc.value.errors


def test_bad_date_and_time(sample):
    sample["travel"][0]["date"] = "2026-02-30"
    sample["travel"][1]["start"] = "25:00"
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert {"travel.0.date", "travel.1.start"} <= set(exc.value.errors)


def test_invalid_signature_is_reported(sample):
    sample["signature"] = "data:image/png;base64,not-an-image"
    with pytest.raises(ValidationError) as exc:
        parse_claim(sample)
    assert "signature" in exc.value.errors
