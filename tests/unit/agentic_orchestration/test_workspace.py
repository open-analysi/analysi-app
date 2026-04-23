"""Tests for AgentWorkspace file capture pattern."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration import (
    AgentWorkspace,
    StageExecutionMetrics,
    WorkflowGenerationStage,
)


class TestAgentWorkspaceInit:
    """Tests for AgentWorkspace initialization."""

    def test_workspace_creates_isolated_directory(self):
        """Verify workspace creates temp dir with kea prefix."""
        workspace = AgentWorkspace(run_id="test-run-12345678")

        try:
            assert workspace.work_dir.exists()
            assert workspace.work_dir.is_dir()
            assert "kea-test-run" in str(workspace.work_dir)
        finally:
            workspace.cleanup()

    def test_workspace_uses_run_id_prefix(self):
        """Verify workspace directory name includes full run_id."""
        run_id = "abcdefgh-ijkl-mnop-qrst-uvwxyz123456"
        workspace = AgentWorkspace(run_id=run_id)

        try:
            # Should use full run_id
            assert f"kea-{run_id}" in str(workspace.work_dir)
        finally:
            workspace.cleanup()

    def test_workspace_handles_short_run_id(self):
        """Verify workspace handles run_id shorter than 8 chars."""
        workspace = AgentWorkspace(run_id="short")

        try:
            assert workspace.work_dir.exists()
            assert "kea-short" in str(workspace.work_dir)
        finally:
            workspace.cleanup()


class TestAgentWorkspaceCleanup:
    """Tests for AgentWorkspace cleanup."""

    def test_workspace_cleanup_removes_directory(self):
        """Verify cleanup removes workspace directory when auto_cleanup=True."""
        workspace = AgentWorkspace(run_id="cleanup-test", auto_cleanup=True)
        work_dir = workspace.work_dir

        # Create a file in the workspace
        test_file = work_dir / "test.txt"
        test_file.write_text("test content")

        assert work_dir.exists()
        workspace.cleanup()
        assert not work_dir.exists()

    def test_workspace_cleanup_handles_already_removed(self):
        """Verify cleanup handles already-removed directory gracefully."""
        workspace = AgentWorkspace(run_id="already-removed")

        # Manually remove
        workspace.work_dir.rmdir()

        # Should not raise
        workspace.cleanup()

    def test_workspace_cleanup_removes_nested_files(self):
        """Verify cleanup removes nested files and directories when auto_cleanup=True."""
        workspace = AgentWorkspace(run_id="nested-test", auto_cleanup=True)

        # Create nested structure
        subdir = workspace.work_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")
        (workspace.work_dir / "root.txt").write_text("root")

        workspace.cleanup()
        assert not workspace.work_dir.exists()


class TestAgentWorkspaceRunAgent:
    """Tests for AgentWorkspace.run_agent method."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor for testing."""
        executor = MagicMock()
        executor.execute_stage = AsyncMock(
            return_value=(
                "Agent completed successfully",
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={"input_tokens": 100, "output_tokens": 200},
                    tool_calls=[],
                ),
            )
        )
        return executor

    @pytest.fixture
    def agent_file(self, tmp_path):
        """Create a test agent .md file."""
        agent_path = tmp_path / "test-agent.md"
        agent_path.write_text("""# Test Agent

Analyze the input and write results to output files.
""")
        return agent_path

    @pytest.mark.asyncio
    async def test_workspace_captures_expected_outputs(self, mock_executor, agent_file):
        """Verify run_agent reads expected files into dict."""
        workspace = AgentWorkspace(run_id="capture-test")

        try:
            # Pre-create files that agent would create
            (workspace.work_dir / "output.json").write_text('{"result": "success"}')
            (workspace.work_dir / "report.md").write_text("# Report")

            outputs, metrics = await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={"test": "data"},
                expected_outputs=["output.json", "report.md"],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            assert outputs["output.json"] == '{"result": "success"}'
            assert outputs["report.md"] == "# Report"
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_handles_missing_outputs(self, mock_executor, agent_file):
        """Verify missing files return None in outputs."""
        workspace = AgentWorkspace(run_id="missing-test")

        try:
            # Only create one of the expected files
            (workspace.work_dir / "exists.txt").write_text("I exist")

            outputs, metrics = await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=["exists.txt", "missing.txt"],
                stage=WorkflowGenerationStage.TASK_PROPOSALS,
            )

            assert outputs["exists.txt"] == "I exist"
            assert outputs["missing.txt"] is None
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_injects_working_directory(self, mock_executor, agent_file):
        """Verify user prompt includes work_dir path."""
        workspace = AgentWorkspace(run_id="inject-test")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={"alert": "test"},
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            # Check the user_prompt passed to executor
            call_args = mock_executor.execute_stage.call_args
            user_prompt = call_args.kwargs["user_prompt"]

            assert str(workspace.work_dir) in user_prompt
            assert "## Working Directory" in user_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_injects_context_as_json(self, mock_executor, agent_file):
        """Verify context is injected as JSON in user prompt."""
        workspace = AgentWorkspace(run_id="context-test")

        try:
            context = {"alert": {"id": "123", "severity": "high"}}

            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context=context,
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            call_args = mock_executor.execute_stage.call_args
            user_prompt = call_args.kwargs["user_prompt"]

            assert "## Input Context" in user_prompt
            assert '"alert"' in user_prompt
            assert '"id": "123"' in user_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_includes_agent_content(self, mock_executor, agent_file):
        """Verify agent .md content is included in user prompt."""
        workspace = AgentWorkspace(run_id="agent-content-test")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            call_args = mock_executor.execute_stage.call_args
            user_prompt = call_args.kwargs["user_prompt"]

            assert "# Test Agent" in user_prompt
            assert "Analyze the input" in user_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_passes_callback(self, mock_executor, agent_file):
        """Verify callback is passed to executor."""
        workspace = AgentWorkspace(run_id="callback-test")
        mock_callback = AsyncMock()

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                callback=mock_callback,
            )

            call_args = mock_executor.execute_stage.call_args
            assert call_args.kwargs["callback"] == mock_callback
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_returns_metrics(self, mock_executor, agent_file):
        """Verify metrics are returned from executor."""
        workspace = AgentWorkspace(run_id="metrics-test")

        try:
            outputs, metrics = await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            assert metrics.total_cost_usd == 0.05
            assert metrics.num_turns == 3
        finally:
            workspace.cleanup()


class TestAgentWorkspaceTenantIsolation:
    """Tests for tenant isolation in AgentWorkspace."""

    def test_workspace_with_tenant_id_includes_tenant_in_path(self):
        """Verify workspace directory includes tenant ID when provided."""
        tenant_id = "acme"
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        workspace = AgentWorkspace(run_id=run_id, tenant_id=tenant_id)

        try:
            assert workspace.work_dir.exists()
            assert workspace.work_dir.is_dir()
            # Should contain both tenant and full run_id
            assert f"kea-{tenant_id}-{run_id}" in str(workspace.work_dir)
        finally:
            workspace.cleanup()

    def test_workspace_without_tenant_id_omits_tenant_from_path(self):
        """Verify workspace directory excludes tenant ID when not provided."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        workspace = AgentWorkspace(run_id=run_id, tenant_id=None)

        try:
            assert workspace.work_dir.exists()
            assert workspace.work_dir.is_dir()
            # Should contain run_id but not tenant
            assert f"kea-{run_id}" in str(workspace.work_dir)
            # Should not have double hyphen (kea--) from missing tenant
            assert "kea--" not in str(workspace.work_dir)
        finally:
            workspace.cleanup()

    def test_workspace_uses_full_uuid_not_truncated(self):
        """Verify workspace uses full UUID instead of truncating to 8 chars."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        workspace = AgentWorkspace(run_id=run_id)

        try:
            # Should contain full UUID
            assert run_id in str(workspace.work_dir)
            # Should NOT contain only first 8 chars
            dir_str = str(workspace.work_dir)
            assert run_id in dir_str, f"Full UUID {run_id} should be in {dir_str}"
        finally:
            workspace.cleanup()

    def test_workspace_different_tenants_create_different_dirs(self):
        """Verify different tenants get isolated directories."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        workspace1 = AgentWorkspace(run_id=run_id, tenant_id="acme")
        workspace2 = AgentWorkspace(run_id=run_id, tenant_id="globex")

        try:
            # Different tenants should have different directories
            assert workspace1.work_dir != workspace2.work_dir
            assert "acme" in str(workspace1.work_dir)
            assert "globex" in str(workspace2.work_dir)
        finally:
            workspace1.cleanup()
            workspace2.cleanup()


class TestSystemPromptMapping:
    """Tests for stage-specific system prompts."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor for testing."""
        executor = MagicMock()
        executor.execute_stage = AsyncMock(
            return_value=(
                "Agent completed",
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        return executor

    @pytest.fixture
    def agent_file(self, tmp_path):
        """Create a test agent .md file."""
        agent_path = tmp_path / "test-agent.md"
        agent_path.write_text("# Test Agent\n\nDo something.")
        return agent_path

    @pytest.mark.asyncio
    async def test_runbook_generation_uses_specialized_prompt(
        self, mock_executor, agent_file
    ):
        """Verify Runbook Generation stage uses specialized system prompt."""
        workspace = AgentWorkspace(run_id="test-prompt-1")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            )

            call_args = mock_executor.execute_stage.call_args
            system_prompt = call_args.kwargs["system_prompt"]

            assert "Expert Cyber Security Analyst" in system_prompt
            assert "comprehensive runbooks" in system_prompt
            assert "security alerts" in system_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_task_proposal_uses_specialized_prompt(
        self, mock_executor, agent_file
    ):
        """Verify Task Proposals stage uses specialized system prompt."""
        workspace = AgentWorkspace(run_id="test-prompt-2")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.TASK_PROPOSALS,
            )

            call_args = mock_executor.execute_stage.call_args
            system_prompt = call_args.kwargs["system_prompt"]

            assert "Expert Cyber Security Analyst" in system_prompt
            assert "identifying available tools" in system_prompt
            assert "discrete Tasks" in system_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_task_building_uses_specialized_prompt(
        self, mock_executor, agent_file
    ):
        """Verify Task Building stage uses specialized system prompt."""
        workspace = AgentWorkspace(run_id="test-prompt-3")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.TASK_BUILDING,
            )

            call_args = mock_executor.execute_stage.call_args
            system_prompt = call_args.kwargs["system_prompt"]

            assert "Expert Cyber Security Analyst" in system_prompt
            assert "DSL programming" in system_prompt
            assert "quality, accuracy, and testing" in system_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_workflow_assembly_uses_specialized_prompt(
        self, mock_executor, agent_file
    ):
        """Verify Workflow Assembly stage uses specialized system prompt."""
        workspace = AgentWorkspace(run_id="test-prompt-4")

        try:
            await workspace.run_agent(
                executor=mock_executor,
                agent_prompt_path=agent_file,
                context={},
                expected_outputs=[],
                stage=WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
            )

            call_args = mock_executor.execute_stage.call_args
            system_prompt = call_args.kwargs["system_prompt"]

            assert "Expert Cyber Security Analyst" in system_prompt
            assert "workflow composition" in system_prompt
            assert "validation" in system_prompt
        finally:
            workspace.cleanup()

    @pytest.mark.asyncio
    async def test_each_stage_has_different_prompt(self, mock_executor, agent_file):
        """Verify all stages have distinct system prompts."""
        workspace = AgentWorkspace(run_id="test-distinct")

        try:
            prompts = {}

            for stage in WorkflowGenerationStage:
                await workspace.run_agent(
                    executor=mock_executor,
                    agent_prompt_path=agent_file,
                    context={},
                    expected_outputs=[],
                    stage=stage,
                )

                call_args = mock_executor.execute_stage.call_args
                prompts[stage] = call_args.kwargs["system_prompt"]

            # All prompts should be different
            unique_prompts = set(prompts.values())
            assert len(unique_prompts) == len(WorkflowGenerationStage)

            # All should mention security analyst
            for prompt in prompts.values():
                assert "Expert Cyber Security Analyst" in prompt
        finally:
            workspace.cleanup()
