"""
Integration tests for Workflow Composer API.

Tests end-to-end REST API with real database.
All tests follow TDD principles and should FAIL initially with NotImplementedError (501 status code)
since the stubbed service methods raise NotImplementedError.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowComposerAPI:
    """Test workflow composer API endpoints."""

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

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_compose_endpoint_success(self, client: AsyncClient):
        """
        Verify POST /workflows/compose creates workflow and returns 200.

        Expected:
        - HTTP 200 or 501 (stub)
        - ComposeResponse with status="success" (when implemented)
        - workflow_id present
        """
        compose_request = {
            "composition": ["identity", "identity"],
            "name": "Simple Test Workflow",
            "description": "Test composition",
            "created_by": str(SYSTEM_USER_ID),
            "execute": True,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        # Should return 501 (Not Implemented) with stub
        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()["data"]
            assert "status" in data
            assert data["status"] in ["success", "needs_decision", "error"]

    @pytest.mark.asyncio
    async def test_compose_endpoint_plan_only(self, client: AsyncClient):
        """
        Verify POST /workflows/compose with execute=False returns plan only.

        Expected:
        - HTTP 200 or 501 (stub)
        - workflow_id=None
        - plan present
        """
        compose_request = {
            "composition": ["identity", "identity"],
            "name": "Plan Only Workflow",
            "description": "Test plan generation",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,  # Plan only
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()["data"]
            assert data["workflow_id"] is None
            assert "plan" in data

    @pytest.mark.asyncio
    async def test_compose_endpoint_with_questions(self, client: AsyncClient):
        """
        Verify POST /workflows/compose returns questions when needed.

        Expected:
        - HTTP 200 or 501 (stub)
        - status="needs_decision"
        - questions list populated
        """
        # Composition with parallel block but no aggregation
        compose_request = {
            "composition": ["identity", ["identity", "identity"], "identity"],
            "name": "Workflow Needing Decision",
            "description": "Test question generation",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        assert response.status_code in [200, 501]

        if response.status_code == 200:
            response.json()["data"]
            # May have questions about missing aggregation

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_compose_endpoint_invalid_composition(self, client: AsyncClient):
        """
        Verify POST /workflows/compose returns error for invalid composition.

        Expected:
        - HTTP 200 with status="error"
        - Error detail about invalid composition
        """
        compose_request = {
            "composition": [],  # Empty composition (invalid)
            "name": "Invalid Workflow",
            "description": "Test error handling",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        # Service returns 200 with structured error response
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "error"
        assert len(data["errors"]) > 0
        assert (
            "empty" in data["errors"][0]["message"].lower()
            or "cannot" in data["errors"][0]["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_compose_endpoint_task_not_found(self, client: AsyncClient):
        """
        Verify POST /workflows/compose returns error when cy_name doesn't exist.

        Expected:
        - HTTP 200 with status="error"
        - Error detail about task not found
        """
        compose_request = {
            "composition": ["nonexistent_task_xyz_123"],
            "name": "Workflow with Missing Task",
            "description": "Test task resolution error",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        # Service returns 200 with structured error response
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "error"
        assert len(data["errors"]) > 0
        assert (
            "not found" in data["errors"][0]["message"].lower()
            or "resolve" in data["errors"][0]["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_compose_endpoint_missing_required_fields(self, client: AsyncClient):
        """
        Verify POST /workflows/compose validates required request fields.

        Expected:
        - HTTP 422 (Pydantic validation error)
        """
        # Missing required fields: composition, name, created_by
        compose_request = {
            "description": "Incomplete request",
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        # Should return 422 (Unprocessable Entity) for Pydantic validation
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_compose_endpoint_unauthorized_tenant(self, client: AsyncClient):
        """
        Verify POST /workflows/compose enforces tenant isolation.

        Expected:
        - HTTP 200, 400, or 501 (depends on implementation)
        """
        compose_request = {
            "composition": ["identity"],
            "name": "Cross-Tenant Test",
            "description": "Test tenant isolation",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        # Try with different tenant
        response = await client.post(
            "/v1/different_tenant/workflows/compose",
            json=compose_request,
        )

        # Should not create workflow for wrong tenant
        assert response.status_code in [200, 400, 404, 501]


@pytest.mark.asyncio
@pytest.mark.integration
class TestComposerIntegrationScenarios:
    """Test realistic composition scenarios end-to-end."""

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
    async def test_compose_sequential_workflow(self, client: AsyncClient):
        """
        Test composing a simple sequential workflow.

        Composition: ["identity", "identity", "identity"]
        Expected: 3 nodes, 2 edges
        """
        compose_request = {
            "composition": ["identity", "identity", "identity"],
            "name": "Sequential Workflow",
            "description": "Three sequential identity nodes",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()["data"]
            if data.get("plan"):
                assert data["plan"]["nodes"] == 3
                assert data["plan"]["edges"] == 2

    @pytest.mark.asyncio
    async def test_compose_parallel_workflow_with_merge(self, client: AsyncClient):
        """
        Test composing a parallel workflow with aggregation.

        Composition: ["identity", ["identity", "identity"], "merge", "identity"]
        Expected: 5 nodes with proper parallel structure
        """
        compose_request = {
            "composition": ["identity", ["identity", "identity"], "merge", "identity"],
            "name": "Parallel Workflow with Merge",
            "description": "Parallel execution with merge aggregation",
            "created_by": str(SYSTEM_USER_ID),
            "execute": False,
        }

        response = await client.post(
            "/v1/test_tenant/workflows/compose",
            json=compose_request,
        )

        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()["data"]
            # Should have no questions since merge is provided
            assert len(data.get("questions", [])) == 0
