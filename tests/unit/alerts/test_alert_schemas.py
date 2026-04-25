"""
Unit tests for Alert Pydantic schemas.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from analysi.schemas.alert import (
    AlertAnalysisResponse,
    AlertBase,
    AlertCreate,
    AlertList,
    AlertResponse,
    AlertSeverity,
    AlertStatus,
    AlertUpdate,
    AnalysisProgress,
    AnalysisStatus,
    DispositionResponse,
    StepProgress,
)


@pytest.mark.unit
class TestAlertEnums:
    """Test alert-related enums."""

    def test_alert_severity_values(self):
        """Test AlertSeverity enum has expected values."""
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.HIGH == "high"
        assert AlertSeverity.MEDIUM == "medium"
        assert AlertSeverity.LOW == "low"
        assert AlertSeverity.INFO == "info"

    def test_alert_status_values(self):
        """Test AlertStatus enum has expected values (simplified model)."""
        # New simplified states (5 total)
        assert AlertStatus.NEW == "new"
        assert AlertStatus.IN_PROGRESS == "in_progress"
        assert AlertStatus.COMPLETED == "completed"
        assert AlertStatus.FAILED == "failed"
        assert AlertStatus.CANCELLED == "cancelled"

        # OLD values should NOT exist
        assert not hasattr(AlertStatus, "NOT_ANALYZED")
        assert not hasattr(AlertStatus, "ANALYZING")
        assert not hasattr(AlertStatus, "ANALYZED")
        assert not hasattr(AlertStatus, "PAUSED")  # Paused moved to analysis level

    def test_analysis_status_values(self):
        """Test AnalysisStatus enum has expected values (internal states)."""
        # New internal states (5 total)
        assert AnalysisStatus.RUNNING == "running"
        assert AnalysisStatus.PAUSED_WORKFLOW_BUILDING == "paused"  # simplified
        assert AnalysisStatus.COMPLETED == "completed"
        assert AnalysisStatus.FAILED == "failed"
        assert AnalysisStatus.CANCELLED == "cancelled"

        # OLD values should NOT exist
        assert not hasattr(AnalysisStatus, "PENDING")  # No longer needed


@pytest.mark.unit
class TestAlertSchemas:
    """Test Alert-related Pydantic schemas."""

    def test_alert_base_minimal(self):
        """Test AlertBase with minimal required fields."""
        alert = AlertBase(
            title="Suspicious activity detected",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.HIGH,
            raw_alert='{"test": "data"}',
        )

        assert alert.title == "Suspicious activity detected"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.raw_alert == '{"test": "data"}'

    def test_alert_base_full(self):
        """Test AlertBase with all OCSF fields."""
        now = datetime.now(UTC)

        alert = AlertBase(
            title="Critical breach",
            triggering_event_time=now,
            severity=AlertSeverity.CRITICAL,
            source_vendor="Vendor",
            source_product="Product",
            rule_name="Detection Rule",
            source_event_id="EVT-123",
            finding_info={"title": "Critical breach", "uid": "abc"},
            ocsf_metadata={"product": {"name": "EDR"}, "version": "1.8.0"},
            evidences=[{"src_endpoint": {"ip": "10.0.0.1"}}],
            observables=[{"type_id": 1, "type": "IP Address", "value": "192.168.1.1"}],
            actor={"user": {"name": "user@example.com"}},
            device={"hostname": "workstation-01"},
            cloud={"provider": "aws", "region": "us-east-1"},
            severity_id=5,
            disposition_id=2,
            verdict_id=2,
            action_id=1,
            status_id=1,
            confidence_id=3,
            risk_level_id=4,
            ocsf_time=1700000000000,
            detected_at=now,
            raw_alert='{"full": "alert"}',
        )

        assert alert.source_vendor == "Vendor"
        assert alert.finding_info.uid == "abc"
        assert alert.finding_info.title == "Critical breach"
        assert alert.severity_id == 5
        assert alert.disposition_id == 2
        assert alert.actor.user == {"name": "user@example.com"}
        assert alert.device.hostname == "workstation-01"
        assert alert.cloud.provider == "aws"
        assert alert.cloud.region == "us-east-1"
        assert alert.ocsf_time == 1700000000000

    def test_alert_base_validation_empty_title(self):
        """Test AlertBase validation fails with empty title."""
        with pytest.raises(ValidationError) as exc_info:
            AlertBase(
                title="",  # Empty title should fail
                triggering_event_time=datetime.now(UTC),
                severity=AlertSeverity.HIGH,
                raw_alert='{"test": "data"}',
            )

        errors = exc_info.value.errors()
        assert any("at least 1 character" in str(e) for e in errors)

    def test_alert_base_validation_invalid_severity(self):
        """Test AlertBase validation fails with invalid severity."""
        with pytest.raises(ValidationError) as exc_info:
            AlertBase(
                title="Test alert",
                triggering_event_time=datetime.now(UTC),
                severity="invalid_severity",  # Invalid severity
                raw_alert='{"test": "data"}',
            )

        errors = exc_info.value.errors()
        assert any("severity" in str(e).lower() for e in errors)

    def test_alert_base_ocsf_evidences(self):
        """Test OCSF evidences field accepts structured data."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            evidences=[
                {"src_endpoint": {"ip": "10.0.0.1"}},
                {"dst_endpoint": {"ip": "192.168.1.1"}},
            ],
        )

        assert alert.evidences is not None
        assert len(alert.evidences) == 2
        assert alert.evidences[0].src_endpoint["ip"] == "10.0.0.1"

    def test_ocsf_finding_info_typed(self):
        """FindingInfo is validated as a typed OCSF model."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            finding_info={
                "uid": "f-001",
                "title": "SQL Injection Detected",
                "types": ["Web Attack"],
                "analytic": {"name": "SQL Injection Rule", "type_id": 1},
            },
        )
        from analysi.schemas.ocsf.detection_finding import FindingInfo

        assert isinstance(alert.finding_info, FindingInfo)
        assert alert.finding_info.uid == "f-001"
        assert alert.finding_info.analytic == {
            "name": "SQL Injection Rule",
            "type_id": 1,
        }
        assert alert.finding_info.types == ["Web Attack"]

    def test_ocsf_finding_info_preserves_extra_fields(self):
        """FindingInfo with extra="allow" preserves vendor-specific fields."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            finding_info={
                "uid": "f-002",
                "vendor_custom_field": "preserved",
                "nested_extra": {"key": "value"},
            },
        )
        assert alert.finding_info.vendor_custom_field == "preserved"
        assert alert.finding_info.nested_extra == {"key": "value"}

    def test_ocsf_observable_validates_required_fields(self):
        """Observable requires type_id and value."""
        with pytest.raises(ValidationError) as exc_info:
            AlertBase(
                title="Test",
                triggering_event_time=datetime.now(UTC),
                severity=AlertSeverity.LOW,
                raw_alert="{}",
                observables=[{"type_id": 2}],  # missing value
            )
        assert "value" in str(exc_info.value)

    def test_ocsf_observable_typed(self):
        """Observables are validated as typed OCSF models."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            observables=[
                {
                    "type_id": 2,
                    "value": "1.2.3.4",
                    "type": "IP Address",
                    "name": "src_ip",
                },
                {"type_id": 6, "value": "https://attacker.example", "type": "URL String"},
                {
                    "type_id": 8,
                    "value": "abc123",
                    "reputation": {"score_id": 3, "score": "High"},
                },
            ],
        )
        from analysi.schemas.ocsf.detection_finding import Observable

        assert all(isinstance(o, Observable) for o in alert.observables)
        assert alert.observables[0].type_id == 2
        assert alert.observables[0].value == "1.2.3.4"
        assert alert.observables[2].reputation == {"score_id": 3, "score": "High"}

    def test_ocsf_evidence_preserves_nested_structure(self):
        """Evidence artifacts preserve src_endpoint, process, url, etc. via extra="allow"."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            evidences=[
                {
                    "src_endpoint": {"ip": "203.0.113.50", "port": 54321},
                    "dst_endpoint": {"ip": "10.0.1.100", "port": 443},
                    "process": {
                        "name": "powershell.exe",
                        "cmd_line": "powershell -enc ...",
                        "pid": 2476,
                    },
                    "url": {"url_string": "https://example.com/api", "path": "/api"},
                    "http_request": {
                        "http_method": "POST",
                        "user_agent": "curl/7.68.0",
                    },
                    "http_response": {"code": 200},
                    "connection_info": {"protocol_name": "HTTPS"},
                }
            ],
        )
        ev = alert.evidences[0]
        assert ev.src_endpoint["ip"] == "203.0.113.50"
        assert ev.process["name"] == "powershell.exe"
        assert ev.url["url_string"] == "https://example.com/api"
        assert ev.http_request["http_method"] == "POST"

    def test_ocsf_device_typed(self):
        """Device is validated as a typed OCSF model."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            device={
                "hostname": "ws-001",
                "ip": "10.0.1.50",
                "type_id": 6,
                "os": {"name": "Windows 11"},
            },
        )
        from analysi.schemas.ocsf.detection_finding import OCSFDevice

        assert isinstance(alert.device, OCSFDevice)
        assert alert.device.hostname == "ws-001"
        assert alert.device.os == {"name": "Windows 11"}

    def test_ocsf_metadata_typed(self):
        """OCSF metadata is validated as a typed model."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            ocsf_metadata={
                "version": "1.8.0",
                "product": {"name": "Splunk ES", "vendor_name": "Splunk"},
                "labels": ["source_category:Firewall"],
                "profiles": ["security_control", "host"],
            },
        )
        from analysi.schemas.ocsf.detection_finding import OCSFMetadata

        assert isinstance(alert.ocsf_metadata, OCSFMetadata)
        assert alert.ocsf_metadata.version == "1.8.0"
        assert alert.ocsf_metadata.labels == ["source_category:Firewall"]

    def test_ocsf_vulnerability_typed(self):
        """Vulnerabilities are validated as typed OCSF models."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            vulnerabilities=[
                {"cve": {"uid": "CVE-2024-1234"}, "severity": "Critical"},
                {"cve": {"uid": "CVE-2024-5678", "cvss": [{"base_score": 9.8}]}},
            ],
        )
        from analysi.schemas.ocsf.detection_finding import VulnerabilityDetail

        assert all(isinstance(v, VulnerabilityDetail) for v in alert.vulnerabilities)
        assert alert.vulnerabilities[0].cve["uid"] == "CVE-2024-1234"
        assert alert.vulnerabilities[0].severity == "Critical"

    def test_ocsf_empty_jsonb_fields_accepted(self):
        """Empty dicts/lists for OCSF fields are accepted (backward compat)."""
        alert = AlertBase(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            finding_info={},
            ocsf_metadata={},
            evidences=[],
            observables=[],
        )
        assert alert.finding_info is not None
        assert alert.evidences == []

    def test_ocsf_full_normalizer_output(self):
        """A realistic normalizer output dict passes typed AlertCreate validation."""
        alert = AlertCreate(
            title="SQL Injection Payload Detected",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            raw_data='{"raw": "event"}',
            source_vendor="Splunk",
            source_product="Enterprise Security",
            rule_name="SQL Injection Payload Detected",
            finding_info={
                "uid": str(uuid4()),
                "title": "SQL Injection Detected",
                "types": ["Web Attack"],
                "analytic": {
                    "name": "SQL Injection Rule",
                    "type_id": 1,
                    "type": "Rule",
                },
                "created_time_dt": "2024-01-01T00:00:00Z",
            },
            ocsf_metadata={
                "version": "1.8.0",
                "product": {"name": "Enterprise Security", "vendor_name": "Splunk"},
                "labels": ["source_category:WAF"],
            },
            observables=[
                {
                    "type_id": 2,
                    "value": "91.234.56.17",
                    "name": "src_ip",
                    "type": "IP Address",
                },
                {
                    "type_id": 6,
                    "value": "https://target/search?q=OR+1=1",
                    "name": "url",
                    "type": "URL String",
                },
            ],
            evidences=[
                {
                    "src_endpoint": {"ip": "91.234.56.17", "port": 48575},
                    "dst_endpoint": {"ip": "10.10.20.18", "port": 443},
                    "url": {
                        "url_string": "https://target/search?q=OR+1=1",
                        "path": "/search",
                    },
                    "http_request": {"http_method": "GET", "user_agent": "Mozilla/5.0"},
                    "http_response": {"code": 500},
                }
            ],
            device={"hostname": "WebServer1001", "ip": "10.10.20.18", "type_id": 6},
            severity_id=4,
            disposition_id=1,
        )
        assert alert.finding_info.analytic["name"] == "SQL Injection Rule"
        assert len(alert.observables) == 2
        assert alert.evidences[0].http_response["code"] == 500
        assert alert.device.hostname == "WebServer1001"

    def test_alert_create_schema(self):
        """Test AlertCreate schema."""
        alert = AlertCreate(
            title="New alert",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.MEDIUM,
            raw_alert='{"new": "alert"}',
            human_readable_id="AID-123",
        )

        assert alert.human_readable_id == "AID-123"

    def test_alert_create_validate_human_readable_id(self):
        """Test human_readable_id validation."""
        alert = AlertCreate(
            title="Test",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="{}",
            human_readable_id="CUSTOM-ID",
        )

        # Validator is stubbed, should pass but not modify
        assert alert.human_readable_id == "CUSTOM-ID"

    def test_alert_update_schema(self):
        """Test AlertUpdate schema."""
        update = AlertUpdate(
            analysis_status=AlertStatus.IN_PROGRESS, current_analysis_id=uuid4()
        )

        assert update.analysis_status == AlertStatus.IN_PROGRESS
        assert update.current_analysis_id is not None

    def test_alert_update_partial(self):
        """Test AlertUpdate with partial fields."""
        update = AlertUpdate(analysis_status=AlertStatus.COMPLETED)

        assert update.analysis_status == AlertStatus.COMPLETED
        assert update.current_analysis_id is None

    def test_alert_update_forbids_extra(self):
        """Test AlertUpdate forbids extra fields."""
        with pytest.raises(ValidationError):
            AlertUpdate(
                analysis_status=AlertStatus.IN_PROGRESS,
                title="Cannot update title",  # Should not be allowed
            )

    def test_alert_response_schema(self):
        """Test AlertResponse schema."""
        now = datetime.now(UTC)
        alert_id = uuid4()

        response = AlertResponse(
            alert_id=alert_id,
            tenant_id="test-tenant",
            human_readable_id="AID-1",
            title="Response test",
            triggering_event_time=now,
            severity=AlertSeverity.HIGH,
            raw_data="{}",
            analysis_status=AlertStatus.NEW,
            raw_data_hash="hash123",
            ingested_at=now,
            created_at=now,
            updated_at=now,
        )

        assert response.alert_id == alert_id
        assert response.tenant_id == "test-tenant"
        assert response.human_readable_id == "AID-1"
        assert response.analysis_status == AlertStatus.NEW

    def test_alert_list_schema(self):
        """Test AlertList schema."""
        alert_list = AlertList(alerts=[], total=0, limit=20, offset=0)

        assert alert_list.alerts == []
        assert alert_list.total == 0
        assert alert_list.limit == 20


@pytest.mark.unit
class TestAnalysisSchemas:
    """Test analysis-related schemas."""

    def test_step_progress_schema(self):
        """Test StepProgress schema."""
        progress = StepProgress(
            completed=True,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            retries=2,
            error=None,
        )

        assert progress.completed is True
        assert progress.retries == 2

    def test_step_progress_defaults(self):
        """Test StepProgress default values."""
        progress = StepProgress()

        assert progress.completed is False
        assert progress.started_at is None
        assert progress.completed_at is None
        assert progress.retries == 0
        assert progress.error is None

    def test_alert_analysis_response(self):
        """Test AlertAnalysisResponse schema."""
        analysis_id = uuid4()
        alert_id = uuid4()
        now = datetime.now(UTC)

        analysis = AlertAnalysisResponse(
            id=analysis_id,
            alert_id=alert_id,
            tenant_id="test-tenant",
            status=AnalysisStatus.RUNNING,
            started_at=now,
            current_step="workflow_builder",
            steps_progress={"pre_triage": {"completed": True}},
            confidence=75,
            short_summary="Analyzing...",
            created_at=now,
            updated_at=now,
        )

        assert analysis.id == analysis_id
        assert analysis.status == AnalysisStatus.RUNNING
        assert analysis.confidence == 75

    def test_alert_analysis_confidence_validation(self):
        """Test confidence field validation (0-100)."""
        with pytest.raises(ValidationError):
            AlertAnalysisResponse(
                id=uuid4(),
                alert_id=uuid4(),
                tenant_id="test",
                status=AnalysisStatus.COMPLETED,
                confidence=101,  # Should fail (>100)
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    def test_analysis_progress_schema(self):
        """Test AnalysisProgress schema."""
        progress = AnalysisProgress(
            analysis_id=uuid4(),
            current_step="workflow_execution",
            completed_steps=2,
            total_steps=4,
            status=AnalysisStatus.RUNNING,
            steps_detail={
                "pre_triage": StepProgress(completed=True),
                "workflow_builder": StepProgress(completed=True),
                "workflow_execution": StepProgress(completed=False),
            },
        )

        assert progress.completed_steps == 2
        assert progress.total_steps == 4
        assert progress.status == AnalysisStatus.RUNNING


@pytest.mark.unit
class TestDispositionSchema:
    """Test Disposition schema."""

    def test_disposition_response(self):
        """Test DispositionResponse schema."""
        disposition = DispositionResponse(
            disposition_id=uuid4(),
            category="true_positive",
            subcategory="confirmed_breach",
            display_name="Confirmed Breach",
            color_hex="#FF0000",
            color_name="red",
            priority_score=1,
            requires_escalation=True,
        )

        assert disposition.category == "true_positive"
        assert disposition.subcategory == "confirmed_breach"
        assert disposition.color_hex == "#FF0000"
        assert disposition.priority_score == 1
        assert disposition.requires_escalation is True
