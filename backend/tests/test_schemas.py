from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import StoreWeatherRequest

VALID = {
    "latitude": 19.076,
    "longitude": 72.8777,
    "start_date": "2024-06-01",
    "end_date": "2024-06-10",
}


def build(**overrides) -> StoreWeatherRequest:
    return StoreWeatherRequest(**{**VALID, **overrides})


def test_accepts_a_valid_request():
    request = build()
    assert request.latitude == 19.076
    assert request.start_date == date(2024, 6, 1)


def test_accepts_boundary_coordinates():
    build(latitude=90, longitude=180)
    build(latitude=-90, longitude=-180)


@pytest.mark.parametrize("latitude", [90.01, -90.01, 1000])
def test_rejects_out_of_range_latitude(latitude):
    with pytest.raises(ValidationError, match="latitude"):
        build(latitude=latitude)


@pytest.mark.parametrize("longitude", [180.01, -180.01, -999])
def test_rejects_out_of_range_longitude(longitude):
    with pytest.raises(ValidationError, match="longitude"):
        build(longitude=longitude)


@pytest.mark.parametrize("bad", ["not-a-date", "2024-13-01", "06/01/2024", ""])
def test_rejects_malformed_dates(bad):
    with pytest.raises(ValidationError):
        build(start_date=bad)


def test_rejects_start_after_end():
    with pytest.raises(ValidationError, match="on or before"):
        build(start_date="2024-06-11", end_date="2024-06-10")


def test_accepts_single_day_range():
    request = build(start_date="2024-06-01", end_date="2024-06-01")
    assert request.start_date == request.end_date


def test_accepts_exactly_31_inclusive_days():
    """Jun 1 -> Jul 1 is 31 days counted inclusively, and must pass."""
    build(start_date="2024-06-01", end_date="2024-07-01")


def test_rejects_32_inclusive_days():
    with pytest.raises(ValidationError, match="31 days"):
        build(start_date="2024-06-01", end_date="2024-07-02")


def test_rejects_future_end_date():
    # Isolated from the range rule: validators short-circuit on first failure,
    # so both dates must sit in the future and be close together.
    # The schema evaluates "today" as datetime.now(timezone.utc).date(), so
    # the test's expectations are built from the same clock rather than
    # date.today() (local time), which would drift from it near midnight UTC.
    future = datetime.now(timezone.utc).date() + timedelta(days=365)
    with pytest.raises(ValidationError, match="future"):
        build(start_date=str(future), end_date=str(future + timedelta(days=3)))


def test_accepts_today_as_end_date():
    today = datetime.now(timezone.utc).date()
    build(start_date=str(today - timedelta(days=3)), end_date=str(today))


def test_rejects_dates_before_the_archive_begins():
    with pytest.raises(ValidationError, match="1940-01-01"):
        build(start_date="1939-12-25", end_date="1939-12-31")


@pytest.mark.parametrize("missing", ["latitude", "longitude", "start_date", "end_date"])
def test_rejects_missing_fields(missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError, match=missing):
        StoreWeatherRequest(**payload)
