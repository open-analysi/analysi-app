"""Unit tests for Analysis Group Cache"""

from analysi.alert_analysis.steps.workflow_builder import AnalysisGroupCache

# Default tenant used in most tests (single-tenant scenarios)
T = "test-tenant"


class TestAnalysisGroupCache:
    """Test the in-memory cache for analysis groups."""

    def test_cache_initialization(self):
        """Test cache initializes with empty dictionaries."""
        cache = AnalysisGroupCache()

        # Should have empty internal caches
        assert cache.get_group_id("any_title", tenant_id=T) is None
        assert cache.get_workflow_id("any_group_id") is None

    def test_get_group_id_returns_none_when_not_cached(self):
        """Test that get_group_id returns None for uncached titles."""
        cache = AnalysisGroupCache()
        result = cache.get_group_id("uncached_title", tenant_id=T)
        assert result is None

    def test_set_group_caches_title_to_group_mapping(self):
        """Test that set_group stores (tenant_id, title) → group_id mapping."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Suspicious Login",
            group_id="group-123",
            workflow_id="workflow-456",
            tenant_id=T,
        )

        assert cache.get_group_id("Suspicious Login", tenant_id=T) == "group-123"

    def test_set_group_caches_workflow_mapping(self):
        """Test that set_group stores group_id → workflow_id mapping."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Suspicious Login",
            group_id="group-123",
            workflow_id="workflow-456",
            tenant_id=T,
        )

        assert cache.get_workflow_id("group-123") == "workflow-456"

    def test_set_group_allows_none_workflow_id(self):
        """Test that set_group handles None workflow_id (generation in progress)."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="New Alert Type",
            group_id="group-789",
            workflow_id=None,
            tenant_id=T,
        )

        assert cache.get_group_id("New Alert Type", tenant_id=T) == "group-789"
        assert cache.get_workflow_id("group-789") is None

    def test_get_workflow_id_returns_none_when_not_cached(self):
        """Test that get_workflow_id returns None for uncached group IDs."""
        cache = AnalysisGroupCache()
        result = cache.get_workflow_id("uncached_group_id")
        assert result is None

    def test_invalidate_group_removes_workflow_mapping(self):
        """Test that invalidate_group removes workflow entry."""
        cache = AnalysisGroupCache()

        # Setup: Add a cached group with workflow
        cache.set_group(
            title="Test Alert",
            group_id="group-999",
            workflow_id="workflow-111",
            tenant_id=T,
        )
        assert cache.get_workflow_id("group-999") == "workflow-111"

        # Act: Invalidate the group
        cache.invalidate_group("group-999")

        # Assert: Workflow mapping should be removed
        assert cache.get_workflow_id("group-999") is None

    def test_invalidate_group_preserves_title_mapping(self):
        """Test that invalidate_group keeps (tenant, title) → group_id mapping intact."""
        cache = AnalysisGroupCache()

        # Setup
        cache.set_group(
            title="Test Alert",
            group_id="group-999",
            workflow_id="workflow-111",
            tenant_id=T,
        )

        # Act: Invalidate
        cache.invalidate_group("group-999")

        # Assert: Title → group_id mapping should remain
        assert cache.get_group_id("Test Alert", tenant_id=T) == "group-999"

    def test_invalidate_nonexistent_group_is_safe(self):
        """Test that invalidating a non-existent group doesn't raise errors."""
        cache = AnalysisGroupCache()

        # Should not raise
        cache.invalidate_group("nonexistent-group")

    def test_multiple_groups_cached_independently(self):
        """Test that multiple groups can be cached and retrieved independently."""
        cache = AnalysisGroupCache()

        # Setup: Cache multiple groups
        cache.set_group(
            title="Malware Alert", group_id="g1", workflow_id="w1", tenant_id=T
        )
        cache.set_group(
            title="Phishing Alert", group_id="g2", workflow_id="w2", tenant_id=T
        )
        cache.set_group(
            title="Lateral Movement",
            group_id="g3",
            workflow_id=None,
            tenant_id=T,
        )  # No workflow yet

        # Assert: All groups retrievable
        assert cache.get_group_id("Malware Alert", tenant_id=T) == "g1"
        assert cache.get_group_id("Phishing Alert", tenant_id=T) == "g2"
        assert cache.get_group_id("Lateral Movement", tenant_id=T) == "g3"

        # Assert: Workflows correct
        assert cache.get_workflow_id("g1") == "w1"
        assert cache.get_workflow_id("g2") == "w2"
        assert cache.get_workflow_id("g3") is None

    def test_overwrite_existing_group_updates_cache(self):
        """Test that calling set_group twice updates the cache (workflow completion)."""
        cache = AnalysisGroupCache()

        # Setup: Initial state - no workflow
        cache.set_group(
            title="New Rule", group_id="g-abc", workflow_id=None, tenant_id=T
        )
        assert cache.get_workflow_id("g-abc") is None

        # Act: Update with workflow (simulates generation completion)
        cache.set_group(
            title="New Rule", group_id="g-abc", workflow_id="w-xyz", tenant_id=T
        )

        # Assert: Workflow now available
        assert cache.get_workflow_id("g-abc") == "w-xyz"


class TestAnalysisGroupCacheTenantIsolation:
    """Test that cache entries are isolated per tenant."""

    def test_same_title_different_tenants_are_isolated(self):
        """Two tenants with the same rule_name get independent cache entries."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Suspicious Login",
            group_id="group-A",
            workflow_id="workflow-A",
            tenant_id="tenant-alpha",
        )
        cache.set_group(
            title="Suspicious Login",
            group_id="group-B",
            workflow_id="workflow-B",
            tenant_id="tenant-beta",
        )

        assert (
            cache.get_group_id("Suspicious Login", tenant_id="tenant-alpha")
            == "group-A"
        )
        assert (
            cache.get_group_id("Suspicious Login", tenant_id="tenant-beta") == "group-B"
        )

        assert cache.get_workflow_id("group-A") == "workflow-A"
        assert cache.get_workflow_id("group-B") == "workflow-B"

    def test_cache_miss_for_wrong_tenant(self):
        """Cache entry for tenant-A is invisible to tenant-B."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Malware Alert",
            group_id="group-1",
            workflow_id="workflow-1",
            tenant_id="tenant-alpha",
        )

        # Same title, different tenant — should miss
        assert cache.get_group_id("Malware Alert", tenant_id="tenant-beta") is None

    def test_clear_removes_all_tenant_entries(self):
        """Clear wipes entries for all tenants."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Rule",
            group_id="g1",
            workflow_id="w1",
            tenant_id="t1",
        )
        cache.set_group(
            title="Rule",
            group_id="g2",
            workflow_id="w2",
            tenant_id="t2",
        )

        cache.clear()

        assert cache.get_group_id("Rule", tenant_id="t1") is None
        assert cache.get_group_id("Rule", tenant_id="t2") is None
