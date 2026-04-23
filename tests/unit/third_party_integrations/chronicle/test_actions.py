"""Unit tests for Chronicle integration actions."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.chronicle.actions import (
    AlertsToOcsfAction,
    DomainReputationAction,
    HealthCheckAction,
    IpReputationAction,
    ListAlertsAction,
    ListAssetsAction,
    ListDetectionsAction,
    ListEventsAction,
    ListIocDetailsAction,
    ListIocsAction,
    ListRulesAction,
    PullAlertsAction,
)


# Test fixtures
@pytest.fixture
def mock_credentials():
    """Mock credentials for Chronicle."""
    # Valid RSA private key for testing (DO NOT use in production!)
    test_private_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA2a2rwplg3QhN8WSmjWPJA0/hU1tNQ8WyNhSjq/4vGhW3Hvt6
TeXL2J7vKQhNOSqFPWqxhPHf3SFgmKbB8w7ZUwN6V3Z9jwQdMDJ/KtFlg7GXFKZ9
5R7LqmhKc5rSa+K5N35gLvpXE3d9TmxcYFEsU5CrKEGrBKXlLgBEOQrQD/PjxwDj
pMVbpgqK9lqNwMqL5I8nKgJL8bWfTF1dBQqjL5p8K9JzmhQr+Iq2xkJPzJ9lWqNg
G9RxWvhHqJKD6S7bvXnPXK1xh7JqjGhBx8F4x3MqQlNXKWy8H5+RJL7xKQqL6tBl
k3kqPGxqKxlHqJKD6S7bvXnPXK1xh7JqjGhBxwIDAQABAoIBADbcYwzLRpqKLFxq
lX3O7dTQS3rGFqHVCDaZbN5gJvTHAqTmEEQXKfHCtxBH5k6qXTN9XpxXFJKwRkKN
KYZjfQfWXC9QNvPLpA7WHfQP3FXYhHlQHKgHHKBCk0L/4WPfCQKBgQD9HbUqNqP1
E3MxFQxQP5gQqHqP3VXR1yQWHLxLvQ7LqmhKc5rSa+K5N35gLvpXE3d9TmxcYFEs
U5CrKEGrBKXlLgBEOQrQD/PjxwDjpMVbpgqK9lqNwMqL5I8nKgJL8bWfTF1dBQqj
L5p8K9JzmhQr+Iq2xkJPzJ9lWqNgGwKBgQDcFqNP8XJ8QxWqxBHx5YJP3gKHlQHK
gHHKBCk0L/4WPfCQKBgQD9HbUqNqP1E3MxFQxQP5gQqHqP3VXR1yQWHLxLvQ7Lqm
hKc5rSa+K5N35gLvpXE3d9TmxcYFEsU5CrKEGrBKXlLgBEOQrQD/PjxwDjpMVbpg
qK9lqNwMqL5I8nKgJL8bWfTF1dBQqjL5p8K9JzmhQr+Iq2xkJPzJ9lWqNgGwKBgG
9RxWvhHqJKD6S7bvXnPXK1xh7JqjGhBx8F4x3MqQlNXKWy8H5+RJL7xKQqL6tBlk
3kqPGxqKxlHqJKD6S7bvXnPXK1xh7JqjGhBx
-----END RSA PRIVATE KEY-----"""
    return {
        "key_json": json.dumps(
            {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "test-key-id",
                "private_key": test_private_key,
                "client_email": "test@test-project.iam.gserviceaccount.com",
                "client_id": "123456789",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        "scopes": '["https://www.googleapis.com/auth/chronicle-backstory"]',
    }


@pytest.fixture
def mock_settings():
    """Mock settings for Chronicle."""
    return {
        "base_url": "https://backstory.googleapis.com",
        "timeout": 30,
        "no_of_retries": 3,
        "wait_timeout_period": 3,
    }


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check."""
    action = HealthCheckAction(
        integration_id="chronicle",
        action_id="health_check",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "rules": [
            {"ruleId": "rule1", "ruleName": "Test Rule 1"},
            {"ruleId": "rule2", "ruleName": "Test Rule 2"},
        ]
    }

    # Mock both credential creation and API request
    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["rules_count"] == 2
    assert "Chronicle API is accessible" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="chronicle", action_id="test_action", credentials={}, settings={}
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing 'key_json'" in result["error"]
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_auth_failure(mock_credentials, mock_settings):
    """Test health check with authentication failure."""
    action = HealthCheckAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.side_effect = Exception(
            "Authentication failed - invalid service account credentials"
        )

        result = await action.execute()

    assert result["status"] == "error"
    assert "Authentication failed" in result["error"]
    assert result["error_type"] == "AuthenticationError"
    assert result["data"]["healthy"] is False


# ============================================================================
# LIST IOC DETAILS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_ioc_details_domain_success(mock_credentials, mock_settings):
    """Test successful list IOC details for domain."""
    action = ListIocDetailsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "sources": [
            {"category": "malware", "confidence": "high"},
            {"category": "phishing", "confidence": "medium"},
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            artifact_indicator="Domain Name", value="evil.com"
        )

    assert result["status"] == "success"
    assert result["artifact_indicator"] == "Domain Name"
    assert result["value"] == "evil.com"
    assert result["total_sources"] == 2
    assert len(result["sources"]) == 2


@pytest.mark.asyncio
async def test_list_ioc_details_ip_success(mock_credentials, mock_settings):
    """Test successful list IOC details for IP."""
    action = ListIocDetailsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"sources": [{"category": "c2", "confidence": "high"}]}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            artifact_indicator="Destination IP Address", value="192.0.2.1"
        )

    assert result["status"] == "success"
    assert result["artifact_indicator"] == "Destination IP Address"
    assert result["value"] == "192.0.2.1"
    assert result["total_sources"] == 1


@pytest.mark.asyncio
async def test_list_ioc_details_missing_parameter(mock_credentials, mock_settings):
    """Test list IOC details with missing parameter."""
    action = ListIocDetailsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(artifact_indicator="Domain Name")

    assert result["status"] == "error"
    assert "Missing required parameter: value" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_ioc_details_invalid_indicator(mock_credentials, mock_settings):
    """Test list IOC details with invalid artifact indicator."""
    action = ListIocDetailsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    # Mock credentials even though we should fail before using them
    mock_creds = MagicMock()
    with patch(
        "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
        return_value=mock_creds,
    ):
        result = await action.execute(artifact_indicator="Invalid Type", value="test")

    assert result["status"] == "error"
    assert "Invalid parameter value" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST ASSETS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_assets_success(mock_credentials, mock_settings):
    """Test successful list assets."""
    action = ListAssetsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "assets": [{"asset": {"hostname": "host1"}}, {"asset": {"hostname": "host2"}}]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            artifact_indicator="Domain Name",
            value="evil.com",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
        )

    assert result["status"] == "success"
    assert result["total_assets"] == 2
    assert len(result["assets"]) == 2


@pytest.mark.asyncio
async def test_list_assets_invalid_time_range(mock_credentials, mock_settings):
    """Test list assets with invalid time range."""
    action = ListAssetsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(
        artifact_indicator="Domain Name",
        value="evil.com",
        start_time="2024-01-02T00:00:00Z",
        end_time="2024-01-01T00:00:00Z",  # End before start
    )

    assert result["status"] == "error"
    assert "Invalid time range" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_assets_missing_required_params(mock_credentials, mock_settings):
    """Test list assets with missing required parameters."""
    action = ListAssetsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(artifact_indicator="Domain Name", value="evil.com")

    assert result["status"] == "error"
    assert "Missing required parameter" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST EVENTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_events_success(mock_credentials, mock_settings):
    """Test successful list events."""
    action = ListEventsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "events": [
            {"event": {"metadata": {"eventType": "NETWORK_HTTP"}}},
            {"event": {"metadata": {"eventType": "NETWORK_DNS"}}},
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            asset_identifier="hostname",
            asset_identifier_value="host1",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
        )

    assert result["status"] == "success"
    assert result["total_events"] == 2
    assert result["asset_identifier"] == "hostname"


@pytest.mark.asyncio
async def test_list_events_with_reference_time(mock_credentials, mock_settings):
    """Test list events with reference time for pagination."""
    action = ListEventsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"events": []}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            asset_identifier="hostname",
            asset_identifier_value="host1",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            reference_time="2024-01-01T12:00:00Z",
        )

    assert result["status"] == "success"
    assert result["total_events"] == 0


# ============================================================================
# LIST IOCS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_iocs_success(mock_credentials, mock_settings):
    """Test successful list IOCs."""
    action = ListIocsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "response": {
            "matches": [
                {"artifact": {"domainName": "evil.com"}},
                {"artifact": {"destinationIpAddress": "192.0.2.1"}},
            ]
        }
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(start_time="2024-01-01T00:00:00Z")

    assert result["status"] == "success"
    assert result["total_iocs"] == 2
    assert result["start_time"] == "2024-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_list_iocs_missing_start_time(mock_credentials, mock_settings):
    """Test list IOCs with missing start_time."""
    action = ListIocsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing required parameter: start_time" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# REPUTATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_domain_reputation_malicious(mock_credentials, mock_settings):
    """Test domain reputation for malicious domain."""
    action = DomainReputationAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "sources": [
            {"category": "malware", "confidence": "high"},
            {"category": "c2", "confidence": "high"},
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(domain="evil.com")

    assert result["status"] == "success"
    assert result["domain"] == "evil.com"
    assert result["reputation"] == "Malicious"
    assert result["total_sources"] == 2


@pytest.mark.asyncio
async def test_domain_reputation_suspicious(mock_credentials, mock_settings):
    """Test domain reputation for suspicious domain."""
    action = DomainReputationAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"sources": [{"category": "suspicious", "confidence": "medium"}]}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(domain="suspicious.com")

    assert result["status"] == "success"
    assert result["reputation"] == "Suspicious"


@pytest.mark.asyncio
async def test_domain_reputation_unknown(mock_credentials, mock_settings):
    """Test domain reputation for unknown domain."""
    action = DomainReputationAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"sources": []}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(domain="clean.com")

    assert result["status"] == "success"
    assert result["reputation"] == "Unknown"
    assert result["total_sources"] == 0


@pytest.mark.asyncio
async def test_ip_reputation_success(mock_credentials, mock_settings):
    """Test IP reputation lookup."""
    action = IpReputationAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"sources": [{"category": "phishing", "confidence": "high"}]}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["ip"] == "192.0.2.1"
    assert result["reputation"] == "Malicious"


@pytest.mark.asyncio
async def test_ip_reputation_missing_parameter(mock_credentials, mock_settings):
    """Test IP reputation with missing parameter."""
    action = IpReputationAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing required parameter: ip" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST ALERTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_alerts_all_types(mock_credentials, mock_settings):
    """Test list all types of alerts."""
    action = ListAlertsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "alerts": [
            {"asset": "host1", "alertInfos": [{"name": "alert1"}, {"name": "alert2"}]},
            {"asset": "host2", "alertInfos": [{"name": "alert3"}]},
        ],
        "userAlerts": [{"user": "user1", "alertInfos": [{"name": "alert4"}]}],
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            alert_type="All",
        )

    assert result["status"] == "success"
    assert result["total_assets_with_alerts"] == 2
    assert result["total_asset_alerts"] == 3
    assert result["total_users_with_alerts"] == 1
    assert result["total_user_alerts"] == 1


@pytest.mark.asyncio
async def test_list_alerts_asset_only(mock_credentials, mock_settings):
    """Test list asset alerts only."""
    action = ListAlertsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "alerts": [{"asset": "host1", "alertInfos": [{"name": "alert1"}]}],
        "userAlerts": [],
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            alert_type="Asset Alerts",
        )

    assert result["status"] == "success"
    assert "alerts" in result
    assert result["total_assets_with_alerts"] == 1


# ============================================================================
# LIST RULES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_rules_success(mock_credentials, mock_settings):
    """Test successful list rules."""
    action = ListRulesAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "rules": [
            {"ruleId": "rule1", "ruleName": "Detect Malware"},
            {"ruleId": "rule2", "ruleName": "Detect Phishing"},
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute()

    assert result["status"] == "success"
    assert result["total_rules"] == 2
    assert len(result["rules"]) == 2


@pytest.mark.asyncio
async def test_list_rules_with_limit(mock_credentials, mock_settings):
    """Test list rules with custom limit."""
    action = ListRulesAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"rules": []}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(limit=100)

    assert result["status"] == "success"
    assert result["total_rules"] == 0


# ============================================================================
# LIST DETECTIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_detections_success(mock_credentials, mock_settings):
    """Test successful list detections."""
    action = ListDetectionsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {
        "detections": [
            {"id": "detection1", "type": "RULE_DETECTION"},
            {"id": "detection2", "type": "RULE_DETECTION"},
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(rule_id="ru_12345678-1234-1234-1234-1234567890ab")

    assert result["status"] == "success"
    assert result["rule_id"] == "ru_12345678-1234-1234-1234-1234567890ab"
    assert result["total_detections"] == 2


@pytest.mark.asyncio
async def test_list_detections_with_time_range(mock_credentials, mock_settings):
    """Test list detections with time range."""
    action = ListDetectionsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_response = {"detections": []}

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = mock_response

        result = await action.execute(
            rule_id="ru_12345678-1234-1234-1234-1234567890ab",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
        )

    assert result["status"] == "success"
    assert result["total_detections"] == 0


@pytest.mark.asyncio
async def test_list_detections_missing_rule_id(mock_credentials, mock_settings):
    """Test list detections with missing rule_id."""
    action = ListDetectionsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing required parameter: rule_id" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_detections_invalid_time_range(mock_credentials, mock_settings):
    """Test list detections with invalid time range."""
    action = ListDetectionsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(
        rule_id="ru_12345678-1234-1234-1234-1234567890ab",
        start_time="2024-01-02T00:00:00Z",
        end_time="2024-01-01T00:00:00Z",
    )

    assert result["status"] == "error"
    assert "Invalid time range" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# HTTP ERROR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_http_error_handling(mock_credentials, mock_settings):
    """Test HTTP error handling."""
    action = ListRulesAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.side_effect = Exception("HTTP 429: Rate limit exceeded")

        result = await action.execute()

    assert result["status"] == "error"
    assert "Rate limit exceeded" in result["error"]
    assert result["error_type"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_timeout_error_handling(mock_credentials, mock_settings):
    """Test timeout error handling."""
    action = ListIocsAction(
        integration_id="chronicle",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.side_effect = Exception("Request timed out after 30 seconds")

        result = await action.execute(start_time="2024-01-01T00:00:00Z")

    assert result["status"] == "error"
    assert "timed out" in result["error"]


# ============================================================================
# PULL ALERTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_pull_alerts_success(mock_credentials, mock_settings):
    """Test successful pull alerts across rules."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    rules_response = {
        "rules": [
            {"ruleId": "ru_001", "ruleName": "Rule 1"},
            {"ruleId": "ru_002", "ruleName": "Rule 2"},
        ]
    }

    detection_1 = {
        "detections": [
            {
                "id": "de_001",
                "type": "RULE_DETECTION",
                "detection": [{"ruleName": "Rule 1", "severity": "HIGH"}],
            }
        ]
    }
    detection_2 = {
        "detections": [
            {
                "id": "de_002",
                "type": "RULE_DETECTION",
                "detection": [{"ruleName": "Rule 2", "severity": "LOW"}],
            },
            {
                "id": "de_003",
                "type": "RULE_DETECTION",
                "detection": [{"ruleName": "Rule 2", "severity": "MEDIUM"}],
            },
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        # First call: list rules, then two calls for detections per rule
        mock_request.side_effect = [rules_response, detection_1, detection_2]

        result = await action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 3
    assert len(result["alerts"]) == 3
    assert "Retrieved 3 detections from 2 rules" in result["message"]


@pytest.mark.asyncio
async def test_pull_alerts_missing_credentials():
    """Test pull alerts with missing credentials."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials={},
        settings={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing 'key_json'" in result["error"]
    assert result["error_type"] == "ConfigurationError"
    assert result["alerts_count"] == 0
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_pull_alerts_no_rules(mock_credentials, mock_settings):
    """Test pull alerts when no rules exist."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = {"rules": []}

        result = await action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 0
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_pull_alerts_rule_failure_continues(mock_credentials, mock_settings):
    """Test that a failed rule does not stop pulling from remaining rules."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    rules_response = {
        "rules": [
            {"ruleId": "ru_fail", "ruleName": "Failing Rule"},
            {"ruleId": "ru_ok", "ruleName": "Working Rule"},
        ]
    }
    ok_detections = {
        "detections": [
            {
                "id": "de_ok",
                "type": "RULE_DETECTION",
                "detection": [{"ruleName": "Working Rule"}],
            }
        ]
    }

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        # First call returns rules, second call fails, third succeeds
        mock_request.side_effect = [
            rules_response,
            Exception("Rule fetch failed"),
            ok_detections,
        ]

        result = await action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 1
    assert result["alerts"][0]["id"] == "de_ok"


@pytest.mark.asyncio
async def test_pull_alerts_default_lookback(mock_credentials, mock_settings):
    """Test pull alerts uses default lookback when no start_time provided."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials=mock_credentials,
        settings={**mock_settings, "default_lookback_minutes": 10},
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.return_value = {"rules": []}

        result = await action.execute()

    assert result["status"] == "success"
    # Verify _make_chronicle_request was called (rules listing)
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_pull_alerts_auth_failure(mock_credentials, mock_settings):
    """Test pull alerts with authentication failure."""
    action = PullAlertsAction(
        integration_id="chronicle",
        action_id="pull_alerts",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_creds = MagicMock()
    with (
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json",
            return_value=mock_creds,
        ),
        patch(
            "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request",
            new_callable=AsyncMock,
        ) as mock_request,
    ):
        mock_request.side_effect = Exception(
            "Authentication failed - invalid service account credentials"
        )

        result = await action.execute()

    assert result["status"] == "error"
    assert "Authentication failed" in result["error"]
    assert result["error_type"] == "AuthenticationError"
    assert result["alerts_count"] == 0


# ============================================================================
# ALERTS TO OCSF ACTION TESTS
# ============================================================================


@pytest.fixture
def alerts_to_ocsf_action():
    """Create AlertsToOcsfAction instance."""
    return AlertsToOcsfAction(
        integration_id="chronicle",
        action_id="alerts_to_ocsf",
        settings={},
        credentials={},
    )


@pytest.mark.asyncio
async def test_alerts_to_ocsf_success(alerts_to_ocsf_action):
    """Test successful OCSF normalization."""
    raw_alerts = [
        {"id": "de_001", "detection": [{"ruleName": "Rule 1"}]},
        {"id": "de_002", "detection": [{"ruleName": "Rule 2"}]},
    ]
    ocsf_doc_1 = {"class_uid": 2004, "finding_info": {"uid": "de_001"}}
    ocsf_doc_2 = {"class_uid": 2004, "finding_info": {"uid": "de_002"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [ocsf_doc_1, ocsf_doc_2]

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.chronicle_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.chronicle_ocsf.ChronicleOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["errors"] == 0
    assert len(result["normalized_alerts"]) == 2
    assert result["normalized_alerts"][0]["class_uid"] == 2004


@pytest.mark.asyncio
async def test_alerts_to_ocsf_empty(alerts_to_ocsf_action):
    """Test OCSF normalization with empty input."""
    mock_normalizer = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.chronicle_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.chronicle_ocsf.ChronicleOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=[])

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0
    assert result["normalized_alerts"] == []


@pytest.mark.asyncio
async def test_alerts_to_ocsf_partial_failure(alerts_to_ocsf_action):
    """Test OCSF normalization where one alert fails."""
    raw_alerts = [
        {"id": "de_001", "detection": [{"ruleName": "Rule 1"}]},
        {"id": "de_002", "detection": [{"ruleName": "Rule 2"}]},
        {"id": "de_003", "detection": [{"ruleName": "Rule 3"}]},
    ]
    ocsf_good = {"class_uid": 2004, "finding_info": {"uid": "ok"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [
        ocsf_good,
        ValueError("bad detection"),
        ocsf_good,
    ]

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.chronicle_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.chronicle_ocsf.ChronicleOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "partial"
    assert result["count"] == 2
    assert result["errors"] == 1
    assert len(result["normalized_alerts"]) == 2
