"""Request ID and duration middleware.

Project Sifnos — Unified API Response Contract.
Pure ASGI middleware (no BaseHTTPMiddleware) for maximum compatibility
with streaming responses.
"""

from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from analysi.common.correlation import set_correlation_id


class RequestIdMiddleware:
    """Generate a UUID per request and measure wall-clock duration.

    - Stores request_id in ``scope["state"]`` so downstream code can
      read it via ``request.state.request_id``.
    - Adds ``X-Request-Id`` and ``X-Request-Duration`` response headers.
    - Runs as the outermost middleware so duration captures the full
      processing time including all inner middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        start_time = time.monotonic()

        # Make request_id available to all downstream middleware and handlers
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Set correlation_id ContextVar so all structlog events include it
        set_correlation_id(request_id)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                duration_ms = round((time.monotonic() - start_time) * 1000, 2)
                headers.append((b"x-request-id", request_id.encode()))
                headers.append((b"x-request-duration", str(duration_ms).encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
