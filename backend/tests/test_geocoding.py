import httpx
import pytest
import respx

from app.errors import AppError
from app.services.geocoding import search_cities

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

MUMBAI = {
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
}

SPRINGFIELD = {
    "results": [
        {
            "name": "Springfield",
            "admin1": "Illinois",
            "country": "United States",
            "country_code": "US",
            "latitude": 39.80172,
            "longitude": -89.64371,
        },
        {
            "name": "Springfield",
            "admin1": "Missouri",
            "country": "United States",
            "country_code": "US",
            "latitude": 37.21533,
            "longitude": -93.29824,
        },
        {
            "name": "Springfield",
            "admin1": "Massachusetts",
            "country": "United States",
            "country_code": "US",
            "latitude": 42.10148,
            "longitude": -72.58981,
        },
        {
            "name": "Springfield",
            "admin1": "Ohio",
            "country": "United States",
            "country_code": "US",
            "latitude": 39.92455,
            "longitude": -83.80881,
        },
        {
            "name": "Springfield",
            "admin1": "Oregon",
            "country": "United States",
            "country_code": "US",
            "latitude": 44.04621,
            "longitude": -123.02207,
        },
    ]
}

# Confirmed live: a query with no matches omits the `results` key entirely
# rather than returning an empty array.
NO_MATCH = {"generationtime_ms": 0.5}


@respx.mock
@pytest.mark.asyncio
async def test_single_match_maps_fields_correctly():
    respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=MUMBAI))

    results = await search_cities("Mumbai")

    assert results == [
        {
            "name": "Mumbai",
            "admin1": "Maharashtra",
            "country": "India",
            "country_code": "IN",
            "latitude": 19.07283,
            "longitude": 72.88261,
        }
    ]


@respx.mock
@pytest.mark.asyncio
async def test_ambiguous_query_returns_all_matches_in_order():
    respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=SPRINGFIELD))

    results = await search_cities("Springfield")

    assert len(results) == 5
    assert [r["admin1"] for r in results] == [
        "Illinois",
        "Missouri",
        "Massachusetts",
        "Ohio",
        "Oregon",
    ]


@respx.mock
@pytest.mark.asyncio
async def test_no_match_returns_empty_list_not_keyerror():
    respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=NO_MATCH))

    results = await search_cities("xyzzyqqqzz")

    assert results == []


@respx.mock
@pytest.mark.asyncio
async def test_missing_optional_fields_map_to_none():
    body = {
        "results": [
            {
                "name": "Somewhere",
                "country": "Testland",
                "latitude": 1.0,
                "longitude": 2.0,
                # admin1 and country_code absent, as the live API sometimes omits them.
            }
        ]
    }
    respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=body))

    [result] = await search_cities("Somewhere")

    assert result["admin1"] is None
    assert result["country_code"] is None
    assert result["name"] == "Somewhere"


@respx.mock
@pytest.mark.asyncio
async def test_sends_the_correct_query_parameters():
    route = respx.get(GEOCODE).mock(return_value=httpx.Response(200, json=MUMBAI))

    await search_cities("Mumbai")

    params = route.calls.last.request.url.params
    assert params["name"] == "Mumbai"
    assert params["count"] == "5"
    assert params["format"] == "json"


@respx.mock
@pytest.mark.asyncio
async def test_timeout_becomes_502():
    respx.get(GEOCODE).mock(side_effect=httpx.ConnectTimeout("timed out"))

    with pytest.raises(AppError) as caught:
        await search_cities("Mumbai")

    assert caught.value.status_code == 502
    assert "geocod" in caught.value.message.lower()


@respx.mock
@pytest.mark.asyncio
async def test_upstream_500_becomes_502():
    respx.get(GEOCODE).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(AppError) as caught:
        await search_cities("Mumbai")

    assert caught.value.status_code == 502
    assert "geocod" in caught.value.message.lower()
