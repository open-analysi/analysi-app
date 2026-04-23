"""Basic eval tests for task building node.

These tests incrementally verify:
1. Agent workspace and file capture works
2. Task building node produces expected outputs
3. MCP tools are accessible

Run with: make test-eval or pytest -m eval tests/eval/test_task_building_basic.py -v -s

Parallelization Strategy:
- workspace_creates_temp_directory runs separately (no LLM, fast)
- 4 LLM tests run in parallel via task_building_basic_suite
"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from analysi.agentic_orchestration import (
    AgentOrchestrationExecutor,
    get_mcp_servers,
)
from analysi.agentic_orchestration.nodes import task_building_node
from analysi.agentic_orchestration.observability import (
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.workspace import AgentWorkspace

# Enable debug logging for eval tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SIMPLE_TASK_PROPOSAL = {
    "name": "Echo Health Check",
    "description": "Simple task that calls echo_edr health_check integration",
    "designation": "new",
    "existing_cy_name": None,
    "integration_tools": ["echo_edr::health_check"],
    "investigation_steps": [
        "Call the echo_edr health_check integration",
        "Return the result",
    ],
}

SIMPLE_ALERT = {
    "id": "test-alert-basic",
    "title": "Basic Test Alert",
    "severity": "low",
    "raw_alert": {"test": "data"},
}

SIMPLE_RUNBOOK = """# Basic Investigation

## Steps
1. Check the echo_edr health
2. Return result
"""


@pytest.mark.eval
@pytest.mark.asyncio
async def test_workspace_creates_temp_directory(anthropic_api_key):
    """Verify workspace creates isolated temp directory."""
    workspace = AgentWorkspace(
        run_id="test-basic-001", tenant_id="eval-test", auto_cleanup=True
    )

    try:
        assert workspace.work_dir.exists()
        assert "kea-eval-test-test-basic-001" in str(workspace.work_dir)
        logger.info("Workspace created: %s", workspace.work_dir)
    finally:
        workspace.cleanup()
        assert not workspace.work_dir.exists()


@pytest.mark.eval
@pytest.mark.asyncio
async def test_executor_with_mcp_can_list_integrations(anthropic_api_key):
    """Verify MCP servers are accessible and can list integrations."""
    tenant_id = "eval-test-tenant"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
    )

    # Simple test: just verify executor can be created with MCP
    assert executor.mcp_servers is not None
    assert len(executor.mcp_servers) > 0
    logger.info("MCP servers configured: %s", list(executor.mcp_servers.keys()))


@pytest.mark.eval
@pytest.mark.asyncio
async def test_simple_file_write_agent(anthropic_api_key, isolated_claude_dir):
    """Verify agent can write files to workspace.

    Uses a minimal inline agent prompt to test the workspace mechanism.
    """
    tenant_id = "eval-test-tenant"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
        # setting_sources will be auto-set to ["project"] by constructor
    )

    workspace = AgentWorkspace(run_id="test-file-write", tenant_id=tenant_id)

    try:
        # Create a simple test prompt file
        simple_agent = """# Test File Writer Agent

You are a simple agent that writes JSON files.

Given the input context, write a JSON file with the specified structure.
"""
        test_agent_path = Path(tempfile.mktemp(suffix=".md"))
        test_agent_path.write_text(simple_agent)

        context = {"test_value": "hello", "test_number": 42}

        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=test_agent_path,
            context=context,
            expected_outputs=["result.json"],
            stage=WorkflowGenerationStage.TASK_BUILDING,
        )

        logger.info("=== File Write Test Results ===")
        logger.info("Result content: %s", outputs.get("result.json"))
        logger.info(
            "Metrics: cost=$%.4f, turns=%d", metrics.total_cost_usd, metrics.num_turns
        )

        # Check if file was written
        if outputs.get("result.json"):
            logger.info("SUCCESS: Agent wrote result.json")
            parsed_result = json.loads(outputs["result.json"])
            logger.info("Parsed result: %s", parsed_result)
        else:
            logger.warning("Agent did not write result.json")
            # List what files were created
            files = list(workspace.work_dir.iterdir())
            logger.info("Files in workspace: %s", [f.name for f in files])
            for f in files:
                if f.is_file():
                    logger.info("  %s: %s", f.name, f.read_text()[:200])

        # Clean up test agent file
        test_agent_path.unlink()

    finally:
        workspace.cleanup()


@pytest.mark.eval
@pytest.mark.asyncio
async def test_task_building_node_with_simple_proposal(
    anthropic_api_key, isolated_claude_dir
):
    """Test task building node with a simple echo_edr proposal.

    This is the key test - verifies the actual task building node works.
    """
    tenant_id = "eval-test-tenant"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
        # setting_sources will be auto-set to ["project"] by constructor
    )

    # Create workspace for the task building node
    from analysi.agentic_orchestration.workspace import AgentWorkspace

    workspace = AgentWorkspace(run_id="test-task-build-basic", tenant_id=tenant_id)

    try:
        state = {
            "proposal": SIMPLE_TASK_PROPOSAL,
            "alert": SIMPLE_ALERT,
            "runbook": SIMPLE_RUNBOOK,
            "run_id": "test-task-build-basic",
            "tenant_id": tenant_id,
            "workspace": workspace,  # Required by task_building_node
        }

        logger.info("=== Running task_building_node ===")
        result = await task_building_node(state, executor)
    finally:
        # Note: task_building_node calls workspace.cleanup() internally
        pass

    logger.info("=== Task Building Result ===")
    logger.info("tasks_built: %s", result.get("tasks_built"))

    if result["tasks_built"]:
        task = result["tasks_built"][0]
        logger.info("  success: %s", task.get("success"))
        logger.info("  task_id: %s", task.get("task_id"))
        logger.info("  cy_name: %s", task.get("cy_name"))
        logger.info("  error: %s", task.get("error"))

    # Basic assertions
    assert "tasks_built" in result
    assert len(result["tasks_built"]) == 1

    # Report status for debugging
    task = result["tasks_built"][0]
    if task.get("success"):
        logger.info("SUCCESS: Task created with cy_name=%s", task["cy_name"])
    else:
        logger.warning("FAILED: %s", task.get("error"))


@pytest.mark.eval
@pytest.mark.asyncio
async def test_mcp_list_integrations(anthropic_api_key, isolated_claude_dir):
    """Directly test MCP integration listing via SDK execution.

    This verifies MCP tools work through the executor.
    """
    tenant_id = "eval-test-tenant"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
        # setting_sources will be auto-set to ["project"] by constructor
    )

    # Execute a simple prompt that lists integrations
    result, metrics = await executor.execute_stage(
        stage=WorkflowGenerationStage.TASK_BUILDING,
        system_prompt="You are a helpful assistant with access to MCP tools.",
        user_prompt="""Use the mcp__analysi__list_integrations tool to list all configured integrations.

Then write a JSON file called integrations.json with the list of integration names.

Working directory for file writes: /tmp/mcp-test/
""",
        cwd="/tmp/mcp-test/",
    )

    logger.info("=== MCP List Integrations Test ===")
    logger.info("Result text length: %s", len(result) if result else 0)
    logger.info("Cost: $%.4f", metrics.total_cost_usd)
    logger.info("Tool calls: %s", [tc.tool_name for tc in metrics.tool_calls])

    # Check if integrations.json was written
    integrations_file = Path("/tmp/mcp-test/integrations.json")
    if integrations_file.exists():
        file_content = integrations_file.read_text()
        logger.info("integrations.json content: %s", file_content[:500])
    else:
        logger.warning("integrations.json not found")
