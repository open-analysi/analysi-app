"""Unit tests for request/response logging middleware."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from analysi.middleware.logging import (
    RequestLoggingMiddleware,
    generate_correlation_id,
    get_request_body_info,
)


class TestRequestLoggingMiddleware:
    """Test RequestLoggingMiddleware."""

    def test_middleware_initialization(self):
        """Test middleware can be initialized."""
        app = FastAPI()
        middleware = RequestLoggingMiddleware(app)
        assert middleware is not None

    @pytest.mark.asyncio
    async def test_dispatch_adds_correlation_id(self):
        """Test middleware adds correlation ID to request state."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/test")
        @pytest.mark.asyncio
        async def test_endpoint(request: Request):
            # Should have correlation ID in request state
            assert hasattr(request.state, "correlation_id")
            correlation_id = request.state.correlation_id
            assert isinstance(correlation_id, str)
            # Should be valid UUID
            uuid.UUID(correlation_id)
            return {"status": "ok"}

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            # Should have correlation ID in response headers
            assert "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_dispatch_logs_request_and_response(
        self,
    ):
        """Test middleware logs request and response information."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/test")
        @pytest.mark.asyncio
        async def test_endpoint():
            return {"message": "success"}

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            # Response should include correlation ID
            assert "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_dispatch_handles_exceptions(self):
        """Test middleware handles exceptions during logging."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/test")
        @pytest.mark.asyncio
        async def test_endpoint():
            raise ValueError("Test error")

        with TestClient(app) as client:
            # Should log the error and then re-raise it
            with pytest.raises(ValueError, match="Test error"):
                client.get("/test")


class TestGenerateCorrelationId:
    """Test generate_correlation_id function."""

    def test_generate_correlation_id_format(self):
        """Test correlation ID is valid UUID format."""
        correlation_id = generate_correlation_id()

        # Should be valid UUID
        assert isinstance(correlation_id, str)
        uuid_obj = uuid.UUID(correlation_id)
        assert str(uuid_obj) == correlation_id

    def test_generate_correlation_id_uniqueness(self):
        """Test correlation IDs are unique."""
        ids = [generate_correlation_id() for _ in range(100)]

        # All IDs should be unique
        assert len(set(ids)) == 100


class TestGetRequestBodyInfo:
    """Test get_request_body_info function."""

    def test_get_request_body_info_safe_data(self):
        """Test extracting safe information from request body."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {"content-type": "application/json"}
        mock_request.query_params = {}

        info = get_request_body_info(mock_request)
        assert isinstance(info, dict)
        assert info["method"] == "GET"
        assert info["content_type"] == "application/json"

    def test_get_request_body_info_filters_sensitive(self):
        """Test that sensitive data is filtered from request info."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {
            "authorization": "Bearer token123",
            "content-type": "application/json",
            "x-api-key": "secret",
        }
        mock_request.query_params = {"password": "secret123", "username": "testuser"}

        info = get_request_body_info(mock_request)

        # Sensitive headers should be masked
        assert info["headers"]["authorization"] == "***"
        assert info["headers"]["x-api-key"] == "***"
        assert info["headers"]["content-type"] == "application/json"

        # Sensitive query params should be masked
        assert info["query_params"]["password"] == "***"
        assert info["query_params"]["username"] == "testuser"

    def test_get_request_body_info_preserves_safe_data(self):
        """Test that safe data is preserved in request info."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {
            "user-agent": "test-client",
            "accept": "application/json",
        }
        mock_request.query_params = {"page": "1", "limit": "10"}

        info = get_request_body_info(mock_request)

        # Safe data should be preserved
        assert info["headers"]["user-agent"] == "test-client"
        assert info["headers"]["accept"] == "application/json"
        assert info["query_params"]["page"] == "1"
        assert info["query_params"]["limit"] == "10"

    def test_get_request_body_info_handles_large_bodies(self):
        """Test that large request bodies are truncated."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"content-length": "5000"}
        mock_request.query_params = {"data": "x" * 200}  # Long parameter

        info = get_request_body_info(mock_request)

        # Long parameters should be truncated
        assert len(info["query_params"]["data"]) <= 100
        assert info["query_params"]["data"].endswith("...")

    def test_get_request_body_info_handles_malformed_data(self):
        """Test that malformed request data doesn't break logging."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"content-length": "invalid"}
        mock_request.query_params = {}

        info = get_request_body_info(mock_request)

        # Should not have content_length if parsing failed
        assert "content_length" not in info
        assert info["method"] == "POST"
