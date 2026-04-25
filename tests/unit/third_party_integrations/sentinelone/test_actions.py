"""Unit tests for SentinelOne integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.sentinelone.actions import (
    AbortScanAction,
    AddThreatNoteAction,
    AlertsToOcsfAction,
    BlockHashAction,
    BroadcastMessageAction,
    GetHostDetailsAction,
    GetThreatInfoAction,
    GetThreatNotesAction,
    HashReputationAction,
    HealthCheckAction,
    IsolateHostAction,
    MitigateThreatAction,
    PullAlertsAction,
    ReleaseHostAction,
    ScanHostAction,
    ShutdownEndpointAction,
    UnblockHashAction,
    UpdateThreatAnalystVerdictAction,
    UpdateThreatIncidentAction,
)


@pytest.fixture
def credentials():
    """SentinelOne credentials fixture."""
    return {
        "api_token": "test_token_123",
    }


@pytest.fixture
def settings():
    """SentinelOne settings fixture."""
    return {"console_url": "https://test.sentinelone.net", "timeout": 30}


@pytest.fixture
def health_check_action(credentials, settings):
    """HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="sentinelone",
        action_id="health_check",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def block_hash_action(credentials, settings):
    """BlockHashAction instance."""
    return BlockHashAction(
        integration_id="sentinelone",
        action_id="block_hash",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def unblock_hash_action(credentials, settings):
    """UnblockHashAction instance."""
    return UnblockHashAction(
        integration_id="sentinelone",
        action_id="unblock_hash",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def isolate_host_action(credentials, settings):
    """IsolateHostAction instance."""
    return IsolateHostAction(
        integration_id="sentinelone",
        action_id="isolate_host",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def release_host_action(credentials, settings):
    """ReleaseHostAction instance."""
    return ReleaseHostAction(
        integration_id="sentinelone",
        action_id="release_host",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def scan_host_action(credentials, settings):
    """ScanHostAction instance."""
    return ScanHostAction(
        integration_id="sentinelone",
        action_id="scan_host",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_host_details_action(credentials, settings):
    """GetHostDetailsAction instance."""
    return GetHostDetailsAction(
        integration_id="sentinelone",
        action_id="get_host_details",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def mitigate_threat_action(credentials, settings):
    """MitigateThreatAction instance."""
    return MitigateThreatAction(
        integration_id="sentinelone",
        action_id="mitigate_threat",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def abort_scan_action(credentials, settings):
    """AbortScanAction instance."""
    return AbortScanAction(
        integration_id="sentinelone",
        action_id="abort_scan",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def shutdown_endpoint_action(credentials, settings):
    """ShutdownEndpointAction instance."""
    return ShutdownEndpointAction(
        integration_id="sentinelone",
        action_id="shutdown_endpoint",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def broadcast_message_action(credentials, settings):
    """BroadcastMessageAction instance."""
    return BroadcastMessageAction(
        integration_id="sentinelone",
        action_id="broadcast_message",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_threat_info_action(credentials, settings):
    """GetThreatInfoAction instance."""
    return GetThreatInfoAction(
        integration_id="sentinelone",
        action_id="get_threat_info",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def hash_reputation_action(credentials, settings):
    """HashReputationAction instance."""
    return HashReputationAction(
        integration_id="sentinelone",
        action_id="hash_reputation",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_threat_notes_action(credentials, settings):
    """GetThreatNotesAction instance."""
    return GetThreatNotesAction(
        integration_id="sentinelone",
        action_id="get_threat_notes",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def add_threat_note_action(credentials, settings):
    """AddThreatNoteAction instance."""
    return AddThreatNoteAction(
        integration_id="sentinelone",
        action_id="add_threat_note",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def update_threat_analyst_verdict_action(credentials, settings):
    """UpdateThreatAnalystVerdictAction instance."""
    return UpdateThreatAnalystVerdictAction(
        integration_id="sentinelone",
        action_id="update_threat_analyst_verdict",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def update_threat_incident_action(credentials, settings):
    """UpdateThreatIncidentAction instance."""
    return UpdateThreatIncidentAction(
        integration_id="sentinelone",
        action_id="update_threat_incident",
        settings=settings,
        credentials=credentials,
    )


def _make_routing_request(mock_client):
    """Create a request method that routes to get/post/delete based on method."""

    async def _request(method, *args, **kwargs):
        if method.upper() == "GET":
            return await mock_client.get(*args, **kwargs)
        if method.upper() == "POST":
            return await mock_client.post(*args, **kwargs)
        if method.upper() == "DELETE":
            return await mock_client.delete(*args, **kwargs)
        raise ValueError(f"Unsupported method: {method}")

    return _request


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"id": "123"}]}
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "api_version" in result["data"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials(health_check_action):
    """Test health check with missing credentials."""
    health_check_action.credentials = {}

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_api_error(health_check_action):
    """Test health check with API error."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "API error", request=MagicMock(), response=MagicMock(status_code=500)
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert "error" in result["error"].lower() or "500" in result["error"]


# ============================================================================
# BLOCK/UNBLOCK HASH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_hash_success(block_hash_action):
    """Test successful hash blocking."""
    mock_response_check = MagicMock()
    mock_response_check.json.return_value = {"pagination": {"totalItems": 0}}
    mock_response_check.status_code = 200

    mock_response_sites = MagicMock()
    mock_response_sites.json.return_value = {
        "data": {"sites": [{"id": "site1"}, {"id": "site2"}]}
    }
    mock_response_sites.status_code = 200

    mock_response_block = MagicMock()
    mock_response_block.json.return_value = {"data": {"affected": 1}}
    mock_response_block.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = [mock_response_sites, mock_response_check]
    mock_client.post.return_value = mock_response_block

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await block_hash_action.execute(
            hash="abc123def456", description="Test block", os_family="windows"
        )

    assert result["status"] == "success"
    assert "Successfully added hash" in result["message"]


@pytest.mark.asyncio
async def test_block_hash_missing_parameter(block_hash_action):
    """Test block hash with missing hash parameter."""
    result = await block_hash_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'hash'" in result["error"]


@pytest.mark.asyncio
async def test_block_hash_already_exists(block_hash_action):
    """Test block hash when hash already exists."""
    mock_response_check = MagicMock()
    mock_response_check.json.return_value = {"pagination": {"totalItems": 1}}
    mock_response_check.status_code = 200

    mock_response_sites = MagicMock()
    mock_response_sites.json.return_value = {"data": {"sites": [{"id": "site1"}]}}
    mock_response_sites.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = [mock_response_sites, mock_response_check]

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await block_hash_action.execute(
            hash="abc123def456", description="Test", os_family="windows"
        )

    assert result["status"] == "error"
    assert "already exists" in result["error"]


@pytest.mark.asyncio
async def test_unblock_hash_success(unblock_hash_action):
    """Test successful hash unblocking."""
    mock_response_find = MagicMock()
    mock_response_find.json.return_value = {
        "pagination": {"totalItems": 1},
        "data": [{"id": "hash_id_123"}],
    }
    mock_response_find.status_code = 200

    mock_response_delete = MagicMock()
    mock_response_delete.json.return_value = {}
    mock_response_delete.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_find
    mock_client.delete.return_value = mock_response_delete

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await unblock_hash_action.execute(hash="abc123def456")

    assert result["status"] == "success"
    assert "Successfully removed hash" in result["message"]


@pytest.mark.asyncio
async def test_unblock_hash_not_found(unblock_hash_action):
    """Test unblock hash when hash not found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"pagination": {"totalItems": 0}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await unblock_hash_action.execute(hash="abc123def456")

    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# ISOLATE/RELEASE HOST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_isolate_host_success(isolate_host_action):
    """Test successful host isolation."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_isolate = MagicMock()
    mock_response_isolate.json.return_value = {"data": {"affected": 1}}
    mock_response_isolate.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_isolate

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await isolate_host_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "Successfully quarantined" in result["message"]


@pytest.mark.asyncio
async def test_isolate_host_not_found(isolate_host_action):
    """Test isolate host when endpoint not found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": []}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await isolate_host_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "error"
    assert "Endpoint not found" in result["error"]


@pytest.mark.asyncio
async def test_release_host_success(release_host_action):
    """Test successful host release."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_release = MagicMock()
    mock_response_release.json.return_value = {"data": {"affected": 1}}
    mock_response_release.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_release

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await release_host_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "Successfully unquarantined" in result["message"]


# ============================================================================
# SCAN HOST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_host_success(scan_host_action):
    """Test successful host scan."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_scan = MagicMock()
    mock_response_scan.json.return_value = {"data": {"affected": 1}}
    mock_response_scan.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_scan

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scan_host_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "Successfully initiated scan" in result["message"]


@pytest.mark.asyncio
async def test_scan_host_missing_parameter(scan_host_action):
    """Test scan host with missing parameter."""
    result = await scan_host_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# GET HOST DETAILS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_host_details_success(get_host_details_action):
    """Test successful get host details."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_details = MagicMock()
    mock_response_details.json.return_value = {
        "data": [{"id": "agent123", "computerName": "TEST-PC", "osType": "windows"}]
    }
    mock_response_details.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = [mock_response_agent, mock_response_details]

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_host_details_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "data" in result


# ============================================================================
# THREAT MITIGATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_mitigate_threat_success(mitigate_threat_action):
    """Test successful threat mitigation."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"affected": 1}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await mitigate_threat_action.execute(
            s1_threat_id="threat123", action="kill"
        )

    assert result["status"] == "success"
    assert "Successfully mitigated threat" in result["message"]


@pytest.mark.asyncio
async def test_mitigate_threat_invalid_action(mitigate_threat_action):
    """Test mitigate threat with invalid action."""
    result = await mitigate_threat_action.execute(
        s1_threat_id="threat123", action="invalid_action"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid action" in result["error"]


@pytest.mark.asyncio
async def test_mitigate_threat_not_found(mitigate_threat_action):
    """Test mitigate threat when threat not found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"affected": 0}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await mitigate_threat_action.execute(
            s1_threat_id="threat123", action="kill"
        )

    assert result["status"] == "error"
    assert "Threat ID not found" in result["error"]


# ============================================================================
# ABORT SCAN TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_abort_scan_success(abort_scan_action):
    """Test successful scan abort."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_abort = MagicMock()
    mock_response_abort.json.return_value = {"data": {"affected": 1}}
    mock_response_abort.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_abort

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await abort_scan_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "Successfully aborted scan" in result["message"]


# ============================================================================
# SHUTDOWN ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_shutdown_endpoint_success(shutdown_endpoint_action):
    """Test successful endpoint shutdown."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_shutdown = MagicMock()
    mock_response_shutdown.json.return_value = {"data": {"affected": 1}}
    mock_response_shutdown.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_shutdown

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await shutdown_endpoint_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "success"
    assert "Successfully shutdown endpoint" in result["message"]


# ============================================================================
# BROADCAST MESSAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_message_success(broadcast_message_action):
    """Test successful message broadcast."""
    mock_response_agent = MagicMock()
    mock_response_agent.json.return_value = {"data": [{"id": "agent123"}]}
    mock_response_agent.status_code = 200

    mock_response_broadcast = MagicMock()
    mock_response_broadcast.json.return_value = {}
    mock_response_broadcast.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response_agent
    mock_client.post.return_value = mock_response_broadcast

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await broadcast_message_action.execute(
            ip_hostname="192.168.1.100", message="Security alert"
        )

    assert result["status"] == "success"
    assert "Successfully broadcast message" in result["message"]


@pytest.mark.asyncio
async def test_broadcast_message_missing_message(broadcast_message_action):
    """Test broadcast with missing message."""
    result = await broadcast_message_action.execute(ip_hostname="192.168.1.100")

    assert result["status"] == "error"
    assert "Missing required parameter 'message'" in result["error"]


# ============================================================================
# THREAT INFO TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_threat_info_success(get_threat_info_action):
    """Test successful threat info retrieval."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"id": "threat123", "threatInfo": {"threatName": "malware.exe"}}]
    }
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_threat_info_action.execute(s1_threat_id="threat123")

    assert result["status"] == "success"
    assert "data" in result


# ============================================================================
# HASH REPUTATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_hash_reputation_success(hash_reputation_action):
    """Test successful hash reputation lookup."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {"rank": 5, "classification": "malicious"}
    }
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await hash_reputation_action.execute(hash="abc123def456")

    assert result["status"] == "success"
    assert "data" in result


# ============================================================================
# THREAT NOTES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_threat_notes_success(get_threat_notes_action):
    """Test successful threat notes retrieval."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"id": "note1", "text": "Investigated"}]
    }
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_threat_notes_action.execute(s1_threat_id="threat123")

    assert result["status"] == "success"
    assert "data" in result


@pytest.mark.asyncio
async def test_add_threat_note_success(add_threat_note_action):
    """Test successful threat note addition."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"affected": 2}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await add_threat_note_action.execute(
            s1_threat_ids="threat1, threat2", note="Resolved"
        )

    assert result["status"] == "success"
    assert "Successfully added note" in result["message"]


@pytest.mark.asyncio
async def test_add_threat_note_invalid_ids(add_threat_note_action):
    """Test add threat note with invalid IDs."""
    result = await add_threat_note_action.execute(s1_threat_ids="  , , ", note="Test")

    assert result["status"] == "error"
    assert "Invalid s1_threat_ids" in result["error"]


# ============================================================================
# ANALYST VERDICT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_threat_analyst_verdict_success(
    update_threat_analyst_verdict_action,
):
    """Test successful analyst verdict update."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"affected": 1}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await update_threat_analyst_verdict_action.execute(
            s1_threat_id="threat123", analyst_verdict="true_positive"
        )

    assert result["status"] == "success"
    assert "Successfully updated" in result["message"]


@pytest.mark.asyncio
async def test_update_threat_analyst_verdict_invalid_verdict(
    update_threat_analyst_verdict_action,
):
    """Test update verdict with invalid verdict."""
    result = await update_threat_analyst_verdict_action.execute(
        s1_threat_id="threat123", analyst_verdict="invalid"
    )

    assert result["status"] == "error"
    assert "Invalid analyst_verdict" in result["error"]


# ============================================================================
# INCIDENT STATUS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_threat_incident_success(update_threat_incident_action):
    """Test successful threat incident update."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"affected": 1}}
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await update_threat_incident_action.execute(
            s1_threat_id="threat123",
            analyst_verdict="true_positive",
            incident_status="resolved",
        )

    assert result["status"] == "success"
    assert "Successfully updated" in result["message"]


@pytest.mark.asyncio
async def test_update_threat_incident_invalid_status(update_threat_incident_action):
    """Test update incident with invalid status."""
    result = await update_threat_incident_action.execute(
        s1_threat_id="threat123",
        analyst_verdict="true_positive",
        incident_status="invalid",
    )

    assert result["status"] == "error"
    assert "Invalid incident_status" in result["error"]


# ============================================================================
# PULL ALERTS (AlertSource) TESTS
# ============================================================================


@pytest.fixture
def pull_alerts_action(credentials, settings):
    """PullAlertsAction instance."""
    return PullAlertsAction(
        integration_id="sentinelone",
        action_id="pull_alerts",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def alerts_to_ocsf_action(credentials, settings):
    """AlertsToOcsfAction instance."""
    return AlertsToOcsfAction(
        integration_id="sentinelone",
        action_id="alerts_to_ocsf",
        settings=settings,
        credentials=credentials,
    )


def _make_s1_threat(threat_id="1234567890", threat_name="Test.Malware"):
    """Create a realistic SentinelOne threat object."""
    return {
        "id": threat_id,
        "threatInfo": {
            "threatName": threat_name,
            "classification": "Malware",
            "confidenceLevel": "malicious",
            "analystVerdict": "undefined",
            "mitigationStatus": "active",
            "sha256": "a1b2c3d4" * 8,
            "md5": "d41d8cd9" * 4,
            "sha1": "da39a3ee" * 5,
            "filePath": "C:\\test\\malware.exe",
            "fileName": "malware.exe",
            "processUser": "testuser",
            "createdAt": "2025-03-15T14:30:00.000Z",
            "updatedAt": "2025-03-15T14:35:00.000Z",
        },
        "agentRealtimeInfo": {
            "agentComputerName": "WORKSTATION-01",
            "agentOsName": "Windows 10",
            "networkInterfaces": [{"inet": ["192.168.1.50"]}],
        },
    }


@pytest.mark.asyncio
async def test_pull_alerts_success(pull_alerts_action):
    """Test successful threat pull with single page."""
    threats = [_make_s1_threat("threat-1"), _make_s1_threat("threat-2")]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": threats,
        "pagination": {"nextCursor": None, "totalItems": 2},
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 2
    assert len(result["alerts"]) == 2


@pytest.mark.asyncio
async def test_pull_alerts_with_pagination(pull_alerts_action):
    """Test threat pull with cursor pagination."""
    page1_response = MagicMock()
    page1_response.json.return_value = {
        "data": [_make_s1_threat("threat-1")],
        "pagination": {"nextCursor": "cursor-abc", "totalItems": 2},
    }
    page1_response.status_code = 200
    page1_response.raise_for_status = MagicMock()

    page2_response = MagicMock()
    page2_response.json.return_value = {
        "data": [_make_s1_threat("threat-2")],
        "pagination": {"nextCursor": None, "totalItems": 2},
    }
    page2_response.status_code = 200
    page2_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = [page1_response, page2_response]

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 2
    assert len(result["alerts"]) == 2


@pytest.mark.asyncio
async def test_pull_alerts_empty(pull_alerts_action):
    """Test threat pull when no threats found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [],
        "pagination": {"nextCursor": None, "totalItems": 0},
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 0


@pytest.mark.asyncio
async def test_pull_alerts_missing_credentials(pull_alerts_action):
    """Test pull alerts with missing credentials."""
    pull_alerts_action.credentials = {}

    result = await pull_alerts_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_pull_alerts_timeout(pull_alerts_action):
    """Test pull alerts timeout."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_pull_alerts_http_error(pull_alerts_action):
    """Test pull alerts HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_pull_alerts_with_custom_time_range(pull_alerts_action):
    """Test pull alerts with explicit start_time."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [_make_s1_threat()],
        "pagination": {"nextCursor": None},
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.request = AsyncMock(side_effect=_make_routing_request(mock_client))
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await pull_alerts_action.execute(
            start_time="2025-03-15T00:00:00+00:00"
        )

    assert result["status"] == "success"
    assert result["alerts_count"] == 1


# ============================================================================
# ALERTS TO OCSF TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_alerts_to_ocsf_success(alerts_to_ocsf_action):
    """Test successful OCSF normalization."""
    raw_alerts = [_make_s1_threat("threat-1"), _make_s1_threat("threat-2")]

    result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["errors"] == 0
    assert len(result["normalized_alerts"]) == 2

    # Verify OCSF structure
    ocsf = result["normalized_alerts"][0]
    assert ocsf["class_uid"] == 2004
    assert ocsf["severity_id"] == 5  # malicious -> Critical
    assert ocsf["is_alert"] is True


@pytest.mark.asyncio
async def test_alerts_to_ocsf_empty(alerts_to_ocsf_action):
    """Test OCSF normalization with empty list."""
    result = await alerts_to_ocsf_action.execute(raw_alerts=[])

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_alerts_to_ocsf_partial_failure(alerts_to_ocsf_action):
    """Test OCSF normalization with one bad alert."""
    raw_alerts = [
        _make_s1_threat("threat-1"),
        "not_a_dict",  # Will cause an error
    ]

    result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "partial"
    assert result["count"] == 1
    assert result["errors"] == 1


@pytest.mark.asyncio
async def test_alerts_to_ocsf_preserves_threat_id(alerts_to_ocsf_action):
    """Test that threat IDs are preserved in OCSF output."""
    raw_alerts = [_make_s1_threat("threat-42")]

    result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    ocsf = result["normalized_alerts"][0]
    assert ocsf["finding_info"]["uid"] == "threat-42"
    assert ocsf["metadata"]["event_code"] == "threat-42"
