"""
Integration tests for HITL pause/resume inside a workflow.

Workflow-level HITL: verifies the full pause propagation
chain (Task PAUSED → Node PAUSED → WorkflowRun PAUSED) and the resume path
via continue_after_hitl.

Topology:
    start (passthrough)  →  hitl_task  →  after_hitl (passthrough)

The hitl_task is a real Task record, but execute_single_task is patched to
return PAUSED with a checkpoint (simulating a Cy script that called
ask_question_channel).  send_hitl_question is also patched since no real
Slack workspace is available.

Contract under test:
  1. When a task returns PAUSED, the node instance is marked PAUSED.
  2. monitor_execution detects the paused node and marks the WorkflowRun PAUSED.
  3. A hitl_questions row is created with workflow_run_id and node_instance_id.
  4. continue_after_hitl resumes the workflow: node COMPLETED, successors run,
     workflow reaches COMPLETED.
"""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.constants import WorkflowConstants
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.hitl_question import HITLQuestion
from analysi.models.workflow_execution import WorkflowRun
from analysi.repositories.task import TaskRepository
from analysi.repositories.workflow_execution import WorkflowNodeInstanceRepository
from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus
from analysi.services.workflow_execution import WorkflowExecutor

TENANT_ID = f"hitl-wf-test-{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_task(session: AsyncSession, cy_name: str, script: str) -> str:
    """Create a Task record and return its component_id (UUID str)."""
    repo = TaskRepository(session)
    task = await repo.create(
        {
            "tenant_id": TENANT_ID,
            "name": f"HITL WF Test — {cy_name}",
            "cy_name": cy_name,
            "script": script,
        }
    )
    await session.commit()
    return str(task.component_id)


async def _get_passthrough_template(http_client, tenant_id: str) -> str:
    """Create a simple passthrough transformation template."""
    template_data = {
        "name": f"hitl-passthrough-{uuid4().hex[:6]}",
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


async def _build_hitl_workflow(
    session: AsyncSession,
    http_client,
    hitl_task_id: str,
    after_hitl_task_id: str,
    passthrough_template_id: str,
) -> UUID:
    """Create workflow: start -> hitl_task -> after_hitl. Returns workflow_id."""
    nodes = [
        {
            "node_id": "n-start",
            "kind": "transformation",
            "name": "Start",
            "is_start_node": True,
            "node_template_id": passthrough_template_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
        {
            "node_id": "n-hitl-task",
            "kind": "task",
            "name": "HITL Task",
            "task_id": hitl_task_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
        {
            "node_id": "n-after-hitl",
            "kind": "task",
            "name": "After HITL",
            "task_id": after_hitl_task_id,
            "schemas": {
                "input": {"type": "object"},
                "output_result": {"type": "object"},
            },
        },
    ]
    edges = [
        {
            "edge_id": "e-start-hitl",
            "from_node_id": "n-start",
            "to_node_id": "n-hitl-task",
        },
        {
            "edge_id": "e-hitl-after",
            "from_node_id": "n-hitl-task",
            "to_node_id": "n-after-hitl",
        },
    ]
    workflow_data = {
        "name": f"HITL Workflow Test {uuid4().hex[:6]}",
        "description": "Tests HITL pause propagation in workflows",
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
    session: AsyncSession, workflow_id: UUID, input_data: dict
) -> UUID:
    """Create a WorkflowRun directly (bypasses REST API / Valkey dependency)."""
    executor = WorkflowExecutor(session)
    run_id = await executor.create_workflow_run(TENANT_ID, workflow_id, input_data)
    await session.commit()
    return run_id


def _make_paused_result(task_run_id: UUID) -> TaskExecutionResult:
    """Build a TaskExecutionResult that simulates an HITL pause."""
    return TaskExecutionResult(
        status=TaskExecutionStatus.PAUSED,
        output_data={
            "_hitl_checkpoint": {
                "node_results": {"n1": {"output": "enrichment"}},
                "pending_node_id": "n2",
                "pending_tool_name": "app::slack::ask_question_channel",
                "pending_tool_args": {
                    "question": "Block the suspicious IP?",
                    "destination": "C-security-alerts",
                    "responses": "Block,Ignore,Escalate",
                },
                "pending_tool_result": None,
                "variables": {"threat_score": 8.5},
                "plan_version": "2.0",
            }
        },
        error_message=None,
        execution_time_ms=100,
        task_run_id=task_run_id,
    )


def _make_completed_result(task_run_id: UUID) -> TaskExecutionResult:
    """Build a TaskExecutionResult for a successfully completed task."""
    return TaskExecutionResult(
        status=TaskExecutionStatus.COMPLETED,
        output_data={"result": "done", "action": "blocked"},
        error_message=None,
        execution_time_ms=50,
        task_run_id=task_run_id,
    )


# ---------------------------------------------------------------------------
# Fixtures
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowHITLPause:
    """Workflow pauses correctly when a task returns PAUSED (HITL)."""

    async def test_workflow_pauses_when_task_returns_paused(self, workflow_client):
        """
        Full pause propagation: task PAUSED → node PAUSED → workflow PAUSED.
        Also verifies a hitl_questions row is created with correct links.
        """
        http_client, session = workflow_client

        # Create tasks
        hitl_task_id = await _create_task(
            session,
            cy_name=f"hitl_pause_task_{uuid4().hex[:8]}",
            script='answer = ask_question("Block?")\nreturn answer',
        )
        after_hitl_task_id = await _create_task(
            session,
            cy_name=f"after_hitl_task_{uuid4().hex[:8]}",
            script='result = {}\nresult["status"] = "completed"\nreturn result',
        )

        # Create workflow and start run
        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        workflow_id = await _build_hitl_workflow(
            session, http_client, hitl_task_id, after_hitl_task_id, passthrough_id
        )
        run_id = await _start_workflow_run(
            session, workflow_id, {"alert": "test-alert"}
        )

        # Track the task_run_id that the HITL task gets assigned.
        # Note: n-start is a transformation node (not a task), so the FIRST
        # call to execute_single_task is n-hitl-task.
        captured_hitl_task_run_id = None
        call_count = 0

        async def mock_execute(task_run_id, tenant_id):
            nonlocal captured_hitl_task_run_id, call_count
            call_count += 1
            if call_count == 1:
                # First task call is the HITL task (start node is a transformation)
                captured_hitl_task_run_id = task_run_id
                return _make_paused_result(task_run_id)
            return _make_completed_result(task_run_id)

        # Patch execute_single_task + send_hitl_question (no real Slack)
        executor = WorkflowExecutor(session)
        with (
            patch(
                "analysi.services.task_execution.TaskExecutionService.execute_single_task",
                side_effect=mock_execute,
            ),
            patch(
                "analysi.slack_listener.sender.send_hitl_question",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            await executor.monitor_execution(run_id)

        await session.commit()
        session.expire_all()

        # --- Assert 1: WorkflowRun is PAUSED ---
        wf_run_result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        wf_run = wf_run_result.scalar_one()
        assert wf_run.status == WorkflowConstants.Status.PAUSED, (
            f"Expected workflow PAUSED, got {wf_run.status}"
        )

        # --- Assert 2: HITL node instance is PAUSED ---
        node_repo = WorkflowNodeInstanceRepository(session)
        all_nodes = await node_repo.list_node_instances(run_id)
        hitl_node = next((n for n in all_nodes if n.node_id == "n-hitl-task"), None)
        assert hitl_node is not None, "HITL node instance not found"
        assert hitl_node.status == WorkflowConstants.Status.PAUSED, (
            f"Expected HITL node PAUSED, got {hitl_node.status}"
        )

        # --- Assert 3: Start node completed ---
        start_node = next((n for n in all_nodes if n.node_id == "n-start"), None)
        assert start_node is not None
        assert start_node.status == WorkflowConstants.Status.COMPLETED

        # --- Assert 4: After-HITL node should be PENDING (not executed) ---
        after_node = next((n for n in all_nodes if n.node_id == "n-after-hitl"), None)
        assert after_node is not None, "After-HITL node instance should exist"
        assert after_node.status == WorkflowConstants.Status.PENDING, (
            f"After-HITL node should be PENDING (blocked by paused predecessor), got {after_node.status}"
        )

        # --- Assert 5: hitl_questions row was created with correct links ---
        hitl_q_result = await session.execute(
            select(HITLQuestion).where(
                HITLQuestion.tenant_id == TENANT_ID,
                HITLQuestion.task_run_id == captured_hitl_task_run_id,
            )
        )
        hitl_question = hitl_q_result.scalar_one_or_none()
        assert hitl_question is not None, "HITL question row not created"
        assert hitl_question.workflow_run_id == run_id
        assert hitl_question.node_instance_id == hitl_node.id
        assert hitl_question.status == "pending"
        assert hitl_question.channel == "C-security-alerts"
        assert "Block" in hitl_question.question_text

        # --- Assert 6: send_hitl_question was called ---
        mock_send.assert_awaited_once()

        # --- Assert 7: HITL context stored in node error_message ---
        import json

        hitl_ctx = json.loads(hitl_node.error_message)
        assert hitl_ctx["hitl"] is True
        assert "Block" in hitl_ctx["question"]
        assert hitl_ctx["channel"] == "C-security-alerts"

    async def test_workflow_resumes_after_hitl_via_continue_after_hitl(
        self, workflow_client
    ):
        """
        After pause, continue_after_hitl resumes the workflow:
        paused node → COMPLETED, successor created, workflow → COMPLETED.
        """
        http_client, session = workflow_client

        # Create tasks
        hitl_task_id = await _create_task(
            session,
            cy_name=f"hitl_resume_task_{uuid4().hex[:8]}",
            script='answer = ask_question("Block?")\nreturn answer',
        )
        after_hitl_task_id = await _create_task(
            session,
            cy_name=f"after_resume_task_{uuid4().hex[:8]}",
            script='result = {}\nresult["status"] = "completed"\nreturn result',
        )

        # Build workflow and start run
        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        workflow_id = await _build_hitl_workflow(
            session, http_client, hitl_task_id, after_hitl_task_id, passthrough_id
        )
        run_id = await _start_workflow_run(
            session, workflow_id, {"alert": "test-resume"}
        )

        # Step 1: Run until PAUSED
        # n-start is a transformation — first execute_single_task call is n-hitl-task
        captured_hitl_task_run_id = None
        call_count = 0

        async def mock_execute_pause(task_run_id, tenant_id):
            nonlocal captured_hitl_task_run_id, call_count
            call_count += 1
            if call_count == 1:
                captured_hitl_task_run_id = task_run_id
                return _make_paused_result(task_run_id)
            return _make_completed_result(task_run_id)

        executor = WorkflowExecutor(session)
        with (
            patch(
                "analysi.services.task_execution.TaskExecutionService.execute_single_task",
                side_effect=mock_execute_pause,
            ),
            patch(
                "analysi.slack_listener.sender.send_hitl_question",
                new_callable=AsyncMock,
            ),
        ):
            await executor.monitor_execution(run_id)

        await session.commit()
        session.expire_all()

        # Verify paused state
        wf_run_result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        wf_run = wf_run_result.scalar_one()
        assert wf_run.status == WorkflowConstants.Status.PAUSED

        # Get the paused node instance
        node_repo = WorkflowNodeInstanceRepository(session)
        all_nodes = await node_repo.list_node_instances(run_id)
        hitl_node = next(n for n in all_nodes if n.node_id == "n-hitl-task")
        assert hitl_node.status == WorkflowConstants.Status.PAUSED

        # Step 2: Resume via continue_after_hitl
        # Simulate the human answering and the task resuming successfully
        resumed_result = _make_completed_result(captured_hitl_task_run_id)

        with patch(
            "analysi.services.task_execution.TaskExecutionService.execute_single_task",
            side_effect=lambda task_run_id, tenant_id: _make_completed_result(
                task_run_id
            ),
        ):
            await WorkflowExecutor.continue_after_hitl(
                workflow_run_id=run_id,
                node_instance_id=hitl_node.id,
                task_result=resumed_result,
            )

        # Refresh session state
        session.expire_all()

        # --- Assert 1: WorkflowRun is COMPLETED ---
        wf_run_result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        wf_run = wf_run_result.scalar_one()
        assert wf_run.status == WorkflowConstants.Status.COMPLETED, (
            f"Expected workflow COMPLETED after resume, got {wf_run.status}"
        )

        # --- Assert 2: HITL node is now COMPLETED with error_message cleared ---
        all_nodes_after = await node_repo.list_node_instances(run_id)
        hitl_node_after = next(n for n in all_nodes_after if n.node_id == "n-hitl-task")
        assert hitl_node_after.status == WorkflowConstants.Status.COMPLETED
        assert hitl_node_after.error_message is None, (
            f"error_message should be NULL after HITL resume, got: {hitl_node_after.error_message!r}"
        )

        # --- Assert 3: After-HITL node was created and completed ---
        after_node = next(
            (n for n in all_nodes_after if n.node_id == "n-after-hitl"), None
        )
        assert after_node is not None, "After-HITL successor node was never created"
        assert after_node.status == WorkflowConstants.Status.COMPLETED, (
            f"Expected after-HITL node COMPLETED, got {after_node.status}"
        )

    async def test_paused_workflow_not_re_executed_by_synchronous_runner(
        self, workflow_client
    ):
        """
        _execute_workflow_synchronously skips workflows in PAUSED status.
        This prevents duplicate execution if the control event bus re-triggers.
        """
        http_client, session = workflow_client

        hitl_task_id = await _create_task(
            session,
            cy_name=f"hitl_skip_task_{uuid4().hex[:8]}",
            script='answer = ask_question("Block?")\nreturn answer',
        )
        after_hitl_task_id = await _create_task(
            session,
            cy_name=f"after_skip_task_{uuid4().hex[:8]}",
            script='result = {}\nresult["done"] = True\nreturn result',
        )

        passthrough_id = await _get_passthrough_template(http_client, TENANT_ID)
        workflow_id = await _build_hitl_workflow(
            session, http_client, hitl_task_id, after_hitl_task_id, passthrough_id
        )
        run_id = await _start_workflow_run(session, workflow_id, {"alert": "test-skip"})

        # Run until paused
        call_count = 0

        async def mock_execute(task_run_id, tenant_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_paused_result(task_run_id)
            return _make_completed_result(task_run_id)

        executor = WorkflowExecutor(session)
        with (
            patch(
                "analysi.services.task_execution.TaskExecutionService.execute_single_task",
                side_effect=mock_execute,
            ),
            patch(
                "analysi.slack_listener.sender.send_hitl_question",
                new_callable=AsyncMock,
            ),
        ):
            await executor.monitor_execution(run_id)

        await session.commit()

        # Verify paused
        result = await session.execute(
            text("SELECT status FROM workflow_runs WHERE id = :id"),
            {"id": str(run_id)},
        )
        assert result.scalar_one() == "paused"

        # Attempt to re-execute — should be a no-op
        await WorkflowExecutor._execute_workflow_synchronously(run_id)

        # Status should still be PAUSED (not re-run or reset)
        session.expire_all()
        result = await session.execute(
            text("SELECT status FROM workflow_runs WHERE id = :id"),
            {"id": str(run_id)},
        )
        assert result.scalar_one() == "paused"
