"""Recorded Future integration actions for threat intelligence.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

Recorded Future exposes a gateway API at ``/gw/phantom`` that provides
intelligence, reputation, threat-assessment (triage), and alert endpoints.
All calls are authenticated with the ``X-RFToken`` header.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    AUTH_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    MSG_INVALID_CONTEXT,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_PARAM,
    THREAT_CONTEXTS,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_intelligence_response() -> dict[str, Any]:
    """Return a minimal intelligence stub when the entity is unknown to RF."""
    return {
        "entity": {"name": "", "type": None, "id": None},
        "timestamps": {"firstSeen": "never", "lastSeen": "never"},
        "risk": {
            "criticalityLabel": None,
            "rules": None,
            "evidenceDetails": [],
            "riskSummary": "No information available.",
            "criticality": None,
            "riskString": "",
            "score": None,
        },
    }

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _RecordedFutureAction(IntegrationAction):
    """Shared helpers for all Recorded Future actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject the API token into every outbound request."""
        api_token = self.credentials.get("api_token", "")
        return {AUTH_HEADER: api_token} if api_token else {}

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to RF-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL)

    def _require_api_token(self) -> dict[str, Any] | None:
        """Return an error_result if api_token is missing, else None."""
        if not self.credentials.get("api_token"):
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type="ConfigurationError"
            )
        return None

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_RecordedFutureAction):
    """Verify connectivity and API token validity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        try:
            # Step 1: verify endpoint reachability
            await self.http_request(
                url=f"{self.base_url}/helo",
                params={"output-format": "application/json"},
            )

            # Step 2: verify token is accepted
            response = await self.http_request(url=f"{self.base_url}/config/info")
            config_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "config_info": config_data,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("recordedfuture_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# IP INTELLIGENCE / REPUTATION
# ============================================================================

class IpIntelligenceAction(_RecordedFutureAction):
    """Get full threat intelligence for an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/intelligence",
                method="POST",
                json_data={"entity_type": "ip", "ioc": ip},
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data=_empty_intelligence_response(),
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_ip_intelligence_failed", error=e)
            return self.error_result(e)

class IpReputationAction(_RecordedFutureAction):
    """Get reputation score for an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/reputation",
                method="POST",
                json_data={"ip": ip},
            )
            entities = response.json()

            # API returns a list; take first entry (single-entity lookup)
            entity = entities[0] if entities else {}

            return self.success_result(data=entity)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_ip_reputation_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={"ip": ip, "riskscore": None, "rulecount": 0},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_ip_reputation_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DOMAIN INTELLIGENCE / REPUTATION
# ============================================================================

class DomainIntelligenceAction(_RecordedFutureAction):
    """Get full threat intelligence for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/intelligence",
                method="POST",
                json_data={"entity_type": "domain", "ioc": domain},
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data=_empty_intelligence_response(),
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_domain_intelligence_failed", error=e)
            return self.error_result(e)

class DomainReputationAction(_RecordedFutureAction):
    """Get reputation score for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/reputation",
                method="POST",
                json_data={"domain": domain},
            )
            entities = response.json()
            entity = entities[0] if entities else {}

            return self.success_result(data=entity)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "recordedfuture_domain_reputation_not_found",
                    domain=domain,
                )
                return self.success_result(
                    not_found=True,
                    data={"domain": domain, "riskscore": None, "rulecount": 0},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_domain_reputation_failed", error=e)
            return self.error_result(e)

# ============================================================================
# FILE (HASH) INTELLIGENCE / REPUTATION
# ============================================================================

class FileIntelligenceAction(_RecordedFutureAction):
    """Get full threat intelligence for a file hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="hash"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/intelligence",
                method="POST",
                json_data={"entity_type": "file", "ioc": file_hash},
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_file_not_found", file_hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data=_empty_intelligence_response(),
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_file_intelligence_failed", error=e)
            return self.error_result(e)

class FileReputationAction(_RecordedFutureAction):
    """Get reputation score for a file hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="hash"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/reputation",
                method="POST",
                json_data={"hash": file_hash},
            )
            entities = response.json()
            entity = entities[0] if entities else {}

            return self.success_result(data=entity)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "recordedfuture_file_reputation_not_found",
                    file_hash=file_hash,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "riskscore": None,
                        "rulecount": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_file_reputation_failed", error=e)
            return self.error_result(e)

# ============================================================================
# URL INTELLIGENCE / REPUTATION
# ============================================================================

class UrlIntelligenceAction(_RecordedFutureAction):
    """Get full threat intelligence for a URL."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        url = kwargs.get("url")
        if not url:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="url"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/intelligence",
                method="POST",
                json_data={"entity_type": "url", "ioc": url},
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_url_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data=_empty_intelligence_response(),
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_url_intelligence_failed", error=e)
            return self.error_result(e)

class UrlReputationAction(_RecordedFutureAction):
    """Get reputation score for a URL."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        url = kwargs.get("url")
        if not url:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="url"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/reputation",
                method="POST",
                json_data={"url": url},
            )
            entities = response.json()
            entity = entities[0] if entities else {}

            return self.success_result(data=entity)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_url_reputation_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={"url": url, "riskscore": None, "rulecount": 0},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_url_reputation_failed", error=e)
            return self.error_result(e)

# ============================================================================
# VULNERABILITY INTELLIGENCE
# ============================================================================

class VulnerabilityLookupAction(_RecordedFutureAction):
    """Get threat intelligence for a CVE / vulnerability."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cve = kwargs.get("cve")
        if not cve:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="cve"),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/intelligence",
                method="POST",
                json_data={"entity_type": "vulnerability", "ioc": cve},
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_cve_not_found", cve=cve)
                return self.success_result(
                    not_found=True,
                    data=_empty_intelligence_response(),
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_vulnerability_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# THREAT ASSESSMENT (TRIAGE)
# ============================================================================

class ThreatAssessmentAction(_RecordedFutureAction):
    """Get a risk assessment for a collection of IOCs in a given context.

    The ``threat_context`` parameter must be one of: c2, malware, phishing.
    At least one IOC (ip, domain, url, hash) must be provided.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        threat_context = kwargs.get("threat_context")
        if not threat_context:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="threat_context"),
                error_type="ValidationError",
            )
        if threat_context not in THREAT_CONTEXTS:
            return self.error_result(
                MSG_INVALID_CONTEXT.format(
                    value=threat_context,
                    valid=", ".join(THREAT_CONTEXTS),
                ),
                error_type="ValidationError",
            )
        if err := self._require_api_token():
            return err

        # Build IOC payload -- at least one type must be present
        ioc_params: dict[str, list[str]] = {}
        for ioc_type in ("ip", "domain", "url", "hash"):
            raw = kwargs.get(ioc_type)
            if raw:
                ioc_params[ioc_type] = [
                    v.strip() for v in str(raw).split(",") if v.strip()
                ]

        if not ioc_params:
            return self.error_result(
                "At least one IOC (ip, domain, url, hash) is required",
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{self.base_url}/lookup/triage/{threat_context}?&format=phantom",
                method="POST",
                json_data=ioc_params,
            )
            result = response.json()

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_threat_assessment_failed", error=e)
            return self.error_result(e)

# ============================================================================
# ALERT SEARCH
# ============================================================================

class AlertSearchAction(_RecordedFutureAction):
    """Search alerts by alert rule ID and time range.

    Mirrors the upstream ``_handle_alert_search``: fetches the rule, then looks up
    details for each individual alert.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        rule_id = kwargs.get("rule_id")
        if not rule_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="rule_id"),
                error_type="ValidationError",
            )
        timeframe = kwargs.get("timeframe", "-24h to now")
        if err := self._require_api_token():
            return err

        try:
            # Step 1: search for alerts by rule ID + timeframe
            response = await self.http_request(
                url=f"{self.base_url}/alert/rule/{rule_id}",
                params={"triggered": timeframe},
            )
            search_result = response.json()

            counts = search_result.get("counts", {})
            total = counts.get("total", 0)
            returned = counts.get("returned", 0)

            if total == 0:
                return self.success_result(
                    data={
                        "rule_id": rule_id,
                        "timeframe": timeframe,
                        "total_alerts": 0,
                        "alerts_returned": 0,
                        "alerts": [],
                    },
                )

            # Step 2: look up details for each alert
            results_list = search_result.get("data", {}).get("results", [])
            alerts = []
            for alert_entry in results_list:
                alert_id = alert_entry.get("id")
                if not alert_id:
                    continue
                detail_resp = await self.http_request(
                    url=f"{self.base_url}/alert/lookup/{alert_id}",
                )
                alerts.append(detail_resp.json())

            rule_info = results_list[0].get("rule", {}) if results_list else {}

            return self.success_result(
                data={
                    "rule_id": rule_id,
                    "rule_name": rule_info.get("name"),
                    "timeframe": timeframe,
                    "total_alerts": total,
                    "alerts_returned": returned,
                    "rule": rule_info,
                    "alerts": alerts,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("recordedfuture_alert_rule_not_found", rule_id=rule_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "rule_id": rule_id,
                        "total_alerts": 0,
                        "alerts": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("recordedfuture_alert_search_failed", error=e)
            return self.error_result(e)
