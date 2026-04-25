"""OCSF API response schemas.

These schemas serve alert data in OCSF Detection Finding v1.8.0 format.
The Alert model has OCSF columns directly -- no translation needed.
"""

from typing import Any

from pydantic import BaseModel, Field


class OCSFAlertResponse(BaseModel):
    """Alert response in OCSF Detection Finding v1.8.0 format."""

    ocsf: dict[str, Any] = Field(..., description="OCSF Detection Finding v1.8.0")
    alert_id: str = Field(..., description="Analysi alert ID")
    human_readable_id: str = Field(..., description="Human-friendly ID (AID-1)")
    analysis_status: str = Field(..., description="Analysis pipeline status")
    enrichments: dict[str, Any] | None = Field(
        None, description="Task enrichments (internal dict format)"
    )


class OCSFAlertListResponse(BaseModel):
    """Paginated list of OCSF alerts."""

    data: list[OCSFAlertResponse]
    meta: dict[str, Any]


def alert_model_to_ocsf_response(alert_model: Any) -> OCSFAlertResponse:
    """Convert an Alert ORM model to an OCSFAlertResponse.

    Reads OCSF columns directly from the model.

    Args:
        alert_model: SQLAlchemy Alert model instance

    Returns:
        OCSFAlertResponse with full OCSF Detection Finding
    """

    ocsf_finding: dict[str, Any] = {
        "class_uid": 2004,
        "class_name": "Detection Finding",
        "category_uid": 2,
        "category_name": "Findings",
        "activity_id": 1,
        "activity_name": "Create",
        "type_uid": 200401,
        "type_name": "Detection Finding: Create",
        "severity_id": alert_model.severity_id,
        "severity": alert_model.severity.capitalize() if alert_model.severity else None,
        "message": alert_model.title,
        "time": alert_model.ocsf_time,
        "finding_info": alert_model.finding_info or {},
        "metadata": alert_model.ocsf_metadata or {},
        "raw_data": alert_model.raw_data,
    }

    # Add optional fields only if non-null
    if alert_model.observables:
        ocsf_finding["observables"] = alert_model.observables
    if alert_model.evidences:
        ocsf_finding["evidences"] = alert_model.evidences
    if alert_model.disposition_id is not None:
        ocsf_finding["disposition_id"] = alert_model.disposition_id
    if alert_model.verdict_id is not None:
        ocsf_finding["verdict_id"] = alert_model.verdict_id
    if alert_model.action_id is not None:
        ocsf_finding["action_id"] = alert_model.action_id
    if alert_model.actor:
        ocsf_finding["actor"] = alert_model.actor
    if alert_model.device:
        ocsf_finding["device"] = alert_model.device
    if alert_model.cloud:
        ocsf_finding["cloud"] = alert_model.cloud
    if alert_model.vulnerabilities:
        ocsf_finding["vulnerabilities"] = alert_model.vulnerabilities
    if alert_model.osint:
        ocsf_finding["osint"] = alert_model.osint
    if alert_model.unmapped:
        ocsf_finding["unmapped"] = alert_model.unmapped
    if alert_model.raw_data_hash:
        ocsf_finding["raw_data_hash"] = {
            "algorithm": alert_model.raw_data_hash_algorithm or "SHA-256",
            "value": alert_model.raw_data_hash,
        }

    return OCSFAlertResponse(
        ocsf=ocsf_finding,
        alert_id=str(alert_model.id),
        human_readable_id=alert_model.human_readable_id,
        analysis_status=alert_model.analysis_status or "new",
    )
