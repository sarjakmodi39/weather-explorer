"""Application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.routes import weather


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Explorer API",
        description="Fetches historical daily weather from Open-Meteo and stores it in GCS.",
        version="1.0.0",
    )

    # An explicit allowlist, not "*". The frontend origin is injected at deploy
    # time via ALLOWED_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().origin_list,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    register_error_handlers(app)
    app.include_router(weather.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
