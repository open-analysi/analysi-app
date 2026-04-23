"""Integration tests for unified categories filtering.

Tests auto-population from subtype fields and ?categories= query param
across tasks, knowledge units, and skills endpoints.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestCategoriesAutoPopulate:
    """Verify categories are auto-populated from classification fields on create."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def test_document_ku_auto_populates_categories(self, client: AsyncClient):
        """Creating a document KU with document_type/doc_format populates categories."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": f"Test Doc {uuid.uuid4().hex[:8]}",
                "content": "some content",
                "document_type": "feedback",
                "doc_format": "raw",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "feedback" in data["categories"]
        assert "raw" in data["categories"]

    async def test_task_auto_populates_categories(self, client: AsyncClient):
        """Creating a task with function/scope populates categories."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Test Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
                "scope": "processing",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "reasoning" in data["categories"]
        assert "processing" in data["categories"]

    async def test_user_categories_preserved_alongside_auto(self, client: AsyncClient):
        """User-provided categories are preserved alongside auto-populated ones."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Test Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "extraction",
                "categories": ["custom-tag"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "custom-tag" in data["categories"]
        assert "extraction" in data["categories"]

    async def test_omitted_scope_not_auto_populated(self, client: AsyncClient):
        """Task created without explicit scope does not inject default into categories."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Test Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
                # scope not provided — should NOT be injected into categories
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "reasoning" in data["categories"]
        assert "processing" not in data["categories"], (
            "Omitted scope should not be auto-populated into categories"
        )

    async def test_default_doc_format_auto_populates(self, client: AsyncClient):
        """Document KU created without explicit doc_format gets default 'raw' in categories."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": f"Test Doc {uuid.uuid4().hex[:8]}",
                "content": "some content",
                "document_type": "feedback",
                # doc_format not provided — defaults to "raw"
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "feedback" in data["categories"]
        assert "raw" in data["categories"], (
            "Default doc_format 'raw' should be auto-populated into categories"
        )

    async def test_no_duplicate_categories(self, client: AsyncClient):
        """If user already includes the classification value, no duplicate."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Test Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
                "categories": ["reasoning"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["categories"].count("reasoning") == 1


@pytest.mark.asyncio
@pytest.mark.integration
class TestCategoriesUpdateSync:
    """Verify categories are updated when classification fields change."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def test_update_task_function_adds_to_categories(self, client: AsyncClient):
        """Updating a task's function should add the new value to categories."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        # Create a task with function=reasoning
        resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["data"]["id"]

        # Update function to extraction
        resp = await client.put(
            f"/v1/{tenant}/tasks/{task_id}",
            json={"function": "extraction"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Both old and new values should be in categories (additive)
        assert "reasoning" in data["categories"]
        assert "extraction" in data["categories"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestCategoriesFilter:
    """Verify ?categories= query param filters correctly (AND semantics)."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def test_filter_tasks_by_single_category(self, client: AsyncClient):
        """Filter tasks by a single category."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        # Create a task with function=reasoning
        await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Reasoning Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
            },
        )

        # Create a task with function=extraction
        await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Extraction Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "extraction",
            },
        )

        # Filter by reasoning
        resp = await client.get(
            f"/v1/{tenant}/tasks", params={"categories": "reasoning"}
        )
        assert resp.status_code == 200
        tasks = resp.json()["data"]
        assert len(tasks) == 1
        assert "reasoning" in tasks[0]["categories"]

    async def test_filter_tasks_by_multiple_categories_and_semantics(
        self, client: AsyncClient
    ):
        """Filter with multiple categories uses AND semantics."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        # Create a task with both reasoning + processing
        await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": f"Full Task {uuid.uuid4().hex[:8]}",
                "script": 'result = "ok"',
                "function": "reasoning",
                "scope": "processing",
            },
        )

        # Filter by both — should return it
        resp = await client.get(
            f"/v1/{tenant}/tasks",
            params={"categories": ["reasoning", "processing"]},
        )
        assert resp.status_code == 200
        tasks = resp.json()["data"]
        assert len(tasks) == 1

        # Filter by reasoning + nonexistent — AND logic means empty
        resp = await client.get(
            f"/v1/{tenant}/tasks",
            params={"categories": ["reasoning", "nonexistent"]},
        )
        assert resp.status_code == 200
        tasks = resp.json()["data"]
        assert len(tasks) == 0

    async def test_filter_kus_by_category(self, client: AsyncClient):
        """Filter knowledge units by category."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        # Create a document KU with document_type=feedback
        await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": f"Feedback Doc {uuid.uuid4().hex[:8]}",
                "content": "some feedback",
                "document_type": "feedback",
                "doc_format": "raw",
            },
        )

        # Create another document KU without feedback type
        await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": f"General Doc {uuid.uuid4().hex[:8]}",
                "content": "general stuff",
                "document_type": "runbook",
            },
        )

        # Filter KUs by feedback
        resp = await client.get(
            f"/v1/{tenant}/knowledge-units", params={"categories": "feedback"}
        )
        assert resp.status_code == 200
        kus = resp.json()["data"]
        assert len(kus) == 1
        assert "feedback" in kus[0]["categories"]

    async def test_filter_kus_by_multiple_categories(self, client: AsyncClient):
        """Filter KUs with multiple categories (AND semantics)."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        # Create a doc with feedback + raw
        await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": f"Feedback Doc {uuid.uuid4().hex[:8]}",
                "content": "some feedback",
                "document_type": "feedback",
                "doc_format": "raw",
            },
        )

        # Filter by feedback + raw — should match
        resp = await client.get(
            f"/v1/{tenant}/knowledge-units",
            params={"categories": ["feedback", "raw"]},
        )
        assert resp.status_code == 200
        kus = resp.json()["data"]
        assert len(kus) == 1

    async def test_categories_filter_coexists_with_text_search(
        self, client: AsyncClient
    ):
        """Categories filter works alongside ?q= text search."""
        tenant = f"test-cat-{uuid.uuid4().hex[:8]}"

        task_name = f"Special Reasoning Task {uuid.uuid4().hex[:8]}"
        await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": task_name,
                "script": 'result = "ok"',
                "function": "reasoning",
            },
        )

        # Search by q + categories
        resp = await client.get(
            f"/v1/{tenant}/tasks",
            params={"q": "Special", "categories": "reasoning"},
        )
        assert resp.status_code == 200
        tasks = resp.json()["data"]
        assert len(tasks) == 1

        # Search with q that matches but wrong category
        resp = await client.get(
            f"/v1/{tenant}/tasks",
            params={"q": "Special", "categories": "nonexistent"},
        )
        assert resp.status_code == 200
        tasks = resp.json()["data"]
        assert len(tasks) == 0
