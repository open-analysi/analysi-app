"""Slack listener service — manages WebSocket connections to Slack workspaces.

On startup the service queries the database for all enabled Slack integrations
that have an ``app_token`` (``xapp-...``) in their credentials.  It creates one
:class:`WorkspaceConnection` per unique ``app_token`` (deduplicating across
tenants that share a workspace).  A background refresh task re-scans every 60
seconds so newly-added or removed integrations are picked up at runtime.
"""

from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.models.integration import Integration
from analysi.slack_listener._credentials import get_app_token
from analysi.slack_listener.connection import WorkspaceConnection
from analysi.slack_listener.handler import InteractivePayloadHandler

logger = get_logger(__name__)

# How often (seconds) the service re-scans for new / removed Slack integrations.
_REFRESH_INTERVAL_SECONDS = 60

_INTEGRATION_TYPE_SLACK = "slack"


class SlackListenerService:
    """Top-level orchestrator for Slack Socket Mode connections.

    Lifecycle::

        service = SlackListenerService()
        await service.start()   # blocks until stop() is called
        await service.stop()    # graceful shutdown
    """

    def __init__(self) -> None:
        # app_token -> WorkspaceConnection
        self._connections: dict[str, WorkspaceConnection] = {}
        self._refresh_task: asyncio.Task | None = None
        self._running = False
        self._stop_event = asyncio.Event()
        # Keep references to connection tasks so they are not garbage-collected
        self._connection_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Discover Slack workspaces and open Socket Mode connections."""
        self._running = True
        self._stop_event.clear()
        await self._refresh_connections()
        self._refresh_task = asyncio.create_task(self._periodic_refresh())
        # Block until stop() signals
        await self._stop_event.wait()

    async def stop(self) -> None:
        """Shut down all connections and cancel the refresh loop."""
        self._running = False
        self._stop_event.set()

        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task

        # Stop every workspace connection concurrently
        if self._connections:
            await asyncio.gather(
                *(conn.stop() for conn in self._connections.values()),
                return_exceptions=True,
            )
            self._connections.clear()

        logger.info(
            "slack_listener_all_connections_closed",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _periodic_refresh(self) -> None:
        """Re-scan for new / removed integrations every _REFRESH_INTERVAL_SECONDS."""
        while self._running:
            await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
            if not self._running:
                break
            try:
                await self._refresh_connections()
            except Exception:
                logger.exception("slack_listener_refresh_failed")

    async def _refresh_connections(self) -> None:
        """Query the DB for Slack integrations and reconcile connections."""
        discovered = await self._discover_app_tokens()

        # Start connections for newly-discovered app tokens
        for app_token, meta in discovered.items():
            if app_token not in self._connections:
                logger.info(
                    "slack_listener_new_workspace_detected",
                    tenant_ids=meta["tenant_ids"],
                )
                handler = InteractivePayloadHandler()
                conn = WorkspaceConnection(
                    app_token=app_token,
                    handler=handler,
                )
                self._connections[app_token] = conn
                self._connection_tasks[app_token] = asyncio.create_task(conn.run())

        # Tear down connections whose app_token is no longer in the DB
        stale_tokens = set(self._connections) - set(discovered)
        for token in stale_tokens:
            logger.info("slack_listener_removing_stale_workspace")
            conn = self._connections.pop(token)
            self._connection_tasks.pop(token, None)
            await conn.stop()

    async def _discover_app_tokens(self) -> dict[str, dict]:
        """Return a mapping of ``app_token -> {tenant_ids: [...]}`` for all
        enabled Slack integrations that have an app_token credential.

        Multiple tenants may share the same Slack workspace (same app_token),
        so we deduplicate here.
        """
        result: dict[str, dict] = {}

        async with AsyncSessionLocal() as session:
            integrations = await self._list_slack_integrations(session)
            for integration in integrations:
                token = await get_app_token(
                    session,
                    integration.tenant_id,
                    integration.integration_id,
                )
                if not token:
                    continue

                if token in result:
                    result[token]["tenant_ids"].append(integration.tenant_id)
                else:
                    result[token] = {
                        "tenant_ids": [integration.tenant_id],
                    }

        logger.info(
            "slack_listener_discovered_workspaces",
            workspace_count=len(result),
        )
        return result

    @staticmethod
    async def _list_slack_integrations(session: AsyncSession) -> list[Integration]:
        """Return all enabled integrations of type ``slack``."""
        stmt = (
            select(Integration)
            .where(
                and_(
                    Integration.integration_type == _INTEGRATION_TYPE_SLACK,
                    Integration.enabled.is_(True),
                )
            )
            .order_by(Integration.created_at)
        )
        rows = await session.execute(stmt)
        return list(rows.scalars().all())
