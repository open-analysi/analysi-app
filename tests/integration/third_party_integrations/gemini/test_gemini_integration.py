"""
Integration tests for Google Gemini framework integration.

End-to-end tests for Gemini integration via Naxos framework.
"""

import httpx
import pytest

from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
class TestGeminiIntegrationRegistry:
    """Registry discovery tests for Gemini."""

    async def test_gemini_discovered_by_registry(self):
        """Test: Registry returns Gemini with AI archetype."""
        registry = IntegrationRegistry()

        integrations = registry.list_integrations()
        gemini = next((i for i in integrations if i.id == "gemini"), None)

        assert gemini is not None, "Gemini should be discovered by registry"
        assert gemini.name == "Google Gemini"
        assert "AI" in gemini.archetypes, (
            f"Gemini should have AI archetype, got {gemini.archetypes}"
        )
        assert gemini.priority == 75
        assert len(gemini.actions) == 4

    async def test_registry_includes_gemini_alongside_openai(self):
        """Test: Registry lists both OpenAI and Gemini as AI integrations."""
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()
        ids = [i.id for i in integrations]

        assert "openai" in ids, "Should have OpenAI"
        assert "gemini" in ids, "Should have Gemini"

        openai = next(i for i in integrations if i.id == "openai")
        gemini = next(i for i in integrations if i.id == "gemini")
        assert "AI" in openai.archetypes
        assert "AI" in gemini.archetypes


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeminiHealthCheckAction:
    """Health check action tests for Gemini."""

    async def test_gemini_health_check_success(self):
        """Test: Gemini health check returns success on 200 response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from analysi.integrations.framework.integrations.gemini.actions import (
            HealthCheckAction,
        )

        action = HealthCheckAction(
            integration_id="gemini-main",
            action_id="health_check",
            settings={},
            credentials={"api_key": "AIza-test"},
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "models/gemini-2.0-flash"},
                {"name": "models/gemini-1.5-pro"},
            ]
        }

        with patch.object(
            action, "_make_request", new=AsyncMock(return_value=mock_response)
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["models_available"] == 2
        assert "Gemini API connection successful" in result["message"]

    async def test_gemini_health_check_missing_api_key(self):
        """Test: Gemini health check returns error when API key missing."""
        from analysi.integrations.framework.integrations.gemini.actions import (
            HealthCheckAction,
        )

        action = HealthCheckAction(
            integration_id="gemini-main",
            action_id="health_check",
            settings={},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["message"] == "Missing API key"
        assert result["models_available"] == 0

    async def test_gemini_health_check_invalid_key(self):
        """Test: Gemini health check returns error on 403 response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from analysi.integrations.framework.integrations.gemini.actions import (
            HealthCheckAction,
        )

        action = HealthCheckAction(
            integration_id="gemini-main",
            action_id="health_check",
            settings={},
            credentials={"api_key": "AIza-invalid"},
        )

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(
            action, "_make_request", new=AsyncMock(return_value=mock_response)
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "permission" in result["message"].lower()
