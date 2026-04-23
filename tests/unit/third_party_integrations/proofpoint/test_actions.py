"""Unit tests for Proofpoint TAP integration actions.

Tests mock at the IntegrationAction.http_request level so retry behaviour
is transparent and tests stay fast (< 0.1s each).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.proofpoint.actions import (
    DecodeUrlAction,
    GetCampaignDataAction,
    GetCampaignDetailsAction,
    GetForensicDataAction,
    GetForensicDataByCampaignAction,
    HealthCheckAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CREDENTIALS = {"username": "test-principal", "password": "test-secret"}


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = body
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="proofpoint",
            action_id="health_check",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response({"queryEndTime": "2025-01-01T00:05:00Z"})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "proofpoint"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        assert result["data"]["query_end_time"] == "2025-01-01T00:05:00Z"
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = HealthCheckAction(
            integration_id="proofpoint",
            action_id="health_check",
            settings={},
            credentials={},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]
        assert result["error_type"] == "ConfigurationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_auth_passed_to_request(self, action):
        mock_response = _json_response({"queryEndTime": "2025-01-01T00:05:00Z"})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("test-principal", "test-secret")


# ===========================================================================
# GetCampaignDataAction (deprecated alias)
# ===========================================================================


class TestGetCampaignDataAction:
    @pytest.fixture
    def action(self):
        return GetCampaignDataAction(
            integration_id="proofpoint",
            action_id="get_campaign_data",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        campaign_data = {
            "name": "Test Campaign",
            "description": "A test campaign",
            "startDate": "2025-01-01T00:00:00Z",
            "actors": [{"id": "actor-1", "name": "Threat Actor"}],
            "campaignMembers": [
                {
                    "id": "threat-1",
                    "type": "url",
                    "subType": "phishing",
                    "threat": "https://evil.example.com",
                    "threatTime": "2025-01-01T00:00:00Z",
                }
            ],
            "families": [{"id": "family-1", "name": "Malware Family"}],
            "malware": [{"id": "malware-1", "name": "EvilMalware"}],
            "techniques": [{"id": "T1566", "name": "Phishing"}],
        }
        mock_response = _json_response(campaign_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(campaign_id="test-campaign-123")

        assert result["status"] == "success"
        assert result["integration_id"] == "proofpoint"
        assert result["data"]["name"] == "Test Campaign"
        assert result["data"]["actors"][0]["name"] == "Threat Actor"
        assert result["data"]["campaignMembers"][0]["type"] == "url"

    @pytest.mark.asyncio
    async def test_missing_campaign_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "campaign_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = GetCampaignDataAction(
            integration_id="proofpoint",
            action_id="get_campaign_data",
            settings={},
            credentials={},
        )
        result = await action.execute(campaign_id="test-campaign-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_campaign_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(campaign_id="nonexistent-campaign")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["campaign_id"] == "nonexistent-campaign"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(campaign_id="test-campaign-123")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# GetCampaignDetailsAction
# ===========================================================================


class TestGetCampaignDetailsAction:
    @pytest.fixture
    def action(self):
        return GetCampaignDetailsAction(
            integration_id="proofpoint",
            action_id="get_campaign_details",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        campaign_data = {
            "name": "Phishing Campaign",
            "description": "Active phishing campaign",
            "startDate": "2025-01-15T00:00:00Z",
            "actors": [],
            "campaignMembers": [],
            "families": [],
            "malware": [],
            "techniques": [],
        }
        mock_response = _json_response(campaign_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(campaign_id="campaign-456")

        assert result["status"] == "success"
        assert result["data"]["name"] == "Phishing Campaign"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_missing_campaign_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(campaign_id="missing-id")

        assert result["status"] == "success"
        assert result["not_found"] is True


# ===========================================================================
# GetForensicDataAction (deprecated alias)
# ===========================================================================


class TestGetForensicDataAction:
    @pytest.fixture
    def action(self):
        return GetForensicDataAction(
            integration_id="proofpoint",
            action_id="get_forensic_data",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success_with_threat_id(self, action):
        forensic_data = {
            "generated": "2025-01-01T00:00:00Z",
            "reports": [
                {
                    "id": "report-1",
                    "name": "Threat Report",
                    "scope": "threat",
                    "type": "attachment",
                    "forensics": [
                        {
                            "type": "file",
                            "display": "malware.exe",
                            "malicious": "true",
                            "time": "2025-01-01T00:00:00Z",
                            "platforms": [
                                {"name": "Windows", "os": "win", "version": "10"}
                            ],
                            "what": {
                                "md5": "d41d8cd98f00b204e9800998ecf8427e",
                                "sha256": "e3b0c44298fc1c149afbf4c8996fb924",
                                "size": 12345,
                                "name": "malware.exe",
                            },
                        }
                    ],
                }
            ],
        }
        mock_response = _json_response(forensic_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(threat_id="threat-abc-123")

        assert result["status"] == "success"
        assert result["data"]["generated"] == "2025-01-01T00:00:00Z"
        assert len(result["data"]["reports"]) == 1
        assert result["data"]["reports"][0]["forensics"][0]["type"] == "file"

    @pytest.mark.asyncio
    async def test_success_with_campaign_id(self, action):
        forensic_data = {
            "generated": "2025-01-01T00:00:00Z",
            "reports": [],
        }
        mock_response = _json_response(forensic_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(campaign_id="campaign-xyz")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_both_ids(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "campaign_id or threat_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_both_ids_provided(self, action):
        result = await action.execute(campaign_id="camp-1", threat_id="threat-1")

        assert result["status"] == "error"
        assert "Only one" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = GetForensicDataAction(
            integration_id="proofpoint",
            action_id="get_forensic_data",
            settings={},
            credentials={},
        )
        result = await action.execute(threat_id="threat-1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(threat_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_include_campaign_forensics_param(self, action):
        mock_response = _json_response({"generated": "now", "reports": []})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(threat_id="threat-1", include_campaign_forensics=True)

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["includeCampaignForensics"] is True

    @pytest.mark.asyncio
    async def test_include_campaign_forensics_ignored_for_campaign(self, action):
        """include_campaign_forensics should NOT be sent when using campaign_id."""
        mock_response = _json_response({"generated": "now", "reports": []})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(campaign_id="camp-1", include_campaign_forensics=True)

        call_kwargs = action.http_request.call_args.kwargs
        assert "includeCampaignForensics" not in call_kwargs["params"]


# ===========================================================================
# GetForensicDataByCampaignAction
# ===========================================================================


class TestGetForensicDataByCampaignAction:
    @pytest.fixture
    def action(self):
        return GetForensicDataByCampaignAction(
            integration_id="proofpoint",
            action_id="get_forensic_data_by_campaign",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        forensic_data = {
            "generated": "2025-01-01T00:00:00Z",
            "reports": [
                {
                    "id": "report-1",
                    "name": "Threat Report",
                    "scope": "campaign",
                    "type": "url",
                    "forensics": [],
                }
            ],
        }
        mock_response = _json_response(forensic_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(campaign_id="camp-abc")

        assert result["status"] == "success"
        assert result["data"]["reports"][0]["scope"] == "campaign"

    @pytest.mark.asyncio
    async def test_missing_both_ids(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_both_ids_provided(self, action):
        result = await action.execute(campaign_id="camp-1", threat_id="threat-1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ===========================================================================
# DecodeUrlAction
# ===========================================================================


class TestDecodeUrlAction:
    @pytest.fixture
    def action(self):
        return DecodeUrlAction(
            integration_id="proofpoint",
            action_id="decode_url",
            settings={},
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_single_url_success(self, action):
        decode_data = {
            "urls": [
                {
                    "encodedUrl": "https://urldefense.proofpoint.com/v2/url?u=...",
                    "decodedUrl": "https://example.com/original",
                    "success": True,
                    "clusterName": "cluster1",
                    "messageGuid": "msg-guid-123",
                    "recipientEmail": "user@company.com",
                }
            ]
        }
        mock_response = _json_response(decode_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            url="https://urldefense.proofpoint.com/v2/url?u=..."
        )

        assert result["status"] == "success"
        assert result["data"]["urls"][0]["decodedUrl"] == "https://example.com/original"
        assert result["data"]["urls"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_urls_success(self, action):
        decode_data = {
            "urls": [
                {
                    "encodedUrl": "https://urldefense.proofpoint.com/url1",
                    "decodedUrl": "https://example.com/page1",
                    "success": True,
                },
                {
                    "encodedUrl": "https://urldefense.proofpoint.com/url2",
                    "decodedUrl": "https://example.com/page2",
                    "success": True,
                },
            ]
        }
        mock_response = _json_response(decode_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            url="https://urldefense.proofpoint.com/url1, https://urldefense.proofpoint.com/url2"
        )

        assert result["status"] == "success"
        assert len(result["data"]["urls"]) == 2

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_url_after_split(self, action):
        result = await action.execute(url=", , ,")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = DecodeUrlAction(
            integration_id="proofpoint",
            action_id="decode_url",
            settings={},
            credentials={},
        )
        result = await action.execute(url="https://urldefense.proofpoint.com/test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=Exception("Internal server error"))

        result = await action.execute(url="https://urldefense.proofpoint.com/test")

        assert result["status"] == "error"
        assert "Internal server error" in result["error"]

    @pytest.mark.asyncio
    async def test_post_with_json_body(self, action):
        """Verify decode_url sends POST with JSON body containing urls list."""
        mock_response = _json_response({"urls": []})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(url="https://urldefense.proofpoint.com/test")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"] == {
            "urls": ["https://urldefense.proofpoint.com/test"]
        }

    @pytest.mark.asyncio
    async def test_url_list_trimming(self, action):
        """Verify spaces around comma-separated URLs are trimmed."""
        mock_response = _json_response({"urls": []})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(url="  https://url1.com  ,  https://url2.com  ")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"] == {
            "urls": ["https://url1.com", "https://url2.com"]
        }


# ===========================================================================
# Cross-cutting: result envelope verification
# ===========================================================================


class TestResultEnvelope:
    """Verify all actions produce the standard result envelope."""

    @pytest.mark.asyncio
    async def test_success_envelope_has_required_fields(self):
        action = HealthCheckAction(
            integration_id="proofpoint",
            action_id="health_check",
            settings={},
            credentials=VALID_CREDENTIALS,
        )
        mock_response = _json_response({"queryEndTime": "2025-01-01T00:00:00Z"})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert "status" in result
        assert "timestamp" in result
        assert "integration_id" in result
        assert "action_id" in result
        assert "data" in result
        assert result["integration_id"] == "proofpoint"
        assert result["action_id"] == "health_check"

    @pytest.mark.asyncio
    async def test_error_envelope_has_required_fields(self):
        action = GetCampaignDetailsAction(
            integration_id="proofpoint",
            action_id="get_campaign_details",
            settings={},
            credentials=VALID_CREDENTIALS,
        )
        # Missing required param triggers validation error
        result = await action.execute()

        assert "status" in result
        assert "timestamp" in result
        assert "integration_id" in result
        assert "action_id" in result
        assert "error" in result
        assert "error_type" in result
        assert result["status"] == "error"
