"""
Integration tests for Workflow Execution API endpoints.
These tests use real database and HTTP client, following TDD principles.
All tests should FAIL initially since endpoints aren't fully implemented yet.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecutionEndpoints:
    """Test workflow execution REST API endpoints."""

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

    @pytest.fixture
    async def sample_workflow_id(self, client: AsyncClient) -> str:
        """Create a sample workflow for testing execution."""
        # First create a node template
        template_data = {
            "name": "Test Template",
            "type": "static",
            "description": "A test template for workflow execution",
            "code": "return {'result': 'test output'}",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        # Create a basic workflow using the template
        workflow_data = {
            "name": "Test Execution Workflow",
            "description": "A workflow for testing execution",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                },
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            },
            "data_samples": [
                {"alert": {"id": "AL-001", "severity": "high"}}  # Required by Rodos
            ],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-start",
                    "kind": "transformation",
                    "name": "Start Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                    "is_start_node": True,  # Required by Rodos
                }
            ],
            "edges": [],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert response.status_code == 201
        return response.json()["data"]["id"]

    # Workflow Execution Startup Tests
    @pytest.mark.asyncio
    async def test_start_workflow_execution_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test POST /workflows/{id}/run returns 202."""
        execution_data = {
            "input_data": {
                "alert": {
                    "type": "security",
                    "severity": "high",
                    "message": "Suspicious activity detected",
                }
            }
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )

        # Should return 202 Accepted for async operation
        assert response.status_code == 202

        body = response.json()
        response_data = body["data"]
        assert "workflow_run_id" in response_data
        assert "status" in response_data
        assert response_data["status"] == "pending"
        assert "message" in response_data
        assert "Workflow execution initiated" in response_data["message"]

    @pytest.mark.asyncio
    async def test_start_workflow_validation(self, client: AsyncClient):
        """Test workflow validation before execution."""
        # Test with non-existent workflow ID
        non_existent_id = str(uuid4())
        execution_data = {"input_data": {"test": "data"}}

        response = await client.post(
            f"/v1/test_tenant/workflows/{non_existent_id}/run", json=execution_data
        )

        # Should return 404 for non-existent workflow
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_workflow_input_validation_missing_data(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test input validation fails with missing input_data."""
        # Missing input_data field
        invalid_data = {}

        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=invalid_data
        )

        # Should return 422 for validation error
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_workflow_with_string_input(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test workflow execution validates input against io_schema."""
        # Input must match the workflow's io_schema which expects {"alert": {...}}
        valid_input = {"input_data": {"alert": {"id": "AL-002", "severity": "medium"}}}

        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=valid_input
        )

        # Should return 202 for successful workflow initiation
        assert response.status_code == 202
        body = response.json()
        response_data = body["data"]
        assert "workflow_run_id" in response_data

    # Workflow Run List and Details Tests
    @pytest.mark.asyncio
    async def test_workflow_run_list_api(self, client: AsyncClient):
        """Test GET /workflow-runs with filtering."""
        # Test basic list endpoint
        response = await client.get("/v1/test_tenant/workflow-runs")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body
        meta = body["meta"]
        assert "total" in meta
        assert "offset" in meta
        assert "limit" in meta
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_workflow_run_list_with_filters(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs with workflow_id and status filters."""
        # Test with filters
        response = await client.get(
            f"/v1/test_tenant/workflow-runs?workflow_id={sample_workflow_id}&status=pending&skip=0&limit=10"
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]

    @pytest.mark.asyncio
    async def test_workflow_run_list_pagination(self, client: AsyncClient):
        """Test GET /workflow-runs pagination parameters."""
        # Test pagination
        response = await client.get("/v1/test_tenant/workflow-runs?skip=10&limit=25")

        assert response.status_code == 200
        body = response.json()
        meta = body["meta"]
        assert meta["offset"] == 10
        assert meta["limit"] == 25

    @pytest.mark.asyncio
    async def test_workflow_run_list_sorting_and_filtering(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test comprehensive sorting and filtering of workflow-runs list API."""
        import asyncio

        # Start multiple workflow runs with delays to ensure different timestamps
        run_ids = []
        for i in range(3):
            execution_data = {"input_data": {"test": f"data_{i}", "counter": i}}
            response = await client.post(
                f"/v1/test_tenant/workflows/{sample_workflow_id}/run",
                json=execution_data,
            )
            assert response.status_code == 202
            run_ids.append(response.json()["data"]["workflow_run_id"])

            # Add small delay between executions to ensure different created_at times
            if i < 2:
                await asyncio.sleep(0.1)

        # Wait a bit for any processing
        await asyncio.sleep(1)

        # Test 1: Default sorting (created_at desc) - newest first
        response = await client.get("/v1/test_tenant/workflow-runs?limit=10")
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        meta = body["meta"]

        # Verify response structure
        assert meta["total"] >= 3
        assert len(data) >= 3

        # Verify sorting - created_at descending (newest first)
        runs = data
        for i in range(len(runs) - 1):
            assert runs[i]["created_at"] >= runs[i + 1]["created_at"]

        # Test 2: Sort by created_at ascending (oldest first)
        response = await client.get(
            "/v1/test_tenant/workflow-runs?sort=created_at&order=asc&limit=10"
        )
        assert response.status_code == 200
        body = response.json()

        runs_asc = body["data"]
        for i in range(len(runs_asc) - 1):
            assert runs_asc[i]["created_at"] <= runs_asc[i + 1]["created_at"]

        # Test 3: Test error handling for invalid sort field
        response = await client.get("/v1/test_tenant/workflow-runs?sort=invalid_field")
        assert response.status_code == 400
        assert "Invalid sort field" in response.json()["detail"]

        # Test 4: Test error handling for invalid order
        response = await client.get("/v1/test_tenant/workflow-runs?order=invalid_order")
        assert response.status_code == 400
        assert "Invalid order" in response.json()["detail"]

        # Test 5: Test filtering by workflow_id
        response = await client.get(
            f"/v1/test_tenant/workflow-runs?workflow_id={sample_workflow_id}&limit=10"
        )
        assert response.status_code == 200
        body = response.json()

        # All returned runs should be from our sample workflow
        for run in body["data"]:
            assert run["workflow_id"] == sample_workflow_id
            # Validate workflow_name field is populated correctly
            assert run["workflow_name"] == "Test Execution Workflow"

        # Test 6: Test pagination with our created runs
        response = await client.get(
            f"/v1/test_tenant/workflow-runs?workflow_id={sample_workflow_id}&skip=0&limit=2"
        )
        assert response.status_code == 200
        page1 = response.json()

        assert len(page1["data"]) <= 2
        assert page1["meta"]["offset"] == 0
        assert page1["meta"]["limit"] == 2
        assert page1["meta"]["total"] >= 3

        # Get second page
        response = await client.get(
            f"/v1/test_tenant/workflow-runs?workflow_id={sample_workflow_id}&skip=2&limit=2"
        )
        assert response.status_code == 200
        page2 = response.json()

        assert page2["meta"]["offset"] == 2
        assert page2["meta"]["limit"] == 2

        # Verify pages have different data (if both have data)
        if page1["data"] and page2["data"]:
            page1_ids = {run["id"] for run in page1["data"]}
            page2_ids = {run["id"] for run in page2["data"]}
            assert page1_ids.isdisjoint(page2_ids)  # No overlap

    @pytest.mark.asyncio
    async def test_workflow_run_status_filtering(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test filtering workflow runs by status."""
        # Start a workflow run
        execution_data = {"input_data": {"test": "status_filtering"}}
        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert response.status_code == 202
        assert "workflow_run_id" in response.json()["data"]

        # Wait a moment for processing
        import asyncio

        await asyncio.sleep(0.5)

        # Test filtering by pending status (our run might still be pending)
        response = await client.get("/v1/test_tenant/workflow-runs?status=pending")
        assert response.status_code == 200
        body = response.json()

        # All returned runs should have pending status
        for run in body["data"]:
            assert run["status"] == "pending"

        # Test filtering by completed status
        response = await client.get("/v1/test_tenant/workflow-runs?status=completed")
        assert response.status_code == 200
        body = response.json()

        # All returned runs should have completed status
        for run in body["data"]:
            assert run["status"] == "completed"

        # Test filtering by non-existent status should return empty
        response = await client.get("/v1/test_tenant/workflow-runs?status=nonexistent")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 0
        assert body["meta"]["total"] == 0

        # Test combined filtering by workflow_id and status
        response = await client.get(
            f"/v1/test_tenant/workflow-runs?workflow_id={sample_workflow_id}&status=pending"
        )
        assert response.status_code == 200
        body = response.json()

        # All returned runs should match both filters
        for run in body["data"]:
            assert run["workflow_id"] == sample_workflow_id
            assert run["status"] == "pending"

    @pytest.mark.asyncio
    async def test_workflow_run_details_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id} with full details."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Now get the details
        response = await client.get(f"/v1/test_tenant/workflow-runs/{workflow_run_id}")

        assert response.status_code == 200
        response_data = response.json()["data"]
        assert "id" in response_data  # Response uses database field name
        assert "tenant_id" in response_data
        assert "workflow_id" in response_data
        assert "workflow_name" in response_data
        assert response_data["workflow_name"] == "Test Execution Workflow"
        assert "status" in response_data
        assert "input_data" in response_data
        assert "created_at" in response_data
        assert "updated_at" in response_data

    @pytest.mark.asyncio
    async def test_workflow_run_status_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id}/status lightweight."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Now get the lightweight status
        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )

        assert response.status_code == 200
        response_data = response.json()["data"]
        assert "workflow_run_id" in response_data
        assert "status" in response_data
        assert "updated_at" in response_data
        # Should not include heavy fields like input_data, output_data
        assert "input_data" not in response_data
        assert "output_data" not in response_data

    @pytest.mark.asyncio
    async def test_workflow_run_graph_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id}/graph visualization."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Now get the execution graph
        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )

        assert response.status_code == 200
        response_data = response.json()["data"]
        assert "workflow_run_id" in response_data
        assert "is_complete" in response_data
        assert "snapshot_at" in response_data
        assert "summary" in response_data
        assert "nodes" in response_data
        assert "edges" in response_data
        assert isinstance(response_data["summary"], dict)
        assert isinstance(response_data["nodes"], list)
        assert isinstance(response_data["edges"], list)

    # Node Instance Tests
    @pytest.mark.asyncio
    async def test_node_instances_list_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id}/nodes."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get node instances
        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]

    @pytest.mark.asyncio
    async def test_node_instances_list_with_filters(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id}/nodes with status and parent filters."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get filtered node instances
        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes?status=pending"
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_node_instance_details_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test GET /workflow-runs/{id}/nodes/{node_id}."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Use a mock node instance ID for testing
        node_instance_id = str(uuid4())
        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes/{node_instance_id}"
        )

        # May return 404 if node instance doesn't exist, which is expected
        assert response.status_code in [200, 404]

    # Workflow Cancellation Tests
    @pytest.mark.asyncio
    async def test_cancel_workflow_api(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test POST /workflow-runs/{id}/cancel."""
        # First start a workflow to get a run ID
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Cancel the workflow
        response = await client.post(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/cancel"
        )

        # Should return 204 No Content for successful cancellation
        assert response.status_code == 204

    # Error Handling Tests
    @pytest.mark.asyncio
    async def test_workflow_not_found(self, client: AsyncClient):
        """Test 404 when workflow doesn't exist."""
        non_existent_id = str(uuid4())
        execution_data = {"input_data": {"test": "data"}}

        response = await client.post(
            f"/v1/test_tenant/workflows/{non_existent_id}/run", json=execution_data
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_workflow_run_not_found(self, client: AsyncClient):
        """Test 404 when workflow run doesn't exist."""
        non_existent_run_id = str(uuid4())

        response = await client.get(
            f"/v1/test_tenant/workflow-runs/{non_existent_run_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient, sample_workflow_id: str):
        """Test tenant isolation in all endpoints."""
        # Start workflow in test_tenant (where the sample workflow was created)
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Try to access from different tenant (should not find it)
        response = await client.get(
            f"/v1/different_tenant/workflow-runs/{workflow_run_id}"
        )
        assert response.status_code == 404  # Should not find run from different tenant

    @pytest.mark.asyncio
    async def test_malformed_requests(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test validation errors return 400."""
        # Test with malformed JSON
        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run",
            content="invalid json",  # Not JSON
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422  # Unprocessable Entity for invalid JSON

    @pytest.mark.asyncio
    async def test_method_not_allowed(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test unsupported HTTP methods return 404 (route doesn't exist)."""
        # Test unsupported method on workflow execution endpoint
        # FastAPI returns 404 when no route exists for the method (not 405)
        response = await client.patch(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run"
        )

        assert response.status_code == 404  # Not Found (no PATCH endpoint exists)


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecutionEndpointHeaders:
    """Test HTTP headers and response formats for workflow execution endpoints."""

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

    @pytest.fixture
    async def sample_workflow_id(self, client: AsyncClient) -> str:
        """Create a sample workflow for testing execution."""
        # First create a node template
        template_data = {
            "name": "Test Template",
            "type": "static",
            "description": "A test template for workflow execution",
            "code": "return {'result': 'test output'}",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        workflow_data = {
            "name": "Test Headers Workflow",
            "description": "A workflow for testing headers",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"test": {"type": "string"}},  # Required by Rodos
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "data"}],  # Required by Rodos
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-start",
                    "kind": "transformation",
                    "name": "Start Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                    "is_start_node": True,  # Required by Rodos
                }
            ],
            "edges": [],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert response.status_code == 201
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_start_workflow_returns_proper_headers(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test that starting workflow returns proper async operation headers."""
        execution_data = {"input_data": {"test": "data"}}

        response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )

        assert response.status_code == 202

        # Check for standard async operation headers
        headers = response.headers
        assert "Location" in headers or "location" in headers  # FastAPI may normalize

        response_data = response.json()["data"]
        workflow_run_id = response_data["workflow_run_id"]

        # Location should point to status endpoint
        expected_location = f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        location_header = headers.get("Location") or headers.get("location", "")
        assert expected_location in location_header

    @pytest.mark.asyncio
    async def test_all_endpoints_return_json_content_type(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test that all endpoints return proper JSON content type."""
        # Start a workflow first
        execution_data = {"input_data": {"test": "data"}}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run", json=execution_data
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Test all endpoints that should return JSON
        endpoints_to_test = [
            ("GET", "/v1/test_tenant/workflow-runs"),
            ("GET", f"/v1/test_tenant/workflow-runs/{workflow_run_id}"),
            ("GET", f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"),
            ("GET", f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"),
            ("GET", f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"),
        ]

        for method, url in endpoints_to_test:
            if method == "GET":
                response = await client.get(url)
            else:
                continue  # Only testing GET endpoints here

            if response.status_code == 200:  # Only check successful responses
                assert "application/json" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_cors_headers_present(self, client: AsyncClient):
        """Test that CORS headers are present for cross-origin requests."""
        response = await client.get("/v1/test_tenant/workflow-runs")

        # Check if CORS headers are present (if CORS middleware is configured)
        headers = response.headers
        # This may not be present in test environment, but check if available
        if "access-control-allow-origin" in headers:
            assert headers["access-control-allow-origin"] is not None
