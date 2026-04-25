"""Unit tests for backend API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import HTTPStatusError, Response

from analysi.integrations.backend_api_client import BackendAPIClient


class TestBackendAPIClientInitialization:
    """Test BackendAPIClient initialization."""

    @patch(
        "analysi.integrations.config.IntegrationConfig.API_BASE_URL",
        "http://test-api:8000",
    )
    @patch(
        "analysi.integrations.config.IntegrationConfig.API_AUTH_TOKEN",
        "test-token-123",
    )
    def test_initialization_from_environment(self):
        """Test BackendAPIClient initialization from environment variables."""
        client = BackendAPIClient(tenant_id="test-tenant")

        assert client.base_url == "http://test-api:8000"
        assert client.tenant_id == "test-tenant"
        assert client.auth_token == "test-token-123"

    @patch(
        "analysi.integrations.config.IntegrationConfig.API_BASE_URL",
        "http://api:8000",
    )
    @patch("analysi.integrations.config.IntegrationConfig.API_AUTH_TOKEN", None)
    def test_initialization_with_defaults(self):
        """Test BackendAPIClient uses default values when env vars not set."""
        client = BackendAPIClient(tenant_id="test-tenant")

        assert client.base_url == "http://api:8000"
        assert client.tenant_id == "test-tenant"
        assert client.auth_token is None

    def test_initialization_with_custom_config(self):
        """Test BackendAPIClient with custom configuration."""
        client = BackendAPIClient(
            tenant_id="custom-tenant",
            base_url="http://custom-api:9000",
            auth_token="custom-token",
        )

        assert client.base_url == "http://custom-api:9000"
        assert client.tenant_id == "custom-tenant"
        assert client.auth_token == "custom-token"


class TestPostAlerts:
    """Test posting alerts to backend API."""

    @pytest.mark.asyncio
    async def test_successful_alert_post(self):
        """Test successful alert POST (mock 201 response)."""
        client = BackendAPIClient(tenant_id="test-tenant", base_url="http://api:8000")

        mock_alert_response = MagicMock(spec=Response)
        mock_alert_response.status_code = 201
        mock_alert_response.json.return_value = {"alert_id": "test-id"}

        mock_analysis_response = MagicMock(spec=Response)
        mock_analysis_response.status_code = 202

        # Each alert creation triggers 2 calls: create + analyze
        responses = [
            mock_alert_response,  # Alert 1 create
            mock_analysis_response,  # Alert 1 analyze
            mock_alert_response,  # Alert 2 create
            mock_analysis_response,  # Alert 2 analyze
        ]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            alerts = [
                {"title": "Alert 1", "severity": "high"},
                {"title": "Alert 2", "severity": "medium"},
            ]

            result = await client.post_alerts(alerts)

            # API should be called twice per alert (4 times total: 2 creates + 2 analyses)
            assert mock_post.call_count == 4

            # Check first alert creation call
            first_call = mock_post.call_args_list[0]
            assert "/v1/test-tenant/alerts" in first_call[0][0]
            assert first_call[1]["json"] == {"title": "Alert 1", "severity": "high"}

            # Check first alert analysis call
            second_call = mock_post.call_args_list[1]
            assert "/alerts/test-id/analyze" in second_call[0][0]

            # Check second alert creation call
            third_call = mock_post.call_args_list[2]
            assert "/v1/test-tenant/alerts" in third_call[0][0]
            assert third_call[1]["json"] == {"title": "Alert 2", "severity": "medium"}

            # Check second alert analysis call
            fourth_call = mock_post.call_args_list[3]
            assert "/alerts/test-id/analyze" in fourth_call[0][0]

            # Verify result
            assert result["created"] == 2
            assert result["duplicates"] == 0

    @pytest.mark.asyncio
    async def test_duplicate_handling(self):
        """Test duplicate handling (mock 409 response)."""
        client = BackendAPIClient(tenant_id="test-tenant")

        # Setup responses for alert creation
        mock_created = MagicMock(spec=Response, status_code=201)
        mock_created.json.return_value = {"alert_id": "test-id"}
        mock_analysis = MagicMock(spec=Response, status_code=202)
        mock_duplicate = MagicMock(spec=Response, status_code=409)

        # First alert: 201 (created) + 202 (analysis), second alert: 409 (duplicate)
        mock_responses = [
            mock_created,  # First alert created
            mock_analysis,  # First alert analysis triggered
            mock_duplicate,  # Second alert is duplicate
        ]

        with patch("httpx.AsyncClient.post", side_effect=mock_responses) as mock_post:
            alerts = [
                {"title": "New Alert", "severity": "high"},
                {"title": "Duplicate Alert", "severity": "medium"},
            ]

            result = await client.post_alerts(alerts)

            # Should handle 409 gracefully
            assert result["created"] == 1
            assert result["duplicates"] == 1
            # 3 calls: create alert 1, analyze alert 1, try to create alert 2 (duplicate)
            assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_error_handling_500(self):
        """Test error handling for 500 server error."""
        client = BackendAPIClient(tenant_id="test-tenant")

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 500

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            alerts = [{"title": "Alert", "severity": "high"}]

            # API client doesn't raise, it returns errors in result
            result = await client.post_alerts(alerts)

            assert result["created"] == 0
            assert result["duplicates"] == 0
            assert "errors" in result

    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test handling of network errors."""
        client = BackendAPIClient(tenant_id="test-tenant")

        with patch("httpx.AsyncClient.post", side_effect=Exception("Network error")):
            alerts = [{"title": "Alert", "severity": "high"}]

            # API client catches exceptions and returns them in errors
            result = await client.post_alerts(alerts)

            assert result["created"] == 0
            assert result["duplicates"] == 0
            assert "errors" in result
            assert "Network error" in str(result["errors"][0])

    @pytest.mark.asyncio
    async def test_authentication_header_inclusion(self):
        """Test authentication header inclusion when configured."""
        client = BackendAPIClient(
            tenant_id="test-tenant", auth_token="bearer-token-123"
        )

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"created": 1}

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            await client.post_alerts([{"title": "Alert"}])

            # Verify auth header was included (system API key, not Bearer JWT)
            call_headers = mock_post.call_args[1]["headers"]
            assert call_headers["X-API-Key"] == "bearer-token-123"
            # Tenant is in URL, not headers
            assert "/v1/test-tenant/alerts" in mock_post.call_args[0][0]


class TestAPIClientErrorHandling:
    """Test specific error handling methods."""

    @pytest.mark.asyncio
    async def test_handle_409_duplicates(self):
        """Test _handle_409 method for duplicate handling."""
        client = BackendAPIClient(tenant_id="test-tenant")

        response_data = {
            "created": 5,
            "duplicates": 3,
            "duplicate_ids": ["id1", "id2", "id3"],
        }

        result = client._handle_409(response_data)

        assert result["created"] == 5
        assert result["duplicates"] == 3
        assert len(result["duplicate_ids"]) == 3

    @pytest.mark.asyncio
    async def test_handle_error_logging(self):
        """Test _handle_error method logs errors appropriately."""
        client = BackendAPIClient(tenant_id="test-tenant")

        # Create error with status_code and text attributes
        error = MagicMock()
        error.status_code = 400
        error.text = "Invalid payload"

        with patch("analysi.integrations.backend_api_client.logger") as mock_logger:
            client._handle_error(error)

            # Should log the error with status code and text as kwargs
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            assert call_args[0][0] == "api_error"
            assert call_args[1]["status_code"] == 400
            assert call_args[1]["text"] == "Invalid payload"


class TestRetryLogic:
    """Test retry logic for failed requests."""

    @pytest.mark.asyncio
    async def test_retry_on_temporary_failure(self):
        """Test retry logic with exponential backoff."""
        client = BackendAPIClient(
            tenant_id="test-tenant", base_url="http://test-api:8000"
        )

        # Create mock responses - first two fail with 504, third succeeds
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # First two calls fail with server error
                response = MagicMock()
                response.status_code = 504
                response.is_server_error = True
                response.raise_for_status = MagicMock(
                    side_effect=HTTPStatusError(
                        "Timeout", request=MagicMock(), response=response
                    )
                )
                return response
            # Third call succeeds
            response = MagicMock()
            response.status_code = 201
            response.is_server_error = False
            response.json = MagicMock(return_value={"created": 1})
            return response

        with patch(
            "analysi.integrations.backend_api_client.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep") as mock_sleep:  # Skip actual sleep in tests
                result = await client.post_alerts([{"title": "Alert"}], retry_count=3)

                # Should have retried twice
                assert mock_sleep.call_count == 2  # Two retries
                assert result["created"] == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self):
        """Test no retry on 4xx client errors."""
        client = BackendAPIClient(tenant_id="test-tenant")

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 400

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            with patch(
                "asyncio.sleep", return_value=None
            ):  # Skip actual sleep in tests
                result = await client.post_alerts([{"title": "Alert"}], retry_count=3)

                # Should not retry on 400 error (client error)
                assert mock_post.call_count == 1  # No retries
                assert result["created"] == 0
                assert "errors" in result


class TestTenantAwareness:
    """Test tenant-aware API calls."""

    @pytest.mark.asyncio
    async def test_tenant_in_url(self):
        """Test tenant ID is included in URL path."""
        tenants = ["default", "customer-1", "customer-2"]

        for tenant in tenants:
            client = BackendAPIClient(tenant_id=tenant)

            mock_response = MagicMock(spec=Response)
            mock_response.status_code = 201
            mock_response.json.return_value = {"created": 1}

            with patch(
                "httpx.AsyncClient.post", return_value=mock_response
            ) as mock_post:
                await client.post_alerts([{"title": "Alert"}])

                # Tenant should be in URL, not headers
                url = mock_post.call_args[0][0]
                assert f"/v1/{tenant}/alerts" in url
