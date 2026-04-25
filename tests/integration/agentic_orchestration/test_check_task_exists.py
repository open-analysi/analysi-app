"""Integration tests for _check_task_exists API parsing.

Tests verify that the task existence check correctly parses the REST API response
and handles agent renaming via derived cy_name fallback.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.agentic_orchestration.nodes.task_building import _check_task_exists
from analysi.common.internal_client import _UnwrappedResponse
from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestCheckTaskExistsIntegration:
    """Integration tests for _check_task_exists function.

    These tests verify:
    1. The tasks API returns {"tasks": [...]} format
    2. The _check_task_exists function correctly parses this response
    3. The derived cy_name fallback finds tasks when agents rename them

    Critical bug fixed: API returns "tasks" key, not "items" key.
    """

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
    async def created_task(self, client: AsyncClient, sample_tenant_id: str):
        """Create a real task via API and return its details."""
        unique_suffix = uuid4().hex[:8]

        task_data = {
            "name": f"Test Task for Exists Check {unique_suffix}",
            "script": "return input",
            "description": "Task created for _check_task_exists integration test",
            "function": "reasoning",
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post(
            f"/v1/{sample_tenant_id}/tasks",
            json=task_data,
        )
        assert response.status_code == 201, f"Failed to create task: {response.text}"

        task = response.json()["data"]
        yield {
            "id": task["id"],
            "name": task["name"],
            "cy_name": task["cy_name"],
            "tenant_id": sample_tenant_id,
        }

        # Cleanup - delete the task
        await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @asynccontextmanager
    async def _mock_internal_client(self, client: AsyncClient):
        """Patch InternalAsyncClient to route through the test ASGI client."""

        async def mock_get(url, params=None, timeout=None):
            path = url.replace("http://test", "")
            response = await client.get(path, params=params)
            return _UnwrappedResponse(response)

        with patch("analysi.common.internal_client.InternalAsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance
            yield

    async def _create_task(self, client, tenant_id, name):
        """Helper to create a task and return its data. Caller must delete."""
        response = await client.post(
            f"/v1/{tenant_id}/tasks",
            json={
                "name": name,
                "script": "return input",
                "function": "reasoning",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert response.status_code == 201, f"Failed to create task: {response.text}"
        return response.json()["data"]

    @pytest.mark.asyncio
    async def test_api_returns_tasks_key_not_items(
        self, client: AsyncClient, created_task
    ):
        """Verify the API response format uses 'tasks' key.

        This is the root cause test - verifying the API contract.
        The _check_task_exists function must use 'tasks' not 'items'.
        """
        response = await client.get(
            f"/v1/{created_task['tenant_id']}/tasks",
            params={"q": created_task["name"], "limit": 1},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # With ApiListResponse, data is a list of tasks directly
        assert isinstance(data, list), (
            "API list response 'data' must be a list of tasks"
        )
        assert len(data) == 1
        assert data[0]["name"] == created_task["name"]

    @pytest.mark.asyncio
    async def test_api_cy_name_filter_returns_tasks_key(
        self, client: AsyncClient, created_task
    ):
        """Verify cy_name filter also uses 'tasks' response key."""
        response = await client.get(
            f"/v1/{created_task['tenant_id']}/tasks",
            params={"cy_name": created_task["cy_name"], "limit": 1},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert isinstance(data, list), "cy_name filter response 'data' must be a list"
        assert len(data) == 1
        assert data[0]["cy_name"] == created_task["cy_name"]

    @pytest.mark.asyncio
    async def test_check_task_exists_finds_task_by_name(
        self, client: AsyncClient, created_task
    ):
        """Test _check_task_exists finds task by human-readable name."""
        async with self._mock_internal_client(client):
            result = await _check_task_exists(
                tenant_id=created_task["tenant_id"],
                task_identifier=created_task["name"],
                api_base_url="http://test",
            )

        assert result is not None, (
            f"_check_task_exists should find task by name '{created_task['name']}'. "
            "If this fails, verify the function parses 'tasks' key correctly."
        )
        assert result["id"] == created_task["id"]
        assert result["name"] == created_task["name"]

    @pytest.mark.asyncio
    async def test_check_task_exists_finds_task_by_cy_name(
        self, client: AsyncClient, created_task
    ):
        """Test _check_task_exists finds task by cy_name."""
        async with self._mock_internal_client(client):
            result = await _check_task_exists(
                tenant_id=created_task["tenant_id"],
                task_identifier=created_task["cy_name"],
                api_base_url="http://test",
            )

        assert result is not None, (
            f"_check_task_exists should find task by cy_name '{created_task['cy_name']}'."
        )
        assert result["id"] == created_task["id"]
        assert result["cy_name"] == created_task["cy_name"]

    @pytest.mark.asyncio
    async def test_check_task_exists_returns_none_for_nonexistent(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Test _check_task_exists returns None for nonexistent tasks."""
        async with self._mock_internal_client(client):
            nonexistent_name = f"Definitely Does Not Exist {uuid4().hex}"
            result = await _check_task_exists(
                tenant_id=sample_tenant_id,
                task_identifier=nonexistent_name,
                api_base_url="http://test",
            )

        assert result is None, "Should return None for nonexistent task"

    # -------------------------------------------------------------------
    # Derived cy_name fallback tests (agent renaming scenarios)
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_derived_cyname_agent_adds_colon(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent adds colon: proposal 'X Y' but agent creates 'X: Y'."""
        suffix = uuid4().hex[:8]
        proposal_name = f"SharePoint JWT Auth Bypass {suffix}"
        agent_name = f"SharePoint: JWT Auth Bypass {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is not None, (
                f"Should find task via derived cy_name: "
                f"'{proposal_name}' -> '{agent_name}'"
            )
            assert result["id"] == task["id"]
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @pytest.mark.asyncio
    async def test_derived_cyname_agent_adds_hyphen(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent uses hyphens instead of spaces: 'IP Reputation' vs 'IP-Reputation'."""
        suffix = uuid4().hex[:8]
        proposal_name = f"IP Reputation Check {suffix}"
        agent_name = f"IP-Reputation Check {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is not None, (
                f"Should find task via derived cy_name: "
                f"'{proposal_name}' -> '{agent_name}'"
            )
            assert result["id"] == task["id"]
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @pytest.mark.asyncio
    async def test_derived_cyname_agent_adds_parentheses(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent wraps part in parens: 'CVE Analysis' vs 'CVE Analysis (Deep)'."""
        suffix = uuid4().hex[:8]
        # "CVE Analysis Deep X" and "CVE Analysis (Deep) X" produce same cy_name
        proposal_name = f"CVE Analysis Deep {suffix}"
        agent_name = f"CVE Analysis (Deep) {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is not None, (
                f"Should find task via derived cy_name: "
                f"'{proposal_name}' -> '{agent_name}'"
            )
            assert result["id"] == task["id"]
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @pytest.mark.asyncio
    async def test_derived_cyname_agent_adds_exclamation(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent adds trailing punctuation: 'Alert Check' vs 'Alert Check!'."""
        suffix = uuid4().hex[:8]
        proposal_name = f"Alert Check {suffix}"
        agent_name = f"Alert Check! {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is not None, (
                f"Should find task via derived cy_name: "
                f"'{proposal_name}' -> '{agent_name}'"
            )
            assert result["id"] == task["id"]
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    # -------------------------------------------------------------------
    # False positive protection: names that should NOT match
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_task_exists_partial_name_no_false_positive(
        self, client: AsyncClient, created_task
    ):
        """Test partial name matches don't return false positives.

        The 'q' search does fuzzy matching, but exact name match is required.
        """
        async with self._mock_internal_client(client):
            # Use only first 15 chars - should not match due to exact check
            partial_name = created_task["name"][:15]

            result = await _check_task_exists(
                tenant_id=created_task["tenant_id"],
                task_identifier=partial_name,
                api_base_url="http://test",
            )

        assert result is None, (
            "Partial name match should return None due to exact name verification"
        )

    @pytest.mark.asyncio
    async def test_derived_cyname_no_match_when_extra_words(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent adds extra words: different cy_name, should not match."""
        suffix = uuid4().hex[:8]
        proposal_name = f"IP Check {suffix}"
        agent_name = f"IP Reputation Check Extended {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is None, (
                "Should NOT match when agent adds extra words (different cy_name)"
            )
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @pytest.mark.asyncio
    async def test_derived_cyname_no_match_when_words_reordered(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Agent reorders words: different cy_name, should not match."""
        suffix = uuid4().hex[:8]
        proposal_name = f"Reputation IP Analysis {suffix}"
        agent_name = f"IP Analysis Reputation {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is None, (
                "Should NOT match when agent reorders words (different cy_name)"
            )
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")

    @pytest.mark.asyncio
    async def test_derived_cyname_no_match_completely_different_name(
        self, client: AsyncClient, sample_tenant_id: str
    ):
        """Completely unrelated names should never match."""
        suffix = uuid4().hex[:8]
        proposal_name = f"Firewall Log Parser {suffix}"
        agent_name = f"DNS Exfiltration Detector {suffix}"

        task = await self._create_task(client, sample_tenant_id, agent_name)
        try:
            async with self._mock_internal_client(client):
                result = await _check_task_exists(
                    tenant_id=sample_tenant_id,
                    task_identifier=proposal_name,
                    api_base_url="http://test",
                )
            assert result is None, "Should NOT match completely unrelated task names"
        finally:
            await client.delete(f"/v1/{sample_tenant_id}/tasks/{task['id']}")
