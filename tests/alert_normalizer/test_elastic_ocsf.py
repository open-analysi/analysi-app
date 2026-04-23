"""Unit tests for Elastic Security alert -> OCSF normalization.

Tests the ElasticOCSFNormalizer with four fixture types:
1. Simple query-rule alert with host + network info
2. Threshold rule with MITRE ATT&CK mapping
3. Minimal alert with only required fields
4. Alert with process + file info
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.elastic_ocsf import ElasticOCSFNormalizer


@pytest.fixture
def normalizer():
    """Create an ElasticOCSFNormalizer instance."""
    return ElasticOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def query_rule_alert() -> dict:
    """Simple query-rule alert with host + network info."""
    return {
        "@timestamp": "2025-03-15T14:30:00.000Z",
        "kibana": {
            "alert": {
                "uuid": "alert-uuid-001",
                "severity": "high",
                "risk_score": 73,
                "reason": "process cmd.exe on host WORKSTATION-01 by user jdoe",
                "workflow_status": "open",
                "url": "https://kibana.example.com/app/security/alerts/alert-uuid-001",
                "original_time": "2025-03-15T14:29:55.000Z",
                "rule": {
                    "name": "Suspicious CMD Execution",
                    "description": "Detects suspicious cmd.exe usage",
                    "uuid": "rule-uuid-001",
                    "type": "query",
                    "severity": "high",
                    "tags": ["Windows", "Execution", "T1059"],
                },
            },
        },
        "host": {
            "name": "WORKSTATION-01",
            "hostname": "WORKSTATION-01",
            "ip": ["192.168.1.50", "10.0.0.50"],
            "os": {"name": "Windows 10"},
        },
        "user": {
            "name": "jdoe",
            "id": "S-1-5-21-1234",
            "domain": "CORP",
        },
        "source": {"ip": "192.168.1.50", "port": 49152},
        "destination": {"ip": "8.8.8.8", "port": 443},
        "network": {"protocol": "tcp", "direction": "outbound"},
    }


@pytest.fixture
def threshold_rule_with_mitre() -> dict:
    """Threshold rule alert with full MITRE ATT&CK mapping."""
    return {
        "@timestamp": "2025-03-16T08:00:00.000Z",
        "kibana": {
            "alert": {
                "uuid": "alert-uuid-002",
                "severity": "critical",
                "risk_score": 91,
                "reason": "Multiple failed login attempts from 45.33.32.156",
                "workflow_status": "open",
                "rule": {
                    "name": "Brute Force Login Attempts",
                    "description": "Detects brute force login attempts exceeding threshold",
                    "uuid": "rule-uuid-002",
                    "type": "threshold",
                    "severity": "critical",
                    "tags": ["Authentication", "Credential Access"],
                    "threat": [
                        {
                            "framework": "MITRE ATT&CK",
                            "tactic": {
                                "id": "TA0006",
                                "name": "Credential Access",
                                "reference": "https://attack.mitre.org/tactics/TA0006/",
                            },
                            "technique": [
                                {
                                    "id": "T1110",
                                    "name": "Brute Force",
                                    "subtechnique": [
                                        {
                                            "id": "T1110.001",
                                            "name": "Password Guessing",
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "framework": "MITRE ATT&CK",
                            "tactic": {
                                "id": "TA0001",
                                "name": "Initial Access",
                            },
                            "technique": [
                                {
                                    "id": "T1078",
                                    "name": "Valid Accounts",
                                }
                            ],
                        },
                    ],
                },
            },
        },
        "source": {"ip": "45.33.32.156", "port": 54321},
        "destination": {"ip": "10.0.0.5", "port": 22},
        "user": {"name": "admin"},
    }


@pytest.fixture
def minimal_alert() -> dict:
    """Minimal alert with only required fields."""
    return {
        "@timestamp": "2025-03-17T12:00:00.000Z",
        "kibana": {
            "alert": {
                "uuid": "alert-uuid-003",
                "severity": "low",
                "rule": {
                    "name": "Generic Detection Rule",
                    "type": "query",
                },
            },
        },
    }


@pytest.fixture
def process_file_alert() -> dict:
    """Alert with process + file information."""
    return {
        "@timestamp": "2025-03-18T09:15:00.000Z",
        "kibana": {
            "alert": {
                "uuid": "alert-uuid-004",
                "severity": "high",
                "risk_score": 82,
                "reason": "Suspicious process powershell.exe writing to system directory",
                "workflow_status": "acknowledged",
                "rule": {
                    "name": "Suspicious PowerShell File Write",
                    "description": "Detects PowerShell writing to system directories",
                    "uuid": "rule-uuid-004",
                    "type": "eql",
                    "severity": "high",
                    "tags": ["Windows", "Execution", "Defense Evasion"],
                },
            },
        },
        "host": {
            "name": "SERVER-DC01",
            "ip": "10.0.0.10",
            "os": {"name": "Windows Server 2019"},
        },
        "user": {"name": "SYSTEM", "id": "S-1-5-18"},
        "process": {
            "name": "powershell.exe",
            "pid": 4512,
            "executable": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "command_line": "powershell.exe -ep bypass -enc SQBFAFgA...",
            "parent": {"name": "cmd.exe"},
        },
        "file": {
            "name": "payload.dll",
            "path": "C:\\Windows\\Temp\\payload.dll",
            "hash": {
                "sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "md5": "d41d8cd98f00b204e9800998ecf8427e",
            },
        },
        "agent": {"name": "elastic-agent-01", "type": "endpoint"},
    }


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Verify OCSF scaffold fields are correct."""

    def test_class_uid(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["class_uid"] == 2004

    def test_class_name(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["class_name"] == "Detection Finding"

    def test_is_alert(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["is_alert"] is True

    def test_category(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["category_uid"] == 2
        assert result["category_name"] == "Findings"

    def test_activity(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert result["activity_id"] == 1
        assert result["activity_name"] == "Create"
        assert result["type_uid"] == 200401


# ── Finding info tests ───────────────────────────────────────────────


class TestFindingInfo:
    """Verify finding_info mapping."""

    def test_analytic_name_equals_rule_name(self, normalizer, query_rule_alert):
        """CRITICAL: analytic.name must equal the rule name for workflow routing."""
        result = normalizer.to_ocsf(query_rule_alert)
        fi = result["finding_info"]
        assert fi["analytic"]["name"] == "Suspicious CMD Execution"

    def test_analytic_type_is_rule(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        fi = result["finding_info"]
        assert fi["analytic"]["type_id"] == 1
        assert fi["analytic"]["type"] == "Rule"

    def test_analytic_uid_from_rule_uuid(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["finding_info"]["analytic"]["uid"] == "rule-uuid-001"

    def test_finding_uid_is_alert_uuid(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["finding_info"]["uid"] == "alert-uuid-001"

    def test_title_from_reason(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        fi = result["finding_info"]
        assert fi["title"] == "process cmd.exe on host WORKSTATION-01 by user jdoe"

    def test_title_falls_back_to_rule_name(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        fi = result["finding_info"]
        assert fi["title"] == "Generic Detection Rule"

    def test_types_from_rule_type(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["finding_info"]["types"] == ["query"]

    def test_description_from_rule(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["finding_info"]["desc"] == "Detects suspicious cmd.exe usage"

    def test_created_time_dt(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["finding_info"]["created_time_dt"] == "2025-03-15T14:30:00.000Z"


# ── Severity mapping tests ──────────────────────────────────────────


class TestSeverityMapping:
    """Verify severity is correctly mapped."""

    def test_high_severity(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["severity_id"] == 4
        assert result["severity"] == "High"

    def test_critical_severity(self, normalizer, threshold_rule_with_mitre):
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        assert result["severity_id"] == 5
        assert result["severity"] == "Critical"

    def test_low_severity(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert result["severity_id"] == 2
        assert result["severity"] == "Low"


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMitreAttack:
    """Verify MITRE ATT&CK is properly mapped to finding_info.attacks."""

    def test_attacks_present(self, normalizer, threshold_rule_with_mitre):
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        attacks = result["finding_info"].get("attacks", [])
        assert len(attacks) > 0

    def test_tactic_mapping(self, normalizer, threshold_rule_with_mitre):
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        attacks = result["finding_info"]["attacks"]
        # First entry should be sub-technique T1110.001 under Credential Access
        tactic = attacks[0].get("tactic", {})
        assert tactic["uid"] == "TA0006"
        assert tactic["name"] == "Credential Access"

    def test_technique_mapping(self, normalizer, threshold_rule_with_mitre):
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        attacks = result["finding_info"]["attacks"]
        technique = attacks[0].get("technique", {})
        assert technique["uid"] == "T1110"
        assert technique["name"] == "Brute Force"

    def test_subtechnique_mapping(self, normalizer, threshold_rule_with_mitre):
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        attacks = result["finding_info"]["attacks"]
        # First entry has sub-technique
        sub = attacks[0].get("sub_technique", {})
        assert sub["uid"] == "T1110.001"
        assert sub["name"] == "Password Guessing"

    def test_multiple_threat_entries(self, normalizer, threshold_rule_with_mitre):
        """Both MITRE threat entries should produce attack objects."""
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        attacks = result["finding_info"]["attacks"]
        # T1110.001 sub-technique + T1078
        assert len(attacks) == 2
        tactic_uids = {a["tactic"]["uid"] for a in attacks}
        assert "TA0006" in tactic_uids
        assert "TA0001" in tactic_uids

    def test_no_attacks_when_no_mitre(self, normalizer, query_rule_alert):
        """Alert without MITRE threat array has no attacks."""
        result = normalizer.to_ocsf(query_rule_alert)
        assert "attacks" not in result["finding_info"]


# ── Device mapping tests ─────────────────────────────────────────────


class TestDeviceMapping:
    """Verify host -> device mapping."""

    def test_hostname_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["device"]["hostname"] == "WORKSTATION-01"

    def test_ip_from_host_ip_list(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["device"]["ip"] == "192.168.1.50"

    def test_os_name_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["device"]["os"]["name"] == "Windows 10"

    def test_ip_from_string(self, normalizer, process_file_alert):
        """host.ip as string (not list) should still work."""
        result = normalizer.to_ocsf(process_file_alert)
        assert result["device"]["ip"] == "10.0.0.10"

    def test_no_device_when_no_host(self, normalizer, threshold_rule_with_mitre):
        """Alert without host fields should not have device."""
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        assert "device" not in result


# ── Actor mapping tests ──────────────────────────────────────────────


class TestActorMapping:
    """Verify user -> actor mapping."""

    def test_user_name_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["actor"]["user"]["name"] == "jdoe"

    def test_user_uid_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["actor"]["user"]["uid"] == "S-1-5-21-1234"

    def test_user_domain_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["actor"]["user"]["domain"] == "CORP"

    def test_no_actor_when_no_user(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "actor" not in result


# ── Observables tests ────────────────────────────────────────────────


class TestObservables:
    """Verify observable extraction with private IP filtering."""

    def test_public_ip_in_observables(self, normalizer, query_rule_alert):
        """Public destination IP should appear in observables."""
        result = normalizer.to_ocsf(query_rule_alert)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "8.8.8.8" in ip_values

    def test_private_ip_not_in_observables(self, normalizer, query_rule_alert):
        """Private source IP (192.168.1.50) must NOT appear in observables."""
        result = normalizer.to_ocsf(query_rule_alert)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "192.168.1.50" not in ip_values

    def test_hash_in_observables(self, normalizer, process_file_alert):
        """File hashes should appear in observables."""
        result = normalizer.to_ocsf(process_file_alert)
        obs = result.get("observables", [])
        hash_values = [o["value"] for o in obs if o["type_id"] == 8]
        assert (
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
            in hash_values
        )

    def test_no_observables_for_private_only(self, normalizer, process_file_alert):
        """Alert with only private IPs should not have IP observables."""
        result = normalizer.to_ocsf(process_file_alert)
        obs = result.get("observables", [])
        ip_obs = [o for o in obs if o["type_id"] == 2]
        assert len(ip_obs) == 0

    def test_public_source_ip_in_observables(
        self, normalizer, threshold_rule_with_mitre
    ):
        """Public source IP (198.51.100.23) should appear in observables."""
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "45.33.32.156" in ip_values

    def test_private_dest_ip_excluded(self, normalizer, threshold_rule_with_mitre):
        """Private destination IP (10.0.0.5) must NOT appear in observables."""
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "10.0.0.5" not in ip_values


# ── Network / evidences tests ────────────────────────────────────────


class TestEvidences:
    """Verify network/process/file -> evidences mapping."""

    def test_src_endpoint(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        evidence = result["evidences"][0]
        assert evidence["src_endpoint"]["ip"] == "192.168.1.50"
        assert evidence["src_endpoint"]["port"] == 49152

    def test_dst_endpoint(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        evidence = result["evidences"][0]
        assert evidence["dst_endpoint"]["ip"] == "8.8.8.8"
        assert evidence["dst_endpoint"]["port"] == 443

    def test_connection_info(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        evidence = result["evidences"][0]
        assert evidence["connection_info"]["protocol_name"] == "tcp"
        assert evidence["connection_info"]["direction_id"] == 2  # outbound

    def test_process_info(self, normalizer, process_file_alert):
        result = normalizer.to_ocsf(process_file_alert)
        evidence = result["evidences"][0]
        proc = evidence["process"]
        assert proc["name"] == "powershell.exe"
        assert proc["pid"] == 4512
        assert proc["cmd_line"] == "powershell.exe -ep bypass -enc SQBFAFgA..."
        assert proc["file"]["path"] == (
            "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        )
        assert proc["parent_process"]["name"] == "cmd.exe"

    def test_file_info(self, normalizer, process_file_alert):
        result = normalizer.to_ocsf(process_file_alert)
        evidence = result["evidences"][0]
        file_obj = evidence["file"]
        assert file_obj["name"] == "payload.dll"
        assert file_obj["path"] == "C:\\Windows\\Temp\\payload.dll"
        assert len(file_obj["hashes"]) == 2
        hash_algos = {h["algorithm"] for h in file_obj["hashes"]}
        assert "SHA-256" in hash_algos
        assert "MD5" in hash_algos

    def test_no_evidences_when_no_data(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "evidences" not in result


# ── Raw data tests ───────────────────────────────────────────────────


class TestRawData:
    """Verify raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        # Should be valid JSON
        parsed = json.loads(result["raw_data"])
        assert isinstance(parsed, dict)

    def test_raw_data_hash_is_sha256(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        expected_hash = hashlib.sha256(result["raw_data"].encode()).hexdigest()
        assert result["raw_data_hash"] == expected_hash
        assert len(result["raw_data_hash"]) == 64  # SHA-256 hex is 64 chars


# ── Risk score tests ─────────────────────────────────────────────────


class TestRiskScore:
    """Verify risk score and risk level mapping."""

    def test_risk_score_mapped(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["risk_score"] == 73

    def test_risk_level_high(self, normalizer, query_rule_alert):
        """Score 73 -> High (60-80 range)."""
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["risk_level_id"] == 3
        assert result["risk_level"] == "High"

    def test_risk_level_critical(self, normalizer, threshold_rule_with_mitre):
        """Score 91 -> Critical (80+)."""
        result = normalizer.to_ocsf(threshold_rule_with_mitre)
        assert result["risk_level_id"] == 4
        assert result["risk_level"] == "Critical"

    def test_no_risk_score_when_absent(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "risk_score" not in result


# ── Status mapping tests ────────────────────────────────────────────


class TestStatusMapping:
    """Verify workflow_status -> OCSF status mapping."""

    def test_open_is_new(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["status_id"] == 1
        assert result["status"] == "New"

    def test_acknowledged_is_in_progress(self, normalizer, process_file_alert):
        result = normalizer.to_ocsf(process_file_alert)
        assert result["status_id"] == 2
        assert result["status"] == "In Progress"


# ── Metadata tests ──────────────────────────────────────────────────


class TestMetadata:
    """Verify metadata fields."""

    def test_product_vendor(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["metadata"]["product"]["vendor_name"] == "Elastic"
        assert result["metadata"]["product"]["name"] == "Security"

    def test_labels_from_tags(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        labels = result["metadata"]["labels"]
        assert "Windows" in labels
        assert "Execution" in labels
        assert "T1059" in labels

    def test_event_code_from_uuid(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["metadata"]["event_code"] == "alert-uuid-001"


# ── Unmapped fields tests ───────────────────────────────────────────


class TestUnmapped:
    """Verify unmapped fields are collected."""

    def test_agent_in_unmapped(self, normalizer, process_file_alert):
        result = normalizer.to_ocsf(process_file_alert)
        assert "agent" in result["unmapped"]
        assert result["unmapped"]["agent"]["name"] == "elastic-agent-01"
        assert result["unmapped"]["agent"]["type"] == "endpoint"

    def test_no_unmapped_when_empty(self, normalizer, minimal_alert):
        result = normalizer.to_ocsf(minimal_alert)
        assert "unmapped" not in result or result.get("unmapped") == {}


# ── Disposition defaults tests ──────────────────────────────────────


class TestDisposition:
    """Verify disposition defaults."""

    def test_disposition_unknown_by_default(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"

    def test_action_unknown_by_default(self, normalizer, query_rule_alert):
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["action_id"] == 0
        assert result["action"] == "Unknown"


# ── Time tests ──────────────────────────────────────────────────────


class TestTimeMapping:
    """Verify time field mapping."""

    def test_time_from_original_time(self, normalizer, query_rule_alert):
        """time should use original_time when available."""
        result = normalizer.to_ocsf(query_rule_alert)
        assert result["time_dt"] == "2025-03-15T14:29:55.000Z"

    def test_ocsf_time_from_timestamp(self, normalizer, query_rule_alert):
        """ocsf_time should use @timestamp."""
        result = normalizer.to_ocsf(query_rule_alert)
        assert "ocsf_time" in result

    def test_time_falls_back_to_timestamp(self, normalizer, minimal_alert):
        """When no original_time, time should use @timestamp."""
        result = normalizer.to_ocsf(minimal_alert)
        assert result["time_dt"] == "2025-03-17T12:00:00.000Z"
