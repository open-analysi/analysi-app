"""
Unit tests for LLM execution artifact capture in cy_llm_functions.py.

Tests the auto-capture of LLM calls as artifacts during Cy script execution.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


def _make_execute_action_result(response_text="LLM response text"):
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


@pytest.mark.unit
class TestLLMExecutionArtifactCapture:
    """Test automatic artifact capture for LLM calls."""

    @pytest.fixture
    def execution_context(self):
        """Create a sample execution context with all fields."""
        return {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "workflow_run_id": str(uuid.uuid4()),
            "workflow_node_instance_id": str(uuid.uuid4()),
            "analysis_id": str(uuid.uuid4()),
            "session": MagicMock(),
        }

    @pytest.fixture
    def mock_integration_service(self):
        """Create a mock IntegrationService."""
        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "This is the LLM response"
        )
        return mock_service

    @pytest.mark.asyncio
    async def test_llm_call_creates_artifact_with_prompt_and_completion(
        self, execution_context, mock_integration_service
    ):
        """Test that LLM call captures artifact with prompt and completion."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        cy_llm = CyLLMFunctions(mock_integration_service, execution_context)

        with (
            patch.object(
                cy_llm, "_create_llm_artifact", new=AsyncMock()
            ) as mock_create_artifact,
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            result = await cy_llm.llm_run(prompt="What is 2+2?")

            assert result == "This is the LLM response"

            # Verify artifact creation was called
            mock_create_artifact.assert_called_once()
            call_kwargs = mock_create_artifact.call_args.kwargs
            assert call_kwargs["function_name"] == "llm_run"
            assert call_kwargs["prompt"] == "What is 2+2?"
            assert call_kwargs["completion"] == "This is the LLM response"
            assert call_kwargs["integration_id"] == "openai-test"

    @pytest.mark.asyncio
    async def test_artifact_type_is_llm_execution(self):
        """Test that LLM execution artifacts have artifact_type='llm_execution'."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_llm_execution_artifact(
                tenant_id="test-tenant",
                function_name="llm_run",
                integration_id="openai-prod",
                prompt="Hello",
                completion="Hi there!",
                model="gpt-4",
                duration_ms=1500,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.artifact_type == "llm_execution"

    @pytest.mark.asyncio
    async def test_artifact_source_is_auto_capture(self):
        """Test that LLM execution artifacts have source='auto_capture'."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_llm_execution_artifact(
                tenant_id="test-tenant",
                function_name="llm_run",
                integration_id="openai-prod",
                prompt="Test prompt",
                completion="Test completion",
                model=None,
                duration_ms=500,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.source == "auto_capture"

    @pytest.mark.asyncio
    async def test_artifact_name_is_function_name(self):
        """Test that artifact name is set to the LLM function name."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_llm_execution_artifact(
                tenant_id="test-tenant",
                function_name="llm_summarize",
                integration_id="anthropic-claude",
                prompt="Summarize this text...",
                completion="Summary: ...",
                model="claude-3-opus",
                duration_ms=2000,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.name == "llm_summarize"

    @pytest.mark.asyncio
    async def test_artifact_content_includes_prompt_completion_model(self):
        """Test that artifact content includes prompt, completion, model, and timing."""
        import json

        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_llm_execution_artifact(
                tenant_id="test-tenant",
                function_name="llm_run",
                integration_id="openai-prod",
                prompt="What is AI?",
                completion="AI is artificial intelligence...",
                model="gpt-4-turbo",
                duration_ms=1234,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]

            # Parse the content JSON
            content = json.loads(artifact_data.content)
            assert content["prompt"] == "What is AI?"
            assert content["completion"] == "AI is artificial intelligence..."
            assert content["model"] == "gpt-4-turbo"
            assert content["duration_ms"] == 1234
            assert "timestamp" in content

    @pytest.mark.asyncio
    async def test_artifact_captures_duration(self, execution_context):
        """Test that artifact captures execution duration."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Response"
        )

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(
                cy_llm, "_create_llm_artifact", new=AsyncMock()
            ) as mock_create_artifact,
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            await cy_llm.llm_run(prompt="Test")

            call_kwargs = mock_create_artifact.call_args.kwargs
            # Duration should be positive (we can't check exact value but it should exist)
            assert "duration_ms" in call_kwargs
            assert isinstance(call_kwargs["duration_ms"], int)
            assert call_kwargs["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_artifact_captures_model_when_provided(self, execution_context):
        """Test that model name is captured when provided."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Response"
        )

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(
                cy_llm, "_create_llm_artifact", new=AsyncMock()
            ) as mock_create_artifact,
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            await cy_llm.llm_run(prompt="Test", model="gpt-4-turbo")

            call_kwargs = mock_create_artifact.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_llm_artifact_creation_failure_does_not_break_execution(
        self, execution_context
    ):
        """Test that artifact creation failure is logged but doesn't break LLM call."""
        from analysi.services.artifact_service import ArtifactService
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Response"
        )

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        # Mock ArtifactService.create_llm_execution_artifact to fail
        # This tests the real _create_llm_artifact error handling
        with (
            patch.object(
                ArtifactService,
                "create_llm_execution_artifact",
                new=AsyncMock(side_effect=Exception("Database error")),
            ),
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-test", "openai", None)),
            ),
        ):
            # LLM call should still succeed because _create_llm_artifact catches exceptions
            result = await cy_llm.llm_run(prompt="Test")
            assert result == "Response"

    @pytest.mark.asyncio
    async def test_artifact_uses_specific_integration_id(self, execution_context):
        """Test that artifact uses specific integration_id when provided."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        # For specific integration_id, get_integration is called instead of list_integrations
        mock_specific_integration = _make_mock_integration(
            integration_id="anthropic-claude",
            integration_type="anthropic",
        )
        mock_service.get_integration.return_value = mock_specific_integration
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Response"
        )

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with patch.object(
            cy_llm, "_create_llm_artifact", new=AsyncMock()
        ) as mock_create_artifact:
            await cy_llm.llm_run(prompt="Test", integration_id="anthropic-claude")

            call_kwargs = mock_create_artifact.call_args.kwargs
            assert call_kwargs["integration_id"] == "anthropic-claude"

    @pytest.mark.asyncio
    async def test_artifact_uses_primary_integration_id_when_not_specified(
        self, execution_context
    ):
        """Test that artifact uses resolved primary integration_id when none specified."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        mock_service.execute_action.return_value = _make_execute_action_result(
            "Response"
        )

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with (
            patch.object(
                cy_llm, "_create_llm_artifact", new=AsyncMock()
            ) as mock_create_artifact,
            patch.object(
                cy_llm,
                "_resolve_primary_ai_integration",
                new=AsyncMock(return_value=("openai-primary", "openai", None)),
            ),
        ):
            await cy_llm.llm_run(prompt="Test")  # No integration_id

            call_kwargs = mock_create_artifact.call_args.kwargs
            # Should use the resolved primary integration ID
            assert call_kwargs["integration_id"] == "openai-primary"

    @pytest.mark.asyncio
    async def test_artifact_links_to_execution_context(self):
        """Test that LLM artifact is linked to task_run_id, workflow_run_id, etc."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        task_run_id = uuid.uuid4()
        workflow_run_id = uuid.uuid4()
        workflow_node_instance_id = uuid.uuid4()
        analysis_id = uuid.uuid4()

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_llm_execution_artifact(
                tenant_id="test-tenant",
                function_name="llm_run",
                integration_id="openai-prod",
                prompt="Test",
                completion="Response",
                model=None,
                duration_ms=100,
                analysis_id=analysis_id,
                task_run_id=task_run_id,
                workflow_run_id=workflow_run_id,
                workflow_node_instance_id=workflow_node_instance_id,
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.task_run_id == task_run_id
            assert artifact_data.workflow_run_id == workflow_run_id
            assert artifact_data.workflow_node_instance_id == workflow_node_instance_id
            assert artifact_data.analysis_id == analysis_id


@pytest.mark.unit
class TestCyLLMFunctionsCreateArtifactHelper:
    """Test the _create_llm_artifact helper method."""

    @pytest.fixture
    def execution_context(self):
        """Create a sample execution context."""
        return {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "session": MagicMock(),
        }

    @pytest.mark.asyncio
    async def test_create_llm_artifact_handles_missing_session(self):
        """Test that missing session is handled gracefully."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        context_without_session = {"tenant_id": "test-tenant"}

        cy_llm = CyLLMFunctions(mock_service, context_without_session)

        # Should not raise, just return early
        await cy_llm._create_llm_artifact(
            function_name="llm_run",
            integration_id="test",
            prompt="test",
            completion="test",
            model=None,
            duration_ms=100,
        )

    @pytest.mark.asyncio
    async def test_create_llm_artifact_handles_missing_tenant_id(self):
        """Test that missing tenant_id is handled gracefully."""
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()
        context_without_tenant = {"session": MagicMock()}

        cy_llm = CyLLMFunctions(mock_service, context_without_tenant)

        # Should not raise, just return early
        await cy_llm._create_llm_artifact(
            function_name="llm_run",
            integration_id="test",
            prompt="test",
            completion="test",
            model=None,
            duration_ms=100,
        )

    @pytest.mark.asyncio
    async def test_create_llm_artifact_handles_uuid_conversion(self, execution_context):
        """Test that string UUIDs in context are converted properly."""
        from analysi.services.artifact_service import ArtifactService
        from analysi.services.cy_llm_functions import CyLLMFunctions

        mock_service = AsyncMock()

        cy_llm = CyLLMFunctions(mock_service, execution_context)

        with patch.object(
            ArtifactService, "create_llm_execution_artifact", new=AsyncMock()
        ) as mock_create:
            await cy_llm._create_llm_artifact(
                function_name="llm_run",
                integration_id="test",
                prompt="test",
                completion="test",
                model=None,
                duration_ms=100,
            )

            # Verify UUID conversion happened
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["task_run_id"] == uuid.UUID(
                execution_context["task_run_id"]
            )
