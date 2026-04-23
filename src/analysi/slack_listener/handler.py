"""Handler for Slack interactive payloads (HITL button clicks).

When a user clicks a button on a HITL question message in Slack, this handler:

1. Extracts the ``channel_id``, ``message_ts`` (question_ref), selected action
   value, and ``user_id`` from the ``block_actions`` payload.
2. Looks up the matching ``hitl_questions`` row via ``find_by_ref``.
3. If the question is still pending: records the answer and emits a
   ``human:responded`` control event.
4. If already answered or expired: logs and returns without side effects.
5. Updates the original Slack message to remove buttons and show the response.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.constants import HITLQuestionConstants
from analysi.db.session import AsyncSessionLocal
from analysi.models.control_event import ControlEvent
from analysi.models.hitl_question import HITLQuestion
from analysi.repositories.hitl_repository import HITLQuestionRepository
from analysi.slack_listener._credentials import get_bot_token

logger = get_logger(__name__)

# Slack API endpoint for updating messages
_CHAT_UPDATE_URL = "https://slack.com/api/chat.update"


class InteractivePayloadHandler:
    """Processes ``block_actions`` interactive payloads from Slack."""

    async def handle(self, payload: dict[str, Any]) -> None:
        """Dispatch an interactive payload by type.

        Currently only ``block_actions`` is supported; other types are
        silently ignored.
        """
        payload_type = payload.get("type")
        if payload_type != "block_actions":
            logger.debug(
                "slack_interactive_payload_ignored",
                payload_type=payload_type,
            )
            return

        await self._handle_block_actions(payload)

    # ------------------------------------------------------------------
    # block_actions processing
    # ------------------------------------------------------------------

    async def _handle_block_actions(self, payload: dict[str, Any]) -> None:
        """Process a ``block_actions`` payload from a HITL question button."""
        # Extract fields from the Slack interactive payload
        actions = payload.get("actions", [])
        if not actions:
            logger.warning("slack_block_actions_no_actions")
            return

        action = actions[0]
        action_value = action.get("value", "")

        channel_info = payload.get("channel", {})
        channel_id = (
            channel_info.get("id", "") if isinstance(channel_info, dict) else ""
        )

        container = payload.get("container", {})
        message_ts = container.get("message_ts", "")

        user_info = payload.get("user", {})
        user_id = user_info.get("id", "") if isinstance(user_info, dict) else ""
        user_name = (
            user_info.get("username", user_id)
            if isinstance(user_info, dict)
            else user_id
        )

        if not channel_id or not message_ts:
            logger.warning(
                "slack_block_actions_missing_identifiers",
                channel_id=channel_id,
                message_ts=message_ts,
            )
            return

        logger.info(
            "slack_block_action_received",
            channel_id=channel_id,
            message_ts=message_ts,
            user_id=user_id,
            action_value=action_value,
        )

        async with AsyncSessionLocal() as session:
            repo = HITLQuestionRepository(session)
            question = await repo.find_by_ref(
                question_ref=message_ts,
                channel=channel_id,
            )

            if question is None:
                logger.warning(
                    "slack_hitl_question_not_found",
                    message_ts=message_ts,
                    channel_id=channel_id,
                )
                return

            if question.status != HITLQuestionConstants.Status.PENDING:
                logger.info(
                    "slack_hitl_question_already_resolved",
                    question_id=str(question.id),
                    status=question.status,
                )
                # Update Slack message even for already-resolved questions
                await self._update_slack_message(
                    session=session,
                    question=question,
                    answer=question.answer or action_value,
                    answered_by=question.answered_by or user_name,
                    already_resolved=True,
                )
                return

            # Record the answer (atomic UPDATE ... WHERE status='pending')
            answered = await repo.record_answer(
                question_id=question.id,
                answer=action_value,
                answered_by=user_id,
            )

            if not answered:
                # Race condition: another thread answered between SELECT and UPDATE
                logger.info(
                    "slack_hitl_answer_race_condition",
                    question_id=str(question.id),
                )
                return

            # Emit a human:responded control event in the same transaction
            await self._emit_control_event(
                session=session,
                question=question,
                answer=action_value,
                answered_by=user_id,
            )

            await session.commit()

            logger.info(
                "slack_hitl_answer_recorded",
                question_id=str(question.id),
                answer=action_value,
                user_id=user_id,
            )

            # Update the Slack message to show the response and remove buttons
            await self._update_slack_message(
                session=session,
                question=question,
                answer=action_value,
                answered_by=user_name,
            )

    # ------------------------------------------------------------------
    # Control event emission
    # ------------------------------------------------------------------

    @staticmethod
    async def _emit_control_event(
        *,
        session: AsyncSession,
        question: HITLQuestion,
        answer: str,
        answered_by: str,
    ) -> None:
        """Insert a ``human:responded`` control event for the answered question.

        This event is picked up by the control event bus consumer to resume
        the paused workflow / task.
        """
        event = ControlEvent(
            tenant_id=question.tenant_id,
            channel=HITLQuestionConstants.CHANNEL_HUMAN_RESPONDED,
            payload={
                "question_id": str(question.id),
                "answer": answer,
                "answered_by": answered_by,
                "task_run_id": str(question.task_run_id),
                "workflow_run_id": (
                    str(question.workflow_run_id) if question.workflow_run_id else None
                ),
                "node_instance_id": (
                    str(question.node_instance_id)
                    if question.node_instance_id
                    else None
                ),
                "analysis_id": (
                    str(question.analysis_id) if question.analysis_id else None
                ),
            },
        )
        session.add(event)
        await session.flush()

        logger.info(
            "slack_hitl_control_event_emitted",
            event_id=str(event.id),
            question_id=str(question.id),
            channel=HITLQuestionConstants.CHANNEL_HUMAN_RESPONDED,
        )

    # ------------------------------------------------------------------
    # Slack message update
    # ------------------------------------------------------------------

    async def _update_slack_message(
        self,
        *,
        session: AsyncSession,
        question: HITLQuestion,
        answer: str,
        answered_by: str,
        already_resolved: bool = False,
    ) -> None:
        """Replace the original HITL message buttons with a status summary.

        Retrieves the ``bot_token`` from the tenant's Slack integration
        credentials and calls ``chat.update``.
        """
        bot_token = await get_bot_token(session, question.tenant_id)
        if not bot_token:
            logger.warning(
                "slack_hitl_cannot_update_message_no_bot_token",
                tenant_id=question.tenant_id,
                question_id=str(question.id),
            )
            return

        if already_resolved:
            status_text = (
                f"This question was already {question.status}. "
                f"Answer: *{answer}* (by {answered_by})"
            )
        else:
            status_text = f"Answered: *{answer}* (by {answered_by})"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": question.question_text,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": status_text,
                },
            },
        ]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    _CHAT_UPDATE_URL,
                    headers={
                        "Authorization": f"Bearer {bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={
                        "channel": question.channel,
                        "ts": question.question_ref,
                        "blocks": blocks,
                        "text": status_text,  # fallback for notifications
                    },
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.warning(
                        "slack_chat_update_failed",
                        error=data.get("error"),
                        question_id=str(question.id),
                    )
        except Exception:
            logger.exception(
                "slack_chat_update_request_failed",
                question_id=str(question.id),
            )
