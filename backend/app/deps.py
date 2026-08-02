"""FastAPI dependency providers.

Keeping this separate is what makes the storage swap a one-line override in
tests: app.dependency_overrides[get_storage] = lambda: InMemoryStorage().
"""

from functools import lru_cache

from app.config import get_settings
from app.errors import AppError
from app.services.storage import GCSStorage, S3Storage, StorageClient


@lru_cache
def _gcs_storage() -> GCSStorage:
    """Cached so we build one GCS client per process, not per request."""
    return GCSStorage(get_settings().gcs_bucket)


@lru_cache
def _s3_storage() -> S3Storage:
    """Cached so we build one boto3 client per process, not per request."""
    return S3Storage(get_settings().s3_bucket)


def get_storage() -> StorageClient:
    backend = get_settings().storage_backend
    if backend == "gcs":
        return _gcs_storage()
    if backend == "s3":
        return _s3_storage()
    # Fail loudly rather than silently falling back to a default backend —
    # a typo in STORAGE_BACKEND should be obvious, not quietly ignored.
    raise AppError(f"unknown storage_backend: {backend!r}", status_code=500)
