import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as gauth_exceptions

from app.errors import AppError
from app.services.storage import GCSStorage, InMemoryStorage

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
