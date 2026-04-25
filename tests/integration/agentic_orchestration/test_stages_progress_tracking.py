"""Integration tests for stage progress tracking during orchestration.

Tests that running orchestration with pluggable stages correctly updates
workflow_generation database entries via the DatabaseProgressCallback.

This tests the full flow:
1. Create workflow_generation record
2. Run orchestration with mock stages
3. Verify database is updated correctly at each stage transition
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.orchestrator import run_orchestration_with_stages
from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.kea_coordination import AnalysisGroup, WorkflowGeneration


class _MockStage:
    """Lightweight stage that completes immediately for testing the orchestrator."""

    def __init__(self, stage: WorkflowGenerationStage, result: dict[str, Any]):
        self.stage = stage
        self._result = result

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._result


def _make_mock_stages() -> list[_MockStage]:
    """Build 4 fast mock stages matching the real pipeline shape."""
    return [
        _MockStage(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            {"runbook": "mock runbook"},
        ),
        _MockStage(
            WorkflowGenerationStage.TASK_PROPOSALS,
            {"task_proposals": []},
        ),
        _MockStage(
            WorkflowGenerationStage.TASK_BUILDING,
            {"tasks_built": []},
        ),
        _MockStage(
            WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
            {"workflow_id": "mock-workflow-id", "workflow_composition": []},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.integration
class TestStagesProgressTracking:
    """Integration tests for orchestration progress tracking via database."""

    @pytest.fixture
    async def test_analysis_group(
        self, integration_test_session: AsyncSession
    ) -> AnalysisGroup:
        """Create a test analysis group."""
        group = AnalysisGroup(
            tenant_id="test-tenant",
            title="Test Analysis Group for Progress Tracking",
        )
        integration_test_session.add(group)
        await integration_test_session.flush()
        await integration_test_session.commit()
        await integration_test_session.refresh(group)
        return group

    @pytest.fixture
    async def test_workflow_generation(
        self,
        integration_test_session: AsyncSession,
        test_analysis_group: AnalysisGroup,
    ) -> WorkflowGeneration:
        """Create a test workflow generation."""
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
        )
        integration_test_session.add(generation)
        await integration_test_session.flush()
        await integration_test_session.commit()
        await integration_test_session.refresh(generation)
        return generation

    @pytest.fixture
    def sample_alert(self):
        """Sample NAS alert for testing."""
        return {
            "id": str(uuid4()),
            "title": "Test Alert for Progress Tracking",
            "severity": "high",
            "rule_name": "Test Rule",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "raw_alert": '{"source": "test"}',
        }

    @pytest.mark.asyncio
    async def test_mock_stages_update_database_progress(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
        sample_alert: dict,
    ):
        """Test that running stages correctly updates database progress.

        Verify that as orchestration progresses through all 4 stages,
        the workflow_generation.current_phase is updated correctly.
        """
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Create progress callback that will update database via REST API
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:

                class TestProgressCallback:
                    """Progress callback that uses test client to update database."""

                    def __init__(self):
                        self.stages_started = []
                        self.stages_completed = []

                    async def on_stage_start(self, stage, metadata):
                        self.stages_started.append(stage)
                        response = await client.patch(
                            f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                            json={"stage": stage.value},
                        )
                        assert response.status_code == 200, (
                            f"Failed to update progress for {stage.value}"
                        )

                    async def on_stage_complete(self, stage, result, metrics):
                        self.stages_completed.append(stage)

                    async def on_stage_error(self, stage, error, partial_metrics):
                        pass

                callback = TestProgressCallback()
                stages = _make_mock_stages()

                initial_state = {
                    "alert": sample_alert,
                    "tenant_id": tenant_id,
                    "run_id": generation_id,
                    "created_by": str(SYSTEM_USER_ID),
                }

                result = await run_orchestration_with_stages(
                    stages=stages,
                    initial_state=initial_state,
                    callback=callback,
                )

            # Verify orchestration completed without errors
            assert result.get("error") is None
            assert result["workflow_id"] == "mock-workflow-id"

            # Verify all stages were started
            assert len(callback.stages_started) == 4
            assert callback.stages_started == [
                WorkflowGenerationStage.RUNBOOK_GENERATION,
                WorkflowGenerationStage.TASK_PROPOSALS,
                WorkflowGenerationStage.TASK_BUILDING,
                WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
            ]

            # Verify database was updated correctly
            await integration_test_session.refresh(test_workflow_generation)
            current_phase = test_workflow_generation.current_phase

            assert current_phase is not None
            phases = current_phase["phases"]
            assert len(phases) == 4

            # After all stages run, first 3 should be completed (implicitly)
            # and last one (workflow_assembly) should be in_progress
            assert phases[0]["stage"] == "runbook_generation"
            assert phases[0]["status"] == "completed"
            assert phases[0]["completed_at"] is not None

            assert phases[1]["stage"] == "task_proposals"
            assert phases[1]["status"] == "completed"
            assert phases[1]["completed_at"] is not None

            assert phases[2]["stage"] == "task_building"
            assert phases[2]["status"] == "completed"
            assert phases[2]["completed_at"] is not None

            assert phases[3]["stage"] == "workflow_assembly"
            assert phases[3]["status"] == "in_progress"
            assert phases[3]["started_at"] is not None

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_database_progress_callback_integration(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test DatabaseProgressCallback directly with real API calls."""
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Simulate what DatabaseProgressCallback does
                stages = [
                    WorkflowGenerationStage.RUNBOOK_GENERATION,
                    WorkflowGenerationStage.TASK_PROPOSALS,
                    WorkflowGenerationStage.TASK_BUILDING,
                    WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
                ]

                for stage in stages:
                    response = await client.patch(
                        f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                        json={"stage": stage.value},
                    )
                    assert response.status_code == 200

                    # Verify database state after each stage
                    await integration_test_session.refresh(test_workflow_generation)
                    phases = test_workflow_generation.current_phase["phases"]

                    stage_index = stages.index(stage)

                    # Current stage should be in_progress
                    assert phases[stage_index]["status"] == "in_progress"
                    assert phases[stage_index]["started_at"] is not None

                    # Previous stages should be completed
                    for i in range(stage_index):
                        assert phases[i]["status"] == "completed"
                        assert phases[i]["completed_at"] is not None

                    # Later stages should be not_started
                    for i in range(stage_index + 1, 4):
                        assert phases[i]["status"] == "not_started"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_orchestration_with_stage_error_updates_database(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
        sample_alert: dict,
    ):
        """Test that stage errors are handled and database reflects partial progress."""
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:

                class TestProgressCallback:
                    """Progress callback for error test."""

                    async def on_stage_start(self, stage, metadata):
                        response = await client.patch(
                            f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                            json={"stage": stage.value},
                        )
                        assert response.status_code == 200

                    async def on_stage_complete(self, stage, result, metrics):
                        pass

                    async def on_stage_error(self, stage, error, partial_metrics):
                        pass

                callback = TestProgressCallback()

                # Create mock stages, but make the last one fail
                stages = _make_mock_stages()

                class _FailingStage:
                    stage = WorkflowGenerationStage.WORKFLOW_ASSEMBLY

                    async def execute(self, state):
                        raise ValueError("Simulated workflow assembly failure")

                stages[3] = _FailingStage()

                initial_state = {
                    "alert": sample_alert,
                    "tenant_id": tenant_id,
                    "run_id": generation_id,
                    "created_by": str(SYSTEM_USER_ID),
                }

                result = await run_orchestration_with_stages(
                    stages=stages,
                    initial_state=initial_state,
                    callback=callback,
                )

            # Verify error was captured
            assert result.get("error") is not None
            assert "Simulated workflow assembly failure" in result["error"]

            # Verify database shows progress up to the failing stage
            await integration_test_session.refresh(test_workflow_generation)
            phases = test_workflow_generation.current_phase["phases"]

            # First 3 stages should be completed (they ran successfully)
            assert phases[0]["status"] == "completed"
            assert phases[1]["status"] == "completed"
            assert phases[2]["status"] == "completed"

            # Last stage was started before it failed
            assert phases[3]["status"] == "in_progress"
            assert phases[3]["started_at"] is not None

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_fast_mock_stages_complete_quickly(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
        sample_alert: dict,
    ):
        """Test that mock stages complete very quickly (no AI calls)."""
        import time

        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:

                class TestProgressCallback:
                    async def on_stage_start(self, stage, metadata):
                        await client.patch(
                            f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                            json={"stage": stage.value},
                        )

                    async def on_stage_complete(self, stage, result, metrics):
                        pass

                    async def on_stage_error(self, stage, error, partial_metrics):
                        pass

                callback = TestProgressCallback()
                stages = _make_mock_stages()

                initial_state = {
                    "alert": sample_alert,
                    "tenant_id": tenant_id,
                    "run_id": generation_id,
                    "created_by": str(SYSTEM_USER_ID),
                }

                start = time.perf_counter()
                result = await run_orchestration_with_stages(
                    stages=stages,
                    initial_state=initial_state,
                    callback=callback,
                )
                duration_ms = (time.perf_counter() - start) * 1000

            # Verify completion
            assert result.get("error") is None
            assert result["workflow_id"] == "mock-workflow-id"

            # Should complete in under 500ms (includes DB updates)
            assert duration_ms < 500, (
                f"Orchestration took {duration_ms}ms, expected <500ms"
            )

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_metrics_aggregated_correctly(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
        sample_alert: dict,
    ):
        """Test that metrics are correctly aggregated from all stages."""
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:

                class TestProgressCallback:
                    async def on_stage_start(self, stage, metadata):
                        await client.patch(
                            f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                            json={"stage": stage.value},
                        )

                    async def on_stage_complete(self, stage, result, metrics):
                        pass

                    async def on_stage_error(self, stage, error, partial_metrics):
                        pass

                callback = TestProgressCallback()
                stages = _make_mock_stages()

                initial_state = {
                    "alert": sample_alert,
                    "tenant_id": tenant_id,
                    "run_id": generation_id,
                    "created_by": str(SYSTEM_USER_ID),
                }

                result = await run_orchestration_with_stages(
                    stages=stages,
                    initial_state=initial_state,
                    callback=callback,
                )

            # Verify metrics
            assert "metrics" in result
            assert len(result["metrics"]) == 4  # One per stage

            # Each metric should have duration (framework-measured)
            for metric in result["metrics"]:
                assert metric.duration_ms >= 0
                # Mock stages have zero cost
                assert metric.total_cost_usd == 0.0

        finally:
            app.dependency_overrides.clear()
