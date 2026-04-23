"""Integration tests for task run filtering."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.models.task_run import TaskRun


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunFiltering:
    """Test run_context and integration_id filtering on task runs list."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        app.dependency_overrides.clear()

    @pytest.fixture
    async def task_with_runs(
        self, integration_test_session: AsyncSession, tenant_id, unique_id
    ):
        """Create a task with runs of different run_contexts."""
        # Create Component + Task
        component_id = uuid4()
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            kind="task",
            name="Test Task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            component_id=component_id,
            script="return 1",
            function="extraction",
            scope="processing",
            integration_id=f"splunk-{unique_id}",
            origin_type="system",
        )
        integration_test_session.add(task)
        await integration_test_session.flush()

        now = datetime.now(UTC)

        # Create runs with different run_contexts
        runs = {}
        for ctx in ["analysis", "scheduled", "ad_hoc"]:
            run = TaskRun(
                tenant_id=tenant_id,
                task_id=component_id,
                status="completed",
                run_context=ctx,
                started_at=now,
                completed_at=now,
            )
            integration_test_session.add(run)
            runs[ctx] = run

        await integration_test_session.flush()

        return {
            "component_id": component_id,
            "integration_id": f"splunk-{unique_id}",
            "runs": runs,
        }

    async def test_list_task_runs_default_excludes_scheduled(
        self, client, tenant_id, task_with_runs
    ):
        """Default listing excludes scheduled runs."""
        http_client, session = client

        response = await http_client.get(f"/v1/{tenant_id}/task-runs")

        assert response.status_code == 200
        data = response.json()["data"]
        # Default should NOT include 'scheduled' context runs
        run_contexts = []
        for run in data:
            if run.get("task_id") == str(task_with_runs["component_id"]):
                # Check execution_context or rely on the filtering
                run_contexts.append(run)
        # Should see analysis and ad_hoc, NOT scheduled
        assert len(run_contexts) == 2

    async def test_list_task_runs_explicit_scheduled(
        self, client, tenant_id, task_with_runs
    ):
        """Explicit run_context=scheduled returns only scheduled runs."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs?run_context=scheduled"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        matching = [
            r for r in data if r.get("task_id") == str(task_with_runs["component_id"])
        ]
        assert len(matching) == 1

    async def test_list_task_runs_filter_by_integration_id(
        self, client, tenant_id, task_with_runs
    ):
        """integration_id filter returns only matching task runs."""
        http_client, session = client
        integration_id = task_with_runs["integration_id"]

        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs?integration_id={integration_id}&run_context=analysis,ad_hoc,scheduled"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 1
        # All returned runs should be for tasks linked to this integration
        for run in data:
            assert run.get("task_id") == str(task_with_runs["component_id"])

    async def test_list_task_runs_multiple_run_contexts(
        self, client, tenant_id, task_with_runs
    ):
        """run_context=analysis,ad_hoc returns both but not scheduled."""
        http_client, _ = client
        comp_id = str(task_with_runs["component_id"])

        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs?run_context=analysis,ad_hoc"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        matching = [r for r in data if r.get("task_id") == comp_id]
        # Should include analysis and ad_hoc (2 runs), not scheduled
        assert len(matching) == 2

    async def test_list_task_runs_combined_filters(
        self, client, tenant_id, task_with_runs
    ):
        """Combined run_context + integration_id filter narrows results."""
        http_client, _ = client
        integration_id = task_with_runs["integration_id"]
        comp_id = str(task_with_runs["component_id"])

        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs?run_context=scheduled&integration_id={integration_id}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        matching = [r for r in data if r.get("task_id") == comp_id]
        # Only the scheduled run should match both filters
        assert len(matching) == 1

    async def test_list_task_runs_no_matching_integration(
        self, client, tenant_id, task_with_runs
    ):
        """integration_id filter with nonexistent ID returns empty."""
        http_client, _ = client
        fake_int = f"nonexistent-int-{uuid4().hex[:8]}"

        response = await http_client.get(
            f"/v1/{tenant_id}/task-runs?integration_id={fake_int}&run_context=analysis,ad_hoc,scheduled"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 0

    async def test_list_task_runs_default_filter_with_db_verification(
        self, client, tenant_id, task_with_runs
    ):
        """Default filter excludes scheduled -- verified by counting against known data."""
        http_client, _ = client
        comp_id = str(task_with_runs["component_id"])

        # Default (no run_context param uses analysis,ad_hoc)
        default_resp = await http_client.get(f"/v1/{tenant_id}/task-runs")
        default_data = default_resp.json()["data"]
        default_matching = [r for r in default_data if r.get("task_id") == comp_id]

        # Explicit all contexts
        all_resp = await http_client.get(
            f"/v1/{tenant_id}/task-runs?run_context=analysis,ad_hoc,scheduled"
        )
        all_data = all_resp.json()["data"]
        all_matching = [r for r in all_data if r.get("task_id") == comp_id]

        # Default should return 2 (analysis + ad_hoc), all should return 3
        assert len(default_matching) == 2
        assert len(all_matching) == 3
