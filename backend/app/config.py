"""Application settings, sourced from environment variables."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Export .env into the real process environment before anything reads it.
#
# pydantic-settings parses .env into Settings but does not export to
# os.environ, and the cloud SDKs bypass Settings entirely: boto3 reads
# AWS_ACCESS_KEY_ID itself, and google-cloud-storage reads
# STORAGE_EMULATOR_HOST itself. Without this, those keys look configured in
# .env but silently do nothing — which cost real debugging time once.
#
# No-op in production, where config arrives as real environment variables and
# no .env file exists. `override=False` keeps genuine environment variables
# authoritative over a stray local file.
load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Name of the GCS bucket holding stored weather files.
    gcs_bucket: str = ""

    # Which StorageClient implementation app.deps.get_storage() builds.
    # "gcs" (default) or "s3". Anything else fails loudly at request time
    # rather than silently falling back to a default.
    storage_backend: str = "gcs"

    # Name of the S3-compatible bucket holding stored weather files.
    s3_bucket: str = ""

    # Endpoint URL for a non-AWS S3-compatible provider (e.g. Supabase
    # Storage's S3 endpoint). Left empty, boto3 talks to AWS itself.
    s3_endpoint_url: str = ""

    # Supabase Storage requires a region string even though it is not
    # region-partitioned. Left empty, S3Storage falls back to "us-east-1".
    s3_region: str = ""

    # Access keys are read by boto3 directly from AWS_ACCESS_KEY_ID /
    # AWS_SECRET_ACCESS_KEY — deliberately not modeled as Settings fields,
    # so they are never logged or echoed alongside the rest of this object.

    # Comma-separated list of origins permitted by CORS.
    # Deliberately not "*" — see README.
    allowed_origins: str = "http://localhost:5173"

    open_meteo_url: str = "https://archive-api.open-meteo.com/v1/archive"

    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is read once per process."""
    return Settings()
