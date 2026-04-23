"""
Integration tests formally asserting concurrent fan-out execution.

Design contract:
  When multiple workflow nodes are simultaneously ready (all predecessors
  complete), the WorkflowExecutor must launch them concurrently via
  asyncio.gather(), not sequentially. Each task node runs with its own
  isolated session (session isolation contract preserved).

Topology used in tests:

    identity (passthrough transformation)
         |
    ┌────┴────┐
    B         C      ← both ready simultaneously after identity completes
    └────┬────┘
       merge (system_merge)

Timing strategy:
  The concurrent execution tests patch TaskExecutionService.execute_single_task
  to inject asyncio.sleep(BRANCH_SLEEP_S), measuring that both branches are
  launched simultaneously by asyncio.gather() rather than sequentially.

  - Sequential: elapsed ~ 2 x BRANCH_SLEEP_S
  - Concurrent: elapsed ≈ BRANCH_SLEEP_S

Correctness tests use real (unpatched) task execution with simple Cy scripts.
"""

import asyncio
import json
import time
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus
from analysi.services.workflow_execution import WorkflowExecutor
from tests.utils.cy_output import parse_cy_output

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

# Duration each branch "sleeps" (injected via patch). Keep short for CI.
BRANCH_SLEEP_S = 1.0

# Total must be < this for concurrent execution to be confirmed
CONCURRENT_THRESHOLD_S = BRANCH_SLEEP_S * 1.6

TENANT_ID = "ithaca-phase3-parallel-tenant"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_task(
    session: AsyncSession,
    cy_name: str,
    script: str,
) -> str:
    """Create a Task record and return its component_id (UUID str)."""
    repo = TaskRepository(session)
    task = await repo.create(
        {
            "tenant_id": TENANT_ID,
            "name": f"Fan-Out Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()
    return str(task.component_id)


async def _get_passthrough_template(http_client, tenant_id: str) -> str:
    """Create a simple passthrough transformation template."""
    template_data = {
        "name": f"p3-passthrough-{uuid4().hex[:6]}",
        "description": "Pass through input unchanged",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "code": "return inp",
        "language": "python",
        "type": "static",
    }
    response = await http_client.post(
        f"/v1/{tenant_id}/workflows/node-templates", json=template_data
    )
    assert response.status_code == 201, (
        f"Failed to create passthrough template: {response.text}"
    )
    return response.json()["data"]["id"]


async def _get_merge_template_id(http_client, tenant_id: str) -> str:
    """Get the system_merge template ID (seeded by migrations)."""
    response = await http_client.get(f"/v1/{tenant_id}/workflows/node-templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    merge_template = next((t for t in templates if t["name"] == "system_merge"), None)
    assert merge_template is not None, (
        "system_merge template not found. Check migration/seeding."
    )
    return merge_template["id"]


async def _build_fan_out_workflow(
    session: AsyncSession,
    http_client,
    branch_b_task_id: str,
    branch_c_task_id: str,
    passthrough_template_id: str,
    merge_template_id: str,
    workflow_suffix: str = "",
) -> UUID:
    """Create workflow: identity -> [B, C] -> merge. Returns workflow_id UUID."""
    nodes = [
        {
            "node_id": "n-identity",
            "kind": "transformation",
            "name": "Identity",
            "is_start_node": True,
            "node_template_id": passthrough_template_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
        {
            "node_id": "n-branch-b",
            "kind": "task",
            "name": "Branch B",
            "task_id": branch_b_task_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
        {
            "node_id": "n-branch-c",
            "kind": "task",
            "name": "Branch C",
            "task_id": branch_c_task_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
        {
            "node_id": "n-merge",
            "kind": "transformation",
            "name": "Merge",
            "node_template_id": merge_template_id,
            "schemas": {
                "input": {"type": "array"},
                "output_result": {"type": "object"},
            },
        },
    ]
    edges = [
        {
            "edge_id": "e-identity-b",
            "from_node_id": "n-identity",
            "to_node_id": "n-branch-b",
        },
        {
            "edge_id": "e-identity-c",
            "from_node_id": "n-identity",
            "to_node_id": "n-branch-c",
        },
        {"edge_id": "e-b-merge", "from_node_id": "n-branch-b", "to_node_id": "n-merge"},
        {"edge_id": "e-c-merge", "from_node_id": "n-branch-c", "to_node_id": "n-merge"},
    ]
    workflow_data = {
        "name": f"P3 Fan-Out{workflow_suffix} {uuid4().hex[:6]}",
        "description": "concurrent fan-out test",
        "is_dynamic": False,
        "created_by": str(SYSTEM_USER_ID),
        "io_schema": {"input": {"type": "object"}, "output": {"type": "object"}},
        "nodes": nodes,
        "edges": edges,
    }
    response = await http_client.post(f"/v1/{TENANT_ID}/workflows", json=workflow_data)
    assert response.status_code == 201, f"Failed to create workflow: {response.text}"
    await session.commit()
    return UUID(response.json()["data"]["id"])


async def _start_workflow_run(
    session, http_client, workflow_id: UUID, input_data: dict
) -> UUID:
    response = await http_client.post(
        f"/v1/{TENANT_ID}/workflows/{workflow_id}/run",
        json={"input_data": input_data},
    )
    assert response.status_code == 202, f"Failed to start workflow: {response.text}"
    await session.commit()
    return UUID(response.json()["data"]["workflow_run_id"])


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def workflow_client(integration_test_session):
    """HTTP client wired to the integration test DB session."""
    from httpx import ASGITransport, AsyncClient

    from analysi.db.session import get_db
    from analysi.main import app

    async def override_get_db():
        yield integration_test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, integration_test_session
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Timing tests (patched execute_single_task injects asyncio.sleep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestFanOutConcurrentExecution:
    """
    Timing contract: parallel-ready nodes execute concurrently.

    THE CONTRACT:
      Two branches each "sleep" BRANCH_SLEEP_S (injected via patch).
      Sequential execution: elapsed ~ 2 * BRANCH_SLEEP_S
      Concurrent execution: elapsed ~ BRANCH_SLEEP_S

      The test passes only when asyncio.gather() is used for ready nodes.
    """

    async def test_fan_out_nodes_execute_concurrently_not_sequentially(
        self, workflow_client
    ):
        """
        THE TIMING TEST.

        FAILS with sequential for-loop in monitor_execution().
        PASSES only when asyncio.gather() runs ready nodes concurrently.
        """
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"p3_timing_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch"] = "B"\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"p3_timing_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch"] = "C"\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": 10})

        # Inject sleep into execute_single_task — simulates slow real tasks
        async def slow_execute(task_run_id, tenant_id):
            await asyncio.sleep(BRANCH_SLEEP_S)
            return TaskExecutionResult(
                status=TaskExecutionStatus.COMPLETED,
                output_data={"branch": "mocked", "value": 1},
                error_message=None,
                execution_time_ms=int(BRANCH_SLEEP_S * 1000),
                task_run_id=task_run_id,
            )

        executor = WorkflowExecutor(session)
        with patch(
            "analysi.services.task_execution.TaskExecutionService.execute_single_task",
            side_effect=slow_execute,
        ):
            t0 = time.monotonic()
            await executor.monitor_execution(run_id)
            elapsed = time.monotonic() - t0

        await session.commit()

        assert elapsed < CONCURRENT_THRESHOLD_S, (
            f"Fan-out took {elapsed:.2f}s — expected < {CONCURRENT_THRESHOLD_S:.2f}s. "
            f"Sequential would take ~{2 * BRANCH_SLEEP_S:.1f}s; concurrent ~{BRANCH_SLEEP_S:.1f}s. "
            f"Fix: use asyncio.gather() for ready nodes in monitor_execution()."
        )

    async def test_parallel_node_start_times_overlap(self, workflow_client):
        """
        THE OVERLAP TEST: B and C must START within 300ms of each other.

        Records the timestamp when execute_single_task is called for each
        branch. The gap between those two timestamps must be < 300ms.
        """
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"p3_overlap_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch"] = "B"\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"p3_overlap_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch"] = "C"\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " overlap",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {})

        call_start_times = []

        async def recording_execute(task_run_id, tenant_id):
            call_start_times.append(time.monotonic())
            await asyncio.sleep(BRANCH_SLEEP_S)
            return TaskExecutionResult(
                status=TaskExecutionStatus.COMPLETED,
                output_data={"branch": "mocked"},
                error_message=None,
                execution_time_ms=int(BRANCH_SLEEP_S * 1000),
                task_run_id=task_run_id,
            )

        executor = WorkflowExecutor(session)
        with patch(
            "analysi.services.task_execution.TaskExecutionService.execute_single_task",
            side_effect=recording_execute,
        ):
            await executor.monitor_execution(run_id)

        await session.commit()

        assert len(call_start_times) >= 2, (
            f"Expected execute_single_task called at least twice (once per branch), "
            f"got {len(call_start_times)} calls."
        )

        call_start_times.sort()
        gap = call_start_times[1] - call_start_times[0]
        assert gap < 0.3, (
            f"Branch start times differ by {gap:.3f}s — expected < 0.3s. "
            f"Branches did NOT start simultaneously. "
            f"Fix: use asyncio.gather() in monitor_execution()."
        )


# ---------------------------------------------------------------------------
# Correctness tests (real execution, no patching)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestFanOutCorrectness:
    """
    Correctness: concurrent fan-out must produce correct results.

    Uses real (unpatched) task execution with fast Cy scripts.
    Verifies outputs are correct and workflow completes successfully.
    """

    async def test_both_branches_complete_with_status_completed(self, workflow_client):
        """Both branch node instances must reach 'completed' status."""
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"p3_ok_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch_b_done"] = True\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"p3_ok_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch_c_done"] = True\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " correctness",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": 5})

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(run_id)
        await session.commit()

        from sqlalchemy import select

        from analysi.models.workflow_execution import WorkflowNodeInstance

        session.expire_all()
        stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id.in_(["n-branch-b", "n-branch-c"]),
        )
        result = await session.execute(stmt)
        branch_instances = result.scalars().all()

        assert len(branch_instances) == 2, (
            f"Expected 2 branch instances, got {len(branch_instances)}"
        )
        for inst in branch_instances:
            assert inst.status == "completed", (
                f"Branch {inst.node_id} has status={inst.status!r}, expected 'completed'. "
                f"Error: {inst.error_message}"
            )

    async def test_workflow_run_status_is_completed_not_failed(self, workflow_client):
        """Successful fan-out must mark workflow_run as 'completed', not 'failed'."""
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"p3_st_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch_b_ok"] = True\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"p3_st_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["branch_c_ok"] = True\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " status",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {})

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(run_id)
        await session.commit()

        from analysi.repositories.workflow_execution import WorkflowRunRepository

        run_repo = WorkflowRunRepository(session)
        session.expire_all()
        workflow_run = await run_repo.get_workflow_run(TENANT_ID, run_id)

        assert workflow_run is not None
        assert workflow_run.status == "completed", (
            f"Expected status='completed', got {workflow_run.status!r}. "
            f"Error: {workflow_run.error_message}"
        )

    async def test_concurrent_branches_produce_isolated_outputs(self, workflow_client):
        """
        Each branch produces its own correct output — no data mixing.
        B outputs value = x*2; C outputs value = x*3.
        Session isolation must hold under concurrent execution.
        """
        http_client, session = workflow_client
        x = 7

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"p3_iso_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["b_value"] = input["x"] * 2\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"p3_iso_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["c_value"] = input["x"] * 3\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " isolation",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": x})

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(run_id)
        await session.commit()

        from sqlalchemy import select

        from analysi.models.workflow_execution import WorkflowNodeInstance

        session.expire_all()
        stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id.in_(["n-branch-b", "n-branch-c"]),
        )
        result = await session.execute(stmt)
        branch_instances = {inst.node_id: inst for inst in result.scalars().all()}

        assert "n-branch-b" in branch_instances, "Branch B node instance missing"
        assert "n-branch-c" in branch_instances, "Branch C node instance missing"

        def extract_result(inst):
            if inst.output_location:
                raw = json.loads(inst.output_location)
                return parse_cy_output(raw.get("result", raw))
            return None

        b_output = extract_result(branch_instances["n-branch-b"])
        c_output = extract_result(branch_instances["n-branch-c"])

        assert b_output is not None, "Branch B produced no output"
        assert c_output is not None, "Branch C produced no output"

        assert b_output.get("b_value") == x * 2, (
            f"Branch B: b_value={b_output.get('b_value')!r}, expected {x * 2}. "
            f"Session isolation may be broken under concurrent execution."
        )
        assert c_output.get("c_value") == x * 3, (
            f"Branch C: c_value={c_output.get('c_value')!r}, expected {x * 3}. "
            f"Session isolation may be broken under concurrent execution."
        )


# ---------------------------------------------------------------------------
# PAUSED status tests (enum-level, no DB required)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPausedStatus:
    """
    Contract: TaskExecutionStatus.PAUSED exists as a reserved HITL hook.

    Design decision (02/17/2026): HITL pauses are modeled as workflow node
    boundaries. PAUSED is the hook point — a task signals it needs human input
    without the executor treating it as FAILED.
    """

    def test_paused_status_exists_in_enum(self):
        """TaskExecutionStatus.PAUSED must be a valid StrEnum member."""
        assert hasattr(TaskExecutionStatus, "PAUSED"), (
            "TaskExecutionStatus.PAUSED does not exist. "
            "Add PAUSED = 'paused' to the StrEnum — it is the HITL hook."
        )
        assert TaskExecutionStatus.PAUSED == "paused"
        assert isinstance(TaskExecutionStatus.PAUSED, str)

    def test_paused_is_distinct_from_completed_and_failed(self):
        """PAUSED must be a third distinct status value, not an alias."""
        assert TaskExecutionStatus.PAUSED != TaskExecutionStatus.COMPLETED
        assert TaskExecutionStatus.PAUSED != TaskExecutionStatus.FAILED
        assert TaskExecutionStatus.PAUSED != "completed"
        assert TaskExecutionStatus.PAUSED != "failed"
