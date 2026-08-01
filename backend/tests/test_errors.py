from fastapi.testclient import TestClient

from app.main import create_app


def test_apperror_is_rendered_as_uniform_envelope():
    """Any AppError must surface as {"status": "error", "message": ...}."""
    from app.errors import AppError

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise AppError("teapot trouble", status_code=418)

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == 418
    assert response.json() == {"status": "error", "message": "teapot trouble"}


def test_unhandled_exception_does_not_leak_internals():
    app = create_app()

    @app.get("/explode")
    async def explode():
        raise RuntimeError("secret connection string")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/explode")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert "secret connection string" not in body["message"]


def test_validation_error_maps_to_400_not_422():
    """FastAPI defaults request validation failures to 422; we deliberately
    remap to 400 so every failure mode in the API uses the same status-code
    family and the same uniform envelope."""
    app = create_app()

    @app.get("/validate")
    async def validate(count: int):
        return {"count": count}

    client = TestClient(app)
    response = client.get("/validate", params={"count": "not-a-number"})

    assert response.status_code == 400
    assert response.status_code != 422
    body = response.json()
    assert set(body.keys()) == {"status", "message"}
    assert body["status"] == "error"
    assert isinstance(body["message"], str) and body["message"]


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
