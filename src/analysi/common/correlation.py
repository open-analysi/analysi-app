"""Correlation ID and tenant context propagation via ContextVars.

Every log event automatically includes ``correlation_id`` and ``tenant_id``
when set, via the ``inject_context`` structlog processor registered in
``config/logging.py``. This replaces manual ``bind_request_context()`` calls.

API requests set correlation_id in ``RequestIdMiddleware``.
Worker jobs set both correlation_id and tenant_id at job start.
Cron jobs generate a fresh correlation_id per invocation.
"""

import contextvars
import uuid

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_id", default=None
)


def set_correlation_id(cid: str) -> contextvars.Token:
    """Set the correlation ID for the current async context."""
    return _correlation_id_var.set(cid)


def get_correlation_id() -> str | None:
    """Get the correlation ID for the current context, or None."""
    return _correlation_id_var.get()


def set_tenant_id(tid: str) -> contextvars.Token:
    """Set the tenant ID for the current async context."""
    return _tenant_id_var.set(tid)


def get_tenant_id() -> str | None:
    """Get the tenant ID for the current context, or None."""
    return _tenant_id_var.get()


def generate_correlation_id() -> str:
    """Generate a new UUID-based correlation ID."""
    return str(uuid.uuid4())


def inject_context(logger: object, method_name: str, event_dict: dict) -> dict:
    """Structlog processor that injects correlation_id and tenant_id.

    Reads from ContextVars and also reads actor_user_id from
    ``common.internal_auth`` if available.
    """
    cid = _correlation_id_var.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)

    tid = _tenant_id_var.get()
    if tid is not None:
        event_dict.setdefault("tenant_id", tid)

    # Also inject actor_user_id if set
    try:
        from analysi.common.internal_auth import get_actor_user_id

        actor = get_actor_user_id()
        if actor is not None:
            event_dict.setdefault("actor_user_id", actor)
    except ImportError:
        pass

    return event_dict
