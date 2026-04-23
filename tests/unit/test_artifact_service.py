"""
Unit tests for ArtifactService.

Tests service business logic with mocked repository: returns ArtifactResponse,
owns content decoding, implements by-task-run/by-workflow-run/by-analysis queries.
"""

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from analysi.models.artifact import Artifact
from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.schemas.artifact import ArtifactCreate, ArtifactResponse
from analysi.services.artifact_service import ArtifactService


def _make_mock_artifact(**overrides) -> Mock:
    """Create a mock Artifact with sensible defaults for _convert_to_response."""
    defaults = {
        "id": uuid4(),
        "tenant_id": "test-tenant",
        "name": "Test Artifact",
        "artifact_type": "timeline",
        "mime_type": "application/json",
        "tags": ["test"],
        "sha256": b"\x00" * 32,
        "md5": b"\x00" * 16,
        "size_bytes": 100,
        "storage_class": "inline",
        "inline_content": b'{"key":"value"}',
        "bucket": None,
        "object_key": None,
        "alert_id": None,
        "task_run_id": uuid4(),
        "workflow_run_id": None,
        "workflow_node_instance_id": None,
        "analysis_id": None,
        "content_encoding": None,
        "integration_id": None,
        "source": "rest_api",
        "created_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    mock = Mock(spec=Artifact)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


@pytest.fixture
def mock_session():
    """Mock AsyncSession for testing."""
    return AsyncMock()


@pytest.fixture
def mock_repository():
    """Mock ArtifactRepository for testing."""
    return AsyncMock(spec=ArtifactRepository)


@pytest.fixture
def artifact_service(mock_session, mock_repository):
    """ArtifactService instance with mocked dependencies."""
    service = ArtifactService(mock_session)
    service.repository = mock_repository
    return service


@pytest.mark.unit
class TestArtifactService:
    """Test suite for ArtifactService business logic."""

    @pytest.mark.asyncio
    async def test_create_artifact_success(self, artifact_service, mock_repository):
        """Test successful artifact creation returns ArtifactResponse."""
        artifact_data = ArtifactCreate(
            name="Test Timeline",
            content="{'events': [{'time': '10:00', 'event': 'login'}]}",
            artifact_type="timeline",
            tags={"source": "auth_system", "priority": "high"},
        )

        tenant_id = "test-tenant"
        mock_artifact = _make_mock_artifact(tenant_id=tenant_id, name="Test Timeline")
        mock_repository.create.return_value = mock_artifact

        result = await artifact_service.create_artifact(tenant_id, artifact_data)

        # Service now returns ArtifactResponse
        assert isinstance(result, ArtifactResponse)
        assert result.id == mock_artifact.id
        assert result.name == "Test Timeline"
        assert result.tenant_id == tenant_id

        # Verify repository was called with correct data
        mock_repository.create.assert_called_once()
        call_args = mock_repository.create.call_args[0][0]
        assert call_args["tenant_id"] == tenant_id
        assert call_args["name"] == "Test Timeline"
        assert "inline_content" in call_args

    @pytest.mark.asyncio
    async def test_get_artifact_success(self, artifact_service, mock_repository):
        """Test successful artifact retrieval returns ArtifactResponse."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        mock_artifact = _make_mock_artifact(
            id=artifact_id,
            tenant_id=tenant_id,
            mime_type="application/json",
            inline_content=b'{"key":"value"}',
        )
        mock_repository.get_by_id.return_value = mock_artifact

        result = await artifact_service.get_artifact(tenant_id, artifact_id)

        assert isinstance(result, ArtifactResponse)
        assert result.id == artifact_id
        mock_repository.get_by_id.assert_called_once_with(tenant_id, artifact_id)

    @pytest.mark.asyncio
    async def test_get_artifact_not_found(self, artifact_service, mock_repository):
        """Test artifact retrieval when not found."""
        tenant_id = "test-tenant"
        artifact_id = uuid4()

        mock_repository.get_by_id.return_value = None

        result = await artifact_service.get_artifact(tenant_id, artifact_id)

        assert result is None
        mock_repository.get_by_id.assert_called_once_with(tenant_id, artifact_id)

    @pytest.mark.asyncio
    async def test_list_artifacts_with_filters(self, artifact_service, mock_repository):
        """Test artifact listing returns list of ArtifactResponse."""
        tenant_id = "test-tenant"
        filters = {"artifact_type": "timeline"}
        limit = 20
        offset = 0
        sort_by = "created_at"
        sort_order = "desc"

        mock_artifacts = [_make_mock_artifact() for _ in range(5)]
        total_count = 25
        mock_repository.list.return_value = (mock_artifacts, total_count)

        items, total = await artifact_service.list_artifacts(
            tenant_id, filters, limit, offset, sort_by, sort_order
        )

        mock_repository.list.assert_called_once_with(
            tenant_id, filters, limit, offset, sort_by, sort_order
        )
        assert total == total_count
        assert len(items) == 5
        assert all(isinstance(item, ArtifactResponse) for item in items)

    @pytest.mark.asyncio
    async def test_create_artifact_storage_processing(
        self, artifact_service, mock_repository
    ):
        """Test that artifact creation processes content for storage."""
        artifact_data = ArtifactCreate(
            name="Storage Test",
            content=b"binary content",
            mime_type="application/octet-stream",
        )

        tenant_id = "test-tenant"
        mock_artifact = _make_mock_artifact(tenant_id=tenant_id, name="Storage Test")
        mock_repository.create.return_value = mock_artifact

        result = await artifact_service.create_artifact(tenant_id, artifact_data)

        assert isinstance(result, ArtifactResponse)
        mock_repository.create.assert_called_once()
        call_args = mock_repository.create.call_args[0][0]
        assert "storage_class" in call_args
        assert "sha256" in call_args
        assert "md5" in call_args
        assert "size_bytes" in call_args
        assert call_args["tenant_id"] == tenant_id


@pytest.mark.unit
class TestArtifactServiceContentDecoding:
    """Test _convert_to_response content decoding."""

    @pytest.mark.asyncio
    async def test_get_artifact_decodes_json_content(
        self, artifact_service, mock_repository
    ):
        """Inline JSON artifact: content is parsed as dict."""
        json_bytes = b'{"alert":"fired","count":42}'
        mock_artifact = _make_mock_artifact(
            mime_type="application/json",
            inline_content=json_bytes,
        )
        mock_repository.get_by_id.return_value = mock_artifact

        result = await artifact_service.get_artifact("test-tenant", mock_artifact.id)

        assert isinstance(result, ArtifactResponse)
        assert result.content == {"alert": "fired", "count": 42}

    @pytest.mark.asyncio
    async def test_get_artifact_decodes_text_content(
        self, artifact_service, mock_repository
    ):
        """Inline text artifact: content is decoded as string."""
        text_bytes = b"Some plain text content"
        mock_artifact = _make_mock_artifact(
            mime_type="text/plain",
            inline_content=text_bytes,
        )
        mock_repository.get_by_id.return_value = mock_artifact

        result = await artifact_service.get_artifact("test-tenant", mock_artifact.id)

        assert isinstance(result, ArtifactResponse)
        assert result.content == "Some plain text content"

    @pytest.mark.asyncio
    async def test_get_artifact_decodes_binary_as_base64(
        self, artifact_service, mock_repository
    ):
        """Inline binary artifact: content is base64-encoded string."""
        binary_bytes = b"\x89PNG\r\n\x1a\n\x00\x00"
        mock_artifact = _make_mock_artifact(
            mime_type="image/png",
            inline_content=binary_bytes,
        )
        mock_repository.get_by_id.return_value = mock_artifact

        result = await artifact_service.get_artifact("test-tenant", mock_artifact.id)

        assert isinstance(result, ArtifactResponse)
        expected_b64 = base64.b64encode(binary_bytes).decode("ascii")
        assert result.content == expected_b64

    @pytest.mark.asyncio
    async def test_list_artifacts_excludes_content(
        self, artifact_service, mock_repository
    ):
        """List items have content=None (no content in list responses)."""
        mock_artifacts = [
            _make_mock_artifact(inline_content=b'{"data":"secret"}'),
            _make_mock_artifact(inline_content=b"text content"),
        ]
        mock_repository.list.return_value = (mock_artifacts, 2)

        items, total = await artifact_service.list_artifacts("test-tenant")

        assert total == 2
        for item in items:
            assert isinstance(item, ArtifactResponse)
            assert item.content is None


@pytest.mark.unit
class TestArtifactServiceByRunQueries:
    """Tests for get_artifacts_by_task_run, by_workflow_run, by_analysis."""

    @pytest.mark.asyncio
    async def test_get_artifacts_by_task_run(self, artifact_service, mock_repository):
        """Returns list of ArtifactResponse from repo's get_by_task_run."""
        task_run_id = uuid4()
        mock_artifacts = [
            _make_mock_artifact(task_run_id=task_run_id) for _ in range(3)
        ]
        mock_repository.get_by_task_run.return_value = mock_artifacts

        result = await artifact_service.get_artifacts_by_task_run("t", task_run_id)

        assert len(result) == 3
        assert all(isinstance(r, ArtifactResponse) for r in result)
        mock_repository.get_by_task_run.assert_called_once_with("t", task_run_id)

    @pytest.mark.asyncio
    async def test_get_artifacts_by_workflow_run(
        self, artifact_service, mock_repository
    ):
        """Returns list of ArtifactResponse from repo's get_by_workflow_run."""
        wf_run_id = uuid4()
        mock_artifacts = [
            _make_mock_artifact(workflow_run_id=wf_run_id) for _ in range(2)
        ]
        mock_repository.get_by_workflow_run.return_value = mock_artifacts

        result = await artifact_service.get_artifacts_by_workflow_run("t", wf_run_id)

        assert len(result) == 2
        assert all(isinstance(r, ArtifactResponse) for r in result)

    @pytest.mark.asyncio
    async def test_get_artifacts_by_analysis_grouped(
        self, artifact_service, mock_repository
    ):
        """Groups artifacts by artifact_type in a dict."""
        analysis_id = uuid4()
        mock_artifacts = [
            _make_mock_artifact(
                artifact_type="tool_execution", analysis_id=analysis_id
            ),
            _make_mock_artifact(
                artifact_type="tool_execution", analysis_id=analysis_id
            ),
            _make_mock_artifact(artifact_type="llm_execution", analysis_id=analysis_id),
        ]
        mock_repository.get_by_analysis.return_value = mock_artifacts

        result = await artifact_service.get_artifacts_by_analysis("t", analysis_id)

        assert isinstance(result, dict)
        assert len(result["tool_execution"]) == 2
        assert len(result["llm_execution"]) == 1

    @pytest.mark.asyncio
    async def test_get_artifacts_by_analysis_empty(
        self, artifact_service, mock_repository
    ):
        """Returns empty dict when no artifacts found."""
        mock_repository.get_by_analysis.return_value = []

        result = await artifact_service.get_artifacts_by_analysis("t", uuid4())

        assert result == {}
