"""
Basic API tests for workflow execution endpoints.
Tests the REST API layer in isolation without complex execution logic.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecutionAPIBasic:
    """Test workflow execution API endpoints in isolation."""

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
    async def test_workflow_run_creation_basic(self, client: AsyncClient):
        """Test that we can create a workflow run via API without execution."""

        # First create a simple template
        template_data = {
            "name": "basic_test",
            "description": "Basic test template",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        # Now create a simple workflow with one node that uses the template
        workflow_data = {
            "name": "Basic Test Workflow",
            "description": "Simple test workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "data"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-test",
                    "kind": "transformation",
                    "name": "Test Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        print(f"Create workflow response: {create_response.status_code}")
        if create_response.status_code != 201:
            print(f"Error creating workflow: {create_response.text}")

        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]
        print(f"Created workflow: {workflow_id}")

        # Test starting workflow execution (should return 202 even without execution)
        test_input = {"test": "data"}

        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )

        print(f"Start workflow response: {start_response.status_code}")
        if start_response.status_code != 202:
            print(f"Error starting workflow: {start_response.text}")

        assert start_response.status_code == 202

        result = start_response.json()["data"]
        assert "workflow_run_id" in result
        assert "status" in result
        assert result["status"] == "pending"

        workflow_run_id = result["workflow_run_id"]
        print(f"Created workflow run: {workflow_run_id}")

    @pytest.mark.asyncio
    async def test_workflow_run_status_endpoint(self, client: AsyncClient):
        """Test the status endpoint works."""

        # First create a template
        template_data = {
            "name": "status_test",
            "description": "Status test template",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        # Create a simple workflow and run
        workflow_data = {
            "name": "Status Test Workflow",
            "description": "Test status endpoint",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "status"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-status",
                    "kind": "transformation",
                    "name": "Status Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "status"}},
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Test status endpoint
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        print(f"Status response: {status_response.status_code}")
        if status_response.status_code != 200:
            print(f"Status error: {status_response.text}")

        assert status_response.status_code == 200

        status_data = status_response.json()["data"]
        assert "workflow_run_id" in status_data
        assert "status" in status_data
        # In test environment with synchronous execution, workflow completes immediately
        assert status_data["status"] in [
            "pending",
            "running",
            "completed",
        ]  # Valid statuses
