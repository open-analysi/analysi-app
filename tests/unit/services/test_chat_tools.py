"""Unit tests for ``analysi.services.chat_tools``.

The module is the read-only side of the chat agent's tool surface: 14
``*_impl`` async functions that resolve IDs, query services, and format
results back to the LLM. Combined unit + integration coverage was 61 %.

We mock at the service-layer boundary so no real DB session is involved.
``cap_tool_result`` and ``sanitize_tool_result`` are pass-through-ish in
practice, so we just assert on substrings of the returned text.

Notable: ``test_get_platform_summary_impl_unknown_integrations_not_in_unhealthy``
is a regression test for a bug found while writing this file (see commit
message). The original implementation buckets every integration whose
``health_status`` is not in ``{"healthy", "degraded"}`` under
"Unhealthy" — including freshly-provisioned integrations whose
``health_status`` is the documented sentinel ``"unknown"``. The user
sees the integration as broken when in fact we just haven't health-
checked it yet. Fixed in the same commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.chat_tools import (
    _format_dict,
    get_alert_impl,
    get_integration_health_impl,
    get_platform_summary_impl,
    get_workflow_impl,
    list_integrations_impl,
    list_task_runs_impl,
    list_workflow_runs_impl,
    list_workflows_impl,
    search_alerts_impl,
)


# ── _format_dict ────────────────────────────────────────────────────────────


def test_format_dict_handles_uuid() -> None:
    out = _format_dict({"id": uuid4()})
    # No exception means UUID was coerced via ``default=str``.
    assert "id" in out


def test_format_dict_handles_datetime() -> None:
    out = _format_dict({"ts": datetime(2026, 1, 1, tzinfo=UTC)})
    assert "2026-01-01" in out


def test_format_dict_indents_by_two_default() -> None:
    out = _format_dict({"a": 1})
    assert '\n  "a": 1' in out


# ── get_alert_impl ─────────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_alert_impl_invalid_uuid() -> None:
    out = await get_alert_impl(MagicMock(), "tenant", "not-a-uuid")
    assert "Invalid alert ID format" in out
    assert "Expected a UUID" in out


@pytest.mark.asyncio
async def test_get_alert_impl_not_found() -> None:
    fake_session = MagicMock()
    alert_id = str(uuid4())
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.get_alert = AsyncMock(return_value=None)
        out = await get_alert_impl(fake_session, "tenant", alert_id)
    assert "not found" in out


# ── search_alerts_impl ─────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_search_alerts_impl_no_results_lists_filters() -> None:
    """The empty-result message includes the active filters so the LLM
    can usefully respond ('No high-severity firewall alerts found.')."""
    fake_session = MagicMock()
    fake_alert_list = MagicMock(alerts=[], total=0)
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        out = await search_alerts_impl(
            fake_session,
            "t",
            severity="high",
            source_vendor="splunk",
        )
    assert "No alerts found" in out
    assert "severity=" in out
    assert "high" in out
    assert "splunk" in out


@pytest.mark.asyncio
async def test_search_alerts_impl_no_filter_is_described() -> None:
    """When no filters are given, the empty-result message says 'none'."""
    fake_session = MagicMock()
    fake_alert_list = MagicMock(alerts=[], total=0)
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        out = await search_alerts_impl(fake_session, "t")
    assert "none" in out


@pytest.mark.asyncio
async def test_search_alerts_impl_severity_string_wrapped_in_list() -> None:
    """The repository expects ``filters['severity']`` to be a list (IN
    clause). A string is wrapped in a single-element list."""
    fake_session = MagicMock()
    fake_alert_list = MagicMock(alerts=[], total=0)
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        svc = factory.return_value
        svc.list_alerts = AsyncMock(return_value=fake_alert_list)
        await search_alerts_impl(fake_session, "t", severity="high")
        call_kwargs = svc.list_alerts.await_args.kwargs
    assert call_kwargs["filters"]["severity"] == ["high"]


@pytest.mark.asyncio
async def test_search_alerts_impl_clamps_limit_to_20() -> None:
    """Even if the LLM passes ``limit=999``, the repo only sees 20."""
    fake_session = MagicMock()
    fake_alert_list = MagicMock(alerts=[], total=0)
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        svc = factory.return_value
        svc.list_alerts = AsyncMock(return_value=fake_alert_list)
        await search_alerts_impl(fake_session, "t", limit=999)
        call_kwargs = svc.list_alerts.await_args.kwargs
    assert call_kwargs["limit"] == 20


# ── get_workflow_impl ──────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_workflow_impl_invalid_uuid() -> None:
    out = await get_workflow_impl(MagicMock(), "t", "not-a-uuid")
    assert "Invalid workflow ID format" in out


@pytest.mark.asyncio
async def test_get_workflow_impl_not_found() -> None:
    fake_session = MagicMock()
    wid = str(uuid4())
    with patch("analysi.services.workflow.WorkflowService") as cls:
        cls.return_value.get_workflow = AsyncMock(return_value=None)
        out = await get_workflow_impl(fake_session, "t", wid)
    assert "not found" in out


# ── list_workflows_impl ────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_list_workflows_impl_empty_returns_message() -> None:
    fake_session = MagicMock()
    with patch("analysi.services.workflow.WorkflowService") as cls:
        cls.return_value.list_workflows = AsyncMock(return_value=([], {"total": 0}))
        out = await list_workflows_impl(fake_session, "t")
    assert "No workflows found" in out


@pytest.mark.asyncio
async def test_list_workflows_impl_clamps_limit_to_50() -> None:
    fake_session = MagicMock()
    with patch("analysi.services.workflow.WorkflowService") as cls:
        svc = cls.return_value
        svc.list_workflows = AsyncMock(return_value=([], {"total": 0}))
        await list_workflows_impl(fake_session, "t", limit=999)
        kwargs = svc.list_workflows.await_args.kwargs
    assert kwargs["limit"] == 50


# ── list_workflow_runs_impl / list_task_runs_impl ──────────────────────────-


@pytest.mark.asyncio
async def test_list_workflow_runs_impl_empty_with_status_filter() -> None:
    fake_session = MagicMock()
    with patch(
        "analysi.repositories.workflow_execution.WorkflowRunRepository"
    ) as cls:
        cls.return_value.list_workflow_runs = AsyncMock(return_value=([], 0))
        out = await list_workflow_runs_impl(fake_session, "t", status="failed")
    assert "No workflow runs found" in out
    assert "status=failed" in out


@pytest.mark.asyncio
async def test_list_task_runs_impl_invalid_workflow_run_uuid() -> None:
    out = await list_task_runs_impl(
        MagicMock(), "t", workflow_run_id="not-a-uuid"
    )
    assert "Invalid workflow run ID format" in out


@pytest.mark.asyncio
async def test_list_task_runs_impl_clamps_limit() -> None:
    fake_session = MagicMock()
    with patch("analysi.services.task_run.TaskRunService") as cls:
        svc = cls.return_value
        svc.list_task_runs = AsyncMock(return_value=([], 0))
        await list_task_runs_impl(fake_session, "t", limit=999)
        # session is positional arg, limit is in kwargs
        kwargs = svc.list_task_runs.await_args.kwargs
    assert kwargs["limit"] == 20


# ── get_integration_health_impl ────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_get_integration_health_impl_not_found() -> None:
    fake_session = MagicMock()
    with patch(
        "analysi.services.chat_tools._make_integration_service"
    ) as factory:
        svc = factory.return_value
        svc.get_integration = AsyncMock(return_value=None)
        out = await get_integration_health_impl(fake_session, "t", "missing-1")
    assert "not found" in out


@pytest.mark.asyncio
async def test_get_integration_health_impl_returns_summary() -> None:
    fake_session = MagicMock()
    integ = _mk_integ("splunk-1", "healthy")
    with patch(
        "analysi.services.chat_tools._make_integration_service"
    ) as factory:
        svc = factory.return_value
        svc.get_integration = AsyncMock(return_value=integ)
        out = await get_integration_health_impl(fake_session, "t", "splunk-1")
    assert "splunk-1" in out


# ── list_integrations_impl ─────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_list_integrations_impl_empty() -> None:
    fake_session = MagicMock()
    with patch(
        "analysi.services.chat_tools._make_integration_service"
    ) as factory:
        factory.return_value.list_integrations = AsyncMock(return_value=[])
        out = await list_integrations_impl(fake_session, "t")
    assert "No integrations" in out or "no integrations" in out.lower()


# ── get_platform_summary_impl ──────────────────────────────────────────────-
#
# Bug-hunt territory: the implementation buckets integrations into
# {Healthy / Degraded / Unhealthy} based on health_status. Anything not
# in {"healthy", "degraded"} ends up in "Unhealthy" — including the
# documented "unknown" sentinel that the IntegrationHealthStatus enum
# emits for never-checked integrations.
#
# That's user-facing misinformation: a freshly-provisioned integration
# appears under "**Unhealthy**" until the first health check runs (which
# may be hours later). Fixed by introducing a third "Unknown" bucket.


def _mk_integ(name: str, status: str) -> MagicMock:
    """Build the kind of object IntegrationChatSummary.from_integration
    expects (an IntegrationResponse with ``.health.status``)."""
    integ = MagicMock()
    integ.integration_id = f"int-{name}"
    integ.name = name
    integ.integration_type = "vendor"
    integ.enabled = True
    integ.health = MagicMock()
    integ.health.status = status
    integ.health.message = "msg"
    return integ


@pytest.mark.asyncio
async def test_get_platform_summary_impl_buckets_healthy() -> None:
    fake_session = MagicMock()
    integ_alpha = _mk_integ("alpha", "healthy")
    integ_beta = _mk_integ("beta", "healthy")
    fake_alert_list = MagicMock(alerts=[], total=0)
    with (
        patch("analysi.services.chat_tools._make_alert_service") as af,
        patch(
            "analysi.services.chat_tools._make_integration_service"
        ) as ig,
    ):
        af.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        ig.return_value.list_integrations = AsyncMock(
            return_value=[integ_alpha, integ_beta]
        )
        out = await get_platform_summary_impl(fake_session, "t")
    assert "Healthy (2)" in out
    assert "alpha" in out and "beta" in out


@pytest.mark.asyncio
async def test_get_platform_summary_impl_buckets_unhealthy() -> None:
    fake_session = MagicMock()
    integ = _mk_integ("broken", "unhealthy")
    fake_alert_list = MagicMock(alerts=[], total=0)
    with (
        patch("analysi.services.chat_tools._make_alert_service") as af,
        patch(
            "analysi.services.chat_tools._make_integration_service"
        ) as ig,
    ):
        af.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        ig.return_value.list_integrations = AsyncMock(return_value=[integ])
        out = await get_platform_summary_impl(fake_session, "t")
    assert "Unhealthy" in out
    assert "broken" in out


@pytest.mark.asyncio
async def test_get_platform_summary_impl_unknown_integrations_not_in_unhealthy() -> None:
    """REGRESSION: an integration with ``health_status='unknown'`` (the
    sentinel for never-checked integrations) must NOT be reported as
    Unhealthy to the user.

    Prior behaviour (bug):  "**Unhealthy (1)**: never-checked"
    Fixed behaviour:         "**Unknown (1)**: never-checked"

    The user sees the difference between "this integration is broken"
    and "we haven't run a health check yet" — a much more accurate
    picture of platform state.
    """
    fake_session = MagicMock()
    integ = _mk_integ("never-checked", "unknown")
    fake_alert_list = MagicMock(alerts=[], total=0)
    with (
        patch("analysi.services.chat_tools._make_alert_service") as af,
        patch(
            "analysi.services.chat_tools._make_integration_service"
        ) as ig,
    ):
        af.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        ig.return_value.list_integrations = AsyncMock(return_value=[integ])
        out = await get_platform_summary_impl(fake_session, "t")

    # Fixed: "unknown" must be in its OWN bucket — and must NOT appear
    # under "Unhealthy".
    assert "Unknown (1)" in out
    assert "never-checked" in out
    # Specifically: the integration name must not appear on a line that
    # also says "Unhealthy".
    for line in out.splitlines():
        if "never-checked" in line:
            assert "Unhealthy" not in line, (
                f"never-checked appeared under Unhealthy: {line!r}"
            )


@pytest.mark.asyncio
async def test_get_platform_summary_impl_alert_fetch_error_does_not_crash() -> None:
    """If the alert service raises, the summary still returns — the
    alerts section just says we couldn't fetch them."""
    fake_session = MagicMock()
    with (
        patch("analysi.services.chat_tools._make_alert_service") as af,
        patch(
            "analysi.services.chat_tools._make_integration_service"
        ) as ig,
    ):
        af.return_value.list_alerts = AsyncMock(side_effect=RuntimeError("db gone"))
        ig.return_value.list_integrations = AsyncMock(return_value=[])
        out = await get_platform_summary_impl(fake_session, "t")
    assert "Unable to fetch alerts" in out


@pytest.mark.asyncio
async def test_get_platform_summary_impl_integration_fetch_error_does_not_crash() -> (
    None
):
    fake_session = MagicMock()
    fake_alert_list = MagicMock(alerts=[], total=0)
    with (
        patch("analysi.services.chat_tools._make_alert_service") as af,
        patch(
            "analysi.services.chat_tools._make_integration_service"
        ) as ig,
    ):
        af.return_value.list_alerts = AsyncMock(return_value=fake_alert_list)
        ig.return_value.list_integrations = AsyncMock(
            side_effect=RuntimeError("integ db gone")
        )
        out = await get_platform_summary_impl(fake_session, "t")
    assert "Unable to fetch integrations" in out
