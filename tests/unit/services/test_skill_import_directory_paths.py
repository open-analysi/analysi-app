"""Tests for directory path preservation in skill zip imports.

Verifies that nested folder structures (docs/, queries/, procedures/)
are preserved through the entire pipeline: zip → content review → KUDocument → skill tree.
"""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.skill_import import SkillImportService


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _valid_manifest(**overrides) -> str:
    data = {
        "name": "Hierarchy Skill",
        "description": "Skill with nested folders",
        "version": "1.0.0",
        "cy_name": "hierarchy_skill",
        "categories": ["test"],
        "config": {},
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return SkillImportService(mock_session)


class TestDirectoryPathPreservation:
    """Verify nested paths are passed through to content review."""

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_nested_paths_passed_to_review(
        self, MockKMService, MockReviewService, service
    ):
        """submit_for_review receives full paths like 'docs/guide.md'."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": "# Skill",
                "docs/triage.md": "# Triage Guide",
                "docs/evidence.md": "# Evidence Collection",
                "queries/splunk.md": "# Splunk Queries",
                "procedures/containment.md": "# Containment",
            }
        )

        result = await service.import_from_zip(
            file_content=zip_bytes, tenant_id="test-tenant"
        )

        assert result.documents_submitted == 5

        # Collect all filenames passed to submit_for_review
        submitted_filenames = [
            c.kwargs["filename"]
            for c in mock_review_svc.submit_for_review.call_args_list
        ]

        assert "SKILL.md" in submitted_filenames
        assert "docs/triage.md" in submitted_filenames
        assert "docs/evidence.md" in submitted_filenames
        assert "queries/splunk.md" in submitted_filenames
        assert "procedures/containment.md" in submitted_filenames

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_deeply_nested_paths_preserved(
        self, MockKMService, MockReviewService, service
    ):
        """Paths like 'a/b/c/file.md' are preserved through 3+ levels."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": "# Skill",
                "runbooks/network/lateral_movement.md": "# Lateral Movement",
                "runbooks/endpoint/malware_analysis.md": "# Malware Analysis",
            }
        )

        await service.import_from_zip(file_content=zip_bytes, tenant_id="test-tenant")

        submitted_filenames = [
            c.kwargs["filename"]
            for c in mock_review_svc.submit_for_review.call_args_list
        ]

        assert "runbooks/network/lateral_movement.md" in submitted_filenames
        assert "runbooks/endpoint/malware_analysis.md" in submitted_filenames

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_content_matches_path(
        self, MockKMService, MockReviewService, service
    ):
        """Each file's content is correctly paired with its path."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": "# Root Skill File",
                "docs/alpha.md": "# Alpha Content",
                "queries/beta.md": "# Beta Content",
            }
        )

        await service.import_from_zip(file_content=zip_bytes, tenant_id="test-tenant")

        # Build {filename: content} from call args
        submitted = {
            c.kwargs["filename"]: c.kwargs["content"]
            for c in mock_review_svc.submit_for_review.call_args_list
        }

        assert submitted["SKILL.md"] == "# Root Skill File"
        assert submitted["docs/alpha.md"] == "# Alpha Content"
        assert submitted["queries/beta.md"] == "# Beta Content"


class TestCreateAndLinkDocumentPaths:
    """Verify _create_and_link_document preserves directory paths."""

    @pytest.mark.asyncio
    async def test_namespace_path_preserves_directory(self, mock_session):
        """apply_review passes full path (e.g. 'docs/guide.md') to add_document."""
        from analysi.services.content_review import ContentReviewService

        service = ContentReviewService(mock_session)

        review = MagicMock()
        review.status = "approved"
        review.skill_id = uuid4()
        review.original_filename = "procedures/containment.md"
        review.transformed_content = None
        review.original_content = "# Containment\nBlock the threat."

        doc_id = uuid4()

        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=doc_id,
            ) as mock_create,
        ):
            result = await service.apply_review(uuid4(), tenant_id="t1")

        assert result.status == "applied"
        mock_create.assert_called_once_with(
            tenant_id="t1",
            skill_id=review.skill_id,
            filename="procedures/containment.md",
            content="# Containment\nBlock the threat.",
        )

    @pytest.mark.asyncio
    async def test_auto_apply_preserves_directory_path(self, mock_session):
        """auto_apply_review passes the full nested path through."""
        from analysi.services.content_review import ContentReviewService

        service = ContentReviewService(mock_session)

        review = MagicMock()
        review.status = "approved"
        review.skill_id = uuid4()
        review.original_filename = "queries/splunk_hunting.md"
        review.transformed_content = None
        review.original_content = "# Splunk Queries"

        doc_id = uuid4()

        with (
            patch.object(
                service,
                "_get_review_by_id",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=doc_id,
            ) as mock_create,
        ):
            result = await service.auto_apply_review(uuid4(), tenant_id="t1")

        assert result.status == "applied"
        mock_create.assert_called_once_with(
            tenant_id="t1",
            skill_id=review.skill_id,
            filename="queries/splunk_hunting.md",
            content="# Splunk Queries",
        )
