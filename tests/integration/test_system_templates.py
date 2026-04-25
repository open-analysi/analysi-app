"""
Integration tests for system-provided NodeTemplates.

Tests default NodeTemplates that are seeded at database initialization.
Verifies that Identity, Merge, and Collect templates are accessible and functional.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.constants import TemplateConstants
from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.workflow import NodeTemplateRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestSystemTemplates:
    """Test system-provided NodeTemplates."""

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
    async def test_system_templates_exist_in_database(self, integration_test_session):
        """
        Test 1.1: Verify all 3 system templates exist in database after migration.

        Given: Fresh database with migrations applied
        When: Query NodeTemplateRepository for system template UUIDs
        Then: All 3 templates exist with correct properties
        """
        repo = NodeTemplateRepository(integration_test_session)

        # Get each system template
        identity = await repo.get_template_by_id(
            TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        )
        merge = await repo.get_template_by_id(
            TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID
        )
        collect = await repo.get_template_by_id(
            TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID
        )

        # All should exist
        assert identity is not None, "Identity template not found in database"
        assert merge is not None, "Merge template not found in database"
        assert collect is not None, "Collect template not found in database"

        # Verify Identity template properties
        assert identity.id == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        assert identity.name == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_NAME
        assert identity.kind == "identity"
        assert identity.tenant_id is None  # System template (tenant-agnostic)
        assert identity.enabled is True

        # Verify Merge template properties
        assert merge.id == TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID
        assert merge.name == TemplateConstants.SYSTEM_MERGE_TEMPLATE_NAME
        assert merge.kind == "merge"
        assert merge.tenant_id is None
        assert merge.enabled is True

        # Verify Collect template properties
        assert collect.id == TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID
        assert collect.name == TemplateConstants.SYSTEM_COLLECT_TEMPLATE_NAME
        assert collect.kind == "collect"
        assert collect.tenant_id is None
        assert collect.enabled is True

    @pytest.mark.asyncio
    async def test_system_templates_accessible_via_service(
        self, integration_test_session
    ):
        """
        Test 1.2: Verify system templates can be fetched via service layer.

        Given: System templates exist in database
        When: Call NodeTemplateService.get_template() for each template
        Then: Response contains correct template data for any tenant
        """
        from analysi.services.workflow import NodeTemplateService

        service = NodeTemplateService(integration_test_session)

        # Test Identity template
        identity = await service.get_template(
            TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        )
        assert identity is not None
        assert identity.id == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        assert identity.name == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_NAME
        assert identity.kind == "identity"
        assert identity.enabled is True

        # Test Merge template
        merge = await service.get_template(TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID)
        assert merge is not None
        assert merge.id == TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID
        assert merge.name == TemplateConstants.SYSTEM_MERGE_TEMPLATE_NAME
        assert merge.kind == "merge"
        assert merge.enabled is True

        # Test Collect template
        collect = await service.get_template(
            TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID
        )
        assert collect is not None
        assert collect.id == TemplateConstants.SYSTEM_COLLECT_TEMPLATE_ID
        assert collect.name == TemplateConstants.SYSTEM_COLLECT_TEMPLATE_NAME
        assert collect.kind == "collect"
        assert collect.enabled is True

    @pytest.mark.asyncio
    async def test_system_templates_in_list_endpoint(self, client: AsyncClient):
        """
        Test 1.3: Verify system templates appear in list endpoint.

        Given: System templates exist
        When: GET /v1/{tenant_id}/workflows/node-templates
        Then: Response includes all 3 system templates
        """
        response = await client.get("/v1/test_tenant/workflows/node-templates")

        assert response.status_code == 200
        data = response.json()

        # Extract template names from response
        templates = data["data"]
        template_names = {t["name"] for t in templates}

        # Verify all system templates are present
        assert TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_NAME in template_names
        assert TemplateConstants.SYSTEM_MERGE_TEMPLATE_NAME in template_names
        assert TemplateConstants.SYSTEM_COLLECT_TEMPLATE_NAME in template_names

        # Verify system templates have correct properties
        identity_template = next(
            t
            for t in templates
            if t["name"] == TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_NAME
        )
        assert identity_template["kind"] == "identity"
        assert identity_template["enabled"] is True

        # Also verify merge and collect templates have correct kinds
        merge_template = next(
            t
            for t in templates
            if t["name"] == TemplateConstants.SYSTEM_MERGE_TEMPLATE_NAME
        )
        assert merge_template["kind"] == "merge", (
            f"Merge template has wrong kind: {merge_template['kind']}"
        )

        collect_template = next(
            t
            for t in templates
            if t["name"] == TemplateConstants.SYSTEM_COLLECT_TEMPLATE_NAME
        )
        assert collect_template["kind"] == "collect", (
            f"Collect template has wrong kind: {collect_template['kind']}"
        )

    @pytest.mark.asyncio
    async def test_workflow_can_use_system_templates(self, client: AsyncClient):
        """
        Test 1.4: Verify workflows can reference system template UUIDs.

        Given: System templates exist
        When: Create workflow with node referencing SYSTEM_IDENTITY_TEMPLATE_ID
        Then: Workflow creation succeeds and references system template
        """
        workflow_config = {
            "name": "Test Workflow with System Template",
            "description": "Uses system identity template",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n1",
                    "kind": "transformation",
                    "name": "Identity Node",
                    "is_start_node": True,
                    "node_template_id": str(
                        TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
                    ),
                    "schemas": {
                        "input": {"type": "object", "properties": {"data": {}}},
                        "output": {"type": "object", "properties": {"data": {}}},
                    },
                }
            ],
            "edges": [],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_config)
        assert response.status_code == 201

        # Verify node references system template
        created = response.json()["data"]
        assert created["nodes"][0]["node_template_id"] == str(
            TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
        )

    @pytest.mark.asyncio
    async def test_type_validation_with_system_templates(self, client: AsyncClient):
        """
        Test 1.5: Verify type validation works with system templates.

        Given: Workflow using system identity and merge templates
        When: POST /workflows/{id}/validate-types
        Then: Validation succeeds with correct type inference
        """
        # Create workflow with identity template
        workflow_config = {
            "name": "Type Validation Test Workflow",
            "description": "Tests type validation with system templates",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {}}},
                "output": {"type": "object", "properties": {"data": {}}},
            },
            "data_samples": [{"data": {}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "identity-node",
                    "kind": "transformation",
                    "name": "Identity Passthrough",
                    "is_start_node": True,
                    "node_template_id": str(
                        TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID
                    ),
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
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate types
        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={
                "initial_input_schema": {
                    "type": "object",
                    "properties": {"test_field": {"type": "string"}},
                }
            },
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Workflow should be valid
        assert data["status"] in ["valid", "valid_with_warnings"]

        # Verify node type info includes identity node
        assert len(data["nodes"]) == 1
        identity_node = data["nodes"][0]
        assert identity_node["node_id"] == "identity-node"
        assert identity_node["kind"] == "transformation"
        assert identity_node["template_kind"] == "identity"
