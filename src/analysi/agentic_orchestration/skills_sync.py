"""Tenant Skills Syncer — Sync DB-backed skills to filesystem for SDK agents.

Enables the Claude Agent SDK path to use tenant-isolated, DB-backed skills
by syncing them to a temporary filesystem before agent execution.

Key features:
- Sync skills from DatabaseResourceStore to workspace filesystem
- Track baseline manifest for post-execution diffing
- Detect new/modified files created by the agent
- Route approved files to Hydra extraction pipeline
"""

import hashlib
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class SkillNotFoundError(Exception):
    """Raised when a skill cannot be found in the database."""

    pass


class TenantSkillsSyncer:
    """Sync DB-backed skills to filesystem for SDK agent execution.

    Skills are loaded from the database only. No filesystem fallback.
    Each workflow gets its own syncer instance with its own baseline.
    This ensures parallel workflows don't share state.

    Example:
        syncer = TenantSkillsSyncer(
            tenant_id="acme",
            session_factory=AsyncSessionLocal,
        )

        # Sync skills to workspace
        await syncer.sync_skills(workspace / ".claude/skills", ["runbooks-manager"])

        # Agent runs, creates files...

        # Detect new files created by agent
        new_files = syncer.detect_new_files(workspace / ".claude/skills")
    """

    def __init__(
        self,
        tenant_id: str,
        session_factory: Callable[[], AsyncSession],
    ):
        """Initialize with tenant context.

        Args:
            tenant_id: Tenant identifier for DB lookups.
            session_factory: Callable that returns an AsyncSession (as context manager).
        """
        self._tenant_id = tenant_id
        self._session_factory = session_factory

        # Per-instance baseline - not shared across workflows
        self._baseline_manifest: dict[str, str] = {}  # {relative_path: content_hash}
        self._baseline_timestamp: datetime | None = None

    async def sync_all_skills(self, target_dir: Path) -> dict[str, str]:
        """Sync ALL tenant skills to target directory.

        This is the preferred method - syncs all available skills so the agent
        can use any skill without needing to declare dependencies in frontmatter.

        Args:
            target_dir: Directory to sync skills into (e.g., {workspace}/.claude/skills)

        Returns:
            Dict mapping skill_name to source (always "db")
        """
        db_store = DatabaseResourceStore(self._session_factory, self._tenant_id)
        all_skills = await db_store.list_skills_async()

        if not all_skills:
            logger.warning("no_skills_found_for_tenant", _tenant_id=self._tenant_id)
            self._baseline_manifest = {}
            self._baseline_timestamp = datetime.now(UTC)
            return {}

        return await self.sync_skills(target_dir, list(all_skills.keys()))

    async def sync_skills(
        self,
        target_dir: Path,
        skill_names: list[str],
    ) -> dict[str, str]:
        """Sync specific skills to target directory and record baseline manifest.

        Prefer sync_all_skills() unless you need to sync specific skills only.

        Args:
            target_dir: Directory to sync skills into (e.g., {workspace}/.claude/skills)
            skill_names: List of skill names to sync

        Returns:
            Dict mapping skill_name to source (always "db")

        Raises:
            SkillNotFoundError: If skill not found in database
        """
        results = {}
        target_dir.mkdir(parents=True, exist_ok=True)

        for skill in skill_names:
            source = await self._sync_skill(skill, target_dir)
            results[skill] = source

        # Record baseline AFTER sync - this is what the agent starts with
        self._baseline_manifest = self._build_manifest(target_dir)
        self._baseline_timestamp = datetime.now(UTC)

        logger.info(
            "synced_skills_for_tenant",
            skills_count=len(skill_names),
            _tenant_id=self._tenant_id,
            results=results,
        )
        return results

    async def _sync_skill(self, skill_name: str, target_dir: Path) -> str:
        """Sync a single skill from database to target directory.

        Returns "db" (always syncs from database).

        Raises:
            SkillNotFoundError: If skill not found in database
        """
        db_store = DatabaseResourceStore(self._session_factory, self._tenant_id)
        tree = await db_store.tree_async(skill_name)

        if not tree:
            raise SkillNotFoundError(
                f"Skill '{skill_name}' not found in database for tenant '{self._tenant_id}'"
            )

        # Sync all files from DB
        skill_dir = target_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        # Resolve to absolute for path containment check
        skill_dir_resolved = skill_dir.resolve()

        for path in tree:
            content = await db_store.read_async(skill_name, path)
            if content is not None:
                file_path = (skill_dir / path).resolve()
                # Prevent path traversal (../) and absolute paths escaping skill_dir
                if not file_path.is_relative_to(skill_dir_resolved):
                    raise ValueError(
                        f"Blocked path traversal: '{path}' resolves outside skill directory"
                    )
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)

        logger.debug(
            "synced_skill_from_db_files", skill_name=skill_name, tree_count=len(tree)
        )
        return "db"

    def _build_manifest(self, directory: Path) -> dict[str, str]:
        """Build manifest of all files with content hashes.

        Symlinks are rejected — they could point outside the workspace
        and exfiltrate host files into tenant knowledge docs.

        Returns dict mapping relative path to truncated SHA256 hash.
        """
        manifest: dict[str, str] = {}

        if not directory.exists():
            return manifest

        for filepath in directory.rglob("*"):
            if filepath.is_symlink():
                logger.warning(
                    "skipping_symlink_in_manifest",
                    filepath=str(filepath),
                    resolved=str(filepath.resolve()),
                )
                continue
            if filepath.is_file():
                rel_path = str(filepath.relative_to(directory))
                content_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]
                manifest[rel_path] = content_hash

        return manifest

    def detect_new_files(self, workspace_dir: Path) -> list[Path]:
        """Find files created or modified by agent (not in baseline).

        Compares current workspace against baseline captured at sync time.
        Safe for parallel execution - each syncer has its own baseline.

        Returns files that are:
        - NEW: not in baseline at all
        - MODIFIED: in baseline but content changed

        Raises:
            RuntimeError: If called before sync_skills()
        """
        if not self._baseline_manifest:
            raise RuntimeError("Must call sync_skills() before detect_new_files()")

        current_manifest = self._build_manifest(workspace_dir)
        new_files = []

        for rel_path, content_hash in current_manifest.items():
            if rel_path not in self._baseline_manifest:
                # New file - created by agent
                new_files.append(workspace_dir / rel_path)
            elif self._baseline_manifest[rel_path] != content_hash:
                # Modified file - agent changed synced content
                new_files.append(workspace_dir / rel_path)

        if new_files:
            logger.info(
                "detected_newmodified_files_by_agent", new_files_count=len(new_files)
            )

        return new_files

    @property
    def baseline_timestamp(self) -> datetime | None:
        """When the baseline was captured."""
        return self._baseline_timestamp


# =============================================================================
# Hydra Integration
# =============================================================================


@asynccontextmanager
async def hydra_tenant_lock(session: AsyncSession, tenant_id: str):
    """Acquire exclusive lock for Hydra operations on a tenant's skills.

    Uses PostgreSQL advisory lock - lightweight, no table locking.
    Lock is automatically released when transaction commits/rolls back.

    Usage:
        async with AsyncSessionLocal() as session:
            async with hydra_tenant_lock(session, tenant_id):
                # Hydra operations are serialized per tenant
                await extraction_service.start_extraction(...)

    Args:
        session: Active database session
        tenant_id: Tenant identifier for lock scoping
    """
    # Generate stable lock ID from tenant_id (advisory locks use bigint)
    # Use only first 15 hex chars to fit in bigint range
    lock_id = int(hashlib.sha256(f"hydra:{tenant_id}".encode()).hexdigest()[:15], 16)

    # Acquire exclusive advisory lock (blocks if another session holds it).
    # ``pg_advisory_xact_lock`` is a Postgres-only function with no ORM
    # equivalent, so raw SQL via ``text()`` is required. The value flowing
    # into the statement is bound as ``:lock_id`` (never f-string
    # interpolated), so there is no injection surface to defend against.
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(:lock_id)"
        ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        {"lock_id": lock_id},
    )

    try:
        yield
    finally:
        # Lock auto-releases on transaction end
        pass


async def submit_new_files_to_hydra(
    session: AsyncSession,
    tenant_id: str,
    skill_name: str,
    approved_files: list[Path],
    source_metadata: dict,
) -> list[dict]:
    """Submit approved new files for content review via extraction pipeline.

    Creates content review records instead of running the extraction pipeline
    synchronously. Reviews are processed asynchronously by the ARQ worker.
    No auto-apply.

    Args:
        session: Active database session
        tenant_id: Tenant identifier
        skill_name: Name of the skill to add documents to
        approved_files: List of file paths approved by ContentPolicy
        source_metadata: Metadata about the source (run_id, alert_title, etc.)

    Returns:
        List of result dicts with:
        - file: filename
        - status: "pending" | "approved" (if bypassed) | "rejected" | "failed"
        - review_id: UUID of the content review record
        - reason: error message if rejected/failed
    """
    from analysi.repositories.knowledge_module import KnowledgeModuleRepository
    from analysi.services.content_review import (
        ContentReviewGateError,
        ContentReviewService,
    )

    results = []

    km_repo = KnowledgeModuleRepository(session)
    review_service = ContentReviewService(session)

    # Get skill
    skill = await km_repo.get_skill_by_name(tenant_id, skill_name)
    if not skill:
        return [{"error": f"Skill '{skill_name}' not found"}]

    skill_id = skill.component_id

    for filepath in approved_files:
        try:
            # Reject symlinks — they could point outside the workspace
            # and exfiltrate host files into tenant knowledge docs.
            if filepath.is_symlink():
                logger.warning(
                    "rejected_symlink_in_hydra_submission",
                    filepath=str(filepath),
                    resolved=str(filepath.resolve()),
                )
                results.append(
                    {
                        "file": filepath.name,
                        "status": "rejected",
                        "reason": "Symlinks are not allowed",
                    }
                )
                continue

            content = filepath.read_text()

            # Submit for content review (async pipeline)
            review = await review_service.submit_for_review(
                content=content,
                filename=filepath.name,
                skill_id=skill_id,
                tenant_id=tenant_id,
                pipeline_name="extraction",
                trigger_source=source_metadata.get("source", "kea_agent"),
            )
            results.append(
                {
                    "file": filepath.name,
                    "status": str(review.status),
                    "review_id": str(review.id),
                }
            )

        except ContentReviewGateError as exc:
            logger.warning(
                "content_review_sync_failed",
                file=filepath.name,
                errors=str(exc),
            )
            results.append(
                {
                    "file": filepath.name,
                    "status": "rejected",
                    "reason": str(exc),
                }
            )
        except Exception as e:
            logger.exception("failed_to_submit_to_hydra", name=filepath.name)
            results.append(
                {
                    "file": filepath.name,
                    "status": "failed",
                    "reason": str(e),
                }
            )

    await session.commit()

    return results


async def submit_content_to_hydra(
    session: AsyncSession,
    tenant_id: str,
    skill_name: str,
    content: str,
    source_metadata: dict,
) -> dict:
    """Submit composed content for content review via extraction pipeline.

    Creates a content review record instead of running the extraction pipeline
    synchronously. The review is processed asynchronously by the ARQ worker.
    No auto-apply.

    Args:
        session: Active database session
        tenant_id: Tenant identifier
        skill_name: Name of the skill to add document to
        content: Markdown content to submit
        source_metadata: Metadata about the source

    Returns:
        Result dict with:
        - status: "pending" | "approved" (if bypassed) | "failed"
        - review_id: UUID of the content review record
    """
    from analysi.repositories.knowledge_module import KnowledgeModuleRepository
    from analysi.services.content_review import (
        ContentReviewGateError,
        ContentReviewService,
    )

    km_repo = KnowledgeModuleRepository(session)
    review_service = ContentReviewService(session)

    # Get skill
    skill = await km_repo.get_skill_by_name(tenant_id, skill_name)
    if not skill:
        return {"status": "failed", "reason": f"Skill '{skill_name}' not found"}

    skill_id = skill.component_id

    try:
        review = await review_service.submit_for_review(
            content=content,
            filename=source_metadata.get("original_filename", "composed-runbook.md"),
            skill_id=skill_id,
            tenant_id=tenant_id,
            pipeline_name="extraction",
            trigger_source=source_metadata.get("source", "langgraph_composition"),
        )
        await session.commit()
        return {
            "status": str(review.status),
            "review_id": str(review.id),
        }
    except ContentReviewGateError as exc:
        return {"status": "rejected", "reason": str(exc)}
    except Exception as e:
        logger.exception("Failed to submit content to Hydra")
        await session.rollback()
        return {"status": "failed", "reason": str(e)}
