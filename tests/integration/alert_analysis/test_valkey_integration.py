"""
Integration tests for Alert Analysis with real Valkey queue.
Tests the actual queueing and processing with ARQ and Valkey.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from arq import create_pool

from analysi.alert_analysis.worker import (
    process_alert_analysis,
    queue_alert_analysis,
)
from analysi.config.valkey_db import ValkeyDBConfig
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
)
from analysi.schemas.alert import AlertCreate
from analysi.services.alert_service import AlertAnalysisService, AlertService

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


def _test_redis_settings():
    """Single source of truth for test Valkey connection settings."""
    return ValkeyDBConfig.get_redis_settings(
        database=ValkeyDBConfig.TEST_ALERT_PROCESSING_DB,
        test_mode=True,
    )


@pytest.mark.integration
class TestValkeyIntegration:
    """Test Valkey/Redis queue integration."""

    @pytest.mark.asyncio
    async def test_queue_and_retrieve_job(self, arq_pool):
        """Test that we can queue a job and retrieve it from Valkey."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        # Act - Queue the job
        job = await arq_pool.enqueue_job(
            "process_alert_analysis", tenant_id, alert_id, analysis_id
        )

        # Assert
        assert job is not None
        assert job.job_id is not None

        # Verify job is in queue (ARQ uses Redis directly for job storage)
        job_key = f"arq:job:{job.job_id}"
        job_data = await arq_pool.get(job_key)
        assert job_data is not None

    @pytest.mark.asyncio
    async def test_queue_alert_analysis_helper(self, valkey_cleanup):
        """Test the queue_alert_analysis helper function with real Valkey."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        # Act
        job_id = await queue_alert_analysis(tenant_id, alert_id, analysis_id)

        # Assert
        assert job_id is not None

        # Verify job exists in Valkey
        pool = await create_pool(_test_redis_settings())
        try:
            job_key = f"arq:job:{job_id}"
            job_data = await pool.get(job_key)
            assert job_data is not None
        finally:
            await pool.aclose()

    @pytest.mark.asyncio
    async def test_multiple_jobs_queued(self, arq_pool):
        """Test queueing multiple jobs to Valkey."""
        # Arrange
        jobs = []

        # Act - Queue multiple jobs
        for i in range(5):
            job = await arq_pool.enqueue_job(
                "process_alert_analysis", f"tenant-{i}", str(uuid4()), str(uuid4())
            )
            jobs.append(job)

        # Assert
        assert len(jobs) == 5
        for job in jobs:
            assert job.job_id is not None

        # Verify all jobs are in queue
        for job in jobs:
            job_key = f"arq:job:{job.job_id}"
            job_data = await arq_pool.get(job_key)
            assert job_data is not None


@pytest.mark.integration
class TestEndToEndAlertAnalysis:
    """End-to-end integration test with real components."""

    @pytest.mark.asyncio
    async def test_alert_creation_to_analysis_queuing(
        self, integration_test_session, valkey_cleanup
    ):
        """
        Test full flow from alert creation to analysis job queuing.
        Uses real database and Valkey queue.
        """
        # Arrange
        tenant_id = "test-tenant"
        alert_repo = AlertRepository(integration_test_session)
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        disposition_repo = None  # Not needed for this test

        service = AlertService(
            alert_repo, analysis_repo, disposition_repo, integration_test_session
        )

        alert_data = AlertCreate(
            source_vendor="TestVendor",
            source_product="TestProduct",
            severity="high",
            title="Test Alert for Valkey Integration",
            description="Testing alert analysis with real Valkey queue",
            raw_alert="Raw alert data: Suspicious activity detected from user test.user@example.com",
            triggering_event_time=datetime.now(UTC),
            entities=[
                {
                    "entity_type": "user",
                    "entity_value": "test.user@example.com",
                    "context": {"department": "IT"},
                }
            ],
            iocs=[
                {
                    "type": "ip",
                    "value": "192.168.1.100",
                }
            ],
        )

        # Act
        # Step 1: Create alert
        alert = await service.create_alert(tenant_id, alert_data)
        await integration_test_session.commit()

        # Step 2: Start analysis (creates analysis record)
        analysis_service = AlertAnalysisService(
            analysis_repo, alert_repo, integration_test_session
        )
        analysis = await analysis_service.start_analysis(tenant_id, alert.alert_id)
        await integration_test_session.commit()

        # Step 3: Queue analysis job to Valkey
        job_id = await queue_alert_analysis(
            tenant_id, str(alert.alert_id), str(analysis.id)
        )

        # Assert
        assert alert.alert_id is not None
        assert analysis.id is not None
        assert analysis.alert_id == alert.alert_id
        assert analysis.status == "running"
        assert job_id is not None

        # Verify job is in Valkey queue (uses test DB 100)
        pool = await create_pool(_test_redis_settings())
        try:
            job_key = f"arq:job:{job_id}"
            job_data = await pool.get(job_key)
            assert job_data is not None
        finally:
            await pool.aclose()

    @pytest.mark.asyncio
    async def test_worker_process_with_mock_pipeline(
        self, integration_test_session, arq_pool, monkeypatch
    ):
        """
        Test worker processing with mocked pipeline steps.
        Uses real Valkey for job queue but mocks the pipeline execution.
        """
        # Arrange
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        # Mock the pipeline to avoid needing full infrastructure
        class MockPipeline:
            def __init__(self, *args, **kwargs):
                pass

            async def execute(self):
                return {
                    "disposition_id": str(uuid4()),
                    "confidence": 85,
                    "summary": "Test analysis completed",
                }

        monkeypatch.setattr(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline", MockPipeline
        )

        # Mock BackendAPIClient — no API server in test env
        mock_api = AsyncMock()
        mock_api.update_analysis_status.return_value = True
        mock_api.update_alert_analysis_status.return_value = True
        monkeypatch.setattr(
            "analysi.alert_analysis.worker.BackendAPIClient",
            lambda: mock_api,
        )

        # Create mock context (what ARQ provides to workers)
        ctx = {"redis": arq_pool}

        # Act
        result = await process_alert_analysis(ctx, tenant_id, alert_id, analysis_id)

        # Assert
        assert result["status"] == "completed"
        assert result["analysis_id"] == analysis_id
        assert "result" in result
        assert result["result"]["confidence"] == 85
