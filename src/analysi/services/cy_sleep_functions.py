"""
Cy Native Sleep Functions - Testing utility for task execution timing.

Provides a sleep tool for Cy scripts, primarily useful for testing
job lifecycle scenarios (retry, cancellation, stuck detection) where
a task needs to remain running for a controlled duration.

Functions are registered via NATIVE_TOOL_METADATA in native_tools_registry.py
and available as native::tools::sleep in Cy scripts.
"""

import asyncio

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Safety cap to prevent runaway sleeps in production
_MAX_SLEEP_SECONDS = 300  # 5 minutes


class CySleepFunctions:
    """Native Cy functions for pausing task execution.

    These functions are registered via NATIVE_TOOL_METADATA and available
    in Cy scripts as native::tools::sleep.
    """

    async def sleep(self, seconds: float) -> bool:
        """Pause task execution for the specified number of seconds.

        Useful for testing job lifecycle scenarios: retry on failure,
        cancellation during execution, stuck detection, etc.

        Args:
            seconds: Duration to sleep in seconds (capped at 300s).

        Returns:
            True when the sleep completes successfully.

        Raises:
            ValueError: If seconds is negative.
        """
        if not isinstance(seconds, (int, float)):
            raise ValueError(
                f"sleep() seconds must be a number, got {type(seconds).__name__}"
            )
        if seconds < 0:
            raise ValueError(f"sleep() seconds must be non-negative, got {seconds}")

        capped = min(seconds, _MAX_SLEEP_SECONDS)
        if capped < seconds:
            logger.warning(
                "sleep_duration_capped",
                requested=seconds,
                capped=capped,
                max=_MAX_SLEEP_SECONDS,
            )

        logger.info("sleep_started", seconds=capped)
        await asyncio.sleep(capped)
        logger.info("sleep_completed", seconds=capped)
        return True
