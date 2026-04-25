"""Error handling middleware with structured responses."""

import re
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from analysi.config.logging import get_logger
from analysi.schemas.base import ErrorResponse

logger = get_logger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to catch exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next):
        """Process request and handle any exceptions."""
        start_time = time.time()

        try:
            response = await call_next(request)
            return response

        except HTTPException as e:
            # Handle FastAPI HTTP exceptions
            execution_time = time.time() - start_time
            error_code, error_message = map_exception_to_error_code(e)

            return create_error_response(
                error_message=error_message,
                error_code=error_code,
                status_code=e.status_code,
                execution_time=execution_time,
            )

        except Exception as e:
            # Handle unexpected exceptions
            execution_time = time.time() - start_time
            error_code, error_message = map_exception_to_error_code(e)

            # Log the full exception for debugging
            logger.error(
                "unhandled_exception",
                error_code=error_code,
                error_message=error_message,
                path=str(request.url.path),
                method=request.method,
                execution_time=execution_time,
                exception_type=type(e).__name__,
                exc_info=True,
            )

            # In development, return detailed error information
            from analysi.config.settings import settings

            if settings.ENVIRONMENT == "development":
                import traceback

                # Sanitize both the exception message and the traceback
                sanitized_exception = _sanitize_error_message(str(e))
                full_traceback = traceback.format_exc()
                sanitized_traceback = _sanitize_error_message(full_traceback)
                error_message = f"{type(e).__name__}: {sanitized_exception}\n\nTraceback:\n{sanitized_traceback}"

            return create_error_response(
                error_message=error_message,
                error_code=error_code,
                status_code=500,
                execution_time=execution_time,
            )


def create_error_response(
    error_message: str,
    error_code: str,
    status_code: int = 500,
    context: dict[str, Any] | None = None,
    execution_time: float | None = None,
) -> JSONResponse:
    """Create a structured error response."""
    if execution_time is None:
        execution_time = 0.0

    error_data = ErrorResponse(
        error=error_message,
        error_code=error_code,
        context=context,
        execution_time=execution_time,
    )

    return JSONResponse(status_code=status_code, content=error_data.model_dump())


def map_exception_to_error_code(exception: Exception) -> tuple[str, str]:
    """Map exception type to error code and message."""
    # Handle FastAPI HTTP exceptions
    if isinstance(exception, HTTPException):
        status_code = exception.status_code
        detail = exception.detail

        # Map common HTTP status codes to error codes
        status_to_code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            500: "INTERNAL_SERVER_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }

        error_code = status_to_code.get(status_code, "HTTP_ERROR")
        error_message = _sanitize_error_message(str(detail))

        return error_code, error_message

    # Handle specific exception types
    exception_map = {
        ValueError: ("VALIDATION_ERROR", "Invalid input provided"),
        TypeError: ("VALIDATION_ERROR", "Invalid data type"),
        KeyError: ("MISSING_FIELD", "Required field is missing"),
        PermissionError: ("PERMISSION_DENIED", "Access denied"),
        ConnectionError: ("SERVICE_UNAVAILABLE", "External service unavailable"),
        TimeoutError: ("TIMEOUT", "Operation timed out"),
        NotImplementedError: ("NOT_IMPLEMENTED", "Feature not yet implemented"),
    }

    exception_type = type(exception)
    if exception_type in exception_map:
        error_code, default_message = exception_map[exception_type]
        error_message = _sanitize_error_message(str(exception)) or default_message
        return error_code, error_message

    # Generic exception handling
    error_message = (
        _sanitize_error_message(str(exception)) or "An unexpected error occurred"
    )
    return "INTERNAL_SERVER_ERROR", error_message


def _sanitize_error_message(message: str) -> str:
    """Sanitize error message to remove sensitive information."""
    if not message:
        return "An error occurred"

    # Patterns to mask sensitive information
    sensitive_patterns = [
        (r"password[=:]\s*[^\s,}]+", "password=***"),
        (r"token[=:]\s*[^\s,}]+", "token=***"),
        (r"secret[=:]\s*[^\s,}]+", "secret=***"),
        (r"key[=:]\s*[^\s,}]+", "key=***"),
        (r"credential[=:]\s*[^\s,}]+", "credential=***"),
        (r"auth[=:]\s*[^\s,}]+", "auth=***"),
        (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "***@***.***"),  # Email
    ]

    sanitized = message
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # Limit message length
    if len(sanitized) > 200:
        sanitized = sanitized[:197] + "..."

    return sanitized
