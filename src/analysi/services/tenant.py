"""Tenant lifecycle service (Project Delos).

Handles tenant creation, validation, listing, and cascade-delete.
"""

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.auth import Membership
from analysi.models.tenant import Tenant
from analysi.repositories.tenant import TenantRepository
from analysi.repositories.user_repository import UserRepository

logger = get_logger(__name__)

# Tenant ID format: alphanumeric + hyphens, 3-255 chars, no leading/trailing hyphens
_TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{1,253}[a-z0-9]$")

# Tables with tenant_id that must be wiped on cascade-delete.
# Order matters: children/dependents first, parents last.
# Partitioned tables use TRUNCATE-style DELETE (cannot FK cascade).
_CASCADE_DELETE_TABLES = [
    # Execution/run tables (partitioned — children of tasks/workflows)
    # Note: workflow_node_instances and workflow_edge_instances don't have tenant_id;
    # they cascade via FK from workflow_nodes/workflow_edges → workflows.
    "artifacts",
    "task_runs",
    "workflow_runs",
    # Analysis pipeline
    "alert_analyses",
    "alerts",
    "analysis_groups",
    "workflow_generations",
    "task_generations",
    # Control events (partitioned)
    # Note: control_event_dispatches cascades via FK from control_event_rules.
    "control_events",
    "control_event_rules",
    # HITL
    "hitl_questions",
    # Chat
    "chat_messages",
    "chat_conversations",
    # Integrations
    "integration_runs",
    "integration_schedules",
    "integration_credentials",
    "credentials",
    "integrations",
    # Knowledge graph
    "component_graph_edges",
    "knowledge_extractions",
    "content_reviews",
    # Auth
    "memberships",
    "invitations",
    "api_keys",
    # Audit
    "activity_audit_trails",
    # Alert routing
    "alert_routing_rules",
    # Alert sequence counters
    "alert_id_counters",
    # Workflow node templates
    "node_templates",
    # Core content (tasks/KUs inherit from components)
    "workflows",
    "components",
]


class TenantService:
    """Business logic for tenant lifecycle management."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TenantRepository(session)

    @staticmethod
    def validate_tenant_id(tenant_id: str) -> list[str]:
        """Validate a tenant ID format.

        Returns:
            List of validation error messages (empty = valid).
        """
        errors: list[str] = []
        if len(tenant_id) < 3:
            errors.append("Tenant ID must be at least 3 characters")
        if len(tenant_id) > 255:
            errors.append("Tenant ID must be at most 255 characters")
        if not errors and not _TENANT_ID_PATTERN.match(tenant_id):
            errors.append(
                "Tenant ID must contain only lowercase alphanumeric characters "
                "and hyphens, and cannot start or end with a hyphen"
            )
        return errors

    async def create_tenant(
        self,
        *,
        tenant_id: str,
        name: str,
        owner_email: str | None = None,
        dry_run: bool = False,
    ) -> Tenant | None:
        """Create a new tenant with an optional first owner.

        Args:
            tenant_id: Human-readable identifier.
            name: Display name.
            owner_email: If provided, create/lookup user and add as owner.
            dry_run: If True, validate only — do not persist.

        Returns:
            Created Tenant (or None if dry_run).

        Raises:
            ValueError: If tenant_id is invalid or already exists.
        """
        # Validate format
        errors = self.validate_tenant_id(tenant_id)
        if errors:
            raise ValueError(f"Invalid tenant ID: {'; '.join(errors)}")

        # Check uniqueness
        if await self.repository.exists(tenant_id):
            raise ValueError(f"Tenant '{tenant_id}' already exists")

        if dry_run:
            return None

        tenant = await self.repository.create(
            tenant_id=tenant_id,
            name=name,
        )

        if owner_email:
            await self._assign_first_owner(tenant_id, owner_email)

        logger.info(
            "tenant_created",
            tenant_id=tenant_id,
            name=name,
            owner_email=owner_email,
        )
        return tenant

    async def _assign_first_owner(self, tenant_id: str, owner_email: str) -> UUID:
        """Look up or JIT-create a user by email and add as tenant owner.

        Returns the user's database ID.
        """
        user_repo = UserRepository(self.session)
        user = await user_repo.get_by_email(owner_email)

        if user is None:
            # JIT create — keycloak_id is a placeholder until first login.
            # Use a savepoint so a concurrent duplicate doesn't abort the
            # outer transaction (UNIQUE on email).
            try:
                async with self.session.begin_nested():
                    user = await user_repo.create(
                        keycloak_id=f"pending:{owner_email}",
                        email=owner_email,
                    )
                logger.info(
                    "tenant_owner_jit_created",
                    tenant_id=tenant_id,
                    email=owner_email,
                    user_id=str(user.id),
                )
            except Exception:
                # Concurrent insert won the race — re-fetch
                user = await user_repo.get_by_email(owner_email)
                if user is None:
                    raise ValueError(f"Failed to create or find user: {owner_email}")

        # Create owner membership
        membership = Membership(
            user_id=user.id,
            tenant_id=tenant_id,
            role="owner",
        )
        self.session.add(membership)
        await self.session.flush()

        logger.info(
            "tenant_owner_assigned",
            tenant_id=tenant_id,
            email=owner_email,
            user_id=str(user.id),
        )
        return user.id

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID."""
        return await self.repository.get_by_id(tenant_id)

    async def list_tenants(
        self,
        *,
        status: str | None = None,
        has_schedules: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Tenant], int]:
        """List tenants with optional filters."""
        return await self.repository.list_all(
            status=status, has_schedules=has_schedules, skip=skip, limit=limit
        )

    async def cascade_delete_tenant(self, tenant_id: str) -> dict[str, int]:
        """Delete a tenant and ALL its data across every table.

        This is a destructive operation. It removes everything unconditionally,
        including in-flight task runs, active workflows, paused HITL analyses.

        Args:
            tenant_id: The tenant to delete.

        Returns:
            Dict mapping table name to number of rows deleted.

        Raises:
            ValueError: If tenant does not exist.
        """
        if not await self.repository.exists(tenant_id):
            raise ValueError(f"Tenant '{tenant_id}' does not exist")

        deleted_counts: dict[str, int] = {}

        for table in _CASCADE_DELETE_TABLES:
            try:
                # Use a SAVEPOINT so a failure in one table doesn't abort
                # the entire transaction (e.g., table might not exist in
                # test environments or have FK ordering issues).
                async with self.session.begin_nested():
                    # ``table`` iterates over _CASCADE_DELETE_TABLES, a hardcoded
                    # constant defined at module load time — never user input.
                    # ``tenant_id`` is bound as a parameter (``:tid``). There is
                    # no SQL-injection surface here.
                    # Suppression comment must sit on the f-string line so
                    # Bandit's per-line ``# nosec`` parser picks it up; the
                    # same line carries ``# nosemgrep`` for the corresponding
                    # Semgrep rule.
                    result = await self.session.execute(
                        text(f"DELETE FROM {table} WHERE tenant_id = :tid"),  # nosec B608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        {"tid": tenant_id},
                    )
                    count = result.rowcount
                    if count > 0:
                        deleted_counts[table] = count
                        logger.info(
                            "tenant_cascade_delete_table",
                            tenant_id=tenant_id,
                            table=table,
                            deleted=count,
                        )
            except Exception:
                # SAVEPOINT rolled back — transaction remains usable.
                # Log and continue with remaining tables.
                logger.warning(
                    "tenant_cascade_delete_table_error",
                    tenant_id=tenant_id,
                    table=table,
                    exc_info=True,
                )

        # Finally, delete the tenant record itself
        await self.repository.delete(tenant_id)
        deleted_counts["tenants"] = 1

        logger.info(
            "tenant_cascade_delete_complete",
            tenant_id=tenant_id,
            tables_affected=len(deleted_counts),
            total_rows=sum(deleted_counts.values()),
        )

        return deleted_counts
