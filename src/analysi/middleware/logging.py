"""Request/response logging middleware with structured logging and correlation IDs."""

import contextlib
import time
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from analysi.common.correlation import get_correlation_id
from analysi.config.log_sanitizer import _is_sensitive, _redact_value
from analysi.config.logging import get_logger

logger = get_logger(__name__)


def sanitize_dict(data: dict) -> dict:
    """Recursively sanitize sensitive data from dictionaries.

    Uses the shared sensitive-key definitions from log_sanitizer.
    """
    if not isinstance(data, dict):
        return data

    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive(key):
            sanitized[key] = _redact_value(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests and responses in structured JSON format."""

    async def dispatch(self, request: Request, call_next):
        """Process request and log details with correlation ID."""
        # correlation_id is set by RequestIdMiddleware via ContextVar.
        # The inject_context structlog processor adds it to every log event
        # automatically — no need for manual bind_request_context().
        correlation_id = (
            get_correlation_id()
            or getattr(request.state, "request_id", None)
            or generate_correlation_id()
        )

        # Keep correlation_id on state for any code that reads it directly
        request.state.correlation_id = correlation_id

        # Use module-level logger — correlation context injected by processor
        request_logger = logger.bind(api="rest")

        # Capture request body for POST/PUT/PATCH
        request_body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Store the body for later use
                body_bytes = await request.body()
                request._body = body_bytes  # Store for endpoint use
                if body_bytes:
                    import json

                    try:
                        parsed_body = json.loads(body_bytes.decode())
                        # Sanitize sensitive data before logging
                        request_body = (
                            sanitize_dict(parsed_body)
                            if isinstance(parsed_body, dict)
                            else parsed_body
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        request_body = "<binary or non-JSON data>"
            except Exception as e:
                request_body = f"<error reading body: {e}>"

        # Log incoming request with sanitized body if available
        log_data: dict[str, Any] = {
            "method": request.method,
            "path": str(request.url.path),
        }
        if request_body and request.method in ["POST", "PUT", "PATCH"]:
            log_data["request_body"] = request_body

        request_logger.info("request_start", **log_data)

        # Track timing
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)
            execution_time = time.time() - start_time

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            # Capture response body for errors
            response_body = None
            if response.status_code >= 400:
                try:
                    # Read response body
                    body_bytes = b""
                    async for chunk in response.body_iterator:
                        body_bytes += chunk

                    if body_bytes:
                        import json

                        try:
                            parsed_response = json.loads(body_bytes.decode())
                            # Sanitize sensitive data in error responses too
                            response_body = (
                                sanitize_dict(parsed_response)
                                if isinstance(parsed_response, dict)
                                else parsed_response
                            )
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            response_body = body_bytes.decode(errors="ignore")

                    # Create new response with the same body
                    from fastapi.responses import Response

                    response = Response(
                        content=body_bytes,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
                except Exception as e:
                    response_body = f"<error reading response: {e}>"

            # Log response with body for errors
            log_level = (
                "error"
                if response.status_code >= 500
                else "warning"
                if response.status_code >= 400
                else "info"
            )

            response_log_data: dict[str, Any] = {
                "status_code": response.status_code,
                "execution_time": round(execution_time, 4),
            }

            if response_body and response.status_code >= 400:
                response_log_data["response_body"] = response_body
                # Add specific error details for common cases
                if response.status_code == 409 and isinstance(response_body, dict):
                    response_log_data["error_detail"] = response_body.get(
                        "error", "Duplicate detected"
                    )

            getattr(request_logger, log_level)("request_complete", **response_log_data)

            return response

        except Exception as e:
            # Log error and re-raise
            execution_time = time.time() - start_time

            request_logger.error(
                "request_error",
                method=request.method,
                path=str(request.url.path),
                execution_time=round(execution_time, 4),
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            raise


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())


def get_request_body_info(request: Request) -> dict[str, Any]:
    """Extract safe information from request body for logging."""
    info: dict[str, Any] = {}

    # Add basic request metadata
    info["method"] = request.method
    info["content_type"] = request.headers.get("content-type", "")

    # Add content length if available
    content_length = request.headers.get("content-length")
    if content_length:
        with contextlib.suppress(ValueError):
            info["content_length"] = int(content_length)

    # Add query parameters (filtered for sensitive data)
    if request.query_params:
        safe_params = {}
        for key, value in request.query_params.items():
            # Filter out potentially sensitive parameters
            sensitive_keys = ["password", "token", "secret", "key", "auth"]
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                safe_params[key] = "***"
            else:
                # Limit length of parameter values
                if len(str(value)) > 100:
                    safe_params[key] = str(value)[:97] + "..."
                else:
                    safe_params[key] = value

        info["query_params"] = safe_params

    # Add headers (filtered for sensitive data)
    safe_headers = {}
    for key, value in request.headers.items():
        # Always filter out authorization and cookie headers
        if (
            key.lower() in ["authorization", "cookie", "x-api-key"]
            or "token" in key.lower()
            or "secret" in key.lower()
        ):
            safe_headers[key] = "***"
        else:
            safe_headers[key] = value

    info["headers"] = safe_headers

    return info
