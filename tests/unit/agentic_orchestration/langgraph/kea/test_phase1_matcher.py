"""Tests for Runbook Matching matcher wrapper.

Requires the runbooks-manager skill to be installed locally
(~/.claude/skills/runbooks-manager/) or seeded in the database.
Skipped in CI where skills are not available.
"""

import json
import tempfile
from pathlib import Path

import pytest

# Skip entire module if RunbookMatcher script is not available
_SKILL_PATHS = [
    Path(__file__).parents[5]
    / "docker"
    / "agents_skills"
    / "skills"
    / "runbooks-manager"
    / "scripts"
    / "match_scorer.py",
    Path.home()
    / ".claude"
    / "skills"
    / "runbooks-manager"
    / "scripts"
    / "match_scorer.py",
]
if not any(p.exists() for p in _SKILL_PATHS):
    pytest.skip("RunbookMatcher skill not available", allow_module_level=True)

from analysi.agentic_orchestration.langgraph.kea.phase1.matcher import (  # noqa: E402
    Phase1Matcher,
)


@pytest.fixture
def temp_repository():
    """Create a temporary runbook repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create index file
        index = [
            {
                "filename": "sql-injection-detection.md",
                "detection_rule": "Possible SQL Injection Payload Detected",
                "alert_type": "Web Attack",
                "subcategory": "SQL Injection",
                "source_category": "WAF",
                "mitre_tactics": ["T1190"],
            },
            {
                "filename": "idor-detection.md",
                "detection_rule": "IDOR Attempt Detected",
                "alert_type": "Web Attack",
                "subcategory": "IDOR",
                "source_category": "WAF",
                "mitre_tactics": ["T1190"],
            },
            {
                "filename": "xss-detection.md",
                "detection_rule": "XSS Payload Detected",
                "alert_type": "Web Attack",
                "subcategory": "XSS",
                "source_category": "WAF",
                "mitre_tactics": ["T1189"],
            },
        ]
        (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": index}))

        # Create runbook files
        (repo_path / "sql-injection-detection.md").write_text(
            """---
title: SQL Injection Investigation
detection_rule: Possible SQL Injection Payload Detected
---

# SQL Injection Investigation

## Steps

### 1. Alert Understanding ★
Review the SQL injection attempt details.

### 2. Payload Analysis ★
Analyze the injection payload.
"""
        )

        (repo_path / "runbook-with-wikilinks.md").write_text(
            """---
title: Test Runbook
---

# Investigation

![[common/header.md]]

## Steps

### 1. Step ★
Content.
"""
        )

        # Create common directory for WikiLink expansion
        (repo_path / "common").mkdir()
        (repo_path / "common" / "header.md").write_text(
            "# Common Header\nShared content."
        )

        yield repo_path


class TestPhase1MatcherLoading:
    """Tests for index loading."""

    def test_load_index(self, temp_repository):
        """Loads runbook index from repository."""
        matcher = Phase1Matcher(temp_repository)
        index = matcher.load_index()

        assert len(index) == 3
        assert index[0]["filename"] == "sql-injection-detection.md"

    def test_load_index_via_init(self, temp_repository):
        """Index is loaded on initialization if path exists."""
        matcher = Phase1Matcher(temp_repository)
        # Index should be accessible
        assert len(matcher.load_index()) == 3

    def test_load_index_missing_file(self, temp_repository):
        """Handles missing index file gracefully."""
        (temp_repository / "all_runbooks.json").unlink()

        matcher = Phase1Matcher(temp_repository)
        index = matcher.load_index()

        assert index == []


class TestPhase1MatcherScoring:
    """Tests for match scoring."""

    def test_find_matches_exact_rule(self, temp_repository, sample_alert_exact_match):
        """Exact detection_rule match scores highest."""
        matcher = Phase1Matcher(temp_repository)
        matches = matcher.find_matches(sample_alert_exact_match)

        assert len(matches) > 0
        top_match = matches[0]
        assert top_match["runbook"]["filename"] == "sql-injection-detection.md"
        assert top_match["score"] >= 100  # Exact rule match gives 100 points

    def test_find_matches_returns_explanation(
        self, temp_repository, sample_alert_exact_match
    ):
        """Matches include explanation."""
        matcher = Phase1Matcher(temp_repository)
        matches = matcher.find_matches(sample_alert_exact_match)

        assert "explanation" in matches[0]
        assert "matched_criteria" in matches[0]["explanation"]

    def test_find_matches_subcategory(self, temp_repository):
        """Same subcategory boosts score."""
        matcher = Phase1Matcher(temp_repository)
        alert = {
            "detection_rule": "Custom Rule",
            "alert_type": "Web Attack",
            "subcategory": "SQL Injection",
            "source_category": "WAF",
        }
        matches = matcher.find_matches(alert)

        # SQL injection runbook should score higher due to subcategory match
        assert len(matches) > 0
        assert any(m["runbook"]["subcategory"] == "SQL Injection" for m in matches)

    def test_find_matches_similar_family(self, temp_repository):
        """Similar attack family matches."""
        matcher = Phase1Matcher(temp_repository)
        # NoSQL injection is in same family as SQL injection
        alert = {
            "detection_rule": "Custom NoSQL Rule",
            "alert_type": "Web Attack",
            "subcategory": "NoSQL Injection",
            "source_category": "WAF",
        }
        matches = matcher.find_matches(alert)

        # Should find SQL injection runbook as similar family
        assert len(matches) > 0

    def test_no_matches(self, temp_repository):
        """Alert with no matching runbooks returns empty."""
        matcher = Phase1Matcher(temp_repository)
        alert = {
            "detection_rule": "Completely Unrelated Rule",
            "alert_type": "Physical Security",
            "subcategory": "Badge Access",
            "source_category": "PACS",
        }
        matches = matcher.find_matches(alert)

        assert matches == []

    def test_multiple_high_scores(self, temp_repository):
        """Multiple high scores are ranked correctly."""
        matcher = Phase1Matcher(temp_repository)
        alert = {
            "detection_rule": "Custom Rule",
            "alert_type": "Web Attack",
            "subcategory": "Web Attack",  # Broad match
            "source_category": "WAF",
            "mitre_tactics": ["T1190", "T1189"],
        }
        matches = matcher.find_matches(alert, top_n=3)

        assert len(matches) >= 2
        # Should be sorted by score descending
        scores = [m["score"] for m in matches]
        assert scores == sorted(scores, reverse=True)


class TestPhase1MatcherContent:
    """Tests for runbook content retrieval."""

    def test_get_runbook_content(self, temp_repository):
        """Returns runbook content for filename."""
        matcher = Phase1Matcher(temp_repository)
        content = matcher.get_runbook_content("sql-injection-detection.md")

        assert "SQL Injection Investigation" in content
        assert "★" in content

    def test_get_runbook_content_not_found(self, temp_repository):
        """Returns empty string for missing runbook."""
        matcher = Phase1Matcher(temp_repository)
        content = matcher.get_runbook_content("nonexistent.md")

        assert content == ""

    def test_expand_wikilinks(self, temp_repository):
        """WikiLinks in runbook are expanded."""
        matcher = Phase1Matcher(temp_repository)
        content = matcher.get_runbook_content(
            "runbook-with-wikilinks.md", expand_wikilinks=True
        )

        # WikiLink should be expanded to include content
        assert "Common Header" in content
        assert "Shared content" in content
        # Original WikiLink syntax should be gone
        assert "![[common/header.md]]" not in content

    def test_no_expand_wikilinks(self, temp_repository):
        """Can skip WikiLink expansion."""
        matcher = Phase1Matcher(temp_repository)
        content = matcher.get_runbook_content(
            "runbook-with-wikilinks.md", expand_wikilinks=False
        )

        # WikiLink should remain
        assert "![[common/header.md]]" in content
