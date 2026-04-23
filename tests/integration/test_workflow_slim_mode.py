"""
Integration tests for workflow response format.

Tests that get_workflow returns proper WorkflowResponse with all expected fields.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.task import TaskCreate
from analysi.schemas.workflow import WorkflowCreate
from analysi.services.task import TaskService
from analysi.services.workflow import WorkflowService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_includes_all_fields(db_session: AsyncSession):
    """Test that get_workflow returns WorkflowResponse with all expected fields."""
    tenant_id = "test-full-tenant"
    task_service = TaskService(db_session)
    workflow_service = WorkflowService(db_session)

    # Create a simple task
    task_data = TaskCreate(
        name="Test Task for Full Mode",
        cy_name="test_full_task",
        description="Task for testing full responses",
        script='return {"result": "test"}',
        function="enrichment",
        scope="processing",
    )
    task = await task_service.create_task(tenant_id=tenant_id, task_data=task_data)
    await db_session.flush()  # Ensure task is committed before referencing in workflow

    # Create a workflow
    workflow_data = WorkflowCreate(
        name="Test Workflow for Full Mode",
        description="Workflow for testing full responses",
        created_by=str(SYSTEM_USER_ID),
        io_schema={
            "input": {
                "type": "object",
                "properties": {"test_input": {"type": "string"}},
                "required": ["test_input"],
            },
            "output": {"type": "object"},
        },
        data_samples=[{"name": "test", "input": {"test_input": "value"}}],
        nodes=[
            {
                "node_id": "task1",
                "kind": "task",
                "name": "Task Node",
                "task_id": str(task.component_id),  # Use component_id not task.id
                "is_start_node": True,
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
        ],
        edges=[],
    )
    workflow = await workflow_service.create_workflow(tenant_id, workflow_data)

    # Get workflow (standard mode)
    full_result = await workflow_service.get_workflow(tenant_id, workflow.id)

    # Verify full result is WorkflowResponse (has model_dump)
    assert hasattr(full_result, "model_dump"), "Should return WorkflowResponse"

    # Convert to dict for inspection
    full_dict = full_result.model_dump()

    # Verify nodes have ALL fields including timestamps and UUIDs
    assert len(full_dict["nodes"]) == 1
    node = full_dict["nodes"][0]
    assert "id" in node, "Should include database UUID"
    assert "created_at" in node, "Should include timestamps"
    assert "task_id" in node, "Should include task_id"
    assert "schemas" in node, "Should include schemas"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_with_parallel_structure(db_session: AsyncSession):
    """Test get_workflow with a parallel workflow structure."""
    tenant_id = "test-parallel-workflow"
    task_service = TaskService(db_session)
    workflow_service = WorkflowService(db_session)

    # Create tasks
    tasks = []
    for i in range(3):
        task_data = TaskCreate(
            name=f"Parallel Task {i}",
            cy_name=f"parallel_task_{i}",
            description=f"Task {i}",
            script='return {"result": "test"}',
            function="enrichment",
            scope="processing",
        )
        task = await task_service.create_task(tenant_id=tenant_id, task_data=task_data)
        tasks.append(task)

    await (
        db_session.flush()
    )  # Ensure tasks are committed before referencing in workflow

    # Create parallel workflow: task0 -> [task1, task2] -> merge
    workflow_data = WorkflowCreate(
        name="Parallel Workflow Test",
        description="Test parallel structure",
        created_by=str(SYSTEM_USER_ID),
        io_schema={
            "input": {
                "type": "object",
                "properties": {"test_input": {"type": "string"}},
                "required": ["test_input"],
            },
            "output": {"type": "object"},
        },
        data_samples=[{"name": "test", "input": {"test_input": "value"}}],
        nodes=[
            {
                "node_id": "start",
                "kind": "task",
                "name": "Start Task",
                "task_id": str(tasks[0].component_id),  # Use component_id
                "is_start_node": True,
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
            {
                "node_id": "branch1",
                "kind": "task",
                "name": "Branch 1",
                "task_id": str(tasks[1].component_id),  # Use component_id
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
            {
                "node_id": "branch2",
                "kind": "task",
                "name": "Branch 2",
                "task_id": str(tasks[2].component_id),  # Use component_id
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            },
            {
                "node_id": "merge",
                "kind": "transformation",
                "name": "Merge",
                "node_template_id": "00000000-0000-0000-0000-000000000002",
                "schemas": {"input": {"type": "array"}, "output": {"type": "object"}},
            },
        ],
        edges=[
            {"edge_id": "e1", "from_node_id": "start", "to_node_id": "branch1"},
            {"edge_id": "e2", "from_node_id": "start", "to_node_id": "branch2"},
            {"edge_id": "e3", "from_node_id": "branch1", "to_node_id": "merge"},
            {"edge_id": "e4", "from_node_id": "branch2", "to_node_id": "merge"},
        ],
    )
    workflow = await workflow_service.create_workflow(tenant_id, workflow_data)

    # Get workflow
    result = await workflow_service.get_workflow(tenant_id, workflow.id)

    # Verify result is WorkflowResponse
    assert hasattr(result, "model_dump"), "Should return WorkflowResponse"
    result_dict = result.model_dump()

    # Verify structure
    assert len(result_dict["nodes"]) == 4
    assert len(result_dict["edges"]) == 4

    # Verify task nodes
    task_nodes = [n for n in result_dict["nodes"] if n["kind"] == "task"]
    assert len(task_nodes) == 3

    # Verify merge node
    merge_nodes = [n for n in result_dict["nodes"] if n["node_id"] == "merge"]
    assert len(merge_nodes) == 1
    assert merge_nodes[0]["kind"] == "transformation"

    # Verify all nodes have full fields
    for node in result_dict["nodes"]:
        assert "id" in node
        assert "node_id" in node
        assert "kind" in node
        assert "name" in node
