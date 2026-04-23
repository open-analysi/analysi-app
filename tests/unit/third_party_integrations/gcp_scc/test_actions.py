"""Unit tests for Google Cloud SCC integration actions.

All actions use the base-class http_request() helper which applies
integration_retry_policy automatically. Tests mock at the
IntegrationAction.http_request level so retry behaviour is transparent.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.gcp_scc.actions import (
    GetFindingAction,
    GetNotificationConfigAction,
    HealthCheckAction,
    ListAssetsAction,
    ListFindingsAction,
    ListNotificationConfigsAction,
    ListSourcesAction,
    UpdateFindingStateAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"access_token": "ya29.test-access-token"}
DEFAULT_SETTINGS = {"organization_id": "123456789012", "timeout": 30}


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake httpx.HTTPStatusError."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = body
    request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}", request=request, response=response
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="gcp_scc",
            action_id="health_check",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {
                "sources": [
                    {
                        "name": "organizations/123/sources/456",
                        "displayName": "Security Health Analytics",
                    }
                ]
            }
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["api_version"] == "v1"
        assert result["data"]["organization_id"] == "123456789012"
        assert result["healthy"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_access_token(self):
        action = HealthCheckAction(
            integration_id="gcp_scc",
            action_id="health_check",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "access_token" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_organization_id(self):
        action = HealthCheckAction(
            integration_id="gcp_scc",
            action_id="health_check",
            settings={},
            credentials=DEFAULT_CREDENTIALS,
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "organization_id" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["healthy"] is False


# ===========================================================================
# ListFindingsAction
# ===========================================================================


class TestListFindingsAction:
    @pytest.fixture
    def action(self):
        return ListFindingsAction(
            integration_id="gcp_scc",
            action_id="list_findings",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {
                "listFindingsResults": [
                    {
                        "finding": {
                            "name": "organizations/123/sources/456/findings/f1",
                            "category": "PUBLIC_BUCKET_ACL",
                            "severity": "HIGH",
                            "state": "ACTIVE",
                        }
                    },
                    {
                        "finding": {
                            "name": "organizations/123/sources/456/findings/f2",
                            "category": "OPEN_FIREWALL",
                            "severity": "MEDIUM",
                            "state": "ACTIVE",
                        }
                    },
                ],
                "readTime": "2026-01-15T10:00:00Z",
                "nextPageToken": "token123",
            }
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(filter='severity="HIGH"')

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 2
        assert result["data"]["next_page_token"] == "token123"
        assert len(result["data"]["findings"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_all_params(self, action):
        mock_response = _json_response(
            {"listFindingsResults": [], "readTime": "2026-01-15T10:00:00Z"}
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            source_id="456",
            filter='state="ACTIVE"',
            page_size=50,
            page_token="abc",
            order_by="eventTime desc",
        )

        assert result["status"] == "success"
        # Verify the URL and params were passed correctly
        call_kwargs = action.http_request.call_args
        assert "sources/456/findings" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["params"]["pageSize"] == 50
        assert call_kwargs.kwargs["params"]["filter"] == 'state="ACTIVE"'
        assert call_kwargs.kwargs["params"]["pageToken"] == "abc"
        assert call_kwargs.kwargs["params"]["orderBy"] == "eventTime desc"

    @pytest.mark.asyncio
    async def test_page_size_capped_at_max(self, action):
        mock_response = _json_response({"listFindingsResults": []})
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(page_size=5000)

        call_kwargs = action.http_request.call_args
        assert call_kwargs.kwargs["params"]["pageSize"] == 1000

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListFindingsAction(
            integration_id="gcp_scc",
            action_id="list_findings",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_org_id(self):
        action = ListFindingsAction(
            integration_id="gcp_scc",
            action_id="list_findings",
            settings={},
            credentials=DEFAULT_CREDENTIALS,
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "organization_id" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(403))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_invalid_page_size_string(self, action):
        result = await action.execute(page_size="not-a-number")

        assert result["status"] == "error"
        assert "page_size" in result["error"]
        assert result["error_type"] == "ValidationError"


# ===========================================================================
# GetFindingAction
# ===========================================================================


class TestGetFindingAction:
    @pytest.fixture
    def action(self):
        return GetFindingAction(
            integration_id="gcp_scc",
            action_id="get_finding",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        finding_data = {
            "name": "organizations/123/sources/456/findings/f1",
            "category": "PUBLIC_BUCKET_ACL",
            "severity": "HIGH",
            "state": "ACTIVE",
            "resourceName": "//storage.googleapis.com/my-bucket",
        }
        mock_response = _json_response(finding_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1"
        )

        assert result["status"] == "success"
        assert result["data"]["name"] == "organizations/123/sources/456/findings/f1"
        assert result["data"]["severity"] == "HIGH"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/nonexistent"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert "finding_name" in result["data"]

    @pytest.mark.asyncio
    async def test_missing_finding_name(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "finding_name" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = GetFindingAction(
            integration_id="gcp_scc",
            action_id="get_finding",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# UpdateFindingStateAction
# ===========================================================================


class TestUpdateFindingStateAction:
    @pytest.fixture
    def action(self):
        return UpdateFindingStateAction(
            integration_id="gcp_scc",
            action_id="update_finding_state",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success_mute(self, action):
        updated_finding = {
            "name": "organizations/123/sources/456/findings/f1",
            "state": "MUTED",
        }
        mock_response = _json_response(updated_finding)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1",
            state="MUTED",
        )

        assert result["status"] == "success"
        assert result["data"]["new_state"] == "MUTED"
        assert "integration_id" in result

        # Verify the POST call
        call_kwargs = action.http_request.call_args
        assert call_kwargs.kwargs["method"] == "POST"
        assert ":setState" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["json_data"]["state"] == "MUTED"

    @pytest.mark.asyncio
    async def test_success_case_insensitive(self, action):
        mock_response = _json_response({"state": "INACTIVE"})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1",
            state="inactive",
        )

        assert result["status"] == "success"
        assert result["data"]["new_state"] == "INACTIVE"

    @pytest.mark.asyncio
    async def test_invalid_state(self, action):
        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1",
            state="DELETED",
        )

        assert result["status"] == "error"
        assert "Invalid state" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_finding_name(self, action):
        result = await action.execute(state="ACTIVE")

        assert result["status"] == "error"
        assert "finding_name" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_state(self, action):
        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1"
        )

        assert result["status"] == "error"
        assert "state" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/nonexistent",
            state="MUTED",
        )

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = UpdateFindingStateAction(
            integration_id="gcp_scc",
            action_id="update_finding_state",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute(
            finding_name="organizations/123/sources/456/findings/f1",
            state="ACTIVE",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# ListSourcesAction
# ===========================================================================


class TestListSourcesAction:
    @pytest.fixture
    def action(self):
        return ListSourcesAction(
            integration_id="gcp_scc",
            action_id="list_sources",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {
                "sources": [
                    {
                        "name": "organizations/123/sources/1",
                        "displayName": "Security Health Analytics",
                        "description": "Identifies misconfigurations",
                    },
                    {
                        "name": "organizations/123/sources/2",
                        "displayName": "Event Threat Detection",
                        "description": "Detects threats",
                    },
                ],
                "nextPageToken": "next-page",
            }
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 2
        assert len(result["data"]["sources"]) == 2
        assert result["data"]["next_page_token"] == "next-page"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_sources(self, action):
        mock_response = _json_response({"sources": []})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 0
        assert result["data"]["sources"] == []

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListSourcesAction(
            integration_id="gcp_scc",
            action_id="list_sources",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_org_id(self):
        action = ListSourcesAction(
            integration_id="gcp_scc",
            action_id="list_sources",
            settings={},
            credentials=DEFAULT_CREDENTIALS,
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "organization_id" in result["error"]


# ===========================================================================
# ListAssetsAction
# ===========================================================================


class TestListAssetsAction:
    @pytest.fixture
    def action(self):
        return ListAssetsAction(
            integration_id="gcp_scc",
            action_id="list_assets",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {
                "listAssetsResults": [
                    {
                        "asset": {
                            "name": "organizations/123/assets/a1",
                            "securityCenterProperties": {
                                "resourceType": "google.compute.Instance"
                            },
                        }
                    }
                ],
                "readTime": "2026-01-15T10:00:00Z",
            }
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 1
        assert len(result["data"]["assets"]) == 1
        assert result["data"]["read_time"] == "2026-01-15T10:00:00Z"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_filter(self, action):
        mock_response = _json_response({"listAssetsResults": []})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            filter='securityCenterProperties.resourceType="google.compute.Instance"'
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args
        assert (
            call_kwargs.kwargs["params"]["filter"]
            == 'securityCenterProperties.resourceType="google.compute.Instance"'
        )

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListAssetsAction(
            integration_id="gcp_scc",
            action_id="list_assets",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(403))

        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# GetNotificationConfigAction
# ===========================================================================


class TestGetNotificationConfigAction:
    @pytest.fixture
    def action(self):
        return GetNotificationConfigAction(
            integration_id="gcp_scc",
            action_id="get_notification_config",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        config_data = {
            "name": "organizations/123/notificationConfigs/my-config",
            "description": "Alert on critical findings",
            "pubsubTopic": "projects/my-project/topics/scc-alerts",
            "streamingConfig": {"filter": 'severity="CRITICAL"'},
        }
        mock_response = _json_response(config_data)
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(
            config_name="organizations/123/notificationConfigs/my-config"
        )

        assert result["status"] == "success"
        assert result["data"]["pubsubTopic"] == "projects/my-project/topics/scc-alerts"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(
            config_name="organizations/123/notificationConfigs/nonexistent"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert "config_name" in result["data"]

    @pytest.mark.asyncio
    async def test_missing_config_name(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "config_name" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = GetNotificationConfigAction(
            integration_id="gcp_scc",
            action_id="get_notification_config",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute(
            config_name="organizations/123/notificationConfigs/my-config"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# ListNotificationConfigsAction
# ===========================================================================


class TestListNotificationConfigsAction:
    @pytest.fixture
    def action(self):
        return ListNotificationConfigsAction(
            integration_id="gcp_scc",
            action_id="list_notification_configs",
            settings=DEFAULT_SETTINGS,
            credentials=DEFAULT_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {
                "notificationConfigs": [
                    {
                        "name": "organizations/123/notificationConfigs/config-1",
                        "description": "Critical alerts",
                    },
                    {
                        "name": "organizations/123/notificationConfigs/config-2",
                        "description": "High severity alerts",
                    },
                ],
                "nextPageToken": "next",
            }
        )
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 2
        assert len(result["data"]["notification_configs"]) == 2
        assert result["data"]["next_page_token"] == "next"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_configs(self, action):
        mock_response = _json_response({"notificationConfigs": []})
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 0

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListNotificationConfigsAction(
            integration_id="gcp_scc",
            action_id="list_notification_configs",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_org_id(self):
        action = ListNotificationConfigsAction(
            integration_id="gcp_scc",
            action_id="list_notification_configs",
            settings={},
            credentials=DEFAULT_CREDENTIALS,
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "organization_id" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# Bearer token header test (shared across all actions)
# ===========================================================================


class TestGCPSCCBaseHeaders:
    """Verify that all actions inherit the Bearer token header from _GCPSCCBase."""

    @pytest.mark.asyncio
    async def test_bearer_token_in_headers(self):
        action = HealthCheckAction(
            integration_id="gcp_scc",
            action_id="health_check",
            settings=DEFAULT_SETTINGS,
            credentials={"access_token": "ya29.my-token"},
        )
        headers = action.get_http_headers()

        assert headers["Authorization"] == "Bearer ya29.my-token"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_no_token_no_auth_header(self):
        action = HealthCheckAction(
            integration_id="gcp_scc",
            action_id="health_check",
            settings=DEFAULT_SETTINGS,
            credentials={},
        )
        headers = action.get_http_headers()

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
