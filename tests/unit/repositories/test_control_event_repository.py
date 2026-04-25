"""Unit tests for control event repositories."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.control_event_repository import (
    ControlEventDispatchRepository,
    ControlEventRepository,
    ControlEventRuleRepository,
)


class TestControlEventRepository:
    """Tests for ControlEventRepository."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return ControlEventRepository(mock_session)

    @pytest.mark.asyncio
    async def test_insert_creates_control_event(self, repo, mock_session):
        """insert() sets all fields and calls add + flush."""
        tenant_id = "tenant-a"
        channel = "disposition:ready"
        payload = {"alert_id": str(uuid4()), "analysis_id": str(uuid4())}

        event = await repo.insert(tenant_id=tenant_id, channel=channel, payload=payload)

        assert event.tenant_id == tenant_id
        assert event.channel == channel
        assert event.payload == payload
        assert event.status == "pending"
        assert event.retry_count == 0
        mock_session.add.assert_called_once_with(event)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """get_by_id() returns event when present."""
        event_id = uuid4()
        mock_event = MagicMock()
        mock_event.id = event_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_event)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(event_id)

        assert result == mock_event
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """get_by_id() returns None when event is absent."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_claim_batch_resets_stuck_events(self, repo, mock_session):
        """claim_batch() issues UPDATE to reset events stuck in claimed status."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        mock_session.execute.return_value = mock_result

        await repo.claim_batch(batch_size=10, max_retries=3, stuck_hours=1)

        # At least two execute calls: one for reset, one for select
        assert mock_session.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_claim_batch_claims_pending_events(self, repo, mock_session):
        """claim_batch() marks pending events as claimed and returns them."""
        mock_event = MagicMock()
        mock_event.status = "pending"
        mock_event.retry_count = 0

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_event]))
        )

        # First execute (reset stuck) returns a generic result, second returns events
        mock_session.execute.side_effect = [MagicMock(), mock_result]

        events = await repo.claim_batch(batch_size=10, max_retries=3, stuck_hours=1)

        assert len(events) == 1
        assert mock_event.status == "claimed"
        assert mock_event.claimed_at is not None
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_batch_returns_empty_when_none_available(
        self, repo, mock_session
    ):
        """claim_batch() returns empty list when no events are available."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        mock_session.execute.side_effect = [MagicMock(), mock_result]

        events = await repo.claim_batch(batch_size=10, max_retries=3, stuck_hours=1)

        assert events == []
        mock_session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_completed_sets_status(self, repo, mock_session):
        """mark_completed() sets event status to completed."""
        mock_event = MagicMock()
        mock_event.status = "claimed"

        await repo.mark_completed(mock_event)

        assert mock_event.status == "completed"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_sets_status_and_increments_retry(
        self, repo, mock_session
    ):
        """mark_failed() sets status to failed and increments retry_count."""
        mock_event = MagicMock()
        mock_event.status = "claimed"
        mock_event.retry_count = 1

        await repo.mark_failed(mock_event)

        assert mock_event.status == "failed"
        assert mock_event.retry_count == 2
        mock_session.flush.assert_called_once()


class TestControlEventRuleRepository:
    """Tests for ControlEventRuleRepository."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return ControlEventRuleRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_rule_success(self, repo, mock_session):
        """create() sets all fields and calls add + flush."""
        rule = await repo.create(
            tenant_id="tenant-a",
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="JIRA Sync",
            config={"project_key": "SEC"},
        )

        assert rule.tenant_id == "tenant-a"
        assert rule.channel == "disposition:ready"
        assert rule.target_type == "task"
        assert rule.name == "JIRA Sync"
        assert rule.config == {"project_key": "SEC"}
        assert rule.enabled is True
        mock_session.add.assert_called_once_with(rule)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rule_by_id_found(self, repo, mock_session):
        """get_by_id() returns rule when present."""
        rule_id = uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id("tenant-a", rule_id)

        assert result == mock_rule

    @pytest.mark.asyncio
    async def test_get_rule_by_id_not_found(self, repo, mock_session):
        """get_by_id() returns None when absent."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id("tenant-a", uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_rule_by_id_tenant_isolation(self, repo, mock_session):
        """get_by_id() returns None for wrong tenant."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id("wrong-tenant", uuid4())

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_channel_returns_enabled(self, repo, mock_session):
        """list_by_channel() with enabled_only=True returns only enabled rules."""
        mock_rules = [MagicMock(enabled=True), MagicMock(enabled=True)]
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_rules))
        )
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_channel(
            "tenant-a", "disposition:ready", enabled_only=True
        )

        assert result == mock_rules

    @pytest.mark.asyncio
    async def test_list_by_channel_all_when_not_filtered(self, repo, mock_session):
        """list_by_channel() with enabled_only=False returns all rules."""
        mock_rules = [MagicMock(enabled=True), MagicMock(enabled=False)]
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_rules))
        )
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_channel(
            "tenant-a", "disposition:ready", enabled_only=False
        )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_by_channel_empty(self, repo, mock_session):
        """list_by_channel() returns empty list when no rules configured."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_channel("tenant-a", "disposition:ready")

        assert result == []

    @pytest.mark.asyncio
    async def test_update_rule_fields(self, repo, mock_session):
        """update() modifies specified fields and returns updated rule."""
        rule_id = uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Old Name"
        mock_rule.enabled = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result

        result = await repo.update("tenant-a", rule_id, name="New Name", enabled=False)

        assert result == mock_rule
        assert mock_rule.name == "New Name"
        assert mock_rule.enabled is False
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_rule_not_found(self, repo, mock_session):
        """update() returns None when rule not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.update("tenant-a", uuid4(), name="New Name")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_rule_success(self, repo, mock_session):
        """delete() returns True when rule exists."""
        mock_rule = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        result = await repo.delete("tenant-a", uuid4())

        assert result is True
        mock_session.delete.assert_called_once_with(mock_rule)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self, repo, mock_session):
        """delete() returns False when rule does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.delete("tenant-a", uuid4())

        assert result is False


class TestControlEventDispatchRepository:
    """Tests for ControlEventDispatchRepository."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return ControlEventDispatchRepository(mock_session)

    @pytest.mark.asyncio
    async def test_claim_or_skip_new_dispatch(self, repo, mock_session):
        """claim_or_skip() returns dispatch id when INSERT succeeds (new row)."""
        dispatch_id = uuid4()
        mock_row = MagicMock()
        mock_row.id = dispatch_id

        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=mock_row)
        mock_session.execute.return_value = mock_result

        result = await repo.claim_or_skip(uuid4(), uuid4())

        assert result == dispatch_id
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_or_skip_already_succeeded(self, repo, mock_session):
        """claim_or_skip() returns None when dispatch already succeeded (skip)."""
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.claim_or_skip(uuid4(), uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_claim_or_skip_failed_dispatch_retried(self, repo, mock_session):
        """claim_or_skip() returns dispatch id when failed dispatch is retried."""
        dispatch_id = uuid4()
        mock_row = MagicMock()
        mock_row.id = dispatch_id

        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=mock_row)
        mock_session.execute.return_value = mock_result

        result = await repo.claim_or_skip(uuid4(), uuid4())

        assert result == dispatch_id

    @pytest.mark.asyncio
    async def test_claim_or_skip_concurrent_running_skipped(self, repo, mock_session):
        """claim_or_skip() returns None when another worker is already running (skip)."""
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.claim_or_skip(uuid4(), uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_mark_completed_updates_status(self, repo, mock_session):
        """mark_completed() issues UPDATE setting status to succeeded."""
        await repo.mark_completed(uuid4())
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_updates_status(self, repo, mock_session):
        """mark_failed() issues UPDATE setting status to failed."""
        await repo.mark_failed(uuid4())
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_for_event_removes_rows(self, repo, mock_session):
        """delete_for_event() deletes all dispatch rows for the given event."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await repo.delete_for_event(uuid4())

        assert count == 3
        mock_session.execute.assert_called_once()
