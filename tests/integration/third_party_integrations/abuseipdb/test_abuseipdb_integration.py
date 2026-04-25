"""
Integration tests for AbuseIPDB framework integration.

End-to-end tests for AbuseIPDB integration via Naxos framework.
Includes REQUIRED real API tests.
"""

import os

import pytest

from analysi.integrations.framework.integrations.abuseipdb.actions import (
    HealthCheckAction,
    LookupIpAction,
    ReportIpAction,
)
from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)


@pytest.fixture
def abuseipdb_api_key():
    """Provide real AbuseIPDB API key from environment.

    REQUIRED: Tests will FAIL with clear message if key not set.
    Get free key: https://www.abuseipdb.com/ (1,000 requests/day)
    """
    api_key = os.getenv("ABUSEIPDB_API_KEY")
    if not api_key:
        pytest.fail(
            "\n\n"
            "❌ ABUSEIPDB_API_KEY not set in .env.test\n"
            "📝 Get free API key: https://www.abuseipdb.com/\n"
            "💾 Add to .env.test: ABUSEIPDB_API_KEY=your-key\n"
            "   (1,000 requests/day free tier)\n"
        )
    return api_key


@pytest.mark.integration
@pytest.mark.asyncio
class TestAbuseIPDBIntegrationEndToEnd:
    """End-to-end integration tests for AbuseIPDB."""

    @pytest.mark.asyncio
    async def test_abuseipdb_discovered_by_registry(self):
        """Test: Registry returns AbuseIPDB with ThreatIntel archetype.

        Goal: Ensure AbuseIPDB discovered with ThreatIntel archetype.
        """
        registry = IntegrationRegistry()

        # List all integrations
        integrations = registry.list_integrations()

        # Find AbuseIPDB
        abuseipdb = next((i for i in integrations if i.id == "abuseipdb"), None)

        assert abuseipdb is not None, "AbuseIPDB should be discovered by registry"
        assert abuseipdb.name == "AbuseIPDB"

        # Verify ThreatIntel archetype
        assert "ThreatIntel" in abuseipdb.archetypes, (
            f"AbuseIPDB should have ThreatIntel archetype, got {abuseipdb.archetypes}"
        )

        # Verify priority
        assert abuseipdb.priority == 70, (
            f"AbuseIPDB should have priority 70, got {abuseipdb.priority}"
        )

        # Should have 6 actions:
        # - health_check (connector)
        # - lookup_ip, report_ip (fully implemented tools)
        # - lookup_domain, lookup_file_hash, lookup_url (stub tools for ThreatIntel archetype compliance)
        assert len(abuseipdb.actions) == 6, (
            f"AbuseIPDB should have 6 actions, got {len(abuseipdb.actions)}"
        )

    @pytest.mark.asyncio
    async def test_abuseipdb_has_correct_archetype_mappings(self):
        """Test: AbuseIPDB has correct ThreatIntel archetype mappings.

        Goal: Verify ThreatIntel methods are properly mapped.
        """
        registry = IntegrationRegistry()
        abuseipdb = registry.get_integration("abuseipdb")

        assert abuseipdb is not None, "AbuseIPDB should be in registry"

        # Verify ThreatIntel archetype mappings
        mappings = abuseipdb.archetype_mappings.get("ThreatIntel", {})

        # Fully implemented methods
        assert mappings.get("lookup_ip") == "lookup_ip"
        assert mappings.get("submit_ioc") == "report_ip"

        # Stub methods (satisfy archetype requirements but return "not supported" errors)
        assert mappings.get("lookup_domain") == "lookup_domain"
        assert mappings.get("lookup_file_hash") == "lookup_file_hash"
        assert mappings.get("lookup_url") == "lookup_url"

    @pytest.mark.asyncio
    async def test_abuseipdb_actions_are_registered(self):
        """Test: AbuseIPDB actions are registered with correct types.

        Goal: Verify all 6 actions are registered with correct metadata.
        """
        registry = IntegrationRegistry()
        abuseipdb = registry.get_integration("abuseipdb")

        assert abuseipdb is not None, "AbuseIPDB should be in registry"

        # Get action IDs
        action_ids = [a.id for a in abuseipdb.actions]

        # Verify all expected actions are present (including stubs)
        expected_actions = [
            "health_check",
            "lookup_ip",
            "report_ip",
            "lookup_domain",  # Stub - ThreatIntel archetype compliance
            "lookup_file_hash",  # Stub - ThreatIntel archetype compliance
            "lookup_url",  # Stub - ThreatIntel archetype compliance
        ]

        for action_id in expected_actions:
            assert action_id in action_ids, f"Action {action_id} should be registered"

        # Verify health_check has health_monitoring category
        health_check = next(a for a in abuseipdb.actions if a.id == "health_check")
        assert "health_monitoring" in health_check.categories

        # Verify lookup_ip is a tool action
        lookup_ip = next(a for a in abuseipdb.actions if a.id == "lookup_ip")
        assert "threat_intel" in lookup_ip.categories

        # Verify report_ip action
        report_ip = next(a for a in abuseipdb.actions if a.id == "report_ip")
        assert "threat_intel" in report_ip.categories


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegistryIncludesAbuseIPDB:
    """Test registry list_integrations includes AbuseIPDB."""

    @pytest.mark.asyncio
    async def test_registry_lists_abuseipdb(self):
        """Test: Registry list_integrations includes AbuseIPDB.

        Goal: Verify registry lists AbuseIPDB with other integrations.
        """
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        integration_ids = [i.id for i in integrations]

        # Should have at least these integrations
        assert "splunk" in integration_ids, "Should have Splunk"
        assert "openai" in integration_ids, "Should have OpenAI"
        assert "echo_edr" in integration_ids, "Should have Echo EDR"
        assert "virustotal" in integration_ids, "Should have VirusTotal"
        assert "abuseipdb" in integration_ids, "Should have AbuseIPDB"

        # Verify AbuseIPDB archetype
        abuseipdb = next(i for i in integrations if i.id == "abuseipdb")
        assert "ThreatIntel" in abuseipdb.archetypes


@pytest.mark.integration
@pytest.mark.asyncio
class TestManifestValidation:
    """Test AbuseIPDB manifest is valid."""

    @pytest.mark.asyncio
    async def test_abuseipdb_manifest_validation(self):
        """Test: Manifest is valid and parseable by framework.

        Goal: Verify manifest validates successfully.
        """
        registry = IntegrationRegistry()
        abuseipdb = registry.get_integration("abuseipdb")

        assert abuseipdb is not None, "AbuseIPDB should load successfully"

        # Verify required fields
        assert abuseipdb.id == "abuseipdb"
        assert abuseipdb.name == "AbuseIPDB"
        assert abuseipdb.version == "1.0.0"

        # Verify credential schema (singular, not "credentials_schema")
        assert abuseipdb.credential_schema is not None
        assert "api_key" in abuseipdb.credential_schema["properties"]
        assert "api_key" in abuseipdb.credential_schema["required"]


# =====================================================================
# REQUIRED: Real AbuseIPDB API Tests 🔴
# =====================================================================
# These tests will FAIL if ABUSEIPDB_API_KEY not set in .env.test
# Get free API key: https://www.abuseipdb.com/ (1,000 requests/day)
# =====================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.requires_api
class TestRealAbuseIPDBAPI:
    """REQUIRED: Real AbuseIPDB API tests.

    ⚠️ These tests will FAIL if ABUSEIPDB_API_KEY not provided in .env.test.
    Marked ``requires_api`` so they're excluded from standard CI runs that
    don't provision external API keys (same pattern as NIST NVD).
    """

    @pytest.mark.asyncio
    async def test_real_api_health_check(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify health check works with real AbuseIPDB API.

        Test Data: Reports 127.0.0.1 with test category (safe).
        Expected: Returns {"status": "success", "healthy": True}
        """
        action = HealthCheckAction(
            integration_id="abuseipdb-test",
            action_id="health_check",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert "message" in result

    @pytest.mark.asyncio
    async def test_real_api_lookup_known_ip(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify IP lookup works with real API.

        Test Data: Use well-known safe IP (8.8.8.8 Google DNS)
        Expected: Returns success with reputation data
        """
        action = LookupIpAction(
            integration_id="abuseipdb-test",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        result = await action.execute(ip="8.8.8.8", days=30)

        # Verify response structure
        assert result["status"] == "success"
        assert result["ip_address"] == "8.8.8.8"
        assert "abuse_confidence_score" in result
        assert "total_reports" in result
        assert "full_data" in result

        # Verify full_data has AbuseIPDB response structure
        full_data = result["full_data"]
        assert "data" in full_data
        assert "ipAddress" in full_data["data"]

    @pytest.mark.asyncio
    async def test_real_api_lookup_multiple_ips(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify multiple lookups work correctly.

        Test Data: Lookup 3 different IPs (8.8.8.8, 1.1.1.1, 9.9.9.9)
        Expected: All 3 return success, response structure consistent
        """
        action = LookupIpAction(
            integration_id="abuseipdb-test",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        test_ips = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

        for test_ip in test_ips:
            result = await action.execute(ip=test_ip, days=30)

            assert result["status"] == "success", f"Lookup failed for {test_ip}"
            assert result["ip_address"] == test_ip
            assert "abuse_confidence_score" in result
            assert "total_reports" in result

    @pytest.mark.asyncio
    async def test_real_api_report_test_ip(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify IP reporting works with real API.

        Test Data:
        - IP: 127.0.0.1 (localhost - safe to report)
        - Categories: "4" (Hacking - test category)
        - Comment: "Phase 23 integration test - safe to ignore"

        Expected: Returns success with confirmation
        Note: 127.0.0.1 won't pollute AbuseIPDB database
        Note: May skip if rate limit exceeded (1,000/day quota on free tier)
        """
        action = ReportIpAction(
            integration_id="abuseipdb-test",
            action_id="report_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        result = await action.execute(
            ip="127.0.0.1",
            categories="4",
            comment="Phase 23 AbuseIPDB integration test - safe to ignore",
        )

        # Skip if rate limited (expected on free tier after heavy testing)
        if result["status"] == "error" and "Rate limit exceeded" in result.get(
            "error", ""
        ):
            pytest.skip(
                "AbuseIPDB rate limit exceeded - test would pass with available quota"
            )

        assert result["status"] == "success"
        assert result["ip_address"] == "127.0.0.1"
        assert "abuse_confidence_score" in result

    @pytest.mark.asyncio
    async def test_real_api_ipv6_lookup(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify IPv6 addresses work.

        Test Data: 2001:4860:4860::8888 (Google DNS IPv6)
        Expected: Returns success, handles IPv6
        """
        action = LookupIpAction(
            integration_id="abuseipdb-test",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        result = await action.execute(ip="2001:4860:4860::8888", days=30)

        assert result["status"] == "success"
        assert result["ip_address"] == "2001:4860:4860::8888"
        assert "abuse_confidence_score" in result

    @pytest.mark.asyncio
    async def test_real_api_error_handling(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify error handling with real API.

        Test Cases:
        - Invalid IP → Validation error before API call
        - Large days param (days=1000) → Handle gracefully

        Expected: Proper error responses, no crashes
        """
        action = LookupIpAction(
            integration_id="abuseipdb-test",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        # Test 1: Invalid IP - should fail validation before API call
        result = await action.execute(ip="not.an.ip")
        assert result["status"] == "error"
        assert "Invalid IP address format" in result["error"]

        # Test 2: Very large days param - should work or fail gracefully
        result = await action.execute(ip="8.8.8.8", days=365)
        # Either succeeds or returns error (not crash)
        assert "status" in result
        assert result["status"] in ["success", "error"]

    @pytest.mark.asyncio
    async def test_real_api_response_structure(self, abuseipdb_api_key):
        """REQUIRED ✅: Verify response matches expected format.

        Test Data: Lookup 8.8.8.8
        Verification:
        - Has: status, ip_address, full_data
        - full_data.data exists (AbuseIPDB format)
        """
        action = LookupIpAction(
            integration_id="abuseipdb-test",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": abuseipdb_api_key},
        )

        result = await action.execute(ip="8.8.8.8", days=30)

        # Verify top-level structure
        assert "status" in result
        assert "ip_address" in result
        assert "full_data" in result

        # Verify AbuseIPDB response structure
        full_data = result["full_data"]
        assert "data" in full_data, "AbuseIPDB response should have 'data' key"

        data = full_data["data"]
        assert "ipAddress" in data
        assert "abuseConfidenceScore" in data
        assert "totalReports" in data
