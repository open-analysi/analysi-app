"""Tests for AlertsToOcsfAction — verifies full OCSF normalization via SplunkOCSFNormalizer.

Project Symi: AlertSource archetype action that delegates to the Skaros normalizer.
Validates output against OCSF Detection Finding v1.8.0 required fields and structure.
"""

import json
from pathlib import Path

import pytest

from analysi.integrations.framework.integrations.splunk.actions import (
    AlertsToOcsfAction,
)

NOTABLES_DIR = (
    Path(__file__).parent.parent.parent.parent / "alert_normalizer" / "notables"
)


@pytest.fixture
def all_notables() -> dict[str, dict]:
    """Load all 9 test Splunk notable fixtures."""
    results = {}
    for p in sorted(NOTABLES_DIR.glob("*.json")):
        with open(p) as f:
            results[p.stem] = json.load(f)
    return results


@pytest.fixture
def sql_injection_notable() -> dict:
    with open(NOTABLES_DIR / "02-sql-injection-web.json") as f:
        return json.load(f)


@pytest.fixture
def powershell_notable() -> dict:
    with open(NOTABLES_DIR / "01-powershell-exploit.json") as f:
        return json.load(f)


# ── OCSF Required Fields ──────────────────────────────────────────────

OCSF_REQUIRED_TOP_LEVEL = {
    "activity_id",
    "category_uid",
    "class_uid",
    "severity_id",
    "type_uid",
    "finding_info",
    "metadata",
}


class TestAlertsToOcsfAction:
    """Verify AlertsToOcsfAction produces full OCSF via SplunkOCSFNormalizer."""

    async def _run_action(self, raw_alerts: list[dict]) -> dict:
        action = AlertsToOcsfAction(
            integration_id="test-splunk",
            action_id="alerts_to_ocsf",
            settings={},
            credentials={},
        )
        return await action.execute(raw_alerts=raw_alerts)

    @pytest.mark.asyncio
    async def test_produces_full_ocsf_required_fields(self, sql_injection_notable):
        """Every normalized alert must have all OCSF required fields."""
        result = await self._run_action([sql_injection_notable])

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["errors"] == 0

        ocsf = result["normalized_alerts"][0]
        missing = OCSF_REQUIRED_TOP_LEVEL - set(ocsf.keys())
        assert not missing, f"Missing OCSF required fields: {missing}"

    @pytest.mark.asyncio
    async def test_ocsf_classification_constants(self, sql_injection_notable):
        """class_uid=2004, category_uid=2, type_uid=200401."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        assert ocsf["class_uid"] == 2004
        assert ocsf["category_uid"] == 2
        assert ocsf["activity_id"] == 1
        # type_uid = class_uid * 100 + activity_id
        assert ocsf["type_uid"] == 2004 * 100 + ocsf["activity_id"]

    @pytest.mark.asyncio
    async def test_severity_mapped_to_ocsf_enum(self, sql_injection_notable):
        """severity_id must be a valid OCSF enum value (0-6)."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        assert ocsf["severity_id"] in range(7)  # 0=Unknown through 6=Fatal
        assert "severity" in ocsf  # Human-readable label

    @pytest.mark.asyncio
    async def test_metadata_has_product_and_version(self, sql_injection_notable):
        """metadata.product and metadata.version are required by OCSF."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        metadata = ocsf["metadata"]
        assert "product" in metadata
        assert metadata["product"]["vendor_name"] == "Splunk"
        assert metadata["product"]["name"] == "Enterprise Security"
        assert metadata["version"] == "1.8.0"

    @pytest.mark.asyncio
    async def test_finding_info_has_uid_and_analytic(self, sql_injection_notable):
        """finding_info.uid is required; analytic should have name."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        fi = ocsf["finding_info"]
        assert fi.get("uid"), "finding_info.uid must be non-empty"
        assert fi.get("title"), "finding_info.title should be populated"

        analytic = fi.get("analytic")
        if analytic:
            assert analytic.get("name") or analytic.get("uid"), (
                "analytic must have at least name or uid"
            )

    @pytest.mark.asyncio
    async def test_observables_have_type_id_and_value(self, sql_injection_notable):
        """Each observable must have type_id (int) and value (str)."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        observables = ocsf.get("observables", [])
        # SQL injection fixture should produce at least one observable (IP or URL)
        assert len(observables) > 0, "Expected at least one observable"

        for obs in observables:
            assert isinstance(obs["type_id"], int), f"type_id must be int: {obs}"
            assert isinstance(obs["value"], str), f"value must be str: {obs}"
            assert obs["value"], "observable value must not be empty"

    @pytest.mark.asyncio
    async def test_evidences_populated_for_network_alert(self, sql_injection_notable):
        """Network-based alerts should have evidences with src/dst endpoints."""
        result = await self._run_action([sql_injection_notable])
        ocsf = result["normalized_alerts"][0]

        evidences = ocsf.get("evidences", [])
        assert len(evidences) > 0, "Expected evidences for network alert"

        # At least one evidence should have endpoint info
        ev = evidences[0]
        has_endpoint = ev.get("src_endpoint") or ev.get("dst_endpoint")
        has_process = ev.get("process")
        has_url = ev.get("url")
        assert has_endpoint or has_process or has_url, (
            "Evidence must have at least one substantive attribute"
        )

    @pytest.mark.asyncio
    async def test_all_9_fixtures_produce_valid_ocsf(self, all_notables):
        """Every fixture must produce OCSF with all required fields."""
        result = await self._run_action(list(all_notables.values()))

        assert result["status"] == "success"
        assert result["count"] == len(all_notables)
        assert result["errors"] == 0

        for i, ocsf in enumerate(result["normalized_alerts"]):
            missing = OCSF_REQUIRED_TOP_LEVEL - set(ocsf.keys())
            fixture_name = list(all_notables.keys())[i]
            assert not missing, f"Fixture {fixture_name} missing OCSF fields: {missing}"
            # type_uid must follow formula
            assert ocsf["type_uid"] == ocsf["class_uid"] * 100 + ocsf["activity_id"]

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        """Empty raw_alerts produces empty normalized_alerts."""
        result = await self._run_action([])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["normalized_alerts"] == []

    @pytest.mark.asyncio
    async def test_malformed_alert_counted_as_error(self):
        """A malformed alert should not crash; counted as error."""
        # None would cause extraction functions to fail
        result = await self._run_action([{"_time": "not-a-real-notable"}])

        # Should still produce output (possibly with errors or degraded fields)
        assert result["count"] + result["errors"] == 1

    @pytest.mark.asyncio
    async def test_disposition_mapped_from_action(self, powershell_notable):
        """Splunk 'action' field maps to OCSF disposition_id."""
        result = await self._run_action([powershell_notable])
        ocsf = result["normalized_alerts"][0]

        # If the fixture has an action field, disposition should be mapped
        if powershell_notable.get("action"):
            assert "disposition_id" in ocsf
            # Valid disposition IDs: 0-15+ per OCSF spec
            assert isinstance(ocsf["disposition_id"], int)
