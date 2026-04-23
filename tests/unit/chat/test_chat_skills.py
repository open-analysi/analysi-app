"""Unit tests for chat skill loading, pinning, and system prompt building."""

import pytest

from analysi.constants import ChatConstants
from analysi.services.chat_skills import (
    AVAILABLE_SKILLS,
    PAGE_TO_SKILL,
    SKILLS_DIR,
    build_system_prompt,
    get_preloaded_skill,
    load_overview_skill,
    load_skill_content,
    update_pinned_skills,
    validate_skill_budgets,
)


class TestLoadSkillContent:
    """Tests for skill file loading with allowlist gate."""

    def test_loads_valid_skill(self):
        """Known skill name returns markdown content."""
        content = load_skill_content("alerts")
        assert len(content) > 100
        assert "alert" in content.lower()

    def test_rejects_unknown_skill_name(self):
        """Unknown skill name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown skill"):
            load_skill_content("hacking_tools")

    def test_rejects_path_traversal(self):
        """Path traversal attempt raises ValueError (allowlist blocks it)."""
        with pytest.raises(ValueError, match="Unknown skill"):
            load_skill_content("../../etc/passwd")

    def test_rejects_empty_string(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown skill"):
            load_skill_content("")

    def test_all_available_skills_have_files(self):
        """Every entry in AVAILABLE_SKILLS has a corresponding .md file."""
        for skill_name in AVAILABLE_SKILLS:
            skill_path = SKILLS_DIR / f"{skill_name}.md"
            assert skill_path.exists(), f"Missing skill file: {skill_path}"

    def test_overview_skill_file_exists(self):
        """The _overview.md file exists (not in AVAILABLE_SKILLS but always loaded)."""
        overview_path = SKILLS_DIR / "_overview.md"
        assert overview_path.exists(), f"Missing overview skill: {overview_path}"

    def test_overview_skill_loads(self):
        """The global overview skill loads successfully."""
        content = load_overview_skill()
        assert len(content) > 100
        assert "analysi" in content.lower()


class TestGetPreloadedSkill:
    """Tests for page context → skill mapping."""

    def test_maps_alerts_route(self):
        """Alerts page maps to alerts skill."""
        assert get_preloaded_skill({"route": "/alerts/ALT-42"}) == "alerts"

    def test_maps_workflows_route(self):
        """Workflows page maps to workflows skill."""
        assert get_preloaded_skill({"route": "/workflows/123"}) == "workflows"

    def test_maps_tasks_route(self):
        """Tasks page maps to tasks skill."""
        assert get_preloaded_skill({"route": "/tasks/my-task"}) == "tasks"

    def test_maps_integrations_route(self):
        """Integrations page maps to integrations skill."""
        assert get_preloaded_skill({"route": "/integrations/splunk"}) == "integrations"

    def test_maps_knowledge_route(self):
        """Knowledge page maps to knowledge_units skill."""
        assert get_preloaded_skill({"route": "/knowledge/docs"}) == "knowledge_units"

    def test_maps_settings_route(self):
        """Settings page maps to admin skill."""
        assert get_preloaded_skill({"route": "/settings/roles"}) == "admin"

    def test_page_to_skill_values_are_valid_skills(self):
        """Every PAGE_TO_SKILL value must be a member of AVAILABLE_SKILLS."""
        invalid = set(PAGE_TO_SKILL.values()) - AVAILABLE_SKILLS
        assert not invalid, f"PAGE_TO_SKILL maps to unknown skills: {invalid}"

    def test_unknown_route_returns_none(self):
        """Unknown route returns None."""
        assert get_preloaded_skill({"route": "/dashboard"}) is None

    def test_none_context_returns_none(self):
        """None page_context returns None."""
        assert get_preloaded_skill(None) is None

    def test_empty_route_returns_none(self):
        """Empty route string returns None."""
        assert get_preloaded_skill({"route": ""}) is None


class TestUpdatePinnedSkills:
    """Tests for skill pinning with LRU eviction."""

    def test_adds_first_skill(self):
        """Adding to empty list puts skill at front."""
        result = update_pinned_skills([], "alerts")
        assert result == ["alerts"]

    def test_adds_second_skill(self):
        """New skill goes to front (most recent)."""
        result = update_pinned_skills(["alerts"], "workflows")
        assert result == ["workflows", "alerts"]

    def test_reaccessing_moves_to_front(self):
        """Re-accessing a pinned skill moves it to front."""
        result = update_pinned_skills(["alerts", "workflows"], "workflows")
        assert result == ["workflows", "alerts"]

    def test_evicts_lru_at_cap(self):
        """When cap is reached, least-recently-used is evicted."""
        result = update_pinned_skills(["a", "b", "c"], "d")
        assert result == ["d", "a", "b"]
        assert "c" not in result  # LRU evicted

    def test_max_pinned_skills_constant(self):
        """MAX_PINNED_SKILLS is 3."""
        assert ChatConstants.MAX_PINNED_SKILLS == 3

    def test_never_exceeds_cap(self):
        """Result never exceeds MAX_PINNED_SKILLS entries."""
        skills = ["a", "b", "c"]
        for new in ["d", "e", "f"]:
            skills = update_pinned_skills(skills, new)
            assert len(skills) <= ChatConstants.MAX_PINNED_SKILLS


class TestBuildSystemPrompt:
    """Tests for system prompt construction."""

    def test_includes_security_rules(self):
        """System prompt contains security guardrails."""
        prompt = build_system_prompt()
        assert "NEVER reveal" in prompt
        assert "NEVER execute actions" in prompt

    def test_includes_overview_skill(self):
        """System prompt contains global product overview."""
        prompt = build_system_prompt()
        # Overview skill should mention Analysi
        assert "analysi" in prompt.lower()

    def test_includes_pinned_skill_content(self):
        """With pinned skills, prompt contains their content."""
        prompt = build_system_prompt(pinned_skills=["alerts"])
        # Alerts skill should mention alert lifecycle concepts
        assert "alert" in prompt.lower()
        # Should be longer than without pinned skills
        prompt_no_skills = build_system_prompt()
        assert len(prompt) > len(prompt_no_skills)

    def test_no_pinned_skills(self):
        """Without pinned skills, overview is still present."""
        prompt = build_system_prompt(pinned_skills=[])
        assert "analysi" in prompt.lower()

    def test_includes_reinforcement_block(self):
        """System prompt ends with reinforcement reminder."""
        prompt = build_system_prompt()
        assert "load_product_skill" in prompt

    def test_multiple_pinned_skills(self):
        """Multiple pinned skills are all included."""
        prompt = build_system_prompt(pinned_skills=["alerts", "workflows"])
        assert "alert" in prompt.lower()
        assert "workflow" in prompt.lower()

    def test_invalid_skill_name_skipped(self):
        """Invalid skill name in pinned list is skipped gracefully."""
        # Should not raise — just logs a warning and skips
        prompt = build_system_prompt(pinned_skills=["nonexistent_skill"])
        assert "NEVER reveal" in prompt  # Security rules still present


class TestValidateSkillBudgets:
    """Tests for token budget validation."""

    def test_all_skills_under_budget(self):
        """No skill exceeds its token budget."""
        results = validate_skill_budgets()
        over_budget = [
            f"{name}: {info['tokens']}/{info['budget']} tokens"
            for name, info in results.items()
            if info.get("over")
        ]
        assert not over_budget, f"Skills over budget: {over_budget}"

    def test_all_skill_files_exist(self):
        """All budgeted skills have files on disk."""
        results = validate_skill_budgets()
        missing = [name for name, info in results.items() if info.get("missing")]
        assert not missing, f"Missing skill files: {missing}"

    def test_returns_token_counts(self):
        """Validation returns token estimates for each skill."""
        results = validate_skill_budgets()
        for name, info in results.items():
            assert "tokens" in info
            assert "budget" in info
            if not info.get("missing"):
                assert info["tokens"] > 0, f"Skill {name} has 0 tokens"
