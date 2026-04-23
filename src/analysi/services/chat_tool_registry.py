"""Chat tool registry — all tool wrappers + Tool list.

Moves all 22 tool wrapper functions out of the 500-line `_build_agent()` closure
into module-level functions. Each wrapper is a standalone async function with
typed parameters that Pydantic AI can introspect.

`build_tool_list()` returns a list of `Tool` objects ready to pass to `Agent(tools=...)`.
"""

import json

from pydantic_ai import RunContext, Tool

from analysi.config.logging import get_logger
from analysi.constants import ChatConstants
from analysi.services.chat_action_tools import (
    PendingAction,
    analyze_alert_impl,
    build_confirmation_message,
    check_confirmation,
    create_alert_impl,
    run_task_impl,
    run_workflow_impl,
)
from analysi.services.chat_ku_tools import read_document, read_table, search_knowledge
from analysi.services.chat_meta_tools import (
    get_page_context_impl,
    suggest_next_steps_impl,
)
from analysi.services.chat_service import ChatDeps, check_chat_action_permission
from analysi.services.chat_skills import (
    load_skill_content,
    update_pinned_skills,
)
from analysi.services.chat_tool_docs import (
    ANALYZE_ALERT_DOC,
    CREATE_ALERT_DOC,
    GET_ALERT_DOC,
    GET_INTEGRATION_HEALTH_DOC,
    GET_PLATFORM_SUMMARY_DOC,
    GET_TASK_DOC,
    GET_TASK_RUN_DOC,
    GET_WORKFLOW_DOC,
    GET_WORKFLOW_RUN_DOC,
    LIST_INTEGRATIONS_DOC,
    LIST_TASK_RUNS_DOC,
    LIST_TASKS_DOC,
    LIST_WORKFLOW_RUNS_DOC,
    LIST_WORKFLOWS_DOC,
    RUN_TASK_DOC,
    RUN_WORKFLOW_DOC,
    SEARCH_ALERTS_DOC,
    SEARCH_AUDIT_TRAIL_DOC,
)
from analysi.services.chat_tools import (
    get_alert_impl,
    get_integration_health_impl,
    get_platform_summary_impl,
    get_task_impl,
    get_task_run_impl,
    get_workflow_impl,
    get_workflow_run_impl,
    list_integrations_impl,
    list_task_runs_impl,
    list_tasks_impl,
    list_workflow_runs_impl,
    list_workflows_impl,
    search_alerts_impl,
    search_audit_trail_impl,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_tool_call_limit(deps: ChatDeps) -> str | None:
    if deps.tool_call_count >= ChatConstants.MAX_TOOL_CALLS_PER_TURN:
        return (
            f"Tool call limit reached ({ChatConstants.MAX_TOOL_CALLS_PER_TURN} "
            "per turn). Please ask your question and I'll answer with "
            "the information already gathered."
        )
    deps.tool_call_count += 1
    return None


# ---------------------------------------------------------------------------
# 1. Skill tool (exempt from tool-call cap)
# ---------------------------------------------------------------------------

LOAD_PRODUCT_SKILL_DOC = """\
Load detailed product knowledge. Call BEFORE answering any question
about a specific domain — do not guess from general knowledge.

Args:
    skill_name: One of: alerts, workflows, tasks, integrations, api, \
knowledge_units, hitl, admin, cli, automation, analysis_groups."""


async def _load_product_skill(ctx: RunContext[ChatDeps], skill_name: str) -> str:
    if ctx.deps.skill_load_count >= ChatConstants.MAX_PINNED_SKILLS:
        return (
            f"Skill load limit reached ({ChatConstants.MAX_PINNED_SKILLS} per turn). "
            "Answer using the skills already loaded."
        )
    ctx.deps.skill_load_count += 1

    try:
        content = load_skill_content(skill_name)
    except ValueError as exc:
        return str(exc)

    ctx.deps.pinned_skills = update_pinned_skills(ctx.deps.pinned_skills, skill_name)

    logger.info(
        "chat_skill_loaded",
        skill_name=skill_name,
        conversation_id=str(ctx.deps.conversation_id),
        pinned=ctx.deps.pinned_skills,
    )
    return content


# ---------------------------------------------------------------------------
# 2. Knowledge tools
# ---------------------------------------------------------------------------

SEARCH_TENANT_KNOWLEDGE_DOC = """\
Search the tenant's Knowledge Units (documents, tables, indexes).
Use this to find tenant-specific data like runbooks, asset lists, lookup tables.

Args:
    query: Text to search for in KU names and descriptions.
    ku_type: Optional filter — "document", "table", or "index"."""

READ_KNOWLEDGE_DOCUMENT_DOC = """\
Read the content of a specific Knowledge Unit document.

Args:
    name: Document name (preferred).
    document_id: Document UUID (fallback)."""

READ_KNOWLEDGE_TABLE_DOC = """\
Read rows from a specific Knowledge Unit table.

Args:
    name: Table name (preferred).
    table_id: Table UUID (fallback).
    max_rows: Max rows to return (default 50)."""


async def _search_tenant_knowledge(
    ctx: RunContext[ChatDeps], query: str, ku_type: str | None = None
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await search_knowledge(
        session=ctx.deps.session,
        tenant_id=ctx.deps.tenant_id,
        query=query,
        ku_type=ku_type,
    )


async def _read_knowledge_document(
    ctx: RunContext[ChatDeps], name: str | None = None, document_id: str | None = None
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await read_document(
        session=ctx.deps.session,
        tenant_id=ctx.deps.tenant_id,
        name=name,
        document_id=document_id,
    )


async def _read_knowledge_table(
    ctx: RunContext[ChatDeps],
    name: str | None = None,
    table_id: str | None = None,
    max_rows: int = 50,
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await read_table(
        session=ctx.deps.session,
        tenant_id=ctx.deps.tenant_id,
        name=name,
        table_id=table_id,
        max_rows=max_rows,
    )


# ---------------------------------------------------------------------------
# 3. Read-only platform tools
# ---------------------------------------------------------------------------


async def _get_alert(ctx: RunContext[ChatDeps], alert_id: str) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_alert_impl(ctx.deps.session, ctx.deps.tenant_id, alert_id)


async def _search_alerts(
    ctx: RunContext[ChatDeps],
    severity: str | None = None,
    status: str | None = None,
    source_vendor: str | None = None,
    title_filter: str | None = None,
    ioc_filter: str | None = None,
    limit: int = 10,
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await search_alerts_impl(
        ctx.deps.session,
        ctx.deps.tenant_id,
        severity=severity,
        status=status,
        source_vendor=source_vendor,
        title_filter=title_filter,
        ioc_filter=ioc_filter,
        limit=limit,
    )


async def _get_workflow(ctx: RunContext[ChatDeps], workflow_id: str) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_workflow_impl(ctx.deps.session, ctx.deps.tenant_id, workflow_id)


async def _list_workflows(
    ctx: RunContext[ChatDeps], name_filter: str | None = None, limit: int = 20
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await list_workflows_impl(
        ctx.deps.session, ctx.deps.tenant_id, name_filter=name_filter, limit=limit
    )


async def _get_task(ctx: RunContext[ChatDeps], task_identifier: str) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_task_impl(ctx.deps.session, ctx.deps.tenant_id, task_identifier)


async def _list_tasks(
    ctx: RunContext[ChatDeps],
    function: str | None = None,
    name_filter: str | None = None,
    categories: list[str] | None = None,
    limit: int = 50,
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await list_tasks_impl(
        ctx.deps.session,
        ctx.deps.tenant_id,
        function=function,
        name_filter=name_filter,
        categories=categories,
        limit=limit,
    )


async def _get_integration_health(
    ctx: RunContext[ChatDeps], integration_id: str
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_integration_health_impl(
        ctx.deps.session, ctx.deps.tenant_id, integration_id
    )


async def _list_integrations(ctx: RunContext[ChatDeps]) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await list_integrations_impl(ctx.deps.session, ctx.deps.tenant_id)


async def _get_workflow_run(ctx: RunContext[ChatDeps], workflow_run_id: str) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_workflow_run_impl(
        ctx.deps.session, ctx.deps.tenant_id, workflow_run_id
    )


async def _get_task_run(ctx: RunContext[ChatDeps], task_run_id: str) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_task_run_impl(ctx.deps.session, ctx.deps.tenant_id, task_run_id)


async def _list_workflow_runs(
    ctx: RunContext[ChatDeps],
    status: str | None = None,
    limit: int = 10,
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await list_workflow_runs_impl(
        ctx.deps.session, ctx.deps.tenant_id, status=status, limit=limit
    )


async def _list_task_runs(
    ctx: RunContext[ChatDeps],
    status: str | None = None,
    workflow_run_id: str | None = None,
    limit: int = 10,
) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await list_task_runs_impl(
        ctx.deps.session,
        ctx.deps.tenant_id,
        status=status,
        workflow_run_id=workflow_run_id,
        limit=limit,
    )


async def _get_platform_summary(ctx: RunContext[ChatDeps]) -> str:
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await get_platform_summary_impl(ctx.deps.session, ctx.deps.tenant_id)


# ---------------------------------------------------------------------------
# 4. Admin tool
# ---------------------------------------------------------------------------


async def _search_audit_trail(
    ctx: RunContext[ChatDeps],
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 20,
) -> str:
    if not any(r in ("admin", "owner", "platform_admin") for r in ctx.deps.user_roles):
        return "This tool requires admin permissions. Your current role does not have access."
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg
    return await search_audit_trail_impl(
        ctx.deps.session,
        ctx.deps.tenant_id,
        action=action,
        resource_type=resource_type,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 5. Action tools (two-phase confirmation)
# ---------------------------------------------------------------------------


async def _run_workflow(
    ctx: RunContext[ChatDeps], workflow_id: str, input_data: str | None = None
) -> str:
    perm_msg = check_chat_action_permission(ctx.deps.user_roles, "workflows", "execute")
    if perm_msg:
        return perm_msg
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg

    try:
        parsed_input = json.loads(input_data) if input_data else None
    except json.JSONDecodeError:
        return "Invalid JSON in input_data. Please provide valid JSON."

    kwargs = {"workflow_id": workflow_id, "input_data": input_data}
    if check_confirmation(ctx.deps.pending_action, "run_workflow", kwargs):
        result = await run_workflow_impl(
            ctx.deps.session, ctx.deps.tenant_id, workflow_id, parsed_input
        )
        ctx.deps.pending_action = None
        return result

    ctx.deps.pending_action = PendingAction(
        tool_name="run_workflow",
        description=f"Execute workflow {workflow_id}"
        + (f" with input: {input_data[:200]}" if input_data else ""),
        kwargs=kwargs,
    )
    return build_confirmation_message(
        f"I'm about to execute workflow `{workflow_id}`"
        + (" with the provided input data." if input_data else ".")
    )


async def _run_task(
    ctx: RunContext[ChatDeps], task_identifier: str, input_data: str | None = None
) -> str:
    perm_msg = check_chat_action_permission(ctx.deps.user_roles, "tasks", "execute")
    if perm_msg:
        return perm_msg
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg

    try:
        parsed_input = json.loads(input_data) if input_data else None
    except json.JSONDecodeError:
        return "Invalid JSON in input_data. Please provide valid JSON."

    kwargs = {"task_identifier": task_identifier, "input_data": input_data}
    if check_confirmation(ctx.deps.pending_action, "run_task", kwargs):
        result = await run_task_impl(
            ctx.deps.session, ctx.deps.tenant_id, task_identifier, parsed_input
        )
        ctx.deps.pending_action = None
        return result

    ctx.deps.pending_action = PendingAction(
        tool_name="run_task",
        description=f"Execute task {task_identifier}"
        + (f" with input: {input_data[:200]}" if input_data else ""),
        kwargs=kwargs,
    )
    return build_confirmation_message(
        f"I'm about to execute task `{task_identifier}`"
        + (" with the provided input data." if input_data else ".")
    )


async def _analyze_alert(ctx: RunContext[ChatDeps], alert_id: str) -> str:
    perm_msg = check_chat_action_permission(ctx.deps.user_roles, "alerts", "update")
    if perm_msg:
        return perm_msg
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg

    kwargs = {"alert_id": alert_id}
    if check_confirmation(ctx.deps.pending_action, "analyze_alert", kwargs):
        result = await analyze_alert_impl(
            ctx.deps.session, ctx.deps.tenant_id, alert_id
        )
        ctx.deps.pending_action = None
        return result

    ctx.deps.pending_action = PendingAction(
        tool_name="analyze_alert",
        description=f"Trigger analysis for alert {alert_id}",
        kwargs=kwargs,
    )
    return build_confirmation_message(
        f"I'm about to trigger analysis for alert `{alert_id}`."
    )


async def _create_alert(
    ctx: RunContext[ChatDeps],
    title: str,
    severity: str = "medium",
    description: str | None = None,
) -> str:
    perm_msg = check_chat_action_permission(ctx.deps.user_roles, "alerts", "create")
    if perm_msg:
        return perm_msg
    limit_msg = _check_tool_call_limit(ctx.deps)
    if limit_msg:
        return limit_msg

    kwargs = {"title": title, "severity": severity, "description": description}
    if check_confirmation(ctx.deps.pending_action, "create_alert", kwargs):
        result = await create_alert_impl(
            ctx.deps.session,
            ctx.deps.tenant_id,
            title=title,
            severity=severity,
            description=description,
        )
        ctx.deps.pending_action = None
        return result

    ctx.deps.pending_action = PendingAction(
        tool_name="create_alert",
        description=f"Create alert: '{title}' (severity: {severity})",
        kwargs=kwargs,
    )
    return build_confirmation_message(
        f"I'm about to create a new alert:\n- Title: {title}\n- Severity: {severity}\n"
        + (f"- Description: {description[:200]}" if description else "")
    )


# ---------------------------------------------------------------------------
# 6. Meta tools (no session, no tool-call cap)
# ---------------------------------------------------------------------------

GET_PAGE_CONTEXT_DOC = """\
Get information about the page the user is currently viewing. Useful for contextual help."""

SUGGEST_NEXT_STEPS_DOC = """\
Get contextual follow-up suggestions based on the current page."""


async def _get_page_context(ctx: RunContext[ChatDeps]) -> str:
    return get_page_context_impl(ctx.deps.page_context)


async def _suggest_next_steps(ctx: RunContext[ChatDeps]) -> str:
    return suggest_next_steps_impl(ctx.deps.page_context)


# ---------------------------------------------------------------------------
# Tool list — the single source of truth for all chat tools
# ---------------------------------------------------------------------------


def build_tool_list() -> list[Tool]:
    """Build the complete list of Tool objects for the chat agent.

    This is the ONLY place tools are registered. Adding a new tool =
    adding one entry here + one wrapper function above.
    """
    return [
        # Skill (exempt from cap — has own limit)
        Tool(
            _load_product_skill,
            name="load_product_skill",
            description=LOAD_PRODUCT_SKILL_DOC,
        ),
        # Knowledge
        Tool(
            _search_tenant_knowledge,
            name="search_tenant_knowledge",
            description=SEARCH_TENANT_KNOWLEDGE_DOC,
        ),
        Tool(
            _read_knowledge_document,
            name="read_knowledge_document",
            description=READ_KNOWLEDGE_DOCUMENT_DOC,
        ),
        Tool(
            _read_knowledge_table,
            name="read_knowledge_table",
            description=READ_KNOWLEDGE_TABLE_DOC,
        ),
        # Read-only platform
        Tool(_get_alert, name="get_alert", description=GET_ALERT_DOC),
        Tool(_search_alerts, name="search_alerts", description=SEARCH_ALERTS_DOC),
        Tool(_get_workflow, name="get_workflow", description=GET_WORKFLOW_DOC),
        Tool(_list_workflows, name="list_workflows", description=LIST_WORKFLOWS_DOC),
        Tool(_get_task, name="get_task", description=GET_TASK_DOC),
        Tool(_list_tasks, name="list_tasks", description=LIST_TASKS_DOC),
        Tool(
            _get_integration_health,
            name="get_integration_health",
            description=GET_INTEGRATION_HEALTH_DOC,
        ),
        Tool(
            _list_integrations,
            name="list_integrations",
            description=LIST_INTEGRATIONS_DOC,
        ),
        Tool(
            _get_workflow_run, name="get_workflow_run", description=GET_WORKFLOW_RUN_DOC
        ),
        Tool(
            _list_workflow_runs,
            name="list_workflow_runs",
            description=LIST_WORKFLOW_RUNS_DOC,
        ),
        Tool(_get_task_run, name="get_task_run", description=GET_TASK_RUN_DOC),
        Tool(_list_task_runs, name="list_task_runs", description=LIST_TASK_RUNS_DOC),
        Tool(
            _get_platform_summary,
            name="get_platform_summary",
            description=GET_PLATFORM_SUMMARY_DOC,
        ),
        # Admin
        Tool(
            _search_audit_trail,
            name="search_audit_trail",
            description=SEARCH_AUDIT_TRAIL_DOC,
        ),
        # Actions (confirmation-gated)
        Tool(_run_workflow, name="run_workflow", description=RUN_WORKFLOW_DOC),
        Tool(_run_task, name="run_task", description=RUN_TASK_DOC),
        Tool(_analyze_alert, name="analyze_alert", description=ANALYZE_ALERT_DOC),
        Tool(_create_alert, name="create_alert", description=CREATE_ALERT_DOC),
        # Meta
        Tool(
            _get_page_context, name="get_page_context", description=GET_PAGE_CONTEXT_DOC
        ),
        Tool(
            _suggest_next_steps,
            name="suggest_next_steps",
            description=SUGGEST_NEXT_STEPS_DOC,
        ),
    ]
