"""
End-to-end integration tests for Alert Analysis.
Tests the complete flow from alert creation to disposition assignment.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
from analysi.alert_analysis.worker import process_alert_analysis
from analysi.models.alert import Alert, Disposition
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertAnalysisEndToEnd:
    """Test complete alert analysis flow end-to-end."""

    @pytest.fixture
    async def test_dispositions(self, integration_test_session: AsyncSession):
        """Ensure test dispositions exist."""
        # They should already be seeded in conftest.py
        # This fixture just verifies they exist
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(Disposition).where(Disposition.is_system.is_(True))
        )
        dispositions = result.scalars().all()
        assert len(dispositions) > 0, "System dispositions should be seeded"
        return dispositions

    @pytest.fixture
    async def test_alert(self, integration_test_session: AsyncSession):
        """Create a test alert for end-to-end testing."""
        alert_repo = AlertRepository(integration_test_session)

        alert = await alert_repo.create_with_deduplication(
            tenant_id="e2e-tenant",
            raw_data_hash=f"e2e_hash_{uuid4()}",
            human_readable_id="AID-E2E-1",
            title="Suspicious Login from Unknown Location",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            source_vendor="TestVendor",
            source_product="TestProduct",
            raw_data='{"source": "test", "details": "suspicious activity"}',
            raw_data_hash_algorithm="SHA-256",
            finding_info={"title": "Suspicious Login", "types": ["authentication"]},
            ocsf_metadata={
                "product": {"name": "TestProduct", "vendor_name": "TestVendor"}
            },
            observables=[
                {"type_id": 2, "type": "IP Address", "value": "192.168.1.100"},
                {"type_id": 4, "type": "Email Address", "value": "user@example.com"},
            ],
            severity_id=4,
            status_id=1,
        )

        await integration_test_session.commit()
        return alert

    @pytest.mark.asyncio
    async def test_full_analysis_lifecycle(
        self,
        integration_test_session: AsyncSession,
        test_alert: Alert,
        test_dispositions,
    ):
        """Test complete analysis lifecycle from start to disposition."""
        # Arrange
        analysis_repo = AlertAnalysisRepository(integration_test_session)

        # Step 1: Create analysis record
        analysis = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )
        await integration_test_session.commit()

        assert analysis is not None
        assert analysis.status == "running"
        assert analysis.alert_id == test_alert.id

        # Step 2: Mock the pipeline and API client (no API server in test env)
        with (
            patch(
                "analysi.alert_analysis.worker.AlertAnalysisPipeline"
            ) as mock_pipeline_class,
            patch("analysi.alert_analysis.worker.BackendAPIClient") as mock_api_class,
        ):
            # Mock API client — process_alert_analysis uses it to update status
            mock_api = AsyncMock()
            mock_api.update_analysis_status.return_value = True
            mock_api.update_alert_analysis_status.return_value = True
            mock_api_class.return_value = mock_api

            mock_pipeline = AsyncMock()
            mock_pipeline.execute.return_value = {
                "disposition_id": test_dispositions[0].id,
                "confidence": 85,
                "short_summary": "Suspicious login detected",
                "long_summary": "User logged in from unusual location",
            }
            mock_pipeline_class.return_value = mock_pipeline

            # Step 3: Execute the worker job
            ctx = {"redis": MagicMock()}
            result = await process_alert_analysis(
                ctx, "e2e-tenant", str(test_alert.id), str(analysis.id)
            )

            # Assert worker result
            assert result["status"] == "completed"
            assert result["analysis_id"] == str(analysis.id)

            # Verify pipeline was called correctly
            mock_pipeline_class.assert_called_once_with(
                tenant_id="e2e-tenant",
                alert_id=str(test_alert.id),
                analysis_id=str(analysis.id),
                actor_user_id=None,
            )
            mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_pipeline_execution(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test that pipeline can resume from partial completion."""
        # Arrange
        analysis_repo = AlertAnalysisRepository(integration_test_session)

        # Create analysis with some steps already completed
        analysis = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )

        # Mark some steps as completed
        await analysis_repo.update_step_progress(
            analysis_id=analysis.id, step="pre_triage", completed=True, error=None
        )

        analysis.current_step = "workflow_builder"
        analysis.status = "running"
        await integration_test_session.commit()

        # Act - Create pipeline and check idempotency
        pipeline = AlertAnalysisPipeline(
            tenant_id="e2e-tenant",
            alert_id=str(test_alert.id),
            analysis_id=str(analysis.id),
        )

        # Mock the database, step execution, and status updates (no API server in CI)
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
            "workflow_builder": {"completed": False},
            "workflow_execution": {"completed": False},
            "final_disposition_update": {"completed": False},
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        with (
            patch.object(pipeline, "_execute_step") as mock_execute,
            patch.object(pipeline, "_update_status", new_callable=AsyncMock),
        ):
            mock_execute.return_value = {"result": "test"}

            # Execute pipeline
            await pipeline.execute()

            # Assert - Should only execute 3 uncompleted steps
            assert mock_execute.call_count == 3

    @pytest.mark.asyncio
    async def test_reanalysis_scenario(
        self,
        integration_test_session: AsyncSession,
        test_alert: Alert,
        test_dispositions,
    ):
        """Test analyzing the same alert multiple times."""
        # Arrange
        analysis_repo = AlertAnalysisRepository(integration_test_session)

        # Create first analysis
        analysis1 = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )

        # Complete first analysis
        await analysis_repo.mark_completed(
            analysis_id=analysis1.id,
            disposition_id=test_dispositions[0].id,  # Use actual disposition ID
            confidence=75,
            short_summary="First analysis",
            long_summary="First detailed analysis",
        )
        await integration_test_session.commit()

        # Create second analysis (re-analysis)
        analysis2 = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )
        await integration_test_session.commit()

        # Assert
        assert analysis1.id != analysis2.id
        assert analysis1.alert_id == analysis2.alert_id
        assert analysis1.status == "completed"
        assert analysis2.status == "running"

        # Get analysis history
        history = await analysis_repo.get_analysis_history(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )

        assert len(history) == 2
        # History should be ordered by created_at desc
        assert history[0].id == analysis2.id  # Most recent
        assert history[1].id == analysis1.id  # Older

    @pytest.mark.asyncio
    async def test_pipeline_with_workflow_execution(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test pipeline executing a workflow and creating artifacts."""
        # This test simulates the workflow execution step

        # Arrange
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )
        await integration_test_session.commit()

        # Mock the workflow execution step (now uses direct DB calls, not REST)
        from uuid import uuid4

        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        workflow_run_id = uuid4()
        workflow_id = str(uuid4())

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        # Mock session.execute → result.fetchone() for the status check
        # after workflow execution. Return a completed status row.
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.status = "completed"
        mock_row.error_message = None
        mock_result.fetchone.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the helper methods to avoid actual DB calls
        with (
            patch.object(
                step,
                "_prepare_workflow_input",
                new=AsyncMock(return_value={"test": "data"}),
            ),
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=workflow_run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            # Act - Use the actual method signature from our implementation
            result = await step.execute(
                tenant_id="e2e-tenant",
                alert_id=str(test_alert.id),
                analysis_id=str(analysis.id),
                workflow_id=workflow_id,
            )

        # Assert - Should return the workflow run ID
        assert result == str(workflow_run_id)

    @pytest.mark.asyncio
    async def test_disposition_matching_with_llm(
        self,
        integration_test_session: AsyncSession,
        test_alert: Alert,
        test_dispositions,
    ):
        """Test disposition matching using LLM."""
        # Arrange
        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        step = FinalDispositionUpdateStep()

        # Replace the clients with mocks
        mock_api = AsyncMock()
        mock_llm = AsyncMock()
        step.api_client = mock_api
        step.llm_client = mock_llm
        mock_api.get_artifact.return_value = {
            "content": "This appears to be a false positive alert"
        }
        mock_api.get_dispositions.return_value = [
            {
                "disposition_id": str(d.id),
                "display_name": d.display_name,
                "category": d.category,
                "subcategory": d.subcategory,
            }
            for d in test_dispositions[:5]  # Use first 5 dispositions
        ]

        # Mock LLM to select "False Positive" disposition
        false_positive = next(
            (d for d in test_dispositions if "False Positive" in d.display_name),
            test_dispositions[0],
        )
        mock_llm.match_disposition.return_value = str(false_positive.id)
        mock_llm.extract_confidence.return_value = 90

        # Act
        # Create a proper analysis for this test
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )
        await integration_test_session.commit()

        # Mock the database update method to avoid actual DB writes
        with patch.object(step, "_complete_analysis", new=AsyncMock()):
            # Mock get_artifacts_by_workflow_run to return test artifacts
            mock_api.get_artifacts_by_workflow_run.return_value = [
                {
                    "name": "Disposition",
                    "content": "False Positive / Detection Logic Error",
                }
            ]

            result = await step.execute(
                tenant_id="e2e-tenant",
                alert_id=str(test_alert.id),
                analysis_id=str(analysis.id),
                workflow_run_id=str(uuid4()),
            )

        # Assert - The actual matching logic looks for keywords
        # Since we have "False Positive" in the content, it should match a false positive disposition
        assert "disposition_id" in result
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_error_recovery(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test error recovery and retry mechanisms."""
        # Arrange
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis = await analysis_repo.create_analysis(
            alert_id=test_alert.id, tenant_id="e2e-tenant"
        )

        # Mark a step as failed
        await analysis_repo.update_step_progress(
            analysis_id=analysis.id,
            step="workflow_execution",
            completed=False,
            error="Workflow service unavailable",
        )

        analysis.status = "failed"
        analysis.current_step = "workflow_execution"
        await integration_test_session.commit()

        # Act - Retry the pipeline
        pipeline = AlertAnalysisPipeline(
            tenant_id="e2e-tenant",
            alert_id=str(test_alert.id),
            analysis_id=str(analysis.id),
        )

        # Mock successful retry - mock both DB and API client
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": test_alert.id}
        mock_db.get_analysis.return_value = {"id": analysis.id, "status": "failed"}
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
            "workflow_builder": {
                "completed": True,
                "result": {"selected_workflow": "test-workflow"},
            },
            "workflow_execution": {"completed": False, "error": "Previous error"},
            "final_disposition_update": {"completed": False},
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.initialize_steps_progress = AsyncMock()
        pipeline.db = mock_db

        # Mock the API client to succeed
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)

        with patch.object(pipeline, "_execute_step") as mock_execute:
            with patch(
                "analysi.alert_analysis.clients.BackendAPIClient",
                return_value=mock_api_client,
            ):
                mock_execute.return_value = {"result": "success"}

                # Execute pipeline (retry)
                await pipeline.execute()

                # Assert - Should retry from failed step
                assert (
                    mock_execute.call_count == 2
                )  # workflow_execution + final_disposition_update
                # Verify API client was used for status updates
                mock_api_client.update_analysis_status.assert_called()
