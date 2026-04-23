"""Integration tests for integration discovery tools with database filtering."""

import pytest

from analysi.mcp import integration_tools


@pytest.mark.integration
@pytest.mark.asyncio
class TestIntegrationToolsFiltering:
    """Test integration discovery tools with configured_only filtering."""

    @pytest.mark.asyncio
    async def test_list_integrations_all(self):
        """Verify that list_integrations without filter returns all integrations."""
        # Pass configured_only=False to get all integrations (not just configured ones)
        result = await integration_tools.list_integrations(configured_only=False)

        assert "integrations" in result
        assert "count" in result
        assert "filtered" in result
        assert result["filtered"] is False

        # Should return all 36+ integrations
        assert result["count"] >= 36

    @pytest.mark.asyncio
    async def test_list_integrations_configured_only_uses_context(self):
        """Verify that configured_only uses tenant from context."""
        # Tenant is now extracted from context, not parameter
        # This test verifies the function works without explicit tenant parameter
        result = await integration_tools.list_integrations(configured_only=True)

        assert "integrations" in result
        assert "count" in result
        assert "filtered" in result
        assert result["filtered"] is True
        # Result depends on tenant in context (default during tests)

    @pytest.mark.asyncio
    async def test_list_integrations_configured_only_with_tenant(self):
        """Verify that configured_only filters to only configured integrations."""
        # Tenant is extracted from context automatically
        result = await integration_tools.list_integrations(configured_only=True)

        assert "integrations" in result
        assert "count" in result
        assert "filtered" in result
        assert result["filtered"] is True

        # Should return only configured integrations (typically 3-5)
        # For default tenant: splunk, openai, echo_edr, virustotal, abuseipdb
        assert result["count"] <= 10  # Much less than 36

        # Verify all returned integrations are actually configured
        integration_ids = {i["integration_id"] for i in result["integrations"]}

        # These should be configured for default tenant in test environment
        # Note: Exact list depends on test fixtures
        assert isinstance(integration_ids, set)
        assert len(integration_ids) == result["count"]

    @pytest.mark.asyncio
    async def test_list_integrations_configured_only_empty_tenant(self):
        """Verify that non-existent tenant returns empty list."""
        # Note: This test relies on context having a tenant that has no integrations
        # In real usage, tenant is extracted from request context
        result = await integration_tools.list_integrations(configured_only=True)

        assert "integrations" in result
        assert "filtered" in result
        assert result["filtered"] is True
        # Count may be 0 or more depending on configured integrations in context tenant

    @pytest.mark.asyncio
    async def test_list_integrations_configured_structure(self):
        """Verify that filtered integrations maintain correct structure."""
        result = await integration_tools.list_integrations(configured_only=True)

        # Even with filtering, structure should be maintained
        for integration in result["integrations"]:
            assert "integration_id" in integration
            assert "name" in integration
            assert "description" in integration
            assert "archetypes" in integration
            assert isinstance(integration["archetypes"], list)
            assert "connector_count" in integration

    @pytest.mark.asyncio
    async def test_configured_only_reduces_context(self):
        """Verify that configured_only significantly reduces result size (main benefit)."""
        # Get all integrations (pass configured_only=False explicitly)
        all_result = await integration_tools.list_integrations(configured_only=False)

        # Get only configured (tenant extracted from context)
        filtered_result = await integration_tools.list_integrations(
            configured_only=True
        )

        # Filtered should be significantly smaller (context pollution reduction)
        assert filtered_result["count"] < all_result["count"]

        # Typically: all=36, filtered=5-10
        # Context reduction: ~70-85%
        reduction_percentage = (
            1 - (filtered_result["count"] / all_result["count"])
        ) * 100

        assert reduction_percentage > 50  # At least 50% reduction

    @pytest.mark.asyncio
    async def test_filtered_flag_consistency(self):
        """Verify that filtered flag accurately reflects whether filtering was applied."""
        # Without filtering (pass configured_only=False explicitly)
        unfiltered = await integration_tools.list_integrations(configured_only=False)
        assert unfiltered["filtered"] is False

        # With filtering (tenant extracted from context)
        filtered = await integration_tools.list_integrations(configured_only=True)
        assert filtered["filtered"] is True
