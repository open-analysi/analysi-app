"""Internal service-to-service HTTP client with Sifnos envelope unwrapping.

All internal API calls (worker → API, worker → worker) should use
InternalAsyncClient instead of httpx.AsyncClient.  This auto-unwraps
the Sifnos response envelope {"data": ..., "meta": ...} so callers
always get the payload directly from response.json().
"""

from typing import Any

import httpx


class _UnwrappedResponse:
    """Proxy around httpx.Response that auto-unwraps Sifnos envelope on .json().

    Only unwraps successful (2xx) responses that match the envelope shape.
    Error responses, non-JSON, and non-envelope payloads pass through unchanged.
    """

    __slots__ = ("_response",)

    def __init__(self, response: httpx.Response):
        self._response = response

    def json(self, **kwargs) -> Any:
        body = self._response.json(**kwargs)
        if (
            self._response.is_success
            and isinstance(body, dict)
            and "data" in body
            and "meta" in body
        ):
            return body["data"]
        return body

    def __getattr__(self, name):
        return getattr(self._response, name)


class InternalAsyncClient(httpx.AsyncClient):
    """httpx.AsyncClient for internal service-to-service calls.

    Auto-unwraps Sifnos API envelope on successful responses:
        {"data": <payload>, "meta": {...}}  →  <payload>

    Usage — drop-in replacement for httpx.AsyncClient:
        async with InternalAsyncClient(base_url=...) as client:
            response = await client.get("/v1/tenant/items")
            items = response.json()  # already unwrapped list
    """

    async def request(self, *args, **kwargs):
        response = await super().request(*args, **kwargs)
        return _UnwrappedResponse(response)
