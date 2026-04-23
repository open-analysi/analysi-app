"""Integration tests for DatabaseResourceStore.

Verifies that DatabaseResourceStore correctly reads skills and documents
from the database via KnowledgeModuleRepository.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestDatabaseResourceStoreIntegration:
    """Integration tests for DatabaseResourceStore with real PostgreSQL."""

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-dbstore-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        """Create a session factory for DatabaseResourceStore."""
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_skill(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Create a skill with 2 documents in the database."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        # Create skill
        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "Test Skill Alpha",
                "description": "A test skill for DB store integration",
                "cy_name": f"test_skill_alpha_{uuid4().hex[:6]}",
            },
        )

        # Create document 1 (markdown)
        doc1 = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": "# Test Skill Alpha\n\nThis is the main skill file.",
                "content": None,
            },
        )

        # Create document 2 (raw code)
        doc2 = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "references/helper.py",
                "doc_format": "raw",
                "content": "def helper():\n    return 42",
                "markdown_content": None,
            },
        )

        # Link documents to skill
        await km_repo.add_document_to_skill(
            tenant_id, skill.component_id, doc1.component_id, "SKILL.md"
        )
        await km_repo.add_document_to_skill(
            tenant_id, skill.component_id, doc2.component_id, "references/helper.py"
        )

        return {
            "skill": skill,
            "name": skill.component.name,
            "cy_name": skill.component.cy_name,
            "doc1": doc1,
            "doc2": doc2,
        }

    async def test_list_skills_async(self, session_factory, tenant_id, seeded_skill):
        """list_skills_async returns seeded skill with description."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        skills = await store.list_skills_async()

        assert seeded_skill["name"] in skills
        assert skills[seeded_skill["name"]] == "A test skill for DB store integration"

    async def test_tree_async(self, session_factory, tenant_id, seeded_skill):
        """tree_async returns sorted namespace paths."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        tree = await store.tree_async(seeded_skill["name"])

        assert tree == ["SKILL.md", "references/helper.py"]

    async def test_read_async_markdown(self, session_factory, tenant_id, seeded_skill):
        """read_async returns markdown_content for markdown files."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        content = await store.read_async(seeded_skill["name"], "SKILL.md")

        assert content == "# Test Skill Alpha\n\nThis is the main skill file."

    async def test_read_async_raw(self, session_factory, tenant_id, seeded_skill):
        """read_async falls back to content field for raw files."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        content = await store.read_async(seeded_skill["name"], "references/helper.py")

        assert content == "def helper():\n    return 42"

    async def test_read_async_unknown_path(
        self, session_factory, tenant_id, seeded_skill
    ):
        """read_async returns None for non-existent path."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        content = await store.read_async(seeded_skill["name"], "nonexistent.md")

        assert content is None

    async def test_tree_async_unknown_skill(self, session_factory, tenant_id):
        """tree_async returns empty list for unknown skill."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        tree = await store.tree_async("nonexistent-skill")

        assert tree == []
