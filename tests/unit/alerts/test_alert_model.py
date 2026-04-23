"""
Unit tests for Alert, AlertAnalysis, and Disposition models.
These tests don't require a database - they test model structure only.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysi.models.alert import Alert, AlertAnalysis, Disposition


@pytest.mark.unit
class TestAlertModel:
    """Test Alert model structure and validation."""

    def test_alert_model_attributes(self):
        """Test that Alert model has expected attributes."""
        # Core identifiers
        assert hasattr(Alert, "id")
        assert hasattr(Alert, "tenant_id")
        assert hasattr(Alert, "human_readable_id")

        # Source alert information
        assert hasattr(Alert, "title")
        assert hasattr(Alert, "triggering_event_time")
        assert hasattr(Alert, "source_vendor")
        assert hasattr(Alert, "source_product")
        assert hasattr(Alert, "rule_name")
        assert hasattr(Alert, "severity")

        # OCSF structured JSONB fields
        assert hasattr(Alert, "finding_info")
        assert hasattr(Alert, "ocsf_metadata")
        assert hasattr(Alert, "evidences")
        assert hasattr(Alert, "observables")
        assert hasattr(Alert, "actor")
        assert hasattr(Alert, "device")
        assert hasattr(Alert, "cloud")
        assert hasattr(Alert, "vulnerabilities")
        assert hasattr(Alert, "unmapped")

        # OCSF scalar enum columns
        assert hasattr(Alert, "severity_id")
        assert hasattr(Alert, "disposition_id")

        # Other fields
        assert hasattr(Alert, "detected_at")
        assert hasattr(Alert, "ingested_at")
        assert hasattr(Alert, "raw_data")
        assert hasattr(Alert, "raw_data_hash")
        assert hasattr(Alert, "current_analysis_id")
        assert hasattr(Alert, "analysis_status")
        assert hasattr(Alert, "created_at")
        assert hasattr(Alert, "updated_at")

        # Relationships
        assert hasattr(Alert, "analyses")

    def test_alert_table_name(self):
        """Test that Alert has correct table name."""
        assert Alert.__tablename__ == "alerts"

    def test_alert_initialization_minimal(self):
        """Test Alert model initialization with minimal fields."""
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-1",
            title="Suspicious login attempt",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            severity_id=4,
            raw_data='{"test": "data"}',
            raw_data_hash="abc123hash",
            finding_info={},
            ocsf_metadata={},
        )

        assert alert.tenant_id == "test-tenant"
        assert alert.human_readable_id == "AID-1"
        assert alert.title == "Suspicious login attempt"
        assert alert.severity == "high"
        assert alert.raw_data == '{"test": "data"}'
        assert alert.raw_data_hash == "abc123hash"

    def test_alert_initialization_full(self):
        """Test Alert model initialization with all fields."""
        now = datetime.now(UTC)
        analysis_id = uuid4()

        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-2",
            title="Critical security breach",
            triggering_event_time=now,
            source_vendor="CrowdStrike",
            source_product="Falcon",
            rule_name="Malware Detection Rule",
            severity="critical",
            severity_id=5,
            finding_info={"title": "Malware Detection"},
            ocsf_metadata={"product": {"name": "Falcon"}},
            observables=[{"type": "ip", "value": "192.168.1.100"}],
            actor={"user": {"name": "user@example.com"}},
            detected_at=now,
            raw_data='{"full": "alert"}',
            raw_data_hash="xyz789hash",
            current_analysis_id=analysis_id,
            analysis_status="in_progress",
        )

        assert alert.source_vendor == "CrowdStrike"
        assert alert.source_product == "Falcon"
        assert alert.severity == "critical"
        assert alert.severity_id == 5
        assert alert.finding_info["title"] == "Malware Detection"
        assert alert.observables[0]["value"] == "192.168.1.100"
        assert alert.actor["user"]["name"] == "user@example.com"
        assert alert.analysis_status == "in_progress"

    def test_alert_generate_human_readable_id(self):
        """Test human-readable ID generation."""
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="temp",
            title="Test alert",
            triggering_event_time=datetime.now(UTC),
            severity="medium",
            severity_id=3,
            raw_data="{}",
            raw_data_hash="hash",
            finding_info={},
            ocsf_metadata={},
        )

        # Test the implemented method
        result = alert.generate_human_readable_id(1)
        assert result == "AID-1"

        result = alert.generate_human_readable_id(42)
        assert result == "AID-42"

    def test_alert_raw_data_hash_field(self):
        """Test raw_data_hash field stores deduplication hash."""
        now = datetime.now(UTC)
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-1",
            title="Test alert",
            triggering_event_time=now,
            severity="low",
            severity_id=2,
            raw_data="{}",
            raw_data_hash="abc123def456",
            raw_data_hash_algorithm="SHA-256",
            finding_info={},
            ocsf_metadata={},
        )

        assert alert.raw_data_hash == "abc123def456"
        assert alert.raw_data_hash_algorithm == "SHA-256"

    def test_alert_table_args(self):
        """Test Alert table has partitioning and constraint arguments."""
        table_args = Alert.__table_args__

        # Check for unique constraints and indexes
        has_tenant_human_readable_constraint = False
        has_raw_data_hash_index = False
        has_partition_config = False

        for arg in table_args:
            if hasattr(arg, "name"):
                if hasattr(arg, "columns"):
                    col_names = [col.name for col in arg.columns]
                    if "tenant_id" in col_names and "human_readable_id" in col_names:
                        has_tenant_human_readable_constraint = True
                    if "raw_data_hash" in col_names:
                        has_raw_data_hash_index = True
            elif isinstance(arg, dict) and "postgresql_partition_by" in arg:
                has_partition_config = True
                assert "ingested_at" in arg["postgresql_partition_by"]

        assert has_tenant_human_readable_constraint
        assert has_raw_data_hash_index
        assert has_partition_config


@pytest.mark.unit
class TestAlertAnalysisModel:
    """Test AlertAnalysis model structure."""

    def test_alert_analysis_attributes(self):
        """Test that AlertAnalysis model has expected attributes."""
        assert hasattr(AlertAnalysis, "id")
        assert hasattr(AlertAnalysis, "alert_id")
        assert hasattr(AlertAnalysis, "tenant_id")
        assert hasattr(AlertAnalysis, "status")
        assert hasattr(AlertAnalysis, "started_at")
        assert hasattr(AlertAnalysis, "completed_at")
        assert hasattr(AlertAnalysis, "current_step")
        assert hasattr(AlertAnalysis, "steps_progress")
        assert hasattr(AlertAnalysis, "disposition_id")
        assert hasattr(AlertAnalysis, "confidence")
        assert hasattr(AlertAnalysis, "short_summary")
        assert hasattr(AlertAnalysis, "long_summary")
        assert hasattr(AlertAnalysis, "workflow_id")
        assert hasattr(AlertAnalysis, "workflow_run_id")
        assert hasattr(AlertAnalysis, "created_at")
        assert hasattr(AlertAnalysis, "updated_at")

        # Relationships
        assert hasattr(AlertAnalysis, "alert")
        assert hasattr(AlertAnalysis, "disposition")

    def test_alert_analysis_table_name(self):
        """Test that AlertAnalysis has correct table name."""
        assert AlertAnalysis.__tablename__ == "alert_analyses"

    def test_alert_analysis_initialization(self):
        """Test AlertAnalysis initialization."""
        alert_id = uuid4()
        disposition_id = uuid4()
        workflow_id = uuid4()
        workflow_run_id = uuid4()

        analysis = AlertAnalysis(
            alert_id=alert_id,
            tenant_id="test-tenant",
            status="running",
            current_step="pre_triage",
            steps_progress={"pre_triage": {"completed": True}},
            disposition_id=disposition_id,
            confidence=85,
            short_summary="Likely false positive",
            long_summary="Detailed analysis shows...",
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
        )

        assert analysis.alert_id == alert_id
        assert analysis.tenant_id == "test-tenant"
        assert analysis.status == "running"
        assert analysis.current_step == "pre_triage"
        assert analysis.steps_progress["pre_triage"]["completed"] is True
        assert analysis.confidence == 85

    def test_alert_analysis_update_step_progress(self):
        """Test updating step progress."""
        analysis = AlertAnalysis(alert_id=uuid4(), tenant_id="test-tenant")

        # Test the implemented method - it modifies the object
        analysis.update_step_progress("workflow_builder", True)

        # Check that steps_progress was updated
        assert "workflow_builder" in analysis.steps_progress
        assert analysis.steps_progress["workflow_builder"]["completed"] is True

        # Test with error
        analysis.update_step_progress("workflow_builder", False, "Test error")
        assert analysis.steps_progress["workflow_builder"]["error"] == "Test error"
        assert analysis.steps_progress["workflow_builder"]["retries"] == 1

    def test_alert_analysis_mark_completed(self):
        """Test marking analysis as completed."""
        analysis = AlertAnalysis(
            alert_id=uuid4(),
            tenant_id="test-tenant",
            status="running",
            current_step="workflow_execution",
        )

        # Test the implemented method - it modifies the object
        analysis.mark_completed()

        # Check that status and timestamps were updated
        assert analysis.status == "completed"
        assert analysis.completed_at is not None
        assert analysis.current_step is None


@pytest.mark.unit
class TestDispositionModel:
    """Test Disposition model structure."""

    def test_disposition_attributes(self):
        """Test that Disposition model has expected attributes."""
        assert hasattr(Disposition, "id")
        assert hasattr(Disposition, "category")
        assert hasattr(Disposition, "subcategory")
        assert hasattr(Disposition, "display_name")
        assert hasattr(Disposition, "color_hex")
        assert hasattr(Disposition, "color_name")
        assert hasattr(Disposition, "priority_score")
        assert hasattr(Disposition, "description")
        assert hasattr(Disposition, "requires_escalation")
        assert hasattr(Disposition, "is_system")
        assert hasattr(Disposition, "created_at")
        assert hasattr(Disposition, "updated_at")

    def test_disposition_table_name(self):
        """Test that Disposition has correct table name."""
        assert Disposition.__tablename__ == "dispositions"

    def test_disposition_initialization(self):
        """Test Disposition initialization."""
        disposition = Disposition(
            category="true_positive",
            subcategory="confirmed_breach",
            display_name="Confirmed Security Breach",
            color_hex="#FF0000",
            color_name="red",
            priority_score=1,
            description="Confirmed security breach requiring immediate action",
            requires_escalation=True,
            is_system=True,
        )

        assert disposition.category == "true_positive"
        assert disposition.subcategory == "confirmed_breach"
        assert disposition.display_name == "Confirmed Security Breach"
        assert disposition.color_hex == "#FF0000"
        assert disposition.color_name == "red"
        assert disposition.priority_score == 1
        assert disposition.requires_escalation is True
        assert disposition.is_system is True

    def test_disposition_to_dict(self):
        """Test converting disposition to dictionary."""
        disposition = Disposition(
            category="false_positive",
            subcategory="benign_activity",
            display_name="Benign Activity",
            color_hex="#00FF00",
            color_name="green",
            priority_score=10,
        )

        # Test the implemented method
        result = disposition.to_dict()
        assert isinstance(result, dict)
        assert result["category"] == "false_positive"
        assert result["subcategory"] == "benign_activity"
        assert result["display_name"] == "Benign Activity"
        assert result["color_hex"] == "#00FF00"
        assert result["color_name"] == "green"
        assert result["priority_score"] == 10

    def test_disposition_unique_constraint(self):
        """Test Disposition has unique constraint on category/subcategory."""
        table_args = Disposition.__table_args__

        has_unique_constraint = False
        for arg in table_args:
            if hasattr(arg, "columns"):
                col_names = [col.name for col in arg.columns]
                if "category" in col_names and "subcategory" in col_names:
                    has_unique_constraint = True
                    break

        assert has_unique_constraint
