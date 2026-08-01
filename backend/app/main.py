"""Application factory."""

from fastapi import FastAPI

from app.errors import register_error_handlers
from app.routes import weather


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Explorer API",
        description="Fetches historical daily weather from Open-Meteo and stores it in GCS.",
        version="1.0.0",
    )

    register_error_handlers(app)
    app.include_router(weather.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
