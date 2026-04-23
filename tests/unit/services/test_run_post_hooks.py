"""Unit tests for _run_post_hooks method in TaskExecutionService.

This tests the integration between TaskExecutionService and TaskPostHooks,
specifically how TaskMetadata is constructed from Task model objects.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.services.task_execution import TaskExecutionService


class TestRunPostHooksTaskMetadataConstruction:
    """Tests for TaskMetadata construction from Task model in _run_post_hooks."""

    @pytest.fixture
    def execution_context(self):
        """Create execution context with session."""
        return {
            "cy_name": "test_task",
            "task_id": str(uuid4()),
            "tenant_id": "test-tenant",
            "session": MagicMock(),  # Mock session for post-hooks
        }

    @pytest.fixture
    def mock_result(self):
        """Create a successful execution result with ai_analysis."""
        return {
            "status": "completed",
            "output": {
                "enrichments": {
                    "test_task": {
                        "score": 95,
                        "ai_analysis": "This is the analysis text that needs a title.",
                    }
                }
            },
        }

    @pytest.fixture
    def mock_llm_functions(self):
        """Create mock LLM functions."""
        return {
            "llm_run": AsyncMock(return_value="mocked llm response"),
            "llm_summarize": AsyncMock(return_value="Generated Title"),
        }

    @pytest.mark.asyncio
    async def test_run_post_hooks_with_component_loaded(
        self, execution_context, mock_result, mock_llm_functions
    ):
        """Post-hooks work when Task has component relationship loaded."""
        # Create Task with component relationship properly loaded
        component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="task",
            name="Test Task",
            description="A test task description",
            cy_name="test_task",
            status="enabled",
            created_by=str(SYSTEM_USER_ID),
            categories=["test"],
        )

        task = Task(
            id=uuid4(),
            component_id=component.id,
            directive="Be concise.",
            script="return input",
            function="reasoning",
            scope="processing",
        )
        # Manually set the component relationship (simulates eager loading)
        task.component = component

        service = TaskExecutionService()

        with patch.object(
            service.executor, "_load_llm_functions", return_value=mock_llm_functions
        ):
            result = await service._run_post_hooks(
                result=mock_result,
                task=task,
                execution_context=execution_context,
                original_input={"title": "Test Alert"},
            )

        # Verify ai_analysis_title was generated
        assert "ai_analysis_title" in result["output"]["enrichments"]["test_task"]
        assert (
            result["output"]["enrichments"]["test_task"]["ai_analysis_title"]
            == "Generated Title"
        )

    @pytest.mark.asyncio
    async def test_run_post_hooks_fails_when_component_is_none(
        self, execution_context, mock_result, mock_llm_functions
    ):
        """
        BUG REPRODUCTION: Post-hooks fail when Task.component is None.

        This test reproduces the production bug where:
        - Error: 'Task' object has no attribute 'description'
        - Root cause: hasattr(task, 'component') returns True but task.component is None
        - The code tries to access task.component.description which becomes None.description

        Expected behavior: Should handle None component gracefully.
        """
        # Create Task without component relationship loaded
        task = Task(
            id=uuid4(),
            component_id=uuid4(),  # Points to non-existent component
            directive="Be concise.",
            script="return input",
            function="reasoning",
            scope="processing",
        )
        # task.component is None (not loaded)
        assert task.component is None

        service = TaskExecutionService()

        with patch.object(
            service.executor, "_load_llm_functions", return_value=mock_llm_functions
        ):
            # This should NOT raise an exception
            result = await service._run_post_hooks(
                result=mock_result,
                task=task,
                execution_context=execution_context,
                original_input={"title": "Test Alert"},
            )

        # Post-hooks should still work even if component is None
        # The output should be returned (modified or not) without crashing
        assert result is not None
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_post_hooks_uses_fallback_for_missing_component(
        self, execution_context, mock_result, mock_llm_functions
    ):
        """
        When component is None, should use fallback values for metadata.

        Expected fallbacks:
        - name: 'Unknown' (from getattr fallback)
        - description: None
        - cy_name: from execution_context
        """
        task = Task(
            id=uuid4(),
            component_id=uuid4(),
            directive="Be concise.",
            script="return input",
            function="reasoning",
            scope="processing",
        )
        # task.component is None

        service = TaskExecutionService()

        with patch.object(
            service.executor, "_load_llm_functions", return_value=mock_llm_functions
        ):
            result = await service._run_post_hooks(
                result=mock_result,
                task=task,
                execution_context=execution_context,
                original_input={"title": "Test Alert"},
            )

        # Should still generate title using cy_name from execution_context
        assert "ai_analysis_title" in result["output"]["enrichments"]["test_task"]
