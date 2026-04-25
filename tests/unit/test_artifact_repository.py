"""
Unit tests for ArtifactRepository.

Tests repository operations with mocked database session.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from analysi.models.artifact import Artifact
from analysi.repositories.artifact_repository import ArtifactRepository


@pytest.fixture
def mock_session():
    """Mock AsyncSession for testing."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def artifact_repository(mock_session):
    """ArtifactRepository instance with mocked session."""
    return ArtifactRepository(mock_session)


@pytest.mark.unit
class TestArtifactRepository:
    """Test suite for ArtifactRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_artifact_success(self, artifact_repository, mock_session):
        """Test successful artifact creation."""
        artifact_data = {
            "tenant_id": "test-tenant",
            "name": "Test Artifact",
            "artifact_type": "timeline",
            "mime_type": "application/json",
            "tags": ["test", "timeline"],
            "sha256": b"hash123hash123hash123hash123h",  # 32 bytes
            "size_bytes": 1024,
            "storage_class": "inline",
            "inline_content": b'{"test": "data"}',
            "task_run_id": uuid4(),
        }

        # Mock the Artifact constructor
        mock_artifact = Mock(spec=Artifact)
        mock_artifact.id = uuid4()

        with patch(
            "analysi.repositories.artifact_repository.Artifact",
            return_value=mock_artifact,
        ):
            result = await artifact_repository.create(artifact_data)

            # Verify calls
            mock_session.add.assert_called_once_with(mock_artifact)
            mock_session.flush.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_artifact)
            assert result == mock_artifact

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, artifact_repository, mock_session):
        """Test successful artifact retrieval by ID."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        # Mock query result
        mock_artifact = Mock(spec=Artifact)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_artifact
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.get_by_id(tenant_id, artifact_id)

        # Verify result
        assert result == mock_artifact
        mock_session.execute.assert_called_once()

        # Verify query was built correctly (check the call arguments)
        mock_session.execute.call_args[0][0]
        # We can't easily inspect the SQLAlchemy query, so just verify it was called

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, artifact_repository, mock_session):
        """Test artifact retrieval when not found."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        # Mock empty result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.get_by_id(tenant_id, artifact_id)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_artifacts_with_pagination(
        self, artifact_repository, mock_session
    ):
        """Test artifact listing with pagination."""
        tenant_id = "test-tenant"
        filters = {"artifact_type": "timeline"}
        limit = 10
        offset = 0
        sort_by = "created_at"
        sort_order = "desc"

        # Mock artifacts list
        mock_artifacts = [Mock(spec=Artifact) for _ in range(3)]
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_artifacts
        mock_session.execute.return_value = mock_result

        # Mock count result
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 25

        # Configure execute to return different results for different calls
        call_count = 0

        def mock_execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Count query
                return mock_count_result
            # List query
            return mock_result

        mock_session.execute.side_effect = mock_execute_side_effect

        artifacts, total = await artifact_repository.list(
            tenant_id, filters, limit, offset, sort_by, sort_order
        )

        assert artifacts == mock_artifacts
        assert total == 25
        assert mock_session.execute.call_count == 2  # Count + list queries

    @pytest.mark.asyncio
    async def test_soft_delete_success(self, artifact_repository, mock_session):
        """Test successful soft delete operation."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        # Mock existing artifact
        mock_artifact = Mock(spec=Artifact)
        mock_artifact.deleted_at = None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_artifact
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.soft_delete(tenant_id, artifact_id)

        # Verify artifact was marked as deleted (deleted_at set to a datetime)
        assert mock_artifact.deleted_at is not None
        assert result is True
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_not_found(self, artifact_repository, mock_session):
        """Test soft delete when artifact not found."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        # Mock empty result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.soft_delete(tenant_id, artifact_id)

        assert result is False
        mock_session.commit.assert_not_called()


@pytest.mark.unit
class TestArtifactRepositoryFilters:
    """Tests for all list filter parameters."""

    def _mock_list_execute(self, mock_session, artifacts, total):
        """Helper to set up mock session.execute for list() calls (count + list)."""
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = total

        mock_list_result = Mock()
        mock_list_result.scalars.return_value.all.return_value = artifacts

        call_count = 0

        def side_effect(query):
            nonlocal call_count
            call_count += 1
            return mock_count_result if call_count == 1 else mock_list_result

        mock_session.execute.side_effect = side_effect

    @pytest.mark.asyncio
    async def test_list_with_name_filter(self, artifact_repository, mock_session):
        """Name filter uses ilike partial match."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"name": "timeline"})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_alert_id_filter(self, artifact_repository, mock_session):
        """alert_id filter is supported."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"alert_id": uuid4()})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_mime_type_filter(self, artifact_repository, mock_session):
        """mime_type filter is supported."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"mime_type": "application/json"})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_storage_class_filter(
        self, artifact_repository, mock_session
    ):
        """storage_class filter is supported."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"storage_class": "inline"})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_integration_id_filter(
        self, artifact_repository, mock_session
    ):
        """integration_id filter is supported."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"integration_id": "virustotal-prod"})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_source_filter(self, artifact_repository, mock_session):
        """source filter is supported."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list("t", {"source": "cy_script"})
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_multiple_filters(self, artifact_repository, mock_session):
        """Multiple filters can be combined."""
        self._mock_list_execute(mock_session, [], 0)
        await artifact_repository.list(
            "t",
            {
                "artifact_type": "timeline",
                "source": "auto_capture",
                "storage_class": "inline",
            },
        )
        assert mock_session.execute.call_count == 2


@pytest.mark.unit
class TestArtifactRepositoryQueryMethods:
    """Tests for get_by_workflow_run, get_by_analysis, get_storage_stats."""

    @pytest.mark.asyncio
    async def test_get_by_workflow_run(self, artifact_repository, mock_session):
        """Calls execute and returns list of artifacts."""
        wf_run_id = uuid4()
        mock_artifacts = [Mock(spec=Artifact), Mock(spec=Artifact)]
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_artifacts
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.get_by_workflow_run("t", wf_run_id)

        assert result == mock_artifacts
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_analysis(self, artifact_repository, mock_session):
        """Calls execute and returns list of artifacts."""
        analysis_id = uuid4()
        mock_artifacts = [Mock(spec=Artifact)]
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_artifacts
        mock_session.execute.return_value = mock_result

        result = await artifact_repository.get_by_analysis("t", analysis_id)

        assert result == mock_artifacts
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_storage_stats(self, artifact_repository, mock_session):
        """Returns aggregated stats dict."""
        mock_row = Mock()
        mock_row.total = 10
        mock_row.total_size = 5000
        mock_row.inline_count = 8
        mock_row.inline_size = 3000
        mock_row.object_count = 2
        mock_row.object_size = 2000
        mock_result = Mock()
        mock_result.one.return_value = mock_row
        mock_session.execute.return_value = mock_result

        stats = await artifact_repository.get_storage_stats("t")

        assert stats["total_artifacts"] == 10
        assert stats["total_size_bytes"] == 5000
        assert stats["inline_artifacts"] == 8
        assert stats["object_artifacts"] == 2

    @pytest.mark.asyncio
    async def test_cleanup_old_artifacts(self, artifact_repository, mock_session):
        """Executes UPDATE and returns rowcount."""
        mock_result = Mock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await artifact_repository.cleanup_old_artifacts(days_old=30)

        assert count == 5
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
