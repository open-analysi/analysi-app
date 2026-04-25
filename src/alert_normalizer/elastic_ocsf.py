"""Elastic Security Alert -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from Elastic Security alert
documents (from the `.alerts-security.alerts-default` index) by mapping ECS
fields to OCSF structure.  Direct OCSF output.
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

SEVERITY_TO_OCSF: dict[str, tuple[int, str]] = {
    "info": (1, "Info"),
    "low": (2, "Low"),
    "medium": (3, "Medium"),
    "high": (4, "High"),
    "critical": (5, "Critical"),
}

# Risk score -> OCSF risk_level_id thresholds (upper-bound inclusive)
_RISK_LEVEL_BUCKETS: list[tuple[int, int, str]] = [
    (20, 0, "Info"),
    (40, 1, "Low"),
    (60, 2, "Medium"),
    (80, 3, "High"),
    (101, 4, "Critical"),  # 101 to catch score=100
]

# Elastic workflow_status -> OCSF status mapping
_WORKFLOW_STATUS_TO_OCSF: dict[str, tuple[int, str]] = {
    "open": (1, "New"),
    "acknowledged": (2, "In Progress"),
    "closed": (3, "Closed"),
}

# IOC type string -> OCSF observable (type_id, type_name)
IOC_TYPE_TO_OBSERVABLE: dict[str, tuple[int, str]] = {
    "ip": (2, "IP Address"),
    "domain": (1, "Hostname"),
    "hash": (8, "Hash"),
    "url": (6, "URL String"),
}


def _risk_score_to_level(score: int) -> tuple[int, str]:
    """Map 0-100 risk score to OCSF risk_level_id and label."""
    for upper, level_id, label in _RISK_LEVEL_BUCKETS:
        if score < upper:
            return level_id, label
    return 4, "Critical"


def _get_nested(data: dict, dotted_key: str, default: Any = None) -> Any:
    """Get nested dict value using dot notation: 'kibana.alert.severity'."""
    keys = dotted_key.split(".")
    val: Any = data
    for key in keys:
        if isinstance(val, dict):
            val = val.get(key)
        else:
            return default
    return val if val is not None else default


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _normalize_severity(value: Any) -> str:
    """Normalize Elastic severity string to canonical form."""
    if value is None:
        return "info"
    normalized = str(value).lower().strip()
    severity_map = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "info": "info",
        "informational": "info",
    }
    return severity_map.get(normalized, "info")


def _looks_like_ip(value: str) -> bool:
    """Heuristic: contains dots and all parts are digits (IPv4)."""
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


def _build_tactic_obj(tactic_data: dict[str, Any]) -> dict[str, Any] | None:
    """Build OCSF tactic object from Elastic threat tactic."""
    if not isinstance(tactic_data, dict):
        return None
    obj: dict[str, Any] = {}
    if tactic_data.get("id"):
        obj["uid"] = tactic_data["id"]
    if tactic_data.get("name"):
        obj["name"] = tactic_data["name"]
    return obj if obj else None


def _parse_threat_entry(
    threat_entry: dict[str, Any], attacks: list[dict[str, Any]]
) -> None:
    """Parse a single MITRE threat entry into OCSF attack objects."""
    tactic_obj = _build_tactic_obj(threat_entry.get("tactic", {}))
    techniques = threat_entry.get("technique", [])
    if not isinstance(techniques, list):
        techniques = []

    if not techniques and tactic_obj:
        attacks.append({"tactic": tactic_obj})
        return

    for technique in techniques:
        if not isinstance(technique, dict):
            continue
        entry: dict[str, Any] = {}
        if tactic_obj:
            entry["tactic"] = tactic_obj
        tech_obj: dict[str, Any] = {}
        if technique.get("id"):
            tech_obj["uid"] = technique["id"]
        if technique.get("name"):
            tech_obj["name"] = technique["name"]
        if tech_obj:
            entry["technique"] = tech_obj

        subtechniques = technique.get("subtechnique", [])
        if isinstance(subtechniques, list) and subtechniques:
            for sub in subtechniques:
                if isinstance(sub, dict):
                    sub_entry = dict(entry)
                    sub_entry["sub_technique"] = {}
                    if sub.get("id"):
                        sub_entry["sub_technique"]["uid"] = sub["id"]
                    if sub.get("name"):
                        sub_entry["sub_technique"]["name"] = sub["name"]
                    attacks.append(sub_entry)
        else:
            attacks.append(entry)


def _add_network_evidence(data: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Add network endpoints and connection info to evidence dict."""
    src_ip = _get_nested(data, "source.ip")
    src_port = _get_nested(data, "source.port")
    if src_ip or src_port:
        src_ep: dict[str, Any] = {}
        if src_ip:
            src_ep["ip"] = src_ip
        if src_port is not None:
            src_ep["port"] = src_port
        evidence["src_endpoint"] = src_ep

    dst_ip = _get_nested(data, "destination.ip")
    dst_port = _get_nested(data, "destination.port")
    if dst_ip or dst_port:
        dst_ep: dict[str, Any] = {}
        if dst_ip:
            dst_ep["ip"] = dst_ip
        if dst_port is not None:
            dst_ep["port"] = dst_port
        evidence["dst_endpoint"] = dst_ep

    protocol = _get_nested(data, "network.protocol")
    direction = _get_nested(data, "network.direction")
    if protocol or direction:
        conn: dict[str, Any] = {}
        if protocol:
            conn["protocol_name"] = protocol
        if direction:
            dl = str(direction).lower()
            if dl == "inbound":
                conn["direction_id"] = 1
            elif dl == "outbound":
                conn["direction_id"] = 2
        evidence["connection_info"] = conn


def _add_process_evidence(data: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Add process info to evidence dict."""
    proc_name = _get_nested(data, "process.name")
    proc_pid = _get_nested(data, "process.pid")
    proc_exe = _get_nested(data, "process.executable")
    proc_cmd = _get_nested(data, "process.command_line")
    proc_parent = _get_nested(data, "process.parent.name")

    if not (proc_name or proc_pid is not None or proc_exe or proc_cmd):
        return

    process_obj: dict[str, Any] = {}
    if proc_name:
        process_obj["name"] = proc_name
    if proc_pid is not None:
        process_obj["pid"] = proc_pid
    if proc_cmd:
        process_obj["cmd_line"] = proc_cmd
    if proc_exe:
        process_obj["file"] = {"path": proc_exe}
    if proc_parent:
        process_obj["parent_process"] = {"name": proc_parent}
    evidence["process"] = process_obj


def _add_url_evidence(data: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Add URL info to evidence dict."""
    url_full = _get_nested(data, "url.full")
    url_path = _get_nested(data, "url.path")
    url_domain = _get_nested(data, "url.domain")
    if url_full or url_path:
        url_obj: dict[str, Any] = {}
        if url_full:
            url_obj["url_string"] = url_full
        if url_path:
            url_obj["path"] = url_path
        if url_domain:
            url_obj["hostname"] = url_domain
        evidence["url"] = url_obj


def _add_file_evidence(data: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Add file info to evidence dict."""
    file_name = _get_nested(data, "file.name")
    file_path = _get_nested(data, "file.path")
    file_sha256 = _get_nested(data, "file.hash.sha256")
    file_md5 = _get_nested(data, "file.hash.md5")
    if not (file_name or file_path or file_sha256 or file_md5):
        return
    file_obj: dict[str, Any] = {}
    if file_name:
        file_obj["name"] = file_name
    if file_path:
        file_obj["path"] = file_path
    hashes: list[dict[str, str]] = []
    if file_sha256:
        hashes.append({"algorithm": "SHA-256", "value": file_sha256})
    if file_md5:
        hashes.append({"algorithm": "MD5", "value": file_md5})
    if hashes:
        file_obj["hashes"] = hashes
    evidence["file"] = file_obj


class ElasticOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for Elastic Security alerts -> OCSF Detection Finding.

    Maps Elastic Security alert documents (ECS-native) directly to OCSF
    Detection Finding v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert Elastic Security alert to OCSF Detection Finding.

        Args:
            data: Raw Elastic Security alert document.

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
        reason = _get_nested(data, "kibana.alert.reason")
        rule_name = _get_nested(data, "kibana.alert.rule.name")
        ocsf["message"] = reason or rule_name or "Unknown Alert"

        # ── Time ─────────────────────────────────────────────────────
        original_time = _get_nested(data, "kibana.alert.original_time")
        alert_timestamp = data.get("@timestamp")
        event_time = original_time or alert_timestamp

        if event_time:
            ocsf["time"] = _iso_to_epoch_ms(event_time)
            ocsf["time_dt"] = event_time

        # ocsf_time uses @timestamp (when Elastic created the alert)
        if alert_timestamp:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(alert_timestamp)

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = _get_nested(data, "kibana.alert.severity", "info")
        sev = _normalize_severity(raw_severity)
        sev_id, sev_label = SEVERITY_TO_OCSF.get(sev, (1, "Info"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Elastic",
                "name": "Security",
            },
        }

        rule_tags = _get_nested(data, "kibana.alert.rule.tags")
        if rule_tags and isinstance(rule_tags, list):
            metadata["labels"] = rule_tags

        alert_uuid = _get_nested(data, "kibana.alert.uuid")
        if alert_uuid:
            metadata["event_code"] = alert_uuid

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data, reason, rule_name)

        # ── Elastic alerts are always alertable findings ─────────────
        ocsf["is_alert"] = True

        # ── Status ───────────────────────────────────────────────────
        workflow_status = _get_nested(data, "kibana.alert.workflow_status", "open")
        status_id, status_label = _WORKFLOW_STATUS_TO_OCSF.get(
            str(workflow_status).lower(), (1, "New")
        )
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # ── Risk score ───────────────────────────────────────────────
        risk_score = _get_nested(data, "kibana.alert.risk_score")
        if risk_score is not None:
            try:
                ocsf["risk_score"] = int(float(risk_score))
                level_id, level_label = _risk_score_to_level(ocsf["risk_score"])
                ocsf["risk_level_id"] = level_id
                ocsf["risk_level"] = level_label
            except (ValueError, TypeError):
                pass

        # ── Disposition + Action (defaults — Elastic doesn't set these) ──
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Device (from host ECS fields) ────────────────────────────
        self._build_device(data, ocsf)

        # ── Actor (from user ECS fields) ─────────────────────────────
        self._build_actor(data, ocsf)

        # ── Observables (public IPs, domains, hashes, URLs) ──────────
        self._build_observables(data, ocsf)

        # ── Evidences (from network/process/file info) ───────────────
        self._build_evidences(data, ocsf)

        # ── Unmapped fields ──────────────────────────────────────────
        unmapped = self._collect_unmapped(data)
        if unmapped:
            ocsf["unmapped"] = unmapped

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    def _build_finding_info(
        self,
        data: dict[str, Any],
        reason: str | None,
        rule_name: str | None,
    ) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        alert_uuid = _get_nested(data, "kibana.alert.uuid")

        finding: dict[str, Any] = {
            "uid": alert_uuid or "",
            "title": reason or rule_name or "Unknown Alert",
        }

        # Analytic (the detection rule)
        if rule_name:
            analytic: dict[str, Any] = {
                "name": rule_name,
                "type_id": 1,
                "type": "Rule",
            }
            rule_uuid = _get_nested(data, "kibana.alert.rule.uuid")
            if rule_uuid:
                analytic["uid"] = rule_uuid
            finding["analytic"] = analytic

        # Rule description
        rule_desc = _get_nested(data, "kibana.alert.rule.description")
        if rule_desc:
            finding["desc"] = rule_desc

        # Rule type -> finding types
        rule_type = _get_nested(data, "kibana.alert.rule.type")
        finding["types"] = [rule_type] if rule_type else []

        # Created time
        alert_timestamp = data.get("@timestamp")
        if alert_timestamp:
            finding["created_time_dt"] = alert_timestamp

        # MITRE ATT&CK
        attacks = self._build_attacks(data)
        if attacks:
            finding["attacks"] = attacks

        return finding

    @staticmethod
    def _build_attacks(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract MITRE ATT&CK from kibana.alert.rule.threat array."""
        threats = _get_nested(data, "kibana.alert.rule.threat")
        if not threats or not isinstance(threats, list):
            return []

        attacks: list[dict[str, Any]] = []
        for threat_entry in threats:
            if not isinstance(threat_entry, dict):
                continue
            framework = threat_entry.get("framework", "")
            if framework and "MITRE" not in framework.upper():
                continue
            _parse_threat_entry(threat_entry, attacks)
        return attacks

    @staticmethod
    def _build_device(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device from ECS host fields."""
        hostname = _get_nested(data, "host.name") or _get_nested(data, "host.hostname")
        host_ips = _get_nested(data, "host.ip")
        os_name = _get_nested(data, "host.os.name")

        if not hostname and not host_ips and not os_name:
            return

        device: dict[str, Any] = {"type_id": 0}

        if hostname:
            device["hostname"] = hostname

        if host_ips:
            # host.ip can be a string or list
            if isinstance(host_ips, list) and host_ips:
                device["ip"] = host_ips[0]
            elif isinstance(host_ips, str):
                device["ip"] = host_ips

        if os_name:
            device["os"] = {"name": os_name}

        ocsf["device"] = device

    @staticmethod
    def _build_actor(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor from ECS user fields."""
        user_name = _get_nested(data, "user.name")
        user_id = _get_nested(data, "user.id")
        user_domain = _get_nested(data, "user.domain")

        if not user_name and not user_id:
            return

        user: dict[str, Any] = {}
        if user_name:
            user["name"] = user_name
        if user_id:
            user["uid"] = str(user_id)
        if user_domain:
            user["domain"] = user_domain

        ocsf["actor"] = {"user": user}

    @staticmethod
    def _build_observables(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF observables from ECS fields.

        Only public IPs, domains, hashes, and URLs go into observables.
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

        # Public IPs from source/destination
        for ip_field in ["source.ip", "destination.ip"]:
            ip_val = _get_nested(data, ip_field)
            if ip_val and isinstance(ip_val, str) and is_public_ip(ip_val):
                _add_observable(ip_val, 2, "IP Address", "dst_endpoint.ip")

        # Domains from url.domain, dns.question.name
        for domain_field in ["url.domain", "dns.question.name"]:
            domain_val = _get_nested(data, domain_field)
            if domain_val and isinstance(domain_val, str):
                _add_observable(domain_val, 1, "Hostname", "dst_endpoint.domain")

        # File hashes
        for _algo, field in [
            ("SHA-256", "file.hash.sha256"),
            ("MD5", "file.hash.md5"),
        ]:
            hash_val = _get_nested(data, field)
            if hash_val and isinstance(hash_val, str):
                _add_observable(hash_val, 8, "Hash", "file.hashes")

        # URLs
        url_full = _get_nested(data, "url.full")
        if url_full and isinstance(url_full, str):
            _add_observable(url_full, 6, "URL String", "url.url_string")

        if observables:
            ocsf["observables"] = observables

    @staticmethod
    def _build_evidences(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF evidences from ECS network, process, file fields."""
        evidence: dict[str, Any] = {}
        _add_network_evidence(data, evidence)
        _add_process_evidence(data, evidence)
        _add_url_evidence(data, evidence)
        _add_file_evidence(data, evidence)
        if evidence:
            ocsf["evidences"] = [evidence]

    @staticmethod
    def _collect_unmapped(data: dict[str, Any]) -> dict[str, Any]:
        """Collect Elastic-specific fields not mapped to OCSF."""
        unmapped: dict[str, Any] = {}

        # Agent info (Elastic Agent metadata)
        agent_name = _get_nested(data, "agent.name")
        agent_type = _get_nested(data, "agent.type")
        if agent_name or agent_type:
            agent_info: dict[str, Any] = {}
            if agent_name:
                agent_info["name"] = agent_name
            if agent_type:
                agent_info["type"] = agent_type
            unmapped["agent"] = agent_info

        # Cloud info
        cloud_provider = _get_nested(data, "cloud.provider")
        cloud_region = _get_nested(data, "cloud.region")
        if cloud_provider or cloud_region:
            cloud_info: dict[str, Any] = {}
            if cloud_provider:
                cloud_info["provider"] = cloud_provider
            if cloud_region:
                cloud_info["region"] = cloud_region
            unmapped["cloud"] = cloud_info

        # DNS info
        dns_name = _get_nested(data, "dns.question.name")
        dns_type = _get_nested(data, "dns.question.type")
        if dns_name or dns_type:
            dns_info: dict[str, Any] = {}
            if dns_name:
                dns_info["question_name"] = dns_name
            if dns_type:
                dns_info["question_type"] = dns_type
            unmapped["dns"] = dns_info

        # Kibana alert URL
        alert_url = _get_nested(data, "kibana.alert.url")
        if alert_url:
            unmapped["kibana_alert_url"] = alert_url

        return unmapped
