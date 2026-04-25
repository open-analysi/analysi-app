"""OCSF schema contract tests.

Permanent contract tests that lock down the OCSF Detection Finding v1.8.0
schema as implemented in the Alert model, response schemas, Cy helpers,
and enrichment pipeline.

Categories:
  1. Alert model OCSF column inventory
  2. Enrichment pipeline contract (dict-keyed pattern preserved)
  3. OCSF enum value ranges
  4. OCSF response schema field inventory
  5. Cy OCSF helper inventory

Future cleanup (tracked, not yet done):
  - src/analysi/schemas/ocsf/translator.py — translator from NAS to OCSF
  - src/alert_normalizer/base.py — NAS normalizer (wrapped by base_ocsf.py)
  - src/alert_normalizer/splunk.py — NAS normalizer (wrapped by splunk_ocsf.py)
"""

from typing import ClassVar

import pytest
from sqlalchemy import BigInteger, SmallInteger, inspect

from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.schemas.ocsf.responses import OCSFAlertResponse
from analysi.services.cy_enrichment_functions import CyEnrichmentFunctions
from analysi.services.cy_ocsf_helpers import create_cy_ocsf_helpers

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


# ═══════════════════════════════════════════════════════════════════════════
# 1. ALERT MODEL OCSF COLUMN INVENTORY
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertOCSFColumnInventory:
    """Exact column set for the Alert model after OCSF migration.

    Any addition, removal, or rename must cause a test failure so the
    change is explicitly acknowledged.
    """

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
        """Alert model columns must match the OCSF column inventory exactly."""
        cols = _alert_column_names()
        assert cols == self.EXPECTED_COLUMNS, (
            f"Alert column inventory mismatch.\n"
            f"  Unexpected: {cols - self.EXPECTED_COLUMNS}\n"
            f"  Missing: {self.EXPECTED_COLUMNS - cols}"
        )

    def test_ocsf_jsonb_columns_present(self):
        """OCSF JSONB columns must be on the Alert model."""
        cols = _alert_column_names()
        ocsf_jsonb = {
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
        for col in ocsf_jsonb:
            assert col in cols, f"OCSF JSONB column '{col}' missing from Alert model"

    def test_ocsf_scalar_columns_present(self):
        """OCSF integer enum columns must be on the Alert model."""
        cols = _alert_column_names()
        ocsf_scalars = {
            "severity_id",
            "disposition_id",
            "verdict_id",
            "action_id",
            "status_id",
            "confidence_id",
            "risk_level_id",
        }
        for col in ocsf_scalars:
            assert col in cols, f"OCSF scalar column '{col}' missing from Alert model"

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

    def test_nas_columns_absent(self):
        """NAS-specific columns must have been removed from the Alert model."""
        cols = _alert_column_names()
        nas_only = {
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
            "raw_alert",
        }
        for col in nas_only:
            assert col not in cols, (
                f"NAS column '{col}' should have been removed but is still on Alert"
            )

    def test_alert_id_property(self):
        """The alert_id property must still exist for backward compat."""
        assert hasattr(Alert, "alert_id"), "alert_id property missing"

    def test_generate_human_readable_id(self):
        """Static helper still works."""
        assert Alert.generate_human_readable_id(42) == "AID-42"

    def test_analyses_relationship_exists(self):
        """Alert.analyses relationship must still be present."""
        mapper = inspect(Alert)
        assert "analyses" in mapper.relationships


class TestAlertAnalysisColumnsUnchanged:
    """AlertAnalysis model must not be affected by OCSF migration."""

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


class TestDispositionColumnsUnchanged:
    """Disposition model must not be affected by OCSF migration."""

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


# ═══════════════════════════════════════════════════════════════════════════
# 2. ENRICHMENT PIPELINE CONTRACT
# ═══════════════════════════════════════════════════════════════════════════


class TestEnrichmentPipelineContract:
    """Lock down enrichment behavior that 30+ tasks depend on.

    The enrich_alert() function MUST maintain these invariants.
    The dict-keyed pattern (not OCSF array) is preserved for backward
    compatibility with existing Cy tasks.
    """

    @pytest.fixture
    def enrichment_functions(self):
        return CyEnrichmentFunctions(execution_context={"cy_name": "test_task"})

    def test_enrichment_keyed_by_cy_name(self, enrichment_functions):
        """Enrichments must be stored under alert['enrichments'][cy_name]."""
        alert = {"title": "Test"}
        result = enrichment_functions.enrich_alert(alert, {"score": 85})
        assert "enrichments" in result
        assert "test_task" in result["enrichments"]
        assert result["enrichments"]["test_task"] == {"score": 85}

    def test_enrichment_preserves_original_alert_fields(self, enrichment_functions):
        """enrich_alert must never modify original alert fields."""
        alert = {
            "title": "Original Title",
            "severity_id": 4,
            "finding_info": {"title": "Test", "uid": "abc"},
        }
        result = enrichment_functions.enrich_alert(alert, {"data": "new"})
        assert result["title"] == "Original Title"
        assert result["severity_id"] == 4
        assert result["finding_info"] == {"title": "Test", "uid": "abc"}

    def test_enrichment_accumulates_across_tasks(self, enrichment_functions):
        """Multiple enrich_alert calls must accumulate, not overwrite."""
        alert = {"title": "Test"}

        fn1 = CyEnrichmentFunctions(execution_context={"cy_name": "task_a"})
        alert = fn1.enrich_alert(alert, {"from": "task_a"})

        fn2 = CyEnrichmentFunctions(execution_context={"cy_name": "task_b"})
        alert = fn2.enrich_alert(alert, {"from": "task_b"})

        assert alert["enrichments"]["task_a"] == {"from": "task_a"}
        assert alert["enrichments"]["task_b"] == {"from": "task_b"}

    def test_enrichment_custom_key_name(self, enrichment_functions):
        """enrich_alert with explicit key_name must use it instead of cy_name."""
        alert = {"title": "Test"}
        result = enrichment_functions.enrich_alert(
            alert, {"data": 1}, key_name="custom_key"
        )
        assert "custom_key" in result["enrichments"]
        assert "test_task" not in result["enrichments"]

    def test_enrichment_handles_none_enrichments(self, enrichment_functions):
        """Alert with enrichments=None must get a fresh dict."""
        alert = {"title": "Test", "enrichments": None}
        result = enrichment_functions.enrich_alert(alert, {"data": 1})
        assert result["enrichments"]["test_task"] == {"data": 1}

    def test_enrichment_handles_missing_enrichments_key(self, enrichment_functions):
        """Alert without enrichments key must get a fresh dict."""
        alert = {"title": "Test"}
        result = enrichment_functions.enrich_alert(alert, {"data": 1})
        assert result["enrichments"]["test_task"] == {"data": 1}

    def test_enrichment_is_dict_keyed_not_array(self, enrichment_functions):
        """Enrichments MUST be a dict (not OCSF array) internally."""
        alert = {"title": "Test"}
        result = enrichment_functions.enrich_alert(alert, {"data": 1})
        assert isinstance(result["enrichments"], dict)
        # NOT a list — this would break 30+ tasks
        assert not isinstance(result["enrichments"], list)

    def test_enrichment_chained_access_pattern(self, enrichment_functions):
        """Tasks access enrichments as alert['enrichments']['task_name']['field'].

        This is the exact access pattern used by 22+ downstream tasks.
        """
        alert = {"title": "Test"}
        ctx = CyEnrichmentFunctions(
            execution_context={"cy_name": "alert_context_generation"}
        )
        alert = ctx.enrich_alert(
            alert, {"ai_analysis": "SQL injection detected from external IP"}
        )

        # This is how downstream tasks access it:
        ai_text = alert["enrichments"]["alert_context_generation"]["ai_analysis"]
        assert "SQL injection" in ai_text


# ═══════════════════════════════════════════════════════════════════════════
# 3. OCSF ENUM VALUE RANGES
# ═══════════════════════════════════════════════════════════════════════════


class TestOCSFEnumRanges:
    """Lock down OCSF Detection Finding v1.8.0 integer enum ranges.

    These ranges come from the OCSF spec and are used by the validation
    tool (schema_tools.validate_ocsf_alert) and the Alert model.

    All OCSF integer enums also accept 99 = "Other".
    """

    # Ranges are (min, max) inclusive, from _OCSF_ENUM_RANGES in schema_tools.
    EXPECTED_RANGES: ClassVar[dict[str, tuple[int, int]]] = {
        "severity_id": (0, 6),
        "disposition_id": (0, 27),
        "action_id": (0, 4),
        "status_id": (0, 6),
        "confidence_id": (0, 3),
        "verdict_id": (0, 10),
    }

    def test_enum_ranges_match_schema_tools(self):
        """The authoritative enum ranges in schema_tools must match."""
        from analysi.mcp.tools.schema_tools import _OCSF_ENUM_RANGES

        assert _OCSF_ENUM_RANGES == self.EXPECTED_RANGES, (
            f"OCSF enum ranges changed.\n"
            f"  schema_tools: {_OCSF_ENUM_RANGES}\n"
            f"  expected: {self.EXPECTED_RANGES}"
        )

    def test_severity_id_range(self):
        """severity_id: 0=Unknown through 6=Fatal, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["severity_id"]
        assert lo == 0
        assert hi == 6
        # Common values used in the codebase
        valid_values = [*list(range(lo, hi + 1)), 99]
        assert 1 in valid_values  # Info
        assert 4 in valid_values  # High
        assert 5 in valid_values  # Critical
        assert 99 in valid_values  # Other

    def test_disposition_id_range(self):
        """disposition_id: 0=Unknown through 27, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["disposition_id"]
        assert lo == 0
        assert hi == 27

    def test_verdict_id_range(self):
        """verdict_id: 0=Unknown through 10, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["verdict_id"]
        assert lo == 0
        assert hi == 10

    def test_action_id_range(self):
        """action_id: 0=Unknown through 4, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["action_id"]
        assert lo == 0
        assert hi == 4

    def test_status_id_range(self):
        """status_id: 0=Unknown through 6, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["status_id"]
        assert lo == 0
        assert hi == 6

    def test_confidence_id_range(self):
        """confidence_id: 0=Unknown through 3, plus 99=Other."""
        lo, hi = self.EXPECTED_RANGES["confidence_id"]
        assert lo == 0
        assert hi == 3

    def test_all_enum_fields_have_model_columns(self):
        """Every OCSF enum field must exist as a column on the Alert model."""
        cols = _alert_column_names()
        for field_name in self.EXPECTED_RANGES:
            assert field_name in cols, (
                f"OCSF enum field '{field_name}' missing from Alert model"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. OCSF RESPONSE SCHEMA FIELD INVENTORY
# ═══════════════════════════════════════════════════════════════════════════


class TestOCSFAlertResponseFieldInventory:
    """Lock down OCSFAlertResponse Pydantic schema fields."""

    EXPECTED_FIELDS: ClassVar[set[str]] = {
        "ocsf",
        "alert_id",
        "human_readable_id",
        "analysis_status",
        "enrichments",
    }

    def test_ocsf_alert_response_exact_fields(self):
        actual = set(OCSFAlertResponse.model_fields.keys())
        assert actual == self.EXPECTED_FIELDS, (
            f"OCSFAlertResponse fields changed.\n"
            f"  Added:   {actual - self.EXPECTED_FIELDS}\n"
            f"  Removed: {self.EXPECTED_FIELDS - actual}"
        )

    def test_ocsf_alert_response_field_count(self):
        assert len(OCSFAlertResponse.model_fields) == 5

    def test_ocsf_field_is_required(self):
        """The 'ocsf' field (full Detection Finding dict) must be required."""
        assert OCSFAlertResponse.model_fields["ocsf"].is_required()

    def test_alert_id_is_required(self):
        assert OCSFAlertResponse.model_fields["alert_id"].is_required()

    def test_enrichments_is_optional(self):
        """enrichments field must be optional (None when no tasks have run)."""
        assert not OCSFAlertResponse.model_fields["enrichments"].is_required()


# ═══════════════════════════════════════════════════════════════════════════
# 5. CY OCSF HELPER INVENTORY
# ═══════════════════════════════════════════════════════════════════════════


class TestCyOCSFHelperInventory:
    """Lock down the 18 OCSF helper functions registered for Cy scripts."""

    EXPECTED_HELPERS: ClassVar[set[str]] = {
        "get_primary_entity_type",
        "get_primary_entity_value",
        "get_primary_user",
        "get_primary_device",
        "get_primary_observable_type",
        "get_primary_observable_value",
        "get_primary_observable",
        "get_observables",
        "get_src_ip",
        "get_dst_ip",
        "get_dst_domain",
        "get_http_method",
        "get_user_agent",
        "get_http_response_code",
        "get_url",
        "get_url_path",
        "get_cve_ids",
        "get_label",
    }

    def test_helper_count(self):
        """Exactly 18 OCSF helpers must be registered."""
        helpers = create_cy_ocsf_helpers()
        assert len(helpers) == 18, (
            f"Expected 18 OCSF helpers, got {len(helpers)}: {sorted(helpers.keys())}"
        )

    def test_helper_names_exact(self):
        """The exact set of helper function names must match."""
        helpers = create_cy_ocsf_helpers()
        actual = set(helpers.keys())
        assert actual == self.EXPECTED_HELPERS, (
            f"OCSF helper inventory changed.\n"
            f"  Added:   {actual - self.EXPECTED_HELPERS}\n"
            f"  Removed: {self.EXPECTED_HELPERS - actual}"
        )


class TestRuleNameVsTitleContract:
    """Lock down the separation between rule_name and title.

    rule_name (= finding_info.analytic.name) is the stable detection rule
    identifier used for alert routing. title (= finding_info.title) is the
    human-readable alert summary that may contain per-instance data like IPs.

    These are different concepts and must not be confused. If they are
    conflated, alert routing will break (each alert gets a unique "rule"
    instead of grouping by detection rule).
    """

    def test_alert_model_has_both_rule_name_and_finding_info(self):
        """Alert model must have separate rule_name column AND finding_info JSONB."""
        cols = _alert_column_names()
        assert "rule_name" in cols, "rule_name column missing from Alert model"
        assert "finding_info" in cols, "finding_info column missing from Alert model"

    def test_cy_alert_dict_exposes_rule_name(self):
        """The dict returned by alert_read() must include rule_name at top level.

        Cy scripts access rule_name as input.rule_name for routing.
        """
        # Verify the method builds a dict with rule_name key
        import inspect as pyinspect

        from analysi.services.cy_alert_functions import CyAlertFunctions

        source = pyinspect.getsource(CyAlertFunctions.alert_read)
        assert '"rule_name"' in source, (
            "CyAlertFunctions.alert_read() must include 'rule_name' in returned dict"
        )

    def test_cy_alert_dict_exposes_finding_info(self):
        """The dict returned by alert_read() must include finding_info at top level.

        Cy scripts can access finding_info.analytic.name as an alternative
        to rule_name.
        """
        import inspect as pyinspect

        from analysi.services.cy_alert_functions import CyAlertFunctions

        source = pyinspect.getsource(CyAlertFunctions.alert_read)
        assert '"finding_info"' in source, (
            "CyAlertFunctions.alert_read() must include 'finding_info' in returned dict"
        )

    def test_ingestion_extracts_rule_name_from_analytic(self):
        """AlertIngestionService must extract rule_name from finding_info.analytic.name.

        This ensures the DB column rule_name is populated from the correct
        OCSF field, not from finding_info.title.
        """
        import inspect as pyinspect

        from analysi.integrations.framework.alert_ingest import AlertIngestionService

        source = pyinspect.getsource(AlertIngestionService)
        # Must read from analytic.name, not from finding_info.title
        assert "analytic" in source, (
            "AlertIngestionService must extract rule_name from "
            "finding_info.analytic.name, not finding_info.title"
        )

    def test_all_helpers_are_callable(self):
        """Every registered helper must be a callable."""
        helpers = create_cy_ocsf_helpers()
        for name, func in helpers.items():
            assert callable(func), f"Helper '{name}' is not callable"

    def test_helpers_accept_alert_dict(self):
        """Every helper must accept an alert dict as first argument without error."""
        helpers = create_cy_ocsf_helpers()
        empty_alert: dict = {}
        for name, func in helpers.items():
            # get_label requires a second 'key' argument
            if name == "get_label":
                result = func(empty_alert, "test_key")
            # get_primary_observable and get_observables accept optional type kwarg
            else:
                result = func(empty_alert)
            # Should return None or empty list, not raise
            assert (
                result is None or result == [] or isinstance(result, (str, dict, list))
            ), f"Helper '{name}' returned unexpected type: {type(result)}"
