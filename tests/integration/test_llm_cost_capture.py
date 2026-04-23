"""
Integration tests: LLM token and cost capture.

These tests run real LLM calls via the configured OpenAI integration (using
OPENAI_API_KEY from the dev environment) and verify that token counts and
cost metadata are captured end-to-end:

  1. TaskExecutionResult.llm_usage — populated after execute_single_task()
  2. TaskRun.execution_context["_llm_usage"] — persisted to the DB
  3. TaskRunResponse.llm_usage — surfaced via the REST GET endpoint
  4. WorkflowNodeInstanceResponse.llm_usage — per-node in workflow graph
  5. WorkflowRunResponse.llm_usage — aggregate across all task nodes

Each test uses a unique tenant_id to avoid cross-test interference.
"""

import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# All tests in this module require a real OpenAI API key
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("ANALYSI_LLM_INTEGRATION_TESTS"),
        reason="Requires tenant LLM integration setup — set ANALYSI_LLM_INTEGRATION_TESTS=1 to enable",
    ),
]

from analysi.db.session import get_db  # noqa: E402
from analysi.main import app  # noqa: E402
from analysi.models.auth import SYSTEM_USER_ID  # noqa: E402
from analysi.models.component import Component  # noqa: E402
from analysi.models.task import Task  # noqa: E402
from analysi.models.task_run import TaskRun  # noqa: E402
from analysi.services.task_execution import TaskExecutionService  # noqa: E402
from analysi.services.workflow_execution import WorkflowExecutor  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal Cy script that calls llm_run() once — short prompt, low cost
# ---------------------------------------------------------------------------

_LLM_SCRIPT = """result = llm_run("Reply with the single word: PONG")
return {"response": result}
"""

_LLM_SCRIPT_MULTI = """
a = llm_run("Reply with the single word: ONE")
b = llm_run("Reply with the single word: TWO")
return {"a": a, "b": b}
"""


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------


async def _create_task_record(
    session: AsyncSession,
    tenant_id: str,
    cy_name: str,
    script: str,
) -> UUID:
    """Create a Component + Task and return the component_id (= TaskRun.task_id FK)."""
    component_id = uuid4()
    task_id = uuid4()

    component = Component(
        id=component_id,
        tenant_id=tenant_id,
        name=f"LLM Cost Test — {cy_name}",
        description="Created for LLM cost capture tests",
        categories=["test"],
        status="enabled",
        kind="task",
        cy_name=cy_name,
    )
    session.add(component)
    await session.flush()

    task = Task(
        id=task_id,
        component_id=component_id,
        function="processing",
        scope="processing",
        script=script,
    )
    session.add(task)
    await session.commit()
    return component_id


async def _create_task_run(
    session: AsyncSession,
    tenant_id: str,
    task_id: UUID,
    script: str | None = None,
    input_data: dict | None = None,
) -> UUID:
    """Create a TaskRun record and return its id."""
    task_run_id = uuid4()
    task_run = TaskRun(
        id=task_run_id,
        task_id=task_id,
        tenant_id=tenant_id,
        cy_script=script,  # ad-hoc if task_id not resolving
        status="running",
        input_type="inline",
        input_location=json.dumps(input_data or {}),
        execution_context={},
        created_at=datetime.now(UTC),
    )
    session.add(task_run)
    await session.commit()
    return task_run_id


# ---------------------------------------------------------------------------
# Workflow helpers (same pattern as test_workflow_with_nested_tasks.py)
# ---------------------------------------------------------------------------


async def _get_passthrough_template(http_client, tenant_id: str) -> str:
    data = {
        "name": f"llm-cost-pt-{uuid4().hex[:6]}",
        "description": "Pass through",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "code": "return inp",
        "language": "python",
        "type": "static",
    }
    r = await http_client.post(f"/v1/{tenant_id}/workflows/node-templates", json=data)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def _get_merge_template_id(http_client, tenant_id: str) -> str:
    r = await http_client.get(f"/v1/{tenant_id}/workflows/node-templates")
    assert r.status_code == 200
    merge = next((t for t in r.json()["data"] if t["name"] == "system_merge"), None)
    assert merge is not None, "system_merge template not found"
    return merge["id"]


async def _create_workflow(
    http_client,
    tenant_id: str,
    name: str,
    nodes: list,
    edges: list,
) -> UUID:
    data = {
        "name": f"{name} {uuid4().hex[:6]}",
        "description": name,
        "is_dynamic": False,
        "created_by": str(SYSTEM_USER_ID),
        "io_schema": {"input": {"type": "object"}, "output": {"type": "object"}},
        "nodes": nodes,
        "edges": edges,
    }
    r = await http_client.post(f"/v1/{tenant_id}/workflows", json=data)
    assert r.status_code == 201, f"Failed to create workflow: {r.text}"
    return UUID(r.json()["data"]["id"])


async def _start_run(
    http_client, tenant_id: str, workflow_id: UUID, input_data: dict
) -> UUID:
    r = await http_client.post(
        f"/v1/{tenant_id}/workflows/{workflow_id}/run",
        json={"input_data": input_data},
    )
    assert r.status_code == 202, f"Failed to start run: {r.text}"
    return UUID(r.json()["data"]["workflow_run_id"])


async def _run_and_complete(session: AsyncSession, run_id: UUID) -> None:
    executor = WorkflowExecutor(session)
    await executor.monitor_execution(run_id)
    await session.commit()
    session.expire_all()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def workflow_client(integration_test_session: AsyncSession):
    async def _override():
        yield integration_test_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, integration_test_session
    app.dependency_overrides.clear()


# ===========================================================================
# Test class 1 — Task-level token / cost capture
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskLLMCostCapture:
    """
    Verifies that a single task run using llm_run() captures tokens and cost.

    Exercises:
      • TaskExecutionResult.llm_usage is populated (stubs are replaced)
      • TaskRun.execution_context["_llm_usage"] is persisted to DB
      • GET /task-runs/{id} returns llm_usage in the response JSON
    """

    async def test_execute_single_task_captures_tokens(
        self, integration_test_session: AsyncSession
    ):
        """
        execute_single_task() returns a TaskExecutionResult whose llm_usage
        has positive input_tokens and output_tokens after a real llm_run() call.
        """
        tenant_id = f"llm-cost-task-{uuid4().hex[:8]}"
        task_id = await _create_task_record(
            integration_test_session, tenant_id, f"ping_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        task_run_id = await _create_task_run(
            integration_test_session, tenant_id, task_id
        )

        service = TaskExecutionService()
        result = await service.execute_single_task(task_run_id, tenant_id)

        assert result.llm_usage is not None, (
            "llm_usage must not be None after a task that calls llm_run(). "
            "Check _extract_and_accumulate_usage() stub is implemented."
        )
        assert result.llm_usage.input_tokens > 0, (
            f"input_tokens={result.llm_usage.input_tokens} — expected > 0 from a real LLM call"
        )
        assert result.llm_usage.output_tokens > 0, (
            f"output_tokens={result.llm_usage.output_tokens} — expected > 0"
        )
        assert result.llm_usage.total_tokens == (
            result.llm_usage.input_tokens + result.llm_usage.output_tokens
        ), "total_tokens must equal input + output"

    async def test_llm_usage_persisted_to_execution_context(
        self, integration_test_session: AsyncSession
    ):
        """
        After execute_and_persist(), the TaskRun row in the DB has
        execution_context['_llm_usage'] with non-zero token counts.
        """
        tenant_id = f"llm-cost-persist-{uuid4().hex[:8]}"
        task_id = await _create_task_record(
            integration_test_session,
            tenant_id,
            f"persist_{uuid4().hex[:6]}",
            _LLM_SCRIPT,
        )
        task_run_id = await _create_task_run(
            integration_test_session, tenant_id, task_id
        )

        service = TaskExecutionService()
        await service.execute_and_persist(task_run_id, tenant_id)

        # Reload the TaskRun from the DB and inspect execution_context
        await integration_test_session.commit()
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        row = (await integration_test_session.execute(stmt)).scalar_one_or_none()
        assert row is not None

        ctx = row.execution_context or {}
        usage = ctx.get("_llm_usage")
        assert usage is not None, (
            "execution_context['_llm_usage'] must be set after execute_and_persist(). "
            "Check TaskRunService.update_status() llm_usage branch."
        )
        assert isinstance(usage["input_tokens"], int)
        assert usage["input_tokens"] > 0
        assert isinstance(usage["output_tokens"], int)
        assert usage["output_tokens"] > 0
        assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]

    async def test_task_run_api_response_includes_llm_usage(self, workflow_client):
        """
        GET /v1/{tenant}/task-runs/{trid} returns a JSON body where
        llm_usage.input_tokens and output_tokens are positive integers.
        """
        http_client, session = workflow_client
        tenant_id = f"llm-cost-api-{uuid4().hex[:8]}"

        task_id = await _create_task_record(
            session, tenant_id, f"api_test_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        task_run_id = await _create_task_run(session, tenant_id, task_id)

        # Execute and persist so execution_context is written
        service = TaskExecutionService()
        await service.execute_and_persist(task_run_id, tenant_id)
        await session.commit()

        r = await http_client.get(f"/v1/{tenant_id}/task-runs/{task_run_id}")
        assert r.status_code == 200, r.text

        body = r.json()["data"]
        assert "llm_usage" in body, (
            f"llm_usage key missing from response: {list(body.keys())}"
        )
        usage = body["llm_usage"]
        assert usage is not None, (
            "llm_usage must not be null for a task that called llm_run()"
        )
        assert usage["input_tokens"] > 0, f"input_tokens={usage['input_tokens']}"
        assert usage["output_tokens"] > 0, f"output_tokens={usage['output_tokens']}"
        assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
        # cost_usd may be None if model isn't in pricing table yet (stubs)
        # — that's acceptable; we just verify the field is present
        assert "cost_usd" in usage

    async def test_multiple_llm_calls_accumulate_tokens(
        self, integration_test_session: AsyncSession
    ):
        """
        A task that calls llm_run() twice must accumulate both calls into
        a single llm_usage with total_tokens > tokens from a single call.
        """
        tenant_id = f"llm-cost-multi-{uuid4().hex[:8]}"

        # Run a single-call task to get a baseline total_tokens
        single_id = await _create_task_record(
            integration_test_session,
            tenant_id,
            f"single_{uuid4().hex[:6]}",
            _LLM_SCRIPT,
        )
        tr_single = await _create_task_run(
            integration_test_session, tenant_id, single_id
        )
        service = TaskExecutionService()
        result_single = await service.execute_single_task(tr_single, tenant_id)

        # Run a two-call task
        multi_id = await _create_task_record(
            integration_test_session,
            tenant_id,
            f"multi_{uuid4().hex[:6]}",
            _LLM_SCRIPT_MULTI,
        )
        tr_multi = await _create_task_run(integration_test_session, tenant_id, multi_id)
        result_multi = await service.execute_single_task(tr_multi, tenant_id)

        assert result_single.llm_usage is not None, "Single-call usage must not be None"
        assert result_multi.llm_usage is not None, "Multi-call usage must not be None"

        assert (
            result_multi.llm_usage.total_tokens > result_single.llm_usage.total_tokens
        ), (
            f"Two llm_run() calls must produce more tokens than one. "
            f"single={result_single.llm_usage.total_tokens}, "
            f"multi={result_multi.llm_usage.total_tokens}"
        )


# ===========================================================================
# Test class 2 — Workflow-level token / cost capture
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowLLMCostCapture:
    """
    Verifies that workflow runs capture LLM usage per-node and in aggregate.

    Topology tested:
      identity → [llm_task_node] → (terminal)

    Exercises:
      • WorkflowNodeInstance output envelope carries context.llm_usage
      • GET /workflow-runs/{id}/graph → nodes[*].llm_usage is populated
      • GET /workflow-runs/{id} → llm_usage is the aggregate across task nodes
    """

    async def test_workflow_node_captures_llm_usage(self, workflow_client):
        """
        A single task node in a workflow that calls llm_run() must produce
        a WorkflowNodeInstance whose output_location JSON contains
        context.llm_usage with positive token counts.
        """
        http_client, session = workflow_client
        tenant_id = f"llm-wf-node-{uuid4().hex[:8]}"

        task_id = await _create_task_record(
            session, tenant_id, f"wf_llm_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        passthrough_id = await _get_passthrough_template(http_client, tenant_id)

        workflow_id = await _create_workflow(
            http_client,
            tenant_id,
            name="LLM cost capture single node",
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
                    "node_id": "n-llm",
                    "kind": "task",
                    "name": "LLM Task",
                    "task_id": str(task_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {"edge_id": "e1", "from_node_id": "n-identity", "to_node_id": "n-llm"},
            ],
        )

        run_id = await _start_run(http_client, tenant_id, workflow_id, {})
        await _run_and_complete(session, run_id)

        # Verify via GET /graph endpoint
        r = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}/graph")
        assert r.status_code == 200, r.text
        body = r.json()["data"]

        node_map = {n["node_id"]: n for n in body["nodes"]}
        assert "n-llm" in node_map, f"n-llm node missing from graph: {list(node_map)}"

        llm_node = node_map["n-llm"]
        assert llm_node["status"] == "completed", (
            f"LLM task node status={llm_node['status']!r}, error={llm_node.get('error_message')}"
        )

        usage = llm_node.get("llm_usage")
        assert usage is not None, (
            "llm_usage must be populated in the graph node response for a task node "
            "that called llm_run(). Check workflow_execution.py envelope construction."
        )
        assert usage["input_tokens"] > 0, f"input_tokens={usage['input_tokens']}"
        assert usage["output_tokens"] > 0, f"output_tokens={usage['output_tokens']}"
        assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]

    async def test_workflow_run_response_aggregates_llm_usage(self, workflow_client):
        """
        GET /workflow-runs/{id} for a completed workflow with one LLM task node
        returns llm_usage with the aggregate token counts > 0.
        """
        http_client, session = workflow_client
        tenant_id = f"llm-wf-agg-{uuid4().hex[:8]}"

        task_id = await _create_task_record(
            session, tenant_id, f"wf_agg_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        passthrough_id = await _get_passthrough_template(http_client, tenant_id)

        workflow_id = await _create_workflow(
            http_client,
            tenant_id,
            name="LLM cost aggregate workflow run",
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
                    "node_id": "n-llm",
                    "kind": "task",
                    "name": "LLM Task",
                    "task_id": str(task_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {"edge_id": "e1", "from_node_id": "n-identity", "to_node_id": "n-llm"},
            ],
        )

        run_id = await _start_run(http_client, tenant_id, workflow_id, {})
        await _run_and_complete(session, run_id)

        r = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}")
        assert r.status_code == 200, r.text
        body = r.json()["data"]

        assert body["status"] == "completed", (
            f"Workflow run status={body['status']!r}, error={body.get('error_message')}"
        )
        usage = body.get("llm_usage")
        assert usage is not None, (
            "llm_usage must be present in the WorkflowRunResponse when the workflow "
            "contains task nodes that called llm_run()."
        )
        assert usage["input_tokens"] > 0, f"input_tokens={usage['input_tokens']}"
        assert usage["output_tokens"] > 0, f"output_tokens={usage['output_tokens']}"

    async def test_two_parallel_llm_nodes_aggregate_tokens(self, workflow_client):
        """
        Diamond topology: identity → [llm_a, llm_b] → merge.

        The aggregate llm_usage at the workflow-run level must be the sum
        of both branches' token counts, i.e. >= each individual branch.
        """
        http_client, session = workflow_client
        tenant_id = f"llm-wf-diamond-{uuid4().hex[:8]}"

        task_a_id = await _create_task_record(
            session, tenant_id, f"llm_a_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        task_b_id = await _create_task_record(
            session, tenant_id, f"llm_b_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        passthrough_id = await _get_passthrough_template(http_client, tenant_id)
        merge_id = await _get_merge_template_id(http_client, tenant_id)

        workflow_id = await _create_workflow(
            http_client,
            tenant_id,
            name="LLM cost diamond",
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
                    "node_id": "n-llm-a",
                    "kind": "task",
                    "name": "LLM Branch A",
                    "task_id": str(task_a_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-llm-b",
                    "kind": "task",
                    "name": "LLM Branch B",
                    "task_id": str(task_b_id),
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
                    "edge_id": "e-id-a",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-llm-a",
                },
                {
                    "edge_id": "e-id-b",
                    "from_node_id": "n-identity",
                    "to_node_id": "n-llm-b",
                },
                {
                    "edge_id": "e-a-m",
                    "from_node_id": "n-llm-a",
                    "to_node_id": "n-merge",
                },
                {
                    "edge_id": "e-b-m",
                    "from_node_id": "n-llm-b",
                    "to_node_id": "n-merge",
                },
            ],
        )

        run_id = await _start_run(http_client, tenant_id, workflow_id, {})
        await _run_and_complete(session, run_id)

        # Collect per-node usage from graph
        r_graph = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}/graph")
        assert r_graph.status_code == 200, r_graph.text
        nodes = {n["node_id"]: n for n in r_graph.json()["data"]["nodes"]}

        usage_a = nodes["n-llm-a"]["llm_usage"]
        usage_b = nodes["n-llm-b"]["llm_usage"]
        assert usage_a is not None, "Branch A must have llm_usage"
        assert usage_b is not None, "Branch B must have llm_usage"

        # Fetch aggregate from workflow-run response
        r_run = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}")
        assert r_run.status_code == 200, r_run.text
        agg = r_run.json()["data"].get("llm_usage")
        assert agg is not None, "Aggregate llm_usage must be present"

        expected_total = usage_a["total_tokens"] + usage_b["total_tokens"]
        assert agg["total_tokens"] == expected_total, (
            f"Aggregate total_tokens={agg['total_tokens']} != "
            f"sum of branches ({usage_a['total_tokens']} + {usage_b['total_tokens']} = {expected_total}). "
            f"Check WorkflowRunResponse aggregate computation in the router."
        )

    async def test_transformation_nodes_have_no_llm_usage(self, workflow_client):
        """
        Transformation (identity/merge) nodes must have llm_usage=null in the
        graph response — they don't run Cy scripts with llm_run().
        """
        http_client, session = workflow_client
        tenant_id = f"llm-wf-transform-{uuid4().hex[:8]}"

        task_id = await _create_task_record(
            session, tenant_id, f"wf_tx_{uuid4().hex[:6]}", _LLM_SCRIPT
        )
        passthrough_id = await _get_passthrough_template(http_client, tenant_id)

        workflow_id = await _create_workflow(
            http_client,
            tenant_id,
            name="Transformation node has no llm_usage",
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
                    "node_id": "n-llm",
                    "kind": "task",
                    "name": "LLM Task",
                    "task_id": str(task_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            edges=[
                {"edge_id": "e1", "from_node_id": "n-identity", "to_node_id": "n-llm"},
            ],
        )

        run_id = await _start_run(http_client, tenant_id, workflow_id, {})
        await _run_and_complete(session, run_id)

        r = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}/graph")
        assert r.status_code == 200, r.text
        nodes = {n["node_id"]: n for n in r.json()["data"]["nodes"]}

        # identity/transformation node must have llm_usage=null
        identity_node = nodes.get("n-identity")
        assert identity_node is not None
        assert identity_node.get("llm_usage") is None, (
            f"Transformation node must have llm_usage=null, got: {identity_node.get('llm_usage')}"
        )

        # task node must have llm_usage populated
        llm_node = nodes.get("n-llm")
        assert llm_node is not None
        assert llm_node.get("llm_usage") is not None, (
            "Task node that called llm_run() must have llm_usage populated"
        )
