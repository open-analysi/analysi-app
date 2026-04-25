"""Tests for Runbook Matching validators."""

import json

from analysi.agentic_orchestration.langgraph.kea.phase1.validators import (
    validate_confidence,
    validate_extraction,
    validate_gap_analysis,
    validate_matches,
    validate_runbook_output,
    validate_strategy,
)


class TestValidateMatches:
    """Tests for validate_matches."""

    def test_validate_matches_valid(self):
        """Valid matches list passes."""
        output = json.dumps(
            {
                "matches": [
                    {
                        "runbook": {"filename": "test.md"},
                        "score": 150,
                        "explanation": {},
                    },
                ],
                "top_score": 150,
                "has_exact_rule": True,
            }
        )
        result = validate_matches(output)
        assert result.passed is True

    def test_validate_matches_multiple(self):
        """Multiple matches passes."""
        output = json.dumps(
            {
                "matches": [
                    {"runbook": {"filename": "a.md"}, "score": 150, "explanation": {}},
                    {"runbook": {"filename": "b.md"}, "score": 100, "explanation": {}},
                ],
                "top_score": 150,
                "has_exact_rule": False,
            }
        )
        result = validate_matches(output)
        assert result.passed is True

    def test_validate_matches_empty(self):
        """Empty matches fails."""
        output = json.dumps(
            {
                "matches": [],
                "top_score": 0,
                "has_exact_rule": False,
            }
        )
        result = validate_matches(output)
        assert result.passed is False
        assert len(result.errors) > 0

    def test_validate_matches_missing_score(self):
        """Match without score fails."""
        output = json.dumps(
            {
                "matches": [
                    {"runbook": {"filename": "test.md"}, "explanation": {}},
                ],
                "top_score": 0,
                "has_exact_rule": False,
            }
        )
        result = validate_matches(output)
        assert result.passed is False

    def test_validate_matches_invalid_json(self):
        """Invalid JSON fails."""
        result = validate_matches("not valid json")
        assert result.passed is False


class TestValidateConfidence:
    """Tests for validate_confidence."""

    def test_validate_confidence_valid(self):
        """Valid confidence level passes."""
        output = json.dumps(
            {
                "confidence": "high",
                "score": 150,
                "path": "match",
            }
        )
        result = validate_confidence(output)
        assert result.passed is True

    def test_validate_confidence_all_levels(self):
        """All confidence levels are valid."""
        for level in ["very_high", "high", "medium", "low", "very_low"]:
            output = json.dumps(
                {
                    "confidence": level,
                    "score": 100,
                    "path": "match" if level in ["very_high", "high"] else "compose",
                }
            )
            result = validate_confidence(output)
            assert result.passed is True, f"Failed for level: {level}"

    def test_validate_confidence_invalid_level(self):
        """Invalid enum value fails."""
        output = json.dumps(
            {
                "confidence": "super_high",  # Invalid
                "score": 200,
                "path": "match",
            }
        )
        result = validate_confidence(output)
        assert result.passed is False

    def test_validate_confidence_missing_field(self):
        """Missing required field fails."""
        output = json.dumps(
            {
                "confidence": "high",
                # Missing score and path
            }
        )
        result = validate_confidence(output)
        assert result.passed is False


class TestValidateRunbookOutput:
    """Tests for validate_runbook_output.

    Composed runbooks should:
    - Have ★ critical step markers
    - NOT have @include directives
    - NOT have WikiLinks
    - NOT have YAML frontmatter (that's for stored runbooks)
    - Have valid markdown hierarchy
    """

    def test_validate_runbook_valid(self):
        """Valid composed runbook passes all checks."""
        runbook = """# Investigation

## Steps

### 1. First Step ★
Do something critical.

### 2. Second Step ★
Do another critical thing.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is True
        assert result.errors == []

    def test_validate_runbook_with_yaml_frontmatter_fails(self):
        """YAML frontmatter fails (that's for stored runbooks only)."""
        runbook = """---
title: Test Runbook
---

# Investigation

## Steps

### 1. Step ★
Content.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("frontmatter" in e.lower() for e in result.errors)

    def test_validate_runbook_with_includes_fails(self):
        """Has @include fails."""
        runbook = """# Investigation

@include common/header.md

## Steps

### 1. Step ★
Content.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("include" in e.lower() for e in result.errors)

    def test_validate_runbook_with_wikilinks_fails(self):
        """Has WikiLinks fails."""
        runbook = """# Investigation

## Steps

### 1. Step ★
See also ![[common/reference.md]] for details.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("wikilink" in e.lower() for e in result.errors)

    def test_validate_runbook_no_critical_fails(self):
        """Missing ★ fails."""
        runbook = """# Investigation

## Steps

### 1. Step
No critical markers here.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("critical" in e.lower() or "★" in e for e in result.errors)

    def test_validate_runbook_empty_fails(self):
        """Empty runbook fails."""
        result = validate_runbook_output("")
        assert result.passed is False

    def test_validate_runbook_no_headings_fails(self):
        """No headings fails."""
        runbook = """This is just text with a ★ marker but no headings."""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("heading" in e.lower() for e in result.errors)

    def test_validate_runbook_skipped_heading_level_fails(self):
        """Skipped heading level fails (H1 -> H3)."""
        runbook = """# Investigation

### 1. Step ★
Skipped H2 level.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("skipped" in e.lower() for e in result.errors)

    def test_validate_runbook_missing_steps_section_fails(self):
        """Missing Steps section fails."""
        runbook = """# Investigation

## Overview

### 1. Item ★
No steps section.
"""
        result = validate_runbook_output(runbook)
        assert result.passed is False
        assert any("steps" in e.lower() for e in result.errors)


class TestValidateGapAnalysis:
    """Tests for validate_gap_analysis."""

    def test_validate_gaps_valid_json(self):
        """Valid JSON with gaps passes."""
        output = json.dumps(
            {
                "gaps": [
                    {
                        "category": "authentication",
                        "description": "Missing MFA check",
                        "severity": "high",
                    },
                    {
                        "category": "logging",
                        "description": "No audit trail",
                        "severity": "medium",
                    },
                ],
                "coverage_assessment": "Top match covers 60% of alert scope",
            }
        )
        result = validate_gap_analysis(output)
        assert result.passed is True

    def test_validate_gaps_empty_list(self):
        """Empty gaps list is valid (no gaps found)."""
        output = json.dumps(
            {
                "gaps": [],
                "coverage_assessment": "Top match fully covers alert scope",
            }
        )
        result = validate_gap_analysis(output)
        assert result.passed is True

    def test_validate_gaps_invalid_json(self):
        """Invalid JSON fails."""
        result = validate_gap_analysis("not json")
        assert result.passed is False

    def test_validate_gaps_missing_field(self):
        """Missing required field fails."""
        output = json.dumps(
            {
                "gaps": [{"category": "test"}],
                # Missing coverage_assessment
            }
        )
        result = validate_gap_analysis(output)
        assert result.passed is False


class TestValidateStrategy:
    """Tests for validate_strategy."""

    def test_validate_strategy_valid(self):
        """Valid strategy JSON passes."""
        output = json.dumps(
            {
                "strategy": "multi_source_blending",
                "sources": [
                    {
                        "runbook": "sql-injection.md",
                        "sections": ["payload_analysis"],
                        "reason": "covers injection",
                    },
                    {
                        "runbook": "xss-detection.md",
                        "sections": ["reflection_check"],
                        "reason": "covers XSS",
                    },
                ],
                "template": "hybrid-attack-template",
            }
        )
        result = validate_strategy(output)
        assert result.passed is True

    def test_validate_strategy_all_types(self):
        """All strategy types are valid."""
        strategies = [
            "same_attack_family_adaptation",
            "multi_source_blending",
            "category_based_assembly",
            "minimal_scaffold",
        ]
        for strategy in strategies:
            output = json.dumps(
                {
                    "strategy": strategy,
                    "sources": [],
                    "template": None,
                }
            )
            result = validate_strategy(output)
            assert result.passed is True, f"Failed for strategy: {strategy}"

    def test_validate_strategy_invalid_json(self):
        """Invalid format fails."""
        result = validate_strategy("not json")
        assert result.passed is False

    def test_validate_strategy_missing_strategy(self):
        """Missing strategy field fails."""
        output = json.dumps(
            {
                "sources": [],
            }
        )
        result = validate_strategy(output)
        assert result.passed is False


class TestValidateExtraction:
    """Tests for validate_extraction."""

    def test_validate_extraction_valid(self):
        """Valid extraction with provenance passes."""
        output = json.dumps(
            {
                "extractions": [
                    {
                        "content": "## Payload Analysis\n...",
                        "source": "sql-injection.md",
                        "section": "payload_analysis",
                    },
                    {
                        "content": "## XSS Check\n...",
                        "source": "xss-detection.md",
                        "section": "reflection_check",
                    },
                ],
                "remaining_gaps": ["MFA verification"],
            }
        )
        result = validate_extraction(output)
        assert result.passed is True

    def test_validate_extraction_no_remaining_gaps(self):
        """Empty remaining_gaps is valid."""
        output = json.dumps(
            {
                "extractions": [
                    {"content": "content", "source": "src.md", "section": "sec"},
                ],
                "remaining_gaps": [],
            }
        )
        result = validate_extraction(output)
        assert result.passed is True

    def test_validate_extraction_no_provenance(self):
        """Missing provenance (source) fails."""
        output = json.dumps(
            {
                "extractions": [
                    {"content": "content", "section": "sec"},  # Missing source
                ],
                "remaining_gaps": [],
            }
        )
        result = validate_extraction(output)
        assert result.passed is False

    def test_validate_extraction_invalid_json(self):
        """Invalid JSON fails."""
        result = validate_extraction("not json")
        assert result.passed is False


class TestMarkdownCodeBlockExtraction:
    """Tests for JSON extraction from markdown code blocks."""

    def test_validate_gaps_with_markdown_json_block(self):
        """JSON wrapped in ```json ... ``` passes."""
        output = """```json
{
    "gaps": [{"category": "test", "description": "desc", "severity": "high"}],
    "coverage_assessment": "50%"
}
```"""
        result = validate_gap_analysis(output)
        assert result.passed is True

    def test_validate_gaps_with_plain_markdown_block(self):
        """JSON wrapped in ``` ... ``` (no json tag) passes."""
        output = """```
{"gaps": [], "coverage_assessment": "full coverage"}
```"""
        result = validate_gap_analysis(output)
        assert result.passed is True

    def test_validate_strategy_with_markdown_block(self):
        """Strategy JSON in markdown passes."""
        output = """Here is the strategy:

```json
{
    "strategy": "multi_source_blending",
    "sources": [{"runbook": "a.md", "sections": ["s1"], "reason": "test"}],
    "template": null
}
```

Hope this helps!"""
        result = validate_strategy(output)
        assert result.passed is True

    def test_validate_extraction_with_markdown_block(self):
        """Extraction JSON in markdown passes."""
        output = """```json
{
    "extractions": [{"content": "test", "source": "src.md", "section": "s"}],
    "remaining_gaps": []
}
```"""
        result = validate_extraction(output)
        assert result.passed is True

    def test_validate_matches_with_markdown_block(self):
        """Matches JSON in markdown passes."""
        output = """```json
{
    "matches": [{"runbook": {"filename": "test.md"}, "score": 100}],
    "top_score": 100,
    "has_exact_rule": false
}
```"""
        result = validate_matches(output)
        assert result.passed is True

    def test_validate_confidence_with_markdown_block(self):
        """Confidence JSON in markdown passes."""
        output = """```json
{
    "confidence": "high",
    "score": 150,
    "path": "match"
}
```"""
        result = validate_confidence(output)
        assert result.passed is True
