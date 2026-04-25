"""Unit tests for Databricks integration actions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.databricks.actions import (
    CancelQueryAction,
    CreateAlertAction,
    DeleteAlertAction,
    ExecuteNotebookAction,
    GetJobOutputAction,
    GetJobRunAction,
    GetQueryStatusAction,
    HealthCheckAction,
    ListAlertsAction,
    ListClustersAction,
    ListWarehousesAction,
    PerformQueryAction,
)


@pytest.fixture
def mock_credentials():
    """Mock Databricks credentials."""
    return {
        "token": "test-token-123",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "host": "https://example.cloud.databricks.com",
        "timeout": 30,
    }


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check."""
    action = HealthCheckAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_client = MagicMock()
    mock_client.dbfs.get_status.return_value = MagicMock()

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "host" in result["data"]
    mock_client.dbfs.get_status.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_host(mock_credentials, mock_settings):
    """Test health check with missing host."""
    action = HealthCheckAction(
        integration_id="databricks",
        action_id="test_action",
        credentials={"token": "test-token"},
        settings={"timeout": 30},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing" in result["error"]
    assert result["error_type"] == "ConfigurationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_missing_credentials(mock_credentials, mock_settings):
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="databricks",
        action_id="test_action",
        credentials={},
        settings={"host": "https://example.com", "timeout": 30},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "username/password or an authentication token" in result["error"]
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_api_error(mock_credentials, mock_settings):
    """Test health check with API error."""
    action = HealthCheckAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_client = MagicMock()
    mock_client.dbfs.get_status.side_effect = Exception("API Error")

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert "API Error" in result["error"]
    assert result["data"]["healthy"] is False


# ============================================================================
# ALERT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_alerts_success(mock_credentials, mock_settings):
    """Test successful list alerts."""
    action = ListAlertsAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_alert = MagicMock()
    mock_alert.as_dict.return_value = {"id": "alert1", "name": "Test Alert"}

    mock_client = MagicMock()
    mock_client.alerts.list.return_value = [mock_alert]

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_alerts"] == 1
    assert len(result["data"]["alerts"]) == 1
    mock_client.alerts.list.assert_called_once()


@pytest.mark.asyncio
async def test_create_alert_success(mock_credentials, mock_settings):
    """Test successful alert creation."""
    action = CreateAlertAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_alert = MagicMock()
    mock_alert.as_dict.return_value = {"id": "alert1", "name": "Test Alert"}

    mock_client = MagicMock()
    mock_client.alerts.create.return_value = mock_alert

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(
            name="Test Alert",
            query_id="query123",
            column="result",
            operator="GREATER_THAN",
            value="100",
        )

    assert result["status"] == "success"
    assert result["data"]["id"] == "alert1"
    mock_client.alerts.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_alert_missing_params(mock_credentials, mock_settings):
    """Test alert creation with missing parameters."""
    action = CreateAlertAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(name="Test Alert")

    assert result["status"] == "error"
    assert "Missing required parameters" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_delete_alert_success(mock_credentials, mock_settings):
    """Test successful alert deletion."""
    action = DeleteAlertAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_client = MagicMock()
    mock_client.alerts.delete.return_value = None

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(alert_id="alert123")

    assert result["status"] == "success"
    assert result["data"]["alert_id"] == "alert123"
    mock_client.alerts.delete.assert_called_once_with("alert123")


# ============================================================================
# CLUSTER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_clusters_success(mock_credentials, mock_settings):
    """Test successful list clusters."""
    action = ListClustersAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_cluster = MagicMock()
    mock_cluster.as_dict.return_value = {
        "cluster_id": "cluster1",
        "cluster_name": "Test Cluster",
    }

    mock_client = MagicMock()
    mock_client.clusters.list.return_value = [mock_cluster]

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_clusters"] == 1
    assert len(result["data"]["clusters"]) == 1


# ============================================================================
# WAREHOUSE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_warehouses_success(mock_credentials, mock_settings):
    """Test successful list warehouses."""
    action = ListWarehousesAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_warehouse = MagicMock()
    mock_warehouse.as_dict.return_value = {"id": "wh1", "name": "Test Warehouse"}

    mock_client = MagicMock()
    mock_client.warehouses.list.return_value = [mock_warehouse]

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_warehouses"] == 1
    assert len(result["data"]["warehouses"]) == 1


# ============================================================================
# QUERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_perform_query_success(mock_credentials, mock_settings):
    """Test successful query execution."""
    action = PerformQueryAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_result = MagicMock()
    mock_result.as_dict.return_value = {
        "statement_id": "stmt123",
        "status": "SUCCEEDED",
    }

    mock_client = MagicMock()
    mock_client.statement_execution.execute_statement.return_value = mock_result

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(
            statement="SELECT * FROM table",
            warehouse_id="wh123",
        )

    assert result["status"] == "success"
    assert result["data"]["statement_id"] == "stmt123"


@pytest.mark.asyncio
async def test_perform_query_missing_params(mock_credentials, mock_settings):
    """Test query execution with missing parameters."""
    action = PerformQueryAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(statement="SELECT * FROM table")

    assert result["status"] == "error"
    assert "Missing required parameters" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_query_status_success(mock_credentials, mock_settings):
    """Test successful get query status."""
    action = GetQueryStatusAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_result = MagicMock()
    mock_result.as_dict.return_value = {"statement_id": "stmt123", "status": "RUNNING"}

    mock_client = MagicMock()
    mock_client.statement_execution.get_statement.return_value = mock_result

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(statement_id="stmt123")

    assert result["status"] == "success"
    assert result["data"]["statement_id"] == "stmt123"


@pytest.mark.asyncio
async def test_cancel_query_success(mock_credentials, mock_settings):
    """Test successful query cancellation."""
    action = CancelQueryAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_client = MagicMock()
    mock_client.statement_execution.cancel_execution.return_value = None

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(statement_id="stmt123")

    assert result["status"] == "success"
    assert result["data"]["statement_id"] == "stmt123"


# ============================================================================
# JOB TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_job_run_success(mock_credentials, mock_settings):
    """Test successful get job run."""
    action = GetJobRunAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_run = MagicMock()
    mock_run.as_dict.return_value = {"run_id": 12345, "state": "RUNNING"}

    mock_client = MagicMock()
    mock_client.jobs.get_run.return_value = mock_run

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(run_id=12345)

    assert result["status"] == "success"
    assert result["data"]["run_id"] == 12345


@pytest.mark.asyncio
async def test_get_job_output_success(mock_credentials, mock_settings):
    """Test successful get job output."""
    action = GetJobOutputAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_task_run = MagicMock()
    mock_task_run.run_id = 67890

    mock_run = MagicMock()
    mock_run.tasks = [mock_task_run]

    mock_output = MagicMock()
    mock_output.as_dict.return_value = {"notebook_output": "result"}

    mock_client = MagicMock()
    mock_client.jobs.get_run.return_value = mock_run
    mock_client.jobs.get_run_output.return_value = mock_output

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(run_id=12345)

    assert result["status"] == "success"
    assert result["data"]["total_outputs"] == 1
    assert len(result["data"]["outputs"]) == 1


@pytest.mark.asyncio
async def test_get_job_output_no_tasks(mock_credentials, mock_settings):
    """Test get job output with no tasks."""
    action = GetJobOutputAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_run = MagicMock()
    mock_run.tasks = None

    mock_client = MagicMock()
    mock_client.jobs.get_run.return_value = mock_run

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(run_id=12345)

    assert result["status"] == "error"
    assert "no task runs" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# NOTEBOOK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_execute_notebook_success(mock_credentials, mock_settings):
    """Test successful notebook execution."""
    action = ExecuteNotebookAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_state = MagicMock()
    mock_state.result_state = "SUCCEEDED"
    mock_state.state_message = "Success"

    mock_result = MagicMock()
    mock_result.state = mock_state
    mock_result.as_dict.return_value = {
        "run_id": 12345,
        "state": {"result_state": "SUCCEEDED"},
    }

    mock_submitted = MagicMock()
    mock_submitted.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.jobs.submit.return_value = mock_submitted

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(
            notebook_path="/Users/test/notebook",
            existing_cluster_id="cluster123",
        )

    assert result["status"] == "success"
    assert result["data"]["run_id"] == 12345


@pytest.mark.asyncio
async def test_execute_notebook_missing_cluster(mock_credentials, mock_settings):
    """Test notebook execution without cluster specification."""
    action = ExecuteNotebookAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(notebook_path="/Users/test/notebook")

    assert result["status"] == "error"
    assert "new_cluster or existing_cluster_id" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_execute_notebook_with_new_cluster(mock_credentials, mock_settings):
    """Test notebook execution with new cluster."""
    action = ExecuteNotebookAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    mock_state = MagicMock()
    mock_state.result_state = "SUCCEEDED"

    mock_result = MagicMock()
    mock_result.state = mock_state
    mock_result.as_dict.return_value = {"run_id": 12345}

    mock_submitted = MagicMock()
    mock_submitted.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.jobs.submit.return_value = mock_submitted

    cluster_spec = json.dumps(
        {
            "spark_version": "13.3.x-scala2.12",
            "node_type_id": "i3.xlarge",
            "num_workers": 2,
        }
    )

    with patch(
        "analysi.integrations.framework.integrations.databricks.actions._get_databricks_client",
        return_value=mock_client,
    ):
        result = await action.execute(
            notebook_path="/Users/test/notebook",
            new_cluster=cluster_spec,
        )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_notebook_invalid_json(mock_credentials, mock_settings):
    """Test notebook execution with invalid JSON."""
    action = ExecuteNotebookAction(
        integration_id="databricks",
        action_id="test_action",
        credentials=mock_credentials,
        settings=mock_settings,
    )

    result = await action.execute(
        notebook_path="/Users/test/notebook",
        new_cluster="invalid json",
    )

    assert result["status"] == "error"
    assert "Invalid JSON" in result["error"]
    assert result["error_type"] == "ValidationError"
