"""
Unit tests for VirusTotal integration actions — 404 handling and form data.

Tests that 404 (resource not found) returns a success response with zero
counts instead of propagating as a fatal error to Cy scripts.

After the tenacity-consistency refactor, actions use the base-class
``http_request()`` helper.  404s arrive as ``httpx.HTTPStatusError`` with
``status_code == 404`` rather than ``Exception("Resource not found")``.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.virustotal.actions import (
    DomainReputationAction,
    FileReputationAction,
    IpReputationAction,
    SubmitUrlAnalysisAction,
    UrlReputationAction,
)

CREDS = {"api_key": "test-api-key"}
SETTINGS = {"timeout": 5}


_SENTINEL = object()


def _make_action(action_class, credentials=_SENTINEL, settings=_SENTINEL):
    return action_class(
        integration_id="virustotal-test",
        action_id="test",
        settings=SETTINGS if settings is _SENTINEL else settings,
        credentials=CREDS if credentials is _SENTINEL else credentials,
    )


def _make_404_error():
    """Create an httpx.HTTPStatusError for a 404 response."""
    request = httpx.Request("GET", "https://www.virustotal.com/api/v3/test")
    response = httpx.Response(404, request=request)
    return httpx.HTTPStatusError("Not Found", request=request, response=response)


class TestIpReputation404:
    """IP reputation should return success with zero counts on 404."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(IpReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(ip="192.168.1.1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["reputation_summary"]["malicious"] == 0
        assert result["reputation_summary"]["suspicious"] == 0
        assert result["reputation_summary"]["harmless"] == 0
        assert result["reputation_summary"]["undetected"] == 0

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(IpReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(ip="192.168.1.1")

        assert result["status"] == "error"
        assert "Rate limit" in result["error"]


class TestDomainReputation404:
    """Domain reputation should return success with zero counts on 404."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(DomainReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(domain="nonexistent-domain.xyz")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["reputation_summary"]["malicious"] == 0

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(DomainReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await action.execute(domain="example.com")

        assert result["status"] == "error"


class TestUrlReputation404:
    """URL reputation should return success with zero counts on 404."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(UrlReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(url="https://nonexistent-url.xyz/page")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["reputation_summary"]["malicious"] == 0

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(UrlReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("HTTP 500: Internal Server Error"),
        ):
            result = await action.execute(url="https://example.com/page")

        assert result["status"] == "error"


class TestFileReputation404:
    """File reputation should return success with zero counts on 404."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(FileReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(file_hash="d41d8cd98f00b204e9800998ecf8427e")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["reputation_summary"]["malicious"] == 0

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(FileReputationAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(file_hash="d41d8cd98f00b204e9800998ecf8427e")

        assert result["status"] == "error"


class TestSubmitUrlAnalysis:
    """SubmitUrlAnalysisAction must POST form-encoded data, not JSON.

    VirusTotal's POST /urls endpoint requires application/x-www-form-urlencoded.
    Sending JSON causes a 400 error at runtime.
    """

    @pytest.mark.asyncio
    async def test_submit_url_passes_form_data(self):
        """Verify submit_url_analysis sends form-encoded data via http_request."""
        from unittest.mock import MagicMock

        action = _make_action(SubmitUrlAnalysisAction)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"id": "analysis-123", "type": "analysis"}
        }

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            result = await action.execute(url="https://example.com")

        assert result["status"] == "success"
        assert result["analysis_id"] == "analysis-123"

        # Verify form data was passed (not json)
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["data"] == {"url": "https://example.com"}
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_submit_url_validation_error(self):
        action = _make_action(SubmitUrlAnalysisAction)
        result = await action.execute(url="not-a-url")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_submit_url_missing_api_key(self):
        action = _make_action(SubmitUrlAnalysisAction, credentials={})
        result = await action.execute(url="https://example.com")
        assert result["status"] == "error"
        assert "API key" in result["error"]

    @pytest.mark.asyncio
    async def test_submit_url_error_handling(self):
        action = _make_action(SubmitUrlAnalysisAction)

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert "Rate limit" in result["error"]
