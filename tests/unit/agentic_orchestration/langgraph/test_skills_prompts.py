"""Tests for SkillsIR prompts."""

from analysi.agentic_orchestration.langgraph.skills.context import SkillContext
from analysi.agentic_orchestration.langgraph.skills.prompts import (
    format_file_trees,
    format_loaded_files,
    format_retrieval_prompt,
    format_skill_registry,
)


class TestFormatSkillRegistry:
    """Tests for format_skill_registry."""

    def test_empty_registry(self):
        """Empty registry returns (none)."""
        assert format_skill_registry({}) == "(none)"

    def test_single_skill(self):
        """Single skill is formatted correctly."""
        registry = {"skill-a": "Description of skill A"}
        result = format_skill_registry(registry)
        assert "**skill-a**" in result
        assert "Description of skill A" in result

    def test_multiple_skills_sorted(self):
        """Multiple skills are sorted alphabetically."""
        registry = {
            "zebra-skill": "Last",
            "alpha-skill": "First",
        }
        result = format_skill_registry(registry)
        assert result.index("alpha-skill") < result.index("zebra-skill")


class TestFormatLoadedFiles:
    """Tests for format_loaded_files."""

    def test_empty_loaded(self):
        """Empty loaded returns (none)."""
        assert format_loaded_files({}) == "(none)"

    def test_single_file(self):
        """Single file is formatted correctly."""
        loaded = {"skill-a": {"SKILL.md": "content"}}
        result = format_loaded_files(loaded)
        assert "skill-a/SKILL.md" in result

    def test_multiple_files(self):
        """Multiple files from same skill."""
        loaded = {"skill-a": {"SKILL.md": "c1", "guide.md": "c2"}}
        result = format_loaded_files(loaded)
        assert "skill-a/SKILL.md" in result
        assert "skill-a/guide.md" in result


class TestFormatFileTrees:
    """Tests for format_file_trees."""

    def test_empty_trees(self):
        """Empty trees returns (none)."""
        assert format_file_trees({}, {}) == "(none)"

    def test_excludes_loaded_files(self):
        """Already loaded files are excluded."""
        trees = {"skill-a": ["SKILL.md", "guide.md", "other.md"]}
        loaded = {"skill-a": {"SKILL.md": "content"}}

        result = format_file_trees(trees, loaded)

        assert "SKILL.md" not in result
        assert "guide.md" in result
        assert "other.md" in result

    def test_all_loaded_message(self):
        """When all files loaded, shows appropriate message."""
        trees = {"skill-a": ["SKILL.md"]}
        loaded = {"skill-a": {"SKILL.md": "content"}}

        result = format_file_trees(trees, loaded)

        assert "all files already loaded" in result


class TestFormatRetrievalPrompt:
    """Tests for format_retrieval_prompt."""

    def test_includes_all_sections(self):
        """Prompt includes all required sections."""
        context = SkillContext(
            registry={"skill-a": "Test skill"},
            trees={"skill-a": ["SKILL.md", "guide.md"]},
            token_limit=10000,
        )
        context.add("skill-a", "SKILL.md", "Skill content")

        prompt = format_retrieval_prompt(
            objective="Match alert to runbook",
            task_input='{"alert": "test"}',
            context=context,
        )

        assert "## Your Objective" in prompt
        assert "Match alert to runbook" in prompt
        assert "## Task Input" in prompt
        assert '{"alert": "test"}' in prompt
        assert "## Available Skills" in prompt
        assert "skill-a" in prompt
        assert "## Already Loaded" in prompt
        assert "SKILL.md" in prompt
        assert "## Available Files" in prompt
        assert "guide.md" in prompt
        assert "## Token Budget" in prompt
        assert "10000" in prompt

    def test_instructions_present(self):
        """Prompt includes instructions."""
        context = SkillContext()

        prompt = format_retrieval_prompt(
            objective="Test",
            task_input="{}",
            context=context,
        )

        assert "has_enough=true" in prompt
        assert "max 3 per request" in prompt
