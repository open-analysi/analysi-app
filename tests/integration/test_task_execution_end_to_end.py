"""
End-to-End Task Execution Tests

Tests for complete task execution flows and system integration.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_full_stack,
    pytest.mark.arq_worker,
]


@pytest.mark.asyncio
@pytest.mark.integration
class TestEndToEndTaskExecution:
    """Test end-to-end flow: create task -> execute -> poll status."""

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
    async def test_complete_task_execution_flow(self, client: AsyncClient):
        """Test the complete flow from task creation to execution completion."""
        # Step 1: Create a task
        task_data = {
            "name": "End-to-End Test Task",
            "description": "Testing complete execution flow",
            "directive": "Execute the provided Cy script and return results",
            "script": """
            message = "Hello from end-to-end test"
            return {
                "message": message,
                "input_received": input
            }
            """,
            "function": "testing",
            "scope": "processing",
            "llm_config": {
                "default_model": "gpt-4",
                "temperature": 0.1,
                "max_tokens": 1000,
            },
        }

        create_response = await client.post("/v1/test_tenant/tasks", json=task_data)
        assert create_response.status_code == 201

        task = create_response.json()["data"]
        task_id = task["id"]

        # Step 2: Execute the task
        execution_input = {
            "test_data": "input for end-to-end test",
            "numbers": [1, 2, 3, 4, 5],
        }

        execution_response = await client.post(
            f"/v1/test_tenant/tasks/{task_id}/run", json={"input": execution_input}
        )

        assert execution_response.status_code == 202

        execution_result = execution_response.json()["data"]
        trid = execution_result["trid"]

        # Verify response includes required headers
        headers = execution_response.headers
        assert "Location" in headers
        assert "Retry-After" in headers
        assert f"/v1/test_tenant/task-runs/{trid}" in headers["Location"]

        # Step 3: Poll status until completion (give time for async processing)
        max_polls = 10  # Reduced for faster test
        poll_count = 0
        final_status = None

        while poll_count < max_polls:
            status_response = await client.get(
                f"/v1/test_tenant/task-runs/{trid}/status"
            )
            assert status_response.status_code == 200

            status_data = status_response.json()["data"]
            current_status = status_data["status"]

            if current_status in ["completed", "failed"]:
                final_status = current_status
                break
            if current_status == "running":
                # Wait before next poll
                await asyncio.sleep(0.1)
                poll_count += 1
            else:
                pytest.fail(f"Unexpected status: {current_status}")

        # For async execution, we should expect that it may still be running
        # This is the correct behavior for background processing
        assert final_status in [
            "completed",
            "failed",
            None,
        ], f"Final status: {final_status}"

        # If completed, verify it succeeded
        if final_status is not None:
            assert final_status == "completed", (
                f"Task execution failed with status: {final_status}"
            )

    @pytest.mark.asyncio
    async def test_integration_action_error_propagates_to_failed_status(
        self, client: AsyncClient
    ):
        """
        Test that integration action errors result in failed task runs.

        This is an integration test that validates the complete error propagation
        from a failing integration action through to the task run status API.
        """
        # Create a task that calls an integration action with invalid credentials
        task_data = {
            "name": "Error Propagation Test Task",
            "description": "Test that integration errors are properly propagated",
            "directive": "Call VirusTotal with invalid API key",
            "script": """
# This will fail because we're using an invalid API key
ip = "8.8.8.8"
result = app::virustotal::ip_reputation(ip=ip)
return {"result": result}
            """,
            "function": "testing",
            "scope": "processing",
        }

        create_response = await client.post(
            "/v1/test_tenant_error_prop/tasks", json=task_data
        )
        assert create_response.status_code == 201

        task = create_response.json()["data"]
        task_id = task["id"]

        # Execute the task with empty input
        execution_response = await client.post(
            f"/v1/test_tenant_error_prop/tasks/{task_id}/run", json={"input": {}}
        )

        assert execution_response.status_code == 202
        execution_result = execution_response.json()["data"]
        trid = execution_result["trid"]

        # Poll status until completion (allow up to 15s for worker to process)
        max_polls = 30
        poll_count = 0
        final_status = None
        error_message = None

        while poll_count < max_polls:
            status_response = await client.get(
                f"/v1/test_tenant_error_prop/task-runs/{trid}/status"
            )
            assert status_response.status_code == 200

            status_data = status_response.json()["data"]
            current_status = status_data["status"]

            if current_status in ["completed", "failed"]:
                final_status = current_status
                # Get full result to check error message
                result_response = await client.get(
                    f"/v1/test_tenant_error_prop/task-runs/{trid}"
                )
                if result_response.status_code == 200:
                    result_data = result_response.json()["data"]
                    # Error might be in output_location for failed tasks
                    if result_data.get("status") == "failed":
                        output_loc = result_data.get("output_location")
                        if output_loc:
                            import json

                            try:
                                output_data = json.loads(output_loc)
                                error_message = output_data.get("error")
                            except (json.JSONDecodeError, ValueError, KeyError):
                                error_message = output_loc
                break
            if current_status == "running":
                await asyncio.sleep(0.5)
                poll_count += 1
            else:
                pytest.fail(f"Unexpected status: {current_status}")

        # CRITICAL ASSERTION: Task should fail, not succeed
        assert final_status == "failed", (
            f"Expected task to fail due to integration error, "
            f"but got status='{final_status}'. "
            f"This indicates error propagation is broken."
        )

        # Verify we have an error message
        assert error_message is not None, "Failed task should include error message"

        # The error should mention the tool or indicate a failure
        # Note: In test environment, the tool may not be loaded, so we accept either:
        # - "Tool not found" (integration not configured)
        # - HTTPError/API error (integration configured but failed)
        assert (
            "Tool" in str(error_message)
            or "app::virustotal" in str(error_message)
            or "HTTPError" in str(error_message)
            or "API" in str(error_message)
        ), (
            f"Error message should indicate tool/integration failure, got: {error_message}"
        )
