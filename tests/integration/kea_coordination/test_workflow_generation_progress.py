"""Integration tests for workflow generation progress tracking.

Tests that the REST API endpoint for updating workflow generation progress
correctly implements pre-populated phase tracking:
- All 4 phases are initialized on first update
- Marking a stage in_progress auto-completes previous stages
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.kea_coordination import AnalysisGroup, WorkflowGeneration


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowGenerationProgress:
    """Test workflow generation progress tracking API."""

    @pytest.fixture
    async def test_analysis_group(
        self, integration_test_session: AsyncSession
    ) -> AnalysisGroup:
        """Create a test analysis group."""
        group = AnalysisGroup(
            tenant_id="test-tenant",
            title="Test Analysis Group",
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

    @pytest.mark.asyncio
    async def test_update_progress_initializes_all_phases(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that first progress update initializes all 4 phases."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )

            # Assert HTTP response
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["status"] == "running"
            assert data["progress"] is not None

            # All 4 phases should be initialized
            phases = data["progress"]["phases"]
            assert len(phases) == 4

            # First phase should be in_progress
            assert phases[0]["stage"] == "runbook_generation"
            assert phases[0]["status"] == "in_progress"
            assert phases[0]["started_at"] is not None

            # Other phases should be not_started
            assert phases[1]["stage"] == "task_proposals"
            assert phases[1]["status"] == "not_started"
            assert phases[2]["stage"] == "task_building"
            assert phases[2]["status"] == "not_started"
            assert phases[3]["stage"] == "workflow_assembly"
            assert phases[3]["status"] == "not_started"

            # Assert database was updated
            await integration_test_session.refresh(test_workflow_generation)
            assert test_workflow_generation.current_phase is not None
            assert len(test_workflow_generation.current_phase["phases"]) == 4

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_auto_completes_previous_stages(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that marking a stage in_progress auto-completes previous stages."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id
        stages = [
            "runbook_generation",
            "task_proposals",
            "task_building",
            "workflow_assembly",
        ]

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Act - Progress through all stages
                for i, stage in enumerate(stages):
                    response = await client.patch(
                        f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                        json={"stage": stage},
                    )

                    # Assert HTTP response
                    assert response.status_code == 200, f"Stage {stage} failed"
                    data = response.json()["data"]
                    phases = data["progress"]["phases"]

                    # Always have all 4 phases
                    assert len(phases) == 4

                    # All previous phases should be completed
                    for j in range(i):
                        assert phases[j]["status"] == "completed", (
                            f"Phase {j} should be completed"
                        )
                        assert phases[j]["completed_at"] is not None, (
                            f"Phase {j} should have completed_at"
                        )

                    # Current phase should be in_progress
                    assert phases[i]["stage"] == stage
                    assert phases[i]["status"] == "in_progress"
                    assert phases[i]["started_at"] is not None

                    # Later phases should be not_started
                    for j in range(i + 1, 4):
                        assert phases[j]["status"] == "not_started"

            # Final verification from database
            await integration_test_session.refresh(test_workflow_generation)
            phases = test_workflow_generation.current_phase["phases"]
            assert len(phases) == 4

            # First 3 phases completed
            for phase in phases[:3]:
                assert phase["status"] == "completed"
                assert phase["completed_at"] is not None

            # Last phase in_progress
            assert phases[3]["stage"] == "workflow_assembly"
            assert phases[3]["status"] == "in_progress"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_progress_with_tasks_count(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test updating progress with metadata (tasks_count)."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "task_building", "tasks_count": 5},
                )

            # Assert HTTP response
            assert response.status_code == 200
            data = response.json()["data"]
            phases = data["progress"]["phases"]

            # task_building is at index 2
            assert phases[2]["stage"] == "task_building"
            assert phases[2]["status"] == "in_progress"
            assert phases[2]["tasks_count"] == 5

            # Previous phases should be auto-completed
            assert phases[0]["status"] == "completed"
            assert phases[1]["status"] == "completed"

            # Assert database was updated
            await integration_test_session.refresh(test_workflow_generation)
            assert (
                test_workflow_generation.current_phase["phases"][2]["tasks_count"] == 5
            )

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_progress_nonexistent_generation(
        self, integration_test_session: AsyncSession
    ):
        """Test updating progress for non-existent generation returns 404."""
        # Arrange
        fake_generation_id = str(uuid4())
        tenant_id = "test-tenant"

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{fake_generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )

            # Assert
            assert response.status_code == 404

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_workspace_path_early(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test updating workspace_path early for failed generation debugging."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id
        workspace_path = "/tmp/kea-test-workspace-abc123"

        # Verify initial state
        assert test_workflow_generation.workspace_path == "/tmp/unknown"

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act - Update only workspace_path (no stage)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"workspace_path": workspace_path},
                )

            # Assert HTTP response
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["workspace_path"] == workspace_path
            assert data["status"] == "running"  # Other fields unchanged

            # Assert database was updated
            await integration_test_session.refresh(test_workflow_generation)
            assert test_workflow_generation.workspace_path == workspace_path

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_workspace_path_and_stage_together(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test updating both workspace_path and stage in single request."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id
        workspace_path = "/tmp/kea-test-workspace-xyz789"

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act - Update both fields
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={
                        "workspace_path": workspace_path,
                        "stage": "task_building",
                        "tasks_count": 3,
                    },
                )

            # Assert HTTP response
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["workspace_path"] == workspace_path
            phases = data["progress"]["phases"]
            assert phases[2]["stage"] == "task_building"
            assert phases[2]["tasks_count"] == 3

            # Assert database was updated
            await integration_test_session.refresh(test_workflow_generation)
            assert test_workflow_generation.workspace_path == workspace_path
            assert (
                test_workflow_generation.current_phase["phases"][2]["stage"]
                == "task_building"
            )
            assert (
                test_workflow_generation.current_phase["phases"][2]["tasks_count"] == 3
            )

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_preserves_status_field(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that progress updates preserve other fields like status."""
        # Arrange
        generation_id = str(test_workflow_generation.id)
        tenant_id = test_workflow_generation.tenant_id

        # Set initial status
        test_workflow_generation.status = "running"
        await integration_test_session.commit()

        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Act - Progress through two stages
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # First stage
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )
                assert response.status_code == 200

                # Second stage
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "task_proposals"},
                )

            # Assert - Status unchanged, progress accumulated correctly
            assert response.status_code == 200
            await integration_test_session.refresh(test_workflow_generation)
            assert test_workflow_generation.status == "running"

            phases = test_workflow_generation.current_phase["phases"]
            assert len(phases) == 4
            assert phases[0]["status"] == "completed"  # runbook_generation completed
            assert phases[1]["status"] == "in_progress"  # task_proposals in_progress
            assert phases[2]["status"] == "not_started"
            assert phases[3]["status"] == "not_started"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_skip_stages_auto_completes(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that skipping stages auto-completes all previous stages (edge case)."""
        # Arrange
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
                # Start at stage 1
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )
                assert response.status_code == 200

                # Skip directly to stage 3 (task_building), skipping task_proposals
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "task_building", "tasks_count": 4},
                )

            # Assert - all previous stages completed
            assert response.status_code == 200
            data = response.json()["data"]
            phases = data["progress"]["phases"]

            assert phases[0]["status"] == "completed"  # runbook_generation
            assert phases[0]["completed_at"] is not None
            assert (
                phases[1]["status"] == "completed"
            )  # task_proposals (skipped but completed)
            assert phases[1]["completed_at"] is not None
            assert phases[2]["status"] == "in_progress"  # task_building
            assert phases[2]["tasks_count"] == 4
            assert phases[3]["status"] == "not_started"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_same_stage_twice_idempotent(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that calling the same stage twice is idempotent (edge case)."""
        # Arrange
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
                # Call runbook_generation first time
                response1 = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )
                assert response1.status_code == 200
                first_started_at = response1.json()["data"]["progress"]["phases"][0][
                    "started_at"
                ]

                # Call same stage again (e.g., retry scenario)
                response2 = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "runbook_generation"},
                )

            # Assert - should preserve original started_at
            assert response2.status_code == 200
            data = response2.json()["data"]
            phases = data["progress"]["phases"]

            assert phases[0]["status"] == "in_progress"
            assert phases[0]["started_at"] == first_started_at  # Not overwritten
            # Other phases unchanged
            assert phases[1]["status"] == "not_started"
            assert phases[2]["status"] == "not_started"
            assert phases[3]["status"] == "not_started"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_final_stage_completes_all_previous(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that final stage (workflow_assembly) completes all previous stages."""
        # Arrange
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
                # Jump directly to final stage
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "workflow_assembly"},
                )

            # Assert - all previous stages completed
            assert response.status_code == 200
            data = response.json()["data"]
            phases = data["progress"]["phases"]

            assert phases[0]["status"] == "completed"
            assert phases[0]["completed_at"] is not None
            assert phases[1]["status"] == "completed"
            assert phases[1]["completed_at"] is not None
            assert phases[2]["status"] == "completed"
            assert phases[2]["completed_at"] is not None
            assert phases[3]["status"] == "in_progress"  # workflow_assembly
            assert phases[3]["started_at"] is not None

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_progress_invalid_stage_returns_422(
        self,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test that invalid stage name returns 422 validation error."""
        # Arrange
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
                # Try invalid stage name
                response = await client.patch(
                    f"/v1/{tenant_id}/workflow-generations/{generation_id}/progress",
                    json={"stage": "invalid_stage_name"},
                )

            # Assert - should return 422 validation error
            assert response.status_code == 422

        finally:
            app.dependency_overrides.clear()
