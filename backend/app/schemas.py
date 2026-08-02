"""Request and response models.

Validation lives here as declarative schema rather than scattered `if`
statements in the route, so the rules are readable in one place.
"""

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field, model_validator

# Inclusive day count. Jun 1 -> Jul 1 is 31 days and is allowed;
# Jun 1 -> Jul 2 is 32 and is not.
MAX_RANGE_DAYS = 31

# Open-Meteo's ERA5 archive does not go back further than this.
EARLIEST_DATE = date(1940, 1, 1)


class StoreWeatherRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, description="Degrees north, -90 to 90")
    longitude: float = Field(ge=-180, le=180, description="Degrees east, -180 to 180")
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_date_window(self) -> "StoreWeatherRequest":
        # Order matters: the first failing rule is the message the caller sees.
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")

        span = (self.end_date - self.start_date).days + 1
        if span > MAX_RANGE_DAYS:
            raise ValueError(
                f"date range must not exceed {MAX_RANGE_DAYS} days (requested {span})"
            )

        if self.end_date > datetime.now(timezone.utc).date():
            raise ValueError("end_date must not be in the future")

        if self.start_date < EARLIEST_DATE:
            raise ValueError(f"start_date must not be earlier than {EARLIEST_DATE.isoformat()}")

        return self


class StoreWeatherResponse(BaseModel):
    status: str = "ok"
    file: str


class StoredFile(BaseModel):
    name: str
    size: int  # bytes
    created_at: datetime  # serialized as ISO 8601


class ListFilesResponse(BaseModel):
    files: list[StoredFile]
