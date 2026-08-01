"""FastAPI dependency providers.

Keeping this separate is what makes the storage swap a one-line override in
tests: app.dependency_overrides[get_storage] = lambda: InMemoryStorage().
"""

from functools import lru_cache

from app.config import get_settings
from app.services.storage import GCSStorage, StorageClient


@lru_cache
def _gcs_storage() -> GCSStorage:
    """Cached so we build one GCS client per process, not per request."""
    return GCSStorage(get_settings().gcs_bucket)


def get_storage() -> StorageClient:
    return _gcs_storage()
