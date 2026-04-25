"""Unit tests for VirusTotal integration actions.

All actions now use the base-class ``http_request()`` helper which applies
``integration_retry_policy`` automatically.  Tests mock at the
``IntegrationAction.http_request`` level so retry behaviour is transparent.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.virustotal.actions import (
    DomainReputationAction,
    FileReputationAction,
    GetAnalysisReportAction,
    HealthCheckAction,
    IpReputationAction,
    SubmitUrlAnalysisAction,
    UrlReputationAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


class TestHealthCheckAction:
    @pytest.fixture
    def health_check_action(self):
        return HealthCheckAction(
            integration_id="virustotal",
            action_id="health_check",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "quotas": {"api_requests_daily": {"allowed": 500, "used": 10}}
                    }
                }
            }
        )
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await health_check_action.execute()
        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "quota" in result["data"]

    @pytest.mark.asyncio
    async def test_health_check_missing_api_key(self):
        action = HealthCheckAction(
            integration_id="virustotal",
            action_id="health_check",
            settings={},
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "Missing API key" in result["error"]
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self):
        action = HealthCheckAction(
            integration_id="virustotal",
            action_id="health_check",
            settings={},
            credentials={"api_key": "invalid-key"},
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await action.execute()
        assert result["status"] == "error"
        assert "Invalid API key" in result["error"]
        assert result["data"]["healthy"] is False


class TestIPReputationAction:
    @pytest.fixture
    def ip_reputation_action(self):
        return IpReputationAction(
            integration_id="virustotal",
            action_id="ip_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_ip_reputation_success(self, ip_reputation_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "reputation": 0,
                        "last_analysis_stats": {
                            "malicious": 5,
                            "suspicious": 2,
                            "harmless": 80,
                            "undetected": 3,
                        },
                        "country": "US",
                        "as_owner": "Example AS",
                        "network": "192.0.2.0/24",
                    }
                }
            }
        )
        with patch.object(
            ip_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ip_reputation_action.execute(ip_address="192.0.2.1")
        assert result["status"] == "success"
        assert result["ip_address"] == "192.0.2.1"
        assert result["reputation_summary"]["malicious"] == 5
        assert result["network_info"]["country"] == "US"

    @pytest.mark.asyncio
    async def test_ip_reputation_invalid_ip(self, ip_reputation_action):
        result = await ip_reputation_action.execute(ip_address="invalid-ip")
        assert result["status"] == "error"
        assert "Invalid IP address" in result["error"]

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_ip(self, ip_reputation_action):
        result = await ip_reputation_action.execute()
        assert result["status"] == "error"
        assert "must be a non-empty string" in result["error"]


class TestDomainReputationAction:
    @pytest.fixture
    def domain_reputation_action(self):
        return DomainReputationAction(
            integration_id="virustotal",
            action_id="domain_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_domain_reputation_success(self, domain_reputation_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "reputation": 0,
                        "last_analysis_stats": {
                            "malicious": 0,
                            "suspicious": 0,
                            "harmless": 85,
                            "undetected": 5,
                        },
                        "categories": {"security": "security"},
                        "creation_date": 1234567890,
                    }
                }
            }
        )
        with patch.object(
            domain_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await domain_reputation_action.execute(domain="example.com")
        assert result["status"] == "success"
        assert result["domain"] == "example.com"
        assert result["reputation_summary"]["malicious"] == 0
        assert result["reputation_summary"]["harmless"] == 85

    @pytest.mark.asyncio
    async def test_domain_reputation_invalid_domain(self, domain_reputation_action):
        result = await domain_reputation_action.execute(domain="invalid domain!")
        assert result["status"] == "error"
        assert "Invalid domain" in result["error"]


class TestUrlReputationAction:
    @pytest.fixture
    def url_reputation_action(self):
        return UrlReputationAction(
            integration_id="virustotal",
            action_id="url_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_url_reputation_success(self, url_reputation_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "reputation": 0,
                        "last_analysis_stats": {
                            "malicious": 0,
                            "suspicious": 0,
                            "harmless": 80,
                            "undetected": 10,
                        },
                        "title": "Example Page",
                        "categories": {"web": "web"},
                    }
                }
            }
        )
        with patch.object(
            url_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await url_reputation_action.execute(url="https://example.com/page")
        assert result["status"] == "success"
        assert result["url"] == "https://example.com/page"
        assert result["reputation_summary"]["malicious"] == 0

    @pytest.mark.asyncio
    async def test_url_reputation_invalid_url(self, url_reputation_action):
        result = await url_reputation_action.execute(url="not-a-url")
        assert result["status"] == "error"
        assert "Invalid URL" in result["error"]


class TestFileReputationAction:
    @pytest.fixture
    def file_reputation_action(self):
        return FileReputationAction(
            integration_id="virustotal",
            action_id="file_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_file_reputation_md5_success(self, file_reputation_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "reputation": -10,
                        "last_analysis_stats": {
                            "malicious": 45,
                            "suspicious": 5,
                            "harmless": 10,
                            "undetected": 30,
                        },
                        "type_description": "Win32 EXE",
                        "size": 12345,
                    }
                }
            }
        )
        with patch.object(
            file_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await file_reputation_action.execute(
                file_hash="5d41402abc4b2a76b9719d911017c592"
            )
        assert result["status"] == "success"
        assert result["file_hash"] == "5d41402abc4b2a76b9719d911017c592"
        assert result["reputation_summary"]["malicious"] == 45
        assert result["file_info"]["type_description"] == "Win32 EXE"

    @pytest.mark.asyncio
    async def test_file_reputation_sha256_success(self, file_reputation_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "reputation": 0,
                        "last_analysis_stats": {
                            "malicious": 0,
                            "suspicious": 0,
                            "harmless": 70,
                            "undetected": 20,
                        },
                    }
                }
            }
        )
        with patch.object(
            file_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await file_reputation_action.execute(
                file_hash="2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
            )
        assert result["status"] == "success"
        assert result["reputation_summary"]["malicious"] == 0

    @pytest.mark.asyncio
    async def test_file_reputation_invalid_hash(self, file_reputation_action):
        result = await file_reputation_action.execute(file_hash="invalid-hash")
        assert result["status"] == "error"
        assert "File hash must be" in result["error"]

    @pytest.mark.asyncio
    async def test_file_reputation_wrong_length_hash(self, file_reputation_action):
        result = await file_reputation_action.execute(file_hash="abc123")
        assert result["status"] == "error"
        assert "File hash must be" in result["error"]


class TestSubmitUrlAnalysisAction:
    @pytest.fixture
    def submit_url_action(self):
        return SubmitUrlAnalysisAction(
            integration_id="virustotal",
            action_id="submit_url_analysis",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_submit_url_success(self, submit_url_action):
        mock_response = _json_response(
            {"data": {"id": "u-abc123-1234567890", "type": "analysis"}}
        )
        with patch.object(
            submit_url_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await submit_url_action.execute(url="https://example.com/test")
        assert result["status"] == "success"
        assert result["url"] == "https://example.com/test"
        assert result["analysis_id"] == "u-abc123-1234567890"

    @pytest.mark.asyncio
    async def test_submit_url_invalid_url(self, submit_url_action):
        result = await submit_url_action.execute(url="not-a-url")
        assert result["status"] == "error"
        assert "Invalid URL" in result["error"]


class TestGetAnalysisReportAction:
    @pytest.fixture
    def get_analysis_report_action(self):
        return GetAnalysisReportAction(
            integration_id="virustotal",
            action_id="get_analysis_report",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_get_analysis_report_success(self, get_analysis_report_action):
        mock_response = _json_response(
            {
                "data": {
                    "attributes": {
                        "status": "completed",
                        "stats": {
                            "malicious": 0,
                            "suspicious": 0,
                            "harmless": 75,
                            "undetected": 15,
                        },
                        "results": {
                            "Scanner1": {"category": "harmless", "result": "clean"}
                        },
                    }
                }
            }
        )
        with patch.object(
            get_analysis_report_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await get_analysis_report_action.execute(
                analysis_id="u-abc123-1234567890"
            )
        assert result["status"] == "success"
        assert result["analysis_id"] == "u-abc123-1234567890"
        assert result["analysis_status"] == "completed"
        assert result["analysis_stats"]["malicious"] == 0
        assert result["analysis_stats"]["harmless"] == 75

    @pytest.mark.asyncio
    async def test_get_analysis_report_missing_id(self, get_analysis_report_action):
        result = await get_analysis_report_action.execute()
        assert result["status"] == "error"
        assert "must be a non-empty string" in result["error"]

    @pytest.mark.asyncio
    async def test_get_analysis_report_not_found(self, get_analysis_report_action):
        with patch.object(
            get_analysis_report_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await get_analysis_report_action.execute(
                analysis_id="nonexistent-id"
            )
        assert result["status"] == "error"
        assert "Resource not found" in result["error"]
