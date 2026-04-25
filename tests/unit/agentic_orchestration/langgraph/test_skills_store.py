"""Tests for SkillsIR ResourceStore implementations.

Removed FileSystemResourceStore tests - skills are now DB-only.
WikiLink expansion tests use MockResourceStore for testing the abstract base class logic.
"""

import tempfile
from pathlib import Path

import pytest

from analysi.agentic_orchestration.langgraph.skills.store import (
    MAX_WIKILINK_DEPTH,
    ResourceStore,
    extract_wikilinks,
)


class MockResourceStore(ResourceStore):
    """Test-only ResourceStore that reads from filesystem.

    This is used to test WikiLink expansion logic in the ResourceStore base class.
    Production code uses DatabaseResourceStore.
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def list_skills(self) -> dict[str, str]:
        """List all skills in the directory."""
        skills = {}
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # Extract description from frontmatter
                description = ""
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        for line in parts[1].strip().split("\n"):
                            if line.startswith("description:"):
                                description = line.split(":", 1)[1].strip()
                                break
                skills[skill_dir.name] = description
        return skills

    def tree(self, skill: str) -> list[str]:
        """Get all file paths within a skill."""
        skill_dir = self.skills_dir / skill
        if not skill_dir.exists():
            return []
        paths = []
        for path in skill_dir.rglob("*"):
            if path.is_file():
                paths.append(str(path.relative_to(skill_dir)))
        return sorted(paths)

    def read(self, skill: str, path: str) -> str | None:
        """Read content of a file within a skill."""
        file_path = self.skills_dir / skill / path
        if not file_path.exists():
            return None
        return file_path.read_text()


class TestExtractWikilinks:
    """Tests for extract_wikilinks() function."""

    def test_extracts_single_wikilink(self):
        """Extracts single WikiLink from content."""
        content = "See ![[common/alert.md]] for details"
        links = extract_wikilinks(content)
        assert links == ["common/alert.md"]

    def test_extracts_multiple_wikilinks(self):
        """Extracts multiple WikiLinks from content."""
        content = """
        First ![[common/alert.md]] reference.
        Second ![[references/guide.md]] reference.
        """
        links = extract_wikilinks(content)
        assert links == ["common/alert.md", "references/guide.md"]

    def test_returns_empty_for_no_wikilinks(self):
        """Returns empty list when no WikiLinks present."""
        content = "No WikiLinks here"
        links = extract_wikilinks(content)
        assert links == []

    def test_ignores_non_embed_wikilinks(self):
        """Only extracts embed WikiLinks (with ! prefix)."""
        content = "Link [[not-embed.md]] vs embed ![[embed.md]]"
        links = extract_wikilinks(content)
        assert links == ["embed.md"]

    def test_handles_nested_paths(self):
        """Handles deeply nested file paths."""
        content = "![[a/b/c/d/file.md]]"
        links = extract_wikilinks(content)
        assert links == ["a/b/c/d/file.md"]

    def test_extracts_from_code_blocks(self):
        """Currently extracts WikiLinks even inside code blocks.

        Note: This documents current behavior. In the future, we may want
        to skip WikiLinks inside fenced code blocks.
        """
        content = """
        Normal text with ![[normal.md]]

        ```markdown
        Example: ![[example.md]]
        ```
        """
        links = extract_wikilinks(content)
        # Currently extracts both - may want to change this behavior
        assert "normal.md" in links
        assert "example.md" in links

    def test_handles_duplicate_wikilinks(self):
        """Same WikiLink appearing multiple times."""
        content = """
        First reference: ![[common/header.md]]
        Second reference: ![[common/header.md]]
        """
        links = extract_wikilinks(content)
        # Returns duplicates (caller can dedupe if needed)
        assert links == ["common/header.md", "common/header.md"]


class TestWikiLinkExpansion:
    """Tests for WikiLink expansion in ResourceStore."""

    @pytest.fixture
    def skills_with_wikilinks(self) -> Path:
        """Create skills directory with WikiLink references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            # Create skill with WikiLinks
            skill = skills_dir / "test-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test skill\n---\n# Test Skill"
            )

            # Create common/ directory with reusable content
            common = skill / "common"
            common.mkdir()
            (common / "header.md").write_text("## Standard Header\nThis is the header.")
            (common / "footer.md").write_text("## Standard Footer\nThis is the footer.")

            # Create a file that references common files via WikiLinks
            repository = skill / "repository"
            repository.mkdir()
            (repository / "main-doc.md").write_text(
                "# Main Document\n\n"
                "![[common/header.md]]\n\n"
                "Main content here.\n\n"
                "![[common/footer.md]]"
            )

            # Create nested WikiLinks (file that references another file with WikiLinks)
            (common / "wrapper.md").write_text(
                "## Wrapper\n![[common/header.md]]\nWrapper content."
            )
            (repository / "nested-doc.md").write_text(
                "# Nested Document\n![[common/wrapper.md]]"
            )

            # Create cycle: a.md -> b.md -> a.md
            cycles = skill / "cycles"
            cycles.mkdir()
            (cycles / "cycle-a.md").write_text("# Cycle A\n![[cycles/cycle-b.md]]")
            (cycles / "cycle-b.md").write_text("# Cycle B\n![[cycles/cycle-a.md]]")

            yield skills_dir

    def test_read_expanded_expands_single_wikilink(self, skills_with_wikilinks: Path):
        """read_expanded() replaces WikiLink with actual content."""
        store = MockResourceStore(skills_with_wikilinks)

        content, count = store.read_expanded("test-skill", "repository/main-doc.md")

        # WikiLinks should be replaced
        assert "![[common/header.md]]" not in content
        assert "![[common/footer.md]]" not in content
        # Actual content should be present
        assert "## Standard Header" in content
        assert "This is the header." in content
        assert "## Standard Footer" in content
        assert "This is the footer." in content
        # Original content should still be there
        assert "# Main Document" in content
        assert "Main content here." in content
        # Count should reflect expanded WikiLinks
        assert count == 2

    def test_read_expanded_handles_nested_wikilinks(self, skills_with_wikilinks: Path):
        """read_expanded() recursively expands nested WikiLinks."""
        store = MockResourceStore(skills_with_wikilinks)

        content, count = store.read_expanded("test-skill", "repository/nested-doc.md")

        # All WikiLinks should be expanded
        assert "![[" not in content
        # Nested content should be present
        assert "## Wrapper" in content
        assert "## Standard Header" in content
        assert "This is the header." in content
        # Count should include nested expansions (wrapper + header inside wrapper)
        assert count == 2

    def test_read_expanded_handles_cycles(self, skills_with_wikilinks: Path):
        """read_expanded() handles cyclic WikiLinks without infinite loop."""
        store = MockResourceStore(skills_with_wikilinks)

        # This should not hang - cycle detection should prevent infinite recursion
        content, count = store.read_expanded("test-skill", "cycles/cycle-a.md")

        # Should have cycle comment instead of expanding infinitely
        assert "# Cycle A" in content
        assert "# Cycle B" in content
        assert "<!-- WikiLink cycle:" in content
        # Two WikiLinks processed: cycle-b expanded, cycle-a-back-ref replaced with cycle comment
        assert count == 2

    def test_read_expanded_handles_missing_target(self, skills_with_wikilinks: Path):
        """read_expanded() handles WikiLinks to non-existent files gracefully."""
        store = MockResourceStore(skills_with_wikilinks)

        # Create a file with WikiLink to non-existent file
        skill_dir = skills_with_wikilinks / "test-skill"
        (skill_dir / "broken-link.md").write_text("# Broken\n![[nonexistent/file.md]]")

        content, count = store.read_expanded("test-skill", "broken-link.md")

        # Should have comment for missing file
        assert "# Broken" in content
        assert "<!-- WikiLink not found:" in content
        # No successful expansions
        assert count == 0

    def test_read_expanded_returns_none_for_missing_file(
        self, skills_with_wikilinks: Path
    ):
        """read_expanded() returns None if main file doesn't exist."""
        store = MockResourceStore(skills_with_wikilinks)

        content, count = store.read_expanded("test-skill", "nonexistent.md")

        assert content is None
        assert count == 0

    def test_read_vs_read_expanded(self, skills_with_wikilinks: Path):
        """read() preserves WikiLinks, read_expanded() expands them."""
        store = MockResourceStore(skills_with_wikilinks)

        raw = store.read("test-skill", "repository/main-doc.md")
        expanded, count = store.read_expanded("test-skill", "repository/main-doc.md")

        # Raw should have WikiLinks
        assert "![[common/header.md]]" in raw
        # Expanded should not
        assert "![[common/header.md]]" not in expanded
        # Expanded should be longer (has the included content)
        assert len(expanded) > len(raw)
        # Count should be positive
        assert count > 0

    def test_read_expanded_handles_empty_file(self, skills_with_wikilinks: Path):
        """read_expanded() handles WikiLink to empty file."""
        store = MockResourceStore(skills_with_wikilinks)

        # Create empty file
        skill_dir = skills_with_wikilinks / "test-skill"
        (skill_dir / "common" / "empty.md").write_text("")
        (skill_dir / "with-empty-link.md").write_text(
            "# Doc\n![[common/empty.md]]\nMore content"
        )

        content, count = store.read_expanded("test-skill", "with-empty-link.md")

        # Should expand (to empty string) without error
        assert "![[" not in content
        assert "# Doc" in content
        assert "More content" in content
        assert count == 1

    def test_read_expanded_handles_duplicate_wikilinks(
        self, skills_with_wikilinks: Path
    ):
        """read_expanded() handles same WikiLink appearing twice."""
        store = MockResourceStore(skills_with_wikilinks)

        # Create file with duplicate WikiLinks
        skill_dir = skills_with_wikilinks / "test-skill"
        (skill_dir / "duplicate-links.md").write_text(
            "# Start\n"
            "![[common/header.md]]\n"
            "Middle content\n"
            "![[common/header.md]]\n"
            "# End"
        )

        content, count = store.read_expanded("test-skill", "duplicate-links.md")

        # Both should be expanded
        assert "![[" not in content
        # Header content should appear twice
        assert content.count("## Standard Header") == 2
        # Count reflects both expansions
        assert count == 2

    def test_read_expanded_respects_depth_limit(self, skills_with_wikilinks: Path):
        """read_expanded() stops at MAX_WIKILINK_DEPTH."""
        store = MockResourceStore(skills_with_wikilinks)
        skill_dir = skills_with_wikilinks / "test-skill"

        # Create a chain deeper than MAX_WIKILINK_DEPTH
        deep_dir = skill_dir / "deep"
        deep_dir.mkdir()

        # Create chain: level-0 -> level-1 -> level-2 -> ... -> level-N
        for i in range(MAX_WIKILINK_DEPTH + 3):
            if i == MAX_WIKILINK_DEPTH + 2:
                # Last file has no WikiLinks
                (deep_dir / f"level-{i}.md").write_text(f"# Level {i} (leaf)")
            else:
                # Each file links to the next
                (deep_dir / f"level-{i}.md").write_text(
                    f"# Level {i}\n![[deep/level-{i + 1}.md]]"
                )

        content, count = store.read_expanded("test-skill", "deep/level-0.md")

        # Should have expanded up to MAX_WIKILINK_DEPTH levels
        assert "<!-- WikiLink depth limit reached:" in content
        # Early levels should be expanded
        assert "# Level 0" in content
        assert "# Level 1" in content
        # Should not have expanded beyond the limit
        assert count < MAX_WIKILINK_DEPTH + 3


class TestCycleDetection:
    """Dedicated tests for WikiLink cycle detection."""

    @pytest.fixture
    def skills_with_cycles(self) -> Path:
        """Create skills with various cycle patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            skill = skills_dir / "cycle-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: cycle-skill\ndescription: Test cycles\n---"
            )

            # Direct cycle: A -> A (self-reference)
            (skill / "self-ref.md").write_text("# Self Reference\n![[self-ref.md]]")

            # Simple cycle: A -> B -> A
            (skill / "cycle-a.md").write_text("# A\n![[cycle-b.md]]")
            (skill / "cycle-b.md").write_text("# B\n![[cycle-a.md]]")

            # Triangle cycle: A -> B -> C -> A
            (skill / "triangle-a.md").write_text("# Triangle A\n![[triangle-b.md]]")
            (skill / "triangle-b.md").write_text("# Triangle B\n![[triangle-c.md]]")
            (skill / "triangle-c.md").write_text("# Triangle C\n![[triangle-a.md]]")

            # Diamond with cycle: A -> B, A -> C, B -> D, C -> D, D -> A
            diamond = skill / "diamond"
            diamond.mkdir()
            (diamond / "a.md").write_text("# A\n![[diamond/b.md]]\n![[diamond/c.md]]")
            (diamond / "b.md").write_text("# B\n![[diamond/d.md]]")
            (diamond / "c.md").write_text("# C\n![[diamond/d.md]]")
            (diamond / "d.md").write_text("# D\n![[diamond/a.md]]")

            yield skills_dir

    def test_self_reference_cycle(self, skills_with_cycles: Path):
        """File referencing itself is detected as cycle."""
        store = MockResourceStore(skills_with_cycles)

        content, count = store.read_expanded("cycle-skill", "self-ref.md")

        assert "# Self Reference" in content
        assert "<!-- WikiLink cycle: self-ref.md -->" in content
        # Self-reference WikiLink was replaced with cycle comment
        assert count == 1

    def test_simple_two_file_cycle(self, skills_with_cycles: Path):
        """A -> B -> A cycle is detected."""
        store = MockResourceStore(skills_with_cycles)

        content, count = store.read_expanded("cycle-skill", "cycle-a.md")

        assert "# A" in content
        assert "# B" in content
        assert "<!-- WikiLink cycle: cycle-a.md -->" in content
        # Both WikiLinks were replaced: B expanded + A-back-reference replaced with cycle comment
        assert count == 2

    def test_triangle_cycle(self, skills_with_cycles: Path):
        """A -> B -> C -> A cycle is detected."""
        store = MockResourceStore(skills_with_cycles)

        content, count = store.read_expanded("cycle-skill", "triangle-a.md")

        assert "# Triangle A" in content
        assert "# Triangle B" in content
        assert "# Triangle C" in content
        assert "<!-- WikiLink cycle: triangle-a.md -->" in content
        # All 3 WikiLinks replaced: B, C expanded + A-back-reference replaced with cycle comment
        assert count == 3

    def test_diamond_with_cycle(self, skills_with_cycles: Path):
        """Diamond pattern with back-edge is handled correctly."""
        store = MockResourceStore(skills_with_cycles)

        content, count = store.read_expanded("cycle-skill", "diamond/a.md")

        # All nodes should appear
        assert "# A" in content
        assert "# B" in content
        assert "# C" in content
        assert "# D" in content
        # Back-reference to A should be detected
        assert "<!-- WikiLink cycle:" in content


class TestDepthLimit:
    """Dedicated tests for WikiLink depth limiting."""

    @pytest.fixture
    def skills_with_depth(self) -> Path:
        """Create skills with deep nesting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            skill = skills_dir / "depth-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: depth-skill\ndescription: Test depth\n---"
            )

            # Create deep chain without cycles
            for i in range(MAX_WIKILINK_DEPTH + 5):
                if i == MAX_WIKILINK_DEPTH + 4:
                    (skill / f"level-{i}.md").write_text(f"# Level {i} LEAF")
                else:
                    (skill / f"level-{i}.md").write_text(
                        f"# Level {i}\nContent at level {i}\n![[level-{i + 1}.md]]"
                    )

            # Create wide tree (multiple WikiLinks at each level)
            wide = skill / "wide"
            wide.mkdir()
            (wide / "root.md").write_text(
                "# Root\n![[wide/branch-a.md]]\n![[wide/branch-b.md]]"
            )
            (wide / "branch-a.md").write_text(
                "# Branch A\n![[wide/leaf-a1.md]]\n![[wide/leaf-a2.md]]"
            )
            (wide / "branch-b.md").write_text(
                "# Branch B\n![[wide/leaf-b1.md]]\n![[wide/leaf-b2.md]]"
            )
            for leaf in ["leaf-a1", "leaf-a2", "leaf-b1", "leaf-b2"]:
                (wide / f"{leaf}.md").write_text(f"# {leaf.upper()}")

            yield skills_dir

    def test_depth_limit_stops_expansion(self, skills_with_depth: Path):
        """Expansion stops at MAX_WIKILINK_DEPTH."""
        store = MockResourceStore(skills_with_depth)

        content, count = store.read_expanded("depth-skill", "level-0.md")

        # Should see depth limit comment
        assert "<!-- WikiLink depth limit reached:" in content
        # First few levels should be there
        for i in range(min(5, MAX_WIKILINK_DEPTH)):
            assert f"# Level {i}" in content
        # Leaf should NOT be reached (it's beyond the limit)
        assert "LEAF" not in content

    def test_wide_tree_within_depth_limit(self, skills_with_depth: Path):
        """Wide tree (multiple branches) within depth limit expands fully."""
        store = MockResourceStore(skills_with_depth)

        content, count = store.read_expanded("depth-skill", "wide/root.md")

        # All content should be expanded (depth is only 3)
        assert "# Root" in content
        assert "# Branch A" in content
        assert "# Branch B" in content
        assert "# LEAF-A1" in content
        assert "# LEAF-A2" in content
        assert "# LEAF-B1" in content
        assert "# LEAF-B2" in content
        # No depth limit hit
        assert "<!-- WikiLink depth limit" not in content
        # 6 WikiLinks expanded: 2 at root, 2 at branch-a, 2 at branch-b
        assert count == 6

    def test_depth_limit_value(self):
        """MAX_WIKILINK_DEPTH is a reasonable value."""
        # Should be enough for practical use but not too high
        assert 5 <= MAX_WIKILINK_DEPTH <= 20, (
            f"MAX_WIKILINK_DEPTH={MAX_WIKILINK_DEPTH} seems unreasonable"
        )
