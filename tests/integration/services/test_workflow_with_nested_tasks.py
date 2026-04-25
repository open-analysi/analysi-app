"""
Integration tests: workflows whose task nodes use nested task_run() calls.

These tests verify the complete Ithaca stack end-to-end:

  Session Isolation — execute_single_task() creates an isolated session per task node
  Subroutine Model — nested task_run() calls are subroutines sharing the parent's session
  Concurrent Fan-out — asyncio.gather() in monitor_execution()

The tests use real WorkflowExecutor.monitor_execution(), real Cy script
execution, and no patches — the entire stack is exercised.

Topologies tested:

  Sequential chain with nested subtask
    identity → [enricher] → output
    enricher calls task_run("double_value") internally

  Diamond with nested subtasks in both branches
    identity → [B, C] → merge
    B and C each call a shared helper subtask via task_run()

  Deep nesting through a workflow
    identity → [task_A] → [task_B] → output
    task_A calls task_run("helper"), task_B calls task_run("helper") independently
"""

import json
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow_execution import WorkflowNodeInstance
from analysi.repositories.task import TaskRepository
from analysi.repositories.workflow_execution import WorkflowRunRepository
from analysi.services.workflow_execution import WorkflowExecutor
from tests.utils.cy_output import parse_cy_output

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

TENANT_ID = "ithaca-nested-workflow-tenant"


# ---------------------------------------------------------------------------
# Helpers — task creation
# ---------------------------------------------------------------------------


async def _create_task(
    session: AsyncSession,
    cy_name: str,
    script: str,
) -> str:
    """Create a Task and return its component_id (string UUID)."""
    repo = TaskRepository(session)
    task = await repo.create(
        {
            "tenant_id": TENANT_ID,
            "name": f"Nested WF Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()
    return str(task.component_id)


# ---------------------------------------------------------------------------
# Helpers — workflow / run creation (via HTTP API)
# ---------------------------------------------------------------------------


async def _get_passthrough_template(http_client) -> str:
    template_data = {
        "name": f"nwf-passthrough-{uuid4().hex[:6]}",
        "description": "Pass through input unchanged",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "code": "return inp",
        "language": "python",
        "type": "static",
    }
    response = await http_client.post(
        f"/v1/{TENANT_ID}/workflows/node-templates", json=template_data
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _get_merge_template_id(http_client) -> str:
    response = await http_client.get(f"/v1/{TENANT_ID}/workflows/node-templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    merge = next((t for t in templates if t["name"] == "system_merge"), None)
    assert merge is not None, "system_merge template not found"
    return merge["id"]


async def _create_workflow(http_client, name: str, nodes: list, edges: list) -> UUID:
    data = {
        "name": f"{name} {uuid4().hex[:6]}",
        "description": name,
        "is_dynamic": False,
        "created_by": str(SYSTEM_USER_ID),
        "io_schema": {"input": {"type": "object"}, "output": {"type": "object"}},
        "nodes": nodes,
        "edges": edges,
    }
    response = await http_client.post(f"/v1/{TENANT_ID}/workflows", json=data)
    assert response.status_code == 201, f"Failed to create workflow: {response.text}"
    return UUID(response.json()["data"]["id"])


async def _start_run(session, http_client, workflow_id: UUID, input_data: dict) -> UUID:
    response = await http_client.post(
        f"/v1/{TENANT_ID}/workflows/{workflow_id}/run",
        json={"input_data": input_data},
    )
    assert response.status_code == 202, f"Failed to start run: {response.text}"
    await session.commit()
    return UUID(response.json()["data"]["workflow_run_id"])


async def _run_and_assert_completed(session, run_id: UUID):
    """Run monitor_execution and assert the workflow_run reaches 'completed'."""
    executor = WorkflowExecutor(session)
    await executor.monitor_execution(run_id)
    await session.commit()
    session.expire_all()

    run_repo = WorkflowRunRepository(session)
    workflow_run = await run_repo.get_workflow_run(TENANT_ID, run_id)
    assert workflow_run is not None
    assert workflow_run.status == "completed", (
        f"Workflow run status={workflow_run.status!r}. "
        f"Error: {workflow_run.error_message}"
    )
    return workflow_run


async def _get_node_instances(session, run_id: UUID) -> dict[str, WorkflowNodeInstance]:
    """Return a dict of node_id → WorkflowNodeInstance."""
    stmt = select(WorkflowNodeInstance).where(
        WorkflowNodeInstance.workflow_run_id == run_id
    )
    result = await session.execute(stmt)
    return {inst.node_id: inst for inst in result.scalars().all()}


def _parse_output(inst: WorkflowNodeInstance):
    """Parse output_location JSON from a node instance."""
    if inst.output_location:
        raw = json.loads(inst.output_location)
        return parse_cy_output(raw.get("result", raw))
    return None


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def workflow_client(integration_test_session):
    async def override_get_db():
        yield integration_test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, integration_test_session
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestSequentialWorkflowWithNestedTask:
    """
    Single task node in a workflow that internally calls task_run().

    Topology:  identity → [enricher_node] → (terminal)

    The enricher_node's Cy script calls task_run("double_value") to compute
    its result. This exercises session isolation + subroutine model
    through the real monitor_execution() path.
    """

    async def test_single_task_node_calls_nested_task_run(self, workflow_client):
        """
        Workflow with one task node that internally calls task_run().

        identity passes {value: 5} → enricher calls double_value → returns {result: 10}.
        """
        http_client, session = workflow_client

        # Register the helper subtask (only in the DB, not a workflow node)
        suffix = uuid4().hex[:8]
        await _create_task(
            session,
            cy_name=f"double_value_{suffix}",
            script='return input["n"] * 2',
        )

        # The workflow task node calls the helper via task_run()
        enricher_id = await _create_task(
            session,
            cy_name=f"enricher_{suffix}",
            script=(
                f'doubled = task_run("double_value_{suffix}", {{"n": input["value"]}})\n'
                f'return {{"result": doubled}}'
            ),
        )

        passthrough_id = await _get_passthrough_template(http_client)
        workflow_id = await _create_workflow(
            http_client,
            name="Sequential nested task_run",
            nodes=[
                {
                    "node_id": "n-identity",
                    "kind": "transformation",
                    "name": "Identity",
                    "is_start_node": True,
                    "node_template_id": passthrough_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-enricher",
                    "kind": "task",
                    "name": "Enricher",
                    "task_id": enricher_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {
                    "edge_id": "e1",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-enricher",
                },
            ],
        )
        run_id = await _start_run(session, http_client, workflow_id, {"value": 5})
        await _run_and_assert_completed(session, run_id)

        session.expire_all()
        instances = await _get_node_instances(session, run_id)
        assert "n-enricher" in instances, "Enricher node instance missing"

        enricher_inst = instances["n-enricher"]
        assert enricher_inst.status == "completed", (
            f"Enricher node status={enricher_inst.status!r}. "
            f"Error: {enricher_inst.error_message}"
        )
        output = _parse_output(enricher_inst)
        assert output is not None, "Enricher produced no output"
        assert output.get("result") == 10, (
            f"Expected result=10 (5*2), got {output!r}. "
            f"nested task_run() may not be working through monitor_execution()."
        )

    async def test_nested_task_run_chain_three_levels(self, workflow_client):
        """
        Workflow task node calls a two-level nested task_run() chain.

        Level 1 (workflow node) → calls level2 → calls level3 (leaf).
        n=3: leaf returns 3*4=12, level2 returns 12+1=13, node returns {result: 13}.
        """
        http_client, session = workflow_client
        suffix = uuid4().hex[:8]

        await _create_task(
            session,
            cy_name=f"leaf_mul4_{suffix}",
            script='return input["n"] * 4',
        )
        await _create_task(
            session,
            cy_name=f"mid_add1_{suffix}",
            script=(
                f'v = task_run("leaf_mul4_{suffix}", {{"n": input["n"]}})\nreturn v + 1'
            ),
        )
        top_id = await _create_task(
            session,
            cy_name=f"top_wrapper_{suffix}",
            script=(
                f'v = task_run("mid_add1_{suffix}", {{"n": input["n"]}})\n'
                f'return {{"result": v}}'
            ),
        )

        passthrough_id = await _get_passthrough_template(http_client)
        workflow_id = await _create_workflow(
            http_client,
            name="Three-level nested via workflow node",
            nodes=[
                {
                    "node_id": "n-identity",
                    "kind": "transformation",
                    "name": "Identity",
                    "is_start_node": True,
                    "node_template_id": passthrough_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-top",
                    "kind": "task",
                    "name": "Top wrapper",
                    "task_id": top_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {"edge_id": "e1", "from_node_id": "n-identity", "to_node_id": "n-top"},
            ],
        )
        run_id = await _start_run(session, http_client, workflow_id, {"n": 3})
        await _run_and_assert_completed(session, run_id)

        session.expire_all()
        instances = await _get_node_instances(session, run_id)
        output = _parse_output(instances["n-top"])
        # 3*4=12, 12+1=13
        assert output.get("result") == 13, (
            f"Expected result=13 from three-level nesting, got {output!r}"
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestDiamondWorkflowWithNestedTasks:
    """
    Diamond topology where both parallel branches call shared nested subtasks.

    Topology:  identity → [B, C] → merge

    B calls task_run("shared_helper") and C calls task_run("shared_helper").
    Both run concurrently (fan-out) while each using the subroutine model.
    This is the most realistic nested execution scenario.
    """

    async def test_diamond_both_branches_use_nested_task_run(self, workflow_client):
        """
        Concurrent branches B and C both call task_run() on a shared helper.

        B: {b_result: n*2}   C: {c_result: n*3}   with n=6.
        Expected: B.b_result=12, C.c_result=18.
        """
        http_client, session = workflow_client
        suffix = uuid4().hex[:8]
        n = 6

        # Shared helper — called by both B and C concurrently
        await _create_task(
            session,
            cy_name=f"shared_mul_{suffix}",
            script='return input["x"] * input["factor"]',
        )

        branch_b_id = await _create_task(
            session,
            cy_name=f"branch_b_{suffix}",
            script=(
                f'v = task_run("shared_mul_{suffix}", {{"x": input["n"], "factor": 2}})\n'
                f'return {{"b_result": v}}'
            ),
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"branch_c_{suffix}",
            script=(
                f'v = task_run("shared_mul_{suffix}", {{"x": input["n"], "factor": 3}})\n'
                f'return {{"c_result": v}}'
            ),
        )

        passthrough_id = await _get_passthrough_template(http_client)
        merge_id = await _get_merge_template_id(http_client)

        workflow_id = await _create_workflow(
            http_client,
            name="Diamond with nested task_run in both branches",
            nodes=[
                {
                    "node_id": "n-identity",
                    "kind": "transformation",
                    "name": "Identity",
                    "is_start_node": True,
                    "node_template_id": passthrough_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-b",
                    "kind": "task",
                    "name": "Branch B",
                    "task_id": branch_b_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-c",
                    "kind": "task",
                    "name": "Branch C",
                    "task_id": branch_c_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-merge",
                    "kind": "transformation",
                    "name": "Merge",
                    "node_template_id": merge_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {
                    "edge_id": "e-id-b",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-branch-b",
                },
                {
                    "edge_id": "e-id-c",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-branch-c",
                },
                {
                    "edge_id": "e-b-m",
                    "from_node_id": "n-branch-b",
                    "to_node_id": "n-merge",
                },
                {
                    "edge_id": "e-c-m",
                    "from_node_id": "n-branch-c",
                    "to_node_id": "n-merge",
                },
            ],
        )
        run_id = await _start_run(session, http_client, workflow_id, {"n": n})
        await _run_and_assert_completed(session, run_id)

        session.expire_all()
        instances = await _get_node_instances(session, run_id)

        b_output = _parse_output(instances["n-branch-b"])
        c_output = _parse_output(instances["n-branch-c"])

        assert b_output is not None, "Branch B produced no output"
        assert c_output is not None, "Branch C produced no output"

        assert b_output.get("b_result") == n * 2, (
            f"Branch B: b_result={b_output.get('b_result')!r}, expected {n * 2}. "
            f"Session isolation may be broken under concurrent execution."
        )
        assert c_output.get("c_result") == n * 3, (
            f"Branch C: c_result={c_output.get('c_result')!r}, expected {n * 3}. "
            f"Session isolation may be broken under concurrent execution."
        )

    async def test_diamond_nested_tasks_create_no_extra_task_run_records(
        self, workflow_client
    ):
        """
        Subroutine model must hold inside workflow execution:
        nested task_run() calls must NOT create new TaskRun DB records.

        We count TaskRun rows before and after. Only 2 TaskRun rows should
        be created — one per workflow task node (B and C). The nested helper
        calls are subroutines and must not produce rows.
        """
        from sqlalchemy import func

        from analysi.models.task_run import TaskRun

        http_client, session = workflow_client
        suffix = uuid4().hex[:8]

        await _create_task(
            session,
            cy_name=f"helper_add_{suffix}",
            script='return input["v"] + 100',
        )
        branch_b_id = await _create_task(
            session,
            cy_name=f"b_with_helper_{suffix}",
            script=(
                f'result = task_run("helper_add_{suffix}", {{"v": input["x"]}})\n'
                f'return {{"b": result}}'
            ),
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"c_with_helper_{suffix}",
            script=(
                f'result = task_run("helper_add_{suffix}", {{"v": input["x"] * 2}})\n'
                f'return {{"c": result}}'
            ),
        )

        passthrough_id = await _get_passthrough_template(http_client)
        merge_id = await _get_merge_template_id(http_client)

        workflow_id = await _create_workflow(
            http_client,
            name="Diamond subroutine model verification",
            nodes=[
                {
                    "node_id": "n-identity",
                    "kind": "transformation",
                    "name": "Identity",
                    "is_start_node": True,
                    "node_template_id": passthrough_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-b",
                    "kind": "task",
                    "name": "Branch B",
                    "task_id": branch_b_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-c",
                    "kind": "task",
                    "name": "Branch C",
                    "task_id": branch_c_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-merge",
                    "kind": "transformation",
                    "name": "Merge",
                    "node_template_id": merge_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {
                    "edge_id": "e-id-b",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-b",
                },
                {
                    "edge_id": "e-id-c",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-c",
                },
                {"edge_id": "e-b-m", "from_node_id": "n-b", "to_node_id": "n-merge"},
                {"edge_id": "e-c-m", "from_node_id": "n-c", "to_node_id": "n-merge"},
            ],
        )
        run_id = await _start_run(session, http_client, workflow_id, {"x": 5})

        # Count TaskRun rows before execution
        result = await session.execute(
            select(func.count())
            .select_from(TaskRun)
            .where(TaskRun.tenant_id == TENANT_ID)
        )
        count_before = result.scalar()

        await _run_and_assert_completed(session, run_id)

        session.expire_all()
        result = await session.execute(
            select(func.count())
            .select_from(TaskRun)
            .where(TaskRun.tenant_id == TENANT_ID)
        )
        count_after = result.scalar()

        # 2 task nodes → 2 new TaskRun rows (one per node, not per subtask call)
        assert count_after == count_before + 2, (
            f"Expected exactly 2 new TaskRun rows (one per task node). "
            f"Got {count_after - count_before} new rows. "
            f"Nested task_run() must not create TaskRun records (subroutine model)."
        )

        # Also verify correct computed values
        instances = await _get_node_instances(session, run_id)
        b_output = _parse_output(instances["n-b"])
        c_output = _parse_output(instances["n-c"])
        assert b_output.get("b") == 5 + 100, f"Branch B wrong: {b_output}"
        assert c_output.get("c") == 10 + 100, f"Branch C wrong: {c_output}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSequentialChainWithNestedTasks:
    """
    Sequential workflow A → B → C where each task calls task_run() internally.

    This tests that session isolation holds across sequential
    node handoffs through monitor_execution().
    """

    async def test_sequential_chain_each_node_uses_nested_task_run(
        self, workflow_client
    ):
        """
        A → B → C, each calls a helper via task_run().

        Helper adds 1 to its input.
        A: x=10 → calls helper(10) → {a: 11}
        B: receives {a: 11}, calls helper(11) → {b: 12}
        C: receives {b: 12}, calls helper(12) → {c: 13}
        """
        http_client, session = workflow_client
        suffix = uuid4().hex[:8]

        await _create_task(
            session,
            cy_name=f"add_one_{suffix}",
            script='return input["n"] + 1',
        )

        node_a_id = await _create_task(
            session,
            cy_name=f"chain_a_{suffix}",
            script=(
                f'v = task_run("add_one_{suffix}", {{"n": input["x"]}})\n'
                f'return {{"a": v}}'
            ),
        )
        node_b_id = await _create_task(
            session,
            cy_name=f"chain_b_{suffix}",
            script=(
                f'v = task_run("add_one_{suffix}", {{"n": input["a"]}})\n'
                f'return {{"b": v}}'
            ),
        )
        node_c_id = await _create_task(
            session,
            cy_name=f"chain_c_{suffix}",
            script=(
                f'v = task_run("add_one_{suffix}", {{"n": input["b"]}})\n'
                f'return {{"c": v}}'
            ),
        )

        passthrough_id = await _get_passthrough_template(http_client)
        workflow_id = await _create_workflow(
            http_client,
            name="Sequential chain with nested task_run at each step",
            nodes=[
                {
                    "node_id": "n-identity",
                    "kind": "transformation",
                    "name": "Identity",
                    "is_start_node": True,
                    "node_template_id": passthrough_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-a",
                    "kind": "task",
                    "name": "Node A",
                    "task_id": node_a_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-b",
                    "kind": "task",
                    "name": "Node B",
                    "task_id": node_b_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-c",
                    "kind": "task",
                    "name": "Node C",
                    "task_id": node_c_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {
                    "edge_id": "e-id-a",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-a",
                },
                {"edge_id": "e-a-b", "from_node_id": "n-a", "to_node_id": "n-b"},
                {"edge_id": "e-b-c", "from_node_id": "n-b", "to_node_id": "n-c"},
            ],
        )
        run_id = await _start_run(session, http_client, workflow_id, {"x": 10})
        await _run_and_assert_completed(session, run_id)

        session.expire_all()
        instances = await _get_node_instances(session, run_id)

        a_output = _parse_output(instances["n-a"])
        b_output = _parse_output(instances["n-b"])
        c_output = _parse_output(instances["n-c"])

        assert a_output.get("a") == 11, f"Node A: expected a=11, got {a_output}"
        assert b_output.get("b") == 12, f"Node B: expected b=12, got {b_output}"
        assert c_output.get("c") == 13, f"Node C: expected c=13, got {c_output}"
