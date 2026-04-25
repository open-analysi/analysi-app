"""Palo Alto Cortex XDR Alert -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from Cortex XDR
alert documents (from the ``/public_api/v1/alerts/get_alerts_multi_events``
endpoint) by mapping Cortex XDR fields to OCSF structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.helpers.ip_classification import is_public_ip
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

# Cortex XDR severity string -> OCSF severity_id / label
SEVERITY_STR_TO_OCSF: dict[str, tuple[int, str]] = {
    "informational": (1, "Informational"),
    "info": (1, "Informational"),
    "low": (2, "Low"),
    "medium": (3, "Medium"),
    "high": (4, "High"),
    "critical": (5, "Critical"),
}

# Cortex XDR action_pretty -> OCSF disposition mapping
_ACTION_TO_DISPOSITION: dict[str, tuple[int, str]] = {
    "blocked": (2, "Blocked"),
    "prevented": (2, "Blocked"),
    "quarantined": (3, "Quarantined"),
    "detected": (15, "Detected"),
    "allowed": (1, "Allowed"),
}

# Regex for parsing MITRE from "TA0001 - Initial Access" format
_MITRE_PATTERN = re.compile(r"^(T[A0-9.]+)\s*-\s*(.+)$")


def _epoch_ms_to_iso(ts_ms: int | float) -> str:
    """Convert epoch milliseconds to ISO 8601 string."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
    return dt.isoformat()


class CortexXDROCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for Cortex XDR alerts -> OCSF Detection Finding.

    Maps Cortex XDR alert documents directly to OCSF Detection Finding
    v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert Cortex XDR alert to OCSF Detection Finding.

        Args:
            data: Raw Cortex XDR alert document.

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

        # ── Title / message ──────────────────────────────���───────────
        alert_name = data.get("alert_name")
        description = data.get("description")
        ocsf["message"] = alert_name or description or "Unknown Alert"

        # ── Time ─────────────────────────────────────────────────────
        detection_ts = data.get("detection_timestamp")
        if detection_ts is not None:
            try:
                ts_ms = int(detection_ts)
                ocsf["time"] = ts_ms
                ocsf["time_dt"] = _epoch_ms_to_iso(ts_ms)
            except (ValueError, TypeError):
                pass

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = data.get("severity")
        sev_id, sev_label = self._map_severity(raw_severity)
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ────────────────────��────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Palo Alto Networks",
                "name": "Cortex XDR",
            },
        }

        source = data.get("source")
        if source:
            metadata["labels"] = [f"source:{source}"]

        alert_id = data.get("alert_id")
        if alert_id is not None:
            metadata["event_code"] = str(alert_id)

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data)

        # ── Cortex XDR alerts are always alertable findings ──────────
        ocsf["is_alert"] = True

        # ── Status (Cortex XDR alerts are always new when pulled) ────
        ocsf["status_id"] = 1
        ocsf["status"] = "New"

        # ── Disposition + Action ─────────────────────────────────────
        action_pretty = str(data.get("action_pretty", "")).lower().strip()
        disp_id, disp_label = _ACTION_TO_DISPOSITION.get(action_pretty, (0, "Unknown"))
        ocsf["disposition_id"] = disp_id
        ocsf["disposition"] = disp_label
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

        # ── Evidences ───────────────────────────────────��────────────
        self._build_evidences(data, ocsf)

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    @staticmethod
    def _map_severity(raw_severity: Any) -> tuple[int, str]:
        """Map Cortex XDR severity string to OCSF severity_id."""
        if raw_severity is None:
            return 1, "Informational"
        sev_str = str(raw_severity).lower().strip()
        return SEVERITY_STR_TO_OCSF.get(sev_str, (1, "Informational"))

    def _build_finding_info(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        alert_id = data.get("alert_id")
        alert_name = data.get("alert_name")
        description = data.get("description")
        category = data.get("category")

        finding: dict[str, Any] = {
            "uid": str(alert_id) if alert_id is not None else "",
            "title": alert_name or description or "Unknown Alert",
        }

        # Analytic (the detection rule)
        if alert_name:
            analytic: dict[str, Any] = {
                "name": alert_name,
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
        source = data.get("source")
        if source:
            finding["data_sources"] = [source]

        # Types from category
        if category:
            finding["types"] = [category]

        return finding

    @staticmethod
    def _parse_mitre_field(value: str | None) -> tuple[str | None, str | None]:
        """Parse MITRE field from 'TA0001 - Initial Access' format.

        Returns:
            Tuple of (uid, name) or (None, None).
        """
        if not value:
            return None, None
        match = _MITRE_PATTERN.match(value.strip())
        if match:
            return match.group(1), match.group(2).strip()
        return None, None

    @staticmethod
    def _build_attacks(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Build OCSF attacks[] from Cortex XDR MITRE fields."""
        attacks: list[dict[str, Any]] = []

        tactic_raw = data.get("mitre_tactic_id_and_name")
        technique_raw = data.get("mitre_technique_id_and_name")

        if not tactic_raw and not technique_raw:
            return attacks

        entry: dict[str, Any] = {}

        if tactic_raw:
            tactic_id, tactic_name = CortexXDROCSFNormalizer._parse_mitre_field(
                tactic_raw
            )
            if tactic_id or tactic_name:
                tactic_obj: dict[str, Any] = {}
                if tactic_id:
                    tactic_obj["uid"] = tactic_id
                if tactic_name:
                    tactic_obj["name"] = tactic_name
                entry["tactic"] = tactic_obj

        if technique_raw:
            tech_id, tech_name = CortexXDROCSFNormalizer._parse_mitre_field(
                technique_raw
            )
            if tech_id or tech_name:
                tech_obj: dict[str, Any] = {}
                if tech_id:
                    tech_obj["uid"] = tech_id
                if tech_name:
                    tech_obj["name"] = tech_name
                entry["technique"] = tech_obj

        if entry:
            attacks.append(entry)
        return attacks

    @staticmethod
    def _build_device(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device object from Cortex XDR host fields."""
        hostname = data.get("host_name")
        host_ip = data.get("host_ip")

        if not hostname and not host_ip:
            return

        device: dict[str, Any] = {}
        if hostname:
            device["hostname"] = hostname
            device["name"] = hostname
        if host_ip:
            device["ip"] = host_ip

        ocsf["device"] = device

    @staticmethod
    def _build_actor(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor object from Cortex XDR user fields."""
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
        """Build OCSF observables from Cortex XDR IOC fields.

        Only public IPs become observables (internal IPs go to device).
        """
        observables: list[dict[str, Any]] = []

        # Public IPs as observables
        for ip_field in ("action_remote_ip", "action_local_ip"):
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
        sha256 = data.get("action_file_sha256")
        if sha256:
            observables.append(
                {
                    "type_id": 8,
                    "type": "Hash",
                    "name": "SHA-256",
                    "value": sha256,
                }
            )

        md5 = data.get("action_file_md5")
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
    def _build_process_evidence(data: dict[str, Any]) -> dict[str, Any] | None:
        """Build process evidence from action/actor process fields."""
        action_process = data.get("action_process_image_name")
        action_cmdline = data.get("action_process_image_command_line")
        actor_process = data.get("actor_process_image_name")
        actor_cmdline = data.get("actor_process_command_line")

        if not (action_process or action_cmdline or actor_process or actor_cmdline):
            return None

        process_obj: dict[str, Any] = {}
        if action_process:
            process_obj["name"] = action_process
        if action_cmdline:
            process_obj["cmd_line"] = action_cmdline

        if actor_process or actor_cmdline:
            parent_obj: dict[str, Any] = {}
            if actor_process:
                parent_obj["name"] = actor_process
            if actor_cmdline:
                parent_obj["cmd_line"] = actor_cmdline
            process_obj["parent_process"] = parent_obj

        return {"process": process_obj}

    @staticmethod
    def _build_file_evidence(data: dict[str, Any]) -> dict[str, Any] | None:
        """Build file evidence from action_file_* fields."""
        filename = data.get("action_file_name")
        filepath = data.get("action_file_path")
        sha256 = data.get("action_file_sha256")
        md5 = data.get("action_file_md5")

        if not (filename or filepath or sha256 or md5):
            return None

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

        return {"file": file_obj}

    @staticmethod
    def _build_network_evidence(data: dict[str, Any]) -> dict[str, Any] | None:
        """Build network evidence from action_remote/local IP/port fields."""
        remote_ip = data.get("action_remote_ip")
        remote_port = data.get("action_remote_port")
        local_ip = data.get("action_local_ip")

        if not (remote_ip or remote_port or local_ip):
            return None

        net_evidence: dict[str, Any] = {}
        if local_ip:
            net_evidence["src_endpoint"] = {"ip": local_ip}
        if remote_ip or remote_port:
            dst: dict[str, Any] = {}
            if remote_ip:
                dst["ip"] = remote_ip
            if remote_port is not None:
                dst["port"] = remote_port
            net_evidence["dst_endpoint"] = dst

        return net_evidence

    @staticmethod
    def _build_evidences(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF evidences from Cortex XDR process/file/network fields."""
        evidences: list[dict[str, Any]] = []

        proc_ev = CortexXDROCSFNormalizer._build_process_evidence(data)
        if proc_ev:
            evidences.append(proc_ev)

        file_ev = CortexXDROCSFNormalizer._build_file_evidence(data)
        if file_ev:
            evidences.append(file_ev)

        net_ev = CortexXDROCSFNormalizer._build_network_evidence(data)
        if net_ev:
            evidences.append(net_ev)

        if evidences:
            ocsf["evidences"] = evidences
