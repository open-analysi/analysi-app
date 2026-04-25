"""Hardening tests for skill zip import service.

Tests path traversal, zip bombs, manifest injection, decompressed
size limits, and error message leaking.
"""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.services.skill_import import (
    SkillImportError,
    SkillImportService,
)


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
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


class TestPathTraversal:
    """Zip entries with path traversal should be rejected."""

    @pytest.mark.asyncio
    async def test_dot_dot_path_rejected(self, service):
        """Zip entry with ../ should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "../../../etc/passwd": "root:x:0:0",
            }
        )
        with pytest.raises(SkillImportError, match="[Pp]ath traversal"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_dot_dot_in_middle_rejected(self, service):
        """Zip entry with /../ in middle should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "docs/../../../etc/shadow": "hidden",
            }
        )
        with pytest.raises(SkillImportError, match="[Pp]ath traversal"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_absolute_path_rejected(self, service):
        """Zip entry with absolute path should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "/etc/passwd": "root:x:0:0",
            }
        )
        with pytest.raises(SkillImportError, match="[Aa]bsolute|[Pp]ath traversal"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestDecompressedSizeLimit:
    """Individual file size within zip should be bounded."""

    @pytest.mark.asyncio
    async def test_oversized_single_file_rejected(self, service):
        """Single file > 1MB decompressed should fail."""
        big_content = "x" * (1024 * 1024 + 1)  # 1MB + 1 byte
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "docs/huge.md": big_content,
            }
        )
        with pytest.raises(SkillImportError, match="[Ss]ize|[Ll]arge|[Ee]xceeds"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestManifestValidation:
    """Manifest field validation edge cases."""

    @pytest.mark.asyncio
    async def test_manifest_cy_name_with_slashes(self, service):
        """cy_name with path separators should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(cy_name="../../evil"),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="[Ii]nvalid|cy_name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_manifest_cy_name_with_spaces(self, service):
        """cy_name with spaces should fail (must be snake_case)."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(cy_name="my evil skill"),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="[Ii]nvalid|cy_name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_manifest_empty_name(self, service):
        """Empty name should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(name=""),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="[Ii]nvalid|name"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")

    @pytest.mark.asyncio
    async def test_manifest_name_too_long(self, service):
        """Name > 200 chars should fail."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(name="A" * 201),
                "SKILL.md": _valid_skill_md(),
            }
        )
        with pytest.raises(SkillImportError, match="[Ii]nvalid|name|[Ll]ong"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")


class TestExtensionlessFiles:
    """Files without extensions should be handled."""

    @pytest.mark.asyncio
    async def test_extensionless_file_rejected(self, service):
        """File with no extension (e.g., 'Makefile') should be rejected."""
        zip_bytes = _make_zip(
            {
                "manifest.json": _valid_manifest(),
                "SKILL.md": _valid_skill_md(),
                "Makefile": "all:\n\techo hi",
            }
        )
        with pytest.raises(SkillImportError, match="[Ee]xtension|[Bb]locked"):
            await service.import_from_zip(file_content=zip_bytes, tenant_id="test")
