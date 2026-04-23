"""Integration tests for Task Generations API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.kea_coordination import AnalysisGroup, WorkflowGeneration
from analysi.models.task import Task
from analysi.models.task_generation import TaskGeneration


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskGenerationsEndpoints:
    """Test Task Generations REST API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    async def kea_task_generation(
        self, integration_test_session: AsyncSession
    ) -> TaskGeneration:
        """Create a Kea-internal task generation (source='workflow_generation')."""
        # Create prerequisite analysis group + workflow generation
        group = AnalysisGroup(
            tenant_id="test-tenant",
            title=f"Test Group {uuid.uuid4().hex[:8]}",
        )
        integration_test_session.add(group)
        await integration_test_session.flush()

        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=group.id,
            status="running",
            is_active=True,
        )
        integration_test_session.add(generation)
        await integration_test_session.flush()

        run = TaskGeneration(
            tenant_id="test-tenant",
            workflow_generation_id=generation.id,
            source="workflow_generation",
            input_context={"proposal": {"name": "Kea Internal Task"}},
            status="completed",
            created_by=str(SYSTEM_USER_ID),
            progress_messages=[],
        )
        integration_test_session.add(run)
        await integration_test_session.commit()
        return run

    @pytest.mark.asyncio
    async def test_create_task_generation_returns_202(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test POST creates record and returns 202 Accepted."""
        # Mock Redis to avoid actual ARQ job enqueue
        mock_redis = AsyncMock()
        mock_job = AsyncMock()
        mock_job.job_id = "test-job-123"
        mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.routers.task_generations.create_pool",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/v1/test-tenant/task-generations",
                json={
                    "description": "Build a task that checks IP reputation using VirusTotal integration",
                },
            )

        assert response.status_code == 202

        data = response.json()["data"]
        assert "id" in data
        assert data["status"] == "pending"
        assert "VirusTotal" in data["description"]
        assert data["alert_id"] is None
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_task_generation_with_invalid_alert_returns_404(
        self, client: AsyncClient
    ):
        """Test POST with non-existent alert_id returns 404."""
        fake_alert_id = str(uuid.uuid4())
        response = await client.post(
            "/v1/test-tenant/task-generations",
            json={
                "description": "Build a task that checks IP reputation using VirusTotal",
                "alert_id": fake_alert_id,
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_task_generation_description_too_short(
        self, client: AsyncClient
    ):
        """Test POST with too-short description returns 422."""
        response = await client.post(
            "/v1/test-tenant/task-generations",
            json={"description": "short"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_generation_enqueue_failure_marks_run_failed(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test POST returns 503 and marks run as failed when ARQ enqueue fails."""
        with patch(
            "analysi.routers.task_generations.create_pool",
            side_effect=ConnectionError("Redis unavailable"),
        ):
            response = await client.post(
                "/v1/test-tenant/task-generations",
                json={
                    "description": "Build a task that checks IP reputation using VirusTotal integration",
                },
            )

        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"].lower()

        # Verify the run was marked as failed (not stuck as 'new')
        from sqlalchemy import select

        from analysi.models.task_generation import TaskGeneration

        result = await integration_test_session.execute(
            select(TaskGeneration).where(
                TaskGeneration.tenant_id == "test-tenant",
                TaskGeneration.source == "api",
            )
        )
        run = result.scalar_one()
        assert run.status == "failed"
        assert "EnqueueError" in str(run.result)

    @pytest.mark.asyncio
    async def test_get_task_generation_returns_api_build(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test GET returns a standalone API build."""
        # Create an API-sourced run directly
        run = TaskGeneration(
            tenant_id="test-tenant",
            workflow_generation_id=None,
            source="api",
            description="Test task for GET endpoint",
            input_context={"description": "Test task for GET endpoint"},
            status="pending",
            created_by=str(SYSTEM_USER_ID),
            progress_messages=[],
        )
        integration_test_session.add(run)
        await integration_test_session.commit()

        response = await client.get(f"/v1/test-tenant/task-generations/{run.id}")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["id"] == str(run.id)
        assert data["status"] == "pending"
        assert data["source"] == "api"

    @pytest.mark.asyncio
    async def test_get_task_generation_rejects_kea_internal_build(
        self,
        client: AsyncClient,
        kea_task_generation: TaskGeneration,
    ):
        """Test GET returns 404 for Kea-internal builds (source='workflow_generation')."""
        response = await client.get(
            f"/v1/test-tenant/task-generations/{kea_task_generation.id}"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_generation_not_found(self, client: AsyncClient):
        """Test GET with non-existent ID returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/v1/test-tenant/task-generations/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_task_generations_returns_only_api_builds(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        kea_task_generation: TaskGeneration,
    ):
        """Test LIST returns only source='api' builds, not Kea-internal."""
        # Create 2 API-sourced runs
        for i in range(2):
            run = TaskGeneration(
                tenant_id="test-tenant",
                workflow_generation_id=None,
                source="api",
                description=f"API task {i}",
                input_context={"description": f"API task {i}"},
                status="pending",
                created_by=str(SYSTEM_USER_ID),
                progress_messages=[],
            )
            integration_test_session.add(run)
        await integration_test_session.commit()

        response = await client.get("/v1/test-tenant/task-generations")
        assert response.status_code == 200

        body = response.json()
        assert body["meta"]["total"] == 2
        assert len(body["data"]) == 2
        # All returned runs must be source='api'
        for run_data in body["data"]:
            assert run_data["source"] == "api"

    @pytest.mark.asyncio
    async def test_list_task_generations_tenant_isolation(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Test LIST respects tenant isolation."""
        # Create runs for two different tenants
        for tenant in ["tenant-a", "tenant-b"]:
            run = TaskGeneration(
                tenant_id=tenant,
                workflow_generation_id=None,
                source="api",
                description=f"Task for {tenant}",
                input_context={"description": f"Task for {tenant}"},
                status="pending",
                created_by=str(SYSTEM_USER_ID),
                progress_messages=[],
            )
            integration_test_session.add(run)
        await integration_test_session.commit()

        # List for tenant-a
        response_a = await client.get("/v1/tenant-a/task-generations")
        assert response_a.status_code == 200
        data_a = response_a.json()
        assert data_a["meta"]["total"] == 1
        assert data_a["data"][0]["tenant_id"] == "tenant-a"

        # List for tenant-b
        response_b = await client.get("/v1/tenant-b/task-generations")
        assert response_b.status_code == 200
        data_b = response_b.json()
        assert data_b["meta"]["total"] == 1
        assert data_b["data"][0]["tenant_id"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_get_task_generation_tenant_isolation(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Test GET respects tenant isolation."""
        run = TaskGeneration(
            tenant_id="tenant-owner",
            workflow_generation_id=None,
            source="api",
            description="Isolated task",
            input_context={"description": "Isolated task"},
            status="pending",
            created_by=str(SYSTEM_USER_ID),
            progress_messages=[],
        )
        integration_test_session.add(run)
        await integration_test_session.commit()

        # Owner can access
        response_owner = await client.get(f"/v1/tenant-owner/task-generations/{run.id}")
        assert response_owner.status_code == 200

        # Other tenant cannot
        response_other = await client.get(f"/v1/other-tenant/task-generations/{run.id}")
        assert response_other.status_code == 404

    @pytest.mark.asyncio
    async def test_list_task_generations_pagination(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Test LIST supports pagination."""
        # Create 5 runs
        for i in range(5):
            run = TaskGeneration(
                tenant_id="test-tenant",
                workflow_generation_id=None,
                source="api",
                description=f"Paginated task {i}",
                input_context={"description": f"Paginated task {i}"},
                status="pending",
                created_by=str(SYSTEM_USER_ID),
                progress_messages=[],
            )
            integration_test_session.add(run)
        await integration_test_session.commit()

        # Get first page (limit=2)
        response = await client.get("/v1/test-tenant/task-generations?limit=2&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 5
        assert len(body["data"]) == 2

        # Get second page
        response2 = await client.get(
            "/v1/test-tenant/task-generations?limit=2&offset=2"
        )
        assert response2.status_code == 200
        body2 = response2.json()
        assert body2["meta"]["total"] == 5
        assert len(body2["data"]) == 2


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskGenerationWithStartingPoint:
    """Test task generation with an existing task as starting point."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    async def existing_task(self, integration_test_session: AsyncSession) -> Component:
        """Create a task with Component that can be used as starting point."""
        component_id = uuid4()
        cy_name = f"test_ip_reputation_{uuid4().hex[:8]}"

        component = Component(
            id=component_id,
            tenant_id="test-tenant",
            name="VirusTotal: IP Reputation Check",
            description="Check IP reputation via VirusTotal",
            categories=["enrichment"],
            status="enabled",
            kind="task",
            cy_name=cy_name,
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            id=uuid4(),
            component_id=component_id,
            function="enrichment",
            scope="processing",
            script="ip = input.primary_ioc_value\nresult = app::virustotal::ip_reputation(ip=ip)\nreturn enrich_alert(input, result)",
            directive="You are a threat intel analyst.",
            data_samples=[{"primary_ioc_value": "8.8.8.8", "enrichments": {}}],
        )
        integration_test_session.add(task)
        await integration_test_session.commit()
        return component

    @pytest.mark.asyncio
    async def test_create_with_starting_point_returns_202(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        existing_task: Component,
    ):
        """Test POST with task_id packs existing task into input_context."""
        mock_redis = AsyncMock()
        mock_job = AsyncMock()
        mock_job.job_id = "test-job-modify-123"
        mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.routers.task_generations.create_pool",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/v1/test-tenant/task-generations",
                json={
                    "description": "Add AbuseIPDB enrichment alongside the existing VirusTotal check",
                    "task_id": str(existing_task.id),
                },
            )

        assert response.status_code == 202
        data = response.json()["data"]
        assert data["status"] == "pending"
        assert data["task_id"] == str(existing_task.id)
        assert "AbuseIPDB" in data["description"]

        # Verify the ARQ job was called with input_context containing existing_task
        enqueue_call = mock_redis.enqueue_job.call_args
        # input_context is the 6th positional arg (index 5)
        input_context = enqueue_call[0][5]
        assert "existing_task" in input_context
        assert input_context["existing_task"]["cy_name"] == existing_task.cy_name
        assert "ip_reputation" in input_context["existing_task"]["script"]

    @pytest.mark.asyncio
    async def test_create_with_starting_point_stores_in_input_context(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        existing_task: Component,
    ):
        """Test that existing_task is persisted in TaskGeneration.input_context."""
        mock_redis = AsyncMock()
        mock_job = AsyncMock()
        mock_job.job_id = "test-job-modify-456"
        mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.routers.task_generations.create_pool",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/v1/test-tenant/task-generations",
                json={
                    "description": "Change severity threshold to high only",
                    "task_id": str(existing_task.id),
                },
            )

        assert response.status_code == 202
        run_id = response.json()["data"]["id"]

        # Verify input_context in database includes existing_task
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(TaskGeneration).where(TaskGeneration.id == run_id)
        )
        run = result.scalar_one()
        assert "existing_task" in run.input_context
        assert run.input_context["existing_task"]["task_id"] == str(existing_task.id)
        assert run.input_context["existing_task"]["cy_name"] == existing_task.cy_name
        assert run.input_context["existing_task"]["script"] is not None

    @pytest.mark.asyncio
    async def test_create_with_nonexistent_task_returns_404(self, client: AsyncClient):
        """Test POST with non-existent task_id returns 404."""
        fake_task_id = str(uuid4())
        response = await client.post(
            "/v1/test-tenant/task-generations",
            json={
                "description": "Add AbuseIPDB enrichment to this task",
                "task_id": fake_task_id,
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_with_other_tenants_task_returns_404(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Test POST with task_id from another tenant returns 404 (tenant isolation)."""
        # Create a task owned by a different tenant
        component_id = uuid4()
        component = Component(
            id=component_id,
            tenant_id="other-tenant",
            name="Other Tenant Task",
            description="Belongs to other-tenant",
            status="enabled",
            kind="task",
            cy_name=f"other_task_{uuid4().hex[:8]}",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            id=uuid4(),
            component_id=component_id,
            function="enrichment",
            scope="processing",
            script="return input",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        # Try to use it from test-tenant — should 404
        response = await client.post(
            "/v1/test-tenant/task-generations",
            json={
                "description": "Modify this task to add more enrichment",
                "task_id": str(component_id),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_with_system_only_task_returns_403(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Test POST with system_only task returns 403 (immutability guard)."""
        component_id = uuid4()
        component = Component(
            id=component_id,
            tenant_id="test-tenant",
            name="System Task",
            description="System-managed task",
            status="enabled",
            kind="task",
            cy_name=f"system_task_{uuid4().hex[:8]}",
            system_only=True,
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            id=uuid4(),
            component_id=component_id,
            function="enrichment",
            scope="processing",
            script="return input",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        response = await client.post(
            "/v1/test-tenant/task-generations",
            json={
                "description": "Try to modify a system-only task",
                "task_id": str(component_id),
            },
        )
        assert response.status_code == 403
        assert "system-only" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_without_task_id_still_works(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test POST without task_id works as before (creation from scratch)."""
        mock_redis = AsyncMock()
        mock_job = AsyncMock()
        mock_job.job_id = "test-job-create-789"
        mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.routers.task_generations.create_pool",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/v1/test-tenant/task-generations",
                json={
                    "description": "Build a task that checks IP reputation using VirusTotal",
                },
            )

        assert response.status_code == 202
        data = response.json()["data"]
        assert data["task_id"] is None

        # Verify input_context does NOT have existing_task
        enqueue_call = mock_redis.enqueue_job.call_args
        input_context = enqueue_call[0][5]
        assert "existing_task" not in input_context
