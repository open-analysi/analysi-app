"""Unit tests for Cy Alert Functions — OCSF format (Project Skaros)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.alert import Alert
from analysi.services.cy_alert_functions import (
    CyAlertFunctions,
    create_cy_alert_functions,
)


class TestCyAlertFunctions:
    """Test suite for Cy alert functions."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def execution_context(self):
        return {
            "task_id": str(uuid4()),
            "workflow_id": str(uuid4()),
            "tenant_id": "test-tenant",
        }

    @pytest.fixture
    def cy_alert_functions(self, mock_session, execution_context):
        return CyAlertFunctions(
            session=mock_session,
            tenant_id="test-tenant",
            execution_context=execution_context,
        )

    @pytest.fixture
    def sample_alert(self):
        """Create a sample OCSF-shaped alert mock."""
        alert = MagicMock(spec=Alert)
        alert.id = uuid4()
        alert.tenant_id = "test-tenant"
        alert.human_readable_id = "AID-42"
        alert.title = "SQL Injection Detected"
        alert.severity = "high"
        alert.severity_id = 4
        alert.source_vendor = "Splunk"
        alert.source_product = "Enterprise Security"
        alert.rule_name = "SQL Injection Rule"
        alert.source_event_id = None

        # OCSF structured fields
        alert.finding_info = {"title": "SQL Injection Detected", "uid": "abc-123"}
        alert.ocsf_metadata = {"version": "1.8.0", "product": {"vendor_name": "Splunk"}}
        alert.observables = [
            {"type_id": 2, "type": "IP Address", "value": "203.0.113.50"},
        ]
        alert.evidences = [
            {
                "src_endpoint": {"ip": "203.0.113.50"},
                "dst_endpoint": {"ip": "10.0.1.100"},
            },
        ]
        alert.osint = None
        alert.actor = {"user": {"name": "jdoe"}}
        alert.device = {"hostname": "WebServer1001"}
        alert.cloud = None
        alert.vulnerabilities = None
        alert.unmapped = None

        # OCSF scalar enums
        alert.disposition_id = 2
        alert.verdict_id = None
        alert.action_id = None
        alert.status_id = 1
        alert.confidence_id = None
        alert.risk_level_id = None

        # Timestamps
        alert.triggering_event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        alert.detected_at = datetime(2024, 1, 15, 10, 32, 0, tzinfo=UTC)
        alert.created_at = datetime(2024, 1, 15, 10, 35, 0, tzinfo=UTC)
        alert.updated_at = datetime(2024, 1, 15, 10, 40, 0, tzinfo=UTC)

        # Raw data + dedup
        alert.raw_data = '{"rule": "sql-injection-rule"}'
        alert.raw_data_hash = "abc123hash"

        # Analysis state
        alert.analysis_status = "in_progress"
        alert.current_analysis_id = uuid4()
        alert.current_disposition_category = None
        alert.current_disposition_subcategory = None
        alert.current_disposition_display_name = None
        alert.current_disposition_confidence = None

        return alert

    @pytest.mark.asyncio
    async def test_alert_read_success(
        self, cy_alert_functions, mock_session, sample_alert
    ):
        """Test successful alert retrieval returns OCSF-shaped dict."""
        alert_id = str(sample_alert.id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_alert
        mock_session.execute.return_value = mock_result

        result = await cy_alert_functions.alert_read(alert_id)

        # Analysi identifiers
        assert result["alert_id"] == alert_id
        assert result["human_readable_id"] == "AID-42"

        # OCSF core fields
        assert result["title"] == "SQL Injection Detected"
        assert result["severity"] == "high"
        assert result["severity_id"] == 4
        assert result["finding_info"]["title"] == "SQL Injection Detected"
        assert result["metadata"]["version"] == "1.8.0"

        # OCSF structured fields (usable by Cy helpers)
        assert result["observables"][0]["value"] == "203.0.113.50"
        assert result["actor"]["user"]["name"] == "jdoe"
        assert result["device"]["hostname"] == "WebServer1001"
        assert result["evidences"][0]["src_endpoint"]["ip"] == "203.0.113.50"

        # Timestamps are ISO formatted
        assert "T" in result["triggering_event_time"]
        assert "T" in result["created_at"]

        # Raw data
        assert result["raw_data"] == '{"rule": "sql-injection-rule"}'
        assert result["raw_data_hash"] == "abc123hash"

    @pytest.mark.asyncio
    async def test_alert_read_not_found(self, cy_alert_functions, mock_session):
        """Test alert not found error."""
        alert_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc:
            await cy_alert_functions.alert_read(alert_id)
        assert f"Alert {alert_id} not found" in str(exc.value)

    @pytest.mark.asyncio
    async def test_invalid_alert_id_format(self, cy_alert_functions):
        """Test invalid alert ID format."""
        with pytest.raises(ValueError) as exc:
            await cy_alert_functions.alert_read("not-a-uuid")
        assert "Invalid alert_id format" in str(exc.value)

    @pytest.mark.asyncio
    async def test_alert_with_null_optional_fields(
        self, cy_alert_functions, mock_session
    ):
        """Test alert with null optional OCSF fields."""
        alert = MagicMock(spec=Alert)
        alert.id = uuid4()
        alert.tenant_id = "test-tenant"
        alert.human_readable_id = "AID-99"
        alert.title = "Minimal Alert"
        alert.severity = "low"
        alert.severity_id = 2
        alert.source_vendor = None
        alert.source_product = None
        alert.rule_name = None
        alert.source_event_id = None
        alert.finding_info = {}
        alert.ocsf_metadata = {}
        alert.observables = None
        alert.evidences = None
        alert.osint = None
        alert.actor = None
        alert.device = None
        alert.cloud = None
        alert.vulnerabilities = None
        alert.unmapped = None
        alert.disposition_id = None
        alert.verdict_id = None
        alert.action_id = None
        alert.status_id = 1
        alert.confidence_id = None
        alert.risk_level_id = None
        alert.triggering_event_time = None
        alert.detected_at = None
        alert.created_at = None
        alert.updated_at = None
        alert.raw_data = "{}"
        alert.raw_data_hash = ""
        alert.analysis_status = "new"
        alert.current_analysis_id = None
        alert.current_disposition_category = None
        alert.current_disposition_subcategory = None
        alert.current_disposition_display_name = None
        alert.current_disposition_confidence = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = alert
        mock_session.execute.return_value = mock_result

        result = await cy_alert_functions.alert_read(str(alert.id))

        assert result["title"] == "Minimal Alert"
        assert result["observables"] is None
        assert result["actor"] is None
        assert result["triggering_event_time"] is None

    def test_create_cy_alert_functions(self, mock_session, execution_context):
        """Test factory function returns dict with alert_read."""
        funcs = create_cy_alert_functions(
            mock_session, "test-tenant", execution_context
        )
        assert "alert_read" in funcs
        assert callable(funcs["alert_read"])
