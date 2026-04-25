"""
Backend registry — simple dict-based registry for index backend implementations.

Project Paros: Knowledge Index feature.

Backends self-register at import time. The service layer looks up the
correct backend from the collection's backend_type field.
"""

from __future__ import annotations

from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)

_BACKENDS: dict[str, type] = {}


def register_backend(name: str, backend_class: type) -> None:
    """Register an index backend implementation.

    Args:
        name: Backend identifier (e.g., "pgvector", "chroma").
        backend_class: Class implementing the IndexBackend protocol.
    """
    _BACKENDS[name] = backend_class
    logger.info("index_backend_registered", backend_name=name)


def get_backend(name: str, **kwargs: Any) -> Any:
    """Get an index backend instance by name.

    Args:
        name: Backend identifier.
        **kwargs: Passed to the backend constructor (e.g., session=...).

    Returns:
        Backend instance.

    Raises:
        ValueError: If backend name is not registered.
    """
    if name not in _BACKENDS:
        available = list(_BACKENDS.keys())
        raise ValueError(f"Unknown index backend '{name}'. Available: {available}")
    return _BACKENDS[name](**kwargs)


def list_backends() -> list[str]:
    """List all registered backend names."""
    return list(_BACKENDS.keys())


def _register_builtins() -> None:
    """Auto-register built-in backends."""
    from analysi.services.index_backends.pgvector_backend import PgvectorBackend

    register_backend("pgvector", PgvectorBackend)


_register_builtins()
