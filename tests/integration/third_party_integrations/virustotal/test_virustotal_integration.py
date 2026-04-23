"""
Integration tests for VirusTotal framework integration.

End-to-end tests for VirusTotal integration via Naxos framework.
"""

import pytest

from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestVirusTotalIntegrationEndToEnd:
    """End-to-end integration tests for VirusTotal."""

    @pytest.mark.asyncio
    async def test_virustotal_discovered_by_registry(self):
        """Test: Registry returns VirusTotal with ThreatIntel archetype.

        Goal: Ensure VirusTotal discovered with ThreatIntel archetype.
        """
        registry = IntegrationRegistry()

        # List all integrations
        integrations = registry.list_integrations()

        # Find VirusTotal
        virustotal = next((i for i in integrations if i.id == "virustotal"), None)

        assert virustotal is not None, "VirusTotal should be discovered by registry"
        assert virustotal.name == "VirusTotal"

        # Verify ThreatIntel archetype
        assert "ThreatIntel" in virustotal.archetypes, (
            f"VirusTotal should have ThreatIntel archetype, got {virustotal.archetypes}"
        )

        # Verify priority
        assert virustotal.priority == 80, (
            f"VirusTotal should have priority 80, got {virustotal.priority}"
        )

        # Should have 7 actions (health_check + 6 reputation/analysis tools)
        assert len(virustotal.actions) == 7, (
            f"VirusTotal should have 7 actions, got {len(virustotal.actions)}"
        )

    @pytest.mark.asyncio
    async def test_virustotal_has_correct_archetype_mappings(self):
        """Test: VirusTotal has correct ThreatIntel archetype mappings.

        Goal: Verify ThreatIntel methods are properly mapped.
        """
        registry = IntegrationRegistry()
        virustotal = registry.get_integration("virustotal")

        assert virustotal is not None, "VirusTotal should be in registry"

        # Verify ThreatIntel archetype mappings
        mappings = virustotal.archetype_mappings.get("ThreatIntel", {})

        assert mappings.get("lookup_ip") == "ip_reputation"
        assert mappings.get("lookup_domain") == "domain_reputation"
        assert mappings.get("lookup_file_hash") == "file_reputation"
        assert mappings.get("lookup_url") == "url_reputation"

    @pytest.mark.asyncio
    async def test_virustotal_actions_are_registered(self):
        """Test: VirusTotal actions are registered with correct types.

        Goal: Verify all 7 actions are registered with correct metadata.
        """
        registry = IntegrationRegistry()
        virustotal = registry.get_integration("virustotal")

        assert virustotal is not None, "VirusTotal should be in registry"

        # Get action IDs
        action_ids = [a.id for a in virustotal.actions]

        # Verify all expected actions are present
        expected_actions = [
            "health_check",
            "ip_reputation",
            "domain_reputation",
            "url_reputation",
            "file_reputation",
            "submit_url_analysis",
            "get_analysis_report",
        ]

        for action_id in expected_actions:
            assert action_id in action_ids, f"Action {action_id} should be registered"

        # Verify health_check has health_monitoring category
        health_check = next(a for a in virustotal.actions if a.id == "health_check")
        assert "health_monitoring" in health_check.categories

        # Verify reputation tools have correct categories
        ip_reputation = next(a for a in virustotal.actions if a.id == "ip_reputation")
        assert "threat_intel" in ip_reputation.categories


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegistryIncludesVirusTotal:
    """Test registry list_integrations includes VirusTotal."""

    @pytest.mark.asyncio
    async def test_registry_lists_virustotal(self):
        """Test: Registry list_integrations includes VirusTotal.

        Goal: Verify registry lists VirusTotal with other integrations.
        """
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        integration_ids = [i.id for i in integrations]

        # Should have at least these 4
        assert "splunk" in integration_ids, "Should have Splunk"
        assert "openai" in integration_ids, "Should have OpenAI"
        assert "echo_edr" in integration_ids, "Should have Echo EDR"
        assert "virustotal" in integration_ids, "Should have VirusTotal"

        # Verify archetypes
        splunk = next(i for i in integrations if i.id == "splunk")
        openai = next(i for i in integrations if i.id == "openai")
        echo_edr = next(i for i in integrations if i.id == "echo_edr")
        virustotal = next(i for i in integrations if i.id == "virustotal")

        # Check archetypes
        assert "SIEM" in splunk.archetypes
        assert "AI" in openai.archetypes
        assert "EDR" in echo_edr.archetypes
        assert "ThreatIntel" in virustotal.archetypes
