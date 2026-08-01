"""The three weather endpoints.

Routes stay thin: they translate HTTP to service calls and back. Validation
lives in schemas.py, I/O in services/, naming in naming.py.
"""

from fastapi import APIRouter, Depends

from app.deps import get_storage
from app.naming import build_object_name
from app.schemas import StoreWeatherRequest, StoreWeatherResponse
from app.services.open_meteo import fetch_daily_history
from app.services.storage import StorageClient

router = APIRouter(tags=["weather"])


@router.post("/store-weather-data", response_model=StoreWeatherResponse)
async def store_weather_data(
    request: StoreWeatherRequest,
    storage: StorageClient = Depends(get_storage),
) -> StoreWeatherResponse:
    """Fetch a date range from Open-Meteo and persist the raw response."""
    # FastAPI has already validated `request` — an invalid payload never gets
    # here, so we never spend an upstream call on input we know is bad.
    payload = await fetch_daily_history(
        request.latitude,
        request.longitude,
        request.start_date,
        request.end_date,
    )

    name = build_object_name(
        request.latitude,
        request.longitude,
        request.start_date,
        request.end_date,
    )
    storage.save_json(name, payload)

    return StoreWeatherResponse(status="ok", file=name)
