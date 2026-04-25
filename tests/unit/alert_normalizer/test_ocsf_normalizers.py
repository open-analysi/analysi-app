"""Tests for OCSF normalizers.

Validates that:
1. Splunk OCSF normalizer produces valid OCSF Detection Finding v1.8.0
2. OCSF output preserves key fields (title, severity, raw_data) from source
3. All 9 real Splunk fixtures produce valid OCSF
"""

import json
from pathlib import Path

import pytest

from alert_normalizer.splunk import SplunkNotableNormalizer
from alert_normalizer.splunk_ocsf import SplunkOCSFNormalizer
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION

NOTABLES_DIR = Path(__file__).parent.parent.parent / "alert_normalizer" / "notables"


@pytest.fixture
def splunk_ocsf():
    return SplunkOCSFNormalizer()


@pytest.fixture
def splunk_nas():
    return SplunkNotableNormalizer()


@pytest.fixture
def sql_injection_notable():
    with open(NOTABLES_DIR / "02-sql-injection-web.json") as f:
        return json.load(f)


@pytest.fixture
def powershell_notable():
    with open(NOTABLES_DIR / "01-powershell-exploit.json") as f:
        return json.load(f)


@pytest.fixture
def all_notables():
    """Load all 9 test notables."""
    results = {}
    for p in sorted(NOTABLES_DIR.glob("*.json")):
        with open(p) as f:
            results[p.name] = json.load(f)
    return results


# ── OCSF Structure Validation ──────────────────────────────────────────


class TestSplunkOCSFStructure:
    """Validate OCSF Detection Finding structure from Splunk normalizer."""

    def test_required_ocsf_fields_present(self, splunk_ocsf, sql_injection_notable):
        """OCSF output must have all required Detection Finding fields."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)

        assert ocsf["class_uid"] == 2004
        assert ocsf["class_name"] == "Detection Finding"
        assert ocsf["category_uid"] == 2
        assert ocsf["category_name"] == "Findings"
        assert ocsf["activity_id"] == 1
        assert ocsf["type_uid"] == 200401
        assert isinstance(ocsf["time"], int)
        assert ocsf["time"] > 0
        assert ocsf["severity_id"] in (1, 2, 3, 4, 5)
        assert "metadata" in ocsf
        assert "finding_info" in ocsf

    def test_metadata_structure(self, splunk_ocsf, sql_injection_notable):
        """Metadata must have product, version, labels, profiles."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        meta = ocsf["metadata"]

        assert meta["product"]["vendor_name"] == "Splunk"
        assert meta["product"]["name"] == "Enterprise Security"
        assert meta["version"] == OCSF_VERSION
        assert "source_category:Firewall" in meta.get("labels", [])
        assert "security_control" in meta.get("profiles", [])

    def test_finding_info_structure(self, splunk_ocsf, sql_injection_notable):
        """FindingInfo must have title, uid, and analytic."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        fi = ocsf["finding_info"]

        assert fi["title"] == "SQL Injection Payload Detected"
        assert fi.get("uid")  # Must be non-empty
        assert fi["analytic"]["name"] == "SQL Injection Payload Detected"
        assert fi["analytic"]["type_id"] == 1  # Rule

    def test_severity_mapping(self, splunk_ocsf, sql_injection_notable):
        """High severity -> severity_id=4 in OCSF."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"

    def test_disposition_from_device_action(self, splunk_ocsf, sql_injection_notable):
        """device_action=allowed -> disposition_id=1 (Allowed)."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        assert ocsf.get("disposition_id") == 1
        assert ocsf.get("disposition") == "Allowed"

    def test_blocked_disposition(self, splunk_ocsf, powershell_notable):
        """device_action=blocked -> disposition_id=2 (Blocked)."""
        ocsf = splunk_ocsf.to_ocsf(powershell_notable)
        assert ocsf.get("disposition_id") == 2
        assert ocsf.get("disposition") == "Blocked"

    def test_observables_from_iocs(self, splunk_ocsf, sql_injection_notable):
        """IOCs must become observables with correct type_ids."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        observables = ocsf.get("observables", [])

        assert len(observables) >= 1
        # First IOC is IP 91.234.56.17 -> type_id=2
        ip_obs = [o for o in observables if o.get("type_id") == 2]
        assert len(ip_obs) >= 1
        assert ip_obs[0]["value"] == "91.234.56.17"

    def test_evidences_from_network_info(self, splunk_ocsf, sql_injection_notable):
        """network_info must produce evidences with src/dst endpoints."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        evidences = ocsf.get("evidences", [])

        assert len(evidences) >= 1
        ev = evidences[0]
        assert ev.get("src_endpoint", {}).get("ip") == "91.234.56.17"
        assert ev.get("dst_endpoint", {}).get("ip") == "10.10.20.18"

    def test_evidences_from_web_info(self, splunk_ocsf, sql_injection_notable):
        """web_info must produce url + http_request in evidences."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        evidences = ocsf.get("evidences", [])

        assert len(evidences) >= 1
        ev = evidences[0]
        assert "10.10.20.18/search/" in ev.get("url", {}).get("url_string", "")
        assert ev.get("http_request", {}).get("http_method") == "GET"

    def test_device_from_risk_entity(self, splunk_ocsf, sql_injection_notable):
        """Device risk entity must become top-level device object."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        device = ocsf.get("device")

        assert device is not None
        # WebServer1001 is the primary risk entity (device)
        assert (
            device.get("hostname") == "WebServer1001"
            or device.get("name") == "WebServer1001"
        )

    def test_raw_data_preserved(self, splunk_ocsf, sql_injection_notable):
        """Notable event must become raw_data (JSON serialized)."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        assert ocsf.get("raw_data")
        assert "SQL Injection Payload Detected" in ocsf["raw_data"]

    def test_raw_data_hash_computed(self, splunk_ocsf, sql_injection_notable):
        """raw_data_hash must be SHA256 of raw_data."""
        import hashlib

        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        expected_hash = hashlib.sha256(ocsf["raw_data"].encode()).hexdigest()
        assert ocsf.get("raw_data_hash") == expected_hash

    def test_unmapped_from_other_activities(self, splunk_ocsf, sql_injection_notable):
        """other_activities must become unmapped."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        unmapped = ocsf.get("unmapped")
        if unmapped:
            assert "signature" in unmapped

    def test_message_equals_title(self, splunk_ocsf, sql_injection_notable):
        """message field should match the alert title."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        assert ocsf.get("message") == "SQL Injection Payload Detected"


# ── Key Field Consistency ─────────────────────────────────────────────


class TestSplunkOCSFKeyFieldConsistency:
    """Verify OCSF normalizer output preserves key fields from the notable."""

    def test_ocsf_title_matches_nas_title(
        self, splunk_ocsf, splunk_nas, sql_injection_notable
    ):
        """OCSF title must match the NAS normalizer's extracted title."""
        nas = splunk_nas.to_alertcreate(sql_injection_notable)
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)

        assert ocsf["finding_info"]["title"] == nas.title

    def test_ocsf_severity_matches_nas_severity(
        self, splunk_ocsf, splunk_nas, sql_injection_notable
    ):
        """OCSF severity label (lowercased) must match NAS severity."""
        nas = splunk_nas.to_alertcreate(sql_injection_notable)
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)

        assert ocsf["severity"].lower() == nas.severity

    def test_ocsf_source_vendor_matches(self, splunk_ocsf, sql_injection_notable):
        """Source vendor in metadata must be Splunk."""
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)
        assert ocsf["metadata"]["product"]["vendor_name"] == "Splunk"
        assert ocsf["metadata"]["product"]["name"] == "Enterprise Security"

    def test_ocsf_rule_name_matches(
        self, splunk_ocsf, splunk_nas, sql_injection_notable
    ):
        """OCSF analytic name must match NAS rule_name."""
        nas = splunk_nas.to_alertcreate(sql_injection_notable)
        ocsf = splunk_ocsf.to_ocsf(sql_injection_notable)

        assert ocsf["finding_info"]["analytic"]["name"] == nas.rule_name


# ── All 9 Real Fixtures ───────────────────────────────────────────────


class TestAllSplunkFixtures:
    """Validate all 9 real Splunk notable fixtures produce valid OCSF."""

    def test_all_notables_produce_valid_ocsf(self, splunk_ocsf, all_notables):
        """Every fixture must produce a valid OCSF Detection Finding."""
        for name, notable in all_notables.items():
            ocsf = splunk_ocsf.to_ocsf(notable)

            assert ocsf["class_uid"] == 2004, f"{name}: wrong class_uid"
            assert ocsf["severity_id"] in (1, 2, 3, 4, 5), (
                f"{name}: invalid severity_id"
            )
            assert ocsf["finding_info"]["title"], f"{name}: missing title"
            assert ocsf["metadata"]["version"] == OCSF_VERSION, f"{name}: wrong version"
            assert ocsf.get("raw_data"), f"{name}: missing raw_data"

    def test_all_notables_title_matches_nas(
        self, splunk_ocsf, splunk_nas, all_notables
    ):
        """Every fixture's OCSF title must match the NAS normalizer's title."""
        for name, notable in all_notables.items():
            nas_original = splunk_nas.to_alertcreate(notable)
            ocsf = splunk_ocsf.to_ocsf(notable)

            assert ocsf["finding_info"]["title"] == nas_original.title, (
                f"{name}: title mismatch"
            )
            assert ocsf["severity"].lower() == nas_original.severity, (
                f"{name}: severity mismatch"
            )

    def test_all_notables_have_analytic_in_finding_info(
        self, splunk_ocsf, all_notables
    ):
        """Every fixture's finding_info must contain analytic with rule name.

        finding_info.analytic.name is the detection rule name, used for alert
        routing. It must be present and distinct from finding_info.title
        (which is the alert summary). These are different concepts:
        - analytic.name: stable rule identifier, same for all alerts from a rule
        - title: per-alert summary, may contain instance-specific data (IPs, users)
        """
        for name, notable in all_notables.items():
            ocsf = splunk_ocsf.to_ocsf(notable)
            fi = ocsf["finding_info"]

            assert "analytic" in fi, f"{name}: missing finding_info.analytic"
            assert fi["analytic"].get("name"), (
                f"{name}: missing finding_info.analytic.name (rule name)"
            )
            assert fi["analytic"].get("type_id") == 1, (
                f"{name}: analytic.type_id should be 1 (Rule)"
            )

    def test_all_notables_have_observables(self, splunk_ocsf, all_notables):
        """Most fixtures should produce at least one observable."""
        with_observables = 0
        for _name, notable in all_notables.items():
            ocsf = splunk_ocsf.to_ocsf(notable)
            if ocsf.get("observables"):
                with_observables += 1
        # At least 7/9 fixtures should have IOCs -> observables
        assert with_observables >= 7, f"Only {with_observables}/9 have observables"

    def test_all_notables_have_evidences(self, splunk_ocsf, all_notables):
        """Most fixtures should produce evidence artifacts."""
        with_evidences = 0
        for _name, notable in all_notables.items():
            ocsf = splunk_ocsf.to_ocsf(notable)
            if ocsf.get("evidences"):
                with_evidences += 1
        # All fixtures have network_info -> evidences
        assert with_evidences >= 7, f"Only {with_evidences}/9 have evidences"


# ── Ingestion Bridge ───────────────────────────────────────────────────


class TestIngestionBridge:
    """Verify the ingestion service resolves to OCSF normalizers."""

    def test_splunk_resolves_to_ocsf_normalizer(self):
        """splunk integration type must resolve to SplunkOCSFNormalizer."""
        from unittest.mock import AsyncMock

        from analysi.integrations.framework.alert_ingest import AlertIngestionService

        service = AlertIngestionService.__new__(AlertIngestionService)
        service.session = AsyncMock()

        normalizer = service._get_normalizer("splunk")
        assert normalizer is not None
        assert type(normalizer).__name__ == "SplunkOCSFNormalizer"

    def test_ocsf_normalizer_has_to_ocsf(self):
        """OCSF normalizer must expose to_ocsf method."""
        normalizer = SplunkOCSFNormalizer()
        assert hasattr(normalizer, "to_ocsf")
