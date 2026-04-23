"""Unit tests for AWS Security (GuardDuty + Security Hub) -> OCSF normalization.

Tests the AWSSecurityOCSFNormalizer with both GuardDuty and Security Hub
finding formats, severity mapping, MITRE ATT&CK extraction, device/actor
building, observable extraction, and edge cases.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.aws_security_ocsf import (
    _GD_TYPE_TO_TACTIC,
    _SH_SEVERITY_MAP,
    AWSSecurityOCSFNormalizer,
    _is_guardduty,
)


@pytest.fixture
def normalizer():
    """Create an AWSSecurityOCSFNormalizer instance."""
    return AWSSecurityOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def guardduty_network_finding() -> dict:
    """Full GuardDuty finding with network connection action."""
    return {
        "id": "gd-finding-001",
        "type": "Recon:EC2/PortProbeUnprotectedPort",
        "severity": 5.0,
        "title": "Unprotected port on EC2 instance is being probed",
        "description": "EC2 instance i-12345 has an unprotected port being probed.",
        "resource": {
            "resourceType": "Instance",
            "instanceDetails": {
                "instanceId": "i-12345",
                "networkInterfaces": [
                    {
                        "privateIpAddress": "172.31.10.5",
                        "publicIp": "54.239.28.85",
                    }
                ],
            },
        },
        "service": {
            "action": {
                "actionType": "NETWORK_CONNECTION",
                "networkConnectionAction": {
                    "remoteIpDetails": {"ipAddressV4": "45.33.32.156"},
                    "localPortDetails": {"port": 22},
                },
            },
            "evidence": {
                "threatIntelligenceDetails": [{"threatListName": "ProofPoint"}]
            },
        },
        "createdAt": "2025-03-15T10:00:00.000Z",
        "updatedAt": "2025-03-15T10:05:00.000Z",
    }


@pytest.fixture
def guardduty_iam_finding() -> dict:
    """GuardDuty finding with IAM access key details."""
    return {
        "id": "gd-finding-002",
        "type": "UnauthorizedAccess:IAMUser/ConsoleLoginSuccess.B",
        "severity": 7.5,
        "title": "API was invoked from an unusual IP address",
        "description": "An API was invoked from an unusual IP address.",
        "resource": {
            "resourceType": "AccessKey",
            "accessKeyDetails": {
                "userName": "admin-user",
                "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
            },
        },
        "service": {
            "action": {
                "actionType": "AWS_API_CALL",
                "awsApiCallAction": {
                    "api": "ConsoleLogin",
                    "serviceName": "signin.amazonaws.com",
                    "remoteIpDetails": {"ipAddressV4": "85.214.132.117"},
                },
            },
        },
        "createdAt": "2025-03-15T12:00:00.000Z",
        "updatedAt": "2025-03-15T12:01:00.000Z",
    }


@pytest.fixture
def guardduty_minimal_finding() -> dict:
    """Minimal GuardDuty finding with just required fields."""
    return {
        "id": "gd-finding-003",
        "type": "CryptoCurrency:EC2/BitcoinTool.B!DNS",
        "severity": 8.0,
        "title": "EC2 instance is querying a domain associated with Bitcoin",
        "createdAt": "2025-03-16T08:00:00.000Z",
    }


@pytest.fixture
def securityhub_finding() -> dict:
    """Full Security Hub finding."""
    return {
        "Id": "arn:aws:securityhub:us-east-1:123456789012:finding/001",
        "Title": "S3 bucket has public read access",
        "Description": "S3 bucket my-bucket allows public read access.",
        "Severity": {"Label": "HIGH", "Normalized": 70},
        "Types": ["TTPs/Initial Access", "Software and Configuration Checks"],
        "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::my-bucket"}],
        "ProductName": "Security Hub",
        "CompanyName": "AWS",
        "CreatedAt": "2025-03-15T09:00:00.000Z",
        "UpdatedAt": "2025-03-15T09:05:00.000Z",
        "Workflow": {"Status": "NEW"},
        "Network": {
            "SourceIpV4": "10.0.0.1",
            "DestinationIpV4": "45.33.32.156",
            "SourcePort": 443,
            "DestinationPort": 8080,
        },
        "Process": {
            "Name": "sshd",
            "Path": "/usr/sbin/sshd",
            "Pid": 1234,
        },
    }


@pytest.fixture
def securityhub_minimal_finding() -> dict:
    """Minimal Security Hub finding."""
    return {
        "Id": "arn:aws:securityhub:us-east-1:123456789012:finding/002",
        "Title": "Simple finding",
        "Severity": {"Label": "LOW"},
        "CreatedAt": "2025-03-16T10:00:00.000Z",
    }


# ── Format detection tests ───────────────────────────────────────────


class TestFormatDetection:
    """Test auto-detection of GuardDuty vs Security Hub format."""

    def test_guardduty_detected_by_type_field(self, guardduty_network_finding):
        assert _is_guardduty(guardduty_network_finding) is True

    def test_securityhub_detected_by_severity_label(self, securityhub_finding):
        assert _is_guardduty(securityhub_finding) is False

    def test_guardduty_detected_by_numeric_severity(self):
        assert _is_guardduty({"severity": 5.0}) is True

    def test_securityhub_detected_by_severity_dict(self):
        assert _is_guardduty({"Severity": {"Label": "HIGH"}}) is False


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Test OCSF scaffold fields for both formats."""

    def test_guardduty_scaffold(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["class_uid"] == 2004
        assert result["class_name"] == "Detection Finding"
        assert result["category_uid"] == 2
        assert result["category_name"] == "Findings"
        assert result["activity_id"] == 1
        assert result["activity_name"] == "Create"
        assert result["type_uid"] == 200401
        assert result["type_name"] == "Detection Finding: Create"
        assert result["is_alert"] is True

    def test_securityhub_scaffold(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        assert result["class_uid"] == 2004
        assert result["is_alert"] is True


# ── GuardDuty severity mapping tests ────────────────────────────────


class TestGuardDutySeverity:
    """Test GuardDuty severity float -> OCSF severity mapping."""

    @pytest.mark.parametrize(
        ("gd_severity", "expected_id", "expected_label"),
        [
            (0.5, 1, "Informational"),
            (1.0, 2, "Low"),
            (2.5, 2, "Low"),
            (3.9, 2, "Low"),
            (4.0, 3, "Medium"),
            (5.5, 3, "Medium"),
            (6.9, 3, "Medium"),
            (7.0, 4, "High"),
            (8.0, 4, "High"),
            (8.9, 4, "High"),
        ],
    )
    def test_severity_mapping(
        self,
        normalizer,
        guardduty_minimal_finding,
        gd_severity,
        expected_id,
        expected_label,
    ):
        guardduty_minimal_finding["severity"] = gd_severity
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert result["severity_id"] == expected_id
        assert result["severity"] == expected_label

    def test_missing_severity(self, normalizer, guardduty_minimal_finding):
        del guardduty_minimal_finding["severity"]
        # Need to keep the type field so it's still detected as GuardDuty
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert result["severity_id"] == 1
        assert result["severity"] == "Informational"

    def test_invalid_severity(self, normalizer, guardduty_minimal_finding):
        guardduty_minimal_finding["severity"] = "not_a_number"
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert result["severity_id"] == 1

    def test_out_of_range_severity(self, normalizer, guardduty_minimal_finding):
        guardduty_minimal_finding["severity"] = 99.0
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert result["severity_id"] == 1


# ── Security Hub severity mapping tests ─────────────────────────────


class TestSecurityHubSeverity:
    """Test Security Hub severity label -> OCSF severity mapping."""

    @pytest.mark.parametrize(
        ("label", "expected_id", "expected_label"),
        [
            ("INFORMATIONAL", 1, "Informational"),
            ("LOW", 2, "Low"),
            ("MEDIUM", 3, "Medium"),
            ("HIGH", 4, "High"),
            ("CRITICAL", 5, "Critical"),
        ],
    )
    def test_severity_mapping(
        self,
        normalizer,
        securityhub_minimal_finding,
        label,
        expected_id,
        expected_label,
    ):
        securityhub_minimal_finding["Severity"] = {"Label": label}
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert result["severity_id"] == expected_id
        assert result["severity"] == expected_label

    def test_missing_severity_object(self, normalizer, securityhub_minimal_finding):
        del securityhub_minimal_finding["Severity"]
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert result["severity_id"] == 1

    def test_severity_map_complete(self):
        """All 5 severity labels are mapped."""
        assert set(_SH_SEVERITY_MAP.keys()) == {
            "INFORMATIONAL",
            "LOW",
            "MEDIUM",
            "HIGH",
            "CRITICAL",
        }


# ── Time mapping tests ──────────────────────────────────────────────


class TestTimeMapping:
    """Test timestamp mapping for both formats."""

    def test_guardduty_time(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["time_dt"] == "2025-03-15T10:00:00.000Z"
        assert isinstance(result["time"], int)
        assert isinstance(result["ocsf_time"], int)

    def test_securityhub_time(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        assert result["time_dt"] == "2025-03-15T09:00:00.000Z"
        assert isinstance(result["time"], int)
        assert isinstance(result["ocsf_time"], int)

    def test_guardduty_no_created_time(self, normalizer):
        data = {
            "id": "gd-001",
            "type": "Recon:EC2/Test",
            "severity": 2.0,
            "title": "Test",
            "updatedAt": "2025-03-15T10:00:00.000Z",
        }
        result = normalizer.to_ocsf(data)
        assert result["time_dt"] == "2025-03-15T10:00:00.000Z"
        assert "ocsf_time" not in result


# ── Message tests ────────────────────────────────────────────────────


class TestMessage:
    """Test message extraction."""

    def test_guardduty_message_from_title(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["message"] == "Unprotected port on EC2 instance is being probed"

    def test_securityhub_message_from_title(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        assert result["message"] == "S3 bucket has public read access"

    def test_guardduty_message_falls_back_to_description(self, normalizer):
        data = {
            "id": "gd-001",
            "type": "Recon:EC2/Test",
            "severity": 2.0,
            "description": "Fallback description",
            "createdAt": "2025-03-15T10:00:00.000Z",
        }
        result = normalizer.to_ocsf(data)
        assert result["message"] == "Fallback description"

    def test_securityhub_message_defaults_to_unknown(self, normalizer):
        data = {"Id": "arn:test", "Severity": {"Label": "LOW"}}
        result = normalizer.to_ocsf(data)
        assert result["message"] == "Unknown Alert"


# ── Metadata tests ──────────────────────────────────────────────────


class TestMetadata:
    """Test OCSF metadata for both formats."""

    def test_guardduty_product(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        meta = result["metadata"]
        assert meta["product"]["vendor_name"] == "Amazon Web Services"
        assert meta["product"]["name"] == "GuardDuty"
        assert meta["version"] == "1.8.0"
        assert "security_control" in meta["profiles"]

    def test_securityhub_product(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        meta = result["metadata"]
        assert meta["product"]["vendor_name"] == "Amazon Web Services"
        assert meta["product"]["name"] == "Security Hub"

    def test_securityhub_labels(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        labels = result["metadata"]["labels"]
        assert "source_product:Security Hub" in labels
        assert "source_company:AWS" in labels

    def test_securityhub_no_labels_without_product(
        self, normalizer, securityhub_minimal_finding
    ):
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert "labels" not in result["metadata"]


# ── Finding Info tests ──────────────────────────────────────────────


class TestFindingInfo:
    """Test finding_info for both formats."""

    def test_guardduty_uid(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["finding_info"]["uid"] == "gd-finding-001"

    def test_guardduty_title(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert "Unprotected port" in result["finding_info"]["title"]

    def test_guardduty_analytic_is_type(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        analytic = result["finding_info"]["analytic"]
        assert analytic["name"] == "Recon:EC2/PortProbeUnprotectedPort"
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"

    def test_guardduty_description(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert "i-12345" in result["finding_info"]["desc"]

    def test_guardduty_created_time(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["finding_info"]["created_time"] == "2025-03-15T10:00:00.000Z"

    def test_securityhub_uid(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        assert "arn:aws:securityhub" in result["finding_info"]["uid"]

    def test_securityhub_data_sources(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        sources = result["finding_info"]["data_sources"]
        assert "TTPs/Initial Access" in sources

    def test_securityhub_analytic(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        analytic = result["finding_info"]["analytic"]
        assert analytic["name"] == "S3 bucket has public read access"


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMitreAttack:
    """Test MITRE ATT&CK mapping from GuardDuty type prefixes."""

    def test_recon_tactic(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0043"
        assert attacks[0]["tactic"]["name"] == "Reconnaissance"

    def test_unauthorized_access_tactic(self, normalizer, guardduty_iam_finding):
        result = normalizer.to_ocsf(guardduty_iam_finding)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0001"
        assert attacks[0]["tactic"]["name"] == "Initial Access"

    def test_cryptocurrency_tactic(self, normalizer, guardduty_minimal_finding):
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        attacks = result["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0040"
        assert attacks[0]["tactic"]["name"] == "Impact"

    def test_unknown_prefix_no_attack(self, normalizer):
        data = {
            "id": "gd-001",
            "type": "SomethingNew:EC2/Test",
            "severity": 2.0,
            "title": "Test",
            "createdAt": "2025-03-15T10:00:00.000Z",
        }
        result = normalizer.to_ocsf(data)
        assert "attacks" not in result["finding_info"]

    def test_tactic_map_covers_all_known_prefixes(self):
        """Verify the mapping covers common GuardDuty type prefixes."""
        expected_prefixes = {
            "Recon",
            "UnauthorizedAccess",
            "CryptoCurrency",
            "Trojan",
            "Backdoor",
            "PenTest",
            "Stealth",
            "Persistence",
            "Impact",
            "CredentialAccess",
            "Exfiltration",
            "Discovery",
        }
        assert set(_GD_TYPE_TO_TACTIC.keys()) == expected_prefixes


# ── Status tests ─────────────────────────────────────────────────────


class TestStatus:
    """Test status mapping."""

    def test_guardduty_defaults_to_new(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["status_id"] == 1
        assert result["status"] == "New"

    @pytest.mark.parametrize(
        ("workflow_status", "expected_id", "expected_label"),
        [
            ("NEW", 1, "New"),
            ("NOTIFIED", 2, "In Progress"),
            ("RESOLVED", 3, "Closed"),
            ("SUPPRESSED", 3, "Closed"),
        ],
    )
    def test_securityhub_status(
        self,
        normalizer,
        securityhub_finding,
        workflow_status,
        expected_id,
        expected_label,
    ):
        securityhub_finding["Workflow"]["Status"] = workflow_status
        result = normalizer.to_ocsf(securityhub_finding)
        assert result["status_id"] == expected_id
        assert result["status"] == expected_label


# ── Device tests ─────────────────────────────────────────────────────


class TestDevice:
    """Test OCSF device object for both formats."""

    def test_guardduty_device_from_instance(
        self, normalizer, guardduty_network_finding
    ):
        result = normalizer.to_ocsf(guardduty_network_finding)
        device = result["device"]
        assert device["uid"] == "i-12345"
        assert device["ip"] == "172.31.10.5"

    def test_guardduty_no_device_without_instance(
        self, normalizer, guardduty_minimal_finding
    ):
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert "device" not in result

    def test_securityhub_device_from_resources(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        device = result["device"]
        assert "arn:aws:s3:::my-bucket" in device["uid"]
        assert device["type"] == "AwsS3Bucket"

    def test_securityhub_no_device_without_resources(
        self, normalizer, securityhub_minimal_finding
    ):
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert "device" not in result


# ── Actor tests ──────────────────────────────────────────────────────


class TestActor:
    """Test OCSF actor object."""

    def test_guardduty_actor_from_access_key(self, normalizer, guardduty_iam_finding):
        result = normalizer.to_ocsf(guardduty_iam_finding)
        actor = result["actor"]
        assert actor["user"]["name"] == "admin-user"
        assert actor["user"]["uid"] == "AKIAIOSFODNN7EXAMPLE"

    def test_guardduty_no_actor_without_access_key(
        self, normalizer, guardduty_network_finding
    ):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert "actor" not in result

    def test_guardduty_no_actor_on_minimal(self, normalizer, guardduty_minimal_finding):
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert "actor" not in result


# ── Observables tests ────────────────────────────────────────────────


class TestObservables:
    """Test OCSF observables — only public IPs."""

    def test_guardduty_remote_ip_observable(
        self, normalizer, guardduty_network_finding
    ):
        result = normalizer.to_ocsf(guardduty_network_finding)
        obs = result["observables"]
        ip_obs = [o for o in obs if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "45.33.32.156" in ip_values

    def test_guardduty_api_call_remote_ip(self, normalizer, guardduty_iam_finding):
        result = normalizer.to_ocsf(guardduty_iam_finding)
        obs = result["observables"]
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "85.214.132.117" in ip_values

    def test_guardduty_no_observables_without_action(
        self, normalizer, guardduty_minimal_finding
    ):
        result = normalizer.to_ocsf(guardduty_minimal_finding)
        assert "observables" not in result

    def test_securityhub_network_observable(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        obs = result["observables"]
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        # 45.33.32.156 is public, 10.0.0.1 is private (should be excluded)
        assert "45.33.32.156" in ip_values
        assert "10.0.0.1" not in ip_values

    def test_securityhub_no_observables_without_network(
        self, normalizer, securityhub_minimal_finding
    ):
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert "observables" not in result


# ── Evidences tests ──────────────────────────────────────────────────


class TestEvidences:
    """Test OCSF evidences for Security Hub process info."""

    def test_securityhub_process_evidence(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        evidences = result["evidences"]
        proc_ev = [e for e in evidences if "process" in e]
        assert len(proc_ev) == 1
        proc = proc_ev[0]["process"]
        assert proc["name"] == "sshd"
        assert proc["path"] == "/usr/sbin/sshd"
        assert proc["pid"] == 1234

    def test_securityhub_no_evidences_without_process(
        self, normalizer, securityhub_minimal_finding
    ):
        result = normalizer.to_ocsf(securityhub_minimal_finding)
        assert "evidences" not in result


# ── Raw data tests ──────────────────────────────────────────────────


class TestRawData:
    """Test raw_data and raw_data_hash."""

    def test_guardduty_raw_data(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        parsed = json.loads(result["raw_data"])
        assert parsed["id"] == "gd-finding-001"

    def test_securityhub_raw_data(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        parsed = json.loads(result["raw_data"])
        assert "arn:aws:securityhub" in parsed["Id"]

    def test_raw_data_hash_is_sha256(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        expected = hashlib.sha256(result["raw_data"].encode()).hexdigest()
        assert result["raw_data_hash"] == expected
        assert len(result["raw_data_hash"]) == 64

    def test_different_sources_different_hashes(
        self, normalizer, guardduty_network_finding, securityhub_finding
    ):
        gd_result = normalizer.to_ocsf(guardduty_network_finding)
        sh_result = normalizer.to_ocsf(securityhub_finding)
        assert gd_result["raw_data_hash"] != sh_result["raw_data_hash"]


# ── Disposition tests ────────────────────────────────────────────────


class TestDisposition:
    """Test default disposition values."""

    def test_guardduty_disposition(self, normalizer, guardduty_network_finding):
        result = normalizer.to_ocsf(guardduty_network_finding)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"
        assert result["action_id"] == 0
        assert result["action"] == "Unknown"

    def test_securityhub_disposition(self, normalizer, securityhub_finding):
        result = normalizer.to_ocsf(securityhub_finding)
        assert result["disposition_id"] == 0
        assert result["action_id"] == 0


# ── Edge case tests ──────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_guardduty_finding(self, normalizer):
        """Empty dict with type field should produce valid scaffold."""
        result = normalizer.to_ocsf({"type": "Unknown:EC2/Test", "severity": 1.0})
        assert result["class_uid"] == 2004
        assert result["severity_id"] == 2  # 1.0 is Low range
        assert result["is_alert"] is True

    def test_empty_securityhub_finding(self, normalizer):
        """Empty dict with Severity.Label should produce valid scaffold."""
        result = normalizer.to_ocsf({"Severity": {"Label": "MEDIUM"}})
        assert result["class_uid"] == 2004
        assert result["severity_id"] == 3
        assert result["message"] == "Unknown Alert"

    def test_guardduty_port_probe_observables(self, normalizer):
        """Port probe action with remote IPs."""
        data = {
            "id": "gd-probe",
            "type": "Recon:EC2/PortProbeUnprotectedPort",
            "severity": 5.0,
            "title": "Port probe",
            "createdAt": "2025-03-15T10:00:00.000Z",
            "service": {
                "action": {
                    "actionType": "PORT_PROBE",
                    "portProbeAction": {
                        "portProbeDetails": [
                            {
                                "remoteIpDetails": {"ipAddressV4": "85.214.132.10"},
                                "localPortDetails": {"port": 22},
                            },
                            {
                                "remoteIpDetails": {"ipAddressV4": "85.214.132.20"},
                                "localPortDetails": {"port": 80},
                            },
                        ]
                    },
                },
            },
        }
        result = normalizer.to_ocsf(data)
        obs = result["observables"]
        ip_values = {o["value"] for o in obs if o["type_id"] == 2}
        assert "85.214.132.10" in ip_values
        assert "85.214.132.20" in ip_values

    def test_private_remote_ip_not_observable(self, normalizer):
        """Private remote IPs should not become observables."""
        data = {
            "id": "gd-priv",
            "type": "Recon:EC2/Test",
            "severity": 2.0,
            "title": "Test",
            "createdAt": "2025-03-15T10:00:00.000Z",
            "service": {
                "action": {
                    "actionType": "NETWORK_CONNECTION",
                    "networkConnectionAction": {
                        "remoteIpDetails": {"ipAddressV4": "192.168.1.100"},
                    },
                },
            },
        }
        result = normalizer.to_ocsf(data)
        assert "observables" not in result
