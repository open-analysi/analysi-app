"""Unit tests for CrowdStrike Falcon alert -> OCSF normalization.

Tests the CrowdStrikeOCSFNormalizer with multiple fixture types:
1. Full alert with MITRE ATT&CK, host, user, process, file info
2. Minimal alert with only required fields
3. Alert with multiple severity levels
4. Alert with public/private IP handling
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.crowdstrike_ocsf import (
    SEVERITY_INT_TO_OCSF,
    CrowdStrikeOCSFNormalizer,
)


@pytest.fixture
def normalizer():
    """Create a CrowdStrikeOCSFNormalizer instance."""
    return CrowdStrikeOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def full_alert() -> dict:
    """Full CrowdStrike alert with all fields populated."""
    return {
        "composite_id": "cs:alert:abc123def456",
        "severity": 4,
        "tactic": "Credential Access",
        "tactic_id": "TA0006",
        "technique": "Brute Force",
        "technique_id": "T1110",
        "display_name": "Brute Force Login Attempt Detected",
        "description": "Multiple failed login attempts detected from external IP",
        "hostname": "WORKSTATION-01",
        "local_ip": "192.168.1.50",
        "external_ip": "45.33.32.156",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "user_name": "jdoe",
        "filename": "suspicious.exe",
        "filepath": "C:\\Users\\jdoe\\Downloads\\suspicious.exe",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        "cmdline": "suspicious.exe --payload",
        "parent_cmdline": "cmd.exe /c suspicious.exe",
        "process_id": "pid:abc123:1234",
        "parent_process_id": "pid:abc123:1000",
        "source_products": ["Falcon Endpoint Protection"],
        "source_vendor": "CrowdStrike",
        "timestamp": "2025-03-15T14:30:00.000Z",
        "created_timestamp": "2025-03-15T14:30:05.000Z",
        "updated_timestamp": "2025-03-15T14:35:00.000Z",
        "status": "new",
    }


@pytest.fixture
def minimal_alert() -> dict:
    """Minimal CrowdStrike alert with only base fields."""
    return {
        "composite_id": "cs:alert:minimal001",
        "severity": 2,
        "display_name": "Low Severity Alert",
        "timestamp": "2025-03-16T08:00:00.000Z",
        "status": "new",
    }


@pytest.fixture
def process_only_alert() -> dict:
    """Alert with process info but no file info."""
    return {
        "composite_id": "cs:alert:proc001",
        "severity": 3,
        "display_name": "Suspicious Process Execution",
        "description": "Process spawned with unusual command line",
        "hostname": "SERVER-DB-01",
        "local_ip": "10.0.0.100",
        "user_name": "svc_account",
        "cmdline": "powershell -enc SGVsbG8gV29ybGQ=",
        "parent_cmdline": "cmd.exe /c powershell",
        "process_id": "pid:xyz789:5678",
        "parent_process_id": "pid:xyz789:5600",
        "timestamp": "2025-03-17T10:00:00.000Z",
        "status": "in_progress",
    }


@pytest.fixture
def public_ip_alert() -> dict:
    """Alert where local_ip is public (unusual but possible in cloud)."""
    return {
        "composite_id": "cs:alert:pubip001",
        "severity": 5,
        "display_name": "Critical: C2 Communication Detected",
        "hostname": "CLOUD-VM-01",
        "local_ip": "54.239.28.85",
        "external_ip": "45.33.32.156",
        "timestamp": "2025-03-18T12:00:00.000Z",
        "status": "new",
    }


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Test OCSF scaffold fields are correctly set."""

    def test_class_uid(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["class_uid"] == 2004

    def test_class_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["class_name"] == "Detection Finding"

    def test_category_uid(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["category_uid"] == 2
        assert result["category_name"] == "Findings"

    def test_activity(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["activity_id"] == 1
        assert result["activity_name"] == "Create"

    def test_type_uid(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["type_uid"] == 200401
        assert result["type_name"] == "Detection Finding: Create"

    def test_is_alert(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["is_alert"] is True


# ── Severity mapping tests ──────────────────────────────────────────


class TestSeverityMapping:
    """Test CrowdStrike severity integer to OCSF severity mapping."""

    @pytest.mark.parametrize(
        ("cs_severity", "expected_id", "expected_label"),
        [
            (1, 1, "Informational"),
            (2, 2, "Low"),
            (3, 3, "Medium"),
            (4, 4, "High"),
            (5, 5, "Critical"),
        ],
    )
    def test_severity_mapping(
        self, normalizer, minimal_alert, cs_severity, expected_id, expected_label
    ):
        minimal_alert["severity"] = cs_severity
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == expected_id
        assert result["severity"] == expected_label

    def test_missing_severity_defaults_to_informational(
        self, normalizer, minimal_alert
    ):
        del minimal_alert["severity"]
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_invalid_severity_defaults_to_informational(
        self, normalizer, minimal_alert
    ):
        minimal_alert["severity"] = "not_a_number"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_out_of_range_severity_defaults_to_informational(
        self, normalizer, minimal_alert
    ):
        minimal_alert["severity"] = 99
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"


# ── Time mapping tests ──────────────────────────────────────────────


class TestTimeMapping:
    """Test timestamp mapping to OCSF time fields."""

    def test_time_from_timestamp(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["time_dt"] == "2025-03-15T14:30:00.000Z"
        assert isinstance(result["time"], int)

    def test_ocsf_time_from_created_timestamp(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert isinstance(result["ocsf_time"], int)

    def test_missing_timestamp_falls_back_to_created(self, normalizer, minimal_alert):
        del minimal_alert["timestamp"]
        minimal_alert["created_timestamp"] = "2025-03-16T08:00:05.000Z"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["time_dt"] == "2025-03-16T08:00:05.000Z"

    def test_no_timestamps(self, normalizer, minimal_alert):
        del minimal_alert["timestamp"]
        result = normalizer.to_ocsf(minimal_alert)
        assert "time" not in result
        assert "time_dt" not in result


# ── Message tests ────────────────────────────────────────────────────


class TestMessage:
    """Test message/title extraction."""

    def test_message_from_display_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["message"] == "Brute Force Login Attempt Detected"

    def test_message_falls_back_to_description(self, normalizer, minimal_alert):
        del minimal_alert["display_name"]
        minimal_alert["description"] = "Some description"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["message"] == "Some description"

    def test_message_defaults_to_unknown(self, normalizer):
        result = normalizer.to_ocsf({"composite_id": "x", "severity": 1})
        assert result["message"] == "Unknown Alert"


# ── Metadata tests ──────────────────────────────────────────────────


class TestMetadata:
    """Test OCSF metadata object."""

    def test_vendor_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["product"]["vendor_name"] == "CrowdStrike"
        assert result["metadata"]["product"]["name"] == "Falcon"

    def test_ocsf_version(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["version"] == "1.8.0"

    def test_profiles(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "security_control" in result["metadata"]["profiles"]

    def test_source_products_as_labels(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert (
            "source_product:Falcon Endpoint Protection" in result["metadata"]["labels"]
        )

    def test_composite_id_as_event_code(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["event_code"] == "cs:alert:abc123def456"

    def test_no_labels_without_source_products(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "labels" not in result["metadata"]


# ── Finding Info tests ──────────────────────────────────────────────


class TestFindingInfo:
    """Test OCSF finding_info object."""

    def test_uid(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["finding_info"]["uid"] == "cs:alert:abc123def456"

    def test_title(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["finding_info"]["title"] == "Brute Force Login Attempt Detected"

    def test_description(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "Multiple failed login" in result["finding_info"]["desc"]

    def test_analytic_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        analytic = result["finding_info"]["analytic"]
        assert analytic["name"] == "Brute Force Login Attempt Detected"
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"

    def test_data_sources(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "Falcon Endpoint Protection" in result["finding_info"]["data_sources"]

    def test_created_time(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["finding_info"]["created_time"] == "2025-03-15T14:30:05.000Z"


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMitreAttack:
    """Test MITRE ATT&CK mapping."""

    def test_full_attack_mapping(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0006"
        assert attacks[0]["tactic"]["name"] == "Credential Access"
        assert attacks[0]["technique"]["uid"] == "T1110"
        assert attacks[0]["technique"]["name"] == "Brute Force"

    def test_tactic_only(self, normalizer, minimal_alert):
        minimal_alert["tactic"] = "Initial Access"
        minimal_alert["tactic_id"] = "TA0001"
        result = normalizer.to_ocsf(minimal_alert)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0001"
        assert "technique" not in attacks[0]

    def test_no_attack_info(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "attacks" not in result["finding_info"]


# ── Status mapping tests ────────────────────────────────────────────


class TestStatusMapping:
    """Test CrowdStrike status to OCSF status mapping."""

    @pytest.mark.parametrize(
        ("cs_status", "expected_id", "expected_label"),
        [
            ("new", 1, "New"),
            ("in_progress", 2, "In Progress"),
            ("true_positive", 3, "Closed"),
            ("false_positive", 3, "Closed"),
            ("closed", 3, "Closed"),
        ],
    )
    def test_status_mapping(
        self, normalizer, minimal_alert, cs_status, expected_id, expected_label
    ):
        minimal_alert["status"] = cs_status
        result = normalizer.to_ocsf(minimal_alert)
        assert result["status_id"] == expected_id
        assert result["status"] == expected_label

    def test_unknown_status_defaults_to_new(self, normalizer, minimal_alert):
        minimal_alert["status"] = "unknown_status"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["status_id"] == 1
        assert result["status"] == "New"


# ── Device tests ─────────────────────────────────────────────────────


class TestDevice:
    """Test OCSF device object."""

    def test_full_device(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        device = result["device"]
        assert device["hostname"] == "WORKSTATION-01"
        assert device["name"] == "WORKSTATION-01"
        assert device["ip"] == "192.168.1.50"
        assert device["mac"] == "AA:BB:CC:DD:EE:FF"

    def test_no_device_without_host_fields(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "device" not in result


# ── Actor tests ──────────────────────────────────────────────────────


class TestActor:
    """Test OCSF actor object."""

    def test_actor_from_user_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["actor"]["user"]["name"] == "jdoe"

    def test_no_actor_without_user(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "actor" not in result


# ── Observables tests ────────────────────────────────────────────────


class TestObservables:
    """Test OCSF observables — only public IPs and hashes."""

    def test_external_ip_is_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        ip_obs = [o for o in obs if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "45.33.32.156" in ip_values

    def test_private_ip_not_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        ip_obs = [o for o in obs if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "192.168.1.50" not in ip_values

    def test_public_local_ip_is_observable(self, normalizer, public_ip_alert):
        result = normalizer.to_ocsf(public_ip_alert)
        obs = result["observables"]
        ip_obs = [o for o in obs if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "54.239.28.85" in ip_values
        assert "45.33.32.156" in ip_values

    def test_sha256_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        hash_obs = [o for o in obs if o["type_id"] == 8 and o["name"] == "SHA-256"]
        assert len(hash_obs) == 1
        assert hash_obs[0]["value"] == full_alert["sha256"]

    def test_md5_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        hash_obs = [o for o in obs if o["type_id"] == 8 and o["name"] == "MD5"]
        assert len(hash_obs) == 1
        assert hash_obs[0]["value"] == full_alert["md5"]

    def test_no_observables_without_ioc_fields(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "observables" not in result


# ── Evidences tests ──────────────────────────────────────────────────


class TestEvidences:
    """Test OCSF evidences — process and file info."""

    def test_process_evidence(self, normalizer, process_only_alert):
        result = normalizer.to_ocsf(process_only_alert)
        evidences = result["evidences"]
        proc_ev = [e for e in evidences if "process" in e]
        assert len(proc_ev) == 1
        proc = proc_ev[0]["process"]
        assert proc["cmd_line"] == "powershell -enc SGVsbG8gV29ybGQ="
        assert proc["uid"] == "pid:xyz789:5678"
        assert proc["parent_process"]["cmd_line"] == "cmd.exe /c powershell"
        assert proc["parent_process"]["uid"] == "pid:xyz789:5600"

    def test_file_evidence(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        file_ev = [e for e in evidences if "file" in e]
        assert len(file_ev) == 1
        f = file_ev[0]["file"]
        assert f["name"] == "suspicious.exe"
        assert "Downloads" in f["path"]
        assert len(f["hashes"]) == 2

    def test_file_hash_algorithms(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        file_ev = next(e for e in evidences if "file" in e)
        algorithms = [h["algorithm"] for h in file_ev["file"]["hashes"]]
        assert "SHA-256" in algorithms
        assert "MD5" in algorithms

    def test_no_evidences_without_process_or_file(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "evidences" not in result

    def test_both_process_and_file_evidences(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        # full_alert has both process and file info
        assert len(evidences) == 2


# ── Raw data tests ──────────────────────────────────────────────────


class TestRawData:
    """Test raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        parsed = json.loads(result["raw_data"])
        assert parsed["composite_id"] == "cs:alert:abc123def456"

    def test_raw_data_hash_is_sha256(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        expected_hash = hashlib.sha256(result["raw_data"].encode()).hexdigest()
        assert result["raw_data_hash"] == expected_hash
        assert len(result["raw_data_hash"]) == 64

    def test_raw_data_hash_changes_with_content(
        self, normalizer, full_alert, minimal_alert
    ):
        result_full = normalizer.to_ocsf(full_alert)
        result_minimal = normalizer.to_ocsf(minimal_alert)
        assert result_full["raw_data_hash"] != result_minimal["raw_data_hash"]


# ── Disposition tests ────────────────────────────────────────────────


class TestDisposition:
    """Test default disposition values."""

    def test_disposition_defaults(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"
        assert result["action_id"] == 0
        assert result["action"] == "Unknown"


# ── Edge case tests ──────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and minimal inputs."""

    def test_empty_alert(self, normalizer):
        """An empty dict should still produce a valid OCSF scaffold."""
        result = normalizer.to_ocsf({})
        assert result["class_uid"] == 2004
        assert result["severity_id"] == 1
        assert result["message"] == "Unknown Alert"
        assert result["is_alert"] is True
        assert "raw_data" in result
        assert "raw_data_hash" in result

    def test_none_severity(self, normalizer):
        result = normalizer.to_ocsf({"severity": None})
        assert result["severity_id"] == 1

    def test_severity_mapping_constant_complete(self):
        """Verify SEVERITY_INT_TO_OCSF covers all 5 levels."""
        assert set(SEVERITY_INT_TO_OCSF.keys()) == {1, 2, 3, 4, 5}
