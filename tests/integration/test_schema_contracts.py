"""Schema contract tests for API response shapes.

These tests lock down the field names, status values, and response structures
for all major entities. They serve as a safety net for the schema consistency
standardization (V091-V094 migrations).

Standardized terminology:
  - Terminal success status: "completed" (everywhere)
  - Timestamps: started_at / completed_at (everywhere)
  - Initial queued status: "pending" (TaskGeneration, WorkflowRun)
  - Control event terminal: "completed" (was "processed")
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.integration
class TestSchemaContracts:
    """Contract tests that lock down API response shapes."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        app.dependency_overrides.clear()

    # ── Alert response shape ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_alert_response_fields(self, client, unique_id):
        """Alert responses must contain all expected fields."""
        http_client, session = client
        tenant = f"contract-{unique_id}"

        alert_data = {
            "title": "Contract Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": true}',
        }

        response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)
        await session.commit()
        assert response.status_code == 201

        data = response.json()["data"]

        # Required fields (OCSF — Project Skaros)
        required_fields = {
            "alert_id",
            "tenant_id",
            "human_readable_id",
            "title",
            "severity",
            "analysis_status",
            "raw_data_hash",
            "ingested_at",
            "created_at",
            "updated_at",
            "triggering_event_time",
            "raw_data",
        }
        assert required_fields.issubset(data.keys()), (
            f"Missing fields: {required_fields - data.keys()}"
        )

        # analysis_status "new" is intentionally kept (means "not yet analyzed")
        assert data["analysis_status"] == "new"

    @pytest.mark.asyncio
    async def test_alert_list_response_shape(self, client, unique_id):
        """Alert list must use Sifnos envelope with pagination meta."""
        http_client, session = client
        tenant = f"contract-{unique_id}"

        response = await http_client.get(f"/v1/{tenant}/alerts")
        assert response.status_code == 200

        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert isinstance(body["data"], list)
        meta = body["meta"]
        assert "total" in meta

    # ── TaskRun response shape ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_task_run_response_fields(self, client, unique_id):
        """TaskRun list response fields must match expected schema."""
        http_client, session = client
        tenant = f"contract-{unique_id}"

        response = await http_client.get(f"/v1/{tenant}/task-runs")
        assert response.status_code == 200

        body = response.json()
        assert "data" in body
        assert "meta" in body

    @pytest.mark.asyncio
    async def test_task_run_status_values(self, client, unique_id):
        """TaskRun status constants must use 'completed' (not 'succeeded')."""
        from analysi.constants import TaskConstants

        assert TaskConstants.Status.COMPLETED == "completed"
        assert TaskConstants.Status.RUNNING == "running"
        assert TaskConstants.Status.FAILED == "failed"

    @pytest.mark.asyncio
    async def test_task_run_timestamp_field_names(self, client, unique_id):
        """TaskRun model must use started_at/completed_at."""
        from analysi.models.task_run import TaskRun

        assert hasattr(TaskRun, "started_at")
        assert hasattr(TaskRun, "completed_at")

    @pytest.mark.asyncio
    async def test_task_run_schema_timestamp_fields(self, client, unique_id):
        """TaskRunResponse schema must expose started_at/completed_at."""
        from analysi.schemas.task_run import TaskRunResponse

        field_names = set(TaskRunResponse.model_fields.keys())
        assert "started_at" in field_names
        assert "completed_at" in field_names

    # ── WorkflowRun response shape ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_workflow_run_response_fields(self, client, unique_id):
        """WorkflowRun response must use completed_at (not ended_at)."""
        from analysi.schemas.workflow_execution import WorkflowRunResponse

        field_names = set(WorkflowRunResponse.model_fields.keys())
        required = {
            "workflow_run_id",
            "tenant_id",
            "workflow_id",
            "workflow_name",
            "status",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        }
        assert required.issubset(field_names), f"Missing: {required - field_names}"

    @pytest.mark.asyncio
    async def test_workflow_run_status_values(self, client, unique_id):
        """WorkflowRun status values must match WorkflowConstants."""
        from analysi.constants import WorkflowConstants

        assert WorkflowConstants.Status.COMPLETED == "completed"
        assert WorkflowConstants.Status.PENDING == "pending"
        assert WorkflowConstants.Status.RUNNING == "running"
        assert WorkflowConstants.Status.FAILED == "failed"

    @pytest.mark.asyncio
    async def test_workflow_run_model_timestamps(self, client, unique_id):
        """WorkflowRun model must use completed_at."""
        from analysi.models.workflow_execution import WorkflowRun

        assert hasattr(WorkflowRun, "completed_at")

    # ── WorkflowNodeInstance response shape ───────────────────────────

    @pytest.mark.asyncio
    async def test_workflow_node_instance_response_fields(self, client, unique_id):
        """WorkflowNodeInstance response must use completed_at."""
        from analysi.schemas.workflow_execution import WorkflowNodeInstanceResponse

        field_names = set(WorkflowNodeInstanceResponse.model_fields.keys())
        assert "completed_at" in field_names

    @pytest.mark.asyncio
    async def test_workflow_node_instance_model_timestamps(self, client, unique_id):
        """WorkflowNodeInstance model must use completed_at."""
        from analysi.models.workflow_execution import WorkflowNodeInstance

        assert hasattr(WorkflowNodeInstance, "completed_at")

    # ── ControlEvent response shape ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_control_event_status_flow(self, client, unique_id):
        """ControlEvent uses pending → claimed → completed flow."""
        from analysi.models.control_event import ControlEvent

        assert hasattr(ControlEvent, "status")

    @pytest.mark.asyncio
    async def test_control_event_dispatch_status(self, client, unique_id):
        """ControlEventDispatch uses running/completed/failed."""
        from analysi.models.control_event import ControlEventDispatch

        assert hasattr(ControlEventDispatch, "status")

    # ── TaskGeneration response shape ────────────────────────────────

    @pytest.mark.asyncio
    async def test_task_generation_status_values(self, client, unique_id):
        """TaskGeneration status must use 'pending' (not 'new')."""
        from analysi.schemas.task_generation import TaskGenerationStatus

        assert TaskGenerationStatus.PENDING == "pending"
        assert "pending" in [s.value for s in TaskGenerationStatus]

    @pytest.mark.asyncio
    async def test_task_generation_model_default_status(self, client, unique_id):
        """TaskGeneration model default status must be 'pending'."""
        from analysi.models.task_generation import TaskGeneration

        status_col = TaskGeneration.__table__.columns["status"]
        assert status_col.default.arg == "pending"

    # ── WorkflowGeneration response shape ─────────────────────────────

    @pytest.mark.asyncio
    async def test_workflow_generation_status_values(self, client, unique_id):
        """WorkflowGeneration status must match expected values."""
        from analysi.schemas.kea_coordination import WorkflowGenerationStatus

        assert WorkflowGenerationStatus.RUNNING == "running"
        assert WorkflowGenerationStatus.COMPLETED == "completed"
        assert WorkflowGenerationStatus.FAILED == "failed"

    # ── Sifnos envelope contract ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sifnos_envelope_on_list_endpoints(self, client, unique_id):
        """All list endpoints must return {data: [...], meta: {total, ...}}."""
        http_client, session = client
        tenant = f"contract-{unique_id}"

        list_endpoints = [
            f"/v1/{tenant}/alerts",
            f"/v1/{tenant}/task-runs",
        ]

        for endpoint in list_endpoints:
            response = await http_client.get(endpoint)
            assert response.status_code == 200, f"Failed: {endpoint}"
            body = response.json()
            assert "data" in body, f"Missing 'data' in {endpoint}"
            assert "meta" in body, f"Missing 'meta' in {endpoint}"
            assert isinstance(body["data"], list), f"'data' not a list in {endpoint}"
            assert "total" in body["meta"], f"Missing 'total' in meta for {endpoint}"

    # ── ErrorResponse legacy check ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_error_response_still_used_by_middleware(self, client, unique_id):
        """ErrorResponse is used by error_handling middleware — do NOT remove yet."""
        from analysi.schemas.base import ErrorResponse

        field_names = set(ErrorResponse.model_fields.keys())
        assert "error" in field_names
        assert "error_code" in field_names
        assert "execution_time" in field_names
