"""Microsoft Sentinel Incident -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from Sentinel incident
objects (from the Azure Resource Manager API) by mapping incident properties
to OCSF structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

SEVERITY_TO_OCSF: dict[str, tuple[int, str]] = {
    "informational": (1, "Info"),
    "low": (2, "Low"),
    "medium": (3, "Medium"),
    "high": (4, "High"),
}

# Sentinel incident status -> OCSF status mapping
_STATUS_TO_OCSF: dict[str, tuple[int, str]] = {
    "new": (1, "New"),
    "active": (2, "In Progress"),
    "closed": (3, "Closed"),
}

# MITRE tactic name -> (tactic ID, canonical name)
# Sentinel uses PascalCase tactic names without IDs
_TACTIC_NAME_TO_ID: dict[str, str] = {
    "initialaccess": "TA0001",
    "execution": "TA0002",
    "persistence": "TA0003",
    "privilegeescalation": "TA0004",
    "defenseevasion": "TA0005",
    "credentialaccess": "TA0006",
    "discovery": "TA0007",
    "lateralmovement": "TA0008",
    "collection": "TA0009",
    "exfiltration": "TA0010",
    "commandandcontrol": "TA0011",
    "impact": "TA0040",
    "reconnaissance": "TA0043",
    "resourcedevelopment": "TA0042",
}


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _normalize_severity(value: Any) -> str:
    """Normalize Sentinel severity string to canonical lowercase form."""
    if value is None:
        return "informational"
    return str(value).lower().strip()


def _tactic_name_to_ocsf(raw_name: str) -> dict[str, Any]:
    """Convert a Sentinel PascalCase tactic name to an OCSF tactic object.

    Sentinel tactics are PascalCase (e.g. "InitialAccess"). We map them
    to MITRE tactic IDs.
    """
    lookup_key = raw_name.lower().replace("_", "")
    tactic_id = _TACTIC_NAME_TO_ID.get(lookup_key)
    obj: dict[str, Any] = {"name": raw_name}
    if tactic_id:
        obj["uid"] = tactic_id
    return obj


class SentinelOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for Microsoft Sentinel incidents -> OCSF Detection Finding.

    Maps Sentinel incident documents (Azure ARM API) directly to OCSF
    Detection Finding v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert Sentinel incident to OCSF Detection Finding.

        Args:
            data: Raw Sentinel incident object from the ARM API.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
        props = data.get("properties", {})
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
        title = props.get("title", "")
        description = props.get("description", "")
        ocsf["message"] = title or "Unknown Sentinel Incident"

        # ── Time ─────────────────────────────────────────────────────
        created_time = props.get("createdTimeUtc")
        modified_time = props.get("lastModifiedTimeUtc")

        if created_time:
            ocsf["time"] = _iso_to_epoch_ms(created_time)
            ocsf["time_dt"] = created_time

        if modified_time:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(modified_time)

        # ── Severity ─────────────────────────────────────────────────
        raw_severity = _normalize_severity(props.get("severity"))
        sev_id, sev_label = SEVERITY_TO_OCSF.get(raw_severity, (1, "Info"))
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "Microsoft",
                "name": "Sentinel",
            },
        }

        labels = props.get("labels")
        if labels and isinstance(labels, list):
            label_names = []
            for label in labels:
                if isinstance(label, dict):
                    label_names.append(label.get("labelName", str(label)))
                else:
                    label_names.append(str(label))
            if label_names:
                metadata["labels"] = label_names

        incident_number = props.get("incidentNumber")
        if incident_number is not None:
            metadata["event_code"] = str(incident_number)

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data, props, title, description)

        # ── Sentinel incidents are always alertable findings ─────────
        ocsf["is_alert"] = True

        # ── Status ───────────────────────────────────────────────────
        status_raw = str(props.get("status", "New")).lower()
        status_id, status_label = _STATUS_TO_OCSF.get(status_raw, (1, "New"))
        ocsf["status_id"] = status_id
        ocsf["status"] = status_label

        # ── Disposition + Action (defaults) ──────────────────────────
        ocsf["disposition_id"] = 0
        ocsf["disposition"] = "Unknown"
        ocsf["action_id"] = 0
        ocsf["action"] = "Unknown"

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Actor (from owner) ───────────────────────────────────────
        self._build_actor(props, ocsf)

        # ── Unmapped fields ──────────────────────────────────────────
        unmapped = self._collect_unmapped(data, props)
        if unmapped:
            ocsf["unmapped"] = unmapped

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    def _build_finding_info(
        self,
        data: dict[str, Any],
        props: dict[str, Any],
        title: str,
        description: str,
    ) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        incident_name = data.get("name", "")

        finding: dict[str, Any] = {
            "uid": incident_name,
            "title": title or "Unknown Sentinel Incident",
        }

        if description:
            finding["desc"] = description

        # Analytic (source rules)
        additional_data = props.get("additionalData", {})
        alert_product_names = additional_data.get("alertProductNames", [])
        rule_ids = props.get("relatedAnalyticRuleIds", [])

        if alert_product_names or rule_ids:
            analytic: dict[str, Any] = {
                "type_id": 1,
                "type": "Rule",
            }
            if alert_product_names:
                analytic["name"] = ", ".join(alert_product_names)
            if rule_ids:
                analytic["uid"] = (
                    rule_ids[0] if len(rule_ids) == 1 else ", ".join(rule_ids)
                )
            finding["analytic"] = analytic

        # Finding types from alert products
        if alert_product_names:
            finding["types"] = alert_product_names

        # Created time
        created_time = props.get("createdTimeUtc")
        if created_time:
            finding["created_time_dt"] = created_time

        # MITRE ATT&CK from tactics/techniques
        attacks = self._build_attacks(additional_data)
        if attacks:
            finding["attacks"] = attacks

        return finding

    @staticmethod
    def _build_attacks(additional_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract MITRE ATT&CK from Sentinel tactics and techniques."""
        tactics = additional_data.get("tactics", [])
        techniques = additional_data.get("techniques", [])

        if not tactics and not techniques:
            return []

        attacks: list[dict[str, Any]] = []

        # Build tactic-only entries for tactics without paired techniques
        for tactic_name in tactics:
            if not isinstance(tactic_name, str):
                continue
            tactic_obj = _tactic_name_to_ocsf(tactic_name)
            entry: dict[str, Any] = {"tactic": tactic_obj}

            # If we have techniques, pair the first one (Sentinel doesn't
            # provide explicit tactic-technique pairings)
            if techniques:
                for tech_id in techniques:
                    if isinstance(tech_id, str):
                        tech_entry = dict(entry)
                        tech_entry["technique"] = {"uid": tech_id, "name": tech_id}
                        attacks.append(tech_entry)
            else:
                attacks.append(entry)

        # If we have techniques but no tactics, add standalone technique entries
        if techniques and not tactics:
            for tech_id in techniques:
                if isinstance(tech_id, str):
                    attacks.append({"technique": {"uid": tech_id, "name": tech_id}})

        return attacks

    @staticmethod
    def _build_actor(props: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor from incident owner."""
        owner = props.get("owner", {})
        if not isinstance(owner, dict):
            return

        assigned_to = owner.get("assignedTo")
        email = owner.get("email")
        object_id = owner.get("objectId")

        if not assigned_to and not email and not object_id:
            return

        user: dict[str, Any] = {}
        if assigned_to:
            user["name"] = assigned_to
        if email:
            user["email_addr"] = email
        if object_id:
            user["uid"] = str(object_id)

        ocsf["actor"] = {"user": user}

    @staticmethod
    def _collect_unmapped(
        data: dict[str, Any], props: dict[str, Any]
    ) -> dict[str, Any]:
        """Collect Sentinel-specific fields not mapped to OCSF."""
        unmapped: dict[str, Any] = {}

        # Incident URL
        incident_url = props.get("incidentUrl")
        if incident_url:
            unmapped["incident_url"] = incident_url

        # Alert count
        additional_data = props.get("additionalData", {})
        alerts_count = additional_data.get("alertsCount")
        if alerts_count is not None:
            unmapped["alerts_count"] = alerts_count

        # Bookmarks count
        bookmarks_count = additional_data.get("bookmarksCount")
        if bookmarks_count is not None:
            unmapped["bookmarks_count"] = bookmarks_count

        # Comments count
        comments_count = additional_data.get("commentsCount")
        if comments_count is not None:
            unmapped["comments_count"] = comments_count

        # Azure resource ID
        resource_id = data.get("id")
        if resource_id:
            unmapped["azure_resource_id"] = resource_id

        # Etag
        etag = data.get("etag")
        if etag:
            unmapped["etag"] = etag

        return unmapped
