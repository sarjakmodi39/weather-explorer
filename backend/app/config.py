"""Application settings, sourced from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Name of the GCS bucket holding stored weather files.
    gcs_bucket: str = ""

    # Comma-separated list of origins permitted by CORS.
    # Deliberately not "*" — see README.
    allowed_origins: str = "http://localhost:5173"

    open_meteo_url: str = "https://archive-api.open-meteo.com/v1/archive"

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is read once per process."""
    return Settings()
