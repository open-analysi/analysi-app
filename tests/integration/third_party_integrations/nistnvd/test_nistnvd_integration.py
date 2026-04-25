"""
Integration tests for NIST NVD framework integration.

End-to-end tests for NIST NVD integration via Naxos framework.
Includes real API tests (no API key required - public API).
"""

import pytest

from analysi.integrations.framework.integrations.nistnvd.actions import (
    CveLookupAction,
    HealthCheckAction,
)
from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestNISTNVDIntegrationEndToEnd:
    """End-to-end integration tests for NIST NVD."""

    @pytest.mark.asyncio
    async def test_nistnvd_discovered_by_registry(self):
        """Test: Registry returns NIST NVD with DatabaseEnrichment archetype.

        Goal: Ensure NIST NVD discovered with DatabaseEnrichment archetype.
        Note: NIST NVD is a CVE lookup database, not a vulnerability scanner.
        """
        registry = IntegrationRegistry()

        # List all integrations
        integrations = registry.list_integrations()

        # Find NIST NVD
        nistnvd = next((i for i in integrations if i.id == "nistnvd"), None)

        assert nistnvd is not None, "NIST NVD should be discovered by registry"
        assert nistnvd.name == "NIST NVD"

        # Verify DatabaseEnrichment archetype
        assert "DatabaseEnrichment" in nistnvd.archetypes, (
            f"NIST NVD should have DatabaseEnrichment archetype, got {nistnvd.archetypes}"
        )

        # Verify priority
        assert nistnvd.priority == 70, (
            f"NIST NVD should have priority 70, got {nistnvd.priority}"
        )

        # Should have 2 actions (health_check + cve_lookup)
        assert len(nistnvd.actions) == 2, (
            f"NIST NVD should have 2 actions, got {len(nistnvd.actions)}"
        )

    @pytest.mark.asyncio
    async def test_nistnvd_has_correct_archetype_mappings(self):
        """Test: NIST NVD has correct DatabaseEnrichment archetype mappings.

        Goal: Verify DatabaseEnrichment methods are properly mapped.
        """
        registry = IntegrationRegistry()
        nistnvd = registry.get_integration("nistnvd")

        assert nistnvd is not None, "NIST NVD should be in registry"

        # Verify DatabaseEnrichment archetype mappings
        mappings = nistnvd.archetype_mappings.get("DatabaseEnrichment", {})

        assert mappings.get("get_vulnerabilities") == "cve_lookup"

    @pytest.mark.asyncio
    async def test_nistnvd_actions_are_registered(self):
        """Test: NIST NVD actions are registered with correct types.

        Goal: Verify all 2 actions are registered with correct metadata.
        """
        registry = IntegrationRegistry()
        nistnvd = registry.get_integration("nistnvd")

        assert nistnvd is not None, "NIST NVD should be in registry"

        # Get action IDs
        action_ids = [a.id for a in nistnvd.actions]

        # Verify all expected actions are present
        expected_actions = [
            "health_check",
            "cve_lookup",
        ]

        for action_id in expected_actions:
            assert action_id in action_ids, f"Action {action_id} should be registered"

        # Verify health_check has health_monitoring category
        health_check = next(a for a in nistnvd.actions if a.id == "health_check")
        assert "health_monitoring" in health_check.categories

        # Verify cve_lookup has correct categories
        cve_lookup = next(a for a in nistnvd.actions if a.id == "cve_lookup")
        assert "vulnerability_management" in cve_lookup.categories


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegistryIncludesNISTNVD:
    """Test registry list_integrations includes NIST NVD."""

    @pytest.mark.asyncio
    async def test_registry_lists_nistnvd(self):
        """Test: Registry list_integrations includes NIST NVD.

        Goal: Verify registry lists NIST NVD with other integrations.
        """
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        integration_ids = [i.id for i in integrations]

        # Should include NIST NVD
        assert "nistnvd" in integration_ids, "Should have NIST NVD"

        # Verify NIST NVD archetype (DatabaseEnrichment, not VulnerabilityManagement)
        nistnvd = next(i for i in integrations if i.id == "nistnvd")
        assert "DatabaseEnrichment" in nistnvd.archetypes


@pytest.mark.integration
@pytest.mark.asyncio
class TestManifestValidation:
    """Test NIST NVD manifest is valid."""

    @pytest.mark.asyncio
    async def test_nistnvd_manifest_validation(self):
        """Test: Manifest is valid and parseable by framework.

        Goal: Verify manifest validates successfully.
        """
        registry = IntegrationRegistry()
        nistnvd = registry.get_integration("nistnvd")

        assert nistnvd is not None, "NIST NVD should load successfully"

        # Verify required fields
        assert nistnvd.id == "nistnvd"
        assert nistnvd.name == "NIST NVD"
        assert nistnvd.version == "1.0.0"

        # Verify credential schema (optional API key)
        assert nistnvd.credential_schema is not None
        assert "api_key" in nistnvd.credential_schema["properties"]
        # API key is optional (not in required list)
        assert nistnvd.credential_schema["properties"]["api_key"]["required"] is False


# =====================================================================
# Real NIST NVD API Tests 🟢
# =====================================================================
# No API key required - NIST NVD API is public!
# Optional API key only for higher rate limits.
# =====================================================================


@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.asyncio
class TestRealNISTNVDAPI:
    """Real NIST NVD API tests.

    ✅ No API key required - NIST NVD API is public
    ⚠️ Excluded from test-integration-db and nightly CI (requires_api)
       because the public API rate-limits to 5 req/30s without an API key.
    """

    @pytest.mark.asyncio
    async def test_real_api_health_check(self):
        """✅: Verify health check works with real NIST NVD API.

        Test Data: Queries a well-known CVE to verify connectivity
        Expected: Returns {"status": "success", "healthy": True}
        """
        action = HealthCheckAction(
            integration_id="nistnvd-test",
            action_id="health_check",
            settings={"api_version": "2.0", "timeout": 30},
            credentials={},  # No credentials needed for public API
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "NIST NVD API is accessible" in result["message"]
        assert result["data"]["api_version"] == "2.0"
        assert "base_url" in result["data"]

    @pytest.mark.asyncio
    async def test_real_api_lookup_cve_2022_41082(self):
        """✅: Verify CVE lookup works with real API using CVE-2022-41082.

        Test Data: CVE-2022-41082 (ProxyNotShell - Microsoft Exchange Server vulnerability)
        This is a well-known, critical vulnerability discovered in 2022.

        Expected:
        - Returns success with CVE details
        - CVSS score ~8.8 (Critical)
        - Description mentions "Exchange Server"
        - Has published and last modified dates
        """
        action = CveLookupAction(
            integration_id="nistnvd-test",
            action_id="cve_lookup",
            settings={"api_version": "2.0", "timeout": 30},
            credentials={},  # No credentials needed for public API
        )

        result = await action.execute(cve="CVE-2022-41082")

        # Verify response structure
        assert result["status"] == "success", (
            f"Expected success, got: {result.get('error')}"
        )
        assert result["cve_id"] == "CVE-2022-41082"

        # Verify description contains Exchange Server
        assert "description" in result
        assert (
            "Exchange Server" in result["description"]
            or "exchange" in result["description"].lower()
        ), f"Description should mention Exchange Server, got: {result['description']}"

        # Verify CVSS metrics exist (should be Critical - 8.0+)
        assert "cvss_metrics" in result
        assert result["cvss_metrics"] is not None
        assert "base_score" in result["cvss_metrics"]
        base_score = result["cvss_metrics"]["base_score"]
        assert 7.0 <= base_score <= 10.0, (
            f"CVE-2022-41082 should be High/Critical severity, got score: {base_score}"
        )

        # Verify severity
        assert "base_severity" in result["cvss_metrics"]
        assert result["cvss_metrics"]["base_severity"] in ["HIGH", "CRITICAL"], (
            f"CVE-2022-41082 should be HIGH or CRITICAL, got: {result['cvss_metrics']['base_severity']}"
        )

        # Verify dates exist
        assert "published_date" in result
        assert result["published_date"] is not None
        assert "2022" in result["published_date"], (
            f"CVE-2022-41082 should be published in 2022, got: {result['published_date']}"
        )

        assert "last_modified_date" in result
        assert result["last_modified_date"] is not None

        # Verify references exist (should have Microsoft security bulletin, etc.)
        assert "references" in result
        assert len(result["references"]) > 0, "Should have references to advisories"

        # Verify CVSS metrics have attack vector info
        assert "attack_vector" in result["cvss_metrics"]
        assert result["cvss_metrics"]["attack_vector"] is not None

    @pytest.mark.asyncio
    async def test_real_api_lookup_known_cisa_kev_cve(self):
        """✅: Verify CVE lookup identifies CISA KEV catalog entries.

        Test Data: CVE-2021-44228 (Log4Shell - Apache Log4j vulnerability)
        This CVE is listed in CISA's Known Exploited Vulnerabilities catalog.

        Expected:
        - Returns success
        - is_cisa_kev should be True
        - CVSS score 10.0 (Critical)
        """
        action = CveLookupAction(
            integration_id="nistnvd-test",
            action_id="cve_lookup",
            settings={"api_version": "2.0", "timeout": 30},
            credentials={},
        )

        result = await action.execute(cve="CVE-2021-44228")

        # Verify response structure
        assert result["status"] == "success"
        assert result["cve_id"] == "CVE-2021-44228"

        # Verify Log4j mentioned
        assert "description" in result
        assert (
            "log4j" in result["description"].lower() or "Log4j" in result["description"]
        ), f"Description should mention Log4j, got: {result['description']}"

        # Verify CVSS metrics show Critical score (10.0)
        assert "cvss_metrics" in result
        assert result["cvss_metrics"]["base_score"] == 10.0, (
            f"Log4Shell should have CVSS 10.0, got: {result['cvss_metrics']['base_score']}"
        )

        # Verify severity is CRITICAL
        assert result["cvss_metrics"]["base_severity"] == "CRITICAL"

        # Verify CISA KEV data is present (Log4Shell is definitely in CISA KEV catalog)
        assert "cisa_kev" in result
        assert result["cisa_kev"] is not None, (
            "CVE-2021-44228 (Log4Shell) should be in CISA KEV catalog"
        )
        assert result["cisa_kev"]["vulnerability_name"] is not None
        assert result["cisa_kev"]["required_action"] is not None

    @pytest.mark.asyncio
    async def test_real_api_lookup_nonexistent_cve(self):
        """✅: Verify CVE lookup handles non-existent CVE gracefully.

        Test Data: CVE-2099-99999 (non-existent CVE)

        Expected: Returns error with appropriate message
        """
        action = CveLookupAction(
            integration_id="nistnvd-test",
            action_id="cve_lookup",
            settings={"api_version": "2.0", "timeout": 30},
            credentials={},
        )

        result = await action.execute(cve="CVE-2099-99999")

        # Should return error for non-existent CVE
        assert result["status"] == "error"
        assert "error" in result
        # Error should mention "not found" or "no data"
        assert (
            "not found" in result["error"].lower()
            or "no data" in result["error"].lower()
        ), f"Error message should indicate CVE not found, got: {result['error']}"
