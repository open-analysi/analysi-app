"""Unit tests for QRadar offense -> OCSF normalization.

Tests the QRadarOCSFNormalizer with four fixture types:
1. Standard offense with source IP and multiple categories
2. High-severity offense with username offense_source
3. Minimal offense with only required fields
4. Closed offense with rules and counts
"""

from __future__ import annotations

import hashlib
import json

import pytest

from alert_normalizer.qradar_ocsf import (
    QRadarOCSFNormalizer,
    _looks_like_ip,
    _map_severity,
)


@pytest.fixture
def normalizer():
    """Create a QRadarOCSFNormalizer instance."""
    return QRadarOCSFNormalizer()


# ── Test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def source_ip_offense() -> dict:
    """Standard offense triggered by a source IP."""
    return {
        "id": 42,
        "description": "Multiple Login Failures for the Same User",
        "offense_type": 0,
        "offense_type_str": "Source IP",
        "offense_source": "10.0.0.55",
        "severity": 6,
        "magnitude": 7,
        "relevance": 5,
        "credibility": 8,
        "status": "OPEN",
        "categories": ["Authentication", "Brute Force"],
        "rules": [
            {"id": 100123, "type": "CRE_RULE"},
            {"id": 100124, "type": "CRE_RULE"},
        ],
        "start_time": 1710500000000,
        "last_updated_time": 1710503600000,
        "source_address_ids": [1001, 1002],
        "local_destination_address_ids": [2001],
        "username_count": 1,
        "source_count": 2,
        "destination_count": 1,
        "event_count": 150,
        "flow_count": 0,
    }


@pytest.fixture
def username_offense() -> dict:
    """High-severity offense with username as offense source."""
    return {
        "id": 88,
        "description": "Excessive Data Access by Single User",
        "offense_type": 2,
        "offense_type_str": "Username",
        "offense_source": "jsmith",
        "severity": 9,
        "magnitude": 8,
        "relevance": 7,
        "credibility": 9,
        "status": "OPEN",
        "categories": ["Data Exfiltration"],
        "rules": [{"id": 200456, "type": "CRE_RULE"}],
        "start_time": 1710600000000,
        "last_updated_time": 1710603600000,
        "username_count": 1,
        "source_count": 3,
        "destination_count": 5,
        "event_count": 500,
        "flow_count": 25,
    }


@pytest.fixture
def minimal_offense() -> dict:
    """Minimal offense with only required fields."""
    return {
        "id": 1,
        "status": "OPEN",
        "start_time": 1710400000000,
    }


@pytest.fixture
def closed_offense() -> dict:
    """Closed offense with low severity."""
    return {
        "id": 99,
        "description": "Low Severity Network Scan",
        "offense_type_str": "Source IP",
        "offense_source": "192.168.1.100",
        "severity": 2,
        "magnitude": 3,
        "relevance": 2,
        "credibility": 4,
        "status": "CLOSED",
        "categories": ["Reconnaissance"],
        "rules": [],
        "start_time": 1710300000000,
        "last_updated_time": 1710350000000,
        "event_count": 10,
        "flow_count": 0,
    }


# ── OCSF scaffold tests ─────────────────────────────────────────────


class TestOCSFScaffold:
    """Verify the base OCSF structure is always correct."""

    def test_class_uid_and_names(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["class_uid"] == 2004
        assert ocsf["class_name"] == "Detection Finding"
        assert ocsf["category_uid"] == 2
        assert ocsf["category_name"] == "Findings"
        assert ocsf["activity_id"] == 1
        assert ocsf["activity_name"] == "Create"
        assert ocsf["type_uid"] == 200401
        assert ocsf["type_name"] == "Detection Finding: Create"

    def test_is_alert_always_true(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["is_alert"] is True

    def test_minimal_offense_has_scaffold(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert ocsf["class_uid"] == 2004
        assert ocsf["is_alert"] is True


# ── Title / message tests ────────────────────────────────────────────


class TestMessage:
    def test_description_becomes_message(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["message"] == "Multiple Login Failures for the Same User"

    def test_fallback_to_offense_id(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert ocsf["message"] == "QRadar Offense 1"


# ── Time tests ───────────────────────────────────────────────────────


class TestTime:
    def test_start_time_maps_to_time(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["time"] == 1710500000000
        assert "time_dt" in ocsf

    def test_last_updated_maps_to_ocsf_time(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["ocsf_time"] == 1710503600000

    def test_minimal_offense_has_time(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert ocsf["time"] == 1710400000000

    def test_missing_last_updated_no_ocsf_time(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "ocsf_time" not in ocsf


# ── Severity mapping tests ───────────────────────────────────────────


class TestSeverity:
    def test_severity_6_maps_to_high(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"

    def test_severity_9_maps_to_critical(self, normalizer, username_offense):
        ocsf = normalizer.to_ocsf(username_offense)
        assert ocsf["severity_id"] == 5
        assert ocsf["severity"] == "Critical"

    def test_severity_2_maps_to_low(self, normalizer, closed_offense):
        ocsf = normalizer.to_ocsf(closed_offense)
        assert ocsf["severity_id"] == 2
        assert ocsf["severity"] == "Low"

    def test_missing_severity_defaults_to_info(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert ocsf["severity_id"] == 1
        assert ocsf["severity"] == "Info"

    @pytest.mark.parametrize(
        ("sev", "expected_id", "expected_label"),
        [
            (1, 2, "Low"),
            (2, 2, "Low"),
            (3, 3, "Medium"),
            (4, 3, "Medium"),
            (5, 4, "High"),
            (6, 4, "High"),
            (7, 4, "High"),
            (8, 5, "Critical"),
            (9, 5, "Critical"),
            (10, 5, "Critical"),
        ],
    )
    def test_all_severity_values(self, sev, expected_id, expected_label):
        result_id, result_label = _map_severity(sev)
        assert result_id == expected_id
        assert result_label == expected_label


# ── Metadata tests ───────────────────────────────────────────────────


class TestMetadata:
    def test_product_info(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        meta = ocsf["metadata"]
        assert meta["product"]["vendor_name"] == "IBM"
        assert meta["product"]["name"] == "QRadar"

    def test_version_and_profiles(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        meta = ocsf["metadata"]
        assert meta["version"] == "1.8.0"
        assert "security_control" in meta["profiles"]

    def test_categories_as_labels(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        meta = ocsf["metadata"]
        assert "Authentication" in meta["labels"]
        assert "Brute Force" in meta["labels"]

    def test_offense_id_as_event_code(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["metadata"]["event_code"] == "42"

    def test_minimal_offense_no_labels(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "labels" not in ocsf["metadata"]


# ── Finding info tests ───────────────────────────────────────────────


class TestFindingInfo:
    def test_uid_is_generated(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        finding = ocsf["finding_info"]
        assert finding["uid"]  # non-empty UUID

    def test_title_matches_message(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["finding_info"]["title"] == ocsf["message"]

    def test_categories_as_types(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        finding = ocsf["finding_info"]
        assert "Authentication" in finding["types"]
        assert "Brute Force" in finding["types"]

    def test_description_as_desc(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        finding = ocsf["finding_info"]
        assert finding["desc"] == "Multiple Login Failures for the Same User"

    def test_rule_as_analytic(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        finding = ocsf["finding_info"]
        analytic = finding["analytic"]
        assert analytic["type_id"] == 1
        assert analytic["type"] == "Rule"
        assert analytic["uid"] == "100123"
        assert "QRadar Rule" in analytic["name"]

    def test_no_rules_no_analytic(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "analytic" not in ocsf["finding_info"]

    def test_empty_rules_no_analytic(self, normalizer, closed_offense):
        ocsf = normalizer.to_ocsf(closed_offense)
        assert "analytic" not in ocsf["finding_info"]

    def test_created_time_from_start_time(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        finding = ocsf["finding_info"]
        assert "created_time_dt" in finding


# ── Status tests ─────────────────────────────────────────────────────


class TestStatus:
    def test_open_maps_to_new(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["status_id"] == 1
        assert ocsf["status"] == "New"

    def test_closed_maps_to_closed(self, normalizer, closed_offense):
        ocsf = normalizer.to_ocsf(closed_offense)
        assert ocsf["status_id"] == 3
        assert ocsf["status"] == "Closed"

    def test_unknown_status_defaults_to_new(self, normalizer):
        offense = {"id": 1, "status": "WEIRD", "start_time": 1710400000000}
        ocsf = normalizer.to_ocsf(offense)
        assert ocsf["status_id"] == 1
        assert ocsf["status"] == "New"


# ── Risk score tests ─────────────────────────────────────────────────


class TestRiskScore:
    def test_magnitude_maps_to_risk_score(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        # magnitude=7 -> score=70
        assert ocsf["risk_score"] == 70
        assert ocsf["risk_level_id"] == 3
        assert ocsf["risk_level"] == "High"

    def test_no_magnitude_no_risk(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "risk_score" not in ocsf


# ── Observable tests ─────────────────────────────────────────────────


class TestObservables:
    def test_source_ip_observable(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert "observables" in ocsf
        obs = ocsf["observables"]
        assert len(obs) == 1
        assert obs[0]["type_id"] == 2
        assert obs[0]["type"] == "IP Address"
        assert obs[0]["value"] == "10.0.0.55"
        assert obs[0]["name"] == "offense_source"

    def test_username_observable(self, normalizer, username_offense):
        ocsf = normalizer.to_ocsf(username_offense)
        obs = ocsf["observables"]
        assert len(obs) == 1
        assert obs[0]["type_id"] == 4
        assert obs[0]["type"] == "User Name"
        assert obs[0]["value"] == "jsmith"

    def test_no_offense_source_no_observables(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "observables" not in ocsf

    def test_ip_auto_detection_for_unknown_type(self, normalizer):
        """When offense_type_str is unknown but value looks like IP, detect it."""
        offense = {
            "id": 5,
            "offense_source": "203.0.113.50",
            "offense_type_str": "Unknown Type",
            "status": "OPEN",
            "start_time": 1710400000000,
        }
        ocsf = normalizer.to_ocsf(offense)
        obs = ocsf["observables"]
        assert obs[0]["type_id"] == 2
        assert obs[0]["type"] == "IP Address"


# ── Raw data tests ───────────────────────────────────────────────────


class TestRawData:
    def test_raw_data_present(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert "raw_data" in ocsf
        parsed = json.loads(ocsf["raw_data"])
        assert parsed["id"] == 42

    def test_raw_data_hash(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        expected_hash = hashlib.sha256(ocsf["raw_data"].encode()).hexdigest()
        assert ocsf["raw_data_hash"] == expected_hash


# ── Unmapped fields tests ────────────────────────────────────────────


class TestUnmapped:
    def test_credibility_and_relevance(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        unmapped = ocsf["unmapped"]
        assert unmapped["qradar_scoring"]["credibility"] == 8
        assert unmapped["qradar_scoring"]["relevance"] == 5

    def test_event_and_flow_counts(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        unmapped = ocsf["unmapped"]
        assert unmapped["event_count"] == 150
        assert unmapped["flow_count"] == 0

    def test_address_ids(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        unmapped = ocsf["unmapped"]
        assert unmapped["source_address_ids"] == [1001, 1002]
        assert unmapped["local_destination_address_ids"] == [2001]

    def test_minimal_offense_no_unmapped(self, normalizer, minimal_offense):
        ocsf = normalizer.to_ocsf(minimal_offense)
        assert "unmapped" not in ocsf


# ── Disposition tests ────────────────────────────────────────────────


class TestDisposition:
    def test_defaults_to_unknown(self, normalizer, source_ip_offense):
        ocsf = normalizer.to_ocsf(source_ip_offense)
        assert ocsf["disposition_id"] == 0
        assert ocsf["disposition"] == "Unknown"
        assert ocsf["action_id"] == 0
        assert ocsf["action"] == "Unknown"


# ── Helper function tests ────────────────────────────────────────────


class TestHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("10.0.0.1", True),
            ("192.168.1.1", True),
            ("not-an-ip", False),
            ("10.0.0", False),
            ("jsmith", False),
            ("", False),
        ],
    )
    def test_looks_like_ip(self, value, expected):
        assert _looks_like_ip(value) == expected
