"""
Robustness tests for concurrent execution.

These tests target specific race conditions and failure modes identified
during post-implementation review of the asyncio.gather() concurrent
fan-out execution.

Hypothesis 1: Duplicate merge node instances when concurrent branches
              both try to create the same successor node.
Hypothesis 2: Workflow hangs if _create_successor_instances fails after
              a node has already been marked completed.
Hypothesis 3: Main session stale-write after gather exception — the
              error handler uses the main session while isolated sessions
              have already committed changes.
"""

import asyncio
import contextlib
import time
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow_execution import WorkflowNodeInstance, WorkflowRun
from analysi.repositories.task import TaskRepository
from analysi.services.workflow_execution import WorkflowExecutor

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

TENANT_ID = "ithaca-robustness-test"


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_parallel_node_execution.py)
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
            "name": f"Robustness Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()
    return str(task.component_id)


async def _get_passthrough_template(http_client, tenant_id: str) -> str:
    template_data = {
        "name": f"robust-passthrough-{uuid4().hex[:6]}",
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
    assert response.status_code == 201, f"Failed to create template: {response.text}"
    return response.json()["data"]["id"]


async def _get_merge_template_id(http_client, tenant_id: str) -> str:
    response = await http_client.get(f"/v1/{tenant_id}/workflows/node-templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    merge_template = next((t for t in templates if t["name"] == "system_merge"), None)
    assert merge_template is not None, "system_merge template not found"
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
        "name": f"Robust Fan-Out{workflow_suffix} {uuid4().hex[:6]}",
        "description": "Ithaca robustness test — concurrent fan-out/fan-in",
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


# ===========================================================================
# Hypothesis 1: Duplicate merge node from concurrent successor creation
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestDuplicateMergeNodeRace:
    """
    H1: When two concurrent branches complete simultaneously, both call
    _create_successor_instances for the merge node. Without protection,
    both sessions see that no merge node exists yet, and both create one.

    This must NOT happen: exactly ONE merge node instance must exist.
    """

    async def test_no_duplicate_merge_node_instances_after_concurrent_fan_in(
        self, workflow_client
    ):
        """
        Both branches complete concurrently. Exactly ONE merge node instance
        must exist — duplicates would indicate a TOCTOU race in
        _create_successor_instances.

        Strategy: Execute workflow to identity node completion, manually
        create+complete branch node instances, then call
        _create_successor_instances from TWO concurrent sessions — each
        pretending to be a different branch. No merge node exists yet, so
        both will try to create one.
        """
        http_client, session = workflow_client
        from sqlalchemy.orm import selectinload

        from analysi.db.session import AsyncSessionLocal
        from analysi.models.workflow import Workflow

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"h1_race_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["b_done"] = True\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"h1_race_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["c_done"] = True\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " h1-race",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": 1})

        # Execute the workflow through identity -> B,C execution, BUT
        # stop before creating successors for B and C.
        # We do this by patching _create_successor_instances to skip for branch nodes.
        original_create_successors = WorkflowExecutor._create_successor_instances
        skipped_branch_calls = []

        async def skip_branch_successors(self_inner, wf_run_id, completed_node, wf):
            if completed_node.node_id in ("n-branch-b", "n-branch-c"):
                skipped_branch_calls.append(completed_node.node_id)
                return None  # Don't create successors — we'll do this manually
            return await original_create_successors(
                self_inner, wf_run_id, completed_node, wf
            )

        executor = WorkflowExecutor(session)
        with patch.object(
            WorkflowExecutor,
            "_create_successor_instances",
            skip_branch_successors,
        ):
            await executor.monitor_execution(run_id)
        await session.commit()

        # Both branches should have been skipped
        assert "n-branch-b" in skipped_branch_calls
        assert "n-branch-c" in skipped_branch_calls

        # Verify: NO merge node exists yet
        session.expire_all()
        merge_check = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id == "n-merge",
        )
        check_result = await session.execute(merge_check)
        assert check_result.scalar_one_or_none() is None, (
            "Merge node should NOT exist yet — we skipped successor creation for branches"
        )

        # Get branch B and C instance IDs for the race test
        branch_b_stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id == "n-branch-b",
        )
        branch_c_stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id == "n-branch-c",
        )
        branch_b_result = await session.execute(branch_b_stmt)
        branch_b_instance = branch_b_result.scalar_one()
        branch_c_result = await session.execute(branch_c_stmt)
        branch_c_instance = branch_c_result.scalar_one()

        # Now: THE RACE. Call _create_successor_instances from TWO fresh
        # sessions concurrently, one for each branch.  Neither has created
        # the merge node yet, so both will try.
        barrier = asyncio.Barrier(2)

        async def try_create_successor(branch_instance_id, barrier_obj):
            """Call _create_successor_instances from a fresh session."""
            async with AsyncSessionLocal() as s:
                executor_inner = WorkflowExecutor(s)

                # Reload branch node instance from this session
                stmt_inner = select(WorkflowNodeInstance).where(
                    WorkflowNodeInstance.id == branch_instance_id
                )
                res_inner = await s.execute(stmt_inner)
                node_inner = res_inner.scalar_one()

                # Reload workflow
                wf_stmt = (
                    select(Workflow)
                    .options(selectinload(Workflow.edges), selectinload(Workflow.nodes))
                    .where(Workflow.id == workflow_id)
                )
                wf_res = await s.execute(wf_stmt)
                workflow_inner = wf_res.scalar_one()

                # Wait for the other session to be ready
                await barrier_obj.wait()

                await executor_inner._create_successor_instances(
                    run_id, node_inner, workflow_inner
                )

        results_gathered = await asyncio.gather(
            try_create_successor(branch_b_instance.id, barrier),
            try_create_successor(branch_c_instance.id, barrier),
            return_exceptions=True,
        )

        # Check for exceptions (acceptable if code catches duplicates)
        for r in results_gathered:
            if isinstance(r, Exception):
                print(f"One concurrent _create_successor_instances raised: {r}")

        # Count merge node instances — must be EXACTLY 1
        session.expire_all()
        merge_count_stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == run_id,
            WorkflowNodeInstance.node_id == "n-merge",
        )
        merge_count_result = await session.execute(merge_count_stmt)
        merge_instances = list(merge_count_result.scalars().all())

        assert len(merge_instances) == 1, (
            f"Expected exactly 1 merge node instance, got {len(merge_instances)}. "
            f"TOCTOU race in _create_successor_instances: both branches created "
            f"the merge node because they each saw 'no instance exists yet' in "
            f"their isolated sessions."
        )

    async def test_workflow_completes_successfully_despite_race_window(
        self, workflow_client
    ):
        """
        Even with concurrent fan-in + barrier synchronisation, the workflow
        must reach 'completed' status without errors.
        """
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"h1_ok_b_{uuid4().hex[:8]}",
            script='result = {}\nresult["val_b"] = 10\nreturn result',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"h1_ok_c_{uuid4().hex[:8]}",
            script='result = {}\nresult["val_c"] = 20\nreturn result',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " h1-ok",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": 5})

        barrier = asyncio.Barrier(2)
        original_create_successors = WorkflowExecutor._create_successor_instances

        async def synchronised_create_successors(
            self_inner, workflow_run_id, completed_node, workflow
        ):
            if completed_node.node_id in ("n-branch-b", "n-branch-c"):
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(barrier.wait(), timeout=5.0)
            return await original_create_successors(
                self_inner, workflow_run_id, completed_node, workflow
            )

        executor = WorkflowExecutor(session)
        with patch.object(
            WorkflowExecutor,
            "_create_successor_instances",
            synchronised_create_successors,
        ):
            await executor.monitor_execution(run_id)

        await session.commit()

        # Check workflow completed successfully
        session.expire_all()
        run_stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
        result = await session.execute(run_stmt)
        workflow_run = result.scalar_one()

        assert workflow_run.status == "completed", (
            f"Workflow should be 'completed', got '{workflow_run.status}'. "
            f"Error: {workflow_run.error_message}"
        )


# ===========================================================================
# Hypothesis 2: Workflow hangs when _create_successor_instances fails
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestSuccessorCreationFailure:
    """
    H2: If execute_node_instance succeeds but _create_successor_instances
    fails (e.g., DB error), the node is "completed" but no successors exist.
    The workflow must NOT hang — it should detect the inconsistency and fail
    gracefully rather than loop forever.
    """

    async def test_workflow_fails_when_successor_creation_raises(self, workflow_client):
        """
        Inject an error in _create_successor_instances for the identity node.
        The workflow must eventually fail (not hang indefinitely).
        """
        http_client, session = workflow_client

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        merge_id = await _get_merge_template_id(http_client, TENANT_ID)

        branch_b_id = await _create_task(
            session,
            cy_name=f"h2_hang_b_{uuid4().hex[:8]}",
            script='return {"b": True}',
        )
        branch_c_id = await _create_task(
            session,
            cy_name=f"h2_hang_c_{uuid4().hex[:8]}",
            script='return {"c": True}',
        )

        workflow_id = await _build_fan_out_workflow(
            session,
            http_client,
            branch_b_id,
            branch_c_id,
            passthrough_id,
            merge_id,
            " h2-hang",
        )
        run_id = await _start_workflow_run(session, http_client, workflow_id, {"x": 1})

        call_count = 0

        original_create_successors = WorkflowExecutor._create_successor_instances

        async def failing_create_successors(
            self_inner, workflow_run_id, completed_node, workflow
        ):
            nonlocal call_count
            call_count += 1
            # Fail on the FIRST call (identity node creating B and C)
            if call_count == 1:
                raise RuntimeError("Simulated successor creation failure")
            return await original_create_successors(
                self_inner, workflow_run_id, completed_node, workflow
            )

        executor = WorkflowExecutor(session)
        # Set a tight max_iterations to prevent actual infinite loop in test
        executor.polling_interval = 0.01

        with patch.object(
            WorkflowExecutor,
            "_create_successor_instances",
            failing_create_successors,
        ):
            # This should complete within a reasonable time, not hang
            t0 = time.monotonic()
            await executor.monitor_execution(run_id)
            elapsed = time.monotonic() - t0

        await session.commit()

        # The workflow must not have hung for more than 10 seconds
        assert elapsed < 10.0, (
            f"monitor_execution took {elapsed:.1f}s — suspected hang. "
            f"Workflow should fail gracefully when successor creation fails."
        )

        # Check workflow ended (either failed or completed — not hanging)
        session.expire_all()
        run_stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
        result = await session.execute(run_stmt)
        workflow_run = result.scalar_one()

        assert workflow_run.status in ("failed", "completed"), (
            f"Workflow status is '{workflow_run.status}' — expected 'failed' or 'completed'. "
            f"If 'running', the monitor loop didn't detect the stalled state."
        )
