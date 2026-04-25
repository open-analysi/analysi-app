"""DatabaseResourceStore - Skills backed by database (knowledge_module table).

This store adapts the KnowledgeModuleRepository to the ResourceStore interface,
allowing SkillsIR to retrieve skill content from the database.
"""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.langgraph.skills.store import (
    MAX_WIKILINK_DEPTH,
    ResourceStore,
    extract_wikilinks,
)
from analysi.config.logging import get_logger
from analysi.repositories.knowledge_module import KnowledgeModuleRepository

logger = get_logger(__name__)


class DatabaseResourceStore(ResourceStore):
    """ResourceStore implementation backed by database.

    Skills are stored in the knowledge_module table with documents linked
    via KDG 'contains' edges. The namespace_path in edge metadata maps to
    the skill's virtual file tree.

    This store requires an async session factory and tenant_id for all operations.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        tenant_id: str,
    ):
        """Initialize with database session factory and tenant.

        Args:
            session_factory: Callable that returns an AsyncSession.
                            Should create a new session each call for thread safety.
            tenant_id: Tenant identifier for skill lookups.
        """
        self._session_factory = session_factory
        self._tenant_id = tenant_id

    def _get_repo(self, session: AsyncSession) -> KnowledgeModuleRepository:
        """Create a repository instance with the given session."""
        return KnowledgeModuleRepository(session)

    async def list_skills_async(self) -> dict[str, str]:
        """List all available skills with their descriptions.

        Returns:
            Dict mapping skill name to description.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)
            modules, _ = await repo.list_skills(
                tenant_id=self._tenant_id,
                status="enabled",
                limit=1000,  # Reasonable limit for skills
            )

            skills = {}
            for module in modules:
                name = module.component.name
                description = module.component.description or ""
                skills[name] = description

            logger.debug(
                "listed_skills_from_database_for_tenant",
                skills_count=len(skills),
                _tenant_id=self._tenant_id,
            )
            return skills

    async def tree_async(self, skill: str) -> list[str]:
        """Get all file paths within a skill.

        Args:
            skill: The skill's human-readable name.

        Returns:
            List of file paths (namespace_path values).
            Empty list if skill doesn't exist.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)

            # First get the skill by name
            module = await repo.get_skill_by_name(self._tenant_id, skill)
            if not module:
                logger.debug("skill_not_found_in_database", skill=skill)
                return []

            # Get the file tree
            tree_entries = await repo.get_skill_tree(
                self._tenant_id, module.component_id
            )

            paths = [entry["path"] for entry in tree_entries]
            logger.debug("skill_has_files", skill=skill, paths_count=len(paths))
            return sorted(paths)

    async def read_async(self, skill: str, path: str) -> str | None:
        """Read content of a file within a skill.

        Args:
            skill: The skill's human-readable name.
            path: Path to the file (namespace_path).

        Returns:
            File content as string, or None if file doesn't exist.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)

            # First get the skill by name
            module = await repo.get_skill_by_name(self._tenant_id, skill)
            if not module:
                logger.debug("skill_not_found_in_database_for_read", skill=skill)
                return None

            # Read the file
            file_data = await repo.read_skill_file(
                self._tenant_id, module.component_id, path
            )
            if not file_data:
                logger.debug("file_not_found_in_skill", path=path, skill=skill)
                return None

            # Return markdown_content if available, otherwise content
            content = file_data.get("markdown_content") or file_data.get("content")
            logger.debug(
                "skill_content_read",
                chars=len(content) if content else 0,
                skill=skill,
                path=path,
            )
            return content

    async def read_expanded_async(
        self, skill: str, path: str
    ) -> tuple[str | None, int]:
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
        stats: dict[str, int] = {
            "expanded": 0,
            "cycles": 0,
            "missing": 0,
            "depth_limited": 0,
        }
        content = await self._expand_wikilinks_async(
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

    async def _expand_wikilinks_async(
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
        content = await self.read_async(skill, path)
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
            expanded = await self._expand_wikilinks_async(
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

    async def read_table_async(self, skill: str, path: str) -> dict | list | None:
        """Read structured table data (KUTable) within a skill.

        Args:
            skill: The skill's human-readable name.
            path: Path to the table (namespace_path).

        Returns:
            Table content (dict or list), or None if not found.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)

            module = await repo.get_skill_by_name(self._tenant_id, skill)
            if not module:
                logger.debug("skill_not_found_in_database_for_table_read", skill=skill)
                return None

            table_data = await repo.read_skill_table(
                self._tenant_id, module.component_id, path
            )
            if not table_data:
                logger.debug("table_not_found_in_skill", path=path, skill=skill)
                return None

            content = table_data.get("content")
            logger.debug("read_table_from", skill=skill, path=path)
            return content

    async def write_document_async(
        self, skill: str, path: str, content: str, metadata: dict | None = None
    ) -> bool:
        """Write a document to a skill's namespace in the database.

        Args:
            skill: The skill's human-readable name.
            path: Namespace path for the document.
            content: Document content (markdown).
            metadata: Optional metadata dict.

        Returns:
            True if written successfully, False otherwise.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)

            module = await repo.get_skill_by_name(self._tenant_id, skill)
            if not module:
                logger.warning("skill_not_found_for_writedocumentasync", skill=skill)
                return False

            await repo.write_skill_file(
                self._tenant_id, module.component_id, path, content, metadata
            )
            logger.info("wrote_document_to", skill=skill, path=path)
            return True

    async def write_table_async(
        self, skill: str, path: str, content: dict | list, schema: dict | None = None
    ) -> bool:
        """Write structured table data to a skill's namespace in the database.

        Args:
            skill: The skill's human-readable name.
            path: Namespace path for the table.
            content: Table content (dict or list).
            schema: Optional JSON schema.

        Returns:
            True if written successfully, False otherwise.
        """
        async with self._session_factory() as session:
            repo = self._get_repo(session)

            module = await repo.get_skill_by_name(self._tenant_id, skill)
            if not module:
                logger.warning("skill_not_found_for_writetableasync", skill=skill)
                return False

            await repo.write_skill_table(
                self._tenant_id, module.component_id, path, content, schema
            )
            logger.info("wrote_table_to", skill=skill, path=path)
            return True

    # Sync methods for backward compatibility with existing LangGraph nodes
    # These delegate to async methods using a simple pattern

    def list_skills(self) -> dict[str, str]:
        """Sync wrapper - raises NotImplementedError.

        Use list_skills_async() for database-backed stores.
        """
        raise NotImplementedError(
            "DatabaseResourceStore requires async operations. "
            "Use list_skills_async() instead."
        )

    def tree(self, skill: str) -> list[str]:
        """Sync wrapper - raises NotImplementedError."""
        raise NotImplementedError(
            "DatabaseResourceStore requires async operations. Use tree_async() instead."
        )

    def read(self, skill: str, path: str) -> str | None:
        """Sync wrapper - raises NotImplementedError."""
        raise NotImplementedError(
            "DatabaseResourceStore requires async operations. Use read_async() instead."
        )
