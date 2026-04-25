"""Chronicle detection alert -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from Chronicle detection
alerts (from the Detection Engine API) by mapping Chronicle UDM event
fields to OCSF structure.  Direct OCSF output.

Chronicle detection alerts contain:
- detection[].ruleName, ruleType, severity, description, detectionTime
- detection[].events[] — UDM events with principal, target, src, network
- detection[].ruleLabels[] — key-value labels (may include MITRE info)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.helpers.ip_classification import is_public_ip
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# -- Severity mapping ----------------------------------------------------------

SEVERITY_TO_OCSF: dict[str, tuple[int, str]] = {
    "low": (2, "Low"),
    "medium": (3, "Medium"),
    "high": (4, "High"),
    "critical": (5, "Critical"),
    "informational": (1, "Info"),
    "info": (1, "Info"),
}

# -- Status mapping (Chronicle alert state) ------------------------------------

_ALERT_STATE_TO_OCSF: dict[str, tuple[int, str]] = {
    "alerting": (1, "New"),
    "not_alerting": (3, "Closed"),
}

# -- OCSF observable type constants -------------------------------------------

_OBS_IP = (2, "IP Address")
_OBS_HOSTNAME = (1, "Hostname")
_OBS_DOMAIN = (1, "Hostname")
_OBS_URL = (6, "URL String")


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 / RFC 3339 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _normalize_severity(value: Any) -> str:
    """Normalize Chronicle severity string to canonical lowercase form."""
    if value is None:
        return "info"
    normalized = str(value).lower().strip()
    return normalized if normalized in SEVERITY_TO_OCSF else "info"


def _get_nested(data: dict, dotted_key: str, default: Any = None) -> Any:
    """Get nested dict value using dot notation."""
    keys = dotted_key.split(".")
    val: Any = data
    for key in keys:
        if isinstance(val, dict):
            val = val.get(key)
        else:
            return default
    return val if val is not None else default


def _build_endpoint(section: dict[str, Any]) -> dict[str, Any]:
    """Build an OCSF endpoint dict from a UDM section (principal/target/src)."""
    ip_list = section.get("ip", [])
    port = section.get("port")

    if not ip_list and port is None:
        return {}

    ep: dict[str, Any] = {}
    if ip_list:
        if isinstance(ip_list, list) and ip_list:
            ep["ip"] = ip_list[0]
        elif isinstance(ip_list, str):
            ep["ip"] = ip_list
    if port is not None:
        ep["port"] = port
    return ep


def _build_connection_info(network: dict[str, Any]) -> dict[str, Any]:
    """Build an OCSF connection_info dict from a UDM network section."""
    app_protocol = network.get("applicationProtocol", "")
    direction = network.get("direction", "")

    if not app_protocol and not direction:
        return {}

    conn: dict[str, Any] = {}
    if app_protocol:
        conn["protocol_name"] = app_protocol
    if direction:
        dl = str(direction).upper()
        if dl == "INBOUND":
            conn["direction_id"] = 1
        elif dl == "OUTBOUND":
            conn["direction_id"] = 2
    return conn


class ChronicleOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for Chronicle detection alerts -> OCSF Detection Finding.

    Maps Chronicle Detection Engine alerts (UDM-native) directly to OCSF
    Detection Finding v1.8.0 structure.

    Expected input format:
        {
            "id": "de_...",
            "type": "RULE_DETECTION",
            "detection": [{
                "ruleName": "...",
                "ruleType": "SINGLE_EVENT" | "MULTI_EVENT",
                "severity": "HIGH",
                "description": "...",
                "detectionTime": "2026-04-26T10:00:00Z",
                "events": [{ principal, target, src, network, ... }],
                "ruleLabels": [{"key": "...", "value": "..."}],
            }],
        }
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert Chronicle detection alert to OCSF Detection Finding.

        Args:
            data: Raw Chronicle detection alert document.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
        ocsf: dict[str, Any] = {}

        # -- OCSF scaffold ----------------------------------------------------
        ocsf["class_uid"] = 2004
        ocsf["class_name"] = "Detection Finding"
        ocsf["category_uid"] = 2
        ocsf["category_name"] = "Findings"
        ocsf["activity_id"] = 1
        ocsf["activity_name"] = "Create"
        ocsf["type_uid"] = 200401
        ocsf["type_name"] = "Detection Finding: Create"

        # Extract the first detection entry (Chronicle nests under detection[])
        detections = data.get("detection", [])
        det = detections[0] if detections else {}

        rule_name = det.get("ruleName", "")
        rule_description = det.get("description", "")
        detection_time = det.get("detectionTime")

        # -- Title / message ---------------------------------------------------
        ocsf["message"] = rule_description or rule_name or "Unknown Detection"

        # -- Time --------------------------------------------------------------
        if detection_time:
            ocsf["time"] = _iso_to_epoch_ms(detection_time)
            ocsf["time_dt"] = detection_time

        # -- Severity ----------------------------------------------------------
        raw_severity = det.get("severity", "INFORMATIONAL")
        sev = _normalize_severity(raw_severity)
        sev_id, sev_label = SEVERITY_TO_OCSF.get(sev, (1, "Info"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # -- Metadata ----------------------------------------------------------
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Google",
                "name": "Chronicle",
            },
        }

        detection_id = data.get("id", "")
        if detection_id:
            metadata["event_code"] = detection_id

        # Collect rule labels as metadata labels
        rule_labels = det.get("ruleLabels", [])
        if rule_labels:
            labels = [
                f"{lbl['key']}:{lbl['value']}"
                for lbl in rule_labels
                if isinstance(lbl, dict)
            ]
            if labels:
                metadata["labels"] = labels

        ocsf["metadata"] = metadata

        # -- Finding info ------------------------------------------------------
        ocsf["finding_info"] = self._build_finding_info(
            data, det, rule_name, rule_description, detection_time
        )

        # -- Chronicle detections are always alertable -------------------------
        ocsf["is_alert"] = True

        # -- Status ------------------------------------------------------------
        alert_state = data.get("alertState", "ALERTING")
        state_key = str(alert_state).lower()
        status_id, status_label = _ALERT_STATE_TO_OCSF.get(state_key, (1, "New"))
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # -- Disposition (Chronicle does not provide disposition) ---------------
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # -- Raw data ----------------------------------------------------------
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # -- Extract from UDM events -------------------------------------------
        events = det.get("events", [])
        first_event = events[0] if events else {}

        # -- Device (from principal) -------------------------------------------
        self._build_device(first_event, ocsf)

        # -- Actor (from principal.user) ---------------------------------------
        self._build_actor(first_event, ocsf)

        # -- Observables (public IPs, hostnames) -------------------------------
        self._build_observables(events, ocsf)

        # -- Evidences (network endpoints, connection info) --------------------
        self._build_evidences(events, ocsf)

        # -- Unmapped fields ---------------------------------------------------
        unmapped = self._collect_unmapped(data, det, events)
        if unmapped:
            ocsf["unmapped"] = unmapped

        return ocsf

    # -- Private builders ------------------------------------------------------

    def _build_finding_info(
        self,
        data: dict[str, Any],
        det: dict[str, Any],
        rule_name: str,
        rule_description: str,
        detection_time: str | None,
    ) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        detection_id = data.get("id", "")

        finding: dict[str, Any] = {
            "uid": detection_id,
            "title": rule_description or rule_name or "Unknown Detection",
        }

        # Analytic (the detection rule)
        if rule_name:
            analytic: dict[str, Any] = {
                "name": rule_name,
                "type_id": 1,
                "type": "Rule",
            }
            rule_id = det.get("ruleId", "")
            if rule_id:
                analytic["uid"] = rule_id
            finding["analytic"] = analytic

        # Description
        if rule_description:
            finding["desc"] = rule_description

        # Rule type -> finding types
        rule_type = det.get("ruleType", "")
        finding["types"] = [rule_type] if rule_type else []

        # Created time
        if detection_time:
            finding["created_time_dt"] = detection_time

        # MITRE ATT&CK from ruleLabels
        attacks = self._build_attacks_from_labels(det.get("ruleLabels", []))
        if attacks:
            finding["attacks"] = attacks

        return finding

    @staticmethod
    def _build_attacks_from_labels(
        labels: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Extract MITRE ATT&CK from Chronicle ruleLabels.

        Chronicle stores MITRE info in ruleLabels with keys like:
        - "tactic": "TA0001"
        - "tactic_name": "Initial Access"
        - "technique": "T1078"
        - "technique_name": "Valid Accounts"
        """
        if not labels:
            return []

        label_map: dict[str, str] = {}
        for lbl in labels:
            if isinstance(lbl, dict) and "key" in lbl and "value" in lbl:
                label_map[lbl["key"].lower()] = lbl["value"]

        tactic_uid = label_map.get("tactic", "")
        tactic_name = label_map.get("tactic_name", "")
        technique_uid = label_map.get("technique", "")
        technique_name = label_map.get("technique_name", "")
        subtechnique_uid = label_map.get("subtechnique", "")
        subtechnique_name = label_map.get("subtechnique_name", "")

        if not tactic_uid and not technique_uid:
            return []

        attack: dict[str, Any] = {}

        if tactic_uid or tactic_name:
            tactic: dict[str, Any] = {}
            if tactic_uid:
                tactic["uid"] = tactic_uid
            if tactic_name:
                tactic["name"] = tactic_name
            attack["tactic"] = tactic

        if technique_uid or technique_name:
            technique: dict[str, Any] = {}
            if technique_uid:
                technique["uid"] = technique_uid
            if technique_name:
                technique["name"] = technique_name
            attack["technique"] = technique

        if subtechnique_uid or subtechnique_name:
            sub: dict[str, Any] = {}
            if subtechnique_uid:
                sub["uid"] = subtechnique_uid
            if subtechnique_name:
                sub["name"] = subtechnique_name
            attack["sub_technique"] = sub

        return [attack] if attack else []

    @staticmethod
    def _build_device(event: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device from UDM principal fields."""
        principal = event.get("principal", {})
        if not principal:
            return

        hostname = principal.get("hostname", "")
        ip_list = principal.get("ip", [])
        asset_id = principal.get("assetId", "")

        if not hostname and not ip_list and not asset_id:
            return

        device: dict[str, Any] = {"type_id": 0}

        if hostname:
            device["hostname"] = hostname

        if ip_list:
            if isinstance(ip_list, list) and ip_list:
                device["ip"] = ip_list[0]
            elif isinstance(ip_list, str):
                device["ip"] = ip_list

        if asset_id:
            device["uid"] = asset_id

        ocsf["device"] = device

    @staticmethod
    def _build_actor(event: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor from UDM principal.user fields."""
        principal = event.get("principal", {})
        user_data = principal.get("user", {})
        if not user_data:
            return

        user_id = user_data.get("userid", "")
        user_name = user_data.get("windowsSid", "") or user_data.get("userid", "")
        email = user_data.get("emailAddresses", [])

        if not user_id and not user_name and not email:
            return

        user: dict[str, Any] = {}
        if user_id:
            user["uid"] = user_id
        if user_name:
            user["name"] = user_name
        if email:
            if isinstance(email, list) and email:
                user["email_addr"] = email[0]
            elif isinstance(email, str):
                user["email_addr"] = email

        ocsf["actor"] = {"user": user}

    @staticmethod
    def _build_observables(events: list[dict[str, Any]], ocsf: dict[str, Any]) -> None:
        """Build OCSF observables from UDM event fields.

        Only public IPs and hostnames go into observables.
        Private IPs go into device or evidences, NOT observables.
        """
        observables: list[dict[str, Any]] = []
        seen_values: set[str] = set()

        def _add_observable(
            value: str, type_id: int, type_name: str, name: str
        ) -> None:
            if not value or value in seen_values:
                return
            seen_values.add(value)
            observables.append(
                {
                    "type_id": type_id,
                    "type": type_name,
                    "value": value,
                    "name": name,
                }
            )

        for evt in events:
            # IPs from principal, target, src
            for section_name in ["principal", "target", "src"]:
                section = evt.get(section_name, {})
                if not section:
                    continue

                ip_list = section.get("ip", [])
                if isinstance(ip_list, str):
                    ip_list = [ip_list]
                for ip_val in ip_list:
                    if ip_val and is_public_ip(ip_val):
                        _add_observable(
                            ip_val, _OBS_IP[0], _OBS_IP[1], f"{section_name}.ip"
                        )

                hostname = section.get("hostname", "")
                if hostname:
                    _add_observable(
                        hostname,
                        _OBS_HOSTNAME[0],
                        _OBS_HOSTNAME[1],
                        f"{section_name}.hostname",
                    )

                # URL from target
                url = section.get("url", "")
                if url:
                    _add_observable(
                        url, _OBS_URL[0], _OBS_URL[1], f"{section_name}.url"
                    )

            # Domain from network.dns
            network = evt.get("network", {})
            dns = network.get("dns", {})
            if isinstance(dns, dict):
                dns_domain = dns.get("domain", "")
                if dns_domain:
                    _add_observable(
                        dns_domain,
                        _OBS_DOMAIN[0],
                        _OBS_DOMAIN[1],
                        "network.dns.domain",
                    )

        if observables:
            ocsf["observables"] = observables

    @staticmethod
    def _build_evidences(events: list[dict[str, Any]], ocsf: dict[str, Any]) -> None:
        """Build OCSF evidences from UDM network endpoints and connection info."""
        evidences: list[dict[str, Any]] = []

        for evt in events:
            evidence: dict[str, Any] = {}

            # Source endpoint (from principal or src)
            principal = evt.get("principal", {})
            src_section = evt.get("src", {})
            src_data = src_section if src_section else principal
            src_ep = _build_endpoint(src_data)
            if src_ep:
                evidence["src_endpoint"] = src_ep

            # Destination endpoint (from target)
            dst_ep = _build_endpoint(evt.get("target", {}))
            if dst_ep:
                evidence["dst_endpoint"] = dst_ep

            # Connection info (from network)
            conn = _build_connection_info(evt.get("network", {}))
            if conn:
                evidence["connection_info"] = conn

            if evidence:
                evidences.append(evidence)

        if evidences:
            ocsf["evidences"] = evidences

    @staticmethod
    def _collect_unmapped(
        data: dict[str, Any],
        det: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Collect Chronicle-specific fields not mapped to OCSF."""
        unmapped: dict[str, Any] = {}

        # Detection type
        detection_type = data.get("type", "")
        if detection_type:
            unmapped["detection_type"] = detection_type

        # Rule version
        rule_version = det.get("ruleVersion", "")
        if rule_version:
            unmapped["rule_version"] = rule_version

        # Rule set
        rule_set = det.get("ruleSet", "")
        if rule_set:
            unmapped["rule_set"] = rule_set

        # Alert state
        alert_state = data.get("alertState", "")
        if alert_state:
            unmapped["alert_state"] = alert_state

        # Security result from first event
        if events:
            first_evt = events[0]
            sec_results = first_evt.get("securityResult", [])
            if sec_results:
                unmapped["security_result"] = sec_results

        return unmapped
