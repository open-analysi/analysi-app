"""
Unit tests for Component model structure and validation.
These tests don't require a database - they test model structure only.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID, UNKNOWN_USER_ID
from analysi.models.component import Component, ComponentKind, ComponentStatus


@pytest.mark.unit
class TestComponentModel:
    """Test Component model structure and validation."""

    def test_component_model_attributes(self):
        """Test that Component model has expected attributes."""
        # Test required attributes exist
        assert hasattr(Component, "id")
        assert hasattr(Component, "tenant_id")
        assert hasattr(Component, "kind")
        assert hasattr(Component, "name")
        assert hasattr(Component, "description")
        assert hasattr(Component, "status")
        assert hasattr(Component, "created_by")
        assert hasattr(Component, "created_at")
        assert hasattr(Component, "updated_at")

        # Test optional attributes exist
        assert hasattr(Component, "visible")
        assert hasattr(Component, "system_only")
        assert hasattr(Component, "app")
        assert hasattr(Component, "categories")
        assert hasattr(Component, "version")
        assert hasattr(Component, "updated_by")
        assert hasattr(Component, "last_used_at")

        # Test relationship attributes exist
        assert hasattr(Component, "task")
        assert hasattr(Component, "knowledge_unit")
        assert hasattr(Component, "outgoing_edges")
        assert hasattr(Component, "incoming_edges")

    def test_component_kind_enum(self):
        """Test ComponentKind enum values."""
        assert hasattr(ComponentKind, "TASK")
        assert hasattr(ComponentKind, "KU")
        assert ComponentKind.TASK == "task"
        assert ComponentKind.KU == "ku"

    def test_component_status_enum(self):
        """Test ComponentStatus enum values."""
        assert hasattr(ComponentStatus, "ENABLED")
        assert hasattr(ComponentStatus, "DISABLED")
        assert ComponentStatus.ENABLED == "enabled"
        assert ComponentStatus.DISABLED == "disabled"

    def test_component_initialization(self):
        """Test Component model initialization without database."""
        tenant_id = uuid4()

        # Test minimal initialization
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Test Component",
            description="A test component",
            created_by=str(SYSTEM_USER_ID),
        )

        # Verify basic attributes are set
        assert component.tenant_id == tenant_id
        assert component.kind == ComponentKind.TASK
        assert component.name == "Test Component"
        assert component.description == "A test component"
        assert component.created_by == str(SYSTEM_USER_ID)

        # Note: We can't test defaults that are set at database level
        # Those would need integration tests

    def test_component_with_all_fields(self):
        """Test Component with all optional fields."""
        tenant_id = uuid4()

        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Full Component",
            description="Component with all fields",
            created_by=str(SYSTEM_USER_ID),
            status=ComponentStatus.DISABLED,
            visible=True,
            system_only=True,
            app="custom_app",
            categories=["tag1", "tag2"],
            version="2.0.0",
            updated_by=UNKNOWN_USER_ID,
            last_used_at=datetime.now(tz=UTC),
        )

        # Verify all fields are set
        assert component.tenant_id == tenant_id
        assert component.kind == ComponentKind.KU
        assert component.status == ComponentStatus.DISABLED
        assert component.visible is True
        assert component.system_only is True
        assert component.app == "custom_app"
        assert component.categories == ["tag1", "tag2"]
        assert component.version == "2.0.0"
        assert component.updated_by == UNKNOWN_USER_ID
        assert component.last_used_at is not None

    def test_component_repr(self):
        """Test Component string representation."""
        tenant_id = uuid4()
        component_id = uuid4()

        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Test Component",
            description="A test component",
            created_by=str(SYSTEM_USER_ID),
        )

        # Manually set ID for testing
        component.id = component_id

        repr_str = repr(component)
        assert "Component" in repr_str
        assert str(component_id) in repr_str
        assert ComponentKind.TASK in repr_str
        assert "Test Component" in repr_str

    def test_component_table_name(self):
        """Test that Component has correct table name."""
        assert Component.__tablename__ == "components"

    def test_component_enum_validation(self):
        """Test enum value validation (structure only)."""
        # Test valid enum values are accessible and are strings
        assert isinstance(ComponentKind.TASK, str)
        assert isinstance(ComponentKind.KU, str)
        assert isinstance(ComponentStatus.ENABLED, str)
        assert isinstance(ComponentStatus.DISABLED, str)

    def test_component_field_types(self):
        """Test that component fields have expected Python types."""
        tenant_id = uuid4()

        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Test Component",
            description="A test component",
            created_by=str(SYSTEM_USER_ID),
            categories=["test"],
        )

        # Test field types
        assert isinstance(component.name, str)
        assert isinstance(component.description, str)
        assert isinstance(str(component.created_by), str)
        assert isinstance(component.categories, list)
        assert isinstance(component.kind, str)

        # Test UUID fields
        from uuid import UUID

        assert isinstance(component.tenant_id, UUID)
