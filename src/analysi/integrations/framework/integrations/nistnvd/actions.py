"""NIST NVD (National Vulnerability Database) integration actions.

This module provides actions for querying CVE (Common Vulnerabilities and Exposures)
information from the NIST National Vulnerability Database.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Constants
NISTNVD_BASE_URL = "https://services.nvd.nist.gov"
DEFAULT_TIMEOUT = 30
DEFAULT_API_VERSION = "2.0"

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_cve_id_safe(cve_id: str) -> tuple[bool, str]:
    """Validate CVE ID format.

    CVE IDs should follow the format: CVE-YYYY-NNNNN
    Example: CVE-2019-1010218

    Args:
        cve_id: CVE ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not cve_id or not isinstance(cve_id, str):
        return False, "CVE ID must be a non-empty string"

    cve_id = cve_id.strip().upper()

    if not cve_id.startswith("CVE-"):
        return False, "CVE ID must start with 'CVE-'"

    # Basic format validation: CVE-YYYY-NNNNN
    parts = cve_id.split("-")
    if len(parts) < 3:
        return False, "Invalid CVE ID format. Expected: CVE-YYYY-NNNNN"

    # Validate year part
    year_part = parts[1]
    if not year_part.isdigit() or len(year_part) != 4:
        return False, "CVE ID year must be 4 digits"

    # Validate ID part (should be numeric)
    id_part = parts[2]
    if not id_part.isdigit():
        return False, "CVE ID number must be numeric"

    return True, ""

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for NIST NVD API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check NIST NVD API connectivity.

        Tests connectivity by querying a known CVE (CVE-2019-1010218).

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_version = self.settings.get("api_version", DEFAULT_API_VERSION)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        api_key = self.credentials.get("api_key")  # Optional - works without it

        try:
            # Test connectivity with a known CVE
            headers: dict[str, str] = {"Accept": "application/json"}
            if api_key:
                headers["apiKey"] = api_key

            await self.http_request(
                f"{NISTNVD_BASE_URL}/rest/json/cves/{api_version}",
                headers=headers,
                params={"cveId": "CVE-2019-1010218"},
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": "success",
                "message": "NIST NVD API is accessible",
                "data": {
                    "healthy": True,
                    "api_version": api_version,
                    "base_url": NISTNVD_BASE_URL,
                },
            }

        except Exception as e:
            logger.error("nist_nvd_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class CveLookupAction(IntegrationAction):
    """Look up CVE information from NIST NVD database."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get CVE information from NIST NVD.

        Args:
            **kwargs: Must contain 'cve' (CVE ID to look up)

        Returns:
            Result with CVE information or error
        """
        # Validate inputs
        cve = kwargs.get("cve")
        is_valid, error_msg = _validate_cve_id_safe(cve)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        # Normalize CVE ID (uppercase)
        cve = cve.strip().upper()

        api_version = self.settings.get("api_version", DEFAULT_API_VERSION)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        api_key = self.credentials.get("api_key")  # Optional - works without it

        try:
            headers: dict[str, str] = {"Accept": "application/json"}
            if api_key:
                headers["apiKey"] = api_key

            response = await self.http_request(
                f"{NISTNVD_BASE_URL}/rest/json/cves/{api_version}",
                headers=headers,
                params={"cveId": cve},
                timeout=timeout,
            )
            result = response.json()

            # Extract vulnerability data
            vulnerabilities = result.get("vulnerabilities", [])
            if not vulnerabilities:
                return {
                    "status": "error",
                    "error": f"No data found for CVE {cve}",
                    "error_type": "NotFoundError",
                }

            # Get the first vulnerability entry
            vuln_data = vulnerabilities[0]
            cve_data = vuln_data.get("cve", {})

            # Extract descriptions
            descriptions = cve_data.get("descriptions", [])
            description = ""
            if descriptions:
                # Prefer English description
                for desc in descriptions:
                    if desc.get("lang") == "en":
                        description = desc.get("value", "")
                        break
                if not description and descriptions:
                    description = descriptions[0].get("value", "")

            # Extract references
            references = cve_data.get("references", [])
            reference_urls = [ref.get("url") for ref in references if ref.get("url")]

            # Extract CVSS metrics (v3.1)
            metrics = cve_data.get("metrics", {})
            cvss_v31 = metrics.get("cvssMetricV31", [])
            cvss_info = {}
            if cvss_v31:
                cvss_data = cvss_v31[0].get("cvssData", {})
                cvss_info = {
                    "base_score": cvss_data.get("baseScore"),
                    "base_severity": cvss_data.get("baseSeverity"),
                    "attack_vector": cvss_data.get("attackVector"),
                    "attack_complexity": cvss_data.get("attackComplexity"),
                    "privileges_required": cvss_data.get("privilegesRequired"),
                    "user_interaction": cvss_data.get("userInteraction"),
                    "scope": cvss_data.get("scope"),
                    "confidentiality_impact": cvss_data.get("confidentialityImpact"),
                    "integrity_impact": cvss_data.get("integrityImpact"),
                    "availability_impact": cvss_data.get("availabilityImpact"),
                    "exploitability_score": cvss_v31[0].get("exploitabilityScore"),
                    "impact_score": cvss_v31[0].get("impactScore"),
                }

            # Extract CVSS v2 if v3.1 not available
            if not cvss_info:
                cvss_v2 = metrics.get("cvssMetricV2", [])
                if cvss_v2:
                    cvss_data = cvss_v2[0].get("cvssData", {})
                    cvss_info = {
                        "base_score": cvss_data.get("baseScore"),
                        "base_severity": cvss_v2[0].get("baseSeverity"),
                        "attack_vector": cvss_data.get("accessVector"),
                        "attack_complexity": cvss_data.get("accessComplexity"),
                        "exploitability_score": cvss_v2[0].get("exploitabilityScore"),
                        "impact_score": cvss_v2[0].get("impactScore"),
                    }

            # Extract CISA KEV catalog info if available
            # NVD API v2.0 field names: cisaVulnerabilityName, cisaRequiredAction,
            # cisaActionDue, cisaExploitAdd
            cisa_vuln_name = cve_data.get("cisaVulnerabilityName")
            cisa_required_action = cve_data.get("cisaRequiredAction")
            cisa_due_date = cve_data.get("cisaActionDue")
            cisa_date_added = cve_data.get("cisaExploitAdd")

            return {
                "status": "success",
                "cve_id": cve_data.get("id", cve),
                "description": description,
                "published_date": cve_data.get("published"),
                "last_modified_date": cve_data.get("lastModified"),
                "cvss_metrics": cvss_info,
                "references": reference_urls,
                "cisa_kev": (
                    {
                        "vulnerability_name": cisa_vuln_name,
                        "required_action": cisa_required_action,
                        "due_date": cisa_due_date,
                        "date_added": cisa_date_added,
                    }
                    if cisa_vuln_name
                    else None
                ),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("nistnvd_cve_not_found", cve=cve)
                return {
                    "status": "success",
                    "not_found": True,
                    "cve_id": cve,
                }
            logger.error("nist_nvd_cve_lookup_failed_for", cve=cve, error=str(e))
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error("nist_nvd_cve_lookup_failed_for", cve=cve, error=str(e))
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
