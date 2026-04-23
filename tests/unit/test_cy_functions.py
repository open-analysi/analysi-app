"""
Unit tests for CyArtifactFunctions.

Tests Cy native functions implementation.
"""

from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest

from analysi.services.artifact_service import ArtifactService
from analysi.services.cy_functions import (
    CyArtifactFunctions,
    create_cy_artifact_functions,
)


@pytest.fixture
def mock_artifact_service():
    """Mock ArtifactService for testing."""
    service = Mock(spec=ArtifactService)

    # Create a mock artifact object with a proper UUID
    mock_artifact = Mock()
    mock_artifact.id = uuid4()

    service.create_artifact = AsyncMock(return_value=mock_artifact)
    return service


@pytest.fixture
def execution_context():
    """Mock execution context for Cy functions."""
    return {
        "tenant_id": "test-tenant",
        "task_id": str(uuid4()),
        "task_run_id": str(uuid4()),
        "workflow_id": None,
        "workflow_run_id": None,
        "workflow_node_instance_id": None,
        "analysis_id": None,
    }


@pytest.fixture
def cy_functions(mock_artifact_service, execution_context):
    """CyArtifactFunctions instance with mocked dependencies."""
    return CyArtifactFunctions(mock_artifact_service, execution_context)


@pytest.mark.unit
class TestCyArtifactFunctions:
    """Test suite for Cy native functions."""

    def test_cy_artifact_functions_init(self, mock_artifact_service, execution_context):
        """Test CyArtifactFunctions initialization."""
        cy_functions = CyArtifactFunctions(mock_artifact_service, execution_context)

        assert cy_functions.artifact_service == mock_artifact_service
        assert cy_functions.execution_context == execution_context

    @pytest.mark.asyncio
    async def test_store_artifact_with_string_content(self, cy_functions, httpx_mock):
        """Test store_artifact with string content."""
        name = "Timeline Analysis"
        artifact_content = "Timeline events: login at 10:00, logout at 11:30"
        tags = {"type": "timeline", "source": "auth_system"}
        artifact_type = "timeline"

        test_artifact_id = str(uuid4())
        # Mock successful HTTP response
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8001/v1/test-tenant/artifacts",
            status_code=201,
            json={"id": test_artifact_id},
        )

        artifact_id = await cy_functions.store_artifact(
            name, artifact_content, tags, artifact_type
        )

        # Should return a valid UUID string
        assert isinstance(artifact_id, str)
        assert UUID(artifact_id)  # Validates it's a proper UUID
        assert artifact_id == test_artifact_id

    @pytest.mark.asyncio
    async def test_store_artifact_with_bytes_content(self, cy_functions, httpx_mock):
        """Test store_artifact with binary content."""
        name = "Binary Log File"
        artifact_content = b"Binary log data\x00\x01\x02"
        tags = {"format": "binary", "source": "system_log"}
        artifact_type = "log_file"

        test_artifact_id = str(uuid4())
        # Mock successful HTTP response
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8001/v1/test-tenant/artifacts",
            status_code=201,
            json={"id": test_artifact_id},
        )

        artifact_id = await cy_functions.store_artifact(
            name, artifact_content, tags, artifact_type
        )

        # Should return a valid UUID string
        assert isinstance(artifact_id, str)
        assert UUID(artifact_id)
        assert artifact_id == test_artifact_id

    @pytest.mark.asyncio
    async def test_store_artifact_with_dict_content(self, cy_functions, httpx_mock):
        """Test store_artifact with dictionary content."""
        name = "Activity Graph"
        artifact_content = {
            "nodes": [
                {"id": "user1", "type": "user"},
                {"id": "server1", "type": "server"},
            ],
            "edges": [{"from": "user1", "to": "server1", "relation": "connects_from"}],
        }
        tags = {"type": "graph", "format": "json"}
        artifact_type = "activity_graph"

        test_artifact_id = str(uuid4())
        # Mock successful HTTP response
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8001/v1/test-tenant/artifacts",
            status_code=201,
            json={"id": test_artifact_id},
        )

        artifact_id = await cy_functions.store_artifact(
            name, artifact_content, tags, artifact_type
        )

        # Should return a valid UUID string
        assert isinstance(artifact_id, str)
        assert UUID(artifact_id)
        assert artifact_id == test_artifact_id

    @pytest.mark.asyncio
    async def test_store_artifact_without_tags(self, cy_functions, httpx_mock):
        """Test store_artifact without tags parameter."""
        name = "Simple Artifact"
        artifact_content = "Simple content without tags"

        test_artifact_id = str(uuid4())
        # Mock successful HTTP response
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8001/v1/test-tenant/artifacts",
            status_code=201,
            json={"id": test_artifact_id},
        )

        artifact_id = await cy_functions.store_artifact(name, artifact_content)

        # Should return a valid UUID string
        assert isinstance(artifact_id, str)
        assert UUID(artifact_id)
        assert artifact_id == test_artifact_id

    def test_content_preparation_string(self, cy_functions):
        """Test content preparation for string content."""
        content = "test string"
        result = cy_functions._prepare_content_for_storage(content)

        assert result == "test string"
        assert isinstance(result, str)

    def test_content_preparation_dict(self, cy_functions):
        """Test content preparation for dict content."""
        content = {"key": "value", "number": 42}
        result = cy_functions._prepare_content_for_storage(content)

        # Should be JSON encoded
        assert result == '{"key": "value", "number": 42}'
        assert isinstance(result, str)

    def test_content_preparation_bytes(self, cy_functions):
        """Test content preparation for bytes content."""
        content = b"binary data"
        result = cy_functions._prepare_content_for_storage(content)

        assert result == b"binary data"
        assert isinstance(result, bytes)

    def test_tags_conversion_dict(self, cy_functions):
        """Test tags conversion from dict to list."""
        tags = {"type": "test", "priority": "high"}
        result = cy_functions._convert_tags_to_list(tags)

        assert result == ["type:test", "priority:high"]

    def test_tags_conversion_none(self, cy_functions):
        """Test tags conversion from None."""
        tags = None
        result = cy_functions._convert_tags_to_list(tags)

        assert result == []

    def test_tags_conversion_list(self, cy_functions):
        """Test tags conversion from list."""
        tags = ["tag1", "tag2", 123]
        result = cy_functions._convert_tags_to_list(tags)

        assert result == ["tag1", "tag2", "123"]

    def test_execution_context_propagation(self, execution_context):
        """Test that execution context is properly propagated."""
        mock_service = Mock(spec=ArtifactService)
        cy_functions = CyArtifactFunctions(mock_service, execution_context)

        # Test that context is accessible
        context = cy_functions._get_execution_context()
        assert context["tenant_id"] == "test-tenant"
        assert context["task_id"] == execution_context["task_id"]
        assert context["task_run_id"] == execution_context["task_run_id"]


class TestCreateCyArtifactFunctions:
    """Test suite for create_cy_artifact_functions factory."""

    def test_created_function_callable(self, mock_artifact_service, execution_context):
        """Test that created functions are callable."""
        functions = create_cy_artifact_functions(
            mock_artifact_service, execution_context
        )

        assert "store_artifact" in functions
        assert callable(functions["store_artifact"])

    def test_function_signature_compatibility(
        self, mock_artifact_service, execution_context
    ):
        """Test that function signatures are Cy-compatible."""
        functions = create_cy_artifact_functions(
            mock_artifact_service, execution_context
        )
        store_func = functions["store_artifact"]

        # Note: These tests will fail because the function now calls REST API
        # But we can test that the function exists and has the right signature
        import inspect

        sig = inspect.signature(store_func)

        # Check function parameters
        params = list(sig.parameters.keys())
        assert "name" in params
        assert "artifact" in params
        assert "tags" in params
        assert "artifact_type" in params


class TestCyArtifactFunctionsSifnosEnvelope:
    """Test store_artifact works with Sifnos {data, meta} envelope responses."""

    @pytest.mark.asyncio
    async def test_store_artifact_handles_envelope_response(
        self, cy_functions, httpx_mock
    ):
        """Test store_artifact extracts ID from Sifnos envelope.

        The artifacts API returns {data: {id: ...}, meta: {...}} but
        the code must extract the id correctly regardless.
        """
        test_artifact_id = str(uuid4())
        # Mock response with Sifnos envelope (what the real API returns)
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8001/v1/test-tenant/artifacts",
            status_code=201,
            json={
                "data": {"id": test_artifact_id, "name": "Test"},
                "meta": {"request_id": "abc-123"},
            },
        )

        artifact_id = await cy_functions.store_artifact("Test Artifact", "test content")

        assert artifact_id == test_artifact_id


class TestCyArtifactFunctionsErrorHandling:
    """Test suite for HTTP error handling in cy_functions.

    http_retry_policy retries transient errors (network errors, 5xx, 429)
    up to 3 times.  Each test registers enough responses/exceptions for all
    retry attempts and patches the wait to be instantaneous.
    """

    @pytest.fixture(autouse=True)
    def _instant_retry(self):
        """Patch retry wait to avoid exponential backoff in tests."""
        from tenacity import wait_none

        from analysi.services.cy_functions import CyArtifactFunctions

        method = CyArtifactFunctions._create_artifact_via_async_api
        original_wait = method.retry.wait
        method.retry.wait = wait_none()
        yield
        method.retry.wait = original_wait

    @pytest.mark.asyncio
    async def test_store_artifact_timeout_error(self, cy_functions, httpx_mock):
        """Test store_artifact handling of HTTP timeout errors."""
        name = "Timeline Analysis"
        artifact_content = "Timeline events for timeout test"

        # Register exceptions for all 3 retry attempts
        for _ in range(3):
            httpx_mock.add_exception(httpx.TimeoutException("Request timed out"))

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_connection_error(self, cy_functions, httpx_mock):
        """Test store_artifact handling of HTTP connection errors."""
        name = "Connection Test"
        artifact_content = "Content for connection test"

        # Register exceptions for all 3 retry attempts
        for _ in range(3):
            httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_request_error(self, cy_functions, httpx_mock):
        """Test store_artifact handling of general HTTP request errors."""
        name = "Request Error Test"
        artifact_content = "Content for request error test"

        # Register exceptions for all 3 retry attempts
        for _ in range(3):
            httpx_mock.add_exception(httpx.RequestError("Network error occurred"))

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_api_server_error_500(self, cy_functions, httpx_mock):
        """Test store_artifact handling of API server errors (500)."""
        name = "Server Error Test"
        artifact_content = "Content for server error test"

        # Register responses for all 3 retry attempts
        for _ in range(3):
            httpx_mock.add_response(status_code=500, text="Internal Server Error")

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_api_client_error_400(self, cy_functions, httpx_mock):
        """Test store_artifact handling of API client errors (400)."""
        name = "Client Error Test"
        artifact_content = "Content for client error test"

        # Mock HTTP client error response
        httpx_mock.add_response(status_code=400, text="Bad Request - invalid payload")

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_api_unauthorized_403(self, cy_functions, httpx_mock):
        """Test store_artifact handling of API authorization errors (403)."""
        name = "Auth Error Test"
        artifact_content = "Content for auth error test"

        # Mock HTTP unauthorized response
        httpx_mock.add_response(
            status_code=403, text="Forbidden - tenant access denied"
        )

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)

    @pytest.mark.asyncio
    async def test_store_artifact_api_rate_limit_429(self, cy_functions, httpx_mock):
        """Test store_artifact handling of API rate limiting (429)."""
        name = "Rate Limit Test"
        artifact_content = "Content for rate limit test"

        # Register responses for all 3 retry attempts
        for _ in range(3):
            httpx_mock.add_response(
                status_code=429, text="Too Many Requests - rate limit exceeded"
            )

        with pytest.raises(RuntimeError, match="Failed to store artifact"):
            await cy_functions.store_artifact(name, artifact_content)
