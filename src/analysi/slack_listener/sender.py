"""Send HITL questions to Slack as Block Kit messages with buttons.

The :func:`send_hitl_question` function is called after a HITL question row
has been created (with a placeholder ``question_ref``).  It posts a Block Kit
message to Slack with the question text and button options, then updates the
``question_ref`` column with the returned ``message_ts`` so the listener can
match incoming button clicks back to this question.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.hitl_question import HITLQuestion
from analysi.slack_listener._credentials import get_bot_token

logger = get_logger(__name__)

# Slack API endpoint for posting messages
_CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


async def send_hitl_question(
    *,
    session: AsyncSession,
    hitl_question: HITLQuestion,
    pending_tool_args: dict[str, Any],
    tenant_id: str,
) -> bool:
    """Post a HITL question to Slack and record the ``message_ts``.

    Args:
        session: Active DB session (caller is responsible for committing).
        hitl_question: The persisted HITLQuestion row.
        pending_tool_args: The pending tool arguments from the Cy checkpoint,
            expected keys: ``question`` or ``text`` (question body), and
            ``responses`` or ``options`` (comma-separated button labels).
        tenant_id: Tenant identifier.

    Returns:
        True if the message was posted and ``question_ref`` was updated,
        False on any failure.
    """
    bot_token = await get_bot_token(session, tenant_id)
    if not bot_token:
        logger.error(
            "slack_send_hitl_no_bot_token",
            tenant_id=tenant_id,
            question_id=str(hitl_question.id),
        )
        return False

    # Resolve question text — try both key conventions
    question_text = (
        pending_tool_args.get("question")
        or pending_tool_args.get("text")
        or hitl_question.question_text
    )

    # Resolve button options — try both key conventions
    raw_options = pending_tool_args.get("responses") or pending_tool_args.get("options")
    button_labels = _parse_options(raw_options, hitl_question.options)

    # Build the destination channel
    channel = (
        pending_tool_args.get("destination")
        or pending_tool_args.get("channel")
        or hitl_question.channel
    )
    if not channel:
        logger.error(
            "slack_send_hitl_no_channel",
            question_id=str(hitl_question.id),
        )
        return False

    # Construct Block Kit message
    blocks = _build_blocks(question_text, button_labels)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _CHAT_POST_MESSAGE_URL,
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "channel": channel,
                    "blocks": blocks,
                    "text": question_text,  # fallback for notifications
                },
            )
            data = resp.json()

        if not data.get("ok"):
            logger.error(
                "slack_send_hitl_api_error",
                error=data.get("error"),
                question_id=str(hitl_question.id),
            )
            return False

        # Update the question with the Slack message reference
        message_ts = data.get("ts", "")
        channel_id = data.get("channel", channel)

        hitl_question.question_ref = message_ts
        hitl_question.channel = channel_id
        await session.flush()

        logger.info(
            "slack_hitl_question_sent",
            question_id=str(hitl_question.id),
            message_ts=message_ts,
            channel=channel_id,
        )
        return True

    except Exception:
        logger.exception(
            "slack_send_hitl_request_failed",
            question_id=str(hitl_question.id),
        )
        return False


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------


def _build_blocks(question_text: str, button_labels: list[str]) -> list[dict[str, Any]]:
    """Build a Slack Block Kit layout with a question and action buttons."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": question_text,
            },
        },
    ]

    if button_labels:
        elements = []
        for i, label in enumerate(
            button_labels[:5]
        ):  # Slack allows max 5 buttons per block
            # Bug #13 fix: Include index in action_id to guarantee uniqueness.
            # Without this, buttons whose labels normalize to the same string
            # (e.g., "Approve Now" and "approve_now") would get duplicate
            # action_ids, causing Slack to reject the message.
            elements.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": label.strip(),
                    },
                    "value": label.strip(),
                    "action_id": f"hitl_response_{i}_{label.strip().lower().replace(' ', '_')}",
                }
            )
        blocks.append(
            {
                "type": "actions",
                "elements": elements,
            }
        )

    return blocks


def _parse_options(
    raw_options: str | list | None,
    question_options: list[dict] | None,
) -> list[str]:
    """Normalise button options from various input formats.

    Supports:
    - Comma-separated string: ``"Approve, Reject, Escalate"``
    - A list of label strings: ``["Approve", "Reject"]``
    - A list of dicts with ``label`` or ``value`` keys from hitl_question.options
    """
    if isinstance(raw_options, str) and raw_options.strip():
        return [opt.strip() for opt in raw_options.split(",") if opt.strip()]

    if isinstance(raw_options, list):
        result = []
        for item in raw_options:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.append(item.get("label", item.get("value", "")))
        return [r for r in result if r]

    # Fall back to the question's own options column
    if question_options:
        return [
            opt.get("label", opt.get("value", ""))
            for opt in question_options
            if isinstance(opt, dict)
        ]

    return []
