"""Unit tests for NIST NVD integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.nistnvd.actions import (
    CveLookupAction,
    HealthCheckAction,
)


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance for testing."""
    return HealthCheckAction(
        integration_id="nistnvd",
        action_id="health_check",
        settings={"api_version": "2.0", "timeout": 30},
        credentials={},
    )


@pytest.fixture
def cve_lookup_action():
    """Create CveLookupAction instance for testing."""
    return CveLookupAction(
        integration_id="nistnvd",
        action_id="cve_lookup",
        settings={"api_version": "2.0", "timeout": 30},
        credentials={},
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2019-1010218",
                    "descriptions": [{"lang": "en", "value": "Test CVE"}],
                }
            }
        ]
    }

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["api_version"] == "2.0"
    assert "NIST NVD API is accessible" in result["message"]


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check timeout handling."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False
    assert (
        "timeout" in result["error"].lower() or "timed out" in result["error"].lower()
    )


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check HTTP error handling."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "Service unavailable"

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Service unavailable", request=MagicMock(), response=mock_response
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False
    assert result["error_type"] in ("Exception", "HTTPStatusError")


# ============================================================================
# CVE LOOKUP ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_cve_lookup_success(cve_lookup_action):
    """Test successful CVE lookup."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2021-44228",
                    "descriptions": [
                        {"lang": "en", "value": "Apache Log4j2 vulnerability"}
                    ],
                    "published": "2021-12-10T10:15:09.000",
                    "lastModified": "2021-12-14T19:15:08.000",
                    "references": [
                        {"url": "https://example.com/cve"},
                        {"url": "https://example.org/advisory"},
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseScore": 10.0,
                                    "baseSeverity": "CRITICAL",
                                    "attackVector": "NETWORK",
                                    "attackComplexity": "LOW",
                                    "privilegesRequired": "NONE",
                                    "userInteraction": "NONE",
                                    "scope": "CHANGED",
                                    "confidentialityImpact": "HIGH",
                                    "integrityImpact": "HIGH",
                                    "availabilityImpact": "HIGH",
                                },
                                "exploitabilityScore": 3.9,
                                "impactScore": 6.0,
                            }
                        ]
                    },
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await cve_lookup_action.execute(cve="CVE-2021-44228")

    assert result["status"] == "success"
    assert result["cve_id"] == "CVE-2021-44228"
    assert "Apache Log4j2" in result["description"]
    assert result["cvss_metrics"]["base_score"] == 10.0
    assert result["cvss_metrics"]["base_severity"] == "CRITICAL"
    assert len(result["references"]) == 2


@pytest.mark.asyncio
async def test_cve_lookup_missing_cve_parameter(cve_lookup_action):
    """Test CVE lookup with missing CVE parameter."""
    result = await cve_lookup_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "CVE ID must be a non-empty string" in result["error"]


@pytest.mark.asyncio
async def test_cve_lookup_invalid_cve_format(cve_lookup_action):
    """Test CVE lookup with invalid CVE format."""
    result = await cve_lookup_action.execute(cve="INVALID-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "CVE-" in result["error"]


@pytest.mark.asyncio
async def test_cve_lookup_invalid_year_format(cve_lookup_action):
    """Test CVE lookup with invalid year format."""
    result = await cve_lookup_action.execute(cve="CVE-99-1234")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "4 digits" in result["error"]


@pytest.mark.asyncio
async def test_cve_lookup_not_found(cve_lookup_action):
    """Test not-found returns success with not_found flag (not error)."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await cve_lookup_action.execute(cve="CVE-2099-99999")

    assert result["status"] == "success"
    assert result["not_found"] is True


@pytest.mark.asyncio
async def test_cve_lookup_rate_limit(cve_lookup_action):
    """Test CVE lookup rate limit handling."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Rate limit exceeded", request=MagicMock(), response=mock_response
        ),
    ):
        result = await cve_lookup_action.execute(cve="CVE-2021-44228")

    assert result["status"] == "error"
    assert result["error_type"] in ("Exception", "HTTPStatusError")


@pytest.mark.asyncio
async def test_cve_lookup_timeout(cve_lookup_action):
    """Test CVE lookup timeout handling."""
    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timeout"),
    ):
        result = await cve_lookup_action.execute(cve="CVE-2021-44228")

    assert result["status"] == "error"
    assert (
        "timeout" in result["error"].lower() or "timed out" in result["error"].lower()
    )


@pytest.mark.asyncio
async def test_cve_lookup_with_cisa_kev(cve_lookup_action):
    """Test CVE lookup with CISA KEV catalog data."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2021-44228",
                    "descriptions": [
                        {"lang": "en", "value": "Apache Log4j2 vulnerability"}
                    ],
                    "published": "2021-12-10T10:15:09.000",
                    "lastModified": "2021-12-14T19:15:08.000",
                    "cisaVulnerabilityName": "Apache Log4j2 Remote Code Execution",
                    "cisaRequiredAction": "Apply updates per vendor instructions",
                    "cisaActionDue": "2021-12-24",
                    "cisaExploitAdd": "2021-12-10",
                    "references": [],
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseScore": 10.0,
                                    "baseSeverity": "CRITICAL",
                                    "attackVector": "NETWORK",
                                    "attackComplexity": "LOW",
                                },
                                "exploitabilityScore": 3.9,
                                "impactScore": 6.0,
                            }
                        ]
                    },
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await cve_lookup_action.execute(cve="CVE-2021-44228")

    assert result["status"] == "success"
    assert result["cisa_kev"] is not None
    assert (
        result["cisa_kev"]["vulnerability_name"]
        == "Apache Log4j2 Remote Code Execution"
    )
    assert (
        result["cisa_kev"]["required_action"] == "Apply updates per vendor instructions"
    )
    assert result["cisa_kev"]["due_date"] == "2021-12-24"
    assert result["cisa_kev"]["date_added"] == "2021-12-10"


@pytest.mark.asyncio
async def test_cve_lookup_with_cvss_v2_fallback(cve_lookup_action):
    """Test CVE lookup with CVSS v2 when v3.1 is not available."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2019-1010218",
                    "descriptions": [{"lang": "en", "value": "Old vulnerability"}],
                    "published": "2019-07-15T10:15:09.000",
                    "lastModified": "2019-07-20T19:15:08.000",
                    "references": [],
                    "metrics": {
                        "cvssMetricV2": [
                            {
                                "cvssData": {
                                    "baseScore": 7.5,
                                    "accessVector": "NETWORK",
                                    "accessComplexity": "LOW",
                                },
                                "baseSeverity": "HIGH",
                                "exploitabilityScore": 10.0,
                                "impactScore": 6.4,
                            }
                        ]
                    },
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await cve_lookup_action.execute(cve="CVE-2019-1010218")

    assert result["status"] == "success"
    assert result["cvss_metrics"]["base_score"] == 7.5
    assert result["cvss_metrics"]["base_severity"] == "HIGH"
    assert result["cvss_metrics"]["attack_vector"] == "NETWORK"


@pytest.mark.asyncio
async def test_cve_lookup_empty_vulnerabilities(cve_lookup_action):
    """Test CVE lookup when API returns empty vulnerabilities list."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"vulnerabilities": []}

    with patch.object(
        cve_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await cve_lookup_action.execute(cve="CVE-2099-99999")

    assert result["status"] == "error"
    assert result["error_type"] == "NotFoundError"
    assert "No data found" in result["error"]


# ============================================================================
# API KEY USAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_with_api_key():
    """Test that API key is included in headers when provided."""
    action = HealthCheckAction(
        integration_id="nistnvd",
        action_id="health_check",
        settings={"api_version": "2.0", "timeout": 30},
        credentials={"api_key": "test-api-key-123"},
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2019-1010218",
                    "descriptions": [{"lang": "en", "value": "Test CVE"}],
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ) as mock_http:
        result = await action.execute()

    assert result["status"] == "success"

    # Verify API key was included in headers
    call_args = mock_http.call_args
    headers = call_args[1].get("headers", {})
    assert "apiKey" in headers
    assert headers["apiKey"] == "test-api-key-123"


@pytest.mark.asyncio
async def test_health_check_without_api_key():
    """Test that action works without API key (public API)."""
    action = HealthCheckAction(
        integration_id="nistnvd",
        action_id="health_check",
        settings={"api_version": "2.0", "timeout": 30},
        credentials={},  # No API key
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2019-1010218",
                    "descriptions": [{"lang": "en", "value": "Test CVE"}],
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ) as mock_http:
        result = await action.execute()

    assert result["status"] == "success"

    # Verify API key was NOT included in headers (optional)
    call_args = mock_http.call_args
    headers = call_args[1].get("headers", {})
    assert "apiKey" not in headers
    assert headers["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_cve_lookup_with_api_key():
    """Test that CVE lookup includes API key when provided."""
    action = CveLookupAction(
        integration_id="nistnvd",
        action_id="cve_lookup",
        settings={"api_version": "2.0", "timeout": 30},
        credentials={"api_key": "test-api-key-456"},
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2022-41082",
                    "descriptions": [{"lang": "en", "value": "ProxyNotShell"}],
                    "published": "2022-09-30T00:00:00.000",
                    "lastModified": "2023-01-15T00:00:00.000",
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseScore": 8.8,
                                    "baseSeverity": "HIGH",
                                    "attackVector": "NETWORK",
                                }
                            }
                        ]
                    },
                    "references": [],
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ) as mock_http:
        result = await action.execute(cve="CVE-2022-41082")

    assert result["status"] == "success"

    # Verify API key was included in headers
    call_args = mock_http.call_args
    headers = call_args[1].get("headers", {})
    assert "apiKey" in headers
    assert headers["apiKey"] == "test-api-key-456"
