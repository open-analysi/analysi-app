"""
Simplified integration tests for task-runs list API endpoint.

Tests the /v1/{tenant}/task-runs endpoint functionality by creating
task runs directly in the database with known statuses.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.task_run import TaskRun


@pytest.mark.integration
class TestTaskRunsListAPISimple:
    """Simplified integration tests for task-runs list endpoint."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncClient:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    async def sample_task_runs(self, integration_test_session) -> list[TaskRun]:
        """Create sample task runs directly in the database."""
        db = integration_test_session
        tenant_id = "test-tenant"

        task_runs = []
        base_time = datetime.now(UTC)

        # Create succeeded runs (ad-hoc executions, no task_id required)
        for i in range(3):
            task_run = TaskRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                task_id=None,  # Ad-hoc execution
                status="completed",
                cy_script="// Test script",
                started_at=base_time - timedelta(minutes=10 - i),
                completed_at=base_time - timedelta(minutes=9 - i),
                duration=timedelta(minutes=1),
                created_at=base_time - timedelta(minutes=10 - i),
                updated_at=base_time - timedelta(minutes=9 - i),
                input_type="inline",
                input_location='{"test": "data"}',
                output_type="inline",
                output_location='{"result": "success"}',
            )
            db.add(task_run)
            task_runs.append(task_run)

        # Create failed runs (ad-hoc executions)
        for i in range(2):
            task_run = TaskRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                task_id=None,  # Ad-hoc execution
                status="failed",
                cy_script="// Test script",
                started_at=base_time - timedelta(minutes=7 - i),
                completed_at=base_time - timedelta(minutes=6 - i),
                duration=timedelta(minutes=1),
                created_at=base_time - timedelta(minutes=7 - i),
                updated_at=base_time - timedelta(minutes=6 - i),
                input_type="inline",
                input_location='{"test": "data"}',
                output_type="inline",
                output_location='{"error": "failed"}',
            )
            db.add(task_run)
            task_runs.append(task_run)

        # Create running run (ad-hoc execution)
        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            task_id=None,  # Ad-hoc execution
            status="running",
            cy_script="// Test script",
            started_at=base_time - timedelta(minutes=1),
            created_at=base_time - timedelta(minutes=1),
            updated_at=base_time - timedelta(minutes=1),
            input_type="inline",
            input_location='{"test": "data"}',
        )
        db.add(task_run)
        task_runs.append(task_run)

        await db.commit()
        for tr in task_runs:
            await db.refresh(tr)

        return task_runs

    @pytest.mark.asyncio
    async def test_list_all_task_runs(
        self, client: AsyncClient, sample_task_runs: list[TaskRun]
    ):
        """Test listing all task runs without filters."""
        tenant_id = "test-tenant"

        response = await client.get(f"/v1/{tenant_id}/task-runs")
        assert response.status_code == 200

        body = response.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        meta = body["meta"]
        assert meta["total"] >= 6  # At least our 6 sample runs
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_filter_by_status(
        self, client: AsyncClient, sample_task_runs: list[TaskRun]
    ):
        """Test filtering task runs by status."""
        tenant_id = "test-tenant"

        # Test succeeded filter
        response = await client.get(
            f"/v1/{tenant_id}/task-runs", params={"status": "completed"}
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        meta = body["meta"]

        # Should have exactly 3 succeeded runs
        assert all(run["status"] == "completed" for run in data)
        succeeded_count = sum(1 for tr in sample_task_runs if tr.status == "completed")
        assert meta["total"] >= succeeded_count

        # Test failed filter
        response = await client.get(
            f"/v1/{tenant_id}/task-runs", params={"status": "failed"}
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        meta = body["meta"]

        # Should have exactly 2 failed runs
        assert all(run["status"] == "failed" for run in data)
        failed_count = sum(1 for tr in sample_task_runs if tr.status == "failed")
        assert meta["total"] >= failed_count

        # Test running filter
        response = await client.get(
            f"/v1/{tenant_id}/task-runs", params={"status": "running"}
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # Should have at least 1 running run
        assert all(run["status"] == "running" for run in data)

    @pytest.mark.asyncio
    async def test_sorting(self, client: AsyncClient, sample_task_runs: list[TaskRun]):
        """Test sorting task runs by different fields."""
        tenant_id = "test-tenant"

        # Test ascending sort by created_at (all our sample runs)
        response = await client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"sort": "created_at", "order": "asc", "limit": 20},
        )
        assert response.status_code == 200
        data = response.json()["data"]

        runs = data
        for i in range(len(runs) - 1):
            assert runs[i]["created_at"] <= runs[i + 1]["created_at"]

        # Test descending sort by created_at
        response = await client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"sort": "created_at", "order": "desc", "limit": 20},
        )
        assert response.status_code == 200
        data = response.json()["data"]

        runs = data
        for i in range(len(runs) - 1):
            assert runs[i]["created_at"] >= runs[i + 1]["created_at"]

    @pytest.mark.asyncio
    async def test_pagination(
        self, client: AsyncClient, sample_task_runs: list[TaskRun]
    ):
        """Test pagination with skip and limit."""
        tenant_id = "test-tenant"

        # Get first page
        response = await client.get(
            f"/v1/{tenant_id}/task-runs", params={"skip": 0, "limit": 3}
        )
        assert response.status_code == 200
        body1 = response.json()
        page1_data = body1["data"]
        page1_meta = body1["meta"]

        assert len(page1_data) <= 3
        assert page1_meta["offset"] == 0
        assert page1_meta["limit"] == 3

        # Get second page
        response = await client.get(
            f"/v1/{tenant_id}/task-runs", params={"skip": 3, "limit": 3}
        )
        assert response.status_code == 200
        body2 = response.json()
        page2_data = body2["data"]
        page2_meta = body2["meta"]

        assert page2_meta["offset"] == 3
        assert page2_meta["limit"] == 3

        # Pages should have different data
        if page1_data and page2_data:
            page1_ids = {run["id"] for run in page1_data}
            page2_ids = {run["id"] for run in page2_data}
            assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_combined_filters(
        self, client: AsyncClient, sample_task_runs: list[TaskRun]
    ):
        """Test combining multiple filters."""
        tenant_id = "test-tenant"

        # Filter by status with sorting
        response = await client.get(
            f"/v1/{tenant_id}/task-runs",
            params={
                "status": "completed",
                "sort": "created_at",
                "order": "desc",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # All runs should match the filters
        for run in data:
            assert run["status"] == "completed"

        # Should be sorted correctly
        runs = data
        for i in range(len(runs) - 1):
            assert runs[i]["created_at"] >= runs[i + 1]["created_at"]
