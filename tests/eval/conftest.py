"""
Pytest configuration for eval tests.

Eval tests are expensive LLM tests that:
- Require ANTHROPIC_API_KEY environment variable
- Make actual API calls to Claude
- Are skipped by default (run with: pytest -m eval tests/eval/)

Cost tracking is automatic — every SDK and LangChain LLM call is
intercepted and recorded.  A summary table prints at session end.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from analysi.models.auth import SYSTEM_USER_ID

from .cost_tracker import (
    EvalCostTracker,
    install_langchain_interceptor,
    install_sdk_interceptor,
    uninstall_interceptors,
)

# Load .env.test for eval tests (before other configuration)
# This sets BACKEND_API_HOST=localhost and BACKEND_API_PORT=8001
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env.test", override=True)

# Skills are DB-only - no filesystem skills directory needed.
# Agents use default resolution via agents/dist/ (see config.py).


# ── Cost Tracking ───────────────────────────────────────────────
# Singleton tracker — shared across all fixtures and tests.
_cost_tracker = EvalCostTracker()


@pytest.fixture(scope="session", autouse=True)
def _eval_cost_tracking(request):
    """Install LLM cost interceptors for the entire session.

    Patches AgentOrchestrationExecutor.execute_stage and
    ChatAnthropic.ainvoke so every LLM call is recorded
    automatically — no test code changes needed.
    """
    install_sdk_interceptor(_cost_tracker)
    install_langchain_interceptor(_cost_tracker)
    request.config._eval_cost_tracker = _cost_tracker
    yield
    uninstall_interceptors()


@pytest.fixture(autouse=True)
def _set_cost_context(request):
    """Tag each test so cost entries carry the test name."""
    _cost_tracker.current_test = request.node.nodeid
    yield
    _cost_tracker.current_test = ""


@pytest.fixture(scope="session")
def eval_cost_tracker():
    """Public fixture for tests that need to record costs manually.

    Most tests don't need this — SDK and LangChain calls are
    tracked automatically. Use this only for custom LLM calls:

        def test_custom(eval_cost_tracker):
            # ... call some other LLM API ...
            eval_cost_tracker.record(cost_usd=0.05, label="custom call")
    """
    return _cost_tracker


def pytest_terminal_summary(terminalreporter, config):
    """Print cost summary at the end of the test session."""
    tracker = getattr(config, "_eval_cost_tracker", None)
    if tracker and tracker.entries:
        terminalreporter.write_sep("=", "Eval Cost Summary")
        terminalreporter.write_line(tracker.summary())
        terminalreporter.write_line(
            f"  Total session cost: ${tracker.total_cost:.4f}\n"
        )


def _cleanup_old_eval_directories():
    """Clean up eval test directories and workspace directories older than 48 hours.

    This preserves recent test runs for post-mortem analysis while
    preventing unbounded disk usage from accumulated test directories.

    Cleans up:
    - eval-test-* and eval-module-* (isolated .claude directories)
    - kea-* (agent workspace directories with outputs)
    """
    import shutil
    import tempfile
    import time

    temp_dir = Path(tempfile.gettempdir())
    cutoff_time = time.time() - (48 * 60 * 60)  # 48 hours ago
    cleaned = 0

    # Find all eval-test-*, eval-module-*, and kea-* directories
    for prefix in ["eval-test-", "eval-module-", "kea-"]:
        for test_dir in temp_dir.glob(f"{prefix}*"):
            if not test_dir.is_dir():
                continue

            # Check directory age via modification time
            try:
                dir_mtime = test_dir.stat().st_mtime
                if dir_mtime < cutoff_time:
                    shutil.rmtree(test_dir)
                    cleaned += 1
            except (OSError, PermissionError):
                # Skip directories we can't access or delete
                pass

    if cleaned > 0:
        print(f"\n=== Cleaned up {cleaned} old directories (>48h) ===\n")


# NOTE: PreToolUse hooks were attempted but are not invoked by the SDK's subprocess CLI backend.
# Keeping this comment for future reference if hook support is added to the Python SDK.


def _create_isolated_test_directory(prefix: str) -> Path:
    """Create isolated test directory with packaged agents/skills.

    DRY helper for creating test environments. Returns parent directory
    containing .claude/ subdirectory with copied agents/skills.

    Args:
        prefix: Directory prefix (e.g., "eval-test-", "eval-module-")

    Returns:
        Path to parent directory (contains .claude/ subdirectory)

    Directory structure:
        /tmp/{prefix}XXXXXX/          ← Returned path
        ├── .claude/                   ← SDK reads from here
        │   ├── agents/
        │   └── skills/
        └── outputs/                   ← SDK writes here
    """
    import shutil
    import tempfile

    agents_dir = PROJECT_ROOT / "agents" / "dist"

    if not agents_dir.exists():
        pytest.skip("agents/dist/ not found")

    # Clean up old directories before creating new one
    _cleanup_old_eval_directories()

    # Create temp directory (preserved for 48h)
    tmpdir = Path(tempfile.mkdtemp(prefix=prefix))
    claude_dir = tmpdir / ".claude"
    claude_dir.mkdir()

    # Copy production agents
    if agents_dir.exists():
        shutil.copytree(agents_dir, claude_dir / "agents")

    # Create README to explain directory purpose
    readme = tmpdir / "README.txt"
    readme.write_text(
        f"""Eval Test Directory - Preserved for 48h

This directory was created during eval test execution.
It will be automatically deleted after 48 hours.

Created: {Path(tmpdir).stat().st_mtime}
Prefix: {prefix}

Contents:
- .claude/        - Copied agents and skills (isolated from source)
- outputs/        - Agent outputs (runbooks, proposals, etc.)

To manually delete: rm -rf {tmpdir}
"""
    )

    print("\n=== Isolated Test Environment ===")
    print(f"Directory: {tmpdir}")
    agents_count = (
        len(list((claude_dir / "agents").glob("*.md")))
        if (claude_dir / "agents").exists()
        else 0
    )
    skills_dir = claude_dir / "skills"
    skills_count = len(list(skills_dir.iterdir())) if skills_dir.exists() else 0
    print(f"Agents: {agents_count}")
    print(f"Skills: {skills_count} (DB-only)")
    print("Preserved for: 48 hours")
    print("=================================\n")

    return tmpdir


class SecureAPIKey(str):
    """String subclass that masks API key in pytest output."""

    def __repr__(self) -> str:
        """Mask API key for security - only show last 4 chars."""
        if len(self) > 4:
            return f"SecureAPIKey('***{self[-4:]}')"
        return "SecureAPIKey('***')"


@pytest.fixture(scope="session")
def anthropic_api_key():
    """Get ANTHROPIC_API_KEY from environment.

    Session-scoped so it can be used by module-scoped fixtures.
    Returns SecureAPIKey wrapper that masks the key in pytest output
    while still working as a normal string in code.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return SecureAPIKey(api_key)


@pytest.fixture
def isolated_claude_dir():
    """Create isolated .claude directory for eval test.

    Returns:
        Path to PARENT directory containing .claude/ subdirectory

    Features:
        - Complete isolation: SDK cannot access project source code
        - Preserved for 48h for post-mortem analysis
        - Auto-cleanup of old directories (>48h)
    """
    tmpdir = _create_isolated_test_directory("eval-test-")
    return tmpdir
    # Directory preserved for 48h (cleaned by _cleanup_old_eval_directories)


@pytest.fixture
def eval_executor(anthropic_api_key, isolated_claude_dir):
    """Create an isolated executor for eval tests.

    Uses create_eval_executor() factory — the standard way to create
    executors in eval tests.  See config.py for details.
    """
    from analysi.agentic_orchestration import create_eval_executor

    return create_eval_executor(
        api_key=anthropic_api_key,
        isolated_project_dir=isolated_claude_dir,
    )


@pytest.fixture(scope="module")
def first_subgraph_result(anthropic_api_key):
    """Run first subgraph once and cache result for all tests in module.

    This fixture runs the expensive subgraph (2 Claude API calls) once and
    shares the result across all test functions, significantly reducing:
    - Test execution time (5x speedup)
    - API costs (5x reduction)
    - Rate limit pressure

    The result is immutable and safe to share across tests.

    Note: Uses synchronous fixture with asyncio.run() to avoid pytest-asyncio
    module-scope limitations. Includes sleep to allow SDK background tasks to
    complete cleanup before event loop closes.

    Uses isolated .claude directory to prevent pollution of source skills.
    """
    import asyncio

    from analysi.agentic_orchestration import (
        AgentOrchestrationExecutor,
        get_mcp_servers,
    )
    from analysi.agentic_orchestration.subgraphs import run_first_subgraph

    async def run_with_cleanup():
        """Run subgraph and wait for SDK background task cleanup."""
        # Create isolated directory (DRY)
        tmpdir = _create_isolated_test_directory("eval-module-")

        try:
            tenant_id = "default"

            # Sample alert for testing (matches SAMPLE_ALERTS[0] in test file)
            alert = {
                "id": "test-alert-001",
                "title": "Suspicious Login from Unusual Location",
                "severity": "high",
                "source_vendor": "Okta",
                "rule_name": "unusual_login_location",
                "triggering_event_time": "2024-01-15T10:30:00Z",
                "raw_alert": {
                    "user": "john.doe@corp.example",
                    "ip": "91.234.56.101",
                    "country": "Russia",
                    "normal_country": "United States",
                },
            }

            # Configure MCP servers for task proposal phase (needs to query integrations/tasks)
            mcp_servers = get_mcp_servers(tenant_id)

            executor = AgentOrchestrationExecutor(
                api_key=anthropic_api_key,
                mcp_servers=mcp_servers,
                isolated_project_dir=tmpdir,
                # setting_sources will be auto-set to ["project"] by constructor
            )

            # Run subgraph with explicit creator context
            result = await run_first_subgraph(
                alert,
                executor,
                run_id="eval-first-subgraph-test",
                tenant_id=tenant_id,
                created_by=str(SYSTEM_USER_ID),
            )

            # CRITICAL: Give SDK background tasks time to complete cleanup
            # The Claude Agent SDK creates background async tasks for query processing.
            # When asyncio.run() exits, it closes the event loop immediately, but these
            # background tasks are still trying to clean up their anyio cancel scopes.
            # This causes "Attempted to exit cancel scope in a different task" errors.
            # Solution: Sleep to allow background tasks to finish naturally.
            # Note: 0.1s was insufficient - using 1s to ensure all background cleanup completes
            await asyncio.sleep(1.0)

            return result
        finally:
            # Directory preserved for 48h post-mortem (cleaned by _cleanup_old_eval_directories)
            pass

    # Run subgraph once in a new event loop with proper cleanup
    result = asyncio.run(run_with_cleanup())

    # Debug logging
    print("\n=== Cached First Subgraph Result ===")
    print(f"runbook: {result['runbook'][:100] if result['runbook'] else None}...")
    print(
        f"task_proposals: {len(result['task_proposals']) if result['task_proposals'] else 0} proposals"
    )
    print(f"metrics: {len(result['metrics'])} stages")
    print(f"error: {result['error']}")
    print("===================================\n")

    return result


@pytest.fixture(scope="module")
def second_subgraph_result_mixed(anthropic_api_key):
    """Run second subgraph once with MIXED proposals and cache for tests.

    Uses SAMPLE_TASK_PROPOSALS_MIXED (2 new tasks) to test task building
    and workflow assembly with new tasks.

    Uses isolated .claude directory to prevent pollution of source skills.
    """
    import asyncio
    import shutil
    import tempfile

    from analysi.agentic_orchestration import (
        AgentOrchestrationExecutor,
        get_mcp_servers,
    )
    from analysi.agentic_orchestration.subgraphs import run_second_subgraph

    async def run_with_cleanup():
        # Create isolated claude_dir for this module
        agents_dir = PROJECT_ROOT / "agents" / "dist"

        if not agents_dir.exists():
            pytest.skip("agents/dist/ not found")

        # Create temp directory (preserved for 48h, not auto-deleted)
        tmpdir = Path(tempfile.mkdtemp(prefix="eval-module-"))
        claude_dir = tmpdir / ".claude"
        claude_dir.mkdir()

        # Copy production agents
        if agents_dir.exists():
            shutil.copytree(agents_dir, claude_dir / "agents")

        try:
            tenant_id = "default"
            mcp_servers = get_mcp_servers(tenant_id)

            # Sample data - matches Step 2→3 contract
            # Contract: name, designation, description, integration-mapping (optional)
            task_proposals = [
                {
                    "name": "VirusTotal: IP Reputation Check",
                    "designation": "new",
                    "description": "Purpose: Query VirusTotal for IP reputation to assess threat level. Inputs: Source IP from alert. Process: Call VirusTotal API, analyze reputation score and detections. Outputs: Threat assessment with reputation score.",
                    "integration-mapping": {
                        "integration-id": "virustotal-main",
                        "actions-used": ["ip_reputation"],
                    },
                },
                {
                    "name": "Splunk: User Activity Lookup",
                    "designation": "new",
                    "description": "Purpose: Search recent user activity in SIEM to identify anomalous patterns. Inputs: Username from alert, time window. Process: Query SIEM for recent logins, analyze patterns. Outputs: Activity timeline with anomaly flags.",
                    "integration-mapping": {
                        "integration-id": "splunk-local",
                        "actions-used": ["search"],
                    },
                },
            ]

            runbook = """# Investigation Runbook: Suspicious Login
## Overview
Investigate suspicious login from unusual location.
"""

            alert = {
                "id": "test-alert-001",
                "title": "Suspicious Login from Unusual Location",
                "severity": "high",
            }

            executor = AgentOrchestrationExecutor(
                api_key=anthropic_api_key,
                mcp_servers=mcp_servers,
                isolated_project_dir=tmpdir,
                # setting_sources will be auto-set to ["project"] by constructor
            )

            result = await run_second_subgraph(
                task_proposals=task_proposals,
                runbook=runbook,
                alert=alert,
                executor=executor,
                run_id="eval-second-subgraph-mixed",
                tenant_id=tenant_id,
                created_by=str(SYSTEM_USER_ID),
            )

            # Give SDK background tasks time to complete (1s to ensure all cleanup finishes)
            await asyncio.sleep(1.0)

            return result
        finally:
            # Directory preserved for 48h post-mortem (cleaned by _cleanup_old_eval_directories)
            pass

    result = asyncio.run(run_with_cleanup())

    print("\n=== Cached Second Subgraph (MIXED) ===")
    print(f"tasks_built: {len(result['tasks_built'])} tasks")
    print(f"workflow_id: {result['workflow_id']}")
    print(f"metrics: {len(result['metrics'])} entries")
    print("======================================\n")

    return result


@pytest.fixture(scope="module")
def second_subgraph_result_existing(anthropic_api_key):
    """Run second subgraph once with ALL_EXISTING proposals and cache for tests.

    Uses SAMPLE_TASK_PROPOSALS_ALL_EXISTING to test skipping task building
    and going directly to workflow assembly.

    Uses isolated .claude directory to prevent pollution of source skills.
    """
    import asyncio
    import shutil
    import tempfile

    from analysi.agentic_orchestration import (
        AgentOrchestrationExecutor,
        get_mcp_servers,
    )
    from analysi.agentic_orchestration.subgraphs import run_second_subgraph

    async def run_with_cleanup():
        # Create isolated claude_dir for this module
        agents_dir = PROJECT_ROOT / "agents" / "dist"

        if not agents_dir.exists():
            pytest.skip("agents/dist/ not found")

        # Create temp directory (preserved for 48h, not auto-deleted)
        tmpdir = Path(tempfile.mkdtemp(prefix="eval-module-"))
        claude_dir = tmpdir / ".claude"
        claude_dir.mkdir()

        # Copy production agents
        if agents_dir.exists():
            shutil.copytree(agents_dir, claude_dir / "agents")

        try:
            tenant_id = "default"
            mcp_servers = get_mcp_servers(tenant_id)

            # Sample data - matches Step 2→3 contract for existing tasks
            # Contract: name, cy_name, designation, description
            task_proposals = [
                {
                    "name": "VirusTotal: IP Reputation Analysis",
                    "cy_name": "vt_ip_reputation",
                    "designation": "existing",
                    "description": "Enriches alerts with VirusTotal IP reputation data",
                },
                {
                    "name": "Splunk: User Search",
                    "cy_name": "splunk_user_search",
                    "designation": "existing",
                    "description": "Searches SIEM for user activity patterns",
                },
            ]

            runbook = """# Investigation Runbook: Suspicious Login
## Overview
Investigate suspicious login from unusual location.
"""

            alert = {
                "id": "test-alert-001",
                "title": "Suspicious Login from Unusual Location",
                "severity": "high",
            }

            executor = AgentOrchestrationExecutor(
                api_key=anthropic_api_key,
                mcp_servers=mcp_servers,
                isolated_project_dir=tmpdir,
                # setting_sources will be auto-set to ["project"] by constructor
            )

            result = await run_second_subgraph(
                task_proposals=task_proposals,
                runbook=runbook,
                alert=alert,
                executor=executor,
                run_id="eval-second-subgraph-existing",
                tenant_id=tenant_id,
                created_by=str(SYSTEM_USER_ID),
            )

            # Give SDK background tasks time to complete (1s to ensure all cleanup finishes)
            await asyncio.sleep(1.0)

            return result
        finally:
            # Directory preserved for 48h post-mortem (cleaned by _cleanup_old_eval_directories)
            pass

    result = asyncio.run(run_with_cleanup())

    print("\n=== Cached Second Subgraph (EXISTING) ===")
    print(f"tasks_built: {len(result['tasks_built'])} tasks")
    print(f"workflow_composition: {result['workflow_composition']}")
    print(f"metrics: {len(result['metrics'])} entries")
    print("=========================================\n")

    return result
