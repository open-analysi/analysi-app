"""
Integration tests for Component deletion cascade functionality.

Tests that deletion through API endpoints properly cascades to delete all related records:
- Component records (root)
- KnowledgeUnit records (intermediate)
- KUTable/KUDocument/KUIndex records (leaf)
- Task records (leaf)

This prevents regression of the cascade deletion bug where specific endpoint deletions
would leave orphaned records in the general endpoint.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component
from analysi.models.knowledge_unit import KnowledgeUnit, KUDocument, KUIndex, KUTable
from analysi.models.task import Task


@pytest.mark.asyncio
@pytest.mark.integration
class TestComponentDeletionCascade:
    """Test Component deletion cascade for all component types."""

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

    async def _verify_complete_deletion(
        self, session: AsyncSession, component_id: str, component_type: str
    ) -> None:
        """
        Verify that Component and all related records are completely deleted.

        Args:
            session: Database session
            component_id: The component ID that was deleted
            component_type: Type for better error messages (table/document/index/task)
        """
        # Check Component is deleted
        component_count = await session.execute(
            select(func.count())
            .select_from(Component)
            .where(Component.id == component_id)
        )
        assert component_count.scalar() == 0, (
            f"Component {component_id} ({component_type}) still exists"
        )

        # Check KnowledgeUnit is deleted (only for KU types)
        if component_type in ["table", "document", "index"]:
            ku_count = await session.execute(
                select(func.count())
                .select_from(KnowledgeUnit)
                .where(KnowledgeUnit.component_id == component_id)
            )
            assert ku_count.scalar() == 0, (
                f"KnowledgeUnit {component_id} ({component_type}) still exists"
            )

        # Check specific subtype is deleted
        if component_type == "table":
            table_count = await session.execute(
                select(func.count())
                .select_from(KUTable)
                .where(KUTable.component_id == component_id)
            )
            assert table_count.scalar() == 0, f"KUTable {component_id} still exists"
        elif component_type == "document":
            doc_count = await session.execute(
                select(func.count())
                .select_from(KUDocument)
                .where(KUDocument.component_id == component_id)
            )
            assert doc_count.scalar() == 0, f"KUDocument {component_id} still exists"
        elif component_type == "index":
            index_count = await session.execute(
                select(func.count())
                .select_from(KUIndex)
                .where(KUIndex.component_id == component_id)
            )
            assert index_count.scalar() == 0, f"KUIndex {component_id} still exists"
        elif component_type == "task":
            task_count = await session.execute(
                select(func.count())
                .select_from(Task)
                .where(Task.component_id == component_id)
            )
            assert task_count.scalar() == 0, f"Task {component_id} still exists"

    @pytest.mark.asyncio
    async def test_table_deletion_cascade(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that Table KU deletion cascades properly through all database layers."""
        tenant = "test-tenant"

        # Create a table
        table_data = {
            "name": "Test Deletion Table",
            "description": "Table to test cascade deletion",
            "schema": {"type": "object", "properties": {"id": {"type": "string"}}},
            "content": {"data": [{"id": "1"}]},
            "row_count": 1,
            "column_count": 1,
        }

        # CREATE
        create_response = await client.post(
            f"/v1/{tenant}/knowledge-units/tables", json=table_data
        )
        assert create_response.status_code == 201
        created_table = create_response.json()["data"]
        table_id = created_table["id"]

        # Verify creation in both endpoints
        get_response = await client.get(
            f"/v1/{tenant}/knowledge-units/tables/{table_id}"
        )
        assert get_response.status_code == 200

        search_response = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Table"
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["data"]) == 1

        # DELETE
        delete_response = await client.delete(
            f"/v1/{tenant}/knowledge-units/tables/{table_id}"
        )
        assert delete_response.status_code == 204

        # Verify complete deletion from API
        get_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units/tables/{table_id}"
        )
        assert get_after_delete.status_code == 404

        search_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Table"
        )
        assert search_after_delete.status_code == 200
        assert len(search_after_delete.json()["data"]) == 0

        # Verify complete deletion from database
        await self._verify_complete_deletion(
            integration_test_session, table_id, "table"
        )

    @pytest.mark.asyncio
    async def test_document_deletion_cascade(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that Document KU deletion cascades properly through all database layers."""
        tenant = "test-tenant"

        # Create a document
        doc_data = {
            "name": "Test Deletion Document",
            "description": "Document to test cascade deletion",
            "content": "This is test content for cascade deletion testing.",
            "doc_format": "text",
            "document_type": "test",
        }

        # CREATE
        create_response = await client.post(
            f"/v1/{tenant}/knowledge-units/documents", json=doc_data
        )
        assert create_response.status_code == 201
        created_doc = create_response.json()["data"]
        doc_id = created_doc["id"]

        # Verify creation in both endpoints
        get_response = await client.get(
            f"/v1/{tenant}/knowledge-units/documents/{doc_id}"
        )
        assert get_response.status_code == 200

        search_response = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Document"
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["data"]) == 1

        # DELETE
        delete_response = await client.delete(
            f"/v1/{tenant}/knowledge-units/documents/{doc_id}"
        )
        assert delete_response.status_code == 204

        # Verify complete deletion from API
        get_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units/documents/{doc_id}"
        )
        assert get_after_delete.status_code == 404

        search_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Document"
        )
        assert search_after_delete.status_code == 200
        assert len(search_after_delete.json()["data"]) == 0

        # Verify complete deletion from database
        await self._verify_complete_deletion(
            integration_test_session, doc_id, "document"
        )

    @pytest.mark.asyncio
    async def test_index_deletion_cascade(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that Index KU deletion cascades properly through all database layers."""
        tenant = "test-tenant"

        # Create an index
        index_data = {
            "name": "Test Deletion Index",
            "description": "Index to test cascade deletion",
            "index_type": "vector",
            "vector_database": "local",
            "embedding_model": "test-model",
        }

        # CREATE
        create_response = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=index_data
        )
        assert create_response.status_code == 201
        created_index = create_response.json()["data"]
        index_id = created_index["id"]

        # Verify creation in both endpoints
        get_response = await client.get(
            f"/v1/{tenant}/knowledge-units/indexes/{index_id}"
        )
        assert get_response.status_code == 200

        search_response = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Index"
        )
        assert search_response.status_code == 200
        assert len(search_response.json()["data"]) == 1

        # DELETE
        delete_response = await client.delete(
            f"/v1/{tenant}/knowledge-units/indexes/{index_id}"
        )
        assert delete_response.status_code == 204

        # Verify complete deletion from API
        get_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units/indexes/{index_id}"
        )
        assert get_after_delete.status_code == 404

        search_after_delete = await client.get(
            f"/v1/{tenant}/knowledge-units?q=Test+Deletion+Index"
        )
        assert search_after_delete.status_code == 200
        assert len(search_after_delete.json()["data"]) == 0

        # Verify complete deletion from database
        await self._verify_complete_deletion(
            integration_test_session, index_id, "index"
        )

    @pytest.mark.asyncio
    async def test_task_deletion_cascade(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that Task deletion cascades properly through all database layers."""
        tenant = "test-tenant"

        # Create a task
        task_data = {
            "name": "Test Deletion Task",
            "description": "Task to test cascade deletion",
            "directive": "Test task for cascade deletion testing",
            "script_file": "test_deletion.cy",
            "script": '#!cy 2.1\\n// Test script for deletion\\nreturn {\\"result\\": \\"deletion_test\\"}',
            "function": "test",
            "scope": "processing",
        }

        # CREATE
        create_response = await client.post(f"/v1/{tenant}/tasks", json=task_data)
        assert create_response.status_code == 201
        created_task = create_response.json()["data"]
        task_id = created_task["id"]

        # Verify creation
        get_response = await client.get(f"/v1/{tenant}/tasks/{task_id}")
        assert get_response.status_code == 200

        # DELETE
        delete_response = await client.delete(f"/v1/{tenant}/tasks/{task_id}")
        assert delete_response.status_code == 204

        # Verify complete deletion from API
        get_after_delete = await client.get(f"/v1/{tenant}/tasks/{task_id}")
        assert get_after_delete.status_code == 404

        # Verify complete deletion from database
        await self._verify_complete_deletion(integration_test_session, task_id, "task")
