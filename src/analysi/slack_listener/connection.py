"""WebSocket connection to a single Slack workspace via Socket Mode.

Each :class:`WorkspaceConnection` maintains a persistent WebSocket to Slack,
receives JSON envelopes, ACKs them, and dispatches interactive payloads to the
:class:`InteractivePayloadHandler`.

Reconnection uses exponential backoff (1 s, 2 s, 4 s, ... up to 60 s).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from analysi.slack_listener.handler import InteractivePayloadHandler

logger = get_logger(__name__)

# Slack API endpoint for Socket Mode WebSocket URL
_CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"

# Backoff parameters
_BACKOFF_BASE_SECONDS = 1
_BACKOFF_MAX_SECONDS = 60


class WorkspaceConnection:
    """Manages a Socket Mode WebSocket for one Slack workspace.

    Usage::

        conn = WorkspaceConnection(app_token="xapp-...", handler=handler)
        await conn.run()   # blocks, reconnects on failure
        await conn.stop()  # graceful close
    """

    def __init__(
        self,
        *,
        app_token: str,
        handler: InteractivePayloadHandler,
    ) -> None:
        self._app_token = app_token
        self._handler = handler
        self._ws: ClientConnection | None = None
        self._running = False
        self._backoff_seconds = _BACKOFF_BASE_SECONDS
        # Keep references to background tasks so they are not garbage-collected
        self._background_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect to Slack and process messages. Reconnects automatically."""
        self._running = True
        while self._running:
            try:
                ws_url = await self._obtain_ws_url()
                if not ws_url:
                    await self._wait_backoff()
                    continue

                await self._listen(ws_url)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self._running:
                    break
                logger.exception("slack_ws_unexpected_error")
                await self._wait_backoff()

    async def stop(self) -> None:
        """Signal the connection loop to exit and close the WebSocket."""
        self._running = False
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _obtain_ws_url(self) -> str | None:
        """Call ``apps.connections.open`` to get a fresh WebSocket URL."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    _CONNECTIONS_OPEN_URL,
                    headers={
                        "Authorization": f"Bearer {self._app_token}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if not data.get("ok"):
                logger.error(
                    "slack_connections_open_failed",
                    error=data.get("error", "unknown"),
                )
                return None

            url = data.get("url")
            logger.info("slack_ws_url_obtained")
            self._backoff_seconds = _BACKOFF_BASE_SECONDS  # reset on success
            return url

        except Exception:
            logger.exception("slack_connections_open_request_failed")
            return None

    async def _listen(self, ws_url: str) -> None:
        """Open the WebSocket and process incoming envelopes until disconnect."""
        async with websockets.connect(ws_url) as ws:
            self._ws = ws
            self._backoff_seconds = _BACKOFF_BASE_SECONDS
            logger.info("slack_ws_connected")

            try:
                async for raw_message in ws:
                    if not self._running:
                        break
                    await self._handle_envelope(ws, raw_message)
            except websockets.exceptions.ConnectionClosed as exc:
                logger.warning(
                    "slack_ws_connection_closed",
                    code=exc.code,
                    reason=str(exc.reason),
                )
            finally:
                self._ws = None

    async def _handle_envelope(
        self,
        ws: ClientConnection,
        raw_message: str | bytes,
    ) -> None:
        """Parse a Socket Mode envelope, ACK it, and dispatch the payload."""
        try:
            envelope: dict[str, Any] = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError):
            logger.warning("slack_ws_invalid_json", raw=str(raw_message)[:200])
            return

        envelope_id = envelope.get("envelope_id")
        if not envelope_id:
            # Not an envelope that requires ACK (e.g., a hello message)
            logger.debug("slack_ws_non_envelope_message", type=envelope.get("type"))
            return

        # ACK immediately so Slack does not retry
        ack_payload = json.dumps({"envelope_id": envelope_id})
        try:
            await ws.send(ack_payload)
        except Exception:
            logger.exception("slack_ws_ack_send_failed", envelope_id=envelope_id)

        # Dispatch interactive payloads in the background to avoid blocking
        payload = envelope.get("payload")
        envelope_type = envelope.get("type")

        if envelope_type == "interactive" and payload:
            task = asyncio.create_task(self._dispatch_interactive(payload))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        else:
            logger.debug(
                "slack_ws_envelope_ignored",
                envelope_type=envelope_type,
            )

    async def _dispatch_interactive(self, payload: dict[str, Any]) -> None:
        """Forward an interactive payload to the handler, catching errors."""
        try:
            await self._handler.handle(payload)
        except Exception:
            logger.exception("slack_interactive_handler_error")

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    async def _wait_backoff(self) -> None:
        """Sleep with exponential backoff, doubling each time up to the max."""
        logger.info(
            "slack_ws_reconnect_backoff",
            backoff_seconds=self._backoff_seconds,
        )
        await asyncio.sleep(self._backoff_seconds)
        self._backoff_seconds = min(
            self._backoff_seconds * 2,
            _BACKOFF_MAX_SECONDS,
        )
