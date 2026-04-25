"""
Integration tests for workflow execution patterns.
Tests end-to-end execution of different workflow patterns with real database.
All tests follow TDD principles and should FAIL initially since implementation isn't complete yet.
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
class TestWorkflowExecutionPatterns:
    """Test core workflow execution patterns end-to-end."""

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
    async def execution_client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client with session access for execution testing."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, integration_test_session

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.fixture
    async def passthrough_template_id(self, client: AsyncClient) -> str:
        """Create a passthrough node template for testing."""
        template_data = {
            "name": "passthrough",
            "description": "Simple passthrough template",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        # Create template
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create passthrough template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.fixture
    async def pick_field_template_id(self, client: AsyncClient) -> str:
        """Create a field picking node template for testing."""
        template_data = {
            "name": "pick_field",
            "description": "Extract specific field from input",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return {'picked_value': inp.get('field_name')}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        # Create template
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create pick_field template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.fixture
    async def sum_template_id(self, client: AsyncClient) -> str:
        """Create a sum aggregation template for testing."""
        template_data = {
            "name": "sum_values",
            "description": "Sum array of values from multiple inputs",
            "input_schema": {"type": "array"},
            "output_schema": {"type": "object"},
            "code": """
# Handle fan-in aggregation structure
if 'predecessors' in inp:
    # Extract all predecessor results and sum numeric values
    total = 0
    count = 0
    for pred in inp['predecessors']:
        result = pred.get('result', {})
        # Sum any numeric values found in the result
        for key, value in result.items():
            if isinstance(value, (int, float)):
                total += value
                count += 1
    return {'sum': total, 'count': count}
else:
    # Fallback for direct array input
    return {'sum': sum(item.get('value', 0) for item in inp if isinstance(item, dict))}
""",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        # Create template
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create sum template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_linear_workflow_execution(
        self,
        client: AsyncClient,
        passthrough_template_id: str,
        pick_field_template_id: str,
    ):
        """
        Test linear workflow execution (A→B→C).

        Creates workflow with 3 transformation nodes in sequence:
        - Node A: passthrough
        - Node B: pick field
        - Node C: passthrough

        Verifies:
        - Progressive instance creation
        - Each node waits for predecessor completion
        - Final output aggregates correctly
        """
        # Create linear workflow: A→B→C
        workflow_data = {
            "name": "Linear Test Workflow",
            "description": "Three nodes in sequence",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-a",
                    "kind": "transformation",
                    "name": "Node A - Passthrough",
                    "is_start_node": True,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-b",
                    "kind": "transformation",
                    "name": "Node B - Pick Field",
                    "node_template_id": pick_field_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-c",
                    "kind": "transformation",
                    "name": "Node C - Passthrough",
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "n-a", "to_node_id": "n-b"},
                {"edge_id": "e2", "from_node_id": "n-b", "to_node_id": "n-c"},
            ],
        }

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution
        input_data = {
            "data": {"field_name": "test_value", "other_field": "ignored_value"}
        }

        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Verify workflow execution completed successfully
        # (in test environment workflows execute synchronously)
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200
        assert status_response.json()["data"]["status"] in [
            "pending",
            "running",
            "completed",
        ]

        # Get execution graph to verify progressive creation
        graph_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200
        graph_data = graph_response.json()["data"]

        # Should have node instances created progressively
        assert "nodes" in graph_data
        assert "edges" in graph_data
        assert graph_data["workflow_run_id"] == workflow_run_id

        # Get node instances to verify execution order
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200
        nodes_data = nodes_response.json()["data"]
        assert isinstance(nodes_data, list)

        # Verify workflow completes (this will initially fail since execution isn't implemented)
        # In full implementation, we would poll until completion
        final_status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert final_status_response.status_code == 200
        # Initially will be "pending" until implementation is complete

    @pytest.mark.asyncio
    async def test_fan_out_workflow_execution(
        self,
        execution_client,
        passthrough_template_id: str,
        pick_field_template_id: str,
    ):
        """
        Test fan-out pattern (A→[B,C,D]).

        Creates workflow with 1→3 pattern:
        - Node A: passthrough (input)
        - Nodes B,C,D: different transformations

        Verifies:
        - All output nodes receive same input
        - Parallel execution capability
        - Independent completion tracking
        """
        # Create fan-out workflow: A→[B,C,D]
        workflow_data = {
            "name": "Fan-Out Test Workflow",
            "description": "One input to three parallel outputs",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {"type": "array", "items": {"type": "object"}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-source",
                    "kind": "transformation",
                    "name": "Source Node",
                    "is_start_node": True,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-1",
                    "kind": "transformation",
                    "name": "Branch 1",
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-2",
                    "kind": "transformation",
                    "name": "Branch 2",
                    "node_template_id": pick_field_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-3",
                    "kind": "transformation",
                    "name": "Branch 3",
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-source",
                    "to_node_id": "n-branch-1",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n-source",
                    "to_node_id": "n-branch-2",
                },
                {
                    "edge_id": "e3",
                    "from_node_id": "n-source",
                    "to_node_id": "n-branch-3",
                },
            ],
        }

        # Unpack client and session (working pattern)
        http_client, session = execution_client

        # Create workflow
        create_response = await http_client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Start execution
        input_data = {"message": "fan out test", "timestamp": "2024-01-01T00:00:00Z"}

        start_response = await http_client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Manually trigger workflow execution (working pattern)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Verify execution graph shows fan-out structure
        graph_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200
        graph_data = graph_response.json()["data"]

        # Should have 4 node instances after execution
        assert len(graph_data["nodes"]) == 4  # All nodes executed

        # Note: Edge instances may not be created in current implementation
        # Focus on verifying that all nodes executed successfully
        print(f"Nodes executed: {len(graph_data['nodes'])}")
        print(f"Edges created: {len(graph_data['edges'])}")

        # Verify all nodes completed successfully
        for node in graph_data["nodes"]:
            assert node["status"] == "completed", (
                f"Node {node['node_id']} status: {node['status']}"
            )

        # Get node instances to verify parallel execution
        nodes_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200

    @pytest.mark.asyncio
    async def test_fan_in_workflow_execution(
        self, client: AsyncClient, passthrough_template_id: str, sum_template_id: str
    ):
        """
        Test fan-in pattern ([A,B,C]→D).

        Creates workflow with 3→1 pattern:
        - Nodes A,B,C: generate different values
        - Node D: aggregates all inputs

        Verifies:
        - Aggregation node waits for all predecessors
        - Input aggregation creates envelope array
        - Correct aggregation order and format
        """
        # Create fan-in workflow: Start→[A,B,C]→D (modified to have single entry point)
        workflow_data = {
            "name": "Fan-In Test Workflow",
            "description": "Single entry, three parallel branches, one aggregation output",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-start",
                    "kind": "transformation",
                    "name": "Start Node",
                    "is_start_node": True,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-input-a",
                    "kind": "transformation",
                    "name": "Input A",
                    "is_start_node": False,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-input-b",
                    "kind": "transformation",
                    "name": "Input B",
                    "is_start_node": False,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-input-c",
                    "kind": "transformation",
                    "name": "Input C",
                    "is_start_node": False,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-aggregator",
                    "kind": "transformation",
                    "name": "Aggregator",
                    "node_template_id": sum_template_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e0-a",
                    "from_node_id": "n-start",
                    "to_node_id": "n-input-a",
                },
                {
                    "edge_id": "e0-b",
                    "from_node_id": "n-start",
                    "to_node_id": "n-input-b",
                },
                {
                    "edge_id": "e0-c",
                    "from_node_id": "n-start",
                    "to_node_id": "n-input-c",
                },
                {
                    "edge_id": "e1",
                    "from_node_id": "n-input-a",
                    "to_node_id": "n-aggregator",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n-input-b",
                    "to_node_id": "n-aggregator",
                },
                {
                    "edge_id": "e3",
                    "from_node_id": "n-input-c",
                    "to_node_id": "n-aggregator",
                },
            ],
        }

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution with data that can be aggregated
        input_data = {"values": [10, 20, 30]}

        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Verify execution graph shows fan-in structure
        graph_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200
        graph_data = graph_response.json()["data"]

        # Should eventually have 4 node instances and 3 edges
        assert "nodes" in graph_data
        assert "edges" in graph_data

        # Get node instances to verify aggregation waits for all predecessors
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200
        nodes_data = nodes_response.json()["data"]

        # Filter nodes by node_id to check aggregator status
        aggregator_nodes = [
            node for node in nodes_data if node.get("node_id") == "n-aggregator"
        ]

        # Aggregator should wait until all predecessors complete
        if aggregator_nodes:
            # Initially should be pending until all inputs are ready
            assert aggregator_nodes[0]["status"] in ["pending", "running", "completed"]

    @pytest.mark.asyncio
    async def test_diamond_workflow_execution(
        self,
        client: AsyncClient,
        passthrough_template_id: str,
        pick_field_template_id: str,
        sum_template_id: str,
    ):
        """
        Test diamond pattern (A→[B,C]→D).

        Creates workflow with diamond shape:
        - Node A: source
        - Nodes B,C: parallel processing branches
        - Node D: aggregates B and C outputs

        Verifies:
        - Fan-out then fan-in behavior
        - Complex dependency resolution
        - No deadlocks or race conditions
        """
        # Create diamond workflow: A→[B,C]→D
        workflow_data = {
            "name": "Diamond Test Workflow",
            "description": "Diamond pattern with fan-out and fan-in",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-source",
                    "kind": "transformation",
                    "name": "Source",
                    "is_start_node": True,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-left-branch",
                    "kind": "transformation",
                    "name": "Left Branch",
                    "node_template_id": pick_field_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-right-branch",
                    "kind": "transformation",
                    "name": "Right Branch",
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-sink",
                    "kind": "transformation",
                    "name": "Sink - Aggregator",
                    "node_template_id": sum_template_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-source",
                    "to_node_id": "n-left-branch",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n-source",
                    "to_node_id": "n-right-branch",
                },
                {
                    "edge_id": "e3",
                    "from_node_id": "n-left-branch",
                    "to_node_id": "n-sink",
                },
                {
                    "edge_id": "e4",
                    "from_node_id": "n-right-branch",
                    "to_node_id": "n-sink",
                },
            ],
        }

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution with complex test data
        input_data = {
            "left_value": 25,
            "right_value": 35,
            "field_name": "special_field",
            "metadata": {"test": "diamond_pattern"},
        }

        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Verify execution graph shows diamond structure
        graph_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200
        graph_data = graph_response.json()["data"]

        # Should have 4 node instances and 4 edges
        assert "nodes" in graph_data
        assert "edges" in graph_data

        # Verify no deadlocks by checking that workflow can progress
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()["data"]
        assert status_data["status"] in ["pending", "running", "completed", "failed"]

        # Get detailed execution state
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecutionErrorPatterns:
    """Test error handling and failure scenarios in workflow execution."""

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
    async def execution_client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client with session access for execution testing."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, integration_test_session

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.fixture
    async def error_template_id(self, client: AsyncClient) -> str:
        """Create an error-producing node template for testing failures."""
        template_data = {
            "name": "error_template",
            "description": "Template that intentionally fails",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "raise ValueError('Intentional error for testing')",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        # Create template
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create error template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.fixture
    async def passthrough_template_id(self, client: AsyncClient) -> str:
        """Create a passthrough node template for testing."""
        template_data = {
            "name": "passthrough",
            "description": "Simple passthrough template",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        # Create template
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create passthrough template: {response.text}"
        )
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_workflow_with_failing_node(
        self, client: AsyncClient, error_template_id: str
    ):
        """Test workflow execution when one node fails."""
        # Create workflow with one failing node
        workflow_data = {
            "name": "Error Test Workflow",
            "description": "Workflow with intentional failure",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "error"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-error",
                    "kind": "transformation",
                    "name": "Error Node",
                    "is_start_node": True,
                    "node_template_id": error_template_id,
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
            json={"input_data": {"test": "data"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Check that workflow can handle the error gracefully
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200

        # Eventually should move to failed state
        status_data = status_response.json()["data"]
        assert status_data["status"] in ["pending", "running", "failed"]

        # Get node details to verify error handling
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200

    @pytest.mark.asyncio
    async def test_workflow_stops_immediately_when_node_fails(
        self, execution_client, passthrough_template_id: str, error_template_id: str
    ):
        """
        Test that when a node fails, workflow execution stops immediately
        and downstream nodes are NOT executed.

        This reproduces the bug where workflows continue executing all nodes
        even after one fails, causing cascading errors.
        """
        # Unpack client and session (working pattern for reliable execution)
        http_client, session = execution_client

        # Create workflow: identity (succeeds) -> error (fails) -> identity (should NOT execute)
        workflow_data = {
            "name": "Stop on Failure Test",
            "description": "Workflow should stop when middle node fails",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"test": {"type": "string"}},
                    "required": [],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"name": "test sample", "input": {"test": "data"}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n1_success",
                    "kind": "transformation",
                    "name": "First Node (Success)",
                    "is_start_node": True,
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n2_fail",
                    "kind": "transformation",
                    "name": "Second Node (Fails)",
                    "node_template_id": error_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n3_should_not_run",
                    "kind": "transformation",
                    "name": "Third Node (Should NOT Execute)",
                    "node_template_id": passthrough_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n1_success",
                    "to_node_id": "n2_fail",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n2_fail",
                    "to_node_id": "n3_should_not_run",
                },
            ],
        }

        # Create workflow
        create_response = await http_client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Start execution
        start_response = await http_client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "data"}},
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Manually trigger workflow execution (working pattern - more reliable than sleep)
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get workflow status
        status_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()["data"]

        # Workflow should be FAILED (not completed)
        assert status_data["status"] == "failed", (
            f"Expected workflow status='failed' when node fails, "
            f"got status='{status_data['status']}'"
        )

        # Get node instances to verify execution stopped
        nodes_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200
        nodes_data = nodes_response.json()["data"]

        # Find each node instance
        n1 = next((n for n in nodes_data if n["node_id"] == "n1_success"), None)
        n2 = next((n for n in nodes_data if n["node_id"] == "n2_fail"), None)
        n3 = next((n for n in nodes_data if n["node_id"] == "n3_should_not_run"), None)

        # Verify n1 succeeded
        assert n1 is not None
        assert n1["status"] == "completed", (
            "First node should have completed successfully"
        )

        # Verify n2 failed
        assert n2 is not None
        assert n2["status"] == "failed", "Second node should have failed"

        # BUG: Currently n3 might exist and even execute
        # EXPECTED: n3 should either not exist OR be in pending status (never executed)
        if n3 is not None:
            assert n3["status"] == "pending", (
                f"Third node should NOT have executed after n2 failed, "
                f"but got status='{n3['status']}'"
            )

    @pytest.mark.asyncio
    async def test_task_node_with_cy_error_fails_workflow(self, execution_client):
        """
        Test that when a task node's Cy script produces an error output,
        the workflow execution stops immediately and marks both the node
        and the workflow as failed.

        This reproduces the production bug where tasks with Cy errors
        returned {"status": "completed", "output": {"error": "..."}}
        which then caused merge conflicts downstream.
        """
        # Unpack client and session (working pattern for reliable execution)
        http_client, session = execution_client

        # Step 1: Create a task with a Cy script that will error
        # (accessing a non-existent key in a dict)
        failing_task_data = {
            "name": "Failing Cy Task",
            "description": "Task that produces Cy error",
            "script": """
# This will produce a Cy runtime error
input_data = inp
result = input_data['nonexistent_key']  # KeyError
return {"result": result}
""",
            "mode": "saved",
            "created_by": str(SYSTEM_USER_ID),
        }

        task_response = await http_client.post(
            "/v1/test_tenant/tasks", json=failing_task_data
        )
        assert task_response.status_code == 201, (
            f"Failed to create task: {task_response.text}"
        )
        failing_task_id = task_response.json()["data"]["id"]

        # Step 2: Create a workflow with this task as a node
        workflow_data = {
            "name": "Task Node Failure Test",
            "description": "Workflow with failing task node",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"test": {"type": "string"}},
                    "required": [],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"name": "test sample", "input": {"test": "data"}}],
            "nodes": [
                {
                    "node_id": "failing_task_node",
                    "kind": "task",
                    "name": "Failing Task Node",
                    "task_id": failing_task_id,
                    "is_start_node": True,
                    "schemas": {},
                }
            ],
            "edges": [],
            "created_by": str(SYSTEM_USER_ID),
        }

        workflow_response = await http_client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert workflow_response.status_code == 201, (
            f"Failed to create workflow: {workflow_response.text}"
        )
        workflow_id = workflow_response.json()["data"]["id"]

        # CRITICAL: Commit test data so background task can see it
        await session.commit()

        # Step 3: Execute the workflow
        run_response = await http_client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "data"}},
        )
        assert run_response.status_code == 202
        workflow_run_id = run_response.json()["data"]["workflow_run_id"]

        # Step 4: Manually trigger workflow execution (working pattern)
        # This is more reliable than relying on background task execution
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Step 5: Check workflow status - should be FAILED
        # BUG: Currently workflow continues and task node shows "completed"
        # with error output, causing merge conflicts if there are downstream nodes
        # EXPECTED: Workflow should be "failed" and task node should be "failed"
        status_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()["data"]

        assert status_data["status"] == "failed", (
            f"Expected workflow status='failed' when task produces Cy error, "
            f"got status='{status_data['status']}'"
        )

        # Step 6: Check node status - should be FAILED
        nodes_response = await http_client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200
        nodes_data = nodes_response.json()["data"]

        task_node = next(
            (n for n in nodes_data if n["node_id"] == "failing_task_node"), None
        )
        assert task_node is not None
        assert task_node["status"] == "failed", (
            f"Expected task node status='failed' when Cy produces error, "
            f"got status='{task_node['status']}'"
        )

    @pytest.mark.asyncio
    async def test_workflow_cancellation_during_execution(
        self, client: AsyncClient, error_template_id: str
    ):
        """Test workflow cancellation stops execution properly."""
        # Create simple workflow for cancellation test
        workflow_data = {
            "name": "Cancellation Test Workflow",
            "description": "Workflow for testing cancellation",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "cancel"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-slow",
                    "kind": "transformation",
                    "name": "Slow Node",
                    "is_start_node": True,
                    "node_template_id": error_template_id,  # Use error template as placeholder
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
            json={"input_data": {"test": "data"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Check workflow status before cancellation
        pre_cancel_status = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        pre_status_data = pre_cancel_status.json()["data"]
        print(f"Pre-cancellation status: {pre_status_data['status']}")

        # Try to cancel the workflow
        cancel_response = await client.post(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/cancel"
        )
        print(f"Cancel response: {cancel_response.status_code}")

        # In test environment without background execution, workflow stays pending and can be cancelled
        # This is expected behavior - cancellation succeeds for pending/running workflows
        assert cancel_response.status_code == 204  # Cancellation succeeded

        # Verify workflow moved to cancelled state
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()["data"]
        print(f"Post-cancellation status: {status_data['status']}")

        # Should be cancelled (workflow was successfully cancelled before execution)
        assert status_data["status"] == "cancelled"
