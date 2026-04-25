"""Strategy provider for workflow generation stages.

This module provides a factory that returns the appropriate stage
implementations based on configuration.

SDK Skills Integration (Hydra Phases 6-8):
When skills_syncer and session are provided, the AgentRunbookStage
will sync DB-backed skills before agent execution and submit new
files to Hydra after execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from analysi.agentic_orchestration.stages.base import StageStrategy
from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
    from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer
    from analysi.agentic_orchestration.task_generation_client import (
        TaskGenerationApiClient,
    )

logger = get_logger(__name__)


class StageStrategyProvider:
    """Provides stage strategies for workflow generation.

    Usage:
        provider = StageStrategyProvider(executor=executor)
        stages = provider.get_stages()
    """

    def __init__(
        self,
        executor: AgentOrchestrationExecutor | None = None,
        max_tasks_to_build: int | None = None,
        task_generation_client: TaskGenerationApiClient | None = None,
        skills_syncer: TenantSkillsSyncer | None = None,
        session: AsyncSession | None = None,
    ):
        """Initialize provider.

        Args:
            executor: Required — the agent executor for running stages
            max_tasks_to_build: Limit parallel task building (cost control)
            task_generation_client: Optional client for tracking task building progress
            skills_syncer: Optional TenantSkillsSyncer for DB-backed skills.
                          When provided, skills are synced to workspace before
                          agent execution (enables tenant-isolated skills).
            session: Optional database session for Hydra submission.
                    When provided with skills_syncer, new files created by
                    the agent are submitted to the Hydra extraction pipeline.
        """
        self.executor = executor
        self.max_tasks_to_build = max_tasks_to_build
        self.task_generation_client = task_generation_client
        self.skills_syncer = skills_syncer
        self.session = session

        logger.info("stagestrategyprovider_initialized")

    def get_stages(self) -> list[StageStrategy]:
        """Return ordered list of stage strategies.

        Returns:
            List of 4 stages in order: runbook, proposals, building, assembly

        Raises:
            ValueError: If executor not provided
        """
        if not self.executor:
            raise ValueError(
                "StageStrategyProvider requires an AgentOrchestrationExecutor."
            )

        # Import here to avoid circular imports
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
            AgentTaskBuildingStage,
            AgentTaskProposalStage,
            AgentWorkflowAssemblyStage,
        )

        return [
            AgentRunbookStage(
                self.executor,
                skills_syncer=self.skills_syncer,
                session=self.session,
            ),
            AgentTaskProposalStage(self.executor),
            AgentTaskBuildingStage(
                self.executor,
                self.max_tasks_to_build,
                self.task_generation_client,
            ),
            AgentWorkflowAssemblyStage(self.executor),
        ]
