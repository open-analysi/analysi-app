"""
Unit tests for IntegrationRegistryService.

Tests UT-04.1 through UT-04.10 from TEST_PLAN.md
"""

import json
import tempfile
from pathlib import Path

from analysi.integrations.framework.models import (
    ActionDefinition,
    IntegrationManifest,
)
from analysi.integrations.framework.registry import IntegrationRegistryService


class TestIntegrationRegistryService:
    """Test IntegrationRegistryService discovery and query methods."""

    def test_ut_04_1_get_integration(self):
        """UT-04.1: Create registry, add one integration, verify get_integration() returns it."""
        # Create registry with empty path (won't auto-load)
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Manually add integration to registry
            manifest = IntegrationManifest(
                id="test-integration",
                app="test",
                name="Test Integration",
                version="1.0.0",
                archetypes=[],
                priority=50,
                archetype_mappings={},
                actions=[],
            )
            registry.registry["test-integration"] = manifest

            # Verify get_integration returns it
            retrieved = registry.get_integration("test-integration")
            assert retrieved is not None
            assert retrieved.id == "test-integration"
            assert retrieved.name == "Test Integration"

    def test_ut_04_2_list_integrations(self):
        """UT-04.2: Add multiple integrations, verify list_integrations() returns all."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add multiple integrations
            manifests = [
                IntegrationManifest(
                    id=f"integration-{i}",
                    app=f"app{i}",
                    name=f"Integration {i}",
                    version="1.0.0",
                    archetypes=[],
                    priority=50,
                    archetype_mappings={},
                    actions=[],
                )
                for i in range(3)
            ]

            for manifest in manifests:
                registry.registry[manifest.id] = manifest

            # Verify list_integrations returns all
            all_integrations = registry.list_integrations()
            assert len(all_integrations) == 3
            assert all(isinstance(m, IntegrationManifest) for m in all_integrations)

    def test_ut_04_3_get_nonexistent_integration(self):
        """UT-04.3: Query non-existent integration, verify returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            result = registry.get_integration("nonexistent")
            assert result is None

    def test_ut_04_4_list_by_archetype_filtering(self):
        """UT-04.4: Add integrations with different archetypes, verify list_by_archetype() filters correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add integrations with different archetypes
            virustotal = IntegrationManifest(
                id="virustotal",
                app="virustotal",
                name="VirusTotal",
                version="1.0.0",
                archetypes=["ThreatIntel"],
                priority=90,
                archetype_mappings={"ThreatIntel": {}},
                actions=[],
            )

            splunk = IntegrationManifest(
                id="splunk",
                app="splunk",
                name="Splunk",
                version="1.0.0",
                archetypes=["SIEM"],
                priority=80,
                archetype_mappings={"SIEM": {}},
                actions=[],
            )

            crowdstrike = IntegrationManifest(
                id="crowdstrike",
                app="crowdstrike",
                name="CrowdStrike",
                version="1.0.0",
                archetypes=["EDR"],
                priority=85,
                archetype_mappings={"EDR": {}},
                actions=[],
            )

            registry.registry["virustotal"] = virustotal
            registry.registry["splunk"] = splunk
            registry.registry["crowdstrike"] = crowdstrike

            # Test filtering
            threatintel_integrations = registry.list_by_archetype("ThreatIntel")
            assert len(threatintel_integrations) == 1
            assert threatintel_integrations[0].id == "virustotal"

            siem_integrations = registry.list_by_archetype("SIEM")
            assert len(siem_integrations) == 1
            assert siem_integrations[0].id == "splunk"

            edr_integrations = registry.list_by_archetype("EDR")
            assert len(edr_integrations) == 1
            assert edr_integrations[0].id == "crowdstrike"

    def test_ut_04_5_list_by_archetype_priority_sorting(self):
        """UT-04.5: Add integrations with same archetype but different priorities, verify sorted by priority descending."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add ThreatIntel integrations with different priorities
            integrations = [
                IntegrationManifest(
                    id="virustotal",
                    app="virustotal",
                    name="VirusTotal",
                    version="1.0.0",
                    archetypes=["ThreatIntel"],
                    priority=90,
                    archetype_mappings={"ThreatIntel": {}},
                    actions=[],
                ),
                IntegrationManifest(
                    id="abuseipdb",
                    app="abuseipdb",
                    name="AbuseIPDB",
                    version="1.0.0",
                    archetypes=["ThreatIntel"],
                    priority=70,
                    archetype_mappings={"ThreatIntel": {}},
                    actions=[],
                ),
                IntegrationManifest(
                    id="alienvault",
                    app="alienvault",
                    name="AlienVault OTX",
                    version="1.0.0",
                    archetypes=["ThreatIntel"],
                    priority=60,
                    archetype_mappings={"ThreatIntel": {}},
                    actions=[],
                ),
            ]

            for manifest in integrations:
                registry.registry[manifest.id] = manifest

            # Verify sorted by priority descending
            threatintel = registry.list_by_archetype("ThreatIntel")
            assert len(threatintel) == 3
            assert threatintel[0].id == "virustotal"  # Priority 90
            assert threatintel[1].id == "abuseipdb"  # Priority 70
            assert threatintel[2].id == "alienvault"  # Priority 60

    def test_ut_04_6_get_primary_integration(self):
        """UT-04.6: Get primary integration for archetype, verify highest priority returned."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add integrations
            integrations = [
                IntegrationManifest(
                    id="virustotal",
                    app="virustotal",
                    name="VirusTotal",
                    version="1.0.0",
                    archetypes=["ThreatIntel"],
                    priority=90,
                    archetype_mappings={"ThreatIntel": {}},
                    actions=[],
                ),
                IntegrationManifest(
                    id="abuseipdb",
                    app="abuseipdb",
                    name="AbuseIPDB",
                    version="1.0.0",
                    archetypes=["ThreatIntel"],
                    priority=70,
                    archetype_mappings={"ThreatIntel": {}},
                    actions=[],
                ),
            ]

            for manifest in integrations:
                registry.registry[manifest.id] = manifest

            # Get primary should return highest priority
            primary = registry.get_primary_integration_for_archetype("ThreatIntel")
            assert primary is not None
            assert primary.id == "virustotal"
            assert primary.priority == 90

    def test_ut_04_7_get_primary_no_implementations(self):
        """UT-04.7: Get primary integration for archetype with no implementations, verify returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add integrations with different archetypes
            splunk = IntegrationManifest(
                id="splunk",
                app="splunk",
                name="Splunk",
                version="1.0.0",
                archetypes=["SIEM"],
                priority=80,
                archetype_mappings={"SIEM": {}},
                actions=[],
            )
            registry.registry["splunk"] = splunk

            # Query for archetype with no implementations
            primary = registry.get_primary_integration_for_archetype("ThreatIntel")
            assert primary is None

    def test_ut_04_8_resolve_archetype_action(self):
        """UT-04.8: Resolve archetype action (ThreatIntel.lookup_ip), verify correct action_id returned."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add integration with archetype mapping
            virustotal = IntegrationManifest(
                id="virustotal",
                app="virustotal",
                name="VirusTotal",
                version="1.0.0",
                archetypes=["ThreatIntel"],
                priority=90,
                archetype_mappings={
                    "ThreatIntel": {
                        "lookup_ip": "vt_ip_lookup",
                        "lookup_domain": "vt_domain_lookup",
                        "lookup_file_hash": "vt_hash_lookup",
                        "lookup_url": "vt_url_lookup",
                    }
                },
                actions=[
                    ActionDefinition(
                        id="vt_ip_lookup", type="tool", categories=["investigation"]
                    ),
                ],
            )
            registry.registry["virustotal"] = virustotal

            # Resolve archetype method
            action_id = registry.resolve_archetype_action(
                "virustotal", "ThreatIntel", "lookup_ip"
            )
            assert action_id == "vt_ip_lookup"

    def test_ut_04_9_resolve_unmapped_method(self):
        """UT-04.9: Resolve archetype action for unmapped method, verify returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = IntegrationRegistryService(integrations_path=Path(temp_dir))

            # Add integration with partial archetype mapping
            partial = IntegrationManifest(
                id="partial",
                app="partial",
                name="Partial Integration",
                version="1.0.0",
                archetypes=["ThreatIntel"],
                priority=50,
                archetype_mappings={
                    "ThreatIntel": {
                        "lookup_ip": "ip_action",
                        # Missing other methods
                    }
                },
                actions=[],
            )
            registry.registry["partial"] = partial

            # Resolve unmapped method
            action_id = registry.resolve_archetype_action(
                "partial", "ThreatIntel", "lookup_domain"
            )
            assert action_id is None

    def test_ut_04_10_reload_registry(self):
        """UT-04.10: Reload registry, verify updated manifests reflected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create initial integration
            integration_dir = temp_path / "test-integration"
            integration_dir.mkdir()

            manifest_v1 = {
                "id": "test-integration",
                "app": "test",
                "name": "Test Integration v1",
                "version": "1.0.0",
                "archetypes": [],
                "priority": 50,
                "archetype_mappings": {},
                "actions": [],
            }

            manifest_path = integration_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest_v1, f)

            # Create registry and load
            registry = IntegrationRegistryService(integrations_path=temp_path)

            initial = registry.get_integration("test-integration")
            assert initial is not None
            assert initial.name == "Test Integration v1"

            # Update manifest
            manifest_v2 = {
                "id": "test-integration",
                "app": "test",
                "name": "Test Integration v2",  # Changed name
                "version": "2.0.0",  # Changed version
                "archetypes": [],
                "priority": 50,
                "archetype_mappings": {},
                "actions": [],
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_v2, f)

            # Reload
            registry.reload()

            # Verify updated manifest reflected
            updated = registry.get_integration("test-integration")
            assert updated is not None
            assert updated.name == "Test Integration v2"
            assert updated.version == "2.0.0"
