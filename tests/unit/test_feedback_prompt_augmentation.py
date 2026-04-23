"""Unit tests for feedback prompt augmentation in CyLLMFunctions (Project Zakynthos).

Tests the _augment_prompt_with_feedback method and the llm_run integration
with feedback entries and relevance filtering.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.services.cy_llm_functions import CyLLMFunctions


def _make_framework_result(response_text: str = "test response") -> dict:
    """Build a standard framework action success result."""
    return {
        "status": "success",
        "data": {
            "response": response_text,
            "message": {"role": "assistant", "content": response_text},
            "input_tokens": 10,
            "output_tokens": 5,
        },
    }


def _make_cy_llm(
    feedback_entries: list[str] | None = None,
    relevance_service=None,
    directive: str | None = None,
) -> CyLLMFunctions:
    """Helper to create a CyLLMFunctions with mocked IntegrationService."""
    mock_service = AsyncMock()

    # Mock primary integration discovery
    mock_integration = MagicMock()
    mock_integration.integration_id = "anthropic-agent-main"
    mock_integration.integration_type = "anthropic_agent"
    mock_integration.settings = {"is_primary": True}
    mock_service.list_integrations.return_value = [mock_integration]

    # Mock execute_action default return
    mock_service.execute_action.return_value = _make_framework_result()

    ctx = {
        "tenant_id": "test-tenant",
        "feedback_entries": feedback_entries or [],
        "feedback_relevance_service": relevance_service,
        "directive": directive,
    }
    return CyLLMFunctions(mock_service, ctx)


class TestAugmentPromptWithFeedback:
    """Test _augment_prompt_with_feedback method in isolation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_feedback_returns_original_prompt(self):
        cy = _make_cy_llm(feedback_entries=[])
        result = await cy._augment_prompt_with_feedback("original prompt")
        assert result == "original prompt"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_feedback_included_when_no_relevance_service(self):
        """Without a relevance service, all feedback is injected."""
        cy = _make_cy_llm(
            feedback_entries=["Use JSON output", "Check for CVEs"],
            relevance_service=None,
        )
        result = await cy._augment_prompt_with_feedback("Analyze this alert")

        assert "ANALYST FEEDBACK" in result
        assert "Use JSON output" in result
        assert "Check for CVEs" in result
        assert "takes precedence" in result
        assert "TASK PROMPT:" in result
        assert "Analyze this alert" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_only_relevant_feedback_included(self):
        """With relevance service, only relevant feedback is injected."""
        relevance_svc = MagicMock()
        relevance_svc.get_relevant_feedback = AsyncMock(
            return_value=["Use JSON output"]
        )

        cy = _make_cy_llm(
            feedback_entries=["Use JSON output", "Irrelevant note"],
            relevance_service=relevance_svc,
        )
        result = await cy._augment_prompt_with_feedback("Analyze this")

        assert "Use JSON output" in result
        assert "Irrelevant note" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_relevant_feedback_returns_original(self):
        """If relevance check filters everything out, return original prompt."""
        relevance_svc = MagicMock()
        relevance_svc.get_relevant_feedback = AsyncMock(return_value=[])

        cy = _make_cy_llm(
            feedback_entries=["Irrelevant note"],
            relevance_service=relevance_svc,
        )
        result = await cy._augment_prompt_with_feedback("Analyze this")

        assert result == "Analyze this"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_relevance_service_error_returns_original(self):
        """Relevance service failure should not break — return original prompt."""
        relevance_svc = MagicMock()
        relevance_svc.get_relevant_feedback = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        cy = _make_cy_llm(
            feedback_entries=["Some feedback"],
            relevance_service=relevance_svc,
        )
        result = await cy._augment_prompt_with_feedback("Analyze this")

        assert result == "Analyze this"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_augmented_prompt_format(self):
        """Verify the exact format of the augmented prompt."""
        cy = _make_cy_llm(
            feedback_entries=["Feedback A", "Feedback B"],
            relevance_service=None,
        )
        result = await cy._augment_prompt_with_feedback("Do the thing")

        expected = (
            "ANALYST FEEDBACK (takes precedence over default instructions):\n"
            "- Feedback A\n"
            "- Feedback B\n"
            "\n"
            "TASK PROMPT:\n"
            "Do the thing"
        )
        assert result == expected


class TestLlmRunWithFeedback:
    """Test that llm_run() integrates feedback augmentation correctly."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_run_augments_prompt_when_feedback_present(self):
        """When feedback_entries are present, llm_run should augment the prompt."""
        cy = _make_cy_llm(
            feedback_entries=["Always output JSON"],
            relevance_service=None,
        )
        cy._create_llm_artifact = AsyncMock()

        result = await cy.llm_run("Analyze this alert")

        assert result == "test response"
        # Verify the prompt was augmented before sending to framework
        call_kwargs = cy.integration_service.execute_action.call_args.kwargs
        prompt = call_kwargs["params"]["prompt"]
        assert "ANALYST FEEDBACK" in prompt
        assert "Always output JSON" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_run_no_augmentation_without_feedback(self):
        """Without feedback entries, llm_run should use original prompt."""
        cy = _make_cy_llm(feedback_entries=[])
        cy._create_llm_artifact = AsyncMock()

        await cy.llm_run("Analyze this alert")

        call_kwargs = cy.integration_service.execute_action.call_args.kwargs
        prompt = call_kwargs["params"]["prompt"]
        assert prompt == "Analyze this alert"


class TestRelevanceLlmCallable:
    """Test the _create_relevance_llm_callable helper."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callable_invokes_llm_run_without_directive_or_feedback(self):
        """The relevance callable should invoke llm_run with no directive
        or feedback to avoid recursion."""
        cy = _make_cy_llm(
            feedback_entries=["Some feedback"],
            directive="Original directive",
        )
        cy._create_llm_artifact = AsyncMock()

        callable_fn = cy._create_relevance_llm_callable()
        result = await callable_fn("Is this relevant?")

        assert result == "test response"
        # Verify no directive/context was sent (stripped to avoid recursion)
        call_kwargs = cy.integration_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert "context" not in params
        # Verify prompt was not augmented with feedback
        assert params["prompt"] == "Is this relevant?"
