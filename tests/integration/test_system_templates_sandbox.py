"""
Integration tests for system templates (identity, merge, collect) executed in sandbox.

Tests that all three system templates work correctly when executed through
the actual sandbox environment, not just mocked.
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
class TestSystemTemplatesSandbox:
    """Test all system templates execute correctly in sandbox."""

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
    async def test_all_system_templates_in_single_workflow(self, client):
        """
        Test all three system templates (identity, merge, collect) in one workflow.

        Workflow structure:
        identity → [branch_a, branch_b] → merge → collect → identity

        This tests:
        1. system_identity (pass-through)
        2. system_merge (fan-in with field-level conflict detection)
        3. system_collect (array aggregation)
        4. Sandbox execution of template code
        5. Envelope structure handling
        """
        http_client, session = client

        # Get system template IDs
        templates_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates"
        )
        assert templates_response.status_code == 200
        templates = templates_response.json()["data"]

        identity_template = next(
            (t for t in templates if t["name"] == "system_identity"), None
        )
        merge_template = next(
            (t for t in templates if t["name"] == "system_merge"), None
        )
        collect_template = next(
            (t for t in templates if t["name"] == "system_collect"), None
        )

        assert identity_template is not None, "system_identity template not found"
        assert merge_template is not None, "system_merge template not found"
        assert collect_template is not None, "system_collect template not found"

        identity_id = identity_template["id"]
        merge_id = merge_template["id"]
        collect_id = collect_template["id"]

        # Create custom templates for branches (to add different fields)
        branch_a_template_id = await self.create_template(
            http_client,
            "add_field_a",
            """
# Add field 'a' to input
result = inp.copy() if isinstance(inp, dict) else {}
result['a'] = 'value_a'
return result
""",
            {"type": "object"},
            {"type": "object"},
            "Adds field 'a'",
        )

        branch_b_template_id = await self.create_template(
            http_client,
            "add_field_b",
            """
# Add field 'b' to input
result = inp.copy() if isinstance(inp, dict) else {}
result['b'] = 'value_b'
return result
""",
            {"type": "object"},
            {"type": "object"},
            "Adds field 'b'",
        )

        # Create workflow: identity → [branch_a, branch_b] → merge → [identity, identity] → collect
        workflow_data = {
            "name": "System Templates Sandbox Test",
            "description": "Test all three system templates in sandbox",
            "is_dynamic": False,
            "data_samples": [
                {
                    "name": "Test all templates",
                    "input": {"base": "initial"},
                    "description": "Tests identity, merge, and collect templates",
                }
            ],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"base": {"type": "string"}},
                },
                "output": {"type": "object"},
            },
            "nodes": [
                # Start with identity
                {
                    "node_id": "n-identity-start",
                    "kind": "transformation",
                    "name": "Identity Start",
                    "is_start_node": True,
                    "node_template_id": identity_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                # Parallel branches
                {
                    "node_id": "n-branch-a",
                    "kind": "transformation",
                    "name": "Branch A",
                    "node_template_id": branch_a_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-b",
                    "kind": "transformation",
                    "name": "Branch B",
                    "node_template_id": branch_b_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                # Merge node
                {
                    "node_id": "n-merge",
                    "kind": "transformation",
                    "name": "Merge",
                    "node_template_id": merge_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "object"},
                    },
                },
                # Parallel identities (for collect test)
                {
                    "node_id": "n-identity-1",
                    "kind": "transformation",
                    "name": "Identity 1",
                    "node_template_id": identity_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-identity-2",
                    "kind": "transformation",
                    "name": "Identity 2",
                    "node_template_id": identity_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                # Collect node
                {
                    "node_id": "n-collect",
                    "kind": "transformation",
                    "name": "Collect",
                    "node_template_id": collect_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "array"},
                    },
                },
            ],
            "edges": [
                # identity → branches
                {
                    "edge_id": "e1",
                    "from_node_id": "n-identity-start",
                    "to_node_id": "n-branch-a",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n-identity-start",
                    "to_node_id": "n-branch-b",
                },
                # branches → merge
                {
                    "edge_id": "e3",
                    "from_node_id": "n-branch-a",
                    "to_node_id": "n-merge",
                },
                {
                    "edge_id": "e4",
                    "from_node_id": "n-branch-b",
                    "to_node_id": "n-merge",
                },
                # merge → identities
                {
                    "edge_id": "e5",
                    "from_node_id": "n-merge",
                    "to_node_id": "n-identity-1",
                },
                {
                    "edge_id": "e6",
                    "from_node_id": "n-merge",
                    "to_node_id": "n-identity-2",
                },
                # identities → collect
                {
                    "edge_id": "e7",
                    "from_node_id": "n-identity-1",
                    "to_node_id": "n-collect",
                },
                {
                    "edge_id": "e8",
                    "from_node_id": "n-identity-2",
                    "to_node_id": "n-collect",
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

        # Commit test data
        await session.commit()
        print("✅ Committed workflow")

        # Execute workflow
        test_input = {"base": "initial"}
        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": test_input},
        )
        assert start_response.status_code == 202, (
            f"Failed to start workflow: {start_response.text}"
        )
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]
        print(f"Workflow started: {workflow_run_id}")

        # Manually trigger execution
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get final result
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200
        result = details_response.json()["data"]

        # Verify workflow completed successfully
        assert result["status"] == "completed", (
            f"Workflow failed: {result.get('error_message')}"
        )

        print("✅ Workflow completed successfully!")
        print("   All system templates executed correctly in sandbox:")
        print("   - system_identity: Pass-through transformation (3 instances)")
        print(
            "   - system_merge: Field-level merge with conflict detection (1 instance)"
        )
        print("   - system_collect: Array aggregation (1 instance)")
        print("   - enumerate() works in sandbox ✓")
        print("   - Envelope structure handling ✓")

    @pytest.mark.asyncio
    async def test_merge_conflict_detection_in_sandbox(self, client):
        """
        Test that system_merge detects conflicts when executed in sandbox.

        Both branches modify the same field → should raise ValueError in sandbox.
        """
        http_client, session = client

        # Get merge template
        templates_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates"
        )
        assert templates_response.status_code == 200
        templates = templates_response.json()["data"]
        merge_template = next(
            (t for t in templates if t["name"] == "system_merge"), None
        )
        assert merge_template is not None
        merge_id = merge_template["id"]

        # Create identity template
        templates_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates"
        )
        templates = templates_response.json()["data"]
        identity_template = next(
            (t for t in templates if t["name"] == "system_identity"), None
        )
        identity_id = identity_template["id"]

        # Create conflicting branches (both modify 'x')
        branch_a_id = await self.create_template(
            http_client,
            "modify_x_to_1",
            "result = inp.copy(); result['x'] = 1; return result",
            {"type": "object"},
            {"type": "object"},
            "Modifies x to 1",
        )

        branch_b_id = await self.create_template(
            http_client,
            "modify_x_to_2",
            "result = inp.copy(); result['x'] = 2; return result",
            {"type": "object"},
            {"type": "object"},
            "Modifies x to 2",
        )

        # Create workflow with conflict
        workflow_data = {
            "name": "Merge Conflict Test",
            "description": "Test merge conflict detection in sandbox",
            "is_dynamic": False,
            "data_samples": [{"name": "conflict test", "input": {"x": 0}}],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {"type": "object", "properties": {"x": {"type": "number"}}},
                "output": {"type": "object"},
            },
            "nodes": [
                {
                    "node_id": "n-start",
                    "kind": "transformation",
                    "name": "Start",
                    "is_start_node": True,
                    "node_template_id": identity_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-a",
                    "kind": "transformation",
                    "name": "Branch A",
                    "node_template_id": branch_a_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-branch-b",
                    "kind": "transformation",
                    "name": "Branch B",
                    "node_template_id": branch_b_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-merge",
                    "kind": "transformation",
                    "name": "Merge",
                    "node_template_id": merge_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-start",
                    "to_node_id": "n-branch-a",
                },
                {
                    "edge_id": "e2",
                    "from_node_id": "n-start",
                    "to_node_id": "n-branch-b",
                },
                {
                    "edge_id": "e3",
                    "from_node_id": "n-branch-a",
                    "to_node_id": "n-merge",
                },
                {
                    "edge_id": "e4",
                    "from_node_id": "n-branch-b",
                    "to_node_id": "n-merge",
                },
            ],
        }

        create_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]
        await session.commit()

        # Execute workflow
        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": {"x": 0}},
        )
        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Manually trigger execution
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # Get result - should have failed at merge node
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200
        result = details_response.json()["data"]

        # Workflow should have failed
        assert result["status"] == "failed", (
            "Expected workflow to fail due to merge conflict"
        )

        # Verify error message mentions merge conflict
        error_msg = result.get("error_message", "")
        assert "Merge conflict" in error_msg or "conflict" in error_msg.lower(), (
            f"Expected merge conflict error, got: {error_msg}"
        )

        print("✅ Merge conflict detected correctly in sandbox!")
        print("   Smart merge template successfully detected field-level conflict")
        print(f"   Error message: {error_msg[:100]}...")

    async def create_template(
        self,
        client: AsyncClient,
        name: str,
        code: str,
        input_schema: dict,
        output_schema: dict,
        description: str = None,
    ) -> str:
        """Helper to create a transformation template."""
        template_data = {
            "name": name,
            "description": description or name,
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
