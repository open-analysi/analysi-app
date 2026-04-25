"""Tests for Runbook Matching SubStep definitions."""

from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
    create_analyze_gaps_substep,
    create_compose_runbook_substep,
    create_extract_sections_substep,
    create_fetch_runbook_substep,
    create_fix_runbook_substep,
    create_load_and_score_substep,
    create_select_strategy_substep,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.validators import (
    validate_matched_runbook,
    validate_runbook_output,
)


class TestMatchPathSubSteps:
    """Tests for match path (deterministic) SubSteps."""

    def test_load_and_score_deterministic(self):
        """load_and_score has needs_context=False."""
        substep = create_load_and_score_substep()

        assert substep.needs_context is False
        assert substep.name == "load_and_score"

    def test_load_and_score_has_validator(self):
        """load_and_score has a validator."""
        substep = create_load_and_score_substep()

        assert substep.validator is not None

    def test_fetch_runbook_deterministic(self):
        """fetch_runbook has needs_context=False."""
        substep = create_fetch_runbook_substep()

        assert substep.needs_context is False
        assert substep.name == "fetch_runbook"

    def test_fetch_runbook_has_validator(self):
        """fetch_runbook has a validator."""
        substep = create_fetch_runbook_substep()

        assert substep.validator is not None


class TestCompositionPathSubSteps:
    """Tests for composition path (LLM) SubSteps."""

    def test_analyze_gaps_uses_context(self):
        """analyze_gaps has needs_context=True and uses runbooks-manager."""
        substep = create_analyze_gaps_substep()

        assert substep.needs_context is True
        assert substep.name == "analyze_gaps"
        assert "runbooks-manager" in substep.skills

    def test_analyze_gaps_has_prompt(self):
        """analyze_gaps has a task prompt."""
        substep = create_analyze_gaps_substep()

        assert substep.task_prompt is not None
        assert len(substep.task_prompt) > 0

    def test_select_strategy_uses_context(self):
        """select_strategy has needs_context=True."""
        substep = create_select_strategy_substep()

        assert substep.needs_context is True
        assert substep.name == "select_strategy"
        assert "runbooks-manager" in substep.skills

    def test_extract_sections_uses_context(self):
        """extract_sections has needs_context=True."""
        substep = create_extract_sections_substep()

        assert substep.needs_context is True
        assert substep.name == "extract_sections"

    def test_compose_runbook_uses_context(self):
        """compose_runbook has needs_context=True, uses multiple skills."""
        substep = create_compose_runbook_substep()

        assert substep.needs_context is True
        assert substep.name == "compose_runbook"
        # Should use multiple skills for composition
        assert len(substep.skills) >= 1

    def test_compose_runbook_has_prompt(self):
        """compose_runbook has a comprehensive task prompt."""
        substep = create_compose_runbook_substep()

        assert substep.task_prompt is not None
        # Should mention key composition instructions
        assert "★" in substep.task_prompt or "critical" in substep.task_prompt.lower()

    def test_fix_runbook_uses_context(self):
        """fix_runbook has needs_context=True."""
        substep = create_fix_runbook_substep()

        assert substep.needs_context is True
        assert substep.name == "fix_runbook"

    def test_fix_runbook_has_error_placeholder(self):
        """fix_runbook prompt has placeholder for errors."""
        substep = create_fix_runbook_substep()

        assert (
            "{errors}" in substep.task_prompt or "errors" in substep.task_prompt.lower()
        )


class TestSubStepValidators:
    """Tests for SubStep validators."""

    def test_analyze_gaps_has_json_validator(self):
        """analyze_gaps uses JSON validator."""
        substep = create_analyze_gaps_substep()

        # Test that validator rejects invalid JSON
        result = substep.validator("not json")
        assert result.passed is False

    def test_compose_runbook_uses_passthrough_validator(self):
        """compose_runbook uses passthrough validator (defers to graph-level validation).

        This allows the graph-level fix_runbook loop to handle validation failures.
        """
        substep = create_compose_runbook_substep()

        # Passthrough validator always passes - validation happens at graph level
        result = substep.validator("# Runbook\n\n## Steps\n\n1. Do something")
        assert result.passed is True

        # Also passes with content that would be valid at graph-level
        runbook = """# Investigation

## Steps

### 1. Step ★
Critical step.
"""
        result = substep.validator(runbook)
        assert result.passed is True


class TestCybersecAnalystSkillAvailability:
    """Gap 2: All composition substeps should have cybersecurity-analyst skill.

    The runbook-match-agent loads both runbooks-manager and cybersecurity-analyst
    at startup. LangGraph must make cybersecurity-analyst available to early
    composition substeps (analyze_gaps, select_strategy) so SkillsIR can
    discover investigation patterns for LOW/VERY_LOW confidence alerts.
    """

    def test_analyze_gaps_has_cybersec_skill(self):
        """analyze_gaps needs cybersecurity-analyst for investigation patterns."""
        substep = create_analyze_gaps_substep()
        assert "cybersecurity-analyst" in substep.skills

    def test_select_strategy_has_cybersec_skill(self):
        """select_strategy needs cybersecurity-analyst for minimal scaffold strategy."""
        substep = create_select_strategy_substep()
        assert "cybersecurity-analyst" in substep.skills

    def test_compose_runbook_has_cybersec_skill(self):
        """compose_runbook uses cybersecurity-analyst (already had it)."""
        substep = create_compose_runbook_substep()
        assert "cybersecurity-analyst" in substep.skills

    def test_all_composition_substeps_have_both_skills(self):
        """All LLM composition substeps have both skills matching the agent."""
        required_skills = {"runbooks-manager", "cybersecurity-analyst"}
        for factory in [
            create_analyze_gaps_substep,
            create_select_strategy_substep,
            create_compose_runbook_substep,
        ]:
            substep = factory()
            assert required_skills.issubset(set(substep.skills)), (
                f"{substep.name} missing skills: {required_skills - set(substep.skills)}"
            )


class TestFetchRunbookValidatorAcceptsFrontmatter:
    """Gap 4: fetch_runbook must use a validator that accepts YAML frontmatter.

    Matched runbooks from the repository have YAML frontmatter.
    validate_runbook_output rejects frontmatter (designed for composed runbooks).
    fetch_runbook must use validate_matched_runbook instead.
    """

    def test_fetch_runbook_uses_matched_validator(self):
        """fetch_runbook substep uses validate_matched_runbook, not validate_runbook_output."""
        substep = create_fetch_runbook_substep()
        assert substep.validator is validate_matched_runbook
        assert substep.validator is not validate_runbook_output

    def test_matched_validator_accepts_frontmatter(self):
        """validate_matched_runbook accepts runbooks with YAML frontmatter."""
        runbook_with_frontmatter = """---
detection_rule: "SQL Injection Detected"
alert_type: "Web Attack"
source_category: WAF
mitre_tactics: [T1190]
---

# SQL Injection Investigation

## Steps

### 1. Analyze Payload ★
Check for injection patterns.
"""
        result = validate_matched_runbook(runbook_with_frontmatter)
        assert result.passed is True

    def test_composed_validator_rejects_frontmatter(self):
        """validate_runbook_output rejects frontmatter (confirms the gap existed)."""
        runbook_with_frontmatter = """---
detection_rule: "SQL Injection"
---

# Investigation

## Steps

### 1. Step ★
Content.
"""
        result = validate_runbook_output(runbook_with_frontmatter)
        assert result.passed is False
        assert any("frontmatter" in e.lower() for e in result.errors)

    def test_matched_validator_rejects_unresolved_wikilinks(self):
        """Matched runbooks must still have WikiLinks expanded."""
        runbook = """# Investigation

![[common/header.md]]

## Steps
### 1. Step
Content.
"""
        result = validate_matched_runbook(runbook)
        assert result.passed is False
        assert any("wikilink" in e.lower() for e in result.errors)
