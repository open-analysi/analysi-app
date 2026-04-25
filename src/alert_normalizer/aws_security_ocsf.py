"""AWS Security (GuardDuty + Security Hub) -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from AWS GuardDuty findings
and Security Hub findings.  Detects the source format automatically:
- GuardDuty findings have a lowercase ``type`` field (e.g., "Recon:EC2/...")
- Security Hub findings have ``Severity`` with a ``Label`` key

Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.helpers.ip_classification import is_public_ip
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── GuardDuty severity ranges -> OCSF severity_id / label ───────────
# GuardDuty severity is a float 0-8.9:
#   Low: 1.0 - 3.9, Medium: 4.0 - 6.9, High: 7.0 - 8.9
_GD_SEVERITY_RANGES: list[tuple[float, float, int, str]] = [
    (0.0, 0.9, 1, "Informational"),
    (1.0, 3.9, 2, "Low"),
    (4.0, 6.9, 3, "Medium"),
    (7.0, 8.9, 4, "High"),
]

# Security Hub severity label -> OCSF severity_id / label
_SH_SEVERITY_MAP: dict[str, tuple[int, str]] = {
    "INFORMATIONAL": (1, "Informational"),
    "LOW": (2, "Low"),
    "MEDIUM": (3, "Medium"),
    "HIGH": (4, "High"),
    "CRITICAL": (5, "Critical"),
}

# GuardDuty type prefix -> MITRE ATT&CK tactic mapping
# GuardDuty type format: "ThreatPurpose:ResourceTypeAffected/ThreatFamilyName.DetectionMechanism"
_GD_TYPE_TO_TACTIC: dict[str, tuple[str, str]] = {
    "Recon": ("TA0043", "Reconnaissance"),
    "UnauthorizedAccess": ("TA0001", "Initial Access"),
    "CryptoCurrency": ("TA0040", "Impact"),
    "Trojan": ("TA0002", "Execution"),
    "Backdoor": ("TA0003", "Persistence"),
    "PenTest": ("TA0043", "Reconnaissance"),
    "Stealth": ("TA0005", "Defense Evasion"),
    "Persistence": ("TA0003", "Persistence"),
    "Impact": ("TA0040", "Impact"),
    "CredentialAccess": ("TA0006", "Credential Access"),
    "Exfiltration": ("TA0010", "Exfiltration"),
    "Discovery": ("TA0007", "Discovery"),
}

# Security Hub workflow status -> OCSF status mapping
_SH_STATUS_MAP: dict[str, tuple[int, str]] = {
    "NEW": (1, "New"),
    "NOTIFIED": (2, "In Progress"),
    "RESOLVED": (3, "Closed"),
    "SUPPRESSED": (3, "Closed"),
}


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _is_guardduty(data: dict[str, Any]) -> bool:
    """Detect whether raw data is a GuardDuty finding vs Security Hub.

    GuardDuty findings have a lowercase ``type`` field with the format
    "ThreatPurpose:ResourceType/ThreatFamily".
    Security Hub findings have ``Severity`` with ``Label``.
    """
    # GuardDuty findings have lowercase 'type' containing ':'
    gd_type = data.get("type")
    if isinstance(gd_type, str) and ":" in gd_type:
        return True
    # Security Hub findings have Severity.Label
    severity = data.get("Severity")
    if isinstance(severity, dict) and "Label" in severity:
        return False
    # Fallback: GuardDuty has lowercase 'severity' (float), SH has 'Severity' (dict)
    return "severity" in data and not isinstance(data["severity"], dict)


class AWSSecurityOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for AWS GuardDuty + Security Hub -> OCSF Detection Finding.

    Handles both source formats, auto-detecting based on field structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert an AWS security finding to OCSF Detection Finding.

        Args:
            data: Raw GuardDuty or Security Hub finding dict.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
        if _is_guardduty(data):
            return self._guardduty_to_ocsf(data)
        return self._securityhub_to_ocsf(data)

    # ── GuardDuty ────────────────────────────────────────────────────

    def _guardduty_to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        ocsf = self._build_scaffold()

        # Title / message
        title = data.get("title", "")
        description = data.get("description", "")
        ocsf["message"] = title or description or "Unknown Alert"

        # Time
        created_at = data.get("createdAt")
        updated_at = data.get("updatedAt")
        event_time = created_at or updated_at
        if event_time:
            ocsf["time"] = _iso_to_epoch_ms(event_time)
            ocsf["time_dt"] = event_time
        if created_at:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(created_at)

        # Severity
        sev_id, sev_label = self._map_guardduty_severity(data.get("severity"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # Metadata
        ocsf["metadata"] = self._build_guardduty_metadata(data)

        # Finding info
        ocsf["finding_info"] = self._build_guardduty_finding_info(data)

        # Status — GuardDuty doesn't have workflow status, default to New
        ocsf["status_id"] = 1
        ocsf["status"] = "New"

        # Disposition + action
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # Raw data
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # Device from resource.instanceDetails
        self._build_guardduty_device(data, ocsf)

        # Actor from resource.accessKeyDetails
        self._build_guardduty_actor(data, ocsf)

        # Observables from network action IPs
        self._build_guardduty_observables(data, ocsf)

        return ocsf

    # ── Security Hub ─────────────────────────────────────────────────

    def _securityhub_to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        ocsf = self._build_scaffold()

        # Title / message
        title = data.get("Title", "")
        description = data.get("Description", "")
        ocsf["message"] = title or description or "Unknown Alert"

        # Time
        created_at = data.get("CreatedAt")
        updated_at = data.get("UpdatedAt")
        event_time = created_at or updated_at
        if event_time:
            ocsf["time"] = _iso_to_epoch_ms(event_time)
            ocsf["time_dt"] = event_time
        if created_at:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(created_at)

        # Severity
        sev_id, sev_label = self._map_securityhub_severity(data.get("Severity"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # Metadata
        ocsf["metadata"] = self._build_securityhub_metadata(data)

        # Finding info
        ocsf["finding_info"] = self._build_securityhub_finding_info(data)

        # Status from Workflow.Status
        workflow = data.get("Workflow", {})
        workflow_status = workflow.get("Status", "NEW") if workflow else "NEW"
        status_id, status_label = _SH_STATUS_MAP.get(workflow_status, (1, "New"))
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # Disposition + action
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # Raw data
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # Device from Resources
        self._build_securityhub_device(data, ocsf)

        # Observables from Network
        self._build_securityhub_observables(data, ocsf)

        # Evidences from Process
        self._build_securityhub_evidences(data, ocsf)

        return ocsf

    # ── Shared scaffold ──────────────────────────────────────────────

    @staticmethod
    def _build_scaffold() -> dict[str, Any]:
        """Build the common OCSF Detection Finding scaffold."""
        return {
            "class_uid": 2004,
            "class_name": "Detection Finding",
            "category_uid": 2,
            "category_name": "Findings",
            "activity_id": 1,
            "activity_name": "Create",
            "type_uid": 200401,
            "type_name": "Detection Finding: Create",
            "is_alert": True,
        }

    # ── GuardDuty severity ───────────────────────────────────────────

    @staticmethod
    def _map_guardduty_severity(
        raw_severity: Any,
    ) -> tuple[int, str]:
        """Map GuardDuty severity float (0-8.9) to OCSF severity_id."""
        if raw_severity is None:
            return 1, "Informational"
        try:
            sev = float(raw_severity)
        except (ValueError, TypeError):
            return 1, "Informational"
        for low, high, ocsf_id, label in _GD_SEVERITY_RANGES:
            if low <= sev <= high:
                return ocsf_id, label
        return 1, "Informational"

    # ── Security Hub severity ────────────────────────────────────────

    @staticmethod
    def _map_securityhub_severity(
        severity_obj: Any,
    ) -> tuple[int, str]:
        """Map Security Hub Severity object to OCSF severity_id."""
        if not isinstance(severity_obj, dict):
            return 1, "Informational"
        label = severity_obj.get("Label", "").upper()
        return _SH_SEVERITY_MAP.get(label, (1, "Informational"))

    # ── GuardDuty metadata ───────────────────────────────────────────

    @staticmethod
    def _build_guardduty_metadata(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Amazon Web Services",
                "name": "GuardDuty",
            },
        }

    # ── Security Hub metadata ────────────────────────────────────────

    @staticmethod
    def _build_securityhub_metadata(data: dict[str, Any]) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Amazon Web Services",
                "name": "Security Hub",
            },
        }
        product_name = data.get("ProductName")
        company_name = data.get("CompanyName")
        labels: list[str] = []
        if product_name:
            labels.append(f"source_product:{product_name}")
        if company_name:
            labels.append(f"source_company:{company_name}")
        if labels:
            meta["labels"] = labels
        return meta

    # ── GuardDuty finding_info ───────────────────────────────────────

    def _build_guardduty_finding_info(self, data: dict[str, Any]) -> dict[str, Any]:
        finding_id = data.get("id", "")
        title = data.get("title", "")
        description = data.get("description", "")

        finding: dict[str, Any] = {
            "uid": finding_id,
            "title": title or description or "Unknown Alert",
        }

        if description:
            finding["desc"] = description

        # GuardDuty type as analytic name
        gd_type = data.get("type", "")
        if gd_type:
            finding["analytic"] = {
                "name": gd_type,
                "type_id": 1,
                "type": "Rule",
            }

        # MITRE ATT&CK from type prefix
        attacks = self._guardduty_type_to_attacks(gd_type)
        if attacks:
            finding["attacks"] = attacks

        created_at = data.get("createdAt")
        if created_at:
            finding["created_time"] = created_at

        return finding

    @staticmethod
    def _guardduty_type_to_attacks(gd_type: str) -> list[dict[str, Any]]:
        """Extract MITRE tactic from GuardDuty type prefix.

        GuardDuty type format: "ThreatPurpose:ResourceType/ThreatFamily"
        The prefix before ':' maps to a MITRE tactic.
        """
        if not gd_type or ":" not in gd_type:
            return []
        prefix = gd_type.split(":")[0]
        mapping = _GD_TYPE_TO_TACTIC.get(prefix)
        if not mapping:
            return []
        tactic_uid, tactic_name = mapping
        return [{"tactic": {"uid": tactic_uid, "name": tactic_name}}]

    # ── Security Hub finding_info ────────────────────────────────────

    @staticmethod
    def _build_securityhub_finding_info(data: dict[str, Any]) -> dict[str, Any]:
        finding_id = data.get("Id", "")
        title = data.get("Title", "")
        description = data.get("Description", "")

        finding: dict[str, Any] = {
            "uid": finding_id,
            "title": title or description or "Unknown Alert",
        }

        if description:
            finding["desc"] = description

        if title:
            finding["analytic"] = {
                "name": title,
                "type_id": 1,
                "type": "Rule",
            }

        # Types as data_sources
        types = data.get("Types")
        if types and isinstance(types, list):
            finding["data_sources"] = types

        created_at = data.get("CreatedAt")
        if created_at:
            finding["created_time"] = created_at

        return finding

    # ── GuardDuty device ─────────────────────────────────────────────

    @staticmethod
    def _build_guardduty_device(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        resource = data.get("resource", {})
        if not resource:
            return

        instance = resource.get("instanceDetails", {})
        if not instance:
            return

        device: dict[str, Any] = {}
        instance_id = instance.get("instanceId")
        if instance_id:
            device["uid"] = instance_id

        # Extract IP from network interfaces
        net_interfaces = instance.get("networkInterfaces", [])
        if net_interfaces and isinstance(net_interfaces, list):
            iface = net_interfaces[0]
            private_ip = iface.get("privateIpAddress")
            if private_ip:
                device["ip"] = private_ip

        if device:
            ocsf["device"] = device

    # ── GuardDuty actor ──────────────────────────────────────────────

    @staticmethod
    def _build_guardduty_actor(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        resource = data.get("resource", {})
        if not resource:
            return

        access_key = resource.get("accessKeyDetails", {})
        if not access_key:
            return

        user_name = access_key.get("userName")
        if not user_name:
            return

        actor: dict[str, Any] = {"user": {"name": user_name}}
        access_key_id = access_key.get("accessKeyId")
        if access_key_id:
            actor["user"]["uid"] = access_key_id
        ocsf["actor"] = actor

    # ── GuardDuty observables ────────────────────────────────────────

    @staticmethod
    def _build_guardduty_observables(
        data: dict[str, Any], ocsf: dict[str, Any]
    ) -> None:
        observables: list[dict[str, Any]] = []

        service = data.get("service", {})
        if not service:
            return

        action_info = service.get("action", {})
        if not action_info:
            return

        # Network connection action
        net_action = action_info.get("networkConnectionAction", {})
        if net_action:
            remote_ip_details = net_action.get("remoteIpDetails", {})
            remote_ip = remote_ip_details.get("ipAddressV4")
            if remote_ip and is_public_ip(remote_ip):
                observables.append(
                    {
                        "type_id": 2,
                        "type": "IP Address",
                        "name": "remote_ip",
                        "value": remote_ip,
                    }
                )

        # Port probe action
        port_probe = action_info.get("portProbeAction", {})
        if port_probe:
            probes = port_probe.get("portProbeDetails", [])
            for probe in probes:
                remote_ip_details = probe.get("remoteIpDetails", {})
                remote_ip = remote_ip_details.get("ipAddressV4")
                if remote_ip and is_public_ip(remote_ip):
                    # Avoid duplicates
                    existing_ips = {o["value"] for o in observables}
                    if remote_ip not in existing_ips:
                        observables.append(
                            {
                                "type_id": 2,
                                "type": "IP Address",
                                "name": "remote_ip",
                                "value": remote_ip,
                            }
                        )

        # AWS API call action — remote IP
        api_action = action_info.get("awsApiCallAction", {})
        if api_action:
            remote_ip_details = api_action.get("remoteIpDetails", {})
            remote_ip = remote_ip_details.get("ipAddressV4")
            if remote_ip and is_public_ip(remote_ip):
                existing_ips = {o["value"] for o in observables}
                if remote_ip not in existing_ips:
                    observables.append(
                        {
                            "type_id": 2,
                            "type": "IP Address",
                            "name": "remote_ip",
                            "value": remote_ip,
                        }
                    )

        if observables:
            ocsf["observables"] = observables

    # ── Security Hub device ──────────────────────────────────────────

    @staticmethod
    def _build_securityhub_device(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        resources = data.get("Resources")
        if not resources or not isinstance(resources, list):
            return

        first = resources[0]
        device: dict[str, Any] = {}
        resource_id = first.get("Id")
        resource_type = first.get("Type")
        if resource_id:
            device["uid"] = resource_id
        if resource_type:
            device["type"] = resource_type

        if device:
            ocsf["device"] = device

    # ── Security Hub observables ─────────────────────────────────────

    @staticmethod
    def _build_securityhub_observables(
        data: dict[str, Any], ocsf: dict[str, Any]
    ) -> None:
        observables: list[dict[str, Any]] = []
        network = data.get("Network", {})
        if not network:
            return

        for field_name, display in [
            ("SourceIpV4", "source_ip"),
            ("DestinationIpV4", "destination_ip"),
        ]:
            ip_val = network.get(field_name)
            if ip_val and is_public_ip(ip_val):
                observables.append(
                    {
                        "type_id": 2,
                        "type": "IP Address",
                        "name": display,
                        "value": ip_val,
                    }
                )

        if observables:
            ocsf["observables"] = observables

    # ── Security Hub evidences ───────────────────────────────────────

    @staticmethod
    def _build_securityhub_evidences(
        data: dict[str, Any], ocsf: dict[str, Any]
    ) -> None:
        evidences: list[dict[str, Any]] = []

        process = data.get("Process", {})
        if process:
            proc_obj: dict[str, Any] = {}
            name = process.get("Name")
            path = process.get("Path")
            pid = process.get("Pid")
            if name:
                proc_obj["name"] = name
            if path:
                proc_obj["path"] = path
            if pid is not None:
                proc_obj["pid"] = pid
            if proc_obj:
                evidences.append({"process": proc_obj})

        if evidences:
            ocsf["evidences"] = evidences
