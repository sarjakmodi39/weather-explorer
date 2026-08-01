from datetime import date

import httpx
import pytest
import respx

from app.errors import AppError
from app.services.open_meteo import DAILY_VARIABLES, fetch_daily_history

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

ARGS = (19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 2))


@respx.mock
@pytest.mark.asyncio
async def test_requests_all_four_required_variables():
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    await fetch_daily_history(*ARGS)

    requested = route.calls.last.request.url.params["daily"].split(",")
    assert set(requested) == {
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "apparent_temperature_min",
    }
    assert set(DAILY_VARIABLES) == set(requested)


@respx.mock
@pytest.mark.asyncio
async def test_sends_the_correct_query_parameters():
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    await fetch_daily_history(*ARGS)

    params = route.calls.last.request.url.params
    assert params["latitude"] == "19.076"
    assert params["longitude"] == "72.8777"
    assert params["start_date"] == "2024-06-01"
    assert params["end_date"] == "2024-06-02"
    assert params["timezone"] == "auto"


@respx.mock
@pytest.mark.asyncio
async def test_returns_the_body_unmodified():
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    assert await fetch_daily_history(*ARGS) == SAMPLE


@respx.mock
@pytest.mark.asyncio
async def test_upstream_400_surfaces_the_reason_as_400():
    respx.get(ARCHIVE).mock(
        return_value=httpx.Response(
            400, json={"error": True, "reason": "Parameter 'end_date' is out of allowed range"}
        )
    )

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 400
    assert "out of allowed range" in caught.value.message


@respx.mock
@pytest.mark.asyncio
async def test_upstream_500_becomes_502():
    respx.get(ARCHIVE).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 502
    assert "Open-Meteo" in caught.value.message


@respx.mock
@pytest.mark.asyncio
async def test_timeout_becomes_502():
    respx.get(ARCHIVE).mock(side_effect=httpx.ConnectTimeout("timed out"))

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 502
    assert "Open-Meteo" in caught.value.message
