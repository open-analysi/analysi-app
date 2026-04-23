"""Basic integration tests for progressive task disclosure pattern."""

import pytest

from analysi.mcp.context import set_tenant
from analysi.mcp.tools import workflow_tools


@pytest.mark.integration
@pytest.mark.asyncio
class TestProgressiveDisclosureBasic:
    """Test core progressive disclosure functionality with sample_tasks fixture."""

    @pytest.fixture
    async def sample_tasks(self, integration_test_session, sample_tenant_id):
        """Create sample tasks for testing."""
        from analysi.schemas.task import TaskCreate
        from analysi.services.task import TaskService

        service = TaskService(integration_test_session)
        tasks = []

        # Create 3 sample tasks with different functions
        for i, function in enumerate(["search", "reasoning", "extraction"]):
            task_data = TaskCreate(
                name=f"Test Task {i + 1}",
                description=f"Test task for {function}",
                script=f'# Test script {i + 1}\nreturn {{"result": "test"}}',
                function=function,
                scope="processing",
            )

            task = await service.create_task(sample_tenant_id, task_data)
            tasks.append(task)

        await integration_test_session.commit()
        return tasks

    @pytest.mark.asyncio
    async def test_list_task_summaries_no_scripts(self, sample_tasks):
        """Verify summaries exclude scripts (key feature)."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries()

        assert result["total"] > 0
        # NO scripts in summaries
        for task in result["tasks"]:
            assert "script" not in task
            assert "id" in task
            assert "name" in task

    @pytest.mark.asyncio
    async def test_get_task_details_includes_scripts(self, sample_tasks):
        """Verify details include scripts."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Get summaries first
        summaries = await workflow_tools.list_task_summaries()
        task_id = summaries["tasks"][0]["id"]

        # Then get details
        result = await workflow_tools.get_task_details(task_ids=[task_id])

        assert result["count"] == 1
        # Scripts ARE present in details
        assert "script" in result["tasks"][0]
        assert result["tasks"][0]["script"]  # Non-empty

    @pytest.mark.asyncio
    async def test_progressive_pattern_end_to_end(self, sample_tasks):
        """Test complete progressive disclosure workflow."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Step 1: Browse summaries (lightweight)
        summaries = await workflow_tools.list_task_summaries()
        assert summaries["total"] > 0

        # Step 2: Select interesting tasks
        interesting_ids = [summaries["tasks"][0]["id"]]

        # Step 3: Get full details for selected tasks only
        details = await workflow_tools.get_task_details(task_ids=interesting_ids)

        assert details["count"] == 1
        assert "script" in details["tasks"][0]

    @pytest.mark.asyncio
    async def test_context_reduction(self, sample_tasks):
        """Verify progressive disclosure reduces context usage."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Old way: all tasks with scripts
        all_tasks = await workflow_tools.list_available_tasks()

        # New way: summaries without scripts
        summaries = await workflow_tools.list_task_summaries()

        # Same count
        assert all_tasks["total"] == summaries["total"]

        # But summaries have NO scripts (massive context saving)
        for task in summaries["tasks"]:
            assert "script" not in task

        # All tasks DO have scripts
        for task in all_tasks["tasks"]:
            assert "script" in task
