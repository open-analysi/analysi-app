"""Integration test: InternalAsyncClient unwraps Sifnos {data, meta} envelope.

Hits a real API endpoint to verify that InternalAsyncClient transparently
unwraps the response envelope, preventing the class of regression where
internal HTTP clients break after API response format changes.
"""

import httpx
import pytest

from analysi.common.internal_client import InternalAsyncClient

API_BASE = "http://localhost:8001"


@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.requires_full_stack
@pytest.mark.asyncio
class TestInternalClientEnvelopeUnwrap:
    """Verify InternalAsyncClient unwraps real API responses."""

    async def test_healthz_endpoint_unwrapped(self):
        """InternalAsyncClient should unwrap /healthz envelope to just the data."""
        async with InternalAsyncClient() as client:
            response = await client.get(f"{API_BASE}/healthz")

            assert response.status_code == 200

            body = response.json()

            # InternalAsyncClient should have unwrapped {data, meta} → data
            assert "status" in body, (
                f"Expected unwrapped data with 'status', got: {body}"
            )
            assert body["status"] == "ok"
            # meta should NOT be present (it was stripped)
            assert "meta" not in body
            assert "data" not in body  # not nested

    async def test_bare_httpx_returns_envelope(self):
        """Bare httpx.AsyncClient should return the raw {data, meta} envelope."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/healthz")

            assert response.status_code == 200

            body = response.json()

            # Bare client returns the full envelope
            assert "data" in body, f"Expected envelope with 'data' key, got: {body}"
            assert "meta" in body
            assert body["data"]["status"] == "ok"

    async def test_status_code_preserved(self):
        """Status code and other response attributes should still work."""
        async with InternalAsyncClient() as client:
            response = await client.get(f"{API_BASE}/healthz")

            assert response.status_code == 200
            assert response.is_success is True

    async def test_error_response_not_unwrapped(self):
        """Error responses (4xx) should pass through unchanged."""
        async with InternalAsyncClient() as client:
            # Hit a non-existent endpoint
            response = await client.get(f"{API_BASE}/v1/nonexistent/endpoint")

            assert response.status_code in (401, 404, 405)
            # Error body should pass through as-is, not unwrapped
            body = response.json()
            assert isinstance(body, dict)
