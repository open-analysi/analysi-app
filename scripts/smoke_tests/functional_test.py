#!/usr/bin/env python3
"""Functional smoke test for the Analysi platform.

Exercises the full stack across three scenario groups:
  Original:  Integration -> Task -> Workflow -> Execution -> Cleanup
  Scenario A: Knowledge Units (Document + Table) -> Task reading KUs
  Scenario B: Alert analysis workflow with disposition artifact
  Scenario C: Detection routing -> Alert ingestion -> Full pipeline -> Disposition

Uses Global DNS (no API keys needed) to validate end-to-end functionality.

Usage:
    poetry run python scripts/smoke_tests/functional_test.py
    poetry run python scripts/smoke_tests/functional_test.py --setup-only
    # or via Makefile:
    make smoke-test
"""

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_HOST = os.getenv("BACKEND_API_HOST", "localhost")
API_PORT = os.getenv("BACKEND_API_EXTERNAL_PORT", "8001")
BASE_URL = f"http://{API_HOST}:{API_PORT}"
TENANT = "default"
API_KEY = os.getenv("ANALYSI_ADMIN_API_KEY", "dev-admin-api-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Unique suffix to avoid collisions
RUN_ID = uuid.uuid4().hex[:8]
INTEGRATION_ID = f"smoke-dns-{RUN_ID}"

# Polling config
POLL_INTERVAL = 2  # seconds
POLL_TIMEOUT = 60  # max seconds to wait
ANALYSIS_POLL_TIMEOUT = 120  # longer timeout for full pipeline

# Sample input used consistently across tasks, workflow, and execution
SAMPLE_INPUT = {"domain": "example.com", "enrichments": {}}

# Alert analysis sample input (NAS-like)
ALERT_SAMPLE_INPUT = {
    "title": f"Smoke Test Alert ({RUN_ID})",
    "severity": "high",
    "domain": "example.com",
    "enrichments": {},
}

# Track created resources for cleanup
created_resources: dict[str, list] = {
    "integration_ids": [],
    "task_ids": [],
    "workflow_ids": [],
    "ku_doc_ids": [],
    "ku_table_ids": [],
    "analysis_group_ids": [],
    "routing_rule_ids": [],
    "alert_ids": [],
}

# Track pass/fail
steps_passed = 0
steps_total = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def url(path: str) -> str:
    return f"{BASE_URL}/v1/{TENANT}{path}"


def check(resp: httpx.Response, step_name: str) -> dict:
    """Unwrap Sifnos envelope and assert success."""
    if resp.status_code >= 400:
        print(f"  FAIL [{resp.status_code}]: {resp.text[:500]}")
        raise SystemExit(1)
    body = resp.json()
    if "data" in body:
        return body["data"]
    return body


def poll_status(
    status_url: str, client: httpx.Client, timeout: int = POLL_TIMEOUT
) -> str:
    """Poll until terminal status or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        resp = client.get(status_url, headers=HEADERS)
        data = check(resp, "poll")
        status = data.get("status", "unknown")
        if status in ("completed", "succeeded", "failed", "error", "cancelled"):
            return status
        time.sleep(POLL_INTERVAL)
    print(f"  FAIL: Timed out after {timeout}s waiting for completion")
    raise SystemExit(1)


def step(name: str):
    """Print step header and increment counter."""
    global steps_total
    steps_total += 1
    print(f"Step {steps_total}: {name}")


def passed():
    global steps_passed
    steps_passed += 1


# ---------------------------------------------------------------------------
# Original Test Steps
# ---------------------------------------------------------------------------
def create_integration(client: httpx.Client) -> str:
    """(a) Create a Global DNS integration instance."""
    step("Create Global DNS integration")
    resp = client.post(
        url("/integrations"),
        headers=HEADERS,
        json={
            "integration_type": "global_dns",
            "integration_id": INTEGRATION_ID,
            "name": f"Smoke Test DNS ({RUN_ID})",
            "description": "Temporary integration for smoke testing",
            "enabled": True,
            "settings": {"timeout": 10},
        },
    )
    data = check(resp, "create integration")
    iid = data["integration_id"]
    assert iid == INTEGRATION_ID, f"Expected {INTEGRATION_ID}, got {iid}"
    assert data["enabled"] is True
    created_resources["integration_ids"].append(iid)
    print(f"  OK: integration_id={iid}")
    passed()
    return iid


def health_check(client: httpx.Client, integration_id: str) -> None:
    """(b) Execute health_check connector and verify DNS resolution works."""
    step("Run health check on integration")
    resp = client.post(
        url(f"/integrations/{integration_id}/tools/health_check/execute"),
        headers=HEADERS,
        json={"arguments": {}},
    )
    data = check(resp, "health check")
    status = data.get("status")
    assert status == "success", f"Health check returned status={status}, data={data}"
    output = data.get("output", {})
    healthy = output.get("healthy")
    assert healthy is True, f"healthy={healthy}, expected True"
    print(f"  OK: healthy={healthy}, dns_server={output.get('dns_server')}")
    passed()


def create_task_1(client: httpx.Client) -> str:
    """(a) Create Task 1: DNS domain resolver."""
    step("Create Task 1 -- DNS Domain Resolver")
    script = """\
# Smoke test task: resolve a domain using Global DNS
domain = input.domain ?? "example.com"
result = app::global_dns::resolve_domain(domain=domain)
enrichment = {
    "domain": domain,
    "resolved_ips": result.records ?? [],
    "dns_status": result.status ?? "unknown"
}
return enrich_alert(input, enrichment)
"""
    resp = client.post(
        url("/tasks"),
        headers=HEADERS,
        json={
            "name": f"Smoke: DNS Resolver ({RUN_ID})",
            "script": script,
            "app": "global_dns",
            "function": "enrichment",
            "scope": "processing",
            "mode": "saved",
            "data_samples": [SAMPLE_INPUT],
        },
    )
    data = check(resp, "create task 1")
    task_id = data["id"]
    cy_name = data["cy_name"]
    assert task_id, "No task_id returned"
    assert cy_name, "No cy_name returned"
    created_resources["task_ids"].append(task_id)
    print(f"  OK: task_id={task_id}, cy_name={cy_name}")
    passed()
    return cy_name


def create_task_2(client: httpx.Client, task1_cy: str) -> str:
    """(a) Create Task 2: summarize DNS results from Task 1."""
    step("Create Task 2 -- DNS Summary")
    script = f"""\
# Smoke test task: summarize DNS resolution results
domain = input.domain ?? "unknown"

# Read enrichment from the DNS resolver task
dns_data = input.enrichments.{task1_cy} ?? {{}}
ips = dns_data.resolved_ips ?? []
status = dns_data.dns_status ?? "unknown"

summary = "Domain " + domain + " resolved to " + str(ips) + " (status: " + status + ")"

enrichment = {{
    "summary": summary,
    "ip_count": len(ips)
}}
return enrich_alert(input, enrichment)
"""
    resp = client.post(
        url("/tasks"),
        headers=HEADERS,
        json={
            "name": f"Smoke: DNS Summary ({RUN_ID})",
            "script": script,
            "function": "summarization",
            "scope": "output",
            "mode": "saved",
            "data_samples": [
                {
                    "domain": "example.com",
                    "enrichments": {
                        task1_cy: {
                            "domain": "example.com",
                            "resolved_ips": ["93.184.216.34"],
                            "dns_status": "success",
                        }
                    },
                }
            ],
        },
    )
    data = check(resp, "create task 2")
    task_id = data["id"]
    cy_name = data["cy_name"]
    assert task_id, "No task_id returned"
    assert cy_name, "No cy_name returned"
    created_resources["task_ids"].append(task_id)
    print(f"  OK: task_id={task_id}, cy_name={cy_name}")
    passed()
    return cy_name


def compose_workflow(client: httpx.Client, task1_cy: str, task2_cy: str) -> str:
    """(a) Compose and save a workflow: Task1 -> Task2."""
    step("Compose workflow (Task1 -> Task2)")
    resp = client.post(
        url("/workflows/compose"),
        headers=HEADERS,
        json={
            "composition": [task1_cy, task2_cy],
            "name": f"Smoke: DNS Pipeline ({RUN_ID})",
            "description": "Smoke test: resolve domain then summarize",
            "execute": True,
        },
    )
    data = check(resp, "compose workflow")
    workflow_id = data.get("workflow_id")
    status = data.get("status")
    assert workflow_id, (
        f"No workflow_id returned. status={status}, errors={data.get('errors', [])}"
    )
    created_resources["workflow_ids"].append(workflow_id)

    # Patch workflow with real data_samples so UI can run it too
    patch_resp = client.patch(
        url(f"/workflows/{workflow_id}"),
        headers=HEADERS,
        json={"data_samples": [SAMPLE_INPUT]},
    )
    if patch_resp.status_code >= 400:
        print(f"  WARN: failed to patch data_samples: {patch_resp.status_code}")

    print(f"  OK: workflow_id={workflow_id}, status={status}")
    passed()
    return workflow_id


def execute_workflow(client: httpx.Client, workflow_id: str, task1_cy: str) -> str:
    """(c) Execute the workflow, wait for completion, validate results."""
    step("Execute workflow and validate results")
    resp = client.post(
        url(f"/workflows/{workflow_id}/run"),
        headers=HEADERS,
        json={"input_data": SAMPLE_INPUT},
    )
    data = check(resp, "start workflow run")
    run_id = data.get("workflow_run_id")
    assert run_id, f"No workflow_run_id returned: {data}"
    print(f"  Started: workflow_run_id={run_id}")

    # Poll for completion
    print("  Polling for completion...", end="", flush=True)
    status = poll_status(url(f"/workflow-runs/{run_id}/status"), client)
    print(f" {status}")
    assert status in ("completed", "succeeded"), f"Workflow ended with status={status}"

    # Validate node results
    nodes_resp = client.get(url(f"/workflow-runs/{run_id}/nodes"), headers=HEADERS)
    nodes = check(nodes_resp, "get nodes")
    assert isinstance(nodes, list), f"Expected list of nodes, got {type(nodes)}"
    assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"

    # Validate both nodes completed
    for node in nodes:
        node_status = node.get("status")
        assert node_status == "completed", (
            f"Node {node.get('node_label', '?')} status={node_status}, "
            f"expected completed"
        )

    # Validate Task 1 produced DNS enrichment
    task1_node = nodes[0]
    task1_result = task1_node.get("output_data", {}).get("result", {})
    task1_enrichments = task1_result.get("enrichments", {})
    dns_enrichment = task1_enrichments.get(task1_cy, {})
    resolved_ips = dns_enrichment.get("resolved_ips", [])
    assert len(resolved_ips) > 0, (
        f"Task 1 should have resolved IPs, got enrichments={task1_enrichments}"
    )
    print(f"  Task 1: resolved example.com -> {resolved_ips}")

    # Validate Task 2 produced summary
    task2_node = nodes[1]
    task2_result = task2_node.get("output_data", {}).get("result", {})
    task2_enrichments = task2_result.get("enrichments", {})
    # Find the summary enrichment (cy_name has RUN_ID suffix)
    summary_keys = [k for k in task2_enrichments if "summary" in k]
    assert len(summary_keys) > 0, (
        f"Task 2 should have summary enrichment, got keys={list(task2_enrichments.keys())}"
    )
    summary_data = task2_enrichments[summary_keys[0]]
    assert summary_data.get("ip_count", 0) > 0, (
        f"Expected ip_count > 0, got {summary_data}"
    )
    print(f"  Task 2: summary ip_count={summary_data['ip_count']}")

    print("  OK: workflow results validated")
    passed()
    return run_id


# ---------------------------------------------------------------------------
# Scenario A: Knowledge Units + Task Reading KUs
# ---------------------------------------------------------------------------
def create_document_ku(client: httpx.Client) -> str:
    """Create a Document Knowledge Unit with incident response content."""
    step("Create Document KU -- IR Playbook")
    doc_name = f"Smoke: IR Playbook ({RUN_ID})"
    resp = client.post(
        url("/knowledge-units/documents"),
        headers=HEADERS,
        json={
            "name": doc_name,
            "description": "Smoke test incident response playbook",
            "content": (
                "# Incident Response Playbook\n\n"
                "## Step 1: Identify\n"
                "Check source IP 192.168.1.100 against the allowlist.\n\n"
                "## Step 2: Contain\n"
                "Block the IP at the firewall if not in the allowlist.\n\n"
                "## Step 3: Eradicate\n"
                "Remove any persistence mechanisms found.\n"
            ),
            "document_type": "markdown",
            "status": "enabled",
        },
    )
    data = check(resp, "create document KU")
    ku_id = data["id"]
    assert ku_id, "No KU id returned"
    created_resources["ku_doc_ids"].append(ku_id)
    print(f"  OK: doc_id={ku_id}, name={doc_name}")
    passed()
    return doc_name


def create_table_ku(client: httpx.Client) -> str:
    """Create a Table Knowledge Unit with IP allowlist data."""
    step("Create Table KU -- IP Allowlist")
    table_name = f"Smoke: IP Allowlist ({RUN_ID})"
    resp = client.post(
        url("/knowledge-units/tables"),
        headers=HEADERS,
        json={
            "name": table_name,
            "description": "Smoke test IP allowlist for incident response",
            "schema": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string"},
                    "severity": {"type": "string"},
                    "action": {"type": "string"},
                },
            },
            "content": {
                "rows": [
                    {"ip": "192.168.1.100", "severity": "high", "action": "block"},
                    {"ip": "10.0.0.1", "severity": "low", "action": "monitor"},
                    {
                        "ip": "172.16.0.50",
                        "severity": "medium",
                        "action": "investigate",
                    },
                ]
            },
            "row_count": 3,
            "column_count": 3,
            "status": "enabled",
        },
    )
    data = check(resp, "create table KU")
    ku_id = data["id"]
    assert ku_id, "No KU id returned"
    created_resources["ku_table_ids"].append(ku_id)
    print(f"  OK: table_id={ku_id}, name={table_name}")
    passed()
    return table_name


def create_ku_reader_task(client: httpx.Client, doc_name: str, table_name: str) -> str:
    """Create a Cy task that reads from both KUs and combines them."""
    step("Create Task -- KU Reader (Document + Table)")
    script = f"""\
# Read the incident response document
doc = document_read("{doc_name}")

# Read the IP allowlist table
rows = table_read("{table_name}")

# Collect IPs from table rows
all_ips = []
for (row in rows) {{
    all_ips = all_ips + [row.ip ?? "unknown"]
}}

enrichment = {{
    "document_length": len(doc),
    "table_row_count": len(rows),
    "collected_ips": all_ips,
    "summary": "Read playbook (" + str(len(doc)) + " chars) and " + str(len(rows)) + " table rows"
}}
return enrich_alert(input, enrichment)
"""
    resp = client.post(
        url("/tasks"),
        headers=HEADERS,
        json={
            "name": f"Smoke: KU Reader ({RUN_ID})",
            "script": script,
            "function": "enrichment",
            "scope": "processing",
            "mode": "saved",
            "data_samples": [SAMPLE_INPUT],
        },
    )
    data = check(resp, "create KU reader task")
    task_id = data["id"]
    cy_name = data["cy_name"]
    assert task_id, "No task_id returned"
    created_resources["task_ids"].append(task_id)
    print(f"  OK: task_id={task_id}, cy_name={cy_name}")
    passed()
    return cy_name


def execute_ku_task(client: httpx.Client, ku_reader_cy: str) -> None:
    """Compose a single-task workflow, execute it, and verify KU data was read."""
    step("Execute KU Reader task and validate KU access")

    # Compose a single-task workflow to execute
    resp = client.post(
        url("/workflows/compose"),
        headers=HEADERS,
        json={
            "composition": [ku_reader_cy],
            "name": f"Smoke: KU Test Pipeline ({RUN_ID})",
            "description": "Smoke test: verify Knowledge Unit access from tasks",
            "execute": True,
        },
    )
    data = check(resp, "compose KU workflow")
    workflow_id = data.get("workflow_id")
    assert workflow_id, f"No workflow_id returned: {data}"
    created_resources["workflow_ids"].append(workflow_id)

    # Execute the workflow
    run_resp = client.post(
        url(f"/workflows/{workflow_id}/run"),
        headers=HEADERS,
        json={"input_data": SAMPLE_INPUT},
    )
    run_data = check(run_resp, "start KU workflow run")
    run_id = run_data.get("workflow_run_id")
    assert run_id, f"No workflow_run_id: {run_data}"

    # Poll for completion
    print("  Polling for completion...", end="", flush=True)
    status = poll_status(url(f"/workflow-runs/{run_id}/status"), client)
    print(f" {status}")
    assert status in ("completed", "succeeded"), f"KU workflow status={status}"

    # Validate the task read both KUs
    nodes_resp = client.get(url(f"/workflow-runs/{run_id}/nodes"), headers=HEADERS)
    nodes = check(nodes_resp, "get KU workflow nodes")
    assert len(nodes) == 1, f"Expected 1 node, got {len(nodes)}"

    node = nodes[0]
    assert node.get("status") == "completed", f"Node status={node.get('status')}"

    result = node.get("output_data", {}).get("result", {})
    enrichments = result.get("enrichments", {})
    # Find the KU reader enrichment
    ku_keys = [k for k in enrichments if "ku_reader" in k]
    assert len(ku_keys) > 0, (
        f"No KU reader enrichment found. Keys: {list(enrichments.keys())}"
    )
    ku_data = enrichments[ku_keys[0]]

    assert ku_data.get("document_length", 0) > 0, f"Document was empty: {ku_data}"
    assert ku_data.get("table_row_count", 0) == 3, f"Expected 3 table rows: {ku_data}"
    assert len(ku_data.get("collected_ips", [])) == 3, (
        f"Expected 3 collected IPs from table: {ku_data}"
    )
    print(
        f"  Doc length: {ku_data['document_length']}, "
        f"Table rows: {ku_data['table_row_count']}, "
        f"Collected IPs: {ku_data['collected_ips']}"
    )
    print("  OK: KU reader task successfully accessed both Knowledge Units")
    passed()


# ---------------------------------------------------------------------------
# Scenario B: Alert Analysis Workflow with Disposition
# ---------------------------------------------------------------------------
def create_disposition_task(client: httpx.Client, enrichment_task_cy: str) -> str:
    """Create a task that produces a disposition artifact."""
    step("Create Task -- Disposition (store_artifact)")
    script = f"""\
# Read DNS enrichment from previous task
dns_data = input.enrichments.{enrichment_task_cy} ?? {{}}
domain = dns_data.domain ?? input.domain ?? "unknown"
ips = dns_data.resolved_ips ?? []

# Determine disposition based on enrichment
disposition_result = "True Positive (Malicious) / Confirmed Compromise"

# Store as artifact for workflow visibility
artifact_id = store_artifact(
    "Disposition",
    disposition_result,
    {{}},
    "alert_disposition"
)

enrichment = {{
    "disposition": disposition_result,
    "artifact_id": artifact_id,
    "analyzed_domain": domain,
    "ip_count": len(ips)
}}
return enrich_alert(input, enrichment)
"""
    resp = client.post(
        url("/tasks"),
        headers=HEADERS,
        json={
            "name": f"Smoke: Disposition ({RUN_ID})",
            "script": script,
            "function": "disposition",
            "scope": "output",
            "mode": "saved",
            "data_samples": [
                {
                    "domain": "example.com",
                    "enrichments": {
                        enrichment_task_cy: {
                            "domain": "example.com",
                            "resolved_ips": ["93.184.216.34"],
                            "dns_status": "success",
                        }
                    },
                }
            ],
        },
    )
    data = check(resp, "create disposition task")
    task_id = data["id"]
    cy_name = data["cy_name"]
    assert task_id, "No task_id returned"
    created_resources["task_ids"].append(task_id)
    print(f"  OK: task_id={task_id}, cy_name={cy_name}")
    passed()
    return cy_name


def compose_analysis_workflow(
    client: httpx.Client, enrichment_cy: str, disposition_cy: str
) -> str:
    """Compose an alert analysis workflow: Enrichment -> Disposition."""
    step("Compose alert analysis workflow (Enrichment -> Disposition)")
    resp = client.post(
        url("/workflows/compose"),
        headers=HEADERS,
        json={
            "composition": [enrichment_cy, disposition_cy],
            "name": f"workflow-1-{RUN_ID}",
            "description": "Smoke test: alert analysis with disposition artifact",
            "execute": True,
        },
    )
    data = check(resp, "compose analysis workflow")
    workflow_id = data.get("workflow_id")
    assert workflow_id, f"No workflow_id: {data}"
    created_resources["workflow_ids"].append(workflow_id)

    # Patch with alert-like data_samples
    client.patch(
        url(f"/workflows/{workflow_id}"),
        headers=HEADERS,
        json={"data_samples": [ALERT_SAMPLE_INPUT]},
    )

    print(f"  OK: workflow_id={workflow_id}, name=workflow-1-{RUN_ID}")
    passed()
    return workflow_id


def execute_analysis_workflow(client: httpx.Client, workflow_id: str) -> str:
    """Execute the analysis workflow and verify disposition artifact is created."""
    step("Execute analysis workflow and verify disposition artifact")
    resp = client.post(
        url(f"/workflows/{workflow_id}/run"),
        headers=HEADERS,
        json={"input_data": ALERT_SAMPLE_INPUT},
    )
    data = check(resp, "start analysis workflow run")
    run_id = data.get("workflow_run_id")
    assert run_id, f"No workflow_run_id: {data}"

    # Poll for completion
    print("  Polling for completion...", end="", flush=True)
    status = poll_status(url(f"/workflow-runs/{run_id}/status"), client)
    print(f" {status}")
    assert status in ("completed", "succeeded"), f"Analysis workflow status={status}"

    # Verify disposition artifact exists
    artifacts_resp = client.get(
        url("/artifacts"),
        headers=HEADERS,
        params={"workflow_run_id": run_id},
    )
    if artifacts_resp.status_code == 200:
        artifacts = artifacts_resp.json().get("data", [])
        disposition_artifacts = [a for a in artifacts if a.get("name") == "Disposition"]
        assert len(disposition_artifacts) > 0, (
            f"No Disposition artifact found for workflow_run {run_id}. "
            f"Found artifacts: {[a.get('name') for a in artifacts]}"
        )
        print(f"  Disposition artifact found: id={disposition_artifacts[0]['id']}")
    else:
        print(
            f"  WARN: Could not query artifacts (status={artifacts_resp.status_code})"
        )

    print("  OK: analysis workflow completed with disposition artifact")
    passed()
    return run_id


# ---------------------------------------------------------------------------
# Scenario C: Detection -> Alert -> Full Pipeline -> Disposition
# ---------------------------------------------------------------------------
def create_analysis_group(client: httpx.Client) -> str:
    """Create an analysis group for the detection."""
    step("Create Analysis Group for detection")
    detection_title = f"Detection-1-{RUN_ID}"
    resp = client.post(
        url("/analysis-groups"),
        headers=HEADERS,
        json={"title": detection_title},
    )
    data = check(resp, "create analysis group")
    group_id = data["id"]
    assert group_id, "No analysis group id returned"
    created_resources["analysis_group_ids"].append(group_id)
    print(f"  OK: group_id={group_id}, title={detection_title}")
    passed()
    return group_id


def create_routing_rule(client: httpx.Client, group_id: str, workflow_id: str) -> str:
    """Create an alert routing rule linking the analysis group to the workflow."""
    step("Create Alert Routing Rule (Detection -> Workflow)")
    resp = client.post(
        url("/alert-routing-rules"),
        headers=HEADERS,
        json={
            "analysis_group_id": group_id,
            "workflow_id": workflow_id,
        },
    )
    data = check(resp, "create routing rule")
    rule_id = data["id"]
    assert rule_id, "No routing rule id returned"
    created_resources["routing_rule_ids"].append(rule_id)
    print(f"  OK: rule_id={rule_id}, group->workflow={group_id}->{workflow_id}")
    passed()
    return rule_id


def ingest_and_analyze_alert(client: httpx.Client) -> tuple[str, str]:
    """Create an alert with the detection's rule_name and trigger analysis."""
    step("Ingest alert and trigger analysis pipeline")
    detection_title = f"Detection-1-{RUN_ID}"

    # Create alert
    alert_resp = client.post(
        url("/alerts"),
        headers=HEADERS,
        json={
            "title": f"Smoke Test Alert ({RUN_ID})",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": json.dumps(
                {
                    "source": "smoke-test",
                    "run_id": RUN_ID,
                    "message": "Test alert for disposition pipeline",
                }
            ),
            "source_product": "Smoke Test",
            "rule_name": detection_title,
            "primary_risk_entity_value": "test-user@example.com",
            "primary_risk_entity_type": "user",
            "primary_ioc_value": "example.com",
            "primary_ioc_type": "domain",
        },
    )
    alert_data = check(alert_resp, "create alert")
    alert_id = alert_data["alert_id"]
    assert alert_id, "No alert_id returned"
    created_resources["alert_ids"].append(alert_id)
    print(f"  Alert created: alert_id={alert_id}, rule_name={detection_title}")

    # Trigger analysis
    analyze_resp = client.post(
        url(f"/alerts/{alert_id}/analyze"),
        headers=HEADERS,
    )
    analyze_data = check(analyze_resp, "trigger analysis")
    analysis_id = analyze_data.get("analysis_id")
    assert analysis_id, f"No analysis_id returned: {analyze_data}"
    print(f"  Analysis triggered: analysis_id={analysis_id}")

    passed()
    return alert_id, analysis_id


def verify_alert_disposition(
    client: httpx.Client, alert_id: str, analysis_id: str
) -> None:
    """Poll until analysis completes, then verify the alert disposition."""
    step("Verify alert disposition after pipeline completion")

    # Poll analysis progress until terminal state
    print("  Polling analysis progress...", end="", flush=True)
    start = time.time()
    final_status = None
    while time.time() - start < ANALYSIS_POLL_TIMEOUT:
        resp = client.get(
            url(f"/alerts/{alert_id}/analysis/progress"),
            headers=HEADERS,
        )
        if resp.status_code >= 400:
            # Analysis might not be visible yet, retry
            time.sleep(POLL_INTERVAL)
            continue
        data = resp.json().get("data", {})
        status = data.get("status", "unknown")
        current_step = data.get("current_step", "unknown")
        print(f" [{current_step}]", end="", flush=True)

        if status in ("completed", "failed", "error", "cancelled"):
            final_status = status
            break
        time.sleep(POLL_INTERVAL)

    print(f" -> {final_status}")
    assert final_status == "completed", (
        f"Analysis did not complete. Final status: {final_status}"
    )

    # Verify alert disposition
    alert_resp = client.get(url(f"/alerts/{alert_id}"), headers=HEADERS)
    alert_data = check(alert_resp, "get alert detail")

    disposition_name = alert_data.get("current_disposition_display_name")
    disposition_category = alert_data.get("current_disposition_category")
    analysis_status = alert_data.get("analysis_status")

    assert analysis_status == "completed", (
        f"Alert analysis_status={analysis_status}, expected 'completed'"
    )
    assert disposition_name == "Confirmed Compromise", (
        f"Alert disposition_display_name='{disposition_name}', "
        f"expected 'Confirmed Compromise'"
    )
    assert "True Positive" in (disposition_category or ""), (
        f"Alert disposition_category='{disposition_category}', "
        f"expected to contain 'True Positive'"
    )

    print(f"  Alert analysis_status: {analysis_status}")
    print(f"  Disposition: {disposition_category} / {disposition_name}")
    print("  OK: alert disposition matches expected value")
    passed()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def cleanup_and_verify(client: httpx.Client) -> None:  # noqa: C901
    """Remove all resources and verify they're gone."""
    step("Cleanup and verify")
    all_clean = True

    # Delete in reverse dependency order
    for rule_id in created_resources["routing_rule_ids"]:
        resp = client.delete(url(f"/alert-routing-rules/{rule_id}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(f"  WARN: Routing rule {rule_id} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted routing rule {rule_id}")

    for group_id in created_resources["analysis_group_ids"]:
        resp = client.delete(url(f"/analysis-groups/{group_id}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(
                f"  WARN: Analysis group {group_id} delete returned {resp.status_code}"
            )
            all_clean = False
        else:
            print(f"  Deleted analysis group {group_id}")

    for wf_id in created_resources["workflow_ids"]:
        resp = client.delete(url(f"/workflows/{wf_id}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(f"  WARN: Workflow {wf_id} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted workflow {wf_id}")

    for task_id in created_resources["task_ids"]:
        resp = client.delete(url(f"/tasks/{task_id}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(f"  WARN: Task {task_id} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted task {task_id}")

    for iid in created_resources["integration_ids"]:
        resp = client.delete(url(f"/integrations/{iid}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(f"  WARN: Integration {iid} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted integration {iid}")

    for ku_id in created_resources["ku_doc_ids"]:
        resp = client.delete(
            url(f"/knowledge-units/documents/{ku_id}"), headers=HEADERS
        )
        if resp.status_code not in (204, 404):
            print(f"  WARN: Document KU {ku_id} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted document KU {ku_id}")

    for ku_id in created_resources["ku_table_ids"]:
        resp = client.delete(url(f"/knowledge-units/tables/{ku_id}"), headers=HEADERS)
        if resp.status_code not in (204, 404):
            print(f"  WARN: Table KU {ku_id} delete returned {resp.status_code}")
            all_clean = False
        else:
            print(f"  Deleted table KU {ku_id}")

    # Note: alerts are not deleted — they are isolated by RUN_ID
    # and will not interfere with other tests.

    # Verify key resources are gone
    for wf_id in created_resources["workflow_ids"]:
        resp = client.get(url(f"/workflows/{wf_id}"), headers=HEADERS)
        if resp.status_code != 404:
            print(f"  FAIL: Workflow {wf_id} still exists after delete!")
            all_clean = False

    for task_id in created_resources["task_ids"]:
        resp = client.get(url(f"/tasks/{task_id}"), headers=HEADERS)
        if resp.status_code != 404:
            print(f"  FAIL: Task {task_id} still exists after delete!")
            all_clean = False

    for iid in created_resources["integration_ids"]:
        resp = client.get(url(f"/integrations/{iid}"), headers=HEADERS)
        if resp.status_code != 404:
            print(f"  FAIL: Integration {iid} still exists after delete!")
            all_clean = False

    assert all_clean, "Some resources were not properly cleaned up"
    print("  OK: all resources verified gone")
    passed()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(setup_only: bool = False) -> None:
    mode = "setup-only" if setup_only else "full"
    print("=== Analysi Functional Smoke Test ===")
    print(f"API: {BASE_URL}")
    print(f"Run ID: {RUN_ID}  Mode: {mode}")
    print()

    client = httpx.Client(timeout=30.0)

    try:
        # Quick connectivity check
        try:
            resp = client.get(f"{BASE_URL}/healthz")
            if resp.status_code >= 500:
                print(f"FAIL: API health check returned {resp.status_code}")
                raise SystemExit(1)
        except httpx.ConnectError:
            print(f"FAIL: Cannot connect to API at {BASE_URL}")
            print("  Is the API running? Try: make up")
            raise SystemExit(1)

        # === Original Scenario: Integration -> Task -> Workflow ===
        print("--- Original: Integration + Task + Workflow ---")
        iid = create_integration(client)
        health_check(client, iid)
        task1_cy = create_task_1(client)
        task2_cy = create_task_2(client, task1_cy)
        wf_id = compose_workflow(client, task1_cy, task2_cy)

        if setup_only:
            print(f"\n=== SETUP COMPLETE ({steps_passed}/{steps_total} passed) ===")
            print(f"  Integration: {iid}")
            print(f"  Task 1: {task1_cy}")
            print(f"  Task 2: {task2_cy}")
            print(f"  Workflow: {wf_id}")
            return

        execute_workflow(client, wf_id, task1_cy)

        # === Scenario A: Knowledge Units + Task ===
        print("\n--- Scenario A: Knowledge Units + Task ---")
        doc_name = create_document_ku(client)
        table_name = create_table_ku(client)
        ku_reader_cy = create_ku_reader_task(client, doc_name, table_name)
        execute_ku_task(client, ku_reader_cy)

        # === Scenario B: Alert Analysis Workflow with Disposition ===
        print("\n--- Scenario B: Alert Analysis Workflow ---")
        disposition_cy = create_disposition_task(client, task1_cy)
        analysis_wf_id = compose_analysis_workflow(client, task1_cy, disposition_cy)
        execute_analysis_workflow(client, analysis_wf_id)

        # === Scenario C: Detection -> Alert -> Pipeline ===
        print("\n--- Scenario C: Detection -> Alert -> Pipeline ---")
        group_id = create_analysis_group(client)
        create_routing_rule(client, group_id, analysis_wf_id)
        alert_id, analysis_id = ingest_and_analyze_alert(client)
        verify_alert_disposition(client, alert_id, analysis_id)

        # === Cleanup ===
        print("\n--- Cleanup ---")
        cleanup_and_verify(client)

        print(f"\n=== ALL {steps_passed}/{steps_total} STEPS PASSED ===")

    except (SystemExit, AssertionError) as e:
        print(f"\n=== SMOKE TEST FAILED ({steps_passed}/{steps_total} passed) ===")
        if isinstance(e, AssertionError):
            print(f"  Assertion: {e}")
        # Best-effort cleanup on failure
        if not setup_only:
            print("\nBest-effort cleanup:")
            for rule_id in created_resources["routing_rule_ids"]:
                client.delete(url(f"/alert-routing-rules/{rule_id}"), headers=HEADERS)
            for group_id in created_resources["analysis_group_ids"]:
                client.delete(url(f"/analysis-groups/{group_id}"), headers=HEADERS)
            for wf_id in created_resources["workflow_ids"]:
                client.delete(url(f"/workflows/{wf_id}"), headers=HEADERS)
            for tid in created_resources["task_ids"]:
                client.delete(url(f"/tasks/{tid}"), headers=HEADERS)
            for iid in created_resources["integration_ids"]:
                client.delete(url(f"/integrations/{iid}"), headers=HEADERS)
            for ku_id in created_resources["ku_doc_ids"]:
                client.delete(
                    url(f"/knowledge-units/documents/{ku_id}"), headers=HEADERS
                )
            for ku_id in created_resources["ku_table_ids"]:
                client.delete(url(f"/knowledge-units/tables/{ku_id}"), headers=HEADERS)
        raise SystemExit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main(setup_only="--setup-only" in sys.argv)
