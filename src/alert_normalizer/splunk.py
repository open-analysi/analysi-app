"""Splunk Notable event normalizer."""

import json
from typing import Any

try:
    import glom
    from glom import glom as glom_get
except ImportError:
    # Fallback if glom is not installed
    glom = None

    def glom_get(data, spec):
        """Simple fallback for glom."""
        if isinstance(spec, dict):
            result = {}
            for key, path in spec.items():
                if callable(path):
                    result[key] = path(data)
                elif isinstance(path, str):
                    result[key] = data.get(path)
                else:
                    result[key] = path
            return result
        return data.get(spec)


from analysi.schemas.alert import AlertCreate

from .base import BaseNormalizer
from .mappers.splunk_notable import (
    ALERTCREATE_TO_NOTABLE,
    NOTABLE_TO_ALERTCREATE,
    extract_primary_ioc,
)


class SplunkNotableNormalizer(BaseNormalizer):
    """Normalizer for Splunk Notable events."""

    def to_extracted_dict(self, notable: dict[str, Any]) -> dict[str, Any]:
        """Convert Notable to full extracted fields dict.

        Returns ALL extracted fields before AlertCreate validation strips
        non-schema fields. Useful for testing extraction logic.

        Args:
            notable: Splunk Notable event

        Returns:
            dict with all extracted fields
        """
        if glom:
            alert_dict = glom_get(notable, NOTABLE_TO_ALERTCREATE)
        else:
            alert_dict = {
                "title": notable.get("rule_name", "Unknown Alert"),
                "triggering_event_time": notable.get("_time"),
                "severity": self._normalize_enums(notable.get("severity", "unknown")),
                "source_vendor": "Splunk",
                "source_product": "Enterprise Security",
                "primary_risk_entity_value": notable.get("dest"),
                "primary_ioc_value": extract_primary_ioc(notable),
            }

        if "severity" in alert_dict:
            alert_dict["severity"] = self._normalize_enums(alert_dict["severity"])

        alert_dict["raw_alert"] = self.preserve_raw(notable)
        return alert_dict

    def to_alertcreate(self, notable: dict[str, Any]) -> AlertCreate:
        """Convert Notable to AlertCreate format.

        Args:
            notable: Splunk Notable event

        Returns:
            AlertCreate Pydantic model
        """
        alert_dict = self.to_extracted_dict(notable)
        return AlertCreate(**alert_dict)

    def from_alertcreate(
        self, alert_create: AlertCreate | dict[str, Any]
    ) -> dict[str, Any]:
        """Convert AlertCreate to Notable format.

        Args:
            alert_create: AlertCreate object or dictionary

        Returns:
            Notable event dictionary
        """
        # Convert to dict if it's a Pydantic model
        if hasattr(alert_create, "model_dump"):
            alert_dict = alert_create.model_dump(mode="json")
        else:
            alert_dict = alert_create

        # Start with raw alert if available
        notable = {}
        raw_notable = {}
        if "raw_alert" in alert_dict:
            try:
                raw_notable = json.loads(alert_dict["raw_alert"])
                notable = raw_notable.copy()
            except (json.JSONDecodeError, TypeError):
                raw_notable = {}
                notable = {}

        # Apply reverse mapping (only update non-None values to preserve raw_alert data)
        if glom:
            mapped = glom_get(alert_dict, ALERTCREATE_TO_NOTABLE)
            # Only update fields that have non-None values
            # But prefer raw_notable values for certain fields
            preserve_from_raw = ["risk_score", "dest_risk_score", "user_risk_score"]
            for key, value in mapped.items():
                # If field should be preserved from raw and exists there, skip
                if key in preserve_from_raw and key in raw_notable:
                    continue
                # Otherwise update if value is not None
                if value is not None:
                    notable[key] = value
        else:
            # Manual reverse mapping
            if "title" in alert_dict:
                notable["rule_name"] = alert_dict["title"]
            if "triggering_event_time" in alert_dict:
                notable["_time"] = alert_dict["triggering_event_time"]
            if "severity" in alert_dict:
                notable["severity"] = alert_dict["severity"]

        return notable

    def _normalize_enums(self, value: Any) -> str:
        """Normalize enum values (e.g., severity to lowercase).

        Args:
            value: Value to normalize

        Returns:
            Normalized string
        """
        if value is None:
            return "info"  # Default to info for AlertSeverity enum

        # Convert to string and lowercase
        normalized = str(value).lower()

        # Map common variations to AlertSeverity enum values
        severity_map = {
            "crit": "critical",
            "critical": "critical",
            "high": "high",
            "med": "medium",
            "medium": "medium",
            "low": "low",
            "info": "info",
            "informational": "info",
            "unknown": "info",  # Map unknown to info
        }

        return severity_map.get(normalized, "info")  # Default to info if not found
