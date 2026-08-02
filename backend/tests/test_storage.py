import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from botocore import exceptions as boto_exceptions
from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as gauth_exceptions

from app import deps
from app.config import get_settings
from app.errors import AppError
from app.services import storage as storage_module
from app.services.storage import GCSStorage, InMemoryStorage, S3Storage

PAYLOAD = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}


def test_round_trips_a_payload():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    assert storage.get_json("weather_a.json") == PAYLOAD


def test_missing_file_returns_none():
    assert InMemoryStorage().get_json("nope.json") is None


def test_empty_storage_lists_nothing():
    assert InMemoryStorage().list_files() == []


def test_list_reports_size_in_bytes():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    [entry] = storage.list_files()
    assert entry.name == "weather_a.json"
    assert entry.size > 0
    assert entry.created_at.tzinfo is not None


def test_list_is_newest_first():
    storage = InMemoryStorage()
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    storage.save_json("older.json", PAYLOAD, created_at=base)
    storage.save_json("newest.json", PAYLOAD, created_at=base + timedelta(hours=2))
    storage.save_json("middle.json", PAYLOAD, created_at=base + timedelta(hours=1))

    assert [f.name for f in storage.list_files()] == ["newest.json", "middle.json", "older.json"]


def test_stores_bytes_unmodified():
    """The brief says 'full API JSON' — assert nothing is reshaped."""
    storage = InMemoryStorage()
    payload = {"z": 1, "a": {"nested": [1, 2, None]}, "extra_field": "kept"}
    storage.save_json("weather_a.json", payload)

    assert storage.get_json("weather_a.json") == payload


# --- GCSStorage: fakes covering only what the code touches ------------------
#
# No mocking framework, no patched globals: a plain fake object stands in for
# the google-cloud-storage client, exercising real GCSStorage code against
# fake data and fake failures instead of a mock's recorded expectations.


class FakeBlob:
    """Stands in for google.cloud.storage.Blob.

    `_raise_on_upload` / `_raise_on_download` let a test simulate the two
    failure classes GCSStorage must translate into AppError.
    """

    def __init__(self, name: str, download_bytes: bytes | None = None) -> None:
        self.name = name
        self.uploaded = None
        self.uploaded_content_type = None
        self._download_bytes = download_bytes
        self._raise_on_upload = None
        self._raise_on_download = None

    def upload_from_string(self, data, content_type=None) -> None:
        if self._raise_on_upload:
            raise self._raise_on_upload
        self.uploaded = data
        self.uploaded_content_type = content_type

    def download_as_bytes(self) -> bytes:
        if self._raise_on_download:
            raise self._raise_on_download
        if self._download_bytes is None:
            raise gcp_exceptions.NotFound("no such object")
        return self._download_bytes


class FakeBucket:
    """Stands in for google.cloud.storage.Bucket. One bucket, keyed blobs."""

    def __init__(self, blobs: dict[str, FakeBlob] | None = None) -> None:
        self._blobs = blobs or {}

    def blob(self, name: str) -> FakeBlob:
        return self._blobs.setdefault(name, FakeBlob(name))


class FakeClient:
    """Stands in for google.cloud.storage.Client.

    Records every list_blobs call so a test can assert on the exact kwargs
    GCSStorage sent (the fields mask is the efficiency requirement the spec
    calls out).
    """

    def __init__(
        self,
        blobs: dict[str, FakeBlob] | None = None,
        list_blobs_result: list | None = None,
        list_blobs_error: Exception | None = None,
    ) -> None:
        self._bucket = FakeBucket(blobs)
        self._list_blobs_result = list_blobs_result if list_blobs_result is not None else []
        self._list_blobs_error = list_blobs_error
        self.list_blobs_calls: list[tuple[str, dict]] = []

    def bucket(self, name: str) -> FakeBucket:
        return self._bucket

    def list_blobs(self, bucket_name: str, **kwargs):
        self.list_blobs_calls.append((bucket_name, kwargs))
        if self._list_blobs_error:
            raise self._list_blobs_error
        return self._list_blobs_result


def test_list_files_requests_the_documented_field_mask():
    client = FakeClient()
    storage = GCSStorage("test-bucket", client=client)

    storage.list_files()

    assert client.list_blobs_calls == [
        ("test-bucket", {"fields": "items(name,size,timeCreated),nextPageToken"})
    ]


def test_list_files_returns_newest_first_for_out_of_order_blobs():
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    blobs = [
        SimpleNamespace(name="older.json", size=10, time_created=base),
        SimpleNamespace(name="newest.json", size=20, time_created=base + timedelta(hours=2)),
        SimpleNamespace(name="middle.json", size=15, time_created=base + timedelta(hours=1)),
    ]
    client = FakeClient(list_blobs_result=blobs)
    storage = GCSStorage("test-bucket", client=client)

    result = storage.list_files()

    assert [f.name for f in result] == ["newest.json", "middle.json", "older.json"]


def test_get_json_returns_none_when_object_is_missing():
    client = FakeClient()
    storage = GCSStorage("test-bucket", client=client)

    assert storage.get_json("missing.json") is None


def test_save_json_round_trips_with_json_content_type():
    client = FakeClient()
    storage = GCSStorage("test-bucket", client=client)
    payload = {"a": 1, "b": [1, 2, None], "nested": {"c": "keep"}}

    storage.save_json("weather_a.json", payload)

    blob = client.bucket("test-bucket").blob("weather_a.json")
    assert json.loads(blob.uploaded) == payload
    assert blob.uploaded_content_type == "application/json"


def test_save_json_wraps_google_api_error_as_app_error():
    blob = FakeBlob("weather_a.json")
    blob._raise_on_upload = gcp_exceptions.GoogleAPIError("upstream failure")
    client = FakeClient(blobs={"weather_a.json": blob})
    storage = GCSStorage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.save_json("weather_a.json", PAYLOAD)

    assert exc_info.value.status_code == 502


def test_client_construction_environment_error_maps_to_app_error(monkeypatch):
    """gcs.Client() raises a bare EnvironmentError (not a GoogleAuthError)
    when no project can be determined from the environment. Regression test:
    this must map to a controlled 502, not escape as an opaque 500."""

    def _raise():
        raise EnvironmentError(
            "Project was not passed and could not be determined from the environment."
        )

    monkeypatch.setattr(storage_module.gcs, "Client", _raise)
    storage = GCSStorage("test-bucket")

    with pytest.raises(AppError) as exc_info:
        storage.list_files()

    assert exc_info.value.status_code == 502


def test_save_json_wraps_google_auth_error_as_app_error():
    """Regression test for Fix 1: auth failures must not fall through as a
    bare 500 — they are a distinct, common production failure mode (expired
    token, missing ADC) and must surface as a controlled AppError."""
    blob = FakeBlob("weather_a.json")
    blob._raise_on_upload = gauth_exceptions.RefreshError("token refresh failed")
    client = FakeClient(blobs={"weather_a.json": blob})
    storage = GCSStorage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.save_json("weather_a.json", PAYLOAD)

    assert exc_info.value.status_code == 502


# --- S3Storage: fakes covering only what the code touches --------------------
#
# Same approach as the GCSStorage fakes above: a plain fake stands in for the
# boto3 S3 client. No mocking framework, no patched globals, no network, no
# credentials — S3Storage's real code runs against fake data and fake
# failures instead of a mock's recorded expectations.


class FakeS3Body:
    """Stands in for botocore's StreamingBody, returned by get_object."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakePaginator:
    """Stands in for a boto3 Paginator. `pages` is exactly what paginate()
    yields, so a test can assert S3Storage merges more than one page rather
    than reading only the first (the 1000-key truncation this guards)."""

    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages

    def paginate(self, **kwargs):
        return self._pages


class FakeS3Client:
    """Stands in for a boto3 S3 client. One bucket, keyed objects."""

    def __init__(
        self,
        objects: dict[str, bytes] | None = None,
        list_pages: list[dict] | None = None,
        put_object_error: Exception | None = None,
        get_object_error: Exception | None = None,
        list_objects_error: Exception | None = None,
    ) -> None:
        self._objects = objects if objects is not None else {}
        self._list_pages = list_pages if list_pages is not None else [{"Contents": []}]
        self._put_object_error = put_object_error
        self._get_object_error = get_object_error
        self._list_objects_error = list_objects_error
        self.put_object_calls: list[dict] = []

    def put_object(self, **kwargs) -> None:
        if self._put_object_error:
            raise self._put_object_error
        self.put_object_calls.append(kwargs)
        self._objects[kwargs["Key"]] = kwargs["Body"]

    def get_paginator(self, operation_name: str) -> FakePaginator:
        assert operation_name == "list_objects_v2"
        if self._list_objects_error:
            raise self._list_objects_error
        return FakePaginator(self._list_pages)

    def get_object(self, Bucket: str, Key: str) -> dict:
        if self._get_object_error:
            raise self._get_object_error
        if Key not in self._objects:
            raise boto_exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
            )
        return {"Body": FakeS3Body(self._objects[Key])}


def test_s3_save_json_round_trips_with_json_content_type():
    client = FakeS3Client()
    storage = S3Storage("test-bucket", client=client)
    payload = {"a": 1, "b": [1, 2, None], "nested": {"c": "keep"}}

    storage.save_json("weather_a.json", payload)

    [call] = client.put_object_calls
    assert call["Bucket"] == "test-bucket"
    assert call["Key"] == "weather_a.json"
    assert json.loads(call["Body"]) == payload
    assert call["ContentType"] == "application/json"


def test_s3_list_files_maps_key_size_last_modified():
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    client = FakeS3Client(
        list_pages=[{"Contents": [{"Key": "weather_a.json", "Size": 42, "LastModified": base}]}]
    )
    storage = S3Storage("test-bucket", client=client)

    [entry] = storage.list_files()

    assert entry.name == "weather_a.json"
    assert entry.size == 42
    assert entry.created_at == base


def test_s3_list_files_returns_newest_first_for_out_of_order_objects():
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    client = FakeS3Client(
        list_pages=[
            {
                "Contents": [
                    {"Key": "older.json", "Size": 10, "LastModified": base},
                    {
                        "Key": "newest.json",
                        "Size": 20,
                        "LastModified": base + timedelta(hours=2),
                    },
                    {
                        "Key": "middle.json",
                        "Size": 15,
                        "LastModified": base + timedelta(hours=1),
                    },
                ]
            }
        ]
    )
    storage = S3Storage("test-bucket", client=client)

    result = storage.list_files()

    assert [f.name for f in result] == ["newest.json", "middle.json", "older.json"]


def test_s3_list_files_merges_multiple_pages():
    """list_objects_v2 truncates at 1000 keys per call. S3Storage must drive
    the paginator to completion, not read only the first page — this is the
    regression guard for that cap."""
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    client = FakeS3Client(
        list_pages=[
            {"Contents": [{"Key": "page1.json", "Size": 1, "LastModified": base}]},
            {
                "Contents": [
                    {"Key": "page2.json", "Size": 2, "LastModified": base + timedelta(hours=1)}
                ]
            },
        ]
    )
    storage = S3Storage("test-bucket", client=client)

    result = storage.list_files()

    assert {f.name for f in result} == {"page1.json", "page2.json"}


def test_s3_list_files_on_empty_bucket_returns_nothing():
    assert S3Storage("test-bucket", client=FakeS3Client()).list_files() == []


def test_s3_get_json_returns_none_for_no_such_key():
    client = FakeS3Client()
    storage = S3Storage("test-bucket", client=client)

    assert storage.get_json("missing.json") is None


def test_s3_get_json_returns_none_for_404_coded_error():
    """Supabase Storage is not AWS: S3-compatible implementations have been
    observed returning a bare "404" error code for a missing object rather
    than AWS's "NoSuchKey"."""
    client = FakeS3Client(
        get_object_error=boto_exceptions.ClientError(
            {"Error": {"Code": "404", "Message": "not found"}}, "GetObject"
        )
    )
    storage = S3Storage("test-bucket", client=client)

    assert storage.get_json("missing.json") is None


def test_s3_get_json_round_trips_a_stored_payload():
    payload = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}
    client = FakeS3Client(objects={"weather_a.json": json.dumps(payload).encode("utf-8")})
    storage = S3Storage("test-bucket", client=client)

    assert storage.get_json("weather_a.json") == payload


def test_s3_no_credentials_error_surfaces_as_502_with_authentication_wording():
    client = FakeS3Client(put_object_error=boto_exceptions.NoCredentialsError())
    storage = S3Storage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.save_json("weather_a.json", PAYLOAD)

    assert exc_info.value.status_code == 502
    assert "authenticate" in exc_info.value.message


def test_s3_partial_credentials_error_surfaces_as_502_with_authentication_wording():
    client = FakeS3Client(
        put_object_error=boto_exceptions.PartialCredentialsError(
            provider="aws", cred_var="AWS_SECRET_ACCESS_KEY"
        )
    )
    storage = S3Storage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.save_json("weather_a.json", PAYLOAD)

    assert exc_info.value.status_code == 502
    assert "authenticate" in exc_info.value.message


def test_s3_generic_client_error_surfaces_as_502():
    client = FakeS3Client(
        put_object_error=boto_exceptions.ClientError(
            {"Error": {"Code": "InternalError", "Message": "upstream failure"}}, "PutObject"
        )
    )
    storage = S3Storage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.save_json("weather_a.json", PAYLOAD)

    assert exc_info.value.status_code == 502


def test_s3_empty_bucket_name_raises_on_first_use_not_construction():
    """Regression guard for the dependency-ordering bug described in
    GCSStorage: constructing S3Storage("") must not raise. Only the first
    real call — list_files() here — should hit the empty-bucket check."""
    storage = S3Storage("", client=FakeS3Client())  # must not raise

    with pytest.raises(AppError) as exc_info:
        storage.list_files()

    assert exc_info.value.status_code == 500


def test_s3_invalid_json_raises_500():
    client = FakeS3Client(objects={"broken.json": b"not json"})
    storage = S3Storage("test-bucket", client=client)

    with pytest.raises(AppError) as exc_info:
        storage.get_json("broken.json")

    assert exc_info.value.status_code == 500


# --- deps.get_storage(): backend selection -----------------------------------


@pytest.fixture(autouse=True)
def _clear_storage_caches():
    """get_settings and the two per-backend factories in app.deps are all
    lru_cache'd for production (one client per process). Tests that flip
    STORAGE_BACKEND via the environment need every cache cleared before and
    after, or they will see a stale Settings/storage instance from whichever
    test ran first."""
    get_settings.cache_clear()
    deps._gcs_storage.cache_clear()
    deps._s3_storage.cache_clear()
    yield
    get_settings.cache_clear()
    deps._gcs_storage.cache_clear()
    deps._s3_storage.cache_clear()


def test_get_storage_selects_gcs_by_default(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    assert isinstance(deps.get_storage(), GCSStorage)


def test_get_storage_selects_s3_when_configured(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")

    assert isinstance(deps.get_storage(), S3Storage)


def test_get_storage_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "azure-blob")

    with pytest.raises(AppError):
        deps.get_storage()
