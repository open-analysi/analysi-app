"""Tests for InternalAsyncClient — Sifnos envelope auto-unwrapping."""

import httpx
import pytest

from analysi.common.internal_client import InternalAsyncClient


class TestEnvelopeUnwrapping:
    """Test that InternalAsyncClient auto-unwraps Sifnos envelope."""

    @pytest.mark.asyncio
    async def test_unwraps_single_item_envelope(self, httpx_mock):
        """Successful response with {data: {...}, meta: {...}} unwraps to inner data."""
        httpx_mock.add_response(
            json={"data": {"id": "123", "name": "test"}, "meta": {"request_id": "abc"}},
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/item")
            result = response.json()

        assert result == {"id": "123", "name": "test"}

    @pytest.mark.asyncio
    async def test_unwraps_list_envelope(self, httpx_mock):
        """Successful response with {data: [...], meta: {...}} unwraps to list."""
        httpx_mock.add_response(
            json={"data": [{"id": "1"}, {"id": "2"}], "meta": {"total": 2}},
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/items")
            result = response.json()

        assert result == [{"id": "1"}, {"id": "2"}]

    @pytest.mark.asyncio
    async def test_preserves_error_response(self, httpx_mock):
        """Error responses (4xx) should NOT be unwrapped."""
        httpx_mock.add_response(
            json={"detail": "Not found"},
            status_code=404,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/missing")
            result = response.json()

        assert result == {"detail": "Not found"}
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preserves_server_error_response(self, httpx_mock):
        """5xx responses should NOT be unwrapped."""
        httpx_mock.add_response(
            json={"detail": "Internal server error"},
            status_code=500,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/broken")
            result = response.json()

        assert result == {"detail": "Internal server error"}

    @pytest.mark.asyncio
    async def test_preserves_non_envelope_response(self, httpx_mock):
        """Responses without Sifnos envelope pass through unchanged."""
        httpx_mock.add_response(
            json={"workflow_run_id": "abc", "status": "running"},
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/legacy")
            result = response.json()

        assert result == {"workflow_run_id": "abc", "status": "running"}

    @pytest.mark.asyncio
    async def test_preserves_plain_list_response(self, httpx_mock):
        """Plain list responses (no envelope) pass through unchanged."""
        httpx_mock.add_response(
            json=[{"id": "1"}, {"id": "2"}],
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/plain-list")
            result = response.json()

        assert result == [{"id": "1"}, {"id": "2"}]

    @pytest.mark.asyncio
    async def test_status_code_accessible(self, httpx_mock):
        """Response attributes like status_code are still accessible."""
        httpx_mock.add_response(
            json={"data": {"id": "1"}, "meta": {}},
            status_code=201,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/create")

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_raise_for_status_works(self, httpx_mock):
        """raise_for_status() still works on wrapped responses."""
        httpx_mock.add_response(
            json={"detail": "Forbidden"},
            status_code=403,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/forbidden")

            with pytest.raises(httpx.HTTPStatusError):
                response.raise_for_status()

    @pytest.mark.asyncio
    async def test_post_unwraps(self, httpx_mock):
        """POST responses are also unwrapped."""
        httpx_mock.add_response(
            json={"data": {"run_id": "r-1"}, "meta": {}},
            status_code=201,
        )

        async with InternalAsyncClient() as client:
            response = await client.post(
                "https://test.local/api/runs",
                json={"input": "test"},
            )
            result = response.json()

        assert result == {"run_id": "r-1"}

    @pytest.mark.asyncio
    async def test_patch_unwraps(self, httpx_mock):
        """PATCH responses are also unwrapped."""
        httpx_mock.add_response(
            json={"data": {"status": "updated"}, "meta": {}},
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.patch(
                "https://test.local/api/item/1",
                json={"status": "done"},
            )
            result = response.json()

        assert result == {"status": "updated"}

    @pytest.mark.asyncio
    async def test_text_attribute_preserved(self, httpx_mock):
        """response.text still returns the raw body."""
        httpx_mock.add_response(
            json={"data": {"id": "1"}, "meta": {}},
            status_code=200,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/item")

        # .text should return the raw JSON string, not unwrapped
        assert "data" in response.text
        assert "meta" in response.text

    @pytest.mark.asyncio
    async def test_error_response_with_data_key_not_unwrapped(self, httpx_mock):
        """A 4xx response that happens to have 'data' key should NOT unwrap."""
        httpx_mock.add_response(
            json={"data": None, "meta": {}, "detail": "Validation failed"},
            status_code=422,
        )

        async with InternalAsyncClient() as client:
            response = await client.get("https://test.local/api/invalid")
            result = response.json()

        # Should NOT unwrap because status is 4xx
        assert result == {"data": None, "meta": {}, "detail": "Validation failed"}
