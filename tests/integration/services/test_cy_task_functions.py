"""Integration tests for Cy task composition via task_run()."""

import uuid
from unittest.mock import MagicMock

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.cy_task_functions import (
    MAX_TASK_RECURSION_DEPTH,
    CyTaskFunctions,
    create_cy_task_functions,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyTaskFunctions:
    """Test Cy task composition functionality."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.fixture
    async def task_functions(self, integration_test_session, tenant_id):
        """Create CyTaskFunctions instance."""
        execution_context = {
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
            "alert_analysis_id": str(uuid.uuid4()),
        }
        return CyTaskFunctions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

    @pytest.mark.asyncio
    async def test_task_run_basic(self, task_functions, repository, tenant_id):
        """Test basic task_run() functionality."""
        # Create child task with valid Cy script
        child_task_data = {
            "tenant_id": tenant_id,
            "name": "Calculate Metrics",
            "cy_name": "calculate_metrics",
            "script": """data = input["data"]
avg = data[0] + 100
return avg""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task_data)

        # Test default behavior - returns just the output
        result = await task_functions.task_run(
            "calculate_metrics", {"data": [1, 2, 3, 4, 5]}
        )
        assert result == 101  # 1 + 100

        # Test with full_result flag - returns full execution context
        full_result = await task_functions.task_run(
            "calculate_metrics", {"data": [1, 2, 3, 4, 5]}, full_result=True
        )
        assert full_result["status"] == "completed"
        assert "output" in full_result
        assert full_result["output"] == 101  # 1 + 100

    @pytest.mark.asyncio
    async def test_task_run_recursion_limit(self, integration_test_session, tenant_id):
        """Test that recursion depth is enforced."""
        # Create context with max depth already reached
        execution_context = {
            "task_call_depth": MAX_TASK_RECURSION_DEPTH,
            "workflow_run_id": str(uuid.uuid4()),
        }

        task_functions = CyTaskFunctions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

        # Should raise RecursionError
        with pytest.raises(RecursionError) as exc_info:
            await task_functions.task_run("any_task", {})

        assert (
            f"Maximum task recursion depth ({MAX_TASK_RECURSION_DEPTH}) exceeded"
            in str(exc_info.value)
        )

    @pytest.mark.asyncio
    async def test_task_run_context_propagation(
        self, integration_test_session, tenant_id
    ):
        """Test that execution context is propagated to nested calls."""
        workflow_run_id = str(uuid.uuid4())
        alert_analysis_id = str(uuid.uuid4())

        execution_context = {
            "task_call_depth": 2,
            "workflow_run_id": workflow_run_id,
            "alert_analysis_id": alert_analysis_id,
            "session": integration_test_session,
            "artifact_service": MagicMock(),
        }

        task_functions = CyTaskFunctions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

        # Verify context is available
        assert task_functions.execution_context["workflow_run_id"] == workflow_run_id
        assert (
            task_functions.execution_context["alert_analysis_id"] == alert_analysis_id
        )
        assert task_functions.execution_context["task_call_depth"] == 2
        assert "session" in task_functions.execution_context
        assert "artifact_service" in task_functions.execution_context

    @pytest.mark.asyncio
    async def test_task_run_not_found(self, task_functions):
        """Test calling task_run with non-existent cy_name."""
        # Should fail with ValueError
        with pytest.raises(ValueError) as exc_info:
            await task_functions.task_run("non_existent_task", {})
        assert "Task with cy_name 'non_existent_task' not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_task_run_disabled_task(self, task_functions, repository, tenant_id):
        """Test that disabled tasks cannot be run."""
        # Create disabled task
        task_data = {
            "tenant_id": tenant_id,
            "name": "Disabled Task",
            "cy_name": "disabled_task",
            "status": "disabled",
            "script": "return 'should not run'",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(task_data)

        # Try to run disabled task - should fail with ValueError
        with pytest.raises(ValueError) as exc_info:
            await task_functions.task_run("disabled_task", {})
        assert "is not enabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_cy_task_functions(self, integration_test_session, tenant_id):
        """Test the factory function for creating task functions."""
        execution_context = {
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        functions = create_cy_task_functions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

        assert "task_run" in functions
        assert callable(functions["task_run"])

    @pytest.mark.asyncio
    async def test_task_run_wrapper(self, integration_test_session, tenant_id):
        """Test the Cy-compatible wrapper for task_run."""
        execution_context = {
            "task_call_depth": 0,
        }

        functions = create_cy_task_functions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

        # Test wrapper with and without input_data
        with pytest.raises(ValueError) as exc_info:
            await functions["task_run"]("test_task", {"key": "value"})
        assert "not found" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            await functions["task_run"]("test_task", None)
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_task_run_increments_depth(self, integration_test_session, tenant_id):
        """Test that task_run would increment call depth."""
        execution_context = {
            "task_call_depth": 5,  # Start at depth 5
        }

        task_functions = CyTaskFunctions(
            session=integration_test_session,
            tenant_id=tenant_id,
            execution_context=execution_context,
        )

        # Depth check happens before task lookup
        assert task_functions.execution_context["task_call_depth"] == 5

        # Will fail with ValueError (task not found), but depth check passes
        with pytest.raises(ValueError) as exc_info:
            await task_functions.task_run("test_task", {})
        assert "not found" in str(exc_info.value)
