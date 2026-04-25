"""RFC 9457 Problem Details error handling.

Project Sifnos — Unified API Response Contract.
Registers exception handlers that return RFC 9457 ``application/problem+json``
responses with ``request_id`` as a custom extension field.

Uses ``ProblemResponse`` from ``fastapi-problem-details`` for the response
format but registers all handlers directly (no ``init_app`` call) so we
have full control over handler registration order and request_id injection.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi_problem_details import ProblemResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from analysi.config.logging import get_logger

logger = get_logger(__name__)


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make Pydantic validation errors JSON-serializable.

    The ``ctx`` dict can contain live Python exception objects (e.g.
    ``ValueError``) which are not serializable.  Convert them to strings.
    """
    sanitized = []
    for err in errors:
        clean = dict(err)
        if "ctx" in clean and isinstance(clean["ctx"], dict):
            clean["ctx"] = {
                k: str(v)
                if not isinstance(v, (str, int, float, bool, type(None)))
                else v
                for k, v in clean["ctx"].items()
            }
        sanitized.append(clean)
    return sanitized


def init_error_handling(app: FastAPI) -> None:
    """Wire up RFC 9457 error responses with request_id injection.

    Registers handlers for HTTPException, RequestValidationError,
    SQLAlchemyError, and generic Exception. Each returns a
    ``ProblemResponse`` (Content-Type: application/problem+json)
    with ``request_id`` from the current request state.
    """

    # -- Override built-in handlers to inject request_id -----------------

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> ProblemResponse:
        extras: dict[str, Any] = {"request_id": _get_request_id(request)}
        if isinstance(exc.detail, str):
            detail = exc.detail
        elif isinstance(exc.detail, (dict, list)):
            # Preserve structured detail (e.g. HTTPException(detail={...}))
            detail = "Request error"
            extras["detail_data"] = exc.detail
        else:
            detail = str(exc.detail)
        resp = ProblemResponse(
            status=exc.status_code,
            detail=detail,
            **extras,
        )
        # Preserve headers from the exception (e.g. WWW-Authenticate)
        if exc_headers := getattr(exc, "headers", None):
            resp.headers.update(exc_headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> ProblemResponse:
        return ProblemResponse(
            status=422,
            title="Validation Error",
            detail="Request validation failed",
            request_id=_get_request_id(request),
            errors=_sanitize_validation_errors(exc.errors()),  # type: ignore[arg-type]
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        request: Request, exc: SQLAlchemyError
    ) -> ProblemResponse:
        """Return 503 without leaking DB internals."""
        logger.error(
            "database_error",
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return ProblemResponse(
            status=503,
            detail="Database temporarily unavailable. Please retry.",
            request_id=_get_request_id(request),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> ProblemResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return ProblemResponse(
            status=500,
            detail="Internal server error",
            request_id=_get_request_id(request),
        )
