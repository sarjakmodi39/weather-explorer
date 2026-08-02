import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

DEFAULT_TEST_ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """These tests assert on the default ALLOWED_ORIGINS value. Settings is
    lru_cache'd and reads from the environment (and an optional local .env),
    so a developer who follows .env.example and sets a real ALLOWED_ORIGINS
    would otherwise break every test here. Pin the env var explicitly and
    clear the cache so the tests are independent of ambient config, whether
    or not backend/.env exists."""
    monkeypatch.setenv("ALLOWED_ORIGINS", DEFAULT_TEST_ORIGIN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_allowed_origin_receives_cors_headers():
    # ALLOWED_ORIGINS is pinned to the Vite dev server by the fixture above.
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": DEFAULT_TEST_ORIGIN})

    assert response.headers["access-control-allow-origin"] == DEFAULT_TEST_ORIGIN


def test_preflight_permits_post():
    client = TestClient(create_app())
    response = client.options(
        "/store-weather-data",
        headers={
            "Origin": DEFAULT_TEST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code in (200, 204)
    assert "POST" in response.headers["access-control-allow-methods"]


def test_origin_list_splits_and_trims():
    settings = Settings(allowed_origins="http://a.com, https://b.com ,")
    assert settings.origin_list == ["http://a.com", "https://b.com"]


def test_disallowed_origin_receives_no_cors_header():
    # CORS uses an explicit allowlist, never "*" — this origin is not in it,
    # so the response must carry no access-control-allow-origin header at
    # all. A regression to allow_origins=["*"] would still differ from the
    # evil origin's own value, so absence (not a mismatch) is what we assert.
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert "access-control-allow-origin" not in response.headers


def test_disallowed_origin_preflight_receives_no_cors_header():
    client = TestClient(create_app())
    response = client.options(
        "/store-weather-data",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_unhandled_exception_still_carries_cors_header():
    # Starlette routes the @app.exception_handler(Exception) handler to
    # ServerErrorMiddleware, which sits outside CORSMiddleware. Without a
    # catch-all inside the CORS layer, a genuine 500 reaches the browser
    # with no access-control-allow-origin header and the fetch is blocked
    # client-side, masking the real server error as a connectivity problem.
    app = create_app()

    @app.get("/boom-cors")
    async def boom_cors():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom-cors", headers={"Origin": DEFAULT_TEST_ORIGIN})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == DEFAULT_TEST_ORIGIN
