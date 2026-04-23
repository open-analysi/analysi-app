"""Unit tests for task feedback ownership checks (Project Zakynthos).

Tests that only feedback owners or admins can update/delete feedback entries.
"""

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from analysi.auth.models import CurrentUser
from analysi.routers.task_feedback import _check_feedback_ownership


def _make_user(
    db_user_id: UUID | None = None,
    roles: list[str] | None = None,
) -> CurrentUser:
    return CurrentUser(
        user_id="user-123",
        email="user@example.com",
        tenant_id="test-tenant",
        roles=roles or ["analyst"],
        actor_type="user",
        db_user_id=db_user_id or uuid4(),
    )


def _make_feedback_doc(created_by: UUID) -> MagicMock:
    doc = MagicMock()
    doc.component = MagicMock()
    doc.component.id = uuid4()
    doc.component.created_by = created_by
    return doc


class TestFeedbackOwnershipCheck:
    """Test _check_feedback_ownership authorization logic."""

    @pytest.mark.unit
    def test_owner_can_modify_own_feedback(self):
        """Feedback owner should pass ownership check."""
        user_id = uuid4()
        user = _make_user(db_user_id=user_id, roles=["analyst"])
        doc = _make_feedback_doc(created_by=user_id)

        # Should not raise
        _check_feedback_ownership(doc, user)

    @pytest.mark.unit
    def test_non_owner_analyst_is_denied(self):
        """Non-owner analyst should get 403."""
        owner_id = uuid4()
        other_user_id = uuid4()
        user = _make_user(db_user_id=other_user_id, roles=["analyst"])
        doc = _make_feedback_doc(created_by=owner_id)

        with pytest.raises(HTTPException) as exc_info:
            _check_feedback_ownership(doc, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_admin_can_modify_any_feedback(self):
        """Admin should bypass ownership check."""
        owner_id = uuid4()
        admin_id = uuid4()
        user = _make_user(db_user_id=admin_id, roles=["admin"])
        doc = _make_feedback_doc(created_by=owner_id)

        # Should not raise
        _check_feedback_ownership(doc, user)

    @pytest.mark.unit
    def test_owner_role_can_modify_any_feedback(self):
        """Owner role should bypass ownership check."""
        feedback_owner_id = uuid4()
        org_owner_id = uuid4()
        user = _make_user(db_user_id=org_owner_id, roles=["owner"])
        doc = _make_feedback_doc(created_by=feedback_owner_id)

        # Should not raise
        _check_feedback_ownership(doc, user)

    @pytest.mark.unit
    def test_viewer_is_denied(self):
        """Viewer should get 403 even if somehow reaching this check."""
        user_id = uuid4()
        user = _make_user(db_user_id=user_id, roles=["viewer"])
        doc = _make_feedback_doc(created_by=uuid4())

        with pytest.raises(HTTPException) as exc_info:
            _check_feedback_ownership(doc, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_user_with_no_db_user_id_is_denied(self):
        """User without db_user_id should be denied (safety)."""
        user = _make_user(roles=["analyst"])
        user.db_user_id = None
        doc = _make_feedback_doc(created_by=uuid4())

        with pytest.raises(HTTPException) as exc_info:
            _check_feedback_ownership(doc, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_error_message_is_generic(self):
        """403 should use generic message, not leak feedback/user details."""
        user = _make_user(db_user_id=uuid4(), roles=["analyst"])
        doc = _make_feedback_doc(created_by=uuid4())

        with pytest.raises(HTTPException) as exc_info:
            _check_feedback_ownership(doc, user)

        # Should use the standard INSUFFICIENT_PERMISSIONS message
        assert exc_info.value.detail == "Insufficient permissions"

    @pytest.mark.unit
    def test_owner_who_is_also_admin_passes(self):
        """User who is both owner and admin should pass."""
        user_id = uuid4()
        user = _make_user(db_user_id=user_id, roles=["admin"])
        doc = _make_feedback_doc(created_by=user_id)

        # Should not raise
        _check_feedback_ownership(doc, user)
