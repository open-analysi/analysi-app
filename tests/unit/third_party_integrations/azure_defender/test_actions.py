"""Unit tests for Microsoft Defender for Cloud integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.azure_defender.actions import (
    GetAlertAction,
    GetRecommendationAction,
    HealthCheckAction,
    ListAlertsAction,
    ListAssessmentsAction,
    ListRecommendationsAction,
    ListSecureScoresAction,
    UpdateAlertStatusAction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def integration_id():
    """Integration ID for testing."""
    return "test-azure-defender"


@pytest.fixture
def credentials():
    """Azure AD app credentials."""
    return {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }


@pytest.fixture
def settings():
    """Integration settings with tenant_id and subscription_id."""
    return {
        "tenant_id": "test-tenant-id",
        "subscription_id": "test-sub-id",
        "timeout": 30,
    }


def _make_action(cls, integration_id, settings, credentials):
    """Helper to instantiate an action class."""
    return cls(
        integration_id=integration_id,
        action_id=cls.__name__.replace("Action", "").lower(),
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def health_check_action(integration_id, settings, credentials):
    return _make_action(HealthCheckAction, integration_id, settings, credentials)


@pytest.fixture
def list_alerts_action(integration_id, settings, credentials):
    return _make_action(ListAlertsAction, integration_id, settings, credentials)


@pytest.fixture
def get_alert_action(integration_id, settings, credentials):
    return _make_action(GetAlertAction, integration_id, settings, credentials)


@pytest.fixture
def update_alert_status_action(integration_id, settings, credentials):
    return _make_action(UpdateAlertStatusAction, integration_id, settings, credentials)


@pytest.fixture
def list_secure_scores_action(integration_id, settings, credentials):
    return _make_action(ListSecureScoresAction, integration_id, settings, credentials)


@pytest.fixture
def list_recommendations_action(integration_id, settings, credentials):
    return _make_action(
        ListRecommendationsAction, integration_id, settings, credentials
    )


@pytest.fixture
def get_recommendation_action(integration_id, settings, credentials):
    return _make_action(GetRecommendationAction, integration_id, settings, credentials)


@pytest.fixture
def list_assessments_action(integration_id, settings, credentials):
    return _make_action(ListAssessmentsAction, integration_id, settings, credentials)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _token_response():
    """Create a mock token response."""
    resp = MagicMock()
    resp.json.return_value = {"access_token": "test-token-123"}
    resp.raise_for_status = MagicMock()
    resp.status_code = 200
    return resp


def _json_response(data, status_code=200):
    """Create a mock JSON response."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    resp.status_code = status_code
    return resp


def _http_error_response(status_code, message="error"):
    """Create an httpx.HTTPStatusError for testing."""
    response = MagicMock()
    response.status_code = status_code
    response.text = message
    request = MagicMock()
    return httpx.HTTPStatusError(message=message, request=request, response=response)


# ===================================================================
# HealthCheckAction tests
# ===================================================================


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check lists subscriptions."""
        token_resp = _token_response()
        subs_resp = _json_response(
            {
                "value": [
                    {"subscriptionId": "sub-1", "displayName": "Dev"},
                    {"subscriptionId": "sub-2", "displayName": "Prod"},
                ]
            }
        )

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "test-azure-defender"
        assert result["data"]["healthy"] is True
        assert result["data"]["subscription_count"] == 2
        assert "Dev" in result["data"]["subscriptions"]
        assert "Prod" in result["data"]["subscriptions"]

    @pytest.mark.asyncio
    async def test_health_check_no_subscriptions(self, health_check_action):
        """Test health check with empty subscription list."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["data"]["subscription_count"] == 0

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self, integration_id, settings):
        """Test health check fails with missing credentials."""
        action = _make_action(HealthCheckAction, integration_id, settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert (
            "credentials" in result["error"].lower()
            or "client_id" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_health_check_missing_tenant_id(self, integration_id, credentials):
        """Test health check fails with missing tenant_id."""
        action = _make_action(
            HealthCheckAction,
            integration_id,
            {"subscription_id": "sub-1"},
            credentials,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "tenant_id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_token_failure(self, health_check_action):
        """Test health check when token acquisition fails."""
        health_check_action.http_request = AsyncMock(
            side_effect=_http_error_response(401, "Unauthorized")
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        """Test health check when ARM API returns server error."""
        token_resp = _token_response()

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(500, "Internal")]
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"


# ===================================================================
# ListAlertsAction tests
# ===================================================================


class TestListAlertsAction:
    """Tests for ListAlertsAction."""

    @pytest.mark.asyncio
    async def test_list_alerts_success(self, list_alerts_action):
        """Test listing security alerts."""
        token_resp = _token_response()
        alerts_resp = _json_response(
            {
                "value": [
                    {
                        "id": "/alerts/alert-1",
                        "name": "alert-1",
                        "properties": {"alertType": "VM_MaliciousScript"},
                    },
                    {
                        "id": "/alerts/alert-2",
                        "name": "alert-2",
                        "properties": {"alertType": "Storage_AnomalousAccess"},
                    },
                ]
            }
        )

        list_alerts_action.http_request = AsyncMock(
            side_effect=[token_resp, alerts_resp]
        )

        result = await list_alerts_action.execute(limit=10)

        assert result["status"] == "success"
        assert result["integration_id"] == "test-azure-defender"
        assert result["data"]["total_alerts"] == 2
        assert len(result["data"]["alerts"]) == 2

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, list_alerts_action):
        """Test listing alerts when none exist."""
        token_resp = _token_response()
        alerts_resp = _json_response({"value": []})

        list_alerts_action.http_request = AsyncMock(
            side_effect=[token_resp, alerts_resp]
        )

        result = await list_alerts_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 0
        assert result["data"]["alerts"] == []

    @pytest.mark.asyncio
    async def test_list_alerts_invalid_limit(self, list_alerts_action):
        """Test validation of invalid limit parameter."""
        result = await list_alerts_action.execute(limit=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_alerts_zero_limit(self, list_alerts_action):
        """Test validation of zero limit."""
        result = await list_alerts_action.execute(limit=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_alerts_default_limit(self, list_alerts_action):
        """Test that default limit is applied when not specified."""
        token_resp = _token_response()
        alerts_resp = _json_response({"value": [{"id": "a1"}]})

        list_alerts_action.http_request = AsyncMock(
            side_effect=[token_resp, alerts_resp]
        )

        result = await list_alerts_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 1

    @pytest.mark.asyncio
    async def test_list_alerts_missing_subscription(self, integration_id, credentials):
        """Test error when subscription_id is missing."""
        action = _make_action(
            ListAlertsAction,
            integration_id,
            {"tenant_id": "t1"},
            credentials,
        )

        # Token call succeeds, but subscription_id is missing
        action.http_request = AsyncMock(return_value=_token_response())

        result = await action.execute()

        assert result["status"] == "error"
        assert "subscription_id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_list_alerts_pagination(self, list_alerts_action):
        """Test paginated alert fetching."""
        token_resp = _token_response()
        page1 = _json_response(
            {
                "value": [{"id": "a1"}, {"id": "a2"}],
                "nextLink": "https://management.azure.com/next-page",
            }
        )
        page2 = _json_response(
            {
                "value": [{"id": "a3"}],
            }
        )

        list_alerts_action.http_request = AsyncMock(
            side_effect=[token_resp, page1, page2]
        )

        result = await list_alerts_action.execute(limit=10)

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 3

    @pytest.mark.asyncio
    async def test_list_alerts_pagination_respects_limit(self, list_alerts_action):
        """Test that pagination stops when limit is reached."""
        token_resp = _token_response()
        page1 = _json_response(
            {
                "value": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}],
                "nextLink": "https://management.azure.com/next-page",
            }
        )

        list_alerts_action.http_request = AsyncMock(side_effect=[token_resp, page1])

        result = await list_alerts_action.execute(limit=2)

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 2
        assert len(result["data"]["alerts"]) == 2


# ===================================================================
# GetAlertAction tests
# ===================================================================


class TestGetAlertAction:
    """Tests for GetAlertAction."""

    @pytest.mark.asyncio
    async def test_get_alert_success(self, get_alert_action):
        """Test getting alert details."""
        token_resp = _token_response()
        alert_resp = _json_response(
            {
                "id": "/alerts/alert-1",
                "name": "alert-1",
                "properties": {
                    "alertType": "VM_MaliciousScript",
                    "severity": "High",
                    "status": "Active",
                },
            }
        )

        get_alert_action.http_request = AsyncMock(side_effect=[token_resp, alert_resp])

        result = await get_alert_action.execute(
            alert_name="alert-1", location="centralus"
        )

        assert result["status"] == "success"
        assert result["data"]["name"] == "alert-1"
        assert result["data"]["properties"]["severity"] == "High"

    @pytest.mark.asyncio
    async def test_get_alert_missing_name(self, get_alert_action):
        """Test validation when alert_name is missing."""
        result = await get_alert_action.execute(location="centralus")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "alert_name" in result["error"]

    @pytest.mark.asyncio
    async def test_get_alert_missing_location(self, get_alert_action):
        """Test validation when location is missing."""
        result = await get_alert_action.execute(alert_name="alert-1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "location" in result["error"]

    @pytest.mark.asyncio
    async def test_get_alert_not_found(self, get_alert_action):
        """Test 404 returns success with not_found=True."""
        token_resp = _token_response()

        get_alert_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(404, "Not Found")]
        )

        result = await get_alert_action.execute(
            alert_name="nonexistent", location="centralus"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["alert_name"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_get_alert_server_error(self, get_alert_action):
        """Test 500 returns error result."""
        token_resp = _token_response()

        get_alert_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(500, "Server Error")]
        )

        result = await get_alert_action.execute(
            alert_name="alert-1", location="centralus"
        )

        assert result["status"] == "error"


# ===================================================================
# UpdateAlertStatusAction tests
# ===================================================================


class TestUpdateAlertStatusAction:
    """Tests for UpdateAlertStatusAction."""

    @pytest.mark.asyncio
    async def test_update_alert_status_dismiss(self, update_alert_status_action):
        """Test dismissing an alert."""
        token_resp = _token_response()
        status_resp = _json_response({})  # POST to status endpoint returns 204 / empty

        update_alert_status_action.http_request = AsyncMock(
            side_effect=[token_resp, status_resp]
        )

        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="centralus", status="dismiss"
        )

        assert result["status"] == "success"
        assert result["data"]["new_status"] == "dismiss"
        assert result["data"]["alert_name"] == "alert-1"

    @pytest.mark.asyncio
    async def test_update_alert_status_resolve(self, update_alert_status_action):
        """Test resolving an alert."""
        token_resp = _token_response()
        status_resp = _json_response({})

        update_alert_status_action.http_request = AsyncMock(
            side_effect=[token_resp, status_resp]
        )

        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="eastus", status="resolve"
        )

        assert result["status"] == "success"
        assert result["data"]["new_status"] == "resolve"

    @pytest.mark.asyncio
    async def test_update_alert_status_activate(self, update_alert_status_action):
        """Test activating an alert."""
        token_resp = _token_response()
        status_resp = _json_response({})

        update_alert_status_action.http_request = AsyncMock(
            side_effect=[token_resp, status_resp]
        )

        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="westus2", status="activate"
        )

        assert result["status"] == "success"
        assert result["data"]["new_status"] == "activate"

    @pytest.mark.asyncio
    async def test_update_alert_status_in_progress(self, update_alert_status_action):
        """Test setting alert to inProgress."""
        token_resp = _token_response()
        status_resp = _json_response({})

        update_alert_status_action.http_request = AsyncMock(
            side_effect=[token_resp, status_resp]
        )

        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="centralus", status="inProgress"
        )

        assert result["status"] == "success"
        assert result["data"]["new_status"] == "inProgress"

    @pytest.mark.asyncio
    async def test_update_alert_status_missing_name(self, update_alert_status_action):
        """Test validation when alert_name is missing."""
        result = await update_alert_status_action.execute(
            location="centralus", status="dismiss"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_alert_status_missing_location(
        self, update_alert_status_action
    ):
        """Test validation when location is missing."""
        result = await update_alert_status_action.execute(
            alert_name="alert-1", status="dismiss"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_alert_status_missing_status(self, update_alert_status_action):
        """Test validation when status is missing."""
        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="centralus"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_alert_status_invalid_status(self, update_alert_status_action):
        """Test validation with invalid status value."""
        result = await update_alert_status_action.execute(
            alert_name="alert-1", location="centralus", status="invalid_status"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert (
            "invalid" in result["error"].lower() or "status" in result["error"].lower()
        )


# ===================================================================
# ListSecureScoresAction tests
# ===================================================================


class TestListSecureScoresAction:
    """Tests for ListSecureScoresAction."""

    @pytest.mark.asyncio
    async def test_list_secure_scores_success(self, list_secure_scores_action):
        """Test listing secure scores."""
        token_resp = _token_response()
        scores_resp = _json_response(
            {
                "value": [
                    {
                        "id": "/secureScores/ascScore",
                        "name": "ascScore",
                        "properties": {
                            "score": {"current": 45.5, "max": 100},
                            "displayName": "ASC score",
                        },
                    }
                ]
            }
        )

        list_secure_scores_action.http_request = AsyncMock(
            side_effect=[token_resp, scores_resp]
        )

        result = await list_secure_scores_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_scores"] == 1
        assert result["data"]["scores"][0]["name"] == "ascScore"

    @pytest.mark.asyncio
    async def test_list_secure_scores_empty(self, list_secure_scores_action):
        """Test listing scores when none exist."""
        token_resp = _token_response()
        scores_resp = _json_response({"value": []})

        list_secure_scores_action.http_request = AsyncMock(
            side_effect=[token_resp, scores_resp]
        )

        result = await list_secure_scores_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_scores"] == 0

    @pytest.mark.asyncio
    async def test_list_secure_scores_api_error(self, list_secure_scores_action):
        """Test error handling for secure scores."""
        token_resp = _token_response()

        list_secure_scores_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(403, "Forbidden")]
        )

        result = await list_secure_scores_action.execute()

        assert result["status"] == "error"


# ===================================================================
# ListRecommendationsAction tests
# ===================================================================


class TestListRecommendationsAction:
    """Tests for ListRecommendationsAction."""

    @pytest.mark.asyncio
    async def test_list_recommendations_success(self, list_recommendations_action):
        """Test listing security recommendations."""
        token_resp = _token_response()
        recs_resp = _json_response(
            {
                "value": [
                    {
                        "id": "/recommendations/rec-1",
                        "name": "rec-1",
                        "properties": {
                            "displayName": "Enable MFA for accounts",
                            "status": {"code": "Unhealthy"},
                        },
                    },
                    {
                        "id": "/recommendations/rec-2",
                        "name": "rec-2",
                        "properties": {
                            "displayName": "Encrypt storage accounts",
                            "status": {"code": "Healthy"},
                        },
                    },
                ]
            }
        )

        list_recommendations_action.http_request = AsyncMock(
            side_effect=[token_resp, recs_resp]
        )

        result = await list_recommendations_action.execute(limit=50)

        assert result["status"] == "success"
        assert result["data"]["total_recommendations"] == 2

    @pytest.mark.asyncio
    async def test_list_recommendations_invalid_limit(
        self, list_recommendations_action
    ):
        """Test validation of invalid limit."""
        result = await list_recommendations_action.execute(limit=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_recommendations_api_error(self, list_recommendations_action):
        """Test error handling for recommendations."""
        token_resp = _token_response()

        list_recommendations_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(500, "Server Error")]
        )

        result = await list_recommendations_action.execute()

        assert result["status"] == "error"


# ===================================================================
# GetRecommendationAction tests
# ===================================================================


class TestGetRecommendationAction:
    """Tests for GetRecommendationAction."""

    @pytest.mark.asyncio
    async def test_get_recommendation_success(self, get_recommendation_action):
        """Test getting recommendation details."""
        token_resp = _token_response()
        rec_resp = _json_response(
            {
                "id": "/recommendations/rec-1",
                "name": "rec-1",
                "properties": {
                    "displayName": "Enable MFA for accounts",
                    "description": "Multi-factor authentication should be enabled.",
                    "status": {"code": "Unhealthy"},
                    "resourceDetails": {"source": "Azure"},
                },
            }
        )

        get_recommendation_action.http_request = AsyncMock(
            side_effect=[token_resp, rec_resp]
        )

        result = await get_recommendation_action.execute(recommendation_id="rec-1")

        assert result["status"] == "success"
        assert result["data"]["name"] == "rec-1"

    @pytest.mark.asyncio
    async def test_get_recommendation_missing_id(self, get_recommendation_action):
        """Test validation when recommendation_id is missing."""
        result = await get_recommendation_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "recommendation_id" in result["error"]

    @pytest.mark.asyncio
    async def test_get_recommendation_not_found(self, get_recommendation_action):
        """Test 404 returns success with not_found=True."""
        token_resp = _token_response()

        get_recommendation_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(404, "Not Found")]
        )

        result = await get_recommendation_action.execute(
            recommendation_id="nonexistent"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["recommendation_id"] == "nonexistent"


# ===================================================================
# ListAssessmentsAction tests
# ===================================================================


class TestListAssessmentsAction:
    """Tests for ListAssessmentsAction."""

    @pytest.mark.asyncio
    async def test_list_assessments_success(self, list_assessments_action):
        """Test listing assessments for a resource."""
        resource_id = "/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1"
        token_resp = _token_response()
        assess_resp = _json_response(
            {
                "value": [
                    {
                        "id": f"{resource_id}/providers/Microsoft.Security/assessments/assess-1",
                        "name": "assess-1",
                        "properties": {
                            "displayName": "Disk encryption",
                            "status": {"code": "Unhealthy"},
                        },
                    }
                ]
            }
        )

        list_assessments_action.http_request = AsyncMock(
            side_effect=[token_resp, assess_resp]
        )

        result = await list_assessments_action.execute(
            resource_id=resource_id, limit=50
        )

        assert result["status"] == "success"
        assert result["data"]["resource_id"] == resource_id
        assert result["data"]["total_assessments"] == 1

    @pytest.mark.asyncio
    async def test_list_assessments_missing_resource_id(self, list_assessments_action):
        """Test validation when resource_id is missing."""
        result = await list_assessments_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "resource_id" in result["error"]

    @pytest.mark.asyncio
    async def test_list_assessments_invalid_limit(self, list_assessments_action):
        """Test validation with invalid limit."""
        result = await list_assessments_action.execute(
            resource_id="/sub/1/rg/2", limit=0
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_assessments_api_error(self, list_assessments_action):
        """Test error handling for assessments."""
        token_resp = _token_response()

        list_assessments_action.http_request = AsyncMock(
            side_effect=[token_resp, _http_error_response(500, "Server Error")]
        )

        result = await list_assessments_action.execute(resource_id="/sub/1/rg/2")

        assert result["status"] == "error"


# ===================================================================
# Base class / token acquisition tests
# ===================================================================


class TestTokenAcquisition:
    """Tests for shared OAuth2 token acquisition in _AzureDefenderBase."""

    @pytest.mark.asyncio
    async def test_token_request_payload(self, health_check_action):
        """Verify the token request is sent with correct OAuth2 parameters."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        await health_check_action.execute()

        # First call should be the token request
        token_call = health_check_action.http_request.call_args_list[0]
        assert "login.microsoftonline.com" in token_call.args[0]
        assert token_call.kwargs["method"] == "POST"
        assert token_call.kwargs["data"]["grant_type"] == "client_credentials"
        assert token_call.kwargs["data"]["client_id"] == "test-client-id"
        assert (
            token_call.kwargs["data"]["scope"]
            == "https://management.azure.com/.default"
        )

    @pytest.mark.asyncio
    async def test_token_url_contains_tenant_id(self, health_check_action):
        """Verify tenant_id is embedded in the token URL."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        await health_check_action.execute()

        token_url = health_check_action.http_request.call_args_list[0].args[0]
        assert "test-tenant-id" in token_url

    @pytest.mark.asyncio
    async def test_arm_request_uses_bearer_token(self, health_check_action):
        """Verify ARM requests include the Bearer token header."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        await health_check_action.execute()

        # Second call is the ARM request
        arm_call = health_check_action.http_request.call_args_list[1]
        assert arm_call.kwargs["headers"]["Authorization"] == "Bearer test-token-123"

    @pytest.mark.asyncio
    async def test_arm_request_includes_api_version(self, health_check_action):
        """Verify ARM requests include api-version query parameter."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        await health_check_action.execute()

        arm_call = health_check_action.http_request.call_args_list[1]
        assert "api-version" in arm_call.kwargs["params"]

    @pytest.mark.asyncio
    async def test_token_invalid_response(self, health_check_action):
        """Test handling of token response missing access_token field."""
        bad_token_resp = _json_response({"error": "invalid_client"})

        health_check_action.http_request = AsyncMock(return_value=bad_token_resp)

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert (
            "token" in result["error"].lower()
            or "access_token" in result["error"].lower()
        )


# ===================================================================
# Result envelope tests
# ===================================================================


class TestResultEnvelope:
    """Verify all actions produce results with the standard envelope fields."""

    @pytest.mark.asyncio
    async def test_success_result_has_envelope(self, health_check_action):
        """Success results must have integration_id, action_id, timestamp."""
        token_resp = _token_response()
        subs_resp = _json_response({"value": []})

        health_check_action.http_request = AsyncMock(
            side_effect=[token_resp, subs_resp]
        )

        result = await health_check_action.execute()

        assert "integration_id" in result
        assert "action_id" in result
        assert "timestamp" in result
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_error_result_has_envelope(self, list_alerts_action):
        """Error results must have integration_id, action_id, error_type."""
        result = await list_alerts_action.execute(limit=-1)

        assert "integration_id" in result
        assert "action_id" in result
        assert "timestamp" in result
        assert "error_type" in result
        assert result["status"] == "error"
