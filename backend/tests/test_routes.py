from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.deps import get_storage
from app.main import create_app
from app.naming import is_valid_object_name
from app.services.storage import GCSStorage

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

SAMPLE = {
    "latitude": 19.125,
    "longitude": 72.875,
    "daily_units": {"temperature_2m_max": "°C"},
    "daily": {
        "time": ["2024-06-01", "2024-06-02"],
        "temperature_2m_max": [34.4, 31.6],
        "temperature_2m_min": [28.1, 27.0],
        "apparent_temperature_max": [40.2, 37.1],
        "apparent_temperature_min": [31.0, 30.2],
    },
}

VALID = {
    "latitude": 19.076,
    "longitude": 72.8777,
    "start_date": "2024-06-01",
    "end_date": "2024-06-02",
}

NOT_FOUND = {"status": "error", "message": "not found"}


@respx.mock
def test_store_returns_ok_and_a_wellformed_filename(client):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    response = client.post("/store-weather-data", json=VALID)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert is_valid_object_name(body["file"])
    assert body["file"].startswith("weather_19.0760_72.8777_2024-06-01_2024-06-02_")


@respx.mock
def test_store_persists_the_api_json_unmodified(client, storage):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]

    assert storage.get_json(name) == SAMPLE


@respx.mock
def test_store_rejects_invalid_input_before_calling_open_meteo(client):
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    response = client.post("/store-weather-data", json={**VALID, "latitude": 91})

    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert "latitude" in response.json()["message"]
    assert not route.called, "must not spend an upstream call on input we know is invalid"


@respx.mock
def test_store_rejects_a_32_day_range(client):
    response = client.post(
        "/store-weather-data",
        json={**VALID, "start_date": "2024-06-01", "end_date": "2024-07-02"},
    )

    assert response.status_code == 400
    assert "31 days" in response.json()["message"]


@respx.mock
def test_store_maps_upstream_failure_to_502(client):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(503, text="unavailable"))

    response = client.post("/store-weather-data", json=VALID)

    assert response.status_code == 502
    assert response.json()["status"] == "error"
    assert "Open-Meteo" in response.json()["message"]


def test_store_rejects_a_non_json_body(client):
    response = client.post(
        "/store-weather-data",
        content="not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_list_is_empty_for_a_fresh_bucket(client):
    response = client.get("/list-weather-files")

    assert response.status_code == 200
    assert response.json() == {"files": []}


def test_list_returns_name_size_and_created_at(client, storage):
    storage.save_json("weather_a.json", {"daily": {"time": ["2024-06-01"]}})

    response = client.get("/list-weather-files")

    assert response.status_code == 200
    [entry] = response.json()["files"]
    assert entry["name"] == "weather_a.json"
    assert isinstance(entry["size"], int) and entry["size"] > 0
    # Must parse as ISO 8601.
    datetime.fromisoformat(entry["created_at"])


def test_list_is_ordered_newest_first(client, storage):
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    storage.save_json("older.json", {"a": 1}, created_at=base)
    storage.save_json("newest.json", {"a": 1}, created_at=base + timedelta(hours=2))
    storage.save_json("middle.json", {"a": 1}, created_at=base + timedelta(hours=1))

    names = [f["name"] for f in client.get("/list-weather-files").json()["files"]]

    assert names == ["newest.json", "middle.json", "older.json"]


@respx.mock
def test_a_stored_file_appears_in_the_listing(client):
    """End-to-end within the backend: store then list."""
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]
    names = [f["name"] for f in client.get("/list-weather-files").json()["files"]]

    assert name in names


def test_content_round_trips_stored_json(client, storage):
    payload = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}
    name = "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.json"
    storage.save_json(name, payload)

    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 200
    assert response.json() == payload


def test_content_returns_404_for_a_missing_file(client):
    name = "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.json"

    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


@pytest.mark.parametrize(
    "hostile",
    [
        "..%2F..%2Fetc%2Fpasswd",
        "random.json",
        "weather.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.txt",
    ],
)
def test_content_returns_404_for_invalid_names(client, hostile):
    """Malformed and missing are deliberately indistinguishable — it leaks nothing."""
    response = client.get(f"/weather-file-content/{hostile}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


def test_invalid_name_never_reaches_storage(client, monkeypatch, storage):
    def explode(_name):
        raise AssertionError("storage must not be queried for an invalid name")

    monkeypatch.setattr(storage, "get_json", explode)

    response = client.get("/weather-file-content/not-our-shape.json")

    assert response.status_code == 404


@respx.mock
def test_store_then_read_back(client):
    """Full backend round trip: store -> list -> read."""
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]
    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 200
    assert response.json() == SAMPLE


def test_invalid_body_still_gets_validated_when_storage_would_fail():
    """Regression test: a failing storage dependency must not shadow a bad
    request body.

    GCSStorage with an empty bucket name only fails on first use (lazily),
    not at construction, so FastAPI's dependency resolution (which runs
    before body validation) cannot short-circuit here. Before the fix,
    GCSStorage("") raised in __init__ and the dependency itself failed
    first, so an invalid body never got the chance to be rejected with 400
    — it always came back as 500 "GCS_BUCKET is not configured", regardless
    of what was in the body.

    This builds its own app and override rather than using conftest's
    `client`/`storage` fixtures, which use InMemoryStorage and would never
    exercise this failure path.
    """
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: GCSStorage("")
    client = TestClient(app)

    response = client.post("/store-weather-data", json={**VALID, "latitude": 999})

    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert "latitude" in response.json()["message"]


@respx.mock
def test_geocode_returns_matches_for_a_valid_query(client):
    respx.get(GEOCODE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Mumbai",
                        "admin1": "Maharashtra",
                        "country": "India",
                        "country_code": "IN",
                        "latitude": 19.07283,
                        "longitude": 72.88261,
                    }
                ]
            },
        )
    )

    response = client.get("/geocode", params={"q": "Mumbai"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["name"] == "Mumbai"


def test_geocode_rejects_a_one_character_query(client):
    response = client.get("/geocode", params={"q": "x"})

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_geocode_rejects_a_missing_query_param(client):
    response = client.get("/geocode")

    assert response.status_code == 400
    assert response.json()["status"] == "error"
