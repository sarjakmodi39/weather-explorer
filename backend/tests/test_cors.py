from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_allowed_origin_receives_cors_headers():
    # The default allowed origin is the Vite dev server, so no env setup here.
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_permits_post():
    client = TestClient(create_app())
    response = client.options(
        "/store-weather-data",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code in (200, 204)
    assert "POST" in response.headers["access-control-allow-methods"]


def test_origin_list_splits_and_trims():
    settings = Settings(allowed_origins="http://a.com, https://b.com ,")
    assert settings.origin_list == ["http://a.com", "https://b.com"]
