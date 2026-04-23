"""Alert model OCSF column contract tests.

Verifies the Alert SQLAlchemy model has the correct OCSF Detection
Finding v1.8.0 columns and that legacy NAS columns are absent.
"""

from typing import ClassVar

from sqlalchemy import BigInteger, SmallInteger, inspect

from analysi.models.alert import Alert, AlertAnalysis, Disposition

# ── Helpers ─────────────────────────────────────────────────────────────────


def _alert_column_names() -> set[str]:
    """Return the set of column names on the Alert model."""
    mapper = inspect(Alert)
    return {col.key for col in mapper.columns}


def _alert_analysis_column_names() -> set[str]:
    """Return the set of column names on the AlertAnalysis model."""
    mapper = inspect(AlertAnalysis)
    return {col.key for col in mapper.columns}


def _disposition_column_names() -> set[str]:
    """Return the set of column names on the Disposition model."""
    mapper = inspect(Disposition)
    return {col.key for col in mapper.columns}


# ── 1. OCSF columns exist on Alert ─────────────────────────────────────────


class TestOCSFColumnsExist:
    """Alert model has all new OCSF columns from V113."""

    OCSF_JSONB_COLUMNS: ClassVar[set[str]] = {
        "finding_info",
        "ocsf_metadata",
        "evidences",
        "observables",
        "osint",
        "actor",
        "device",
        "cloud",
        "vulnerabilities",
        "unmapped",
    }

    OCSF_SCALAR_COLUMNS: ClassVar[set[str]] = {
        "severity_id",
        "disposition_id",
        "verdict_id",
        "action_id",
        "status_id",
        "confidence_id",
        "risk_level_id",
    }

    OCSF_TIME_DEDUP_COLUMNS: ClassVar[set[str]] = {
        "ocsf_time",
        "raw_data_hash",
        "raw_data_hash_algorithm",
    }

    def test_ocsf_jsonb_columns_present(self):
        cols = _alert_column_names()
        for col in self.OCSF_JSONB_COLUMNS:
            assert col in cols, f"OCSF JSONB column '{col}' missing from Alert model"

    def test_ocsf_scalar_columns_present(self):
        cols = _alert_column_names()
        for col in self.OCSF_SCALAR_COLUMNS:
            assert col in cols, f"OCSF scalar column '{col}' missing from Alert model"

    def test_ocsf_time_dedup_columns_present(self):
        cols = _alert_column_names()
        for col in self.OCSF_TIME_DEDUP_COLUMNS:
            assert col in cols, (
                f"OCSF time/dedup column '{col}' missing from Alert model"
            )

    def test_raw_data_column_present(self):
        """raw_alert was renamed to raw_data in V113."""
        cols = _alert_column_names()
        assert "raw_data" in cols, "raw_data column (renamed from raw_alert) missing"

    def test_severity_id_is_smallinteger(self):
        mapper = inspect(Alert)
        col = mapper.columns["severity_id"]
        assert isinstance(col.type, SmallInteger)

    def test_ocsf_time_is_biginteger(self):
        mapper = inspect(Alert)
        col = mapper.columns["ocsf_time"]
        assert isinstance(col.type, BigInteger)

    def test_finding_info_not_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["finding_info"]
        assert col.nullable is False

    def test_ocsf_metadata_not_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["ocsf_metadata"]
        assert col.nullable is False

    def test_severity_id_not_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["severity_id"]
        assert col.nullable is False

    def test_status_id_not_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["status_id"]
        assert col.nullable is False

    def test_raw_data_hash_not_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["raw_data_hash"]
        assert col.nullable is False

    def test_evidences_is_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["evidences"]
        assert col.nullable is True

    def test_observables_is_nullable(self):
        mapper = inspect(Alert)
        col = mapper.columns["observables"]
        assert col.nullable is True


# ── 2. NAS-only columns are gone ───────────────────────────────────────────


class TestNASColumnsRemoved:
    """NAS-specific columns have been dropped from the Alert model."""

    NAS_ONLY_COLUMNS: ClassVar[set[str]] = {
        "primary_risk_entity_value",
        "primary_risk_entity_type",
        "primary_ioc_value",
        "primary_ioc_type",
        "device_action",
        "alert_type",
        "source_category",
        "network_info",
        "web_info",
        "process_info",
        "file_info",
        "email_info",
        "cloud_info",
        "cve_info",
        "other_activities",
        "risk_entities",
        "iocs",
        "content_hash",
        "raw_alert",  # renamed to raw_data
    }

    def test_nas_columns_absent(self):
        cols = _alert_column_names()
        for col in self.NAS_ONLY_COLUMNS:
            assert col not in cols, (
                f"NAS column '{col}' should have been removed but is still on Alert"
            )

    def test_calculate_content_hash_removed(self):
        """The calculate_content_hash() method should no longer exist."""
        assert not hasattr(Alert, "calculate_content_hash"), (
            "calculate_content_hash() should be removed — dedup uses raw_data_hash now"
        )


# ── 3. Shared columns kept ─────────────────────────────────────────────────


class TestSharedColumnsKept:
    """Columns that survive the NAS->OCSF migration are still present."""

    SHARED_COLUMNS: ClassVar[set[str]] = {
        "id",
        "tenant_id",
        "human_readable_id",
        "title",
        "severity",
        "source_vendor",
        "source_product",
        "rule_name",
        "source_event_id",
        "detected_at",
        "ingested_at",
        "triggering_event_time",
        "current_analysis_id",
        "analysis_status",
        "current_disposition_category",
        "current_disposition_subcategory",
        "current_disposition_display_name",
        "current_disposition_confidence",
        "created_at",
        "updated_at",
    }

    def test_shared_columns_present(self):
        cols = _alert_column_names()
        for col in self.SHARED_COLUMNS:
            assert col in cols, (
                f"Shared column '{col}' missing — should survive migration"
            )

    def test_alert_id_property(self):
        """The alert_id property should still exist for backward compat."""
        assert hasattr(Alert, "alert_id"), "alert_id property missing"

    def test_generate_human_readable_id(self):
        """Static helper still works."""
        assert Alert.generate_human_readable_id(42) == "AID-42"

    def test_severity_column_is_string(self):
        """severity (string caption) stays alongside new severity_id."""
        mapper = inspect(Alert)
        col = mapper.columns["severity"]
        assert col.nullable is False

    def test_analyses_relationship_exists(self):
        """Alert.analyses relationship still present."""
        mapper = inspect(Alert)
        assert "analyses" in mapper.relationships


# ── 4. AlertAnalysis unchanged ──────────────────────────────────────────────


class TestAlertAnalysisUnchanged:
    """AlertAnalysis model columns are stable."""

    EXPECTED_COLUMNS: ClassVar[set[str]] = {
        "id",
        "alert_id",
        "tenant_id",
        "status",
        "error_message",
        "started_at",
        "completed_at",
        "current_step",
        "steps_progress",
        "disposition_id",
        "confidence",
        "short_summary",
        "long_summary",
        "workflow_id",
        "workflow_run_id",
        "workflow_gen_retry_count",
        "workflow_gen_last_failure_at",
        "job_tracking",
        "created_at",
        "updated_at",
    }

    def test_alert_analysis_columns_exact(self):
        cols = _alert_analysis_column_names()
        assert cols == self.EXPECTED_COLUMNS, (
            f"AlertAnalysis columns changed.\n"
            f"  Added: {cols - self.EXPECTED_COLUMNS}\n"
            f"  Removed: {self.EXPECTED_COLUMNS - cols}"
        )

    def test_alert_analysis_has_mark_completed(self):
        assert hasattr(AlertAnalysis, "mark_completed")

    def test_alert_analysis_has_update_step_progress(self):
        assert hasattr(AlertAnalysis, "update_step_progress")

    def test_alert_analysis_relationships(self):
        mapper = inspect(AlertAnalysis)
        rel_names = set(mapper.relationships.keys())
        assert "alert" in rel_names
        assert "disposition" in rel_names


# ── 5. Disposition unchanged ────────────────────────────────────────────────


class TestDispositionUnchanged:
    """Disposition model columns are stable."""

    EXPECTED_COLUMNS: ClassVar[set[str]] = {
        "id",
        "category",
        "subcategory",
        "display_name",
        "color_hex",
        "color_name",
        "priority_score",
        "description",
        "requires_escalation",
        "is_system",
        "created_at",
        "updated_at",
    }

    def test_disposition_columns_exact(self):
        cols = _disposition_column_names()
        assert cols == self.EXPECTED_COLUMNS, (
            f"Disposition columns changed.\n"
            f"  Added: {cols - self.EXPECTED_COLUMNS}\n"
            f"  Removed: {self.EXPECTED_COLUMNS - cols}"
        )

    def test_disposition_has_to_dict(self):
        assert hasattr(Disposition, "to_dict")


# ── 6. Complete Alert column inventory ──────────────────────────────────────


class TestAlertColumnInventory:
    """Exact column set for the Alert model (OCSF schema)."""

    EXPECTED_COLUMNS: ClassVar[set[str]] = {
        # Core identifiers
        "id",
        "tenant_id",
        "human_readable_id",
        # Source info (immutable)
        "title",
        "triggering_event_time",
        "source_vendor",
        "source_product",
        "rule_name",
        "severity",
        "source_event_id",
        # OCSF JSONB
        "finding_info",
        "ocsf_metadata",
        "evidences",
        "observables",
        "osint",
        "actor",
        "device",
        "cloud",
        "vulnerabilities",
        "unmapped",
        # OCSF scalars
        "severity_id",
        "disposition_id",
        "verdict_id",
        "action_id",
        "status_id",
        "confidence_id",
        "risk_level_id",
        # OCSF time + dedup
        "ocsf_time",
        "raw_data_hash",
        "raw_data_hash_algorithm",
        # Timestamps
        "detected_at",
        "ingested_at",
        # Raw data
        "raw_data",
        # Analysis
        "current_analysis_id",
        "analysis_status",
        # Disposition (denormalized)
        "current_disposition_category",
        "current_disposition_subcategory",
        "current_disposition_display_name",
        "current_disposition_confidence",
        # Metadata
        "created_at",
        "updated_at",
    }

    def test_alert_columns_exact(self):
        cols = _alert_column_names()
        assert cols == self.EXPECTED_COLUMNS, (
            f"Alert column inventory mismatch.\n"
            f"  Unexpected: {cols - self.EXPECTED_COLUMNS}\n"
            f"  Missing: {self.EXPECTED_COLUMNS - cols}"
        )
