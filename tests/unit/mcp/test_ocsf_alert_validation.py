"""Unit tests for OCSF Detection Finding validation tool.

Tests:
- Valid OCSF alert passes validation
- Missing required fields produce errors
- Invalid severity_id range produces errors
- Invalid class_uid produces errors
- Extra fields (OCSF is extensible) produce warnings, not errors
"""

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp.context import mcp_current_user_context
from analysi.mcp.tools import schema_tools


def _valid_ocsf_alert() -> dict:
    """Return a minimal valid OCSF Detection Finding dict."""
    return {
        "class_uid": 2004,
        "class_name": "Detection Finding",
        "category_uid": 2,
        "category_name": "Findings",
        "activity_id": 1,
        "activity_name": "Create",
        "type_uid": 200401,
        "type_name": "Detection Finding: Create",
        "severity_id": 4,
        "severity": "High",
        "message": "SQL Injection Detected",
        "time": 1718444400000,
        "metadata": {
            "version": "1.8.0",
            "product": {"vendor_name": "Splunk", "name": "ES"},
        },
        "finding_info": {
            "uid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "title": "SQL Injection Detected",
            "types": ["network"],
        },
    }


@pytest.mark.asyncio
class TestOCSFAlertValidation:
    """Test suite for OCSF Detection Finding validation."""

    @pytest.fixture(autouse=True)
    def _set_mcp_user(self):
        """Set an authenticated MCP user for all tests."""
        user = CurrentUser(
            user_id="kc-test",
            email="test@analysi.dev",
            tenant_id="test-tenant",
            roles=["analyst"],
            actor_type="user",
        )
        mcp_current_user_context.set(user)
        yield
        mcp_current_user_context.set(None)

    @pytest.mark.asyncio
    async def test_valid_ocsf_alert(self):
        """A fully valid OCSF alert passes validation."""
        result = await schema_tools.validate_ocsf_alert(_valid_ocsf_alert())

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["alert_structure"]["has_required_fields"] is True

    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        """Missing required fields produce errors."""
        alert = {}  # completely empty

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        error_fields = {e["field"] for e in result["errors"]}
        assert "class_uid" in error_fields
        assert "severity_id" in error_fields
        assert "time" in error_fields
        assert "metadata" in error_fields
        assert "finding_info" in error_fields

    @pytest.mark.asyncio
    async def test_missing_metadata_subfields(self):
        """Metadata present but missing product and version produces errors."""
        alert = _valid_ocsf_alert()
        alert["metadata"] = {}  # no product, no version

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        error_fields = {e["field"] for e in result["errors"]}
        assert "metadata.product" in error_fields
        assert "metadata.version" in error_fields

    @pytest.mark.asyncio
    async def test_missing_finding_info_subfields(self):
        """finding_info present but missing title and uid produces errors."""
        alert = _valid_ocsf_alert()
        alert["finding_info"] = {}  # no title, no uid

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        error_fields = {e["field"] for e in result["errors"]}
        assert "finding_info.title" in error_fields
        assert "finding_info.uid" in error_fields

    @pytest.mark.asyncio
    async def test_invalid_severity_id_range(self):
        """severity_id outside 1-6 (and not 99) produces an error."""
        alert = _valid_ocsf_alert()
        alert["severity_id"] = 42

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        severity_errors = [e for e in result["errors"] if e["field"] == "severity_id"]
        assert len(severity_errors) == 1
        assert "42" in severity_errors[0]["message"]

    @pytest.mark.asyncio
    async def test_severity_id_99_is_valid(self):
        """severity_id=99 (Other) is always valid per OCSF convention."""
        alert = _valid_ocsf_alert()
        alert["severity_id"] = 99

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_class_uid(self):
        """class_uid != 2004 produces an error."""
        alert = _valid_ocsf_alert()
        alert["class_uid"] = 1001  # not Detection Finding

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        class_errors = [e for e in result["errors"] if e["field"] == "class_uid"]
        assert len(class_errors) == 1
        assert "2004" in class_errors[0]["message"]

    @pytest.mark.asyncio
    async def test_extra_fields_produce_warnings(self):
        """Unrecognised fields are allowed (OCSF extensibility) with warnings."""
        alert = _valid_ocsf_alert()
        alert["custom_vendor_field"] = "some value"
        alert["x_internal_id"] = 12345

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is True  # extra fields do NOT invalidate
        assert len(result["warnings"]) >= 2
        warning_fields = {w["field"] for w in result["warnings"]}
        assert "custom_vendor_field" in warning_fields
        assert "x_internal_id" in warning_fields

    @pytest.mark.asyncio
    async def test_invalid_disposition_id_range(self):
        """disposition_id outside 0-27 (and not 99) produces an error."""
        alert = _valid_ocsf_alert()
        alert["disposition_id"] = 50

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        disp_errors = [e for e in result["errors"] if e["field"] == "disposition_id"]
        assert len(disp_errors) == 1

    @pytest.mark.asyncio
    async def test_valid_disposition_id(self):
        """disposition_id within 0-27 passes."""
        alert = _valid_ocsf_alert()
        alert["disposition_id"] = 15  # Detected

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_verdict_id_range(self):
        """verdict_id outside 0-10 (and not 99) produces an error."""
        alert = _valid_ocsf_alert()
        alert["verdict_id"] = 55

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_non_integer_enum_field(self):
        """Enum fields that are not integers produce type errors."""
        alert = _valid_ocsf_alert()
        alert["severity_id"] = "high"  # should be int

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        type_errors = [
            e
            for e in result["errors"]
            if e["field"] == "severity_id" and e["error_type"] == "invalid_type"
        ]
        assert len(type_errors) == 1

    @pytest.mark.asyncio
    async def test_metadata_wrong_type(self):
        """metadata that is not a dict produces a type error."""
        alert = _valid_ocsf_alert()
        alert["metadata"] = "not a dict"

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False
        meta_errors = [e for e in result["errors"] if e["field"] == "metadata"]
        assert len(meta_errors) == 1
        assert meta_errors[0]["error_type"] == "invalid_type"

    @pytest.mark.asyncio
    async def test_finding_info_wrong_type(self):
        """finding_info that is not a dict produces a type error."""
        alert = _valid_ocsf_alert()
        alert["finding_info"] = ["not", "a", "dict"]

        result = await schema_tools.validate_ocsf_alert(alert)

        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_alert_structure_summary(self):
        """alert_structure summarises field presence correctly."""
        alert = _valid_ocsf_alert()
        alert["custom_field"] = True

        result = await schema_tools.validate_ocsf_alert(alert)

        structure = result["alert_structure"]
        assert structure["has_required_fields"] is True
        assert structure["has_optional_fields"] is True
        assert structure["has_extra_fields"] is True
        assert structure["field_count"] == len(alert)

    @pytest.mark.asyncio
    async def test_empty_alert(self):
        """An empty dict fails with multiple missing-field errors."""
        result = await schema_tools.validate_ocsf_alert({})

        assert result["valid"] is False
        assert len(result["errors"]) >= 5
        assert result["alert_structure"]["field_count"] == 0
