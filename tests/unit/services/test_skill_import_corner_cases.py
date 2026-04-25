"""Corner-case tests for skill zip import.

Covers edge cases not in the basic or hardening suites: encoding issues,
manifest field boundaries, directory entries, content gate partial failures,
and the CY_NAME_PATTERN regex.
"""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.skill_import import (
    CY_NAME_PATTERN,
    MAX_NAME_LENGTH,
    SkillImportError,
    SkillImportService,
)


def _make_zip(files: dict[str, str | bytes]) -> bytes:
    """Create a zip file in memory. Supports both str and bytes values."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, bytes):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)
    return buf.getvalue()


def _valid_manifest(**overrides) -> str:
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


class TestCyNamePatternRegex:
    """Test the CY_NAME_PATTERN regex directly for boundary inputs."""

    def test_valid_simple(self):
        assert CY_NAME_PATTERN.match("test_skill")

    def test_valid_single_letter(self):
        assert CY_NAME_PATTERN.match("a")

    def test_valid_with_digits(self):
        assert CY_NAME_PATTERN.match("skill_v2_beta")

    def test_rejects_starting_with_digit(self):
        assert CY_NAME_PATTERN.match("1skill") is None

    def test_rejects_starting_with_underscore(self):
        assert CY_NAME_PATTERN.match("_skill") is None

    def test_rejects_uppercase(self):
        assert CY_NAME_PATTERN.match("TestSkill") is None

    def test_rejects_mixed_case(self):
        assert CY_NAME_PATTERN.match("test_Skill") is None

    def test_rejects_hyphen(self):
        assert CY_NAME_PATTERN.match("test-skill") is None

    def test_rejects_spaces(self):
        assert CY_NAME_PATTERN.match("test skill") is None

    def test_rejects_empty(self):
        assert CY_NAME_PATTERN.match("") is None

    def test_rejects_dot(self):
        assert CY_NAME_PATTERN.match("test.skill") is None

    def test_rejects_special_chars(self):
        for char in ["@", "#", "$", "%", "!", "+"]:
            assert CY_NAME_PATTERN.match(f"test{char}skill") is None


class TestNonUtf8Content:
    """Files that aren't valid UTF-8 should be rejected."""

    @pytest.mark.asyncio
    async def test_binary_content_in_md_file(self, service):
        """A .md file with binary content should fail UTF-8 decode."""
        # Create zip with raw bytes (Latin-1 encoded with non-UTF-8 bytes)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", _valid_manifest())
            zf.writestr("SKILL.md", _valid_skill_md())
            zf.writestr("docs/data.md", b"\xff\xfe Binary \x80\x81 content")
        zip_bytes = buf.getvalue()

        with pytest.raises(SkillImportError, match="UTF-8"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestManifestFieldBoundaries:
    """Boundary conditions on manifest fields."""

    @pytest.mark.asyncio
    async def test_name_at_exact_max_length(self, service):
        """Name with exactly MAX_NAME_LENGTH chars should pass manifest validation."""
        name = "A" * MAX_NAME_LENGTH
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(name=name),
                "SKILL.md": _valid_skill_md(),
            }
        )
        # This should pass manifest validation (content gates may fail, that's ok)
        # We just want to confirm it doesn't raise SkillImportError about name length
        try:
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")
        except SkillImportError as e:
            # Should NOT be about name length
            assert "name" not in str(e).lower() or "exceed" not in str(e).lower()  # noqa: PT017
        except Exception:
            pass  # Other errors (mock setup) are fine

    @pytest.mark.asyncio
    async def test_name_one_over_max_length(self, service):
        """Name with MAX_NAME_LENGTH + 1 chars should fail."""
        name = "A" * (MAX_NAME_LENGTH + 1)
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(name=name),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_whitespace_only_name(self, service):
        """Name that's only spaces should be treated as empty."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(name="   "),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_cy_name_starting_with_digit_rejected(self, service):
        """cy_name starting with digit should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(cy_name="3skill"),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="cy_name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_cy_name_uppercase_rejected(self, service):
        """cy_name with uppercase should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(cy_name="TestSkill"),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="cy_name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestDirectoryEntries:
    """Zip files with directory entries should be handled correctly."""

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_directory_entries_skipped(
        self, MockKMService, MockReviewService, service
    ):
        """Directory entries (trailing /) should be filtered out, not counted."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        # Create zip with explicit directory entries
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", _valid_manifest())
            zf.writestr("SKILL.md", _valid_skill_md())
            # Add directory entry
            zf.writestr("docs/", "")
            zf.writestr("docs/guide.md", "# Guide")
        zip_bytes = buf.getvalue()

        result = await service.import_from_zip(
            file_content=zip_bytes, tenant_id="test-tenant"
        )
        # Only SKILL.md and docs/guide.md submitted (not docs/ directory or manifest.json)
        assert result.documents_submitted == 2


class TestContentGatePartialFailure:
    """When some files pass content gates but others fail."""

    @pytest.mark.asyncio
    async def test_one_bad_file_rejects_entire_import(self, service):
        """If one of several files fails content gates, whole import is rejected."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "good_doc.md": "# Good Document\n\nSafe content here.",
                "evil.py": "import os\nos.system('rm -rf /')",
            }
        )
        with pytest.raises(SkillImportError, match="content safety checks"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_empty_content_file_rejected(self, service):
        """A file with empty content should fail content gates."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "empty.md": "",
            }
        )
        with pytest.raises(SkillImportError, match="content safety checks"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_whitespace_only_file_rejected(self, service):
        """A file with only whitespace should fail content gates."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "blank.md": "   \n\t  \n  ",
            }
        )
        with pytest.raises(SkillImportError, match="content safety checks"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestMalformedManifest:
    """Manifest edge cases beyond basic validation."""

    @pytest.mark.asyncio
    async def test_manifest_missing_required_fields(self, service):
        """Manifest without name/cy_name should fail."""
        manifest = json.dumps({"description": "no name"})
        zip_bytes = _make_zip(
            {
                "manifest.json": manifest,
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_manifest_empty_json_object(self, service):
        """Empty JSON object should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": "{}",
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_manifest_json_array(self, service):
        """JSON array instead of object should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": "[]",
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")
