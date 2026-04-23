"""Tests for DatabaseResourceStore."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)


class TestDatabaseResourceStore:
    """Tests for DatabaseResourceStore."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock async session factory."""
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return factory, session

    @pytest.fixture
    def store(self, mock_session_factory):
        """Create DatabaseResourceStore with mocked session."""
        factory, _ = mock_session_factory
        return DatabaseResourceStore(session_factory=factory, tenant_id="test-tenant")

    def test_sync_methods_raise_not_implemented(self, store):
        """Sync methods raise NotImplementedError for database store."""
        with pytest.raises(NotImplementedError):
            store.list_skills()

        with pytest.raises(NotImplementedError):
            store.tree("some-skill")

        with pytest.raises(NotImplementedError):
            store.read("some-skill", "file.md")

    @pytest.mark.asyncio
    async def test_list_skills_async_returns_names(self, mock_session_factory):
        """list_skills_async returns name -> description mapping."""
        factory, session = mock_session_factory

        module1 = MagicMock()
        module1.component.name = "skill-alpha"
        module1.component.description = "Alpha skill"

        module2 = MagicMock()
        module2.component.name = "skill-beta"
        module2.component.description = "Beta skill"

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.list_skills.return_value = ([module1, module2], {"total": 2})
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.list_skills_async()

        assert result == {"skill-alpha": "Alpha skill", "skill-beta": "Beta skill"}

    @pytest.mark.asyncio
    async def test_tree_async_returns_namespace_paths(self, mock_session_factory):
        """tree_async returns sorted namespace paths from DB."""
        factory, session = mock_session_factory

        module = MagicMock()
        module.component_id = "uuid-1"

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.get_skill_tree.return_value = [
                {"path": "references/guide.md", "document_id": "doc-1"},
                {"path": "SKILL.md", "document_id": "doc-2"},
            ]
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.tree_async("skill_alpha")

        assert result == ["SKILL.md", "references/guide.md"]

    @pytest.mark.asyncio
    async def test_tree_async_returns_empty_for_unknown_skill(
        self, mock_session_factory
    ):
        """tree_async returns empty list for unknown skill."""
        factory, session = mock_session_factory

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = None
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.tree_async("unknown_skill")

        assert result == []

    @pytest.mark.asyncio
    async def test_read_async_returns_content(self, mock_session_factory):
        """read_async returns markdown_content from DB."""
        factory, session = mock_session_factory

        module = MagicMock()
        module.component_id = "uuid-1"

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.read_skill_file.return_value = {
                "path": "SKILL.md",
                "markdown_content": "# My Skill\nContent here",
                "content": None,
            }
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.read_async("skill_alpha", "SKILL.md")

        assert result == "# My Skill\nContent here"

    @pytest.mark.asyncio
    async def test_read_async_falls_back_to_content(self, mock_session_factory):
        """read_async uses content field when markdown_content is None."""
        factory, session = mock_session_factory

        module = MagicMock()
        module.component_id = "uuid-1"

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.read_skill_file.return_value = {
                "path": "SKILL.md",
                "markdown_content": None,
                "content": "raw content",
            }
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.read_async("skill_alpha", "SKILL.md")

        assert result == "raw content"

    @pytest.mark.asyncio
    async def test_read_async_returns_none_for_unknown_skill(
        self, mock_session_factory
    ):
        """read_async returns None for unknown skill."""
        factory, session = mock_session_factory

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = None
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.read_async("unknown", "SKILL.md")

        assert result is None

    @pytest.mark.asyncio
    async def test_read_table_async_returns_content(self, mock_session_factory):
        """read_table_async returns table content from DB."""
        factory, session = mock_session_factory

        module = MagicMock()
        module.component_id = "uuid-1"

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.read_skill_table.return_value = {
                "path": "index/all_runbooks",
                "content": [{"filename": "sql-injection.md", "title": "SQL Injection"}],
                "schema": {},
            }
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.read_table_async(
                "runbooks-manager", "index/all_runbooks"
            )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["filename"] == "sql-injection.md"

    @pytest.mark.asyncio
    async def test_read_table_async_returns_none_for_unknown(
        self, mock_session_factory
    ):
        """read_table_async returns None when skill not found."""
        factory, session = mock_session_factory

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = None
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.read_table_async("unknown", "index/all_runbooks")

        assert result is None

    @pytest.mark.asyncio
    async def test_write_document_async_creates_document(self, mock_session_factory):
        """write_document_async writes document via repo."""
        factory, session = mock_session_factory
        from uuid import uuid4

        module = MagicMock()
        module.component_id = uuid4()

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.write_skill_file.return_value = uuid4()
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.write_document_async(
                "runbooks-manager", "repository/new-runbook.md", "# New Runbook"
            )

        assert result is True
        repo_instance.write_skill_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_document_async_returns_false_for_unknown_skill(
        self, mock_session_factory
    ):
        """write_document_async returns False when skill not found."""
        factory, session = mock_session_factory

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = None
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.write_document_async("unknown", "path.md", "content")

        assert result is False

    @pytest.mark.asyncio
    async def test_write_table_async_writes_table(self, mock_session_factory):
        """write_table_async writes table via repo."""
        factory, session = mock_session_factory
        from uuid import uuid4

        module = MagicMock()
        module.component_id = uuid4()

        with patch(
            "analysi.agentic_orchestration.langgraph.skills.db_store.KnowledgeModuleRepository"
        ) as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_skill_by_name.return_value = module
            repo_instance.write_skill_table.return_value = uuid4()
            MockRepo.return_value = repo_instance

            store = DatabaseResourceStore(
                session_factory=factory, tenant_id="test-tenant"
            )
            result = await store.write_table_async(
                "runbooks-manager", "index/all_runbooks", [{"filename": "test.md"}]
            )

        assert result is True
        repo_instance.write_skill_table.assert_called_once()


class TestGetDbSkillsStore:
    """Tests for get_db_skills_store config function."""

    def test_returns_database_resource_store(self):
        """get_db_skills_store returns a DatabaseResourceStore."""
        with patch("analysi.db.session.AsyncSessionLocal"):
            from analysi.agentic_orchestration.langgraph.config import (
                get_db_skills_store,
            )

            store = get_db_skills_store("test-tenant")
            assert isinstance(store, DatabaseResourceStore)
