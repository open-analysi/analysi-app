"""Unit tests for Microsoft Sentinel integration actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.integrations.framework.integrations.mssentinel.actions import (
    AddIncidentCommentAction,
    AlertsToOcsfAction,
    GetIncidentAction,
    GetIncidentAlertsAction,
    GetIncidentEntitiesAction,
    HealthCheckAction,
    ListIncidentsAction,
    PullAlertsAction,
    RunQueryAction,
    UpdateIncidentAction,
)


@pytest.fixture
def integration_id():
    """Integration ID for testing."""
    return "test-mssentinel-integration"


@pytest.fixture
def credentials():
    """Fixture for Sentinel credentials."""
    return {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }


@pytest.fixture
def settings():
    """Fixture for Sentinel settings."""
    return {
        "tenant_id": "test-tenant-id",
        "subscription_id": "test-subscription-id",
        "resource_group_name": "test-resource-group",
        "workspace_name": "test-workspace",
        "workspace_id": "test-workspace-id",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(integration_id, credentials, settings):
    """Fixture for HealthCheckAction."""
    return HealthCheckAction(integration_id, "health_check", settings, credentials)


@pytest.fixture
def list_incidents_action(integration_id, credentials, settings):
    """Fixture for ListIncidentsAction."""
    return ListIncidentsAction(integration_id, "list_incidents", settings, credentials)


@pytest.fixture
def get_incident_action(integration_id, credentials, settings):
    """Fixture for GetIncidentAction."""
    return GetIncidentAction(integration_id, "get_incident", settings, credentials)


@pytest.fixture
def update_incident_action(integration_id, credentials, settings):
    """Fixture for UpdateIncidentAction."""
    return UpdateIncidentAction(
        integration_id, "update_incident", settings, credentials
    )


@pytest.fixture
def add_comment_action(integration_id, credentials, settings):
    """Fixture for AddIncidentCommentAction."""
    return AddIncidentCommentAction(
        integration_id, "add_incident_comment", settings, credentials
    )


@pytest.fixture
def get_entities_action(integration_id, credentials, settings):
    """Fixture for GetIncidentEntitiesAction."""
    return GetIncidentEntitiesAction(
        integration_id, "get_incident_entities", settings, credentials
    )


@pytest.fixture
def get_alerts_action(integration_id, credentials, settings):
    """Fixture for GetIncidentAlertsAction."""
    return GetIncidentAlertsAction(
        integration_id, "get_incident_alerts", settings, credentials
    )


@pytest.fixture
def run_query_action(integration_id, credentials, settings):
    """Fixture for RunQueryAction."""
    return RunQueryAction(integration_id, "run_query", settings, credentials)


def _token_response():
    """Create a mock token response."""
    resp = MagicMock()
    resp.json.return_value = {"access_token": "test-token"}
    resp.raise_for_status = MagicMock()
    return resp


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_token_resp = _token_response()

        mock_incidents_response = MagicMock()
        mock_incidents_response.json.return_value = {"value": []}
        mock_incidents_response.raise_for_status = MagicMock()

        health_check_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_incidents_response]
        )
        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert "Microsoft Sentinel connection successful" in result["message"]
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self, health_check_action):
        """Test health check with missing credentials."""
        health_check_action.credentials = {}

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_http_error(self, health_check_action):
        """Test health check with HTTP error."""
        import httpx

        mock_token_resp = _token_response()

        mock_error_response = MagicMock()
        mock_error_response.status_code = 401
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_error_response
        )

        health_check_action.http_request = AsyncMock(
            side_effect=[
                mock_token_resp,
                httpx.HTTPStatusError(
                    "Unauthorized",
                    request=MagicMock(),
                    response=mock_error_response,
                ),
            ]
        )
        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"
        assert "401" in result["error"]


class TestListIncidentsAction:
    """Tests for ListIncidentsAction."""

    @pytest.mark.asyncio
    async def test_list_incidents_success(self, list_incidents_action):
        """Test successful incident listing."""
        mock_token_resp = _token_response()

        mock_incidents_response = MagicMock()
        mock_incidents_response.json.return_value = {
            "value": [
                {"id": "incident1", "name": "test-incident-1"},
                {"id": "incident2", "name": "test-incident-2"},
            ]
        }
        mock_incidents_response.raise_for_status = MagicMock()

        list_incidents_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_incidents_response]
        )
        result = await list_incidents_action.execute(limit=100)

        assert result["status"] == "success"
        assert result["total_incidents"] == 2
        assert len(result["incidents"]) == 2

    @pytest.mark.asyncio
    async def test_list_incidents_invalid_limit(self, list_incidents_action):
        """Test list incidents with invalid limit."""
        result = await list_incidents_action.execute(limit=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "positive integer" in result["error"]

    @pytest.mark.asyncio
    async def test_list_incidents_with_filter(self, list_incidents_action):
        """Test list incidents with filter."""
        mock_token_resp = _token_response()

        mock_incidents_response = MagicMock()
        mock_incidents_response.json.return_value = {
            "value": [{"id": "incident1", "name": "high-severity"}]
        }
        mock_incidents_response.raise_for_status = MagicMock()

        list_incidents_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_incidents_response]
        )
        result = await list_incidents_action.execute(
            limit=10, filter="properties/severity eq 'High'"
        )

        assert result["status"] == "success"
        assert result["total_incidents"] == 1


class TestGetIncidentAction:
    """Tests for GetIncidentAction."""

    @pytest.mark.asyncio
    async def test_get_incident_success(self, get_incident_action):
        """Test successful incident retrieval."""
        mock_token_resp = _token_response()

        mock_incident_response = MagicMock()
        mock_incident_response.json.return_value = {
            "id": "/subscriptions/.../incident123",
            "name": "incident123",
            "properties": {
                "title": "Test Incident",
                "severity": "High",
                "status": "Active",
            },
        }
        mock_incident_response.raise_for_status = MagicMock()

        get_incident_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_incident_response]
        )
        result = await get_incident_action.execute(incident_name="incident123")

        assert result["status"] == "success"
        assert result["incident_name"] == "incident123"
        assert "incident" in result

    @pytest.mark.asyncio
    async def test_get_incident_missing_name(self, get_incident_action):
        """Test get incident with missing name."""
        result = await get_incident_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "incident_name" in result["error"]


class TestUpdateIncidentAction:
    """Tests for UpdateIncidentAction."""

    @pytest.mark.asyncio
    async def test_update_incident_success(self, update_incident_action):
        """Test successful incident update."""
        mock_token_resp = _token_response()

        # UpdateIncidentAction calls: token, GET incident, PUT update
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "id": "incident123",
            "name": "incident123",
            "properties": {
                "title": "Old Title",
                "severity": "Medium",
                "status": "New",
            },
        }
        mock_get_response.raise_for_status = MagicMock()

        mock_put_response = MagicMock()
        mock_put_response.json.return_value = {
            "id": "incident123",
            "name": "incident123",
            "properties": {
                "title": "New Title",
                "severity": "High",
                "status": "Active",
            },
        }
        mock_put_response.raise_for_status = MagicMock()

        update_incident_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_get_response, mock_put_response]
        )
        result = await update_incident_action.execute(
            incident_name="incident123",
            severity="High",
            status="Active",
            title="New Title",
        )

        assert result["status"] == "success"
        assert result["incident_name"] == "incident123"

    @pytest.mark.asyncio
    async def test_update_incident_missing_name(self, update_incident_action):
        """Test update incident with missing name."""
        result = await update_incident_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestAddIncidentCommentAction:
    """Tests for AddIncidentCommentAction."""

    @pytest.mark.asyncio
    async def test_add_comment_success(self, add_comment_action):
        """Test successful comment addition."""
        mock_token_resp = _token_response()

        mock_put_response = MagicMock()
        mock_put_response.json.return_value = {
            "id": "comment123",
            "properties": {"message": "Test comment"},
        }
        mock_put_response.raise_for_status = MagicMock()

        add_comment_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_put_response]
        )
        result = await add_comment_action.execute(
            incident_name="incident123", message="Test comment"
        )

        assert result["status"] == "success"
        assert "comment" in result

    @pytest.mark.asyncio
    async def test_add_comment_missing_params(self, add_comment_action):
        """Test add comment with missing parameters."""
        result = await add_comment_action.execute(incident_name="incident123")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestGetIncidentEntitiesAction:
    """Tests for GetIncidentEntitiesAction."""

    @pytest.mark.asyncio
    async def test_get_entities_success(self, get_entities_action):
        """Test successful entities retrieval."""
        mock_token_resp = _token_response()

        mock_entities_response = MagicMock()
        mock_entities_response.json.return_value = {
            "entities": [
                {"id": "entity1", "kind": "Account"},
                {"id": "entity2", "kind": "Host"},
            ]
        }
        mock_entities_response.raise_for_status = MagicMock()

        get_entities_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_entities_response]
        )
        result = await get_entities_action.execute(incident_name="incident123")

        assert result["status"] == "success"
        assert result["total_entities"] == 2

    @pytest.mark.asyncio
    async def test_get_entities_missing_name(self, get_entities_action):
        """Test get entities with missing incident name."""
        result = await get_entities_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestGetIncidentAlertsAction:
    """Tests for GetIncidentAlertsAction."""

    @pytest.mark.asyncio
    async def test_get_alerts_success(self, get_alerts_action):
        """Test successful alerts retrieval."""
        mock_token_resp = _token_response()

        mock_alerts_response = MagicMock()
        mock_alerts_response.json.return_value = {
            "value": [
                {"id": "alert1", "kind": "SecurityAlert"},
                {"id": "alert2", "kind": "SecurityAlert"},
            ]
        }
        mock_alerts_response.raise_for_status = MagicMock()

        get_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_alerts_response]
        )
        result = await get_alerts_action.execute(incident_name="incident123")

        assert result["status"] == "success"
        assert result["total_alerts"] == 2

    @pytest.mark.asyncio
    async def test_get_alerts_missing_name(self, get_alerts_action):
        """Test get alerts with missing incident name."""
        result = await get_alerts_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestRunQueryAction:
    """Tests for RunQueryAction."""

    @pytest.mark.asyncio
    async def test_run_query_success(self, run_query_action):
        """Test successful KQL query execution."""
        mock_token_resp = _token_response()

        mock_query_response = MagicMock()
        mock_query_response.json.return_value = {
            "tables": [
                {
                    "name": "PrimaryResult",
                    "columns": [
                        {"name": "TimeGenerated", "type": "datetime"},
                        {"name": "IncidentName", "type": "string"},
                    ],
                    "rows": [
                        ["2024-01-01T00:00:00Z", "incident1"],
                        ["2024-01-01T01:00:00Z", "incident2"],
                    ],
                }
            ]
        }
        mock_query_response.raise_for_status = MagicMock()

        run_query_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_query_response]
        )
        result = await run_query_action.execute(
            query="SecurityIncident | limit 10", max_rows=3000
        )

        assert result["status"] == "success"
        assert result["total_rows"] == 2
        assert len(result["rows"]) == 2

    @pytest.mark.asyncio
    async def test_run_query_missing_query(self, run_query_action):
        """Test run query with missing query parameter."""
        result = await run_query_action.execute(max_rows=3000)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_run_query_invalid_max_rows(self, run_query_action):
        """Test run query with invalid max_rows."""
        result = await run_query_action.execute(query="SecurityIncident", max_rows=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "positive integer" in result["error"]


# ── AlertSource action fixtures ──────────────────────────────────────


@pytest.fixture
def pull_alerts_action(integration_id, credentials, settings):
    """Fixture for PullAlertsAction."""
    return PullAlertsAction(integration_id, "pull_alerts", settings, credentials)


@pytest.fixture
def alerts_to_ocsf_action(integration_id, credentials, settings):
    """Fixture for AlertsToOcsfAction."""
    return AlertsToOcsfAction(integration_id, "alerts_to_ocsf", settings, credentials)


def _sentinel_incident(
    name="inc-001", title="Test Incident", severity="High", status="Active"
):
    """Build a minimal Sentinel incident dict for testing."""
    return {
        "id": f"/subscriptions/sub/resourceGroups/rg/providers/.../incidents/{name}",
        "name": name,
        "properties": {
            "incidentNumber": 1,
            "title": title,
            "description": "Test incident description",
            "severity": severity,
            "status": status,
            "createdTimeUtc": "2025-03-15T10:00:00.000Z",
            "lastModifiedTimeUtc": "2025-03-15T12:00:00.000Z",
            "additionalData": {
                "alertProductNames": ["Microsoft Defender"],
                "tactics": ["InitialAccess"],
            },
        },
    }


class TestPullAlertsAction:
    """Tests for PullAlertsAction."""

    @pytest.mark.asyncio
    async def test_pull_alerts_success(self, pull_alerts_action):
        """Test successful alert pulling."""
        mock_token_resp = _token_response()

        mock_incidents_response = MagicMock()
        mock_incidents_response.json.return_value = {
            "value": [
                _sentinel_incident("inc-001"),
                _sentinel_incident("inc-002", title="Second Incident"),
            ]
        }
        mock_incidents_response.raise_for_status = MagicMock()

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_incidents_response]
        )
        result = await pull_alerts_action.execute()

        assert result["status"] == "success"
        assert result["alerts_count"] == 2
        assert len(result["alerts"]) == 2
        assert "Retrieved 2 incidents" in result["message"]

    @pytest.mark.asyncio
    async def test_pull_alerts_with_time_range(self, pull_alerts_action):
        """Test pull alerts with explicit start_time."""
        mock_token_resp = _token_response()

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": [_sentinel_incident("inc-001")]}
        mock_response.raise_for_status = MagicMock()

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_response]
        )
        result = await pull_alerts_action.execute(
            start_time="2025-03-15T00:00:00Z",
            end_time="2025-03-15T23:59:59Z",
        )

        assert result["status"] == "success"
        assert result["alerts_count"] == 1

        # Verify the filter was applied (check the second call args)
        call_args = pull_alerts_action.http_request.call_args_list[1]
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert "$filter" in params
        assert "createdTimeUtc ge" in params["$filter"]
        assert "$orderby" in params
        assert "createdTimeUtc desc" in params["$orderby"]

    @pytest.mark.asyncio
    async def test_pull_alerts_empty_result(self, pull_alerts_action):
        """Test pull alerts with no results."""
        mock_token_resp = _token_response()

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_response]
        )
        result = await pull_alerts_action.execute()

        assert result["status"] == "success"
        assert result["alerts_count"] == 0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_pull_alerts_missing_credentials(self, pull_alerts_action):
        """Test pull alerts with missing credentials."""
        pull_alerts_action.credentials = {}

        result = await pull_alerts_action.execute()

        assert result["status"] == "error"
        assert result["alerts_count"] == 0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_pull_alerts_http_error(self, pull_alerts_action):
        """Test pull alerts with HTTP error."""
        import httpx

        mock_token_resp = _token_response()

        mock_error_response = MagicMock()
        mock_error_response.status_code = 403

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[
                mock_token_resp,
                httpx.HTTPStatusError(
                    "Forbidden",
                    request=MagicMock(),
                    response=mock_error_response,
                ),
            ]
        )
        result = await pull_alerts_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"
        assert "403" in result["error"]
        assert result["alerts_count"] == 0

    @pytest.mark.asyncio
    async def test_pull_alerts_pagination(self, pull_alerts_action):
        """Test pull alerts with paginated results."""
        mock_token_resp = _token_response()

        # First page with nextLink
        page1_response = MagicMock()
        page1_response.json.return_value = {
            "value": [_sentinel_incident("inc-001")],
            "nextLink": "https://management.azure.com/next?token=abc",
        }
        page1_response.raise_for_status = MagicMock()

        # Second page without nextLink
        page2_response = MagicMock()
        page2_response.json.return_value = {
            "value": [_sentinel_incident("inc-002")],
        }
        page2_response.raise_for_status = MagicMock()

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, page1_response, page2_response]
        )
        result = await pull_alerts_action.execute()

        assert result["status"] == "success"
        assert result["alerts_count"] == 2
        # Three HTTP calls: token + page1 + page2
        assert pull_alerts_action.http_request.call_count == 3

    @pytest.mark.asyncio
    async def test_pull_alerts_uses_lookback_setting(self, pull_alerts_action):
        """Test that default_lookback_minutes from settings is used."""
        pull_alerts_action.settings["default_lookback_minutes"] = 15

        mock_token_resp = _token_response()
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        pull_alerts_action.http_request = AsyncMock(
            side_effect=[mock_token_resp, mock_response]
        )
        result = await pull_alerts_action.execute()

        assert result["status"] == "success"


class TestAlertsToOcsfAction:
    """Tests for AlertsToOcsfAction."""

    @pytest.mark.asyncio
    async def test_normalize_success(self, alerts_to_ocsf_action):
        """Test successful OCSF normalization."""
        raw_alerts = [
            _sentinel_incident("inc-001"),
            _sentinel_incident("inc-002", title="Second Alert", severity="Medium"),
        ]

        result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["errors"] == 0
        assert len(result["normalized_alerts"]) == 2

        # Verify OCSF structure
        first = result["normalized_alerts"][0]
        assert first["class_uid"] == 2004
        assert first["class_name"] == "Detection Finding"
        assert first["severity_id"] == 4  # High
        assert first["metadata"]["product"]["vendor_name"] == "Microsoft"

    @pytest.mark.asyncio
    async def test_normalize_empty_list(self, alerts_to_ocsf_action):
        """Test normalization with empty input."""
        result = await alerts_to_ocsf_action.execute(raw_alerts=[])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["errors"] == 0
        assert result["normalized_alerts"] == []

    @pytest.mark.asyncio
    async def test_normalize_default_empty(self, alerts_to_ocsf_action):
        """Test normalization with no raw_alerts param defaults to empty."""
        result = await alerts_to_ocsf_action.execute()

        assert result["status"] == "success"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_normalize_partial_failure(self, alerts_to_ocsf_action):
        """Test normalization where some alerts fail."""
        raw_alerts = [
            _sentinel_incident("inc-001"),
            "not-a-dict",  # This should cause a normalizer error
        ]

        result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

        assert result["status"] == "partial"
        assert result["count"] == 1
        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_normalize_preserves_mitre(self, alerts_to_ocsf_action):
        """Test that MITRE ATT&CK tactics are preserved in OCSF output."""
        raw_alerts = [_sentinel_incident("inc-001")]

        result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

        first = result["normalized_alerts"][0]
        attacks = first["finding_info"].get("attacks", [])
        assert len(attacks) > 0
        # InitialAccess -> TA0001
        assert any(a.get("tactic", {}).get("uid") == "TA0001" for a in attacks)
