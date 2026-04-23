"""
Unit tests for IndexBackend registry.
"""

import pytest

from analysi.services.index_backends.registry import (
    _BACKENDS,
    get_backend,
    list_backends,
    register_backend,
)


@pytest.mark.unit
class TestBackendRegistry:
    """Test backend registration and lookup."""

    def test_pgvector_registered_by_default(self):
        """pgvector should be auto-registered at import time."""
        assert "pgvector" in _BACKENDS
        assert "pgvector" in list_backends()

    def test_register_and_get_backend(self):
        """Register a mock backend, retrieve it."""

        class FakeBackend:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        register_backend("fake-test", FakeBackend)
        try:
            backend = get_backend("fake-test", session="mock-session")
            assert isinstance(backend, FakeBackend)
            assert backend.kwargs == {"session": "mock-session"}
        finally:
            # Clean up to avoid polluting other tests
            _BACKENDS.pop("fake-test", None)

    def test_get_unknown_backend_raises(self):
        """Requesting an unregistered backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown index backend"):
            get_backend("nonexistent-backend")

    def test_get_backend_returns_pgvector(self):
        """get_backend('pgvector') returns a PgvectorBackend instance."""
        from unittest.mock import AsyncMock

        from analysi.services.index_backends.pgvector_backend import PgvectorBackend

        mock_session = AsyncMock()
        backend = get_backend("pgvector", session=mock_session)
        assert isinstance(backend, PgvectorBackend)
        assert backend.session is mock_session
