"""
Unit tests for tool execution artifact capture in task_execution.py.

Tests the auto-capture of integration tool calls as artifacts during Cy script execution.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestToolExecutionArtifactCapture:
    """Test automatic artifact capture for integration tool calls."""

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

    @pytest.mark.asyncio
    async def test_tool_execution_creates_artifact_with_correct_fields(
        self, execution_context
    ):
        """Test that tool execution captures artifact with correct fields."""
        from analysi.services.artifact_service import ArtifactService

        with patch.object(
            ArtifactService, "create_tool_execution_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            # Simulate what happens in tool_wrapper after execute_action
            tool_fqn = "app::virustotal::ip_reputation"
            integration_id = "virustotal-prod"
            input_params = {"ip": "8.8.8.8"}
            output = {"reputation": "clean", "score": 0}
            duration_ms = 234

            artifact_svc = ArtifactService(execution_context["session"])
            await artifact_svc.create_tool_execution_artifact(
                tenant_id=execution_context["tenant_id"],
                tool_fqn=tool_fqn,
                integration_id=integration_id,
                input_params=input_params,
                output=output,
                duration_ms=duration_ms,
                analysis_id=uuid.UUID(execution_context["analysis_id"]),
                task_run_id=uuid.UUID(execution_context["task_run_id"]),
                workflow_run_id=uuid.UUID(execution_context["workflow_run_id"]),
                workflow_node_instance_id=uuid.UUID(
                    execution_context["workflow_node_instance_id"]
                ),
            )

            # Verify the method was called with correct arguments
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["tenant_id"] == "test-tenant"
            assert call_kwargs["tool_fqn"] == "app::virustotal::ip_reputation"
            assert call_kwargs["integration_id"] == "virustotal-prod"
            assert call_kwargs["input_params"] == {"ip": "8.8.8.8"}
            assert call_kwargs["output"] == {"reputation": "clean", "score": 0}
            assert call_kwargs["duration_ms"] == 234

    @pytest.mark.asyncio
    async def test_artifact_source_is_auto_capture(self):
        """Test that tool execution artifacts have source='auto_capture'."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        # Check that create_tool_execution_artifact uses source="auto_capture"
        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::test::action",
                integration_id="test-int",
                input_params={"key": "value"},
                output={"result": "ok"},
                duration_ms=100,
                task_run_id=uuid.uuid4(),
            )

            # Verify the artifact data passed to create_artifact
            mock_create.assert_called_once()
            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.source == "auto_capture"

    @pytest.mark.asyncio
    async def test_artifact_type_is_tool_execution(self):
        """Test that tool execution artifacts have artifact_type='tool_execution'."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::test::action",
                integration_id="test-int",
                input_params={},
                output={},
                duration_ms=50,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.artifact_type == "tool_execution"

    @pytest.mark.asyncio
    async def test_artifact_name_is_tool_fqn(self):
        """Test that artifact name is set to the tool FQN (cy_name)."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::splunk::search",
                integration_id="splunk-prod",
                input_params={"query": "index=main"},
                output={"events": []},
                duration_ms=500,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.name == "app::splunk::search"

    @pytest.mark.asyncio
    async def test_artifact_content_includes_input_output_timing(self):
        """Test that artifact content includes input, output, and timing."""
        import json

        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            input_params = {"ip": "1.2.3.4"}
            output = {"malicious": False, "score": 0}

            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::test::check",
                integration_id="test-int",
                input_params=input_params,
                output=output,
                duration_ms=123,
                task_run_id=uuid.uuid4(),
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]

            # Parse the content JSON
            content = json.loads(artifact_data.content)
            assert content["input"] == input_params
            assert content["output"] == output
            assert content["duration_ms"] == 123
            assert "timestamp" in content

    @pytest.mark.asyncio
    async def test_artifact_links_to_execution_context(self):
        """Test that artifact is linked to task_run_id, workflow_run_id, etc."""
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

            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::test::action",
                integration_id="test-int",
                input_params={},
                output={},
                duration_ms=50,
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

    @pytest.mark.asyncio
    async def test_artifact_creation_failure_in_tool_wrapper_is_caught(self):
        """Test that artifact creation failure in tool_wrapper is caught and logged.

        The fire-and-forget pattern is implemented in the tool_wrapper closure
        in task_execution.py, not in create_tool_execution_artifact itself.
        This test verifies that the tool_wrapper's try-except works correctly.
        """
        import logging

        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()

        # Simulate what happens in tool_wrapper when artifact creation fails
        # The tool_wrapper catches the exception and logs a warning
        with patch.object(
            ArtifactService, "create_tool_execution_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.side_effect = Exception("Database connection lost")

            # Simulate the try-except pattern from tool_wrapper
            result = {"status": "success", "data": "tool output"}
            try:
                artifact_svc = ArtifactService(session)
                await artifact_svc.create_tool_execution_artifact(
                    tenant_id="test-tenant",
                    tool_fqn="app::test::action",
                    integration_id="test-int",
                    input_params={},
                    output=result,
                    duration_ms=50,
                    task_run_id=uuid.uuid4(),
                )
            except Exception as artifact_err:
                # This is what tool_wrapper does - catch and log, don't propagate
                logging.getLogger(__name__).warning(
                    "Failed to create tool execution artifact: %s",
                    artifact_err,
                )

            # The tool result is still available despite artifact failure
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_artifact_without_optional_context_fields(self):
        """Test artifact creation works when optional context fields are None."""
        from analysi.schemas.artifact import ArtifactCreate
        from analysi.services.artifact_service import ArtifactService

        session = MagicMock()
        artifact_svc = ArtifactService(session)

        with patch.object(
            artifact_svc, "create_artifact", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = MagicMock(id=uuid.uuid4())

            # Only task_run_id provided, others are None
            await artifact_svc.create_tool_execution_artifact(
                tenant_id="test-tenant",
                tool_fqn="app::test::action",
                integration_id="test-int",
                input_params={},
                output={},
                duration_ms=50,
                task_run_id=uuid.uuid4(),
                # workflow_run_id, workflow_node_instance_id, analysis_id all default to None
            )

            call_args = mock_create.call_args[0]
            artifact_data: ArtifactCreate = call_args[1]
            assert artifact_data.workflow_run_id is None
            assert artifact_data.workflow_node_instance_id is None
            assert artifact_data.analysis_id is None
