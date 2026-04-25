"""Unit tests for managed resources service."""

from analysi.services.managed_resources import (
    WELL_KNOWN_RESOURCE_KEYS,
    ManagedResource,
)


class TestWellKnownResourceKeys:
    """Test WELL_KNOWN_RESOURCE_KEYS constant."""

    def test_contains_alert_ingestion(self):
        assert "alert_ingestion" in WELL_KNOWN_RESOURCE_KEYS

    def test_contains_health_check(self):
        assert "health_check" in WELL_KNOWN_RESOURCE_KEYS


class TestManagedResourceDataclass:
    """Test ManagedResource dataclass."""

    def test_managed_resource_dataclass_fields(self):
        """ManagedResource has all required fields."""
        from uuid import uuid4

        resource = ManagedResource(
            resource_key="health_check",
            task_id=uuid4(),
            task_name="Test Health Check",
            schedule_id=uuid4(),
            schedule={"type": "every", "value": "5m", "enabled": False},
            last_run={"status": "completed", "at": "2026-04-26T00:00:00Z"},
            next_run_at=None,
        )

        assert resource.resource_key == "health_check"
        assert resource.task_name == "Test Health Check"
        assert resource.schedule is not None
        assert resource.last_run is not None

    def test_managed_resource_dataclass_optional_fields(self):
        """schedule_id, schedule, last_run, next_run_at can all be None."""
        from uuid import uuid4

        resource = ManagedResource(
            resource_key="health_check",
            task_id=uuid4(),
            task_name="Test Health Check",
            schedule_id=None,
            schedule=None,
            last_run=None,
            next_run_at=None,
        )

        assert resource.schedule_id is None
        assert resource.schedule is None
        assert resource.last_run is None
        assert resource.next_run_at is None
