"""Generated tool docstrings for the product chatbot.

Tool docstrings are generated at import time from actual model enums, preventing
the drift that caused bugs (e.g., 'informational' vs 'info', fake 'enrichment'
function type). Each constant is a complete docstring ready to be used as a
Pydantic AI tool description.
"""

from analysi.models.task import TaskFunction
from analysi.schemas.alert import AlertSeverity, AlertStatus


def _enum_values(enum_cls: type) -> str:
    """Comma-separated enum values for embedding in docstrings."""
    return ", ".join(e.value for e in enum_cls)


def _class_constant_values(cls: type) -> str:
    """Comma-separated string constant values from a plain class (not an enum)."""
    return ", ".join(
        v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)
    )


# --- Alert tools ---

SEARCH_ALERTS_DOC = f"""\
Search and list alerts. Call with no arguments to get recent alerts.
Use title_filter to find alerts by name (e.g., "SQL Injection", "PowerShell").
Use ioc_filter to find alerts containing a specific IOC value — IP address, domain, \
URL, or file hash (e.g., ioc_filter="167.99.169.17" or ioc_filter="evil.com"). \
Searches observables, evidences, and actor fields.
When the user mentions an alert by name or asks about "the alerts" or "our alerts",
always search first rather than asking for an ID.

Args:
    severity: Filter by severity ({_enum_values(AlertSeverity)}).
    status: Filter by analysis status ({_enum_values(AlertStatus)}).
    source_vendor: Filter by source vendor name.
    title_filter: Text to search alert titles (case-insensitive, supports multi-word).
    ioc_filter: Search for alerts containing this IOC value (IP, domain, hash, URL).
    limit: Max results to return (default 10, max 20)."""

GET_ALERT_DOC = """\
Get alert details by ID. Returns severity, analysis status, analysis summary,
entities, and IOCs.

Args:
    alert_id: The alert UUID."""

# --- Task tools ---

LIST_TASKS_DOC = f"""\
List available tasks with optional filters.

Use name_filter to search task names (e.g., name_filter="Splunk").
Use categories to filter by category tag (e.g., categories=["Foundation"]
for all foundation tasks, or categories=["Splunk"] for Splunk-related tasks).
Tasks have categories like Foundation, Examples, Splunk, VirusTotal, LDAP,
ProxyNotShell, enrichment, reasoning, etc.

Args:
    function: Filter by function type ({_class_constant_values(TaskFunction)}).
    name_filter: Text to search task names (case-insensitive substring match).
    categories: List of category tags to filter by (AND logic).
    limit: Max results to return (default 50, max 50)."""

GET_TASK_DOC = """\
Get task details by ID or cy_name. Returns name, description,
function type, and categories.

Args:
    task_identifier: Task UUID or cy_name (e.g., "phishing_triage")."""

# --- Workflow tools ---

LIST_WORKFLOWS_DOC = """\
List available workflows with optional name search.

Args:
    name_filter: Optional text to filter workflow names.
    limit: Max results to return (default 20, max 50)."""

GET_WORKFLOW_DOC = """\
Get workflow definition by ID. Returns name, description, nodes, and edges.

Args:
    workflow_id: The workflow UUID."""

# --- Integration tools ---

LIST_INTEGRATIONS_DOC = "List all configured integrations with their health status."

GET_INTEGRATION_HEALTH_DOC = """\
Check an integration's configuration and health status.

Args:
    integration_id: The integration identifier."""

# --- Execution tools ---

GET_WORKFLOW_RUN_DOC = """\
Get workflow execution details including status and timing.

Args:
    workflow_run_id: The workflow run UUID."""

LIST_WORKFLOW_RUNS_DOC = """\
List recent workflow runs. Use this for "show recent workflow runs",
"which workflows ran today", or "any failed workflow runs".

Args:
    status: Optional filter by status (pending, running, completed, failed, cancelled).
    limit: Max results to return (default 10, max 20)."""

GET_TASK_RUN_DOC = """\
Get task execution details including status and output.

Args:
    task_run_id: The task run UUID."""

LIST_TASK_RUNS_DOC = """\
List recent task runs. Use this for "show recent task runs",
"any failed tasks", or "task runs for workflow run X".

Args:
    status: Optional filter by status (running, completed, failed, paused).
    workflow_run_id: Optional filter by parent workflow run UUID.
    limit: Max results to return (default 10, max 20)."""

# --- Admin tools ---

SEARCH_AUDIT_TRAIL_DOC = """\
Search the activity audit trail. Requires admin role.

Args:
    action: Filter by action (e.g., "task.create", "workflow.execute").
    resource_type: Filter by resource type (e.g., "task", "workflow", "alert").
    limit: Max results to return (default 20, max 50)."""

# --- Action tools ---

RUN_WORKFLOW_DOC = """\
Execute a workflow. Requires user confirmation before running.

Args:
    workflow_id: The workflow UUID to execute.
    input_data: Optional JSON string of input data for the workflow."""

RUN_TASK_DOC = """\
Execute a task. Requires user confirmation before running.

Args:
    task_identifier: Task UUID or cy_name.
    input_data: Optional JSON string of input data for the task."""

ANALYZE_ALERT_DOC = """\
Trigger alert analysis by dispatching a control event.

Args:
    alert_id: The alert UUID to analyze."""

CREATE_ALERT_DOC = """\
Create a new alert.

Args:
    title: Alert title (required).
    severity: Severity level (default: medium).
    description: Optional description.
    source_vendor: Source vendor (default: chatbot).
    source_product: Source product (default: analysi-chatbot)."""

# --- Meta tools ---

GET_PLATFORM_SUMMARY_DOC = """\
Get a combined overview of alerts AND integrations in one call.
Use this for "morning briefing", "what's the status", "give me an overview",
"anything I should know about", or similar broad questions.
Returns recent alerts with severity/status/summary AND integration health."""

# --- Validation ---


def validate_chat_tool_docs() -> list[str]:
    """Validate that generated docstrings contain correct enum values.

    Returns a list of error messages. Empty list = all valid.
    Used in CI to catch docstring/enum drift.
    """
    errors: list[str] = []

    # Check severity values in SEARCH_ALERTS_DOC
    for sev in AlertSeverity:
        if sev.value not in SEARCH_ALERTS_DOC:
            errors.append(f"SEARCH_ALERTS_DOC missing severity '{sev.value}'")

    # Check status values in SEARCH_ALERTS_DOC
    for status in AlertStatus:
        if status.value not in SEARCH_ALERTS_DOC:
            errors.append(f"SEARCH_ALERTS_DOC missing status '{status.value}'")

    # Check function values in LIST_TASKS_DOC
    for k, v in vars(TaskFunction).items():
        if not k.startswith("_") and isinstance(v, str) and v not in LIST_TASKS_DOC:
            errors.append(f"LIST_TASKS_DOC missing function '{v}'")

    # Check no fake values (common drift examples)
    fake_values = ["informational", "resolved", "closed"]
    for fake in fake_values:
        if fake in SEARCH_ALERTS_DOC:
            errors.append(f"SEARCH_ALERTS_DOC contains deprecated value '{fake}'")

    return errors
