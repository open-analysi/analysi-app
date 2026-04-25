"""CrowdStrike Falcon Alert -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from CrowdStrike Falcon
alert documents (from the ``/alerts/entities/alerts/v1`` endpoint) by mapping
CrowdStrike fields to OCSF structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.helpers.ip_classification import is_public_ip
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

# CrowdStrike severity (1-5) -> OCSF severity_id / label
SEVERITY_INT_TO_OCSF: dict[int, tuple[int, str]] = {
    1: (1, "Informational"),
    2: (2, "Low"),
    3: (3, "Medium"),
    4: (4, "High"),
    5: (5, "Critical"),
}

# CrowdStrike status -> OCSF status mapping
_STATUS_TO_OCSF: dict[str, tuple[int, str]] = {
    "new": (1, "New"),
    "in_progress": (2, "In Progress"),
    "true_positive": (3, "Closed"),
    "false_positive": (3, "Closed"),
    "closed": (3, "Closed"),
}


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


class CrowdStrikeOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for CrowdStrike Falcon alerts -> OCSF Detection Finding.

    Maps CrowdStrike alert documents directly to OCSF Detection Finding
    v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert CrowdStrike alert to OCSF Detection Finding.

        Args:
            data: Raw CrowdStrike alert document.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
        ocsf: dict[str, Any] = {}

        # ── OCSF scaffold ────────────────────────────────────────────
        ocsf["class_uid"] = 2004
        ocsf["class_name"] = "Detection Finding"
        ocsf["category_uid"] = 2
        ocsf["category_name"] = "Findings"
        ocsf["activity_id"] = 1
        ocsf["activity_name"] = "Create"
        ocsf["type_uid"] = 200401
        ocsf["type_name"] = "Detection Finding: Create"

        # ── Title / message ──────────────────────────────────────────
        display_name = data.get("display_name")
        description = data.get("description")
        ocsf["message"] = display_name or description or "Unknown Alert"

        # ── Time ─────────────────────────────────────────────────────
        timestamp = data.get("timestamp")
        created_timestamp = data.get("created_timestamp")
        event_time = timestamp or created_timestamp

        if event_time:
            ocsf["time"] = _iso_to_epoch_ms(event_time)
            ocsf["time_dt"] = event_time

        if created_timestamp:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(created_timestamp)

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = data.get("severity")
        sev_id, sev_label = self._map_severity(raw_severity)
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "CrowdStrike",
                "name": "Falcon",
            },
        }

        source_products = data.get("source_products")
        if source_products and isinstance(source_products, list):
            metadata["labels"] = [f"source_product:{p}" for p in source_products]

        composite_id = data.get("composite_id")
        if composite_id:
            metadata["event_code"] = composite_id

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data)

        # ── CrowdStrike alerts are always alertable findings ─────────
        ocsf["is_alert"] = True

        # ── Status ───────────────────────────────────────────────────
        cs_status = str(data.get("status", "new")).lower()
        status_id, status_label = _STATUS_TO_OCSF.get(cs_status, (1, "New"))
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # ── Disposition + Action ─────────────────────────────────────
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Device ───────────────────────────────────────────────────
        self._build_device(data, ocsf)

        # ── Actor ────────────────────────────────────────────────────
        self._build_actor(data, ocsf)

        # ── Observables ──────────────────────────────────────────────
        self._build_observables(data, ocsf)

        # ── Evidences ────────────────────────────────────────────────
        self._build_evidences(data, ocsf)

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    @staticmethod
    def _map_severity(raw_severity: Any) -> tuple[int, str]:
        """Map CrowdStrike severity integer (1-5) to OCSF severity_id."""
        if raw_severity is None:
            return 1, "Informational"
        try:
            sev_int = int(raw_severity)
        except (ValueError, TypeError):
            return 1, "Informational"
        return SEVERITY_INT_TO_OCSF.get(sev_int, (1, "Informational"))

    def _build_finding_info(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        composite_id = data.get("composite_id", "")
        display_name = data.get("display_name")
        description = data.get("description")

        finding: dict[str, Any] = {
            "uid": composite_id,
            "title": display_name or description or "Unknown Alert",
        }

        # Analytic (the detection rule)
        if display_name:
            analytic: dict[str, Any] = {
                "name": display_name,
                "type_id": 1,
                "type": "Rule",
            }
            finding["analytic"] = analytic

        if description:
            finding["desc"] = description

        # MITRE ATT&CK mapping
        attacks = self._build_attacks(data)
        if attacks:
            finding["attacks"] = attacks

        # Data sources
        source_products = data.get("source_products")
        if source_products and isinstance(source_products, list):
            finding["data_sources"] = source_products

        # Created time
        created_timestamp = data.get("created_timestamp")
        if created_timestamp:
            finding["created_time"] = created_timestamp

        return finding

    @staticmethod
    def _build_attacks(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build OCSF attacks[] from CrowdStrike tactic/technique fields."""
        attacks: list[dict[str, Any]] = []

        tactic = data.get("tactic")
        tactic_id = data.get("tactic_id")
        technique = data.get("technique")
        technique_id = data.get("technique_id")

        if not (tactic or tactic_id or technique or technique_id):
            return attacks

        entry: dict[str, Any] = {}

        if tactic or tactic_id:
            tactic_obj: dict[str, Any] = {}
            if tactic_id:
                tactic_obj["uid"] = tactic_id
            if tactic:
                tactic_obj["name"] = tactic
            entry["tactic"] = tactic_obj

        if technique or technique_id:
            tech_obj: dict[str, Any] = {}
            if technique_id:
                tech_obj["uid"] = technique_id
            if technique:
                tech_obj["name"] = technique
            entry["technique"] = tech_obj

        attacks.append(entry)
        return attacks

    @staticmethod
    def _build_device(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device object from CrowdStrike host fields."""
        hostname = data.get("hostname")
        local_ip = data.get("local_ip")
        external_ip = data.get("external_ip")
        mac_address = data.get("mac_address")

        if not (hostname or local_ip or external_ip or mac_address):
            return

        device: dict[str, Any] = {}
        if hostname:
            device["hostname"] = hostname
            device["name"] = hostname
        if local_ip:
            device["ip"] = local_ip
        if mac_address:
            device["mac"] = mac_address

        ocsf["device"] = device

    @staticmethod
    def _build_actor(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor object from CrowdStrike user fields."""
        user_name = data.get("user_name")
        if not user_name:
            return

        ocsf["actor"] = {
            "user": {
                "name": user_name,
            }
        }

    @staticmethod
    def _build_observables(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF observables from CrowdStrike IOC fields.

        Only public IPs become observables (internal IPs go to device).
        """
        observables: list[dict[str, Any]] = []

        # Public IPs as observables
        for ip_field in ("external_ip", "local_ip"):
            ip_val = data.get(ip_field)
            if ip_val and is_public_ip(ip_val):
                observables.append(
                    {
                        "type_id": 2,
                        "type": "IP Address",
                        "name": ip_field,
                        "value": ip_val,
                    }
                )

        # File hashes
        sha256 = data.get("sha256")
        if sha256:
            observables.append(
                {
                    "type_id": 8,
                    "type": "Hash",
                    "name": "SHA-256",
                    "value": sha256,
                }
            )

        md5 = data.get("md5")
        if md5:
            observables.append(
                {
                    "type_id": 8,
                    "type": "Hash",
                    "name": "MD5",
                    "value": md5,
                }
            )

        if observables:
            ocsf["observables"] = observables

    @staticmethod
    def _build_evidences(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF evidences from CrowdStrike process/file fields."""
        evidences: list[dict[str, Any]] = []

        # Process evidence
        cmdline = data.get("cmdline")
        parent_cmdline = data.get("parent_cmdline")
        process_id = data.get("process_id")
        parent_process_id = data.get("parent_process_id")

        if cmdline or parent_cmdline or process_id:
            evidence: dict[str, Any] = {}
            process_obj: dict[str, Any] = {}

            if cmdline:
                process_obj["cmd_line"] = cmdline
            if process_id:
                process_obj["uid"] = process_id

            if parent_cmdline or parent_process_id:
                parent_obj: dict[str, Any] = {}
                if parent_cmdline:
                    parent_obj["cmd_line"] = parent_cmdline
                if parent_process_id:
                    parent_obj["uid"] = parent_process_id
                process_obj["parent_process"] = parent_obj

            evidence["process"] = process_obj
            evidences.append(evidence)

        # File evidence
        filename = data.get("filename")
        filepath = data.get("filepath")
        sha256 = data.get("sha256")
        md5 = data.get("md5")

        if filename or filepath or sha256 or md5:
            file_evidence: dict[str, Any] = {}
            file_obj: dict[str, Any] = {}

            if filename:
                file_obj["name"] = filename
            if filepath:
                file_obj["path"] = filepath

            hashes: list[dict[str, str]] = []
            if sha256:
                hashes.append({"algorithm": "SHA-256", "value": sha256})
            if md5:
                hashes.append({"algorithm": "MD5", "value": md5})
            if hashes:
                file_obj["hashes"] = hashes

            file_evidence["file"] = file_obj
            evidences.append(file_evidence)

        if evidences:
            ocsf["evidences"] = evidences
