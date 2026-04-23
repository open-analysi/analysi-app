"""Unit tests for BigQuery integration actions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.bigquery.actions import (
    GetResultsAction,
    HealthCheckAction,
    ListTablesAction,
    RunQueryAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance for testing."""
    return HealthCheckAction(
        integration_id="bigquery",
        action_id="health_check",
        settings={},
        credentials={
            "service_account_json": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "test-project",
                    "private_key_id": "key123",
                    "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                    "client_email": "test@test-project.iam.gserviceaccount.com",
                    "client_id": "123456789",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        },
    )


@pytest.fixture
def list_tables_action():
    """Create ListTablesAction instance for testing."""
    return ListTablesAction(
        integration_id="bigquery",
        action_id="list_tables",
        settings={},
        credentials={
            "service_account_json": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "test-project",
                    "private_key_id": "key123",
                    "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                    "client_email": "test@test-project.iam.gserviceaccount.com",
                    "client_id": "123456789",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        },
    )


@pytest.fixture
def run_query_action():
    """Create RunQueryAction instance for testing."""
    return RunQueryAction(
        integration_id="bigquery",
        action_id="run_query",
        settings={"default_timeout": 30},
        credentials={
            "service_account_json": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "test-project",
                    "private_key_id": "key123",
                    "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                    "client_email": "test@test-project.iam.gserviceaccount.com",
                    "client_id": "123456789",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        },
    )


@pytest.fixture
def get_results_action():
    """Create GetResultsAction instance for testing."""
    return GetResultsAction(
        integration_id="bigquery",
        action_id="get_results",
        settings={"default_timeout": 30},
        credentials={
            "service_account_json": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "test-project",
                    "private_key_id": "key123",
                    "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                    "client_email": "test@test-project.iam.gserviceaccount.com",
                    "client_id": "123456789",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        },
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_client = MagicMock()
    mock_client.list_datasets.return_value = []

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "BigQuery API is accessible" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="bigquery",
        action_id="health_check",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False
    assert "Missing required service account credentials" in result["error"]


@pytest.mark.asyncio
async def test_health_check_invalid_json():
    """Test health check with invalid service account JSON."""
    action = HealthCheckAction(
        integration_id="bigquery",
        action_id="health_check",
        settings={},
        credentials={"service_account_json": "not valid json"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_authentication_error(health_check_action):
    """Test health check with authentication error."""
    mock_client = MagicMock()
    mock_client.list_datasets.side_effect = Exception("Authentication failed")

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
    assert result["data"]["healthy"] is False


# ============================================================================
# LIST TABLES ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_tables_success(list_tables_action):
    """Test successful table listing."""
    # Create mock dataset and table objects
    mock_dataset_ref = MagicMock()
    mock_dataset_ref.dataset_id = "test_dataset"
    mock_dataset_ref.project = "test-project"

    mock_dataset = MagicMock()
    mock_dataset.reference = mock_dataset_ref

    mock_table = MagicMock()
    mock_table.table_id = "test_table"
    mock_table.full_table_id = "test-project:test_dataset.test_table"

    mock_client = MagicMock()
    mock_client.list_datasets.return_value = [mock_dataset]
    mock_client.list_tables.return_value = [mock_table]

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await list_tables_action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_tables"] == 1
    assert len(result["data"]["tables"]) == 1
    assert result["data"]["tables"][0]["table_id"] == "test_table"
    assert result["data"]["tables"][0]["dataset_id"] == "test_dataset"


@pytest.mark.asyncio
async def test_list_tables_with_dataset_filter(list_tables_action):
    """Test table listing with dataset filter."""
    mock_dataset_ref = MagicMock()
    mock_dataset_ref.dataset_id = "test_dataset"
    mock_dataset_ref.project = "test-project"

    mock_table = MagicMock()
    mock_table.table_id = "test_table"
    mock_table.full_table_id = "test-project:test_dataset.test_table"

    mock_client = MagicMock()
    mock_client.dataset.return_value = mock_dataset_ref
    mock_client.list_tables.return_value = [mock_table]

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await list_tables_action.execute(dataset="test_dataset")

    assert result["status"] == "success"
    assert result["data"]["total_tables"] == 1
    mock_client.dataset.assert_called_once_with("test_dataset")


@pytest.mark.asyncio
async def test_list_tables_missing_credentials():
    """Test list tables with missing credentials."""
    action = ListTablesAction(
        integration_id="bigquery",
        action_id="list_tables",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required service account credentials" in result["error"]


@pytest.mark.asyncio
async def test_list_tables_query_error(list_tables_action):
    """Test list tables with query error."""
    mock_client = MagicMock()
    mock_client.list_datasets.side_effect = Exception("Query failed")

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await list_tables_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "QueryError"


# ============================================================================
# RUN QUERY ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_run_query_success(run_query_action):
    """Test successful query execution."""
    mock_row = {"col1": "value1", "col2": "value2"}
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])

    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await run_query_action.execute(query="SELECT * FROM test_table")

    assert result["status"] == "success"
    assert result["data"]["job_id"] == "job_123"
    assert result["data"]["num_rows"] == 1
    assert len(result["data"]["rows"]) == 1


@pytest.mark.asyncio
async def test_run_query_missing_query(run_query_action):
    """Test run query with missing query parameter."""
    result = await run_query_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'query'" in result["error"]


@pytest.mark.asyncio
async def test_run_query_invalid_timeout(run_query_action):
    """Test run query with invalid timeout."""
    result = await run_query_action.execute(query="SELECT 1", timeout="invalid")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Timeout must be a positive integer" in result["error"]


@pytest.mark.asyncio
async def test_run_query_timeout(run_query_action):
    """Test query execution timeout."""
    from concurrent.futures import TimeoutError as FuturesTimeoutError

    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.result.side_effect = FuturesTimeoutError("Query timed out")

    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await run_query_action.execute(
            query="SELECT * FROM test_table", timeout=1
        )

    assert result["status"] == "success"
    assert result["data"]["job_id"] == "job_123"
    assert result["data"]["timed_out"] is True


@pytest.mark.asyncio
async def test_run_query_missing_credentials():
    """Test run query with missing credentials."""
    action = RunQueryAction(
        integration_id="bigquery",
        action_id="run_query",
        settings={"default_timeout": 30},
        credentials={},
    )

    result = await action.execute(query="SELECT 1")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GET RESULTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_results_success(get_results_action):
    """Test successful result retrieval."""
    mock_row = {"col1": "value1", "col2": "value2"}
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])

    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.get_job.return_value = mock_job

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await get_results_action.execute(job_id="job_123")

    assert result["status"] == "success"
    assert result["data"]["job_id"] == "job_123"
    assert result["data"]["num_rows"] == 1
    assert len(result["data"]["rows"]) == 1


@pytest.mark.asyncio
async def test_get_results_missing_job_id(get_results_action):
    """Test get results with missing job_id parameter."""
    result = await get_results_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'job_id'" in result["error"]


@pytest.mark.asyncio
async def test_get_results_invalid_timeout(get_results_action):
    """Test get results with invalid timeout."""
    result = await get_results_action.execute(job_id="job_123", timeout=-5)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Timeout must be a positive integer" in result["error"]


@pytest.mark.asyncio
async def test_get_results_timeout(get_results_action):
    """Test result retrieval timeout."""
    from concurrent.futures import TimeoutError as FuturesTimeoutError

    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.result.side_effect = FuturesTimeoutError("Query timed out")

    mock_client = MagicMock()
    mock_client.get_job.return_value = mock_job

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await get_results_action.execute(job_id="job_123", timeout=1)

    assert result["status"] == "success"
    assert result["data"]["job_id"] == "job_123"
    assert result["data"]["timed_out"] is True


@pytest.mark.asyncio
async def test_get_results_missing_credentials():
    """Test get results with missing credentials."""
    action = GetResultsAction(
        integration_id="bigquery",
        action_id="get_results",
        settings={"default_timeout": 30},
        credentials={},
    )

    result = await action.execute(job_id="job_123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_results_job_not_found(get_results_action):
    """Test get results with non-existent job."""
    mock_client = MagicMock()
    mock_client.get_job.side_effect = Exception("Job not found")

    with (
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.service_account"
        ),
        patch(
            "analysi.integrations.framework.integrations.bigquery.actions.bigquery.Client",
            return_value=mock_client,
        ),
    ):
        result = await get_results_action.execute(job_id="nonexistent_job")

    assert result["status"] == "error"
    assert result["error_type"] == "QueryError"
