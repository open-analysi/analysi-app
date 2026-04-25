"""
Integration tests for task-runs list API endpoint.

Tests the /v1/{tenant}/task-runs endpoint functionality:
1. Running same task multiple times with delays
2. Sorting by creation time
3. Filtering by status (succeeded/failed)
4. Pagination
"""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component
from analysi.models.task import Task

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_full_stack,
    pytest.mark.arq_worker,
]


@pytest.mark.integration
class TestTaskRunsListAPI:
    """Integration tests for task-runs list endpoint."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> tuple[AsyncClient, AsyncSession]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, integration_test_session

        app.dependency_overrides.clear()

    @pytest.fixture
    async def test_task(self, integration_test_session) -> Task:
        """Create a simple test task that succeeds."""
        db = integration_test_session
        tenant_id = "test-tenant"

        # Create component for task
        component_id = uuid.uuid4()
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            name="Test Counter Task",
            description="Simple task for testing list API",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        db.add(component)
        await db.flush()

        # Create task
        task_id = uuid.uuid4()
        task = Task(
            id=task_id,
            component_id=component_id,
            function="processing",
            scope="processing",
            script="""
# Simple Cy script that always succeeds
counter = input["counter"]
timestamp = "2025-08-23T12:00:00Z"

return {
    "counter": counter,
    "doubled": counter * 2,
    "timestamp": timestamp,
    "status": "processed"
}
""",
            mode="saved",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        return task

    @pytest.fixture
    async def failing_task(self, integration_test_session) -> Task:
        """Create a test task with bad Cy script that fails."""
        db = integration_test_session
        tenant_id = "test-tenant"

        # Create component for task
        component_id = uuid.uuid4()
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            name="Failing Test Task",
            description="Task with bad Cy script for testing failures",
            categories=["test", "failing"],
            status="enabled",
            kind="task",
        )
        db.add(component)
        await db.flush()

        # Create task with bad Cy script
        task_id = uuid.uuid4()
        task = Task(
            id=task_id,
            component_id=component_id,
            function="processing",
            scope="processing",
            script="""
# Bad Cy script that will fail
undefined_var = nonexistent["field"]
bad_operation = undefined_function()
return {
    "this": "will never execute"
}
""",
            mode="saved",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        return task

    @pytest.mark.asyncio
    async def test_list_task_runs_with_sorting(
        self, client: tuple[AsyncClient, AsyncSession], test_task: Task
    ):
        """
        Test listing task runs with sorting by creation time.
        Runs the same task 3 times with delays to ensure different timestamps.
        """
        # Unpack client and session from fixture
        http_client, session = client
        tenant_id = "test-tenant"
        task_id = test_task.component_id  # Use component_id as the public task ID

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Run the same task 3 times with delays
        run_ids = []
        for i in range(3):
            # Execute task
            response = await http_client.post(
                f"/v1/{tenant_id}/tasks/{task_id}/run",
                json={"input": {"counter": i + 1}},
            )
            assert response.status_code == 202
            run_data = response.json()["data"]
            run_ids.append(run_data["trid"])

            # Add delay between executions (except after last one)
            if i < 2:
                await asyncio.sleep(0.2)  # 200ms delay

        # Wait for all tasks to complete
        await asyncio.sleep(2)

        # Test 1: List all task runs for this task (default: desc by created_at)
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"task_id": str(task_id), "limit": 10}
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        meta = body["meta"]

        assert meta["total"] >= 3
        assert len(data) >= 3

        # Verify default sorting (desc by created_at - newest first)
        task_runs = data
        for i in range(len(task_runs) - 1):
            assert task_runs[i]["created_at"] >= task_runs[i + 1]["created_at"]

        # Test 2: Sort by created_at ascending (oldest first)
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs",
            params={
                "task_id": str(task_id),
                "sort": "created_at",
                "order": "asc",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]

        task_runs_asc = data
        for i in range(len(task_runs_asc) - 1):
            assert task_runs_asc[i]["created_at"] <= task_runs_asc[i + 1]["created_at"]

        # Test 3: Verify the runs we created are present
        our_run_ids = {str(rid) for rid in run_ids}
        returned_run_ids = {run["id"] for run in data}
        assert our_run_ids.issubset(returned_run_ids)

    @pytest.mark.asyncio
    async def test_filter_by_status(
        self,
        client: tuple[AsyncClient, AsyncSession],
        test_task: Task,
        failing_task: Task,
    ):
        """
        Test filtering task runs by status.
        Executes both succeeding and failing tasks, then filters by status.
        """
        # Unpack client and session from fixture
        http_client, session = client
        tenant_id = "test-tenant"

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Run the succeeding task twice
        success_runs = []
        for i in range(2):
            response = await http_client.post(
                f"/v1/{tenant_id}/tasks/{test_task.component_id}/run",
                json={"input": {"counter": i + 10}},
            )
            assert response.status_code == 202
            success_runs.append(response.json()["data"]["trid"])

        # Run the failing task twice
        failed_runs = []
        for i in range(2):
            response = await http_client.post(
                f"/v1/{tenant_id}/tasks/{failing_task.component_id}/run",
                json={"input": {"value": i}},
            )
            assert response.status_code == 202
            failed_runs.append(response.json()["data"]["trid"])

        # Wait for background tasks to complete
        await asyncio.sleep(15)

        # Test 1: Filter by status=succeeded
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"status": "completed", "limit": 50}
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        meta = body["meta"]

        print(f"Total succeeded runs found: {meta['total']}")
        print(f"Returned succeeded runs: {len(data)}")

        # All returned runs should have status=succeeded
        for run in data:
            assert run["status"] == "completed"

        # Our successful runs should be in the results
        success_run_ids = {str(rid) for rid in success_runs}
        returned_ids = {run["id"] for run in data}

        if not success_run_ids.issubset(returned_ids):
            print(f"Expected success runs: {success_run_ids}")
            print(f"Returned run IDs: {returned_ids}")
            print("Missing runs:", success_run_ids - returned_ids)

        assert success_run_ids.issubset(returned_ids)

        # Test 2: Filter by status=failed
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"status": "failed", "limit": 50}
        )
        assert response.status_code == 200
        body = response.json()
        data = body["data"]

        # All returned runs should have status=failed
        for run in data:
            assert run["status"] == "failed"

        # Our failed runs should be in the results
        failed_run_ids = {str(rid) for rid in failed_runs}
        returned_ids = {run["id"] for run in data}
        assert failed_run_ids.issubset(returned_ids)

    @pytest.mark.asyncio
    async def test_pagination(
        self, client: tuple[AsyncClient, AsyncSession], test_task: Task
    ):
        """
        Test pagination with skip and limit parameters.
        """
        # Unpack client and session from fixture
        http_client, session = client
        tenant_id = "test-tenant"
        task_id = test_task.component_id

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Run task 5 times to ensure we have enough data
        for i in range(5):
            response = await http_client.post(
                f"/v1/{tenant_id}/tasks/{task_id}/run",
                json={"input": {"counter": i + 100}},
            )
            assert response.status_code == 202
            await asyncio.sleep(0.1)  # Small delay between runs

        # Wait for tasks to complete
        await asyncio.sleep(2)

        # Test 1: Get first page (limit=2)
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"task_id": str(task_id), "skip": 0, "limit": 2},
        )
        assert response.status_code == 200
        body1 = response.json()
        page1_data = body1["data"]
        page1_meta = body1["meta"]

        assert len(page1_data) == 2
        assert page1_meta["limit"] == 2
        assert page1_meta["offset"] == 0
        assert page1_meta["total"] >= 5

        # Test 2: Get second page (skip=2, limit=2)
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"task_id": str(task_id), "skip": 2, "limit": 2},
        )
        assert response.status_code == 200
        body2 = response.json()
        page2_data = body2["data"]
        page2_meta = body2["meta"]

        assert len(page2_data) == 2
        assert page2_meta["offset"] == 2

        # Test 3: Verify pages have different data
        page1_ids = {run["id"] for run in page1_data}
        page2_ids = {run["id"] for run in page2_data}
        assert page1_ids.isdisjoint(page2_ids)  # No overlap

    @pytest.mark.asyncio
    async def test_invalid_parameters(self, client: tuple[AsyncClient, AsyncSession]):
        """
        Test error handling for invalid query parameters.
        """
        # Unpack client and session from fixture
        http_client, session = client
        tenant_id = "test-tenant"

        # Test 1: Invalid sort field
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"sort": "invalid_field"}
        )
        assert response.status_code == 400
        assert "Invalid sort field" in response.json()["detail"]

        # Test 2: Invalid order
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"order": "invalid_order"}
        )
        assert response.status_code == 400
        assert "Invalid order" in response.json()["detail"]

        # Test 3: Negative skip
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"skip": -1}
        )
        assert response.status_code == 422  # Pydantic validation error

        # Test 4: Limit too high
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"limit": 101}
        )
        assert response.status_code == 422  # Exceeds max limit of 100

    @pytest.mark.asyncio
    async def test_filter_by_workflow_run_id(
        self, client: tuple[AsyncClient, AsyncSession], test_task: Task
    ):
        """
        Test filtering task runs by workflow_run_id.
        Creates task runs with different workflow_run_ids and verifies filtering works.
        """
        # Unpack client and session from fixture
        http_client, session = client
        tenant_id = "test-tenant"

        # Generate unique workflow run IDs
        workflow_run_id_1 = str(uuid.uuid4())
        workflow_run_id_2 = str(uuid.uuid4())

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Create task runs associated with workflow 1
        workflow_1_runs = []
        for i in range(2):
            # Create task run directly with workflow_run_id
            from analysi.services.task_run import TaskRunService

            task_run_service = TaskRunService()
            task_run = await task_run_service.create_execution(
                session=session,
                tenant_id=tenant_id,
                task_id=test_task.component_id,
                cy_script=None,
                input_data={"counter": i},
                executor_config=None,
                workflow_run_id=uuid.UUID(workflow_run_id_1),
            )
            workflow_1_runs.append(str(task_run.id))

        # Create task runs associated with workflow 2
        workflow_2_runs = []
        for i in range(2):
            task_run = await task_run_service.create_execution(
                session=session,
                tenant_id=tenant_id,
                task_id=test_task.component_id,
                cy_script=None,
                input_data={"counter": i + 10},
                executor_config=None,
                workflow_run_id=uuid.UUID(workflow_run_id_2),
            )
            workflow_2_runs.append(str(task_run.id))

        # Create task runs without workflow association
        standalone_runs = []
        for i in range(2):
            task_run = await task_run_service.create_execution(
                session=session,
                tenant_id=tenant_id,
                task_id=test_task.component_id,
                cy_script=None,
                input_data={"counter": i + 20},
                executor_config=None,
                workflow_run_id=None,
            )
            standalone_runs.append(str(task_run.id))

        await session.commit()

        # Test 1: Filter by workflow_run_id_1
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"workflow_run_id": workflow_run_id_1, "limit": 50},
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # Should only return task runs from workflow 1
        returned_ids = {run["id"] for run in data}
        assert len(returned_ids) >= 2  # At least our 2 runs

        # All returned runs should have the correct workflow_run_id
        for run in data:
            if run["id"] in workflow_1_runs:
                assert run["workflow_run_id"] == workflow_run_id_1

        # Our workflow 1 runs should be in the results
        assert set(workflow_1_runs).issubset(returned_ids)

        # Workflow 2 and standalone runs should NOT be in the results
        assert set(workflow_2_runs).isdisjoint(returned_ids)
        assert set(standalone_runs).isdisjoint(returned_ids)

        # Test 2: Filter by workflow_run_id_2
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs",
            params={"workflow_run_id": workflow_run_id_2, "limit": 50},
        )
        assert response.status_code == 200
        data = response.json()["data"]

        returned_ids = {run["id"] for run in data}
        assert len(returned_ids) >= 2  # At least our 2 runs

        # All returned runs should have the correct workflow_run_id
        for run in data:
            if run["id"] in workflow_2_runs:
                assert run["workflow_run_id"] == workflow_run_id_2

        # Our workflow 2 runs should be in the results
        assert set(workflow_2_runs).issubset(returned_ids)

        # Workflow 1 and standalone runs should NOT be in the results
        assert set(workflow_1_runs).isdisjoint(returned_ids)
        assert set(standalone_runs).isdisjoint(returned_ids)

        # Test 3: Get all task runs (no filter) - should include all
        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs", params={"limit": 50}
        )
        assert response.status_code == 200
        data = response.json()["data"]

        all_returned_ids = {run["id"] for run in data}
        all_our_runs = set(workflow_1_runs + workflow_2_runs + standalone_runs)

        # All our created runs should be present when no filter is applied
        assert all_our_runs.issubset(all_returned_ids)
