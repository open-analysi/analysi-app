"""RunbookMatcher wrapper for Runbook Matching.

Wraps the RunbookMatcher from runbooks-manager skill for use in SubSteps.
Uses the ACTUAL RunbookMatcher class from the skill to avoid algorithm drift.

Supports two modes:
1. Filesystem-based (original): Phase1Matcher(repository_path)
2. DB-backed via ResourceStore: await Phase1Matcher.from_store(store, skill)
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore

logger = get_logger(__name__)

# WikiLink pattern: ![[path/to/file.md]]
WIKILINK_PATTERN = re.compile(r"!\[\[([^\]]+)\]\]")


def _get_runbook_matcher_class():
    """Import RunbookMatcher from the skill script.

    Uses importlib to import from the actual skill file, avoiding algorithm
    duplication and ensuring consistent behavior with the runbooks-manager skill.
    """
    # Find the skill script - check multiple possible locations
    possible_paths = [
        # Packaged location (git committed)
        Path(__file__).parents[6]
        / "docker"
        / "agents_skills"
        / "skills"
        / "runbooks-manager"
        / "scripts"
        / "match_scorer.py",
        # Development location
        Path.home()
        / ".claude"
        / "skills"
        / "runbooks-manager"
        / "scripts"
        / "match_scorer.py",
    ]

    script_path = None
    for path in possible_paths:
        if path.exists():
            script_path = path
            break

    if script_path is None:
        raise ImportError(
            f"RunbookMatcher script not found. Searched: {[str(p) for p in possible_paths]}"
        )

    # Import the module from file path
    spec = importlib.util.spec_from_file_location("match_scorer", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["match_scorer"] = module
    spec.loader.exec_module(module)

    return module.RunbookMatcher


# Lazy-loaded RunbookMatcher class
_RunbookMatcher = None


def get_runbook_matcher():
    """Get the RunbookMatcher class (lazy loaded)."""
    global _RunbookMatcher
    if _RunbookMatcher is None:
        _RunbookMatcher = _get_runbook_matcher_class()
    return _RunbookMatcher


class Phase1Matcher:
    """Wrapper around RunbookMatcher for Runbook Matching SubSteps.

    Delegates scoring to the actual RunbookMatcher from runbooks-manager skill,
    and adds WikiLink expansion functionality specific to Runbook Matching.

    Supports two directory structures:
    1. Flat structure (tests): all_runbooks.json and *.md in same directory
    2. Skill structure (production): index/all_runbooks.json + repository/*.md
    """

    _store: ResourceStore | None
    _skill: str

    def __init__(self, repository_path: Path | str):
        """Initialize matcher with runbook repository path.

        Args:
            repository_path: Path to runbook repository. Can be:
                - Flat structure: directory containing all_runbooks.json and *.md files
                - Skill structure: skill root with index/ and repository/ subdirectories
        """
        self.repository_path = Path(repository_path)

        # Detect directory structure
        if (self.repository_path / "all_runbooks.json").exists():
            # Flat structure (tests)
            self._index_dir = self.repository_path
            self._runbooks_dir = self.repository_path
        elif (self.repository_path / "index" / "all_runbooks.json").exists():
            # Skill structure (production)
            self._index_dir = self.repository_path / "index"
            self._runbooks_dir = self.repository_path / "repository"
        else:
            # No index found - matcher will have empty runbooks
            self._index_dir = self.repository_path
            self._runbooks_dir = self.repository_path

        # Use the actual RunbookMatcher from the skill
        RunbookMatcher = get_runbook_matcher()
        self._matcher = RunbookMatcher(str(self._index_dir))

    @classmethod
    async def from_store(
        cls, store: ResourceStore, skill: str = "runbooks-manager"
    ) -> Phase1Matcher:
        """Create matcher with index loaded from DB via ResourceStore.

        Reads the runbook index KUTable from the store and configures the
        matcher to use the store for subsequent content reads.

        Args:
            store: ResourceStore (typically DatabaseResourceStore).
            skill: Skill name containing the runbook index.

        Returns:
            Phase1Matcher configured for DB-backed operations.
        """
        instance = object.__new__(cls)
        instance._store = store
        instance._skill = skill
        instance.repository_path = Path("/dev/null")  # Not used for DB mode
        instance._index_dir = instance.repository_path
        instance._runbooks_dir = instance.repository_path

        # Load index from DB (KUTable at index/all_runbooks)
        index_data = await store.read_table_async(skill, "index/all_runbooks")

        # Create matcher with empty index dir (we'll set metadata directly)
        RunbookMatcher = get_runbook_matcher()
        instance._matcher = RunbookMatcher.__new__(RunbookMatcher)
        instance._matcher.index_dir = "/dev/null"

        if index_data and isinstance(index_data, list):
            instance._matcher.runbooks_metadata = index_data
            logger.info(
                "loaded_runbooks_from_db_index", index_data_count=len(index_data)
            )
        else:
            instance._matcher.runbooks_metadata = []
            logger.warning("no_runbook_index_found_in_db_for_skill", skill=skill)

        return instance

    def _is_db_mode(self) -> bool:
        """Check if matcher is operating in DB mode."""
        return hasattr(self, "_store") and self._store is not None

    async def get_runbook_content_async(
        self, filename: str, expand_wikilinks: bool = True
    ) -> str:
        """Get runbook content from DB via ResourceStore.

        Args:
            filename: Runbook filename.
            expand_wikilinks: Whether to expand WikiLinks inline.

        Returns:
            Runbook content (with WikiLinks expanded if requested).
        """
        if not self._is_db_mode():
            # Fall back to filesystem
            return self.get_runbook_content(filename, expand_wikilinks)

        path = f"repository/{filename}"
        assert self._store is not None, "ResourceStore required for DB mode"
        if expand_wikilinks:
            content, _ = await self._store.read_expanded_async(self._skill, path)
            return content or ""
        content = await self._store.read_async(self._skill, path)
        return content or ""

    def load_index(self) -> list[dict[str, Any]]:
        """Load runbook index from repository.

        Returns:
            List of runbook metadata dicts.
        """
        index_file = self._index_dir / "all_runbooks.json"
        if not index_file.exists():
            return []

        self._matcher.load_index()
        return self._matcher.runbooks_metadata

    def find_matches(
        self, alert: dict[str, Any], top_n: int = 5
    ) -> list[dict[str, Any]]:
        """Find matching runbooks for alert.

        Delegates to the actual RunbookMatcher from the skill.

        Args:
            alert: alert dict.
            top_n: Number of top matches to return.

        Returns:
            List of match dicts with runbook, score, explanation.
        """
        return self._matcher.find_matches(alert, top_n=top_n)

    def _expand_wikilinks(self, content: str) -> str:
        """Expand WikiLinks in content inline.

        WikiLink syntax: ![[path/to/file.md]]

        WikiLinks are relative to the skill root (e.g., common/universal/alert-understanding.md),
        not the repository subdirectory.
        """

        def replace_wikilink(match: re.Match) -> str:
            link_path = match.group(1)
            # WikiLinks are relative to skill root, not repository/
            full_path = self.repository_path / link_path
            if full_path.exists():
                # Recursively expand nested WikiLinks
                nested_content = full_path.read_text()
                return self._expand_wikilinks(nested_content)
            return match.group(0)  # Keep original if not found

        return WIKILINK_PATTERN.sub(replace_wikilink, content)

    def get_runbook_content(self, filename: str, expand_wikilinks: bool = True) -> str:
        """Get runbook content by filename.

        Args:
            filename: Runbook filename.
            expand_wikilinks: Whether to expand WikiLinks inline.

        Returns:
            Runbook content (with WikiLinks expanded if requested).
        """
        file_path = self._runbooks_dir / filename
        if not file_path.exists():
            return ""

        content = file_path.read_text()

        if expand_wikilinks:
            content = self._expand_wikilinks(content)

        return content
