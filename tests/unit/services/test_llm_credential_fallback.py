"""Unit tests for LLM credential handling via IntegrationService.

Verifies that CyLLMFunctions delegates credential resolution to the
IntegrationService (which handles credentials internally via execute_action).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.cy_llm_functions import CyLLMFunctions


def _make_mock_integration(
    integration_id="openai-test",
    integration_type="openai",
    settings=None,
):
    """Create a mock integration object with expected attributes."""
    mock = MagicMock()
    mock.integration_id = integration_id
    mock.integration_type = integration_type
    mock.settings = settings or {}
    return mock


def _make_execute_action_result(response_text="Test response"):
    """Create a standard execute_action return value."""
    return {
        "status": "success",
        "data": {
            "response": response_text,
            "message": {"role": "assistant", "content": response_text},
            "input_tokens": 10,
            "output_tokens": 5,
        },
    }


class TestLLMCredentialHandling:
    """Test that CyLLMFunctions uses IntegrationService for credential resolution."""

    @pytest.mark.asyncio
    async def test_raises_error_when_no_ai_integrations_configured(self):
        """Test error when no AI integrations are configured for tenant."""
        mock_service = AsyncMock()
        mock_service.list_integrations.return_value = []

        execution_context = {
            "tenant_id": "tenant1",
            "session": MagicMock(),
        }

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with pytest.raises(RuntimeError, match="LLM execution failed"):
            # Patch the registry so _resolve_primary_ai_integration can discover
            # AI types, but list_integrations returns empty -> ValueError -> RuntimeError
            with patch(
                "analysi.integrations.framework.registry.get_registry"
            ) as mock_registry:
                mock_registry.return_value.list_by_archetype.return_value = [
                    MagicMock(id="openai"),
                    MagicMock(id="anthropic"),
                ]
                await cy_llm.llm_run(prompt="Hello")

    @pytest.mark.asyncio
    async def test_execute_action_receives_resolved_integration(self):
        """Test that execute_action is called with the resolved integration details."""
        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result()

        execution_context = {
            "tenant_id": "tenant1",
            "session": MagicMock(),
        }

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(cy_llm, "_create_llm_artifact", new=AsyncMock()),
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-tenant", "openai", None)),
            ),
        ):
            await cy_llm.llm_run(prompt="Hello")

            # Verify execute_action was called with the correct integration details
            mock_service.execute_action.assert_called_once()
            call_kwargs = mock_service.execute_action.call_args.kwargs
            assert call_kwargs["tenant_id"] == "tenant1"
            assert call_kwargs["integration_id"] == "openai-tenant"
            assert call_kwargs["integration_type"] == "openai"
            assert call_kwargs["action_id"] == "llm_run"
            assert "params" in call_kwargs


class TestCyLLMFunctionsCredentialDelegation:
    """Test that CyLLMFunctions delegates credential handling to IntegrationService."""

    @pytest.mark.asyncio
    async def test_cy_functions_use_integration_service_for_credentials(self):
        """Test that CyLLMFunctions uses IntegrationService which handles credentials internally."""
        execution_context = {
            "tenant_id": "test-tenant",
            "task_id": "test-task-123",
            "session": MagicMock(),
        }

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Test response"
        )

        llm_functions = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(llm_functions, "_create_llm_artifact", new=AsyncMock()),
            patch.object(
                llm_functions,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            result = await llm_functions.llm_run("Test prompt")

            assert result == "Test response"

            # Verify IntegrationService.execute_action was called (credentials are
            # resolved internally by the framework, not by CyLLMFunctions)
            mock_service.execute_action.assert_called_once()
            call_kwargs = mock_service.execute_action.call_args.kwargs
            assert call_kwargs["integration_id"] == "openai-test"
            assert call_kwargs["integration_type"] == "openai"
            assert call_kwargs["params"]["prompt"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_cy_functions_pass_session_to_execute_action(self):
        """Test that the session from execution context is passed to execute_action."""
        mock_session = MagicMock()
        execution_context = {
            "tenant_id": "test-tenant",
            "session": mock_session,
        }

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result()

        llm_functions = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(llm_functions, "_create_llm_artifact", new=AsyncMock()),
            patch.object(
                llm_functions,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            await llm_functions.llm_run("Test prompt")

            call_kwargs = mock_service.execute_action.call_args.kwargs
            assert call_kwargs["session"] is mock_session
