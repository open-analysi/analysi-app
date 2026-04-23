"""Unit tests for skill zip import service."""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.skill_import import (
    MAX_ZIP_SIZE,
    SkillImportError,
    SkillImportService,
)


def _make_zip(files: dict[str, str]) -> bytes:
    """Create a zip file in memory from a dict of {filename: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _valid_manifest(**overrides) -> str:
    """Create a valid manifest JSON string."""
    data = {
        "name": "Test Skill",
        "description": "A test skill",
        "version": "1.0.0",
        "cy_name": "test_skill",
        "categories": ["detection"],
        "config": {},
    }
    data.update(overrides)
    return json.dumps(data)


def _valid_skill_md() -> str:
    return "# Test Skill\n\nA skill for testing."


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return SkillImportService(mock_session)


class TestValidZipImport:
    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_valid_zip_imports(self, MockKMService, MockReviewService, service):
        """Valid zip with manifest + SKILL.md creates skill + reviews."""
        # Mock skill creation
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        # Mock review submission
        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "docs/guide.md": "# Guide\n\nSome content.",
            }
        )

        result = await service.import_from_zip(
            file_content=zip_bytes,
            tenant_id="test-tenant",
        )

        assert result.skill_id == mock_skill.component.id
        assert result.name == "Test Skill"
        # SKILL.md + docs/guide.md = 2 files (manifest.json excluded)
        assert result.documents_submitted == 2
        assert len(result.review_ids) == 2


class TestStructureValidation:
    @pytest.mark.asyncio
    async def test_missing_manifest(self, service):
        """Zip without manifest.json should fail."""
        zip_bytes = _make_zip({"SKILL.md": _valid_skill_md()})

        with pytest.raises(
            SkillImportError, match="manifest.json|[Mm]issing skill metadata"
        ):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_missing_skill_md(self, service):
        """Zip without SKILL.md should fail."""
        zip_bytes = _make_zip({"manifest.json": _valid_manifest()})

        with pytest.raises(SkillImportError, match="SKILL.md"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_oversized_zip(self, service):
        """Zip > 10MB should fail."""
        # Create oversized content
        oversized = b"x" * (MAX_ZIP_SIZE + 1)

        with pytest.raises(SkillImportError, match="10MB|size limit"):
            await service.import_from_zip(file_content=oversized, tenant_id="test")

    @pytest.mark.asyncio
    async def test_too_many_files(self, service):
        """Zip with > 100 files should fail."""
        files = {"manifest.json": _valid_manifest(), "SKILL.md": _valid_skill_md()}
        for i in range(100):
            files[f"file_{i}.md"] = f"# File {i}"

        zip_bytes = _make_zip(files)

        with pytest.raises(SkillImportError, match="maximum is 100"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_blocked_extension(self, service):
        """Zip with .sh file should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "script.sh": "#!/bin/bash\necho hi",
            }
        )

        with pytest.raises(SkillImportError, match="not allowed|extension"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_invalid_manifest_json(self, service):
        """Bad JSON in manifest should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": "not valid json{",
                "SKILL.md": _valid_skill_md(),
            }
        )

        with pytest.raises((SkillImportError, json.JSONDecodeError)):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_invalid_zip(self, service):
        """Non-zip content should fail."""
        with pytest.raises(SkillImportError, match="not a valid zip"):
            await service.import_from_zip(
                file_content=b"not a zip file", tenant_id="test"
            )


class TestReimportExistingSkill:
    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_reimport_reuses_existing_skill(
        self, MockKMService, MockReviewService, service
    ):
        """Re-importing a zip reuses the existing skill instead of 409."""
        existing_skill = MagicMock()
        existing_skill.component.id = uuid4()

        mock_km = MockKMService.return_value
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=existing_skill)
        mock_km.create_skill = AsyncMock()

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
            }
        )

        result = await service.import_from_zip(
            file_content=zip_bytes, tenant_id="test-tenant"
        )

        assert result.skill_id == existing_skill.component.id
        mock_km.create_skill.assert_not_called()

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_reimport_submits_files_for_review(
        self, MockKMService, MockReviewService, service
    ):
        """Re-import still submits all files for content review."""
        existing_skill = MagicMock()
        existing_skill.component.id = uuid4()

        mock_km = MockKMService.return_value
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=existing_skill)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "docs/guide.md": "# Guide",
            }
        )

        result = await service.import_from_zip(
            file_content=zip_bytes, tenant_id="test-tenant"
        )

        assert result.documents_submitted == 2
        assert mock_review_svc.submit_for_review.call_count == 2


class TestContentGateFailure:
    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_gate_failure_rejects_import(self, MockKMService, service):
        """Zip with suspicious .py should reject the entire import."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "evil.py": "import os\nos.system('rm -rf /')",
            }
        )

        with pytest.raises(SkillImportError, match="content safety checks"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestStructuredErrorFields:
    """Verify SkillImportError carries structured fields for the frontend."""

    @pytest.mark.asyncio
    async def test_invalid_archive_error_fields(self, service):
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=b"not a zip", tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "invalid_archive"
        assert exc.title == "Invalid archive"
        assert exc.hint is not None

    @pytest.mark.asyncio
    async def test_archive_too_large_error_fields(self, service):
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(
                file_content=b"x" * (MAX_ZIP_SIZE + 1), tenant_id="t"
            )
        exc = exc_info.value
        assert exc.error_code == "archive_too_large"
        assert "10MB" in exc.message

    @pytest.mark.asyncio
    async def test_missing_skill_md_error_fields(self, service):
        zip_bytes = _make_zip({"manifest.json": _valid_manifest()})
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "missing_skill_md"
        assert exc.hint is not None

    @pytest.mark.asyncio
    async def test_blocked_extension_error_fields(self, service):
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "payload.exe": "MZ...",
            }
        )
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "blocked_extension"
        assert exc.details.get("file") == "payload.exe"
        assert exc.details.get("extension") == ".exe"

    @pytest.mark.asyncio
    async def test_file_too_large_error_fields(self, service):
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "big.md": "x" * (1024 * 1024 + 1),
            }
        )
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "file_too_large"
        assert exc.details.get("file") == "big.md"
        assert exc.details.get("size_bytes") > 1024 * 1024

    @pytest.mark.asyncio
    async def test_invalid_manifest_json_error_fields(self, service):
        zip_bytes = _make_zip(
            {
                "manifest.json": "not json{",
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "invalid_manifest"
        assert "JSON" in exc.message

    @pytest.mark.asyncio
    async def test_missing_manifest_error_fields(self, service):
        zip_bytes = _make_zip({"SKILL.md": "# No frontmatter"})
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "missing_manifest"
        assert exc.hint is not None

    @pytest.mark.asyncio
    async def test_path_traversal_error_fields(self, service):
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "../../etc/passwd": "root",
            }
        )
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "path_traversal"

    @pytest.mark.asyncio
    async def test_content_gate_violation_error_fields(self, service):
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "evil.py": "import os\nos.system('rm -rf /')",
            }
        )
        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="t")
        exc = exc_info.value
        assert exc.error_code == "content_gate_violation"
        assert "failures" in exc.details
        assert len(exc.details["failures"]) >= 1

    @pytest.mark.asyncio
    async def test_error_maps_to_rfc9457_problem_response(self, service):
        """SkillImportError maps to RFC 9457 ProblemResponse."""
        import json

        from fastapi_problem_details import ProblemResponse

        with pytest.raises(SkillImportError) as exc_info:
            await service.import_from_zip(file_content=b"bad", tenant_id="t")
        exc = exc_info.value
        resp = ProblemResponse(
            status=422,
            title=exc.title,
            detail=exc.message,
            request_id="test-req-id",
            error_code=exc.error_code,
            hint=exc.hint,
            **exc.details,
        )
        d = json.loads(resp.body.decode())
        assert d["status"] == 422
        assert d["title"] == exc.title
        assert d["detail"] == exc.message
        assert d["error_code"] == "invalid_archive"
        assert d["hint"] == exc.hint
        assert d["request_id"] == "test-req-id"
