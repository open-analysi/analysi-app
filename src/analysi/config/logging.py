"""
Centralized logging configuration using structlog.

Provides structured JSON logging for production and readable console logging for development.
Designed for containerized environments with stdout/stderr output.

All Python entry points (API, alert worker, integrations worker) MUST call
``configure_logging()`` at startup. Individual modules get loggers via
``get_logger(__name__)``. See AD-5 in Project Syros PLAN.md.
"""

import contextlib
import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import WrappedLogger


def configure_logging(
    *,
    log_level: str | None = None,
    environment: str | None = None,
) -> None:
    """Configure application-wide logging with structlog.

    Args:
        log_level: Override log level (e.g. "INFO", "DEBUG"). Falls back to
            ``LOG_LEVEL`` env var, then to Settings, then to "INFO".
        environment: Override environment (e.g. "development", "production").
            Falls back to ``ENVIRONMENT`` env var, then to Settings, then to
            "development".

    This function can be called from workers that should NOT import
    FastAPI Settings eagerly. When explicit args or env vars are provided,
    Settings is never imported.
    """
    # Resolve configuration without requiring Settings import when possible
    resolved_level = log_level or os.getenv("LOG_LEVEL")
    resolved_env = environment or os.getenv("ENVIRONMENT")

    # Only fall back to Settings if we still need values
    if resolved_level is None or resolved_env is None:
        try:
            from analysi.config.settings import settings

            resolved_level = resolved_level or settings.LOG_LEVEL
            resolved_env = resolved_env or settings.ENVIRONMENT
        except Exception:
            # If Settings fails to load (e.g. missing env), use safe defaults
            resolved_level = resolved_level or "INFO"
            resolved_env = resolved_env or "development"

    # Import context processors
    from analysi.common.correlation import inject_context
    from analysi.config.log_sanitizer import sanitize_log_event

    inject_trace_context: Any = None
    with contextlib.suppress(ImportError):
        from analysi.config.telemetry import inject_trace_context

    # Processor chain:
    # 1. filter_by_level — drop events below configured level
    # 2. add_logger_name, add_log_level — standard metadata
    # 3. TimeStamper — ISO timestamp
    # 4. inject_context — correlation_id, tenant_id, actor_user_id
    # 5. inject_trace_context — trace_id, span_id from OTEL
    # 6. sanitize_log_event — PII redaction + payload truncation
    # 7. Renderer — final output format
    # Build common processor prefix
    common_pre: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        inject_context,
    ]
    if inject_trace_context is not None:
        common_pre.append(inject_trace_context)
    common_pre.append(sanitize_log_event)

    if resolved_env == "development":
        # Development: Readable console output with colors
        processors: list[Any] = [*common_pre, structlog.dev.ConsoleRenderer()]
    else:
        # Production: Structured JSON output
        processors = [
            *common_pre,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    numeric_level = getattr(logging, resolved_level.upper(), logging.INFO)

    # Root logger configuration
    logging.basicConfig(
        format="%(message)s",  # structlog handles formatting
        stream=sys.stdout,  # Container-friendly: stdout only
        level=numeric_level,
        force=True,  # Override any prior basicConfig calls
    )

    # Adjust specific loggers
    _configure_third_party_loggers()


def _configure_third_party_loggers() -> None:
    """Configure log levels for third-party libraries."""

    # Reduce noise from verbose libraries
    noisy_loggers = {
        "uvicorn.access": logging.WARNING,  # Reduce uvicorn access logs
        "sqlalchemy.engine": logging.WARNING,  # Reduce SQLAlchemy query logs
        "asyncpg": logging.WARNING,  # Reduce asyncpg connection logs
        "aioboto3": logging.WARNING,  # Reduce MinIO client logs
        "botocore": logging.WARNING,
        "arq.worker": logging.INFO,  # Suppress "already running elsewhere" debug spam
    }

    for logger_name, level in noisy_loggers.items():
        logging.getLogger(logger_name).setLevel(level)


def get_logger(name: str | None = None) -> WrappedLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name, defaults to the calling module

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> WrappedLogger:
    """
    Create a logger with bound context variables.

    Args:
        **kwargs: Context variables to bind to all log messages

    Returns:
        Logger with bound context

    Example:
        logger = bind_context(tenant_id="acme", user_id="user123")
        logger.info("User action", action="login")
        # Output: {"tenant_id": "acme", "user_id": "user123", "action": "login", ...}
    """
    return structlog.get_logger().bind(**kwargs)


def bind_request_context(
    correlation_id: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    **kwargs: Any,
) -> WrappedLogger:
    """
    Create a logger with common request context.

    Args:
        correlation_id: Request correlation ID
        tenant_id: Tenant identifier
        user_id: User identifier
        **kwargs: Additional context variables

    Returns:
        Logger with bound request context
    """
    context = {"correlation_id": correlation_id}

    if tenant_id:
        context["tenant_id"] = tenant_id
    if user_id:
        context["user_id"] = user_id

    context.update(kwargs)

    return structlog.get_logger().bind(**context)


# Common logger instances for convenience
logger = get_logger(__name__)
