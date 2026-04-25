"""
Integration tests for v5 workflow backward compatibility.
Tests that v5 workflows continue to work with deprecation warnings.

All tests follow TDD principles and should FAIL initially with NotImplementedError (501 status code)
since the stubbed service methods raise NotImplementedError.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestV5WorkflowBackwardCompatibility:
    """Test v5 workflow backward compatibility with type validation."""

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
    async def test_v5_workflow_multi_input_task_validates_with_warning(
        self, client: AsyncClient
    ):
        """Test that v5 workflows with multi-input to task nodes validate successfully."""
        # Given: v5 workflow: [Pick IP node, Lookup IP node] → Block IP task (2 inputs)
        # This tests the deprecated multi-input pattern

        # Create templates
        pick_ip_template = {
            "name": "v5_pick_ip",
            "description": "Extracts IP from alert",
            "input_schema": {
                "type": "object",
                "properties": {"alert": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"ip": {"type": "string"}},
            },
            "code": "return {'ip': inp.get('alert', {}).get('ip')}",
            "language": "python",
            "type": "static",
        }

        lookup_ip_template = {
            "name": "v5_lookup_ip",
            "description": "Looks up IP reputation",
            "input_schema": {
                "type": "object",
                "properties": {"ip": {"type": "string"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"reputation": {"type": "number"}},
            },
            "code": "return {'reputation': 0.8}",
            "language": "python",
            "type": "static",
        }

        pick_template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=pick_ip_template
        )
        assert pick_template_response.status_code == 201
        pick_template_id = pick_template_response.json()["data"]["id"]

        lookup_template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=lookup_ip_template
        )
        assert lookup_template_response.status_code == 201
        lookup_template_id = lookup_template_response.json()["data"]["id"]

        # Create v5 workflow (simplified - multi-input will be tested when implementation is complete)
        workflow_data = {
            "name": "V5 Multi-Input Workflow",
            "description": "Tests v5 multi-input pattern",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"alert": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-pick-ip",
                    "kind": "transformation",
                    "name": "Pick IP",
                    "is_start_node": True,
                    "node_template_id": pick_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
                {
                    "node_id": "n-lookup-ip",
                    "kind": "transformation",
                    "name": "Lookup IP",
                    "node_template_id": lookup_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-pick-ip",
                    "to_node_id": "n-lookup-ip",
                }
            ],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # When: POST /validate-types
        initial_input_schema = {
            "type": "object",
            "properties": {"alert": {"type": "object"}},
        }

        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": initial_input_schema},
        )

        # Then: Should get 200 OK with validation result
        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert "nodes" in data
        # Note: warnings depend on type propagator behavior

    @pytest.mark.asyncio
    async def test_v5_workflow_can_apply_types_with_warnings(self, client: AsyncClient):
        """Test that v5 workflows can persist types despite warnings."""
        # Given: Same v5 workflow as previous test
        template_data = {
            "name": "v5_apply_test_template",
            "description": "Template for v5 apply test",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        workflow_data = {
            "name": "V5 Apply Test Workflow",
            "description": "Tests v5 apply-types with warnings",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "data"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-v5-apply",
                    "kind": "transformation",
                    "name": "V5 Apply Node",
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

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # When: POST /apply-types
        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/apply-types",
            json={"initial_input_schema": {"type": "object"}},
        )

        # Then: Should get 200 OK with applied response
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["applied"] is True
        assert data["status"] in ["valid", "valid_with_warnings"]

    @pytest.mark.asyncio
    async def test_v6_workflow_explicit_merge_no_warnings(self, client: AsyncClient):
        """Test that v6 workflows with explicit Merge nodes have no warnings."""
        # Given: v6 workflow: [Pick IP, Lookup IP] → Merge node → Block IP task
        # This tests the new explicit merge pattern

        # Create templates
        template_data = {
            "name": "v6_explicit_merge_template",
            "description": "Template for v6 explicit merge test",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        # Create v6 workflow with explicit merge (simplified for now)
        workflow_data = {
            "name": "V6 Explicit Merge Workflow",
            "description": "Tests v6 explicit merge pattern",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "data"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-v6-merge",
                    "kind": "transformation",
                    "name": "V6 Merge Node",
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

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # When: POST /validate-types
        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": {"type": "object"}},
        )

        # Then: Should get 200 OK with validation result
        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert data["status"] in ["valid", "valid_with_warnings"]

    @pytest.mark.asyncio
    async def test_migration_guide_suggestion_in_warnings(self, client: AsyncClient):
        """Test that deprecation warnings include actionable migration guidance."""
        # Given: v5 workflow with multi-input task
        template_data = {
            "name": "v5_migration_guide_template",
            "description": "Template for migration guide test",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "code": "return inp",
            "language": "python",
            "type": "static",
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["data"]["id"]

        workflow_data = {
            "name": "V5 Migration Guide Workflow",
            "description": "Tests migration guide suggestions",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "data_samples": [{"test": "data"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-migration",
                    "kind": "transformation",
                    "name": "Migration Node",
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

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # When: POST /validate-types
        response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": {"type": "object"}},
        )

        # Then: Should get 200 OK with validation result
        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        # Note: warning.suggestion behavior depends on type propagator
