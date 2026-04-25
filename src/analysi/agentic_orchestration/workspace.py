"""Agent workspace for file-based agent execution.

Key Pattern: REPL Agent Adaptation for Headless Execution
---------------------------------------------------------
Agents designed for interactive REPL use don't automatically write files.
This module adapts REPL agents for headless SDK execution by:

1. Injecting working directory instructions
2. Providing input context as JSON
3. **Adding explicit file write requirements** (critical for headless mode)

Example prompt transformation:
    Original REPL agent: "Analyze this alert and find matching runbook"
    Adapted for SDK: "... [same] ...
                      ## Required Output Files
                      - Write matching-report.json with the appropriate content
                      - Write matched-runbook.md with the appropriate content

                      IMPORTANT: This is running in headless mode. You must write
                      these files - do not just provide the content in your response."

This allows the same agent .md files to work in both contexts:
- REPL: User reads chat output
- SDK/Orchestrator: System captures file outputs into state

- TenantSkillsSyncer syncs DB-backed skills to workspace before execution
- ContentPolicy filters agent-created files before submission
- New files are routed through extraction pipeline for validation
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from analysi.agentic_orchestration.config import get_workspace_auto_cleanup
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer

logger = get_logger(__name__)


def get_system_prompt_for_stage(stage: WorkflowGenerationStage) -> str:
    """Get specialized system prompt for each workflow generation stage.

    System prompts are defined in AutomatedWorkflowBuilder_v1.md spec and
    provide phase-specific expertise for each agent.

    Args:
        stage: The workflow generation stage

    Returns:
        Specialized system prompt for the stage
    """
    prompts = {
        WorkflowGenerationStage.RUNBOOK_GENERATION: (
            "Expert Cyber Security Analyst specialized in creating comprehensive "
            "runbooks from security alerts"
        ),
        WorkflowGenerationStage.TASK_PROPOSALS: (
            "Expert Cyber Security Analyst specialized in identifying available "
            "tools and composing them into discrete Tasks"
        ),
        WorkflowGenerationStage.TASK_BUILDING: (
            "Expert Cyber Security Analyst specialized in DSL programming, with "
            "emphasis on quality, accuracy, and testing"
        ),
        WorkflowGenerationStage.WORKFLOW_ASSEMBLY: (
            "Expert Cyber Security Analyst specialized in workflow composition "
            "and validation, with emphasis on creating executable workflows"
        ),
    }
    return prompts[stage]


class AgentWorkspace:
    """Manages isolated workspace for agent execution.

    Enables using the same agent .md files for both:
    - Local REPL testing (files appear in working directory)
    - Production execution (isolated temp dir, captured into state)

    Key SDK options required:
    - permission_mode="bypassPermissions" - Auto-accept file writes
    - allowed_tools=["Write", "Read", "Bash"] - Restrict to file operations
    - cwd=str(work_dir) - Set working directory for file writes

    - skills_syncer: Syncs DB-backed skills to workspace/.claude/skills/
    - skills_dir: Path to synced skills (for SDK setting_sources=["project"])
    - setup_skills(): Sync ALL tenant skills before agent execution (no args needed)
    - detect_new_files(): Find agent-created files after execution
    """

    def __init__(
        self,
        run_id: str,
        tenant_id: str | None = None,
        auto_cleanup: bool | None = None,
        skills_syncer: TenantSkillsSyncer | None = None,
    ):
        """Create isolated workspace for a workflow run.

        Args:
            run_id: Workflow generation run ID (UUID) for unique isolation
            tenant_id: Optional tenant ID for multi-tenant isolation
            auto_cleanup: If True, cleanup() removes workspace. If False, workspace is preserved.
                         If None (default), uses get_workspace_auto_cleanup() from config (defaults to False).
            skills_syncer: Optional TenantSkillsSyncer for DB-backed skills.
                          When provided, skills are synced to workspace/.claude/skills/
                          and SDK uses setting_sources=["project"] for tenant isolation.

        Cleanup Policy:
            - Default (auto_cleanup=None): Workspace is preserved (no automatic cleanup)
            - Eval/Testing: Fixtures call cleanup() explicitly when needed
            - Production: Set ANALYSI_AUTO_CLEANUP_WORKSPACES=true to enable auto-cleanup
        """
        self.run_id = run_id
        self.tenant_id = tenant_id
        self.skills_syncer = skills_syncer
        self._skills_synced = False

        # Determine cleanup policy from config or explicit parameter
        if auto_cleanup is None:
            self.auto_cleanup = get_workspace_auto_cleanup()
        else:
            self.auto_cleanup = auto_cleanup

        # Build prefix with tenant isolation
        # Format: kea-{tenant}-{full-uuid}-
        # Examples:
        #   With tenant: kea-acme-550e8400-e29b-41d4-a716-446655440000-abc123
        #   Without tenant: kea-550e8400-e29b-41d4-a716-446655440000-xyz789
        prefix = f"kea-{tenant_id}-{run_id}-" if tenant_id else f"kea-{run_id}-"

        self.work_dir = Path(tempfile.mkdtemp(prefix=prefix))

    @property
    def skills_dir(self) -> Path:
        """Path to .claude/skills directory in workspace.

        This is where skills are synced for SDK to load via setting_sources=["project"].
        """
        return self.work_dir / ".claude" / "skills"

    async def setup_skills(
        self, skill_names: list[str] | None = None
    ) -> dict[str, str]:
        """Sync skills to workspace before agent execution.

        Args:
            skill_names: Optional list of specific skill names to sync.
                        If None (default), syncs ALL tenant skills.

        Returns:
            Dict mapping skill_name to source ("db")

        Raises:
            RuntimeError: If called without skills_syncer
            SkillNotFoundError: If specific skill not found in DB
        """
        if not self.skills_syncer:
            raise RuntimeError(
                "Cannot setup_skills without skills_syncer. "
                "Pass skills_syncer to AgentWorkspace constructor."
            )

        if skill_names is None:
            # Sync ALL tenant skills - preferred approach
            result = await self.skills_syncer.sync_all_skills(self.skills_dir)
        else:
            # Sync specific skills only
            result = await self.skills_syncer.sync_skills(self.skills_dir, skill_names)

        self._skills_synced = True
        logger.info(
            "synced_skills_to", result_count=len(result), skills_dir=self.skills_dir
        )
        return result

    def detect_new_files(self) -> list[Path]:
        """Detect files created or modified by the agent.

        Must call setup_skills() first to establish baseline.

        Returns:
            List of new/modified file paths in the skills directory

        Raises:
            RuntimeError: If skills weren't synced or no syncer configured
        """
        if not self.skills_syncer:
            raise RuntimeError("Cannot detect_new_files without skills_syncer")
        if not self._skills_synced:
            raise RuntimeError("Must call setup_skills() before detect_new_files()")

        return self.skills_syncer.detect_new_files(self.skills_dir)

    async def run_agent(
        self,
        executor: AgentOrchestrationExecutor,
        agent_prompt_path: Path,
        context: dict[str, Any],
        expected_outputs: list[str],
        stage: WorkflowGenerationStage,
        callback: ProgressCallback | None = None,
    ) -> tuple[dict[str, str | None], StageExecutionMetrics]:
        """Run agent and capture file outputs.

        Args:
            executor: AgentOrchestrationExecutor for Claude SDK calls
            agent_prompt_path: Path to agent .md file
            context: Context data to inject into prompt
            expected_outputs: List of expected output filenames
            stage: Workflow generation stage for metrics
            callback: Optional progress callback

        Returns:
            Tuple of (outputs dict mapping filename to content or None, metrics)
        """
        # Load agent prompt
        agent_prompt = agent_prompt_path.read_text()

        # Build user prompt with working directory and context injection
        # Add explicit file write instructions for headless SDK execution
        file_write_instructions = "\n".join(
            [
                f"- Write {filename} with the appropriate content"
                for filename in expected_outputs
            ]
        )

        user_prompt = f"""{agent_prompt}

## Working Directory
Write all output files to: {self.work_dir}

## Input Context
```json
{json.dumps(context, indent=2)}
```

## Required Output Files
After completing your analysis, you MUST write the following files to the working directory:
{file_write_instructions}

IMPORTANT: This is running in headless mode. You must write these files - do not just provide the content in your response.
"""

        # Execute via SDK
        # Note: executor needs to be configured with:
        # - permission_mode="bypassPermissions" (headless execution)
        # - allowed_tools=["Write", "Read", "Bash"]
        # - cwd parameter set to working directory

        # Auto-sync skills from DB if syncer is provided and not yet synced
        if self.skills_syncer and not self._skills_synced:
            await self.setup_skills()
            executor.skills_project_dir = self.work_dir
            logger.info("autosynced_skills_to", skills_dir=self.skills_dir)

        logger.info("executing_agent", name=agent_prompt_path.name)
        logger.info("working_directory", work_dir=self.work_dir)
        logger.info("expected_outputs", expected_outputs=expected_outputs)

        # Validate MCP configuration for agents that require it
        mcp_required_agents = [
            "runbook-to-task-proposals.md",
            "cybersec-task-builder.md",
            "workflow-builder.md",
        ]

        if agent_prompt_path.name in mcp_required_agents:
            if not executor.mcp_servers:
                logger.warning(
                    "mcp_servers_not_configured_for_agent",
                    agent_name=agent_prompt_path.name,
                )
            else:
                logger.info(
                    "mcp_servers_configured", servers=list(executor.mcp_servers.keys())
                )

        # Determine cwd parameter based on isolated_project_dir
        # If isolated_project_dir is set (eval tests), pass None to let SDK use it directly
        # Otherwise, pass workspace directory for file operations
        if executor.isolated_project_dir:
            logger.info(
                "using_isolatedprojectdir",
                isolated_project_dir=executor.isolated_project_dir,
            )
            logger.info("workspace_for_output_capture", work_dir=self.work_dir)
            cwd_param = None  # Let SDK use isolated_project_dir
        else:
            logger.info("using_workspace_as_cwd", work_dir=self.work_dir)
            cwd_param = str(self.work_dir)

        # Get and log the system prompt for this stage
        system_prompt = get_system_prompt_for_stage(stage)
        logger.info(
            "starting_with_system_prompt",
            value=stage.value,
            system_prompt=system_prompt,
        )

        # Extract context_id from run_id for logging (e.g., "task0" from "uuid-task-0")
        context_id = None
        if "-task-" in self.run_id:
            # Format: {generation_id}-task-{index}
            task_part = self.run_id.split("-task-")[-1]
            context_id = f"task{task_part}"

        result, metrics = await executor.execute_stage(
            stage=stage,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cwd=cwd_param,
            callback=callback,
            context_id=context_id,
        )

        logger.info(
            "agent_execution_completed", result_length=len(result) if result else 0
        )

        # List what files actually exist in workspace
        actual_files = list(self.work_dir.iterdir()) if self.work_dir.exists() else []
        logger.info("workspace_files", files=[f.name for f in actual_files])

        # Log workspace file summary (not individual contents — may contain sensitive data)
        file_sizes = {}
        for file in actual_files:
            if file.is_file():
                try:
                    file_sizes[file.name] = len(file.read_text())
                except UnicodeDecodeError:
                    file_sizes[file.name] = file.stat().st_size
        if file_sizes:
            logger.debug(
                "workspace_file_sizes",
                file_count=len(file_sizes),
                files=file_sizes,
            )

        # Capture expected outputs
        outputs: dict[str, str | None] = {}
        for filename in expected_outputs:
            filepath = self.work_dir / filename
            if filepath.exists():
                try:
                    content = filepath.read_text()
                    outputs[filename] = content
                    logger.info(
                        "captured_bytes", filename=filename, content_count=len(content)
                    )
                except UnicodeDecodeError as e:
                    logger.error(
                        "failed_to_read_as_utf8", filename=filename, error=str(e)
                    )
                    outputs[filename] = None
            else:
                # Check for alternative filenames
                # The agent might write composed-runbook.md when composing new runbooks
                if filename == "matched-runbook.md":
                    alt_filepath = self.work_dir / "composed-runbook.md"
                    if alt_filepath.exists():
                        content = alt_filepath.read_text()
                        outputs[filename] = content
                        logger.info(
                            "Found generated runbook (direct match was not possible)"
                        )
                        logger.info(
                            "captured_from_composedrunbookmd_bytes",
                            filename=filename,
                            content_count=len(content),
                        )
                        continue

                outputs[filename] = None
                logger.warning("expected_file_not_found", filename=filename)

        return outputs, metrics

    def cleanup(self):
        """Remove workspace directory if auto_cleanup is enabled.

        Default behavior: Workspace is preserved (not deleted).
        Test fixtures should call cleanup() explicitly when needed.
        Production can set ANALYSI_AUTO_CLEANUP_WORKSPACES=true for automatic cleanup.
        """
        if not self.auto_cleanup:
            logger.info("preserving_workspace_autocleanupfalse", work_dir=self.work_dir)
            return

        if self.work_dir.exists():
            logger.info("cleaning_up_workspace_autocleanuptrue", work_dir=self.work_dir)
            shutil.rmtree(self.work_dir)
