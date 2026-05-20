"""Unit tests for retry_config — centralized retry policies.

Covers:
- should_retry_http_error() with httpx.HTTPStatusError support
- should_retry_llm_error() with status_code precedence and pattern matching
- should_retry_database_error() and should_retry_storage_error()
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
    should_retry_database_error,
    should_retry_http_error,
    should_retry_llm_error,
    should_retry_storage_error,
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


# ---------------------------------------------------------------------------
# should_retry_llm_error
# ---------------------------------------------------------------------------


class _LLMError(Exception):
    """Plain exception used for message-based retry tests."""


class _LLMErrorWithStatus(Exception):
    """Exception that carries a ``status_code`` attribute (mirrors OpenAI SDK)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class TestShouldRetryLlmError:
    """Test the retry predicate for LLM API errors.

    Critical bug we guard against: substring-matching against bare
    HTTP status codes (e.g. "500") falsely retries permanent client
    errors whose messages mention numbers like "9500 tokens".  The
    predicate must rely on explicit ``status_code``/``http_status``
    attributes when available, and only fall back to **semantic**
    message patterns — not numeric substrings.
    """

    # --- Permanent (4xx, non-429) errors must NOT be retried ---------------

    def test_token_limit_error_is_not_retried(self):
        """OpenAI BadRequestError for context-length: status 400, message
        contains "9500 tokens" — must not match the old "500" substring."""
        exc = _LLMErrorWithStatus(
            "This model's maximum context length is 8192 tokens. "
            "However, your messages resulted in 9500 tokens.",
            status_code=400,
        )
        assert should_retry_llm_error(exc) is False

    def test_invalid_request_with_5xx_substring_is_not_retried(self):
        """A 400 BadRequest whose message happens to mention port 8500."""
        exc = _LLMErrorWithStatus(
            "Invalid request. See https://api.example.com:8500/docs",
            status_code=400,
        )
        assert should_retry_llm_error(exc) is False

    def test_auth_error_404_is_not_retried(self):
        exc = _LLMErrorWithStatus("Not Found", status_code=404)
        assert should_retry_llm_error(exc) is False

    def test_auth_error_401_is_not_retried(self):
        exc = _LLMErrorWithStatus("Invalid API key", status_code=401)
        assert should_retry_llm_error(exc) is False

    def test_permission_403_is_not_retried(self):
        exc = _LLMErrorWithStatus("Forbidden", status_code=403)
        assert should_retry_llm_error(exc) is False

    def test_token_limit_message_without_status_attr_is_not_retried(self):
        """Even without status_code, a token-limit message must not be retried
        merely because '9500' contains the substring '500'."""
        exc = _LLMError("Context length exceeded: 9500 tokens exceeds 8192 limit")
        assert should_retry_llm_error(exc) is False

    # --- Transient errors should still be retried --------------------------

    def test_status_500_retried(self):
        exc = _LLMErrorWithStatus("Internal Server Error", status_code=500)
        assert should_retry_llm_error(exc) is True

    def test_status_502_retried(self):
        exc = _LLMErrorWithStatus("Bad Gateway", status_code=502)
        assert should_retry_llm_error(exc) is True

    def test_status_503_retried(self):
        exc = _LLMErrorWithStatus("Service Unavailable", status_code=503)
        assert should_retry_llm_error(exc) is True

    def test_status_504_retried(self):
        exc = _LLMErrorWithStatus("Gateway Timeout", status_code=504)
        assert should_retry_llm_error(exc) is True

    def test_status_429_retried(self):
        exc = _LLMErrorWithStatus("Too Many Requests", status_code=429)
        assert should_retry_llm_error(exc) is True

    def test_http_status_attr_alias_retried(self):
        """Some SDKs use ``http_status`` instead of ``status_code``."""
        exc = _LLMError("Server error")
        exc.http_status = 503
        assert should_retry_llm_error(exc) is True

    def test_rate_limit_message_retried(self):
        exc = _LLMError("Rate limit reached for requests")
        assert should_retry_llm_error(exc) is True

    def test_connection_error_retried(self):
        exc = _LLMError("Connection reset by peer")
        assert should_retry_llm_error(exc) is True

    def test_timeout_message_retried(self):
        exc = _LLMError("Request timeout after 30s")
        assert should_retry_llm_error(exc) is True

    def test_internal_server_error_phrase_retried(self):
        """Semantic phrase, not bare status substring."""
        exc = _LLMError("upstream returned internal server error")
        assert should_retry_llm_error(exc) is True

    def test_retryable_exception_name(self):
        """Type name match should still work."""

        class RateLimitError(Exception):
            pass

        assert should_retry_llm_error(RateLimitError("oops")) is True

    def test_unknown_exception_not_retried(self):
        assert should_retry_llm_error(ValueError("bad input")) is False


# ---------------------------------------------------------------------------
# should_retry_database_error
# ---------------------------------------------------------------------------


class TestShouldRetryDatabaseError:
    def test_unique_violation_not_retried(self):
        class IntegrityError(Exception):
            pass

        exc = IntegrityError(
            "duplicate key value violates unique constraint 'pk_users'"
        )
        assert should_retry_database_error(exc) is False

    def test_operational_error_retried(self):
        class OperationalError(Exception):
            pass

        assert should_retry_database_error(OperationalError("server gone away")) is True

    def test_connection_message_retried(self):
        class SomeErr(Exception):
            pass

        assert should_retry_database_error(SomeErr("connection refused")) is True

    def test_deadlock_retried(self):
        class SomeErr(Exception):
            pass

        assert should_retry_database_error(SomeErr("deadlock detected")) is True


# ---------------------------------------------------------------------------
# should_retry_storage_error
# ---------------------------------------------------------------------------


class TestShouldRetryStorageError:
    def test_access_denied_not_retried(self):
        class ClientError(Exception):
            pass

        assert should_retry_storage_error(ClientError("Access Denied")) is False

    def test_throttling_retried(self):
        class ClientError(Exception):
            pass

        assert should_retry_storage_error(ClientError("Throttle: SlowDown")) is True

    def test_connect_error_retried(self):
        assert should_retry_storage_error(httpx.ConnectError("nope")) is True

    def test_slow_down_retried(self):
        class ClientError(Exception):
            pass

        assert should_retry_storage_error(ClientError("please slow down")) is True
