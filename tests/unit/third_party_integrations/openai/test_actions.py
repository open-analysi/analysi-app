"""
Unit tests for OpenAI integration actions.

Tests action execution via framework with mocked http_request.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.openai.actions import (
    HealthCheckAction,
)


def _mock_response(status_code=200, json_data=None):
    """Create a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


class TestOpenAIHealthCheckAction:
    """Test OpenAI health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1", "default_model": "gpt-4"},
            credentials={"api_key": "sk-test-key-12345"},
        )

    @pytest.mark.asyncio
    async def test_execute_openai_health_check_via_framework(self, health_check_action):
        """Test: Execute OpenAI health_check via framework."""
        mock_resp = _mock_response(
            200, {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}
        )

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await health_check_action.execute()

            assert result["status"] == "success"
            assert "message" in result
            assert "OpenAI API connection successful" in result["message"]
            assert "models_available" in result
            assert result["models_available"] == 2
            assert "endpoint" in result
            assert result["endpoint"] == "https://api.openai.com/v1"
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_openai_health_check_with_default_settings(self):
        """Test: OpenAI health check with default settings."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={},  # No custom settings
            credentials={"api_key": "sk-test"},
        )

        mock_resp = _mock_response(200, {"data": []})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

            assert result["status"] == "success"
            assert "endpoint" in result
            assert result["endpoint"] == "https://api.openai.com/v1"

    @pytest.mark.asyncio
    async def test_openai_health_check_without_credentials(self):
        """Test: OpenAI health check without API key."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={},  # No API key
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing API key" in result["message"]


class TestOpenAIHealthCheckErrorScenarios:
    """Test OpenAI health check error scenarios."""

    @pytest.mark.asyncio
    async def test_health_check_invalid_api_key(self):
        """Test health check with invalid API key (401)."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={"api_key": "invalid-key"},
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_resp
            ),
        ):
            result = await action.execute()

            assert result["status"] == "error"
            assert "Invalid API key" in result["message"] or "401" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """Test health check with connection timeout."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={"api_key": "sk-test123"},
        )

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Request timed out"),
        ):
            result = await action.execute()

            assert result["status"] == "error"
            assert (
                "timeout" in result["message"].lower()
                or "timed out" in result["message"].lower()
            )

    @pytest.mark.asyncio
    async def test_health_check_custom_endpoint(self):
        """Test health check with custom API endpoint."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://custom.openai.azure.com/v1"},
            credentials={"api_key": "sk-test123"},
        )

        mock_resp = _mock_response(200, {"data": [{"id": "gpt-4"}]})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute()

            assert result["status"] == "success"
            assert result["endpoint"] == "https://custom.openai.azure.com/v1"

            # Verify custom URL was used
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][0]
            assert "https://custom.openai.azure.com/v1/models" in call_url

    @pytest.mark.asyncio
    async def test_health_check_api_error(self):
        """Test health check with API error response (500)."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={"api_key": "sk-test123"},
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_resp
            ),
        ):
            result = await action.execute()

            assert result["status"] == "error"
            assert (
                "500" in result["message"] or "API returned status" in result["message"]
            )

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        """Test health check with connection error."""
        action = HealthCheckAction(
            integration_id="openai",
            action_id="health_check",
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={"api_key": "sk-test123"},
        )

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            result = await action.execute()

            assert result["status"] == "error"
            assert (
                "Connection failed" in result["message"]
                or "failed" in result["message"].lower()
            )
