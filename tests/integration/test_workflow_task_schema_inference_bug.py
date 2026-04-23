"""
Integration test to reproduce workflow type propagation bug with real tasks.

BUG: Type propagation doesn't load actual Task objects, so it can't infer
output schemas from Cy scripts. Instead it uses a placeholder with generic
"return input" script, causing all tasks to have pass-through schemas.

This test creates two tasks with incompatible schemas and verifies that
validation correctly detects the mismatch. It will FAIL initially, demonstrating
the bug, and PASS after the fix.
"""

import json
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskSchemaInferenceBug:
    """Test that workflow validation correctly infers task output schemas from Cy scripts."""

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
    async def test_workflow_validation_detects_task_schema_mismatch(
        self, client: AsyncClient
    ):
        """
        Test that type propagation correctly infers task output schemas from Cy scripts
        and detects incompatibilities between connected tasks.

        BUG REPRODUCTION TEST:
        - Task 1 returns: {" correlation_analysis": string, "recommended_action": string}
        - Task 2 expects: {"detailed_analysis": string}
        - Type checker should detect that Task 1's output doesn't provide "detailed_analysis"
        - Currently FAILS: Type propagation incorrectly passes both tasks through unchanged

        This test will FAIL initially, demonstrating the bug.
        After fix (adding Task relationship to WorkflowNode), it should PASS.
        """
        # Step 1: Create Task 1 - Returns correlation_analysis
        task1_script = """
# Multi-source IP reputation task
ip_address = input["ip"]

# Simulate correlation analysis
correlation_analysis = "IP has high threat score across multiple sources"
recommended_action = "BLOCK_IMMEDIATELY"

return {
    "ip_address": ip_address,
    "correlation_analysis": correlation_analysis,
    "recommended_action": recommended_action
}
"""
        task1_data = {
            "name": "Multi-Source IP Correlation Test",
            "description": "Returns correlation_analysis field",
            "directive": "Analyze IP reputation",
            "script": task1_script,
            "function": "search",
            "mode": "saved",
        }

        task1_response = await client.post("/v1/default/tasks", json=task1_data)
        assert task1_response.status_code == 201
        task1_id = task1_response.json()["data"]["id"]

        # Step 2: Create Task 2 - Expects detailed_analysis
        task2_script = """
# Summary generation task
detailed_analysis = input["detailed_analysis"]

# Generate summary from detailed analysis
summary = "Summary: " + detailed_analysis

return {
    "summary": summary
}
"""
        task2_data = {
            "name": "Generate Summary Test",
            "description": "Expects detailed_analysis field",
            "directive": "Generate summary",
            "script": task2_script,
            "function": "summarization",
            "mode": "saved",
        }

        task2_response = await client.post("/v1/default/tasks", json=task2_data)
        assert task2_response.status_code == 201
        task2_id = task2_response.json()["data"]["id"]

        # Step 3: Create workflow connecting Task 1 -> Task 2
        workflow_data = {
            "name": "IP Reputation Analysis Workflow - Bug Reproduction",
            "description": "Workflow with incompatible task schemas",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                    "required": ["ip"],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"ip": "192.168.1.1"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "correlation_node",
                    "kind": "task",
                    "name": "Multi-Source IP Correlation",
                    "is_start_node": True,
                    "task_id": task1_id,
                    "schemas": {},  # Empty - let type propagation infer
                },
                {
                    "node_id": "summary_node",
                    "kind": "task",
                    "name": "Generate Summary",
                    "task_id": task2_id,
                    "schemas": {},  # Empty - let type propagation infer
                },
            ],
            "edges": [
                {
                    "edge_id": "edge-1",
                    "from_node_id": "correlation_node",
                    "to_node_id": "summary_node",
                    "from_output_key": "default",
                    "to_input_key": "default",
                }
            ],
        }

        create_response = await client.post("/v1/default/workflows", json=workflow_data)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Step 4: Run type validation
        initial_input_schema = {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
            "required": ["ip"],
        }

        validation_response = await client.post(
            f"/v1/default/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": initial_input_schema},
        )

        assert validation_response.status_code == 200
        validation_data = validation_response.json()["data"]

        # Step 5: Verify type inference worked correctly
        # The validation should detect that:
        # - correlation_node outputs: {ip_address, correlation_analysis, recommended_action}
        # - summary_node expects: {detailed_analysis}
        # - These are INCOMPATIBLE - validation should fail

        # DEBUG: Print what we got
        print("\n=== VALIDATION RESULT ===")
        print(f"Status: {validation_data['status']}")
        print(f"Nodes: {json.dumps(validation_data['nodes'], indent=2)}")
        print(f"Errors: {json.dumps(validation_data.get('errors', []), indent=2)}")

        # ASSERTION: This should FAIL initially (bug reproduction)
        # After fix, validation status should be "invalid" with type mismatch error
        assert validation_data["status"] == "invalid", (
            "BUG: Type propagation should detect schema mismatch between tasks! "
            f"Expected 'invalid' but got '{validation_data['status']}'. "
            "Task 1 outputs 'correlation_analysis' but Task 2 expects 'detailed_analysis'."
        )

        # Verify we got a meaningful error message
        errors = validation_data.get("errors", [])
        assert len(errors) > 0, "Should have at least one type mismatch error"

        # Check that error mentions the missing field
        error_messages = [e.get("message", "") for e in errors]
        assert any("detailed_analysis" in msg for msg in error_messages), (
            f"Error should mention missing 'detailed_analysis' field. Got: {error_messages}"
        )

    @pytest.mark.asyncio
    async def test_workflow_tasks_match_rest_api_tasks(self, client: AsyncClient):
        """
        Verify that Task objects loaded via workflow join match tasks from REST API.

        This ensures the foreign key relationship and join are working correctly.
        """
        # Step 1: Create a task via REST API
        task_script = """
ip = input["ip"]
result = "processed: " + ip
return {"result": result}
"""
        task_data = {
            "name": "Test Task for Join Verification",
            "description": "Verifies FK join works correctly",
            "directive": "Process IP",
            "script": task_script,
            "function": "search",
            "mode": "saved",
        }

        create_response = await client.post("/v1/default/tasks", json=task_data)
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Step 2: Get the task via REST API (ground truth)
        get_task_response = await client.get(f"/v1/default/tasks/{task_id}")
        assert get_task_response.status_code == 200
        task_from_api = get_task_response.json()["data"]

        # Step 3: Create workflow with node referencing this task
        workflow_data = {
            "name": "Task Join Verification Workflow",
            "description": "Tests that workflow task join works correctly",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"ip": "192.168.1.1"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "test_node",
                    "kind": "task",
                    "name": "Test Node",
                    "is_start_node": True,
                    "task_id": task_id,
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        workflow_response = await client.post(
            "/v1/default/workflows", json=workflow_data
        )
        assert workflow_response.status_code == 201
        workflow_id = workflow_response.json()["data"]["id"]

        # Step 4: Get workflow (which eagerly loads tasks via join)
        get_workflow_response = await client.get(f"/v1/default/workflows/{workflow_id}")
        assert get_workflow_response.status_code == 200
        workflow_data = get_workflow_response.json()["data"]

        # Step 5: Verify the task in workflow matches REST API task
        assert len(workflow_data["nodes"]) == 1
        node = workflow_data["nodes"][0]
        assert node["task_id"] == task_id, "Node should reference the correct task_id"

        # Step 6: Run type validation to trigger task loading
        validation_response = await client.post(
            f"/v1/default/workflows/{workflow_id}/validate-types",
            json={
                "initial_input_schema": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                }
            },
        )
        assert validation_response.status_code == 200
        validation_data = validation_response.json()["data"]

        # Verify type inference used the actual task script
        # If the join worked, the inferred output should match what the script returns
        nodes = validation_data["nodes"]
        assert len(nodes) == 1
        inferred_output = nodes[0]["inferred_output"]

        # The script returns {"result": string}, so inferred output should reflect that
        assert "properties" in inferred_output, (
            "Should have inferred properties from task script"
        )
        assert "result" in inferred_output["properties"], (
            f"Should infer 'result' field from task script. Got: {inferred_output}"
        )

        print(f"\n✅ Task from API: {task_from_api['script'][:50]}...")
        print(f"✅ Inferred output: {inferred_output}")
        print(
            "✅ Verification passed: Tasks loaded via workflow join match REST API tasks"
        )
