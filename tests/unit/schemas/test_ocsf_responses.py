"""Unit tests for OCSF API response schemas — Project Skaros.

Tests OCSFAlertResponse schema and alert_model_to_ocsf_response()
using OCSF model columns directly (no NAS translation).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from analysi.schemas.ocsf.responses import (
    OCSFAlertResponse,
    alert_model_to_ocsf_response,
)


def _make_ocsf_alert_model(**overrides) -> SimpleNamespace:
    """Build a fake Alert model with OCSF columns."""
    defaults = {
        "id": uuid4(),
        "human_readable_id": "AID-42",
        "analysis_status": "new",
        "title": "SQL Injection Detected",
        "severity": "high",
        "severity_id": 4,
        "ocsf_time": 1718444400000,
        "raw_data": '{"rule": "sqli"}',
        "raw_data_hash": "abc123",
        "raw_data_hash_algorithm": "SHA-256",
        "finding_info": {"title": "SQL Injection Detected", "uid": "f-001"},
        "ocsf_metadata": {
            "version": "1.8.0",
            "product": {"vendor_name": "Splunk", "name": "Enterprise Security"},
        },
        "observables": [{"type_id": 2, "value": "91.234.56.17"}],
        "evidences": [{"src_endpoint": {"ip": "91.234.56.17"}}],
        "osint": None,
        "actor": {"user": {"name": "jdoe"}},
        "device": {"hostname": "WebServer1001"},
        "cloud": None,
        "vulnerabilities": None,
        "unmapped": None,
        "disposition_id": 2,
        "verdict_id": None,
        "action_id": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestOCSFAlertResponse:
    def test_construct_with_required_fields(self):
        resp = OCSFAlertResponse(
            ocsf={"class_uid": 2004, "severity_id": 4},
            alert_id="abc-123",
            human_readable_id="AID-1",
            analysis_status="new",
        )
        assert resp.ocsf["class_uid"] == 2004
        assert resp.alert_id == "abc-123"
        assert resp.enrichments is None

    def test_construct_with_enrichments(self):
        resp = OCSFAlertResponse(
            ocsf={"class_uid": 2004},
            alert_id="abc-123",
            human_readable_id="AID-1",
            analysis_status="completed",
            enrichments={"vt_score": 5},
        )
        assert resp.enrichments == {"vt_score": 5}

    def test_missing_required_field_raises(self):
        with pytest.raises(ValueError):
            OCSFAlertResponse(
                ocsf={"class_uid": 2004},
                human_readable_id="AID-1",
                analysis_status="new",
            )


class TestAlertModelToOcsfResponse:
    def test_basic_conversion(self):
        model = _make_ocsf_alert_model()
        resp = alert_model_to_ocsf_response(model)

        assert resp.alert_id == str(model.id)
        assert resp.human_readable_id == "AID-42"
        assert resp.analysis_status == "new"

        ocsf = resp.ocsf
        assert ocsf["class_uid"] == 2004
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"
        assert ocsf["message"] == "SQL Injection Detected"
        assert ocsf["time"] == 1718444400000

    def test_finding_info_populated(self):
        model = _make_ocsf_alert_model()
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["finding_info"]["title"] == "SQL Injection Detected"

    def test_metadata_populated(self):
        model = _make_ocsf_alert_model()
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["metadata"]["version"] == "1.8.0"

    def test_observables_included(self):
        model = _make_ocsf_alert_model()
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["observables"][0]["value"] == "91.234.56.17"

    def test_disposition_included(self):
        model = _make_ocsf_alert_model(disposition_id=2)
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["disposition_id"] == 2

    def test_disposition_excluded_when_none(self):
        model = _make_ocsf_alert_model(disposition_id=None)
        resp = alert_model_to_ocsf_response(model)
        assert "disposition_id" not in resp.ocsf

    def test_device_included(self):
        model = _make_ocsf_alert_model(device={"hostname": "srv01"})
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["device"] == {"hostname": "srv01"}

    def test_raw_data_hash_included(self):
        model = _make_ocsf_alert_model(raw_data_hash="abc123")
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["raw_data_hash"]["value"] == "abc123"
        assert resp.ocsf["raw_data_hash"]["algorithm"] == "SHA-256"

    def test_raw_data_preserved(self):
        model = _make_ocsf_alert_model()
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["raw_data"] == '{"rule": "sqli"}'

    def test_analysis_status_defaults_to_new(self):
        model = _make_ocsf_alert_model(analysis_status=None)
        resp = alert_model_to_ocsf_response(model)
        assert resp.analysis_status == "new"

    def test_minimal_alert(self):
        model = _make_ocsf_alert_model(
            observables=None,
            evidences=None,
            actor=None,
            device=None,
            cloud=None,
            osint=None,
            vulnerabilities=None,
            unmapped=None,
            disposition_id=None,
            verdict_id=None,
            action_id=None,
            raw_data_hash=None,
        )
        resp = alert_model_to_ocsf_response(model)
        assert resp.ocsf["class_uid"] == 2004
        assert "observables" not in resp.ocsf
        assert "disposition_id" not in resp.ocsf
