"""
Claude Agent SDK query wrapper with observability.

This module provides a wrapper around the Claude Agent SDK's query() function
that standardizes how we call it with system/user prompts and captures
execution metrics for observability.
"""

from pathlib import Path
from typing import Any, Literal

from analysi.config.logging import get_logger

from .observability import (
    ProgressCallback,
    StageExecutionMetrics,
    ToolCallTrace,
    WorkflowGenerationStage,
)

# ---------------------------------------------------------------------------
# Patch claude_agent_sdk to handle rate_limit_event messages gracefully.
#
# Claude Code sends a `rate_limit_event` JSON message when it hits API rate
# limits. The SDK's message_parser raises MessageParseError for any unrecognised
# message type, which terminates the async generator and kills the whole
# workflow generation run.
#
# Fix: intercept rate_limit_event before parse_message sees it and convert it
# to a SystemMessage. Our execute_stage loop already silently ignores
# SystemMessage (no elif branch), so the loop continues uninterrupted while
# Claude Code handles the backoff internally.
# ---------------------------------------------------------------------------
_patch_logger = get_logger(__name__)

try:
    from claude_agent_sdk._internal import client as _sdk_internal_client
    from claude_agent_sdk._internal import message_parser as _sdk_mp
    from claude_agent_sdk.types import SystemMessage as _SystemMessage

    if not hasattr(_sdk_mp.parse_message, "_rate_limit_patched"):
        _original_parse_message = _sdk_mp.parse_message

        def _patched_parse_message(data: dict) -> object:  # type: ignore[type-arg]
            if isinstance(data, dict) and data.get("type") == "rate_limit_event":
                retry_ms = data.get("retry_after_ms", "unknown")
                _patch_logger.warning(
                    "claude_code_rate_limit_event_received",
                    retry_after_ms=retry_ms,
                )
                return _SystemMessage(subtype="rate_limit_event", data=data)
            return _original_parse_message(data)

        _patched_parse_message._rate_limit_patched = True  # type: ignore[attr-defined]

        # Patch the module attribute (for future imports via the module)
        _sdk_mp.parse_message = _patched_parse_message  # type: ignore[assignment]

        # CRITICAL: Also patch the locally-bound name in _internal/client.py.
        # InternalClient.process_query() calls parse_message via a module-level
        # `from .message_parser import parse_message` (line 13), which creates a
        # local binding that is NOT affected by patching the module attribute above.
        # Without this second patch, rate_limit_event still crashes with
        # MessageParseError("Unknown message type: rate_limit_event").
        _sdk_internal_client.parse_message = _patched_parse_message  # type: ignore[attr-defined,assignment]

        _patch_logger.debug(
            "claude_agent_sdk patched: rate_limit_event → SystemMessage"
        )

except ImportError:
    pass  # SDK not installed — no patch needed


class AgentOrchestrationExecutor:
    """Wrapper for Claude Agent SDK query() calls with observability.

    This executor provides a standardized interface for executing workflow
    generation stages via the Claude Agent SDK. It captures execution metrics
    and supports progress callbacks for real-time monitoring.

    Example:
        executor = AgentOrchestrationExecutor(
            api_key="...",
            mcp_servers={
                "analysi": {"url": "http://api:8000/v1/tenant/mcp"}
            },
        )

        result, metrics = await executor.execute_stage(
            stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            system_prompt="You are an expert security analyst...",
            user_prompt="Analyze this alert and generate a runbook...",
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        permission_mode: Literal[
            "default", "acceptEdits", "plan", "bypassPermissions"
        ] = "bypassPermissions",
        setting_sources: list[Literal["user", "project", "local"]] | None = None,
        max_turns: int = 800,
        isolated_project_dir: Path | None = None,
        skills_project_dir: Path | None = None,
        oauth_token: str | None = None,
    ):
        """Initialize the executor.

        Args:
            api_key: Anthropic API key for Claude Agent SDK (deprecated, use oauth_token)
            mcp_servers: MCP server configurations (name -> config dict)
            allowed_tools: List of allowed tool names (default: Write, Read, Bash)
            permission_mode: Permission mode (default: bypassPermissions for headless execution)
            setting_sources: Settings sources to use (default: ["user", "project"] for skills + team settings)
            max_turns: Maximum conversation turns (default: 800 for complex task building with testing iterations)
            isolated_project_dir: Optional parent directory containing .claude/ for eval tests (prevents pollution)
            skills_project_dir: Optional directory containing synced skills at .claude/skills/.
                              When set, uses setting_sources=["project"] for tenant-isolated skills.
                              This is used by TenantSkillsSyncer for DB-backed skills.
            oauth_token: OAuth token from anthropic_agent integration (preferred over api_key).
                        When set, uses CLAUDE_CODE_OAUTH_TOKEN instead of ANTHROPIC_API_KEY.

        Raises:
            ValueError: If neither api_key nor oauth_token is provided or both are empty
        """
        # oauth_token takes precedence over api_key
        self.oauth_token: str | None = None
        self.api_key: str | None = None
        if oauth_token is not None:
            if not oauth_token:
                raise ValueError("oauth_token cannot be empty")
            self.oauth_token = oauth_token
        elif api_key is not None:
            if not api_key:
                raise ValueError("api_key cannot be empty")
            self.api_key = api_key
        else:
            raise TypeError("Either api_key or oauth_token must be provided")

        self.mcp_servers = mcp_servers or {}
        self.isolated_project_dir = isolated_project_dir
        self.skills_project_dir = skills_project_dir

        # SECURITY: Never set allowed_tools=None — that grants unrestricted
        # access (including Bash) which is exploitable via prompt injection
        # from attacker-influenced content (alerts, runbooks, task context).
        if mcp_servers and allowed_tools is None:
            # Allow file operations + Skill/Task but NOT Bash.
            # MCP tools REQUIRE explicit permission via wildcards — without
            # these entries agents can see MCP tools but cannot call them.
            # See: Claude Agent SDK docs on allowedTools + MCP permissions.
            from .config import mcp_tool_wildcards

            self.allowed_tools = [
                "Write",
                "Read",
                "Glob",
                "Grep",
                "Skill",
                "Task",
                *mcp_tool_wildcards(mcp_servers),
            ]
        else:
            self.allowed_tools = allowed_tools or ["Write", "Read", "Bash"]
        self.permission_mode = permission_mode

        # Default setting_sources based on project dir settings
        # Priority: skills_project_dir > isolated_project_dir > default
        _SettingSources = list[Literal["user", "project", "local"]]
        if setting_sources is None:
            if skills_project_dir is not None:
                # DB skills mode: Project first (DB-synced), user as fallback (global)
                # "project" = workspace/.claude/skills/ (synced from DB, tenant-isolated)
                # "user" = ~/.claude/skills/ (global fallback for skills not in DB)
                # DB skills take precedence; global skills remain accessible
                self.setting_sources: _SettingSources = ["project", "user"]
            elif isolated_project_dir is not None:
                # Isolated mode: Use ONLY project settings (from isolated_project_dir/.claude/)
                # Prevents loading from ~/.claude/skills/ which would cause pollution
                self.setting_sources = ["project"]
            else:
                # Normal mode: Use user + project settings
                # Include "user" to load Skills from ~/.claude/skills/
                # Include "project" to load CLAUDE.md and project settings
                self.setting_sources = ["user", "project"]
        else:
            self.setting_sources = setting_sources

        self.max_turns = max_turns

    async def execute_stage(  # noqa: C901
        self,
        stage: WorkflowGenerationStage,
        system_prompt: str,
        user_prompt: str,
        cwd: str | None = None,
        callback: ProgressCallback | None = None,
        context_id: str | None = None,
    ) -> tuple[str | None, StageExecutionMetrics]:
        """Execute a workflow generation stage via Agent SDK query().

        This method calls the Claude Agent SDK's query() function with the
        provided prompts and captures all execution metrics. Tool calls are
        tracked in real-time via streaming.

        Args:
            stage: The workflow generation stage being executed
            system_prompt: System prompt for the agent
            user_prompt: User prompt (can be agent .md file content)
            cwd: Working directory for file operations (CRITICAL for Write tool)
            callback: Optional progress callback for real-time notifications
            context_id: Optional context identifier for logs (e.g., "task0", "task1")
                       Appears in logs as [STAGE:context_id] for easier debugging

        Returns:
            Tuple of (result_text, metrics) from the execution

        Raises:
            ValueError: If system_prompt or user_prompt is empty
            RuntimeError: If the SDK query ends without a ResultMessage
        """
        if not system_prompt:
            raise ValueError("system_prompt cannot be empty")
        if not user_prompt:
            raise ValueError("user_prompt cannot be empty")

        # Build log prefix: [STAGE] or [STAGE:context_id]
        if context_id:
            log_prefix = f"[{stage.value.upper()}:{context_id}]"
        else:
            log_prefix = f"[{stage.value.upper()}]"

        # Import here to avoid import errors when SDK is not installed
        # This allows unit tests to run without the SDK
        try:
            import asyncio as _asyncio

            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                UserMessage,
                query,
            )
            from claude_agent_sdk.types import (
                SystemMessage,
                ToolResultBlock,
                ToolUseBlock,
            )
        except ImportError as e:
            raise ImportError(
                "claude_agent_sdk is required for execute_stage. "
                "Install with: pip install claude-agent-sdk"
            ) from e

        import os

        # Set authentication in environment for the SDK
        # oauth_token uses CLAUDE_CODE_OAUTH_TOKEN (preferred)
        # api_key uses ANTHROPIC_API_KEY (deprecated)
        if self.oauth_token:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = self.oauth_token
            # Clear ANTHROPIC_API_KEY to avoid confusion
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]
        elif self.api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.api_key

        tool_calls: list[ToolCallTrace] = []
        result_text: str | None = None

        # CRITICAL FIX: Override cwd when using project dir settings
        # The cwd parameter tells SDK where to find .claude/ directory (for skills) AND where to write output files
        # Priority: skills_project_dir > isolated_project_dir > cwd parameter
        #
        # skills_project_dir: For DB-backed skills synced by TenantSkillsSyncer
        # isolated_project_dir: For eval tests to prevent ~/.claude/ pollution
        effective_cwd: str | None
        if self.skills_project_dir:
            effective_cwd = str(self.skills_project_dir)
        elif self.isolated_project_dir:
            effective_cwd = str(self.isolated_project_dir)
        else:
            effective_cwd = cwd

        # Create options for the query
        # These options are critical for file-based agent execution:
        # - cwd: Working directory AND location of .claude/ directory (CRITICAL!)
        # - permission_mode: bypassPermissions for headless execution
        # - setting_sources: ["project"] to use only team-shared settings (isolated mode) or ["user", "project"] for normal mode
        # - allowed_tools: Restrict to file operations
        # - max_turns: Limit conversation turns
        # - mcp_servers: Tenant-aware MCP server configurations
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            cwd=effective_cwd,  # CRITICAL: Tells SDK where to find .claude/ and write files
            allowed_tools=self.allowed_tools,
            permission_mode=self.permission_mode,
            setting_sources=self.setting_sources,
            max_turns=self.max_turns,
            mcp_servers=self.mcp_servers,  # Enable MCP tools (unified analysi server)
        )

        # Track pending tool calls to correlate with results
        pending_tool_calls: dict[str, dict[str, Any]] = {}

        # Execute query with streaming
        # CRITICAL: The SDK uses anyio internally, but we run under asyncio.
        # This mismatch causes cancel scope errors during generator cleanup.
        # We catch these errors at the function boundary if we have a valid result.
        sdk_logger = get_logger(__name__)

        query_gen = query(prompt=user_prompt, options=options)
        result_to_return = None
        got_result = False

        try:
            async for message in query_gen:
                # Skip processing after we have result (don't break - causes cleanup error)
                if got_result:
                    continue
                # Check AssistantMessage for ToolUseBlock (tool invocations)
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            # Track tool call start
                            pending_tool_calls[block.id] = {
                                "name": block.name,
                                "input": block.input,
                            }
                            sdk_logger.info(
                                "tool_call",
                                prefix=log_prefix,
                                tool_name=block.name,
                                input_preview=str(block.input)[:200],
                            )

                            if callback:
                                await callback.on_tool_call(
                                    stage, block.name, block.input
                                )

                # Check UserMessage for ToolResultBlock (tool results)
                elif isinstance(message, UserMessage):
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                # Get the original tool call info
                                tool_info = pending_tool_calls.get(
                                    block.tool_use_id, {}
                                )
                                tool_name = tool_info.get("name", block.tool_use_id)

                                # Detect MCP tool access failures
                                if block.is_error and tool_name.startswith("mcp__"):
                                    sdk_logger.error(
                                        "mcp_tool_error",
                                        prefix=log_prefix,
                                        tool_name=tool_name,
                                        error_content=block.content,
                                        mcp_config=list(self.mcp_servers.keys())
                                        if self.mcp_servers
                                        else "NONE",
                                    )

                                trace = ToolCallTrace(
                                    tool_name=tool_name,
                                    input_args=tool_info.get("input", {}),
                                    result=block.content,
                                    is_error=block.is_error or False,
                                )
                                tool_calls.append(trace)
                                if callback:
                                    await callback.on_tool_result(
                                        stage,
                                        tool_name,
                                        block.content,
                                        block.is_error or False,
                                    )

                elif isinstance(message, SystemMessage):
                    # rate_limit_event is patched to SystemMessage at module load.
                    # Sleep for the requested backoff duration so we respect the
                    # rate limit before the SDK retries the API call.
                    if message.subtype == "rate_limit_event":
                        retry_ms = message.data.get("retry_after_ms", 0) or 0
                        retry_sec = retry_ms / 1000.0
                        sdk_logger.warning(
                            "claude_code_rate_limit_backoff",
                            prefix=log_prefix,
                            retry_seconds=round(retry_sec, 1),
                            retry_after_ms=retry_ms,
                        )
                        if retry_sec > 0:
                            await _asyncio.sleep(retry_sec)

                elif isinstance(message, ResultMessage):
                    # Final message with metrics
                    result_text = message.result

                    sdk_logger.info(
                        "sdk_query_completed",
                        prefix=log_prefix,
                        result_preview=result_text[:500] if result_text else None,
                    )
                    sdk_logger.info(
                        "sdk_query_cost",
                        prefix=log_prefix,
                        cost_usd=message.total_cost_usd,
                        usage=str(message.usage),
                    )
                    sdk_logger.info(
                        "sdk_tool_calls_count", prefix=log_prefix, count=len(tool_calls)
                    )

                    # Detect credit balance errors
                    if (
                        result_text
                        and "credit balance is too low" in result_text.lower()
                    ):
                        sdk_logger.error("credit_balance_exhausted", prefix=log_prefix)
                        raise RuntimeError(
                            "Anthropic API credit balance is too low to complete this request. "
                            "Please add credits to your Anthropic account and try again."
                        )

                    metrics = StageExecutionMetrics(
                        duration_ms=0,  # Not available in SDK
                        duration_api_ms=0,  # Not available in SDK
                        num_turns=len(tool_calls),  # Approximate from tool calls
                        total_cost_usd=message.total_cost_usd or 0.0,
                        usage=message.usage or {},
                        tool_calls=tool_calls,
                    )
                    # Store result and set flag - DON'T use break!
                    result_to_return = (result_text, metrics)
                    got_result = True

        except RuntimeError as e:
            # CRITICAL: Catch anyio cancel scope errors during generator cleanup.
            # The SDK uses anyio internally, but we run under asyncio. When the
            # async for loop ends, Python calls aclose() which can trigger:
            # "Attempted to exit cancel scope in a different task than it was entered in"
            # If we have a valid result, this error is harmless - ignore it.
            if result_to_return is not None and "cancel scope" in str(e).lower():
                sdk_logger.debug(
                    "cancel_scope_error_ignored", prefix=log_prefix, error=str(e)
                )
            else:
                raise

        # Check if we got a result
        if result_to_return is None:
            raise RuntimeError("Query ended without ResultMessage")

        return result_to_return
