"""Regression tests for execution_context identity injection.

User-supplied execution_context (from REST API) must not be able to
override trusted identity fields like tenant_id, task_id, task_run_id,
session, or directive. Without guards, a caller can submit:

    POST /workflows/{id}/execute
    {"execution_context": {"tenant_id": "victim-tenant"}}

and pivot all downstream DB/integration/artifact operations to another tenant.

The centralized sanitization lives in analysi.auth.context_sanitizer;
these tests verify the integration with TaskRunService.create_execution.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestTaskRunServiceContextInjection:
    """Verify TaskRunService.create_execution strips protected keys."""

    @pytest.mark.asyncio
    async def test_user_supplied_tenant_id_stripped(self):
        """execution_context with tenant_id must not override the trusted tenant."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService.__new__(TaskRunService)
        service.repository = MagicMock()
        service.storage_manager = MagicMock()

        # Capture the TaskRun passed to repository.create
        created_task_runs = []

        async def capture_create(session, task_run):
            created_task_runs.append(task_run)
            return task_run

        service.repository.create = capture_create
        service.store_input_data = AsyncMock()

        session = AsyncMock()

        # Attacker passes tenant_id in execution_context
        await service.create_execution(
            session=session,
            tenant_id="real-tenant",
            task_id=uuid4(),
            cy_script="emit('ok')",
            input_data={},
            execution_context={
                "tenant_id": "evil-tenant",
                "analysis_id": "legit-value",
            },
        )

        task_run = created_task_runs[0]
        ctx = task_run.execution_context

        # tenant_id must be the trusted one, not the attacker's
        assert ctx["tenant_id"] == "real-tenant", (
            f"execution_context tenant_id was overridden to '{ctx['tenant_id']}' "
            "by user-supplied input — cross-tenant pivot possible"
        )
        # Legitimate fields should still pass through
        assert ctx.get("analysis_id") == "legit-value"

    @pytest.mark.asyncio
    async def test_session_key_stripped(self):
        """execution_context with 'session' must be stripped (runtime-only field)."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService.__new__(TaskRunService)
        service.repository = MagicMock()
        service.storage_manager = MagicMock()

        created_task_runs = []

        async def capture_create(session, task_run):
            created_task_runs.append(task_run)
            return task_run

        service.repository.create = capture_create
        service.store_input_data = AsyncMock()

        await service.create_execution(
            session=AsyncMock(),
            tenant_id="real-tenant",
            task_id=uuid4(),
            cy_script="emit('ok')",
            input_data={},
            execution_context={"session": "injected-session-ref"},
        )

        ctx = created_task_runs[0].execution_context
        assert ctx.get("session") != "injected-session-ref", (
            "User-supplied 'session' was stored in execution_context"
        )

    @pytest.mark.asyncio
    async def test_task_id_override_stripped(self):
        """execution_context must not override task_id."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService.__new__(TaskRunService)
        service.repository = MagicMock()
        service.storage_manager = MagicMock()

        real_task_id = uuid4()
        created_task_runs = []

        async def capture_create(session, task_run):
            created_task_runs.append(task_run)
            return task_run

        service.repository.create = capture_create
        service.store_input_data = AsyncMock()

        await service.create_execution(
            session=AsyncMock(),
            tenant_id="real-tenant",
            task_id=real_task_id,
            cy_script="emit('ok')",
            input_data={},
            execution_context={"task_id": "fake-task-id"},
        )

        ctx = created_task_runs[0].execution_context
        assert ctx["task_id"] == str(real_task_id), (
            f"task_id was overridden to '{ctx['task_id']}' by user input"
        )

    @pytest.mark.asyncio
    async def test_workflow_run_id_override_stripped(self):
        """execution_context must not override workflow_run_id."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService.__new__(TaskRunService)
        service.repository = MagicMock()
        service.storage_manager = MagicMock()

        real_wf_id = uuid4()
        created_task_runs = []

        async def capture_create(session, task_run):
            created_task_runs.append(task_run)
            return task_run

        service.repository.create = capture_create
        service.store_input_data = AsyncMock()

        await service.create_execution(
            session=AsyncMock(),
            tenant_id="real-tenant",
            task_id=uuid4(),
            cy_script="emit('ok')",
            input_data={},
            workflow_run_id=real_wf_id,
            execution_context={"workflow_run_id": "fake-wf-id"},
        )

        ctx = created_task_runs[0].execution_context
        assert ctx["workflow_run_id"] == str(real_wf_id), (
            f"workflow_run_id was overridden to '{ctx['workflow_run_id']}'"
        )

    @pytest.mark.asyncio
    async def test_legitimate_keys_pass_through(self):
        """Non-protected keys like analysis_id and alert_id must pass through."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService.__new__(TaskRunService)
        service.repository = MagicMock()
        service.storage_manager = MagicMock()

        created_task_runs = []

        async def capture_create(session, task_run):
            created_task_runs.append(task_run)
            return task_run

        service.repository.create = capture_create
        service.store_input_data = AsyncMock()

        await service.create_execution(
            session=AsyncMock(),
            tenant_id="real-tenant",
            task_id=uuid4(),
            cy_script="emit('ok')",
            input_data={},
            execution_context={
                "analysis_id": "analysis-123",
                "alert_id": "alert-456",
                "custom_key": "custom_value",
            },
        )

        ctx = created_task_runs[0].execution_context
        assert ctx["analysis_id"] == "analysis-123"
        assert ctx["alert_id"] == "alert-456"
        assert ctx["custom_key"] == "custom_value"
