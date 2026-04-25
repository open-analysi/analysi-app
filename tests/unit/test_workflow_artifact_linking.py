"""
Unit tests for verifying workflow_run_id propagation to artifacts.

Tests the complete chain:
WorkflowExecutor → TaskRunService → TaskRun → TaskExecution → CyFunctions → Artifacts
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.services.cy_functions import CyArtifactFunctions
from analysi.services.task_execution import ExecutionContext


class TestTaskRunWithWorkflowRunId:
    """Test TaskRun creation with workflow_run_id."""

    @pytest.mark.asyncio
    async def test_create_task_run_with_workflow_run_id(self):
        """Verify TaskRun is created with workflow_run_id."""
        # Mock TaskRunService with all dependencies mocked
        from analysi.services.task_run import TaskRunService

        with patch("analysi.services.task_run.TaskRun") as MockTaskRun:
            # Mock the TaskRun class to avoid SQLAlchemy initialization
            mock_task_run_instance = Mock()
            mock_task_run_instance.id = uuid.uuid4()
            mock_task_run_instance.workflow_run_id = uuid.uuid4()
            mock_task_run_instance.tenant_id = "test-tenant"
            mock_task_run_instance.task_id = uuid.uuid4()
            mock_task_run_instance.execution_context = {
                "tenant_id": "test-tenant",
                "task_id": str(mock_task_run_instance.task_id),
                "task_run_id": str(mock_task_run_instance.id),
                "workflow_run_id": str(mock_task_run_instance.workflow_run_id),
            }
            MockTaskRun.return_value = mock_task_run_instance

            # Setup session
            session = AsyncMock(spec=AsyncSession)
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.refresh = AsyncMock()

            service = TaskRunService()

            # Mock storage manager and repository
            with patch.object(
                service.storage_manager, "store", new=AsyncMock()
            ) as mock_store:
                mock_store.return_value = {
                    "storage_type": "inline",
                    "location": "inline:123",
                }

                with patch.object(
                    service.repository, "create", new=AsyncMock()
                ) as mock_create:
                    mock_create.return_value = mock_task_run_instance

                    # Execute
                    await service.create_execution(
                        session=session,
                        tenant_id="test-tenant",
                        task_id=mock_task_run_instance.task_id,
                        cy_script=None,
                        input_data={"key": "value"},
                        workflow_run_id=mock_task_run_instance.workflow_run_id,
                    )

                    # Verify TaskRun was created with workflow_run_id
                    assert MockTaskRun.called
                    call_kwargs = MockTaskRun.call_args.kwargs
                    assert (
                        call_kwargs["workflow_run_id"]
                        == mock_task_run_instance.workflow_run_id
                    )
                    assert call_kwargs["tenant_id"] == "test-tenant"

    @pytest.mark.asyncio
    async def test_task_run_without_workflow_run_id(self):
        """Verify TaskRun works without workflow_run_id (ad-hoc execution)."""
        from analysi.services.task_run import TaskRunService

        with patch("analysi.services.task_run.TaskRun") as MockTaskRun:
            # Mock the TaskRun class to avoid SQLAlchemy initialization
            mock_task_run_instance = Mock()
            mock_task_run_instance.id = uuid.uuid4()
            mock_task_run_instance.workflow_run_id = None
            mock_task_run_instance.tenant_id = "test-tenant"
            mock_task_run_instance.task_id = None
            mock_task_run_instance.cy_script = "print('hello')"
            mock_task_run_instance.execution_context = {
                "tenant_id": "test-tenant",
                "task_run_id": str(mock_task_run_instance.id),
            }
            MockTaskRun.return_value = mock_task_run_instance

            # Setup session
            session = AsyncMock(spec=AsyncSession)
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.refresh = AsyncMock()

            service = TaskRunService()

            # Mock storage manager and repository
            with patch.object(
                service.storage_manager, "store", new=AsyncMock()
            ) as mock_store:
                mock_store.return_value = {
                    "storage_type": "inline",
                    "location": "inline:123",
                }

                with patch.object(
                    service.repository, "create", new=AsyncMock()
                ) as mock_create:
                    mock_create.return_value = mock_task_run_instance

                    # Execute
                    await service.create_execution(
                        session=session,
                        tenant_id="test-tenant",
                        task_id=None,  # Ad-hoc execution
                        cy_script="print('hello')",
                        input_data={"key": "value"},
                        workflow_run_id=None,  # No workflow
                    )

                    # Verify TaskRun was created without workflow_run_id
                    assert MockTaskRun.called
                    call_kwargs = MockTaskRun.call_args.kwargs
                    assert call_kwargs["workflow_run_id"] is None
                    assert call_kwargs["cy_script"] == "print('hello')"
                    assert call_kwargs["task_id"] is None


class TestCyFunctionsWithWorkflowContext:
    """Test CyArtifactFunctions with workflow execution context."""

    @pytest.mark.asyncio
    async def test_store_artifact_with_workflow_context(self):
        """Verify store_artifact includes workflow_run_id from context."""
        # Setup
        workflow_run_id = uuid.uuid4()
        task_run_id = uuid.uuid4()
        task_id = uuid.uuid4()
        tenant_id = "test-tenant"

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(task_id),
            "task_run_id": str(task_run_id),
            "workflow_run_id": str(workflow_run_id),
        }

        # Create CyArtifactFunctions with context
        artifact_service = MagicMock()
        cy_functions = CyArtifactFunctions(artifact_service, execution_context)

        # Mock the API call
        with patch.object(
            cy_functions, "_create_artifact_via_async_api", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = str(uuid.uuid4())

            # Execute
            artifact_name = "Test Artifact"
            artifact_content = {"data": "test"}
            await cy_functions.store_artifact(
                name=artifact_name,
                artifact=artifact_content,
                artifact_type="test_type",
            )

            # Verify the API was called with workflow_run_id
            assert mock_create.called
            call_args = mock_create.call_args
            artifact_data = call_args[0][1]  # Second positional argument

            # Check that workflow_run_id is included (task_id removed)
            assert artifact_data.workflow_run_id == workflow_run_id
            assert artifact_data.task_run_id == task_run_id
            assert (
                artifact_data.source == "cy_script"
            )  # Artifacts from store_artifact()

    @pytest.mark.asyncio
    async def test_store_artifact_without_workflow_context(self):
        """Verify store_artifact works without workflow_run_id."""
        # Setup
        task_run_id = uuid.uuid4()
        task_id = uuid.uuid4()
        tenant_id = "test-tenant"

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(task_id),
            "task_run_id": str(task_run_id),
            # No workflow_run_id
        }

        # Create CyArtifactFunctions with context
        artifact_service = MagicMock()
        cy_functions = CyArtifactFunctions(artifact_service, execution_context)

        # Mock the API call
        with patch.object(
            cy_functions, "_create_artifact_via_async_api", new=AsyncMock()
        ) as mock_create:
            mock_create.return_value = str(uuid.uuid4())

            # Execute
            artifact_name = "Test Artifact"
            artifact_content = "simple text"
            await cy_functions.store_artifact(
                name=artifact_name,
                artifact=artifact_content,
            )

            # Verify the API was called without workflow_run_id
            assert mock_create.called
            call_args = mock_create.call_args
            artifact_data = call_args[0][1]

            # Check that workflow_run_id is None (task_id removed)
            assert artifact_data.workflow_run_id is None
            assert artifact_data.task_run_id == task_run_id
            assert (
                artifact_data.source == "cy_script"
            )  # Artifacts from store_artifact()


class TestExecutionContextPropagation:
    """Test ExecutionContext propagation through the execution chain."""

    def test_execution_context_includes_workflow_run_id(self):
        """Verify ExecutionContext.build_context includes workflow_run_id."""
        tenant_id = "test-tenant"
        task_id = str(uuid.uuid4())
        workflow_run_id = str(uuid.uuid4())

        context = ExecutionContext.build_context(
            tenant_id=tenant_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,
            available_kus=[],
        )

        assert context["tenant_id"] == tenant_id
        assert context["task_id"] == task_id
        assert context["workflow_run_id"] == workflow_run_id

    def test_execution_context_without_workflow_run_id(self):
        """Verify ExecutionContext works without workflow_run_id."""
        tenant_id = "test-tenant"
        task_id = str(uuid.uuid4())

        context = ExecutionContext.build_context(
            tenant_id=tenant_id,
            task_id=task_id,
            workflow_run_id=None,
            available_kus=[],
        )

        assert context["tenant_id"] == tenant_id
        assert context["task_id"] == task_id
        assert context.get("workflow_run_id") is None


class TestDispositionArtifactAccess:
    """Test that FinalDispositionUpdateStep can access Disposition artifacts."""

    @pytest.mark.asyncio
    async def test_final_disposition_step_retrieves_artifacts_by_workflow_run_id(self):
        """Verify FinalDispositionUpdateStep retrieves artifacts using workflow_run_id."""
        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        # Setup
        step = FinalDispositionUpdateStep()
        tenant_id = "test-tenant"
        alert_id = str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())
        workflow_run_id = str(uuid.uuid4())

        # Mock API client to return test artifacts
        mock_artifacts = [
            {
                "id": str(uuid.uuid4()),
                "name": "Disposition",
                "content": "Benign / False Positive",
                "artifact_type": "disposition",
                "workflow_run_id": workflow_run_id,
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Analysis Summary",
                "content": "Test analysis",
                "artifact_type": "summary",
                "workflow_run_id": workflow_run_id,
            },
        ]

        mock_dispositions = [
            {
                "disposition_id": str(uuid.uuid4()),
                "display_name": "False Positive",
                "category": "Benign",
                "subcategory": "false_positive",
            },
            {
                "disposition_id": str(uuid.uuid4()),
                "display_name": "True Positive",
                "category": "Malicious",
                "subcategory": "true_positive",
            },
        ]

        with patch.object(
            step.api_client, "get_artifacts_by_workflow_run", new=AsyncMock()
        ) as mock_get_artifacts:
            with patch.object(
                step.api_client, "get_dispositions", new=AsyncMock()
            ) as mock_get_dispositions:
                with patch.object(step, "_complete_analysis", new=AsyncMock()):
                    mock_get_artifacts.return_value = mock_artifacts
                    mock_get_dispositions.return_value = mock_dispositions

                    # Execute
                    result = await step.execute(
                        tenant_id=tenant_id,
                        alert_id=alert_id,
                        analysis_id=analysis_id,
                        workflow_run_id=workflow_run_id,
                    )

                    # Verify artifacts were queried by workflow_run_id
                    mock_get_artifacts.assert_called_once_with(
                        tenant_id, workflow_run_id
                    )

                    # Verify disposition was extracted and matched
                    assert "disposition_id" in result
                    assert result["disposition_name"] == "False Positive"
                    assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_final_disposition_step_completes_without_disposition_artifact(self):
        """Missing Disposition artifact should complete with warning, not crash."""
        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        step = FinalDispositionUpdateStep()
        tenant_id = "test-tenant"
        alert_id = str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())
        workflow_run_id = str(uuid.uuid4())

        # Artifacts without Disposition
        mock_artifacts = [
            {
                "id": str(uuid.uuid4()),
                "name": "Analysis Summary",
                "content": "Test analysis",
                "artifact_type": "summary",
                "workflow_run_id": workflow_run_id,
            },
        ]

        with patch.object(
            step.api_client, "get_artifacts_by_workflow_run", new=AsyncMock()
        ) as mock_get_artifacts:
            with patch.object(
                step.api_client, "get_dispositions", new=AsyncMock()
            ) as mock_get_dispositions:
                mock_get_artifacts.return_value = mock_artifacts
                mock_get_dispositions.return_value = []

                with patch.object(step, "_complete_analysis", new=AsyncMock()):
                    result = await step.execute(
                        tenant_id=tenant_id,
                        alert_id=alert_id,
                        analysis_id=analysis_id,
                        workflow_run_id=workflow_run_id,
                    )

                assert result["status"] == "completed"
                assert result["disposition_id"] is None
                assert "warning" in result
