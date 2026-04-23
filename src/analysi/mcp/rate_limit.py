"""Rate limiting for MCP execution tools.

The heavy MCP tools (``run_script``, ``run_workflow``,
``run_integration_tool``) are RBAC-gated but otherwise unbounded. A
compromised or misbehaving client could exhaust workers, Postgres, or
LLM budget. This module gates each call by per-(tenant, user, tool)
budget enforced via :class:`analysi.auth.rate_limit.ValkeyRateLimiter`.

The limiter is configured at process startup by the application factory
(when a Valkey client is available). Tests inject their own via
``set_mcp_limiter``. When the limiter is not configured, the check is a
no-op so unit tests and dev environments without Valkey continue to work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from analysi.config.logging import get_logger
from analysi.mcp import context as mcp_context

if TYPE_CHECKING:
    from analysi.auth.rate_limit import ValkeyRateLimiter

logger = get_logger(__name__)

# Generic rate-limit message: doesn't echo the tool name back to the caller
# to avoid revealing which tools exist (defense in depth on top of RBAC).
_RATE_LIMIT_MESSAGE = "Rate limit exceeded for this operation. Try again later."

# Process-wide singleton, set during MCP server startup. ``None`` means
# rate limiting is disabled (dev/test).
_mcp_limiter: ValkeyRateLimiter | None = None


def set_mcp_limiter(limiter: ValkeyRateLimiter | None) -> None:
    """Configure (or unset) the process-wide MCP rate limiter."""
    global _mcp_limiter
    _mcp_limiter = limiter


def get_mcp_limiter() -> ValkeyRateLimiter | None:
    """Return the configured limiter, or None if disabled."""
    return _mcp_limiter


async def check_mcp_rate_limit(tool_name: str) -> None:
    """Charge one invocation of ``tool_name`` against the current user's bucket.

    Raises:
        PermissionError: if the user has no authenticated identity (the
            limiter cannot safely bucket anonymous requests), or if the
            user has exceeded their budget for this tool.

    No-op if no limiter is configured (dev/test).
    """
    limiter = _mcp_limiter
    if limiter is None:
        return

    user = mcp_context.get_mcp_current_user()
    if user is None:
        # Fail closed — we can't bucket anonymous requests, and they
        # shouldn't reach here anyway (middleware enforces auth).
        logger.warning("mcp_rate_limit_no_user", tool=tool_name)
        raise PermissionError(_RATE_LIMIT_MESSAGE)

    tenant = mcp_context.get_tenant()
    user_id = str(user.db_user_id) if user.db_user_id else user.user_id
    key = f"{tenant}:{user_id}:{tool_name}"

    try:
        allowed = await limiter.check_and_record(key)
    except Exception as exc:
        # Backend hiccup (timeout, reconnect, failover, etc.) MUST NOT
        # turn an MCP call into an outage. Startup wires the limiter as
        # best-effort; runtime failures degrade open the same way.
        logger.warning(
            "mcp_rate_limit_backend_error",
            tenant=tenant,
            tool=tool_name,
            error=str(exc)[:200],
        )
        return

    if not allowed:
        logger.warning(
            "mcp_rate_limit_exceeded",
            tenant=tenant,
            user_id=user_id,
            tool=tool_name,
        )
        raise PermissionError(_RATE_LIMIT_MESSAGE)
