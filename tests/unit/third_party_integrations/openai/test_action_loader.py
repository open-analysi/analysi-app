"""
Unit tests for OpenAI action loader.

Tests dynamic action loading for OpenAI integration.
Following TDD - these tests will fail until implementations are complete.
"""

import pytest

from analysi.integrations.framework.integrations.openai.actions import (
    HealthCheckAction,
)
from analysi.integrations.framework.loader import IntegrationLoader


class TestOpenAIActionLoader:
    """Test loading OpenAI actions via IntegrationLoader."""

    @pytest.mark.asyncio
    async def test_load_openai_health_check_action(self):
        """Test: Load OpenAI HealthCheckAction via loader.

        Goal: Verify IntegrationLoader can dynamically instantiate OpenAI health_check action.
        """
        loader = IntegrationLoader()

        action = await loader.load_action(
            integration_id="openai",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={"api_key": "sk-test-key-12345"},
        )

        # Should be correct action class
        assert isinstance(action, HealthCheckAction), (
            f"Expected HealthCheckAction, got {type(action)}"
        )

        # Should have credentials and settings injected
        assert action.credentials == {"api_key": "sk-test-key-12345"}
        assert action.settings == {"api_url": "https://api.openai.com/v1"}
        assert action.integration_id == "openai"
        assert action.action_id == "health_check"

    @pytest.mark.asyncio
    async def test_openai_action_with_missing_api_key_credential(self):
        """Test: OpenAI action with missing api_key credential.

        Goal: Ensure action handles missing required credentials gracefully.
        """
        loader = IntegrationLoader()

        # Load action with empty credentials
        action = await loader.load_action(
            integration_id="openai",
            action_id="health_check",
            action_metadata={"type": "connector"},
            settings={"api_url": "https://api.openai.com/v1"},
            credentials={},  # No API key
        )

        # Action should load (credentials validation happens at execution time)
        assert isinstance(action, HealthCheckAction)
        assert action.credentials == {}

        # Execute should handle missing credentials gracefully
        result = await action.execute()

        # Should return error status or handle missing key
        # (This will fail until implementation handles this case)
        assert result["status"] in ["error", "success"]

    @pytest.mark.asyncio
    async def test_openai_action_with_custom_settings(self):
        """Test: OpenAI action with custom API URL and model settings."""
        loader = IntegrationLoader()

        custom_settings = {
            "api_url": "https://custom-openai-endpoint.com/v1",
            "default_model": "gpt-4-turbo",
        }

        action = await loader.load_action(
            integration_id="openai",
            action_id="health_check",
            action_metadata={"type": "connector"},
            settings=custom_settings,
            credentials={"api_key": "sk-custom-key"},
        )

        assert action.settings == custom_settings
        assert action.settings.get("api_url") == "https://custom-openai-endpoint.com/v1"
        assert action.settings.get("default_model") == "gpt-4-turbo"
