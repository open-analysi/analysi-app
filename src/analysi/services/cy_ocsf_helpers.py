"""
Cy OCSF Helper Functions.

Provides helper functions exposed to Cy scripts that navigate OCSF-shaped
alert dicts.
"""

from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# OCSF type_id <-> human-readable name mapping
# ---------------------------------------------------------------------------
OCSF_TYPE_ID_TO_NAME: dict[int, str] = {
    1: "Hostname",
    2: "IP Address",
    3: "MAC Address",
    4: "User Name",
    5: "Email Address",
    6: "URL String",
    7: "File Name",
    8: "Hash",
    9: "Process Name",
}

OCSF_NAME_TO_TYPE_ID: dict[str, int] = {v: k for k, v in OCSF_TYPE_ID_TO_NAME.items()}

# OCSF type_id -> short name used by Cy scripts (e.g. "ip", "domain")
OCSF_TYPE_ID_TO_SHORT: dict[int, str] = {
    2: "ip",
    1: "domain",
    7: "filename",
    8: "filehash",
    6: "url",
    9: "process",
    16: "user_agent",
}

# Reverse: short name -> OCSF type_id
SHORT_TO_OCSF_TYPE_ID: dict[str, int] = {v: k for k, v in OCSF_TYPE_ID_TO_SHORT.items()}


def _ocsf_type_id_to_name(type_id: int) -> str:
    """Map an OCSF observable type_id integer to its human-readable name."""
    return OCSF_TYPE_ID_TO_NAME.get(type_id, f"Unknown({type_id})")


def _normalise_observable(obs: dict[str, Any]) -> dict[str, Any]:
    """
    Return a dict with at minimum {"type": str, "value": str}.

    OCSF observables have "type_id" as an integer. This maps it to a short
    string (e.g. "ip", "domain", "filehash") so Cy scripts like
    ``if ioc_type == "ip"`` work naturally.
    """
    result = dict(obs)
    if "type_id" in obs:
        type_id = obs["type_id"]
        short = OCSF_TYPE_ID_TO_SHORT.get(type_id)
        if short:
            result["type"] = short
        elif "type" not in obs:
            # Unmapped type_id and no existing type -- use verbose fallback
            result["type"] = _ocsf_type_id_to_name(type_id)
    return result


class CyOCSFHelpers:
    """
    Helper functions for navigating OCSF-shaped alert fields.

    Each method extracts data from OCSF alert dicts and returns values in
    a format suitable for Cy scripts.
    """

    # ------------------------------------------------------------------
    # Entity helpers
    # ------------------------------------------------------------------

    def get_primary_entity_type(self, alert: dict[str, Any]) -> str | None:
        """
        Return the primary risk entity type ("user", "device", etc.).

        OCSF: inferred from ``actor.user`` or top-level ``device``.
        """
        actor = alert.get("actor")
        if isinstance(actor, dict) and actor.get("user"):
            return "user"
        if alert.get("device"):
            return "device"
        return None

    def get_primary_entity_value(self, alert: dict[str, Any]) -> str | None:
        """
        Return the primary risk entity value (username, hostname, etc.).

        OCSF: ``actor.user.name`` / ``actor.user.uid`` or
              ``device.hostname`` / ``device.name`` / ``device.ip``.
        """
        return self.get_primary_user(alert) or self.get_primary_device(alert)

    def get_primary_user(self, alert: dict[str, Any]) -> str | None:
        """
        Return the primary user associated with the alert.

        OCSF: ``actor.user.name`` or ``actor.user.uid``.
        """
        actor = alert.get("actor")
        if isinstance(actor, dict):
            user = actor.get("user")
            if isinstance(user, dict):
                return user.get("name") or user.get("uid")

        return None

    def get_primary_device(self, alert: dict[str, Any]) -> str | None:
        """
        Return the primary device associated with the alert.

        OCSF: ``device.hostname`` or ``device.name`` or ``device.ip``.
        """
        device = alert.get("device")
        if isinstance(device, dict):
            return device.get("hostname") or device.get("name") or device.get("ip")

        return None

    # ------------------------------------------------------------------
    # Observable / IOC helpers
    # ------------------------------------------------------------------

    def get_primary_observable_type(self, alert: dict[str, Any]) -> str | None:
        """
        Return the type of the primary observable / IOC.

        OCSF: first observable's ``type_id`` mapped to a short string name.
        """
        observables = alert.get("observables")
        if isinstance(observables, list) and observables:
            first = observables[0]
            if isinstance(first, dict) and "type_id" in first:
                type_id = first["type_id"]
                return OCSF_TYPE_ID_TO_SHORT.get(
                    type_id, _ocsf_type_id_to_name(type_id)
                )

        return None

    def get_primary_observable_value(self, alert: dict[str, Any]) -> str | None:
        """
        Return the value of the primary observable / IOC.

        OCSF: first observable's ``value``.
        """
        observables = alert.get("observables")
        if isinstance(observables, list) and observables:
            first = observables[0]
            if isinstance(first, dict):
                return first.get("value")

        return None

    def get_primary_observable(
        self, alert: dict[str, Any], type: str | None = None
    ) -> dict[str, Any] | None:
        """
        Return the first observable matching *type*, or the primary one.

        OCSF: first observable matching *type* (if given), else first observable.

        Returns a dict with at minimum ``{"type": str, "value": str}`` or None.
        """
        observables = alert.get("observables")
        if not isinstance(observables, list) or not observables:
            return None

        if type is not None:
            # Try matching by short name or OCSF type_id
            target_type_id = SHORT_TO_OCSF_TYPE_ID.get(type)
            for obs in observables:
                if not isinstance(obs, dict):
                    continue
                obs_type_name = _ocsf_type_id_to_name(obs.get("type_id", -1))
                if obs.get("type") == type or obs_type_name == type:
                    return _normalise_observable(obs)
                if target_type_id is not None and obs.get("type_id") == target_type_id:
                    return _normalise_observable(obs)
            return None

        return _normalise_observable(observables[0])

    def get_observables(
        self, alert: dict[str, Any], type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return all observables, optionally filtered by *type*.

        OCSF: ``alert["observables"]`` with ``type_id`` mapped to a short
              string, filtered if *type* given.

        Each entry is a dict with at minimum ``{"type": str, "value": str}``.
        """
        observables = alert.get("observables")
        if not isinstance(observables, list):
            return []

        results: list[dict[str, Any]] = []
        target_type_id = SHORT_TO_OCSF_TYPE_ID.get(type) if type else None

        for obs in observables:
            if not isinstance(obs, dict):
                continue
            normalised = _normalise_observable(obs)
            if type is not None:
                obs_type_name = normalised.get("type", "")
                matches = obs_type_name == type or (
                    target_type_id is not None and obs.get("type_id") == target_type_id
                )
                if not matches:
                    continue
            results.append(normalised)

        return results

    # ------------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_evidence_value(alert: dict[str, Any], *keys: str) -> str | None:
        """Walk ``evidences[]`` and return the first nested value at *keys* path.

        Example: ``_first_evidence_value(alert, "src_endpoint", "ip")``
        returns the first non-None ``evidences[i]["src_endpoint"]["ip"]``.
        """
        for ev in alert.get("evidences", []):
            if not isinstance(ev, dict):
                continue
            obj = ev
            for key in keys:
                if not isinstance(obj, dict):
                    obj = None
                    break
                obj = obj.get(key)
            if obj is not None:
                return obj
        return None

    def get_src_ip(self, alert: dict[str, Any]) -> str | None:
        """Return the source IP — first ``evidences[].src_endpoint.ip``."""
        return self._first_evidence_value(alert, "src_endpoint", "ip")

    def get_dst_ip(self, alert: dict[str, Any]) -> str | None:
        """Return the destination IP — first ``evidences[].dst_endpoint.ip``."""
        return self._first_evidence_value(alert, "dst_endpoint", "ip")

    def get_dst_domain(self, alert: dict[str, Any]) -> str | None:
        """Return the destination domain — first ``evidences[].dst_endpoint.domain``."""
        return self._first_evidence_value(alert, "dst_endpoint", "domain")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def get_http_method(self, alert: dict[str, Any]) -> str | None:
        """Return the HTTP method — first ``evidences[].http_request.http_method``."""
        return self._first_evidence_value(alert, "http_request", "http_method")

    def get_user_agent(self, alert: dict[str, Any]) -> str | None:
        """Return the user agent — first ``evidences[].http_request.user_agent``."""
        return self._first_evidence_value(alert, "http_request", "user_agent")

    def get_http_response_code(self, alert: dict[str, Any]) -> int | None:
        """Return the HTTP response code — first ``evidences[].http_response.code``."""
        return self._first_evidence_value(alert, "http_response", "code")

    # ------------------------------------------------------------------
    # Web / URL helpers
    # ------------------------------------------------------------------

    def get_url(self, alert: dict[str, Any]) -> str | None:
        """Return the full URL — first ``evidences[].url.url_string``."""
        return self._first_evidence_value(alert, "url", "url_string")

    def get_url_path(self, alert: dict[str, Any]) -> str | None:
        """Return the URL path — first ``evidences[].url.path``."""
        return self._first_evidence_value(alert, "url", "path")

    # ------------------------------------------------------------------
    # CVE helpers
    # ------------------------------------------------------------------

    def get_cve_ids(self, alert: dict[str, Any]) -> list[str]:
        """
        Return list of CVE identifiers.

        OCSF: ``vulnerabilities[].cve.uid``.
        """
        vulns = alert.get("vulnerabilities")
        if isinstance(vulns, list):
            result: list[str] = []
            for v in vulns:
                if not isinstance(v, dict):
                    continue
                cve = v.get("cve")
                if isinstance(cve, dict):
                    uid = cve.get("uid")
                    if uid:
                        result.append(uid)
            if result:
                return result

        return []

    # ------------------------------------------------------------------
    # Label / metadata helpers
    # ------------------------------------------------------------------

    def get_label(self, alert: dict[str, Any], key: str) -> str | None:
        """
        Return a label value by key.

        OCSF: search ``metadata.labels`` for ``"{key}:..."`` prefix and
              return the value after ``":"``.
        """
        metadata = alert.get("metadata")
        if isinstance(metadata, dict):
            labels = metadata.get("labels")
            if isinstance(labels, list):
                prefix = f"{key}:"
                for label in labels:
                    if isinstance(label, str) and label.startswith(prefix):
                        return label[len(prefix) :]

        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_cy_ocsf_helpers() -> dict[str, Any]:
    """
    Create dictionary of OCSF helper functions for Cy interpreter.

    Returns:
        Dictionary mapping function names to callables.
    """
    helpers = CyOCSFHelpers()

    return {
        "get_primary_entity_type": helpers.get_primary_entity_type,
        "get_primary_entity_value": helpers.get_primary_entity_value,
        "get_primary_user": helpers.get_primary_user,
        "get_primary_device": helpers.get_primary_device,
        "get_primary_observable_type": helpers.get_primary_observable_type,
        "get_primary_observable_value": helpers.get_primary_observable_value,
        "get_primary_observable": helpers.get_primary_observable,
        "get_observables": helpers.get_observables,
        "get_src_ip": helpers.get_src_ip,
        "get_dst_ip": helpers.get_dst_ip,
        "get_dst_domain": helpers.get_dst_domain,
        "get_http_method": helpers.get_http_method,
        "get_user_agent": helpers.get_user_agent,
        "get_http_response_code": helpers.get_http_response_code,
        "get_url": helpers.get_url,
        "get_url_path": helpers.get_url_path,
        "get_cve_ids": helpers.get_cve_ids,
        "get_label": helpers.get_label,
    }
