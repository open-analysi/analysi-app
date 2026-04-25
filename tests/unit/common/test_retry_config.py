"""Unit tests for retry_config — centralized retry policies.

Covers:
- should_retry_http_error() with httpx.HTTPStatusError support
- integration_retry_policy() factory
- http_retry_policy() factory
"""

from unittest.mock import MagicMock

import httpx
import pytest

from analysi.common.retry_config import (
    RetryableHTTPError,
    http_retry_policy,
    integration_retry_policy,
    should_retry_http_error,
)

# ---------------------------------------------------------------------------
# should_retry_http_error
# ---------------------------------------------------------------------------


class TestShouldRetryHttpError:
    """Test the retry predicate for HTTP errors."""

    def test_retries_connect_error(self):
        assert should_retry_http_error(httpx.ConnectError("refused")) is True

    def test_retries_timeout(self):
        assert should_retry_http_error(httpx.ReadTimeout("slow")) is True

    def test_retries_connect_timeout(self):
        assert should_retry_http_error(httpx.ConnectTimeout("slow")) is True

    def test_retries_request_error(self):
        assert should_retry_http_error(httpx.RequestError("network")) is True

    def test_retries_http_status_500(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        exc = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is True

    def test_retries_http_status_502(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 502
        exc = httpx.HTTPStatusError("502", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is True

    def test_retries_http_status_503(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 503
        exc = httpx.HTTPStatusError("503", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is True

    def test_retries_http_status_429(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        exc = httpx.HTTPStatusError("429", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is True

    def test_does_not_retry_http_status_404(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 404
        exc = httpx.HTTPStatusError("404", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is False

    def test_does_not_retry_http_status_400(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 400
        exc = httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is False

    def test_does_not_retry_http_status_401(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is False

    def test_does_not_retry_http_status_403(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 403
        exc = httpx.HTTPStatusError("403", request=MagicMock(), response=resp)
        assert should_retry_http_error(exc) is False

    def test_retries_retryable_http_error_5xx(self):
        exc = RetryableHTTPError("server error", status_code=503)
        assert should_retry_http_error(exc) is True

    def test_retries_retryable_http_error_429(self):
        exc = RetryableHTTPError("rate limited", status_code=429)
        assert should_retry_http_error(exc) is True

    def test_does_not_retry_retryable_http_error_400(self):
        exc = RetryableHTTPError("bad request", status_code=400)
        assert should_retry_http_error(exc) is False

    def test_does_not_retry_unrelated_exception(self):
        assert should_retry_http_error(ValueError("oops")) is False

    def test_does_not_retry_none(self):
        assert should_retry_http_error(None) is False


# ---------------------------------------------------------------------------
# Policy factory functions
# ---------------------------------------------------------------------------


class TestIntegrationRetryPolicy:
    """Test integration_retry_policy() factory."""

    def test_returns_decorator(self):
        policy = integration_retry_policy()
        assert callable(policy)

    def test_custom_parameters(self):
        # Should not raise
        policy = integration_retry_policy(max_attempts=5, min_wait=4, max_wait=30)
        assert callable(policy)

    @pytest.mark.asyncio
    async def test_default_parameters_retries_5xx(self):
        """Decorator with defaults should retry on 5xx and then succeed."""

        # Use instant wait for test speed; keep the real retry condition.
        policy = integration_retry_policy(max_attempts=3, min_wait=0, max_wait=0)

        call_count = 0

        @policy
        async def _fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                resp = MagicMock(spec=httpx.Response)
                resp.status_code = 500
                raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
            return "ok"

        result = await _fn()
        assert result == "ok"
        assert call_count == 2


class TestHttpRetryPolicy:
    """Test http_retry_policy() factory."""

    def test_returns_decorator(self):
        policy = http_retry_policy()
        assert callable(policy)
