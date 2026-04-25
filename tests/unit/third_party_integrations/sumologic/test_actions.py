"""Unit tests for Sumo Logic integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.sumologic.actions import (
    DeleteJobAction,
    GetResultsAction,
    HealthCheckAction,
    RunQueryAction,
)


@pytest.fixture
def mock_credentials():
    """Mock credentials for Sumo Logic."""
    return {
        "access_id": "test_access_id",
        "access_key": "test_access_key",
    }


@pytest.fixture
def mock_settings():
    """Mock settings for Sumo Logic."""
    return {
        "environment": "us1",
        "timezone": "UTC",
    }


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    action = HealthCheckAction(
        integration_id="test-sumologic",
        action_id="health_check",
        credentials=mock_credentials,
        settings=mock_settings,
    )
    return action


@pytest.fixture
def run_query_action(mock_credentials, mock_settings):
    """Create RunQueryAction instance."""
    action = RunQueryAction(
        integration_id="test-sumologic",
        action_id="run_query",
        credentials=mock_credentials,
        settings=mock_settings,
    )
    return action


@pytest.fixture
def get_results_action(mock_credentials, mock_settings):
    """Create GetResultsAction instance."""
    action = GetResultsAction(
        integration_id="test-sumologic",
        action_id="get_results",
        credentials=mock_credentials,
        settings=mock_settings,
    )
    return action


@pytest.fixture
def delete_job_action(mock_credentials, mock_settings):
    """Create DeleteJobAction instance."""
    action = DeleteJobAction(
        integration_id="test-sumologic",
        action_id="delete_job",
        credentials=mock_credentials,
        settings=mock_settings,
    )
    return action


# HealthCheckAction Tests


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"collectors": []}

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert "Connection to Sumo Logic API successful" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials(mock_settings):
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="test-sumologic",
        action_id="health_check",
        credentials={},
        settings=mock_settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_environment(mock_credentials):
    """Test health check with missing environment."""
    action = HealthCheckAction(
        integration_id="test-sumologic",
        action_id="health_check",
        credentials=mock_credentials,
        settings={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required environment" in result["error"]


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 401

    health_check_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"


# RunQueryAction Tests


@pytest.mark.asyncio
async def test_run_query_success(run_query_action):
    """Test successful query execution with completed job."""
    # Mock search job creation
    mock_create_response = MagicMock()
    mock_create_response.raise_for_status = MagicMock()
    mock_create_response.json.return_value = {"id": "test-job-123"}

    # Mock job status (done)
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "DONE GATHERING RESULTS"}

    # Mock results
    mock_results_response = MagicMock()
    mock_results_response.raise_for_status = MagicMock()
    mock_results_response.json.return_value = {
        "messages": [
            {"map": {"_raw": "test message 1"}},
            {"map": {"_raw": "test message 2"}},
        ]
    }

    # Sequence: create job -> poll status -> get results
    run_query_action.http_request = AsyncMock(
        side_effect=[mock_create_response, mock_status_response, mock_results_response]
    )
    result = await run_query_action.execute(query="*")

    assert result["status"] == "success"
    assert result["search_id"] == "test-job-123"
    assert result["total_objects"] == 2
    assert "data" in result


@pytest.mark.asyncio
async def test_run_query_missing_query(run_query_action):
    """Test run query with missing query parameter."""
    result = await run_query_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'query'" in result["error"]


@pytest.mark.asyncio
async def test_run_query_timeout(run_query_action):
    """Test run query with job timeout."""
    # Mock search job creation
    mock_create_response = MagicMock()
    mock_create_response.raise_for_status = MagicMock()
    mock_create_response.json.return_value = {"id": "test-job-123"}

    # Mock job status (not done) - will trigger timeout
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "GATHERING RESULTS"}

    # First call: create job returns mock_create_response
    # Subsequent calls: poll status returns GATHERING RESULTS (not done)
    run_query_action.http_request = AsyncMock(
        side_effect=[
            mock_create_response,
            mock_status_response,
            mock_status_response,
            mock_status_response,
        ]
    )
    # Patch polling timeout to be very short and mock asyncio.sleep
    with (
        patch(
            "analysi.integrations.framework.integrations.sumologic.actions.POLLING_MAX_TIME",
            0.1,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await run_query_action.execute(query="*")

    assert result["status"] == "success"
    assert result["search_id"] == "test-job-123"
    assert "not completed" in result.get("message", "")


@pytest.mark.asyncio
async def test_run_query_zero_time_range(run_query_action):
    """Test run query with zero time range."""
    result = await run_query_action.execute(query="*", from_time=0)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Time range cannot start or end with zero" in result["error"]


@pytest.mark.asyncio
async def test_run_query_records_type(run_query_action):
    """Test run query with records response type."""
    # Mock search job creation
    mock_create_response = MagicMock()
    mock_create_response.raise_for_status = MagicMock()
    mock_create_response.json.return_value = {"id": "test-job-123"}

    # Mock job status (done)
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "DONE GATHERING RESULTS"}

    # Mock results
    mock_results_response = MagicMock()
    mock_results_response.raise_for_status = MagicMock()
    mock_results_response.json.return_value = {
        "records": [
            {"count": "10"},
            {"count": "20"},
        ]
    }

    # Sequence: create job -> poll status -> get results
    run_query_action.http_request = AsyncMock(
        side_effect=[mock_create_response, mock_status_response, mock_results_response]
    )
    result = await run_query_action.execute(query="* | count", type="records")

    assert result["status"] == "success"
    assert result["total_objects"] == 2


@pytest.mark.asyncio
async def test_run_query_job_cancelled(run_query_action):
    """Test run query with cancelled job."""
    # Mock search job creation
    mock_create_response = MagicMock()
    mock_create_response.raise_for_status = MagicMock()
    mock_create_response.json.return_value = {"id": "test-job-123"}

    # Mock job status (cancelled)
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "CANCELLED"}

    # First call: create job; second call: poll returns CANCELLED
    run_query_action.http_request = AsyncMock(
        side_effect=[mock_create_response, mock_status_response]
    )
    result = await run_query_action.execute(query="*")

    assert result["status"] == "error"
    assert result["error_type"] == "SearchJobError"
    assert "cancelled" in result["error"]


# GetResultsAction Tests


@pytest.mark.asyncio
async def test_get_results_success(get_results_action):
    """Test successful get results."""
    # Mock job status (done)
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "DONE GATHERING RESULTS"}

    # Mock results
    mock_results_response = MagicMock()
    mock_results_response.raise_for_status = MagicMock()
    mock_results_response.json.return_value = {
        "messages": [
            {"map": {"_raw": "test message"}},
        ]
    }

    get_results_action.http_request = AsyncMock(
        side_effect=[mock_status_response, mock_results_response]
    )
    result = await get_results_action.execute(search_id="test-job-123")

    assert result["status"] == "success"
    assert result["search_id"] == "test-job-123"
    assert result["total_objects"] == 1
    assert "data" in result


@pytest.mark.asyncio
async def test_get_results_missing_search_id(get_results_action):
    """Test get results with missing search_id parameter."""
    result = await get_results_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'search_id'" in result["error"]


@pytest.mark.asyncio
async def test_get_results_not_found(get_results_action):
    """Test get results with invalid search_id."""
    from httpx import HTTPStatusError, Request, Response

    mock_response = Response(status_code=404, request=Request("GET", "http://test"))
    get_results_action.http_request = AsyncMock(
        side_effect=HTTPStatusError(
            "Not found", request=mock_response.request, response=mock_response
        )
    )
    result = await get_results_action.execute(search_id="invalid-job")

    assert result["status"] == "error"
    assert result["error_type"] == "NotFoundError"
    assert "Invalid or expired search job ID" in result["error"]


@pytest.mark.asyncio
async def test_get_results_job_not_done_then_timeout(get_results_action):
    """Test get results when job is not done and times out."""
    # Mock job status (not done)
    mock_status_response = MagicMock()
    mock_status_response.raise_for_status = MagicMock()
    mock_status_response.json.return_value = {"state": "GATHERING RESULTS"}

    get_results_action.http_request = AsyncMock(return_value=mock_status_response)
    # Patch polling timeout to be very short and mock asyncio.sleep
    with (
        patch(
            "analysi.integrations.framework.integrations.sumologic.actions.POLLING_MAX_TIME",
            0.1,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await get_results_action.execute(search_id="test-job-123")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


# DeleteJobAction Tests


@pytest.mark.asyncio
async def test_delete_job_success(delete_job_action):
    """Test successful job deletion."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    delete_job_action.http_request = AsyncMock(return_value=mock_response)
    result = await delete_job_action.execute(search_id="test-job-123")

    assert result["status"] == "success"
    assert result["search_id"] == "test-job-123"
    assert "deleted successfully" in result["message"]


@pytest.mark.asyncio
async def test_delete_job_missing_search_id(delete_job_action):
    """Test delete job with missing search_id parameter."""
    result = await delete_job_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'search_id'" in result["error"]


@pytest.mark.asyncio
async def test_delete_job_not_found(delete_job_action):
    """Test delete job with invalid search_id."""
    from httpx import HTTPStatusError, Request, Response

    mock_response = Response(status_code=404, request=Request("DELETE", "http://test"))
    delete_job_action.http_request = AsyncMock(
        side_effect=HTTPStatusError(
            "Not found", request=mock_response.request, response=mock_response
        )
    )
    result = await delete_job_action.execute(search_id="invalid-job")

    assert result["status"] == "error"
    assert result["error_type"] == "NotFoundError"
    assert "Invalid or expired search job ID" in result["error"]


@pytest.mark.asyncio
async def test_delete_job_missing_credentials(mock_settings):
    """Test delete job with missing credentials."""
    action = DeleteJobAction(
        integration_id="test-sumologic",
        action_id="delete_job",
        credentials={},
        settings=mock_settings,
    )

    result = await action.execute(search_id="test-job-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]
