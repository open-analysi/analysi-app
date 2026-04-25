"""Shared auth headers for internal service-to-API HTTP calls.

Workers (alert-analysis, integrations, agentic-orchestration) call the
backend API over HTTP. Since auth was introduced (Project Mikonos), every
internal call must carry the system API key.

Actor propagation uses a ``ContextVar`` so callers don't need to explicitly
thread actor_user_id through every constructor and HTTP call.  Set it once
at the job entry point with ``set_actor_user_id()``; every downstream
``internal_auth_headers()`` call picks it up automatically.

Usage:
    # At ARQ job entry point:
    from analysi.common.internal_auth import set_actor_user_id
    set_actor_user_id(actor_user_id)

    # Anywhere downstream — actor is included automatically:
    async with httpx.AsyncClient(headers=internal_auth_headers(), ...) as c:
        ...
"""

import contextvars
import os
from uuid import UUID

# Execution-scoped actor identity.  Each asyncio Task inherits the context
# from where it was created, so all async work spawned within a single ARQ
# job shares the same actor.
_actor_user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "actor_user_id",
    default=None,
)


def set_actor_user_id(actor_user_id: str | None) -> contextvars.Token:
    """Set the actor for the current execution context.

    Call this once at job entry points (ARQ workers, etc.).
    Returns a token that can be used to reset the value.
    """
    return _actor_user_id_var.set(actor_user_id)


def get_actor_user_id() -> str | None:
    """Read the actor from the current execution context."""
    return _actor_user_id_var.get()


def internal_auth_headers(
    actor_user_id: UUID | str | None = None,
) -> dict[str, str]:
    """Return auth headers for internal service-to-API calls.

    Always includes ``X-API-Key`` when the system API key is configured.
    Includes ``X-Actor-User-Id`` when an actor is available — either from
    the explicit parameter (takes precedence) or from the execution context
    set via ``set_actor_user_id()``.

    Args:
        actor_user_id: Explicit override. When provided, used instead of the
            context variable.  Useful for the rare case where a caller needs
            to impersonate a different user within the same context.
    """
    headers: dict[str, str] = {}
    api_key = os.getenv("ANALYSI_SYSTEM_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    effective_actor = (
        actor_user_id if actor_user_id is not None else _actor_user_id_var.get()
    )
    if effective_actor is not None:
        headers["X-Actor-User-Id"] = str(effective_actor)
    return headers
