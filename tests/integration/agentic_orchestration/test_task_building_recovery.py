"""Integration tests for task building node recovery mechanism.

Tests verify that when agent execution fails after creating a task via MCP,
the recovery logic successfully retrieves the task from the database.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.agentic_orchestration.nodes.task_building import task_building_node


@pytest.mark.integration
class TestTaskBuildingRecovery:
    """Integration tests for task building recovery logic."""

    @pytest.fixture
    async def test_client(self, integration_test_session):
        """Create an async HTTP client for testing with test database."""
        from httpx import ASGITransport, AsyncClient

        from analysi.db.session import get_db
        from analysi.main import app

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_task_building_no_recovery_when_task_missing(
        self, test_client, sample_tenant_id
    ):
        """Integration test: Verify genuine failure when task doesn't exist.

        Scenario:
        1. Pre-flight check: task doesn't exist
        2. Agent crashes BEFORE creating task
        3. Recovery logic checks REST API and task is not found
        4. Genuine failure is returned
        """
        tenant_id = sample_tenant_id
        proposal_name = f"Missing Task {uuid4().hex[:8]}"

        # Setup mock executor and workspace
        mock_executor = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.run_id = f"test-no-recovery-{uuid4().hex[:8]}"

        # Simulate agent crash BEFORE task creation
        mock_workspace.run_agent = AsyncMock(
            side_effect=RuntimeError("Agent initialization failed")
        )
        mock_workspace.cleanup = MagicMock()

        # Create state with proposal
        state = {
            "proposal": {
                "name": proposal_name,
                "description": "Task that will never be created",
                "designation": "new",
                "integration_tools": ["echo_edr::health_check"],
            },
            "alert": {"id": "test-alert", "title": "Test Alert"},
            "runbook": "# Test Runbook",
            "run_id": mock_workspace.run_id,
            "tenant_id": tenant_id,
            "workspace": mock_workspace,
        }

        # Execute task building node (should fail genuinely)
        result = await task_building_node(state, mock_executor)

        # Verify genuine failure
        assert len(result["tasks_built"]) == 1
        task_result = result["tasks_built"][0]

        assert task_result["success"] is False, "Should fail when task doesn't exist"
        assert task_result.get("recovered") is None, "Should not have recovered flag"
        assert task_result["task_id"] is None, "No task ID on failure"
        assert task_result["cy_name"] is None, "No cy_name on failure"
        assert "Agent initialization failed" in task_result["error"]

        # Verify workspace cleanup was called
        mock_workspace.cleanup.assert_called_once()
