"""
AWS Security integration actions (Security Hub + GuardDuty).

Uses the AWS REST API directly with Signature V4 signing via
self.http_request(). Does NOT depend on boto3.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.aws_security.constants import (
    ALERT_PAGE_SIZE,
    AWS_SIGV4_ALGORITHM,
    AWS_SIGV4_TERMINATOR,
    CREDENTIAL_ACCESS_KEY_ID,
    CREDENTIAL_SECRET_ACCESS_KEY,
    CREDENTIAL_SESSION_TOKEN,
    DEFAULT_LOOKBACK_MINUTES,
    DEFAULT_MAX_ALERTS,
    DEFAULT_REGION,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    GUARDDUTY_HOST_TEMPLATE,
    GUARDDUTY_SERVICE,
    MSG_MISSING_CREDENTIALS,
    SECURITYHUB_HOST_TEMPLATE,
    SECURITYHUB_SERVICE,
    SECURITYHUB_TARGET_BATCH_UPDATE,
    SECURITYHUB_TARGET_GET_FINDINGS,
    SECURITYHUB_TARGET_GET_FINDINGS_V2,
    SETTINGS_DEFAULT_LOOKBACK,
    SETTINGS_GUARDDUTY_DETECTOR_ID,
    SETTINGS_REGION,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# AWS Signature V4 helpers (stdlib only: hmac + hashlib)
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()

def _hmac_sha256(key: bytes, msg: str) -> bytes:
    """Return the HMAC-SHA256 of *msg* using *key*."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def _derive_signing_key(
    secret_key: str,
    date_stamp: str,
    region: str,
    service: str,
) -> bytes:
    """Derive the SigV4 signing key via the HMAC chain.

    signing_key = HMAC(HMAC(HMAC(HMAC("AWS4" + secret, date), region), service), "aws4_request")
    """
    k_date = _hmac_sha256(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(
        k_service, AWS_SIGV4_TERMINATOR.encode("utf-8"), hashlib.sha256
    ).digest()
    return k_signing

def _build_canonical_query_string(params: dict[str, str] | None) -> str:
    """Build a canonical query string (sorted, URI-encoded)."""
    if not params:
        return ""
    sorted_params = sorted(params.items())
    return urlencode(sorted_params, quote_via=quote)

def sign_request(
    *,
    method: str,
    host: str,
    uri: str,
    query_params: dict[str, str] | None,
    headers: dict[str, str],
    payload: bytes,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    service: str,
    now: datetime | None = None,
) -> dict[str, str]:
    """Compute AWS SigV4 Authorization header and return updated headers.

    Parameters
    ----------
    method : str
        HTTP method (GET, POST, etc.).
    host : str
        Host header value (e.g. ``securityhub.us-east-1.amazonaws.com``).
    uri : str
        Request URI path (e.g. ``/``).
    query_params : dict | None
        Query string parameters (already un-encoded).
    headers : dict
        Headers dict. Must already contain ``host`` and ``x-amz-date``.
        The function adds ``Authorization`` and returns the merged dict.
    payload : bytes
        Request body bytes (empty bytes for GET).
    access_key_id, secret_access_key, region, service : str
        AWS credential and target service fields.
    now : datetime | None
        Override current time (for testing). Uses UTC.

    Returns
    -------
    dict[str, str]
        Updated headers dict with ``Authorization`` added.
    """
    if now is None:
        now = datetime.now(UTC)

    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Ensure required headers are present
    headers["host"] = host
    headers["x-amz-date"] = amz_date

    # 1. Canonical request ------------------------------------------------
    payload_hash = _sha256_hex(payload)
    canonical_query = _build_canonical_query_string(query_params)

    # Signed headers: lowercase, sorted, semicolon-delimited
    signed_header_keys = sorted(k.lower() for k in headers)
    signed_headers_str = ";".join(signed_header_keys)

    canonical_headers = "".join(
        f"{k}:{headers[k].strip()}\n" for k in sorted(headers, key=str.lower)
    )

    canonical_request = "\n".join(
        [
            method.upper(),
            uri,
            canonical_query,
            canonical_headers,
            signed_headers_str,
            payload_hash,
        ]
    )

    # 2. String to sign ---------------------------------------------------
    credential_scope = f"{date_stamp}/{region}/{service}/{AWS_SIGV4_TERMINATOR}"

    string_to_sign = "\n".join(
        [
            AWS_SIGV4_ALGORITHM,
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    # 3. Signing key + signature ------------------------------------------
    signing_key = _derive_signing_key(secret_access_key, date_stamp, region, service)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # 4. Authorization header ---------------------------------------------
    auth_header = (
        f"{AWS_SIGV4_ALGORITHM} "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )
    headers["Authorization"] = auth_header
    return headers

# ---------------------------------------------------------------------------
# Base class for AWS actions
# ---------------------------------------------------------------------------

class _AWSBase(IntegrationAction):
    """Shared AWS credential extraction and SigV4 request helper."""

    def _get_region(self) -> str:
        return self.settings.get(SETTINGS_REGION, DEFAULT_REGION)

    def _validate_credentials(self) -> tuple[str, str, str | None] | None:
        """Return (access_key_id, secret_access_key, session_token) or None on error."""
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY_ID)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_ACCESS_KEY)
        if not access_key or not secret_key:
            return None
        session_token = self.credentials.get(CREDENTIAL_SESSION_TOKEN)
        return access_key, secret_key, session_token

    async def _aws_request(
        self,
        *,
        service: str,
        host: str,
        method: str = "POST",
        uri: str = "/",
        query_params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a signed AWS API request via self.http_request().

        Builds SigV4 auth headers then delegates to the framework helper
        which provides retry, logging, SSL, and timeout.
        """
        creds = self._validate_credentials()
        if creds is None:
            raise ValueError(MSG_MISSING_CREDENTIALS)

        access_key, secret_key, session_token = creds
        region = self._get_region()

        payload = json.dumps(body).encode("utf-8") if body else b""
        content_type = "application/x-amz-json-1.1"

        headers: dict[str, str] = {
            "Content-Type": content_type,
        }
        if extra_headers:
            headers.update(extra_headers)
        if session_token:
            headers["X-Amz-Security-Token"] = session_token

        # Sign the request
        signed_headers = sign_request(
            method=method,
            host=host,
            uri=uri,
            query_params=query_params,
            headers=headers,
            payload=payload,
            access_key_id=access_key,
            secret_access_key=secret_key,
            region=region,
            service=service,
        )

        url = f"https://{host}{uri}"
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        return await self.http_request(
            url=url,
            method=method,
            headers=signed_headers,
            params=query_params,
            content=payload,
            timeout=timeout,
        )

# ---------------------------------------------------------------------------
# Security Hub base
# ---------------------------------------------------------------------------

class _SecurityHubBase(_AWSBase):
    """Security Hub specific helpers."""

    def _get_host(self) -> str:
        return SECURITYHUB_HOST_TEMPLATE.format(region=self._get_region())

    async def _securityhub_request(
        self,
        target: str,
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST to Security Hub with the given X-Amz-Target."""
        return await self._aws_request(
            service=SECURITYHUB_SERVICE,
            host=self._get_host(),
            method="POST",
            extra_headers={"X-Amz-Target": target},
            body=body or {},
        )

# ---------------------------------------------------------------------------
# GuardDuty base
# ---------------------------------------------------------------------------

class _GuardDutyBase(_AWSBase):
    """GuardDuty specific helpers."""

    def _get_host(self) -> str:
        return GUARDDUTY_HOST_TEMPLATE.format(region=self._get_region())

    async def _guardduty_request(
        self,
        *,
        method: str = "GET",
        uri: str = "/",
        body: dict[str, Any] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a signed GuardDuty REST call."""
        return await self._aws_request(
            service=GUARDDUTY_SERVICE,
            host=self._get_host(),
            method=method,
            uri=uri,
            body=body,
            query_params=query_params,
        )

# ============================================================================
# Security Hub actions
# ============================================================================

class HealthCheckAction(_SecurityHubBase):
    """Verify AWS Security Hub API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Call GetFindings with maxResults=1 to verify connectivity."""
        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._securityhub_request(
                SECURITYHUB_TARGET_GET_FINDINGS,
                body={"MaxResults": 1},
            )
            data = response.json()
            return self.success_result(
                data={
                    "healthy": True,
                    "region": self._get_region(),
                    "findings_count": len(data.get("Findings", [])),
                }
            )
        except Exception as e:
            self.log_error("aws_security_health_check_failed", error=e)
            return self.error_result(e)

class ListFindingsAction(_SecurityHubBase):
    """List Security Hub findings with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List findings, optionally filtered by severity/status/product.

        Args:
            severity_label: Filter by severity label (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
            workflow_status: Filter by workflow status (NEW, NOTIFIED, SUPPRESSED, RESOLVED)
            product_name: Filter by product name
            max_results: Max findings to return (1-100, default 20)
            next_token: Pagination token
        """
        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        max_results = min(int(kwargs.get("max_results", 20)), 100)
        body: dict[str, Any] = {"MaxResults": max_results}

        # Build filters
        filters: dict[str, Any] = {}

        severity_label = kwargs.get("severity_label")
        if severity_label:
            filters["SeverityLabel"] = [
                {"Value": severity_label.upper(), "Comparison": "EQUALS"}
            ]

        workflow_status = kwargs.get("workflow_status")
        if workflow_status:
            filters["WorkflowStatus"] = [
                {"Value": workflow_status.upper(), "Comparison": "EQUALS"}
            ]

        product_name = kwargs.get("product_name")
        if product_name:
            filters["ProductName"] = [{"Value": product_name, "Comparison": "EQUALS"}]

        if filters:
            body["Filters"] = filters

        next_token = kwargs.get("next_token")
        if next_token:
            body["NextToken"] = next_token

        try:
            response = await self._securityhub_request(
                SECURITYHUB_TARGET_GET_FINDINGS,
                body=body,
            )
            data = response.json()
            findings = data.get("Findings", [])
            return self.success_result(
                data={
                    "findings": findings,
                    "count": len(findings),
                    "next_token": data.get("NextToken"),
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("aws_security_list_findings_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_list_findings_failed", error=e)
            return self.error_result(e)

class GetFindingAction(_SecurityHubBase):
    """Get Security Hub finding details by finding ID (ARN)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a specific finding by its ARN.

        Args:
            finding_id: The ARN of the finding
        """
        finding_id = kwargs.get("finding_id")
        if not finding_id:
            return self.error_result(
                "Missing required parameter: finding_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        body = {
            "Filters": {"Id": [{"Value": finding_id, "Comparison": "EQUALS"}]},
            "MaxResults": 1,
        }

        try:
            response = await self._securityhub_request(
                SECURITYHUB_TARGET_GET_FINDINGS,
                body=body,
            )
            data = response.json()
            findings = data.get("Findings", [])

            if not findings:
                self.log_info("aws_security_finding_not_found", finding_id=finding_id)
                return self.success_result(
                    not_found=True,
                    data={"finding_id": finding_id},
                )

            return self.success_result(data={"finding": findings[0]})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"finding_id": finding_id},
                )
            self.log_error("aws_security_get_finding_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_get_finding_failed", error=e)
            return self.error_result(e)

class UpdateFindingStatusAction(_SecurityHubBase):
    """Update the workflow status of a Security Hub finding."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update finding workflow status.

        Args:
            finding_id: The ARN of the finding
            product_arn: The ARN of the product that generated the finding
            workflow_status: New status (NEW, NOTIFIED, SUPPRESSED, RESOLVED)
            note: Optional note explaining the status change
        """
        finding_id = kwargs.get("finding_id")
        if not finding_id:
            return self.error_result(
                "Missing required parameter: finding_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        product_arn = kwargs.get("product_arn")
        if not product_arn:
            return self.error_result(
                "Missing required parameter: product_arn",
                error_type=ERROR_TYPE_VALIDATION,
            )

        workflow_status = kwargs.get("workflow_status")
        valid_statuses = {"NEW", "NOTIFIED", "SUPPRESSED", "RESOLVED"}
        if not workflow_status or workflow_status.upper() not in valid_statuses:
            return self.error_result(
                f"workflow_status must be one of: {', '.join(sorted(valid_statuses))}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        body: dict[str, Any] = {
            "FindingIdentifiers": [{"Id": finding_id, "ProductArn": product_arn}],
            "Workflow": {"Status": workflow_status.upper()},
        }

        note_text = kwargs.get("note")
        if note_text:
            body["Note"] = {
                "Text": note_text,
                "UpdatedBy": "Analysi",
            }

        try:
            response = await self._securityhub_request(
                SECURITYHUB_TARGET_BATCH_UPDATE,
                body=body,
            )
            data = response.json()
            processed = data.get("ProcessedFindings", [])
            unprocessed = data.get("UnprocessedFindings", [])

            return self.success_result(
                data={
                    "finding_id": finding_id,
                    "workflow_status": workflow_status.upper(),
                    "processed_count": len(processed),
                    "unprocessed_count": len(unprocessed),
                    "unprocessed_findings": unprocessed,
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("aws_security_update_finding_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_update_finding_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GuardDuty actions
# ============================================================================

class ListGuarddutyDetectorsAction(_GuardDutyBase):
    """List GuardDuty detector IDs."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all GuardDuty detector IDs in the region.

        Args:
            max_results: Max detectors to return (1-50, default 50)
            next_token: Pagination token
        """
        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        query: dict[str, str] = {}
        max_results = kwargs.get("max_results")
        if max_results:
            query["maxResults"] = str(min(int(max_results), 50))

        next_token = kwargs.get("next_token")
        if next_token:
            query["nextToken"] = next_token

        try:
            response = await self._guardduty_request(
                method="GET",
                uri="/detector",
                query_params=query or None,
            )
            data = response.json()
            detector_ids = data.get("detectorIds", [])
            return self.success_result(
                data={
                    "detector_ids": detector_ids,
                    "count": len(detector_ids),
                    "next_token": data.get("nextToken"),
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("aws_security_list_detectors_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_list_detectors_failed", error=e)
            return self.error_result(e)

class ListGuarddutyFindingsAction(_GuardDutyBase):
    """List GuardDuty findings for a detector."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List findings for a given detector.

        Args:
            detector_id: The GuardDuty detector ID (required)
            severity_min: Minimum severity (0-8, optional)
            finding_type: Filter by finding type prefix (optional)
            max_results: Max findings (1-50, default 50)
            next_token: Pagination token
        """
        detector_id = kwargs.get("detector_id")
        if not detector_id:
            return self.error_result(
                "Missing required parameter: detector_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # POST /detector/{detectorId}/findings to list finding IDs
        body: dict[str, Any] = {
            "maxResults": min(int(kwargs.get("max_results", 50)), 50),
        }

        # Build finding criteria
        criteria: dict[str, Any] = {}
        severity_min = kwargs.get("severity_min")
        if severity_min is not None:
            criteria["severity"] = {"gte": int(severity_min)}

        finding_type = kwargs.get("finding_type")
        if finding_type:
            criteria["type"] = {"eq": [finding_type]}

        if criteria:
            body["findingCriteria"] = {"criterion": criteria}

        next_token = kwargs.get("next_token")
        if next_token:
            body["nextToken"] = next_token

        try:
            response = await self._guardduty_request(
                method="POST",
                uri=f"/detector/{detector_id}/findings",
                body=body,
            )
            data = response.json()
            finding_ids = data.get("findingIds", [])
            return self.success_result(
                data={
                    "finding_ids": finding_ids,
                    "count": len(finding_ids),
                    "next_token": data.get("nextToken"),
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("aws_security_list_gd_findings_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_list_gd_findings_failed", error=e)
            return self.error_result(e)

class GetGuarddutyFindingAction(_GuardDutyBase):
    """Get GuardDuty finding details."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get details for specific GuardDuty findings.

        Args:
            detector_id: The GuardDuty detector ID (required)
            finding_ids: List of finding IDs to retrieve (required)
        """
        detector_id = kwargs.get("detector_id")
        if not detector_id:
            return self.error_result(
                "Missing required parameter: detector_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        finding_ids = kwargs.get("finding_ids")
        if not finding_ids:
            return self.error_result(
                "Missing required parameter: finding_ids",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Normalize to list
        if isinstance(finding_ids, str):
            finding_ids = [finding_ids]

        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # POST /detector/{detectorId}/findings/get
        body = {"findingIds": finding_ids}

        try:
            response = await self._guardduty_request(
                method="POST",
                uri=f"/detector/{detector_id}/findings/get",
                body=body,
            )
            data = response.json()
            findings = data.get("findings", [])

            if not findings:
                return self.success_result(
                    not_found=True,
                    data={
                        "detector_id": detector_id,
                        "finding_ids": finding_ids,
                    },
                )

            return self.success_result(
                data={
                    "findings": findings,
                    "count": len(findings),
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={
                        "detector_id": detector_id,
                        "finding_ids": finding_ids,
                    },
                )
            self.log_error("aws_security_get_gd_finding_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_get_gd_finding_failed", error=e)
            return self.error_result(e)

class ArchiveGuarddutyFindingAction(_GuardDutyBase):
    """Archive a GuardDuty finding."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Archive GuardDuty findings by marking them with archive feedback.

        Args:
            detector_id: The GuardDuty detector ID (required)
            finding_ids: List of finding IDs to archive (required)
        """
        detector_id = kwargs.get("detector_id")
        if not detector_id:
            return self.error_result(
                "Missing required parameter: detector_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        finding_ids = kwargs.get("finding_ids")
        if not finding_ids:
            return self.error_result(
                "Missing required parameter: finding_ids",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if isinstance(finding_ids, str):
            finding_ids = [finding_ids]

        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # POST /detector/{detectorId}/findings/archive
        body = {"findingIds": finding_ids}

        try:
            await self._guardduty_request(
                method="POST",
                uri=f"/detector/{detector_id}/findings/archive",
                body=body,
            )
            return self.success_result(
                data={
                    "detector_id": detector_id,
                    "archived_finding_ids": finding_ids,
                    "count": len(finding_ids),
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("aws_security_archive_gd_finding_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("aws_security_archive_gd_finding_failed", error=e)
            return self.error_result(e)

# ============================================================================
# AlertSource actions (pull_alerts + alerts_to_ocsf)
# ============================================================================

class PullAlertsLegacyAction(_AWSBase):
    """Pull alerts from both Security Hub (ASFF) and GuardDuty (legacy path).

    Combines findings from both services into a unified list.
    Security Hub findings are fetched via GetFindings (ASFF format) with a
    CreatedAt time filter. GuardDuty findings are listed and fetched with
    an updatedAt criterion.

    Extends _AWSBase directly (not _SecurityHubBase/_GuardDutyBase) to
    avoid MRO conflicts with _get_host(). Uses explicit host construction.

    Superseded by PullAlertsAction which uses GetFindingsV2 (native OCSF).
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull alerts from Security Hub and GuardDuty within a time range.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of alerts to return (default: 200)

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting (default: 5 minutes).
        """
        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time")
        start_time = params.get("start_time")

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        if not end_time:
            end_time = now

        if start_time and isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if not start_time:
            lookback = self.settings.get(
                SETTINGS_DEFAULT_LOOKBACK, DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback)

        max_results = params.get("max_results", DEFAULT_MAX_ALERTS)

        all_alerts: list[dict[str, Any]] = []

        # Pull from Security Hub
        try:
            sh_alerts = await self._pull_securityhub(start_time, end_time, max_results)
            all_alerts.extend(sh_alerts)
        except Exception as e:
            logger.warning(
                "aws_security_pull_securityhub_failed",
                error=str(e),
            )

        # Pull from GuardDuty (only if detector_id is configured)
        detector_id = self.settings.get(SETTINGS_GUARDDUTY_DETECTOR_ID)
        if detector_id:
            remaining = max(0, max_results - len(all_alerts))
            if remaining > 0:
                try:
                    gd_alerts = await self._pull_guardduty(
                        detector_id, start_time, remaining
                    )
                    all_alerts.extend(gd_alerts)
                except Exception as e:
                    logger.warning(
                        "aws_security_pull_guardduty_failed",
                        error=str(e),
                    )

        return self.success_result(
            data={
                "alerts_count": len(all_alerts),
                "alerts": all_alerts,
                "message": f"Retrieved {len(all_alerts)} alerts",
            }
        )

    async def _pull_securityhub(
        self,
        start_time: datetime,
        end_time: datetime,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Pull findings from Security Hub with time filter."""
        host = SECURITYHUB_HOST_TEMPLATE.format(region=self._get_region())
        all_findings: list[dict[str, Any]] = []
        next_token: str | None = None

        while len(all_findings) < max_results:
            page_size = min(ALERT_PAGE_SIZE, max_results - len(all_findings))
            body: dict[str, Any] = {
                "Filters": {
                    "CreatedAt": [
                        {
                            "Start": start_time.isoformat(),
                            "End": end_time.isoformat(),
                        }
                    ],
                },
                "MaxResults": page_size,
            }
            if next_token:
                body["NextToken"] = next_token

            response = await self._aws_request(
                service=SECURITYHUB_SERVICE,
                host=host,
                method="POST",
                extra_headers={
                    "X-Amz-Target": SECURITYHUB_TARGET_GET_FINDINGS,
                },
                body=body,
            )
            data = response.json()
            findings = data.get("Findings", [])
            all_findings.extend(findings)

            next_token = data.get("NextToken")
            if not next_token or not findings:
                break

        return all_findings

    async def _pull_guardduty(
        self,
        detector_id: str,
        start_time: datetime,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Pull findings from GuardDuty with time filter.

        1. POST /detector/{id}/findings — list finding IDs with updatedAt criterion
        2. POST /detector/{id}/findings/get — get full details
        """
        host = GUARDDUTY_HOST_TEMPLATE.format(region=self._get_region())

        # Step 1: List finding IDs with time filter
        epoch_ms = int(start_time.timestamp() * 1000)
        body: dict[str, Any] = {
            "findingCriteria": {
                "criterion": {
                    "updatedAt": {"greaterThanOrEqual": epoch_ms},
                },
            },
            "maxResults": min(50, max_results),
        }

        response = await self._aws_request(
            service=GUARDDUTY_SERVICE,
            host=host,
            method="POST",
            uri=f"/detector/{detector_id}/findings",
            body=body,
        )
        data = response.json()
        finding_ids = data.get("findingIds", [])

        if not finding_ids:
            return []

        # Step 2: Fetch full finding details
        finding_ids = finding_ids[:max_results]
        get_body = {"findingIds": finding_ids}
        response = await self._aws_request(
            service=GUARDDUTY_SERVICE,
            host=host,
            method="POST",
            uri=f"/detector/{detector_id}/findings/get",
            body=get_body,
        )
        data = response.json()
        return data.get("findings", [])

class AlertsToOcsfLegacyAction(_AWSBase):
    """Normalize raw ASFF/GuardDuty alerts to OCSF Detection Finding v1.8.0 (legacy path).

    Delegates to AWSSecurityOCSFNormalizer which handles both GuardDuty
    and Security Hub ASFF finding formats, producing full OCSF Detection
    Findings with metadata, observables, device, actor, and MITRE ATT&CK.

    Superseded by AlertsToOcsfAction which is a pass-through for native
    OCSF findings from GetFindingsV2.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw AWS alerts to OCSF format.

        Args:
            raw_alerts: List of raw AWS finding documents (GuardDuty or Security Hub).

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.aws_security_ocsf import AWSSecurityOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("aws_security_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = AWSSecurityOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "aws_security_alert_to_ocsf_failed",
                    alert_id=alert.get("id") or alert.get("Id"),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

# ============================================================================
# AlertSource actions — native OCSF via GetFindingsV2
# ============================================================================

class PullAlertsAction(_AWSBase):
    """Pull alerts from Security Hub using GetFindingsV2 (native OCSF).

    The new Security Hub API returns findings in OCSF v1.6 format directly,
    eliminating the need for custom normalization. GuardDuty findings are
    automatically included via Security Hub aggregation.

    Project Symi: AlertSource archetype uses this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull OCSF findings from Security Hub via GetFindingsV2.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of alerts to return (default: 200)

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting (default: 5 minutes).
        """
        creds = self._validate_credentials()
        if creds is None:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time") or now
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        start_time = params.get("start_time")
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if not start_time:
            lookback = self.settings.get(
                SETTINGS_DEFAULT_LOOKBACK, DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback)

        max_results = params.get("max_results", DEFAULT_MAX_ALERTS)
        host = SECURITYHUB_HOST_TEMPLATE.format(region=self._get_region())

        all_findings: list[dict[str, Any]] = []
        next_token: str | None = None

        while len(all_findings) < max_results:
            page_size = min(ALERT_PAGE_SIZE, max_results - len(all_findings))
            body: dict[str, Any] = {
                "OcsfFindingFilters": {
                    "CreatedAt": [
                        {
                            "Start": start_time.isoformat(),
                            "End": end_time.isoformat(),
                        }
                    ],
                },
                "MaxResults": page_size,
            }
            if next_token:
                body["NextToken"] = next_token

            try:
                response = await self._aws_request(
                    service=SECURITYHUB_SERVICE,
                    host=host,
                    method="POST",
                    extra_headers={
                        "X-Amz-Target": SECURITYHUB_TARGET_GET_FINDINGS_V2,
                    },
                    body=body,
                )
                data = response.json()
                findings = data.get("Findings", [])
                all_findings.extend(findings)

                next_token = data.get("NextToken")
                if not next_token or not findings:
                    break
            except Exception as e:
                self.log_error("aws_pull_alerts_v2_failed", error=e)
                if not all_findings:
                    return self.error_result(e)
                break  # Return what we have

        return self.success_result(
            data={
                "alerts_count": len(all_findings),
                "alerts": all_findings,
                "message": f"Retrieved {len(all_findings)} OCSF findings via GetFindingsV2",
                "ocsf_native": True,
            }
        )

class AlertsToOcsfAction(_AWSBase):
    """Pass-through normalizer for native OCSF findings from GetFindingsV2.

    Since GetFindingsV2 returns findings already in OCSF v1.6 format,
    this action only adds raw_data and raw_data_hash for deduplication.
    No field mapping needed.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Add dedup fields to already-OCSF findings.

        Args:
            raw_alerts: List of OCSF finding documents from GetFindingsV2.

        Returns:
            dict with status, normalized_alerts, count, and errors.
        """
        raw_alerts = params.get("raw_alerts", [])
        normalized: list[dict[str, Any]] = []
        errors = 0

        for alert in raw_alerts:
            try:
                # Findings are already OCSF — just add dedup fields
                ocsf = dict(alert)  # shallow copy
                raw_json = json.dumps(alert, sort_keys=True, default=str)
                ocsf["raw_data"] = raw_json
                ocsf["raw_data_hash"] = hashlib.sha256(raw_json.encode()).hexdigest()

                # Ensure required fields exist
                if "class_uid" not in ocsf:
                    ocsf["class_uid"] = 2004
                    ocsf["class_name"] = "Detection Finding"
                if "is_alert" not in ocsf:
                    ocsf["is_alert"] = True

                normalized.append(ocsf)
            except Exception:
                logger.exception("aws_ocsf_passthrough_failed")
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }
