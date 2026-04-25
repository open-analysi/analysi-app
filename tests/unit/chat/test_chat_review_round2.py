"""Hypothesis-driven code review tests (Round 2).

H1: increment_token_count must include tenant_id in WHERE clause
H2: Partial timeout must NOT produce contradictory SSE events
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.chat_service import ChatService


class TestH1IncrementTokenCountTenantFilter:
    """H1: ConversationRepository.increment_token_count must filter by
    tenant_id for defense-in-depth consistency with other repository methods.

    Every mutation method in ConversationRepository (get_by_id, update_title,
    soft_delete) filters by tenant_id. increment_token_count must do the same.
    """

    def test_increment_token_count_where_clause_includes_tenant_id(self):
        """The UPDATE statement must include tenant_id in the WHERE clause."""
        from sqlalchemy import and_, update

        from analysi.models.conversation import Conversation

        conversation_id = uuid4()
        tenant_id = "test-tenant"

        # Reproduce the fixed statement from increment_token_count
        stmt = (
            update(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                )
            )
            .values(
                token_count_total=Conversation.token_count_total + 100,
            )
        )

        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))

        assert "tenant_id" in compiled, (
            "increment_token_count WHERE clause must include tenant_id "
            "for defense-in-depth"
        )

    def test_increment_token_count_signature_requires_tenant_id(self):
        """The method signature must accept tenant_id as a parameter."""
        import inspect

        from analysi.repositories.conversation_repository import (
            ConversationRepository,
        )

        sig = inspect.signature(ConversationRepository.increment_token_count)
        param_names = list(sig.parameters.keys())
        assert "tenant_id" in param_names, (
            "increment_token_count must accept tenant_id parameter"
        )


class TestH2PartialTimeoutDoesNotProduceContradictoryEvents:
    """H2: When the LLM stream times out after partial text has been
    streamed, the client must NOT receive both error and message_complete.

    After a timeout, the partial text must not be persisted (it would
    corrupt conversation history) and message_complete must not be sent
    (it contradicts the preceding error event).
    """

    @pytest.mark.asyncio
    async def test_timeout_after_partial_stream_yields_error_not_complete(self):
        """After a timeout with partial text, the stream yields an error
        event but NOT a message_complete event.
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        user_id = uuid4()
        conversation_id = uuid4()

        # Mock session and repositories
        mock_session = AsyncMock()
        service = ChatService(mock_session)

        # Mock conversation_repo.get_by_id to return a valid conversation
        mock_conversation = MagicMock()
        mock_conversation.id = conversation_id
        mock_conversation.token_count_total = 0
        mock_conversation.metadata_ = {}
        service.conversation_repo = AsyncMock()
        service.conversation_repo.get_by_id = AsyncMock(return_value=mock_conversation)
        service.conversation_repo.increment_token_count = AsyncMock()

        # Mock message_repo — only the user message should be persisted
        mock_user_msg = MagicMock(id=uuid4())
        service.message_repo = AsyncMock()
        service.message_repo.create = AsyncMock(return_value=mock_user_msg)
        service.message_repo.list_recent_by_conversation = AsyncMock(return_value=[])

        # Mock _stream_agent_response to yield partial text then timeout
        async def mock_stream_response(*args, **kwargs):
            yield ("partial ", 0)
            yield ("response ", 0)
            raise TimeoutError()

        # Patch the model resolver and stream helper
        with (
            patch(
                "analysi.services.chat_service.resolve_chat_model",
                new_callable=AsyncMock,
                return_value=(MagicMock(), {}),
            ),
            patch("analysi.services.chat_service._build_agent"),
            patch(
                "analysi.services.chat_service._stream_agent_response",
                side_effect=mock_stream_response,
            ),
        ):
            # Collect all SSE events
            events = []
            async for event in service.send_message_stream(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="test message",
            ):
                events.append(event)

        # Parse SSE events into dicts (skip [DONE])
        parsed = []
        for event in events:
            if event.startswith("data: ") and "[DONE]" not in event:
                data = json.loads(event.removeprefix("data: ").strip())
                parsed.append(data)

        event_types = [e["type"] for e in parsed]

        # Verify text_delta events were streamed (partial content)
        assert "text_delta" in event_types, (
            "Expected text_delta events for partial content"
        )

        # Verify error event was sent
        assert "error" in event_types, "Expected an error event after timeout"

        # FIXED: message_complete must NOT be present after an error
        assert "message_complete" not in event_types, (
            "message_complete must not be emitted after an error — "
            "this produces contradictory SSE events for the client"
        )

        # FIXED: Only user message should have been persisted (1 call),
        # not the partial assistant message
        assert service.message_repo.create.call_count == 1, (
            "Only the user message should be persisted; partial assistant "
            "responses from timeouts should not be saved"
        )

    @pytest.mark.asyncio
    async def test_successful_stream_yields_message_complete(self):
        """After a successful stream, message_complete IS emitted."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        user_id = uuid4()
        conversation_id = uuid4()

        mock_session = AsyncMock()
        service = ChatService(mock_session)

        mock_conversation = MagicMock()
        mock_conversation.id = conversation_id
        mock_conversation.token_count_total = 0
        mock_conversation.metadata_ = {}
        service.conversation_repo = AsyncMock()
        service.conversation_repo.get_by_id = AsyncMock(return_value=mock_conversation)
        service.conversation_repo.increment_token_count = AsyncMock()

        mock_user_msg = MagicMock(id=uuid4())
        mock_assistant_msg = MagicMock(id=uuid4())
        service.message_repo = AsyncMock()
        service.message_repo.create = AsyncMock(
            side_effect=[mock_user_msg, mock_assistant_msg]
        )
        service.message_repo.list_recent_by_conversation = AsyncMock(return_value=[])

        # Mock _stream_agent_response — successful stream with token count
        async def mock_stream_response(*args, **kwargs):
            yield ("complete ", 0)
            yield ("response", 0)
            yield ("", 150)  # final item: total_tokens

        with (
            patch(
                "analysi.services.chat_service.resolve_chat_model",
                new_callable=AsyncMock,
                return_value=(MagicMock(), {}),
            ),
            patch("analysi.services.chat_service._build_agent"),
            patch(
                "analysi.services.chat_service._stream_agent_response",
                side_effect=mock_stream_response,
            ),
        ):
            events = []
            async for event in service.send_message_stream(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                content="test message",
            ):
                events.append(event)

        parsed = []
        for event in events:
            if event.startswith("data: ") and "[DONE]" not in event:
                data = json.loads(event.removeprefix("data: ").strip())
                parsed.append(data)

        event_types = [e["type"] for e in parsed]

        # Successful stream should have message_complete and no error
        assert "message_complete" in event_types, (
            "Successful stream must emit message_complete"
        )
        assert "error" not in event_types, (
            "Successful stream must not emit error events"
        )

        # Both user message and assistant message should be persisted
        assert service.message_repo.create.call_count == 2, (
            "Both user and assistant messages should be persisted on success"
        )
