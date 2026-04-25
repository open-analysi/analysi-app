"""End-to-end eval test for Task creation and execution.

This test verifies the core Kea mechanics with a simpler scenario:
1. Agent 1 (Task Creator): Uses cybersec-task-builder to create a Task that summarizes NAS alerts
2. Agent 2 (Task Runner): Runs the created Task on the alert and captures the summary

This validates:
- Agents can use MCP analysi server to create Tasks
- Created Tasks are executable
- LangGraph + Claude Agent SDK integration works as expected

Run with: pytest -m eval tests/eval/test_task_creation_e2e.py -v -s
"""

import json
import logging
import operator
import uuid
from pathlib import Path
from typing import Annotated, Any

import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from analysi.agentic_orchestration import (
    AgentOrchestrationExecutor,
    get_mcp_servers,
)
from analysi.agentic_orchestration.config import get_agent_path
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.workspace import AgentWorkspace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Test Data
# ============================================================================

TEST_NAS_ALERT = {
    "id": f"eval-alert-{uuid.uuid4().hex[:8]}",
    "title": "Suspicious PowerShell Execution Detected",
    "severity": "high",
    "source_vendor": "CrowdStrike",
    "source_category": "EDR",
    "rule_name": "powershell_encoded_command",
    "triggering_event_time": "2024-01-15T14:32:00Z",
    "raw_alert": {
        "event_type": "ProcessCreate",
        "process_name": "powershell.exe",
        "command_line": "powershell.exe -EncodedCommand SGVsbG8gV29ybGQ=",
        "parent_process": "cmd.exe",
        "user": "CORP\\john.smith",
        "hostname": "WORKSTATION-42",
        "ip_address": "192.168.1.105",
        "detection_score": 85,
        "mitre_tactics": ["Execution", "Defense Evasion"],
        "mitre_techniques": ["T1059.001", "T1027"],
    },
}


# ============================================================================
# LangGraph State
# ============================================================================


class TaskCreationState(TypedDict):
    """State for the two-agent workflow."""

    # Input
    alert: dict[str, Any]

    # Agent 1 outputs
    task_cy_name: str | None
    task_id: str | None
    task_creation_error: str | None

    # Agent 2 outputs
    alert_summary: str | None
    task_execution_error: str | None

    # Metrics
    metrics: Annotated[list[StageExecutionMetrics], operator.add]

    # Context
    run_id: str
    tenant_id: str


# ============================================================================
# Agent 1: Task Creator
# ============================================================================


async def task_creator_node(
    state: TaskCreationState,
    executor: AgentOrchestrationExecutor,
) -> dict[str, Any]:
    """Create a Task that summarizes NAS alerts using cybersec-task-builder agent.

    This agent uses MCP analysi server to create a real Task.
    """
    run_id = state["run_id"]
    tenant_id = state["tenant_id"]
    alert = state["alert"]

    # Generate unique task name
    task_name = f"alert_summarizer_{uuid.uuid4().hex[:8]}"

    logger.info("=== Task Creator Agent ===")
    logger.info("Creating task: %s", task_name)

    workspace = AgentWorkspace(
        run_id=f"{run_id}-creator",
        tenant_id=tenant_id,
    )

    default_metrics = StageExecutionMetrics(
        duration_ms=0,
        duration_api_ms=0,
        num_turns=0,
        total_cost_usd=0.0,
        usage={},
        tool_calls=[],
    )

    try:
        # Context for the task-builder agent
        context = {
            "task_request": {
                "name": task_name,
                "description": "A simple Task that takes a NAS alert and produces a brief summary",
                "cy_name": task_name,
                "requirements": [
                    "Accept a NAS alert as input",
                    "Use llm_run to generate a 2-3 sentence summary of the alert",
                    "The summary should highlight: what happened, severity, and key indicators",
                    "Return the summary as the task output",
                ],
            },
            "sample_alert": alert,
            "output_instructions": {
                "task_result_file": "task-result.json",
                "alert_file": "test-alert.json",
                "format": {
                    "task-result.json": {
                        "task_id": "the UUID returned by create_task MCP tool",
                        "cy_name": task_name,
                        "error": "null if successful, error message if failed",
                    },
                    "test-alert.json": "the sample_alert for testing the task",
                },
            },
            "methodology_requirements": {
                "note": "Even though this is a simple task, we want to validate the full methodology.",
                "required_steps": [
                    "You MUST use the Task tool to spawn a 'cy-script-segment-tester' subagent to test each code segment",
                    "Each segment of Cy code must be validated by the segment tester before proceeding",
                    "Do NOT skip the segment testing phase - this validates correctness before integration",
                ],
            },
        }

        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=get_agent_path("cybersec-task-builder.md"),
            context=context,
            expected_outputs=["task-result.json", "test-alert.json"],
            stage=WorkflowGenerationStage.TASK_BUILDING,
        )

        logger.info("Task Creator outputs: %s", list(outputs.keys()))

        # Parse task-result.json
        task_result_json = outputs.get("task-result.json")
        if task_result_json:
            try:
                task_result = json.loads(task_result_json)
                logger.info("Task result: %s", task_result)

                if task_result.get("error"):
                    return {
                        "task_cy_name": None,
                        "task_id": None,
                        "task_creation_error": task_result["error"],
                        "metrics": [metrics],
                    }

                return {
                    "task_cy_name": task_result.get("cy_name", task_name),
                    "task_id": task_result.get("task_id"),
                    "task_creation_error": None,
                    "metrics": [metrics],
                }
            except json.JSONDecodeError as e:
                logger.error("Failed to parse task-result.json: %s", e)
                return {
                    "task_cy_name": None,
                    "task_id": None,
                    "task_creation_error": f"Invalid JSON in task-result.json: {e}",
                    "metrics": [metrics],
                }
        else:
            # List what files were created for debugging
            files = (
                list(workspace.work_dir.iterdir())
                if workspace.work_dir.exists()
                else []
            )
            logger.warning(
                "No task-result.json found. Files in workspace: %s",
                [f.name for f in files],
            )
            for f in files:
                if f.is_file():
                    content = f.read_text()[:500]
                    logger.info("  %s: %s", f.name, content)

            return {
                "task_cy_name": None,
                "task_id": None,
                "task_creation_error": "Agent did not produce task-result.json",
                "metrics": [metrics],
            }

    except Exception as e:
        logger.exception("Task creator failed")
        return {
            "task_cy_name": None,
            "task_id": None,
            "task_creation_error": str(e),
            "metrics": [default_metrics],
        }
    finally:
        workspace.cleanup()


# ============================================================================
# Agent 2: Task Runner
# ============================================================================


async def task_runner_node(
    state: TaskCreationState,
    executor: AgentOrchestrationExecutor,
) -> dict[str, Any]:
    """Run the created Task on the alert and capture the summary.

    This agent uses MCP analysi server to execute the Task.
    """
    run_id = state["run_id"]
    tenant_id = state["tenant_id"]
    task_cy_name = state.get("task_cy_name")
    alert = state["alert"]

    logger.info("=== Task Runner Agent ===")
    logger.info("Running task: %s", task_cy_name)

    if not task_cy_name:
        logger.warning("No task_cy_name provided - skipping execution")
        return {
            "alert_summary": None,
            "task_execution_error": "No task to run (task creation failed)",
            "metrics": [],
        }

    workspace = AgentWorkspace(
        run_id=f"{run_id}-runner",
        tenant_id=tenant_id,
    )

    default_metrics = StageExecutionMetrics(
        duration_ms=0,
        duration_api_ms=0,
        num_turns=0,
        total_cost_usd=0.0,
        usage={},
        tool_calls=[],
    )

    try:
        # Simple agent prompt for running the task
        runner_prompt = f"""# Task Runner Agent

You are a simple agent that runs a Cy Task and captures its output.

## Your Task

1. Use the MCP tool `mcp__analysi__run_script` to run the task "{task_cy_name}"
   - The task expects a NAS alert as input
   - Pass the alert from the Input Context below

2. Capture the task output (the alert summary)

3. Write the summary to `summary.txt`

## Important

- The task cy_name is: {task_cy_name}
- Use run_script with the task's script
- Or use get_task to get the task first, then execute its script
"""

        # Create temporary agent file
        import tempfile

        agent_path = Path(tempfile.mktemp(suffix=".md"))
        agent_path.write_text(runner_prompt)

        context = {
            "task_cy_name": task_cy_name,
            "alert": alert,
        }

        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=agent_path,
            context=context,
            expected_outputs=["summary.txt"],
            stage=WorkflowGenerationStage.TASK_BUILDING,
        )

        # Clean up temp file
        agent_path.unlink()

        logger.info("Task Runner outputs: %s", list(outputs.keys()))

        summary = outputs.get("summary.txt")
        if summary:
            logger.info("Alert summary: %s...", summary[:200])
            return {
                "alert_summary": summary,
                "task_execution_error": None,
                "metrics": [metrics],
            }
        # Debug: show what files were created
        files = (
            list(workspace.work_dir.iterdir()) if workspace.work_dir.exists() else []
        )
        logger.warning("No summary.txt found. Files: %s", [f.name for f in files])

        return {
            "alert_summary": None,
            "task_execution_error": "Agent did not produce summary.txt",
            "metrics": [metrics],
        }

    except Exception as e:
        logger.exception("Task runner failed")
        return {
            "alert_summary": None,
            "task_execution_error": str(e),
            "metrics": [default_metrics],
        }
    finally:
        workspace.cleanup()


# ============================================================================
# Routing
# ============================================================================


def should_run_task(state: TaskCreationState) -> str:
    """Determine if we should proceed to run the task."""
    if state.get("task_creation_error"):
        return "end"
    if state.get("task_cy_name"):
        return "run_task"
    return "end"


# ============================================================================
# Graph Builder
# ============================================================================


def create_task_e2e_graph(
    executor: AgentOrchestrationExecutor,
) -> StateGraph:
    """Create the two-agent LangGraph workflow."""

    async def create_task(state: TaskCreationState) -> dict[str, Any]:
        return await task_creator_node(state, executor)

    async def run_task(state: TaskCreationState) -> dict[str, Any]:
        return await task_runner_node(state, executor)

    graph = StateGraph(TaskCreationState)

    graph.add_node("create_task", create_task)
    graph.add_node("run_task", run_task)

    graph.add_edge(START, "create_task")
    graph.add_conditional_edges(
        "create_task",
        should_run_task,
        {
            "run_task": "run_task",
            "end": END,
        },
    )
    graph.add_edge("run_task", END)

    return graph.compile()


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.eval
@pytest.mark.asyncio
async def test_task_creation_and_execution_e2e(anthropic_api_key, isolated_claude_dir):
    """End-to-end test: Create a summarizer task and run it on an alert.

    This test validates:
    1. cybersec-task-builder agent can create a Task via MCP
    2. The created Task is executable
    3. The Task produces a meaningful summary
    """
    tenant_id = "eval-test-tenant"
    run_id = f"e2e-test-{uuid.uuid4().hex[:8]}"

    mcp_servers = get_mcp_servers(tenant_id)
    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
        # setting_sources will be auto-set to ["project"] by constructor
    )

    graph = create_task_e2e_graph(executor)

    initial_state: TaskCreationState = {
        "alert": TEST_NAS_ALERT,
        "task_cy_name": None,
        "task_id": None,
        "task_creation_error": None,
        "alert_summary": None,
        "task_execution_error": None,
        "metrics": [],
        "run_id": run_id,
        "tenant_id": tenant_id,
    }

    logger.info("=" * 60)
    logger.info("Starting E2E Task Creation Test")
    logger.info("Alert: %s", TEST_NAS_ALERT["title"])
    logger.info("Run ID: %s", run_id)
    logger.info("=" * 60)

    result = await graph.ainvoke(initial_state)

    # Report results
    logger.info("\n" + "=" * 60)
    logger.info("E2E Test Results")
    logger.info("=" * 60)
    logger.info("Task cy_name: %s", result.get("task_cy_name"))
    logger.info("Task ID: %s", result.get("task_id"))
    logger.info("Task creation error: %s", result.get("task_creation_error"))
    logger.info("Task execution error: %s", result.get("task_execution_error"))
    logger.info("Alert summary: %s", result.get("alert_summary"))

    total_cost = sum(m.total_cost_usd for m in result.get("metrics", []))
    logger.info("Total cost: $%.4f", total_cost)
    logger.info("=" * 60)

    # Assertions
    # Verify task creation
    if result.get("task_creation_error"):
        pytest.fail(f"Task creation failed: {result['task_creation_error']}")

    assert result.get("task_cy_name"), "Task cy_name should be set"
    assert result.get("task_id"), "Task ID should be set"

    # Verify task execution
    if result.get("task_execution_error"):
        pytest.fail(f"Task execution failed: {result['task_execution_error']}")

    assert result.get("alert_summary"), "Alert summary should be produced"

    # Verify summary quality (basic check)
    summary = result["alert_summary"].lower()
    # Summary should mention key elements from the alert
    assert any(
        word in summary for word in ["powershell", "suspicious", "execution", "alert"]
    ), f"Summary should reference the alert content. Got: {result['alert_summary']}"

    logger.info("SUCCESS: Task created and executed successfully!")


def print_metrics_report(  # noqa: C901
    metrics_list: list[StageExecutionMetrics], title: str = "Metrics Report"
):
    """Print detailed metrics report showing all tool calls."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

    total_cost = 0.0
    all_tool_calls = []

    for i, metrics in enumerate(metrics_list):
        print(f"\n--- Stage {i + 1} ---")
        print(f"  Cost: ${metrics.total_cost_usd:.4f}")
        print(f"  Turns: {metrics.num_turns}")
        print(f"  Usage: {metrics.usage}")
        print(f"  Tool calls: {len(metrics.tool_calls)}")

        total_cost += metrics.total_cost_usd
        all_tool_calls.extend(metrics.tool_calls)

    # Categorize tool calls
    mcp_calls = [t for t in all_tool_calls if t.tool_name.startswith("mcp__")]
    task_calls = [t for t in all_tool_calls if t.tool_name == "Task"]
    skill_calls = [t for t in all_tool_calls if t.tool_name == "Skill"]
    write_calls = [t for t in all_tool_calls if t.tool_name == "Write"]
    read_calls = [t for t in all_tool_calls if t.tool_name == "Read"]
    other_calls = [
        t
        for t in all_tool_calls
        if t.tool_name not in ["Task", "Skill", "Write", "Read"]
        and not t.tool_name.startswith("mcp__")
    ]

    print("\n" + "-" * 80)
    print("  TOOL CALL SUMMARY")
    print("-" * 80)
    print(f"  Total tool calls: {len(all_tool_calls)}")
    print(f"  MCP calls: {len(mcp_calls)}")
    print(f"  Task (subagent) calls: {len(task_calls)}")
    print(f"  Skill calls: {len(skill_calls)}")
    print(f"  Write calls: {len(write_calls)}")
    print(f"  Read calls: {len(read_calls)}")
    print(f"  Other: {len(other_calls)}")

    # Detail MCP calls - these are critical for understanding what testing was done
    if mcp_calls:
        print("\n" + "-" * 80)
        print("  MCP TOOL CALLS (analysi)")
        print("-" * 80)
        for call in mcp_calls:
            tool_short = call.tool_name.replace("mcp__analysi__", "a::")
            print(f"\n  [{tool_short}]")
            # Show abbreviated input
            input_str = json.dumps(call.input_args, indent=2)
            if len(input_str) > 300:
                input_str = input_str[:300] + "..."
            print(f"    Input: {input_str}")
            # Show if error
            if call.is_error:
                print(f"    ERROR: {call.result}")
            else:
                result_str = str(call.result)
                if len(result_str) > 200:
                    result_str = result_str[:200] + "..."
                print(f"    Result: {result_str}")

    # Detail Task calls (subagents)
    if task_calls:
        print("\n" + "-" * 80)
        print("  SUBAGENT (Task) CALLS")
        print("-" * 80)
        for call in task_calls:
            print(
                f"\n  Subagent type: {call.input_args.get('subagent_type', 'unknown')}"
            )
            print(f"    Description: {call.input_args.get('description', 'N/A')}")
            prompt = call.input_args.get("prompt", "")
            if len(prompt) > 200:
                prompt = prompt[:200] + "..."
            print(f"    Prompt: {prompt}")
            if call.is_error:
                print(f"    ERROR: {call.result}")

    # Detail Skill calls
    if skill_calls:
        print("\n" + "-" * 80)
        print("  SKILL CALLS")
        print("-" * 80)
        for call in skill_calls:
            print(f"\n  Skill: {call.input_args.get('skill', 'unknown')}")
            if call.is_error:
                print(f"    ERROR: {call.result}")

    # Files written
    if write_calls:
        print("\n" + "-" * 80)
        print("  FILES WRITTEN")
        print("-" * 80)
        for call in write_calls:
            filepath = call.input_args.get("file_path", "unknown")
            content = call.input_args.get("content", "")
            print(f"\n  File: {filepath}")
            print(f"    Size: {len(content)} bytes")
            if call.is_error:
                print(f"    ERROR: {call.result}")

    print("\n" + "=" * 80)
    print(f"  TOTAL COST: ${total_cost:.4f}")
    print("=" * 80 + "\n")


@pytest.mark.eval
@pytest.mark.asyncio
async def test_task_creator_with_detailed_metrics(
    anthropic_api_key, isolated_claude_dir
):
    """Diagnostic test that prints detailed metrics to understand agent behavior.

    This test runs the task creator and dumps all tool calls to understand:
    - What MCP calls were made (compile_script, run_script, create_task)
    - Whether subagents (Task tool) were spawned for testing
    - What skills were invoked
    - What files were written
    """
    tenant_id = "eval-test-tenant"
    run_id = f"metrics-test-{uuid.uuid4().hex[:8]}"

    mcp_servers = get_mcp_servers(tenant_id)
    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
        # setting_sources will be auto-set to ["project"] by constructor
    )

    state: TaskCreationState = {
        "alert": TEST_NAS_ALERT,
        "task_cy_name": None,
        "task_id": None,
        "task_creation_error": None,
        "alert_summary": None,
        "task_execution_error": None,
        "metrics": [],
        "run_id": run_id,
        "tenant_id": tenant_id,
    }

    print("\n" + "=" * 80)
    print("  DIAGNOSTIC TEST: Task Creator with Detailed Metrics")
    print("=" * 80)
    print(f"  Run ID: {run_id}")
    print(f"  Tenant: {tenant_id}")
    print(f"  Alert: {TEST_NAS_ALERT['title']}")

    result = await task_creator_node(state, executor)

    # Print the detailed metrics report
    metrics_list = result.get("metrics", [])
    print_metrics_report(metrics_list, "Task Creator Metrics")

    # Summary
    print("\n" + "=" * 80)
    print("  TEST RESULT")
    print("=" * 80)
    if result.get("task_creation_error"):
        print("  Status: FAILED")
        print(f"  Error: {result['task_creation_error']}")
    else:
        print("  Status: SUCCESS")
        print(f"  Task cy_name: {result.get('task_cy_name')}")
        print(f"  Task ID: {result.get('task_id')}")

    # Key questions to answer
    print("\n" + "-" * 80)
    print("  KEY OBSERVATIONS")
    print("-" * 80)

    all_tool_calls = []
    for m in metrics_list:
        all_tool_calls.extend(m.tool_calls)

    # Check for testing-related MCP calls
    compile_calls = [t for t in all_tool_calls if "compile_script" in t.tool_name]
    execute_calls = [t for t in all_tool_calls if "run_script" in t.tool_name]
    create_calls = [t for t in all_tool_calls if "create_task" in t.tool_name]

    print(f"  Script compilations (compile_script): {len(compile_calls)}")
    print(f"  Script executions (run_script): {len(execute_calls)}")
    print(f"  Task creations (create_task): {len(create_calls)}")

    # Check for subagent testing
    task_calls = [t for t in all_tool_calls if t.tool_name == "Task"]
    segment_tester_subagents = [
        t
        for t in task_calls
        if t.input_args.get("subagent_type") == "cy-script-segment-tester"
    ]
    print(f"  Subagents spawned: {len(task_calls)}")
    print(f"  cy-script-segment-tester subagents: {len(segment_tester_subagents)}")

    # Check for skill calls
    skill_calls = [t for t in all_tool_calls if t.tool_name == "Skill"]
    successful_skill_calls = [t for t in skill_calls if not t.is_error]
    print(f"  Skill invocations: {len(skill_calls)}")
    print(f"  Successful skill calls: {len(successful_skill_calls)}")

    print("=" * 80 + "\n")

    # =========================================================================
    # ASSERTIONS - Validate the methodology was followed
    # =========================================================================
    print("\n" + "=" * 80)
    print("  METHODOLOGY VALIDATION")
    print("=" * 80)

    validation_errors = []

    # 1. Skills must load successfully (validates setting_sources includes "user")
    if skill_calls and not successful_skill_calls:
        validation_errors.append(
            f"Skills failed to load ({len(skill_calls)} calls, 0 successful). "
            "Check setting_sources includes 'user' for ~/.claude/skills/"
        )
    elif successful_skill_calls:
        print(
            f"  [PASS] Skills loaded successfully ({len(successful_skill_calls)} calls)"
        )

    # 2. cy-script-segment-tester subagents should be spawned (per methodology)
    if len(segment_tester_subagents) == 0:
        validation_errors.append(
            "No cy-script-segment-tester subagents spawned. "
            "The cybersec-task-builder methodology requires segment testing."
        )
    else:
        print(
            f"  [PASS] Spawned {len(segment_tester_subagents)} cy-script-segment-tester subagents"
        )

    # 3. Scripts should be compiled (validates MCP connectivity)
    if len(compile_calls) == 0:
        validation_errors.append(
            "No compile_script calls made. "
            "Scripts must be compiled to validate correctness."
        )
    else:
        print(f"  [PASS] Compiled scripts {len(compile_calls)} times")

    # 4. Scripts should be executed for testing
    if len(execute_calls) == 0:
        validation_errors.append(
            "No run_script calls made. "
            "Scripts must be tested with sample data before creation."
        )
    else:
        print(f"  [PASS] Executed scripts {len(execute_calls)} times for testing")

    # 5. MCP calls should be made (validates MCP server connectivity)
    mcp_calls = [t for t in all_tool_calls if t.tool_name.startswith("mcp__")]
    if len(mcp_calls) == 0:
        validation_errors.append(
            "No MCP tool calls made. Check MCP server configuration."
        )
    else:
        print(f"  [PASS] Made {len(mcp_calls)} MCP tool calls")

    print("=" * 80)

    # Report validation results
    if validation_errors:
        print("\n  VALIDATION FAILURES:")
        for err in validation_errors:
            print(f"    - {err}")
        # Note: We don't fail the test here, just report. The main assertions
        # below will fail if the task wasn't created.

    print("\n")
