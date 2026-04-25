"""Unit tests for zip common directory prefix stripping.

Covers zip layouts from different OS tools and edge cases:
- macOS Compress (Finder right-click)
- Linux zip -r
- Windows Explorer "Send to Compressed"
- GitHub "Download ZIP"
- Flat zips (no prefix)
- Nested subdirectories
- Mixed roots (no stripping)
"""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.skill_import import (
    SkillImportService,
    _strip_common_prefix,
)

# --- _strip_common_prefix unit tests ---


class TestStripCommonPrefix:
    """Test prefix detection and stripping for various zip layouts."""

    def test_no_prefix_flat_layout(self):
        """Files at root level — no stripping needed."""
        names = ["SKILL.md", "manifest.json", "docs/guide.md"]
        result = _strip_common_prefix(names)
        assert result == {
            "SKILL.md": "SKILL.md",
            "manifest.json": "manifest.json",
            "docs/guide.md": "docs/guide.md",
        }

    def test_macos_compress_with_directory_entry(self):
        """macOS Finder 'Compress' creates folder/ + folder/file entries."""
        names = ["nist-nvd/", "nist-nvd/SKILL.md", "nist-nvd/references/guide.md"]
        result = _strip_common_prefix(names)
        # Directory entry stripped entirely, files have prefix removed
        assert "nist-nvd/" not in result
        assert result["nist-nvd/SKILL.md"] == "SKILL.md"
        assert result["nist-nvd/references/guide.md"] == "references/guide.md"

    def test_linux_zip_r_with_directory_entries(self):
        """Linux 'zip -r skill.zip my-skill/' includes directory entries."""
        names = [
            "my-skill/",
            "my-skill/SKILL.md",
            "my-skill/manifest.json",
            "my-skill/docs/",
            "my-skill/docs/readme.md",
        ]
        result = _strip_common_prefix(names)
        assert result["my-skill/SKILL.md"] == "SKILL.md"
        assert result["my-skill/manifest.json"] == "manifest.json"
        assert result["my-skill/docs/readme.md"] == "docs/readme.md"
        assert "my-skill/" not in result

    def test_linux_zip_r_without_directory_entries(self):
        """Some zip tools omit directory entries."""
        names = [
            "my-skill/SKILL.md",
            "my-skill/manifest.json",
            "my-skill/docs/readme.md",
        ]
        result = _strip_common_prefix(names)
        assert result["my-skill/SKILL.md"] == "SKILL.md"
        assert result["my-skill/manifest.json"] == "manifest.json"
        assert result["my-skill/docs/readme.md"] == "docs/readme.md"

    def test_github_download_zip(self):
        """GitHub 'Download ZIP' uses 'repo-branch/' prefix."""
        names = [
            "alert-triage-main/",
            "alert-triage-main/SKILL.md",
            "alert-triage-main/references/sources.md",
            "alert-triage-main/docs/guide.md",
        ]
        result = _strip_common_prefix(names)
        assert result["alert-triage-main/SKILL.md"] == "SKILL.md"
        assert (
            result["alert-triage-main/references/sources.md"] == "references/sources.md"
        )

    def test_mixed_roots_no_stripping(self):
        """Files under different top-level dirs — no common prefix."""
        names = ["skill-a/SKILL.md", "skill-b/other.md"]
        result = _strip_common_prefix(names)
        # No stripping — different roots
        assert result["skill-a/SKILL.md"] == "skill-a/SKILL.md"
        assert result["skill-b/other.md"] == "skill-b/other.md"

    def test_some_files_at_root_no_stripping(self):
        """Mix of root files and prefixed files — no stripping."""
        names = ["README.md", "my-skill/SKILL.md", "my-skill/docs/guide.md"]
        result = _strip_common_prefix(names)
        assert result["README.md"] == "README.md"
        assert result["my-skill/SKILL.md"] == "my-skill/SKILL.md"

    def test_single_file_with_prefix(self):
        """Single file in a directory."""
        names = ["my-skill/", "my-skill/SKILL.md"]
        result = _strip_common_prefix(names)
        assert result["my-skill/SKILL.md"] == "SKILL.md"
        assert "my-skill/" not in result

    def test_empty_zip(self):
        """No files at all."""
        result = _strip_common_prefix([])
        assert result == {}

    def test_only_directories(self):
        """Only directory entries, no files."""
        names = ["my-skill/", "my-skill/docs/"]
        result = _strip_common_prefix(names)
        # No files to determine prefix — return as-is
        assert result["my-skill/"] == "my-skill/"
        assert result["my-skill/docs/"] == "my-skill/docs/"

    def test_deeply_nested_common_prefix(self):
        """Only strips one level of common prefix."""
        names = [
            "outer/inner/SKILL.md",
            "outer/inner/docs/guide.md",
        ]
        result = _strip_common_prefix(names)
        # Only strips 'outer/' (the top-level common prefix)
        assert result["outer/inner/SKILL.md"] == "inner/SKILL.md"
        assert result["outer/inner/docs/guide.md"] == "inner/docs/guide.md"

    def test_prefix_with_dots_in_name(self):
        """Directory name with dots (e.g. version numbers)."""
        names = [
            "my-skill-v1.2/",
            "my-skill-v1.2/SKILL.md",
            "my-skill-v1.2/config.json",
        ]
        result = _strip_common_prefix(names)
        assert result["my-skill-v1.2/SKILL.md"] == "SKILL.md"

    def test_prefix_with_spaces(self):
        """Directory name with spaces (Windows-style)."""
        names = [
            "My Skill/",
            "My Skill/SKILL.md",
            "My Skill/docs/guide.md",
        ]
        result = _strip_common_prefix(names)
        assert result["My Skill/SKILL.md"] == "SKILL.md"
        assert result["My Skill/docs/guide.md"] == "docs/guide.md"

    def test_underscore_prefix(self):
        """macOS sometimes creates __MACOSX entries — but those get
        filtered by extension check, not here. We just strip the common prefix."""
        names = [
            "alert_triage/",
            "alert_triage/SKILL.md",
            "alert_triage/playbook.md",
        ]
        result = _strip_common_prefix(names)
        assert result["alert_triage/SKILL.md"] == "SKILL.md"


# --- Full import with prefix stripping ---


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return SkillImportService(mock_session)


class TestPrefixStrippingImport:
    """Test full import flow with prefixed zip layouts."""

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_import_macos_compressed_folder(
        self, MockKMService, MockReviewService, service
    ):
        """macOS-style zip with folder prefix imports successfully."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        manifest = json.dumps(
            {
                "name": "Alert Triage",
                "cy_name": "alert_triage",
                "description": "Triage alerts",
            }
        )
        zip_bytes = _make_zip(
            {
                "alert-triage/": "",
                "alert-triage/manifest.json": manifest,
                "alert-triage/SKILL.md": "# Alert Triage\n\nContent.",
                "alert-triage/docs/guide.md": "# Guide\n\nHow to triage.",
            }
        )

        result = await service.import_from_zip(zip_bytes, "test-tenant")
        assert result.name == "Alert Triage"
        assert result.documents_submitted == 2  # SKILL.md + guide.md

        # Verify filenames passed to review are normalized (no prefix)
        calls = mock_review_svc.submit_for_review.call_args_list
        filenames = sorted(
            c.kwargs.get("filename", c[1].get("filename", "")) or "" for c in calls
        )
        # submit_for_review uses keyword args
        filenames = sorted(c[1]["filename"] for c in calls)
        assert "SKILL.md" in filenames
        assert "docs/guide.md" in filenames

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_import_frontmatter_with_prefix(
        self, MockKMService, MockReviewService, service
    ):
        """Prefixed zip with frontmatter-only SKILL.md (no manifest.json)."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        skill_md = "---\nname: NIST NVD\ndescription: Vuln triage\n---\n# NIST NVD"
        zip_bytes = _make_zip(
            {
                "nist-nvd/": "",
                "nist-nvd/SKILL.md": skill_md,
                "nist-nvd/references/guide.md": "# Guide\n\nReference material.",
            }
        )

        result = await service.import_from_zip(zip_bytes, "test-tenant")
        assert result.name == "NIST NVD"
        assert result.documents_submitted == 2

    @pytest.mark.asyncio
    async def test_import_prefixed_missing_skill_md_raises(self, service):
        """Prefixed zip without SKILL.md (even after stripping) raises."""
        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/README.md": "# Not a skill",
            }
        )

        from analysi.services.skill_import import SkillImportError

        with pytest.raises(SkillImportError, match="SKILL.md"):
            await service.import_from_zip(zip_bytes, "test-tenant")


class TestPrefixStrippingSecurity:
    """Security tests: evil patterns inside prefixed zips."""

    @pytest.mark.asyncio
    async def test_traversal_inside_prefix_rejected(self, service):
        """Path traversal within a prefixed zip is still caught."""
        from analysi.services.skill_import import SkillImportError

        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/SKILL.md": "---\nname: Evil\n---\n# Evil",
                "my-skill/../../../etc/passwd": "root:x:0:0",
            }
        )
        with pytest.raises(SkillImportError, match="[Pp]ath traversal"):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_traversal_after_strip_rejected(self, service):
        """Even if prefix stripping normalizes, traversal in remaining path is caught."""
        from analysi.services.skill_import import SkillImportError

        # All files share 'evil/' prefix, so it gets stripped.
        # After stripping: '../../../etc/shadow' — must be caught.
        zip_bytes = _make_zip(
            {
                "evil/SKILL.md": "---\nname: Evil\n---\n# Evil",
                "evil/../../../etc/shadow": "secret",
            }
        )
        with pytest.raises(SkillImportError, match="[Pp]ath traversal"):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_absolute_path_inside_prefix_rejected(self, service):
        """Absolute path within a prefixed zip is still caught."""
        from analysi.services.skill_import import SkillImportError

        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/SKILL.md": "---\nname: Evil\n---\n# Evil",
                "my-skill//etc/passwd": "root:x:0:0",
            }
        )
        with pytest.raises(SkillImportError):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_dangerous_python_inside_prefix_rejected(self, service):
        """Dangerous Python code in prefixed zip is blocked by content gates."""
        from analysi.services.skill_import import SkillImportError

        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/manifest.json": json.dumps(
                    {
                        "name": "Evil Skill",
                        "cy_name": "evil_skill",
                        "description": "Does bad things",
                    }
                ),
                "my-skill/SKILL.md": "# Evil\n\nDo bad things.",
                "my-skill/scripts/evil.py": "import os\nos.system('rm -rf /')",
            }
        )
        with pytest.raises(SkillImportError, match="content safety checks"):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_blocked_extension_inside_prefix_rejected(self, service):
        """Blocked file extensions in prefixed zips are still caught."""
        from analysi.services.skill_import import SkillImportError

        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/SKILL.md": "---\nname: Evil\n---\n# Evil",
                "my-skill/payload.exe": "MZ...",
            }
        )
        with pytest.raises(SkillImportError, match="[Ee]xtension|[Bb]locked"):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_oversized_file_inside_prefix_rejected(self, service):
        """Oversized files in prefixed zips are still caught."""
        from analysi.services.skill_import import SkillImportError

        big_content = "x" * (1024 * 1024 + 1)
        zip_bytes = _make_zip(
            {
                "my-skill/": "",
                "my-skill/SKILL.md": "---\nname: Big\n---\n# Big",
                "my-skill/docs/huge.md": big_content,
            }
        )
        with pytest.raises(SkillImportError, match="[Ss]ize|[Ee]xceeds"):
            await service.import_from_zip(zip_bytes, "test-tenant")
