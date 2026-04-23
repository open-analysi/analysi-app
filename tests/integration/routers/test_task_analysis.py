"""Integration tests for Task script analysis and tool edge sync."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskScriptAnalysis:
    """Test GET /{tenant}/tasks/{id}/analyze and POST /{tenant}/tasks/analyze."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.dependency_overrides.clear()

    # --- POST /tasks/analyze (ad-hoc) ---

    async def test_adhoc_analyze_extracts_tools(self, client: AsyncClient):
        """Ad-hoc analysis returns tools_used from script."""
        response = await client.post(
            "/v1/default/tasks/analyze",
            json={
                "script": "result = app::virustotal::ip_reputation(input.ip)\nreturn result"
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["task_id"] is None
        assert data["cy_name"] is None
        assert "app::virustotal::ip_reputation" in data["tools_used"]
        assert "input" in data["external_variables"]
        assert data["errors"] is None

    async def test_adhoc_analyze_no_tools(self, client: AsyncClient):
        """Ad-hoc analysis with a script that uses no tools."""
        response = await client.post(
            "/v1/default/tasks/analyze",
            json={"script": "x = 1 + 2\nreturn x"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tools_used"] == []
        assert data["errors"] is None

    async def test_adhoc_analyze_syntax_error(self, client: AsyncClient):
        """Ad-hoc analysis with invalid Cy code returns errors."""
        response = await client.post(
            "/v1/default/tasks/analyze",
            json={"script": "??? bad code !!!"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tools_used"] is None
        assert data["external_variables"] is None
        assert data["errors"] is not None
        assert len(data["errors"]) > 0

    async def test_adhoc_analyze_empty_script_rejected(self, client: AsyncClient):
        """Empty script is rejected by validation."""
        response = await client.post(
            "/v1/default/tasks/analyze",
            json={"script": ""},
        )
        assert response.status_code == 422

    # --- GET /tasks/{id}/analyze (saved task) ---

    async def test_saved_task_analyze(self, client: AsyncClient):
        """Analyze a saved task returns tools and task metadata."""
        # Create a task first
        create_resp = await client.post(
            "/v1/default/tasks",
            json={
                "name": f"Analysis Test Task {uuid.uuid4().hex[:8]}",
                "script": "result = app::echo_edr::get_host_details(input.hostname)\nreturn result",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_resp.status_code == 201
        task = create_resp.json()["data"]

        # Analyze it
        response = await client.get(f"/v1/default/tasks/{task['id']}/analyze")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["task_id"] == task["id"]
        assert data["cy_name"] == task["cy_name"]
        assert "app::echo_edr::get_host_details" in data["tools_used"]
        assert "input" in data["external_variables"]
        assert data["errors"] is None

    async def test_saved_task_analyze_not_found(self, client: AsyncClient):
        """Analyzing a nonexistent task returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/v1/default/tasks/{fake_id}/analyze")
        assert response.status_code == 404

    async def test_saved_task_analyze_tenant_isolation(self, client: AsyncClient):
        """Task from tenant-a cannot be analyzed via tenant-b."""
        create_resp = await client.post(
            "/v1/tenant-analysis-a/tasks",
            json={
                "name": f"Isolation Test {uuid.uuid4().hex[:8]}",
                "script": "return 1",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["id"]

        # Try to analyze from a different tenant
        response = await client.get(f"/v1/tenant-analysis-b/tasks/{task_id}/analyze")
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskToolEdgeSync:
    """Test auto-creation of KDG Task->Tool 'uses' edges on task create/update."""

    TENANT = "edge-sync-test"

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    async def registered_tool(self, integration_test_session):
        """Create a KUTool Component so edge creation has a target.

        Uses echo_edr::get_host_details as the 2-part name, matching the
        FQN app::echo_edr::get_host_details that Cy analysis returns.
        """
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        repo = KnowledgeUnitRepository(integration_test_session)
        tool = await repo.create_tool_ku(
            tenant_id=self.TENANT,
            name="echo_edr::get_host_details",
            description="Get host details from echo EDR",
            tool_type="app",
            input_schema={
                "properties": {"hostname": {"type": "string"}},
                "required": ["hostname"],
            },
            output_schema={"type": "object"},
        )
        return tool

    # --- Create with valid tool → edge created ---

    async def test_create_task_with_tool_creates_edge(
        self, client: AsyncClient, registered_tool
    ):
        """Creating a task that uses a registered tool creates a KDG edge."""
        resp = await client.post(
            f"/v1/{self.TENANT}/tasks",
            json={
                "name": f"Edge Test {uuid.uuid4().hex[:8]}",
                "script": "r = app::echo_edr::get_host_details(input.h)\nreturn r",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert resp.status_code == 201, resp.json()
        task_id = resp.json()["data"]["id"]

        # Check relationships via KDG edges endpoint
        edges_resp = await client.get(
            f"/v1/{self.TENANT}/kdg/nodes/{task_id}/edges",
            params={"direction": "out"},
        )
        assert edges_resp.status_code == 200
        edges = edges_resp.json()["data"]
        target_names = [e["target_node"]["name"] for e in edges if e.get("target_node")]
        assert "echo_edr::get_host_details" in target_names

    # --- Create with unknown tool → 400 ---

    async def test_create_task_with_unknown_tool_fails(self, client: AsyncClient):
        """Creating a task referencing an unknown tool returns 400."""
        resp = await client.post(
            f"/v1/{self.TENANT}/tasks",
            json={
                "name": f"Bad Tool {uuid.uuid4().hex[:8]}",
                "script": "r = app::fake_integration::nope(input.x)\nreturn r",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        detail_str = detail["error"] if isinstance(detail, dict) else detail
        assert "unknown tools" in detail_str.lower() or "invalid" in detail_str.lower()

    # --- Create with no tools → succeeds, no edges ---

    async def test_create_task_no_tools_no_edges(self, client: AsyncClient):
        """Creating a task with no tool calls succeeds with no edges."""
        resp = await client.post(
            f"/v1/{self.TENANT}/tasks",
            json={
                "name": f"No Tools {uuid.uuid4().hex[:8]}",
                "script": "x = 1 + 2\nreturn x",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["data"]["id"]

        edges_resp = await client.get(
            f"/v1/{self.TENANT}/kdg/nodes/{task_id}/edges",
            params={"direction": "out"},
        )
        assert edges_resp.status_code == 200
        assert edges_resp.json()["data"] == []

    # --- Update script → old edge removed, new edge added ---

    async def test_update_script_replaces_edges(
        self, client: AsyncClient, registered_tool, integration_test_session
    ):
        """Updating a task's script replaces old tool edges with new ones."""
        # Create second tool KU for the swap
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_tool_ku(
            tenant_id=self.TENANT,
            name="echo_edr::scan_host",
            description="Search events",
            tool_type="app",
            input_schema={
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            output_schema={"type": "object"},
        )

        # Create task using get_host
        resp = await client.post(
            f"/v1/{self.TENANT}/tasks",
            json={
                "name": f"Swap Test {uuid.uuid4().hex[:8]}",
                "script": "r = app::echo_edr::get_host_details(input.h)\nreturn r",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["data"]["id"]

        # Verify initial edge via KDG
        edges_resp = await client.get(
            f"/v1/{self.TENANT}/kdg/nodes/{task_id}/edges",
            params={"direction": "out"},
        )
        target_names = [
            e["target_node"]["name"]
            for e in edges_resp.json()["data"]
            if e.get("target_node")
        ]
        assert "echo_edr::get_host_details" in target_names

        # Update to search_events
        update_resp = await client.put(
            f"/v1/{self.TENANT}/tasks/{task_id}",
            json={"script": "r = app::echo_edr::scan_host(input.q)\nreturn r"},
        )
        assert update_resp.status_code == 200

        # Verify edges swapped via KDG
        edges_resp2 = await client.get(
            f"/v1/{self.TENANT}/kdg/nodes/{task_id}/edges",
            params={"direction": "out"},
        )
        target_names2 = [
            e["target_node"]["name"]
            for e in edges_resp2.json()["data"]
            if e.get("target_node")
        ]
        assert "echo_edr::scan_host" in target_names2
        assert "echo_edr::get_host_details" not in target_names2

    # --- Backfill endpoint ---

    async def test_sync_edges_backfill(self, client: AsyncClient, registered_tool):
        """POST /tasks/sync-edges creates missing edges for existing tasks."""
        # Create a task (edges created automatically)
        resp = await client.post(
            f"/v1/{self.TENANT}/tasks",
            json={
                "name": f"Backfill Test {uuid.uuid4().hex[:8]}",
                "script": "r = app::echo_edr::get_host_details(input.h)\nreturn r",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert resp.status_code == 201

        # Run backfill — should succeed without errors
        sync_resp = await client.post(f"/v1/{self.TENANT}/tasks/sync-edges")
        assert sync_resp.status_code == 200
        data = sync_resp.json()["data"]
        assert "synced" in data
        assert "skipped" in data
        assert "errors" in data
        assert isinstance(data["errors"], list)
