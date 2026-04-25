"""Splunk Notable -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from Splunk Notable events
by calling the battle-tested extraction functions in mappers/splunk_notable.py
and mappers/splunk_notable_lists.py, then mapping their output straight to
OCSF structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.mappers.splunk_notable import (
    extract_cve_info,
    extract_network_info,
    extract_other_activities,
    extract_primary_ioc,
    extract_process_info,
    extract_web_info,
    get_primary_risk_entity,
    map_security_domain_to_category,
    normalize_device_action,
)
from alert_normalizer.mappers.splunk_notable_lists import (
    extract_all_iocs,
    extract_all_risk_entities,
    is_ip_address,
    is_private_ip,
)
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

SEVERITY_TO_OCSF: dict[str, tuple[int, str]] = {
    "info": (1, "Info"),
    "low": (2, "Low"),
    "medium": (3, "Medium"),
    "high": (4, "High"),
    "critical": (5, "Critical"),
    "fatal": (6, "Fatal"),
}

DISPOSITION_TO_OCSF: dict[str, tuple[int, str]] = {
    "allowed": (1, "Allowed"),
    "blocked": (2, "Blocked"),
    "quarantined": (3, "Quarantined"),
    "terminated": (5, "Deleted"),
    "detected": (15, "Detected"),
    "unknown": (0, "Unknown"),
}

# Risk score → OCSF risk_level_id thresholds (upper-bound inclusive)
_RISK_LEVEL_BUCKETS: list[tuple[int, int, str]] = [
    (20, 0, "Info"),
    (40, 1, "Low"),
    (60, 2, "Medium"),
    (80, 3, "High"),
    (101, 4, "Critical"),  # 101 to catch score=100
]


def _risk_score_to_level(score: int) -> tuple[int, str]:
    """Map 0-100 risk score to OCSF risk_level_id and label."""
    for upper, level_id, label in _RISK_LEVEL_BUCKETS:
        if score < upper:
            return level_id, label
    return 4, "Critical"


# IOC type string -> OCSF observable (type_id, type_name)
IOC_TYPE_TO_OBSERVABLE: dict[str, tuple[int, str]] = {
    "ip": (2, "IP Address"),
    "domain": (1, "Hostname"),
    "filename": (7, "File Name"),
    "filehash": (8, "Hash"),
    "url": (6, "URL String"),
    "process": (9, "Process Name"),
    "user_agent": (16, "HTTP User-Agent"),
    "email": (5, "Email Address"),
    "mac": (3, "MAC Address"),
    "port": (11, "Port"),
}

# MITRE ATT&CK Technique Map: technique_id -> (name, tactic_id, tactic_name)
TECHNIQUE_MAP: dict[str, tuple[str, str, str]] = {
    "T1190": ("Exploit Public-Facing Application", "TA0001", "Initial Access"),
    "T1059": ("Command and Scripting Interpreter", "TA0002", "Execution"),
    "T1189": ("Drive-by Compromise", "TA0001", "Initial Access"),
    "T1078": ("Valid Accounts", "TA0001", "Initial Access"),
    "T1110": ("Brute Force", "TA0006", "Credential Access"),
    "T1005": ("Data from Local System", "TA0009", "Collection"),
    "T1548": (
        "Abuse Elevation Control Mechanism",
        "TA0004",
        "Privilege Escalation",
    ),
    "T1083": ("File and Directory Discovery", "TA0007", "Discovery"),
    "T1068": (
        "Exploitation for Privilege Escalation",
        "TA0004",
        "Privilege Escalation",
    ),
    "T1210": ("Exploitation of Remote Services", "TA0008", "Lateral Movement"),
}

# Confidence score bucketing: OCSF reputation.score_id
_CONFIDENCE_BUCKETS: list[tuple[int, int, str]] = [
    (1, 30, "Low"),
    (2, 70, "Medium"),
    (3, 100, "High"),
]


def _confidence_to_score_id(confidence: int) -> tuple[int, str]:
    """Map 0-100 confidence to OCSF reputation score_id."""
    for score_id, upper, label in _CONFIDENCE_BUCKETS:
        if confidence <= upper:
            return score_id, label
    return 3, "High"


def _normalize_severity(value: Any) -> str:
    """Normalize severity string (same logic as SplunkNotableNormalizer._normalize_enums)."""
    if value is None:
        return "info"
    normalized = str(value).lower()
    severity_map = {
        "crit": "critical",
        "critical": "critical",
        "fatal": "fatal",
        "high": "high",
        "med": "medium",
        "medium": "medium",
        "low": "low",
        "info": "info",
        "informational": "info",
        "unknown": "info",
    }
    return severity_map.get(normalized, "info")


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _looks_like_ip(value: str) -> bool:
    """Heuristic: contains dots and all parts are digits (IPv4)."""
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


def _collect_hashes(source: dict[str, Any]) -> list[dict[str, str]]:
    """Collect hash entries from a process/file info dict."""
    hashes: list[dict[str, str]] = []
    for algo, key in [
        ("MD5", "hash_md5"),
        ("SHA-1", "hash_sha1"),
        ("SHA-256", "hash_sha256"),
    ]:
        if source.get(key):
            hashes.append({"algorithm": algo, "value": source[key]})
    return hashes


_TECHNIQUE_RE = re.compile(r"T\d{4}(?:\.\d{3})?")


def _extract_technique_ids_from_value(val: Any, seen: set[str], out: list[str]) -> None:
    """Extract technique IDs from a string or list value into *out*."""
    items = val if isinstance(val, list) else [val]
    for item in items:
        for tid in _TECHNIQUE_RE.findall(str(item)):
            if tid not in seen:
                seen.add(tid)
                out.append(tid)


def _collect_technique_ids(notable: dict[str, Any]) -> list[str]:
    """Collect MITRE ATT&CK technique IDs from all known sources."""
    technique_ids: list[str] = []
    seen: set[str] = set()

    # Source 1: annotations.mitre_attack (list of technique IDs)
    annotations = notable.get("annotations")
    if isinstance(annotations, dict):
        mitre_attack = annotations.get("mitre_attack")
        if isinstance(mitre_attack, list):
            _extract_technique_ids_from_value(mitre_attack, seen, technique_ids)

    # Source 2: other_activities.mitre_technique from extract_other_activities
    other = extract_other_activities(notable)
    if other and other.get("mitre_technique"):
        _extract_technique_ids_from_value(other["mitre_technique"], seen, technique_ids)

    # Source 3: direct mitre_technique field on the notable
    if notable.get("mitre_technique"):
        _extract_technique_ids_from_value(
            notable["mitre_technique"], seen, technique_ids
        )

    return technique_ids


def _build_attack_entry(technique_id: str) -> dict[str, Any] | None:
    """Build an OCSF attack entry from a technique ID.

    For sub-techniques (e.g. T1059.001), look up the parent technique
    (T1059) for the tactic mapping and set the sub_technique field.
    """
    # Determine if this is a sub-technique
    parent_id = technique_id.split(".")[0] if "." in technique_id else technique_id

    mapping = TECHNIQUE_MAP.get(parent_id)
    if not mapping:
        # Unknown technique -- still emit with uid only
        entry: dict[str, Any] = {
            "technique": {"uid": technique_id, "name": technique_id},
        }
        return entry

    tech_name, tactic_id, tactic_name = mapping

    entry = {
        "tactic": {"uid": tactic_id, "name": tactic_name},
        "technique": {"uid": parent_id, "name": tech_name},
    }

    # If sub-technique, add sub_technique field
    if "." in technique_id:
        entry["sub_technique"] = {"uid": technique_id}

    return entry


class SplunkOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for Splunk Notable events -> OCSF Detection Finding.

    Calls extraction functions from mappers/splunk_notable.py directly and
    maps their output to OCSF structure — no NAS intermediate layer.
    """

    # ── Helpers shared with glom spec ─────────────────────────────────

    @staticmethod
    def _extract_title(notable: dict[str, Any]) -> str:
        return (
            notable.get("rule_name")
            or notable.get("rule_title")
            or notable.get("search_name")
            or "Unknown Alert"
        )

    @staticmethod
    def _extract_rule_name(notable: dict[str, Any]) -> str | None:
        return notable.get("rule_name") or notable.get("search_name")

    # ── Public API ────────────────────────────────────────────────────

    def to_ocsf(self, notable: dict[str, Any]) -> dict[str, Any]:
        """Convert Splunk Notable event to OCSF Detection Finding.

        Args:
            notable: Raw Splunk Notable event dict.

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
        title = self._extract_title(notable)
        ocsf["message"] = title

        # ── Time ─────────────────────────────────────────────────────
        trigger_time = notable.get("_time")
        if trigger_time:
            ocsf["time"] = _iso_to_epoch_ms(trigger_time)
            ocsf["time_dt"] = trigger_time

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = notable.get("severity") or notable.get("urgency") or "unknown"
        sev = _normalize_severity(raw_severity)
        sev_id, sev_label = SEVERITY_TO_OCSF.get(sev, (0, "Unknown"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Splunk",
                "name": "Enterprise Security",
            },
        }

        source_cat = map_security_domain_to_category(notable.get("security_domain"))
        if source_cat:
            metadata["labels"] = [f"source_category:{source_cat}"]

        source_event_id = notable.get("event_id")
        if source_event_id:
            metadata["event_code"] = source_event_id

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(notable, title)

        # ── Splunk Notables are always alertable findings ────────────
        ocsf["is_alert"] = True

        # ── Status (all Create events are New) ──────────────────────
        ocsf["status_id"] = 1
        ocsf["status"] = "New"

        # ── Disposition + Action (Security Control profile) ─────────
        action = normalize_device_action(notable.get("action"))
        if action and action in DISPOSITION_TO_OCSF:
            disp_id, disp_label = DISPOSITION_TO_OCSF[action]
            ocsf["disposition_id"] = disp_id
            ocsf["disposition"] = disp_label
            # action_id: 1=Allowed, 2=Denied per Security Control profile
            if action == "allowed":
                ocsf["action_id"] = 1
                ocsf["action"] = "Allowed"
            elif action in ("blocked", "quarantined", "terminated"):
                ocsf["action_id"] = 2
                ocsf["action"] = "Denied"

        # ── Risk score (from Splunk risk framework) ─────────────────
        risk_score = notable.get("risk_score")
        if risk_score is not None:
            try:
                ocsf["risk_score"] = int(float(risk_score))
                level_id, level_label = _risk_score_to_level(ocsf["risk_score"])
                ocsf["risk_level_id"] = level_id
                ocsf["risk_level"] = level_label
            except (ValueError, TypeError):
                pass

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(notable, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Device & Actor (from risk entities) ──────────────────────
        self._build_device_and_actor(notable, ocsf)

        # ── Observables (from IOCs) ──────────────────────────────────
        self._build_observables(notable, ocsf)

        # ── Evidences (from network/web/process info) ────────────────
        self._build_evidences(notable, ocsf)

        # ── Vulnerabilities (from CVE info) ──────────────────────────
        self._build_vulnerabilities(notable, ocsf)

        # ── Unmapped (from other_activities) ─────────────────────────
        other = extract_other_activities(notable)
        if other:
            ocsf["unmapped"] = other

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    def _build_finding_info(
        self, notable: dict[str, Any], title: str
    ) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        finding: dict[str, Any] = {
            "uid": str(uuid.uuid4()),
            "title": title,
        }

        alert_type = notable.get("security_domain")
        finding["types"] = [alert_type] if alert_type else []

        rule_name = self._extract_rule_name(notable)
        if rule_name:
            finding["analytic"] = {
                "name": rule_name,
                "type_id": 1,
                "type": "Rule",
            }

        rule_desc = notable.get("rule_description") or notable.get("description")
        if rule_desc:
            finding["desc"] = rule_desc

        detected_at = notable.get("firstTime") or notable.get("_time")
        if detected_at:
            finding["created_time_dt"] = detected_at

        # MITRE ATT&CK attacks from technique IDs
        technique_ids = _collect_technique_ids(notable)
        if technique_ids:
            attacks = [
                entry
                for tid in technique_ids
                if (entry := _build_attack_entry(tid)) is not None
            ]
            if attacks:
                finding["attacks"] = attacks

        return finding

    @staticmethod
    def _build_device_and_actor(notable: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device and actor from risk entities + primary entity."""
        risk_entities = extract_all_risk_entities(notable) or []
        network_info = extract_network_info(notable) or {}

        # Primary entity from extraction function
        primary_value, primary_type = get_primary_risk_entity(notable)

        device_entity: dict | None = None
        user_entity: dict | None = None

        # Primary entity takes precedence
        if primary_type == "device" and primary_value:
            device_entity = {"value": primary_value, "type": "device"}
        elif primary_type == "user" and primary_value:
            user_entity = {"value": primary_value, "type": "user"}

        # Check risk_entities for additional info
        for entity in risk_entities:
            etype = (entity.get("type") or "").lower()
            if etype == "device" and not device_entity:
                device_entity = entity
            elif etype == "user" and not user_entity:
                user_entity = entity

        # Build device
        if device_entity:
            device: dict[str, Any] = {"type_id": 0}
            val = device_entity.get("value", "")
            if _looks_like_ip(val):
                device["ip"] = val
            else:
                device["hostname"] = val
            # Associate an IP from risk_entities or network_info
            if "ip" not in device:
                for entity in risk_entities:
                    if (entity.get("type") or "").lower() == "ip":
                        device["ip"] = entity["value"]
                        break
                else:
                    dest_ip = network_info.get("dest_ip")
                    if dest_ip:
                        device["ip"] = dest_ip
            ocsf["device"] = device

        # Build actor
        if user_entity:
            user_val = user_entity.get("value", "")
            ocsf["actor"] = {
                "user": {"name": user_val, "uid": user_val},
            }

    @staticmethod
    def _build_observables(notable: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Convert IOCs to OCSF observables."""
        # Get all IOCs including primary without duplication
        iocs = extract_all_iocs(notable) or []

        # Also check primary IOC to ensure it's included
        primary_ioc = extract_primary_ioc(notable)
        if primary_ioc:
            ioc_values = {ioc.get("value") for ioc in iocs}
            if primary_ioc not in ioc_values and not (
                is_ip_address(primary_ioc) and is_private_ip(primary_ioc)
            ):
                from alert_normalizer.mappers.splunk_notable import (
                    determine_ioc_type,
                )

                ioc_type = determine_ioc_type(notable)
                iocs.insert(
                    0,
                    {
                        "value": primary_ioc,
                        "type": ioc_type or "unknown",
                        "source_field": "primary_ioc",
                        "confidence": 90,
                    },
                )

        if not iocs:
            return

        # OCSF attribute path hints for known IOC types
        _IOC_TYPE_TO_NAME: dict[str, str] = {
            "ip": "dst_endpoint.ip",
            "domain": "dst_endpoint.domain",
            "url": "url.url_string",
            "filename": "file.name",
            "filehash": "file.hashes",
            "process": "process.name",
            "user_agent": "http_request.user_agent",
            "email": "email.from",
        }

        observables: list[dict[str, Any]] = []
        for ioc in iocs:
            ioc_type = (ioc.get("type") or "").lower()
            type_id, type_name = IOC_TYPE_TO_OBSERVABLE.get(ioc_type, (99, "Other"))
            obs: dict[str, Any] = {
                "type_id": type_id,
                "type": type_name,
                "value": ioc.get("value", ""),
            }
            # OCSF name = attribute reference path
            if ioc_type in _IOC_TYPE_TO_NAME:
                obs["name"] = _IOC_TYPE_TO_NAME[ioc_type]
            elif type_id == 99:
                obs["name"] = ioc_type or "unknown"

            # Confidence -> reputation
            confidence = ioc.get("confidence")
            if confidence is not None:
                score_id, score_label = _confidence_to_score_id(confidence)
                obs["reputation"] = {
                    "base_score": confidence,
                    "score_id": score_id,
                    "score": score_label,
                }

            observables.append(obs)

        ocsf["observables"] = observables

    @staticmethod
    def _build_evidences(  # noqa: C901
        notable: dict[str, Any], ocsf: dict[str, Any]
    ) -> None:
        """Build OCSF evidences from network/web/process info."""
        evidence: dict[str, Any] = {}

        # Network info -> src/dst endpoints + connection_info
        net = extract_network_info(notable)
        if net:
            src_ep: dict[str, Any] = {}
            for ocsf_key, splunk_key in [
                ("ip", "src_ip"),
                ("port", "src_port"),
                ("hostname", "src_hostname"),
                ("mac", "src_mac"),
            ]:
                if net.get(splunk_key):
                    src_ep[ocsf_key] = net[splunk_key]
            if src_ep:
                evidence["src_endpoint"] = src_ep

            dst_ep: dict[str, Any] = {}
            for ocsf_key, splunk_key in [
                ("ip", "dest_ip"),
                ("port", "dest_port"),
                ("hostname", "dest_hostname"),
                ("mac", "dest_mac"),
            ]:
                if net.get(splunk_key):
                    dst_ep[ocsf_key] = net[splunk_key]
            if dst_ep:
                evidence["dst_endpoint"] = dst_ep

            conn: dict[str, Any] = {}
            if net.get("protocol"):
                conn["protocol_name"] = net["protocol"]
            direction = (net.get("direction") or "").lower()
            if direction == "inbound":
                conn["direction_id"] = 1
            elif direction == "outbound":
                conn["direction_id"] = 2
            if conn:
                evidence["connection_info"] = conn

        # Web info -> url + http_request + http_response
        web = extract_web_info(notable)
        if web:
            url_obj: dict[str, Any] = {}
            if web.get("url"):
                url_obj["url_string"] = web["url"]
                # Parse the full URL to extract path and query_string
                parsed = urlparse(web["url"])
                if parsed.path:
                    url_obj["path"] = parsed.path
                if parsed.query:
                    url_obj["query_string"] = parsed.query
            elif web.get("uri_path"):
                # Path-only URL (no scheme) -- use uri_path directly
                raw_path = web["uri_path"]
                if "?" in raw_path:
                    path_part, query_part = raw_path.split("?", 1)
                    url_obj["path"] = path_part
                    url_obj["query_string"] = query_part
                else:
                    url_obj["path"] = raw_path
            if web.get("uri_query") and "query_string" not in url_obj:
                url_obj["query_string"] = web["uri_query"]
            if url_obj:
                evidence["url"] = url_obj

            http_req: dict[str, Any] = {}
            if web.get("http_method"):
                http_req["http_method"] = web["http_method"]
            if web.get("user_agent"):
                http_req["user_agent"] = web["user_agent"]
            if web.get("http_referrer"):
                http_req["referrer"] = web["http_referrer"]
            if http_req:
                evidence["http_request"] = http_req

            if web.get("http_status"):
                evidence["http_response"] = {"code": web["http_status"]}

        # Process info -> process object
        proc = extract_process_info(notable)
        if proc:
            process_obj: dict[str, Any] = {}
            if proc.get("name"):
                process_obj["name"] = proc["name"]
            if proc.get("pid") is not None:
                process_obj["pid"] = proc["pid"]
            if proc.get("cmd_line") or proc.get("cmd"):
                process_obj["cmd_line"] = proc.get("cmd_line") or proc.get("cmd")
            if proc.get("path"):
                process_obj["file"] = {"path": proc["path"]}

            hashes = _collect_hashes(proc)
            if hashes:
                process_obj.setdefault("file", {})["hashes"] = hashes

            parent: dict[str, Any] = {}
            if proc.get("parent_name"):
                parent["name"] = proc["parent_name"]
            if proc.get("parent_pid") is not None:
                parent["pid"] = proc["parent_pid"]
            if proc.get("parent_cmd_line") or proc.get("parent_cmd"):
                parent["cmd_line"] = proc.get("parent_cmd_line") or proc.get(
                    "parent_cmd"
                )
            if parent:
                process_obj["parent_process"] = parent

            if proc.get("user"):
                process_obj["user"] = {"name": proc["user"]}

            if process_obj:
                evidence["process"] = process_obj

        if evidence:
            ocsf["evidences"] = [evidence]

    @staticmethod
    def _build_vulnerabilities(notable: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Convert CVE info to OCSF vulnerabilities."""
        cve_info = extract_cve_info(notable)
        if not cve_info:
            return

        cve_ids: list[str] = []
        if cve_info.get("ids"):
            cve_ids = cve_info["ids"]
        elif cve_info.get("id"):
            cve_ids = [cve_info["id"]]

        if not cve_ids:
            return

        vulns: list[dict[str, Any]] = []
        for cve_id in cve_ids:
            vuln: dict[str, Any] = {"cve": {"uid": cve_id}}
            if cve_info.get("severity"):
                vuln["severity"] = cve_info["severity"]
            if cve_info.get("cvss_score") is not None:
                cvss: dict[str, Any] = {"base_score": cve_info["cvss_score"]}
                if cve_info.get("cvss_version"):
                    cvss["version"] = cve_info["cvss_version"]
                vuln["cve"]["cvss"] = [cvss]
            vulns.append(vuln)

        ocsf["vulnerabilities"] = vulns
