"""Unit tests for AWS Security integration actions."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.aws_security.actions import (
    AlertsToOcsfAction,
    AlertsToOcsfLegacyAction,
    ArchiveGuarddutyFindingAction,
    GetFindingAction,
    GetGuarddutyFindingAction,
    HealthCheckAction,
    ListFindingsAction,
    ListGuarddutyDetectorsAction,
    ListGuarddutyFindingsAction,
    PullAlertsAction,
    PullAlertsLegacyAction,
    UpdateFindingStatusAction,
    _build_canonical_query_string,
    _derive_signing_key,
    _sha256_hex,
    sign_request,
)

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def aws_credentials():
    """Standard AWS credentials for testing."""
    return {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }


@pytest.fixture
def aws_credentials_with_token(aws_credentials):
    """AWS credentials with a session token."""
    return {
        **aws_credentials,
        "session_token": "FwoGZXIvYXdzEBYaDH7example",
    }


@pytest.fixture
def aws_settings():
    """Standard settings."""
    return {"region": "us-east-1", "timeout": 30}


def _make_action(cls, credentials=None, settings=None, action_id="test"):
    """Create an action instance with defaults."""
    return cls(
        integration_id="aws_security",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def _mock_response(json_data, status_code=200):
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


# ============================================================================
# SigV4 helpers unit tests
# ============================================================================


class TestSigV4Helpers:
    """Tests for low-level SigV4 signing functions."""

    def test_sha256_hex_empty(self):
        """SHA-256 of empty payload matches known constant."""
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert _sha256_hex(b"") == expected

    def test_sha256_hex_payload(self):
        """SHA-256 of a JSON body is deterministic."""
        payload = b'{"MaxResults":1}'
        digest = _sha256_hex(payload)
        assert len(digest) == 64
        assert digest == _sha256_hex(payload)  # idempotent

    def test_derive_signing_key_deterministic(self):
        """Signing key derivation returns the same result for the same inputs."""
        key1 = _derive_signing_key("secret", "20260409", "us-east-1", "securityhub")
        key2 = _derive_signing_key("secret", "20260409", "us-east-1", "securityhub")
        assert key1 == key2
        assert isinstance(key1, bytes)
        assert len(key1) == 32  # HMAC-SHA256 produces 32 bytes

    def test_derive_signing_key_varies_by_date(self):
        """Different dates produce different signing keys."""
        k1 = _derive_signing_key("secret", "20260409", "us-east-1", "securityhub")
        k2 = _derive_signing_key("secret", "20260410", "us-east-1", "securityhub")
        assert k1 != k2

    def test_derive_signing_key_varies_by_region(self):
        """Different regions produce different signing keys."""
        k1 = _derive_signing_key("secret", "20260409", "us-east-1", "securityhub")
        k2 = _derive_signing_key("secret", "20260409", "eu-west-1", "securityhub")
        assert k1 != k2

    def test_derive_signing_key_varies_by_service(self):
        """Different services produce different signing keys."""
        k1 = _derive_signing_key("secret", "20260409", "us-east-1", "securityhub")
        k2 = _derive_signing_key("secret", "20260409", "us-east-1", "guardduty")
        assert k1 != k2

    def test_canonical_query_string_empty(self):
        """Empty/None params produce empty string."""
        assert _build_canonical_query_string(None) == ""
        assert _build_canonical_query_string({}) == ""

    def test_canonical_query_string_sorted(self):
        """Parameters are sorted alphabetically."""
        result = _build_canonical_query_string({"z": "1", "a": "2"})
        assert result == "a=2&z=1"

    def test_canonical_query_string_encoded(self):
        """Special characters are percent-encoded."""
        result = _build_canonical_query_string({"key": "a b"})
        assert "a%20b" in result


class TestSignRequest:
    """Tests for the full sign_request function."""

    FIXED_TIME = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)

    def test_produces_authorization_header(self):
        """sign_request adds Authorization header to the returned dict."""
        headers: dict[str, str] = {"Content-Type": "application/x-amz-json-1.1"}
        result = sign_request(
            method="POST",
            host="securityhub.us-east-1.amazonaws.com",
            uri="/",
            query_params=None,
            headers=headers,
            payload=b'{"MaxResults":1}',
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            service="securityhub",
            now=self.FIXED_TIME,
        )

        assert "Authorization" in result
        auth = result["Authorization"]
        assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/")
        assert "20260409/us-east-1/securityhub/aws4_request" in auth
        assert "SignedHeaders=" in auth
        assert "Signature=" in auth

    def test_sets_amz_date_header(self):
        """sign_request sets x-amz-date in ISO-8601 basic format."""
        headers: dict[str, str] = {}
        result = sign_request(
            method="GET",
            host="guardduty.us-east-1.amazonaws.com",
            uri="/detector",
            query_params=None,
            headers=headers,
            payload=b"",
            access_key_id="AKID",
            secret_access_key="SECRET",
            region="us-east-1",
            service="guardduty",
            now=self.FIXED_TIME,
        )
        assert result["x-amz-date"] == "20260409T120000Z"

    def test_sets_host_header(self):
        """sign_request sets the host header."""
        headers: dict[str, str] = {}
        sign_request(
            method="GET",
            host="guardduty.eu-west-1.amazonaws.com",
            uri="/detector",
            query_params=None,
            headers=headers,
            payload=b"",
            access_key_id="AKID",
            secret_access_key="SECRET",
            region="eu-west-1",
            service="guardduty",
            now=self.FIXED_TIME,
        )
        assert headers["host"] == "guardduty.eu-west-1.amazonaws.com"

    def test_signed_headers_are_sorted(self):
        """SignedHeaders value lists headers in alphabetical order."""
        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "SecurityHubService.GetFindings",
        }
        result = sign_request(
            method="POST",
            host="securityhub.us-east-1.amazonaws.com",
            uri="/",
            query_params=None,
            headers=headers,
            payload=b"{}",
            access_key_id="AKID",
            secret_access_key="SECRET",
            region="us-east-1",
            service="securityhub",
            now=self.FIXED_TIME,
        )
        # Extract SignedHeaders value
        auth = result["Authorization"]
        sh_start = auth.index("SignedHeaders=") + len("SignedHeaders=")
        sh_end = auth.index(",", sh_start)
        signed_headers = auth[sh_start:sh_end].split(";")
        assert signed_headers == sorted(signed_headers)

    def test_deterministic_signature(self):
        """Same inputs always produce the same signature."""
        kwargs = {
            "method": "POST",
            "host": "securityhub.us-east-1.amazonaws.com",
            "uri": "/",
            "query_params": None,
            "payload": b'{"MaxResults":1}',
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "region": "us-east-1",
            "service": "securityhub",
            "now": self.FIXED_TIME,
        }
        h1 = sign_request(
            **kwargs, headers={"Content-Type": "application/x-amz-json-1.1"}
        )
        h2 = sign_request(
            **kwargs, headers={"Content-Type": "application/x-amz-json-1.1"}
        )

        # Extract signature from both
        def _extract_sig(auth):
            return auth.split("Signature=")[1]

        assert _extract_sig(h1["Authorization"]) == _extract_sig(h2["Authorization"])

    def test_different_payloads_produce_different_signatures(self):
        """Different request bodies change the signature."""
        common = {
            "method": "POST",
            "host": "securityhub.us-east-1.amazonaws.com",
            "uri": "/",
            "query_params": None,
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "region": "us-east-1",
            "service": "securityhub",
            "now": self.FIXED_TIME,
        }
        h1 = sign_request(**common, payload=b'{"a":1}', headers={})
        h2 = sign_request(**common, payload=b'{"b":2}', headers={})

        sig1 = h1["Authorization"].split("Signature=")[1]
        sig2 = h2["Authorization"].split("Signature=")[1]
        assert sig1 != sig2

    def test_query_params_included_in_signature(self):
        """Query parameters affect the canonical request and thus the signature."""
        common = {
            "method": "GET",
            "host": "guardduty.us-east-1.amazonaws.com",
            "uri": "/detector",
            "payload": b"",
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "region": "us-east-1",
            "service": "guardduty",
            "now": self.FIXED_TIME,
        }
        h1 = sign_request(**common, query_params=None, headers={})
        h2 = sign_request(**common, query_params={"maxResults": "10"}, headers={})

        sig1 = h1["Authorization"].split("Signature=")[1]
        sig2 = h2["Authorization"].split("Signature=")[1]
        assert sig1 != sig2


# ============================================================================
# HealthCheckAction tests
# ============================================================================


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successful health check returns healthy=True."""
        action = _make_action(
            HealthCheckAction, aws_credentials, aws_settings, "health_check"
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"Findings": [{"Id": "f1"}]})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["region"] == "us-east-1"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns ConfigurationError."""
        action = _make_action(HealthCheckAction, {}, aws_settings, "health_check")

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, aws_credentials, aws_settings):
        """HTTP error during health check returns error."""
        action = _make_action(
            HealthCheckAction, aws_credentials, aws_settings, "health_check"
        )
        action.http_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


# ============================================================================
# ListFindingsAction tests
# ============================================================================


class TestListFindingsAction:
    """Tests for ListFindingsAction."""

    @pytest.mark.asyncio
    async def test_success_no_filters(self, aws_credentials, aws_settings):
        """List findings without filters returns results."""
        action = _make_action(
            ListFindingsAction, aws_credentials, aws_settings, "list_findings"
        )
        findings = [{"Id": "arn:aws:sh:f1"}, {"Id": "arn:aws:sh:f2"}]
        action.http_request = AsyncMock(
            return_value=_mock_response({"Findings": findings})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["findings"]) == 2

    @pytest.mark.asyncio
    async def test_with_severity_filter(self, aws_credentials, aws_settings):
        """Severity filter is passed to the API body."""
        action = _make_action(
            ListFindingsAction, aws_credentials, aws_settings, "list_findings"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        result = await action.execute(severity_label="HIGH")

        assert result["status"] == "success"
        # Verify the request was made (http_request called once)
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_pagination(self, aws_credentials, aws_settings):
        """NextToken is included in response."""
        action = _make_action(
            ListFindingsAction, aws_credentials, aws_settings, "list_findings"
        )
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"Findings": [{"Id": "f1"}], "NextToken": "abc123"}
            )
        )

        result = await action.execute(max_results=1)

        assert result["status"] == "success"
        assert result["data"]["next_token"] == "abc123"

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns error."""
        action = _make_action(ListFindingsAction, {}, aws_settings, "list_findings")

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, aws_credentials, aws_settings):
        """HTTP error returns error result."""
        action = _make_action(
            ListFindingsAction, aws_credentials, aws_settings, "list_findings"
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        error = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=mock_resp
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GetFindingAction tests
# ============================================================================


class TestGetFindingAction:
    """Tests for GetFindingAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully retrieves a finding by ARN."""
        action = _make_action(
            GetFindingAction, aws_credentials, aws_settings, "get_finding"
        )
        finding = {
            "Id": "arn:aws:sh:f1",
            "Title": "Test Finding",
            "Severity": {"Label": "HIGH"},
        }
        action.http_request = AsyncMock(
            return_value=_mock_response({"Findings": [finding]})
        )

        result = await action.execute(finding_id="arn:aws:sh:f1")

        assert result["status"] == "success"
        assert result["data"]["finding"]["Title"] == "Test Finding"

    @pytest.mark.asyncio
    async def test_not_found_empty_results(self, aws_credentials, aws_settings):
        """Empty findings list returns not_found=True."""
        action = _make_action(
            GetFindingAction, aws_credentials, aws_settings, "get_finding"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        result = await action.execute(finding_id="arn:aws:sh:missing")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_not_found_404(self, aws_credentials, aws_settings):
        """404 HTTP status returns not_found=True (not crash)."""
        action = _make_action(
            GetFindingAction, aws_credentials, aws_settings, "get_finding"
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        error = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_resp
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(finding_id="arn:aws:sh:missing")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_finding_id(self, aws_credentials, aws_settings):
        """Missing finding_id returns ValidationError."""
        action = _make_action(
            GetFindingAction, aws_credentials, aws_settings, "get_finding"
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# UpdateFindingStatusAction tests
# ============================================================================


class TestUpdateFindingStatusAction:
    """Tests for UpdateFindingStatusAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully updates finding status."""
        action = _make_action(
            UpdateFindingStatusAction,
            aws_credentials,
            aws_settings,
            "update_finding_status",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "ProcessedFindings": [{"Id": "f1"}],
                    "UnprocessedFindings": [],
                }
            )
        )

        result = await action.execute(
            finding_id="arn:aws:sh:f1",
            product_arn="arn:aws:securityhub:us-east-1::product/aws/guardduty",
            workflow_status="RESOLVED",
        )

        assert result["status"] == "success"
        assert result["data"]["workflow_status"] == "RESOLVED"
        assert result["data"]["processed_count"] == 1
        assert result["data"]["unprocessed_count"] == 0

    @pytest.mark.asyncio
    async def test_with_note(self, aws_credentials, aws_settings):
        """Note is included when provided."""
        action = _make_action(
            UpdateFindingStatusAction,
            aws_credentials,
            aws_settings,
            "update_finding_status",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "ProcessedFindings": [{"Id": "f1"}],
                    "UnprocessedFindings": [],
                }
            )
        )

        result = await action.execute(
            finding_id="arn:aws:sh:f1",
            product_arn="arn:aws:prod",
            workflow_status="NOTIFIED",
            note="Reviewed by SOC team",
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_finding_id(self, aws_credentials, aws_settings):
        """Missing finding_id returns ValidationError."""
        action = _make_action(
            UpdateFindingStatusAction,
            aws_credentials,
            aws_settings,
            "update_finding_status",
        )
        result = await action.execute(
            product_arn="arn:aws:prod", workflow_status="RESOLVED"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_product_arn(self, aws_credentials, aws_settings):
        """Missing product_arn returns ValidationError."""
        action = _make_action(
            UpdateFindingStatusAction,
            aws_credentials,
            aws_settings,
            "update_finding_status",
        )
        result = await action.execute(
            finding_id="arn:aws:sh:f1", workflow_status="RESOLVED"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_status(self, aws_credentials, aws_settings):
        """Invalid workflow_status returns ValidationError."""
        action = _make_action(
            UpdateFindingStatusAction,
            aws_credentials,
            aws_settings,
            "update_finding_status",
        )
        result = await action.execute(
            finding_id="arn:aws:sh:f1",
            product_arn="arn:aws:prod",
            workflow_status="INVALID",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns ConfigurationError."""
        action = _make_action(
            UpdateFindingStatusAction, {}, aws_settings, "update_finding_status"
        )
        result = await action.execute(
            finding_id="arn:aws:sh:f1",
            product_arn="arn:aws:prod",
            workflow_status="RESOLVED",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ListGuarddutyDetectorsAction tests
# ============================================================================


class TestListGuarddutyDetectorsAction:
    """Tests for ListGuarddutyDetectorsAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully lists detectors."""
        action = _make_action(
            ListGuarddutyDetectorsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_detectors",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"detectorIds": ["d-123", "d-456"]})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert "d-123" in result["data"]["detector_ids"]

    @pytest.mark.asyncio
    async def test_empty_list(self, aws_credentials, aws_settings):
        """Empty detector list is a valid success."""
        action = _make_action(
            ListGuarddutyDetectorsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_detectors",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"detectorIds": []})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns ConfigurationError."""
        action = _make_action(
            ListGuarddutyDetectorsAction, {}, aws_settings, "list_guardduty_detectors"
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ListGuarddutyFindingsAction tests
# ============================================================================


class TestListGuarddutyFindingsAction:
    """Tests for ListGuarddutyFindingsAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully lists GuardDuty findings."""
        action = _make_action(
            ListGuarddutyFindingsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_findings",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"findingIds": ["gd-f1", "gd-f2"]})
        )

        result = await action.execute(detector_id="d-123")

        assert result["status"] == "success"
        assert result["data"]["count"] == 2

    @pytest.mark.asyncio
    async def test_with_severity_filter(self, aws_credentials, aws_settings):
        """Severity filter is accepted."""
        action = _make_action(
            ListGuarddutyFindingsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_findings",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"findingIds": ["gd-f1"]})
        )

        result = await action.execute(detector_id="d-123", severity_min=5)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_detector_id(self, aws_credentials, aws_settings):
        """Missing detector_id returns ValidationError."""
        action = _make_action(
            ListGuarddutyFindingsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_findings",
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns ConfigurationError."""
        action = _make_action(
            ListGuarddutyFindingsAction,
            {},
            aws_settings,
            "list_guardduty_findings",
        )

        result = await action.execute(detector_id="d-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GetGuarddutyFindingAction tests
# ============================================================================


class TestGetGuarddutyFindingAction:
    """Tests for GetGuarddutyFindingAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully retrieves GuardDuty finding details."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )
        finding = {
            "id": "gd-f1",
            "type": "Recon:EC2/PortProbeUnprotectedPort",
            "severity": 5,
        }
        action.http_request = AsyncMock(
            return_value=_mock_response({"findings": [finding]})
        )

        result = await action.execute(detector_id="d-123", finding_ids=["gd-f1"])

        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert (
            result["data"]["findings"][0]["type"]
            == "Recon:EC2/PortProbeUnprotectedPort"
        )

    @pytest.mark.asyncio
    async def test_single_string_finding_id(self, aws_credentials, aws_settings):
        """A single string finding_id is normalized to a list."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"findings": [{"id": "gd-f1"}]})
        )

        result = await action.execute(detector_id="d-123", finding_ids="gd-f1")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_not_found_empty(self, aws_credentials, aws_settings):
        """Empty findings returns not_found=True."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )
        action.http_request = AsyncMock(return_value=_mock_response({"findings": []}))

        result = await action.execute(detector_id="d-123", finding_ids=["gd-missing"])

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_not_found_404(self, aws_credentials, aws_settings):
        """404 HTTP status returns not_found=True."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        error = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_resp
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(detector_id="d-123", finding_ids=["gd-missing"])

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_detector_id(self, aws_credentials, aws_settings):
        """Missing detector_id returns ValidationError."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )

        result = await action.execute(finding_ids=["gd-f1"])

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_finding_ids(self, aws_credentials, aws_settings):
        """Missing finding_ids returns ValidationError."""
        action = _make_action(
            GetGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "get_guardduty_finding",
        )

        result = await action.execute(detector_id="d-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# ArchiveGuarddutyFindingAction tests
# ============================================================================


class TestArchiveGuarddutyFindingAction:
    """Tests for ArchiveGuarddutyFindingAction."""

    @pytest.mark.asyncio
    async def test_success(self, aws_credentials, aws_settings):
        """Successfully archives findings."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "archive_guardduty_finding",
        )
        action.http_request = AsyncMock(return_value=_mock_response({}))

        result = await action.execute(
            detector_id="d-123", finding_ids=["gd-f1", "gd-f2"]
        )

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert "gd-f1" in result["data"]["archived_finding_ids"]

    @pytest.mark.asyncio
    async def test_single_string_finding_id(self, aws_credentials, aws_settings):
        """A single string finding_id is normalized."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "archive_guardduty_finding",
        )
        action.http_request = AsyncMock(return_value=_mock_response({}))

        result = await action.execute(detector_id="d-123", finding_ids="gd-f1")

        assert result["status"] == "success"
        assert result["data"]["count"] == 1

    @pytest.mark.asyncio
    async def test_missing_detector_id(self, aws_credentials, aws_settings):
        """Missing detector_id returns ValidationError."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "archive_guardduty_finding",
        )

        result = await action.execute(finding_ids=["gd-f1"])

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_finding_ids(self, aws_credentials, aws_settings):
        """Missing finding_ids returns ValidationError."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "archive_guardduty_finding",
        )

        result = await action.execute(detector_id="d-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self, aws_settings):
        """Missing credentials returns ConfigurationError."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            {},
            aws_settings,
            "archive_guardduty_finding",
        )

        result = await action.execute(detector_id="d-123", finding_ids=["gd-f1"])

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, aws_credentials, aws_settings):
        """HTTP error returns error result."""
        action = _make_action(
            ArchiveGuarddutyFindingAction,
            aws_credentials,
            aws_settings,
            "archive_guardduty_finding",
        )
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        error = httpx.HTTPStatusError(
            "500 Internal Server Error", request=MagicMock(), response=mock_resp
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(detector_id="d-123", finding_ids=["gd-f1"])

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# _AWSBase._aws_request tests (via actions)
# ============================================================================


class TestAWSBaseIntegration:
    """Tests for shared _AWSBase behavior accessed through concrete actions."""

    @pytest.mark.asyncio
    async def test_session_token_in_headers(
        self, aws_credentials_with_token, aws_settings
    ):
        """Session token is passed as X-Amz-Security-Token header."""
        action = _make_action(
            HealthCheckAction, aws_credentials_with_token, aws_settings, "health_check"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert "X-Amz-Security-Token" in call_kwargs["headers"]
        assert (
            call_kwargs["headers"]["X-Amz-Security-Token"]
            == "FwoGZXIvYXdzEBYaDH7example"
        )

    @pytest.mark.asyncio
    async def test_default_region(self, aws_credentials):
        """Default region is us-east-1 when not specified in settings."""
        action = _make_action(HealthCheckAction, aws_credentials, {}, "health_check")
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["region"] == "us-east-1"

    @pytest.mark.asyncio
    async def test_custom_region(self, aws_credentials):
        """Custom region is used when provided."""
        settings = {"region": "eu-west-1"}
        action = _make_action(
            HealthCheckAction, aws_credentials, settings, "health_check"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        result = await action.execute()

        assert result["data"]["region"] == "eu-west-1"
        # Verify URL uses eu-west-1
        call_kwargs = action.http_request.call_args.kwargs
        assert "eu-west-1" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_securityhub_target_header(self, aws_credentials, aws_settings):
        """Security Hub requests include X-Amz-Target header."""
        action = _make_action(
            HealthCheckAction, aws_credentials, aws_settings, "health_check"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert (
            call_kwargs["headers"]["X-Amz-Target"] == "SecurityHubService.GetFindings"
        )

    @pytest.mark.asyncio
    async def test_guardduty_uses_rest_uri(self, aws_credentials, aws_settings):
        """GuardDuty requests use REST-style URI paths."""
        action = _make_action(
            ListGuarddutyDetectorsAction,
            aws_credentials,
            aws_settings,
            "list_guardduty_detectors",
        )
        action.http_request = AsyncMock(
            return_value=_mock_response({"detectorIds": []})
        )

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert "/detector" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_request_uses_content_not_json_data(
        self, aws_credentials, aws_settings
    ):
        """Signed requests send pre-serialized bytes via content=, not json_data=."""
        action = _make_action(
            HealthCheckAction, aws_credentials, aws_settings, "health_check"
        )
        action.http_request = AsyncMock(return_value=_mock_response({"Findings": []}))

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        # Must use content= (pre-serialized for signing) not json_data=
        assert "content" in call_kwargs
        assert isinstance(call_kwargs["content"], bytes)


# ============================================================================
# PullAlertsAction Tests (native OCSF via GetFindingsV2)
# ============================================================================


class TestPullAlertsAction:
    """Tests for the native OCSF GetFindingsV2 alert puller."""

    @pytest.fixture
    def pull_action(self, aws_credentials, aws_settings):
        """Create PullAlertsAction with credentials."""
        return _make_action(
            PullAlertsAction, aws_credentials, aws_settings, "pull_alerts"
        )

    @pytest.mark.asyncio
    async def test_pull_returns_ocsf_findings(self, pull_action):
        """GetFindingsV2 returns native OCSF findings."""
        now = datetime.now(UTC)
        v2_response = _mock_response(
            {
                "Findings": [
                    {
                        "class_uid": 2004,
                        "class_name": "Detection Finding",
                        "finding_info": {"uid": "ocsf-001"},
                        "severity_id": 4,
                    },
                    {
                        "class_uid": 2004,
                        "class_name": "Detection Finding",
                        "finding_info": {"uid": "ocsf-002"},
                        "severity_id": 2,
                    },
                ],
            }
        )
        pull_action.http_request = AsyncMock(return_value=v2_response)

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 2
        assert result["data"]["ocsf_native"] is True
        assert len(result["data"]["alerts"]) == 2

    @pytest.mark.asyncio
    async def test_pull_uses_get_findings_v2_target(self, pull_action):
        """Request uses GetFindingsV2 X-Amz-Target header."""
        v2_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=v2_response)

        await pull_action.execute()

        call_kwargs = pull_action.http_request.call_args.kwargs
        assert (
            call_kwargs["headers"]["X-Amz-Target"] == "SecurityHubService.GetFindingsV2"
        )

    @pytest.mark.asyncio
    async def test_pull_uses_ocsf_finding_filters(self, pull_action):
        """Request body uses OcsfFindingFilters, not Filters."""
        v2_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=v2_response)

        await pull_action.execute(
            start_time="2025-06-15T10:00:00+00:00",
            end_time="2025-06-15T11:00:00+00:00",
        )

        call_kwargs = pull_action.http_request.call_args.kwargs
        body = json.loads(call_kwargs["content"])
        assert "OcsfFindingFilters" in body
        assert "Filters" not in body
        assert "CreatedAt" in body["OcsfFindingFilters"]

    @pytest.mark.asyncio
    async def test_pull_empty_results(self, pull_action):
        """Empty results from GetFindingsV2."""
        now = datetime.now(UTC)
        v2_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=v2_response)

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 0
        assert result["data"]["alerts"] == []
        assert result["data"]["ocsf_native"] is True

    @pytest.mark.asyncio
    async def test_pull_missing_credentials(self):
        """Missing credentials returns error."""
        action = _make_action(PullAlertsAction, {}, {}, "pull_alerts")
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_pull_default_lookback(self, pull_action):
        """Default lookback is used when no start_time given."""
        v2_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=v2_response)

        result = await pull_action.execute()

        assert result["status"] == "success"
        assert pull_action.http_request.called

    @pytest.mark.asyncio
    async def test_pull_iso_string_times(self, pull_action):
        """ISO string time parameters are parsed correctly."""
        v2_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=v2_response)

        result = await pull_action.execute(
            start_time="2025-06-15T10:00:00+00:00",
            end_time="2025-06-15T11:00:00+00:00",
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_pull_pagination(self, pull_action):
        """GetFindingsV2 pagination with NextToken."""
        now = datetime.now(UTC)

        page1 = _mock_response(
            {
                "Findings": [
                    {"class_uid": 2004, "finding_info": {"uid": f"ocsf-{i}"}}
                    for i in range(100)
                ],
                "NextToken": "page2-token",
            }
        )
        page2 = _mock_response(
            {
                "Findings": [
                    {"class_uid": 2004, "finding_info": {"uid": f"ocsf-{i}"}}
                    for i in range(100, 150)
                ],
            }
        )

        pull_action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
            max_results=200,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 150

    @pytest.mark.asyncio
    async def test_pull_api_error_no_partial(self, pull_action):
        """API error with no findings yet returns error result."""
        pull_action.http_request = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await pull_action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_pull_api_error_returns_partial(self, pull_action):
        """API error after collecting some findings returns what we have."""
        now = datetime.now(UTC)

        page1 = _mock_response(
            {
                "Findings": [
                    {"class_uid": 2004, "finding_info": {"uid": f"ocsf-{i}"}}
                    for i in range(100)
                ],
                "NextToken": "page2-token",
            }
        )

        pull_action.http_request = AsyncMock(side_effect=[page1, Exception("Timeout")])

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
            max_results=200,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 100


# ============================================================================
# AlertsToOcsfAction Tests (pass-through for native OCSF)
# ============================================================================


class TestAlertsToOcsfAction:
    """Tests for the native OCSF pass-through normalizer."""

    @pytest.fixture
    def ocsf_action(self):
        """Create AlertsToOcsfAction instance."""
        return _make_action(AlertsToOcsfAction, {}, {}, "alerts_to_ocsf")

    @pytest.mark.asyncio
    async def test_passthrough_adds_dedup_fields(self, ocsf_action):
        """Pass-through adds raw_data and raw_data_hash."""
        raw_alerts = [
            {
                "class_uid": 2004,
                "class_name": "Detection Finding",
                "finding_info": {"uid": "ocsf-001"},
                "severity_id": 4,
            },
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["errors"] == 0
        normalized = result["normalized_alerts"][0]
        assert "raw_data" in normalized
        assert "raw_data_hash" in normalized
        assert len(normalized["raw_data_hash"]) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_passthrough_preserves_class_uid(self, ocsf_action):
        """Existing class_uid is preserved (not overwritten)."""
        raw_alerts = [
            {
                "class_uid": 2004,
                "class_name": "Detection Finding",
                "finding_info": {"uid": "ocsf-001"},
            },
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        normalized = result["normalized_alerts"][0]
        assert normalized["class_uid"] == 2004
        assert normalized["class_name"] == "Detection Finding"

    @pytest.mark.asyncio
    async def test_passthrough_adds_missing_class_uid(self, ocsf_action):
        """Missing class_uid gets default 2004 (Detection Finding)."""
        raw_alerts = [
            {
                "finding_info": {"uid": "ocsf-001"},
                "severity_id": 2,
            },
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        normalized = result["normalized_alerts"][0]
        assert normalized["class_uid"] == 2004
        assert normalized["class_name"] == "Detection Finding"

    @pytest.mark.asyncio
    async def test_passthrough_adds_is_alert(self, ocsf_action):
        """Missing is_alert gets set to True."""
        raw_alerts = [
            {
                "class_uid": 2004,
                "finding_info": {"uid": "ocsf-001"},
            },
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        normalized = result["normalized_alerts"][0]
        assert normalized["is_alert"] is True

    @pytest.mark.asyncio
    async def test_passthrough_preserves_is_alert(self, ocsf_action):
        """Existing is_alert=False is preserved."""
        raw_alerts = [
            {
                "class_uid": 2004,
                "finding_info": {"uid": "ocsf-001"},
                "is_alert": False,
            },
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        normalized = result["normalized_alerts"][0]
        assert normalized["is_alert"] is False

    @pytest.mark.asyncio
    async def test_passthrough_empty_input(self, ocsf_action):
        """Empty input returns empty output."""
        result = await ocsf_action.execute(raw_alerts=[])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["errors"] == 0
        assert result["normalized_alerts"] == []

    @pytest.mark.asyncio
    async def test_passthrough_deterministic_hash(self, ocsf_action):
        """Same input always produces the same raw_data_hash."""
        alert = {
            "class_uid": 2004,
            "finding_info": {"uid": "ocsf-001"},
        }

        result1 = await ocsf_action.execute(raw_alerts=[alert])
        result2 = await ocsf_action.execute(raw_alerts=[alert])

        hash1 = result1["normalized_alerts"][0]["raw_data_hash"]
        hash2 = result2["normalized_alerts"][0]["raw_data_hash"]
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_passthrough_multiple_findings(self, ocsf_action):
        """Multiple findings are all processed."""
        raw_alerts = [
            {"class_uid": 2004, "finding_info": {"uid": f"ocsf-{i}"}} for i in range(5)
        ]

        result = await ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "success"
        assert result["count"] == 5
        assert result["errors"] == 0
        # Each should have a unique hash
        hashes = {n["raw_data_hash"] for n in result["normalized_alerts"]}
        assert len(hashes) == 5


# ============================================================================
# PullAlertsLegacyAction Tests (ASFF + GuardDuty)
# ============================================================================


class TestPullAlertsLegacyAction:
    """Tests for the legacy ASFF + GuardDuty alert puller."""

    @pytest.fixture
    def pull_action(self, aws_credentials, aws_settings):
        """Create PullAlertsLegacyAction with credentials."""
        return _make_action(
            PullAlertsLegacyAction, aws_credentials, aws_settings, "pull_alerts_legacy"
        )

    @pytest.fixture
    def pull_action_with_detector(self, aws_credentials):
        """Create PullAlertsLegacyAction with GuardDuty detector ID."""
        settings = {
            "region": "us-east-1",
            "timeout": 30,
            "guardduty_detector_id": "detector-abc123",
        }
        return _make_action(
            PullAlertsLegacyAction, aws_credentials, settings, "pull_alerts_legacy"
        )

    @pytest.mark.asyncio
    async def test_pull_securityhub_only(self, pull_action):
        """Without detector_id, only Security Hub ASFF findings are pulled."""
        now = datetime.now(UTC)
        sh_response = _mock_response(
            {
                "Findings": [
                    {
                        "Id": "arn:sh:001",
                        "Title": "Finding 1",
                        "Severity": {"Label": "HIGH"},
                    },
                    {
                        "Id": "arn:sh:002",
                        "Title": "Finding 2",
                        "Severity": {"Label": "LOW"},
                    },
                ],
            }
        )
        pull_action.http_request = AsyncMock(return_value=sh_response)

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 2

    @pytest.mark.asyncio
    async def test_pull_uses_get_findings_target(self, pull_action):
        """Legacy path uses GetFindings (not GetFindingsV2) X-Amz-Target."""
        sh_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=sh_response)

        await pull_action.execute()

        call_kwargs = pull_action.http_request.call_args.kwargs
        assert (
            call_kwargs["headers"]["X-Amz-Target"] == "SecurityHubService.GetFindings"
        )

    @pytest.mark.asyncio
    async def test_pull_uses_asff_filters(self, pull_action):
        """Legacy path uses Filters (not OcsfFindingFilters) in request body."""
        sh_response = _mock_response({"Findings": []})
        pull_action.http_request = AsyncMock(return_value=sh_response)

        await pull_action.execute(
            start_time="2025-03-15T10:00:00+00:00",
            end_time="2025-03-15T11:00:00+00:00",
        )

        call_kwargs = pull_action.http_request.call_args.kwargs
        body = json.loads(call_kwargs["content"])
        assert "Filters" in body
        assert "OcsfFindingFilters" not in body

    @pytest.mark.asyncio
    async def test_pull_both_sources(self, pull_action_with_detector):
        """With detector_id, pulls from both Security Hub and GuardDuty."""
        now = datetime.now(UTC)

        sh_response = _mock_response(
            {
                "Findings": [
                    {
                        "Id": "arn:sh:001",
                        "Title": "SH Finding",
                        "Severity": {"Label": "HIGH"},
                    },
                ],
            }
        )
        gd_list_response = _mock_response({"findingIds": ["gd-finding-001"]})
        gd_get_response = _mock_response(
            {
                "findings": [
                    {
                        "id": "gd-finding-001",
                        "type": "Recon:EC2/Test",
                        "severity": 5.0,
                        "title": "GD Finding",
                    }
                ]
            }
        )

        pull_action_with_detector.http_request = AsyncMock(
            side_effect=[sh_response, gd_list_response, gd_get_response]
        )

        result = await pull_action_with_detector.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 2
        alerts = result["data"]["alerts"]
        assert alerts[0]["Id"] == "arn:sh:001"
        assert alerts[1]["id"] == "gd-finding-001"

    @pytest.mark.asyncio
    async def test_pull_missing_credentials(self):
        """Missing credentials returns error."""
        action = _make_action(PullAlertsLegacyAction, {}, {}, "pull_alerts_legacy")
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_pull_securityhub_pagination(self, pull_action):
        """Legacy Security Hub pagination with NextToken."""
        now = datetime.now(UTC)

        page1 = _mock_response(
            {
                "Findings": [
                    {"Id": f"arn:sh:{i}", "Severity": {"Label": "LOW"}}
                    for i in range(100)
                ],
                "NextToken": "page2-token",
            }
        )
        page2 = _mock_response(
            {
                "Findings": [
                    {"Id": f"arn:sh:{i}", "Severity": {"Label": "LOW"}}
                    for i in range(100, 150)
                ],
            }
        )

        pull_action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await pull_action.execute(
            start_time=now - timedelta(hours=1),
            end_time=now,
            max_results=200,
        )

        assert result["status"] == "success"
        assert result["data"]["alerts_count"] == 150


# ============================================================================
# AlertsToOcsfLegacyAction Tests
# ============================================================================


class TestAlertsToOcsfLegacyAction:
    """Tests for the legacy OCSF normalization action."""

    @pytest.fixture
    def ocsf_action(self):
        """Create AlertsToOcsfLegacyAction instance."""
        return _make_action(AlertsToOcsfLegacyAction, {}, {}, "alerts_to_ocsf_legacy")

    @pytest.mark.asyncio
    async def test_normalize_success(self, ocsf_action):
        """Successful normalization via AWSSecurityOCSFNormalizer."""
        raw_alerts = [
            {
                "id": "gd-001",
                "type": "Recon:EC2/PortProbe",
                "severity": 5.0,
                "title": "GD Alert",
                "createdAt": "2025-03-15T10:00:00.000Z",
            },
            {
                "Id": "arn:sh:001",
                "Title": "SH Alert",
                "Severity": {"Label": "HIGH"},
                "CreatedAt": "2025-03-15T10:00:00.000Z",
            },
        ]

        ocsf_doc_gd = {"class_uid": 2004, "finding_info": {"uid": "gd-001"}}
        ocsf_doc_sh = {"class_uid": 2004, "finding_info": {"uid": "arn:sh:001"}}

        mock_normalizer = MagicMock()
        mock_normalizer.to_ocsf.side_effect = [ocsf_doc_gd, ocsf_doc_sh]

        with patch.dict(
            "sys.modules",
            {
                "alert_normalizer": MagicMock(),
                "alert_normalizer.aws_security_ocsf": MagicMock(),
            },
        ):
            with patch(
                "alert_normalizer.aws_security_ocsf.AWSSecurityOCSFNormalizer",
                return_value=mock_normalizer,
            ):
                result = await ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["errors"] == 0
        assert len(result["normalized_alerts"]) == 2

    @pytest.mark.asyncio
    async def test_normalize_empty(self, ocsf_action):
        """Empty input returns empty output."""
        mock_normalizer = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "alert_normalizer": MagicMock(),
                "alert_normalizer.aws_security_ocsf": MagicMock(),
            },
        ):
            with patch(
                "alert_normalizer.aws_security_ocsf.AWSSecurityOCSFNormalizer",
                return_value=mock_normalizer,
            ):
                result = await ocsf_action.execute(raw_alerts=[])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["errors"] == 0
        assert result["normalized_alerts"] == []

    @pytest.mark.asyncio
    async def test_normalize_partial_failure(self, ocsf_action):
        """One failing alert produces partial status."""
        raw_alerts = [
            {"id": "gd-001", "type": "Recon:EC2/Test", "severity": 5.0, "title": "OK"},
            {"id": "gd-bad", "type": "Recon:EC2/Test", "severity": 5.0, "title": "Bad"},
            {"id": "gd-003", "type": "Recon:EC2/Test", "severity": 5.0, "title": "OK2"},
        ]

        ocsf_good = {"class_uid": 2004, "finding_info": {"uid": "ok"}}
        mock_normalizer = MagicMock()
        mock_normalizer.to_ocsf.side_effect = [
            ocsf_good,
            ValueError("bad alert"),
            ocsf_good,
        ]

        with patch.dict(
            "sys.modules",
            {
                "alert_normalizer": MagicMock(),
                "alert_normalizer.aws_security_ocsf": MagicMock(),
            },
        ):
            with patch(
                "alert_normalizer.aws_security_ocsf.AWSSecurityOCSFNormalizer",
                return_value=mock_normalizer,
            ):
                result = await ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "partial"
        assert result["count"] == 2
        assert result["errors"] == 1
