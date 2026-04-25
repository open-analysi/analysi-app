"""Integration tests for SkillsIR retrieve() with DatabaseResourceStore.

Proves that the full SkillsIR retrieval loop works end-to-end with
DB-backed skills (real PostgreSQL) and a mocked LLM.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.langgraph.skills.context import (
    FileRequest,
    RetrievalDecision,
)
from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.agentic_orchestration.langgraph.skills.retrieval import retrieve
from analysi.models.component import Component
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.knowledge_module import KnowledgeModuleService


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillsIRWithDatabaseStore:
    """End-to-end tests: retrieve() + DatabaseResourceStore + mocked LLM."""

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-skillsir-db-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_skills(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Create 2 skills with documents in the database."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        # --- Skill 1: runbooks-test (with WikiLinks) ---
        skill1_cy = f"runbooks_test_{uuid4().hex[:6]}"
        skill1 = await km_repo.create_skill(
            tenant_id,
            {
                "name": "Runbooks Test",
                "description": "Test skill with runbook content and WikiLinks",
                "cy_name": skill1_cy,
            },
        )
        ns1 = f"/{skill1_cy}/"

        # SKILL.md
        doc_skill_md = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# Runbooks Test\n\n"
                    "A test skill for SkillsIR DB integration.\n\n"
                    "## References\n"
                    "- `references/guide.md` - Matching guide\n"
                    "- `repository/sql-injection.md` - SQL injection runbook"
                ),
                "content": None,
            },
            namespace=ns1,
        )
        await km_repo.add_document_to_skill(
            tenant_id, skill1.component_id, doc_skill_md.component_id, "SKILL.md"
        )

        # references/guide.md
        doc_guide = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "guide.md",
                "doc_format": "markdown",
                "markdown_content": "# Matching Guide\n\nHow to match alerts to runbooks.",
                "content": None,
            },
            namespace=ns1,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill1.component_id,
            doc_guide.component_id,
            "references/guide.md",
        )

        # common/header.md (for WikiLink expansion)
        doc_header = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "header.md",
                "doc_format": "markdown",
                "markdown_content": "## Standard Investigation Header\n\nAlways start here.",
                "content": None,
            },
            namespace=ns1,
        )
        await km_repo.add_document_to_skill(
            tenant_id, skill1.component_id, doc_header.component_id, "common/header.md"
        )

        # repository/sql-injection.md (with WikiLink to common/header.md)
        doc_runbook = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "sql-injection.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# SQL Injection Runbook\n\n"
                    "![[common/header.md]]\n\n"
                    "## SQL-Specific Steps\n"
                    "Check for injection patterns."
                ),
                "content": None,
            },
            namespace=ns1,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill1.component_id,
            doc_runbook.component_id,
            "repository/sql-injection.md",
        )

        # --- Skill 2: enrichment-test ---
        skill2_cy = f"enrichment_test_{uuid4().hex[:6]}"
        skill2 = await km_repo.create_skill(
            tenant_id,
            {
                "name": "Enrichment Test",
                "description": "Test skill for enrichment patterns",
                "cy_name": skill2_cy,
            },
        )
        ns2 = f"/{skill2_cy}/"

        # Both skills can now have a doc named "SKILL.md" thanks to namespace
        doc_enrich = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": "# Enrichment Test\n\nEnrichment patterns skill.",
                "content": None,
            },
            namespace=ns2,
        )
        await km_repo.add_document_to_skill(
            tenant_id, skill2.component_id, doc_enrich.component_id, "SKILL.md"
        )

        return {
            "skill1_name": skill1.component.name,
            "skill2_name": skill2.component.name,
            "skill1_cy_name": skill1.component.cy_name,
            "skill2_cy_name": skill2.component.cy_name,
            "skill1_id": str(skill1.component_id),
            "skill2_id": str(skill2.component_id),
        }

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    async def test_db_store_reads_correct_skill(
        self, session_factory, tenant_id, seeded_skills
    ):
        """Sanity check: DatabaseResourceStore reads the correct SKILL.md for each skill."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        name1 = seeded_skills["skill1_name"]
        name2 = seeded_skills["skill2_name"]

        content1 = await store.read_async(name1, "SKILL.md")
        content2 = await store.read_async(name2, "SKILL.md")

        assert content1 is not None, f"SKILL.md not found for {name1}"
        assert content2 is not None, f"SKILL.md not found for {name2}"
        assert "Runbooks Test" in content1, (
            f"Expected 'Runbooks Test' in skill1, got: {content1[:100]}"
        )
        assert "Enrichment Test" in content2, (
            f"Expected 'Enrichment Test' in skill2, got: {content2[:100]}"
        )

    async def test_retrieve_immediate_success(
        self, session_factory, tenant_id, seeded_skills, mock_llm
    ):
        """retrieve() loads SKILL.md from DB when LLM says has_enough immediately."""
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        skill1_name = seeded_skills["skill1_name"]

        context = await retrieve(
            store=store,
            initial_skills=[skill1_name],
            task_input={"alert": "test"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        assert context.token_count > 0
        assert skill1_name in context.loaded
        assert "SKILL.md" in context.loaded[skill1_name]
        assert "Runbooks Test" in context.loaded[skill1_name]["SKILL.md"]

    async def test_retrieve_one_iteration(
        self, session_factory, tenant_id, seeded_skills, mock_llm
    ):
        """retrieve() loads additional files from DB when LLM requests them."""
        name = seeded_skills["skill1_name"]

        decisions = [
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(
                        skill=name, path="references/guide.md", reason="Need guide"
                    )
                ],
            ),
            RetrievalDecision(has_enough=True),
        ]
        mock_structured = AsyncMock()
        mock_structured.ainvoke.side_effect = decisions
        mock_llm.with_structured_output.return_value = mock_structured

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        context = await retrieve(
            store=store,
            initial_skills=[name],
            task_input={"alert": "SQL injection detected"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        assert "SKILL.md" in context.loaded[name]
        assert "references/guide.md" in context.loaded[name]
        assert "How to match alerts" in context.loaded[name]["references/guide.md"]

    async def test_retrieve_wikilink_expansion(
        self, session_factory, tenant_id, seeded_skills, mock_llm
    ):
        """retrieve() expands WikiLinks in DB-backed files."""
        name = seeded_skills["skill1_name"]

        decisions = [
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(
                        skill=name,
                        path="repository/sql-injection.md",
                        reason="Need runbook",
                    )
                ],
            ),
            RetrievalDecision(has_enough=True),
        ]
        mock_structured = AsyncMock()
        mock_structured.ainvoke.side_effect = decisions
        mock_llm.with_structured_output.return_value = mock_structured

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        context = await retrieve(
            store=store,
            initial_skills=[name],
            task_input={"alert": "SQL injection detected"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        runbook_content = context.loaded[name]["repository/sql-injection.md"]

        # WikiLinks should be expanded
        assert "![[" not in runbook_content, "WikiLinks should be expanded"
        # Expanded content should be present
        assert "Standard Investigation Header" in runbook_content
        assert "Always start here" in runbook_content
        # Original content preserved
        assert "SQL Injection Runbook" in runbook_content
        assert "SQL-Specific Steps" in runbook_content

    async def test_retrieve_registry_has_all_skills(
        self, session_factory, tenant_id, seeded_skills, mock_llm
    ):
        """retrieve() populates registry with all DB skills for the tenant."""
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        context = await retrieve(
            store=store,
            initial_skills=[seeded_skills["skill1_name"]],
            task_input={"alert": "test"},
            objective="test",
            llm=mock_llm,
        )

        # Registry should contain both skills (keyed by name now)
        assert seeded_skills["skill1_name"] in context.registry
        assert seeded_skills["skill2_name"] in context.registry

    async def test_add_document_auto_sets_namespace(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """When linking a document to a skill via service, namespace is auto-set."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        # Create a skill
        skill_cy = f"ns_test_{uuid4().hex[:6]}"
        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "Namespace Test Skill",
                "cy_name": skill_cy,
            },
        )

        # Create a document with default namespace
        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "test-doc.md",
                "doc_format": "markdown",
                "markdown_content": "test content",
                "content": None,
            },
        )
        assert doc.component.namespace == "/"

        # Link via service (not repo directly)
        service = KnowledgeModuleService(session)
        await service.add_document(
            tenant_id, skill.component_id, doc.component_id, "test-doc.md"
        )

        # Refresh and verify namespace was auto-set
        from sqlalchemy import select

        stmt = select(Component).where(Component.id == doc.component_id)
        result = await session.execute(stmt)
        updated_component = result.scalar_one()
        assert updated_component.namespace == f"/{skill_cy}/"
