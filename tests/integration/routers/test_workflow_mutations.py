"""
Integration tests for workflow mutation REST API endpoints.

Tests end-to-end REST API with real database. All tests follow TDD principles
and should FAIL initially with 501 status code since endpoints are stubbed.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowMutationAPI:
    """Test workflow mutation API endpoints."""

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
    async def template_id(self, client: AsyncClient) -> str:
        """Create a test template for workflow nodes."""
        template_data = {
            "name": f"test_mutation_template_{uuid4().hex[:8]}",
            "type": "static",
            "description": "Template for mutation testing",
            "code": "return inp",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }

        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Template creation failed: {response.json()}"
        )
        return response.json()["data"]["id"]

    @pytest.fixture
    def valid_io_schema(self) -> dict:
        """Return a valid io_schema for workflow creation."""
        return {
            "input": {
                "type": "object",
                "properties": {"data": {"type": "string"}},
                "required": ["data"],
            },
            "output": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        }

    @pytest.fixture
    async def empty_workflow_id(
        self, client: AsyncClient, template_id: str, valid_io_schema: dict
    ) -> str:
        """Create a minimal workflow (one node, no edges) for mutation testing."""
        workflow_data = {
            "name": f"Mutable Test Workflow {uuid4().hex[:8]}",
            "description": "Test workflow for mutation operations",
            "io_schema": valid_io_schema,
            "data_samples": [{"data": "test"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-initial",
                    "kind": "transformation",
                    "name": "Initial Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert response.status_code == 201, f"Failed: {response.json()}"
        return response.json()["data"]["id"]

    @pytest.fixture
    async def workflow_with_nodes(
        self, client: AsyncClient, template_id: str, valid_io_schema: dict
    ) -> str:
        """Create a workflow with two nodes for edge testing."""
        workflow_data = {
            "name": f"Two Node Workflow {uuid4().hex[:8]}",
            "description": "Workflow with nodes for edge testing",
            "io_schema": valid_io_schema,
            "data_samples": [{"data": "test"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-1",
                    "kind": "transformation",
                    "name": "Node 1",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-2",
                    "kind": "transformation",
                    "name": "Node 2",
                    "is_start_node": False,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e-1",
                    "from_node_id": "n-1",
                    "to_node_id": "n-2",
                }
            ],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert response.status_code == 201, f"Failed: {response.json()}"
        return response.json()["data"]["id"]

    # ========== PATCH Workflow Metadata ==========

    @pytest.mark.asyncio
    async def test_patch_workflow_name(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test PATCH updates workflow name and returns 200."""
        response = await client.patch(
            f"/v1/test_tenant/workflows/{empty_workflow_id}",
            json={"name": "Updated Workflow Name"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Workflow Name"

    @pytest.mark.asyncio
    async def test_patch_workflow_description(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test PATCH updates workflow description."""
        response = await client.patch(
            f"/v1/test_tenant/workflows/{empty_workflow_id}",
            json={"description": "New description"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] == "New description"

    @pytest.mark.asyncio
    async def test_patch_workflow_not_found(self, client: AsyncClient):
        """Test PATCH non-existent workflow returns 404."""
        fake_id = str(uuid4())
        response = await client.patch(
            f"/v1/test_tenant/workflows/{fake_id}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_workflow_wrong_tenant(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test PATCH cross-tenant returns 404."""
        response = await client.patch(
            f"/v1/other_tenant/workflows/{empty_workflow_id}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404

    # ========== POST Node (Add) ==========

    @pytest.mark.asyncio
    async def test_add_node_success(
        self, client: AsyncClient, empty_workflow_id: str, template_id: str
    ):
        """Test POST node returns 201 with node data."""
        unique_node_id = f"n-new-{uuid4().hex[:8]}"
        node_data = {
            "node_id": unique_node_id,
            "kind": "transformation",
            "name": "New Node",
            "is_start_node": False,  # Fixture already has start node
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/nodes",
            json=node_data,
        )

        assert response.status_code == 201, f"Unexpected error: {response.json()}"
        data = response.json()["data"]
        assert data["node_id"] == unique_node_id
        assert data["name"] == "New Node"

    @pytest.mark.asyncio
    async def test_add_node_with_task_id(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test POST node referencing a task returns 400 for invalid task_id."""
        # Note: task_id must be valid, so random UUID will fail FK constraint
        unique_node_id = f"n-task-{uuid4().hex[:8]}"
        node_data = {
            "node_id": unique_node_id,
            "kind": "task",
            "name": "Task Node",
            "is_start_node": False,
            "task_id": str(uuid4()),  # Invalid task ID
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/nodes",
            json=node_data,
        )

        # Invalid task_id returns 409 due to FK constraint violation
        assert response.status_code in [400, 409], f"Unexpected: {response.json()}"

    @pytest.mark.asyncio
    async def test_add_node_duplicate_node_id(
        self, client: AsyncClient, workflow_with_nodes: str, template_id: str
    ):
        """Test POST duplicate node_id returns 409 Conflict."""
        node_data = {
            "node_id": "n-1",  # Already exists
            "kind": "transformation",
            "name": "Duplicate Node",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes",
            json=node_data,
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_add_node_workflow_not_found(
        self, client: AsyncClient, template_id: str
    ):
        """Test POST to non-existent workflow returns 404."""
        fake_id = str(uuid4())
        node_data = {
            "node_id": "n-1",
            "kind": "transformation",
            "name": "Test Node",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{fake_id}/nodes",
            json=node_data,
        )

        assert response.status_code == 404

    # ========== PATCH Node (Update) ==========

    @pytest.mark.asyncio
    async def test_update_node_success(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test PATCH node returns 200."""
        response = await client.patch(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes/n-1",
            json={"name": "Updated Node Name"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Node Name"

    @pytest.mark.asyncio
    async def test_update_node_not_found(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test PATCH non-existent node returns 404."""
        response = await client.patch(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes/nonexistent",
            json={"name": "New Name"},
        )

        assert response.status_code == 404

    # ========== DELETE Node ==========

    @pytest.mark.asyncio
    async def test_delete_node_success(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test DELETE node returns 204."""
        response = await client.delete(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes/n-2"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_node_cascades_edges(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test DELETE node removes connected edges."""
        # Delete node n-1 which has edge e-1 connected
        response = await client.delete(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes/n-1"
        )
        assert response.status_code == 204

        # Verify workflow no longer has the edge
        get_response = await client.get(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}"
        )
        assert get_response.status_code == 200
        workflow = get_response.json()["data"]

        # Edge e-1 should be gone
        edge_ids = [e["edge_id"] for e in workflow.get("edges", [])]
        assert "e-1" not in edge_ids

    @pytest.mark.asyncio
    async def test_delete_node_not_found(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test DELETE non-existent node returns 404."""
        response = await client.delete(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes/nonexistent"
        )

        assert response.status_code == 404

    # ========== POST Edge (Add) ==========

    @pytest.mark.asyncio
    async def test_add_edge_success(
        self, client: AsyncClient, empty_workflow_id: str, template_id: str
    ):
        """Test POST edge returns 201."""
        # First add two nodes
        for i, node_id in enumerate(["n-a", "n-b"]):
            node_data = {
                "node_id": node_id,
                "kind": "transformation",
                "name": f"Node {node_id}",
                "is_start_node": (i == 0),
                "node_template_id": template_id,
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            }
            resp = await client.post(
                f"/v1/test_tenant/workflows/{empty_workflow_id}/nodes",
                json=node_data,
            )
            assert resp.status_code == 201

        # Now add edge
        edge_data = {
            "edge_id": "e-new",
            "from_node_id": "n-a",
            "to_node_id": "n-b",
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/edges",
            json=edge_data,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["edge_id"] == "e-new"

    @pytest.mark.asyncio
    async def test_add_edge_invalid_from_node(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test POST edge with bad from_node returns 400."""
        edge_data = {
            "edge_id": "e-bad",
            "from_node_id": "nonexistent",
            "to_node_id": "n-1",
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/edges",
            json=edge_data,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_add_edge_invalid_to_node(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test POST edge with bad to_node returns 400."""
        edge_data = {
            "edge_id": "e-bad",
            "from_node_id": "n-1",
            "to_node_id": "nonexistent",
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/edges",
            json=edge_data,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_add_edge_duplicate_edge_id(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test POST duplicate edge_id returns 409."""
        edge_data = {
            "edge_id": "e-1",  # Already exists
            "from_node_id": "n-1",
            "to_node_id": "n-2",
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/edges",
            json=edge_data,
        )

        assert response.status_code == 409

    # ========== DELETE Edge ==========

    @pytest.mark.asyncio
    async def test_delete_edge_success(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test DELETE edge returns 204."""
        response = await client.delete(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/edges/e-1"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_edge_not_found(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test DELETE non-existent edge returns 404."""
        response = await client.delete(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/edges/nonexistent"
        )

        assert response.status_code == 404

    # ========== POST Validate (On-demand) ==========

    @pytest.mark.asyncio
    async def test_validate_complete_workflow(
        self, client: AsyncClient, workflow_with_nodes: str
    ):
        """Test validating complete workflow returns valid=True."""
        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/validate"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["valid"] is True
        assert data["workflow_status"] == "validated"

    @pytest.mark.asyncio
    async def test_validate_incomplete_workflow(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test validating incomplete workflow is allowed (warnings only)."""
        # empty_workflow_id already has one node - just validate it
        # (incomplete because it has no edges to other nodes)

        response = await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/validate"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # Incomplete workflows may have warnings but shouldn't error
        assert "warnings" in data

    @pytest.mark.asyncio
    async def test_validate_workflow_with_cycle(
        self, client: AsyncClient, empty_workflow_id: str, template_id: str
    ):
        """Test validating workflow with cycle returns valid=False."""
        # empty_workflow_id already has n-initial node, add n-b
        node_data = {
            "node_id": "n-b",
            "kind": "transformation",
            "name": "Node B",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }
        await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/nodes",
            json=node_data,
        )

        # Create cycle: n-initial -> n-b -> n-initial
        for edge in [
            {"edge_id": "e-1", "from_node_id": "n-initial", "to_node_id": "n-b"},
            {"edge_id": "e-2", "from_node_id": "n-b", "to_node_id": "n-initial"},
        ]:
            await client.post(
                f"/v1/test_tenant/workflows/{empty_workflow_id}/edges",
                json=edge,
            )

        response = await client.post(
            f"/v1/test_tenant/workflows/{empty_workflow_id}/validate"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["valid"] is False
        assert len(data["dag_errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_workflow_not_found(self, client: AsyncClient):
        """Test validating non-existent workflow returns 404."""
        fake_id = str(uuid4())
        response = await client.post(f"/v1/test_tenant/workflows/{fake_id}/validate")

        assert response.status_code == 404

    # ========== End-to-End Mutation Flow ==========

    @pytest.mark.asyncio
    async def test_build_workflow_incrementally(
        self, client: AsyncClient, template_id: str, valid_io_schema: dict
    ):
        """Test building a complete workflow through incremental mutations."""
        # Create minimal workflow (required: at least 1 node)
        workflow_data = {
            "name": f"Incremental Build {uuid4().hex[:8]}",
            "io_schema": valid_io_schema,
            "data_samples": [{"data": "test"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-start",
                    "kind": "transformation",
                    "name": "Start Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        create_resp = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert create_resp.status_code == 201, f"Failed: {create_resp.json()}"
        workflow_id = create_resp.json()["data"]["id"]

        # Add more nodes via mutation
        for i, node_id in enumerate(["n-middle", "n-end"]):
            node_data = {
                "node_id": node_id,
                "kind": "transformation",
                "name": f"Node {i + 2}",
                "is_start_node": False,
                "node_template_id": template_id,
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            }
            resp = await client.post(
                f"/v1/test_tenant/workflows/{workflow_id}/nodes",
                json=node_data,
            )
            assert resp.status_code == 201

        # Add edges
        for edge in [
            {"edge_id": "e-1", "from_node_id": "n-start", "to_node_id": "n-middle"},
            {"edge_id": "e-2", "from_node_id": "n-middle", "to_node_id": "n-end"},
        ]:
            resp = await client.post(
                f"/v1/test_tenant/workflows/{workflow_id}/edges",
                json=edge,
            )
            assert resp.status_code == 201

        # Validate
        validate_resp = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate"
        )
        assert validate_resp.status_code == 200
        assert validate_resp.json()["data"]["valid"] is True

    @pytest.mark.asyncio
    async def test_modify_existing_workflow(
        self, client: AsyncClient, workflow_with_nodes: str, template_id: str
    ):
        """Test modifying an already validated workflow."""
        # First validate
        await client.post(f"/v1/test_tenant/workflows/{workflow_with_nodes}/validate")

        # Now modify - add another node
        node_data = {
            "node_id": "n-3",
            "kind": "transformation",
            "name": "Node 3",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        resp = await client.post(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}/nodes",
            json=node_data,
        )

        # Should still be able to add nodes even after validation
        assert resp.status_code == 201

    # ========== Tenant Isolation ==========

    @pytest.mark.asyncio
    async def test_mutations_tenant_isolated(
        self, client: AsyncClient, empty_workflow_id: str
    ):
        """Test that mutation operations are scoped to tenant."""
        # Try to access from different tenant
        response = await client.patch(
            f"/v1/other_tenant/workflows/{empty_workflow_id}",
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 404

    # ========== Validation Flag Tests ==========

    @pytest.mark.asyncio
    async def test_create_workflow_validation_disabled_by_default(
        self, client: AsyncClient, template_id: str
    ):
        """Test that validation is disabled by default on workflow creation."""
        # Create workflow with missing data_samples (would fail validation)
        workflow_data = {
            "name": f"no_validation_workflow_{uuid4().hex[:8]}",
            "io_schema": {
                "input": {
                    "type": "object"
                },  # Missing properties - would fail validation
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            # Missing data_samples - would fail validation
            "nodes": [
                {
                    "node_id": "n-1",
                    "kind": "transformation",
                    "name": "Test Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        # Should succeed without validation
        response = await client.post(
            "/v1/test_tenant/workflows",
            json=workflow_data,
        )

        assert response.status_code == 201, f"Creation failed: {response.json()}"
        assert "id" in response.json()["data"]

    @pytest.mark.asyncio
    async def test_create_workflow_with_validation_enabled(
        self, client: AsyncClient, template_id: str
    ):
        """Test that validation runs when validate=true is passed."""
        # Create workflow with missing data_samples (would fail validation)
        workflow_data = {
            "name": f"validated_workflow_{uuid4().hex[:8]}",
            "io_schema": {
                "input": {"type": "object"},  # Missing properties - fails validation
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            # Missing data_samples - fails validation
            "nodes": [
                {
                    "node_id": "n-1",
                    "kind": "transformation",
                    "name": "Test Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        # Should fail with validation enabled
        response = await client.post(
            "/v1/test_tenant/workflows?validate=true",
            json=workflow_data,
        )

        assert response.status_code == 400, (
            f"Expected validation error, got: {response.json()}"
        )
        # Router returns a generic error message per security conventions
        assert response.json().get("detail")

    # ========== PUT Workflow (Full Replace) ==========

    @pytest.mark.asyncio
    async def test_put_workflow_replaces_all_nodes(
        self,
        client: AsyncClient,
        workflow_with_nodes: str,
        template_id: str,
        valid_io_schema: dict,
    ):
        """Test PUT replaces all existing nodes with new ones."""
        # workflow_with_nodes has n-1 and n-2 with edge e-1
        # Replace with completely different structure
        new_workflow_data = {
            "name": "Replaced Workflow",
            "description": "Completely new structure",
            "io_schema": valid_io_schema,
            "data_samples": [{"data": "new test"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-new-1",
                    "kind": "transformation",
                    "name": "New Node 1",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-new-2",
                    "kind": "transformation",
                    "name": "New Node 2",
                    "is_start_node": False,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-new-3",
                    "kind": "transformation",
                    "name": "New Node 3",
                    "is_start_node": False,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e-new-1",
                    "from_node_id": "n-new-1",
                    "to_node_id": "n-new-2",
                },
                {
                    "edge_id": "e-new-2",
                    "from_node_id": "n-new-2",
                    "to_node_id": "n-new-3",
                },
            ],
        }

        response = await client.put(
            f"/v1/test_tenant/workflows/{workflow_with_nodes}",
            json=new_workflow_data,
        )

        assert response.status_code == 200, f"Replace failed: {response.json()}"
        data = response.json()["data"]

        # Verify workflow ID is preserved
        assert data["id"] == workflow_with_nodes

        # Verify new metadata
        assert data["name"] == "Replaced Workflow"
        assert data["description"] == "Completely new structure"

        # Verify new nodes (old nodes should be gone)
        node_ids = [n["node_id"] for n in data["nodes"]]
        assert "n-new-1" in node_ids
        assert "n-new-2" in node_ids
        assert "n-new-3" in node_ids
        assert "n-1" not in node_ids  # Old node gone
        assert "n-2" not in node_ids  # Old node gone
        assert len(data["nodes"]) == 3

        # Verify new edges
        edge_ids = [e["edge_id"] for e in data["edges"]]
        assert "e-new-1" in edge_ids
        assert "e-new-2" in edge_ids
        assert "e-1" not in edge_ids  # Old edge gone
        assert len(data["edges"]) == 2

    @pytest.mark.asyncio
    async def test_put_workflow_preserves_id(
        self,
        client: AsyncClient,
        empty_workflow_id: str,
        template_id: str,
        valid_io_schema: dict,
    ):
        """Test PUT preserves the workflow ID."""
        new_data = {
            "name": "ID Preserved",
            "io_schema": valid_io_schema,
            "data_samples": [],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-single",
                    "kind": "transformation",
                    "name": "Single Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.put(
            f"/v1/test_tenant/workflows/{empty_workflow_id}",
            json=new_data,
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == empty_workflow_id

    @pytest.mark.asyncio
    async def test_put_workflow_not_found(
        self, client: AsyncClient, template_id: str, valid_io_schema: dict
    ):
        """Test PUT to non-existent workflow returns 404."""
        fake_id = str(uuid4())
        new_data = {
            "name": "Not Found",
            "io_schema": valid_io_schema,
            "data_samples": [],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-1",
                    "kind": "transformation",
                    "name": "Test Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.put(
            f"/v1/test_tenant/workflows/{fake_id}",
            json=new_data,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_put_workflow_wrong_tenant(
        self,
        client: AsyncClient,
        empty_workflow_id: str,
        template_id: str,
        valid_io_schema: dict,
    ):
        """Test PUT cross-tenant returns 404."""
        new_data = {
            "name": "Cross Tenant",
            "io_schema": valid_io_schema,
            "data_samples": [],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-1",
                    "kind": "transformation",
                    "name": "Test Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.put(
            f"/v1/other_tenant/workflows/{empty_workflow_id}",
            json=new_data,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_put_workflow_updates_metadata(
        self, client: AsyncClient, empty_workflow_id: str, template_id: str
    ):
        """Test PUT updates workflow metadata along with nodes."""
        new_data = {
            "name": "Updated Name via PUT",
            "description": "Updated description via PUT",
            "io_schema": {"input": {"type": "object"}, "output": {"type": "object"}},
            "data_samples": [{"key": "new_value"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-updated",
                    "kind": "transformation",
                    "name": "Updated Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.put(
            f"/v1/test_tenant/workflows/{empty_workflow_id}",
            json=new_data,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Name via PUT"
        assert data["description"] == "Updated description via PUT"
        assert data["data_samples"] == [{"key": "new_value"}]
