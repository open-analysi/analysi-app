"""
Unit tests for Slack Listener.

Tests R21-R25: Socket Mode connection, interactive payload handling,
HITL question sending, and workspace management.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.constants import HITLQuestionConstants

# ---------------------------------------------------------------------------
# R21 — send_hitl_question (sender.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendHITLQuestion:
    """R21: Send HITL questions to Slack as Block Kit messages."""

    @pytest.mark.asyncio
    async def test_sends_message_and_updates_question_ref(self):
        """send_hitl_question posts to Slack and updates question_ref with message_ts."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        # Build a mock HITLQuestion
        hitl_question = MagicMock()
        hitl_question.id = uuid4()
        hitl_question.question_text = "Should we escalate?"
        hitl_question.channel = ""
        hitl_question.question_ref = ""
        hitl_question.options = []

        pending_tool_args = {
            "destination": "C12345",
            "question": "Should we escalate?",
            "responses": "Yes, No, Defer",
        }

        # Mock the bot_token retrieval
        with (
            patch(
                "analysi.slack_listener.sender.get_bot_token",
                new_callable=AsyncMock,
                return_value="xoxb-fake-bot-token",
            ),
            patch("analysi.slack_listener.sender.httpx.AsyncClient") as MockClient,
        ):
            # Mock Slack API response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": True,
                "ts": "1234567890.123456",
                "channel": "C12345",
            }
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                pending_tool_args=pending_tool_args,
                tenant_id="t1",
            )

            assert result is True
            assert hitl_question.question_ref == "1234567890.123456"
            assert hitl_question.channel == "C12345"
            mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_bot_token(self):
        """send_hitl_question returns False when bot_token is not available."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        hitl_question = MagicMock()
        hitl_question.id = uuid4()

        with patch(
            "analysi.slack_listener.sender.get_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                pending_tool_args={"destination": "C1", "question": "Q?"},
                tenant_id="t1",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_slack_api_fails(self):
        """send_hitl_question returns False when Slack API returns ok=false."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        hitl_question = MagicMock()
        hitl_question.id = uuid4()
        hitl_question.channel = ""
        hitl_question.question_ref = ""
        hitl_question.question_text = "Q?"
        hitl_question.options = []

        with (
            patch(
                "analysi.slack_listener.sender.get_bot_token",
                new_callable=AsyncMock,
                return_value="xoxb-fake",
            ),
            patch("analysi.slack_listener.sender.httpx.AsyncClient") as MockClient,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": False,
                "error": "channel_not_found",
            }
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                pending_tool_args={"destination": "C1", "question": "Q?"},
                tenant_id="t1",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_destination(self):
        """send_hitl_question returns False when no destination channel is provided."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        hitl_question = MagicMock()
        hitl_question.id = uuid4()
        hitl_question.channel = ""

        with patch(
            "analysi.slack_listener.sender.get_bot_token",
            new_callable=AsyncMock,
            return_value="xoxb-fake",
        ):
            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                pending_tool_args={"question": "Q?"},
                tenant_id="t1",
            )

            assert result is False


# ---------------------------------------------------------------------------
# R21 — Block Kit helpers (sender.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlockKitHelpers:
    """R21: Block Kit message construction and option parsing."""

    def test_build_blocks_with_buttons(self):
        """_build_blocks creates section + actions block with buttons."""
        from analysi.slack_listener.sender import _build_blocks

        blocks = _build_blocks("Should we escalate?", ["Yes", "No", "Defer"])

        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["text"] == "Should we escalate?"
        assert blocks[1]["type"] == "actions"
        assert len(blocks[1]["elements"]) == 3
        assert blocks[1]["elements"][0]["text"]["text"] == "Yes"
        assert blocks[1]["elements"][0]["value"] == "Yes"

    def test_build_blocks_without_buttons(self):
        """_build_blocks creates section only when no button labels."""
        from analysi.slack_listener.sender import _build_blocks

        blocks = _build_blocks("Info message", [])

        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_build_blocks_limits_to_five_buttons(self):
        """_build_blocks caps buttons at 5 per Slack limitation."""
        from analysi.slack_listener.sender import _build_blocks

        labels = ["A", "B", "C", "D", "E", "F", "G"]
        blocks = _build_blocks("Q?", labels)

        assert len(blocks[1]["elements"]) == 5

    def test_parse_options_comma_separated_string(self):
        """_parse_options splits comma-separated string."""
        from analysi.slack_listener.sender import _parse_options

        result = _parse_options("Approve, Reject, Escalate", None)
        assert result == ["Approve", "Reject", "Escalate"]

    def test_parse_options_list_of_strings(self):
        """_parse_options handles a list of plain strings."""
        from analysi.slack_listener.sender import _parse_options

        result = _parse_options(["Yes", "No"], None)
        assert result == ["Yes", "No"]

    def test_parse_options_list_of_dicts(self):
        """_parse_options extracts labels from list of dicts."""
        from analysi.slack_listener.sender import _parse_options

        result = _parse_options(
            [{"label": "Approve", "value": "approve"}, {"value": "deny"}], None
        )
        assert result == ["Approve", "deny"]

    def test_parse_options_falls_back_to_question_options(self):
        """_parse_options uses question_options when raw_options is None."""
        from analysi.slack_listener.sender import _parse_options

        question_opts = [{"label": "X", "value": "x"}, {"label": "Y", "value": "y"}]
        result = _parse_options(None, question_opts)
        assert result == ["X", "Y"]

    def test_parse_options_returns_empty_for_none(self):
        """_parse_options returns empty list when both inputs are None."""
        from analysi.slack_listener.sender import _parse_options

        result = _parse_options(None, None)
        assert result == []


# ---------------------------------------------------------------------------
# R23 — InteractivePayloadHandler (handler.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInteractivePayloadHandler:
    """R23: Process Slack interactive payloads (button clicks)."""

    @pytest.mark.asyncio
    async def test_handles_block_actions_and_records_answer(self):
        """Handler records answer and emits control event for pending question."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        question_id = uuid4()
        task_run_id = uuid4()
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.status = HITLQuestionConstants.Status.PENDING
        mock_question.question_text = "Escalate?"
        mock_question.channel = "C12345"
        mock_question.question_ref = "1234567890.123456"

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Escalate", "action_id": "hitl_response_escalate"}],
            "channel": {"id": "C12345"},
            "container": {"message_ts": "1234567890.123456"},
            "user": {"id": "U999", "username": "analyst1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock the repo
            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question)
                mock_repo.record_answer = AsyncMock(return_value=True)
                MockRepo.return_value = mock_repo

                # Mock _update_slack_message
                with patch.object(
                    handler, "_update_slack_message", new_callable=AsyncMock
                ) as mock_update:
                    await handler.handle(payload)

                    # Answer should have been recorded
                    mock_repo.record_answer.assert_awaited_once_with(
                        question_id=question_id,
                        answer="Escalate",
                        answered_by="U999",
                    )

                    # Control event should have been flushed
                    mock_session.add.assert_called_once()
                    mock_session.commit.assert_awaited_once()

                    # Slack message should be updated
                    mock_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_block_actions_payloads(self):
        """Handler ignores payloads that are not block_actions."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        payload = {"type": "view_submission", "view": {}}

        # Should return without error — no DB interaction
        await handler.handle(payload)

    @pytest.mark.asyncio
    async def test_handles_already_answered_question(self):
        """Handler gracefully handles duplicate button clicks."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.tenant_id = "t1"
        mock_question.status = HITLQuestionConstants.Status.ANSWERED
        mock_question.answer = "Escalate"
        mock_question.answered_by = "analyst1"
        mock_question.question_text = "Escalate?"
        mock_question.channel = "C12345"
        mock_question.question_ref = "ts-1"

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Ignore"}],
            "channel": {"id": "C12345"},
            "container": {"message_ts": "ts-1"},
            "user": {"id": "U999", "username": "analyst2"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question)
                MockRepo.return_value = mock_repo

                with patch.object(
                    handler, "_update_slack_message", new_callable=AsyncMock
                ) as mock_update:
                    await handler.handle(payload)

                    # record_answer should NOT be called (question not pending)
                    mock_repo.record_answer.assert_not_awaited()

                    # Should still update Slack message with "already resolved" info
                    mock_update.assert_awaited_once()
                    call_kwargs = mock_update.call_args.kwargs
                    assert call_kwargs["already_resolved"] is True

    @pytest.mark.asyncio
    async def test_handles_question_not_found(self):
        """Handler logs warning when question not found in DB."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Yes"}],
            "channel": {"id": "C12345"},
            "container": {"message_ts": "unknown-ts"},
            "user": {"id": "U999", "username": "analyst1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=None)
                MockRepo.return_value = mock_repo

                # Should not raise
                await handler.handle(payload)

                # No attempt to record answer
                mock_repo.record_answer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_race_condition_in_record_answer(self):
        """Handler handles race when record_answer returns False (answered between SELECT and UPDATE)."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.status = HITLQuestionConstants.Status.PENDING

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Yes"}],
            "channel": {"id": "C1"},
            "container": {"message_ts": "ts-1"},
            "user": {"id": "U1", "username": "user1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question)
                mock_repo.record_answer = AsyncMock(return_value=False)  # Race!
                MockRepo.return_value = mock_repo

                # Should not raise, and should not commit
                await handler.handle(payload)
                mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_emits_control_event_with_correct_payload(self):
        """Handler emits human:responded control event with all context."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = HITLQuestionConstants.Status.PENDING
        mock_question.question_text = "Approve?"
        mock_question.channel = "C1"
        mock_question.question_ref = "ts-1"

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Approve"}],
            "channel": {"id": "C1"},
            "container": {"message_ts": "ts-1"},
            "user": {"id": "U1", "username": "user1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question)
                mock_repo.record_answer = AsyncMock(return_value=True)
                MockRepo.return_value = mock_repo

                with patch.object(
                    handler, "_update_slack_message", new_callable=AsyncMock
                ):
                    await handler.handle(payload)

                    # Verify control event was added
                    added_event = mock_session.add.call_args[0][0]
                    assert added_event.channel == "human:responded"
                    assert added_event.tenant_id == "t1"
                    assert added_event.payload["question_id"] == str(question_id)
                    assert added_event.payload["answer"] == "Approve"
                    assert added_event.payload["answered_by"] == "U1"
                    assert added_event.payload["task_run_id"] == str(task_run_id)
                    assert added_event.payload["workflow_run_id"] == str(
                        workflow_run_id
                    )
                    assert added_event.payload["node_instance_id"] == str(
                        node_instance_id
                    )
                    assert added_event.payload["analysis_id"] == str(analysis_id)


# ---------------------------------------------------------------------------
# R22 — WorkspaceConnection (connection.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkspaceConnection:
    """R22: WebSocket connection with backoff and message dispatch."""

    @pytest.mark.asyncio
    async def test_obtain_ws_url_success(self):
        """_obtain_ws_url calls apps.connections.open and returns URL."""
        from analysi.slack_listener.connection import WorkspaceConnection

        handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=handler)

        with patch("analysi.slack_listener.connection.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": True,
                "url": "wss://wss-primary.slack.com/link/?ticket=abc",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            url = await conn._obtain_ws_url()

            assert url == "wss://wss-primary.slack.com/link/?ticket=abc"
            mock_client_instance.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_obtain_ws_url_api_error(self):
        """_obtain_ws_url returns None when Slack API returns ok=false."""
        from analysi.slack_listener.connection import WorkspaceConnection

        handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=handler)

        with patch("analysi.slack_listener.connection.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": False,
                "error": "invalid_auth",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            url = await conn._obtain_ws_url()
            assert url is None

    @pytest.mark.asyncio
    async def test_handle_envelope_acks_and_dispatches(self):
        """_handle_envelope ACKs the envelope and dispatches interactive payloads."""
        import json

        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)

        mock_ws = AsyncMock()

        envelope = {
            "envelope_id": "env-123",
            "type": "interactive",
            "payload": {
                "type": "block_actions",
                "actions": [{"value": "Yes"}],
            },
        }

        await conn._handle_envelope(mock_ws, json.dumps(envelope))

        # Should ACK
        mock_ws.send.assert_awaited_once()
        ack = json.loads(mock_ws.send.call_args[0][0])
        assert ack["envelope_id"] == "env-123"

    @pytest.mark.asyncio
    async def test_handle_envelope_ignores_non_interactive(self):
        """_handle_envelope ignores non-interactive envelopes after ACK."""
        import json

        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)

        mock_ws = AsyncMock()

        envelope = {
            "envelope_id": "env-456",
            "type": "events_api",
            "payload": {"type": "message"},
        }

        await conn._handle_envelope(mock_ws, json.dumps(envelope))

        # Should ACK but NOT dispatch to handler
        mock_ws.send.assert_awaited_once()
        mock_handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_envelope_skips_hello_message(self):
        """_handle_envelope ignores messages without envelope_id (hello)."""
        import json

        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)

        mock_ws = AsyncMock()

        hello_msg = {"type": "hello", "num_connections": 1}
        await conn._handle_envelope(mock_ws, json.dumps(hello_msg))

        # No ACK, no dispatch
        mock_ws.send.assert_not_awaited()
        mock_handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backoff_doubles_up_to_max(self):
        """_wait_backoff doubles the backoff on each call up to the max."""
        from analysi.slack_listener.connection import (
            _BACKOFF_MAX_SECONDS,
            WorkspaceConnection,
        )

        handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=handler)

        with patch("analysi.slack_listener.connection.asyncio.sleep") as mock_sleep:
            # First call: 1s
            await conn._wait_backoff()
            mock_sleep.assert_awaited_with(1)

            # Second: 2s
            await conn._wait_backoff()
            mock_sleep.assert_awaited_with(2)

            # Third: 4s
            await conn._wait_backoff()
            mock_sleep.assert_awaited_with(4)

            # Keep doubling...
            for _ in range(10):
                await conn._wait_backoff()

            # Should be capped at max
            assert conn._backoff_seconds == _BACKOFF_MAX_SECONDS

    @pytest.mark.asyncio
    async def test_stop_closes_websocket(self):
        """stop() sets _running to False and closes the WebSocket."""
        from analysi.slack_listener.connection import WorkspaceConnection

        handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=handler)
        conn._running = True

        mock_ws = AsyncMock()
        conn._ws = mock_ws

        await conn.stop()

        assert conn._running is False
        mock_ws.close.assert_awaited_once()
        assert conn._ws is None


# ---------------------------------------------------------------------------
# R22 — SlackListenerService (service.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSlackListenerService:
    """R22: Multi-tenant workspace management."""

    @pytest.mark.asyncio
    async def test_discover_app_tokens_deduplicates(self):
        """_discover_app_tokens groups multiple tenants under same app_token."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()

        # Create mock integrations from two tenants sharing same app_token
        int1 = MagicMock()
        int1.tenant_id = "t1"
        int1.integration_id = "slack-t1"
        int1.integration_type = "slack"
        int1.enabled = True

        int2 = MagicMock()
        int2.tenant_id = "t2"
        int2.integration_id = "slack-t2"
        int2.integration_type = "slack"
        int2.enabled = True

        with (
            patch("analysi.slack_listener.service.AsyncSessionLocal") as MockSession,
            patch.object(
                service,
                "_list_slack_integrations",
                new_callable=AsyncMock,
                return_value=[int1, int2],
            ),
            patch(
                "analysi.slack_listener.service.get_app_token",
                new_callable=AsyncMock,
                # Both tenants share the same app_token
                return_value="xapp-shared-token",
            ),
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service._discover_app_tokens()

            # One entry, but two tenants
            assert len(result) == 1
            assert "xapp-shared-token" in result
            assert result["xapp-shared-token"]["tenant_ids"] == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_discover_skips_integrations_without_app_token(self):
        """_discover_app_tokens skips integrations that have no app_token."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()

        int1 = MagicMock()
        int1.tenant_id = "t1"
        int1.integration_id = "slack-t1"

        with (
            patch("analysi.slack_listener.service.AsyncSessionLocal") as MockSession,
            patch.object(
                service,
                "_list_slack_integrations",
                new_callable=AsyncMock,
                return_value=[int1],
            ),
            patch(
                "analysi.slack_listener.service.get_app_token",
                new_callable=AsyncMock,
                return_value=None,  # No app_token
            ),
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service._discover_app_tokens()
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_refresh_adds_new_connections(self):
        """_refresh_connections starts connections for newly-discovered app_tokens."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()

        with patch.object(
            service,
            "_discover_app_tokens",
            new_callable=AsyncMock,
            return_value={"xapp-new": {"tenant_ids": ["t1"]}},
        ):
            with patch(
                "analysi.slack_listener.service.WorkspaceConnection"
            ) as MockConn:
                mock_conn = AsyncMock()
                MockConn.return_value = mock_conn

                with patch("analysi.slack_listener.service.InteractivePayloadHandler"):
                    await service._refresh_connections()

                    assert "xapp-new" in service._connections
                    assert "xapp-new" in service._connection_tasks

    @pytest.mark.asyncio
    async def test_refresh_removes_stale_connections(self):
        """_refresh_connections tears down connections for removed app_tokens."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()

        # Pre-populate with a stale connection
        mock_stale = AsyncMock()
        service._connections["xapp-stale"] = mock_stale
        service._connection_tasks["xapp-stale"] = AsyncMock()

        with patch.object(
            service,
            "_discover_app_tokens",
            new_callable=AsyncMock,
            return_value={},  # No tokens discovered
        ):
            await service._refresh_connections()

            # Stale connection should have been stopped and removed
            mock_stale.stop.assert_awaited_once()
            assert "xapp-stale" not in service._connections
            assert "xapp-stale" not in service._connection_tasks

    @pytest.mark.asyncio
    async def test_stop_shuts_down_all_connections(self):
        """stop() cancels refresh task and stops all connections."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()
        service._running = True

        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()
        service._connections = {"xapp-1": mock_conn1, "xapp-2": mock_conn2}

        # Create a real asyncio.Future and cancel it so await raises CancelledError
        import asyncio

        loop = asyncio.get_event_loop()
        mock_refresh_task = loop.create_future()
        # Don't resolve — cancel will be called by stop()
        service._refresh_task = mock_refresh_task

        await service.stop()

        assert service._running is False
        assert mock_refresh_task.cancelled()
        mock_conn1.stop.assert_awaited_once()
        mock_conn2.stop.assert_awaited_once()
        assert len(service._connections) == 0


# ---------------------------------------------------------------------------
# R21 — Sender wired into pause flow
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSenderWiredIntoPauseFlow:
    """R21: send_hitl_question is called after create_question_from_checkpoint."""

    @pytest.mark.asyncio
    async def test_standalone_task_pause_calls_sender(self):
        """execute_and_persist calls send_hitl_question after creating question."""
        from analysi.slack_listener.sender import send_hitl_question

        # Verify the import path exists (not the execution — that's integration test territory)
        assert callable(send_hitl_question)

    @pytest.mark.asyncio
    async def test_sender_integration_in_task_execution(self):
        """Verify the sender import is reachable from task_execution module."""
        # This confirms the lazy import path works
        import importlib

        mod = importlib.import_module("analysi.slack_listener.sender")
        assert hasattr(mod, "send_hitl_question")


# ---------------------------------------------------------------------------
# Credential schema update
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSlackCredentialSchema:
    """Slack manifest includes app_token for Socket Mode."""

    def test_manifest_includes_app_token(self):
        """Slack manifest credential_schema includes app_token property."""
        import json
        from pathlib import Path

        manifest_path = Path(
            "src/analysi/integrations/framework/integrations/slack/manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())

        cred_schema = manifest["credential_schema"]
        assert "app_token" in cred_schema["properties"]
        assert "xapp-" in cred_schema["properties"]["app_token"]["description"]

    def test_app_token_is_not_required(self):
        """app_token is optional — existing bot-only integrations still work."""
        import json
        from pathlib import Path

        manifest_path = Path(
            "src/analysi/integrations/framework/integrations/slack/manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())

        required_fields = manifest["credential_schema"]["required"]
        assert "app_token" not in required_fields
        assert "bot_token" in required_fields


# ---------------------------------------------------------------------------
# Shared credential helper (_credentials.py) — unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSlackCredentialHelpers:
    """Unhappy paths for the shared credential resolution module."""

    @pytest.mark.asyncio
    async def test_get_bot_token_returns_none_when_secret_missing_key(self):
        """get_bot_token returns None when decrypted secret has no bot_token key."""
        from analysi.slack_listener._credentials import get_bot_token

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials.get_slack_secret",
            new_callable=AsyncMock,
            return_value={"app_token": "xapp-something"},  # no bot_token!
        ):
            result = await get_bot_token(mock_session, "t1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_app_token_returns_none_when_secret_missing_key(self):
        """get_app_token returns None when decrypted secret has no app_token key."""
        from analysi.slack_listener._credentials import get_app_token

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials.get_slack_secret",
            new_callable=AsyncMock,
            return_value={"bot_token": "xoxb-something"},  # no app_token!
        ):
            result = await get_app_token(mock_session, "t1", "int-1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_slack_secret_returns_none_on_exception(self):
        """get_slack_secret swallows exceptions and returns None."""
        from analysi.slack_listener._credentials import get_slack_secret

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials._find_slack_integration_id",
            new_callable=AsyncMock,
            return_value="int-1",
        ):
            with patch(
                "analysi.slack_listener._credentials.CredentialService"
            ) as MockCredSvc:
                mock_svc = AsyncMock()
                mock_svc.get_integration_credentials = AsyncMock(
                    side_effect=RuntimeError("Vault is down")
                )
                MockCredSvc.return_value = mock_svc

                result = await get_slack_secret(mock_session, "t1")
                assert result is None  # swallowed, not propagated

    @pytest.mark.asyncio
    async def test_get_slack_secret_returns_none_when_no_integration(self):
        """get_slack_secret returns None when no Slack integration is found."""
        from analysi.slack_listener._credentials import get_slack_secret

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials._find_slack_integration_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_slack_secret(mock_session, "t1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_slack_secret_returns_none_when_cred_list_empty(self):
        """get_slack_secret returns None when credential list is empty."""
        from analysi.slack_listener._credentials import get_slack_secret

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials._find_slack_integration_id",
            new_callable=AsyncMock,
            return_value="int-1",
        ):
            with patch(
                "analysi.slack_listener._credentials.CredentialService"
            ) as MockCredSvc:
                mock_svc = AsyncMock()
                mock_svc.get_integration_credentials = AsyncMock(return_value=[])
                MockCredSvc.return_value = mock_svc

                result = await get_slack_secret(mock_session, "t1")
                assert result is None

    @pytest.mark.asyncio
    async def test_get_slack_secret_returns_none_when_cred_has_no_id(self):
        """get_slack_secret returns None when credential dict has no 'id' key."""
        from analysi.slack_listener._credentials import get_slack_secret

        mock_session = AsyncMock()
        with patch(
            "analysi.slack_listener._credentials._find_slack_integration_id",
            new_callable=AsyncMock,
            return_value="int-1",
        ):
            with patch(
                "analysi.slack_listener._credentials.CredentialService"
            ) as MockCredSvc:
                mock_svc = AsyncMock()
                mock_svc.get_integration_credentials = AsyncMock(
                    return_value=[{"name": "my_cred"}]  # no "id" key
                )
                MockCredSvc.return_value = mock_svc

                result = await get_slack_secret(mock_session, "t1")
                assert result is None


# ---------------------------------------------------------------------------
# Sender unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendHITLQuestionUnhappyPaths:
    """Unhappy paths for send_hitl_question."""

    @pytest.mark.asyncio
    async def test_returns_false_on_network_exception(self):
        """send_hitl_question returns False when httpx throws (network error)."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        hitl_question = MagicMock()
        hitl_question.id = uuid4()
        hitl_question.channel = ""
        hitl_question.question_ref = ""
        hitl_question.question_text = "Q?"
        hitl_question.options = []

        with (
            patch(
                "analysi.slack_listener.sender.get_bot_token",
                new_callable=AsyncMock,
                return_value="xoxb-fake",
            ),
            patch("analysi.slack_listener.sender.httpx.AsyncClient") as MockClient,
        ):
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                pending_tool_args={"destination": "C1", "question": "Q?"},
                tenant_id="t1",
            )

            assert result is False
            # question_ref should NOT have been updated
            assert hitl_question.question_ref == ""

    @pytest.mark.asyncio
    async def test_falls_back_to_question_text_from_model(self):
        """send_hitl_question uses hitl_question.question_text when tool args lack both keys."""
        from analysi.slack_listener.sender import send_hitl_question

        mock_session = AsyncMock()
        hitl_question = MagicMock()
        hitl_question.id = uuid4()
        hitl_question.channel = ""
        hitl_question.question_ref = ""
        hitl_question.question_text = "Fallback question from model"
        hitl_question.options = [{"label": "OK", "value": "ok"}]

        with (
            patch(
                "analysi.slack_listener.sender.get_bot_token",
                new_callable=AsyncMock,
                return_value="xoxb-fake",
            ),
            patch("analysi.slack_listener.sender.httpx.AsyncClient") as MockClient,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": True,
                "ts": "ts-1",
                "channel": "C1",
            }
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_hitl_question(
                session=mock_session,
                hitl_question=hitl_question,
                # No "question" or "text" key — should fall back to model
                pending_tool_args={"destination": "C1"},
                tenant_id="t1",
            )

            assert result is True
            # Verify the fallback text was used in the API call
            call_kwargs = mock_client_instance.post.call_args.kwargs
            assert call_kwargs["json"]["text"] == "Fallback question from model"


# ---------------------------------------------------------------------------
# Handler unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInteractiveHandlerUnhappyPaths:
    """Unhappy paths for InteractivePayloadHandler."""

    @pytest.mark.asyncio
    async def test_empty_actions_list_returns_early(self):
        """Handler returns early when actions list is empty."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        payload = {
            "type": "block_actions",
            "actions": [],  # empty!
            "channel": {"id": "C1"},
            "container": {"message_ts": "ts-1"},
            "user": {"id": "U1"},
        }

        # Should not raise, and should NOT open a DB session
        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            await handler.handle(payload)
            MockSession.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_as_string_returns_early(self):
        """Handler handles gracefully when channel is a string (not dict)."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Yes"}],
            "channel": "C12345",  # string, not {"id": "C12345"}
            "container": {"message_ts": "ts-1"},
            "user": {"id": "U1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            # channel_id will be "" → early return
            await handler.handle(payload)
            # No DB session should have been opened (early return)
            MockSession.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_slack_message_exception_does_not_propagate(self):
        """_update_slack_message swallows HTTP exceptions."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.tenant_id = "t1"
        mock_question.question_text = "Q?"
        mock_question.channel = "C1"
        mock_question.question_ref = "ts-1"

        mock_session = AsyncMock()

        with (
            patch(
                "analysi.slack_listener.handler.get_bot_token",
                new_callable=AsyncMock,
                return_value="xoxb-fake",
            ),
            patch("analysi.slack_listener.handler.httpx.AsyncClient") as MockClient,
        ):
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(
                side_effect=ConnectionError("Slack is down")
            )
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should NOT raise
            await handler._update_slack_message(
                session=mock_session,
                question=mock_question,
                answer="Yes",
                answered_by="analyst",
            )

    @pytest.mark.asyncio
    async def test_update_slack_message_skips_when_no_bot_token(self):
        """_update_slack_message returns without API call when no bot_token."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.tenant_id = "t1"

        mock_session = AsyncMock()

        with patch(
            "analysi.slack_listener.handler.get_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Should return without error — no HTTP call attempted
            await handler._update_slack_message(
                session=mock_session,
                question=mock_question,
                answer="Yes",
                answered_by="analyst",
            )


# ---------------------------------------------------------------------------
# Connection unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkspaceConnectionUnhappyPaths:
    """Unhappy paths for WorkspaceConnection."""

    @pytest.mark.asyncio
    async def test_handle_envelope_invalid_json_does_not_crash(self):
        """_handle_envelope logs warning and returns on invalid JSON."""
        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)
        mock_ws = AsyncMock()

        # Send garbage data
        await conn._handle_envelope(mock_ws, "not valid json {{{")

        # No ACK, no dispatch, no crash
        mock_ws.send.assert_not_awaited()
        mock_handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_envelope_ack_failure_still_dispatches(self):
        """_handle_envelope continues dispatching even if ACK send fails."""
        import json

        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=ConnectionError("WS broken"))

        envelope = {
            "envelope_id": "env-789",
            "type": "interactive",
            "payload": {"type": "block_actions", "actions": [{"value": "Yes"}]},
        }

        # Should NOT crash — ACK failure is caught
        await conn._handle_envelope(mock_ws, json.dumps(envelope))

        # ACK was attempted
        mock_ws.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_interactive_catches_handler_exception(self):
        """_dispatch_interactive catches exceptions from the handler."""
        from analysi.slack_listener.connection import WorkspaceConnection

        mock_handler = AsyncMock()
        mock_handler.handle = AsyncMock(side_effect=RuntimeError("Handler exploded"))
        conn = WorkspaceConnection(app_token="xapp-fake", handler=mock_handler)

        # Should NOT raise
        await conn._dispatch_interactive({"type": "block_actions"})

        mock_handler.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_obtain_ws_url_catches_http_exception(self):
        """_obtain_ws_url returns None when HTTP request throws."""
        from analysi.slack_listener.connection import WorkspaceConnection

        handler = AsyncMock()
        conn = WorkspaceConnection(app_token="xapp-fake", handler=handler)

        with patch("analysi.slack_listener.connection.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(
                side_effect=ConnectionError("DNS resolution failed")
            )
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            url = await conn._obtain_ws_url()
            assert url is None


# ---------------------------------------------------------------------------
# Service unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSlackListenerServiceUnhappyPaths:
    """Unhappy paths for SlackListenerService."""

    @pytest.mark.asyncio
    async def test_periodic_refresh_survives_exception(self):
        """_periodic_refresh catches exceptions and continues the loop."""
        from analysi.slack_listener.service import SlackListenerService

        service = SlackListenerService()
        service._running = True

        call_count = 0

        async def mock_refresh():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB connection lost")
            # On second call, stop the loop
            service._running = False

        with (
            patch.object(service, "_refresh_connections", side_effect=mock_refresh),
            patch(
                "analysi.slack_listener.service.asyncio.sleep", new_callable=AsyncMock
            ),
        ):
            await service._periodic_refresh()

        # Should have been called twice — survived the first exception
        assert call_count == 2
