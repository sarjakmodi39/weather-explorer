"""Client for the Open-Meteo geocoding API.

Mirrors open_meteo.py: same transport, same single-attempt/no-retry
reasoning, same error mapping. This is the only place in the app that talks
to the geocoding service — the browser never does.
"""

import logging

import httpx

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30.0


async def search_cities(query: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` city matches for `query`.

    Raises AppError(502) when the geocoding service is unreachable, returns
    a non-200 status, or returns a body we can't parse. A query that simply
    has no matches is not an error — see below.
    """
    params = {
        "name": query,
        "count": limit,
        "language": "en",
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(get_settings().geocoding_url, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Geocoding service unreachable: %s", exc)
        raise AppError(f"Geocoding service is unreachable: {exc}", status_code=502) from exc

    if response.status_code != 200:
        raise AppError(
            f"Geocoding service returned an unexpected status {response.status_code}",
            status_code=502,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AppError("Geocoding service returned a malformed response", status_code=502) from exc

    # Confirmed against the live API: a query with no matches omits the
    # `results` key entirely rather than returning an empty array. A naive
    # body["results"] raises KeyError here, so .get() with a [] default is
    # load-bearing, not defensive style.
    return [_to_result(item) for item in body.get("results", [])]


def _to_result(item: dict) -> dict:
    return {
        "name": item["name"],
        "admin1": item.get("admin1"),
        "country": item.get("country"),
        "country_code": item.get("country_code"),
        "latitude": item["latitude"],
        "longitude": item["longitude"],
    }
