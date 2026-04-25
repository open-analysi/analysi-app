"""Unit tests for correlation ID propagation."""

from analysi.common.correlation import (
    generate_correlation_id,
    get_correlation_id,
    get_tenant_id,
    inject_context,
    set_correlation_id,
    set_tenant_id,
)


class TestCorrelationId:
    """Test ContextVar-based correlation ID."""

    def test_default_is_none(self):
        assert get_correlation_id() is None

    def test_set_and_get(self):
        token = set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"
        # Reset
        from analysi.common.correlation import _correlation_id_var

        _correlation_id_var.reset(token)

    def test_generate_returns_uuid(self):
        cid = generate_correlation_id()
        assert len(cid) == 36  # UUID format
        assert cid.count("-") == 4


class TestTenantId:
    """Test ContextVar-based tenant ID."""

    def test_default_is_none(self):
        assert get_tenant_id() is None

    def test_set_and_get(self):
        token = set_tenant_id("acme")
        assert get_tenant_id() == "acme"
        from analysi.common.correlation import _tenant_id_var

        _tenant_id_var.reset(token)


class TestInjectContext:
    """Test the structlog processor."""

    def test_injects_correlation_id_when_set(self):
        token = set_correlation_id("cid-abc")
        try:
            event_dict = {"event": "test"}
            result = inject_context(None, "info", event_dict)
            assert result["correlation_id"] == "cid-abc"
        finally:
            from analysi.common.correlation import _correlation_id_var

            _correlation_id_var.reset(token)

    def test_injects_tenant_id_when_set(self):
        token = set_tenant_id("acme-corp")
        try:
            event_dict = {"event": "test"}
            result = inject_context(None, "info", event_dict)
            assert result["tenant_id"] == "acme-corp"
        finally:
            from analysi.common.correlation import _tenant_id_var

            _tenant_id_var.reset(token)

    def test_omits_when_not_set(self):
        event_dict = {"event": "test"}
        result = inject_context(None, "info", event_dict)
        assert "correlation_id" not in result
        assert "tenant_id" not in result

    def test_does_not_override_existing(self):
        """If event_dict already has correlation_id, don't overwrite."""
        token = set_correlation_id("from-contextvar")
        try:
            event_dict = {"event": "test", "correlation_id": "explicit-value"}
            result = inject_context(None, "info", event_dict)
            assert result["correlation_id"] == "explicit-value"
        finally:
            from analysi.common.correlation import _correlation_id_var

            _correlation_id_var.reset(token)

    def test_injects_both(self):
        t1 = set_correlation_id("cid-xyz")
        t2 = set_tenant_id("tenant-1")
        try:
            result = inject_context(None, "info", {"event": "test"})
            assert result["correlation_id"] == "cid-xyz"
            assert result["tenant_id"] == "tenant-1"
        finally:
            from analysi.common.correlation import _correlation_id_var, _tenant_id_var

            _correlation_id_var.reset(t1)
            _tenant_id_var.reset(t2)
