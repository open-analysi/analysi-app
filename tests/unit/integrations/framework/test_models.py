"""
Unit tests for Integrations Framework Pydantic models.

Tests UT-02.1 through UT-02.9 from TEST_PLAN.md
"""

import pytest
from pydantic import ValidationError

from analysi.integrations.framework.models import (
    ActionDefinition,
    IntegrationManifest,
)


class TestIntegrationManifest:
    """Test IntegrationManifest Pydantic validation."""

    def test_ut_02_1_valid_manifest(self):
        """UT-02.1: Create valid IntegrationManifest with all required fields, verify parsing succeeds."""
        manifest = IntegrationManifest(
            id="virustotal",
            app="virustotal",
            name="VirusTotal",
            version="1.0.0",
            archetypes=["ThreatIntel"],
            priority=80,
            archetype_mappings={
                "ThreatIntel": {
                    "lookup_ip": "lookup_ip_action",
                    "lookup_domain": "lookup_domain_action",
                    "lookup_file_hash": "lookup_hash_action",
                    "lookup_url": "lookup_url_action",
                }
            },
            actions=[
                ActionDefinition(
                    id="lookup_ip_action", type="tool", categories=["investigation"]
                )
            ],
        )

        assert manifest.id == "virustotal"
        assert manifest.app == "virustotal"
        assert manifest.name == "VirusTotal"
        assert manifest.version == "1.0.0"
        assert manifest.archetypes == ["ThreatIntel"]
        assert manifest.priority == 80
        assert len(manifest.actions) == 1

    def test_ut_02_2_missing_required_field(self):
        """UT-02.2: Create manifest missing required field (e.g., id), verify ValidationError raised."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationManifest(
                # Missing 'id' field
                app="test",
                name="Test",
                version="1.0.0",
                archetypes=[],
                priority=50,
                archetype_mappings={},
                actions=[],
            )

        assert "id" in str(exc_info.value)

    def test_ut_02_3_invalid_priority_values(self):
        """UT-02.3: Create manifest with invalid priority (0, 101, -1), verify ValidationError raised."""
        # Priority 0 - below minimum
        with pytest.raises(ValidationError) as exc_info:
            IntegrationManifest(
                id="test",
                app="test",
                name="Test",
                version="1.0.0",
                archetypes=[],
                priority=0,
                archetype_mappings={},
                actions=[],
            )
        assert "priority" in str(exc_info.value).lower()

        # Priority 101 - above maximum
        with pytest.raises(ValidationError) as exc_info:
            IntegrationManifest(
                id="test",
                app="test",
                name="Test",
                version="1.0.0",
                archetypes=[],
                priority=101,
                archetype_mappings={},
                actions=[],
            )
        assert "priority" in str(exc_info.value).lower()

        # Priority -1 - negative
        with pytest.raises(ValidationError) as exc_info:
            IntegrationManifest(
                id="test",
                app="test",
                name="Test",
                version="1.0.0",
                archetypes=[],
                priority=-1,
                archetype_mappings={},
                actions=[],
            )
        assert "priority" in str(exc_info.value).lower()

    def test_ut_02_4_priority_boundary_values(self):
        """UT-02.4: Create manifest with priority 1 and 100 (boundary values), verify success."""
        # Priority 1 (minimum)
        manifest1 = IntegrationManifest(
            id="test1",
            app="test",
            name="Test",
            version="1.0.0",
            archetypes=[],
            priority=1,
            archetype_mappings={},
            actions=[],
        )
        assert manifest1.priority == 1

        # Priority 100 (maximum)
        manifest100 = IntegrationManifest(
            id="test100",
            app="test",
            name="Test",
            version="1.0.0",
            archetypes=[],
            priority=100,
            archetype_mappings={},
            actions=[],
        )
        assert manifest100.priority == 100


class TestActionDefinition:
    """Test ActionDefinition Pydantic validation."""

    def test_ut_02_5_legacy_type_field_absorbed_by_extra(self):
        """UT-02.5: Legacy type field is absorbed by extra='allow', not rejected.

        type/purpose are no longer explicit model fields.
        They are accepted as extra fields for backward compat.
        """
        # Should NOT raise -- extra="allow" absorbs unknown fields
        action = ActionDefinition(id="test", type="invalid_type")  # type: ignore[call-arg]
        assert action.id == "test"

    def test_ut_02_6_action_with_categories(self):
        """UT-02.6: Create action with categories for health monitoring."""
        action = ActionDefinition(
            id="health_check",
            categories=["health_monitoring"],
            description="Check system health",
        )

        assert action.id == "health_check"
        assert action.categories == ["health_monitoring"]

    def test_ut_02_7_action_default_categories(self):
        """UT-02.7: Create action without categories, defaults to empty list."""
        action = ActionDefinition(id="health_check")

        assert action.id == "health_check"
        assert action.categories == []

    def test_ut_02_8_tool_action_with_categories(self):
        """UT-02.8: Create tool action with categories, verify validation passes."""
        action = ActionDefinition(
            id="lookup_ip",
            name="IP Lookup",
            description="Look up IP address information",
            categories=["investigation", "enrichment"],
        )

        assert action.id == "lookup_ip"
        assert action.categories == ["investigation", "enrichment"]

    def test_ut_02_9_manifest_with_multiple_archetypes(self):
        """UT-02.9: Create manifest with multiple archetypes, verify all stored."""
        manifest = IntegrationManifest(
            id="hybrid-integration",
            app="hybrid",
            name="Hybrid Integration",
            version="1.0.0",
            archetypes=["ThreatIntel", "SIEM", "EDR"],
            priority=50,
            archetype_mappings={
                "ThreatIntel": {"lookup_ip": "lookup_ip_action"},
                "SIEM": {"query_events": "query_action"},
                "EDR": {"isolate_host": "isolate_action"},
            },
            actions=[
                ActionDefinition(id="lookup_ip_action", categories=["investigation"]),
                ActionDefinition(id="query_action", categories=["alert_ingestion"]),
                ActionDefinition(id="isolate_action", categories=["response"]),
            ],
        )

        assert len(manifest.archetypes) == 3
        assert "ThreatIntel" in manifest.archetypes
        assert "SIEM" in manifest.archetypes
        assert "EDR" in manifest.archetypes
        assert len(manifest.archetype_mappings) == 3
        assert len(manifest.actions) == 3
