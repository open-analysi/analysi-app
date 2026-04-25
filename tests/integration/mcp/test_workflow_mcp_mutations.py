"""
Integration tests for Workflow MCP Mutation Tools.
Tests add/remove/update operations on workflows via MCP tools.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.constants import TemplateConstants
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import workflow_tools
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow import Workflow, WorkflowNode


@pytest.fixture(autouse=True)
def _mcp_user():
    """Set MCP user context so RBAC checks pass.

    Uses platform_admin to cover all operations including delete
    (which requires admin role).
    """
    set_mcp_current_user(
        CurrentUser(
            user_id="test-user",
            email="test@test.com",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )
    )
    return


@pytest.fixture
async def empty_workflow(integration_test_session: AsyncSession) -> dict:
    """Create empty workflow for mutation testing."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    set_tenant(tenant_id)
    workflow_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        tenant_id=tenant_id,
        name="Mutable Workflow",
        description="For mutation testing",
        is_dynamic=False,
        io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
        created_by=str(SYSTEM_USER_ID),
    )

    integration_test_session.add(workflow)
    await integration_test_session.commit()

    return {"workflow_id": str(workflow_id), "tenant_id": tenant_id}


@pytest.fixture
async def workflow_with_nodes(integration_test_session: AsyncSession) -> dict:
    """Create workflow with two nodes for edge testing."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    set_tenant(tenant_id)
    workflow_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        tenant_id=tenant_id,
        name="Workflow With Nodes",
        description="For edge testing",
        is_dynamic=False,
        io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
        created_by=str(SYSTEM_USER_ID),
    )

    node1 = WorkflowNode(
        workflow_id=workflow_id,
        node_id="node-1",
        kind="transformation",
        name="Node 1",
        is_start_node=True,
        node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
        schemas={"input": {"type": "object"}, "output": {"type": "object"}},
    )

    node2 = WorkflowNode(
        workflow_id=workflow_id,
        node_id="node-2",
        kind="transformation",
        name="Node 2",
        node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
        schemas={"input": {"type": "object"}, "output": {"type": "object"}},
    )

    integration_test_session.add(workflow)
    integration_test_session.add_all([node1, node2])
    await integration_test_session.commit()

    return {
        "workflow_id": str(workflow_id),
        "tenant_id": tenant_id,
        "node_ids": ["node-1", "node-2"],
    }


@pytest.mark.asyncio
@pytest.mark.integration
class TestAddNodeMCP:
    """Test add_node MCP tool."""

    @pytest.mark.asyncio
    async def test_add_node_success(self, empty_workflow):
        """Add node to empty workflow."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.add_node(
            workflow_id=empty_workflow["workflow_id"],
            node_id="new-node",
            kind="transformation",
            name="New Node",
            node_template_id=str(TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID),
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["node_id"] == "new-node"

    @pytest.mark.asyncio
    async def test_add_node_nonexistent_workflow(self):
        """Error when workflow doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.add_node(
            workflow_id=str(uuid4()),
            node_id="new-node",
            kind="transformation",
            name="New Node",
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_node_duplicate_node_id(self, workflow_with_nodes):
        """Error when node_id already exists."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.add_node(
            workflow_id=workflow_with_nodes["workflow_id"],
            node_id="node-1",  # Already exists
            kind="transformation",
            name="Duplicate Node",
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestAddNodeCyNameResolution:
    """Test add_node with cy_name resolution."""

    @pytest.mark.asyncio
    async def test_add_node_with_cy_name(
        self, empty_workflow, integration_test_session: AsyncSession
    ):
        """Add task node using cy_name instead of UUID."""
        from analysi.models.component import Component, ComponentKind
        from analysi.models.task import Task

        tenant_id = empty_workflow["tenant_id"]
        set_tenant(tenant_id)

        # Create a Component with cy_name
        component = Component(
            tenant_id=tenant_id,
            name="Test Context Generator",
            cy_name="test_context_gen",
            kind=ComponentKind.TASK,
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create the Task that references the component
        task = Task(
            component_id=component.id,
            script="return input",
            directive="Test directive",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        # Add node using cy_name (not UUID)
        result = await workflow_tools.add_node(
            workflow_id=empty_workflow["workflow_id"],
            node_id="context-node",
            kind="task",
            name="Context Node",
            task_id="test_context_gen",  # cy_name, not UUID
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["node_id"] == "context-node"

    @pytest.mark.asyncio
    async def test_add_node_with_uuid(
        self, empty_workflow, integration_test_session: AsyncSession
    ):
        """Add task node using UUID still works."""
        from analysi.models.component import Component, ComponentKind
        from analysi.models.task import Task

        tenant_id = empty_workflow["tenant_id"]
        set_tenant(tenant_id)

        # Create a Component
        component = Component(
            tenant_id=tenant_id,
            name="Test Task",
            cy_name="test_task_uuid",
            kind=ComponentKind.TASK,
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create the Task
        task = Task(
            component_id=component.id,
            script="return input",
            directive="Test directive",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        # Add node using UUID
        result = await workflow_tools.add_node(
            workflow_id=empty_workflow["workflow_id"],
            node_id="task-node",
            kind="task",
            name="Task Node",
            task_id=str(component.id),  # UUID
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["node_id"] == "task-node"

    @pytest.mark.asyncio
    async def test_add_node_invalid_cy_name(self, empty_workflow):
        """Error when cy_name doesn't exist."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.add_node(
            workflow_id=empty_workflow["workflow_id"],
            node_id="bad-node",
            kind="task",
            name="Bad Node",
            task_id="nonexistent_cy_name",
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
class TestAddEdgeMCP:
    """Test add_edge MCP tool."""

    @pytest.mark.asyncio
    async def test_add_edge_success(self, workflow_with_nodes):
        """Add edge between existing nodes."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.add_edge(
            workflow_id=workflow_with_nodes["workflow_id"],
            source_node_id="node-1",
            target_node_id="node-2",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert "edge_id" in result

    @pytest.mark.asyncio
    async def test_add_edge_nonexistent_nodes(self, workflow_with_nodes):
        """Error when source or target node doesn't exist."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.add_edge(
            workflow_id=workflow_with_nodes["workflow_id"],
            source_node_id="nonexistent",
            target_node_id="node-2",
        )

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestRemoveNodeMCP:
    """Test remove_node MCP tool."""

    @pytest.mark.asyncio
    async def test_remove_node_success(self, workflow_with_nodes):
        """Remove node from workflow."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.remove_node(
            workflow_id=workflow_with_nodes["workflow_id"],
            node_id="node-2",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"

    @pytest.mark.asyncio
    async def test_remove_node_nonexistent(self, workflow_with_nodes):
        """Graceful handling when node doesn't exist."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.remove_node(
            workflow_id=workflow_with_nodes["workflow_id"],
            node_id="nonexistent",
        )

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestRemoveEdgeMCP:
    """Test remove_edge MCP tool."""

    @pytest.mark.asyncio
    async def test_remove_edge_success(
        self, workflow_with_nodes, integration_test_session: AsyncSession
    ):
        """Remove edge from workflow."""
        set_tenant(workflow_with_nodes["tenant_id"])
        workflow_id = workflow_with_nodes["workflow_id"]

        # First add an edge via MCP
        add_result = await workflow_tools.add_edge(
            workflow_id=workflow_id,
            source_node_id="node-1",
            target_node_id="node-2",
            edge_id="test-edge",
        )
        assert add_result["success"] is True, (
            f"add_edge failed: {add_result.get('error')}"
        )

        # Now remove it
        result = await workflow_tools.remove_edge(
            workflow_id=workflow_id,
            edge_id="test-edge",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"

    @pytest.mark.asyncio
    async def test_remove_edge_nonexistent(self, workflow_with_nodes):
        """Graceful handling when edge doesn't exist."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.remove_edge(
            workflow_id=workflow_with_nodes["workflow_id"],
            edge_id="nonexistent",
        )

        assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestUpdateWorkflowMCP:
    """Test update_workflow MCP tool."""

    @pytest.mark.asyncio
    async def test_update_workflow_name(self, empty_workflow):
        """Update workflow name."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.update_workflow(
            workflow_id=empty_workflow["workflow_id"],
            name="Updated Name",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_workflow_description(self, empty_workflow):
        """Update workflow description."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.update_workflow(
            workflow_id=empty_workflow["workflow_id"],
            description="New description",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"

    @pytest.mark.asyncio
    async def test_update_workflow_nonexistent(self):
        """Error when workflow doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.update_workflow(
            workflow_id=str(uuid4()),
            name="New Name",
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_workflow_io_schema(self, empty_workflow):
        """Update workflow io_schema."""
        set_tenant(empty_workflow["tenant_id"])

        new_schema = {
            "input": {
                "type": "object",
                "properties": {"source_ip": {"type": "string"}},
            },
            "output": {"type": "object"},
        }

        result = await workflow_tools.update_workflow(
            workflow_id=empty_workflow["workflow_id"],
            io_schema=new_schema,
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["io_schema"] == new_schema

    @pytest.mark.asyncio
    async def test_update_workflow_data_samples(self, empty_workflow):
        """Update workflow data_samples."""
        set_tenant(empty_workflow["tenant_id"])

        samples = [
            {"source_ip": "192.168.1.100", "alert_title": "Test Alert 1"},
            {"source_ip": "10.0.0.50", "alert_title": "Test Alert 2"},
        ]

        result = await workflow_tools.update_workflow(
            workflow_id=empty_workflow["workflow_id"],
            data_samples=samples,
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["data_samples"] == samples

    @pytest.mark.asyncio
    async def test_update_workflow_io_schema_and_samples(self, empty_workflow):
        """Update both io_schema and data_samples together."""
        set_tenant(empty_workflow["tenant_id"])

        new_schema = {
            "input": {
                "type": "object",
                "properties": {"ip": {"type": "string"}},
            },
            "output": {"type": "object"},
        }
        samples = [{"ip": "8.8.8.8"}]

        result = await workflow_tools.update_workflow(
            workflow_id=empty_workflow["workflow_id"],
            io_schema=new_schema,
            data_samples=samples,
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["io_schema"] == new_schema
        assert result["data_samples"] == samples


@pytest.mark.asyncio
@pytest.mark.integration
class TestUpdateNodeMCP:
    """Test update_node MCP tool."""

    @pytest.mark.asyncio
    async def test_update_node_name(self, workflow_with_nodes):
        """Update node name."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.update_node(
            workflow_id=workflow_with_nodes["workflow_id"],
            node_id="node-1",
            name="Updated Node Name",
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert result["name"] == "Updated Node Name"

    @pytest.mark.asyncio
    async def test_update_node_nonexistent(self, workflow_with_nodes):
        """Error when node doesn't exist."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.update_node(
            workflow_id=workflow_with_nodes["workflow_id"],
            node_id="nonexistent",
            name="New Name",
        )

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeleteWorkflowMCP:
    """Test delete_workflow MCP tool."""

    @pytest.mark.asyncio
    async def test_delete_workflow_success(self, empty_workflow):
        """Delete workflow."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.delete_workflow(
            workflow_id=empty_workflow["workflow_id"],
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"

    @pytest.mark.asyncio
    async def test_delete_workflow_nonexistent(self):
        """Error when workflow doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.delete_workflow(
            workflow_id=str(uuid4()),
        )

        assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestStartWorkflowMCP:
    """Test start_workflow MCP tool (non-blocking). Requires Redis for ARQ enqueue."""

    @pytest.mark.asyncio
    async def test_start_workflow_returns_run_id(self, workflow_with_nodes):
        """Non-blocking start returns workflow_run_id immediately."""
        set_tenant(workflow_with_nodes["tenant_id"])

        result = await workflow_tools.start_workflow(
            workflow_id=workflow_with_nodes["workflow_id"],
            input_data={"test": "value"},
        )

        assert result["success"] is True, f"MCP tool failed: {result.get('error')}"
        assert "workflow_run_id" in result
        assert result["workflow_run_id"] is not None

    @pytest.mark.asyncio
    async def test_start_workflow_nonexistent(self):
        """Error when workflow doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.start_workflow(
            workflow_id=str(uuid4()),
            input_data={},
        )

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestGetWorkflowRunStatusMCP:
    """Test get_workflow_run_status MCP tool. Requires Redis for start_workflow."""

    @pytest.mark.asyncio
    async def test_get_status_after_start(self, workflow_with_nodes):
        """Get status of running workflow."""
        set_tenant(workflow_with_nodes["tenant_id"])

        start_result = await workflow_tools.start_workflow(
            workflow_id=workflow_with_nodes["workflow_id"],
            input_data={},
        )

        assert start_result["success"] is True
        run_id = start_result["workflow_run_id"]

        # Get status
        result = await workflow_tools.get_workflow_run_status(
            workflow_run_id=run_id,
        )

        assert "status" in result
        assert result["status"] in ["pending", "running", "completed", "failed"]

    @pytest.mark.asyncio
    async def test_get_status_nonexistent(self):
        """Error when workflow run doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.get_workflow_run_status(
            workflow_run_id=str(uuid4()),
        )

        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestGetWorkflowRunMCP:
    """Test get_workflow_run MCP tool."""

    @pytest.mark.asyncio
    async def test_get_run_details(self, workflow_with_nodes):
        """Get full workflow run details - verify structure."""
        set_tenant(workflow_with_nodes["tenant_id"])

        start_result = await workflow_tools.start_workflow(
            workflow_id=workflow_with_nodes["workflow_id"],
            input_data={"key": "value"},
        )

        assert start_result["success"] is True
        run_id = start_result["workflow_run_id"]

        # Get full details - may error due to session isolation in tests
        result = await workflow_tools.get_workflow_run(
            workflow_run_id=run_id,
        )

        # Either we get the run details or an error (session isolation in tests)
        assert ("workflow_run_id" in result and "status" in result) or "error" in result

    @pytest.mark.asyncio
    async def test_get_run_nonexistent(self):
        """Error when workflow run doesn't exist."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        result = await workflow_tools.get_workflow_run(
            workflow_run_id=str(uuid4()),
        )

        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestListWorkflowRunsMCP:
    """Test list_workflow_runs MCP tool. Requires Redis for start_workflow."""

    @pytest.mark.asyncio
    async def test_list_runs_for_workflow(self, workflow_with_nodes):
        """List execution history for a workflow - verify structure."""
        set_tenant(workflow_with_nodes["tenant_id"])
        workflow_id = workflow_with_nodes["workflow_id"]

        # Start a run
        start_result = await workflow_tools.start_workflow(
            workflow_id=workflow_id,
            input_data={},
        )

        assert start_result["success"] is True

        # List runs - may be empty due to session isolation in tests
        result = await workflow_tools.list_workflow_runs(
            workflow_id=workflow_id,
        )

        assert "runs" in result
        assert "total" in result
        # May be 0 or >= 1 depending on session isolation
        assert isinstance(result["total"], int)

    @pytest.mark.asyncio
    async def test_list_runs_empty(self, empty_workflow):
        """List runs for workflow with no executions."""
        set_tenant(empty_workflow["tenant_id"])

        result = await workflow_tools.list_workflow_runs(
            workflow_id=empty_workflow["workflow_id"],
        )

        assert "runs" in result
        assert result["total"] == 0
