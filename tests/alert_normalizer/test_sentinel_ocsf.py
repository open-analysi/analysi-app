"""Unit tests for Microsoft Sentinel incident -> OCSF normalization.

Tests the SentinelOCSFNormalizer with four fixture types:
1. High-severity incident with MITRE ATT&CK tactics and techniques
2. Informational incident with minimal properties
3. Incident with owner and labels
4. Closed incident with classification
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.sentinel_ocsf import SentinelOCSFNormalizer


@pytest.fixture
def normalizer():
    """Create a SentinelOCSFNormalizer instance."""
    return SentinelOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def high_severity_incident() -> dict:
    """High-severity incident with MITRE tactics and techniques."""
    return {
        "id": "/subscriptions/sub-123/resourceGroups/rg-sec/providers/Microsoft.OperationalInsights/workspaces/ws-sentinel/providers/Microsoft.SecurityInsights/incidents/inc-001",
        "name": "inc-001",
        "etag": '"abc123"',
        "type": "Microsoft.SecurityInsights/incidents",
        "properties": {
            "incidentNumber": 42,
            "title": "Brute Force Attack Against Azure Portal",
            "description": "Multiple failed login attempts detected from suspicious IP",
            "severity": "High",
            "status": "Active",
            "createdTimeUtc": "2025-03-15T10:00:00.000Z",
            "lastModifiedTimeUtc": "2025-03-15T12:30:00.000Z",
            "owner": {
                "assignedTo": "John Doe",
                "email": "john.doe@contoso.com",
                "objectId": "user-obj-001",
            },
            "labels": [
                {"labelName": "high-priority", "labelType": "User"},
                {"labelName": "brute-force", "labelType": "User"},
            ],
            "incidentUrl": "https://portal.azure.com/#/sentinel/incidents/inc-001",
            "additionalData": {
                "alertsCount": 5,
                "bookmarksCount": 1,
                "commentsCount": 2,
                "alertProductNames": ["Azure Active Directory Identity Protection"],
                "tactics": ["InitialAccess", "CredentialAccess"],
                "techniques": ["T1078", "T1110"],
            },
            "relatedAnalyticRuleIds": ["/subscriptions/sub-123/providers/.../rule-001"],
        },
    }


@pytest.fixture
def informational_incident() -> dict:
    """Informational/low-severity incident with minimal fields."""
    return {
        "id": "/subscriptions/sub-123/resourceGroups/rg-sec/providers/.../incidents/inc-002",
        "name": "inc-002",
        "properties": {
            "incidentNumber": 43,
            "title": "Unusual Sign-in Activity",
            "severity": "Informational",
            "status": "New",
            "createdTimeUtc": "2025-03-16T08:00:00.000Z",
            "additionalData": {},
        },
    }


@pytest.fixture
def closed_incident() -> dict:
    """Closed incident with classification."""
    return {
        "id": "/subscriptions/sub-123/resourceGroups/rg-sec/providers/.../incidents/inc-003",
        "name": "inc-003",
        "properties": {
            "incidentNumber": 44,
            "title": "Suspicious PowerShell Activity",
            "description": "PowerShell execution with encoded commands",
            "severity": "Medium",
            "status": "Closed",
            "createdTimeUtc": "2025-03-14T06:00:00.000Z",
            "lastModifiedTimeUtc": "2025-03-15T18:00:00.000Z",
            "classification": "TruePositive",
            "classificationComment": "Confirmed malicious activity",
            "owner": {
                "assignedTo": "Jane Smith",
            },
            "additionalData": {
                "alertProductNames": ["Microsoft Defender for Endpoint"],
                "tactics": ["Execution"],
            },
            "relatedAnalyticRuleIds": [
                "/subscriptions/sub-123/providers/.../rule-002",
                "/subscriptions/sub-123/providers/.../rule-003",
            ],
        },
    }


@pytest.fixture
def tactics_only_incident() -> dict:
    """Incident with tactics but no techniques."""
    return {
        "id": "/subscriptions/sub-123/resourceGroups/rg-sec/providers/.../incidents/inc-004",
        "name": "inc-004",
        "properties": {
            "incidentNumber": 45,
            "title": "Lateral Movement Detected",
            "severity": "High",
            "status": "Active",
            "createdTimeUtc": "2025-03-17T14:00:00.000Z",
            "additionalData": {
                "tactics": ["LateralMovement", "Discovery"],
            },
        },
    }


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Test the fixed OCSF scaffold fields."""

    def test_class_uid(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["class_uid"] == 2004
        assert ocsf["class_name"] == "Detection Finding"

    def test_category(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["category_uid"] == 2
        assert ocsf["category_name"] == "Findings"

    def test_activity(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["activity_id"] == 1
        assert ocsf["activity_name"] == "Create"

    def test_type(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["type_uid"] == 200401
        assert ocsf["type_name"] == "Detection Finding: Create"


# ── Message / title tests ────────────────────────────────────────────


class TestMessage:
    """Test message field mapping."""

    def test_message_from_title(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["message"] == "Brute Force Attack Against Azure Portal"

    def test_message_fallback(self, normalizer):
        """Empty title falls back to default."""
        incident = {
            "name": "inc-empty",
            "properties": {"title": "", "severity": "Low", "status": "New"},
        }
        ocsf = normalizer.to_ocsf(incident)
        assert ocsf["message"] == "Unknown Sentinel Incident"


# ── Time tests ───────────────────────────────────────────────────────


class TestTime:
    """Test time field mapping."""

    def test_time_from_created(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["time_dt"] == "2025-03-15T10:00:00.000Z"
        assert isinstance(ocsf["time"], int)
        assert ocsf["time"] > 0

    def test_ocsf_time_from_modified(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert "ocsf_time" in ocsf
        assert isinstance(ocsf["ocsf_time"], int)

    def test_no_ocsf_time_without_modified(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert "ocsf_time" not in ocsf


# ── Severity tests ───────────────────────────────────────────────────


class TestSeverity:
    """Test severity mapping."""

    def test_high_severity(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"

    def test_informational_severity(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert ocsf["severity_id"] == 1
        assert ocsf["severity"] == "Info"

    def test_medium_severity(self, normalizer, closed_incident):
        ocsf = normalizer.to_ocsf(closed_incident)
        assert ocsf["severity_id"] == 3
        assert ocsf["severity"] == "Medium"

    def test_unknown_severity_defaults_to_info(self, normalizer):
        incident = {
            "name": "inc-x",
            "properties": {"title": "Test", "severity": "Unknown", "status": "New"},
        }
        ocsf = normalizer.to_ocsf(incident)
        assert ocsf["severity_id"] == 1
        assert ocsf["severity"] == "Info"


# ── Metadata tests ───────────────────────────────────────────────────


class TestMetadata:
    """Test metadata mapping."""

    def test_product_info(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        product = ocsf["metadata"]["product"]
        assert product["vendor_name"] == "Microsoft"
        assert product["name"] == "Sentinel"

    def test_version_and_profiles(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["metadata"]["version"] == "1.8.0"
        assert "security_control" in ocsf["metadata"]["profiles"]

    def test_labels_from_incident_labels(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        labels = ocsf["metadata"]["labels"]
        assert "high-priority" in labels
        assert "brute-force" in labels

    def test_no_labels_when_empty(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert "labels" not in ocsf["metadata"]

    def test_event_code_from_incident_number(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["metadata"]["event_code"] == "42"


# ── Finding info tests ───────────────────────────────────────────────


class TestFindingInfo:
    """Test finding_info mapping."""

    def test_uid_from_incident_name(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["finding_info"]["uid"] == "inc-001"

    def test_title(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert (
            ocsf["finding_info"]["title"] == "Brute Force Attack Against Azure Portal"
        )

    def test_description(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert "Multiple failed login attempts" in ocsf["finding_info"]["desc"]

    def test_analytic_from_alert_products(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        analytic = ocsf["finding_info"]["analytic"]
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"
        assert "Azure Active Directory Identity Protection" in analytic["name"]

    def test_analytic_uid_single_rule(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        analytic = ocsf["finding_info"]["analytic"]
        assert analytic["uid"] == "/subscriptions/sub-123/providers/.../rule-001"

    def test_analytic_uid_multiple_rules(self, normalizer, closed_incident):
        ocsf = normalizer.to_ocsf(closed_incident)
        analytic = ocsf["finding_info"]["analytic"]
        # Multiple rule IDs joined with comma
        assert "rule-002" in analytic["uid"]
        assert "rule-003" in analytic["uid"]

    def test_types_from_alert_products(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert (
            "Azure Active Directory Identity Protection"
            in ocsf["finding_info"]["types"]
        )

    def test_created_time_dt(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["finding_info"]["created_time_dt"] == "2025-03-15T10:00:00.000Z"


# ── MITRE ATT&CK tests ──────────────────────────────────────────────


class TestMITREAttack:
    """Test MITRE ATT&CK extraction from tactics and techniques."""

    def test_tactics_with_techniques(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        attacks = ocsf["finding_info"]["attacks"]
        assert len(attacks) > 0

        # Should have tactic entries with technique pairings
        tactic_uids = set()
        technique_uids = set()
        for attack in attacks:
            if "tactic" in attack and "uid" in attack["tactic"]:
                tactic_uids.add(attack["tactic"]["uid"])
            if "technique" in attack:
                technique_uids.add(attack["technique"]["uid"])

        assert "TA0001" in tactic_uids  # InitialAccess
        assert "TA0006" in tactic_uids  # CredentialAccess
        assert "T1078" in technique_uids
        assert "T1110" in technique_uids

    def test_tactics_only_no_techniques(self, normalizer, tactics_only_incident):
        ocsf = normalizer.to_ocsf(tactics_only_incident)
        attacks = ocsf["finding_info"]["attacks"]
        assert len(attacks) == 2

        tactic_names = {a["tactic"]["name"] for a in attacks}
        assert "LateralMovement" in tactic_names
        assert "Discovery" in tactic_names

        # LateralMovement -> TA0008
        lateral = next(a for a in attacks if a["tactic"]["name"] == "LateralMovement")
        assert lateral["tactic"]["uid"] == "TA0008"

    def test_no_attacks_when_empty(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert "attacks" not in ocsf["finding_info"]

    def test_tactic_name_to_id_mapping(self, normalizer):
        """Execution tactic should map to TA0002."""
        incident = {
            "name": "inc-x",
            "properties": {
                "title": "Test",
                "severity": "Low",
                "status": "New",
                "additionalData": {"tactics": ["Execution"]},
            },
        }
        ocsf = normalizer.to_ocsf(incident)
        attacks = ocsf["finding_info"]["attacks"]
        assert len(attacks) == 1
        assert attacks[0]["tactic"]["uid"] == "TA0002"
        assert attacks[0]["tactic"]["name"] == "Execution"


# ── Status tests ─────────────────────────────────────────────────────


class TestStatus:
    """Test status mapping."""

    def test_active_status(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["status_id"] == 2
        assert ocsf["status"] == "In Progress"

    def test_new_status(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert ocsf["status_id"] == 1
        assert ocsf["status"] == "New"

    def test_closed_status(self, normalizer, closed_incident):
        ocsf = normalizer.to_ocsf(closed_incident)
        assert ocsf["status_id"] == 3
        assert ocsf["status"] == "Closed"


# ── is_alert tests ───────────────────────────────��───────────────────


class TestIsAlert:
    """Test is_alert flag."""

    def test_always_true(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["is_alert"] is True


# ── Disposition and action defaults ──────────────────────────────────


class TestDispositionAndAction:
    """Test default disposition and action."""

    def test_defaults(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["disposition_id"] == 0
        assert ocsf["disposition"] == "Unknown"
        assert ocsf["action_id"] == 0
        assert ocsf["action"] == "Unknown"


# ── Raw data tests ───────────────────────────────────────────────────


class TestRawData:
    """Test raw_data and raw_data_hash."""

    def test_raw_data_is_json(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        parsed = json.loads(ocsf["raw_data"])
        assert parsed["name"] == "inc-001"

    def test_raw_data_hash(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        expected_hash = hashlib.sha256(ocsf["raw_data"].encode()).hexdigest()
        assert ocsf["raw_data_hash"] == expected_hash


# ── Actor tests ──────────────────────────────────────────────────────


class TestActor:
    """Test actor mapping from incident owner."""

    def test_actor_from_owner(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        actor = ocsf["actor"]
        assert actor["user"]["name"] == "John Doe"
        assert actor["user"]["email_addr"] == "john.doe@contoso.com"
        assert actor["user"]["uid"] == "user-obj-001"

    def test_actor_name_only(self, normalizer, closed_incident):
        ocsf = normalizer.to_ocsf(closed_incident)
        actor = ocsf["actor"]
        assert actor["user"]["name"] == "Jane Smith"
        assert "email_addr" not in actor["user"]

    def test_no_actor_without_owner(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        assert "actor" not in ocsf


# ── Unmapped fields tests ────────────────────────────────────────────


class TestUnmapped:
    """Test unmapped Sentinel-specific fields."""

    def test_incident_url(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["unmapped"]["incident_url"] == (
            "https://portal.azure.com/#/sentinel/incidents/inc-001"
        )

    def test_alerts_count(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["unmapped"]["alerts_count"] == 5

    def test_azure_resource_id(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert "azure_resource_id" in ocsf["unmapped"]
        assert "sub-123" in ocsf["unmapped"]["azure_resource_id"]

    def test_etag(self, normalizer, high_severity_incident):
        ocsf = normalizer.to_ocsf(high_severity_incident)
        assert ocsf["unmapped"]["etag"] == '"abc123"'

    def test_minimal_unmapped(self, normalizer, informational_incident):
        ocsf = normalizer.to_ocsf(informational_incident)
        # Should still have azure_resource_id
        assert "azure_resource_id" in ocsf["unmapped"]


# ── Edge case tests ────────────────────────────────���─────────────────


class TestEdgeCases:
    """Test edge cases and robustness."""

    def test_empty_properties(self, normalizer):
        """Incident with empty properties should not crash."""
        incident = {"name": "inc-empty", "properties": {}}
        ocsf = normalizer.to_ocsf(incident)
        assert ocsf["class_uid"] == 2004
        assert ocsf["message"] == "Unknown Sentinel Incident"

    def test_missing_properties(self, normalizer):
        """Incident without properties key should not crash."""
        incident = {"name": "inc-none"}
        ocsf = normalizer.to_ocsf(incident)
        assert ocsf["class_uid"] == 2004

    def test_none_severity(self, normalizer):
        """None severity defaults to Informational."""
        incident = {
            "name": "inc-x",
            "properties": {"title": "Test", "severity": None, "status": "New"},
        }
        ocsf = normalizer.to_ocsf(incident)
        assert ocsf["severity_id"] == 1
        assert ocsf["severity"] == "Info"

    def test_labels_as_strings(self, normalizer):
        """Labels that are plain strings (not dicts) should work."""
        incident = {
            "name": "inc-x",
            "properties": {
                "title": "Test",
                "severity": "Low",
                "status": "New",
                "labels": ["tag1", "tag2"],
            },
        }
        ocsf = normalizer.to_ocsf(incident)
        assert "tag1" in ocsf["metadata"]["labels"]
        assert "tag2" in ocsf["metadata"]["labels"]

    def test_techniques_without_tactics(self, normalizer):
        """Techniques without tactics should still produce attack entries."""
        incident = {
            "name": "inc-x",
            "properties": {
                "title": "Test",
                "severity": "Low",
                "status": "New",
                "additionalData": {"techniques": ["T1059", "T1071"]},
            },
        }
        ocsf = normalizer.to_ocsf(incident)
        attacks = ocsf["finding_info"]["attacks"]
        assert len(attacks) == 2
        technique_uids = {a["technique"]["uid"] for a in attacks}
        assert "T1059" in technique_uids
        assert "T1071" in technique_uids
