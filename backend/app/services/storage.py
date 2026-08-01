"""Object storage behind a narrow protocol.

Two implementations: GCSStorage for production, InMemoryStorage for tests.
Routes depend on the protocol, never on google.cloud, which is what lets the
whole suite run with no credentials and no network.
"""

import json
from datetime import datetime, timezone
from typing import Protocol

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage as gcs

from app.errors import AppError
from app.schemas import StoredFile


class StorageClient(Protocol):
    """The only storage surface the rest of the app knows about."""

    def save_json(self, name: str, payload: dict) -> None: ...

    def list_files(self) -> list[StoredFile]: ...

    def get_json(self, name: str) -> dict | None:
        """Return the parsed object, or None if it does not exist."""
        ...


class InMemoryStorage:
    """Test double. Mirrors GCSStorage's observable behavior."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, datetime]] = {}

    def save_json(self, name: str, payload: dict, created_at: datetime | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._objects[name] = (raw, created_at or datetime.now(timezone.utc))

    def list_files(self) -> list[StoredFile]:
        entries = [
            StoredFile(name=name, size=len(raw), created_at=created)
            for name, (raw, created) in self._objects.items()
        ]
        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    def get_json(self, name: str) -> dict | None:
        record = self._objects.get(name)
        return json.loads(record[0]) if record else None


class GCSStorage:
    """Google Cloud Storage implementation.

    Credentials come from Application Default Credentials: the attached
    service account on Cloud Run, or `gcloud auth application-default login`
    locally. No key file is ever read from the repo.
    """

    # Ask GCS for only the three fields we surface. Without this mask the API
    # returns full object metadata for every blob, which is wasted bytes.
    _LIST_FIELDS = "items(name,size,timeCreated),nextPageToken"

    def __init__(self, bucket_name: str, client: gcs.Client | None = None) -> None:
        if not bucket_name:
            raise AppError("GCS_BUCKET is not configured", status_code=500)
        self._bucket_name = bucket_name
        self._client = client or gcs.Client()

    def save_json(self, name: str, payload: dict) -> None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            blob.upload_from_string(
                json.dumps(payload),
                content_type="application/json",
            )
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not write to storage: {exc}", status_code=502) from exc

    def list_files(self) -> list[StoredFile]:
        try:
            blobs = self._client.list_blobs(self._bucket_name, fields=self._LIST_FIELDS)
            entries = [
                StoredFile(
                    name=blob.name,
                    size=blob.size or 0,
                    created_at=blob.time_created,
                )
                for blob in blobs
            ]
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not list storage: {exc}", status_code=502) from exc

        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    def get_json(self, name: str) -> dict | None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            raw = blob.download_as_bytes()
        except gcp_exceptions.NotFound:
            return None
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not read from storage: {exc}", status_code=502) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("stored object is not valid JSON", status_code=500) from exc
