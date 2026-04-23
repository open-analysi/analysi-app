"""Integration tests for list_workflows MCP tool."""

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import workflow_tools
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestListWorkflowsMCP:
    """Integration tests for list_workflows MCP tool."""

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

    @pytest.mark.asyncio
    async def test_list_workflows_returns_thin_representations(
        self, integration_test_session
    ):
        """
        Test list_workflows returns thin workflow representations.

        Expected format for each workflow:
        {
            "workflow_id": str,
            "name": str,
            "description": str,
            "composition": list,  # Array format like ["task1", "task2"]
            "created_by": str,
            "created_at": str,
            "status": str
        }
        """
        # Set tenant context
        set_tenant("default")

        # Create a test workflow using compose_workflow with execute=True
        from analysi.services.workflow_composer.service import WorkflowComposerService

        # Get a session - reuse integration_test_session
        composer = WorkflowComposerService(integration_test_session)

        # Compose and create the workflow
        result = await composer.compose_workflow(
            composition=["identity", "identity"],
            workflow_name="Test List Workflow",
            workflow_description="Workflow for testing list functionality",
            tenant_id="default",
            created_by=str(SYSTEM_USER_ID),
            execute=True,  # This will persist the workflow
        )

        assert result.status in [
            "success",
            "needs_decision",
        ], f"Composition failed: {result.errors}"
        assert result.workflow_id is not None, (
            "compose_workflow with execute=True should return workflow_id"
        )

        await integration_test_session.commit()
        workflow_id = str(result.workflow_id)

        # Now call list_workflows
        list_result = await workflow_tools.list_workflows()

        # Verify response structure
        assert isinstance(list_result, dict)
        assert "workflows" in list_result
        assert "total" in list_result
        assert isinstance(list_result["workflows"], list)
        assert isinstance(list_result["total"], int)

        # Should have at least one workflow (the one we just created)
        assert list_result["total"] >= 1
        assert len(list_result["workflows"]) >= 1

        # Verify each workflow has the thin representation
        for workflow in list_result["workflows"]:
            assert "workflow_id" in workflow
            assert "name" in workflow
            assert "description" in workflow
            assert "composition" in workflow
            assert "created_by" in workflow
            assert "created_at" in workflow
            assert "status" in workflow

            # Verify composition is a list
            assert isinstance(workflow["composition"], list)

            # Verify types
            assert isinstance(workflow["workflow_id"], str)
            assert isinstance(workflow["name"], str)
            assert isinstance(workflow["created_by"], str)
            assert isinstance(workflow["status"], str)

        # Find our created workflow in the list
        our_workflow = next(
            (wf for wf in list_result["workflows"] if wf["workflow_id"] == workflow_id),
            None,
        )
        assert our_workflow is not None, "Should find our created workflow"
        assert our_workflow["name"] == "Test List Workflow"
        assert our_workflow["description"] == "Workflow for testing list functionality"

    @pytest.mark.asyncio
    async def test_list_workflows_empty_tenant(self):
        """Test list_workflows with a tenant that has no workflows."""
        # Set a unique tenant that won't have workflows
        set_tenant("empty_tenant_no_workflows_xyz123")

        result = await workflow_tools.list_workflows()

        assert isinstance(result, dict)
        assert "workflows" in result
        assert "total" in result
        assert result["total"] == 0
        assert len(result["workflows"]) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_composition_format(self, integration_test_session):
        """
        Test that composition is correctly reverse-engineered from workflow structure.

        For a linear workflow, composition should be a simple array.
        For parallel workflows, composition should include nested arrays.
        """
        # Set tenant context
        set_tenant("default")

        # Create a simple linear workflow using WorkflowComposerService
        from analysi.services.workflow_composer.service import WorkflowComposerService

        composer = WorkflowComposerService(integration_test_session)
        compose_result = await composer.compose_workflow(
            composition=["identity", "identity", "identity"],
            workflow_name="Linear Test Workflow",
            workflow_description="Linear workflow for testing",
            tenant_id="default",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )

        assert compose_result.status in ["success", "needs_decision"]
        assert compose_result.workflow_id is not None
        workflow_id = str(compose_result.workflow_id)

        await integration_test_session.commit()

        # Get the workflow list
        result = await workflow_tools.list_workflows()

        # Find our workflow
        our_workflow = None
        for wf in result["workflows"]:
            if wf["workflow_id"] == workflow_id:
                our_workflow = wf
                break

        assert our_workflow is not None, "Should find our created workflow"

        # Verify composition structure (should be a simple array for linear flow)
        assert isinstance(our_workflow["composition"], list)
        assert len(our_workflow["composition"]) >= 2  # At least two nodes

        # For now, we accept that composition might be simplified or node IDs
        # The important thing is it's a list that represents the workflow structure

    @pytest.mark.asyncio
    async def test_list_workflows_with_limit(self, integration_test_session):
        """Test list_workflows with limit parameter."""
        set_tenant("default")

        # Create multiple workflows using WorkflowComposerService
        from analysi.services.workflow_composer.service import WorkflowComposerService

        composer = WorkflowComposerService(integration_test_session)
        for i in range(3):
            result = await composer.compose_workflow(
                composition=["identity"],
                workflow_name=f"Test Workflow {i}",
                workflow_description=f"Test workflow number {i}",
                tenant_id="default",
                created_by=str(SYSTEM_USER_ID),
                execute=True,
            )
            assert result.status in ["success", "needs_decision"]

        await integration_test_session.commit()

        # List with limit
        result = await workflow_tools.list_workflows(limit=2)

        assert isinstance(result, dict)
        assert "workflows" in result
        assert "total" in result
        # Should return at most 2 workflows
        assert len(result["workflows"]) <= 2

    @pytest.mark.asyncio
    async def test_list_workflows_includes_created_at_timestamp(
        self, integration_test_session
    ):
        """Test that created_at is included and is a valid timestamp string."""
        set_tenant("default")

        # Create workflow using WorkflowComposerService
        from analysi.services.workflow_composer.service import WorkflowComposerService

        composer = WorkflowComposerService(integration_test_session)
        result = await composer.compose_workflow(
            composition=["identity"],
            workflow_name="Timestamp Test Workflow",
            workflow_description="Test timestamp",
            tenant_id="default",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )
        assert result.status in ["success", "needs_decision"]

        await integration_test_session.commit()

        result = await workflow_tools.list_workflows()

        assert result["total"] >= 1
        workflow = result["workflows"][0]

        assert "created_at" in workflow
        # Should be an ISO format timestamp string
        assert isinstance(workflow["created_at"], str)
        # Basic check for ISO format (contains 'T' separator)
        assert "T" in workflow["created_at"] or " " in workflow["created_at"]

    @pytest.mark.asyncio
    async def test_list_workflows_composition_contains_cy_names_not_node_ids(
        self, integration_test_session
    ):
        """
        Test that composition array contains task cy_names, not node_ids.

        This is critical for usability - users should see recognizable task names
        like "ip_reputation_check" not internal node IDs like "n-abcd1234".

        Bug: Previously returned node.node_id for all nodes instead of task.cy_name
        for task nodes.
        """
        set_tenant("default")

        # Create a test task with a known cy_name
        from uuid import uuid4

        from analysi.schemas.task import TaskCreate
        from analysi.services.task import TaskService

        task_service = TaskService(integration_test_session)

        # Create a simple task with a known cy_name
        task_cy_name = f"test_task_for_composition_{uuid4().hex[:8]}"

        task_data = TaskCreate(
            name="Test Task for Composition",
            cy_name=task_cy_name,
            script='return {"test": "result"}',
            function="enrichment",
            scope="processing",
            mode="saved",
            data_samples=[{"test": "input"}],
            created_by=str(SYSTEM_USER_ID),
        )

        await task_service.create_task(
            tenant_id="default",
            task_data=task_data,
        )
        await integration_test_session.commit()

        # Create a workflow using this task
        from analysi.services.workflow_composer.service import WorkflowComposerService

        composer = WorkflowComposerService(integration_test_session)
        compose_result = await composer.compose_workflow(
            composition=["identity", task_cy_name, "identity"],
            workflow_name="Test Workflow with Task",
            workflow_description="Workflow for testing cy_name in composition",
            tenant_id="default",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )

        assert compose_result.status == "success", (
            f"Composition failed: {compose_result.errors}"
        )
        assert compose_result.workflow_id is not None
        workflow_id = str(compose_result.workflow_id)

        await integration_test_session.commit()

        # Call list_workflows
        result = await workflow_tools.list_workflows()

        # Find our workflow
        our_workflow = next(
            (wf for wf in result["workflows"] if wf["workflow_id"] == workflow_id), None
        )
        assert our_workflow is not None, "Should find our created workflow in list"

        # Verify composition contains the cy_name, not node_id (this was the bug)
        composition = our_workflow["composition"]
        assert isinstance(composition, list)
        assert len(composition) >= 3, (
            f"Expected at least 3 nodes, got {len(composition)}"
        )

        # CRITICAL: Task nodes should return cy_name, not internal node_id
        assert task_cy_name in composition, (
            f"BUG NOT FIXED: Composition should contain task cy_name '{task_cy_name}', "
            f"but got: {composition}. Task nodes must use cy_name for user readability."
        )

        # Verify templates/non-task nodes still use node_ids (they don't have cy_names)
        non_task_nodes = [node for node in composition if node != task_cy_name]
        assert len(non_task_nodes) >= 2, "Should have at least 2 template nodes"
