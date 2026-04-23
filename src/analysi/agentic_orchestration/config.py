"""Configuration for agentic orchestration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from analysi.common.internal_auth import internal_auth_headers

if TYPE_CHECKING:
    from .sdk_wrapper import AgentOrchestrationExecutor


def get_workspace_auto_cleanup() -> bool:
    """Get workspace auto-cleanup policy from environment.

    Default behavior: Workspaces are preserved (not deleted automatically).
    - Eval/Testing: Fixtures call cleanup() explicitly when needed
    - Production: Set ANALYSI_AUTO_CLEANUP_WORKSPACES=true to enable auto-cleanup

    Returns:
        True if workspaces should be auto-cleaned, False to preserve them
    """
    return os.getenv("ANALYSI_AUTO_CLEANUP_WORKSPACES", "false").lower() == "true"


# Project root (works both in Docker and local dev)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Default agent directories in order of precedence
# In Docker: /app/agents (copied from agents/dist/ by Dockerfile)
# In local dev: {PROJECT_ROOT}/agents/dist (single source of truth)
DEFAULT_AGENT_DIRS = [
    Path("/app/agents"),  # Docker container
    PROJECT_ROOT / "agents" / "dist",  # Local dev
]

# NOTE: Skills are now DB-only. No filesystem skills directories.
# Skills are installed per-tenant via content packs (e.g., `analysi packs install foundation`)
# and accessed at runtime via DatabaseResourceStore. See docs/projects/delos.md.


def get_agent_dirs() -> list[Path]:
    """Get list of agent directories to search.

    Uses ANALYSI_ALERT_PROCESSING_AGENT_DIR env var if set (single directory),
    otherwise returns default directories.
    """
    if env_dir := os.environ.get("ANALYSI_ALERT_PROCESSING_AGENT_DIR"):
        return [Path(env_dir)]
    return DEFAULT_AGENT_DIRS


def get_agent_path(agent_name: str) -> Path:
    """Find agent .md file in configured directories.

    Args:
        agent_name: Name of agent file (e.g., "runbook-match-agent.md")

    Returns:
        Path to agent file

    Raises:
        FileNotFoundError: If agent not found in any directory
    """
    agent_dirs = get_agent_dirs()

    for agent_dir in agent_dirs:
        path = agent_dir / agent_name
        if path.exists():
            return path

    # Not found - return first directory path for error message
    searched = ", ".join(str(d) for d in agent_dirs)
    raise FileNotFoundError(f"Agent '{agent_name}' not found in: {searched}")


def get_mcp_servers(
    tenant_id: str,
    api_host: str | None = None,
    api_port: int | None = None,
    actor_user_id: UUID | str | None = None,
) -> dict[str, dict]:
    """Build MCP server configuration for Claude Agent SDK.

    Creates tenant-aware MCP server URL for the unified analysi server.

    Auto-detects environment from BACKEND_API_HOST and BACKEND_API_PORT:
    - Docker: BACKEND_API_HOST=api, BACKEND_API_PORT=8000
    - Local: BACKEND_API_HOST=localhost, BACKEND_API_PORT=8001

    Args:
        tenant_id: Tenant ID for multi-tenant MCP access
        api_host: API hostname (default: from BACKEND_API_HOST env, or "api")
        api_port: API port (default: from BACKEND_API_PORT env, or 8000)
        actor_user_id: UUID of the originating user. When provided, auth
            headers (system API key + X-Actor-User-Id) are included so that
            MCP tools attribute created resources to the real user.

    Returns:
        MCP server configuration dict for ClaudeAgentOptions

    Example:
        >>> get_mcp_servers("tenant123")
        {
            "analysi": {
                "type": "http",
                "url": "http://api:8000/v1/tenant123/mcp/"
            }
        }
    """
    # Auto-detect from environment if not explicitly provided
    if api_host is None:
        api_host = os.getenv("BACKEND_API_HOST", "api")

    if api_port is None:
        api_port = int(os.getenv("BACKEND_API_PORT", "8000"))

    base_url = f"http://{api_host}:{api_port}/v1/{tenant_id}"

    # Build auth headers (system API key + optional actor identity)
    headers = internal_auth_headers(actor_user_id=actor_user_id)

    def _server(url: str) -> dict:
        cfg: dict = {"type": "http", "url": url}
        if headers:
            cfg["headers"] = headers
        return cfg

    return {
        "analysi": _server(f"{base_url}/mcp/"),
    }


def create_executor(
    *,
    tenant_id: str,
    oauth_token: str | None = None,
    api_key: str | None = None,
    actor_user_id: UUID | str | None = None,
) -> AgentOrchestrationExecutor:
    """Create a production executor with tenant-aware MCP servers.

    This is the standard way to create executors for production jobs.
    Uses setting_sources=["project"] so the SDK only reads from the
    workspace .claude/ directory (set later via skills_project_dir or
    isolated_project_dir) — never from ~/.claude/ or the local project
    CLAUDE.md.

    Args:
        tenant_id: Tenant ID for MCP server routing.
        oauth_token: OAuth token (preferred).
        api_key: API key (fallback for evals).
        actor_user_id: User ID for MCP audit attribution.
    """
    from .sdk_wrapper import AgentOrchestrationExecutor

    mcp_servers = get_mcp_servers(tenant_id, actor_user_id=actor_user_id)
    return AgentOrchestrationExecutor(
        oauth_token=oauth_token,
        api_key=api_key,
        mcp_servers=mcp_servers,
        setting_sources=["project"],
    )


def create_eval_executor(
    *,
    api_key: str,
    isolated_project_dir: Path,
    tenant_id: str = "default",
) -> AgentOrchestrationExecutor:
    """Create an isolated executor for eval tests.

    Uses isolated_project_dir so the SDK reads .claude/ from a temp
    directory — never from the local project or ~/.claude/.

    Args:
        api_key: Anthropic API key.
        isolated_project_dir: Temp directory containing .claude/.
        tenant_id: Tenant ID for MCP servers (default: "default").
    """
    from .sdk_wrapper import AgentOrchestrationExecutor

    mcp_servers = get_mcp_servers(tenant_id)
    return AgentOrchestrationExecutor(
        api_key=api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_project_dir,
    )


def mcp_tool_wildcards(mcp_servers: dict[str, object]) -> list[str]:
    """Derive MCP tool wildcard permissions from server names.

    Claude Agent SDK requires explicit ``mcp__<server>__*`` entries in
    ``allowed_tools`` for agents to call MCP tools. This helper keeps
    the server names defined in one place (``get_mcp_servers``).

    Args:
        mcp_servers: The dict returned by ``get_mcp_servers()``.

    Returns:
        List of wildcard strings, e.g. ``["mcp__analysi__*"]``
    """
    return [f"mcp__{name}__*" for name in mcp_servers]
