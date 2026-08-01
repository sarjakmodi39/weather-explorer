"""Client for the Open-Meteo historical archive API.

This is the only place in the app that talks to Open-Meteo. The browser never
does — it only ever reads files we already stored.
"""

import logging
from datetime import date

import httpx

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

# The four the brief requires. Kept as a module constant so the test can assert
# on the exact set rather than a hand-copied string.
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
]

TIMEOUT_SECONDS = 30.0


async def fetch_daily_history(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> dict:
    """Return Open-Meteo's response body verbatim.

    Raises AppError(400) when Open-Meteo rejects the request, AppError(502)
    when it is unreachable or failing.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "auto",
    }

    # No retries: respx-based tests cannot exercise retry behavior (mocking intercepts
    # above the httpcore layer where retries run), and silent retries in production
    # would double worst-case latency before surfacing as a 502. Single attempt with
    # TIMEOUT_SECONDS timeout surfaces transport failures immediately.
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(get_settings().open_meteo_url, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Open-Meteo unreachable: %s", exc)
        raise AppError(f"Open-Meteo is unreachable: {exc}", status_code=502) from exc

    if response.status_code == 400:
        # Open-Meteo explains its own rejections well; pass the reason through
        # rather than inventing our own wording.
        reason = _reason(response) or "Open-Meteo rejected the request"
        raise AppError(reason, status_code=400)

    if response.status_code >= 500 or response.status_code != 200:
        raise AppError(
            f"Open-Meteo returned an unexpected status {response.status_code}",
            status_code=502,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise AppError("Open-Meteo returned a malformed response", status_code=502) from exc


def _reason(response: httpx.Response) -> str | None:
    try:
        return response.json().get("reason")
    except ValueError:
        return None
