"""Test knowledge unit duplicate handling with cy_name generation."""

import uuid

import pytest

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeUnitDuplicateHandling:
    """Test duplicate KU handling with cy_name generation."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create KnowledgeUnitRepository with test session."""
        return KnowledgeUnitRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_duplicate_ku_handling_with_cy_name(self, repository, tenant_id):
        """Test that duplicate KUs are handled properly with cy_name generation."""
        app = "TestApp"

        # Create first KU
        ku1 = await repository.create_document_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Test Document",
                "content": "Test content",
                "metadata": {"version": "1.0"},
            },
        )

        # Verify cy_name was generated
        assert ku1.component.cy_name is not None
        assert ku1.component.cy_name.startswith("test_document")
        print(f"Created KU1 with cy_name: {ku1.component.cy_name}")

        # Try to create duplicate - should update instead
        ku2 = await repository.create_document_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Test Document",
                "content": "Updated content",
                "metadata": {"version": "2.0"},
            },
        )

        # Should be the same KU with updated content
        assert ku2.id == ku1.id
        assert ku2.component.cy_name == ku1.component.cy_name
        assert ku2.content == "Updated content"
        assert ku2.doc_metadata["version"] == "2.0"
        print(f"Updated KU with same cy_name: {ku2.component.cy_name}")

    @pytest.mark.asyncio
    async def test_unique_cy_names_for_different_names(self, repository, tenant_id):
        """Test that different KU names get unique cy_names."""
        app = "TestApp"

        # Create KUs with different names
        ku1 = await repository.create_document_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Document One",
                "content": "Content 1",
                "metadata": {},
            },
        )

        ku2 = await repository.create_document_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Document Two",
                "content": "Content 2",
                "metadata": {},
            },
        )

        # Should have different cy_names
        assert ku1.component.cy_name != ku2.component.cy_name
        assert ku1.component.cy_name.startswith("document_one")
        assert ku2.component.cy_name.startswith("document_two")
        print(f"KU1 cy_name: {ku1.component.cy_name}")
        print(f"KU2 cy_name: {ku2.component.cy_name}")

    @pytest.mark.asyncio
    async def test_table_ku_cy_name_generation(self, repository, tenant_id):
        """Test that table KUs also get cy_names generated."""
        app = "TestApp"

        # Create table KU
        ku = await repository.create_table_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Test Table",
                "schema": {"columns": ["id", "name", "value"]},
                "data": [
                    {"id": 1, "name": "Item 1", "value": 100},
                    {"id": 2, "name": "Item 2", "value": 200},
                ],
            },
        )

        # Verify cy_name was generated
        assert ku.component.cy_name is not None
        assert ku.component.cy_name.startswith("test_table")
        print(f"Created table KU with cy_name: {ku.component.cy_name}")

        # Try to create duplicate - should update
        ku2 = await repository.create_table_ku(
            tenant_id=tenant_id,
            data={
                "app": app,
                "name": "Test Table",
                "schema": {"columns": ["id", "name", "value", "extra"]},
                "data": [
                    {"id": 1, "name": "Item 1", "value": 150, "extra": "new"},
                ],
            },
        )

        # Should be same KU with updated data
        assert ku2.id == ku.id
        assert ku2.component.cy_name == ku.component.cy_name
        assert "extra" in ku2.schema["columns"]
        print(f"Updated table KU with same cy_name: {ku2.component.cy_name}")
