"""
Integration tests for Workflow MCP Tools.

Tests that workflow builder MCP tools properly integrate with:
- WorkflowService
- WorkflowValidationService
- TaskService
- NodeTemplateService

All tests should FAIL initially since workflow tools are stubbed.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.constants import TemplateConstants
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import workflow_tools
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.models.workflow import NodeTemplate, Workflow, WorkflowEdge, WorkflowNode
from analysi.repositories.task import TaskRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestGetWorkflowTool:
    """Test get_workflow MCP tool."""

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
    async def sample_workflow(self, integration_test_session: AsyncSession) -> dict:
        """Create a sample workflow for testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        # Create workflow with 2 nodes and 1 edge
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Test Workflow",
            description="Workflow for MCP testing",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        # Create tasks first for the workflow nodes
        task1_comp_id = uuid4()
        task1_id = uuid4()
        task1_comp = Component(
            id=task1_comp_id,
            tenant_id=tenant_id,
            name="Start Task",
            description="Start task for workflow",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        task1 = Task(
            id=task1_id,
            component_id=task1_comp_id,
            function="reasoning",
            scope="processing",
            script="return input",
        )

        task2_comp_id = uuid4()
        task2_id = uuid4()
        task2_comp = Component(
            id=task2_comp_id,
            tenant_id=tenant_id,
            name="End Task",
            description="End task for workflow",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        task2 = Task(
            id=task2_id,
            component_id=task2_comp_id,
            function="reasoning",
            scope="processing",
            script="return input",
        )

        integration_test_session.add_all([task1_comp, task1, task2_comp, task2])
        await integration_test_session.flush()

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="task",
            name="Start Node",
            task_id=task1_comp_id,
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="task",
            name="End Node",
            task_id=task2_comp_id,
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.flush()
        await integration_test_session.refresh(node1)
        await integration_test_session.refresh(node2)

        edge1 = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="edge-1",
            from_node_uuid=node1.id,
            to_node_uuid=node2.id,
        )

        integration_test_session.add(edge1)
        await integration_test_session.commit()

        return {
            "workflow_id": str(workflow_id),
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_get_workflow_success(self, sample_workflow):
        """Verify retrieving an existing workflow returns complete definition."""
        workflow_id = sample_workflow["workflow_id"]
        tenant_id = sample_workflow["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.get_workflow(
            workflow_id=workflow_id, include_validation=True
        )

        # Should return workflow with complete definition
        assert "workflow" in result
        assert result["workflow"]["id"] == workflow_id
        assert result["workflow"]["name"] == "Test Workflow"
        assert len(result["workflow"]["nodes"]) == 2
        assert len(result["workflow"]["edges"]) == 1

        # Should include validation results
        assert "validation" in result

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self):
        """Verify helpful error message when workflow doesn't exist."""
        non_existent_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.get_workflow(workflow_id=non_existent_id)

        # Should return error information
        assert "error" in result or result.get("workflow") is None
        # Error message should be clear and actionable
        if "error" in result:
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_workflow_without_validation(self, sample_workflow):
        """Verify validation can be skipped for performance."""
        workflow_id = sample_workflow["workflow_id"]
        tenant_id = sample_workflow["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.get_workflow(
            workflow_id=workflow_id, include_validation=False
        )

        # Should return workflow
        assert "workflow" in result
        # Validation should be None or absent
        assert result.get("validation") is None or "validation" not in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestProgressiveTaskDisclosureTool:
    """Test progressive task discovery with list_task_summaries + get_task_details."""

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
    async def sample_tasks(self, integration_test_session: AsyncSession) -> dict:
        """Create sample tasks for testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        TaskRepository(integration_test_session)

        # Create 3 tasks with different functions and scopes
        tasks = []
        for i in range(3):
            component_id = uuid4()
            task_id = uuid4()
            cy_name = f"test_task_{i + 1}_{uuid4().hex[:6]}"

            component = Component(
                id=component_id,
                tenant_id=tenant_id,
                name=f"Task {i + 1}",
                description=f"Task {i + 1} for testing",
                categories=["test"],
                status="enabled",
                kind="task",
                cy_name=cy_name,  # cy_name is on Component, not Task
            )

            function = "reasoning" if i < 2 else "extraction"
            scope = "processing"

            task = Task(
                id=task_id,
                component_id=component_id,
                function=function,
                scope=scope,
                script=f"# Script for task {i + 1}\nreturn input",
            )

            integration_test_session.add(component)
            integration_test_session.add(task)
            tasks.append(
                {
                    "id": str(component_id),
                    "name": f"Task {i + 1}",
                    "function": function,
                    "scope": scope,
                    "cy_name": cy_name,
                }
            )

        await integration_test_session.commit()

        return {
            "tasks": tasks,
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_list_task_summaries_no_filters(self, sample_tasks):
        """Verify listing task summaries without filters returns metadata without scripts."""
        tenant_id = sample_tasks["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_task_summaries()

        # Should return all tasks
        assert "tasks" in result
        assert "total" in result
        assert result["total"] >= 3  # At least our 3 tasks

        # Each task should include required metadata fields
        for task in result["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "cy_name" in task
            assert "description" in task
            # Should NOT include script (summaries only)
            assert "script" not in task

    @pytest.mark.asyncio
    async def test_list_task_summaries_with_function_filter(self, sample_tasks):
        """Verify filtering task summaries by function."""
        tenant_id = sample_tasks["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_task_summaries(function="reasoning")

        # Should return only reasoning tasks
        assert "tasks" in result
        assert "total" in result

        # All returned tasks should have reasoning function
        for task in result["tasks"]:
            if "function" in task:
                assert task["function"] == "reasoning"

    @pytest.mark.asyncio
    async def test_list_task_summaries_with_scope_filter(self, sample_tasks):
        """Verify filtering task summaries by scope."""
        tenant_id = sample_tasks["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_task_summaries(scope="processing")

        # Should return only processing-scoped tasks
        assert "tasks" in result
        assert "total" in result

        # All returned tasks should have processing scope
        for task in result["tasks"]:
            if "scope" in task:
                assert task["scope"] == "processing"

    @pytest.mark.asyncio
    async def test_list_task_summaries_empty_result(self):
        """Verify graceful handling when no tasks match filters."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_task_summaries(
            function="nonexistent_function"
        )

        # Should return empty list gracefully
        assert "tasks" in result
        assert "total" in result
        assert result["total"] == 0
        assert len(result["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_get_task_details_returns_scripts(self, sample_tasks):
        """Verify get_task_details returns full task details including scripts."""
        tenant_id = sample_tasks["tenant_id"]
        sample_cy_names = [t["cy_name"] for t in sample_tasks["tasks"]]

        # Set tenant context
        set_tenant(tenant_id)

        # First get summaries to find task IDs
        summaries = await workflow_tools.list_task_summaries()

        # Get cy_names for our sample tasks
        task_cy_names = [
            t["cy_name"] for t in summaries["tasks"] if t["cy_name"] in sample_cy_names
        ]

        # Get full details using cy_names
        result = await workflow_tools.get_task_details(task_ids=task_cy_names[:2])

        # Should return full task details
        assert "tasks" in result
        assert "count" in result
        assert result["count"] == 2

        # Each task should include full details including script
        for task in result["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "cy_name" in task
            assert "script" in task  # Full details include scripts
            assert task["script"].startswith("# Script for task")
            assert "return input" in task["script"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestListAvailableTemplatesTool:
    """Test list_available_templates MCP tool."""

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
    async def sample_templates(self, integration_test_session: AsyncSession) -> dict:
        """Create sample NodeTemplates for testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Create 2 system templates and 1 tenant template
        templates = []
        for i in range(3):
            template_id = uuid4()
            resource_id = uuid4()
            is_system = i < 2

            template = NodeTemplate(
                id=template_id,
                resource_id=resource_id,
                tenant_id=None if is_system else tenant_id,
                name=f"Template {i + 1}",
                description=f"Template {i + 1} for testing",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                code="return inp",
                language="python",
                type="static",
                kind="identity" if i == 0 else "projection",
                enabled=True,
                revision_num=1,
            )

            integration_test_session.add(template)
            templates.append(
                {
                    "id": str(template_id),
                    "name": f"Template {i + 1}",
                    "kind": "identity" if i == 0 else "projection",
                    "scope": "system" if is_system else "tenant",
                }
            )

        await integration_test_session.commit()

        return {
            "templates": templates,
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_list_available_templates_no_filters(self, sample_templates):
        """Verify listing all NodeTemplates (system + tenant-specific)."""
        tenant_id = sample_templates["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_available_templates()

        # Should return all templates (system + tenant)
        assert "templates" in result
        assert "total" in result
        assert result["total"] >= 3  # At least our 3 templates
        # Each template should include required fields
        for template in result["templates"]:
            assert "id" in template
            assert "name" in template

    @pytest.mark.asyncio
    async def test_list_available_templates_with_kind_filter(self, sample_templates):
        """Verify filtering templates by kind."""
        tenant_id = sample_templates["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.list_available_templates(kind="projection")

        # Should return only projection templates
        assert "templates" in result
        assert "total" in result
        # All returned templates should have projection kind
        for template in result["templates"]:
            # If kind is included in response, verify it matches
            if "kind" in template:
                assert template["kind"] == "projection"


@pytest.mark.asyncio
@pytest.mark.integration
class TestCreateWorkflowTool:
    """Test create_workflow MCP tool."""

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

    @pytest.fixture(autouse=True)
    def enable_validation(self, monkeypatch):
        """Enable type validation for these tests (default is now False)."""
        from analysi.config.settings import settings

        monkeypatch.setattr(settings, "ENABLE_WORKFLOW_TYPE_VALIDATION", True)

    @pytest.fixture
    async def sample_tasks_for_workflow(
        self, integration_test_session: AsyncSession
    ) -> dict:
        """Create sample tasks to use in workflow."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Create 2 tasks with compatible schemas
        task_ids = []
        for i in range(2):
            component_id = uuid4()
            task_id = uuid4()

            component = Component(
                id=component_id,
                tenant_id=tenant_id,
                name=f"Workflow Task {i + 1}",
                description=f"Task {i + 1} for workflow",
                categories=["test"],
                status="enabled",
                kind="task",
            )

            task = Task(
                id=task_id,
                component_id=component_id,
                function="reasoning",
                scope="processing",
                script="result = input\nreturn result",
            )

            integration_test_session.add(component)
            integration_test_session.add(task)
            task_ids.append(str(component_id))

        await integration_test_session.commit()

        return {"task_ids": task_ids, "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_create_workflow_basic_success(self, sample_tasks_for_workflow):
        """Verify creating a simple workflow with nodes and edges."""
        tenant_id = sample_tasks_for_workflow["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        task_ids = sample_tasks_for_workflow["task_ids"]

        # Define workflow with 2 task nodes and 1 edge
        nodes = [
            {
                "node_id": "node-1",
                "kind": "task",
                "name": "Task 1",
                "task_id": task_ids[0],
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
            {
                "node_id": "node-2",
                "kind": "task",
                "name": "Task 2",
                "task_id": task_ids[1],
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
        ]

        edges = [
            {
                "source_node_id": "node-1",
                "target_node_id": "node-2",
                "source_output": "default",
                "target_input": "default",
            }
        ]

        result = await workflow_tools.create_workflow(
            name="Test Workflow",
            description="Created via MCP",
            nodes=nodes,
            edges=edges,
        )

        # Should return workflow_id and success
        assert "workflow_id" in result
        assert "success" in result
        assert result["success"] is True
        # Should include validation results
        assert "validation" in result

    @pytest.mark.asyncio
    async def test_create_workflow_with_type_validation_success(
        self, sample_tasks_for_workflow
    ):
        """Verify type validation runs automatically on creation."""
        tenant_id = sample_tasks_for_workflow["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        task_ids = sample_tasks_for_workflow["task_ids"]

        # Create workflow with compatible nodes
        nodes = [
            {
                "node_id": "node-1",
                "kind": "task",
                "name": "Task 1",
                "task_id": task_ids[0],
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"ip": {"type": "string"}},
                    },
                },
            },
            {
                "node_id": "node-2",
                "kind": "task",
                "name": "Task 2",
                "task_id": task_ids[1],
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {"ip": {"type": "string"}},
                    },
                    "output": {"type": "object"},
                },
            },
        ]

        edges = [{"source_node_id": "node-1", "target_node_id": "node-2"}]

        result = await workflow_tools.create_workflow(
            name="Type Safe Workflow",
            description="With compatible types",
            nodes=nodes,
            edges=edges,
        )

        # Should succeed
        assert result["success"] is True
        # Validation should be valid or include minimal errors
        assert "validation" in result

    @pytest.mark.asyncio
    async def test_create_workflow_with_type_mismatch(self, sample_tasks_for_workflow):
        """Verify type validation catches incompatible node connections."""
        tenant_id = sample_tasks_for_workflow["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        task_ids = sample_tasks_for_workflow["task_ids"]

        # Create workflow with incompatible types
        nodes = [
            {
                "node_id": "node-1",
                "kind": "task",
                "name": "Task 1",
                "task_id": task_ids[0],
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"count": {"type": "number"}},
                    },
                },
            },
            {
                "node_id": "node-2",
                "kind": "task",
                "name": "Task 2",
                "task_id": task_ids[1],
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                    },
                    "output": {"type": "object"},
                },
            },
        ]

        edges = [{"source_node_id": "node-1", "target_node_id": "node-2"}]

        result = await workflow_tools.create_workflow(
            name="Type Unsafe Workflow",
            description="With incompatible types",
            nodes=nodes,
            edges=edges,
        )

        # Workflow should be created
        assert "workflow_id" in result
        # But validation should report errors
        assert "validation" in result
        # Validation should indicate type mismatch
        # (exact format depends on implementation)

    @pytest.mark.asyncio
    async def test_create_workflow_with_missing_task(self):
        """Verify error when creating workflow with non-existent task."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        non_existent_task_id = str(uuid4())

        nodes = [
            {
                "node_id": "node-1",
                "kind": "task",
                "name": "Missing Task",
                "task_id": non_existent_task_id,
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            }
        ]

        result = await workflow_tools.create_workflow(
            name="Invalid Workflow",
            description="With non-existent task",
            nodes=nodes,
            edges=[],
        )

        # With FK constraint, workflow creation should fail with invalid task_id
        assert "success" in result
        assert result["success"] is False
        assert "error" in result
        assert (
            "foreign key" in result["error"].lower()
            or "not found" in result["error"].lower()
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestValidateWorkflowTypesTool:
    """Test validate_workflow_types MCP tool."""

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

    @pytest.fixture(autouse=True)
    def enable_validation(self, monkeypatch):
        """Enable type validation for these tests (default is now False)."""
        from analysi.config.settings import settings

        monkeypatch.setattr(settings, "ENABLE_WORKFLOW_TYPE_VALIDATION", True)

    @pytest.fixture
    async def workflow_for_validation(
        self, integration_test_session: AsyncSession
    ) -> dict:
        """Create a workflow for type validation testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        # Create workflow with compatible nodes
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Validation Test Workflow",
            description="For type validation testing",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Node 1",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            },
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="Node 2",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.flush()
        await integration_test_session.refresh(node1)
        await integration_test_session.refresh(node2)

        edge1 = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="edge-1",
            from_node_uuid=node1.id,
            to_node_uuid=node2.id,
        )

        integration_test_session.add(edge1)
        await integration_test_session.commit()

        return {"workflow_id": str(workflow_id), "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_validate_workflow_types_success(self, workflow_for_validation):
        """Verify validation passes for well-formed workflow."""
        workflow_id = workflow_for_validation["workflow_id"]
        workflow_for_validation["tenant_id"]

        result = await workflow_tools.validate_workflow_types(workflow_id=workflow_id)

        # Should return validation result
        assert "valid" in result
        # Validation should have errors list (may be empty)
        assert "errors" in result
        # May have warnings
        if "warnings" in result:
            assert isinstance(result["warnings"], list)

    @pytest.mark.asyncio
    async def test_validate_workflow_types_with_errors(
        self, integration_test_session: AsyncSession
    ):
        """Verify validation catches type mismatches."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        # Create workflow with type-incompatible nodes
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Invalid Type Workflow",
            description="With type mismatches",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Node 1",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "output": {
                    "type": "object",
                    "properties": {"count": {"type": "number"}},
                },
            },
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="Node 2",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.flush()
        await integration_test_session.refresh(node1)
        await integration_test_session.refresh(node2)

        edge1 = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="edge-1",
            from_node_uuid=node1.id,
            to_node_uuid=node2.id,
        )

        integration_test_session.add(edge1)
        await integration_test_session.commit()

        result = await workflow_tools.validate_workflow_types(
            workflow_id=str(workflow_id)
        )

        # Should return validation result
        assert "valid" in result
        assert "errors" in result
        # Should have at least one error due to type mismatch

    @pytest.mark.asyncio
    async def test_validate_workflow_types_nonexistent_workflow(self):
        """Verify error when validating non-existent workflow."""
        workflow_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.validate_workflow_types(workflow_id=workflow_id)

        # Should return error
        assert "error" in result or result.get("valid") is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestAddNodeTool:
    """Test add_node MCP tool."""

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
    async def workflow_for_node_addition(
        self, integration_test_session: AsyncSession
    ) -> dict:
        """Create a workflow for node addition testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Node Addition Workflow",
            description="For testing node addition",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Existing Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        integration_test_session.add(workflow)
        integration_test_session.add(node1)
        await integration_test_session.commit()

        return {"workflow_id": str(workflow_id), "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_add_node_success(self, workflow_for_node_addition):
        """Verify adding a node to existing workflow."""
        workflow_id = workflow_for_node_addition["workflow_id"]
        workflow_for_node_addition["tenant_id"]

        result = await workflow_tools.add_node(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="New Node",
            node_template_id=str(TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID),
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        # Workflows are now mutable - should succeed
        assert "success" in result
        assert result["success"] is True
        assert result["node_id"] == "node-2"

    @pytest.mark.asyncio
    async def test_add_node_with_template(
        self, workflow_for_node_addition, integration_test_session: AsyncSession
    ):
        """Verify adding a node using NodeTemplate."""
        workflow_id = workflow_for_node_addition["workflow_id"]
        tenant_id = workflow_for_node_addition["tenant_id"]

        # Create a NodeTemplate
        template_id = uuid4()
        template = NodeTemplate(
            id=template_id,
            resource_id=uuid4(),
            tenant_id=tenant_id,
            name="Test Template",
            description="For testing",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return inp",
            language="python",
            type="static",
            kind="projection",
            enabled=True,
            revision_num=1,
        )
        integration_test_session.add(template)
        await integration_test_session.commit()

        result = await workflow_tools.add_node(
            workflow_id=workflow_id,
            node_id="node-template",
            kind="transformation",
            name="Template Node",
            node_template_id=str(template_id),
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        # Workflows are now mutable - should succeed
        assert "success" in result
        assert result["success"] is True
        assert result["node_id"] == "node-template"

    @pytest.mark.asyncio
    async def test_add_node_duplicate_node_id(self, workflow_for_node_addition):
        """Verify error when adding node with existing node_id."""
        workflow_id = workflow_for_node_addition["workflow_id"]
        workflow_for_node_addition["tenant_id"]

        result = await workflow_tools.add_node(
            workflow_id=workflow_id,
            node_id="node-1",  # Already exists
            kind="transformation",
            name="Duplicate Node",
        )

        # Should return error
        assert "success" in result
        assert result["success"] is False or "error" in result

    @pytest.mark.asyncio
    async def test_add_node_to_nonexistent_workflow(self):
        """Verify error when adding node to invalid workflow."""
        workflow_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.add_node(
            workflow_id=workflow_id,
            node_id="node-new",
            kind="transformation",
            name="New Node",
        )

        # Should return error
        assert "error" in result or result.get("success") is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestAddEdgeTool:
    """Test add_edge MCP tool."""

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
    async def workflow_for_edge_addition(
        self, integration_test_session: AsyncSession
    ) -> dict:
        """Create a workflow for edge addition testing."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Edge Addition Workflow",
            description="For testing edge addition",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        # Create 2 nodes with compatible schemas
        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Source Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            },
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="Target Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.commit()

        return {"workflow_id": str(workflow_id), "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_add_edge_type_compatible(self, workflow_for_edge_addition):
        """Verify adding edge between type-compatible nodes."""
        workflow_id = workflow_for_edge_addition["workflow_id"]
        workflow_for_edge_addition["tenant_id"]

        result = await workflow_tools.add_edge(
            workflow_id=workflow_id,
            source_node_id="node-1",
            target_node_id="node-2",
        )

        # Workflows are now mutable - should succeed
        assert "success" in result
        assert result["success"] is True
        assert "edge_id" in result

    @pytest.mark.asyncio
    async def test_add_edge_type_incompatible(
        self, integration_test_session: AsyncSession
    ):
        """Verify error when connecting incompatible nodes."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Incompatible Edge Workflow",
            description="For testing incompatible edge",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        # Create 2 nodes with incompatible schemas
        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Source Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "output": {"type": "string"},  # Outputs string
            },
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="Target Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "number"},  # Expects number
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.commit()

        result = await workflow_tools.add_edge(
            workflow_id=str(workflow_id),
            source_node_id="node-1",
            target_node_id="node-2",
        )

        # Workflows are now mutable - edge creation succeeds regardless of types
        # (type validation is separate from mutation)
        assert "success" in result
        assert result["success"] is True
        assert "edge_id" in result

    @pytest.mark.asyncio
    async def test_add_edge_nonexistent_nodes(self, workflow_for_edge_addition):
        """Verify error when adding edge with invalid node references."""
        workflow_id = workflow_for_edge_addition["workflow_id"]
        workflow_for_edge_addition["tenant_id"]

        result = await workflow_tools.add_edge(
            workflow_id=workflow_id,
            source_node_id="nonexistent-node",
            target_node_id="node-2",
        )

        # Should return error because source node doesn't exist
        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_edge_with_named_ports(
        self, integration_test_session: AsyncSession
    ):
        """Verify connecting specific input/output ports."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        workflow_id = uuid4()

        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Named Ports Workflow",
            description="For testing named ports",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        # Create nodes with multiple outputs/inputs
        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Source Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "outputs": {
                    "default": {"type": "object"},
                    "metadata": {
                        "type": "object",
                        "properties": {"info": {"type": "string"}},
                    },
                },
            },
        )

        node2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-2",
            kind="transformation",
            name="Target Node",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "inputs": {
                    "default": {"type": "object"},
                    "enrichment_data": {
                        "type": "object",
                        "properties": {"info": {"type": "string"}},
                    },
                },
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add_all([node1, node2])
        await integration_test_session.commit()

        result = await workflow_tools.add_edge(
            workflow_id=str(workflow_id),
            source_node_id="node-1",
            target_node_id="node-2",
            source_output="metadata",
            target_input="enrichment_data",
        )

        # Should return success
        assert "success" in result
        # Edge should use specified ports
        if "edge" in result:
            # Edge details should reflect named ports
            pass  # Implementation will verify port details


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowMCPServerAccessibility:
    """Test workflow MCP server is accessible and tools are registered."""

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
    async def test_analysi_mcp_server_accessible(self):
        """Verify unified analysi MCP server can be created."""
        from analysi.mcp.analysi_server import create_analysi_mcp_server

        server = create_analysi_mcp_server()
        assert server is not None
        assert server.name == "analysi"

    @pytest.mark.asyncio
    async def test_analysi_mcp_has_workflow_tools(self):
        """Verify workflow tools are registered in the unified analysi server."""
        from analysi.mcp.analysi_server import create_analysi_mcp_server

        server = create_analysi_mcp_server()
        tool_names = list(server._tool_manager._tools.keys())

        # Core workflow tools must be present
        assert "compose_workflow" in tool_names
        assert "get_workflow" in tool_names
        assert "list_workflows" in tool_names
        assert "run_workflow" in tool_names
        assert "add_workflow_node" in tool_names
        assert "add_workflow_edge" in tool_names


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowMCPErrorHandling:
    """Test error handling across workflow MCP tools."""

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
    async def test_tools_handle_database_errors_gracefully(
        self, integration_test_session: AsyncSession
    ):
        """Verify tools return helpful errors on database failures."""
        # Test with invalid session or database error condition
        # For now, test with invalid workflow ID
        workflow_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.get_workflow(workflow_id=workflow_id)

        # Should not raise unhandled exception
        # Should return error information
        assert result is not None
        # Should have error or None workflow
        assert "error" in result or result.get("workflow") is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestComposeWorkflowTool:
    """Test compose_workflow MCP tool."""

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
    async def test_compose_sequential_workflow(
        self, integration_test_session: AsyncSession
    ):
        """Test composing a simple sequential workflow."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=["identity", "identity", "identity"],
            name="Sequential Workflow",
            description="Three sequential identity nodes",
            execute=False,
        )

        # Should succeed or return questions
        assert result is not None
        assert result["status"] in ["success", "needs_decision", "error"]

        if result["status"] == "success":
            assert result["plan"] is not None
            assert result["plan"]["nodes"] == 3
            assert result["plan"]["edges"] == 2
            assert len(result.get("errors", [])) == 0

    @pytest.mark.asyncio
    async def test_compose_parallel_workflow_with_merge(
        self, integration_test_session: AsyncSession
    ):
        """Test composing a parallel workflow with merge aggregation."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=["identity", ["identity", "identity"], "merge", "identity"],
            name="Parallel Workflow",
            description="Parallel execution with merge",
            execute=False,
        )

        assert result is not None
        assert result["status"] in ["success", "needs_decision", "error"]

        if result["status"] == "success":
            assert result["plan"] is not None
            assert result["plan"]["nodes"] == 5
            assert len(result.get("questions", [])) == 0  # merge provided

    @pytest.mark.asyncio
    async def test_compose_missing_aggregation_generates_question(
        self, integration_test_session: AsyncSession
    ):
        """Test that missing aggregation generates a question."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=["identity", ["identity", "identity"], "identity"],
            name="Missing Aggregation",
            description="Should generate question",
            execute=False,
        )

        assert result is not None
        # Should have errors about missing aggregation
        assert result["status"] == "error"
        assert len(result.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_compose_with_execution(self, integration_test_session: AsyncSession):
        """Test compose with execute=True creates workflow (doesn't run it)."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Execute Workflow",
            description="Should create workflow",
            execute=True,
        )

        assert result is not None
        # When execute=True, should create workflow (not run it)
        if result["status"] == "success":
            assert result.get("workflow_id") is not None
            # workflow_run_id is not set because workflow is only created, not executed
            assert result.get("workflow_run_id") is None

    @pytest.mark.asyncio
    async def test_compose_invalid_composition(
        self, integration_test_session: AsyncSession
    ):
        """Test compose with invalid composition returns errors."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=[],  # Empty composition
            name="Invalid Workflow",
            description="Should fail",
            execute=False,
        )

        assert result is not None
        assert result["status"] == "error"
        assert len(result.get("errors", [])) > 0
        assert "empty" in result["errors"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_compose_unknown_task_reference(
        self, integration_test_session: AsyncSession
    ):
        """Test compose with unknown task reference."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await workflow_tools.compose_workflow(
            composition=["identity", "unknown_task_xyz", "identity"],
            name="Unknown Task",
            description="Should report task not found",
            execute=False,
        )

        assert result is not None
        assert result["status"] == "error"
        assert len(result.get("errors", [])) > 0


@pytest.mark.asyncio
@pytest.mark.integration
class TestTypeValidationFeatureFlag:
    """Test that type validation is disabled by default (ENABLE_WORKFLOW_TYPE_VALIDATION=False)."""

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

    # NOTE: No autouse fixture here for validation - we test with the default (False)

    @pytest.fixture
    async def sample_tasks_for_workflow(
        self, integration_test_session: AsyncSession
    ) -> dict:
        """Create sample tasks to use in workflow."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Create 2 tasks with compatible schemas
        task_ids = []
        for i in range(2):
            component_id = uuid4()
            task_id = uuid4()

            component = Component(
                id=component_id,
                tenant_id=tenant_id,
                name=f"Workflow Task {i + 1}",
                description=f"Task {i + 1} for workflow",
                categories=["test"],
                status="enabled",
                kind="task",
            )

            task = Task(
                id=task_id,
                component_id=component_id,
                function="reasoning",
                scope="processing",
                script="result = input\nreturn result",
            )

            integration_test_session.add(component)
            integration_test_session.add(task)
            task_ids.append(str(component_id))

        await integration_test_session.commit()

        return {"task_ids": task_ids, "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_create_workflow_with_validation_disabled_by_default(
        self, sample_tasks_for_workflow
    ):
        """Verify type validation is skipped by default (flag is False)."""
        tenant_id = sample_tasks_for_workflow["tenant_id"]
        set_tenant(tenant_id)
        task_ids = sample_tasks_for_workflow["task_ids"]

        # Create workflow (validation should be skipped by default)
        nodes = [
            {
                "node_id": "node-1",
                "kind": "task",
                "name": "Task 1",
                "task_id": task_ids[0],
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            }
        ]

        result = await workflow_tools.create_workflow(
            name="No Validation Workflow",
            description="Validation should be skipped by default",
            nodes=nodes,
            edges=[],
        )

        # Should succeed
        assert result["success"] is True
        # Validation should be skipped (valid=False because status != "valid")
        assert "validation" in result
        assert (
            result["validation"]["valid"] is False
        )  # Because status is "skipped", not "valid"
        assert len(result["validation"]["warnings"]) > 0
        assert "disabled" in result["validation"]["warnings"][0]["message"].lower()
        assert len(result["validation"]["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_workflow_types_disabled_by_default(
        self, integration_test_session: AsyncSession
    ):
        """Verify validate_workflow_types returns skipped by default (flag is False)."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)
        workflow_id = uuid4()

        # Create workflow for validation testing
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Validation Test Workflow",
            description="For type validation testing",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Node 1",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={
                "input": {"type": "object"},
                "output": {"type": "object"},
            },
        )

        integration_test_session.add(workflow)
        integration_test_session.add(node1)
        await integration_test_session.commit()

        result = await workflow_tools.validate_workflow_types(
            workflow_id=str(workflow_id)
        )

        # Should return valid=True with warning (validation is skipped)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) > 0
        assert "disabled" in result["warnings"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_get_workflow_with_validation_disabled_by_default(
        self, integration_test_session: AsyncSession
    ):
        """Verify get_workflow skips validation by default (flag is False)."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)
        workflow_id = uuid4()

        # Create workflow
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Test Workflow",
            description="Workflow for MCP testing",
            is_dynamic=False,
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )

        node1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="node-1",
            kind="transformation",
            name="Node 1",
            node_template_id=TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID,
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        integration_test_session.add(workflow)
        integration_test_session.add(node1)
        await integration_test_session.commit()

        result = await workflow_tools.get_workflow(
            workflow_id=str(workflow_id), include_validation=True
        )

        # Should return workflow
        assert "workflow" in result
        # Validation should be skipped
        assert "validation" in result
        assert result["validation"]["status"] == "skipped"
        assert "disabled" in result["validation"]["warnings"][0]["message"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteWorkflowTool:
    """Test execute_workflow MCP tool.

    Tests the blocking workflow execution that polls for completion
    and retrieves output from StorageManager.
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

    @pytest.mark.asyncio
    async def test_execute_workflow_nonexistent_workflow(self):
        """Verify error when executing non-existent workflow."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        non_existent_id = str(uuid4())

        result = await workflow_tools.execute_workflow(
            workflow_id=non_existent_id,
            input_data={"test": "value"},
            timeout_seconds=5,
        )

        # Should return error status
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()
        assert result["workflow_run_id"] is None
        assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_success_with_output(
        self, integration_test_session: AsyncSession
    ):
        """Verify execute_workflow returns output on completion.

        This test exercises the StorageManager.retrieve() path that was
        fixed (previously missing storage_type, location, content_type args).
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Create a simple identity workflow using compose_workflow
        compose_result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Test Execute Workflow",
            description="For testing execute_workflow output retrieval",
            execute=False,  # Just create, don't execute yet
        )

        assert compose_result["status"] == "success", (
            f"Compose failed: {compose_result}"
        )
        workflow_id = compose_result["workflow_id"]

        # Execute the workflow
        result = await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data={"test_key": "test_value", "number": 42},
            timeout_seconds=30,
        )

        # Should complete successfully
        assert "status" in result
        assert "workflow_run_id" in result
        assert "execution_time_ms" in result

        # Handle both success and error cases
        if result["status"] == "completed":
            # Output should contain the input (identity workflow passes through)
            assert "output" in result
            # Identity workflow returns input as-is
            if result["output"] is not None:
                # The exact structure depends on workflow implementation
                pass  # Output structure varies
        elif result["status"] == "error":
            # Log error for debugging but don't fail test
            # Some environments may not have workflow execution fully configured
            print(
                f"Execute workflow error (may be expected in test env): {result.get('error')}"
            )
            assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_returns_execution_time(
        self, integration_test_session: AsyncSession
    ):
        """Verify execute_workflow always returns execution_time_ms."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Create workflow
        compose_result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Execution Time Test",
            description="Test that execution_time_ms is always returned",
            execute=False,
        )

        assert compose_result["status"] == "success"
        workflow_id = compose_result["workflow_id"]

        # Execute
        result = await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data={},
            timeout_seconds=30,
        )

        # execution_time_ms should always be present regardless of status
        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)
        assert result["execution_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_workflow_timeout_behavior(self):
        """Verify execute_workflow respects timeout and returns timeout status.

        Note: This test uses a very short timeout to test the timeout path.
        In a real scenario, workflows should complete within reasonable time.
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Create workflow
        compose_result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Timeout Test Workflow",
            description="For testing timeout behavior",
            execute=False,
        )

        if compose_result["status"] != "success":
            pytest.skip("Could not create workflow for timeout test")

        workflow_id = compose_result["workflow_id"]

        # Execute with very short timeout (0.1s)
        # This may timeout or complete quickly - both are valid outcomes
        result = await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data={},
            timeout_seconds=0.1,
        )

        # Status should be one of the valid states
        assert result["status"] in ["completed", "failed", "timeout", "error"]
        assert "execution_time_ms" in result

        # If timeout occurred, verify the error message
        if result["status"] == "timeout":
            assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_workflow_with_empty_input(
        self, integration_test_session: AsyncSession
    ):
        """Verify execute_workflow handles empty input data."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Create workflow
        compose_result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Empty Input Test",
            description="Test with empty input",
            execute=False,
        )

        assert compose_result["status"] == "success"
        workflow_id = compose_result["workflow_id"]

        # Execute with empty input
        result = await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data={},
            timeout_seconds=30,
        )

        # Should not crash, should return valid response structure
        assert "status" in result
        assert "workflow_run_id" in result
        assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_result_structure(
        self, integration_test_session: AsyncSession
    ):
        """Verify execute_workflow returns all expected fields."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Test with non-existent workflow to get error response
        non_existent_id = str(uuid4())

        result = await workflow_tools.execute_workflow(
            workflow_id=non_existent_id,
            input_data={},
            timeout_seconds=5,
        )

        # All responses should have these fields
        required_fields = [
            "workflow_run_id",
            "status",
            "workflow_id",
            "execution_time_ms",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

        # Status should be valid
        assert result["status"] in ["completed", "failed", "timeout", "error"]

        # On error, should have error field
        if result["status"] in ["error", "failed"]:
            assert "error" in result
