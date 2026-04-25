"""Integration tests for runbook matching composition path with DB-backed skills.

Proves that runbook matching substeps correctly load skill context from the database
using skill names (not cy_names), matching what substeps.py hardcodes.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
    create_analyze_gaps_substep,
)
from analysi.agentic_orchestration.langgraph.skills.context import (
    FileRequest,
    RetrievalDecision,
)
from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.agentic_orchestration.langgraph.skills.retrieval import retrieve
from analysi.agentic_orchestration.langgraph.substep.executor import execute_substep
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestPhase1CompositionWithDBSkills:
    """Verify runbook matching composition substeps work with DatabaseResourceStore.

    The critical thing being tested: substeps hardcode skills=["runbooks-manager"]
    (the human-readable name), and DatabaseResourceStore must resolve by name.
    """

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-phase1-db-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_runbooks_manager(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Seed a 'runbooks-manager' skill (matching substeps.py hardcoded name)."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        # Name matches what substeps.py uses: skills=["runbooks-manager"]
        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "runbooks-manager",
                "description": "Build, match, and manage security investigation runbooks",
                "cy_name": f"runbooks_manager_{uuid4().hex[:6]}",
            },
        )
        ns = f"/{skill.component.cy_name}/"

        # SKILL.md - root document
        doc_skill_md = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# runbooks-manager\n\n"
                    "Build, match, and manage security investigation runbooks.\n\n"
                    "## References\n"
                    "- `references/matching/composition-guide.md` - Composition guide\n"
                    "- `repository/sql-injection.md` - SQL injection runbook"
                ),
                "content": None,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id, skill.component_id, doc_skill_md.component_id, "SKILL.md"
        )

        # references/matching/composition-guide.md
        doc_guide = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "composition-guide.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# Composition Guide\n\n"
                    "Strategies for composing runbooks from multiple sources."
                ),
                "content": None,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            doc_guide.component_id,
            "references/matching/composition-guide.md",
        )

        # repository/sql-injection.md
        doc_runbook = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "sql-injection.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# SQL Injection Detection Runbook\n\n"
                    "## Investigation Steps\n"
                    "1. Check WAF logs\n"
                    "2. Review database query logs"
                ),
                "content": None,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            doc_runbook.component_id,
            "repository/sql-injection.md",
        )

        return {
            "skill_name": skill.component.name,
            "skill_cy_name": skill.component.cy_name,
            "skill_id": str(skill.component_id),
        }

    async def test_retrieve_loads_skill_context_from_db(
        self, session_factory, tenant_id, seeded_runbooks_manager
    ):
        """retrieve() finds 'runbooks-manager' by name in DB store."""
        mock_llm = MagicMock()
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        # Use the exact name substeps.py hardcodes
        context = await retrieve(
            store=store,
            initial_skills=["runbooks-manager"],
            task_input={"alert": {"title": "SQL Injection Detected"}},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        assert context.token_count > 0
        assert "runbooks-manager" in context.loaded
        assert "SKILL.md" in context.loaded["runbooks-manager"]
        assert "runbooks-manager" in context.loaded["runbooks-manager"]["SKILL.md"]

    async def test_retrieve_additional_files_by_name(
        self, session_factory, tenant_id, seeded_runbooks_manager
    ):
        """LLM can request additional files using skill name."""
        mock_llm = MagicMock()
        decisions = [
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(
                        skill="runbooks-manager",
                        path="references/matching/composition-guide.md",
                        reason="Need composition guide",
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
            initial_skills=["runbooks-manager"],
            task_input={"alert": {"title": "SQL Injection Detected"}},
            objective="Compose runbook",
            llm=mock_llm,
        )

        loaded = context.loaded["runbooks-manager"]
        assert "SKILL.md" in loaded
        assert "references/matching/composition-guide.md" in loaded
        assert "Composition Guide" in loaded["references/matching/composition-guide.md"]

    async def test_composition_substep_gets_db_context(
        self, session_factory, tenant_id, seeded_runbooks_manager
    ):
        """analyze_gaps substep loads context from DB via skill name."""
        from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
            Gap,
            GapAnalysisOutput,
        )

        mock_llm = MagicMock()

        # with_structured_output is called with different schemas:
        # - RetrievalDecision for retrieve()
        # - GapAnalysisOutput for substep execution
        mock_retrieval = AsyncMock()
        mock_retrieval.ainvoke.return_value = RetrievalDecision(has_enough=True)

        mock_gap = AsyncMock()
        mock_gap.ainvoke.return_value = GapAnalysisOutput(
            gaps=[
                Gap(
                    category="attack_vector",
                    description="Missing WAF-specific steps",
                    severity="medium",
                )
            ],
            coverage_assessment="Partial coverage of SQL injection patterns",
        )

        def structured_output_side_effect(schema):
            if schema is RetrievalDecision:
                return mock_retrieval
            return mock_gap

        mock_llm.with_structured_output.side_effect = structured_output_side_effect

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        substep = create_analyze_gaps_substep()
        # Verify substep uses the right skill name
        assert "runbooks-manager" in substep.skills

        state = {
            "alert": {"title": "SQL Injection Detected"},
            "matches": [{"runbook": "sql-injection.md", "score": 50}],
            "top_match": "repository/sql-injection.md (score: 50)",
            "top_score": 50,
            "score": 50,
        }

        result = await execute_substep(
            substep=substep,
            state=state,
            store=store,
            llm=mock_llm,
        )

        # Context was retrieved (substep has needs_context=True)
        assert result.context is not None
        assert "runbooks-manager" in result.context.loaded

    async def test_list_skills_returns_names_not_cy_names(
        self, session_factory, tenant_id, seeded_runbooks_manager
    ):
        """list_skills_async() returns names as keys, not cy_names."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        skills = await store.list_skills_async()

        # Key should be the human-readable name
        assert "runbooks-manager" in skills
        # cy_name should NOT be a key
        cy_name = seeded_runbooks_manager["skill_cy_name"]
        assert cy_name not in skills

    async def test_tree_async_uses_name(
        self, session_factory, tenant_id, seeded_runbooks_manager
    ):
        """tree_async() works when called with skill name."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        paths = await store.tree_async("runbooks-manager")

        assert len(paths) >= 3
        assert "SKILL.md" in paths
        assert "references/matching/composition-guide.md" in paths
        assert "repository/sql-injection.md" in paths


class _StubRunbookMatcher:
    """Minimal stand-in for the filesystem-based RunbookMatcher.

    Phase1Matcher.from_store() only needs a class that supports __new__()
    and has settable index_dir / runbooks_metadata attributes.
    """

    def __init__(self, index_dir=None):
        self.index_dir = index_dir
        self.runbooks_metadata = []

    def find_matches(self, alert, top_n=5):
        matches = []
        for rb in self.runbooks_metadata:
            if (
                alert.get("subcategory", "").lower()
                == rb.get("subcategory", "").lower()
            ):
                matches.append({"runbook": rb, "score": 90, "explanation": {}})
        return matches[:top_n]


@pytest.mark.asyncio
@pytest.mark.integration
class TestPhase1MatchPathWithDB:
    """Verify runbook match path reads index and runbooks from DB."""

    @pytest.fixture(autouse=True)
    def _mock_runbook_matcher(self):
        """Bypass filesystem import of match_scorer.py — DB tests don't need it.

        Sets the module-level _RunbookMatcher cache directly so that
        get_runbook_matcher() returns our stub without ever calling
        _get_runbook_matcher_class() (which does a filesystem lookup).
        """
        import analysi.agentic_orchestration.langgraph.kea.phase1.matcher as _mod

        saved = _mod._RunbookMatcher
        _mod._RunbookMatcher = _StubRunbookMatcher
        try:
            yield
        finally:
            _mod._RunbookMatcher = saved

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-match-db-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_with_index(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Seed a skill with KUTable index and KUDocument runbooks."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "runbooks-manager",
                "description": "Build, match, and manage security investigation runbooks",
                "cy_name": f"runbooks_manager_{uuid4().hex[:6]}",
            },
        )
        ns = f"/{skill.component.cy_name}/"

        # Seed index as KUTable at index/all_runbooks
        index_content = [
            {
                "filename": "sql-injection.md",
                "title": "SQL Injection Detection Runbook",
                "alert_type": "Intrusion",
                "subcategory": "SQL Injection",
                "detection_rules": ["WAF-SQLi-001"],
                "source_category": "WAF",
                "mitre_tactics": ["TA0001"],
            },
            {
                "filename": "phishing.md",
                "title": "Phishing Email Investigation Runbook",
                "alert_type": "Phishing",
                "subcategory": "Email Phishing",
                "detection_rules": ["EMAIL-PHISH-001"],
                "source_category": "Email",
                "mitre_tactics": ["TA0001"],
            },
        ]

        index_table = await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": "all_runbooks",
                "content": index_content,
                "schema": {},
                "row_count": len(index_content),
                "column_count": 0,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            index_table.component_id,
            "index/all_runbooks",
        )

        # Seed runbook documents
        doc_sqli = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "sql-injection.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# SQL Injection Detection Runbook\n\n"
                    "## Investigation Steps\n"
                    "1. Review WAF logs for injection patterns\n"
                    "2. Check database query logs"
                ),
                "content": None,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            doc_sqli.component_id,
            "repository/sql-injection.md",
        )

        doc_phish = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "phishing.md",
                "doc_format": "markdown",
                "markdown_content": (
                    "# Phishing Email Investigation Runbook\n\n"
                    "## Investigation Steps\n"
                    "1. Analyze email headers\n"
                    "2. Check sender reputation"
                ),
                "content": None,
            },
            namespace=ns,
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            doc_phish.component_id,
            "repository/phishing.md",
        )

        return {
            "skill_id": str(skill.component_id),
            "skill_name": skill.component.name,
        }

    async def test_read_table_loads_index_from_db(
        self, session_factory, tenant_id, seeded_with_index
    ):
        """read_table_async loads runbook index KUTable from DB."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        index = await store.read_table_async("runbooks-manager", "index/all_runbooks")

        assert index is not None
        assert isinstance(index, list)
        assert len(index) == 2
        filenames = [r["filename"] for r in index]
        assert "sql-injection.md" in filenames
        assert "phishing.md" in filenames

    async def test_matcher_from_store_loads_index(
        self, session_factory, tenant_id, seeded_with_index
    ):
        """Phase1Matcher.from_store() loads index from DB store."""
        from analysi.agentic_orchestration.langgraph.kea.phase1.matcher import (
            Phase1Matcher,
        )

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        matcher = await Phase1Matcher.from_store(store)

        assert len(matcher._matcher.runbooks_metadata) == 2

    async def test_fetch_runbook_from_db(
        self, session_factory, tenant_id, seeded_with_index
    ):
        """Runbook content loaded from DB via async method."""
        from analysi.agentic_orchestration.langgraph.kea.phase1.matcher import (
            Phase1Matcher,
        )

        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )
        matcher = await Phase1Matcher.from_store(store)

        content = await matcher.get_runbook_content_async("sql-injection.md")
        assert "SQL Injection Detection" in content
        assert "WAF logs" in content

    async def test_write_document_stores_runbook(
        self, session_factory, tenant_id, seeded_with_index
    ):
        """write_document_async creates a new KUDocument in DB."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        written = await store.write_document_async(
            "runbooks-manager",
            "repository/new-composed.md",
            "# New Composed Runbook\n\nInvestigation steps here.",
            metadata={"source": "phase1_composition"},
        )
        assert written is True

        # Verify it can be read back
        content = await store.read_async(
            "runbooks-manager", "repository/new-composed.md"
        )
        assert content is not None
        assert "New Composed Runbook" in content

    async def test_write_table_updates_index(
        self, session_factory, tenant_id, seeded_with_index
    ):
        """write_table_async updates the runbook index KUTable."""
        store = DatabaseResourceStore(
            session_factory=session_factory, tenant_id=tenant_id
        )

        # Read current index
        index = await store.read_table_async("runbooks-manager", "index/all_runbooks")
        assert len(index) == 2

        # Append new entry and write back
        index.append(
            {
                "filename": "new-composed.md",
                "title": "New Composed Runbook",
                "source": "composed",
            }
        )
        written = await store.write_table_async(
            "runbooks-manager", "index/all_runbooks", index
        )
        assert written is True

        # Verify updated
        updated = await store.read_table_async("runbooks-manager", "index/all_runbooks")
        assert len(updated) == 3
        assert updated[2]["filename"] == "new-composed.md"
