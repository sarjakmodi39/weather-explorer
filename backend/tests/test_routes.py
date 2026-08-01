import httpx
import respx

from app.naming import is_valid_object_name

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

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
