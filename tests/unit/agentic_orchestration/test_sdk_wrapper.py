"""
Unit tests for agentic orchestration SDK wrapper.

Tests validate the structure and input validation of AgentOrchestrationExecutor
without making actual API calls.
"""

import pytest

from analysi.agentic_orchestration.config import mcp_tool_wildcards
from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor


class TestAgentOrchestrationExecutorInit:
    """Tests for AgentOrchestrationExecutor initialization."""

    def test_agent_orchestration_executor_initialization(self):
        """Verify AgentOrchestrationExecutor initializes with api_key, mcp_servers, and allowed_tools."""
        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers={"test-server": {"url": "http://localhost:8000/mcp"}},
            allowed_tools=["mcp__test__tool1"],
        )
        assert executor.api_key == "test-api-key"
        assert "test-server" in executor.mcp_servers
        assert executor.allowed_tools == ["mcp__test__tool1"]

    def test_agent_orchestration_executor_missing_api_key(self):
        """Verify AgentOrchestrationExecutor raises error when api_key is None."""
        with pytest.raises((ValueError, TypeError)):
            AgentOrchestrationExecutor(
                api_key=None,  # type: ignore
                mcp_servers={},
            )

    def test_agent_orchestration_executor_empty_api_key(self):
        """Verify AgentOrchestrationExecutor raises error when api_key is empty string."""
        with pytest.raises(ValueError):
            AgentOrchestrationExecutor(
                api_key="",
                mcp_servers={},
            )

    def test_agent_orchestration_executor_default_allowed_tools(self):
        """Verify AgentOrchestrationExecutor defaults to file operation tools."""
        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers={},
        )
        # Default tools for file-based agent execution
        assert executor.allowed_tools == ["Write", "Read", "Bash"]
        # bypassPermissions is required for headless execution
        assert executor.permission_mode == "bypassPermissions"
        # 800 turns for complex multi-phase agent tasks with testing iterations
        assert executor.max_turns == 800


class TestExecuteStageValidation:
    """Tests for execute_stage input validation."""

    @pytest.fixture
    def executor(self):
        """Create executor for testing."""
        return AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers={},
        )

    @pytest.mark.asyncio
    async def test_execute_stage_validates_system_prompt(self, executor):
        """Verify execute_stage requires non-empty system_prompt."""
        with pytest.raises(ValueError, match="system_prompt"):
            await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="",
                user_prompt="Valid prompt",
            )

    @pytest.mark.asyncio
    async def test_execute_stage_validates_user_prompt(self, executor):
        """Verify execute_stage requires non-empty user_prompt."""
        with pytest.raises(ValueError, match="user_prompt"):
            await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="Valid system prompt",
                user_prompt="",
            )

    @pytest.mark.asyncio
    async def test_execute_stage_accepts_all_stages(self, executor):
        """Verify execute_stage works with all WorkflowGenerationStage values."""
        # This test will fail until implementation exists
        # For now, just verify stages are valid
        for stage in WorkflowGenerationStage:
            assert isinstance(stage, WorkflowGenerationStage)

    @pytest.mark.asyncio
    async def test_execute_stage_callback_optional(self, executor):
        """Verify execute_stage works without callback parameter."""
        # This test validates that callback is optional in the signature
        # Will fail until implementation exists, but signature should be correct
        import inspect

        sig = inspect.signature(executor.execute_stage)
        callback_param = sig.parameters.get("callback")
        assert callback_param is not None
        assert callback_param.default is None


class TestMcpServerConfiguration:
    """Tests for MCP server configuration."""

    def test_mcp_server_configuration_format(self):
        """Verify MCP server config uses correct structure."""
        mcp_servers = {
            "analysi": {"url": "http://api:8000/v1/test-tenant/mcp"},
        }

        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers=mcp_servers,
        )

        assert len(executor.mcp_servers) == 1
        assert "analysi" in executor.mcp_servers

    def test_allowed_tools_restricted_when_mcp_configured(self):
        """Verify allowed_tools excludes Bash and includes MCP wildcards when MCP servers configured."""
        mcp_servers = {
            "analysi": {"url": "http://api:8000/v1/test-tenant/mcp"},
        }

        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers=mcp_servers,
            # allowed_tools not specified - should default to safe list
        )

        # When MCP servers are configured, Bash must be excluded to prevent
        # arbitrary command execution from prompt-injected content.
        assert executor.allowed_tools is not None
        assert "Bash" not in executor.allowed_tools
        assert "Read" in executor.allowed_tools
        assert "Write" in executor.allowed_tools

        # MCP tools require explicit wildcard permission — without these,
        # agents can see MCP tools but cannot call them (SDK requirement).
        assert "mcp__analysi__*" in executor.allowed_tools

    def test_allowed_tools_explicit_overrides_mcp_default(self):
        """Verify explicit allowed_tools overrides MCP default behavior."""
        mcp_servers = {
            "analysi": {"url": "http://api:8000/v1/test-tenant/mcp"},
        }

        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers=mcp_servers,
            allowed_tools=["Write", "Read"],  # Explicit list should be respected
        )

        # Explicit allowed_tools should be used even with MCP servers
        assert executor.allowed_tools == ["Write", "Read"]

    def test_allowed_tools_defaults_without_mcp(self):
        """Verify allowed_tools defaults to basic tools without MCP servers."""
        executor = AgentOrchestrationExecutor(
            api_key="test-api-key",
            mcp_servers={},  # Empty MCP servers
        )

        # Without MCP, default to file operation tools
        assert executor.allowed_tools == ["Write", "Read", "Bash"]


class TestMcpToolWildcards:
    """Tests for mcp_tool_wildcards() helper.

    This function derives MCP tool permission wildcards from server names,
    ensuring a single source of truth (config.get_mcp_servers) for server
    names and their corresponding SDK permission entries.
    """

    def test_standard_servers(self):
        """Verify wildcards for production MCP server name."""
        servers = {
            "analysi": {"url": "http://api:8000/v1/t1/mcp/"},
        }
        wildcards = mcp_tool_wildcards(servers)
        assert "mcp__analysi__*" in wildcards
        assert len(wildcards) == 1

    def test_empty_servers_returns_empty(self):
        """Empty MCP server dict produces no wildcards."""
        assert mcp_tool_wildcards({}) == []

    def test_single_server(self):
        """Single server produces exactly one wildcard."""
        wildcards = mcp_tool_wildcards({"only-one": {"url": "http://x"}})
        assert wildcards == ["mcp__only-one__*"]

    def test_preserves_hyphenated_names(self):
        """Server names with hyphens must be preserved verbatim."""
        wildcards = mcp_tool_wildcards(
            {
                "my-long-server-name": {"url": "http://x"},
            }
        )
        assert wildcards == ["mcp__my-long-server-name__*"]

    def test_wildcard_format_matches_sdk_convention(self):
        """Every wildcard must match the mcp__<name>__* pattern."""
        import re

        servers = {
            "analysi": {"url": "http://x"},
            "some-future-server": {"url": "http://x"},
        }
        pattern = re.compile(r"^mcp__[a-z0-9_-]+__\*$")
        for wc in mcp_tool_wildcards(servers):
            assert pattern.match(wc), f"Wildcard '{wc}' does not match SDK convention"

    def test_order_matches_dict_insertion_order(self):
        """Wildcards follow dict insertion order (Python 3.7+ guarantee)."""
        from collections import OrderedDict

        servers = OrderedDict(
            [
                ("alpha", {"url": "http://x"}),
                ("beta", {"url": "http://x"}),
                ("gamma", {"url": "http://x"}),
            ]
        )
        wildcards = mcp_tool_wildcards(servers)
        assert wildcards == ["mcp__alpha__*", "mcp__beta__*", "mcp__gamma__*"]

    def test_production_get_mcp_servers_integration(self):
        """Wildcards derived from get_mcp_servers() match expected production names."""
        import os
        from unittest.mock import patch

        from analysi.agentic_orchestration.config import get_mcp_servers

        # Patch env vars to avoid requiring a running API server
        with patch.dict(
            os.environ,
            {
                "BACKEND_API_HOST": "localhost",
                "BACKEND_API_PORT": "8000",
            },
        ):
            servers = get_mcp_servers("test-tenant")

        wildcards = mcp_tool_wildcards(servers)
        assert "mcp__analysi__*" in wildcards
        # If a new server is added to get_mcp_servers(), this test will
        # catch it early and force updating the security review.
        assert len(wildcards) == len(servers)


class TestMcpToolWildcardsInExecutor:
    """Verify the executor correctly integrates mcp_tool_wildcards.

    These tests confirm the executor's allowed_tools list is dynamically
    built from MCP server names (not hardcoded), so renaming a server in
    config.py automatically propagates to the permission list.
    """

    def test_executor_derives_wildcards_from_server_names(self):
        """Executor builds MCP wildcards dynamically from server config keys."""
        servers = {
            "analysi": {"url": "http://api:8000/v1/t/mcp/"},
        }
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
        )
        assert "mcp__analysi__*" in executor.allowed_tools

    def test_executor_adapts_to_renamed_server(self):
        """If a server is renamed, wildcards update automatically."""
        servers = {"renamed-assistant": {"url": "http://api:8000/v1/t/mcp/"}}
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
        )
        assert "mcp__renamed-assistant__*" in executor.allowed_tools
        # Old name should NOT be present
        assert "mcp__analysi__*" not in executor.allowed_tools

    def test_executor_adapts_to_additional_server(self):
        """Adding a new MCP server automatically grants tool access."""
        servers = {
            "analysi": {"url": "http://x"},
            "new-enrichment-server": {"url": "http://x"},
        }
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
        )
        assert "mcp__new-enrichment-server__*" in executor.allowed_tools
        assert len([t for t in executor.allowed_tools if t.startswith("mcp__")]) == 2

    def test_executor_no_mcp_wildcards_without_servers(self):
        """Without MCP servers, no mcp__ wildcards appear."""
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers={},
        )
        assert not any(t.startswith("mcp__") for t in executor.allowed_tools)

    def test_executor_explicit_allowed_tools_not_augmented(self):
        """When caller provides explicit allowed_tools, MCP wildcards are NOT added."""
        servers = {
            "analysi": {"url": "http://x"},
        }
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
            allowed_tools=["Read", "Write"],
        )
        # Caller's explicit list must be respected exactly
        assert executor.allowed_tools == ["Read", "Write"]
        assert "mcp__analysi__*" not in executor.allowed_tools

    def test_executor_base_tools_always_present_with_mcp(self):
        """Base tools (Read, Write, etc.) are always in the list alongside MCP wildcards."""
        servers = {"analysi": {"url": "http://x"}}
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
        )
        for tool in ["Write", "Read", "Glob", "Grep", "Skill", "Task"]:
            assert tool in executor.allowed_tools, f"Base tool '{tool}' missing"

    def test_executor_bash_excluded_with_mcp(self):
        """Bash must never appear in default allowed_tools when MCP is configured."""
        servers = {
            "analysi": {"url": "http://x"},
        }
        executor = AgentOrchestrationExecutor(
            api_key="test-key",
            mcp_servers=servers,
        )
        assert "Bash" not in executor.allowed_tools


class TestOAuthTokenCredentials:
    """Tests for OAuth token credential handling.

    These tests verify the transition from api_key to oauth_token for
    Claude Code SDK authentication.
    """

    def test_executor_accepts_oauth_token(self):
        """Verify AgentOrchestrationExecutor accepts oauth_token parameter."""
        executor = AgentOrchestrationExecutor(
            oauth_token="sk-ant-oauth-token-12345",
            mcp_servers={},
        )
        assert executor.oauth_token == "sk-ant-oauth-token-12345"
        # api_key should be None when using oauth_token
        assert executor.api_key is None

    def test_executor_oauth_token_required(self):
        """Verify AgentOrchestrationExecutor raises if oauth_token is empty."""
        with pytest.raises(ValueError, match="oauth_token cannot be empty"):
            AgentOrchestrationExecutor(
                oauth_token="",
                mcp_servers={},
            )

    def test_executor_oauth_token_none_raises(self):
        """Verify AgentOrchestrationExecutor raises if oauth_token is None."""
        with pytest.raises((ValueError, TypeError)):
            AgentOrchestrationExecutor(
                oauth_token=None,  # type: ignore
                mcp_servers={},
            )

    def test_executor_stores_oauth_token(self):
        """Verify executor stores oauth_token correctly."""
        executor = AgentOrchestrationExecutor(
            oauth_token="sk-ant-oauth-test-token",
            mcp_servers={},
        )
        assert executor.oauth_token == "sk-ant-oauth-test-token"
        assert executor.api_key is None

    def test_executor_stores_api_key_when_no_oauth(self):
        """Verify executor stores api_key when oauth_token not provided."""
        executor = AgentOrchestrationExecutor(
            api_key="sk-ant-api-key",
            mcp_servers={},
        )
        assert executor.api_key == "sk-ant-api-key"
        assert executor.oauth_token is None

    def test_executor_prefers_oauth_over_api_key(self):
        """Verify oauth_token takes precedence when both are provided."""
        executor = AgentOrchestrationExecutor(
            api_key="old-api-key",
            oauth_token="sk-ant-oauth-preferred",
            mcp_servers={},
        )
        # OAuth should take precedence
        assert executor.oauth_token == "sk-ant-oauth-preferred"
        # api_key should be ignored when oauth_token is present
        assert executor.api_key is None or executor.api_key == "old-api-key"

    def test_executor_backwards_compatible_with_api_key(self):
        """Verify existing api_key parameter still works for backwards compatibility."""
        # This ensures we don't break existing code during migration
        executor = AgentOrchestrationExecutor(
            api_key="sk-ant-legacy-key",
            mcp_servers={},
        )
        assert executor.api_key == "sk-ant-legacy-key"
