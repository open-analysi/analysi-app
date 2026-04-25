"""ResourceStore - Abstraction for accessing skill resources."""

import re
from abc import ABC, abstractmethod

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# WikiLink pattern: ![[path/to/file.md]] - the ! prefix indicates embed
WIKILINK_PATTERN = re.compile(r"!\[\[([^\]]+\.md)\]\]")

# Maximum depth for WikiLink expansion (prevents runaway recursion)
MAX_WIKILINK_DEPTH = 10


def extract_wikilinks(content: str) -> list[str]:
    """Extract WikiLink paths from content.

    WikiLinks use the syntax ![[path/to/file.md]] to embed other files.

    Args:
        content: Markdown content that may contain WikiLinks.

    Returns:
        List of paths referenced by WikiLinks (without the ![[]] wrapper).

    Example:
        >>> extract_wikilinks("See ![[common/alert.md]] for details")
        ['common/alert.md']
    """
    return WIKILINK_PATTERN.findall(content)


class ResourceStore(ABC):
    """Abstract base class for accessing skill resources.

    This abstraction allows skills to be stored in different backends
    (filesystem, database, etc.) while maintaining a consistent interface.

    Implementations can provide either sync or async methods:
    - Sync methods (list_skills, tree, read) - required for ABC compliance
    - Async methods (list_skills_async, tree_async, read_async, read_expanded_async)
      - optional, defaults to calling sync methods

    LangGraph nodes should prefer async methods when available.
    """

    # =============================================================================
    # Sync methods (ABC contract - must be implemented or raise NotImplementedError)
    # =============================================================================

    @abstractmethod
    def list_skills(self) -> dict[str, str]:
        """List all available skills with their descriptions.

        Returns:
            Dict mapping skill name to description extracted from SKILL.md frontmatter.
        """
        ...

    @abstractmethod
    def tree(self, skill: str) -> list[str]:
        """Get all file paths within a skill.

        Args:
            skill: Name of the skill.

        Returns:
            List of file paths relative to the skill directory.
            Empty list if skill doesn't exist.
        """
        ...

    @abstractmethod
    def read(self, skill: str, path: str) -> str | None:
        """Read content of a file within a skill.

        Args:
            skill: Name of the skill.
            path: Path to the file relative to skill directory.

        Returns:
            File content as string, or None if file doesn't exist.
        """
        ...

    # =============================================================================
    # Async methods (optional - default to calling sync methods)
    # =============================================================================

    async def list_skills_async(self) -> dict[str, str]:
        """Async version of list_skills.

        Override this for stores that need async operations (e.g., database).
        Default implementation calls sync list_skills().
        """
        return self.list_skills()

    async def tree_async(self, skill: str) -> list[str]:
        """Async version of tree.

        Override this for stores that need async operations.
        Default implementation calls sync tree().
        """
        return self.tree(skill)

    async def read_async(self, skill: str, path: str) -> str | None:
        """Async version of read.

        Override this for stores that need async operations.
        Default implementation calls sync read().
        """
        return self.read(skill, path)

    async def read_expanded_async(
        self, skill: str, path: str
    ) -> tuple[str | None, int]:
        """Async version of read_expanded with WikiLink expansion.

        Override this for stores that need async operations.
        Default implementation calls sync read_expanded().
        """
        return self.read_expanded(skill, path)

    async def read_table_async(self, skill: str, path: str) -> dict | list | None:
        """Read structured table data (KUTable) within a skill.

        Tables store structured JSON data (e.g., runbook index metadata).
        This is distinct from read_async which reads KUDocument content.

        Args:
            skill: Name of the skill.
            path: Path to the table (namespace_path in KDG edge).

        Returns:
            Table content (dict or list), or None if not found.
        """
        return None

    async def write_document_async(
        self, skill: str, path: str, content: str, metadata: dict | None = None
    ) -> bool:
        """Write a document to a skill's namespace.

        Creates a new KUDocument and links it to the skill via KDG edge.

        Args:
            skill: Name of the skill.
            path: Namespace path for the document.
            content: Document content (markdown).
            metadata: Optional metadata dict.

        Returns:
            True if written successfully, False otherwise.
        """
        return False

    async def write_table_async(
        self, skill: str, path: str, content: dict | list, schema: dict | None = None
    ) -> bool:
        """Write structured table data to a skill's namespace.

        Creates or updates a KUTable linked to the skill.

        Args:
            skill: Name of the skill.
            path: Namespace path for the table.
            content: Table content (dict or list).
            schema: Optional JSON schema for the table.

        Returns:
            True if written successfully, False otherwise.
        """
        return False

    def read_expanded(self, skill: str, path: str) -> tuple[str | None, int]:
        """Read file content with WikiLinks expanded inline.

        WikiLinks (![[path/to/file.md]]) are replaced with the actual
        content of the referenced files. Expansion is recursive but
        cycle-safe and depth-limited.

        Args:
            skill: Name of the skill.
            path: Path to the file relative to skill directory.

        Returns:
            Tuple of (expanded_content, wikilinks_expanded_count).
            Content is None if file doesn't exist.
        """
        stats = {"expanded": 0, "cycles": 0, "missing": 0, "depth_limited": 0}
        content = self._expand_wikilinks(
            skill, path, visited=set(), depth=0, stats=stats
        )

        total_expanded = stats["expanded"]
        if total_expanded > 0 or stats["cycles"] > 0 or stats["depth_limited"] > 0:
            logger.info(
                "wikilink_expansion",
                skill=skill,
                path=path,
                expanded=total_expanded,
                cycles=stats["cycles"],
                depth_limited=stats["depth_limited"],
                missing=stats["missing"],
            )

        return content, total_expanded

    def _expand_wikilinks(
        self,
        skill: str,
        path: str,
        visited: set[tuple[str, str]],
        depth: int = 0,
        stats: dict[str, int] | None = None,
    ) -> str | None:
        """Recursively expand WikiLinks in a file.

        Args:
            skill: Name of the skill.
            path: Path to the file relative to skill directory.
            visited: Set of (skill, path) tuples already visited (cycle detection).
            depth: Current recursion depth.
            stats: Optional dict to track expansion statistics.

        Returns:
            Expanded content, or None if file doesn't exist.
        """
        if stats is None:
            stats = {"expanded": 0, "cycles": 0, "missing": 0, "depth_limited": 0}

        # Depth limit check
        if depth >= MAX_WIKILINK_DEPTH:
            logger.warning(
                "wikilink_depth_limit_reached",
                max_depth=MAX_WIKILINK_DEPTH,
                skill=skill,
                path=path,
            )
            stats["depth_limited"] += 1
            return f"<!-- WikiLink depth limit reached: {path} -->"

        # Cycle detection
        key = (skill, path)
        if key in visited:
            logger.warning("wikilink_cycle_detected_skipping", skill=skill, path=path)
            stats["cycles"] += 1
            return f"<!-- WikiLink cycle: {path} -->"
        visited.add(key)

        # Read the file
        content = self.read(skill, path)
        if content is None:
            return None

        # Find and expand WikiLinks
        wikilinks = extract_wikilinks(content)
        if not wikilinks:
            return content

        logger.debug(
            "found_wikilinks_in",
            wikilinks_count=len(wikilinks),
            skill=skill,
            path=path,
            wikilinks=wikilinks,
        )

        # Replace each WikiLink with expanded content
        for link_path in wikilinks:
            # WikiLinks are relative to the skill root
            expanded = self._expand_wikilinks(
                skill, link_path, visited, depth + 1, stats
            )
            if expanded is not None:
                # Replace the WikiLink with expanded content
                pattern = f"![[{link_path}]]"
                content = content.replace(pattern, expanded)
                stats["expanded"] += 1
                logger.debug("expanded_wikilink", skill=skill, link_path=link_path)
            else:
                # File not found - leave a comment
                logger.warning(
                    "wikilink_target_not_found", skill=skill, link_path=link_path
                )
                stats["missing"] += 1
                pattern = f"![[{link_path}]]"
                content = content.replace(
                    pattern, f"<!-- WikiLink not found: {link_path} -->"
                )

        return content
