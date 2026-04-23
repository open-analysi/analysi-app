"""Unit tests for Chronicle detection alert -> OCSF normalization.

Tests the ChronicleOCSFNormalizer with four fixture types:
1. Single-event rule detection with principal + target + network
2. Multi-event rule with MITRE ATT&CK labels
3. Minimal detection with only required fields
4. Detection with multiple UDM events
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.chronicle_ocsf import ChronicleOCSFNormalizer


@pytest.fixture
def normalizer():
    """Create a ChronicleOCSFNormalizer instance."""
    return ChronicleOCSFNormalizer()


# -- Test fixtures -----------------------------------------------------------


@pytest.fixture
def single_event_detection() -> dict:
    """Single-event rule detection with principal, target, and network."""
    return {
        "id": "de_12345678-1234-1234-1234-123456789abc",
        "type": "RULE_DETECTION",
        "alertState": "ALERTING",
        "detection": [
            {
                "ruleName": "Suspicious Outbound Connection",
                "ruleId": "ru_abcd1234",
                "ruleType": "SINGLE_EVENT",
                "severity": "HIGH",
                "description": "Outbound connection to known malicious IP detected",
                "detectionTime": "2025-03-15T10:30:00Z",
                "ruleVersion": "v1.2",
                "ruleLabels": [
                    {"key": "author", "value": "secops-team"},
                    {"key": "priority", "value": "high"},
                ],
                "events": [
                    {
                        "principal": {
                            "hostname": "WORKSTATION-42",
                            "ip": ["192.168.1.100"],
                            "user": {
                                "userid": "jsmith",
                                "windowsSid": "S-1-5-21-1234",
                                "emailAddresses": ["jsmith@example.com"],
                            },
                            "assetId": "asset-001",
                        },
                        "target": {
                            "ip": ["93.184.216.34"],
                            "port": 443,
                        },
                        "network": {
                            "applicationProtocol": "HTTPS",
                            "direction": "OUTBOUND",
                        },
                        "securityResult": [
                            {
                                "action": ["ALLOW"],
                                "severity": "HIGH",
                                "category": "Network",
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def multi_event_with_mitre() -> dict:
    """Multi-event detection with MITRE ATT&CK labels."""
    return {
        "id": "de_mitre_detection_001",
        "type": "RULE_DETECTION",
        "alertState": "ALERTING",
        "detection": [
            {
                "ruleName": "Brute Force SSH Attempts",
                "ruleId": "ru_brute_001",
                "ruleType": "MULTI_EVENT",
                "severity": "CRITICAL",
                "description": "Multiple failed SSH login attempts from external IP",
                "detectionTime": "2025-03-16T08:00:00Z",
                "ruleLabels": [
                    {"key": "tactic", "value": "TA0006"},
                    {"key": "tactic_name", "value": "Credential Access"},
                    {"key": "technique", "value": "T1110"},
                    {"key": "technique_name", "value": "Brute Force"},
                    {"key": "subtechnique", "value": "T1110.001"},
                    {"key": "subtechnique_name", "value": "Password Guessing"},
                ],
                "events": [
                    {
                        "principal": {
                            "ip": ["45.33.32.156"],
                            "port": 54321,
                        },
                        "target": {
                            "ip": ["10.0.0.5"],
                            "port": 22,
                            "hostname": "ssh-server-01",
                        },
                        "network": {
                            "applicationProtocol": "SSH",
                            "direction": "INBOUND",
                        },
                    },
                    {
                        "principal": {
                            "ip": ["45.33.32.156"],
                            "port": 54322,
                        },
                        "target": {
                            "ip": ["10.0.0.5"],
                            "port": 22,
                        },
                        "network": {
                            "applicationProtocol": "SSH",
                        },
                    },
                ],
            }
        ],
    }


@pytest.fixture
def minimal_detection() -> dict:
    """Minimal detection with only required fields."""
    return {
        "id": "de_minimal_001",
        "type": "RULE_DETECTION",
        "detection": [
            {
                "ruleName": "Generic Detection Rule",
                "ruleType": "SINGLE_EVENT",
                "severity": "LOW",
                "detectionTime": "2025-03-17T12:00:00Z",
                "events": [],
            }
        ],
    }


@pytest.fixture
def detection_with_dns() -> dict:
    """Detection with DNS and URL info in events."""
    return {
        "id": "de_dns_001",
        "type": "RULE_DETECTION",
        "alertState": "NOT_ALERTING",
        "detection": [
            {
                "ruleName": "DNS Query to Suspicious Domain",
                "ruleId": "ru_dns_001",
                "ruleType": "SINGLE_EVENT",
                "severity": "MEDIUM",
                "description": "DNS query to suspicious domain detected",
                "detectionTime": "2025-03-18T09:15:00Z",
                "events": [
                    {
                        "principal": {
                            "hostname": "SERVER-DC01",
                            "ip": ["10.0.0.10"],
                        },
                        "target": {
                            "url": "https://evil.example.tk/payload",
                            "hostname": "evil.example.tk",
                        },
                        "network": {
                            "applicationProtocol": "DNS",
                            "dns": {
                                "domain": "evil.example.tk",
                            },
                        },
                    }
                ],
            }
        ],
    }


# -- OCSF scaffold tests -----------------------------------------------------


class TestOCSFScaffold:
    """Verify OCSF scaffold fields are correct."""

    def test_class_uid(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["class_uid"] == 2004

    def test_class_name(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["class_name"] == "Detection Finding"

    def test_is_alert(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["is_alert"] is True

    def test_category(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["category_uid"] == 2
        assert result["category_name"] == "Findings"

    def test_activity(self, normalizer, minimal_detection):
        result = normalizer.to_ocsf(minimal_detection)
        assert result["activity_id"] == 1
        assert result["activity_name"] == "Create"
        assert result["type_uid"] == 200401


# -- Finding info tests -------------------------------------------------------


class TestFindingInfo:
    """Verify finding_info mapping."""

    def test_analytic_name_equals_rule_name(self, normalizer, single_event_detection):
        """CRITICAL: analytic.name must equal the rule name for workflow routing."""
        result = normalizer.to_ocsf(single_event_detection)
        fi = result["finding_info"]
        assert fi["analytic"]["name"] == "Suspicious Outbound Connection"

    def test_analytic_type_is_rule(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        fi = result["finding_info"]
        assert fi["analytic"]["type_id"] == 1
        assert fi["analytic"]["type"] == "Rule"

    def test_analytic_uid_from_rule_id(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["finding_info"]["analytic"]["uid"] == "ru_abcd1234"

    def test_finding_uid_is_detection_id(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert (
            result["finding_info"]["uid"] == "de_12345678-1234-1234-1234-123456789abc"
        )

    def test_title_from_description(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        fi = result["finding_info"]
        assert fi["title"] == "Outbound connection to known malicious IP detected"

    def test_title_falls_back_to_rule_name(self, normalizer):
        """When no description, title should use rule name."""
        data = {
            "id": "de_test",
            "type": "RULE_DETECTION",
            "detection": [
                {
                    "ruleName": "My Rule",
                    "ruleType": "SINGLE_EVENT",
                    "severity": "LOW",
                    "detectionTime": "2025-03-17T12:00:00Z",
                    "events": [],
                }
            ],
        }
        result = normalizer.to_ocsf(data)
        assert result["finding_info"]["title"] == "My Rule"

    def test_types_from_rule_type(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["finding_info"]["types"] == ["SINGLE_EVENT"]

    def test_description_from_rule(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert (
            result["finding_info"]["desc"]
            == "Outbound connection to known malicious IP detected"
        )

    def test_created_time_dt(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["finding_info"]["created_time_dt"] == "2025-03-15T10:30:00Z"


# -- Severity mapping tests ---------------------------------------------------


class TestSeverityMapping:
    """Verify severity is correctly mapped."""

    def test_high_severity(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["severity_id"] == 4
        assert result["severity"] == "High"

    def test_critical_severity(self, normalizer, multi_event_with_mitre):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        assert result["severity_id"] == 5
        assert result["severity"] == "Critical"

    def test_low_severity(self, normalizer, minimal_detection):
        result = normalizer.to_ocsf(minimal_detection)
        assert result["severity_id"] == 2
        assert result["severity"] == "Low"

    def test_medium_severity(self, normalizer, detection_with_dns):
        result = normalizer.to_ocsf(detection_with_dns)
        assert result["severity_id"] == 3
        assert result["severity"] == "Medium"


# -- MITRE ATT&CK tests -------------------------------------------------------


class TestMitreAttack:
    """Verify MITRE ATT&CK extracted from ruleLabels."""

    def test_attacks_present(self, normalizer, multi_event_with_mitre):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        attacks = result["finding_info"].get("attacks", [])
        assert len(attacks) > 0

    def test_tactic_mapping(self, normalizer, multi_event_with_mitre):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        attacks = result["finding_info"]["attacks"]
        tactic = attacks[0].get("tactic", {})
        assert tactic["uid"] == "TA0006"
        assert tactic["name"] == "Credential Access"

    def test_technique_mapping(self, normalizer, multi_event_with_mitre):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        attacks = result["finding_info"]["attacks"]
        technique = attacks[0].get("technique", {})
        assert technique["uid"] == "T1110"
        assert technique["name"] == "Brute Force"

    def test_subtechnique_mapping(self, normalizer, multi_event_with_mitre):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        attacks = result["finding_info"]["attacks"]
        sub = attacks[0].get("sub_technique", {})
        assert sub["uid"] == "T1110.001"
        assert sub["name"] == "Password Guessing"

    def test_no_attacks_when_no_mitre_labels(self, normalizer, single_event_detection):
        """Detection without MITRE labels has no attacks."""
        result = normalizer.to_ocsf(single_event_detection)
        assert "attacks" not in result["finding_info"]


# -- Device mapping tests (principal -> device) --------------------------------


class TestDeviceMapping:
    """Verify principal -> device mapping."""

    def test_hostname_mapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["device"]["hostname"] == "WORKSTATION-42"

    def test_ip_from_principal_ip_list(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["device"]["ip"] == "192.168.1.100"

    def test_asset_id_as_uid(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["device"]["uid"] == "asset-001"

    def test_no_device_when_no_principal(self, normalizer, minimal_detection):
        """Detection with empty events should not have device."""
        result = normalizer.to_ocsf(minimal_detection)
        assert "device" not in result


# -- Actor mapping tests (principal.user -> actor) -----------------------------


class TestActorMapping:
    """Verify principal.user -> actor mapping."""

    def test_user_uid_mapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["actor"]["user"]["uid"] == "jsmith"

    def test_user_name_from_windows_sid(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["actor"]["user"]["name"] == "S-1-5-21-1234"

    def test_user_email(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["actor"]["user"]["email_addr"] == "jsmith@example.com"

    def test_no_actor_when_no_user(self, normalizer, minimal_detection):
        result = normalizer.to_ocsf(minimal_detection)
        assert "actor" not in result


# -- Observables tests ---------------------------------------------------------


class TestObservables:
    """Verify observable extraction with private IP filtering."""

    def test_public_target_ip_in_observables(self, normalizer, single_event_detection):
        """Public target IP should appear in observables."""
        result = normalizer.to_ocsf(single_event_detection)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "93.184.216.34" in ip_values

    def test_private_principal_ip_not_in_observables(
        self, normalizer, single_event_detection
    ):
        """Private principal IP (192.168.1.100) must NOT appear in observables."""
        result = normalizer.to_ocsf(single_event_detection)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "192.168.1.100" not in ip_values

    def test_public_source_ip_in_observables(self, normalizer, multi_event_with_mitre):
        """Public principal IP (45.33.32.156) should appear in observables."""
        result = normalizer.to_ocsf(multi_event_with_mitre)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "45.33.32.156" in ip_values

    def test_private_target_ip_excluded(self, normalizer, multi_event_with_mitre):
        """Private target IP (10.0.0.5) must NOT appear in observables."""
        result = normalizer.to_ocsf(multi_event_with_mitre)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "10.0.0.5" not in ip_values

    def test_hostname_in_observables(self, normalizer, multi_event_with_mitre):
        """Target hostname should appear in observables."""
        result = normalizer.to_ocsf(multi_event_with_mitre)
        obs = result.get("observables", [])
        hostname_values = [o["value"] for o in obs if o["type_id"] == 1]
        assert "ssh-server-01" in hostname_values

    def test_url_in_observables(self, normalizer, detection_with_dns):
        """Target URL should appear in observables."""
        result = normalizer.to_ocsf(detection_with_dns)
        obs = result.get("observables", [])
        url_values = [o["value"] for o in obs if o["type_id"] == 6]
        assert "https://evil.example.tk/payload" in url_values

    def test_dns_domain_in_observables(self, normalizer, detection_with_dns):
        """DNS domain should appear in observables."""
        result = normalizer.to_ocsf(detection_with_dns)
        obs = result.get("observables", [])
        hostname_values = [o["value"] for o in obs if o["type_id"] == 1]
        assert "evil.example.tk" in hostname_values

    def test_no_observables_for_private_only(self, normalizer, detection_with_dns):
        """Detection with only private IPs should not have IP observables."""
        result = normalizer.to_ocsf(detection_with_dns)
        obs = result.get("observables", [])
        ip_obs = [o for o in obs if o["type_id"] == 2]
        assert len(ip_obs) == 0

    def test_deduplication_across_events(self, normalizer, multi_event_with_mitre):
        """Same IP appearing in multiple events should only appear once."""
        result = normalizer.to_ocsf(multi_event_with_mitre)
        obs = result.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert ip_values.count("45.33.32.156") == 1


# -- Network / evidences tests ------------------------------------------------


class TestEvidences:
    """Verify network -> evidences mapping."""

    def test_src_endpoint(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        evidence = result["evidences"][0]
        assert evidence["src_endpoint"]["ip"] == "192.168.1.100"

    def test_dst_endpoint(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        evidence = result["evidences"][0]
        assert evidence["dst_endpoint"]["ip"] == "93.184.216.34"
        assert evidence["dst_endpoint"]["port"] == 443

    def test_connection_info_protocol(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        evidence = result["evidences"][0]
        assert evidence["connection_info"]["protocol_name"] == "HTTPS"

    def test_connection_info_direction_outbound(
        self, normalizer, single_event_detection
    ):
        result = normalizer.to_ocsf(single_event_detection)
        evidence = result["evidences"][0]
        assert evidence["connection_info"]["direction_id"] == 2  # outbound

    def test_connection_info_direction_inbound(
        self, normalizer, multi_event_with_mitre
    ):
        result = normalizer.to_ocsf(multi_event_with_mitre)
        evidence = result["evidences"][0]
        assert evidence["connection_info"]["direction_id"] == 1  # inbound

    def test_multiple_events_create_multiple_evidences(
        self, normalizer, multi_event_with_mitre
    ):
        """Each UDM event should produce a separate evidence entry."""
        result = normalizer.to_ocsf(multi_event_with_mitre)
        assert len(result["evidences"]) == 2

    def test_no_evidences_when_no_events(self, normalizer, minimal_detection):
        result = normalizer.to_ocsf(minimal_detection)
        assert "evidences" not in result


# -- Raw data tests -----------------------------------------------------------


class TestRawData:
    """Verify raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        parsed = json.loads(result["raw_data"])
        assert isinstance(parsed, dict)

    def test_raw_data_hash_is_sha256(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        expected_hash = hashlib.sha256(result["raw_data"].encode()).hexdigest()
        assert result["raw_data_hash"] == expected_hash
        assert len(result["raw_data_hash"]) == 64


# -- Status mapping tests -----------------------------------------------------


class TestStatusMapping:
    """Verify alertState -> OCSF status mapping."""

    def test_alerting_is_new(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["status_id"] == 1
        assert result["status"] == "New"

    def test_not_alerting_is_closed(self, normalizer, detection_with_dns):
        result = normalizer.to_ocsf(detection_with_dns)
        assert result["status_id"] == 3
        assert result["status"] == "Closed"


# -- Metadata tests -----------------------------------------------------------


class TestMetadata:
    """Verify metadata fields."""

    def test_product_vendor(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["metadata"]["product"]["vendor_name"] == "Google"
        assert result["metadata"]["product"]["name"] == "Chronicle"

    def test_event_code_from_detection_id(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert (
            result["metadata"]["event_code"]
            == "de_12345678-1234-1234-1234-123456789abc"
        )

    def test_labels_from_rule_labels(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        labels = result["metadata"]["labels"]
        assert "author:secops-team" in labels
        assert "priority:high" in labels


# -- Disposition defaults tests ------------------------------------------------


class TestDisposition:
    """Verify disposition defaults."""

    def test_disposition_unknown_by_default(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["disposition_id"] == 0
        assert result["disposition"] == "Unknown"

    def test_action_unknown_by_default(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["action_id"] == 0
        assert result["action"] == "Unknown"


# -- Unmapped fields tests ----------------------------------------------------


class TestUnmapped:
    """Verify unmapped fields are collected."""

    def test_detection_type_in_unmapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["unmapped"]["detection_type"] == "RULE_DETECTION"

    def test_rule_version_in_unmapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["unmapped"]["rule_version"] == "v1.2"

    def test_alert_state_in_unmapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["unmapped"]["alert_state"] == "ALERTING"

    def test_security_result_in_unmapped(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        sec_results = result["unmapped"]["security_result"]
        assert len(sec_results) == 1
        assert sec_results[0]["severity"] == "HIGH"


# -- Time tests ---------------------------------------------------------------


class TestTimeMapping:
    """Verify time field mapping."""

    def test_time_from_detection_time(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert result["time_dt"] == "2025-03-15T10:30:00Z"

    def test_time_as_epoch_ms(self, normalizer, single_event_detection):
        result = normalizer.to_ocsf(single_event_detection)
        assert isinstance(result["time"], int)
        assert result["time"] > 0
