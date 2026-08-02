"""Application factory."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import error_body, register_error_handlers
from app.routes import weather

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Explorer API",
        description="Fetches historical daily weather from Open-Meteo and stores it in GCS.",
        version="1.0.0",
    )

    # Starlette routes @app.exception_handler(Exception) to ServerErrorMiddleware,
    # which sits outside CORSMiddleware in the stack. A genuine 500 would then
    # reach the browser with no access-control-allow-origin header, so the
    # fetch gets blocked client-side and looks like a connectivity problem
    # instead of a server error. This catches unhandled exceptions from
    # inside the CORS layer so the response still carries the header.
    # `add_middleware` inserts at index 0, so registering this before
    # CORSMiddleware below makes CORSMiddleware the outermost layer.
    @app.middleware("http")
    async def _catch_unexpected(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("unhandled error")
            return JSONResponse(status_code=500, content=error_body("internal server error"))

    # An explicit allowlist, not "*". The frontend origin is injected at deploy
    # time via ALLOWED_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().origin_list,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # Kept as a last-resort backstop: any exception that escapes the
    # middleware above (e.g. raised by middleware itself) is still caught
    # here so the response envelope stays uniform.
    register_error_handlers(app)
    app.include_router(weather.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
