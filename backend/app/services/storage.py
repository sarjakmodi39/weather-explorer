"""Object storage behind a narrow protocol.

Three implementations: GCSStorage and S3Storage for production,
InMemoryStorage for tests. Routes depend on the protocol, never on
google.cloud or boto3 directly, which is what lets the whole suite run with
no credentials and no network — and what lets the production backend be
swapped by configuration alone (see app.deps.get_storage).

S3Storage exists because the deployment target moved from GCS to Supabase
Storage, which speaks the S3 API but is not AWS. It is not a replacement for
GCSStorage — both stay, selected by `settings.storage_backend` — this is the
Protocol doing its job.
"""

import json
from datetime import datetime, timezone
from typing import Protocol

import botocore.exceptions as boto_exceptions
from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as gauth_exceptions
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
        # Inert by design: construction must never raise. FastAPI resolves
        # `Depends(get_storage)` before it validates the request body, so an
        # eager failure here would shadow a genuine 400 with a 500. Both the
        # empty-bucket check and the real client construction are deferred to
        # `_client`, which fires on first actual use.
        self._bucket_name = bucket_name
        self._injected_client = client
        self._client_cache: gcs.Client | None = None

    @property
    def _client(self) -> gcs.Client:
        if self._client_cache is None:
            if not self._bucket_name:
                raise AppError("GCS_BUCKET is not configured", status_code=500)
            if self._injected_client is not None:
                self._client_cache = self._injected_client
            else:
                try:
                    self._client_cache = gcs.Client()
                except (gauth_exceptions.GoogleAuthError, EnvironmentError) as exc:
                    # gcs.Client() raises a bare EnvironmentError (not a
                    # GoogleAuthError) when no project can be determined from
                    # the environment — e.g. "Project was not passed and
                    # could not be determined from the environment." Caught
                    # alongside GoogleAuthError so it maps to the same 502
                    # instead of escaping as an opaque 500.
                    raise AppError(
                        f"could not authenticate with storage: {exc}", status_code=502
                    ) from exc
        return self._client_cache

    def save_json(self, name: str, payload: dict) -> None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            blob.upload_from_string(
                json.dumps(payload),
                content_type="application/json",
            )
        except gauth_exceptions.GoogleAuthError as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
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
        except gauth_exceptions.GoogleAuthError as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not list storage: {exc}", status_code=502) from exc

        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    def get_json(self, name: str) -> dict | None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            raw = blob.download_as_bytes()
        except gcp_exceptions.NotFound:
            return None
        except gauth_exceptions.GoogleAuthError as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not read from storage: {exc}", status_code=502) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("stored object is not valid JSON", status_code=500) from exc


# Raised locally by botocore itself (never sent by the server) when no
# credentials, or an incomplete set, can be found. Named once here so the
# three call sites below don't each repeat a two-exception tuple.
_CREDENTIAL_ERRORS = (boto_exceptions.NoCredentialsError, boto_exceptions.PartialCredentialsError)


class S3Storage:
    """S3-compatible implementation, used for Supabase Storage.

    Supabase Storage exposes a genuine S3-compatible API, so this talks
    straight boto3 against a configurable endpoint rather than a
    Supabase-specific SDK. Access keys are never handled here: boto3 reads
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the environment on its
    own, so nothing secret ever passes through Settings, logs, or this class.
    """

    def __init__(self, bucket_name: str, client=None) -> None:
        # Inert by design, mirroring GCSStorage: construction must never
        # raise, because FastAPI resolves Depends(get_storage) before it
        # validates the request body. An eager failure here would shadow a
        # genuine 400 with a 500 (see the GCSStorage docstring/history for
        # the bug this guards against). The empty-bucket check and the real
        # boto3 client construction are both deferred to `_client`, which
        # fires on first actual use. Endpoint/region come from Settings
        # (read lazily below, not stashed as constructor args) so this
        # constructor keeps GCSStorage's exact (bucket_name, client) shape.
        self._bucket_name = bucket_name
        self._injected_client = client
        self._client_cache = None

    @property
    def _client(self):
        if self._client_cache is None:
            if not self._bucket_name:
                raise AppError("S3_BUCKET is not configured", status_code=500)
            if self._injected_client is not None:
                self._client_cache = self._injected_client
            else:
                import boto3

                from app.config import get_settings

                settings = get_settings()
                self._client_cache = boto3.client(
                    "s3",
                    endpoint_url=settings.s3_endpoint_url or None,
                    # Supabase requires a region string even though its
                    # storage is not region-partitioned; AWS ignores an
                    # unnecessary one, so a fixed default is safe either way.
                    region_name=settings.s3_region or "us-east-1",
                )
        return self._client_cache

    def save_json(self, name: str, payload: dict) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket_name,
                Key=name,
                Body=json.dumps(payload).encode("utf-8"),
                ContentType="application/json",
            )
        except _CREDENTIAL_ERRORS as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
        except (boto_exceptions.ClientError, boto_exceptions.BotoCoreError) as exc:
            raise AppError(f"could not write to storage: {exc}", status_code=502) from exc

    def list_files(self) -> list[StoredFile]:
        entries = []
        try:
            # list_objects_v2 truncates at 1000 keys per call. A paginator
            # drives repeated calls (using the continuation token S3 returns)
            # until every page has been consumed, so this never silently
            # drops objects in a bucket beyond the 1000th.
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket_name):
                for obj in page.get("Contents", []):
                    entries.append(
                        StoredFile(
                            name=obj["Key"],
                            size=obj.get("Size", 0),
                            created_at=obj["LastModified"],
                        )
                    )
        except _CREDENTIAL_ERRORS as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
        except (boto_exceptions.ClientError, boto_exceptions.BotoCoreError) as exc:
            raise AppError(f"could not list storage: {exc}", status_code=502) from exc

        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    # Error codes seen for a missing key across S3-compatible backends.
    # AWS itself returns "NoSuchKey"; Supabase Storage and other
    # non-AWS implementations have been observed returning a bare "404"
    # or "NotFound" instead.
    _MISSING_KEY_CODES = {"NoSuchKey", "404", "NotFound"}

    def get_json(self, name: str) -> dict | None:
        try:
            response = self._client.get_object(Bucket=self._bucket_name, Key=name)
        except _CREDENTIAL_ERRORS as exc:
            raise AppError(
                f"could not authenticate with storage: {exc}", status_code=502
            ) from exc
        except boto_exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in self._MISSING_KEY_CODES:
                return None
            raise AppError(f"could not read from storage: {exc}", status_code=502) from exc
        except boto_exceptions.BotoCoreError as exc:
            raise AppError(f"could not read from storage: {exc}", status_code=502) from exc

        raw = response["Body"].read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("stored object is not valid JSON", status_code=500) from exc
