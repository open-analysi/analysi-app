"""Unit tests for RequestIdMiddleware.

Verifies UUID generation, header injection, and duration measurement.
"""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from analysi.api.middleware import RequestIdMiddleware


@pytest.fixture
def app():
    """Minimal FastAPI app with only RequestIdMiddleware."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo-request-id")
    async def echo(request: Request):
        return {"request_id": getattr(request.state, "request_id", "missing")}

    return app


class TestRequestIdMiddleware:
    @pytest.mark.asyncio
    async def test_injects_request_id_into_state(self, app):
        """Handler can read request.state.request_id."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/echo-request-id")

        data = resp.json()
        assert data["request_id"] != "missing"
        # Should be a valid UUID format (8-4-4-4-12)
        parts = data["request_id"].split("-")
        assert len(parts) == 5

    @pytest.mark.asyncio
    async def test_adds_x_request_id_header(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/echo-request-id")

        assert "x-request-id" in resp.headers
        # Header value matches what the handler saw in state
        assert resp.headers["x-request-id"] == resp.json()["request_id"]

    @pytest.mark.asyncio
    async def test_adds_x_request_duration_header(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/echo-request-id")

        assert "x-request-duration" in resp.headers
        duration = float(resp.headers["x-request-duration"])
        assert duration >= 0

    @pytest.mark.asyncio
    async def test_unique_ids_per_request(self, app):
        """Each request gets a different UUID."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get("/echo-request-id")
            resp2 = await client.get("/echo-request-id")

        assert resp1.json()["request_id"] != resp2.json()["request_id"]

    @pytest.mark.asyncio
    async def test_passthrough_for_non_http(self):
        """Non-HTTP scopes (like lifespan) should pass through without error."""
        from analysi.api.middleware import RequestIdMiddleware

        calls = []

        async def mock_app(scope, receive, send):
            calls.append(scope["type"])

        middleware = RequestIdMiddleware(mock_app)
        await middleware({"type": "lifespan"}, None, None)

        assert calls == ["lifespan"]
