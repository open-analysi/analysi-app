"""Unit tests for skill import from SKILL.md frontmatter (no manifest.json)."""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.skill_import import (
    SkillImportError,
    SkillImportService,
    _name_to_cy_name,
    _parse_yaml_frontmatter,
)


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# --- _parse_yaml_frontmatter ---


class TestParseYamlFrontmatter:
    def test_parses_simple_frontmatter(self):
        text = "---\nname: My Skill\ndescription: Does things\n---\n# Content"
        result = _parse_yaml_frontmatter(text)
        assert result == {"name": "My Skill", "description": "Does things"}

    def test_returns_none_without_frontmatter(self):
        assert _parse_yaml_frontmatter("# Just Markdown") is None

    def test_returns_none_for_empty_frontmatter(self):
        assert _parse_yaml_frontmatter("---\n---\n# Content") is None

    def test_returns_none_for_unclosed_frontmatter(self):
        assert _parse_yaml_frontmatter("---\nname: test\n# No closing") is None

    def test_parses_list_values(self):
        text = "---\ncategories: [detection, triage]\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result["categories"] == ["detection", "triage"]

    def test_skips_comment_lines(self):
        text = "---\nname: Test\n# this is a comment\ndescription: Desc\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result == {"name": "Test", "description": "Desc"}

    def test_handles_leading_whitespace(self):
        text = "\n\n---\nname: Test\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result == {"name": "Test"}

    def test_handles_quoted_list_items(self):
        text = "---\ncategories: ['security', \"ops\"]\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result["categories"] == ["security", "ops"]

    def test_handles_colon_in_value(self):
        text = "---\ndescription: Step 1: do the thing\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result["description"] == "Step 1: do the thing"

    def test_folded_scalar(self):
        """YAML >- folded block scalar should join lines with spaces."""
        text = (
            "---\n"
            "name: nist-nvd\n"
            "description: >-\n"
            "  Investigate vulnerabilities using NIST NVD.\n"
            "  Use when analyzing CVEs.\n"
            "---\n"
            "# Content"
        )
        result = _parse_yaml_frontmatter(text)
        assert result["name"] == "nist-nvd"
        assert "Investigate vulnerabilities" in result["description"]
        assert "Use when analyzing CVEs" in result["description"]

    def test_literal_scalar(self):
        """YAML |- literal block scalar should preserve newlines."""
        text = "---\nname: test\ndescription: |-\n  Line one.\n  Line two.\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert "Line one." in result["description"]
        assert "Line two." in result["description"]

    def test_version_field_parsed(self):
        text = "---\nname: test\nversion: 0.1.0\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result["version"] == "0.1.0"


# --- _name_to_cy_name ---


class TestNameToCyName:
    def test_simple_name(self):
        assert _name_to_cy_name("Alert Triage") == "alert_triage"

    def test_with_hyphens(self):
        assert _name_to_cy_name("my-cool-runbook") == "my_cool_runbook"

    def test_with_version(self):
        assert _name_to_cy_name("Runbook v2") == "runbook_v2"

    def test_starts_with_number(self):
        assert _name_to_cy_name("123 Alerts") == "skill_123_alerts"

    def test_special_chars(self):
        assert _name_to_cy_name("Test (Alpha)!") == "test_alpha"

    def test_empty_returns_default(self):
        assert _name_to_cy_name("") == "unnamed_skill"

    def test_already_snake_case(self):
        assert _name_to_cy_name("alert_triage") == "alert_triage"


# --- Frontmatter-based import ---


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return SkillImportService(mock_session)


class TestFrontmatterImport:
    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_import_with_frontmatter_only(
        self, MockKMService, MockReviewService, service
    ):
        """Zip with SKILL.md frontmatter but no manifest.json succeeds."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        skill_md = (
            "---\n"
            "name: Alert Triage\n"
            "description: Triage security alerts\n"
            "---\n"
            "# Alert Triage\n\nContent here."
        )
        zip_bytes = _make_zip({"SKILL.md": skill_md})

        result = await service.import_from_zip(zip_bytes, "test-tenant")

        assert result.name == "Alert Triage"
        assert result.documents_submitted == 1

        # Verify cy_name was derived
        create_call = mock_km.create_skill.call_args
        skill_create = create_call[0][1]
        assert skill_create.cy_name == "alert_triage"
        assert skill_create.description == "Triage security alerts"

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_frontmatter_with_explicit_cy_name(
        self, MockKMService, MockReviewService, service
    ):
        """Frontmatter cy_name takes precedence over derived name."""
        mock_km = MockKMService.return_value
        mock_skill = MagicMock()
        mock_skill.component.id = uuid4()
        mock_km.create_skill = AsyncMock(return_value=mock_skill)
        mock_km.get_skill_by_cy_name = AsyncMock(return_value=None)

        mock_review_svc = MockReviewService.return_value
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review_svc.submit_for_review = AsyncMock(return_value=mock_review)

        skill_md = (
            "---\n"
            "name: Alert Triage Skill\n"
            "cy_name: custom_triage\n"
            "description: Custom\n"
            "---\n"
            "# Content"
        )
        zip_bytes = _make_zip({"SKILL.md": skill_md})

        await service.import_from_zip(zip_bytes, "test-tenant")

        create_call = mock_km.create_skill.call_args
        assert create_call[0][1].cy_name == "custom_triage"

    @pytest.mark.asyncio
    async def test_no_manifest_no_frontmatter_raises(self, service):
        """Zip with SKILL.md but no frontmatter and no manifest.json raises."""
        zip_bytes = _make_zip({"SKILL.md": "# Just a heading\n\nNo frontmatter."})

        with pytest.raises(
            SkillImportError, match="No manifest.json found|[Mm]issing skill metadata"
        ):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    async def test_frontmatter_missing_name_raises(self, service):
        """Frontmatter without name field raises."""
        skill_md = "---\ndescription: No name here\n---\n# Content"
        zip_bytes = _make_zip({"SKILL.md": skill_md})

        with pytest.raises(SkillImportError, match="missing.*'name'|required.*name"):
            await service.import_from_zip(zip_bytes, "test-tenant")

    @pytest.mark.asyncio
    @patch("analysi.services.skill_import.ContentReviewService")
    @patch("analysi.services.skill_import.KnowledgeModuleService")
    async def test_manifest_json_takes_precedence(
        self, MockKMService, MockReviewService, service
    ):
        """When both manifest.json and frontmatter exist, manifest.json wins."""
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
                "name": "From Manifest",
                "cy_name": "from_manifest",
                "description": "Manifest desc",
            }
        )
        skill_md = "---\nname: From Frontmatter\ndescription: FM desc\n---\n# Content"
        zip_bytes = _make_zip(
            {
                "manifest.json": manifest,
                "SKILL.md": skill_md,
            }
        )

        result = await service.import_from_zip(zip_bytes, "test-tenant")
        assert result.name == "From Manifest"

        create_call = mock_km.create_skill.call_args
        assert create_call[0][1].cy_name == "from_manifest"
