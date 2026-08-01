"""A single error contract for the whole API.

Every failure — validation, not-found, upstream, or unexpected — leaves the
service as {"status": "error", "message": "..."}. One shape for the frontend
to parse is worth more than per-case fidelity.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Raised anywhere in the app to produce a controlled error response."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def error_body(message: str) -> dict:
    return {"status": "error", "message": message}


def _readable(exc: RequestValidationError) -> str:
    """Turn pydantic's first error into one human sentence.

    pydantic prefixes messages raised from validators with "Value error, ";
    strip it so the client sees the sentence we actually wrote.
    """
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"] if part != "body")
    message = str(first["msg"]).removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 400 rather than FastAPI's default 422 — the brief asks for 400.
        return JSONResponse(status_code=400, content=error_body(_readable(exc)))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(str(exc.detail)))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the real cause; return an opaque message so nothing leaks.
        logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=error_body("internal server error"))
