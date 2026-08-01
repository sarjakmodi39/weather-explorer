"""Shared fixtures. Every test runs against in-memory storage."""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_storage
from app.main import create_app
from app.services.storage import InMemoryStorage


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    return TestClient(app)
