"""
Integration tests for task-run enrichment API endpoint.

Tests the GET /v1/{tenant}/task-runs/{trid}/enrichment endpoint
that extracts enrichment data added by enrich_alert().
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.task_run import TaskRun


@pytest.mark.integration
class TestTaskRunEnrichmentAPI:
    """Integration tests for task-run enrichment endpoint."""

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
    async def task_run_with_enrichment(self, integration_test_session) -> TaskRun:
        """Create a task run with enrichment output."""
        db = integration_test_session
        tenant_id = "test-tenant"

        # Output simulating enrich_alert() result
        output_data = {
            "title": "Suspicious IP Communication",
            "severity": "high",
            "enrichments": {
                "vt_ip_reputation": {
                    "ip": "185.220.101.1",
                    "malicious_score": 85,
                    "reputation": -50,
                    "country": "DE",
                }
            },
        }

        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            task_id=None,
            status="completed",
            cy_script="return enrich_alert(input, enrichment)",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
            duration=timedelta(seconds=30),
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC),
            input_type="inline",
            input_location='{"title": "Test Alert"}',
            output_type="inline",
            output_location=json.dumps(output_data),
            execution_context={"cy_name": "vt_ip_reputation", "tenant_id": tenant_id},
        )
        db.add(task_run)
        await db.commit()
        await db.refresh(task_run)

        return task_run

    @pytest.fixture
    async def task_run_without_enrichment(self, integration_test_session) -> TaskRun:
        """Create a task run without enrichment output."""
        db = integration_test_session
        tenant_id = "test-tenant"

        # Output without enrichments field
        output_data = {"result": "some_value", "status": "ok"}

        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            task_id=None,
            status="completed",
            cy_script="return result",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
            duration=timedelta(seconds=10),
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC),
            input_type="inline",
            input_location="{}",
            output_type="inline",
            output_location=json.dumps(output_data),
            execution_context={"cy_name": "other_task", "tenant_id": tenant_id},
        )
        db.add(task_run)
        await db.commit()
        await db.refresh(task_run)

        return task_run

    @pytest.fixture
    async def task_run_no_cy_name(self, integration_test_session) -> TaskRun:
        """Create a task run without cy_name in execution context."""
        db = integration_test_session
        tenant_id = "test-tenant"

        output_data = {"enrichments": {"unknown_task": {"data": "value"}}}

        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            task_id=None,
            status="completed",
            cy_script="return enrich_alert(input, data)",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
            duration=timedelta(seconds=5),
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC),
            input_type="inline",
            input_location="{}",
            output_type="inline",
            output_location=json.dumps(output_data),
            execution_context={"tenant_id": tenant_id},  # No cy_name
        )
        db.add(task_run)
        await db.commit()
        await db.refresh(task_run)

        return task_run

    @pytest.mark.asyncio
    async def test_get_enrichment_success(
        self, client: AsyncClient, task_run_with_enrichment: TaskRun
    ):
        """Test getting enrichment data from a task run with enrichment."""
        tenant_id = "test-tenant"
        trid = task_run_with_enrichment.id

        response = await client.get(f"/v1/{tenant_id}/task-runs/{trid}/enrichment")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["trid"] == str(trid)
        assert data["cy_name"] == "vt_ip_reputation"
        assert data["has_enrichment"] is True
        assert data["status"] == "completed"

        # Check enrichment content
        enrichment = data["enrichment"]
        assert enrichment["ip"] == "185.220.101.1"
        assert enrichment["malicious_score"] == 85
        assert enrichment["country"] == "DE"

    @pytest.mark.asyncio
    async def test_get_enrichment_no_enrichment_data(
        self, client: AsyncClient, task_run_without_enrichment: TaskRun
    ):
        """Test getting enrichment from a task run without enrichment data."""
        tenant_id = "test-tenant"
        trid = task_run_without_enrichment.id

        response = await client.get(f"/v1/{tenant_id}/task-runs/{trid}/enrichment")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["trid"] == str(trid)
        assert data["cy_name"] == "other_task"
        assert data["has_enrichment"] is False
        assert data["enrichment"] is None
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_enrichment_no_cy_name(
        self, client: AsyncClient, task_run_no_cy_name: TaskRun
    ):
        """Test getting enrichment from a task run without cy_name."""
        tenant_id = "test-tenant"
        trid = task_run_no_cy_name.id

        response = await client.get(f"/v1/{tenant_id}/task-runs/{trid}/enrichment")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["trid"] == str(trid)
        assert data["cy_name"] is None  # No cy_name in execution_context
        assert data["has_enrichment"] is False  # Can't extract without cy_name
        assert data["enrichment"] is None

    @pytest.mark.asyncio
    async def test_get_enrichment_not_found(self, client: AsyncClient):
        """Test getting enrichment for non-existent task run."""
        tenant_id = "test-tenant"
        fake_trid = uuid.uuid4()

        response = await client.get(f"/v1/{tenant_id}/task-runs/{fake_trid}/enrichment")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_enrichment_tenant_isolation(
        self, client: AsyncClient, task_run_with_enrichment: TaskRun
    ):
        """Test that enrichment endpoint respects tenant isolation."""
        other_tenant = "other-tenant"
        trid = task_run_with_enrichment.id

        # Task run belongs to "test-tenant", not "other-tenant"
        response = await client.get(f"/v1/{other_tenant}/task-runs/{trid}/enrichment")
        assert response.status_code == 404


@pytest.mark.integration
class TestEnrichAlertExecutionFlow:
    """Test full execution flow: task runs, cy_name persisted, enrichment extracted."""

    @pytest.fixture
    async def setup_task_with_cy_name(self, integration_test_session):
        """Create a task with cy_name that uses enrich_alert()."""
        from analysi.models.component import Component
        from analysi.models.task import Task

        tenant_id = f"enrich-test-{uuid.uuid4().hex[:8]}"
        component_id = uuid.uuid4()
        cy_name = "test_enrichment_task"

        # Create Component with cy_name
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            name="Test Enrichment Task",
            cy_name=cy_name,
            description="Task for testing enrich_alert flow",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create Task with script that uses enrich_alert()
        task = Task(
            id=uuid.uuid4(),
            component_id=component_id,
            function="processing",
            scope="processing",
            script="""# Test enrich_alert
enrichment_data = {"score": 95, "verdict": "clean", "source": "test"}
return enrich_alert(input, enrichment_data)
""",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return {
            "tenant_id": tenant_id,
            "component_id": component_id,
            "cy_name": cy_name,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_execution_persists_cy_name_to_execution_context(
        self, integration_test_session, setup_task_with_cy_name
    ):
        """
        Test that when a task executes, cy_name is persisted to task_run.execution_context.

        This is critical for the enrichment endpoint to work correctly.
        """
        from analysi.models.task_run import TaskRun
        from analysi.services.task_execution import TaskExecutionService

        tenant_id = setup_task_with_cy_name["tenant_id"]
        component_id = setup_task_with_cy_name["component_id"]
        expected_cy_name = setup_task_with_cy_name["cy_name"]

        # Create TaskRun (task_id references component_id per FK constraint)
        task_run_id = uuid.uuid4()
        task_run = TaskRun(
            id=task_run_id,
            task_id=component_id,
            tenant_id=tenant_id,
            status="running",
            input_type="inline",
            input_location=json.dumps({"title": "Test Alert", "severity": "high"}),
            execution_context={},  # Initially empty - should be populated during execution
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute the task using the new API (task_run_id, tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Expire and refresh to get updated execution_context from DB
        integration_test_session.expire_all()
        await integration_test_session.refresh(task_run)

        # Verify cy_name was persisted to execution_context
        assert task_run.execution_context is not None, (
            "execution_context should not be None"
        )
        assert "cy_name" in task_run.execution_context, (
            f"cy_name should be in execution_context. Got: {task_run.execution_context}"
        )
        assert task_run.execution_context["cy_name"] == expected_cy_name, (
            f"Expected cy_name='{expected_cy_name}', got '{task_run.execution_context.get('cy_name')}'"
        )

    @pytest.mark.asyncio
    async def test_enrichment_endpoint_with_executed_task(
        self, integration_test_session, setup_task_with_cy_name
    ):
        """
        End-to-end test: execute task with enrich_alert(), then verify enrichment endpoint.

        This tests the full flow:
        1. Task executes and uses enrich_alert()
        2. cy_name is persisted to execution_context
        3. Enrichment endpoint extracts the correct enrichment data
        """
        from httpx import ASGITransport, AsyncClient

        from analysi.db.session import get_db
        from analysi.main import app
        from analysi.models.task_run import TaskRun
        from analysi.services.task_execution import TaskExecutionService

        tenant_id = setup_task_with_cy_name["tenant_id"]
        component_id = setup_task_with_cy_name["component_id"]
        expected_cy_name = setup_task_with_cy_name["cy_name"]

        # Create and execute task run
        task_run_id = uuid.uuid4()
        task_run = TaskRun(
            id=task_run_id,
            task_id=component_id,
            tenant_id=tenant_id,
            status="running",
            input_type="inline",
            input_location=json.dumps({"title": "Alert for Enrichment Test"}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Use execute_and_persist to write output to DB (execute_single_task does NOT write output)
        execution_service = TaskExecutionService()
        await execution_service.execute_and_persist(task_run_id, tenant_id)

        # Expire cached objects so the test session sees the updated data from execute_and_persist
        integration_test_session.expire_all()

        # Set up test client
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Call enrichment endpoint
                response = await client.get(
                    f"/v1/{tenant_id}/task-runs/{task_run_id}/enrichment"
                )

                assert response.status_code == 200, (
                    f"Expected 200, got {response.status_code}: {response.text}"
                )

                data = response.json()["data"]
                assert data["trid"] == str(task_run_id)
                assert data["cy_name"] == expected_cy_name
                assert data["has_enrichment"] is True, (
                    f"Expected has_enrichment=True. Response: {data}"
                )
                assert data["status"] == "completed"

                # Verify enrichment content matches what enrich_alert() stored
                enrichment = data["enrichment"]
                assert enrichment is not None, "enrichment should not be None"
                assert enrichment["score"] == 95
                assert enrichment["verdict"] == "clean"
                assert enrichment["source"] == "test"
        finally:
            app.dependency_overrides.clear()
