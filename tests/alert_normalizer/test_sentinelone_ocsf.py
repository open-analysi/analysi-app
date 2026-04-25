"""Unit tests for SentinelOne threat -> OCSF normalization.

Tests the SentinelOneOCSFNormalizer with four fixture types:
1. Malware threat with full threat info and agent data
2. Suspicious threat with MITRE ATT&CK indicators
3. Minimal threat with only required fields
4. Threat with process + file info and multiple hashes
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.sentinelone_ocsf import SentinelOneOCSFNormalizer


@pytest.fixture
def normalizer():
    """Create a SentinelOneOCSFNormalizer instance."""
    return SentinelOneOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def malware_threat() -> dict:
    """Malware threat with full agent and threat info."""
    return {
        "id": "1234567890",
        "threatInfo": {
            "threatName": "Trojan.GenericKD.46813450",
            "classification": "Malware",
            "confidenceLevel": "malicious",
            "analystVerdict": "true_positive",
            "mitigationStatus": "mitigated",
            "sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "sha1": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            "filePath": "C:\\Users\\jdoe\\Downloads\\malware.exe",
            "fileName": "malware.exe",
            "processUser": "CORP\\jdoe",
            "originatorProcess": "explorer.exe",
            "originatorProcessPid": 4512,
            "createdAt": "2025-03-15T14:30:00.000Z",
            "updatedAt": "2025-03-15T14:35:00.000Z",
            "engines": ["Static AI", "Behavioral AI"],
        },
        "agentRealtimeInfo": {
            "agentComputerName": "WORKSTATION-01",
            "agentOsName": "Windows 10 Pro",
            "agentVersion": "23.4.1.155",
            "agentMachineType": "desktop",
            "accountName": "ACME Corp",
            "siteName": "Default Site",
            "networkInterfaces": [
                {"inet": ["192.168.1.50"]},
                {"inet": ["10.0.0.50"]},
            ],
        },
        "indicators": [],
    }


@pytest.fixture
def suspicious_threat_with_mitre() -> dict:
    """Suspicious threat with MITRE ATT&CK indicators."""
    return {
        "id": "9876543210",
        "threatInfo": {
            "threatName": "Suspicious PowerShell Activity",
            "classification": "Hacking Tool",
            "confidenceLevel": "suspicious",
            "analystVerdict": "suspicious",
            "mitigationStatus": "active",
            "sha256": "bbcc1122334455667788aabbccddeeff00112233445566778899aabbccddeeff",
            "filePath": "C:\\Windows\\System32\\powershell.exe",
            "fileName": "powershell.exe",
            "processUser": "NT AUTHORITY\\SYSTEM",
            "originatorProcess": "cmd.exe",
            "originatorProcessPid": 9872,
            "createdAt": "2025-03-16T08:00:00.000Z",
            "updatedAt": "2025-03-16T08:05:00.000Z",
        },
        "agentRealtimeInfo": {
            "agentComputerName": "SERVER-DC01",
            "agentOsName": "Windows Server 2022",
            "networkInterfaces": [
                {"inet": ["10.0.1.100"]},
            ],
        },
        "indicators": [
            {
                "tactics": [
                    {"id": "TA0002", "name": "Execution"},
                ],
                "techniques": [
                    {"id": "T1059", "name": "Command and Scripting Interpreter"},
                    {"id": "T1059.001", "name": "PowerShell"},
                ],
            },
            {
                "tactics": [
                    {"id": "TA0005", "name": "Defense Evasion"},
                ],
                "techniques": [
                    {"id": "T1562", "name": "Impair Defenses"},
                ],
            },
        ],
    }


@pytest.fixture
def minimal_threat() -> dict:
    """Minimal threat with only basic fields."""
    return {
        "id": "5555555555",
        "threatInfo": {
            "threatName": "Generic.Threat",
            "createdAt": "2025-03-17T12:00:00.000Z",
        },
        "agentRealtimeInfo": {},
    }


@pytest.fixture
def pup_threat_with_public_ip() -> dict:
    """PUP threat on a host with a public IP."""
    return {
        "id": "7777777777",
        "threatInfo": {
            "threatName": "PUP.Optional.BrowserHelper",
            "classification": "PUP",
            "confidenceLevel": "suspicious",
            "analystVerdict": "false_positive",
            "mitigationStatus": "blocked",
            "sha256": "deadbeef" * 8,
            "md5": "cafebabe" * 4,
            "sha1": "0" * 40,
            "filePath": "/usr/local/bin/browser_helper",
            "fileName": "browser_helper",
            "processUser": "admin",
            "createdAt": "2025-03-18T10:00:00.000Z",
            "updatedAt": "2025-03-18T10:02:00.000Z",
        },
        "agentRealtimeInfo": {
            "agentComputerName": "LINUX-WEB-01",
            "agentOsName": "Ubuntu 22.04",
            "networkInterfaces": [
                {"inet": ["8.8.8.8"]},
                {"inet": ["10.0.0.5"]},
            ],
        },
    }


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Tests for the OCSF Detection Finding scaffold fields."""

    def test_class_fields(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["class_uid"] == 2004
        assert result["class_name"] == "Detection Finding"
        assert result["category_uid"] == 2
        assert result["category_name"] == "Findings"

    def test_activity_fields(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["activity_id"] == 1
        assert result["activity_name"] == "Create"
        assert result["type_uid"] == 200401
        assert result["type_name"] == "Detection Finding: Create"

    def test_is_alert(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["is_alert"] is True

    def test_status_always_new(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["status_id"] == 1
        assert result["status"] == "New"


# ── Message tests ────────────────────────────────────────────────────


class TestMessage:
    """Tests for the message field construction."""

    def test_full_message(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert "Trojan.GenericKD.46813450" in result["message"]
        assert "(Malware)" in result["message"]
        assert "on WORKSTATION-01" in result["message"]

    def test_minimal_message(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert result["message"] == "Generic.Threat"


# ── Time tests ───────────────────────────────────────────────────────


class TestTime:
    """Tests for time mapping."""

    def test_time_from_created_at(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["time_dt"] == "2025-03-15T14:30:00.000Z"
        assert isinstance(result["time"], int)
        assert result["time"] > 0

    def test_ocsf_time_from_updated_at(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert isinstance(result["ocsf_time"], int)
        assert result["ocsf_time"] > result["time"]

    def test_minimal_time(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "time" in result
        assert "ocsf_time" not in result


# ── Severity tests ───────────────────────────────────────────────────


class TestSeverity:
    """Tests for severity mapping from confidenceLevel."""

    def test_malicious_is_critical(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["severity_id"] == 5
        assert result["severity"] == "Critical"

    def test_suspicious_is_high(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        assert result["severity_id"] == 4
        assert result["severity"] == "High"

    def test_missing_confidence_is_info(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert result["severity_id"] == 1
        assert result["severity"] == "Info"


# ── Metadata tests ───────────────────────────────────────────────────


class TestMetadata:
    """Tests for OCSF metadata."""

    def test_metadata_product(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        meta = result["metadata"]
        assert meta["product"]["vendor_name"] == "SentinelOne"
        assert meta["product"]["name"] == "Singularity"

    def test_metadata_version(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["metadata"]["version"] == "1.8.0"

    def test_metadata_event_code(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["metadata"]["event_code"] == "1234567890"

    def test_metadata_profiles(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        profiles = result["metadata"]["profiles"]
        assert "security_control" in profiles
        assert "host" in profiles


# ── Finding info tests ───────────────────────────────────────────────


class TestFindingInfo:
    """Tests for finding_info construction."""

    def test_uid_from_threat_id(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["finding_info"]["uid"] == "1234567890"

    def test_title_from_threat_name(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["finding_info"]["title"] == "Trojan.GenericKD.46813450"

    def test_analytic_with_engines(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        analytic = result["finding_info"]["analytic"]
        assert "Static AI" in analytic["name"]
        assert "Behavioral AI" in analytic["name"]
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"

    def test_types_from_classification(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert "Malware" in result["finding_info"]["types"]

    def test_types_pup_classification(self, normalizer, pup_threat_with_public_ip):
        result = normalizer.to_ocsf(pup_threat_with_public_ip)
        assert "PUP" in result["finding_info"]["types"]

    def test_description_has_classification_and_confidence(
        self, normalizer, malware_threat
    ):
        result = normalizer.to_ocsf(malware_threat)
        desc = result["finding_info"]["desc"]
        assert "Malware" in desc
        assert "malicious" in desc

    def test_created_time(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["finding_info"]["created_time_dt"] == "2025-03-15T14:30:00.000Z"

    def test_minimal_finding_info(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        fi = result["finding_info"]
        assert fi["uid"] == "5555555555"
        assert fi["title"] == "Generic.Threat"
        assert fi["types"] == []


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMitreAttack:
    """Tests for MITRE ATT&CK extraction from indicators."""

    def test_attacks_extracted(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 3

    def test_technique_uid_mapped(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        attacks = result["finding_info"]["attacks"]
        technique_uids = [a.get("technique", {}).get("uid") for a in attacks]
        assert "T1059" in technique_uids
        assert "T1059.001" in technique_uids
        assert "T1562" in technique_uids

    def test_tactic_mapped(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        attacks = result["finding_info"]["attacks"]
        # First two attacks share the Execution tactic
        assert attacks[0]["tactic"]["uid"] == "TA0002"
        assert attacks[0]["tactic"]["name"] == "Execution"

    def test_no_attacks_for_empty_indicators(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert "attacks" not in result["finding_info"]

    def test_no_attacks_for_minimal(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "attacks" not in result["finding_info"]


# ── Disposition tests ────────────────────────────────────────────────


class TestDisposition:
    """Tests for disposition mapping from analystVerdict."""

    def test_true_positive(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["disposition_id"] == 10
        assert result["disposition"] == "True Positive"

    def test_suspicious(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        assert result["disposition_id"] == 14
        assert result["disposition"] == "Suspicious"

    def test_false_positive(self, normalizer, pup_threat_with_public_ip):
        result = normalizer.to_ocsf(pup_threat_with_public_ip)
        assert result["disposition_id"] == 11
        assert result["disposition"] == "False Positive"

    def test_undefined_verdict(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"


# ── Action tests ─────────────────────────────────────────────────────


class TestAction:
    """Tests for action mapping from mitigationStatus."""

    def test_mitigated_action(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["action_id"] == 2
        assert result["action"] == "Denied"

    def test_active_action(self, normalizer, suspicious_threat_with_mitre):
        result = normalizer.to_ocsf(suspicious_threat_with_mitre)
        assert result["action_id"] == 1
        assert result["action"] == "Allowed"

    def test_blocked_action(self, normalizer, pup_threat_with_public_ip):
        result = normalizer.to_ocsf(pup_threat_with_public_ip)
        assert result["action_id"] == 2
        assert result["action"] == "Denied"


# ── Device tests ─────────────────────────────────────────────────────


class TestDevice:
    """Tests for OCSF device from SentinelOne agent info."""

    def test_device_hostname(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["device"]["hostname"] == "WORKSTATION-01"

    def test_device_ip_from_network_interfaces(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["device"]["ip"] == "192.168.1.50"

    def test_device_os(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["device"]["os"]["name"] == "Windows 10 Pro"

    def test_no_device_for_empty_agent(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "device" not in result


# ── Actor tests ──────────────────────────────────────────────────────


class TestActor:
    """Tests for OCSF actor from SentinelOne threat fields."""

    def test_actor_user(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["actor"]["user"]["name"] == "CORP\\jdoe"

    def test_no_actor_when_no_user(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "actor" not in result


# ── Observables tests ────────────────────────────────────────────────


class TestObservables:
    """Tests for OCSF observables from SentinelOne threat fields."""

    def test_hash_observables(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        observables = result["observables"]
        hash_obs = [o for o in observables if o["type_id"] == 8]
        assert len(hash_obs) == 3  # sha256, md5, sha1

    def test_public_ip_observable(self, normalizer, pup_threat_with_public_ip):
        result = normalizer.to_ocsf(pup_threat_with_public_ip)
        observables = result["observables"]
        ip_obs = [o for o in observables if o["type_id"] == 2]
        assert len(ip_obs) == 1
        assert ip_obs[0]["value"] == "8.8.8.8"

    def test_private_ip_not_in_observables(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        observables = result.get("observables", [])
        ip_obs = [o for o in observables if o["type_id"] == 2]
        # 192.168.1.50 and 10.0.0.50 are private — should NOT appear
        assert len(ip_obs) == 0

    def test_no_observables_for_minimal(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "observables" not in result


# ── Evidences tests ──────────────────────────────────────────────────


class TestEvidences:
    """Tests for OCSF evidences from SentinelOne threat fields."""

    def test_file_evidence(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        evidence = result["evidences"][0]
        assert evidence["file"]["name"] == "malware.exe"
        assert evidence["file"]["path"] == "C:\\Users\\jdoe\\Downloads\\malware.exe"

    def test_file_hashes_in_evidence(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        hashes = result["evidences"][0]["file"]["hashes"]
        algorithms = [h["algorithm"] for h in hashes]
        assert "SHA-256" in algorithms
        assert "MD5" in algorithms
        assert "SHA-1" in algorithms

    def test_process_evidence(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        evidence = result["evidences"][0]
        assert evidence["process"]["name"] == "explorer.exe"
        assert evidence["process"]["pid"] == 4512

    def test_no_evidences_for_minimal(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert "evidences" not in result


# ── Raw data tests ───────────────────────────────────────────────────


class TestRawData:
    """Tests for raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        # Should be valid JSON
        parsed = json.loads(result["raw_data"])
        assert parsed["id"] == "1234567890"

    def test_raw_data_hash(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        expected_hash = hashlib.sha256(result["raw_data"].encode()).hexdigest()
        assert result["raw_data_hash"] == expected_hash


# ── Unmapped fields tests ────────────────────────────────────────────


class TestUnmapped:
    """Tests for unmapped SentinelOne-specific fields."""

    def test_unmapped_mitigation(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["unmapped"]["mitigation_status"] == "mitigated"

    def test_unmapped_analyst_verdict(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["unmapped"]["analyst_verdict"] == "true_positive"

    def test_unmapped_agent_version(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["unmapped"]["agent_version"] == "23.4.1.155"

    def test_unmapped_account_site(self, normalizer, malware_threat):
        result = normalizer.to_ocsf(malware_threat)
        assert result["unmapped"]["account_name"] == "ACME Corp"
        assert result["unmapped"]["site_name"] == "Default Site"

    def test_minimal_no_unmapped(self, normalizer, minimal_threat):
        result = normalizer.to_ocsf(minimal_threat)
        assert result.get("unmapped") is None or result["unmapped"] == {}
