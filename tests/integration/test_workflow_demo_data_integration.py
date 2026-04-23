"""
Integration tests for complete workflow demo data flow.
Tests the entire workflow API lifecycle similar to the demo loading script.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowDemoDataIntegration:
    """Test complete workflow demo data flow via API."""

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
    async def test_complete_workflow_demo_data_flow(self, client: AsyncClient):
        """
        Test the complete workflow demo data flow similar to load_demo_data.py.

        This test covers:
        1. Creating node templates
        2. Creating workflows with template references
        3. Retrieving workflows with enriched data
        4. Validating immutability (PUT returns 405)
        """
        # Step 1: Create node templates (similar to demo script)
        print("Step 1: Creating node templates...")

        # Create passthrough template
        passthrough_template = {
            "name": "test_passthrough",
            "description": "Pass input to output unchanged - test version",
            "input_schema": {"type": "object", "properties": {"data": {}}},
            "output_schema": {"type": "object", "properties": {"data": {}}},
            "code": "return inp",
            "language": "python",
            "type": "static",
        }

        template_response = await client.post(
            "/v1/default/workflows/node-templates", json=passthrough_template
        )
        assert template_response.status_code == 201
        template_data = template_response.json()["data"]
        template_id = template_data["id"]
        assert template_data["name"] == "test_passthrough"
        print(f"✅ Created template: {template_id}")

        # Create pick_field template
        pick_field_template = {
            "name": "test_pick_field",
            "description": "Extract specific field from input - test version",
            "input_schema": {
                "type": "object",
                "properties": {"field_name": {"type": "string"}},
                "required": ["field_name"],
            },
            "output_schema": {"type": "object", "properties": {"picked_value": {}}},
            "code": """field_name = inp.get("field_name", "unknown")
result = inp.get("result", inp) if "result" in inp else inp
return {"picked_value": result.get(field_name) if isinstance(result, dict) else None}""",
            "language": "python",
            "type": "static",
        }

        pick_field_response = await client.post(
            "/v1/default/workflows/node-templates", json=pick_field_template
        )
        assert pick_field_response.status_code == 201
        pick_field_data = pick_field_response.json()["data"]
        pick_field_id = pick_field_data["id"]
        print(f"✅ Created pick_field template: {pick_field_id}")

        # Step 2: List node templates to verify creation
        print("Step 2: Listing node templates...")
        templates_response = await client.get("/v1/default/workflows/node-templates")
        assert templates_response.status_code == 200
        templates_data = templates_response.json()
        assert "data" in templates_data
        assert templates_data["meta"]["total"] >= 2  # At least our 2 test templates
        print(f"✅ Found {templates_data['meta']['total']} templates")

        # Step 3: Create comprehensive workflow (similar to demo)
        print("Step 3: Creating comprehensive workflow...")

        demo_workflow = {
            "name": "Test Security Alert Processing Pipeline",
            "description": "Integration test workflow with multiple transformation nodes",
            "is_dynamic": False,
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                    "required": ["alert"],
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"alert": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "start_node",
                    "kind": "transformation",
                    "name": "Start Processing",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "extract_node",
                    "kind": "transformation",
                    "name": "Extract Alert Data",
                    "node_template_id": pick_field_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "final_node",
                    "kind": "transformation",
                    "name": "Final Processing",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "edge_1",
                    "from_node_id": "start_node",
                    "to_node_id": "extract_node",
                },
                {
                    "edge_id": "edge_2",
                    "from_node_id": "extract_node",
                    "to_node_id": "final_node",
                },
            ],
        }

        workflow_response = await client.post(
            "/v1/default/workflows", json=demo_workflow
        )
        assert workflow_response.status_code == 201
        workflow_data = workflow_response.json()["data"]
        workflow_id = workflow_data["id"]
        assert workflow_data["name"] == "Test Security Alert Processing Pipeline"
        assert len(workflow_data["nodes"]) == 3
        assert len(workflow_data["edges"]) == 2
        print(f"✅ Created workflow: {workflow_id}")

        # Step 4: Retrieve workflow by ID with enriched data
        print("Step 4: Retrieving workflow with enriched data...")

        get_response = await client.get(f"/v1/default/workflows/{workflow_id}")
        assert get_response.status_code == 200
        enriched_workflow = get_response.json()["data"]

        # Verify enriched data includes template information
        assert enriched_workflow["id"] == workflow_id
        assert enriched_workflow["name"] == "Test Security Alert Processing Pipeline"
        assert "nodes" in enriched_workflow
        assert "edges" in enriched_workflow

        # Verify nodes have template references
        nodes = enriched_workflow["nodes"]
        assert len(nodes) == 3

        # Find start node and verify template data
        start_node = next((n for n in nodes if n["node_id"] == "start_node"), None)
        assert start_node is not None
        assert start_node["node_template_id"] == template_id
        assert start_node["kind"] == "transformation"
        print("✅ Verified enriched workflow data")

        # Step 5: List workflows to verify it appears
        print("Step 5: Listing workflows...")

        list_response = await client.get("/v1/default/workflows")
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert "data" in list_data
        assert list_data["meta"]["total"] >= 1

        # Find our workflow in the list
        our_workflow = next(
            (w for w in list_data["data"] if w["id"] == workflow_id), None
        )
        assert our_workflow is not None
        assert our_workflow["name"] == "Test Security Alert Processing Pipeline"
        print("✅ Workflow appears in listing")

        # Step 6: Test PUT validates input (requires full WorkflowCreate schema)
        print("Step 6: Testing workflow PUT validation...")

        put_response = await client.put(
            f"/v1/default/workflows/{workflow_id}", json={"name": "Modified Name"}
        )
        # PUT endpoint exists but requires full WorkflowCreate payload
        assert put_response.status_code == 422
        print("✅ Confirmed workflow PUT validates input (422 for partial payload)")

        # Step 7: Test template immutability - PUT should return 404 (no PUT endpoint exists)
        print("Step 7: Testing template immutability...")

        template_put_response = await client.put(
            f"/v1/default/workflows/node-templates/{template_id}",
            json={"name": "Modified Template"},
        )
        # FastAPI returns 404 when route doesn't exist (no PUT endpoint defined)
        # RFC 9457 Problem Details format — check key fields, ignore request_id
        assert template_put_response.status_code == 404
        error_body = template_put_response.json()
        assert error_body["detail"] == "Not Found"
        assert error_body["status"] == 404
        print("✅ Confirmed template immutability (PUT returns 404)")

        # Step 8: Test template retrieval by ID
        print("Step 8: Testing template retrieval...")

        template_get_response = await client.get(
            f"/v1/default/workflows/node-templates/{template_id}"
        )
        assert template_get_response.status_code == 200
        template_detail = template_get_response.json()["data"]
        assert template_detail["id"] == template_id
        assert template_detail["name"] == "test_passthrough"
        assert template_detail["code"] == "return inp"
        print("✅ Template retrieval working correctly")

        # Step 9: Test workflow deletion (cleanup)
        print("Step 9: Testing workflow deletion...")

        delete_response = await client.delete(f"/v1/default/workflows/{workflow_id}")
        assert delete_response.status_code == 204

        # Verify workflow is gone
        get_deleted_response = await client.get(f"/v1/default/workflows/{workflow_id}")
        assert get_deleted_response.status_code == 404
        print("✅ Workflow deletion working correctly")

        # Step 10: Clean up templates
        print("Step 10: Cleaning up templates...")

        await client.delete(f"/v1/default/workflows/node-templates/{template_id}")
        await client.delete(f"/v1/default/workflows/node-templates/{pick_field_id}")
        print("✅ Templates cleaned up")

        print("🎉 Complete workflow demo data integration test passed!")

    @pytest.mark.asyncio
    async def test_workflow_dag_validation(self, client: AsyncClient):
        """Test that workflow creation validates DAG structure."""
        # Create a simple template first
        template = {
            "name": "dag_test_template",
            "description": "Template for DAG validation testing",
            "input_schema": {"type": "object", "properties": {"data": {}}},
            "output_schema": {"type": "object", "properties": {"data": {}}},
            "code": "return inp",
            "language": "python",
            "type": "static",
        }

        template_response = await client.post(
            "/v1/default/workflows/node-templates", json=template
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        # Try to create workflow with cycle (should fail)
        cyclic_workflow = {
            "name": "Cyclic Workflow Test",
            "description": "This should fail due to cycle",
            "is_dynamic": False,
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "node_a",
                    "kind": "transformation",
                    "name": "Node A",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
                {
                    "node_id": "node_b",
                    "kind": "transformation",
                    "name": "Node B",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                },
            ],
            "edges": [
                {"edge_id": "edge_1", "from_node_id": "node_a", "to_node_id": "node_b"},
                {
                    "edge_id": "edge_2",
                    "from_node_id": "node_b",
                    "to_node_id": "node_a",  # Creates cycle!
                },
            ],
        }

        cycle_response = await client.post(
            "/v1/default/workflows?validate=true", json=cyclic_workflow
        )
        # Should fail with validation error (router returns generic error per security conventions)
        assert cycle_response.status_code == 400
        assert cycle_response.json()["detail"]

        # Clean up
        await client.delete(f"/v1/default/workflows/node-templates/{template_id}")

    @pytest.mark.asyncio
    async def test_workflow_with_invalid_template_reference(self, client: AsyncClient):
        """Test workflow creation fails with invalid template reference."""
        invalid_workflow = {
            "name": "Invalid Template Reference",
            "description": "This should fail due to invalid template ID",
            "is_dynamic": False,
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "invalid_node",
                    "kind": "transformation",
                    "name": "Invalid Node",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000000",  # Non-existent
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output_envelope": {
                            "type": "object",
                            "properties": {"data": {}},
                        },
                        "output_result": {"type": "object", "properties": {"data": {}}},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.post(
            "/v1/default/workflows?validate=true", json=invalid_workflow
        )
        assert response.status_code == 400
        # Router returns generic error per security conventions
        assert response.json()["detail"]
