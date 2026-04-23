"""
Integration tests for task execution log persistence and retrieval.

Verifies:
- log() calls from Cy scripts are persisted as artifacts after execution
- Logs are stored with artifact_type='execution_log' and source='auto_capture'
- REST API endpoint GET /{tenant}/task-runs/{trid}/logs returns persisted logs
- Empty logs (no log() calls) still work correctly
- Logs from failed executions are also persisted

Note: Cy 0.47+ returns structured log entries as {"ts": float, "message": str}
dicts instead of plain strings.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.task_run import TaskRun
from analysi.repositories.task import TaskRepository
from analysi.services.artifact_service import ArtifactService
from analysi.services.task_execution import TaskExecutionService
from analysi.services.task_run import TaskRunService

TENANT_ID = f"logs-test-{uuid4().hex[:8]}"


def _extract_messages(entries: list) -> list[str]:
    """Extract message strings from log entries (handles both legacy and structured formats).

    Cy 0.47+ returns {"ts": float, "message": str} dicts; older versions returned
    plain strings. This helper normalizes both formats to a list of message strings.
    """
    messages = []
    for entry in entries:
        if isinstance(entry, dict):
            messages.append(entry["message"])
        else:
            messages.append(str(entry))
    return messages


async def _create_task_and_run(
    session: AsyncSession,
    cy_script: str,
    input_data: dict | None = None,
    tenant_id: str = TENANT_ID,
) -> TaskRun:
    """Helper: create a Task + TaskRun in the DB, return the TaskRun."""

    task_repo = TaskRepository(session)
    task = await task_repo.create(
        {
            "tenant_id": tenant_id,
            "name": f"Log Test Task {uuid4().hex[:8]}",
            "description": "Test task for log persistence",
            "script": cy_script,
        }
    )
    await session.commit()

    task_run_service = TaskRunService()
    task_run = await task_run_service.create_execution(
        session=session,
        tenant_id=tenant_id,
        task_id=task.component_id,
        cy_script=None,  # loaded from task
        input_data=input_data or {},
        executor_config=None,
    )
    await session.commit()
    return task_run


async def _execute_with_session(
    session: AsyncSession,
    task_run: TaskRun,
    tenant_id: str,
) -> None:
    """Execute a task run using the test session and persist results.

    Uses _execute_task_with_session (which accepts a session) instead of
    execute_and_persist (which creates its own AsyncSessionLocal session
    pointing to the app DATABASE_URL, not the test database).
    """
    from analysi.constants import TaskConstants
    from analysi.schemas.task_execution import TaskExecutionStatus

    service = TaskExecutionService()
    result = await service._execute_task_with_session(task_run, session)
    await session.commit()

    # Persist status update (mirrors what execute_and_persist does)
    task_run_service = TaskRunService()
    if result.status == TaskExecutionStatus.COMPLETED:
        await task_run_service.update_status(
            session,
            result.task_run_id,
            TaskConstants.Status.COMPLETED,
            output_data=result.output_data,
            llm_usage=result.llm_usage,
        )
    else:
        await task_run_service.update_status(
            session,
            result.task_run_id,
            TaskConstants.Status.FAILED,
            error_info={"error": result.error_message or "Unknown error"},
            llm_usage=result.llm_usage,
        )

    # Persist log artifact (mirrors _persist_log_artifact logic)
    if result.log_entries:
        await service._persist_log_artifact(session, tenant_id, result, task_run)

    await session.commit()


# ─── Service-level tests: execute_and_persist stores logs as artifacts ───


@pytest.mark.asyncio
@pytest.mark.integration
class TestLogPersistence:
    """execute_and_persist() stores log_entries as an artifact in the artifact store."""

    async def test_logs_persisted_as_artifact_after_execution(
        self, integration_test_session: AsyncSession
    ):
        """After execution, log entries are stored as an execution_log artifact."""
        script = 'log("step one")\nlog("step two")\nreturn "ok"'
        task_run = await _create_task_and_run(integration_test_session, script)

        await _execute_with_session(integration_test_session, task_run, TENANT_ID)

        # Query artifacts for this task run
        artifact_service = ArtifactService(integration_test_session)
        artifacts = await artifact_service.get_artifacts_by_task_run(
            TENANT_ID, task_run.id
        )

        # Find the execution_log artifact
        log_artifacts = [a for a in artifacts if a.artifact_type == "execution_log"]
        assert len(log_artifacts) == 1, (
            f"Expected exactly 1 execution_log artifact, got {len(log_artifacts)}"
        )

        log_artifact = log_artifacts[0]
        assert log_artifact.source == "auto_capture"
        assert log_artifact.task_run_id == task_run.id
        assert log_artifact.mime_type == "application/json"

        # Verify content contains the log lines (Cy 0.47+ returns structured entries)
        content = await artifact_service.get_artifact(TENANT_ID, log_artifact.id)
        assert content is not None
        assert isinstance(content.content, dict)
        messages = _extract_messages(content.content["entries"])
        assert messages == ["step one", "step two"]

    async def test_no_log_artifact_when_no_log_calls(
        self, integration_test_session: AsyncSession
    ):
        """When a script produces no log() calls, no execution_log artifact is created."""
        script = 'return "quiet"'
        task_run = await _create_task_and_run(integration_test_session, script)

        await _execute_with_session(integration_test_session, task_run, TENANT_ID)

        # Query artifacts for this task run
        artifact_service = ArtifactService(integration_test_session)
        artifacts = await artifact_service.get_artifacts_by_task_run(
            TENANT_ID, task_run.id
        )

        log_artifacts = [a for a in artifacts if a.artifact_type == "execution_log"]
        assert len(log_artifacts) == 0, (
            "No execution_log artifact should be created when there are no log() calls"
        )

    async def test_logs_persisted_even_on_failure(
        self, integration_test_session: AsyncSession
    ):
        """Log entries written before a script failure are still persisted as artifact."""
        script = 'log("before crash")\nx = undefined_var\nreturn x'
        task_run = await _create_task_and_run(integration_test_session, script)

        await _execute_with_session(integration_test_session, task_run, TENANT_ID)

        # Query artifacts for this task run
        artifact_service = ArtifactService(integration_test_session)
        artifacts = await artifact_service.get_artifacts_by_task_run(
            TENANT_ID, task_run.id
        )

        log_artifacts = [a for a in artifacts if a.artifact_type == "execution_log"]
        assert len(log_artifacts) == 1, (
            "Logs from failed execution should still be persisted"
        )

        content = await artifact_service.get_artifact(TENANT_ID, log_artifacts[0].id)
        messages = _extract_messages(content.content["entries"])
        assert messages == ["before crash"]


# ─── REST API tests: GET /{tenant}/task-runs/{trid}/logs ───


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunLogsEndpoint:
    """GET /{tenant}/task-runs/{trid}/logs returns persisted execution logs."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.pop(get_db, None)

    async def test_get_logs_returns_log_entries(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """GET /task-runs/{trid}/logs returns the log entries from execution."""
        tenant = f"logs-api-{uuid4().hex[:8]}"
        script = 'log("api test log")\nlog("second line")\nreturn "done"'
        task_run = await _create_task_and_run(
            integration_test_session, script, tenant_id=tenant
        )

        # Execute with test session (not execute_and_persist which uses app DB)
        trid = task_run.id
        await _execute_with_session(integration_test_session, task_run, tenant)

        # Expire cached objects so the API endpoint sees committed data
        integration_test_session.expire_all()

        # Call the logs endpoint
        response = await client.get(f"/v1/{tenant}/task-runs/{trid}/logs")
        assert response.status_code == 200

        body = response.json()
        assert "data" in body
        data = body["data"]
        assert data["trid"] == str(trid)
        assert data["status"] == "completed"
        # Cy 0.47+ returns structured log entries {ts, message}
        messages = _extract_messages(data["entries"])
        assert messages == ["api test log", "second line"]
        assert data["has_logs"] is True

    async def test_get_logs_empty_when_no_logs(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """GET /task-runs/{trid}/logs returns empty entries when no log() calls."""
        tenant = f"logs-api-{uuid4().hex[:8]}"
        script = 'return "quiet"'
        task_run = await _create_task_and_run(
            integration_test_session, script, tenant_id=tenant
        )

        trid = task_run.id
        await _execute_with_session(integration_test_session, task_run, tenant)
        integration_test_session.expire_all()

        response = await client.get(f"/v1/{tenant}/task-runs/{trid}/logs")
        assert response.status_code == 200

        body = response.json()
        data = body["data"]
        assert data["status"] == "completed"
        assert data["entries"] == []
        assert data["has_logs"] is False

    async def test_get_logs_404_for_nonexistent_task_run(
        self,
        client: AsyncClient,
    ):
        """GET /task-runs/{trid}/logs returns 404 for non-existent task run."""
        fake_trid = uuid4()
        response = await client.get(f"/v1/{TENANT_ID}/task-runs/{fake_trid}/logs")
        assert response.status_code == 404

    async def test_get_logs_from_failed_execution(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """GET /task-runs/{trid}/logs returns logs even from failed executions."""
        tenant = f"logs-api-{uuid4().hex[:8]}"
        script = 'log("before error")\nx = nope\nreturn x'
        task_run = await _create_task_and_run(
            integration_test_session, script, tenant_id=tenant
        )

        trid = task_run.id
        await _execute_with_session(integration_test_session, task_run, tenant)
        integration_test_session.expire_all()

        response = await client.get(f"/v1/{tenant}/task-runs/{trid}/logs")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["status"] == "failed"
        # Cy 0.47+ returns structured log entries {ts, message}
        messages = _extract_messages(data["entries"])
        assert messages == ["before error"]
        assert data["has_logs"] is True
