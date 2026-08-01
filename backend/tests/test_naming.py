from datetime import date, datetime, timezone

import pytest

from app.naming import build_object_name, is_valid_object_name

FIXED_NOW = datetime(2026, 8, 1, 14, 25, 30, tzinfo=timezone.utc)


def test_builds_the_documented_format():
    name = build_object_name(19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 10), FIXED_NOW)
    assert name == "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json"


def test_preserves_negative_coordinates():
    name = build_object_name(-33.8688, 151.2093, date(2024, 6, 1), date(2024, 6, 10), FIXED_NOW)
    assert name == "weather_-33.8688_151.2093_2024-06-01_2024-06-10_20260801T142530Z.json"


def test_normalizes_coordinate_precision():
    """19.076 and 19.0760 must produce the same name — names are predictable,
    not a mirror of whatever the caller typed."""
    a = build_object_name(19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    b = build_object_name(19.07600, 72.87770, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    assert a == b


def test_pads_and_rounds_to_four_decimals():
    name = build_object_name(5, -0.123456, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    assert "weather_5.0000_-0.1235_" in name


def test_generated_names_are_always_valid():
    name = build_object_name(-89.9999, 179.9999, date(1940, 1, 1), date(1940, 1, 2), FIXED_NOW)
    assert is_valid_object_name(name)


def test_defaults_to_current_utc_time():
    name = build_object_name(0, 0, date(2024, 6, 1), date(2024, 6, 2))
    assert is_valid_object_name(name)


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..%2F..%2Fsecret.json",
        "weather_../../escape_2024-06-01_2024-06-02_20260801T142530Z.json",
        "/absolute/path.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json/../other",
        "",
        "random.json",
        "weather.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.txt",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10.json",
        "WEATHER_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json",
    ],
)
def test_rejects_malformed_and_hostile_names(hostile):
    assert not is_valid_object_name(hostile)
