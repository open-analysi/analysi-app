"""Integration tests for control event bus jobs."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.jobs.control_events import (
    consume_control_events,
    execute_control_event,
)
from analysi.db.session import AsyncSessionLocal
from analysi.repositories.control_event_repository import (
    ControlEventDispatchRepository,
    ControlEventRepository,
    ControlEventRuleRepository,
)


async def _insert_event(tenant_id: str, channel: str = "disposition:ready"):
    """Insert a control event and return it."""
    async with AsyncSessionLocal() as session:
        repo = ControlEventRepository(session)
        event = await repo.insert(
            tenant_id=tenant_id,
            channel=channel,
            payload={"alert_id": str(uuid4())},
        )
        await session.commit()
        return event


async def _insert_rule(tenant_id: str, channel: str = "disposition:ready"):
    """Insert a control event rule and return it."""
    async with AsyncSessionLocal() as session:
        repo = ControlEventRuleRepository(session)
        rule = await repo.create(
            tenant_id=tenant_id,
            channel=channel,
            target_type="task",
            target_id=uuid4(),
            name=f"test-rule-{uuid4().hex[:8]}",
        )
        await session.commit()
        return rule


async def _get_event(event_id):
    """Fetch event by id."""
    async with AsyncSessionLocal() as session:
        repo = ControlEventRepository(session)
        return await repo.get_by_id(event_id)


async def _count_dispatches(event_id):
    """Count dispatch rows for an event."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM control_event_dispatches WHERE control_event_id = :eid"
            ),
            {"eid": event_id},
        )
        return result.scalar()


# ---------------------------------------------------------------------------
# Test 1: all rules succeed → event marked processed, dispatch rows deleted
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_all_rules_succeed_marks_event_processed():
    """Two rules succeed → event marked processed, dispatch rows deleted."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    event = await _insert_event(tenant_id)
    rule1 = await _insert_rule(tenant_id)
    rule2 = await _insert_rule(tenant_id)

    rule_ids_executed = []

    async def fake_execute_rule(ev, rule):
        rule_ids_executed.append(rule.id)

    with patch(
        "analysi.alert_analysis.jobs.control_events.execute_rule",
        side_effect=fake_execute_rule,
    ):
        result = await execute_control_event({}, str(event.id), tenant_id)

    assert result["status"] == "completed"
    assert result["rules_executed"] == 2
    assert set(rule_ids_executed) == {rule1.id, rule2.id}

    # Event must be processed in DB
    reloaded = await _get_event(event.id)
    assert reloaded.status == "completed"

    # Dispatch rows must be cleaned up
    count = await _count_dispatches(event.id)
    assert count == 0


# ---------------------------------------------------------------------------
# Test 2: retry scenario — one rule already succeeded → skipped
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_skips_already_succeeded_rule_on_retry():
    """Idempotency: a rule with a 'completed' dispatch is skipped on retry."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    event = await _insert_event(tenant_id)
    rule_skip = await _insert_rule(tenant_id)
    rule_rerun = await _insert_rule(tenant_id)

    # Pre-seed rule_skip as already succeeded
    async with AsyncSessionLocal() as session:
        dispatch_repo = ControlEventDispatchRepository(session)
        dispatch_id = await dispatch_repo.claim_or_skip(event.id, rule_skip.id)
        await session.commit()

    async with AsyncSessionLocal() as session:
        dispatch_repo = ControlEventDispatchRepository(session)
        await dispatch_repo.mark_completed(dispatch_id)
        await session.commit()

    executed_rule_ids = []

    async def fake_execute_rule(ev, rule):
        executed_rule_ids.append(rule.id)

    with patch(
        "analysi.alert_analysis.jobs.control_events.execute_rule",
        side_effect=fake_execute_rule,
    ):
        result = await execute_control_event({}, str(event.id), tenant_id)

    # Only rule_rerun should have been executed
    assert rule_skip.id not in executed_rule_ids
    assert rule_rerun.id in executed_rule_ids

    assert result["status"] == "completed"
    reloaded = await _get_event(event.id)
    assert reloaded.status == "completed"


# ---------------------------------------------------------------------------
# Test 3: one rule fails → event marked failed, retry_count incremented
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_one_rule_fails_marks_event_failed_and_increments_retry():
    """A failing rule → event marked failed, retry_count incremented."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    event = await _insert_event(tenant_id)
    await _insert_rule(tenant_id)

    async def fake_execute_rule(ev, rule):
        raise RuntimeError("simulated rule failure")

    with patch(
        "analysi.alert_analysis.jobs.control_events.execute_rule",
        side_effect=fake_execute_rule,
    ):
        # execute_control_event now raises RuntimeError on rule failure
        with pytest.raises(RuntimeError, match="1 rule\\(s\\) failed"):
            await execute_control_event({}, str(event.id), tenant_id)

    # DB state should still be updated before the raise
    reloaded = await _get_event(event.id)
    assert reloaded.status == "failed"
    assert reloaded.retry_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_event_stays_failed_after_max_retries():
    """After MAX_CONTROL_EVENT_RETRIES, the event stays failed and cron skips it."""
    from analysi.alert_analysis.config import AlertAnalysisConfig

    tenant_id = f"test-tenant-{uuid4().hex[:8]}"
    max_retries = AlertAnalysisConfig.MAX_CONTROL_EVENT_RETRIES

    event = await _insert_event(tenant_id)
    await _insert_rule(tenant_id)

    async def fake_execute_rule(ev, rule):
        raise RuntimeError("persistent failure")

    # Simulate MAX_CONTROL_EVENT_RETRIES failures
    with patch(
        "analysi.alert_analysis.jobs.control_events.execute_rule",
        side_effect=fake_execute_rule,
    ):
        for _ in range(max_retries):
            # execute_control_event now raises RuntimeError on rule failure
            with pytest.raises(RuntimeError, match="rule\\(s\\) failed"):
                await execute_control_event({}, str(event.id), tenant_id)

    # After max_retries the retry_count should equal max_retries
    reloaded = await _get_event(event.id)
    assert reloaded.status == "failed"
    assert reloaded.retry_count == max_retries

    # The cron claim_batch should not pick up this event (retry_count >= limit)
    async with AsyncSessionLocal() as session:
        repo = ControlEventRepository(session)
        claimable = await repo.claim_batch(
            batch_size=10,
            max_retries=max_retries,
            stuck_hours=1,
        )
        await session.commit()

    event_ids_claimed = [e.id for e in claimable]
    assert event.id not in event_ids_claimed


# ---------------------------------------------------------------------------
# consume_control_events cron
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consume_claims_pending_events_and_enqueues_jobs():
    """consume_control_events claims pending events and enqueues one ARQ job each."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    # Insert two pending events
    async with AsyncSessionLocal() as session:
        repo = ControlEventRepository(session)
        event1 = await repo.insert(
            tenant_id=tenant_id, channel="disposition:ready", payload={}
        )
        event2 = await repo.insert(
            tenant_id=tenant_id, channel="disposition:ready", payload={}
        )
        await session.commit()

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    await consume_control_events(ctx)

    # Both events should have been enqueued
    assert mock_redis.enqueue_job.call_count >= 2
    job_ids = [call.kwargs["_job_id"] for call in mock_redis.enqueue_job.call_args_list]
    # Job IDs must include retry_count (format: "{event_id}:{retry_count}")
    assert any(str(event1.id) in jid for jid in job_ids)
    assert any(str(event2.id) in jid for jid in job_ids)
    # Verify retry_count suffix format
    assert all(":" in jid for jid in job_ids)

    # Events should be in 'claimed' status
    reloaded1 = await _get_event(event1.id)
    reloaded2 = await _get_event(event2.id)
    assert reloaded1.status == "claimed"
    assert reloaded2.status == "claimed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consume_skips_already_claimed_events():
    """consume_control_events does not re-enqueue events already in 'claimed' status."""
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    async with AsyncSessionLocal() as session:
        repo = ControlEventRepository(session)
        await repo.insert(tenant_id=tenant_id, channel="disposition:ready", payload={})
        await session.commit()

    # First consume: claims the event
    mock_redis = AsyncMock()
    await consume_control_events({"redis": mock_redis})
    assert mock_redis.enqueue_job.call_count == 1

    # Second consume: event is still 'claimed', should not be picked up again
    mock_redis2 = AsyncMock()
    await consume_control_events({"redis": mock_redis2})
    mock_redis2.enqueue_job.assert_not_called()
