"""
Unit tests for Splunk integration actions.

Tests action execution via framework with mocked Splunk SDK.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tenacity import wait_fixed

from analysi.integrations.framework.integrations.splunk.actions import (
    GenerateTriggeringEventsSplAction,
    GetIndexStatsAction,
    HealthCheckAction,
    ListDatamodelsAction,
    ListIndexesAction,
    ListSavedSearchesAction,
    PullAlertsAction,
    SendEventsAction,
    SourcetypeDiscoveryAction,
    SplRunAction,
    UpdateNotableAction,
)


class TestSplunkHealthCheckAction:
    """Test Splunk health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="splunk",
            action_id="health_check",
            settings={"host": "splunk.example.com", "port": 8089},
            credentials={"username": "admin", "password": "changeme"},
        )

    @pytest.mark.asyncio
    async def test_execute_splunk_health_check_via_framework(self, health_check_action):
        """Test: Execute Splunk health_check via framework.

        Goal: Verify framework execution path works with implementation.
        """
        # Mock the Splunk SDK client
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_service = MagicMock()
            mock_client.connect.return_value = mock_service

            result = await health_check_action.execute()

            # Should return success response
            assert result["status"] == "success", (
                f"Expected success status, got {result.get('status')}"
            )
            assert "message" in result, "Result should have message"
            assert "Splunk connection successful" in result["message"]
            assert "timestamp" in result, "Result should have timestamp"

            # Verify Splunk SDK was called
            mock_client.connect.assert_called_once()


class TestSplunkToolActions:
    """Test Splunk tool actions execution."""

    @pytest.mark.asyncio
    async def test_execute_update_notable(self):
        """Test: Execute update_notable via framework."""
        action = UpdateNotableAction(
            integration_id="splunk",
            action_id="update_notable",
            settings={},
            credentials={"username": "admin", "password": "pass"},
        )

        result = await action.execute(
            notable_id="ABC123", status="closed", comment="Automated closure"
        )

        assert result["status"] == "success"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_execute_send_events(self):
        """Test: Execute send_events via framework."""
        action = SendEventsAction(
            integration_id="splunk",
            action_id="send_events",
            settings={},
            credentials={"username": "admin", "password": "pass"},
        )

        result = await action.execute(
            events=[{"message": "test event"}], index="main", sourcetype="custom"
        )

        assert result["status"] == "success"
        assert "events_sent" in result
        assert result["events_sent"] == 0  # Placeholder returns 0

    @pytest.mark.asyncio
    async def test_execute_all_splunk_tool_actions(self):
        """Test: Execute all 6 Splunk tool actions via framework.

        Goal: Ensure all 6 Splunk tool actions execute via framework without errors.
        Note: sourcetype_discovery is now a connector, not a tool.
        """
        # Mock Splunk SDK for actions that need it
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                # Mock service.get() for datamodels REST API call
                mock_response = MagicMock()
                mock_response.body.read.return_value = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
                mock_service.get.return_value = mock_response

                mock_service.saved_searches = []
                mock_service.indexes = []

                # Mock job for actions that create search jobs
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_job.results.return_value = MagicMock()
                mock_service.jobs.create.return_value = mock_job

                mock_client.connect.return_value = mock_service

                # Mock results reader to return empty list
                mock_results.JSONResultsReader.return_value = []

                # Only tool actions (sourcetype_discovery is now a connector)
                tool_actions = [
                    (UpdateNotableAction, "update_notable", {}),
                    (SendEventsAction, "send_events", {}),
                    (ListDatamodelsAction, "list_datamodels", {}),
                    (ListSavedSearchesAction, "list_saved_searches", {}),
                    (GetIndexStatsAction, "get_index_stats", {}),
                    (ListIndexesAction, "list_indexes", {}),
                ]

                for action_class, action_id, params in tool_actions:
                    action = action_class(
                        integration_id="splunk",
                        action_id=action_id,
                        settings={"host": "splunk.local", "port": 8089},
                        credentials={"username": "admin", "password": "pass"},
                    )

                    result = await action.execute(**params)

                    assert result["status"] == "success", (
                        f"Action {action_id} should return success, got {result.get('status')}: {result.get('message')}"
                    )


class TestSplunkPullAlertsAction:
    """Test Splunk pull_alerts connector action."""

    @pytest.mark.asyncio
    async def test_execute_pull_alerts(self):
        """Test: Execute pull_alerts via framework."""
        from datetime import UTC, datetime, timedelta

        action = PullAlertsAction(
            integration_id="splunk",
            action_id="pull_alerts",
            settings={
                "host": "splunk.local",
                "port": 8089,
                "search_query": "search index=notable",
            },
            credentials={"username": "admin", "password": "pass"},
        )

        # Mock the Splunk SDK client
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_job.results.return_value = MagicMock()
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                # Mock results reader to return empty list
                mock_results.JSONResultsReader.return_value = []

                now = datetime.now(UTC)
                result = await action.execute(
                    start_time=now - timedelta(hours=1), end_time=now
                )

                assert result["status"] == "success"
                assert "alerts_count" in result
                assert result["alerts_count"] == 0  # Empty results
                assert "alerts" in result
                assert isinstance(result["alerts"], list)
                assert len(result["alerts"]) == 0  # Empty results


# ========================================
# PORTED TESTS FROM LEGACY test_splunk_connector.py
# Additional coverage for connection errors, retries, query variants
# ========================================


class TestSplunkConnectionErrorHandling:
    """Test Splunk connection error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_connection_retry_on_failure(self):
        """Test that connection retries via sdk_retry_policy then raises.

        sdk_retry_policy retries on all exceptions (including ValueError).
        After exhausting 3 attempts the error re-raises.
        """
        action = HealthCheckAction(
            integration_id="splunk",
            action_id="health_check",
            settings={"host": "splunk.example.com", "port": 8089},
            credentials={"username": "admin", "password": "changeme"},
        )

        # Patch retry wait to avoid exponential backoff delays
        with (
            patch(
                "analysi.integrations.framework.integrations.splunk.actions.client"
            ) as mock_client,
            patch.object(action._connect.retry, "wait", wait_fixed(0)),
        ):
            mock_client.connect.side_effect = Exception("Connection refused")

            # Should raise ValueError after exhausting retries (3 attempts)
            with pytest.raises(ValueError, match="Failed to connect to Splunk"):
                await action._connect()

            # sdk_retry_policy retries 3 times total
            assert mock_client.connect.call_count == 3

    @pytest.mark.asyncio
    async def test_health_check_returns_error_on_connection_failure(self):
        """Test health check returns error status on connection failure.

        Enhanced version ensuring graceful error handling.
        """
        action = HealthCheckAction(
            integration_id="splunk",
            action_id="health_check",
            settings={"host": "unreachable.example.com", "port": 8089},
            credentials={"username": "admin", "password": "changeme"},
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_client.connect.side_effect = Exception("Network unreachable")

            with patch("asyncio.sleep", return_value=None):
                result = await action.execute()

                # Should return error status, not raise
                assert result["status"] == "error"
                assert (
                    "failed" in result["message"].lower()
                    or "unreachable" in result["message"].lower()
                )
                assert "timestamp" in result


class TestSplunkQueryVariants:
    """Test Splunk query execution variants.

    Ported from: test_splunk_connector.py::TestSplunkQueryExecution
    """

    @pytest.mark.asyncio
    async def test_pull_alerts_with_results(self):
        """Test pull_alerts returns events from query."""
        action = PullAlertsAction(
            integration_id="splunk",
            action_id="pull_alerts",
            settings={
                "host": "splunk.local",
                "port": 8089,
                "search_query": "search index=notable",
            },
            credentials={"username": "admin", "password": "pass"},
        )

        # Mock Splunk SDK
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                # Mock results with actual data
                mock_results_data = [
                    {
                        "_time": "2024-01-15T10:30:00Z",
                        "rule_name": "Test Alert 1",
                        "severity": "high",
                    },
                    {
                        "_time": "2024-01-15T10:31:00Z",
                        "rule_name": "Test Alert 2",
                        "severity": "medium",
                    },
                ]
                mock_results.JSONResultsReader.return_value = mock_results_data

                from datetime import timedelta

                now = datetime.now(UTC)
                result = await action.execute(
                    start_time=now - timedelta(hours=1), end_time=now
                )

                assert result["status"] == "success"
                assert result["alerts_count"] == 2
                assert len(result["alerts"]) == 2
                assert result["alerts"][0]["rule_name"] == "Test Alert 1"

    @pytest.mark.asyncio
    async def test_pull_alerts_empty_results(self):
        """Test pull_alerts handles empty results gracefully.

        Ported from: test_splunk_connector.py::TestSplunkQueryExecution::test_empty_result_handling
        """
        action = PullAlertsAction(
            integration_id="splunk",
            action_id="pull_alerts",
            settings={
                "host": "splunk.local",
                "port": 8089,
                "search_query": "search index=notable",
            },
            credentials={"username": "admin", "password": "pass"},
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                # Empty results
                mock_results.JSONResultsReader.return_value = []

                from datetime import timedelta

                now = datetime.now(UTC)
                result = await action.execute(
                    start_time=now - timedelta(hours=1), end_time=now
                )

                assert result["status"] == "success"
                assert result["alerts_count"] == 0
                assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_pull_alerts_uses_custom_query(self):
        """Test pull_alerts uses custom SPL query from settings.

        Ported from: test_splunk_connector.py::TestSplunkQueryExecution::test_query_with_custom_spl
        """
        custom_query = "search index=notable severity=high | head 50"

        action = PullAlertsAction(
            integration_id="splunk",
            action_id="pull_alerts",
            settings={
                "host": "splunk.local",
                "port": 8089,
                "search_query": custom_query,
            },
            credentials={"username": "admin", "password": "pass"},
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service
                mock_results.JSONResultsReader.return_value = []

                from datetime import timedelta

                now = datetime.now(UTC)
                await action.execute(start_time=now - timedelta(hours=1), end_time=now)

                # Verify custom query was used
                call_args = mock_service.jobs.create.call_args
                query_used = call_args[0][0] if call_args[0] else ""

                # Should contain the custom query
                assert "severity=high" in query_used or custom_query in str(call_args)

    @pytest.mark.asyncio
    async def test_pull_alerts_uses_default_lookback_when_time_params_missing(self):
        """Test pull_alerts uses default lookback when start_time and end_time are not provided."""
        action = PullAlertsAction(
            integration_id="splunk",
            action_id="pull_alerts",
            settings={
                "host": "splunk.local",
                "port": 8089,
                "default_lookback_minutes": 10,
            },
            credentials={"username": "admin", "password": "pass"},
        )

        # Mock the Splunk SDK client to avoid real network calls
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service
                mock_results.JSONResultsReader.return_value = []

                # Call without time params - should use default lookback
                result = await action.execute()

                # Should succeed with default lookback
                assert result["status"] == "success"
                assert result["alerts_count"] == 0
                assert result["alerts"] == []

                # Verify the query was created (meaning default lookback was used)
                assert mock_service.jobs.create.called


class TestSplunkSourcetypeDiscovery:
    """Test Splunk sourcetype_discovery action with enhanced coverage.

    Ported from: test_splunk_sourcetype_discovery.py
    """

    @pytest.mark.asyncio
    async def test_sourcetype_discovery_data_conversion(self):
        """Test that search results properly convert string values to correct types.

        Ported from: test_splunk_sourcetype_discovery.py::test_sourcetype_discovery_data_conversion
        """
        action = SourcetypeDiscoveryAction(
            integration_id="splunk",
            action_id="sourcetype_discovery",
            settings={"host": "splunk.local", "port": 8089},
            credentials={"username": "admin", "password": "pass"},
        )

        # Mock Splunk SDK
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_job.sid = "test-job-123"
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                # Mock results with string values (as returned by Splunk)
                mock_results_data = [
                    {
                        "index": "_internal",
                        "sourcetype": "splunkd",
                        "count": "1234",  # String that should be converted to int
                        "earliest": "1700000000.123",  # String that should be converted to float
                        "latest": "1700086400.456",  # String that should be converted to float
                        "time_span_seconds": "86400.333",  # String that should be converted to float
                        "eps": "0.0142857",  # String that should be converted to float
                    }
                ]
                mock_results.JSONResultsReader.return_value = mock_results_data

                # Mock KU storage to avoid API client dependency
                with patch.object(
                    action, "_store_in_knowledge_unit", new_callable=AsyncMock
                ):
                    result = await action.execute()

                # Verify success
                assert result["status"] == "success"

                # Verify data types in results array
                first_result = result["results"][0]
                assert isinstance(first_result["count"], int), (
                    f"count should be int, got {type(first_result['count'])}"
                )
                assert first_result["count"] == 1234
                assert isinstance(first_result["earliest"], float), (
                    f"earliest should be float, got {type(first_result['earliest'])}"
                )
                assert first_result["earliest"] == 1700000000.123
                assert isinstance(first_result["latest"], float), (
                    f"latest should be float, got {type(first_result['latest'])}"
                )
                assert first_result["latest"] == 1700086400.456
                assert isinstance(first_result["time_span_seconds"], float)
                assert first_result["time_span_seconds"] == 86400.333
                assert isinstance(first_result["eps"], float)
                assert first_result["eps"] == 0.0142857

    @pytest.mark.asyncio
    async def test_sourcetype_discovery_query_parameters(self):
        """Test that sourcetype_discovery uses correct search query and parameters.

        Ported from: test_splunk_sourcetype_discovery.py::test_sourcetype_discovery_success
        """
        action = SourcetypeDiscoveryAction(
            integration_id="splunk",
            action_id="sourcetype_discovery",
            settings={"host": "splunk.local", "port": 8089},
            credentials={"username": "admin", "password": "pass"},
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_job.sid = "test-job-123"
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service
                mock_results.JSONResultsReader.return_value = []

                await action.execute()

                # Verify search query contains tstats
                call_args = mock_service.jobs.create.call_args
                query = call_args[0][0]
                assert "tstats count" in query, "Should use tstats query"
                assert "by index, sourcetype" in query, (
                    "Should group by index and sourcetype"
                )

                # Verify search parameters
                search_kwargs = call_args[1]
                assert search_kwargs["earliest_time"] == "-24h", (
                    "Should search last 24 hours"
                )
                assert search_kwargs["latest_time"] == "now"
                assert search_kwargs["count"] == 0, "Should return all results"

    @pytest.mark.asyncio
    async def test_sourcetype_discovery_result_structure(self):
        """Test that sourcetype_discovery returns correct result structure.

        Enhanced from: test_splunk_sourcetype_discovery.py
        """
        action = SourcetypeDiscoveryAction(
            integration_id="splunk",
            action_id="sourcetype_discovery",
            settings={"host": "splunk.local", "port": 8089},
            credentials={"username": "admin", "password": "pass"},
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch(
                "analysi.integrations.framework.integrations.splunk.actions.results"
            ) as mock_results:
                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = True
                mock_job.sid = "test-job-123"
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                # Mock 2 sourcetype results
                mock_results_data = [
                    {
                        "index": "_internal",
                        "sourcetype": "splunkd",
                        "count": "1000",
                        "earliest": "1700000000",
                        "latest": "1700086400",
                        "time_span_seconds": "86400",
                        "eps": "0.0115",
                    },
                    {
                        "index": "main",
                        "sourcetype": "access_combined",
                        "count": "5000",
                        "earliest": "1700000000",
                        "latest": "1700086400",
                        "time_span_seconds": "86400",
                        "eps": "0.0578",
                    },
                ]
                mock_results.JSONResultsReader.return_value = mock_results_data

                # Mock KU storage to avoid API client dependency
                with patch.object(
                    action, "_store_in_knowledge_unit", new_callable=AsyncMock
                ):
                    result = await action.execute()

                # Verify result structure
                assert result["status"] == "success"
                assert "results" in result, "Should have results key"
                assert "rows" in result, "Should have rows key"
                assert result["rows"] == 2, f"Should have rows=2, got {result['rows']}"
                assert len(result["results"]) == 2, "Should have 2 results"

                # Verify each result has required fields
                for st in result["results"]:
                    assert "index" in st
                    assert "sourcetype" in st
                    assert "count" in st
                    assert "earliest" in st
                    assert "latest" in st


# ========================================
# SPL RUN ACTION TESTS
# Migrated from deprecated test_cy_splunk_functions.py
# ========================================


class TestSplRunAction:
    """Test SplRunAction - Execute arbitrary SPL queries.

    Migrated from: tests/unit/services/test_cy_splunk_functions.py
    """

    @pytest.fixture
    def spl_run_action(self):
        """Create SplRunAction instance."""
        return SplRunAction(
            integration_id="splunk",
            action_id="spl_run",
            settings={"host": "splunk.local", "port": 8089},
            credentials={"username": "admin", "password": "pass"},
        )

    @pytest.mark.asyncio
    async def test_spl_run_success(self, spl_run_action):
        """Test successful SPL query execution."""
        # Mock Splunk SDK
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_service = MagicMock()
            mock_job = MagicMock()
            mock_job.is_done.return_value = True
            mock_job.results.return_value = [
                b'{"results": [{"_raw": "test event 1"}, {"_raw": "test event 2"}]}'
            ]
            mock_service.jobs.create.return_value = mock_job
            mock_client.connect.return_value = mock_service

            result = await spl_run_action.execute(
                spl_query="search index=main | head 2", timeout=30
            )

            assert result["status"] == "success"
            assert "events" in result
            assert len(result["events"]) == 2
            assert "count" in result
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_spl_run_empty_query(self, spl_run_action):
        """Test SPL run with empty query string."""
        result = await spl_run_action.execute(spl_query="", timeout=30)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert (
            "required" in result["error"].lower() or "empty" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_spl_run_none_query(self, spl_run_action):
        """Test SPL run with None query."""
        result = await spl_run_action.execute(spl_query=None, timeout=30)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_spl_run_negative_timeout(self, spl_run_action):
        """Test SPL run with negative timeout."""
        result = await spl_run_action.execute(
            spl_query="search index=main", timeout=-10
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_spl_run_zero_timeout(self, spl_run_action):
        """Test SPL run with zero timeout."""
        result = await spl_run_action.execute(spl_query="search index=main", timeout=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_spl_run_missing_credentials(self):
        """Test SPL run with missing credentials."""
        action = SplRunAction(
            integration_id="splunk",
            action_id="spl_run",
            settings={"host": "splunk.local", "port": 8089},
            credentials={},  # Empty credentials
        )

        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_client.connect.side_effect = ValueError(
                "Splunk connection requires host and credentials"
            )

            with patch("asyncio.sleep", return_value=None):
                result = await action.execute(spl_query="search index=main", timeout=30)

                assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_spl_run_connection_failure(self, spl_run_action):
        """Test SPL run with connection failure."""
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_client.connect.side_effect = Exception("Connection refused")

            with patch("asyncio.sleep", return_value=None):
                result = await spl_run_action.execute(
                    spl_query="search index=main", timeout=30
                )

                assert result["status"] == "error"
                assert "error" in result

    @pytest.mark.asyncio
    async def test_spl_run_timeout_exceeded(self, spl_run_action):
        """Test SPL run query exceeds timeout."""
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            with patch("time.time") as mock_time:
                # First call returns start time, subsequent calls simulate timeout
                mock_time.side_effect = [0, 0, 0.5, 121]  # 121 seconds elapsed

                mock_service = MagicMock()
                mock_job = MagicMock()
                mock_job.is_done.return_value = False  # Never completes
                mock_job.cancel.return_value = None
                mock_service.jobs.create.return_value = mock_job
                mock_client.connect.return_value = mock_service

                with patch("asyncio.sleep", return_value=None):
                    result = await spl_run_action.execute(
                        spl_query="search index=_audit | stats count", timeout=120
                    )

                    assert result["status"] == "error"
                    assert result["error_type"] == "TimeoutError"
                    assert "timeout" in result["error"].lower()
                    mock_job.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_spl_run_empty_results(self, spl_run_action):
        """Test SPL run with no results returned."""
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_service = MagicMock()
            mock_job = MagicMock()
            mock_job.is_done.return_value = True
            mock_job.results.return_value = []  # Empty results
            mock_service.jobs.create.return_value = mock_job
            mock_client.connect.return_value = mock_service

            result = await spl_run_action.execute(
                spl_query="search index=main sourcetype=nonexistent", timeout=30
            )

            assert result["status"] == "success"
            assert result["events"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_spl_run_multiple_events(self, spl_run_action):
        """Test SPL run returns multiple events."""
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_service = MagicMock()
            mock_job = MagicMock()
            mock_job.is_done.return_value = True
            mock_job.results.return_value = [
                b'{"results": [{"_raw": "event 1"}, {"_raw": "event 2"}, {"_raw": "event 3"}]}'
            ]
            mock_service.jobs.create.return_value = mock_job
            mock_client.connect.return_value = mock_service

            result = await spl_run_action.execute(
                spl_query="search index=main | head 3", timeout=30
            )

            assert result["status"] == "success"
            assert len(result["events"]) == 3
            assert result["count"] == 3
            assert "event 1" in result["events"]
            assert "event 2" in result["events"]
            assert "event 3" in result["events"]

    @pytest.mark.asyncio
    async def test_spl_run_result_format(self, spl_run_action):
        """Test SPL run result format - should be list of _raw strings."""
        with patch(
            "analysi.integrations.framework.integrations.splunk.actions.client"
        ) as mock_client:
            mock_service = MagicMock()
            mock_job = MagicMock()
            mock_job.is_done.return_value = True
            # Test with dict results containing _raw field
            mock_job.results.return_value = [{"_raw": "raw event data"}]
            mock_service.jobs.create.return_value = mock_job
            mock_client.connect.return_value = mock_service

            result = await spl_run_action.execute(
                spl_query="search index=main | head 1", timeout=30
            )

            assert result["status"] == "success"
            assert isinstance(result["events"], list)
            assert len(result["events"]) == 1
            assert result["events"][0] == "raw event data"


# ========================================
# GENERATE TRIGGERING EVENTS SPL ACTION TESTS
# Migrated from deprecated test_cy_splunk_functions.py
# ========================================


class TestGenerateTriggeringEventsSplAction:
    """Test GenerateTriggeringEventsSplAction - Generate SPL from NAS alerts.

    Migrated from: tests/unit/services/test_cy_splunk_functions.py
    """

    @pytest.fixture
    def generate_spl_action(self):
        """Create GenerateTriggeringEventsSplAction instance."""
        return GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

    @pytest.mark.asyncio
    async def test_generate_spl_missing_source_category(self, generate_spl_action):
        """Test generate SPL with missing source_category."""
        alert = {
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        # Mock CIM data loading to return empty mappings (will cause error)
        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            mock_instance = AsyncMock()
            mock_instance.load_source_to_cim_mappings.return_value = {}
            mock_instance.load_cim_to_sourcetypes_mappings.return_value = {}
            mock_instance.load_sourcetype_to_index_directory.return_value = {}
            mock_loader.return_value = mock_instance

            result = await generate_spl_action.execute(alert=alert, lookback_seconds=60)

            # Should fail due to missing source_category or CIM data not found
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_generate_spl_missing_triggering_time(self):
        """Test generate SPL with missing triggering_event_time."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            mock_instance = AsyncMock()
            mock_instance.load_source_to_cim_mappings.return_value = {}
            mock_instance.load_cim_to_sourcetypes_mappings.return_value = {}
            mock_instance.load_sourcetype_to_index_directory.return_value = {}
            mock_loader.return_value = mock_instance

            result = await action.execute(alert=alert, lookback_seconds=60)

            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_generate_spl_invalid_timestamp(self):
        """Test generate SPL with invalid timestamp format."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "not-a-valid-timestamp",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            mock_instance = AsyncMock()
            mock_instance.load_source_to_cim_mappings.return_value = {}
            mock_instance.load_cim_to_sourcetypes_mappings.return_value = {}
            mock_instance.load_sourcetype_to_index_directory.return_value = {}
            mock_loader.return_value = mock_instance

            result = await action.execute(alert=alert, lookback_seconds=60)

            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_generate_spl_negative_lookback(self):
        """Test generate SPL with negative lookback_seconds."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        result = await action.execute(alert=alert, lookback_seconds=-60)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "lookback_seconds" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_spl_zero_lookback(self):
        """Test generate SPL with zero lookback_seconds."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        result = await action.execute(alert=alert, lookback_seconds=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "lookback_seconds" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_spl_empty_iocs(self):
        """Test generate SPL with empty IOCs list (should work)."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],  # Empty but valid
        }

        # Mock CIM data loading to return proper mappings
        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            with patch("analysi.utils.splunk_utils.CIMMapper") as mock_mapper:
                with patch("analysi.utils.splunk_utils.SPLGenerator") as mock_generator:
                    mock_instance = AsyncMock()
                    mock_instance.load_source_to_cim_mappings.return_value = {
                        "Firewall": "Network Traffic"
                    }
                    mock_instance.load_cim_to_sourcetypes_mappings.return_value = {}
                    mock_instance.load_sourcetype_to_index_directory.return_value = {}
                    mock_loader.return_value = mock_instance

                    mock_mapper_instance = MagicMock()
                    mock_mapper.return_value = mock_mapper_instance

                    mock_gen_instance = MagicMock()
                    mock_gen_instance.generate_triggering_events_spl.return_value = (
                        "search index=network"
                    )
                    mock_generator.return_value = mock_gen_instance

                    result = await action.execute(alert=alert, lookback_seconds=60)

                    # Should succeed even with empty IOCs
                    assert result["status"] == "success"
                    assert "spl_query" in result

    @pytest.mark.asyncio
    async def test_generate_spl_alert_format_adapter(self):
        """Test generate SPL adapts OCSF alert to SPL generator format."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        # OCSF format alert
        ocsf_alert = {
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "metadata": {
                "labels": ["source_category:Firewall", "env:prod"],
            },
            "actor": {"user": {"name": "192.168.1.100"}},
            "observables": [
                {"type": "domain", "value": "malicious.com"},
                {"type": "file_name", "value": "badfile.exe"},
            ],
        }

        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            with patch("analysi.utils.splunk_utils.CIMMapper") as mock_mapper:
                with patch("analysi.utils.splunk_utils.SPLGenerator") as mock_generator:
                    mock_instance = AsyncMock()
                    mock_instance.load_source_to_cim_mappings.return_value = {}
                    mock_instance.load_cim_to_sourcetypes_mappings.return_value = {}
                    mock_instance.load_sourcetype_to_index_directory.return_value = {}
                    mock_loader.return_value = mock_instance

                    mock_mapper_instance = MagicMock()
                    mock_mapper.return_value = mock_mapper_instance

                    mock_gen_instance = MagicMock()
                    mock_gen_instance.generate_triggering_events_spl.return_value = (
                        "search index=firewall"
                    )
                    mock_generator.return_value = mock_gen_instance

                    result = await action.execute(alert=ocsf_alert, lookback_seconds=60)

                    # Should successfully adapt and generate SPL
                    assert result["status"] == "success"
                    assert "spl_query" in result

                    # Verify the adapter produced SPL generator format
                    call_args = (
                        mock_gen_instance.generate_triggering_events_spl.call_args
                    )
                    adapted_alert = call_args[0][0]

                    # Should have SPL generator contract keys
                    assert "primary_risk_entity" in adapted_alert
                    assert "indicators_of_compromise" in adapted_alert
                    assert "source_category" in adapted_alert
                    assert adapted_alert["source_category"] == "Firewall"
                    assert adapted_alert["primary_risk_entity"] == "192.168.1.100"
                    assert adapted_alert["indicators_of_compromise"] == [
                        "malicious.com",
                        "badfile.exe",
                    ]

    @pytest.mark.asyncio
    async def test_generate_spl_missing_ku_tables(self):
        """Test generate SPL with missing KU tables."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={"session": MagicMock(), "tenant_id": "test-tenant"},
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        # Mock CIM loader to raise exception (tables not found)
        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            mock_instance = AsyncMock()
            mock_instance.load_source_to_cim_mappings.side_effect = Exception(
                "KU table not found"
            )
            mock_loader.return_value = mock_instance

            result = await action.execute(alert=alert, lookback_seconds=60)

            assert result["status"] == "error"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_generate_spl_missing_session_context(self):
        """Test generate SPL with missing session in context."""
        action = GenerateTriggeringEventsSplAction(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            settings={},
            credentials={},
            ctx={},  # Missing session and tenant_id
        )

        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-01T12:00:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": [],
        }

        result = await action.execute(alert=alert, lookback_seconds=60)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert (
            "session" in result["error"].lower() or "tenant" in result["error"].lower()
        )
