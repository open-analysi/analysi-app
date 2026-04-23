"""
Debug the progressive execution algorithm step by step.
Tests the monitoring and execution logic with timeouts and debug output.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestProgressiveExecutionDebug:
    """Debug progressive execution algorithm."""

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
    async def test_single_node_execution_with_timeout(self, client: AsyncClient):
        """Test single node execution with quick timeout to see debug output."""

        # Create a simple template
        template_data = {
            "name": "debug_passthrough",
            "description": "Debug passthrough template",
            "input_schema": {"type": "object", "properties": {"data": {}}},
            "output_schema": {"type": "object", "properties": {"data": {}}},
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

        # Create a single-node workflow
        workflow_data = {
            "name": "Debug Single Node",
            "description": "Debug single node execution",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-debug",
                    "kind": "transformation",
                    "name": "Debug Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
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
        print(f"Created debug workflow: {workflow_id}")

        # Start execution
        test_input = {"debug": "test"}

        print("Starting workflow execution...")
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )

        print(f"Start response: {start_response.status_code}")
        if start_response.status_code != 202:
            print(f"Start error: {start_response.text}")
            raise AssertionError(f"Failed to start workflow: {start_response.text}")

        workflow_run_id = start_response.json()["data"]["workflow_run_id"]
        print(f"Started workflow run: {workflow_run_id}")

        # Wait a short time to see debug output, then check status
        print("Waiting 2 seconds for execution to start...")
        await asyncio.sleep(2)

        # Check status
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        print(f"Status response: {status_response.status_code}")
        if status_response.status_code == 200:
            status_data = status_response.json()["data"]
            print(f"Workflow status: {status_data['status']}")
        else:
            print(f"Status error: {status_response.text}")

        # This test is just for debugging - we expect it might timeout
        # The goal is to see the debug prints from monitor_execution
        print("Debug test complete - check console output for execution debug info")
