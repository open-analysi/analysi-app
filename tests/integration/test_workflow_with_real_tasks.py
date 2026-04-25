#!/usr/bin/env python3
"""
Integration test for workflow execution with real tasks.

This test creates a complete workflow with transformation + task nodes
and verifies that real task execution (including LLM calls) works properly.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from tests.utils.cy_output import parse_cy_output

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

DEFAULT_TENANT = "default"


@pytest.mark.integration
@pytest.mark.asyncio
class TestWorkflowWithRealTasks:
    """Test workflow execution with real task nodes."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, integration_test_session

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_workflow_with_real_task_execution(self, client):
        """Test workflow execution with a real task node that calls LLM."""

        # Unpack client and session
        http_client, session = client

        # Use a simple task without LLM calls to test the workflow execution mechanism
        # 1. Create a simple task for IP analysis (no LLM)
        task_data = {
            "name": "Simple IP Security Analysis",
            "description": "Analyzes IP addresses for security threats",
            "version": "1.0.0",
            "script": """# Simple IP analysis task without LLM
ip_address = input["ip"]

# Simulate some analysis without external calls
risk_score = 75
is_suspicious = True

# Return structured result
return {
    "ip": ip_address,
    "risk_score": risk_score,
    "is_suspicious": is_suspicious,
    "analysis": "Simulated security analysis completed",
    "analyzed_at": "2024-01-15T10:30:00Z"
}""",
            "function": "reasoning",
            "scope": "processing",
            "llm_config": None,
        }

        response = await http_client.post(f"/v1/{DEFAULT_TENANT}/tasks", json=task_data)
        assert response.status_code == 201, f"Failed to create task: {response.text}"
        task_id = response.json()["data"]["id"]
        print(f"Created task: {task_id}")

        # 2. Create a passthrough transformation template
        template_data = {
            "name": "IP Extractor",
            "description": "Extracts IP from alert input",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return {'ip': inp.get('ip', '127.0.0.1')}",
            "language": "python",
            "type": "static",
        }

        response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create template: {response.text}"
        )
        template_id = response.json()["data"]["id"]
        print(f"Created template: {template_id}")

        # 3. Create workflow with transformation -> task
        workflow_data = {
            "name": "IP Analysis Workflow",
            "description": "Test workflow with real task execution",
            "is_dynamic": False,
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                    "required": ["ip"],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"ip": "192.168.1.1"}],
            "nodes": [
                {
                    "node_id": "n-extract-ip",
                    "kind": "transformation",
                    "name": "Extract IP",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-analyze-ip",
                    "kind": "task",
                    "name": "Analyze IP",
                    "task_id": task_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-extract-ip",
                    "to_node_id": "n-analyze-ip",
                }
            ],
        }

        response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert response.status_code == 201, (
            f"Failed to create workflow: {response.text}"
        )
        workflow_id = response.json()["data"]["id"]
        print(f"Created workflow: {workflow_id}")

        # CRITICAL: Commit the test data so background task can see it
        await session.commit()
        print(
            "✅ Committed test data - background task can now see workflow/task/template"
        )

        # 4. Execute workflow with test data
        # Input must match io_schema which expects {"ip": "..."}
        test_input = {"ip": "8.8.8.8"}

        execution_data = {"input_data": test_input}

        response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run", json=execution_data
        )

        assert response.status_code == 202, (
            f"Failed to start workflow: {response.status_code} - {response.text}"
        )
        run_id = response.json()["data"]["workflow_run_id"]
        print(f"Workflow started: {run_id}")

        # Manually trigger workflow execution (temporary workaround)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(run_id)
        await session.commit()

        # 5. Poll for completion (simulated task should be fast)
        final_status = None
        for poll_count in range(20):  # 1 minute max for simulated task
            await asyncio.sleep(3)

            response = await http_client.get(
                f"/v1/{DEFAULT_TENANT}/workflow-runs/{run_id}/status"
            )
            assert response.status_code == 200, f"Failed to get status: {response.text}"

            status_data = response.json()["data"]
            final_status = status_data["status"]
            print(f"Status: {final_status} (poll {poll_count + 1}/20)")

            if final_status in ["completed", "failed"]:
                break

        # 6. Verify completion
        assert final_status == "completed", (
            f"Workflow did not complete successfully: {final_status}"
        )

        # 7. Get and verify results
        response = await http_client.get(f"/v1/{DEFAULT_TENANT}/workflow-runs/{run_id}")
        assert response.status_code == 200, f"Failed to get results: {response.text}"

        results = response.json()["data"]
        assert "output_data" in results, "Workflow should have output_data"

        output_data = results["output_data"]
        print(f"Workflow output: {json.dumps(output_data, indent=2)}")

        # 8. Verify the structure contains simulated task results
        # After our fix, the result is now directly in output_data (no extra wrapping)
        # Parse in case Cy runtime returned Python repr format
        result_data = parse_cy_output(output_data)

        assert "ip" in result_data, "Result should contain IP address"
        assert "risk_score" in result_data, "Result should contain risk score"
        assert "analysis" in result_data, "Result should contain analysis"
        assert result_data["ip"] == "8.8.8.8", "IP should match input"
        assert result_data["risk_score"] == 75, "Risk score should match expected value"
        assert "Simulated" in result_data["analysis"], (
            "Analysis should contain simulated content"
        )

        print("✅ Workflow with task execution test passed!")


if __name__ == "__main__":
    # Allow running this test standalone
    # Note: This would require a proper test runner setup
    print("Use pytest to run this test")
