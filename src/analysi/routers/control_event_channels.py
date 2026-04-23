"""Control Event Channel Registry API (Project Tilos).

Returns known channels: hardcoded system channels plus any custom channels
derived from existing rules. No DB table needed — system channels are constants,
configured channels are discovered from the rules table.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, api_list_response
from analysi.auth.dependencies import require_permission
from analysi.constants import HITLQuestionConstants
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.control_event_repository import ControlEventRepository

router = APIRouter(
    prefix="/{tenant}/control-event-channels",
    tags=["control-event-channels"],
    dependencies=[Depends(require_permission("control_events", "read"))],
)
# ---------------------------------------------------------------------------
# System channel definitions — hardcoded, always available for all tenants
# ---------------------------------------------------------------------------

_SYSTEM_CHANNELS = [
    {
        "channel": "disposition:ready",
        "type": "system",
        "description": (
            "Fires when an analyst completes an analysis with a disposition. "
            "Use this to trigger notifications, ticket creation, or enrichment workflows."
        ),
        "payload_fields": [
            "alert_id",
            "analysis_id",
            "disposition_id",
            "disposition",
            "confidence_score",
            "short_summary",
            "event_id",
            "config",
        ],
    },
    {
        "channel": "analysis:failed",
        "type": "system",
        "description": (
            "Fires when an analysis fails due to an error. "
            "Use this to trigger alerts or escalation workflows."
        ),
        "payload_fields": [
            "alert_id",
            "analysis_id",
            "error",
            "event_id",
            "config",
        ],
    },
    {
        "channel": HITLQuestionConstants.CHANNEL_HUMAN_RESPONDED,
        "type": "system",
        "description": (
            "Internal channel — fires when a human answers an HITL question "
            "(e.g., Slack button click). Resumes the paused task and workflow."
        ),
        "payload_fields": [
            "question_id",
            "answer",
            "answered_by",
        ],
    },
]

_SYSTEM_CHANNEL_NAMES = {c["channel"] for c in _SYSTEM_CHANNELS}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChannelInfo(BaseModel):
    channel: str
    type: str  # "system" | "configured"
    description: str | None
    payload_fields: list[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiListResponse[ChannelInfo])
async def list_control_event_channels(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiListResponse[ChannelInfo]:
    """List all available control event channels for the tenant.

    Returns system channels (always present) plus any custom channels
    derived from existing rules configured for this tenant.
    """
    repo = ControlEventRepository(session)
    rule_channels = await repo.list_distinct_channels(tenant_id)

    # Start with system channels
    channels: list[ChannelInfo] = [ChannelInfo(**c) for c in _SYSTEM_CHANNELS]

    # Add configured channels that aren't already system channels
    for channel in rule_channels:
        if channel not in _SYSTEM_CHANNEL_NAMES:
            channels.append(
                ChannelInfo(
                    channel=channel,
                    type="configured",
                    description=None,
                    payload_fields=[],
                )
            )

    return api_list_response(channels, total=len(channels), request=request)
