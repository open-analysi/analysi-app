"""Unit tests for IntegrationAction.http_request() helper.

Tests the shared HTTP helper added to the base class:
- Retry behaviour via integration_retry_policy
- Header merging (get_http_headers + per-call headers)
- Timeout / SSL-verify extraction from settings
- Correct httpx call arguments for all HTTP methods
- Error propagation (4xx not retried, 5xx/429 retried)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_none,
)

from analysi.common.retry_config import should_retry_http_error
from analysi.integrations.framework.base import IntegrationAction

# ---------------------------------------------------------------------------
# Concrete test subclasses
# ---------------------------------------------------------------------------


class _PlainAction(IntegrationAction):
    """Minimal concrete action for testing."""

    async def execute(self, **kwargs):
        return {"status": "success"}


class _AuthAction(IntegrationAction):
    """Action with custom auth headers via get_http_headers()."""

    def get_http_headers(self) -> dict[str, str]:
        return {"x-apikey": self.credentials.get("api_key", "")}

    async def execute(self, **kwargs):
        return {"status": "success"}


# ---------------------------------------------------------------------------
# Helpers for httpx mock construction
# ---------------------------------------------------------------------------


def _make_mock_response(status_code: int = 200, json_data=None):
    """Build a MagicMock that quacks like httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(spec=httpx.Request),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _make_mock_client(responses):
    """Create an AsyncMock httpx.AsyncClient that yields *responses* in order.

    ``responses`` can be a single response (always returned), or a list
    (returned one-per-call; the last one is repeated if exhausted).
    """
    if not isinstance(responses, list):
        responses = [responses]

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=list(responses))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _instant_retry_policy(max_attempts: int = 3):
    """Return a retry decorator with the real retry predicate but no wait.

    Uses ``should_retry_http_error`` so 5xx/429/network errors are retried and
    4xx errors are NOT retried — exactly like production but instantaneous.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_none(),
        retry=retry_if_exception(should_retry_http_error),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHttpRequestSuccess:
    """Happy-path: request succeeds on first attempt."""

    @pytest.mark.asyncio
    async def test_get_returns_response(self):
        action = _PlainAction(
            integration_id="test", action_id="act", settings={}, credentials={}
        )
        resp = _make_mock_response(200, {"ok": True})
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            result = await action.http_request("https://api.example.com/v1/test")

        assert result.status_code == 200
        assert result.json() == {"ok": True}
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_with_json(self):
        action = _PlainAction(
            integration_id="test", action_id="act", settings={}, credentials={}
        )
        resp = _make_mock_response(201, {"id": "abc"})
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            result = await action.http_request(
                "https://api.example.com/v1/items",
                method="POST",
                json_data={"name": "widget"},
            )

        assert result.status_code == 201
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["json"] == {"name": "widget"}
        assert call_kwargs.args == ("POST", "https://api.example.com/v1/items")


class TestHttpRequestHeaders:
    """get_http_headers() merging and per-call overrides."""

    @pytest.mark.asyncio
    async def test_base_headers_from_get_http_headers(self):
        action = _AuthAction(
            integration_id="vt",
            action_id="lookup",
            settings={},
            credentials={"api_key": "KEY123"},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://vt.api/test")

        call_headers = mock_client.request.call_args.kwargs["headers"]
        assert call_headers["x-apikey"] == "KEY123"

    @pytest.mark.asyncio
    async def test_per_call_headers_merged(self):
        action = _AuthAction(
            integration_id="vt",
            action_id="lookup",
            settings={},
            credentials={"api_key": "KEY123"},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request(
                "https://vt.api/test",
                headers={"Content-Type": "application/json"},
            )

        call_headers = mock_client.request.call_args.kwargs["headers"]
        assert call_headers["x-apikey"] == "KEY123"
        assert call_headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_per_call_headers_override_base(self):
        """Per-call header with the same key wins over get_http_headers()."""
        action = _AuthAction(
            integration_id="vt",
            action_id="lookup",
            settings={},
            credentials={"api_key": "KEY123"},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request(
                "https://vt.api/test",
                headers={"x-apikey": "OVERRIDE"},
            )

        call_headers = mock_client.request.call_args.kwargs["headers"]
        assert call_headers["x-apikey"] == "OVERRIDE"


class TestHttpRequestTimeoutAndSSL:
    """Timeout and SSL verification from settings."""

    @pytest.mark.asyncio
    async def test_timeout_from_settings(self):
        action = _PlainAction(
            integration_id="t",
            action_id="a",
            settings={"timeout": 60},
            credentials={},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client) as mock_cls,
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x")

        mock_cls.assert_called_once_with(timeout=60, verify=True, cert=None)

    @pytest.mark.asyncio
    async def test_timeout_override(self):
        action = _PlainAction(
            integration_id="t",
            action_id="a",
            settings={"timeout": 60},
            credentials={},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client) as mock_cls,
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x", timeout=5)

        mock_cls.assert_called_once_with(timeout=5, verify=True, cert=None)

    @pytest.mark.asyncio
    async def test_verify_ssl_from_settings(self):
        action = _PlainAction(
            integration_id="t",
            action_id="a",
            settings={"verify_ssl": False},
            credentials={},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client) as mock_cls,
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x")

        mock_cls.assert_called_once_with(timeout=30, verify=False, cert=None)

    @pytest.mark.asyncio
    async def test_verify_cert_fallback_key(self):
        """Settings with 'verify_cert' key (used by some integrations)."""
        action = _PlainAction(
            integration_id="t",
            action_id="a",
            settings={"verify_cert": False},
            credentials={},
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client) as mock_cls,
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x")

        mock_cls.assert_called_once_with(timeout=30, verify=False, cert=None)

    @pytest.mark.asyncio
    async def test_basic_auth_passed_through(self):
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x", auth=("user", "pass"))

        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["auth"] == ("user", "pass")


class TestHttpRequestErrorHandling:
    """Error propagation and retry behaviour."""

    @pytest.mark.asyncio
    async def test_4xx_raises_without_retry(self):
        """4xx errors are NOT retried and propagate immediately."""
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp_404 = _make_mock_response(404)
        mock_client = _make_mock_client(resp_404)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=3),
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await action.http_request("https://api.test/missing")

        assert exc_info.value.response.status_code == 404
        # Only one call — 404 is not retryable
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_5xx_is_retried(self):
        """5xx errors trigger retries via should_retry_http_error."""
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp_500 = _make_mock_response(500)
        resp_200 = _make_mock_response(200, {"ok": True})
        mock_client = _make_mock_client([resp_500, resp_200])

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=3),
            ),
        ):
            result = await action.http_request("https://api.test/flaky")

        assert result.status_code == 200
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_429_is_retried(self):
        """429 rate-limit errors trigger retries."""
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp_429 = _make_mock_response(429)
        resp_200 = _make_mock_response(200)
        mock_client = _make_mock_client([resp_429, resp_200])

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=3),
            ),
        ):
            result = await action.http_request("https://api.test/limited")

        assert result.status_code == 200
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_raises_after_retries(self):
        """Network timeouts are retried then propagate."""
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=2),
            ),
        ):
            with pytest.raises(httpx.ConnectTimeout):
                await action.http_request("https://api.test/slow")

        assert mock_client.request.call_count == 2


class TestHttpRequestMethods:
    """Verify all HTTP methods are passed through correctly."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def test_method_passed_to_httpx(self, method):
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request("https://api.test/x", method=method)

        assert mock_client.request.call_args.args[0] == method

    @pytest.mark.asyncio
    async def test_form_data_post(self):
        action = _PlainAction(
            integration_id="t", action_id="a", settings={}, credentials={}
        )
        resp = _make_mock_response(200)
        mock_client = _make_mock_client(resp)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "analysi.integrations.framework.base.integration_retry_policy",
                return_value=_instant_retry_policy(max_attempts=1),
            ),
        ):
            await action.http_request(
                "https://api.test/submit",
                method="POST",
                data={"url": "https://example.com"},
            )

        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["data"] == {"url": "https://example.com"}
        assert call_kwargs["json"] is None  # Not set
