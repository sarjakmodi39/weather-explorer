from datetime import datetime, timedelta, timezone

from app.services.storage import InMemoryStorage

PAYLOAD = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}


def test_round_trips_a_payload():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    assert storage.get_json("weather_a.json") == PAYLOAD


def test_missing_file_returns_none():
    assert InMemoryStorage().get_json("nope.json") is None


def test_empty_storage_lists_nothing():
    assert InMemoryStorage().list_files() == []


def test_list_reports_size_in_bytes():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    [entry] = storage.list_files()
    assert entry.name == "weather_a.json"
    assert entry.size > 0
    assert entry.created_at.tzinfo is not None


def test_list_is_newest_first():
    storage = InMemoryStorage()
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    storage.save_json("older.json", PAYLOAD, created_at=base)
    storage.save_json("newest.json", PAYLOAD, created_at=base + timedelta(hours=2))
    storage.save_json("middle.json", PAYLOAD, created_at=base + timedelta(hours=1))

    assert [f.name for f in storage.list_files()] == ["newest.json", "middle.json", "older.json"]


def test_stores_bytes_unmodified():
    """The brief says 'full API JSON' — assert nothing is reshaped."""
    storage = InMemoryStorage()
    payload = {"z": 1, "a": {"nested": [1, 2, None]}, "extra_field": "kept"}
    storage.save_json("weather_a.json", payload)

    assert storage.get_json("weather_a.json") == payload
