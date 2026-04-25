"""Unit tests for control event bus jobs."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.jobs.control_events import (
    _run_rule_with_dispatch,
    consume_control_events,
    execute_control_event,
    execute_rule,
)


def _make_event(channel="disposition:ready", retry_count=0):
    event = MagicMock()
    event.id = uuid4()
    event.tenant_id = "tenant-a"
    event.channel = channel
    event.payload = {"alert_id": str(uuid4())}
    event.retry_count = retry_count
    return event


def _make_rule(target_type="task"):
    rule = MagicMock()
    rule.id = uuid4()
    rule.target_id = uuid4()
    rule.target_type = target_type
    rule.config = {}
    return rule


# ---------------------------------------------------------------------------
# consume_control_events
# ---------------------------------------------------------------------------


class TestConsumeControlEvents:
    """Tests for the consume_control_events cron."""

    @pytest.mark.asyncio
    async def test_no_events_returns_zero_dispatched(self):
        """No pending events → nothing enqueued."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_repo = AsyncMock()
            mock_repo.claim_batch.return_value = []

            with patch(
                "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                return_value=mock_repo,
            ):
                result = await consume_control_events(ctx)

        assert result["dispatched"] == 0
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_claims_and_enqueues_events(self):
        """Two pending events → two enqueue_job calls."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}
        events = [_make_event(), _make_event()]

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_repo = AsyncMock()
            mock_repo.claim_batch.return_value = events

            with patch(
                "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                return_value=mock_repo,
            ):
                result = await consume_control_events(ctx)

        assert result["dispatched"] == 2
        assert mock_redis.enqueue_job.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_attempt_job_id_for_idempotency(self):
        """_job_id is {event_id}:{retry_count} so each retry gets its own Valkey slot."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}
        event = _make_event(retry_count=0)

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_repo = AsyncMock()
            mock_repo.claim_batch.return_value = [event]

            with patch(
                "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                return_value=mock_repo,
            ):
                await consume_control_events(ctx)

        call_kwargs = mock_redis.enqueue_job.call_args[1]
        assert call_kwargs["_job_id"] == f"{event.id}:{event.retry_count}"


# ---------------------------------------------------------------------------
# execute_control_event
# ---------------------------------------------------------------------------


class TestExecuteControlEvent:
    """Tests for the execute_control_event ARQ job."""

    def _patch_session(self, events=None, rules=None):
        """Helper to patch AsyncSessionLocal returning a mock session."""
        return patch("analysi.alert_analysis.jobs.control_events.AsyncSessionLocal")

    @pytest.mark.asyncio
    async def test_event_not_found_raises(self):
        """Non-existent event_id raises ValueError."""
        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_event_repo = AsyncMock()
            mock_event_repo.get_by_id.return_value = None
            mock_rule_repo = AsyncMock()
            mock_rule_repo.list_by_channel.return_value = []

            with (
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                    return_value=mock_event_repo,
                ),
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventRuleRepository",
                    return_value=mock_rule_repo,
                ),
            ):
                with pytest.raises(ValueError, match="not found"):
                    await execute_control_event({}, str(uuid4()), "tenant-a")

    @pytest.mark.asyncio
    async def test_no_rules_marks_event_processed(self):
        """Event with no configured rules is marked processed immediately."""
        event = _make_event()

        session_call_count = 0
        sessions = []

        def make_session():
            nonlocal session_call_count
            s = AsyncMock()
            s.__aenter__ = AsyncMock(return_value=s)
            s.__aexit__ = AsyncMock(return_value=False)
            sessions.append(s)
            return s

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
            side_effect=make_session,
        ):
            mock_event_repo = AsyncMock()
            mock_event_repo.get_by_id.return_value = event
            mock_rule_repo = AsyncMock()
            mock_rule_repo.list_by_channel.return_value = []

            with (
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                    return_value=mock_event_repo,
                ),
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventRuleRepository",
                    return_value=mock_rule_repo,
                ),
            ):
                result = await execute_control_event({}, str(event.id), event.tenant_id)

        assert result["status"] == "completed"
        assert result["rules_executed"] == 0

    @pytest.mark.asyncio
    async def test_all_rules_succeed_marks_completed(self):
        """All rules succeeding marks event completed and deletes dispatches."""
        event = _make_event()
        rules = [_make_rule(), _make_rule()]

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events._run_rule_with_dispatch",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "analysi.alert_analysis.jobs.control_events.asyncio.gather",
                new_callable=AsyncMock,
                return_value=[None, None],
            ),
        ):
            with patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
            ) as mock_sl:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_sl.return_value = mock_session

                mock_event_repo = AsyncMock()
                mock_event_repo.get_by_id.return_value = event
                mock_rule_repo = AsyncMock()
                mock_rule_repo.list_by_channel.return_value = rules
                mock_dispatch_repo = AsyncMock()

                with (
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                        return_value=mock_event_repo,
                    ),
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventRuleRepository",
                        return_value=mock_rule_repo,
                    ),
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventDispatchRepository",
                        return_value=mock_dispatch_repo,
                    ),
                ):
                    result = await execute_control_event(
                        {}, str(event.id), event.tenant_id
                    )

        assert result["status"] == "completed"
        assert result["rules_executed"] == 2

    @pytest.mark.asyncio
    async def test_failed_rule_marks_event_failed(self):
        """One rule failing marks the event as failed and increments retry_count."""
        event = _make_event()
        rules = [_make_rule()]

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.asyncio.gather",
                new_callable=AsyncMock,
                return_value=[RuntimeError("rule failed")],
            ),
        ):
            with patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
            ) as mock_sl:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_sl.return_value = mock_session

                mock_event_repo = AsyncMock()
                mock_event_repo.get_by_id.return_value = event
                mock_rule_repo = AsyncMock()
                mock_rule_repo.list_by_channel.return_value = rules
                mock_dispatch_repo = AsyncMock()

                with (
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventRepository",
                        return_value=mock_event_repo,
                    ),
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventRuleRepository",
                        return_value=mock_rule_repo,
                    ),
                    patch(
                        "analysi.alert_analysis.jobs.control_events.ControlEventDispatchRepository",
                        return_value=mock_dispatch_repo,
                    ),
                ):
                    with pytest.raises(RuntimeError, match="1 rule.*failed"):
                        await execute_control_event({}, str(event.id), event.tenant_id)

        mock_event_repo.mark_failed.assert_called_once_with(event)


# ---------------------------------------------------------------------------
# _run_rule_with_dispatch
# ---------------------------------------------------------------------------


class TestRunRuleWithDispatch:
    """Tests for _run_rule_with_dispatch helper."""

    @pytest.mark.asyncio
    async def test_skips_when_dispatch_already_succeeded(self):
        """claim_or_skip returning None means dispatch already succeeded — skip."""
        event = _make_event()
        rule = _make_rule()

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_dispatch_repo = AsyncMock()
            mock_dispatch_repo.claim_or_skip.return_value = None

            with (
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventDispatchRepository",
                    return_value=mock_dispatch_repo,
                ),
                patch(
                    "analysi.alert_analysis.jobs.control_events.execute_rule",
                    new_callable=AsyncMock,
                ) as mock_execute_rule,
            ):
                await _run_rule_with_dispatch(event, rule)

        mock_execute_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_and_marks_succeeded_on_success(self):
        """Successful execute_rule marks dispatch succeeded."""
        event = _make_event()
        rule = _make_rule()
        dispatch_id = uuid4()

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_dispatch_repo = AsyncMock()
            mock_dispatch_repo.claim_or_skip.return_value = dispatch_id

            with (
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventDispatchRepository",
                    return_value=mock_dispatch_repo,
                ),
                patch(
                    "analysi.alert_analysis.jobs.control_events.execute_rule",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                await _run_rule_with_dispatch(event, rule)

        mock_dispatch_repo.mark_completed.assert_called_once_with(dispatch_id)

    @pytest.mark.asyncio
    async def test_marks_failed_and_reraises_on_rule_error(self):
        """Failed execute_rule marks dispatch failed and re-raises."""
        event = _make_event()
        rule = _make_rule()
        dispatch_id = uuid4()

        with patch(
            "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal"
        ) as mock_sl:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_session

            mock_dispatch_repo = AsyncMock()
            mock_dispatch_repo.claim_or_skip.return_value = dispatch_id

            with (
                patch(
                    "analysi.alert_analysis.jobs.control_events.ControlEventDispatchRepository",
                    return_value=mock_dispatch_repo,
                ),
                patch(
                    "analysi.alert_analysis.jobs.control_events.execute_rule",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("boom"),
                ),
            ):
                with pytest.raises(RuntimeError, match="boom"):
                    await _run_rule_with_dispatch(event, rule)

        mock_dispatch_repo.mark_failed.assert_called_once_with(dispatch_id)


# ---------------------------------------------------------------------------
# execute_rule
# ---------------------------------------------------------------------------


class TestExecuteRule:
    """Tests for execute_rule dispatcher."""

    @pytest.mark.asyncio
    async def test_unknown_target_type_raises(self):
        """Unknown target_type raises ValueError."""
        event = _make_event()
        rule = _make_rule(target_type="unknown")

        with pytest.raises(ValueError, match="Unknown rule target_type"):
            await execute_rule(event, rule)

    @pytest.mark.asyncio
    async def test_task_rule_delegates_to_task_executor(self):
        """task target_type calls _execute_task_rule."""
        event = _make_event()
        rule = _make_rule(target_type="task")

        with patch(
            "analysi.alert_analysis.jobs.control_events._execute_task_rule",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_task:
            await execute_rule(event, rule)

        mock_task.assert_called_once()
        call_kwargs = mock_task.call_args[1]
        assert call_kwargs["tenant_id"] == event.tenant_id
        assert call_kwargs["task_id"] == rule.target_id
        assert call_kwargs["input_data"]["event_id"] == str(event.id)
        assert call_kwargs["execution_context"]["control_event_id"] == str(event.id)

    @pytest.mark.asyncio
    async def test_workflow_rule_delegates_to_workflow_executor(self):
        """workflow target_type calls _execute_workflow_rule."""
        event = _make_event()
        rule = _make_rule(target_type="workflow")

        with patch(
            "analysi.alert_analysis.jobs.control_events._execute_workflow_rule",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_wf:
            await execute_rule(event, rule)

        mock_wf.assert_called_once()
        call_kwargs = mock_wf.call_args[1]
        assert call_kwargs["workflow_id"] == rule.target_id
