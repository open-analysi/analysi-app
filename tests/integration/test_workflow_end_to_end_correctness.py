"""
End-to-end workflow execution correctness tests.

These tests verify that workflows actually produce the correct computational results
by running real templates through the execution engine and validating outputs.
Simplified to focus on core functionality with the working execution pattern.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

DEFAULT_TENANT = "test_tenant"


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowEndToEndCorrectness:
    """Test that workflows produce mathematically correct results end-to-end."""

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

    async def create_template(
        self,
        client: AsyncClient,
        name: str,
        code: str,
        input_schema: dict,
        output_schema: dict,
        description: str = None,
    ) -> str:
        """Helper to create a template and return its ID."""
        template_data = {
            "name": name,
            "description": description or f"Template for {name}",
            "input_schema": input_schema,
            "output_schema": output_schema,
            "code": code,
            "language": "python",
            "type": "static",
        }

        response = await client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_arithmetic_transformation_pipeline(self, client):
        """
        Test a workflow that performs mathematical transformations and verify correctness.
        Pipeline: Input → Add 10 → Multiply by 2 → Subtract 5 → Output
        Expected: input=7 → 17 → 34 → 29
        """
        # Unpack client and session
        http_client, session = client

        # Create templates with real mathematical operations
        add_template_id = await self.create_template(
            http_client,
            "add_ten",
            "return inp.get('value', 0) + 10",
            {"type": "object", "properties": {"value": {"type": "number"}}},
            {"type": "object", "properties": {"result": {"type": "number"}}},
            "Add 10 to input value",
        )

        multiply_template_id = await self.create_template(
            http_client,
            "multiply_by_two",
            "return inp * 2",
            {"type": "object", "properties": {"result": {"type": "number"}}},
            {"type": "object", "properties": {"result": {"type": "number"}}},
            "Multiply input by 2",
        )

        subtract_template_id = await self.create_template(
            http_client,
            "subtract_five",
            "return {'result': inp - 5}",
            {"type": "object", "properties": {"result": {"type": "number"}}},
            {"type": "object", "properties": {"result": {"type": "number"}}},
            "Subtract 5 from input",
        )

        # Create workflow with transformation pipeline
        workflow_data = {
            "name": "Arithmetic Pipeline",
            "description": "Mathematical transformation pipeline",
            "is_dynamic": False,
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                },
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                },
            },
            "nodes": [
                {
                    "node_id": "add-node",
                    "kind": "transformation",
                    "name": "Add 10",
                    "is_start_node": True,
                    "node_template_id": add_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "multiply-node",
                    "kind": "transformation",
                    "name": "Multiply by 2",
                    "node_template_id": multiply_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "subtract-node",
                    "kind": "transformation",
                    "name": "Subtract 5",
                    "node_template_id": subtract_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "add-node",
                    "to_node_id": "multiply-node",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "multiply-node",
                    "to_node_id": "subtract-node",
                },
            ],
        }

        # Create workflow
        create_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert create_response.status_code == 201, (
            f"Failed to create workflow: {create_response.text}"
        )
        workflow_id = create_response.json()["data"]["id"]

        # CRITICAL: Commit the test data so background task can see it
        await session.commit()
        print("✅ Committed test data")

        # Execute workflow with test input
        test_input = {"value": 7}
        expected_output = 29  # (7 + 10) * 2 - 5 = 17 * 2 - 5 = 34 - 5 = 29

        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )
        assert start_response.status_code == 202, (
            f"Failed to start workflow: {start_response.text}"
        )
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]
        print(f"Workflow started: {workflow_run_id}")

        # Manually trigger workflow execution (working pattern)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get final result and verify correctness
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200, (
            f"Failed to get results: {details_response.text}"
        )

        workflow_details = details_response.json()["data"]
        assert "output_data" in workflow_details, "Workflow should have output data"

        output_data = workflow_details["output_data"]
        assert "result" in output_data, (
            f"Output should contain 'result' field: {output_data}"
        )
        assert output_data["result"] == expected_output, (
            f"Expected {expected_output}, got {output_data['result']}"
        )

        print(
            f"✅ Arithmetic pipeline test passed: {test_input} → {output_data['result']}"
        )

    @pytest.mark.asyncio
    async def test_string_processing_pipeline(self, client):
        """
        Test a workflow that processes strings through transformations.
        Pipeline: Input → Uppercase → Add Prefix → Add Suffix → Output
        Expected: input="hello" → "HELLO" → "PREFIX_HELLO" → "PREFIX_HELLO_SUFFIX"
        """
        # Unpack client and session
        http_client, session = client

        # Create string processing templates
        uppercase_template_id = await self.create_template(
            http_client,
            "uppercase",
            "return {'text': inp.get('text', '').upper()}",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            {"type": "object", "properties": {"text": {"type": "string"}}},
            "Convert text to uppercase",
        )

        prefix_template_id = await self.create_template(
            http_client,
            "add_prefix",
            "return {'text': 'PREFIX_' + inp.get('text', '')}",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            {"type": "object", "properties": {"text": {"type": "string"}}},
            "Add prefix to text",
        )

        suffix_template_id = await self.create_template(
            http_client,
            "add_suffix",
            "return {'text': inp.get('text', '') + '_SUFFIX'}",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            {"type": "object", "properties": {"text": {"type": "string"}}},
            "Add suffix to text",
        )

        # Create workflow with string processing pipeline
        workflow_data = {
            "name": "String Processing Pipeline",
            "description": "Text transformation pipeline",
            "is_dynamic": False,
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {"type": "object", "properties": {"text": {"type": "string"}}},
                "output": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            },
            "nodes": [
                {
                    "node_id": "uppercase-node",
                    "kind": "transformation",
                    "name": "Uppercase",
                    "is_start_node": True,
                    "node_template_id": uppercase_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "prefix-node",
                    "kind": "transformation",
                    "name": "Add Prefix",
                    "node_template_id": prefix_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "suffix-node",
                    "kind": "transformation",
                    "name": "Add Suffix",
                    "node_template_id": suffix_template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "uppercase-node",
                    "to_node_id": "prefix-node",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "prefix-node",
                    "to_node_id": "suffix-node",
                },
            ],
        }

        # Create workflow
        create_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert create_response.status_code == 201, (
            f"Failed to create workflow: {create_response.text}"
        )
        workflow_id = create_response.json()["data"]["id"]

        # CRITICAL: Commit the test data
        await session.commit()
        print("✅ Committed test data")

        # Execute workflow with test input
        test_input = {"text": "hello"}
        expected_output = "PREFIX_HELLO_SUFFIX"

        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )
        assert start_response.status_code == 202, (
            f"Failed to start workflow: {start_response.text}"
        )
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]
        print(f"Workflow started: {workflow_run_id}")

        # Manually trigger workflow execution (working pattern)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get final result and verify correctness
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200, (
            f"Failed to get results: {details_response.text}"
        )

        workflow_details = details_response.json()["data"]
        assert "output_data" in workflow_details, "Workflow should have output data"

        output_data = workflow_details["output_data"]
        assert "text" in output_data, (
            f"Output should contain 'text' field: {output_data}"
        )
        assert output_data["text"] == expected_output, (
            f"Expected '{expected_output}', got '{output_data['text']}'"
        )

        print(f"✅ String pipeline test passed: {test_input} → {output_data['text']}")

    @pytest.mark.asyncio
    async def test_fan_in_aggregation_correctness(self, client):
        """
        Test a workflow with fan-in pattern: multiple nodes feeding into one aggregator.
        Pipeline: Input → [Double, Triple] → Sum Results → Output
        Expected: input=5 → [10, 15] → 25
        """
        # Unpack client and session
        http_client, session = client

        # Create mathematical operation templates
        double_template_id = await self.create_template(
            http_client,
            "double",
            "return inp.get('value', 0) * 2",
            {"type": "object", "properties": {"value": {"type": "number"}}},
            {"type": "object", "properties": {"result": {"type": "number"}}},
            "Double the input value",
        )

        triple_template_id = await self.create_template(
            http_client,
            "triple",
            "return inp.get('value', 0) * 3",
            {"type": "object", "properties": {"value": {"type": "number"}}},
            {"type": "object", "properties": {"result": {"type": "number"}}},
            "Triple the input value",
        )

        sum_template_id = await self.create_template(
            http_client,
            "sum_results",
            """
# Template receives simplified input: inp = [array of results]
# After envelope fix: no more {node_id, result} wrappers, just plain results

total = 0
for result in inp:
    # Each result is a plain number (from double/triple operations)
    if isinstance(result, (int, float)):
        total += result

return {"total": total}
""",
            {"type": "object"},
            {"type": "object", "properties": {"total": {"type": "number"}}},
            "Sum results from multiple inputs",
        )

        # Create workflow with fan-in pattern
        workflow_data = {
            "name": "Fan-in Aggregation",
            "description": "Multiple paths converging to one aggregator",
            "is_dynamic": False,
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                },
                "output": {
                    "type": "object",
                    "properties": {"total": {"type": "number"}},
                },
            },
            "nodes": [
                {
                    "node_id": "double-node",
                    "kind": "transformation",
                    "name": "Double",
                    "is_start_node": True,
                    "node_template_id": double_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "triple-node",
                    "kind": "transformation",
                    "name": "Triple",
                    "node_template_id": triple_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "sum-node",
                    "kind": "transformation",
                    "name": "Sum Results",
                    "node_template_id": sum_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "double-node",
                    "to_node_id": "sum-node",
                    "alias": "double_result",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "triple-node",
                    "to_node_id": "sum-node",
                    "alias": "triple_result",
                },
            ],
        }

        # Create workflow
        create_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert create_response.status_code == 201, (
            f"Failed to create workflow: {create_response.text}"
        )
        workflow_id = create_response.json()["data"]["id"]

        # CRITICAL: Commit the test data
        await session.commit()
        print("✅ Committed test data")

        # Execute workflow with test input
        test_input = {"value": 5}
        expected_output = 25  # (5*2) + (5*3) = 10 + 15 = 25

        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )
        assert start_response.status_code == 202, (
            f"Failed to start workflow: {start_response.text}"
        )
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]
        print(f"Workflow started: {workflow_run_id}")

        # Manually trigger workflow execution (working pattern)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get final result and verify correctness
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200, (
            f"Failed to get results: {details_response.text}"
        )

        workflow_details = details_response.json()["data"]
        assert "output_data" in workflow_details, "Workflow should have output data"

        output_data = workflow_details["output_data"]
        assert "total" in output_data, (
            f"Output should contain 'total' field: {output_data}"
        )
        assert output_data["total"] == expected_output, (
            f"Expected {expected_output}, got {output_data['total']}"
        )

        print(
            f"✅ Fan-in aggregation test passed: {test_input} → {output_data['total']}"
        )
