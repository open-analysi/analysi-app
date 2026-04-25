"""QRadar Offense -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from QRadar offenses
(from GET /api/siem/offenses) by mapping QRadar offense fields to OCSF
structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

# QRadar severity 1-10 -> OCSF (severity_id, severity label)
SEVERITY_TO_OCSF: dict[int, tuple[int, str]] = {
    1: (2, "Low"),
    2: (2, "Low"),
    3: (3, "Medium"),
    4: (3, "Medium"),
    5: (4, "High"),
    6: (4, "High"),
    7: (4, "High"),
    8: (5, "Critical"),
    9: (5, "Critical"),
    10: (5, "Critical"),
}

# QRadar offense status -> OCSF status mapping
STATUS_TO_OCSF: dict[str, tuple[int, str]] = {
    "OPEN": (1, "New"),
    "HIDDEN": (2, "In Progress"),
    "CLOSED": (3, "Closed"),
}

# QRadar offense_type_str -> OCSF observable type mapping
_OFFENSE_TYPE_TO_OBSERVABLE: dict[str, tuple[int, str]] = {
    "source ip": (2, "IP Address"),
    "destination ip": (2, "IP Address"),
    "username": (4, "User Name"),
    "hostname": (1, "Hostname"),
    "source mac address": (3, "MAC Address"),
    "destination mac address": (3, "MAC Address"),
    "log source": (99, "Other"),
    "event name": (99, "Other"),
}

_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _looks_like_ip(value: str) -> bool:
    """Heuristic: matches IPv4 address pattern."""
    return bool(_IPV4_RE.match(value))


def _epoch_ms_to_iso(epoch_ms: int | float) -> str:
    """Convert epoch milliseconds to ISO 8601 string."""
    dt = datetime.fromtimestamp(int(epoch_ms) / 1000, tz=UTC)
    return dt.isoformat()


def _map_severity(severity: int) -> tuple[int, str]:
    """Map QRadar severity (1-10) to OCSF severity_id and label."""
    severity = max(1, min(10, int(severity)))
    return SEVERITY_TO_OCSF.get(severity, (1, "Info"))


class QRadarOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for QRadar offenses -> OCSF Detection Finding.

    Maps QRadar offense documents directly to OCSF Detection Finding
    v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert QRadar offense to OCSF Detection Finding.

        Args:
            data: Raw QRadar offense dict from /api/siem/offenses.

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
        description = data.get("description", "")
        offense_id = data.get("id")
        title = description or f"QRadar Offense {offense_id}"
        ocsf["message"] = title

        # ── Time ─────────────────────────────────────────────────────
        start_time = data.get("start_time")
        last_updated = data.get("last_updated_time")

        if start_time is not None:
            ocsf["time"] = int(start_time)
            ocsf["time_dt"] = _epoch_ms_to_iso(start_time)

        if last_updated is not None:
            ocsf["ocsf_time"] = int(last_updated)

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = data.get("severity")
        if raw_severity is not None:
            sev_id, sev_label = _map_severity(raw_severity)
        else:
            sev_id, sev_label = 1, "Info"
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "IBM",
                "name": "QRadar",
            },
        }

        categories = data.get("categories", [])
        if categories and isinstance(categories, list):
            metadata["labels"] = [str(c) for c in categories]

        if offense_id is not None:
            metadata["event_code"] = str(offense_id)

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data, title)

        # ── QRadar offenses are always alertable findings ────────────
        ocsf["is_alert"] = True

        # ── Status ───────────────────────────────────────────────────
        raw_status = str(data.get("status", "OPEN")).upper()
        status_id, status_label = STATUS_TO_OCSF.get(raw_status, (1, "New"))
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # ── Risk score (from magnitude, 1-10 -> 0-100) ──────────────
        magnitude = data.get("magnitude")
        if magnitude is not None:
            try:
                score = int(float(magnitude)) * 10
                ocsf["risk_score"] = score
                ocsf["risk_level_id"], ocsf["risk_level"] = _risk_score_to_level(score)
            except (ValueError, TypeError):
                pass

        # ── Disposition + Action (defaults — QRadar doesn't set these) ──
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Observables (from offense_source + offense_type) ─────────
        self._build_observables(data, ocsf)

        # ── Unmapped fields ──────────────────────────────────────────
        unmapped = self._collect_unmapped(data)
        if unmapped:
            ocsf["unmapped"] = unmapped

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    def _build_finding_info(self, data: dict[str, Any], title: str) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        finding: dict[str, Any] = {
            "uid": str(uuid.uuid4()),
            "title": title,
        }

        # Map categories to finding types
        categories = data.get("categories", [])
        if categories and isinstance(categories, list):
            finding["types"] = [str(c) for c in categories]
        else:
            finding["types"] = []

        # Description from the offense
        description = data.get("description")
        if description:
            finding["desc"] = description

        # Created time from start_time
        start_time = data.get("start_time")
        if start_time is not None:
            finding["created_time_dt"] = _epoch_ms_to_iso(start_time)

        # Rules that triggered the offense -> analytic
        rules = data.get("rules", [])
        if rules and isinstance(rules, list):
            first_rule = rules[0]
            if isinstance(first_rule, dict):
                analytic: dict[str, Any] = {
                    "type_id": 1,
                    "type": "Rule",
                }
                rule_id = first_rule.get("id")
                if rule_id is not None:
                    analytic["uid"] = str(rule_id)
                    analytic["name"] = f"QRadar Rule {rule_id}"
                finding["analytic"] = analytic

        return finding

    @staticmethod
    def _build_observables(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF observables from offense_source and offense_type."""
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

        # Primary observable from offense_source + offense_type_str
        offense_source = data.get("offense_source")
        offense_type_str = str(data.get("offense_type_str", "")).lower()

        if offense_source:
            source_str = str(offense_source)
            type_mapping = _OFFENSE_TYPE_TO_OBSERVABLE.get(offense_type_str)

            if type_mapping:
                type_id, type_name = type_mapping
                _add_observable(source_str, type_id, type_name, "offense_source")
            elif _looks_like_ip(source_str):
                _add_observable(source_str, 2, "IP Address", "offense_source")
            else:
                _add_observable(source_str, 99, "Other", "offense_source")

        if observables:
            ocsf["observables"] = observables

    @staticmethod
    def _collect_unmapped(data: dict[str, Any]) -> dict[str, Any]:
        """Collect QRadar-specific fields not mapped to OCSF."""
        unmapped: dict[str, Any] = {}

        # Credibility and relevance (QRadar-specific scoring)
        credibility = data.get("credibility")
        relevance = data.get("relevance")
        if credibility is not None or relevance is not None:
            scoring: dict[str, Any] = {}
            if credibility is not None:
                scoring["credibility"] = credibility
            if relevance is not None:
                scoring["relevance"] = relevance
            unmapped["qradar_scoring"] = scoring

        # Counts
        for count_field in [
            "event_count",
            "flow_count",
            "username_count",
            "source_count",
            "destination_count",
        ]:
            val = data.get(count_field)
            if val is not None:
                unmapped[count_field] = val

        # Address IDs
        src_ids = data.get("source_address_ids")
        if src_ids:
            unmapped["source_address_ids"] = src_ids
        dst_ids = data.get("local_destination_address_ids")
        if dst_ids:
            unmapped["local_destination_address_ids"] = dst_ids

        return unmapped


# ── Risk score helper ────────────────────────────────────────────────

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
