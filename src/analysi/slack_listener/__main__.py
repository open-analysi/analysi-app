"""Entrypoint for ``python -m analysi.slack_listener``.

Starts the Slack listener service that connects to Slack workspaces
via Socket Mode and processes interactive payloads (HITL button clicks).
"""

import asyncio
import signal

from analysi.config.logging import configure_logging, get_logger
from analysi.slack_listener.service import SlackListenerService

configure_logging()
logger = get_logger(__name__)


async def main() -> None:
    """Start the Slack listener and wait for shutdown signal."""
    service = SlackListenerService()

    # Wire up graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown(service)))

    try:
        logger.info("slack_listener_starting")
        await service.start()
    except asyncio.CancelledError:
        logger.info("slack_listener_cancelled")
    finally:
        await service.stop()
        logger.info("slack_listener_stopped")


async def _shutdown(service: SlackListenerService) -> None:
    """Trigger graceful shutdown.

    ``service.stop()`` sets the stop event (unblocking ``start()``) and
    tears down all WebSocket connections.  The ``finally`` block in
    ``main()`` handles any remaining cleanup.
    """
    logger.info("slack_listener_shutdown_signal_received")
    await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
