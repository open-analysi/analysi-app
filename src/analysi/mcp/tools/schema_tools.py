"""MCP tools for OCSF schema validation."""

from typing import Any

# ── OCSF Detection Finding enum ranges ──────────────────────────────────
# Maps field name -> (min, max) inclusive range of valid integer values.
_OCSF_ENUM_RANGES: dict[str, tuple[int, int]] = {
    "severity_id": (0, 6),
    "disposition_id": (0, 27),
    "action_id": (0, 4),
    "status_id": (0, 6),
    "confidence_id": (0, 3),
    "verdict_id": (0, 10),
}

# Known OCSF Detection Finding (class 2004) fields.
# OCSF is extensible, so extra fields are allowed but generate warnings.
_OCSF_KNOWN_FIELDS: set[str] = {
    # Classification
    "class_uid",
    "class_name",
    "category_uid",
    "category_name",
    "activity_id",
    "activity_name",
    "type_uid",
    "type_name",
    # Core
    "severity_id",
    "severity",
    "message",
    "time",
    "time_dt",
    "start_time",
    "start_time_dt",
    "end_time",
    "end_time_dt",
    "timezone_offset",
    "count",
    "duration",
    "status_id",
    "status",
    "status_code",
    "status_detail",
    # Finding
    "finding_info",
    "metadata",
    "observables",
    "evidences",
    "raw_data",
    "raw_data_hash",
    "enrichments",
    "unmapped",
    # Security Control profile
    "disposition_id",
    "disposition",
    "action_id",
    "action",
    "is_alert",
    "policy",
    "firewall_rule",
    "attacks",
    "malware",
    "malware_scan_info",
    "authorizations",
    # Host profile
    "device",
    "actor",
    # OSINT profile
    "osint",
    # Incident profile
    "verdict_id",
    "verdict",
    "assignee",
    "assignee_group",
    "tickets",
    "is_suspected_breach",
    # Cloud profile
    "cloud",
    "api",
    "src_endpoint",
    "dst_endpoint",
    # Vulnerability profile
    "vulnerabilities",
    # Additional
    "confidence_id",
    "confidence",
    "confidence_score",
    "risk_level_id",
    "risk_level",
    "risk_score",
    "priority_id",
    "priority",
    "src_url",
    "vendor_attributes",
    "anomaly_analyses",
}


async def validate_ocsf_alert(alert_data: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Validate a JSON dict against OCSF Detection Finding v1.8.0.

    Checks for:
    - class_uid == 2004
    - Required fields: severity_id, time, metadata (with product and version),
      finding_info (with title and uid)
    - Integer enum ranges: severity_id, disposition_id, action_id, status_id,
      confidence_id, verdict_id
    - Warnings for unrecognised top-level fields (OCSF is extensible)

    Args:
        alert_data: Dictionary representation of an OCSF alert (or JSON string)

    Returns:
        {
            "valid": bool,
            "errors": list[dict],
            "warnings": list[dict],
            "alert_structure": dict,
        }

    Each error/warning contains:
        {
            "field": str,
            "message": str,
            "error_type": str,
            "expected": Any | None,
            "valid_values": list | None,
        }
    """
    import json as _json

    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("alerts", "read")

    # Guard: MCP tool inputs may arrive as JSON strings from Claude
    if isinstance(alert_data, str):
        try:
            alert_data = _json.loads(alert_data)
        except _json.JSONDecodeError:
            return {
                "valid": False,
                "errors": [
                    {
                        "field": "alert_data",
                        "message": "Invalid JSON string",
                        "error_type": "parse_error",
                    }
                ],
                "warnings": [],
                "alert_structure": {},
            }

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    alert_structure: dict[str, Any] = {
        "field_count": len(alert_data),
        "has_required_fields": False,
        "has_optional_fields": False,
        "has_extra_fields": False,
    }

    # ── class_uid must be 2004 ─────────────────────────────────────────
    class_uid = alert_data.get("class_uid")
    if class_uid is None:
        errors.append(
            {
                "field": "class_uid",
                "message": "Required field 'class_uid' is missing",
                "error_type": "missing_required",
                "expected": 2004,
            }
        )
    elif class_uid != 2004:
        errors.append(
            {
                "field": "class_uid",
                "message": (
                    f"Invalid class_uid {class_uid}. "
                    "OCSF Detection Finding requires class_uid=2004"
                ),
                "error_type": "invalid_value",
                "expected": 2004,
            }
        )

    # ── Required scalar fields ─────────────────────────────────────────
    required_scalars = {"severity_id", "time"}
    for field_name in required_scalars:
        if field_name not in alert_data:
            errors.append(
                {
                    "field": field_name,
                    "message": f"Required field '{field_name}' is missing",
                    "error_type": "missing_required",
                    "expected": "Required field must be present",
                }
            )

    # ── Required object: metadata ──────────────────────────────────────
    metadata = alert_data.get("metadata")
    if metadata is None:
        errors.append(
            {
                "field": "metadata",
                "message": "Required field 'metadata' is missing",
                "error_type": "missing_required",
                "expected": "dict with 'product' and 'version'",
            }
        )
    elif not isinstance(metadata, dict):
        errors.append(
            {
                "field": "metadata",
                "message": f"Field 'metadata' must be a dict, got {type(metadata).__name__}",
                "error_type": "invalid_type",
                "expected": "dict",
            }
        )
    else:
        if "product" not in metadata:
            errors.append(
                {
                    "field": "metadata.product",
                    "message": "Required field 'metadata.product' is missing",
                    "error_type": "missing_required",
                    "expected": "dict with product info",
                }
            )
        if "version" not in metadata:
            errors.append(
                {
                    "field": "metadata.version",
                    "message": "Required field 'metadata.version' is missing",
                    "error_type": "missing_required",
                    "expected": "OCSF schema version string (e.g., '1.8.0')",
                }
            )

    # ── Required object: finding_info ──────────────────────────────────
    finding_info = alert_data.get("finding_info")
    if finding_info is None:
        errors.append(
            {
                "field": "finding_info",
                "message": "Required field 'finding_info' is missing",
                "error_type": "missing_required",
                "expected": "dict with 'title' and 'uid'",
            }
        )
    elif not isinstance(finding_info, dict):
        errors.append(
            {
                "field": "finding_info",
                "message": f"Field 'finding_info' must be a dict, got {type(finding_info).__name__}",
                "error_type": "invalid_type",
                "expected": "dict",
            }
        )
    else:
        if "title" not in finding_info:
            errors.append(
                {
                    "field": "finding_info.title",
                    "message": "Required field 'finding_info.title' is missing",
                    "error_type": "missing_required",
                    "expected": "string",
                }
            )
        if "uid" not in finding_info:
            errors.append(
                {
                    "field": "finding_info.uid",
                    "message": "Required field 'finding_info.uid' is missing",
                    "error_type": "missing_required",
                    "expected": "string (unique finding identifier)",
                }
            )

    # ── Enum range validation ──────────────────────────────────────────
    for field_name, (lo, hi) in _OCSF_ENUM_RANGES.items():
        value = alert_data.get(field_name)
        if value is None:
            continue
        if not isinstance(value, int):
            errors.append(
                {
                    "field": field_name,
                    "message": f"Field '{field_name}' must be an integer, got {type(value).__name__}",
                    "error_type": "invalid_type",
                    "expected": "integer",
                }
            )
        elif (value < lo or value > hi) and value != 99:
            # OCSF convention: 99 means "Other" and is always valid
            errors.append(
                {
                    "field": field_name,
                    "message": (
                        f"Invalid {field_name} value {value}. "
                        f"Must be {lo}-{hi} or 99 (Other)"
                    ),
                    "error_type": "invalid_range",
                    "expected": f"{lo}-{hi} or 99",
                    "valid_values": [*list(range(lo, hi + 1)), 99],
                }
            )

    # ── Extra / unrecognised fields (warnings) ─────────────────────────
    extra_fields = set(alert_data.keys()) - _OCSF_KNOWN_FIELDS
    for field_name in sorted(extra_fields):
        warnings.append(
            {
                "field": field_name,
                "message": (
                    f"Unrecognised field '{field_name}' is not part of the "
                    "standard OCSF Detection Finding schema"
                ),
                "error_type": "extra_field",
            }
        )

    # ── Build structure summary ────────────────────────────────────────
    required_top_level = {
        "class_uid",
        "severity_id",
        "time",
        "metadata",
        "finding_info",
    }
    present_required = required_top_level & set(alert_data.keys())
    alert_structure["has_required_fields"] = present_required == required_top_level
    alert_structure["has_optional_fields"] = bool(
        set(alert_data.keys()) - required_top_level
    )
    alert_structure["has_extra_fields"] = len(extra_fields) > 0

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "alert_structure": alert_structure,
    }
