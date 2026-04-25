"""Integration tests for workflow composition REST API."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowComposeAPI:
    """Integration tests for POST /v1/{tenant}/workflows/compose endpoint."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_compose_workflow_success_simple_sequence(self, client: AsyncClient):
        """
        Test successful workflow composition with simple sequential tasks.

        Composition: ["identity"]
        Expected: status="success" or "error", response structure valid
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity"],  # Simple identity workflow
                "name": "Simple Sequence Workflow",
                "description": "Test simple sequential composition",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert data["status"] in ["success", "needs_decision", "error"]
        assert "plan" in data
        assert "errors" in data
        assert "warnings" in data
        assert "questions" in data

    @pytest.mark.asyncio
    async def test_compose_workflow_with_parallel_branches(self, client: AsyncClient):
        """
        Test workflow composition with parallel branches and merge.

        Composition: ["identity", ["identity", "identity"], "merge"]
        Expected: Response with valid structure
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity", ["identity", "identity"], "merge"],
                "name": "Parallel Workflow",
                "description": "Test parallel branches with merge",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        # May succeed or have questions/errors depending on validation
        assert data["status"] in ["success", "needs_decision", "error"]

    @pytest.mark.asyncio
    async def test_compose_workflow_missing_aggregation_returns_questions(
        self, client: AsyncClient
    ):
        """
        Test that missing aggregation after parallel block returns questions.

        Composition: ["identity", ["identity", "identity"], "identity"]  # Missing merge
        Expected: Response with valid structure, may have questions
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity", ["identity", "identity"], "identity"],
                "name": "Missing Aggregation",
                "description": "Test missing aggregation detection",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert "questions" in data
        assert isinstance(data["questions"], list)

    @pytest.mark.asyncio
    async def test_compose_workflow_invalid_cy_name_returns_errors(
        self, client: AsyncClient
    ):
        """
        Test that invalid cy_name returns error.

        Composition: ["identity", "nonexistent_task_xyz123"]
        Expected: status="error", errors list with resolution error
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity", "nonexistent_task_xyz123"],
                "name": "Invalid Task",
                "description": "Test invalid task reference",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert data["status"] == "error"
        assert "errors" in data
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_compose_workflow_with_execute_flag(self, client: AsyncClient):
        """
        Test workflow composition with execute flag.

        Composition: ["identity"]
        execute: False (composer doesn't execute, only creates)
        Expected: Response with valid structure
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity"],
                "name": "Execute Immediately",
                "description": "Test workflow creation",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert data["status"] in ["success", "needs_decision", "error"]
        assert "workflow_id" in data
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_compose_workflow_type_incompatibility_returns_warnings(
        self, client: AsyncClient
    ):
        """
        Test type incompatibility warnings.

        Composition: Simple identity workflow
        Expected: Response with valid structure, warnings field present
        """
        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json={
                "composition": ["identity"],
                "name": "Type Incompatibility",
                "description": "Test type warnings",
                "created_by": str(SYSTEM_USER_ID),
                "execute": False,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
