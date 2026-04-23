"""Step 3: Workflow Builder implementation"""

from analysi.config.logging import get_logger

logger = get_logger(__name__)


# Module-level global cache shared across all workers in the same process
# This enables cache updates from reconciliation job to benefit subsequent alert processing
_GLOBAL_ANALYSIS_GROUP_CACHE: "AnalysisGroupCache | None" = None


def get_global_cache() -> "AnalysisGroupCache":
    """Get or create the global analysis group cache singleton."""
    global _GLOBAL_ANALYSIS_GROUP_CACHE
    if _GLOBAL_ANALYSIS_GROUP_CACHE is None:
        _GLOBAL_ANALYSIS_GROUP_CACHE = AnalysisGroupCache()
    return _GLOBAL_ANALYSIS_GROUP_CACHE


def invalidate_global_cache() -> bool:
    """
    Invalidate (clear) the global analysis group cache.

    Called by admin endpoints when workflow mappings are reset.
    Note: This only clears the cache in the current process. Worker processes
    will still have stale cache until they hit a 404 and retry.

    Returns:
        True if cache was cleared, False if cache didn't exist
    """
    global _GLOBAL_ANALYSIS_GROUP_CACHE
    if _GLOBAL_ANALYSIS_GROUP_CACHE is not None:
        _GLOBAL_ANALYSIS_GROUP_CACHE.clear()
        logger.info("Global analysis group cache invalidated via admin API")
        return True
    return False


class AnalysisGroupCache:
    """In-memory cache for analysis groups to reduce DB lookups.

    Provides fast lookups for:
    - (tenant_id, title) → group IDs
    - Group IDs → workflow IDs

    All lookups are tenant-scoped to prevent cross-tenant data leaks.
    Used by WorkflowBuilderStep to avoid repeated API calls to Kea Coordination.
    """

    def __init__(self):
        self._cache: dict[tuple[str, str], str] = {}  # (tenant_id, title) → group_id
        self._workflows: dict[str, str | None] = {}  # group_id → workflow_id

    def _key(self, tenant_id: str, title: str) -> tuple[str, str]:
        return (tenant_id, title)

    def get_group_id(self, title: str, tenant_id: str) -> str | None:
        """Get cached group ID by tenant and title.

        Args:
            title: Analysis group title (e.g., alert rule_name)
            tenant_id: Tenant identifier for isolation

        Returns:
            Group ID if cached, None otherwise
        """
        return self._cache.get(self._key(tenant_id, title))

    def set_group(
        self, title: str, group_id: str, workflow_id: str | None, tenant_id: str
    ):
        """Cache group and its workflow.

        Args:
            title: Analysis group title
            group_id: Analysis group UUID
            workflow_id: Workflow UUID (None if generation in progress)
            tenant_id: Tenant identifier for isolation
        """
        self._cache[self._key(tenant_id, title)] = group_id
        self._workflows[group_id] = workflow_id

    def get_workflow_id(self, group_id: str) -> str | None:
        """Get cached workflow ID for group.

        Args:
            group_id: Analysis group UUID

        Returns:
            Workflow ID if cached, None if not cached or no workflow yet
        """
        return self._workflows.get(group_id)

    def invalidate_group(self, group_id: str):
        """Invalidate cache entry (used when workflow generation completes).

        This removes the workflow mapping but keeps the title → group_id mapping.
        Allows re-querying for the newly created workflow.

        Args:
            group_id: Analysis group UUID to invalidate
        """
        if group_id in self._workflows:
            del self._workflows[group_id]

    def clear(self):
        """Clear all cached entries.

        Used when we detect stale cache (e.g., workflow not found 404).
        Forces fresh lookups from Kea Coordination API.
        """
        logger.info("Clearing analysis group cache")
        self._cache.clear()
        self._workflows.clear()


class WorkflowBuilderStep:
    """
    Workflow builder step using Kea Coordination for intelligent workflow selection.

    1. Determines analysis group from alert data (using rule_name)
    2. Uses cache for fast lookups
    3. Queries/creates analysis groups via Kea Coordination API
    4. Triggers workflow generation for new alert types
    5. Pauses alerts during generation
    """

    def __init__(
        self,
        kea_client,  # KeaCoordinationClient
        cache: AnalysisGroupCache | None = None,
        actor_user_id: str | None = None,
    ):
        """
        Initialize workflow builder step with dependencies.

        Args:
            kea_client: Client for Kea Coordination API
            cache: Optional cache instance (uses global cache if not provided)
            actor_user_id: UUID of the user who triggered analysis (for audit attribution).
                None for system-initiated triggers (reconciliation, control events).
        """
        self.kea_client = kea_client
        # Use global cache by default to share cache across reconciliation and normal processing
        self.cache = cache if cache is not None else get_global_cache()
        self.actor_user_id = actor_user_id

    def invalidate_cache(self):
        """Clear the workflow cache to force fresh lookups.

        Called by the pipeline when a workflow is not found (404),
        indicating the cache may contain stale workflow IDs.
        """
        self.cache.clear()

    async def execute(
        self,
        tenant_id: str,
        alert_id: str,
        analysis_id: str,
        alert_data: dict,  # alert data
        **kwargs,
    ) -> str | None:
        """
        Select workflow for alert analysis using Kea Coordination.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID
            analysis_id: Analysis UUID for tracking
            alert_data: Alert data dictionary (OCSF format)

        Returns:
            str: Workflow ID if ready for execution
            None: If alert is paused (workflow generation in progress)

        Raises:
            ValueError: If alert missing required fields
            Exception: If API call fails
        """
        # Determine analysis group from alert (V1: use rule_name)
        group_title = await self._get_analysis_group_title(alert_data)
        logger.info(
            "alert_belongs_to_analysis_group",
            alert_id=alert_id,
            group_title=group_title,
        )

        # Check cache first (fast path) — tenant-scoped to prevent cross-tenant leaks
        group_id = self.cache.get_group_id(group_title, tenant_id=tenant_id)

        if group_id:
            workflow_id = self.cache.get_workflow_id(group_id)
            if workflow_id:
                logger.info(
                    "cache_hit_group_has_workflow",
                    group_id=group_id,
                    workflow_id=workflow_id,
                )
                return workflow_id

        # Cache miss - query/create group atomically
        try:
            result = await self.kea_client.create_group_with_generation(
                tenant_id=tenant_id,
                title=group_title,
                triggering_alert_analysis_id=analysis_id,
            )
            group_id = result["analysis_group"]["id"]
            generation = result["workflow_generation"]

            logger.info(
                "group_generation_status",
                group_id=group_id,
                status=generation["status"],
            )

            # Check if workflow already exists (race condition: another worker created it)
            if generation.get("workflow_id"):
                workflow_id = generation["workflow_id"]
                self.cache.set_group(
                    group_title, group_id, workflow_id, tenant_id=tenant_id
                )
                logger.info(
                    "workflow_already_exists_for_group",
                    workflow_id=workflow_id,
                    group_id=group_id,
                )
                return workflow_id

            # Workflow generation needed - return None to signal pause
            # Pipeline will handle database status update (maintains decoupling)
            logger.info(
                "workflow_not_ready_for_alert_will_pause_for_genera", alert_id=alert_id
            )

            # Only trigger workflow generation if THIS alert created the generation.
            # This prevents duplicate jobs when multiple alerts arrive for the same rule_name.
            # The triggering_alert_analysis_id is set when the generation is first created.
            triggering_id = generation.get("triggering_alert_analysis_id")
            if not triggering_id:
                logger.warning(
                    "generation_missing_triggering_analysis_id",
                    generation_id=generation["id"],
                )
            elif str(triggering_id) == str(analysis_id):
                await self._trigger_workflow_generation(
                    tenant_id=tenant_id,
                    generation_id=generation["id"],
                    alert_data=alert_data,
                )
            else:
                logger.info(
                    "skipping_job_enqueue_already_triggered",
                    generation_id=generation["id"],
                    triggering_id=triggering_id,
                )

            return None  # Signal to pipeline: workflow not ready, pause needed

        except Exception as e:
            logger.error("failed_to_getcreate_analysis_group", error=str(e))
            raise

    async def _get_analysis_group_title(self, alert_data: dict) -> str:
        """
        Extract analysis group title from alert.

        Uses rule_name as the group title.

        Args:
            alert_data: Alert data dictionary

        Returns:
            str: Analysis group title

        Raises:
            ValueError: If rule_name missing
        """
        rule_name = alert_data.get("rule_name")
        if not rule_name:
            raise ValueError("Alert missing required field: rule_name")
        return rule_name

    async def _trigger_workflow_generation(
        self,
        tenant_id: str,
        generation_id: str,
        alert_data: dict,
    ):
        """
        Trigger workflow generation asynchronously.

        Enqueues ARQ job for workflow generation.

        Args:
            tenant_id: Tenant identifier
            generation_id: Workflow generation UUID
            alert_data: Alert data for context

        Note:
            actor_user_id is forwarded from self. When provided, the MCP
            middleware resolves the actor's tenant membership and applies
            their RBAC roles instead of the system key's roles.
        """
        from arq import create_pool

        from analysi.config.valkey_db import ValkeyDBConfig

        logger.info("triggering_workflow_generation", generation_id=generation_id)

        # Create Redis pool
        redis_settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        redis = await create_pool(redis_settings)

        try:
            # Enqueue workflow generation job
            await redis.enqueue_job(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.execute_workflow_generation",
                generation_id,
                tenant_id,
                alert_data,
                None,  # max_tasks_to_build (use config default)
                self.actor_user_id,  # For audit attribution
            )
            logger.info(
                "enqueued_workflow_generation_job_for", generation_id=generation_id
            )
        finally:
            await redis.aclose()
