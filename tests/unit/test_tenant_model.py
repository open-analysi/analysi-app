"""Unit tests for Tenant model and Workflow.app field."""

import pytest

from analysi.models.tenant import Tenant
from analysi.models.workflow import Workflow
from analysi.services.tenant import TenantService


@pytest.mark.unit
class TestTenantModel:
    """Test Tenant model structure (no database)."""

    def test_tenant_model_attributes(self):
        """Model has expected attributes."""
        assert hasattr(Tenant, "id")
        assert hasattr(Tenant, "name")
        assert hasattr(Tenant, "status")
        assert hasattr(Tenant, "created_at")
        assert hasattr(Tenant, "updated_at")

    def test_tenant_tablename(self):
        """Table name is 'tenant'."""
        assert Tenant.__tablename__ == "tenants"

    def test_tenant_initialization(self):
        """Create instance with required fields."""
        tenant = Tenant(id="test-tenant", name="Test Tenant")
        assert tenant.id == "test-tenant"
        assert tenant.name == "Test Tenant"

    def test_tenant_status_column_has_default(self):
        """Status column has 'active' default configured."""
        col = Tenant.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "active"

    def test_tenant_repr(self):
        """Repr includes id, name, status."""
        tenant = Tenant(id="acme", name="Acme Corp", status="active")
        result = repr(tenant)
        assert "acme" in result
        assert "Acme Corp" in result
        assert "active" in result


@pytest.mark.unit
class TestWorkflowAppField:
    """Test Workflow model has app field."""

    def test_workflow_has_app_attribute(self):
        """Workflow model has 'app' attribute."""
        assert hasattr(Workflow, "app")

    def test_workflow_app_column_has_default(self):
        """Workflow.app column has 'default' default configured."""
        col = Workflow.__table__.columns["app"]
        assert col.default is not None
        assert col.default.arg == "default"


@pytest.mark.unit
class TestTenantIdValidation:
    """Test tenant ID format validation (pure logic, no DB)."""

    def test_valid_tenant_ids(self):
        """Accept valid tenant IDs."""
        valid_ids = [
            "acme",
            "acme-corp",
            "tenant-123",
            "a-b",
            "abc",
            "my-very-long-tenant-name",
        ]
        for tid in valid_ids:
            errors = TenantService.validate_tenant_id(tid)
            assert errors == [], f"Expected '{tid}' to be valid, got: {errors}"

    def test_too_short(self):
        """Reject IDs shorter than 3 characters."""
        errors = TenantService.validate_tenant_id("ab")
        assert any("at least 3" in e for e in errors)

    def test_too_long(self):
        """Reject IDs longer than 255 characters."""
        errors = TenantService.validate_tenant_id("a" * 256)
        assert any("at most 255" in e for e in errors)

    def test_leading_hyphen(self):
        """Reject IDs starting with a hyphen."""
        errors = TenantService.validate_tenant_id("-acme")
        assert len(errors) > 0

    def test_trailing_hyphen(self):
        """Reject IDs ending with a hyphen."""
        errors = TenantService.validate_tenant_id("acme-")
        assert len(errors) > 0

    def test_uppercase_rejected(self):
        """Reject IDs with uppercase characters."""
        errors = TenantService.validate_tenant_id("AcmeCorp")
        assert len(errors) > 0

    def test_special_characters_rejected(self):
        """Reject IDs with special characters."""
        errors = TenantService.validate_tenant_id("acme_corp")
        assert len(errors) > 0

    def test_spaces_rejected(self):
        """Reject IDs with spaces."""
        errors = TenantService.validate_tenant_id("acme corp")
        assert len(errors) > 0
