"""
Service layer for Integration operations.

Use Schedule/JobRun APIs for scheduled execution management.
"""

from typing import Any
from uuid import UUID

from analysi.config.logging import get_logger
from analysi.constants import IntegrationHealthStatus
from analysi.integrations.framework.loader import IntegrationLoader
from analysi.integrations.framework.models import Archetype
from analysi.integrations.framework.registry import (
    get_registry,
)
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.schemas.integration import (
    IntegrationCreate,
    IntegrationHealth,
    IntegrationResponse,
    IntegrationUpdate,
)

logger = get_logger(__name__)


class IntegrationService:
    """Service for integration operations."""

    def __init__(
        self,
        integration_repo: IntegrationRepository,
        credential_repo=None,  # Optional credential repository for action execution
    ):
        self.integration_repo = integration_repo
        self.credential_repo = credential_repo

    async def list_integrations(
        self,
        tenant_id: str,
        enabled: bool | None = None,
        integration_type: str | None = None,
    ) -> list[IntegrationResponse]:
        """List all integrations for a tenant, optionally filtered by enabled status and integration type."""
        integrations = await self.integration_repo.list_integrations(
            tenant_id, enabled=enabled, integration_type=integration_type
        )
        result = []

        for integration in integrations:
            health = await self.calculate_health(
                tenant_id, integration.integration_id, integration=integration
            )

            result.append(
                IntegrationResponse(
                    integration_id=integration.integration_id,
                    integration_type=integration.integration_type,
                    tenant_id=tenant_id,
                    name=integration.name,
                    description=integration.description,
                    enabled=integration.enabled,
                    settings=integration.settings,
                    created_at=integration.created_at,
                    updated_at=integration.updated_at,
                    health=health,
                )
            )

        return result

    async def get_integration(
        self, tenant_id: str, integration_id: str
    ) -> IntegrationResponse | None:
        """Get integration details including managed resources."""
        integration = await self.integration_repo.get_integration(
            tenant_id, integration_id
        )

        if not integration:
            return None

        health = await self.calculate_health(
            tenant_id, integration_id, integration=integration
        )

        # Populate managed_resources block
        managed_resources_block = await self._get_managed_resources_block(
            tenant_id, integration_id
        )

        return IntegrationResponse(
            integration_id=integration.integration_id,
            integration_type=integration.integration_type,
            tenant_id=tenant_id,
            name=integration.name,
            description=integration.description,
            enabled=integration.enabled,
            settings=integration.settings,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
            health=health,
            managed_resources=managed_resources_block
            if managed_resources_block
            else None,
        )

    async def create_integration(
        self, tenant_id: str, data: IntegrationCreate
    ) -> IntegrationResponse:
        """Create a new integration."""
        # Validate integration type exists in Naxos framework
        framework_registry = get_registry()
        manifest = framework_registry.get_integration(data.integration_type)
        if not manifest:
            # Get list of available integration types for helpful error message
            available_types = framework_registry.list_integrations()
            available_type_names = [integration.id for integration in available_types]
            raise ValueError(
                f"Integration type '{data.integration_type}' is not supported. "
                f"Available integration types: {', '.join(available_type_names)}"
            )

        # Auto-generate integration_id if not provided
        if not data.integration_id:
            # Generate a unique ID: {integration_type}-{timestamp}
            import time

            timestamp = int(time.time() * 1000)  # milliseconds
            data.integration_id = f"{data.integration_type}-{timestamp}"

        # Check if integration already exists
        existing = await self.integration_repo.get_integration(
            tenant_id, data.integration_id
        )
        if existing:
            raise ValueError(f"Integration {data.integration_id} already exists")

        # Enforce AI primary invariant before writing to DB
        ai_types = {m.id for m in framework_registry.list_by_archetype(Archetype.AI)}
        if data.integration_type in ai_types:
            existing_ai = await self._get_all_ai_integrations(tenant_id)
            has_primary = any((i.settings or {}).get("is_primary") for i in existing_ai)
            if not has_primary:
                # First AI integration for this tenant — make it primary automatically
                data.settings = {**(data.settings or {}), "is_primary": True}
                logger.info(
                    "auto_promoting_to_primary",
                    integration_id=data.integration_id,
                    reason="no existing AI primary for tenant",
                )

        # Create the integration
        integration = await self.integration_repo.create_integration(
            tenant_id=tenant_id,
            integration_id=data.integration_id,
            integration_type=data.integration_type,
            name=data.name,
            description=data.description,
            settings=data.settings,
            enabled=data.enabled,
        )

        # If the new integration claims primary, clear any other that was primary
        if (data.settings or {}).get("is_primary"):
            await self._clear_primary_for_ai_llm_peers(tenant_id, data.integration_id)

        # Auto-create Tasks + Schedules via factory
        await self._create_managed_resources(
            tenant_id=tenant_id,
            integration_id=integration.integration_id,
            integration_type=data.integration_type,
            manifest=manifest,
        )

        # Project Symi: If the integration was created already enabled,
        # enable its schedules now. _create_managed_resources always creates
        # schedules with enabled=False; the cascade sets enabled=True and
        # computes next_run_at so the executor can pick them up.
        if integration.enabled:
            from analysi.services.task_factory import cascade_enable_schedules

            session = self.integration_repo.session
            symi_count = await cascade_enable_schedules(
                session, tenant_id, integration.integration_id
            )
            if symi_count > 0:
                logger.info(
                    "enabled_schedules_on_create",
                    integration_id=integration.integration_id,
                    schedules_enabled=symi_count,
                )

        # Calculate initial health
        health = await self.calculate_health(
            tenant_id, integration.integration_id, integration=integration
        )

        return IntegrationResponse(
            integration_id=integration.integration_id,
            integration_type=integration.integration_type,
            tenant_id=tenant_id,
            name=integration.name,
            description=integration.description,
            enabled=integration.enabled,
            settings=integration.settings,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
            health=health,
        )

    async def update_integration(
        self, tenant_id: str, integration_id: str, data: IntegrationUpdate
    ) -> IntegrationResponse | None:
        """Update an existing integration."""
        # Check if integration exists
        existing = await self.integration_repo.get_integration(
            tenant_id, integration_id
        )
        if not existing:
            return None

        # Store original enabled state before update
        original_enabled = existing.enabled

        # Reject removing primary when no other AI integration can take over
        ai_types = {m.id for m in get_registry().list_by_archetype(Archetype.AI)}
        if (
            existing.integration_type in ai_types
            and (existing.settings or {}).get("is_primary")
            and data.settings is not None
            and data.settings.get("is_primary") is False
        ):
            other_ai = [
                i
                for i in await self._get_all_ai_integrations(tenant_id)
                if i.integration_id != integration_id
            ]
            if not other_ai:
                raise ValueError(
                    f"Cannot remove primary designation from '{integration_id}' — "
                    "it is the only AI integration. Add another AI integration first."
                )
            raise ValueError(
                f"Cannot remove primary designation from '{integration_id}'. "
                "Promote another AI integration to primary instead."
            )

        # Build update dict from provided fields
        updates: dict[str, Any] = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.description is not None:
            updates["description"] = data.description
        if data.enabled is not None:
            updates["enabled"] = data.enabled
        if data.settings is not None:
            # Validate settings before updating
            data.validate_settings_with_type(existing.integration_type)

            # Merge settings instead of replacing them entirely
            merged_settings = existing.settings.copy() if existing.settings else {}

            # Update base settings
            for key, value in data.settings.items():
                merged_settings[key] = value

            updates["settings"] = merged_settings

        # Update if there are changes
        if updates:
            integration = await self.integration_repo.update_integration(
                tenant_id, integration_id, updates
            )

            # Enforce single-primary constraint across AI LLM integrations
            if updates.get("settings", {}).get("is_primary"):
                ai_types = {
                    m.id for m in get_registry().list_by_archetype(Archetype.AI)
                }
                if existing.integration_type in ai_types:
                    await self._clear_primary_for_ai_llm_peers(
                        tenant_id, integration_id
                    )

            # If enabled status changed, cascade to Symi schedules
            if data.enabled is not None and data.enabled != original_enabled:
                logger.info(
                    "updating_schedules_for_enabled",
                    integration_id=integration_id,
                    enabled=data.enabled,
                )

                # Cascade to schedules table
                from analysi.services.task_factory import (
                    cascade_disable_schedules,
                    cascade_enable_schedules,
                )

                session = self.integration_repo.session
                if data.enabled:
                    symi_count = await cascade_enable_schedules(
                        session, tenant_id, integration_id
                    )
                    logger.info(
                        "enabled_integration_and_schedules",
                        integration_id=integration_id,
                        symi_schedules_enabled=symi_count,
                    )
                else:
                    symi_count = await cascade_disable_schedules(
                        session, tenant_id, integration_id
                    )
                    logger.info(
                        "disabled_integration_and_schedules",
                        integration_id=integration_id,
                        symi_schedules_disabled=symi_count,
                    )
        else:
            integration = existing

        # Calculate health
        health = await self.calculate_health(
            tenant_id, integration_id, integration=integration
        )

        return IntegrationResponse(
            integration_id=integration.integration_id,
            integration_type=integration.integration_type,
            tenant_id=tenant_id,
            name=integration.name,
            description=integration.description,
            enabled=integration.enabled,
            settings=integration.settings,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
            health=health,
        )

    async def _get_all_ai_integrations(self, tenant_id: str) -> list[Any]:
        """Return all configured AI archetype integrations for the tenant."""
        ai_types = {m.id for m in get_registry().list_by_archetype(Archetype.AI)}
        all_integrations: list[Any] = []
        for integration_type in ai_types:
            all_integrations.extend(
                await self.integration_repo.list_integrations(
                    tenant_id, integration_type=integration_type
                )
            )
        return all_integrations

    async def _clear_primary_for_ai_llm_peers(
        self, tenant_id: str, exclude_integration_id: str
    ) -> None:
        """Clear is_primary from all AI LLM integrations except the given one."""
        for peer in await self._get_all_ai_integrations(tenant_id):
            if peer.integration_id == exclude_integration_id:
                continue
            peer_settings = peer.settings or {}
            if peer_settings.get("is_primary"):
                cleared = dict(peer_settings)
                cleared["is_primary"] = False
                await self.integration_repo.update_integration(
                    tenant_id, peer.integration_id, {"settings": cleared}
                )
                logger.info(
                    "cleared_is_primary",
                    peer_integration_id=peer.integration_id,
                    new_primary=exclude_integration_id,
                )

    # Action IDs handled by dedicated factory functions (not generic).
    _BUILTIN_MANAGED_ACTIONS: frozenset[str] = frozenset(
        {
            "health_check",
            "pull_alerts",
            "alerts_to_ocsf",
        }
    )

    async def _create_managed_resources(
        self,
        tenant_id: str,
        integration_id: str,
        integration_type: str,
        manifest: Any,
    ) -> None:
        """Auto-create Tasks + Schedules for a newly created integration.

        - If the integration implements AlertSource, create an alert ingestion Task + Schedule.
        - Always create a health check Task + Schedule.
        - Create generic action Tasks for any additional default_schedules entries.
        - All schedules start disabled (admin enables after configuring credentials).
        """
        from analysi.services.task_factory import (
            create_alert_ingestion_task,
            create_default_schedule,
            create_health_check_task,
        )

        session = self.integration_repo.session

        try:
            # AlertSource archetype: create alert ingestion Task + Schedule
            if Archetype.ALERT_SOURCE in manifest.archetypes:
                ingestion_task = await create_alert_ingestion_task(
                    session=session,
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    integration_type=integration_type,
                )
                await create_default_schedule(
                    session=session,
                    tenant_id=tenant_id,
                    task_id=ingestion_task.component.id,
                    schedule_value="5m",
                    integration_id=integration_id,
                )
                logger.info(
                    "created_alert_ingestion_managed_resources",
                    integration_id=integration_id,
                    task_component_id=str(ingestion_task.component.id),
                )

            # Health check Task + Schedule for every integration
            health_task = await create_health_check_task(
                session=session,
                tenant_id=tenant_id,
                integration_id=integration_id,
                integration_type=integration_type,
            )
            await create_default_schedule(
                session=session,
                tenant_id=tenant_id,
                task_id=health_task.component.id,
                schedule_value="5m",
                integration_id=integration_id,
            )
            logger.info(
                "created_health_check_managed_resources",
                integration_id=integration_id,
                task_component_id=str(health_task.component.id),
            )

            # Generic action Tasks from manifest default_schedules
            await self._create_custom_action_tasks(
                session=session,
                tenant_id=tenant_id,
                integration_id=integration_id,
                integration_type=integration_type,
                manifest=manifest,
            )
        except Exception:
            logger.exception(
                "failed_to_create_managed_resources",
                integration_id=integration_id,
                integration_type=integration_type,
            )

    async def _create_custom_action_tasks(
        self,
        session: Any,
        tenant_id: str,
        integration_id: str,
        integration_type: str,
        manifest: Any,
    ) -> None:
        """Create Tasks + Schedules for custom actions in default_schedules.

        Reads the manifest's default_schedules array and creates a generic
        action Task for any action_id not already handled by the built-in
        factory functions (health_check, pull_alerts, alerts_to_ocsf).
        """
        from analysi.services.task_factory import (
            create_action_task,
            create_default_schedule,
        )

        # default_schedules lives in manifest extra fields
        default_schedules = getattr(manifest, "default_schedules", None)
        if not default_schedules:
            raw = manifest.model_dump() if hasattr(manifest, "model_dump") else {}
            default_schedules = raw.get("default_schedules", [])

        if not default_schedules:
            return

        # Build action lookup: action_id -> ActionDefinition
        actions_by_id = {a.id: a for a in manifest.actions}

        for sched_entry in default_schedules:
            action_id = sched_entry.get("action_id", "")
            if action_id in self._BUILTIN_MANAGED_ACTIONS:
                continue

            action = actions_by_id.get(action_id)
            if action is None:
                logger.warning(
                    "default_schedule_action_not_found",
                    integration_id=integration_id,
                    action_id=action_id,
                )
                continue

            # Parse schedule value from "every/24h" -> "24h"
            schedule_raw = sched_entry.get("schedule", "every/5m")
            schedule_value = (
                schedule_raw.split("/", 1)[1] if "/" in schedule_raw else schedule_raw
            )

            task = await create_action_task(
                session=session,
                tenant_id=tenant_id,
                integration_id=integration_id,
                integration_type=integration_type,
                action_id=action_id,
                action_name=action.name or action_id,
                cy_name=action.cy_name or action_id,
                categories=action.categories,
            )
            await create_default_schedule(
                session=session,
                tenant_id=tenant_id,
                task_id=task.component.id,
                schedule_value=schedule_value,
                integration_id=integration_id,
            )
            logger.info(
                "created_action_managed_resources",
                integration_id=integration_id,
                action_id=action_id,
                task_component_id=str(task.component.id),
                schedule_value=schedule_value,
            )

    async def _get_managed_resources_block(
        self, tenant_id: str, integration_id: str
    ) -> dict | None:
        """Build the managed_resources block for the integration detail response."""
        try:
            from analysi.schemas.integration import ManagedResourceBlock
            from analysi.services.managed_resources import list_managed_resources

            session = self.integration_repo.session
            resources = await list_managed_resources(session, tenant_id, integration_id)

            if not resources:
                return None

            result = {}
            for key, resource in resources.items():
                result[key] = ManagedResourceBlock(
                    resource_key=resource.resource_key,
                    task_id=str(resource.task_id),
                    task_name=resource.task_name,
                    schedule_id=(
                        str(resource.schedule_id) if resource.schedule_id else None
                    ),
                    schedule=resource.schedule,
                    last_run=resource.last_run,
                    next_run_at=(
                        resource.next_run_at.isoformat()
                        if resource.next_run_at
                        else None
                    ),
                )
            return result
        except Exception:
            logger.exception(
                "failed_to_get_managed_resources",
                integration_id=integration_id,
            )
            return None

    async def delete_integration(self, tenant_id: str, integration_id: str) -> bool:
        """Delete an integration and its associated credentials."""
        existing = await self.integration_repo.get_integration(
            tenant_id, integration_id
        )

        # Detect if we're deleting the AI primary before it disappears
        promote_after_delete: Any = None
        if existing:
            ai_types = {m.id for m in get_registry().list_by_archetype(Archetype.AI)}
            if existing.integration_type in ai_types and (existing.settings or {}).get(
                "is_primary"
            ):
                remaining = [
                    i
                    for i in await self._get_all_ai_integrations(tenant_id)
                    if i.integration_id != integration_id
                ]
                if remaining:
                    promote_after_delete = remaining[0]

        # Archive Tasks and disable Schedules
        if existing:
            from analysi.services.task_factory import cleanup_integration_tasks

            session = self.integration_repo.session
            cleanup_result = await cleanup_integration_tasks(
                session, tenant_id, integration_id
            )
            logger.info(
                "delete_integration_cleanup",
                integration_id=integration_id,
                **cleanup_result,
            )

        deleted = await self.integration_repo.delete_integration(
            tenant_id, integration_id
        )

        if deleted and promote_after_delete is not None:
            promoted_settings = dict(promote_after_delete.settings or {})
            promoted_settings["is_primary"] = True
            await self.integration_repo.update_integration(
                tenant_id,
                promote_after_delete.integration_id,
                {"settings": promoted_settings},
            )
            logger.info(
                "auto_promoted_to_primary",
                promoted_integration_id=promote_after_delete.integration_id,
                deleted_primary_id=integration_id,
            )

        return deleted

    async def calculate_health(
        self,
        tenant_id: str,
        integration_id: str,
        integration: Any = None,
    ) -> IntegrationHealth:
        """Read cached health status from Integration.health_status.

        The health_status field is updated by a post-execution hook after
        each health check TaskRun completes (see _maybe_update_integration_health
        in task_execution.py).  Falls back to 'unknown' when no health check
        has run yet (health_status is NULL).

        Pass ``integration`` to avoid a redundant DB fetch when the caller
        already has the object loaded.
        """
        if integration is None:
            integration = await self.integration_repo.get_integration(
                tenant_id, integration_id
            )
        if not integration or not integration.health_status:
            return IntegrationHealth(
                status="unknown",
                message="No health check data available",
            )

        messages = {
            IntegrationHealthStatus.HEALTHY: "Integration is healthy",
            IntegrationHealthStatus.UNHEALTHY: "Integration is unhealthy",
            IntegrationHealthStatus.UNKNOWN: "Health check could not determine status",
        }

        return IntegrationHealth(
            status=integration.health_status,
            last_successful_run=integration.last_health_check_at,
            message=messages.get(integration.health_status, "Health data unavailable"),
        )

    async def execute_action(
        self,
        tenant_id: str,
        integration_id: str,
        integration_type: str,
        action_id: str,
        credential_id: UUID | None = None,
        params: dict[str, Any] | None = None,
        job_id: str | None = None,
        run_id: str | None = None,
        session: Any = None,
    ) -> dict[str, Any]:
        """Execute an integration action using the framework."""
        logger.info(
            "executing_action",
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type=integration_type,
            action_id=action_id,
            run_id=run_id,
        )

        # Get framework registry and loader
        framework_registry = get_registry()
        loader = IntegrationLoader()

        # Verify integration type exists in framework
        manifest = framework_registry.get_integration(integration_type)
        if not manifest:
            raise ValueError(
                f"Integration type '{integration_type}' not found in framework"
            )

        # Find the action in manifest
        action_def = None
        for action in manifest.actions:
            if action.id == action_id:
                action_def = action
                break

        if not action_def:
            raise ValueError(
                f"Action '{action_id}' not found in integration '{integration_type}'"
            )

        # Fetch integration settings
        integration = await self.integration_repo.get_integration(
            tenant_id, integration_id
        )
        if not integration:
            raise ValueError(
                f"Integration '{integration_id}' not found for tenant '{tenant_id}'"
            )

        # Merge manifest defaults with tenant-specific overrides
        from analysi.integrations.framework.base_ai import _extract_settings_defaults

        settings = _extract_settings_defaults(manifest)
        overrides = integration.settings or {}
        default_presets = settings.get("model_presets", {})
        override_presets = overrides.get("model_presets")
        settings.update(overrides)
        if default_presets and override_presets is not None:
            settings["model_presets"] = {**default_presets, **override_presets}

        # Fetch credentials if credential_id provided
        credentials = {}
        if credential_id and self.credential_repo:
            from analysi.services.credential_service import CredentialService

            credential_service = CredentialService(self.credential_repo.session)
            credentials = await credential_service.get_credential(
                tenant_id, credential_id
            )
            if credentials:
                logger.info("loaded_credentials_for", integration_id=integration_id)
            else:
                raise ValueError(
                    f"Credential {credential_id} not found for tenant {tenant_id}"
                )

        # Build execution context
        ctx = {
            "tenant_id": tenant_id,
            "integration_id": integration_id,
            "job_id": job_id,
            "run_id": run_id,
            "session": session,
        }

        # Load and execute action
        action = await loader.load_action(
            integration_id=integration_type,
            action_id=action_id,
            action_metadata={"categories": action_def.categories},
            settings=settings,
            credentials=credentials,
            ctx=ctx,
        )

        result = await action.execute(**(params or {}))

        logger.info(
            "action_execution_completed",
            integration_id=integration_id,
            action_id=action_id,
            status=result.get("status"),
        )

        return result
