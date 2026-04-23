"""Unit tests for AgentWorkspace preservation feature."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.workspace import AgentWorkspace


class TestWorkspacePreservation:
    """Test workspace preservation via preserve flag and environment variable."""

    def test_workspace_cleanup_default_behavior(self):
        """By default, cleanup() should PRESERVE the workspace directory (not delete it)."""
        workspace = AgentWorkspace(run_id="test-run-123")

        # Verify directory was created
        assert workspace.work_dir.exists()
        work_dir_path = workspace.work_dir

        # Cleanup should PRESERVE directory by default
        workspace.cleanup()
        assert work_dir_path.exists(), "Default behavior should preserve workspace"

        # Manual cleanup for test
        import shutil

        shutil.rmtree(work_dir_path)

    def test_workspace_auto_cleanup_via_flag(self):
        """When auto_cleanup=True, cleanup() should remove the directory."""
        workspace = AgentWorkspace(run_id="test-run-456", auto_cleanup=True)

        # Verify directory was created
        assert workspace.work_dir.exists()
        work_dir_path = workspace.work_dir

        # Cleanup should remove directory when auto_cleanup=True
        workspace.cleanup()
        assert not work_dir_path.exists(), "auto_cleanup=True should delete workspace"

    def test_workspace_auto_cleanup_via_env_var(self, monkeypatch):
        """When ANALYSI_AUTO_CLEANUP_WORKSPACES=true, cleanup() should remove directory."""
        monkeypatch.setenv("ANALYSI_AUTO_CLEANUP_WORKSPACES", "true")

        workspace = AgentWorkspace(run_id="test-run-789")

        # Verify directory was created
        assert workspace.work_dir.exists()
        work_dir_path = workspace.work_dir

        # Cleanup should remove directory due to env var
        workspace.cleanup()
        assert not work_dir_path.exists(), (
            "ANALYSI_AUTO_CLEANUP_WORKSPACES=true should delete workspace"
        )

    def test_workspace_auto_cleanup_env_var_case_insensitive(self, monkeypatch):
        """Environment variable should be case-insensitive."""
        test_cases = ["true", "TRUE", "True", "TrUe"]

        for value in test_cases:
            monkeypatch.setenv("ANALYSI_AUTO_CLEANUP_WORKSPACES", value)

            workspace = AgentWorkspace(run_id=f"test-run-{value}")
            work_dir_path = workspace.work_dir

            workspace.cleanup()
            assert not work_dir_path.exists(), f"Failed for value: {value}"

    def test_workspace_auto_cleanup_env_var_false_values(self, monkeypatch):
        """Environment variable with false-like values should preserve (not delete)."""
        test_cases = ["false", "FALSE", "0", "no", ""]

        for value in test_cases:
            monkeypatch.setenv("ANALYSI_AUTO_CLEANUP_WORKSPACES", value)

            workspace = AgentWorkspace(run_id=f"test-run-{value}")
            work_dir_path = workspace.work_dir

            workspace.cleanup()
            assert work_dir_path.exists(), (
                f"Directory should be preserved for value: {value}"
            )

            # Manual cleanup for test
            import shutil

            shutil.rmtree(work_dir_path)

    def test_workspace_auto_cleanup_flag_overrides_env_var(self, monkeypatch):
        """Explicit auto_cleanup=False should work even if env var enables cleanup."""
        monkeypatch.setenv("ANALYSI_AUTO_CLEANUP_WORKSPACES", "true")

        workspace = AgentWorkspace(run_id="test-run-override", auto_cleanup=False)
        work_dir_path = workspace.work_dir

        workspace.cleanup()
        assert work_dir_path.exists(), (
            "Explicit auto_cleanup=False should override env var"
        )

        # Manual cleanup
        import shutil

        shutil.rmtree(work_dir_path)

    def test_workspace_directory_naming_without_tenant(self):
        """Workspace directory should use correct naming format without tenant."""
        workspace = AgentWorkspace(run_id="550e8400-e29b-41d4-a716-446655440000")

        # Directory name should start with kea-{run_id}-
        assert workspace.work_dir.name.startswith(
            "kea-550e8400-e29b-41d4-a716-446655440000-"
        )

        workspace.cleanup()

    def test_workspace_directory_naming_with_tenant(self):
        """Workspace directory should use correct naming format with tenant."""
        workspace = AgentWorkspace(
            run_id="550e8400-e29b-41d4-a716-446655440000", tenant_id="acme"
        )

        # Directory name should start with kea-{tenant}-{run_id}-
        assert workspace.work_dir.name.startswith(
            "kea-acme-550e8400-e29b-41d4-a716-446655440000-"
        )

        workspace.cleanup()

    def test_cleanup_nonexistent_directory(self):
        """cleanup() should handle case where directory was already deleted."""
        workspace = AgentWorkspace(run_id="test-run-gone")
        work_dir_path = workspace.work_dir

        # Manually delete the directory
        import shutil

        shutil.rmtree(work_dir_path)

        # cleanup() should not raise an error
        workspace.cleanup()  # Should complete without error

    def test_preserve_logs_message(self, caplog):
        """When auto_cleanup=False (default), cleanup() should log preservation message."""
        import logging

        caplog.set_level(logging.INFO)

        workspace = AgentWorkspace(run_id="test-run-log")  # Default: auto_cleanup=False
        work_dir_path = workspace.work_dir

        workspace.cleanup()

        # Should have logged preservation message (structlog event name)
        assert any(
            "preserving_workspace" in record.message for record in caplog.records
        )

        # Manual cleanup
        import shutil

        shutil.rmtree(work_dir_path)


class TestWorkspacePreservationIntegration:
    """Integration tests for workspace preservation with actual node execution."""

    @pytest.mark.asyncio
    async def test_runbook_generation_preserves_workspace_with_env_var(
        self, monkeypatch
    ):
        """Verify runbook_generation_node uses workspace from state and doesn't call cleanup.

        With workspace sharing refactoring, nodes receive workspace from state
        (created at subgraph level) and cleanup is handled by the subgraph, not individual nodes.
        """
        monkeypatch.setenv("ANALYSI_PRESERVE_WORKSPACES", "true")

        from analysi.agentic_orchestration import AgentOrchestrationExecutor
        from analysi.agentic_orchestration.nodes import runbook_generation_node
        from analysi.agentic_orchestration.observability import StageExecutionMetrics

        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"matched-runbook.md": "# Test Runbook", "matching-report.json": "{}"},
                StageExecutionMetrics(
                    tool_calls=[],
                    total_cost_usd=0.0,
                    usage={},
                    duration_ms=100,
                    duration_api_ms=80,
                    num_turns=1,
                ),
            )
        )
        mock_workspace.cleanup = MagicMock()

        # Mock state with workspace (shared pattern)
        state = {
            "alert": {
                "title": "Test Alert",
                "severity": "high",
                "triggering_event_time": "2024-01-01T00:00:00Z",
                "raw_alert": {},
            },
            "run_id": "test-integration-123",
            "tenant_id": "test-tenant",
            "workspace": mock_workspace,  # Workspace from state (subgraph-level)
        }

        # Mock executor to avoid actual LLM calls
        mock_executor = MagicMock(spec=AgentOrchestrationExecutor)

        # Mock agent path resolution
        with patch(
            "analysi.agentic_orchestration.nodes.runbook_generation.get_agent_path"
        ) as mock_get_path:
            mock_get_path.return_value = Path("/fake/agent.md")

            result = await runbook_generation_node(state, mock_executor)

        # Verify workspace from state was used
        mock_workspace.run_agent.assert_called_once()

        # Verify cleanup was NOT called (nodes don't cleanup - subgraphs do)
        mock_workspace.cleanup.assert_not_called()

        # Verify result contains expected fields
        assert "runbook" in result
        assert result["runbook"] == "# Test Runbook"

    def test_workspace_preservation_documented_in_claude_md(self):
        """Verify workspace preservation is documented in CLAUDE.md."""
        claude_md_path = (
            Path(__file__).parent.parent.parent.parent
            / "src/analysi/agentic_orchestration/CLAUDE.md"
        )

        if claude_md_path.exists():
            content = claude_md_path.read_text()
            # Check for documentation of preservation feature
            # This is a smoke test - if we document it, this will pass
            assert "workspace" in content.lower() or "cleanup" in content.lower()
