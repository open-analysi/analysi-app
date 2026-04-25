"""
Integration tests for cancel analysis API — TDD.

Covers:
1. Cancel endpoint behaviour (paused, running, terminal states, edge cases)
2. Guard on PUT /analyses/{id}/status — rejected when analysis is cancelled
3. Guard on PUT /alerts/{id}/analysis-status — rejected when alert is cancelled
4. Worker early-exit when update_analysis_status("running") returns False
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.alert import Alert, AlertAnalysis

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _create_alert_with_analysis(
    session: AsyncSession,
    *,
    analysis_status: str,
    alert_status: str = "in_progress",
    tenant_id: str | None = None,
) -> tuple[Alert, AlertAnalysis]:
    """Create an alert + analysis in any status pair."""
    tid = tenant_id or f"test-cancel-{uuid4().hex[:8]}"

    alert = Alert(
        id=uuid4(),
        tenant_id=tid,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Test Cancel Alert",
        triggering_event_time=datetime.now(UTC),
        severity="high",
        rule_name="Test Rule",
        raw_data=json.dumps({"test": "data"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=alert_status,
        ingested_at=datetime.now(UTC),
    )
    session.add(alert)
    await session.flush()

    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tid,
        status=analysis_status,
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    session.add(analysis)
    alert.current_analysis_id = analysis.id
    await session.commit()

    return alert, analysis


def _make_client(session: AsyncSession) -> AsyncClient:
    """Create ASGI test client bound to the integration test session."""

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1.  POST /v1/{tenant}/alerts/{alert_id}/analysis/cancel
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_from_paused_workflow_building(integration_test_session):
    """Cancel succeeds from paused_workflow_building state."""
    alert, analysis = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="paused",  # paused_workflow_building -> paused
        alert_status="in_progress",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["status"] == "cancelled"
    assert data["previous_status"] == "paused"  # simplified

    await integration_test_session.refresh(alert)
    await integration_test_session.refresh(analysis)
    assert alert.analysis_status == "cancelled"
    assert analysis.status == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_from_running_state(integration_test_session):
    """Cancel succeeds from running state (in-flight job will abort)."""
    alert, analysis = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="running",
        alert_status="in_progress",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["status"] == "cancelled"
    assert data["previous_status"] == "running"

    await integration_test_session.refresh(alert)
    await integration_test_session.refresh(analysis)
    assert alert.analysis_status == "cancelled"
    assert analysis.status == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_completed_returns_409(integration_test_session):
    """Cancel is rejected when analysis is already completed."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="completed",
        alert_status="completed",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_failed_returns_409(integration_test_session):
    """Cancel is rejected when analysis already failed."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="failed",
        alert_status="failed",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409(integration_test_session):
    """Cancel is rejected when analysis is already cancelled (idempotent 409)."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="cancelled",
        alert_status="cancelled",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_nonexistent_alert_returns_404(integration_test_session):
    """Cancel returns 404 for an alert that does not exist."""
    fake_alert_id = uuid4()

    async with _make_client(integration_test_session) as client:
        response = await client.post(
            f"/v1/nonexistent-tenant/alerts/{fake_alert_id}/analysis/cancel"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_alert_with_no_current_analysis_returns_404(
    integration_test_session,
):
    """Cancel returns 404 when the alert has no current analysis."""
    tid = f"test-cancel-{uuid4().hex[:8]}"
    alert = Alert(
        id=uuid4(),
        tenant_id=tid,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Alert Without Analysis",
        triggering_event_time=datetime.now(UTC),
        severity="medium",
        rule_name="Test",
        raw_data=json.dumps({}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status="new",
        ingested_at=datetime.now(UTC),
    )
    integration_test_session.add(alert)
    await integration_test_session.commit()

    async with _make_client(integration_test_session) as client:
        response = await client.post(f"/v1/{tid}/alerts/{alert.id}/analysis/cancel")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_is_tenant_scoped(integration_test_session):
    """Cancel endpoint uses the URL tenant, ignoring other tenants' alerts."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="paused",  # paused_workflow_building -> paused
    )
    wrong_tenant = f"wrong-{uuid4().hex[:8]}"

    async with _make_client(integration_test_session) as client:
        response = await client.post(
            f"/v1/{wrong_tenant}/alerts/{alert.id}/analysis/cancel"
        )

    # Either 404 (alert not visible in wrong tenant) or 403 — either is correct
    assert response.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_403_FORBIDDEN,
    )


# ---------------------------------------------------------------------------
# 2. Guard on PUT /analyses/{id}/status — reject if current status is cancelled
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_analysis_status_rejects_running_when_cancelled(
    integration_test_session,
):
    """PUT /analyses/{id}/status?status=running returns 409 if current status is cancelled."""
    alert, analysis = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="cancelled",
        alert_status="cancelled",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.put(
            f"/v1/{tid}/analyses/{analysis.id}/status",
            params={"status": "running"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    # DB must not have changed
    await integration_test_session.refresh(analysis)
    assert analysis.status == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_analysis_status_rejects_failed_when_cancelled(
    integration_test_session,
):
    """PUT /analyses/{id}/status?status=failed returns 409 if current status is cancelled."""
    alert, analysis = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="cancelled",
        alert_status="cancelled",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.put(
            f"/v1/{tid}/analyses/{analysis.id}/status",
            params={"status": "failed"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    await integration_test_session.refresh(analysis)
    assert analysis.status == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_analysis_status_allows_non_cancelled_transitions(
    integration_test_session,
):
    """Normal status transitions (running→completed) still work after guard is added."""
    alert, analysis = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="running",
        alert_status="in_progress",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.put(
            f"/v1/{tid}/analyses/{analysis.id}/status",
            params={"status": "completed"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["status"] == "updated"
    await integration_test_session.refresh(analysis)
    assert analysis.status == "completed"


# ---------------------------------------------------------------------------
# 3. Guard on PUT /alerts/{id}/analysis-status — reject if current is cancelled
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_alert_analysis_status_rejects_when_cancelled(
    integration_test_session,
):
    """PUT /alerts/{id}/analysis-status returns 409 when alert.analysis_status is cancelled."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="cancelled",
        alert_status="cancelled",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.put(
            f"/v1/{tid}/alerts/{alert.id}/analysis-status",
            params={"analysis_status": "completed"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    await integration_test_session.refresh(alert)
    assert alert.analysis_status == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_alert_analysis_status_allows_normal_transitions(
    integration_test_session,
):
    """Normal alert status transitions still work after the guard is added."""
    alert, _ = await _create_alert_with_analysis(
        integration_test_session,
        analysis_status="running",
        alert_status="in_progress",
    )
    tid = alert.tenant_id

    async with _make_client(integration_test_session) as client:
        response = await client.put(
            f"/v1/{tid}/alerts/{alert.id}/analysis-status",
            params={"analysis_status": "completed"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["analysis_status"] == "completed"
    await integration_test_session.refresh(alert)
    assert alert.analysis_status == "completed"


# ---------------------------------------------------------------------------
# 4. Worker unit-style test: early-exit when update_analysis_status → False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_exits_early_when_update_running_fails():
    """Worker aborts without running the pipeline if update_analysis_status returns False.

    When the REST API returns 409 (analysis was cancelled), the API client
    returns False. The worker must NOT call the pipeline in this case.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_api_client = MagicMock()
    # Simulate: setting "running" was rejected with 409 (analysis is cancelled).
    # BackendAPIClient.update_analysis_status returns None on 409 Conflict.
    mock_api_client.update_analysis_status = AsyncMock(return_value=None)
    mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)

    mock_pipeline = AsyncMock()
    mock_pipeline.execute = AsyncMock(return_value={"status": "completed"})

    tenant_id = "test-tenant"
    alert_id = str(uuid4())
    analysis_id = str(uuid4())

    with (
        patch(
            "analysi.alert_analysis.worker.BackendAPIClient",
            return_value=mock_api_client,
        ),
        patch(
            "analysi.alert_analysis.worker.AlertAnalysisPipeline",
            return_value=mock_pipeline,
        ),
        patch("analysi.alert_analysis.worker.AlertAnalysisDB") as mock_db_cls,
    ):
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        from analysi.alert_analysis.worker import process_alert_analysis

        result = await process_alert_analysis(
            None,  # ARQ context not used in unit test
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

    # Pipeline must NOT have been called
    mock_pipeline.execute.assert_not_called()
    # Should return a cancelled/skipped result (not raise)
    assert result is not None
