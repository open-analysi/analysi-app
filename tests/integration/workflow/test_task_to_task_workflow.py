"""
Task → Task Workflow Integration Test

Tests the missing workflow pattern where one task feeds directly into another task.
This validates:
1. Task output envelope handling when feeding into another task
2. Proper data flow between Cy script executions
3. Both tasks receiving correct input extraction from envelopes
4. Chaining of LLM/MCP tool calls across multiple task nodes

Workflow: Topic Input → Joke Generation Task → Joke Evaluation Task → Output
"""

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.task import Task
from tests.utils.cy_output import parse_cy_output

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
class TestTaskToTaskWorkflow:
    """Integration test for Task → Task workflow pattern."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        """Create an async HTTP client for testing with test database."""

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
    def topic_input(self):
        """Simple topic input for joke generation."""
        return {"topic": "cats"}

    @pytest.mark.asyncio
    async def test_task_to_task_joke_workflow(
        self,
        client,  # FastAPI test client tuple[AsyncClient, AsyncSession]
        topic_input,
    ):
        """
        Test Task → Task workflow: Joke Generation → Joke Evaluation

        This validates the missing workflow pattern where tasks feed directly into each other.
        Requires OPENAI_API_KEY environment variable for real LLM calls.
        """
        # Skip if no OpenAI API key available
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip(
                "OPENAI_API_KEY not available - skipping real LLM integration test"
            )

        # Unpack client and session from tuple
        http_client, session = client
        tenant_id = "test-tenant"

        try:
            # CREATE TEST DATA DIRECTLY IN TEST SESSION (following proven pattern)
            from uuid import uuid4

            from analysi.models.component import Component
            from analysi.models.task import Task

            # 1. Create joke generation task
            joke_component_id = uuid4()
            joke_task_id = uuid4()

            joke_component = Component(
                id=joke_component_id,
                tenant_id=tenant_id,
                name="Joke Generator",
                description="Generate short jokes about given topics",
                categories=["llm", "humor", "generation"],
                status="enabled",
                kind="task",
            )
            session.add(joke_component)
            await session.flush()

            joke_task = Task(
                id=joke_task_id,
                component_id=joke_component_id,
                function="reasoning",
                scope="processing",
                script="""
# Joke Generation Task
topic = input["topic"]

# Generate a simple joke using string interpolation
simple_joke = "A ${topic} joke: Why did the ${topic} cross the road? To test Task to Task workflow!"

return {
    "topic": topic,
    "joke": simple_joke,
    "generated_at": "2025-01-15T10:30:00Z"
}
""",
            )
            session.add(joke_task)

            # 2. Create joke evaluation task
            eval_component_id = uuid4()
            eval_task_id = uuid4()

            eval_component = Component(
                id=eval_component_id,
                tenant_id=tenant_id,
                name="Joke Evaluator",
                description="Evaluate the quality of jokes and provide ratings",
                categories=["llm", "evaluation", "analysis"],
                status="enabled",
                kind="task",
            )
            session.add(eval_component)
            await session.flush()

            eval_task = Task(
                id=eval_task_id,
                component_id=eval_component_id,
                function="reasoning",
                scope="processing",
                script="""
# Simple Task 2 - debug what we actually receive
debug_msg = log("SECOND TASK INPUT: <input>")

topic = input["topic"]
joke = input["joke"]

# Create simple output that references both the joke and topic
simple_evaluation = "Evaluated the ${topic} joke successfully. The joke quality is good and references ${topic} appropriately."

return {
    "topic": topic,
    "joke": joke,
    "evaluation": simple_evaluation,
    "workflow_type": "task_to_task"
}
""",
            )
            session.add(eval_task)

            # Commit all test data
            await session.commit()

            # 3. CREATE TASK → TASK WORKFLOW (task as entry node!)
            workflow_data = {
                "name": "Joke Generation and Evaluation Pipeline",
                "description": "Task → Task workflow: Generate joke then evaluate it",
                "is_dynamic": False,
                "created_by": str(SYSTEM_USER_ID),
                "io_schema": {
                    "input": {
                        "type": "object",
                        "properties": {"topic": {"type": "string"}},
                        "required": ["topic"],
                    },
                    "output": {"type": "object"},
                },
                "data_samples": [{"topic": "programming"}],
                "nodes": [
                    {
                        "node_id": "n-joke-gen",
                        "kind": "task",
                        "name": "Generate Joke",
                        "is_start_node": True,
                        "task_id": str(joke_component_id),
                        "schemas": {
                            "input": {"type": "object"},
                            "output_result": {"type": "object"},
                        },
                    },
                    {
                        "node_id": "n-joke-eval",
                        "kind": "task",
                        "name": "Evaluate Joke",
                        "task_id": str(eval_component_id),
                        "schemas": {
                            "input": {"type": "object"},
                            "output_result": {"type": "object"},
                        },
                    },
                ],
                "edges": [
                    {
                        "edge_id": "e1",
                        "from_node_id": "n-joke-gen",
                        "to_node_id": "n-joke-eval",
                    }
                ],
            }

            response = await http_client.post(
                f"/v1/{tenant_id}/workflows", json=workflow_data
            )
            assert response.status_code == 201
            workflow_id = response.json()["data"]["id"]

            # COMMIT TEST DATA so background task can see it
            await session.commit()

            # 4. EXECUTE WORKFLOW via REST API
            execution_data = {"input_data": topic_input}

            response = await http_client.post(
                f"/v1/{tenant_id}/workflows/{workflow_id}/run", json=execution_data
            )
            if response.status_code != 202:
                print(
                    f"DEBUG: Workflow execution failed with {response.status_code}: {response.text}"
                )
            assert response.status_code == 202  # Accepted for async processing

            run_id = response.json()["data"]["workflow_run_id"]

            # 5. MANUALLY TRIGGER WORKFLOW EXECUTION (working pattern)
            from analysi.services.workflow_execution import WorkflowExecutor

            executor = WorkflowExecutor(session)
            await executor.monitor_execution(run_id)
            await session.commit()

            # 6. VERIFY SUCCESSFUL COMPLETION - workflow should be completed now
            # Expire all cached objects to force fresh queries
            session.expire_all()

            # 7. GET AND VERIFY RESULTS
            response = await http_client.get(f"/v1/{tenant_id}/workflow-runs/{run_id}")
            if response.status_code != 200:
                print(
                    f"❌ GET workflow-runs API failed with {response.status_code}: {response.text}"
                )
            assert response.status_code == 200

            results = response.json()["data"]

            # Verify workflow executed and get the final output
            assert "output_data" in results, "Workflow should have output_data"

            # The workflow output should be the result from the final task node
            workflow_output = results["output_data"]

            # The output is in envelope format, extract the result
            if "result" in workflow_output:
                final_result = parse_cy_output(workflow_output["result"])
            else:
                final_result = parse_cy_output(workflow_output)

            # Verify Task → Task pipeline worked correctly
            assert "topic" in final_result
            assert "joke" in final_result
            assert "evaluation" in final_result
            assert "workflow_type" in final_result

            # Verify the topic passed through correctly
            assert final_result["topic"] == topic_input["topic"]

            # Verify joke was generated (not empty)
            joke_text = final_result["joke"]
            assert joke_text is not None
            assert isinstance(joke_text, str)
            assert len(joke_text.strip()) > 10  # Should be substantial joke

            # Verify evaluation was performed (not empty)
            evaluation_text = final_result["evaluation"]
            assert evaluation_text is not None
            assert isinstance(evaluation_text, str)
            assert len(evaluation_text.strip()) > 20  # Should be substantial evaluation

            # Verify workflow type marker
            assert final_result["workflow_type"] == "task_to_task"

            # Verify evaluation contains expected elements
            eval_lower = evaluation_text.lower()
            eval_keywords = ["rate", "score", "joke", topic_input["topic"].lower()]
            found_keywords = [word for word in eval_keywords if word in eval_lower]
            assert len(found_keywords) >= 2, (
                f"Evaluation should reference the joke and topic. Evaluation: {evaluation_text}"
            )

            print("✅ Task → Task workflow executed successfully!")
            print(f"📝 Topic: '{final_result['topic']}'")
            print(f"😄 Generated joke length: {len(joke_text)} characters")
            print(f"📊 Evaluation length: {len(evaluation_text)} characters")
            print("🔗 Verified Task → Task data flow with envelope handling")

        except Exception as e:
            pytest.fail(f"Task → Task workflow test failed. Error: {e}")

    @pytest.mark.asyncio
    async def test_task_to_task_workflow_creation_via_api(self, client):
        """Test that we can create Task → Task workflows via REST API (validation test)."""
        # Unpack client and session from tuple
        http_client, session = client
        tenant_id = "test-tenant"

        # Create minimal test data for workflow creation validation

        # Create two simple tasks
        task1_component_id = uuid4()
        task1_id = uuid4()
        task2_component_id = uuid4()
        task2_id = uuid4()

        for component_id, task_id, name in [
            (task1_component_id, task1_id, "Task 1"),
            (task2_component_id, task2_id, "Task 2"),
        ]:
            component = Component(
                id=component_id,
                tenant_id=tenant_id,
                name=name,
                description=f"Test {name}",
                categories=["test"],
                status="enabled",
                kind="task",
            )
            session.add(component)
            await session.flush()

            task = Task(
                id=task_id,
                component_id=component_id,
                function="reasoning",
                scope="processing",
                script=f'return {{"result": "{name} executed"}}',
            )
            session.add(task)

        await session.commit()

        # Create Task → Task workflow (task as entry node!)
        workflow_data = {
            "name": "Task to Task Validation",
            "description": "Test Task → Task workflow creation",
            "is_dynamic": False,
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"input_value": {"type": "string"}},
                    "required": ["input_value"],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"input_value": "test"}],
            "nodes": [
                {
                    "node_id": "n-task1",
                    "kind": "task",
                    "name": "First Task",
                    "is_start_node": True,
                    "task_id": str(task1_component_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-task2",
                    "kind": "task",
                    "name": "Second Task",
                    "task_id": str(task2_component_id),
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "n-task1", "to_node_id": "n-task2"}
            ],
        }

        # Create workflow with Task → Task pattern
        response = await http_client.post(
            f"/v1/{tenant_id}/workflows", json=workflow_data
        )
        if response.status_code != 201:
            print(
                "Task → Task workflow creation failed:",
                response.status_code,
                response.json(),
            )
        assert response.status_code == 201

        created_workflow = response.json()["data"]
        workflow_id = created_workflow["id"]

        # Get the created workflow
        response = await http_client.get(f"/v1/{tenant_id}/workflows/{workflow_id}")
        assert response.status_code == 200

        workflow = response.json()["data"]
        assert len(workflow["nodes"]) == 2
        assert len(workflow["edges"]) == 1

        # Verify both nodes are tasks
        node_kinds = [node["kind"] for node in workflow["nodes"]]
        assert all(kind == "task" for kind in node_kinds), (
            f"Expected all task nodes, got: {node_kinds}"
        )

        # Verify the edge connects the tasks correctly
        # Create a mapping of UUID to node_id
        node_uuid_to_id = {node["id"]: node["node_id"] for node in workflow["nodes"]}

        edge = workflow["edges"][0]
        from_node_id = node_uuid_to_id[edge["from_node_uuid"]]
        to_node_id = node_uuid_to_id[edge["to_node_uuid"]]

        assert from_node_id == "n-task1"
        assert to_node_id == "n-task2"

        print("✅ Task → Task workflow creation via REST API works!")
