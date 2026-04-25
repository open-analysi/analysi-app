"""
Index backends — pluggable storage implementations for knowledge index collections.

Project Paros: Knowledge Index feature.
"""

from analysi.services.index_backends.base import (
    IndexBackend,
    IndexEntry,
    SearchResult,
    StoredEntry,
)
from analysi.services.index_backends.registry import get_backend, register_backend

__all__ = [
    "IndexBackend",
    "IndexEntry",
    "SearchResult",
    "StoredEntry",
    "get_backend",
    "register_backend",
]
