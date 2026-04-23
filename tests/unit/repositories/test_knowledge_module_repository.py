"""Unit tests for KnowledgeModuleRepository."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import ComponentKind
from analysi.models.kdg_edge import EdgeType
from analysi.models.knowledge_module import ModuleType
from analysi.repositories.knowledge_module import KnowledgeModuleRepository


class TestKnowledgeModuleRepository:
    """Test KnowledgeModuleRepository operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create a KnowledgeModuleRepository instance with mock session."""
        return KnowledgeModuleRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_skill_generates_cy_name(self, repository, mock_session):
        """Test that create_skill generates cy_name if not provided."""
        tenant_id = "test-tenant"
        skill_data = {
            "name": "Test Skill",
            "description": "A test skill",
            "app": "default",
        }

        # Mock the component repository
        with patch(
            "analysi.repositories.knowledge_module.ComponentRepository"
        ) as MockCompRepo:
            mock_comp_repo = MagicMock()
            mock_comp_repo.generate_cy_name.return_value = "test_skill"
            mock_comp_repo.ensure_unique_cy_name = AsyncMock(return_value="test_skill")
            MockCompRepo.return_value = mock_comp_repo

            # Mock flush and commit
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_session.add = MagicMock()

            await repository.create_skill(tenant_id, skill_data)

            # Verify cy_name was generated
            mock_comp_repo.generate_cy_name.assert_called_once_with(
                "Test Skill", "skill"
            )
            mock_comp_repo.ensure_unique_cy_name.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skill_uses_provided_cy_name(self, repository, mock_session):
        """Test that create_skill uses provided cy_name."""
        tenant_id = "test-tenant"
        skill_data = {
            "name": "Test Skill",
            "description": "A test skill",
            "app": "default",
            "cy_name": "custom_cy_name",
        }

        # Mock the select query for cy_name check
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # cy_name doesn't exist
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        await repository.create_skill(tenant_id, skill_data)

        # Verify session.add was called (component and module)
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_get_skill_by_id_returns_module(self, repository, mock_session):
        """Test get_skill_by_id returns module when found."""
        component_id = uuid4()
        tenant_id = "test-tenant"

        # Create mock module
        mock_module = MagicMock()
        mock_module.component = MagicMock()
        mock_module.component.id = component_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_module
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.refresh = AsyncMock()

        result = await repository.get_skill_by_id(component_id, tenant_id)

        assert result == mock_module
        mock_session.refresh.assert_called_once_with(mock_module, ["component"])

    @pytest.mark.asyncio
    async def test_get_skill_by_id_returns_none_when_not_found(
        self, repository, mock_session
    ):
        """Test get_skill_by_id returns None when module not found."""
        component_id = uuid4()
        tenant_id = "test-tenant"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await repository.get_skill_by_id(component_id, tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_skills_with_search(self, repository, mock_session):
        """Test list_skills with search filter."""
        tenant_id = "test-tenant"

        # Mock modules
        mock_modules = [MagicMock(), MagicMock()]
        for m in mock_modules:
            m.component = MagicMock()

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        # Mock list query
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = mock_modules

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )
        mock_session.refresh = AsyncMock()

        modules, meta = await repository.list_skills(
            tenant_id=tenant_id, search="test", skip=0, limit=10
        )

        assert len(modules) == 2
        assert meta["total"] == 2

    @pytest.mark.asyncio
    async def test_delete_skill_returns_true_when_found(self, repository, mock_session):
        """Test delete_skill returns True when skill found and deleted."""
        component_id = uuid4()
        tenant_id = "test-tenant"

        mock_component = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_component
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.expunge_all = MagicMock()

        result = await repository.delete_skill(component_id, tenant_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_component)

    @pytest.mark.asyncio
    async def test_delete_skill_returns_false_when_not_found(
        self, repository, mock_session
    ):
        """Test delete_skill returns False when skill not found."""
        component_id = uuid4()
        tenant_id = "test-tenant"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await repository.delete_skill(component_id, tenant_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_add_document_to_skill_creates_edge(self, repository, mock_session):
        """Test add_document_to_skill creates 'contains' edge."""
        tenant_id = "test-tenant"
        skill_id = uuid4()
        document_id = uuid4()
        namespace_path = "references/api.md"

        # Mock path check (no existing document at path)
        mock_path_result = MagicMock()
        mock_path_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_path_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        await repository.add_document_to_skill(
            tenant_id, skill_id, document_id, namespace_path
        )

        mock_session.add.assert_called_once()
        # Verify the edge was created with correct data
        added_edge = mock_session.add.call_args[0][0]
        assert added_edge.tenant_id == tenant_id
        assert added_edge.source_id == skill_id
        assert added_edge.target_id == document_id
        assert added_edge.relationship_type == EdgeType.CONTAINS
        assert added_edge.edge_metadata["namespace_path"] == namespace_path

    @pytest.mark.asyncio
    async def test_add_document_to_skill_raises_on_path_conflict(
        self, repository, mock_session
    ):
        """Test add_document_to_skill raises ValueError on path conflict."""
        tenant_id = "test-tenant"
        skill_id = uuid4()
        document_id = uuid4()
        existing_doc_id = uuid4()
        namespace_path = "references/api.md"

        # Mock: first call (_find_edge) returns None (no existing edge)
        # second call (_get_document_at_path) returns existing_doc_id (path conflict)
        mock_edge_result = MagicMock()
        mock_edge_result.scalar_one_or_none.return_value = None

        mock_path_result = MagicMock()
        mock_path_result.scalar_one_or_none.return_value = existing_doc_id

        mock_session.execute = AsyncMock(
            side_effect=[mock_edge_result, mock_path_result]
        )

        with pytest.raises(ValueError) as exc_info:
            await repository.add_document_to_skill(
                tenant_id, skill_id, document_id, namespace_path
            )

        assert "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_skill_tree_returns_paths(self, repository, mock_session):
        """Test get_skill_tree returns list of namespace paths."""
        tenant_id = "test-tenant"
        skill_id = uuid4()

        # Mock edges
        mock_edge1 = MagicMock()
        mock_edge1.edge_metadata = {"namespace_path": "SKILL.md"}
        mock_edge1.target_id = uuid4()

        mock_edge2 = MagicMock()
        mock_edge2.edge_metadata = {"namespace_path": "references/api.md"}
        mock_edge2.target_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_edge1, mock_edge2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        tree = await repository.get_skill_tree(tenant_id, skill_id)

        assert len(tree) == 2
        assert tree[0]["path"] == "SKILL.md"
        assert tree[1]["path"] == "references/api.md"

    @pytest.mark.asyncio
    async def test_check_skill_delete_counts_relationships(
        self, repository, mock_session
    ):
        """Test check_skill_delete counts affected relationships."""
        component_id = uuid4()
        tenant_id = "test-tenant"

        # Mock count queries (documents, includes, depends_on)
        mock_doc_count = MagicMock()
        mock_doc_count.scalar.return_value = 3

        mock_includes_count = MagicMock()
        mock_includes_count.scalar.return_value = 1

        mock_depends_count = MagicMock()
        mock_depends_count.scalar.return_value = 0

        mock_session.execute = AsyncMock(
            side_effect=[mock_doc_count, mock_includes_count, mock_depends_count]
        )

        result = await repository.check_skill_delete(component_id, tenant_id)

        assert result["contained_documents"] == 3
        assert result["skills_including_this"] == 1
        assert result["skills_depending_on_this"] == 0
        assert result["can_delete"] is True
        assert len(result["warnings"]) == 2  # Has warnings for includes


class TestModuleTypeConstants:
    """Test ModuleType constants."""

    def test_module_type_skill(self):
        """Test that SKILL constant is defined correctly."""
        assert ModuleType.SKILL == "skill"


class TestComponentKindModule:
    """Test ComponentKind MODULE constant."""

    def test_component_kind_module(self):
        """Test that MODULE constant is defined correctly."""
        assert ComponentKind.MODULE == "module"


class TestSkillLookupAppFiltering:
    """Regression tests: skill/task lookups must work regardless of app value.

    Bug found in Delos: get_skill_by_name defaulted to app='default' but
    content packs install skills with app='foundation', causing all skill
    lookups to fail with 'Skill not found in database'.
    """

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        return KnowledgeModuleRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_skill_by_name_no_app_filter_by_default(
        self, repository, mock_session
    ):
        """get_skill_by_name without app arg must NOT filter by app."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repository.get_skill_by_name("tenant-1", "cy-language-programming")

        # Inspect the SQL query that was built
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        # Must NOT contain app filter when no app specified
        assert "app" not in compiled.lower() or "app =" not in compiled, (
            f"get_skill_by_name should not filter by app when app=None. Query: {compiled}"
        )

    @pytest.mark.asyncio
    async def test_get_skill_by_name_with_explicit_app_filters(
        self, repository, mock_session
    ):
        """get_skill_by_name with explicit app must filter by it."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repository.get_skill_by_name("tenant-1", "my-skill", app="foundation")

        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "foundation" in compiled, (
            f"get_skill_by_name with app='foundation' should filter by it. Query: {compiled}"
        )

    @pytest.mark.asyncio
    async def test_get_skill_by_cy_name_no_app_filter_by_default(
        self, repository, mock_session
    ):
        """get_skill_by_cy_name without app arg must NOT filter by app."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repository.get_skill_by_cy_name("tenant-1", "cy_language_programming")

        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "app" not in compiled.lower() or "app =" not in compiled, (
            f"get_skill_by_cy_name should not filter by app when app=None. Query: {compiled}"
        )
