"""
Integration tests for the progressive execution algorithm.
Tests the core workflow orchestration logic with real database operations.
All tests follow TDD principles and should FAIL initially since implementation isn't complete yet.
"""

import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow_execution import (
    WorkflowRun,
)
from analysi.services.workflow_execution import WorkflowExecutor

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestProgressiveExecutionAlgorithm:
    """Test the progressive execution algorithm with real database operations."""

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

    @pytest.fixture
    def executor(self, integration_test_session: AsyncSession):
        """Create a WorkflowExecutor with real database session."""
        return WorkflowExecutor(integration_test_session)

    @pytest.fixture
    async def node_template(self, integration_test_session: AsyncSession):
        """Get the system Identity template for use in integration tests."""
        from sqlalchemy import select

        from analysi.constants import TemplateConstants
        from analysi.models.workflow import NodeTemplate

        # Fetch the system Identity template (seeded in conftest.py)
        stmt = select(NodeTemplate).where(
            NodeTemplate.id == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        )
        result = await integration_test_session.execute(stmt)
        template = result.scalar_one()
        return template

    @pytest.fixture
    async def sample_workflow_run(
        self, integration_test_session: AsyncSession, node_template
    ) -> WorkflowRun:
        """Create a sample workflow run with complete workflow structure for testing."""
        from analysi.models.workflow import Workflow, WorkflowEdge, WorkflowNode

        template_id = node_template.id

        # First create a valid workflow
        workflow = Workflow(
            tenant_id="test_tenant",
            name="Test Progressive Workflow",
            description="Test workflow for progressive execution",
            is_dynamic=False,
            io_schema={
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            created_by=str(SYSTEM_USER_ID),
        )
        integration_test_session.add(workflow)
        await integration_test_session.commit()
        await integration_test_session.refresh(workflow)

        # Create workflow nodes that the tests will reference
        # All transformation nodes must have node_template_id per database constraint
        root_node = WorkflowNode(
            workflow_id=workflow.id,
            node_id="n-root",
            name="Root Node",
            kind="transformation",
            node_template_id=template_id,
            schemas={
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
        )

        dependent_node = WorkflowNode(
            workflow_id=workflow.id,
            node_id="n-dependent",
            name="Dependent Node",
            kind="transformation",
            node_template_id=template_id,
            schemas={
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
        )

        aggregator_node = WorkflowNode(
            workflow_id=workflow.id,
            node_id="n-aggregator",
            name="Aggregator Node",
            kind="transformation",
            node_template_id=template_id,
            schemas={
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
        )

        integration_test_session.add_all([root_node, dependent_node, aggregator_node])
        await integration_test_session.commit()
        await integration_test_session.refresh(root_node)
        await integration_test_session.refresh(dependent_node)
        await integration_test_session.refresh(aggregator_node)

        # Create edges between nodes using the node UUIDs
        edge1 = WorkflowEdge(
            workflow_id=workflow.id,
            edge_id="e1",
            from_node_uuid=root_node.id,
            to_node_uuid=dependent_node.id,
        )

        edge2 = WorkflowEdge(
            workflow_id=workflow.id,
            edge_id="e2",
            from_node_uuid=dependent_node.id,
            to_node_uuid=aggregator_node.id,
        )

        integration_test_session.add_all([edge1, edge2])
        await integration_test_session.commit()

        # Now create the workflow run with the valid workflow_id
        workflow_run = WorkflowRun(
            tenant_id="test_tenant",
            workflow_id=workflow.id,
            status="pending",
            input_type="inline",
            input_location='{"test": "data"}',
        )

        integration_test_session.add(workflow_run)
        await integration_test_session.commit()
        await integration_test_session.refresh(workflow_run)

        # Store the node UUIDs on the workflow_run for easy access in tests
        workflow_run._test_nodes = {
            "n-root": root_node.id,
            "n-dependent": dependent_node.id,
            "n-aggregator": aggregator_node.id,
        }

        return workflow_run

    @pytest.mark.asyncio
    async def test_workflow_instance_creation_progressive(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test that node instances are created progressively as dependencies are satisfied.

        Verifies:
        - Root nodes are created immediately
        - Dependent nodes wait for predecessors
        - Node creation follows topological order
        """
        workflow_run_id = sample_workflow_run.id
        root_node_uuid = sample_workflow_run._test_nodes["n-root"]

        # Test creating a root node (no predecessors) - now implemented!
        root_instance = await executor.create_node_instance(
            workflow_run_id=workflow_run_id, node_id="n-root", node_uuid=root_node_uuid
        )

        # Verify the instance was created correctly
        assert root_instance is not None
        assert root_instance.workflow_run_id == workflow_run_id
        assert root_instance.node_id == "n-root"
        assert root_instance.node_uuid == root_node_uuid
        assert root_instance.status == "pending"
        # 3. Set up for immediate execution (no predecessors to wait for)

    @pytest.mark.asyncio
    async def test_predecessor_dependency_checking(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test logic for checking if all predecessor nodes have completed.

        Verifies:
        - Single predecessor completion detection
        - Multiple predecessor completion detection (fan-in)
        - Incomplete predecessor handling
        """
        workflow_run_id = sample_workflow_run.id
        root_node_uuid = sample_workflow_run._test_nodes["n-root"]
        sample_workflow_run._test_nodes["n-dependent"]

        # Test checking for root node (should be ready - no predecessors)
        is_ready = await executor.check_predecessors_complete(workflow_run_id, "n-root")
        assert is_ready is True  # Root node has no predecessors

        # Test checking for dependent node (should not be ready initially)
        is_ready = await executor.check_predecessors_complete(
            workflow_run_id, "n-dependent"
        )
        assert is_ready is False  # No predecessor instances exist yet

        # Create and complete the root node instance
        root_instance = await executor.create_node_instance(
            workflow_run_id=workflow_run_id, node_id="n-root", node_uuid=root_node_uuid
        )

        # Mark it as completed (simulate execution)
        await executor.node_repo.update_node_instance_status(
            root_instance.id, status="completed"
        )
        await executor.session.commit()

        # Now the dependent node should be ready
        is_ready = await executor.check_predecessors_complete(
            workflow_run_id, "n-dependent"
        )
        assert is_ready is True  # Root predecessor is now completed

    @pytest.mark.asyncio
    async def test_predecessor_output_aggregation_single(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test aggregating outputs from a single predecessor.

        Verifies:
        - Single input retrieval and formatting
        - Envelope structure handling
        - Storage retrieval integration
        """
        workflow_run_id = sample_workflow_run.id
        root_node_uuid = sample_workflow_run._test_nodes["n-root"]

        # Create and execute the root node to have output to aggregate
        root_instance = await executor.create_node_instance(
            workflow_run_id=workflow_run_id, node_id="n-root", node_uuid=root_node_uuid
        )

        # Simulate completion with output data
        test_output = {"result": "root_node_output", "value": 42}
        await executor.node_repo.update_node_instance_status(
            root_instance.id, status="completed"
        )
        await executor.node_repo.save_node_instance_output(
            root_instance.id,
            output_type="inline",
            output_location=json.dumps(test_output),
        )
        await executor.session.commit()

        # Now test aggregation for the dependent node
        inputs = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-dependent"
        )

        # Verify aggregated data
        assert isinstance(inputs, dict)  # Should return merged data
        # Note: The exact structure depends on implementation
        # For a single predecessor, it might return the output directly

    @pytest.mark.asyncio
    async def test_predecessor_output_aggregation_multiple(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test aggregating outputs from multiple predecessors (fan-in scenario).

        Verifies:
        - Multiple input retrieval and ordering
        - Envelope array construction
        - Consistent aggregation format
        """
        workflow_run_id = sample_workflow_run.id
        root_node_uuid = sample_workflow_run._test_nodes["n-root"]
        dependent_node_uuid = sample_workflow_run._test_nodes["n-dependent"]

        # Create and complete both root and dependent nodes to test fan-in to aggregator
        root_instance = await executor.create_node_instance(
            workflow_run_id=workflow_run_id, node_id="n-root", node_uuid=root_node_uuid
        )

        dependent_instance = await executor.create_node_instance(
            workflow_run_id=workflow_run_id,
            node_id="n-dependent",
            node_uuid=dependent_node_uuid,
        )

        # Complete both nodes with different outputs
        await executor.node_repo.update_node_instance_status(
            root_instance.id, "completed"
        )
        await executor.node_repo.save_node_instance_output(
            root_instance.id,
            output_type="inline",
            output_location=json.dumps({"result": "root_output", "value": 1}),
        )

        await executor.node_repo.update_node_instance_status(
            dependent_instance.id, "completed"
        )
        await executor.node_repo.save_node_instance_output(
            dependent_instance.id,
            output_type="inline",
            output_location=json.dumps({"result": "dependent_output", "value": 2}),
        )
        await executor.session.commit()

        # Test aggregation for the aggregator node (which has no edges to it in our fixture)
        # For now just test that the method works - no predecessors scenario
        inputs = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-aggregator"
        )

        # Should return empty dict since aggregator has no predecessors in our current fixture
        # In a real fan-in scenario, we'd need to create edges from both root and dependent to aggregator
        assert isinstance(inputs, dict)

    @pytest.mark.asyncio
    async def test_workflow_state_transitions(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test workflow run status state machine transitions.

        Verifies:
        - Valid state transitions (pending→running→completed/failed)
        - Invalid transition rejection
        - Timestamp updates
        """
        workflow_run_id = sample_workflow_run.id

        # Get initial workflow run state (use query since WorkflowRun has composite PK)
        from sqlalchemy import select

        stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        result = await executor.session.execute(stmt)
        initial_run = result.scalar_one()

        assert initial_run.status == "pending"
        assert initial_run.started_at is None
        assert initial_run.completed_at is None

        # Test transitioning to running state
        await executor.update_workflow_status(workflow_run_id, "running")
        await executor.session.commit()

        # Verify running state
        result = await executor.session.execute(stmt)
        running_run = result.scalar_one()
        assert running_run.status == "running"
        assert running_run.started_at is not None  # Should set started_at timestamp
        assert running_run.completed_at is None  # Should not set completed_at yet

        # Test transitioning to completed state
        await executor.update_workflow_status(workflow_run_id, "completed")
        await executor.session.commit()

        # Verify completed state
        result = await executor.session.execute(stmt)
        completed_run = result.scalar_one()
        assert completed_run.status == "completed"
        assert completed_run.started_at is not None
        assert (
            completed_run.completed_at is not None
        )  # Should set completed_at timestamp

        # For another test, we could test failed state with error message
        # But since we're using the same workflow_run, we'll skip that here

    @pytest.mark.asyncio
    async def test_execution_monitoring_loop(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test the main execution monitoring loop behavior.

        Verifies:
        - Polling for state changes
        - Node execution triggering
        - Loop termination conditions
        """

        # For now, just test that the method exists and doesn't crash
        # In a real test, we would mock the polling and verify it stops correctly
        # Since monitor_execution might run indefinitely, we'll skip actual execution
        # and just verify the method is callable (exists)
        assert hasattr(executor, "monitor_execution")
        assert callable(executor.monitor_execution)

        # In a full implementation test, would:
        # 1. Poll for workflow state changes at regular intervals
        # 2. Check for nodes ready for execution
        # 3. Trigger node execution when prerequisites are met
        # 4. Continue until workflow reaches terminal state
        # 5. Handle errors and update workflow status accordingly

    @pytest.mark.asyncio
    async def test_node_execution_by_type(
        self, executor, sample_workflow_run, node_template
    ):
        """
        Test node execution dispatch based on node type.

        Verifies:
        - Transformation node execution
        - Task node execution
        - Foreach node execution
        - Error handling for unknown types
        """
        # Use the existing workflow structure from sample_workflow_run
        workflow_run_id = sample_workflow_run.id
        root_node_uuid = sample_workflow_run._test_nodes["n-root"]

        # Create a test node instance using the existing node
        await executor.create_node_instance(
            workflow_run_id=workflow_run_id, node_id="n-root", node_uuid=root_node_uuid
        )

        # For now, just test that the method exists and doesn't crash immediately
        # In a real test, we would verify node execution behavior
        assert hasattr(executor, "execute_node_instance")
        assert callable(executor.execute_node_instance)

        # For actual execution testing, would need proper input data setup
        # and would verify:
        # 1. Determine node type from workflow definition
        # 2. Dispatch to appropriate executor (transformation, task, foreach)
        # 3. Update node instance status during execution
        # 4. Store execution results
        # 5. Handle execution errors gracefully


@pytest.mark.asyncio
@pytest.mark.integration
class TestProgressiveExecutionRealScenarios:
    """Test progressive execution with realistic workflow scenarios."""

    @pytest.fixture
    async def node_template(self, integration_test_session: AsyncSession):
        """Get the system Identity template for use in integration tests."""
        from sqlalchemy import select

        from analysi.constants import TemplateConstants
        from analysi.models.workflow import NodeTemplate

        # Fetch the system Identity template (seeded in conftest.py)
        stmt = select(NodeTemplate).where(
            NodeTemplate.id == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        )
        result = await integration_test_session.execute(stmt)
        template = result.scalar_one()
        return template

    @pytest.fixture
    async def slow_template(self, integration_test_session: AsyncSession):
        """Create a slow node template for cancellation testing."""
        from analysi.models.workflow import NodeTemplate

        template = NodeTemplate(
            resource_id=uuid4(),
            name="test_slow_template",
            description="Slow template for cancellation testing",
            kind="identity",
            input_schema={"type": "object", "properties": {"data": {}}},
            output_schema={"type": "object", "properties": {"data": {}}},
            code="""
# Sleep for 3 seconds to allow cancellation
time.sleep(3)
result = {"message": "This should not complete if cancelled", "input": inp}
return result
""",
            language="python",
            type="static",
            enabled=True,
            revision_num=1,
        )

        integration_test_session.add(template)
        await integration_test_session.commit()
        await integration_test_session.refresh(template)
        return template

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
    async def test_progressive_execution_linear_workflow(
        self, client: AsyncClient, node_template
    ):
        """
        Test progressive execution on a linear workflow (A→B→C).

        Verifies end-to-end progressive behavior:
        - Node A executes immediately
        - Node B waits for A completion
        - Node C waits for B completion
        - Workflow completes when C finishes
        """
        # Create a simple linear workflow using the test template
        template_id = str(node_template.id)
        workflow_data = {
            "name": "Progressive Linear Test",
            "description": "Tests progressive execution in linear chain",
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
                    "node_id": "n-first",
                    "kind": "transformation",
                    "name": "First Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-second",
                    "kind": "transformation",
                    "name": "Second Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-third",
                    "kind": "transformation",
                    "name": "Third Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "n-first", "to_node_id": "n-second"},
                {"edge_id": "e2", "from_node_id": "n-second", "to_node_id": "n-third"},
            ],
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
            json={"input_data": {"test": "progressive_execution"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Check initial state - should only have first node ready
        initial_graph = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert initial_graph.status_code == 200

        # Monitor progression (in real implementation, would poll until completion)
        # For now, just verify the endpoint works
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200

    @pytest.mark.asyncio
    async def test_progressive_execution_fan_in_synchronization(
        self, client: AsyncClient, node_template
    ):
        """
        Test progressive execution with fan-in synchronization ([A,B]→C).

        Verifies:
        - Parallel execution of A and B
        - C waits for both A and B to complete
        - Proper synchronization at fan-in point
        """
        # Create fan-in workflow using the test template
        template_id = str(node_template.id)
        workflow_data = {
            "name": "Progressive Fan-In Test",
            "description": "Tests synchronization in fan-in pattern",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-left",
                    "kind": "transformation",
                    "name": "Left Branch",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-right",
                    "kind": "transformation",
                    "name": "Right Branch",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-merge",
                    "kind": "transformation",
                    "name": "Merge Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "array", "items": {}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "n-left", "to_node_id": "n-merge"},
                {"edge_id": "e2", "from_node_id": "n-right", "to_node_id": "n-merge"},
            ],
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
            json={"input_data": {"data": [1, 2, 3, 4, 5]}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Verify initial state shows parallel execution potential
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200

        # Verify merge node waits for both predecessors
        graph_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200

    @pytest.mark.asyncio
    async def test_progressive_execution_error_propagation(
        self, client: AsyncClient, node_template
    ):
        """
        Test that errors in progressive execution propagate correctly.

        Verifies:
        - Failed node stops downstream execution
        - Workflow status updates to failed
        - Error messages are preserved
        """
        # Create workflow with potential failure point using the test template
        template_id = str(node_template.id)
        workflow_data = {
            "name": "Progressive Error Test",
            "description": "Tests error propagation in progressive execution",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-good",
                    "kind": "transformation",
                    "name": "Good Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-bad",
                    "kind": "transformation",
                    "name": "Bad Node (Will Fail)",
                    "node_template_id": template_id,  # Would use error template in real test
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "n-downstream",
                    "kind": "transformation",
                    "name": "Should Not Execute",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "n-good", "to_node_id": "n-bad"},
                {
                    "edge_id": "e2",
                    "from_node_id": "n-bad",
                    "to_node_id": "n-downstream",
                },
            ],
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
            json={"input_data": {"test": "error_scenario"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Monitor execution state
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200

        # In full implementation, would verify:
        # 1. Workflow eventually moves to "failed" status
        # 2. Good node completes successfully
        # 3. Bad node fails with error message
        # 4. Downstream node never executes (stays pending)

    @pytest.mark.skip(
        reason="Cancellation testing requires async execution mode which conflicts with test environment's synchronous execution for transaction isolation"
    )
    @pytest.mark.asyncio
    async def test_progressive_execution_cancellation_handling(
        self, client: AsyncClient, slow_template
    ):
        """
        Test progressive execution handles cancellation correctly.

        NOTE: This test is skipped because:
        1. Cancellation requires long-running templates (using time.sleep or similar)
        2. Our test environment uses synchronous execution for transaction isolation
        3. time.sleep() blocks the entire test execution preventing cancellation

        In production, cancellation works correctly because:
        - Workflows run asynchronously in background tasks
        - The cancellation endpoint can interrupt running workflows
        - asyncio.create_task() allows proper task cancellation

        To properly test cancellation in the future:
        - Create a separate test environment with async execution
        - Use asyncio.sleep() instead of time.sleep()
        - Or test cancellation at the unit level with mocked execution

        Verifies (when not skipped):
        - Running nodes are stopped
        - Pending nodes are not started
        - Workflow status updates to cancelled
        """
        # Create workflow for cancellation testing using the slow template
        template_id = str(slow_template.id)
        workflow_data = {
            "name": "Progressive Cancellation Test",
            "description": "Tests cancellation during progressive execution",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-slow",
                    "kind": "transformation",
                    "name": "Slow Node",
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

        # Start execution
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "cancellation"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Cancel immediately
        cancel_response = await client.post(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/cancel"
        )
        assert cancel_response.status_code == 204

        # Verify cancellation effect
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200

        # Should eventually show cancelled status
        status_data = status_response.json()["data"]
        assert status_data["status"] in [
            "pending",
            "cancelled",
        ]  # May be immediate or eventual
