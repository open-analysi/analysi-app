"""
Unit tests for AI archetype addition.

Tests that verify AI archetype has been added to archetype definitions.
Following TDD - these tests verify the archetype documentation.
"""

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class TestAIArchetype:
    """Test AI archetype addition."""

    @pytest.fixture
    def archetypes_file(self):
        """Get path to archetypes file."""
        return (
            _PROJECT_ROOT
            / "skills"
            / "dev"
            / "integrations-developer"
            / "references"
            / "archetypes.md"
        )

    def test_ai_archetype_exists_in_archetype_definitions(self, archetypes_file):
        """Test: AI archetype exists in archetype definitions.

        Goal: Verify AI archetype (#17) added to NAXOS_INTEGRATION_ARCHETYPES.md.
        """
        with open(archetypes_file) as f:
            content = f.read()

        # Check for AI archetype heading
        assert "### 17. AI" in content, "Should have '### 17. AI' heading"

        # Check for abstract actions (llm_complete was dropped)
        assert "llm_run" in content, "Should define llm_run action"
        assert "llm_chat" in content, "Should define llm_chat action"
        assert "llm_embed" in content, "Should define llm_embed action"

        # Check for priority guidance
        assert "80" in content, "Should mention priority 80"

    def test_openai_integration_uses_ai_archetype(self):
        """Test: OpenAI integration uses AI archetype.

        Goal: Ensure OpenAI manifest correctly references AI archetype.
        """
        import json

        manifest_path = (
            _PROJECT_ROOT
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "openai"
            / "manifest.json"
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Verify archetypes array includes AI
        assert "AI" in manifest.get("archetypes", []), (
            f"Expected 'AI' in archetypes, got {manifest.get('archetypes')}"
        )

        # Verify priority
        assert manifest.get("priority") == 80, (
            f"Expected priority=80, got {manifest.get('priority')}"
        )
