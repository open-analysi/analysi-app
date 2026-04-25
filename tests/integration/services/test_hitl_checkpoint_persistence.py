"""
Integration tests for HITL checkpoint persistence in PostgreSQL.

Verifies the contract: ExecutionCheckpoint.to_dict() → JSONB → from_dict()
survives a real database round-trip through TaskRun.execution_context.

Checkpoint storage layer.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cy_language.execution_plan import ExecutionCheckpoint
from sqlalchemy import select, text

from analysi.models.task_run import TaskRun


def _make_checkpoint(**overrides) -> ExecutionCheckpoint:
    """Build a realistic ExecutionCheckpoint for testing."""
    defaults = {
        "node_results": {
            "n1": {"output": "enrichment data", "score": 8.5},
            "n2": ["item1", "item2"],
            "n3": None,
            "n4": 42,
        },
        "pending_node_id": "n5",
        "pending_tool_name": "app::slack::ask_question",
        "pending_tool_args": {
            "text": "Block IP 192.168.1.1?",
            "channel": "C-security",
            "options": ["Block", "Ignore", "Escalate"],
        },
        "pending_tool_result": None,
        "variables": {
            "threat_score": 8.5,
            "ip": "192.168.1.1",
            "is_malicious": True,
            "enrichments": {"vt": {"score": 85}, "abuseipdb": None},
        },
        "plan_version": "2.0",
        "captured_logs": [],
    }
    defaults.update(overrides)
    return ExecutionCheckpoint(**defaults)


@pytest.mark.asyncio
@pytest.mark.integration
class TestCheckpointDBRoundTrip:
    """Checkpoint stored in task_runs.execution_context JSONB and loaded back."""

    async def test_checkpoint_survives_db_round_trip(self, integration_test_session):
        """Write checkpoint to execution_context, read it back, verify all fields."""
        db = integration_test_session
        tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"

        original = _make_checkpoint()
        task_run_id = uuid.uuid4()

        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,
            status="paused",
            cy_script='answer = ask_question("Block?")\nreturn answer',
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC),
            execution_context={"_hitl_checkpoint": original.to_dict()},
        )
        db.add(task_run)
        await db.commit()

        # Re-read from DB (fresh load, no cache)
        db.expire_all()
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await db.execute(stmt)
        loaded = result.scalar_one()

        assert loaded.execution_context is not None
        assert "_hitl_checkpoint" in loaded.execution_context

        restored = ExecutionCheckpoint.from_dict(
            loaded.execution_context["_hitl_checkpoint"]
        )

        assert restored.node_results == original.node_results
        assert restored.pending_node_id == original.pending_node_id
        assert restored.pending_tool_name == original.pending_tool_name
        assert restored.pending_tool_args == original.pending_tool_args
        assert restored.pending_tool_result is None
        assert restored.variables == original.variables
        assert restored.plan_version == original.plan_version

    async def test_checkpoint_with_answer_survives_db_round_trip(
        self, integration_test_session
    ):
        """Resume path: checkpoint with pending_tool_result set persists correctly."""
        db = integration_test_session
        tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"

        original = _make_checkpoint(pending_tool_result="Block")
        task_run_id = uuid.uuid4()

        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,
            status="running",
            cy_script='answer = ask_question("Block?")\nreturn answer',
            started_at=datetime.now(UTC) - timedelta(minutes=2),
            created_at=datetime.now(UTC) - timedelta(minutes=2),
            updated_at=datetime.now(UTC),
            execution_context={"_hitl_checkpoint": original.to_dict()},
        )
        db.add(task_run)
        await db.commit()

        db.expire_all()
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await db.execute(stmt)
        loaded = result.scalar_one()

        restored = ExecutionCheckpoint.from_dict(
            loaded.execution_context["_hitl_checkpoint"]
        )

        assert restored.pending_tool_result == "Block"
        assert restored.to_dict() == original.to_dict()

    async def test_checkpoint_update_preserves_other_context(
        self, integration_test_session
    ):
        """Updating checkpoint doesn't clobber other execution_context keys."""
        db = integration_test_session
        tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"

        task_run_id = uuid.uuid4()
        original_context = {
            "cy_name": "threat_analyzer",
            "tenant_id": tenant_id,
            "llm_usage": {"input_tokens": 500, "output_tokens": 200},
        }

        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,
            status="running",
            cy_script="return 1",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC),
            execution_context=original_context,
        )
        db.add(task_run)
        await db.commit()

        # Simulate what update_status does: merge checkpoint into existing context
        await db.refresh(task_run)
        checkpoint = _make_checkpoint()
        ctx = dict(task_run.execution_context or {})
        ctx["_hitl_checkpoint"] = checkpoint.to_dict()
        task_run.execution_context = ctx
        task_run.status = "paused"
        await db.commit()

        # Re-read and verify both checkpoint and original keys survived
        db.expire_all()
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await db.execute(stmt)
        loaded = result.scalar_one()

        assert loaded.execution_context["cy_name"] == "threat_analyzer"
        assert loaded.execution_context["llm_usage"]["input_tokens"] == 500
        assert "_hitl_checkpoint" in loaded.execution_context

        restored = ExecutionCheckpoint.from_dict(
            loaded.execution_context["_hitl_checkpoint"]
        )
        assert restored.pending_tool_name == "app::slack::ask_question"

    async def test_large_node_results_survive_db_round_trip(
        self, integration_test_session
    ):
        """Checkpoint with many cached node results (realistic multi-step task) persists."""
        db = integration_test_session
        tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"

        # Simulate a task that executed 20 tool calls before pausing
        large_node_results = {
            f"n{i}": {
                "tool": f"tool_{i}",
                "output": f"result_{i}" * 50,  # ~350 chars each
                "metadata": {"duration_ms": i * 100, "cached": False},
            }
            for i in range(20)
        }

        original = _make_checkpoint(node_results=large_node_results)
        task_run_id = uuid.uuid4()

        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,
            status="paused",
            cy_script="return 1",
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            created_at=datetime.now(UTC) - timedelta(minutes=5),
            updated_at=datetime.now(UTC),
            execution_context={"_hitl_checkpoint": original.to_dict()},
        )
        db.add(task_run)
        await db.commit()

        db.expire_all()
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await db.execute(stmt)
        loaded = result.scalar_one()

        restored = ExecutionCheckpoint.from_dict(
            loaded.execution_context["_hitl_checkpoint"]
        )

        assert len(restored.node_results) == 20
        assert restored.node_results == large_node_results
        # Verify specific entry to catch any truncation
        assert restored.node_results["n19"]["tool"] == "tool_19"


@pytest.mark.asyncio
@pytest.mark.integration
class TestHITLStatusConstraints:
    """Verify DB constraints accept HITL-related status values.

    These tests guard against the class of bug where application code writes
    a status value that the DB constraint rejects. Each test writes a real row
    with the HITL status and verifies the DB accepts it.
    """

    async def test_alert_analysis_accepts_paused_human_review(
        self, integration_test_session
    ):
        """alert_analysis.status = 'paused_human_review' is accepted by chk_analysis_status.

        Uses SET session_replication_role = 'replica' to skip FK checks so the
        test focuses purely on the CHECK constraint (the bug we're guarding against).
        """
        db = integration_test_session
        tenant_id = f"test-tenant-{uuid.uuid4().hex[:8]}"
        analysis_id = uuid.uuid4()

        await db.execute(text("SET session_replication_role = 'replica'"))

        await db.execute(
            text("""
                INSERT INTO alert_analyses (id, created_at, tenant_id, alert_id, status)
                VALUES (:id, now(), :tenant_id, :alert_id, 'paused_human_review')
            """),
            {
                "id": str(analysis_id),
                "tenant_id": tenant_id,
                "alert_id": str(uuid.uuid4()),
            },
        )
        await db.commit()

        result = await db.execute(
            text("SELECT status FROM alert_analyses WHERE id = :id"),
            {"id": str(analysis_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row.status == "paused_human_review"

        await db.execute(text("SET session_replication_role = 'origin'"))

    async def test_workflow_node_instance_accepts_paused(
        self, integration_test_session
    ):
        """workflow_node_instances.status = 'paused' passes the trigger check.

        Strategy: INSERT the row in replica mode (skips FKs + triggers), then
        UPDATE status in origin mode so check_node_instance_status fires.
        The negative test below proves the trigger actually rejects bad values.
        """
        db = integration_test_session

        wf_run_id = uuid.uuid4()
        node_id = uuid.uuid4()

        # Insert all rows with triggers+FKs disabled
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            text("""
                INSERT INTO workflow_runs (id, created_at, tenant_id, workflow_id, status)
                VALUES (:id, now(), :tid, :wf_id, 'running')
            """),
            {"id": str(wf_run_id), "tid": "t1", "wf_id": str(uuid.uuid4())},
        )
        await db.execute(
            text("""
                INSERT INTO workflow_node_instances
                    (id, created_at, workflow_run_id, node_id, node_uuid, status)
                VALUES (:id, now(), :wf_run_id, :node_id, :node_uuid, 'running')
            """),
            {
                "id": str(node_id),
                "wf_run_id": str(wf_run_id),
                "node_id": "test-node-1",
                "node_uuid": str(uuid.uuid4()),
            },
        )
        await db.commit()

        # Switch to origin — trigger fires on UPDATE
        await db.execute(text("SET session_replication_role = 'origin'"))

        # This is the real test — trigger check_node_instance_status fires here
        await db.execute(
            text("""
                UPDATE workflow_node_instances SET status = 'paused'
                WHERE id = :id
            """),
            {"id": str(node_id)},
        )
        await db.commit()

        result = await db.execute(
            text("SELECT status FROM workflow_node_instances WHERE id = :id"),
            {"id": str(node_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row.status == "paused"

    async def test_workflow_node_instance_rejects_invalid_status(
        self, integration_test_session
    ):
        """Proves the trigger actually fires — invalid status is rejected.

        This is the negative counterpart to test_workflow_node_instance_accepts_paused.
        Without this test, we can't be sure the trigger is running.
        """
        db = integration_test_session

        wf_run_id = uuid.uuid4()
        node_id = uuid.uuid4()

        # Insert rows with triggers disabled
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            text("""
                INSERT INTO workflow_runs (id, created_at, tenant_id, workflow_id, status)
                VALUES (:id, now(), :tid, :wf_id, 'running')
            """),
            {"id": str(wf_run_id), "tid": "t1", "wf_id": str(uuid.uuid4())},
        )
        await db.execute(
            text("""
                INSERT INTO workflow_node_instances
                    (id, created_at, workflow_run_id, node_id, node_uuid, status)
                VALUES (:id, now(), :wf_run_id, :node_id, :node_uuid, 'running')
            """),
            {
                "id": str(node_id),
                "wf_run_id": str(wf_run_id),
                "node_id": "test-node-1",
                "node_uuid": str(uuid.uuid4()),
            },
        )
        await db.commit()

        # Origin mode — trigger fires
        await db.execute(text("SET session_replication_role = 'origin'"))

        with pytest.raises(Exception, match="Invalid node instance status"):
            await db.execute(
                text("""
                    UPDATE workflow_node_instances SET status = 'bogus_status'
                    WHERE id = :id
                """),
                {"id": str(node_id)},
            )

        await db.rollback()

    async def test_workflow_run_accepts_paused(self, integration_test_session):
        """workflow_runs.status = 'paused' passes the trigger check.

        Strategy: INSERT in replica mode, UPDATE status in origin mode so
        check_workflow_run_status fires. Negative test below proves rejection.
        """
        db = integration_test_session

        wf_run_id = uuid.uuid4()

        # Insert with triggers+FKs disabled
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            text("""
                INSERT INTO workflow_runs (id, created_at, tenant_id, workflow_id, status)
                VALUES (:id, now(), :tid, :wf_id, 'running')
            """),
            {"id": str(wf_run_id), "tid": "t1", "wf_id": str(uuid.uuid4())},
        )
        await db.commit()

        # Origin mode — trigger fires on UPDATE
        await db.execute(text("SET session_replication_role = 'origin'"))

        await db.execute(
            text("""
                UPDATE workflow_runs SET status = 'paused' WHERE id = :id
            """),
            {"id": str(wf_run_id)},
        )
        await db.commit()

        result = await db.execute(
            text("SELECT status FROM workflow_runs WHERE id = :id"),
            {"id": str(wf_run_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row.status == "paused"

    async def test_workflow_run_rejects_invalid_status(self, integration_test_session):
        """Proves the trigger actually fires — invalid status is rejected."""
        db = integration_test_session

        wf_run_id = uuid.uuid4()

        # Insert with triggers disabled
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            text("""
                INSERT INTO workflow_runs (id, created_at, tenant_id, workflow_id, status)
                VALUES (:id, now(), :tid, :wf_id, 'running')
            """),
            {"id": str(wf_run_id), "tid": "t1", "wf_id": str(uuid.uuid4())},
        )
        await db.commit()

        # Origin mode — trigger fires
        await db.execute(text("SET session_replication_role = 'origin'"))

        with pytest.raises(Exception, match="Invalid workflow run status"):
            await db.execute(
                text("""
                    UPDATE workflow_runs SET status = 'bogus_status' WHERE id = :id
                """),
                {"id": str(wf_run_id)},
            )

        await db.rollback()
