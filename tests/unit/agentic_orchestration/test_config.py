"""Tests for agentic_orchestration config module."""

import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from analysi.agentic_orchestration.config import (
    create_eval_executor,
    create_executor,
    get_agent_path,
    get_mcp_servers,
)


class TestGetMCPServers:
    """Tests for get_mcp_servers environment-aware configuration."""

    def test_get_mcp_servers_uses_defaults_when_no_env(self):
        """Verify default values when environment variables not set."""
        with patch.dict(os.environ, {}, clear=True):
            servers = get_mcp_servers(tenant_id="test-tenant")

            assert servers == {
                "analysi": {
                    "type": "http",
                    "url": "http://api:8000/v1/test-tenant/mcp/",
                },
            }

    def test_get_mcp_servers_uses_env_variables(self):
        """Verify environment variable override for host and port."""
        with patch.dict(
            os.environ,
            {
                "BACKEND_API_HOST": "localhost",
                "BACKEND_API_PORT": "8001",
                "ANALYSI_SYSTEM_API_KEY": "",
            },
        ):
            servers = get_mcp_servers(tenant_id="test-tenant")

            assert servers == {
                "analysi": {
                    "type": "http",
                    "url": "http://localhost:8001/v1/test-tenant/mcp/",
                },
            }

    def test_get_mcp_servers_explicit_params_override_env(self):
        """Verify explicit parameters override environment variables."""
        with patch.dict(
            os.environ,
            {
                "BACKEND_API_HOST": "localhost",
                "BACKEND_API_PORT": "8001",
                "ANALYSI_SYSTEM_API_KEY": "",
            },
        ):
            servers = get_mcp_servers(
                tenant_id="test-tenant",
                api_host="custom-host",
                api_port=9000,
            )

            assert servers == {
                "analysi": {
                    "type": "http",
                    "url": "http://custom-host:9000/v1/test-tenant/mcp/",
                },
            }

    def test_get_mcp_servers_docker_configuration(self):
        """Verify Docker environment configuration."""
        with patch.dict(
            os.environ, {"BACKEND_API_HOST": "api", "BACKEND_API_PORT": "8000"}
        ):
            servers = get_mcp_servers(tenant_id="acme")

            assert servers["analysi"]["url"] == "http://api:8000/v1/acme/mcp/"

    def test_get_mcp_servers_local_test_configuration(self):
        """Verify local test environment configuration."""
        with patch.dict(
            os.environ, {"BACKEND_API_HOST": "localhost", "BACKEND_API_PORT": "8001"}
        ):
            servers = get_mcp_servers(tenant_id="test-tenant")

            assert (
                servers["analysi"]["url"] == "http://localhost:8001/v1/test-tenant/mcp/"
            )

    def test_get_mcp_servers_includes_single_server(self):
        """Verify unified analysi server is the only MCP server."""
        servers = get_mcp_servers(tenant_id="test-tenant")

        assert "analysi" in servers
        assert len(servers) == 1

    def test_get_mcp_servers_tenant_id_in_url_path(self):
        """Verify tenant ID is correctly placed in URL path."""
        servers = get_mcp_servers(tenant_id="my-tenant-123")

        for server_config in servers.values():
            assert "/v1/my-tenant-123/" in server_config["url"]

    def test_get_mcp_servers_http_type(self):
        """Verify all servers have HTTP type."""
        servers = get_mcp_servers(tenant_id="test-tenant")

        for server_config in servers.values():
            assert server_config["type"] == "http"


class TestGetAgentPath:
    """Tests for get_agent_path agent file resolution."""

    def test_get_agent_path_finds_agent_in_first_directory(self, tmp_path):
        """Verify agent found in first configured directory."""
        # Setup: Create agent file in temp directory
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        agent_file = agent_dir / "test-agent.md"
        agent_file.write_text("# Test Agent")

        # Test
        with patch(
            "analysi.agentic_orchestration.config.get_agent_dirs",
            return_value=[agent_dir],
        ):
            result = get_agent_path("test-agent.md")

        # Verify
        assert result == agent_file
        assert result.exists()

    def test_get_agent_path_searches_multiple_directories(self, tmp_path):
        """Verify agent resolution searches all configured directories."""
        # Setup: Create multiple directories, agent in second one
        dir1 = tmp_path / "agents1"
        dir2 = tmp_path / "agents2"
        dir1.mkdir()
        dir2.mkdir()

        agent_file = dir2 / "test-agent.md"
        agent_file.write_text("# Test Agent")

        # Test: Agent should be found in dir2
        with patch(
            "analysi.agentic_orchestration.config.get_agent_dirs",
            return_value=[dir1, dir2],
        ):
            result = get_agent_path("test-agent.md")

        # Verify
        assert result == agent_file
        assert result.exists()

    def test_get_agent_path_raises_clear_error_when_not_found(self, tmp_path):
        """CRITICAL: Verify clear error message when agent file is missing."""
        # Setup: Create directories but no agent file
        dir1 = tmp_path / "agents1"
        dir2 = tmp_path / "agents2"
        dir1.mkdir()
        dir2.mkdir()

        # Test: Should raise FileNotFoundError with clear message
        with patch(
            "analysi.agentic_orchestration.config.get_agent_dirs",
            return_value=[dir1, dir2],
        ):
            with pytest.raises(FileNotFoundError) as exc_info:
                get_agent_path("missing-agent.md")

        # Verify error message is clear and shows searched directories
        error_message = str(exc_info.value)
        assert "missing-agent.md" in error_message, (
            "Error should mention the agent name"
        )
        assert "not found" in error_message, "Error should clearly state 'not found'"
        assert str(dir1) in error_message, "Error should show first searched directory"
        assert str(dir2) in error_message, "Error should show second searched directory"

    def test_get_agent_path_error_message_format(self, tmp_path):
        """Verify error message format is helpful for troubleshooting."""
        # Setup
        dir1 = tmp_path / "local_agents"
        dir2 = tmp_path / "packaged_agents"
        dir1.mkdir()
        dir2.mkdir()

        # Test
        with patch(
            "analysi.agentic_orchestration.config.get_agent_dirs",
            return_value=[dir1, dir2],
        ):
            with pytest.raises(FileNotFoundError) as exc_info:
                get_agent_path("runbook-match-agent.md")

        # Verify error message includes:
        # 1. Agent name
        # 2. "not found in:" prefix
        # 3. All searched directories separated by commas
        error_message = str(exc_info.value)
        expected_pattern = (
            f"Agent 'runbook-match-agent.md' not found in: {dir1}, {dir2}"
        )
        assert error_message == expected_pattern, (
            f"Error message should match expected format.\n"
            f"Expected: {expected_pattern}\n"
            f"Got: {error_message}"
        )

    def test_get_agent_path_prefers_first_directory_when_agent_in_multiple(
        self, tmp_path
    ):
        """Verify first directory takes precedence when agent exists in multiple places."""
        # Setup: Create agent in both directories
        dir1 = tmp_path / "local"
        dir2 = tmp_path / "packaged"
        dir1.mkdir()
        dir2.mkdir()

        agent1 = dir1 / "test-agent.md"
        agent2 = dir2 / "test-agent.md"
        agent1.write_text("# Local Agent")
        agent2.write_text("# Packaged Agent")

        # Test: Should return agent from first directory
        with patch(
            "analysi.agentic_orchestration.config.get_agent_dirs",
            return_value=[dir1, dir2],
        ):
            result = get_agent_path("test-agent.md")

        # Verify: Returns the first one (local takes precedence)
        assert result == agent1
        assert result.read_text() == "# Local Agent"


class TestExecutorFactoryIsolation:
    """Guard against setting_sources scope creep.

    The SDK loads CLAUDE.md files based on setting_sources. Including
    "user" loads ~/.claude/CLAUDE.md (personal dev config) and the
    project root's CLAUDE.md — both waste tokens and pollute agent
    behaviour.  Executors must use setting_sources=["project"] so
    they only read from the workspace .claude/ directory.
    """

    def test_create_executor_uses_project_only_setting_sources(self):
        """create_executor must set setting_sources=["project"]."""
        executor = create_executor(
            tenant_id="test",
            api_key="sk-test-key",
        )
        assert executor.setting_sources == ["project"], (
            f"create_executor must use setting_sources=['project'] to avoid "
            f"loading local CLAUDE.md files. Got: {executor.setting_sources}"
        )

    def test_create_eval_executor_uses_project_only_setting_sources(self, tmp_path):
        """create_eval_executor must set setting_sources=["project"]."""
        executor = create_eval_executor(
            api_key="sk-test-key",
            isolated_project_dir=tmp_path,
        )
        assert executor.setting_sources == ["project"], (
            f"create_eval_executor must use setting_sources=['project'] to avoid "
            f"loading local CLAUDE.md files. Got: {executor.setting_sources}"
        )

    def test_create_executor_never_includes_user_setting_source(self):
        """Executors must never include 'user' in setting_sources.

        'user' causes the SDK to load ~/.claude/CLAUDE.md which contains
        personal dev instructions unrelated to agent execution.
        """
        executor = create_executor(
            tenant_id="test",
            api_key="sk-test-key",
        )
        assert "user" not in executor.setting_sources, (
            "setting_sources must not include 'user' — this loads ~/.claude/CLAUDE.md "
            "which wastes ~4K tokens per call and pollutes agent behaviour"
        )

    def test_create_eval_executor_sets_isolated_project_dir(self, tmp_path):
        """Eval executor must forward isolated_project_dir to the SDK."""
        executor = create_eval_executor(
            api_key="sk-test-key",
            isolated_project_dir=tmp_path,
        )
        assert executor.isolated_project_dir == tmp_path

    def test_no_direct_executor_instantiation_in_production_jobs(self):
        """Production job files must use create_executor, not AgentOrchestrationExecutor directly.

        Scans job .py files for direct AgentOrchestrationExecutor() calls.
        If this test fails, a new job is bypassing the factory and risks
        loading local CLAUDE.md files into agent execution.
        """
        jobs_dir = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "analysi"
            / "agentic_orchestration"
            / "jobs"
        )

        violations = []
        for py_file in jobs_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            source = py_file.read_text()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "AgentOrchestrationExecutor"
                ) or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "AgentOrchestrationExecutor"
                ):
                    violations.append(f"{py_file.name}:{node.lineno}")

        assert not violations, (
            f"Direct AgentOrchestrationExecutor() calls found in job files: "
            f"{violations}. Use create_executor() instead to ensure proper "
            f"setting_sources isolation."
        )
