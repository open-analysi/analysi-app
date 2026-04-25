"""Unit tests for task feedback audit logging.

Tests that TaskFeedbackService correctly logs audit events for
create, update, and deactivate operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.schemas.audit_context import AuditContext
from analysi.services.task_feedback import TaskFeedbackService

TENANT = "test-tenant"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


def _make_audit_context() -> AuditContext:
    return AuditContext(
        actor_id="analyst@example.com",
        actor_type="user",
        source="rest_api",
        actor_user_id=SYSTEM_USER_ID,
        ip_address="127.0.0.1",
        user_agent="test-agent",
        request_id="req-123",
    )


class TestTaskFeedbackAuditLogging:
    """Verify _log_audit is called with correct action and details."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_feedback_logs_audit_event(self):
        """create_feedback should log a task_feedback.create audit event."""
        session = AsyncMock()
        task_component_id = uuid4()
        feedback_component_id = uuid4()

        # Mock the target component lookup
        mock_component = MagicMock()
        mock_component.tenant_id = TENANT
        session.get = AsyncMock(return_value=mock_component)

        # Mock flush to assign component.id
        created_component = None

        async def capture_flush():
            nonlocal created_component
            # Find the Component that was added and give it an ID
            for call in session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "kind") and not hasattr(obj, "component_id"):
                    obj.id = feedback_component_id
                    created_component = obj

        session.flush = AsyncMock(side_effect=capture_flush)

        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log:
            await svc.create_feedback(
                tenant_id=TENANT,
                task_component_id=task_component_id,
                feedback_text="Always check VirusTotal",
                created_by=SYSTEM_USER_ID,
                audit_context=audit_ctx,
            )

            mock_log.assert_called_once_with(
                tenant_id=TENANT,
                action="task_feedback.create",
                resource_id=str(feedback_component_id),
                audit_context=audit_ctx,
                details={
                    "task_component_id": str(task_component_id),
                    "feedback_preview": "Always check VirusTotal",
                },
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_feedback_no_audit_without_context(self):
        """create_feedback should skip audit when audit_context is None."""
        session = AsyncMock()
        mock_component = MagicMock()
        mock_component.tenant_id = TENANT
        session.get = AsyncMock(return_value=mock_component)

        async def assign_id():
            for call in session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "kind") and not hasattr(obj, "component_id"):
                    obj.id = uuid4()

        session.flush = AsyncMock(side_effect=assign_id)

        svc = TaskFeedbackService(session)

        with patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log:
            await svc.create_feedback(
                tenant_id=TENANT,
                task_component_id=uuid4(),
                feedback_text="No audit",
                created_by=SYSTEM_USER_ID,
                # No audit_context
            )

            mock_log.assert_called_once()
            # audit_context should be None
            assert mock_log.call_args.kwargs["audit_context"] is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_deactivate_feedback_logs_audit_event(self):
        """deactivate_feedback should log a task_feedback.delete audit event."""
        session = AsyncMock()
        feedback_id = uuid4()

        # Mock the UPDATE returning 1 row affected
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log:
            result = await svc.deactivate_feedback(
                tenant_id=TENANT,
                feedback_component_id=feedback_id,
                audit_context=audit_ctx,
            )

            assert result is True
            mock_log.assert_called_once_with(
                tenant_id=TENANT,
                action="task_feedback.delete",
                resource_id=str(feedback_id),
                audit_context=audit_ctx,
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_deactivate_feedback_no_audit_when_not_found(self):
        """deactivate_feedback should not log audit when entry not found."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log:
            result = await svc.deactivate_feedback(
                tenant_id=TENANT,
                feedback_component_id=uuid4(),
                audit_context=audit_ctx,
            )

            assert result is False
            mock_log.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_feedback_logs_audit_event(self):
        """update_feedback should log a task_feedback.update audit event."""
        feedback_id = uuid4()

        # Build a mock KUDocument with component
        mock_doc = MagicMock()
        mock_doc.content = "Old text"
        mock_doc.doc_metadata = {}
        mock_doc.component = MagicMock()
        mock_doc.component.name = "Feedback: Old text"

        session = AsyncMock()
        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with (
            patch.object(
                svc, "get_feedback", new_callable=AsyncMock, return_value=mock_doc
            ),
            patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log,
        ):
            result = await svc.update_feedback(
                tenant_id=TENANT,
                feedback_component_id=feedback_id,
                feedback_text="Updated text",
                metadata={"priority": "high"},
                audit_context=audit_ctx,
            )

            assert result is not None
            mock_log.assert_called_once_with(
                tenant_id=TENANT,
                action="task_feedback.update",
                resource_id=str(feedback_id),
                audit_context=audit_ctx,
                details={"updated_fields": ["feedback_text", "metadata"]},
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_feedback_tracks_partial_fields(self):
        """update_feedback should track only the fields that were updated."""
        feedback_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.content = "Old text"
        mock_doc.doc_metadata = {}
        mock_doc.component = MagicMock()

        session = AsyncMock()
        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with (
            patch.object(
                svc, "get_feedback", new_callable=AsyncMock, return_value=mock_doc
            ),
            patch.object(svc, "_log_audit", new_callable=AsyncMock) as mock_log,
        ):
            await svc.update_feedback(
                tenant_id=TENANT,
                feedback_component_id=feedback_id,
                feedback_text="New text only",
                # metadata not provided (None)
                audit_context=audit_ctx,
            )

            details = mock_log.call_args.kwargs["details"]
            assert details == {"updated_fields": ["feedback_text"]}


class TestLogAuditMethod:
    """Test the _log_audit method directly."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_audit_skips_when_no_context(self):
        """_log_audit should return immediately when audit_context is None."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        with patch(
            "analysi.services.task_feedback.ActivityAuditRepository"
        ) as mock_repo_cls:
            await svc._log_audit(
                tenant_id=TENANT,
                action="task_feedback.create",
                resource_id="some-id",
                audit_context=None,
            )
            mock_repo_cls.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_audit_calls_repository(self):
        """_log_audit should create an audit event via ActivityAuditRepository."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with patch(
            "analysi.services.task_feedback.ActivityAuditRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await svc._log_audit(
                tenant_id=TENANT,
                action="task_feedback.create",
                resource_id="fb-123",
                audit_context=audit_ctx,
                details={"task_component_id": "task-456"},
            )

            mock_repo.create.assert_called_once_with(
                tenant_id=TENANT,
                actor_id=SYSTEM_USER_ID,
                actor_type="user",
                source="rest_api",
                action="task_feedback.create",
                resource_type="task_feedback",
                resource_id="fb-123",
                details={"task_component_id": "task-456"},
                ip_address="127.0.0.1",
                user_agent="test-agent",
                request_id="req-123",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_audit_swallows_exceptions(self):
        """_log_audit should not raise if the repository fails."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)
        audit_ctx = _make_audit_context()

        with patch(
            "analysi.services.task_feedback.ActivityAuditRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(side_effect=RuntimeError("DB down"))
            mock_repo_cls.return_value = mock_repo

            # Should not raise
            await svc._log_audit(
                tenant_id=TENANT,
                action="task_feedback.create",
                resource_id="fb-123",
                audit_context=audit_ctx,
            )
