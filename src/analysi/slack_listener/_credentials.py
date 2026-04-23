"""Shared credential resolution for the Slack listener package.

Centralises the look-up-integration → decrypt-credential → extract-key
pattern that sender, handler, and service all need.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.integration import Integration
from analysi.services.credential_service import CredentialService

logger = get_logger(__name__)


async def get_slack_secret(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str | None = None,
) -> dict | None:
    """Return the full decrypted credential dict for a Slack integration.

    If *integration_id* is ``None`` the first enabled Slack integration for
    the tenant is used.  Returns ``None`` when no integration or credential
    is found.
    """
    if integration_id is None:
        integration_id = await _find_slack_integration_id(session, tenant_id)
        if integration_id is None:
            return None

    try:
        cred_service = CredentialService(session)
        cred_list = await cred_service.get_integration_credentials(
            tenant_id, integration_id
        )
        if not cred_list:
            return None

        cred_id_raw = cred_list[0].get("id")
        if not cred_id_raw:
            return None

        cred_id = UUID(cred_id_raw) if isinstance(cred_id_raw, str) else cred_id_raw
        secret = await cred_service.get_credential(tenant_id, cred_id)
        return secret or None
    except Exception:
        logger.exception(
            "slack_credential_lookup_failed",
            tenant_id=tenant_id,
            integration_id=integration_id,
        )
        return None


async def get_bot_token(session: AsyncSession, tenant_id: str) -> str | None:
    """Return the ``bot_token`` for the tenant's Slack integration."""
    secret = await get_slack_secret(session, tenant_id)
    if not secret:
        return None
    return secret.get("bot_token")


async def get_app_token(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> str | None:
    """Return the ``app_token`` for a specific Slack integration."""
    secret = await get_slack_secret(session, tenant_id, integration_id)
    if not secret:
        logger.debug(
            "slack_integration_missing_app_token",
            tenant_id=tenant_id,
            integration_id=integration_id,
        )
        return None
    return secret.get("app_token")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_INTEGRATION_TYPE_SLACK = "slack"


async def _find_slack_integration_id(
    session: AsyncSession, tenant_id: str
) -> str | None:
    """Return the ``integration_id`` of the first enabled Slack integration.

    Bug #27 fix: Uses deterministic ordering (oldest first) so tenants with
    multiple Slack integrations always resolve the same one.  A future
    improvement could store ``integration_id`` on the hitl_questions row so
    credential lookup targets the exact workspace that sent the question.
    """
    stmt = (
        select(Integration.integration_id)
        .where(
            and_(
                Integration.tenant_id == tenant_id,
                Integration.integration_type == _INTEGRATION_TYPE_SLACK,
                Integration.enabled.is_(True),
            )
        )
        .order_by(Integration.created_at.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row
