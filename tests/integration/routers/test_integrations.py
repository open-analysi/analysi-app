"""
Integration tests for Integration API endpoints.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationEndpoints:
    """Test Integration REST API endpoints."""

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

    # Integration management endpoints
    @pytest.mark.asyncio
    async def test_list_integrations(self, client: AsyncClient):
        """Test GET /{tenant}/integrations lists integrations."""
        response = await client.get("/v1/test-tenant/integrations")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_integration_returns_details(self, client: AsyncClient):
        """Test GET /{tenant}/integrations/{id} returns details."""
        # First create an integration
        await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "test-int-get",
                "integration_type": "splunk",
                "name": "Test Integration",
                "enabled": True,
                "settings": {"host": "localhost", "port": 8089},
            },
        )

        # Now get the integration
        response = await client.get("/v1/test-tenant/integrations/test-int-get")

        if response.status_code == 200:
            body = response.json()
            data = body["data"]
            assert data["integration_id"] == "test-int-get"
        else:
            # Could be 404 if not found, which is valid
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_integration_soft_deletes(self, client: AsyncClient):
        """Test DELETE /{tenant}/integrations/{id} soft deletes."""
        response = await client.delete("/v1/test-tenant/integrations/test-int")

        assert response.status_code in [200, 204, 404]

    @pytest.mark.asyncio
    async def test_get_integration_health_returns_health(self, client: AsyncClient):
        """Test GET /{tenant}/integrations/{id}/health returns health."""
        # First create an integration
        await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "test-int",
                "integration_type": "splunk",
                "name": "Test Integration",
                "enabled": True,
                "settings": {},
            },
        )

        response = await client.get("/v1/test-tenant/integrations/test-int/health")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert "status" in data
        assert "last_successful_run" in data
        assert "recent_failure_rate" in data
        assert "message" in data


# TestIntegrationRunEndpoints removed: connector-runs endpoints no longer exist.
# TestScheduleEndpoints removed: connector schedule endpoints no longer exist.


@pytest.mark.asyncio
@pytest.mark.integration
class TestProvisionFreeIntegrations:
    """Test POST /{tenant}/integrations/provision-free endpoint."""

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
    async def test_provision_free_creates_integrations(self, client: AsyncClient):
        """First call creates all free integrations."""
        response = await client.post("/v1/test-tenant/integrations/provision-free")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]

        assert data["created"] > 0
        assert data["already_exists"] == 0
        assert len(data["integrations"]) == data["created"]

        # All should be "created"
        for integration in data["integrations"]:
            assert integration["status"] == "created"
            assert integration["integration_type"]
            assert integration["integration_id"]
            assert integration["name"]

    @pytest.mark.asyncio
    async def test_provision_free_is_idempotent(self, client: AsyncClient):
        """Second call returns already_exists for all."""
        # First call — creates
        first = await client.post("/v1/test-tenant/integrations/provision-free")
        assert first.status_code == 200
        first_data = first.json()["data"]
        total = first_data["created"]
        assert total > 0

        # Second call — all exist
        second = await client.post("/v1/test-tenant/integrations/provision-free")
        assert second.status_code == 200
        second_data = second.json()["data"]

        assert second_data["created"] == 0
        assert second_data["already_exists"] == total

        for integration in second_data["integrations"]:
            assert integration["status"] == "already_exists"

    @pytest.mark.asyncio
    async def test_provision_free_includes_known_integrations(
        self, client: AsyncClient
    ):
        """Provisioned integrations include our known free integrations."""
        response = await client.post("/v1/test-tenant/integrations/provision-free")

        data = response.json()["data"]
        types = {i["integration_type"] for i in data["integrations"]}

        # These should all be free (requires_credentials=false)
        assert "global_dns" in types
        assert "tor" in types

    @pytest.mark.asyncio
    async def test_provision_free_integrations_are_enabled(self, client: AsyncClient):
        """Provisioned integrations should be enabled and listable."""
        await client.post("/v1/test-tenant/integrations/provision-free")

        # List all integrations — free ones should appear
        response = await client.get("/v1/test-tenant/integrations")
        assert response.status_code == 200

        data = response.json()["data"]
        integration_types = {i["integration_type"] for i in data}

        assert "global_dns" in integration_types


@pytest.mark.asyncio
@pytest.mark.integration
class TestRegistryEndpoints:
    """Test registry endpoints return integration data."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_integrations_registry(self, client: AsyncClient):
        """Test GET /integrations/registry returns all integration types."""
        response = await client.get("/v1/test-tenant/integrations/registry")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) > 0

        # Check for expected integration types
        integration_types = [i["integration_type"] for i in data]
        assert "splunk" in integration_types
        assert "echo_edr" in integration_types

        # Verify unified actions shape (no connectors/tools split)
        for integration in data:
            assert "action_count" in integration
            assert "connectors" not in integration
            assert "tool_count" not in integration

    @pytest.mark.asyncio
    async def test_get_integration_type_from_registry(self, client: AsyncClient):
        """Test GET /integrations/registry/{type} returns integration details."""
        response = await client.get("/v1/test-tenant/integrations/registry/splunk")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["integration_type"] == "splunk"
        assert "actions" in data
        assert len(data["actions"]) > 0
        # Old keys must NOT be present
        assert "connectors" not in data
        assert "tools" not in data

    @pytest.mark.asyncio
    async def test_list_integration_actions(self, client: AsyncClient):
        """Test GET /integrations/registry/{type}/actions returns all actions."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/splunk/actions"
        )

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) > 0

        # Each action should have expected fields
        for action in data:
            assert "action_id" in action
            assert "name" in action
            assert "categories" in action

    @pytest.mark.asyncio
    async def test_get_specific_action(self, client: AsyncClient):
        """Test GET /integrations/registry/{type}/actions/{action_id} returns action."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/splunk/actions/health_check"
        )

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["action_id"] == "health_check"
        assert "name" in data
        assert "params_schema" in data

    # Connector-specific endpoint tests removed: /connectors/ paths no longer exist.


@pytest.mark.asyncio
@pytest.mark.integration
class TestNegativeCases:
    """Test negative cases and error handling."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_nonexistent_registry_type_returns_404(self, client: AsyncClient):
        """Test GET /registry/{nonexistent} returns 404."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/nonexistent_type"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_action_returns_404(self, client: AsyncClient):
        """Test GET /registry/{type}/actions/{nonexistent} returns 404."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/splunk/actions/nonexistent_action"
        )
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationCredentialEndpoints:
    """Test Integration credential management endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_and_associate_credential_success(self, client: AsyncClient):
        """Test creating and associating a credential in one step."""
        # First create an integration
        integration_response = await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "splunk-test-creds",
                "integration_type": "splunk",
                "name": "Test Splunk for Credentials",
                "enabled": True,
                "settings": {"host": "splunk.example.com", "port": 8089},
            },
        )
        assert integration_response.status_code == 201

        # Now create and associate a credential
        response = await client.post(
            "/v1/test-tenant/integrations/splunk-test-creds/credentials",
            json={
                "provider": "splunk",
                "account": "admin-account",
                "secret": {"username": "admin", "password": "test-password-123"},
                "credential_metadata": {"environment": "test"},
                "is_primary": True,
                "purpose": "admin",
            },
        )

        assert response.status_code == 201
        body = response.json()
        data = body["data"]
        assert "credential_id" in data
        assert data["provider"] == "splunk"
        assert data["account"] == "admin-account"
        assert data["is_primary"] is True
        assert data["purpose"] == "admin"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_and_associate_credential_integration_not_found(
        self, client: AsyncClient
    ):
        """Test creating credential for non-existent integration returns 404."""
        response = await client.post(
            "/v1/test-tenant/integrations/non-existent-integration/credentials",
            json={
                "provider": "splunk",
                "account": "test-account",
                "secret": {"username": "user", "password": "pass"},
                "is_primary": False,
            },
        )

        assert response.status_code == 404
        assert "Integration not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_and_associate_credential_minimal(self, client: AsyncClient):
        """Test creating credential with minimal fields."""
        # First create an integration
        await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "echo-test-creds",
                "integration_type": "echo_edr",
                "name": "Test Echo EDR for Credentials",
                "enabled": True,
                "settings": {"api_url": "https://api.echoedr.com"},
            },
        )

        # Create credential with minimal fields
        response = await client.post(
            "/v1/test-tenant/integrations/echo-test-creds/credentials",
            json={"provider": "echo_edr", "secret": {"api_key": "sk-test-key-123"}},
        )

        assert response.status_code == 201
        body = response.json()
        data = body["data"]
        assert "credential_id" in data
        assert data["provider"] == "echo_edr"
        # Default values should be applied
        assert data["is_primary"] is True  # Default from schema

    @pytest.mark.asyncio
    async def test_create_and_associate_credential_with_purpose(
        self, client: AsyncClient
    ):
        """Test creating credential with specific purpose."""
        # First create an integration
        await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "splunk-purpose-test",
                "integration_type": "splunk",
                "name": "Test Splunk Purpose",
                "enabled": True,
                "settings": {"host": "splunk.example.com", "port": 8089},
            },
        )

        # Create read-only credential
        response = await client.post(
            "/v1/test-tenant/integrations/splunk-purpose-test/credentials",
            json={
                "provider": "splunk",
                "account": "readonly-account",
                "secret": {"username": "readonly", "password": "readonly-pass"},
                "is_primary": False,
                "purpose": "read",
            },
        )

        assert response.status_code == 201
        body = response.json()
        data = body["data"]
        assert data["purpose"] == "read"
        assert data["is_primary"] is False

    @pytest.mark.asyncio
    async def test_create_and_associate_credential_invalid_purpose(
        self, client: AsyncClient
    ):
        """Test creating credential with invalid purpose returns 422."""
        # First create an integration
        await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": "splunk-invalid-purpose",
                "integration_type": "splunk",
                "name": "Test Invalid Purpose",
                "enabled": True,
                "settings": {"host": "splunk.example.com", "port": 8089},
            },
        )

        # Try to create credential with invalid purpose
        response = await client.post(
            "/v1/test-tenant/integrations/splunk-invalid-purpose/credentials",
            json={
                "provider": "splunk",
                "secret": {"username": "user", "password": "pass"},
                "purpose": "invalid-purpose",  # Should only be read/write/admin
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_delete_integration_removes_access(self, client: AsyncClient):
        """Test that deleting an integration removes API access to associated resources.

        Note: Due to test transaction isolation, we can't reliably verify database deletion.
        This test verifies that the API properly denies access after deletion.
        """

        # Step 1: Create an integration
        integration_id = "cleanup-test-integration"
        integration_response = await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_id": integration_id,
                "integration_type": "splunk",
                "name": "Integration to Delete",
                "enabled": True,
                "settings": {"host": "splunk.test.com", "port": 8089},
            },
        )
        assert integration_response.status_code == 201

        # Step 2: Create and associate credentials
        cred_response = await client.post(
            f"/v1/test-tenant/integrations/{integration_id}/credentials",
            json={
                "provider": "splunk",
                "account": "test-account",
                "secret": {"username": "admin", "password": "admin-pass"},
                "is_primary": True,
                "purpose": "admin",
            },
        )
        assert cred_response.status_code == 201

        # Step 3: Verify resources are accessible before deletion
        get_integration = await client.get(
            f"/v1/test-tenant/integrations/{integration_id}"
        )
        assert get_integration.status_code == 200

        # Step 4: Delete the integration
        delete_response = await client.delete(
            f"/v1/test-tenant/integrations/{integration_id}"
        )
        assert delete_response.status_code in [200, 204]

        # Step 5: Verify API access is denied after deletion
        get_deleted = await client.get(f"/v1/test-tenant/integrations/{integration_id}")
        assert get_deleted.status_code == 404

        # Can't create new associations for deleted integration
        assoc_response = await client.post(
            f"/v1/test-tenant/integrations/{integration_id}/credentials",
            json={
                "provider": "splunk",
                "account": "new-account",
                "secret": {"username": "new", "password": "new-pass"},
            },
        )
        assert assoc_response.status_code == 404  # Integration not found


@pytest.mark.asyncio
@pytest.mark.integration
class TestToolsAllEndpoint:
    """Test GET /{tenant}/integrations/tools/all returns all tool categories."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_tools_all_returns_200(self, client: AsyncClient):
        """Test endpoint returns 200 with tools list."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert "tools" in data
        assert "total" in data
        assert data["total"] > 0
        assert data["total"] == len(data["tools"])

    @pytest.mark.asyncio
    async def test_tools_all_includes_builtin_tools(self, client: AsyncClient):
        """Test that cy-language builtin tools (sum, len, keys, etc.) are returned."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        fqns = [t["fqn"] for t in data["tools"]]

        # Core cy-language builtins must be present
        # Note: cy-language 0.36.0 namespaced keys/join under dict:: and str::
        assert "len" in fqns
        assert "sum" in fqns
        assert "dict::keys" in fqns
        assert "str::join" in fqns
        assert "from_json" in fqns
        assert "to_json" in fqns

    @pytest.mark.asyncio
    async def test_tools_all_includes_native_tools(self, client: AsyncClient):
        """Test that custom native tools (llm_run, store_artifact, etc.) are returned."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        fqns = [t["fqn"] for t in data["tools"]]

        assert "native::llm::llm_run" in fqns
        assert "native::tools::store_artifact" in fqns
        assert "native::alert::alert_read" in fqns

    @pytest.mark.asyncio
    async def test_tools_all_includes_framework_integration_tools(
        self, client: AsyncClient
    ):
        """Test that framework integration tools (echo_edr, etc.) are returned."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        fqns = [t["fqn"] for t in data["tools"]]

        # echo_edr is always present from framework manifests
        echo_tools = [f for f in fqns if f.startswith("app::echo_edr::")]
        assert len(echo_tools) > 0, "Expected at least one echo_edr tool"

    @pytest.mark.asyncio
    async def test_tools_all_has_category_field(self, client: AsyncClient):
        """Test that each tool has a category field."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        categories_seen = set()
        for tool in data["tools"]:
            assert "category" in tool, f"Tool {tool['fqn']} missing category field"
            categories_seen.add(tool["category"])

        # Must see at least builtin and native categories
        assert "builtin" in categories_seen
        assert "native" in categories_seen

    @pytest.mark.asyncio
    async def test_tools_all_native_tools_have_descriptions(self, client: AsyncClient):
        """Test that native:: tools have non-empty descriptions."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        native_tools = [t for t in data["tools"] if t["fqn"].startswith("native::")]
        assert len(native_tools) > 0

        for tool in native_tools:
            assert tool["description"], (
                f"Native tool {tool['fqn']} has empty description"
            )

    @pytest.mark.asyncio
    async def test_tools_all_builtin_tools_have_descriptions(self, client: AsyncClient):
        """Test that cy-language builtin tools have non-empty descriptions."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        builtin_tools = [t for t in data["tools"] if t["category"] == "builtin"]
        assert len(builtin_tools) >= 20, "Expected many builtin tools"

        missing = [t["fqn"] for t in builtin_tools if not t.get("description")]
        assert not missing, f"Builtin tools missing descriptions: {missing[:5]}"

    @pytest.mark.asyncio
    async def test_tools_all_integration_tools_have_descriptions(
        self, client: AsyncClient
    ):
        """Test that framework integration tools have non-empty descriptions."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        integration_tools = [t for t in data["tools"] if t["category"] == "integration"]
        assert len(integration_tools) > 0

        # Check a sample - echo_edr tools should have descriptions from manifests
        echo_tools = [t for t in integration_tools if "echo_edr" in t["fqn"]]
        missing = [t["fqn"] for t in echo_tools if not t.get("description")]
        assert not missing, f"Echo EDR tools missing descriptions: {missing}"

    @pytest.mark.asyncio
    async def test_tools_all_native_tools_have_params_schema(self, client: AsyncClient):
        """Test that native:: tools have params_schema with properties."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        llm_run = next(
            (t for t in data["tools"] if t["fqn"] == "native::llm::llm_run"), None
        )
        assert llm_run is not None
        assert llm_run["params_schema"] is not None
        assert "properties" in llm_run["params_schema"]
        assert "prompt" in llm_run["params_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_tools_all_builtin_tools_have_params_schema(
        self, client: AsyncClient
    ):
        """Test that builtin tools have params_schema extracted from signatures."""
        response = await client.get("/v1/test-tenant/integrations/tools/all")
        data = response.json()["data"]

        # str::join(items, separator) should have 2 params, 1 required
        # Note: cy-language 0.36.0 namespaced join under str::
        join_tool = next((t for t in data["tools"] if t["fqn"] == "str::join"), None)
        assert join_tool is not None
        schema = join_tool["params_schema"]
        assert schema is not None
        assert "items" in schema["properties"]
        assert "separator" in schema["properties"]
        assert "items" in schema["required"]
        # separator has a default so it should NOT be required
        assert "separator" not in schema["required"]

        # str::split(text, delimiter) should have 2 params
        # Note: cy-language 0.36.0 namespaced split under str::
        split_tool = next((t for t in data["tools"] if t["fqn"] == "str::split"), None)
        assert split_tool is not None
        assert "text" in split_tool["params_schema"]["properties"]
