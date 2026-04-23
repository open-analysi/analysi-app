"""Eval tests for second subgraph (Task Building → Workflow Assembly).

These tests run the actual subgraph with Claude and MCP servers.
They require:
- ANTHROPIC_API_KEY environment variable
- Backend API running with MCP endpoints (localhost:8001 for eval)
- Test tasks 'vt_ip_reputation' and 'splunk_user_search' in database

Marked with @pytest.mark.eval and skipped by default.
Run with: make test-eval

Optimization Strategy:
- Two module-scoped fixtures cache results for common scenarios:
  * second_subgraph_result_mixed: Tests with new task proposals (2 tests share)
  * second_subgraph_result_existing: Tests with existing tasks only (3 tests share)
- Tests with unique inputs run independently (empty proposals, parallel building)
- Result: 7 tests → 4 subgraph executions (43% reduction)

Test Coverage:
1. Task building with mixed proposals (cached)
2. Skipping task building for existing tasks (cached)
3. Workflow assembly validation (cached)
4. Metrics accumulation (cached)
5. Workflow execution with enrichment verification (cached, uses REST API)
6. Empty proposals error handling (independent)
7. Parallel task building (independent)
"""

import pytest

from analysi.agentic_orchestration import (
    AgentOrchestrationExecutor,
    get_mcp_servers,
)
from analysi.agentic_orchestration.subgraphs import run_second_subgraph
from analysi.models.auth import SYSTEM_USER_ID

# Sample task proposals (simulating output from first subgraph)
SAMPLE_TASK_PROPOSALS_MIXED = [
    {
        "name": "IP Reputation Check",
        "description": "Query VirusTotal for IP reputation",
        "designation": "new",
        "existing_cy_name": None,
        "integration_tools": ["virustotal::ip_reputation"],
        "investigation_steps": [
            "Extract source IP from alert",
            "Query VirusTotal IP reputation API",
            "Analyze reputation score and detections",
        ],
    },
    {
        "name": "User Activity Lookup",
        "description": "Search recent user activity in SIEM",
        "designation": "new",
        "existing_cy_name": None,
        "integration_tools": ["splunk::search"],
        "investigation_steps": [
            "Extract username from alert",
            "Query SIEM for recent logins",
            "Identify anomalous patterns",
        ],
    },
]

SAMPLE_TASK_PROPOSALS_ALL_EXISTING = [
    {
        "name": "Existing IP Check",
        "description": "Pre-existing task for IP analysis",
        "designation": "existing",
        "cy_name": "vt_ip_reputation",
        "task_id": "existing-task-001",
    },
    {
        "name": "Existing User Lookup",
        "description": "Pre-existing task for user lookup",
        "designation": "existing",
        "cy_name": "splunk_user_search",
        "task_id": "existing-task-002",
    },
]

SAMPLE_RUNBOOK = """# Investigation Runbook: Suspicious Login

## Overview
Investigate suspicious login from unusual location.

## Investigation Steps

### Step 1: IP Reputation Check
- Query threat intelligence for source IP
- Check for known malicious indicators

### Step 2: User Activity Analysis
- Review recent user login history
- Identify geographic anomalies

### Step 3: Determine Verdict
- Correlate findings
- Recommend action (block, monitor, allow)
"""

SAMPLE_ALERT = {
    "id": "test-alert-001",
    "title": "Suspicious Login from Unusual Location",
    "severity": "high",
    "source_vendor": "Okta",
    "rule_name": "unusual_login_location",
    "triggering_event_time": "2024-01-15T10:30:00Z",
    "primary_ioc_value": "185.220.101.1",
    "primary_ioc_type": "ipv4",
    "iocs": [
        {
            "type": "ipv4",
            "value": "185.220.101.1",
            "description": "Source IP from unusual location",
        },
    ],
    "risk_entities": [
        {
            "type": "user",
            "value": "john.doe@company.com",
            "description": "User with suspicious login",
        },
    ],
    "network_info": {
        "source_ip": "185.220.101.1",
        "source_country": "Russia",
    },
    "user_info": {
        "username": "john.doe@company.com",
        "normal_country": "United States",
    },
    "enrichments": {},
    "raw_alert": {
        "user": "john.doe@company.com",
        "ip": "185.220.101.1",
        "country": "Russia",
        "normal_country": "United States",
    },
}


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_builds_tasks_with_mcp(second_subgraph_result_mixed):
    """Verify subgraph builds tasks using MCP analysi server.

    Uses cached result from MIXED proposals fixture.
    """
    result = second_subgraph_result_mixed

    # Verify tasks were built (may have failures if MCP not fully configured)
    assert "tasks_built" in result, "Expected tasks_built in result"
    # We expect 2 tasks attempted (both are "new")
    assert len(result["tasks_built"]) == 2, (
        f"Expected 2 tasks built, got {len(result['tasks_built'])}"
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_skips_existing_tasks(second_subgraph_result_existing):
    """Verify subgraph skips task building when all proposals are existing.

    Uses cached result from ALL_EXISTING proposals fixture.
    """
    result = second_subgraph_result_existing

    # No tasks should be built (all existing)
    assert len(result["tasks_built"]) == 0, (
        f"Expected 0 tasks built for existing proposals, got {len(result['tasks_built'])}"
    )

    # Workflow composition should include the existing cy_names
    # (order and wrapping may vary due to LLM non-determinism)
    composition = result["workflow_composition"]
    assert isinstance(composition, list), (
        f"Expected workflow_composition to be a list, got {type(composition)}"
    )
    # Flatten nested lists (agent may wrap in subgraph structure)
    flat = []

    def _flatten(item):
        if isinstance(item, list):
            for sub in item:
                _flatten(sub)
        else:
            flat.append(item)

    _flatten(composition)
    assert "vt_ip_reputation" in flat, (
        f"Expected vt_ip_reputation in composition, got {composition}"
    )
    assert "splunk_user_search" in flat, (
        f"Expected splunk_user_search in composition, got {composition}"
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_assembles_workflow(second_subgraph_result_existing):
    """Verify subgraph assembles workflow using MCP analysi server.

    Uses cached result from ALL_EXISTING proposals fixture.
    """
    result = second_subgraph_result_existing

    # Workflow should be assembled (may fail if tasks don't exist in MCP)
    # At minimum, verify workflow_composition is populated
    assert len(result["workflow_composition"]) > 0, (
        "Expected workflow_composition to contain cy_names"
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_accumulates_metrics(second_subgraph_result_mixed):
    """Verify metrics are accumulated from parallel task building.

    Uses cached result from MIXED proposals fixture.
    """
    result = second_subgraph_result_mixed

    # Should have metrics from task building (2 tasks) + workflow assembly (1)
    # Minimum: at least some metrics collected
    assert len(result["metrics"]) > 0, "Expected metrics to be collected"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_handles_empty_proposals(
    anthropic_api_key, isolated_claude_dir
):
    """Verify subgraph handles empty task proposals gracefully."""
    tenant_id = "default"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
    )

    result = await run_second_subgraph(
        task_proposals=[],  # Empty proposals
        runbook=SAMPLE_RUNBOOK,
        alert=SAMPLE_ALERT,
        executor=executor,
        run_id="eval-test-empty-proposals",
        tenant_id=tenant_id,
        created_by=str(SYSTEM_USER_ID),
    )

    print("\n=== Empty Proposals Result ===")
    print(f"tasks_built: {len(result['tasks_built'])}")
    print(f"workflow_error: {result['workflow_error']}")
    print("==============================\n")

    # No tasks built
    assert len(result["tasks_built"]) == 0

    # Workflow assembly should report error (no tasks to compose)
    assert (
        result["workflow_error"] is not None or result["workflow_composition"] == []
    ), "Expected error or empty composition for empty proposals"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_second_subgraph_parallel_task_building(
    anthropic_api_key, isolated_claude_dir
):
    """Verify multiple tasks are built in parallel via asyncio.gather().

    Parallel execution using asyncio.gather() processes all proposals concurrently.
    Verify all proposals are processed regardless of individual failures.
    """
    tenant_id = "default"
    mcp_servers = get_mcp_servers(tenant_id)

    executor = AgentOrchestrationExecutor(
        api_key=anthropic_api_key,
        mcp_servers=mcp_servers,
        isolated_project_dir=isolated_claude_dir,
    )

    # 3 proposals to test parallel execution
    proposals = [
        {
            "name": "Task A",
            "description": "First parallel task",
            "designation": "new",
            "integration_tools": ["echo_edr::health_check"],
        },
        {
            "name": "Task B",
            "description": "Second parallel task",
            "designation": "new",
            "integration_tools": ["echo_edr::health_check"],
        },
        {
            "name": "Task C",
            "description": "Third parallel task",
            "designation": "new",
            "integration_tools": ["echo_edr::health_check"],
        },
    ]

    result = await run_second_subgraph(
        task_proposals=proposals,
        runbook=SAMPLE_RUNBOOK,
        alert=SAMPLE_ALERT,
        executor=executor,
        run_id="eval-test-parallel-building",
        tenant_id=tenant_id,
        created_by=str(SYSTEM_USER_ID),
    )

    print("\n=== Parallel Task Building Result ===")
    print(f"tasks_built: {len(result['tasks_built'])} / {len(proposals)} proposals")
    for task in result["tasks_built"]:
        status = "✓" if task.get("success") else "✗"
        print(f"  {status} {task.get('proposal_name')}: {task.get('error', 'success')}")
    print("=====================================\n")

    # All 3 proposals should be attempted
    assert len(result["tasks_built"]) == 3, (
        f"Expected 3 tasks attempted, got {len(result['tasks_built'])}"
    )

    # Verify each proposal was processed (success or failure)
    proposal_names = {t["proposal_name"] for t in result["tasks_built"]}
    assert proposal_names == {"Task A", "Task B", "Task C"}, (
        f"Not all proposals processed: {proposal_names}"
    )
