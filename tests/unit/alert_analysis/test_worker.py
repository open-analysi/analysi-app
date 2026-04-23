"""
Unit tests for Alert Analysis Worker.
Tests worker initialization, job processing, and queue management.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.connections import RedisSettings

from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.alert_analysis.worker import (
    WorkerSettings,
    process_alert_analysis,
    queue_alert_analysis,
)


class TestWorkerSettings:
    """Test WorkerSettings configuration loading."""

    def test_default_redis_settings(self):
        """Test default Redis/Valkey connection settings."""
        from analysi.config.valkey_db import ValkeyDBConfig

        settings = WorkerSettings.redis_settings
        assert isinstance(settings, RedisSettings)
        assert settings.host == os.getenv("REDIS_HOST", "valkey")
        assert settings.port == int(os.getenv("REDIS_PORT", 6379))
        # Database should be from ValkeyDBConfig
        assert settings.database == ValkeyDBConfig.ALERT_PROCESSING_DB

    def test_worker_settings_from_env(self):
        """Test worker settings load from environment variables."""
        # WorkerSettings now uses AlertAnalysisConfig
        assert WorkerSettings.max_jobs == AlertAnalysisConfig.MAX_JOBS
        assert WorkerSettings.job_timeout == AlertAnalysisConfig.JOB_TIMEOUT
        # Default is now 30 minutes (1800 seconds)
        assert (
            int(os.getenv("ALERT_WORKER_TIMEOUT", 1800))
            == AlertAnalysisConfig.JOB_TIMEOUT
        )
        assert hasattr(WorkerSettings, "functions")
        assert (
            "analysi.alert_analysis.worker.process_alert_analysis"
            in WorkerSettings.functions
        )

    @patch.dict(
        os.environ, {"ALERT_WORKER_MAX_JOBS": "5", "ALERT_WORKER_TIMEOUT": "300"}
    )
    def test_custom_worker_settings(self):
        """Test custom worker settings from environment."""
        # Need to reload both config and worker modules to pick up new env vars
        import importlib

        from analysi.alert_analysis import config, worker

        importlib.reload(config)
        importlib.reload(worker)

        # WorkerSettings now uses AlertAnalysisConfig
        assert worker.WorkerSettings.max_jobs == 5
        assert worker.WorkerSettings.job_timeout == 300


@pytest.mark.asyncio
class TestProcessAlertAnalysis:
    """Test the main ARQ job function."""

    @patch("analysi.alert_analysis.worker.AlertAnalysisDB")
    @patch("analysi.alert_analysis.worker.BackendAPIClient")
    @pytest.mark.asyncio
    async def test_successful_analysis(self, mock_api_client_class, mock_db_class):
        """Test successful alert analysis processing."""
        # Arrange
        ctx = {"redis": MagicMock()}
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"

        # Mock database
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.close = AsyncMock()
        mock_db_class.return_value = mock_db

        # Mock API client
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
        mock_api_client_class.return_value = mock_api_client

        with patch(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline"
        ) as mock_pipeline_class:
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = {
                "status": "completed",  # Pipeline returns status
                "disposition_id": "disp-789",
                "confidence": 85,
                "summary": "Test summary",
            }
            mock_pipeline_class.return_value = mock_pipeline

            # Act
            result = await process_alert_analysis(ctx, tenant_id, alert_id, analysis_id)

            # Assert
            assert result["status"] == "completed"
            assert result["analysis_id"] == analysis_id
            assert "result" in result
            mock_pipeline_class.assert_called_once_with(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                actor_user_id=None,
            )
            mock_pipeline.execute.assert_called_once()
            # Worker uses API client for status updates
            mock_api_client.update_analysis_status.assert_called_once_with(
                tenant_id, analysis_id, "running"
            )
            # Worker updates alert status after successful completion via API
            mock_api_client.update_alert_analysis_status.assert_called_once_with(
                tenant_id, alert_id, "completed"
            )

    @patch("analysi.alert_analysis.worker.AlertAnalysisDB")
    @patch("analysi.alert_analysis.worker.BackendAPIClient")
    @pytest.mark.asyncio
    async def test_analysis_failure(self, mock_api_client_class, mock_db_class):
        """Test alert analysis failure handling."""
        # Arrange
        ctx = {"redis": MagicMock()}
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"

        # Mock database
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        mock_db.close = AsyncMock()
        mock_db_class.return_value = mock_db

        # Mock API client
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
        mock_api_client_class.return_value = mock_api_client

        with patch(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline"
        ) as mock_pipeline_class:
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.side_effect = Exception("Pipeline execution failed")
            mock_pipeline_class.return_value = mock_pipeline

            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                await process_alert_analysis(ctx, tenant_id, alert_id, analysis_id)

            assert str(exc_info.value) == "Pipeline execution failed"
            mock_pipeline.execute.assert_called_once()
            # The error message is wrapped with more context in the worker - check via API
            status_calls = [
                call
                for call in mock_api_client.update_analysis_status.call_args_list
                if call[0][2] == "failed"
            ]
            assert len(status_calls) > 0, "Expected 'failed' status call via API"

    @patch("analysi.alert_analysis.worker.AlertAnalysisDB")
    @patch("analysi.alert_analysis.worker.BackendAPIClient")
    @pytest.mark.asyncio
    async def test_context_validation(self, mock_api_client_class, mock_db_class):
        """Test that context is properly passed to pipeline."""
        # Arrange
        ctx = {"redis": MagicMock(), "job_id": "job-999"}
        tenant_id = "tenant-xyz"
        alert_id = "alert-aaa"
        analysis_id = "analysis-bbb"

        # Mock database
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        mock_db.close = AsyncMock()
        mock_db_class.return_value = mock_db

        # Mock API client
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
        mock_api_client_class.return_value = mock_api_client

        with patch(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline"
        ) as mock_pipeline_class:
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = {"status": "completed"}
            mock_pipeline_class.return_value = mock_pipeline

            # Act
            await process_alert_analysis(ctx, tenant_id, alert_id, analysis_id)

            # Assert
            mock_pipeline_class.assert_called_once_with(
                tenant_id=tenant_id,
                alert_id=alert_id,
                analysis_id=analysis_id,
                actor_user_id=None,
            )

    @patch("analysi.alert_analysis.worker.AlertAnalysisDB")
    @patch("analysi.alert_analysis.worker.BackendAPIClient")
    @pytest.mark.asyncio
    async def test_process_alert_analysis_with_error_stores_error_message(
        self, mock_api_client_class, mock_db_class
    ):
        """Test that error messages are stored when analysis fails."""
        # Arrange
        ctx = {"db_session": MagicMock()}
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        error_message = "Failed to connect to LLM service"

        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.close = AsyncMock()
        mock_db_class.return_value = mock_db

        # Mock API client
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
        mock_api_client_class.return_value = mock_api_client

        with patch(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline"
        ) as mock_pipeline_class:
            mock_pipeline = AsyncMock()
            mock_pipeline.execute.side_effect = Exception(error_message)
            mock_pipeline_class.return_value = mock_pipeline

            # Act & Assert - Should raise the exception
            with pytest.raises(Exception) as exc_info:
                await process_alert_analysis(ctx, tenant_id, alert_id, analysis_id)

            assert str(exc_info.value) == error_message

            # Verify error was passed to API with enhanced message
            # The worker wraps LLM errors with "LLM service error:" prefix
            status_calls = [
                call
                for call in mock_api_client.update_analysis_status.call_args_list
                if call[0][2] == "failed"
                and "LLM service error" in (call[1].get("error") or "")
            ]
            assert len(status_calls) > 0, (
                "Expected 'failed' status call with LLM error message"
            )
            mock_api_client.update_alert_analysis_status.assert_called_with(
                tenant_id, alert_id, "failed"
            )


@pytest.mark.asyncio
class TestQueueAlertAnalysis:
    """Test the queue_alert_analysis helper function."""

    @patch("arq.create_pool")
    @pytest.mark.asyncio
    async def test_successful_job_queuing(self, mock_create_pool):
        """Test successful job queuing to Valkey."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"

        mock_redis = AsyncMock()
        mock_job = MagicMock()
        mock_job.job_id = "job-789"
        mock_redis.enqueue_job.return_value = mock_job
        mock_create_pool.return_value = mock_redis

        # Act
        job_id = await queue_alert_analysis(tenant_id, alert_id, analysis_id)

        # Assert
        assert job_id == "job-789"
        mock_create_pool.assert_called_once_with(WorkerSettings.get_redis_settings())
        mock_redis.enqueue_job.assert_called_once_with(
            "analysi.alert_analysis.worker.process_alert_analysis",  # Full module path now
            tenant_id,
            alert_id,
            analysis_id,
            None,  # actor_user_id
        )
        mock_redis.aclose.assert_called_once()

    @patch("arq.create_pool")
    @pytest.mark.asyncio
    async def test_queue_connection_failure(self, mock_create_pool):
        """Test handling of Valkey connection failure."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"

        mock_create_pool.side_effect = ConnectionError("Cannot connect to Valkey")

        # Act & Assert
        with pytest.raises(ConnectionError) as exc_info:
            await queue_alert_analysis(tenant_id, alert_id, analysis_id)

        assert str(exc_info.value) == "Cannot connect to Valkey"
        mock_create_pool.assert_called_once()

    @patch("arq.create_pool")
    @pytest.mark.asyncio
    async def test_queue_cleanup_on_error(self, mock_create_pool):
        """Test that connection is closed even on error."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"

        mock_redis = AsyncMock()
        mock_redis.enqueue_job.side_effect = Exception("Enqueue failed")
        mock_create_pool.return_value = mock_redis

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await queue_alert_analysis(tenant_id, alert_id, analysis_id)

        assert str(exc_info.value) == "Enqueue failed"
        mock_redis.aclose.assert_called_once()  # Ensure cleanup happens

    @patch("arq.create_pool")
    @pytest.mark.asyncio
    async def test_job_id_returned(self, mock_create_pool):
        """Test that job ID is properly returned."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        expected_job_id = "unique-job-id-xyz"

        mock_redis = AsyncMock()
        mock_job = MagicMock()
        mock_job.job_id = expected_job_id
        mock_redis.enqueue_job.return_value = mock_job
        mock_create_pool.return_value = mock_redis

        # Act
        job_id = await queue_alert_analysis(tenant_id, alert_id, analysis_id)

        # Assert
        assert job_id == expected_job_id
