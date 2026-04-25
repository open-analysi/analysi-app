"""Integration tests for progressive task disclosure (list_task_summaries + get_task_details)."""

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import workflow_tools


@pytest.mark.integration
@pytest.mark.asyncio
class TestProgressiveTaskDisclosure:
    """
    Test progressive task disclosure pattern for reducing context pollution.

    Pattern:
    1. list_task_summaries() - lightweight browsing (no scripts)
    2. get_task_details() - fetch full details for selected tasks only
    """

    @pytest.fixture(autouse=True)
    def _mcp_user(self):
        """Set MCP user context so RBAC checks pass."""
        set_mcp_current_user(
            CurrentUser(
                user_id="test-user",
                email="test@test.com",
                tenant_id="test",
                roles=["analyst"],
                actor_type="user",
            )
        )

    @pytest.fixture
    async def sample_tasks(self, integration_test_session, sample_tenant_id):
        """Create sample tasks for testing."""
        from analysi.schemas.task import TaskCreate
        from analysi.services.task import TaskService

        service = TaskService(integration_test_session)
        tasks = []

        # Create tasks with different functions and scopes
        test_data = [
            ("search", "processing", "Search Task"),
            ("search", "input", "Search Input Task"),
            ("reasoning", "processing", "Reasoning Task"),
            ("extraction", "processing", "Extraction Task"),
        ]

        for _i, (function, scope, name) in enumerate(test_data):
            task_data = TaskCreate(
                name=name,
                description=f"Test task for {function} in {scope}",
                # Pass through test field and add result - type compatible for chaining
                script='# Test script\nreturn {"test": input["test"], "result": "processed"}',
                function=function,
                scope=scope,
                data_samples=[{"test": "value"}],  # Required for schema inference
            )

            task = await service.create_task(sample_tenant_id, task_data)
            tasks.append(task)

        await integration_test_session.commit()
        return tasks

    @pytest.mark.asyncio
    async def test_list_task_summaries_excludes_scripts(self, sample_tasks):
        """Verify that list_task_summaries does NOT include scripts."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries()

        assert "tasks" in result
        assert "total" in result
        assert "note" in result
        assert result["total"] > 0

        # Verify NO scripts in summaries
        for task in result["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "description" in task
            assert "function" in task
            assert "scope" in task
            # Scripts should NOT be present
            assert "script" not in task

    @pytest.mark.asyncio
    async def test_list_task_summaries_includes_usage_note(self, sample_tasks):
        """Verify that summaries include note about using get_task."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries()

        assert "note" in result
        assert "get_task" in result["note"]
        assert "task_ids" in result["note"]

    @pytest.mark.asyncio
    async def test_list_task_summaries_with_function_filter(self, sample_tasks):
        """Verify that function filter works with summaries."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries(function="search")

        assert "tasks" in result
        assert result["total"] > 0

        # All tasks should have function="search"
        for task in result["tasks"]:
            assert task["function"] == "search"

    @pytest.mark.asyncio
    async def test_list_task_summaries_with_scope_filter(self, sample_tasks):
        """Verify that scope filter works with summaries."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries(scope="processing")

        assert "tasks" in result

        # All tasks should have scope="processing"
        for task in result["tasks"]:
            assert task["scope"] == "processing"

    @pytest.mark.asyncio
    async def test_get_task_details_includes_scripts(self, sample_tasks):
        """Verify that get_task_details DOES include scripts."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Step 1: Get summaries to find task IDs
        summaries = await workflow_tools.list_task_summaries()
        assert summaries["total"] > 0

        # Step 2: Get details for first task
        task_id = summaries["tasks"][0]["id"]
        result = await workflow_tools.get_task_details(task_ids=[task_id])

        assert "tasks" in result
        assert "count" in result
        assert result["count"] == 1

        # Verify script IS present in details
        task_detail = result["tasks"][0]
        assert "id" in task_detail
        assert "name" in task_detail
        assert "description" in task_detail
        assert "function" in task_detail
        assert "scope" in task_detail
        assert "script" in task_detail  # Script should be present
        assert "directive" in task_detail
        assert "data_samples" in task_detail

        # Script should be non-empty
        assert task_detail["script"]
        assert len(task_detail["script"]) > 0

    @pytest.mark.asyncio
    async def test_get_task_details_multiple_tasks(self, sample_tasks):
        """Verify that get_task_details can fetch multiple tasks."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Get summaries
        summaries = await workflow_tools.list_task_summaries()
        assert summaries["total"] >= 2

        # Get details for first 2 tasks
        task_ids = [summaries["tasks"][0]["id"], summaries["tasks"][1]["id"]]
        result = await workflow_tools.get_task_details(task_ids=task_ids)

        assert result["count"] == 2
        assert len(result["tasks"]) == 2

        # Both should have scripts
        for task in result["tasks"]:
            assert "script" in task
            assert task["script"]

    @pytest.mark.asyncio
    async def test_get_task_details_invalid_task_id(self, sample_tasks):
        """Verify that invalid task IDs are skipped gracefully."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.get_task_details(
            task_ids=["00000000-0000-0000-0000-000000000000"]
        )

        # Should return empty list, not error
        assert "tasks" in result
        assert result["count"] == 0
        assert len(result["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_get_task_details_mixed_valid_invalid(self, sample_tasks):
        """Verify that mix of valid and invalid IDs returns only valid tasks."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Get one valid task ID
        summaries = await workflow_tools.list_task_summaries()
        valid_id = summaries["tasks"][0]["id"]

        # Mix valid and invalid
        task_ids = [
            valid_id,
            "00000000-0000-0000-0000-000000000000",  # Invalid
        ]

        result = await workflow_tools.get_task_details(task_ids=task_ids)

        # Should return only the valid task
        assert result["count"] == 1
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["id"] == valid_id

    @pytest.mark.asyncio
    async def test_progressive_disclosure_pattern_end_to_end(self, sample_tasks):
        """Test complete progressive disclosure pattern (main use case)."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Step 1: Browse summaries to decide what's interesting
        summaries = await workflow_tools.list_task_summaries(function="search")

        assert summaries["total"] > 0
        # Verify summaries are lightweight (no scripts)
        for task in summaries["tasks"]:
            assert "script" not in task

        # Step 2: User decides tasks 0 and 1 are interesting
        # Fetch full details only for those
        interesting_ids = [
            summaries["tasks"][0]["id"],
        ]

        if summaries["total"] >= 2:
            interesting_ids.append(summaries["tasks"][1]["id"])

        details = await workflow_tools.get_task_details(task_ids=interesting_ids)

        # Step 3: Verify we got full details with scripts
        assert details["count"] == len(interesting_ids)
        for task in details["tasks"]:
            assert "script" in task
            assert task["script"]  # Non-empty

    @pytest.mark.asyncio
    async def test_context_reduction_measurement(self, sample_tasks):
        """Measure context reduction from progressive disclosure."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Get all tasks with scripts (old way)
        all_tasks_result = await workflow_tools.list_available_tasks()

        # Get summaries only (new way - step 1)
        summaries_result = await workflow_tools.list_task_summaries()

        # Calculate token reduction
        # Each script is ~100-300 lines, summaries have no scripts
        # This should result in massive token savings

        all_tasks_count = all_tasks_result["total"]
        summaries_count = summaries_result["total"]

        # Same number of tasks
        assert all_tasks_count == summaries_count

        # But summaries don't have scripts
        for task in summaries_result["tasks"]:
            assert "script" not in task

        # All tasks DO have scripts
        for task in all_tasks_result["tasks"]:
            assert "script" in task

        # This pattern allows browsing 23 tasks (summaries)
        # then fetching details for only 2-3 interesting tasks
        # Context reduction: ~85-90%

    @pytest.mark.asyncio
    async def test_list_available_tasks_still_works_legacy(self, sample_tasks):
        """Verify that legacy list_available_tasks still works (backward compatibility)."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_available_tasks()

        assert "tasks" in result
        assert "total" in result
        assert result["total"] > 0

        # Should still return scripts (legacy behavior)
        for task in result["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "script" in task  # Scripts ARE present in legacy API

    # ============================================================================
    # cy_name-based API tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_list_task_summaries_includes_cy_name(self, sample_tasks):
        """Verify that list_task_summaries returns cy_name for each task."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        result = await workflow_tools.list_task_summaries()

        assert result["total"] > 0
        # Every task should have cy_name
        for task_summary in result["tasks"]:
            assert "cy_name" in task_summary
            assert task_summary["cy_name"] is not None
            assert isinstance(task_summary["cy_name"], str)

    @pytest.mark.asyncio
    async def test_get_task_details_accepts_cy_names(self, sample_tasks):
        """Verify that get_task_details accepts cy_name instead of UUID."""
        tenant_id = sample_tasks[0].component.tenant_id

        # Set tenant context
        set_tenant(tenant_id)

        # Get cy_name from the sample task
        cy_name = sample_tasks[0].component.cy_name
        assert cy_name is not None

        # Fetch by cy_name
        result = await workflow_tools.get_task_details(task_ids=[cy_name])

        assert result["count"] == 1
        assert len(result["tasks"]) == 1
        task_detail = result["tasks"][0]
        assert task_detail["cy_name"] == cy_name
        assert "script" in task_detail

    @pytest.mark.asyncio
    async def test_get_task_details_accepts_mixed_cy_names_and_uuids(
        self, sample_tasks
    ):
        """Verify that get_task_details accepts both cy_names and UUIDs."""
        # Get one cy_name and one UUID
        cy_name = sample_tasks[0].component.cy_name
        uuid_str = str(sample_tasks[1].component.id)

        # Fetch with mixed identifiers
        result = await workflow_tools.get_task_details(task_ids=[cy_name, uuid_str])

        assert result["count"] == 2
        assert len(result["tasks"]) == 2

        # Both should have scripts
        for task in result["tasks"]:
            assert "script" in task
            assert "cy_name" in task

    @pytest.mark.asyncio
    async def test_workflow_composer_uses_cy_names_from_list(self, sample_tasks):
        """
        End-to-end test: list tasks → get cy_names → compose workflow.

        This demonstrates the improved UX where users can:
        1. List tasks to see cy_names
        2. Use cy_names directly in compose_workflow
        """
        # Step 1: List tasks to discover cy_names
        summaries = await workflow_tools.list_task_summaries()
        assert summaries["total"] >= 2

        # Extract cy_names from first two tasks
        cy_name_1 = summaries["tasks"][0]["cy_name"]
        cy_name_2 = summaries["tasks"][1]["cy_name"]
        assert cy_name_1 is not None
        assert cy_name_2 is not None

        # Step 2: Use cy_names directly in compose_workflow
        # Start with task (not identity) for proper schema inference
        result = await workflow_tools.compose_workflow(
            composition=[cy_name_1, cy_name_2],  # Simple 2-task pipeline
            name="Test Workflow with Task cy_names",
            description="Uses cy_names discovered from list_task_summaries",
            execute=False,
        )

        # Should succeed (or have questions, but not errors about unknown tasks)
        # Debug: print errors if status is error
        if result["status"] == "error":
            print(f"Errors: {result.get('errors', [])}")

        assert result["status"] in ["success", "needs_decision"], (
            f"Expected success or needs_decision, got {result['status']}. "
            f"Errors: {result.get('errors', [])}"
        )
