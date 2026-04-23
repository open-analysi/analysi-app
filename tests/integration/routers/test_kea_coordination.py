"""Integration tests for Kea Coordination API endpoints."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestAnalysisGroupEndpoints:
    """Test Analysis Group REST API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_analysis_group(self, client: AsyncClient):
        """Test creating an analysis group."""
        response = await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Suspicious Login Attempts"},
        )
        assert response.status_code == 201

        data = response.json()["data"]
        assert data["title"] == "Suspicious Login Attempts"
        assert data["tenant_id"] == "default"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_analysis_group_duplicate_title(self, client: AsyncClient):
        """Test that duplicate titles within same tenant are rejected."""
        # Create first group
        response1 = await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Malware Detection"},
        )
        assert response1.status_code == 201

        # Attempt duplicate
        response2 = await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Malware Detection"},
        )
        assert response2.status_code == 409  # Conflict

    @pytest.mark.asyncio
    async def test_create_analysis_group_same_title_different_tenant(
        self, client: AsyncClient
    ):
        """Test that same title is allowed across different tenants."""
        # Create for tenant-a
        response_a = await client.post(
            "/v1/tenant-a/analysis-groups",
            json={"title": "Phishing Emails"},
        )
        assert response_a.status_code == 201

        # Create for tenant-b (should succeed)
        response_b = await client.post(
            "/v1/tenant-b/analysis-groups",
            json={"title": "Phishing Emails"},
        )
        assert response_b.status_code == 201

        # Verify different IDs
        assert response_a.json()["data"]["id"] != response_b.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_get_analysis_group_by_id(self, client: AsyncClient):
        """Test retrieving a specific analysis group."""
        # Create group
        create_response = await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Data Exfiltration"},
        )
        assert create_response.status_code == 201
        group_id = create_response.json()["data"]["id"]

        # Get by ID
        get_response = await client.get(f"/v1/default/analysis-groups/{group_id}")
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        assert data["id"] == group_id
        assert data["title"] == "Data Exfiltration"

    @pytest.mark.asyncio
    async def test_get_analysis_group_not_found(self, client: AsyncClient):
        """Test getting non-existent analysis group returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/v1/default/analysis-groups/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_analysis_group_tenant_isolation(self, client: AsyncClient):
        """Test that groups are isolated by tenant."""
        # Create group for tenant-a
        create_response = await client.post(
            "/v1/tenant-a/analysis-groups",
            json={"title": "Tenant A Group"},
        )
        assert create_response.status_code == 201
        group_id = create_response.json()["data"]["id"]

        # Try to access from tenant-b (should not find it)
        get_response = await client.get(f"/v1/tenant-b/analysis-groups/{group_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_analysis_groups(self, client: AsyncClient):
        """Test listing analysis groups."""
        # Create multiple groups
        await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Group 1"},
        )
        await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Group 2"},
        )

        # List all
        response = await client.get("/v1/default/analysis-groups")
        assert response.status_code == 200

        body = response.json()
        # API returns {data, meta} envelope
        assert isinstance(body, dict)
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    @pytest.mark.asyncio
    async def test_list_analysis_groups_returns_paginated_object(
        self, client: AsyncClient
    ):
        """Test that list endpoint returns paginated object, not raw array (TDD for Issue #1)."""
        # Create multiple groups
        await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Group 1"},
        )
        await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Group 2"},
        )

        # List all
        response = await client.get("/v1/default/analysis-groups")
        assert response.status_code == 200

        body = response.json()

        # Should be a {data, meta} envelope, not a raw array
        assert isinstance(body, dict), "Response should be a dict/object, not a list"
        assert "data" in body, "Response should have 'data' field"
        assert "meta" in body, "Response should have 'meta' field"
        assert "total" in body["meta"], "Meta should have 'total' field"
        assert "request_id" in body["meta"], "Meta should have 'request_id' field"

        # Verify structure
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 2
        assert len(body["data"]) >= 2

    @pytest.mark.asyncio
    async def test_list_analysis_groups_tenant_isolation(self, client: AsyncClient):
        """Test that list endpoint respects tenant isolation."""
        # Create group for tenant-a
        await client.post(
            "/v1/tenant-a/analysis-groups",
            json={"title": "Tenant A Only"},
        )

        # List from tenant-b (should be empty)
        response = await client.get("/v1/tenant-b/analysis-groups")
        assert response.status_code == 200

        body = response.json()
        # API returns {data, meta} envelope
        assert isinstance(body, dict)
        assert "data" in body
        titles = [g["title"] for g in body["data"]]
        assert "Tenant A Only" not in titles

    @pytest.mark.asyncio
    async def test_delete_analysis_group(self, client: AsyncClient):
        """Test deleting an analysis group."""
        # Create group
        create_response = await client.post(
            "/v1/default/analysis-groups",
            json={"title": "Group to Delete"},
        )
        assert create_response.status_code == 201
        group_id = create_response.json()["data"]["id"]

        # Delete it
        delete_response = await client.delete(f"/v1/default/analysis-groups/{group_id}")
        assert delete_response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/v1/default/analysis-groups/{group_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_analysis_group_not_found(self, client: AsyncClient):
        """Test deleting non-existent analysis group returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.delete(f"/v1/default/analysis-groups/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_analysis_group_tenant_isolation(self, client: AsyncClient):
        """Test that delete endpoint respects tenant isolation."""
        # Create group for tenant-a
        create_response = await client.post(
            "/v1/tenant-a/analysis-groups",
            json={"title": "Tenant A Group"},
        )
        assert create_response.status_code == 201
        group_id = create_response.json()["data"]["id"]

        # Try to delete from tenant-b (should not find it)
        delete_response = await client.delete(
            f"/v1/tenant-b/analysis-groups/{group_id}"
        )
        assert delete_response.status_code == 404

        # Verify it still exists for tenant-a
        get_response = await client.get(f"/v1/tenant-a/analysis-groups/{group_id}")
        assert get_response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
class TestAtomicGroupGenerationCreation:
    """Test atomic analysis group + workflow generation creation."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_group_with_generation_atomic(self, client: AsyncClient):
        """Test atomically creating analysis group + workflow generation."""
        response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Lateral Movement Detection"},
        )
        assert response.status_code == 201

        data = response.json()["data"]

        # Verify analysis_group
        assert "analysis_group" in data
        group = data["analysis_group"]
        assert group["title"] == "Lateral Movement Detection"
        assert group["tenant_id"] == "default"
        assert "id" in group

        # Verify workflow_generation
        assert "workflow_generation" in data
        generation = data["workflow_generation"]
        assert generation["analysis_group_id"] == group["id"]
        assert generation["status"] == "running"
        assert generation["workflow_id"] is None  # Not yet generated
        assert generation["tenant_id"] == "default"
        assert "id" in generation

    @pytest.mark.asyncio
    async def test_atomic_creation_race_condition_first_wins(self, client: AsyncClient):
        """Test that concurrent creation attempts handle race conditions gracefully."""
        # First worker creates
        response1 = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Brute Force Attempts"},
        )
        assert response1.status_code == 201
        group_id_1 = response1.json()["data"]["analysis_group"]["id"]
        gen_id_1 = response1.json()["data"]["workflow_generation"]["id"]

        # Second worker attempts same (simulates race condition)
        response2 = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Brute Force Attempts"},
        )

        # Should succeed and return SAME group+generation (not create duplicate)
        assert response2.status_code == 201
        group_id_2 = response2.json()["data"]["analysis_group"]["id"]
        gen_id_2 = response2.json()["data"]["workflow_generation"]["id"]

        assert group_id_1 == group_id_2
        assert gen_id_1 == gen_id_2

    @pytest.mark.asyncio
    async def test_atomic_creation_different_tenants_same_title(
        self, client: AsyncClient
    ):
        """Test atomic creation allows same title across tenants."""
        # Tenant A
        response_a = await client.post(
            "/v1/tenant-a/analysis-groups/with-workflow-generation",
            json={"title": "Shared Title"},
        )
        assert response_a.status_code == 201

        # Tenant B
        response_b = await client.post(
            "/v1/tenant-b/analysis-groups/with-workflow-generation",
            json={"title": "Shared Title"},
        )
        assert response_b.status_code == 201

        # Verify different IDs
        assert (
            response_a.json()["data"]["analysis_group"]["id"]
            != response_b.json()["data"]["analysis_group"]["id"]
        )

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_no_paused_alerts(self, client: AsyncClient):
        """Test resume-paused-alerts returns 0 when no alerts are paused."""
        # Create analysis group
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": f"Resume Test {uuid.uuid4().hex[:8]}"},
        )
        assert create_response.status_code == 201
        group_id = create_response.json()["data"]["analysis_group"]["id"]

        # Call resume endpoint (should return 0 since no alerts are paused)
        # Note: In integration test, we can't easily mock Redis, so we just test the API contract
        # when there are no paused alerts
        resume_response = await client.post(
            f"/v1/default/analysis-groups/{group_id}/resume-paused-alerts"
        )
        assert resume_response.status_code == 200

        data = resume_response.json()["data"]
        assert data["resumed_count"] == 0
        assert data["skipped_count"] == 0
        assert data["alert_ids"] == []

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_group_not_found(self, client: AsyncClient):
        """Test resume-paused-alerts returns 404 for non-existent group."""
        fake_group_id = str(uuid.uuid4())

        response = await client.post(
            f"/v1/default/analysis-groups/{fake_group_id}/resume-paused-alerts"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowGenerationEndpoints:
    """Test Workflow Generation REST API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_workflow_generation_by_id(self, client: AsyncClient):
        """Test retrieving a specific workflow generation."""
        # Create group+generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Test Generation"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Get by ID
        get_response = await client.get(f"/v1/default/workflow-generations/{gen_id}")
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        assert data["id"] == gen_id
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_workflow_generation_not_found(self, client: AsyncClient):
        """Test getting non-existent workflow generation returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/v1/default/workflow-generations/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workflow_generation_progress(self, client: AsyncClient):
        """Test updating workflow generation progress with stage-based API."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Progress Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Update progress to task_building stage (new API format)
        progress_data = {
            "stage": "task_building",
            "tasks_count": 3,
        }

        update_response = await client.patch(
            f"/v1/default/workflow-generations/{gen_id}/progress",
            json=progress_data,
        )
        assert update_response.status_code == 200

        # Verify progress was stored with pre-populated phases
        updated = update_response.json()["data"]
        assert updated["id"] == gen_id
        assert updated["progress"] is not None

        # All 4 phases should be present
        phases = updated["progress"]["phases"]
        assert len(phases) == 4

        # task_building is at index 2 and should be in_progress
        assert phases[2]["stage"] == "task_building"
        assert phases[2]["status"] == "in_progress"
        assert phases[2]["tasks_count"] == 3

        # Previous phases should be auto-completed
        assert phases[0]["status"] == "completed"
        assert phases[1]["status"] == "completed"

        # Later phases should be not_started
        assert phases[3]["status"] == "not_started"

        # Get generation again to verify persistence
        get_response = await client.get(f"/v1/default/workflow-generations/{gen_id}")
        assert get_response.status_code == 200
        data = get_response.json()["data"]
        assert data["progress"]["phases"][2]["stage"] == "task_building"

    @pytest.mark.asyncio
    async def test_update_workflow_generation_progress_not_found(
        self, client: AsyncClient
    ):
        """Test updating progress for non-existent generation returns 404."""
        fake_id = str(uuid.uuid4())
        progress_data = {
            "stage": "runbook_generation",
        }

        response = await client.patch(
            f"/v1/default/workflow-generations/{fake_id}/progress",
            json=progress_data,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_workflow_generation_stores_orchestration_results(
        self, client: AsyncClient
    ):
        """Test that workflow generation can store orchestration results (consolidated JSONB)."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Results Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Verify initial state has null orchestration_results
        get_response = await client.get(f"/v1/default/workflow-generations/{gen_id}")
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        # orchestration_results should exist and be null initially
        assert "orchestration_results" in data
        assert data["orchestration_results"] is None

    @pytest.mark.asyncio
    async def test_update_workflow_generation_results_success(
        self, client: AsyncClient
    ):
        """Test updating workflow generation with orchestration results (consolidated JSONB)."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Update Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Simulate orchestration completing
        workflow_id = str(uuid.uuid4())
        update_data = {
            "workflow_id": workflow_id,
            "status": "completed",
            "orchestration_results": {
                "runbook": "# Investigation Runbook\n\nSteps to investigate...",
                "task_proposals": [
                    {
                        "name": "IP Reputation",
                        "category": "existing",
                        "cy_name": "vt_ip_check",
                    }
                ],
                "tasks_built": [
                    {
                        "success": True,
                        "cy_name": "new_task",
                        "task_id": str(uuid.uuid4()),
                    }
                ],
                "workflow_composition": ["vt_ip_check", "new_task"],
                "metrics": {
                    "stages": [{"stage": "runbook_generation", "total_cost_usd": 0.05}],
                    "total_cost_usd": 0.15,
                },
            },
        }

        # Update via PUT endpoint
        update_response = await client.put(
            f"/v1/default/workflow-generations/{gen_id}/results",
            json=update_data,
        )
        assert update_response.status_code == 200

        # Verify update was stored
        updated = update_response.json()["data"]
        assert updated["id"] == gen_id
        assert updated["workflow_id"] == workflow_id
        assert updated["status"] == "completed"

        # Verify orchestration_results structure
        assert updated["orchestration_results"] is not None
        results = updated["orchestration_results"]
        assert "Investigation Runbook" in results["runbook"]
        assert len(results["task_proposals"]) == 1
        assert len(results["tasks_built"]) == 1
        assert results["workflow_composition"] == ["vt_ip_check", "new_task"]
        assert results["metrics"]["total_cost_usd"] == 0.15

        assert updated["completed_at"] is not None  # Should be set for terminal status

    @pytest.mark.asyncio
    async def test_update_workflow_generation_results_not_found(
        self, client: AsyncClient
    ):
        """Test updating non-existent workflow generation returns 404."""
        fake_id = str(uuid.uuid4())
        update_data = {
            "workflow_id": None,
            "status": "failed",
        }

        response = await client.put(
            f"/v1/default/workflow-generations/{fake_id}/results",
            json=update_data,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workflow_generation_results_partial_data(
        self, client: AsyncClient
    ):
        """Test updating with only required fields and error in orchestration_results."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Partial Update Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Update with minimal data (failed status, error in orchestration_results)
        update_data = {
            "workflow_id": None,
            "status": "failed",
            "orchestration_results": {
                "error": {
                    "message": "Failed to generate runbook",
                    "type": "RuntimeError",
                    "timestamp": "2025-12-01T12:00:00Z",
                },
            },
        }

        update_response = await client.put(
            f"/v1/default/workflow-generations/{gen_id}/results",
            json=update_data,
        )
        assert update_response.status_code == 200

        updated = update_response.json()["data"]
        assert updated["status"] == "failed"
        assert updated["workflow_id"] is None
        assert updated["completed_at"] is not None  # Should be set for terminal status

        # Verify error is stored in orchestration_results
        assert updated["orchestration_results"] is not None
        assert "error" in updated["orchestration_results"]
        assert (
            updated["orchestration_results"]["error"]["message"]
            == "Failed to generate runbook"
        )

    @pytest.mark.asyncio
    async def test_delete_workflow_generation(self, client: AsyncClient):
        """Test deleting a workflow generation."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Generation to Delete"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Delete it
        delete_response = await client.delete(
            f"/v1/default/workflow-generations/{gen_id}"
        )
        assert delete_response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/v1/default/workflow-generations/{gen_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_workflow_generation_not_found(self, client: AsyncClient):
        """Test deleting non-existent workflow generation returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.delete(f"/v1/default/workflow-generations/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_workflow_generations_endpoint_exists(self, client: AsyncClient):
        """Test that LIST endpoint for workflow-generations exists (TDD for Issue #2)."""
        # Create multiple workflow generations
        await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Generation 1"},
        )
        await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Generation 2"},
        )

        # Try to list all workflow generations
        response = await client.get("/v1/default/workflow-generations")

        # Should return 200 with paginated object, NOT 404
        assert response.status_code == 200, "LIST endpoint should exist"

        body = response.json()

        # Should be a {data, meta} envelope
        assert isinstance(body, dict), "Response should be a dict/object, not a list"
        assert "data" in body, "Response should have 'data' field"
        assert "meta" in body, "Response should have 'meta' field"
        assert "total" in body["meta"], "Meta should have 'total' field"
        assert "request_id" in body["meta"], "Meta should have 'request_id' field"

        # Verify structure
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 2
        assert len(body["data"]) >= 2


@pytest.mark.asyncio
@pytest.mark.integration
class TestImplicitStageCompletion:
    """Test that stage completion is implicit when the next stage starts."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_starting_next_stage_completes_previous_stages(
        self, client: AsyncClient
    ):
        """Test that starting a new stage implicitly completes all previous stages."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Implicit Completion Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Start first stage (runbook_generation)
        response1 = await client.patch(
            f"/v1/default/workflow-generations/{gen_id}/progress",
            json={"stage": "runbook_generation"},
        )
        assert response1.status_code == 200
        phases = response1.json()["data"]["progress"]["phases"]
        assert phases[0]["status"] == "in_progress"
        assert phases[1]["status"] == "not_started"
        assert phases[2]["status"] == "not_started"
        assert phases[3]["status"] == "not_started"

        # Start third stage (task_building) - skipping task_proposals
        # This should implicitly complete runbook_generation AND task_proposals
        response2 = await client.patch(
            f"/v1/default/workflow-generations/{gen_id}/progress",
            json={"stage": "task_building", "tasks_count": 2},
        )
        assert response2.status_code == 200
        phases = response2.json()["data"]["progress"]["phases"]

        # Verify implicit completion
        assert phases[0]["stage"] == "runbook_generation"
        assert phases[0]["status"] == "completed"  # Implicitly completed
        assert phases[0]["completed_at"] is not None

        assert phases[1]["stage"] == "task_proposals"
        assert phases[1]["status"] == "completed"  # Implicitly completed
        assert phases[1]["completed_at"] is not None

        assert phases[2]["stage"] == "task_building"
        assert phases[2]["status"] == "in_progress"
        assert phases[2]["tasks_count"] == 2

        assert phases[3]["stage"] == "workflow_assembly"
        assert phases[3]["status"] == "not_started"

    @pytest.mark.asyncio
    async def test_full_stage_progression(self, client: AsyncClient):
        """Test full progression through all 4 stages with implicit completion."""
        # Create generation
        create_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Full Progression Test"},
        )
        assert create_response.status_code == 201
        gen_id = create_response.json()["data"]["workflow_generation"]["id"]

        # Progress through each stage
        stages = [
            "runbook_generation",
            "task_proposals",
            "task_building",
            "workflow_assembly",
        ]

        for i, stage in enumerate(stages):
            response = await client.patch(
                f"/v1/default/workflow-generations/{gen_id}/progress",
                json={"stage": stage},
            )
            assert response.status_code == 200
            phases = response.json()["data"]["progress"]["phases"]

            # Current stage should be in_progress
            assert phases[i]["status"] == "in_progress"

            # All previous stages should be completed
            for j in range(i):
                assert phases[j]["status"] == "completed"
                assert phases[j]["completed_at"] is not None

            # All later stages should be not_started
            for j in range(i + 1, 4):
                assert phases[j]["status"] == "not_started"


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertRoutingRuleEndpoints:
    """Test Alert Routing Rule REST API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_alert_routing_rule(self, client: AsyncClient):
        """Test creating an alert routing rule."""
        # Create group+generation
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Routing Test"},
        )
        assert group_response.status_code == 201

        group_id = group_response.json()["data"]["analysis_group"]["id"]

        # For this test, use a fake workflow_id (in production, this would be generated)
        fake_workflow_id = str(uuid.uuid4())

        # Create routing rule
        rule_response = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": fake_workflow_id,
            },
        )
        assert rule_response.status_code == 201

        data = rule_response.json()["data"]
        assert data["analysis_group_id"] == group_id
        assert data["workflow_id"] == fake_workflow_id
        assert data["tenant_id"] == "default"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_alert_routing_rule_by_id(self, client: AsyncClient):
        """Test retrieving a specific alert routing rule."""
        # Create prerequisites
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Rule Get Test"},
        )
        group_id = group_response.json()["data"]["analysis_group"]["id"]
        fake_workflow_id = str(uuid.uuid4())

        # Create rule
        create_response = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": fake_workflow_id,
            },
        )
        rule_id = create_response.json()["data"]["id"]

        # Get by ID
        get_response = await client.get(f"/v1/default/alert-routing-rules/{rule_id}")
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        assert data["id"] == rule_id
        assert data["workflow_id"] == fake_workflow_id

    @pytest.mark.asyncio
    async def test_get_alert_routing_rule_not_found(self, client: AsyncClient):
        """Test getting non-existent alert routing rule returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/v1/default/alert-routing-rules/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_routing_rules_per_group(self, client: AsyncClient):
        """Test that multiple routing rules can exist per analysis group (A/B testing)."""
        # Create group+generation
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Multi-Workflow Test"},
        )
        group_id = group_response.json()["data"]["analysis_group"]["id"]

        workflow_id_1 = str(uuid.uuid4())
        workflow_id_2 = str(uuid.uuid4())

        # Create first rule
        response1 = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id_1,
            },
        )
        assert response1.status_code == 201
        rule_id_1 = response1.json()["data"]["id"]

        # Create second rule for same group (should succeed for A/B testing)
        response2 = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id_2,
            },
        )
        assert response2.status_code == 201
        rule_id_2 = response2.json()["data"]["id"]

        # Verify both rules exist and have different IDs and workflows
        assert rule_id_1 != rule_id_2
        assert response1.json()["data"]["workflow_id"] == workflow_id_1
        assert response2.json()["data"]["workflow_id"] == workflow_id_2
        assert response1.json()["data"]["analysis_group_id"] == group_id
        assert response2.json()["data"]["analysis_group_id"] == group_id

    @pytest.mark.asyncio
    async def test_delete_alert_routing_rule(self, client: AsyncClient):
        """Test deleting an alert routing rule."""
        # Create prerequisites
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Rule Delete Test"},
        )
        group_id = group_response.json()["data"]["analysis_group"]["id"]
        fake_workflow_id = str(uuid.uuid4())

        # Create rule
        create_response = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": fake_workflow_id,
            },
        )
        assert create_response.status_code == 201
        rule_id = create_response.json()["data"]["id"]

        # Delete it
        delete_response = await client.delete(
            f"/v1/default/alert-routing-rules/{rule_id}"
        )
        assert delete_response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/v1/default/alert-routing-rules/{rule_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_alert_routing_rule_not_found(self, client: AsyncClient):
        """Test deleting non-existent alert routing rule returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.delete(f"/v1/default/alert-routing-rules/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_alert_routing_rules_empty_returns_200(
        self, client: AsyncClient
    ):
        """Test that empty list returns 200 with empty array, not 404 (TDD for Issue #3)."""
        # Try to list alert routing rules when none exist
        response = await client.get("/v1/default/alert-routing-rules")

        # Should return 200 with empty collection, NOT 404
        assert response.status_code == 200, "Empty list should return 200, not 404"

        body = response.json()

        # Should be a {data, meta} envelope with empty array
        assert isinstance(body, dict), "Response should be a dict/object, not a list"
        assert "data" in body, "Response should have 'data' field"
        assert "meta" in body, "Response should have 'meta' field"
        assert "total" in body["meta"], "Meta should have 'total' field"
        assert "request_id" in body["meta"], "Meta should have 'request_id' field"

        # Verify empty state
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] == 0
        assert len(body["data"]) == 0

    @pytest.mark.asyncio
    async def test_list_alert_routing_rules_with_data(self, client: AsyncClient):
        """Test that list endpoint works with data (TDD for Issue #3)."""
        # Create prerequisites
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Rule List Test"},
        )
        group_id = group_response.json()["data"]["analysis_group"]["id"]

        # Create multiple rules
        workflow_id_1 = str(uuid.uuid4())
        workflow_id_2 = str(uuid.uuid4())

        await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id_1,
            },
        )
        await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id_2,
            },
        )

        # List all rules
        response = await client.get("/v1/default/alert-routing-rules")
        assert response.status_code == 200

        body = response.json()

        # Should be a {data, meta} envelope
        assert isinstance(body, dict)
        assert "data" in body
        assert "meta" in body

        # Verify data
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 2
        assert len(body["data"]) >= 2


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowRegeneration:
    """Test workflow regeneration support (multiple generations per group)."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_multiple_generations_per_group_allowed(self, client: AsyncClient):
        """Test that multiple workflow generations can exist for one analysis group."""
        # Create initial group+generation
        response1 = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": "Regeneration Test"},
        )
        assert response1.status_code == 201
        group_id = response1.json()["data"]["analysis_group"]["id"]
        gen_id_1 = response1.json()["data"]["workflow_generation"]["id"]

        # TODO: Add an endpoint to trigger regeneration.
        # For now, this test documents the intent that multiple generations
        # per group should be supported via is_active flag

        # Verify first generation exists
        get_response = await client.get(f"/v1/default/workflow-generations/{gen_id_1}")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["analysis_group_id"] == group_id


@pytest.mark.asyncio
@pytest.mark.integration
class TestActiveWorkflowEndpoint:
    """Test active workflow query endpoint."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_active_workflow_with_routing_rule(self, client: AsyncClient):
        """Test getting active workflow when routing rule exists."""
        title = f"Active Workflow Test {uuid.uuid4().hex[:8]}"

        # Create group+generation
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": title},
        )
        assert group_response.status_code == 201
        group_id = group_response.json()["data"]["analysis_group"]["id"]

        # Create routing rule
        workflow_id = str(uuid.uuid4())
        rule_response = await client.post(
            "/v1/default/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id,
            },
        )
        assert rule_response.status_code == 201

        # Query active workflow by title
        active_response = await client.get(
            "/v1/default/analysis-groups/active-workflow",
            params={"title": title},
        )
        assert active_response.status_code == 200

        data = active_response.json()["data"]
        assert "routing_rule" in data
        assert data["routing_rule"] is not None
        assert data["routing_rule"]["workflow_id"] == workflow_id
        assert data["routing_rule"]["analysis_group_id"] == group_id
        assert data["routing_rule"]["tenant_id"] == "default"

    @pytest.mark.asyncio
    async def test_get_active_workflow_no_routing_rule(self, client: AsyncClient):
        """Test getting active workflow when no routing rule exists yet."""
        title = f"No Routing Rule Test {uuid.uuid4().hex[:8]}"

        # Create group+generation (no routing rule)
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": title},
        )
        assert group_response.status_code == 201

        # Query active workflow (should return None for routing_rule)
        active_response = await client.get(
            "/v1/default/analysis-groups/active-workflow",
            params={"title": title},
        )
        assert active_response.status_code == 200

        data = active_response.json()["data"]
        assert "routing_rule" in data
        assert data["routing_rule"] is None

    @pytest.mark.asyncio
    async def test_generation_summary_includes_analysis_group_id(
        self, client: AsyncClient
    ):
        """GenerationSummary must include analysis_group_id for reconciliation recovery.

        Bug: reconciliation.py reads generation["analysis_group_id"] from the
        active-workflow response, but GenerationSummary didn't include it.
        This caused str(None) -> "None" to be sent as a UUID, triggering 422.
        """
        title = f"GenSummary GroupId Test {uuid.uuid4().hex[:8]}"

        # Create group+generation
        group_response = await client.post(
            "/v1/default/analysis-groups/with-workflow-generation",
            json={"title": title},
        )
        assert group_response.status_code == 201
        group_id = group_response.json()["data"]["analysis_group"]["id"]

        # Query active workflow
        active_response = await client.get(
            "/v1/default/analysis-groups/active-workflow",
            params={"title": title},
        )
        assert active_response.status_code == 200

        data = active_response.json()["data"]
        generation = data["generation"]
        assert generation is not None
        assert "analysis_group_id" in generation, (
            "GenerationSummary must include analysis_group_id for reconciliation recovery"
        )
        assert generation["analysis_group_id"] == group_id

    @pytest.mark.asyncio
    async def test_get_active_workflow_tenant_isolation(self, client: AsyncClient):
        """Test that active workflow respects tenant isolation."""
        title = f"Tenant A Workflow {uuid.uuid4().hex[:8]}"

        # Create group+rule for tenant-a
        group_response = await client.post(
            "/v1/tenant-a/analysis-groups/with-workflow-generation",
            json={"title": title},
        )
        group_id = group_response.json()["data"]["analysis_group"]["id"]
        workflow_id = str(uuid.uuid4())

        await client.post(
            "/v1/tenant-a/alert-routing-rules",
            json={
                "analysis_group_id": group_id,
                "workflow_id": workflow_id,
            },
        )

        # Try to query from tenant-b using same title (should not find it)
        active_response = await client.get(
            "/v1/tenant-b/analysis-groups/active-workflow",
            params={"title": title},
        )
        assert active_response.status_code == 200

        data = active_response.json()["data"]
        # Should return None because tenant-b can't see tenant-a's groups
        assert data["routing_rule"] is None
