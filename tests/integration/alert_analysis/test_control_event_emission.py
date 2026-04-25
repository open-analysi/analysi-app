"""Integration tests for control event emission from analysis endpoints."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.models.control_event import ControlEvent

TENANT = "test-tenant"


@pytest.fixture
async def http_client(integration_test_session):
    async def override_get_db():
        yield integration_test_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, integration_test_session
    app.dependency_overrides.clear()


@pytest.fixture
async def disposition(integration_test_session):
    """Return the first system disposition."""
    result = await integration_test_session.execute(
        select(Disposition).where(Disposition.is_system.is_(True)).limit(1)
    )
    d = result.scalar_one_or_none()
    assert d is not None, "System dispositions must be seeded"
    return d


@pytest.fixture
async def alert_and_analysis(integration_test_session):
    """Create an Alert + running AlertAnalysis pair."""
    alert = Alert(
        tenant_id=TENANT,
        human_readable_id=f"AID-TILOS-{uuid4().hex[:6]}",
        title="Tilos test alert",
        triggering_event_time=datetime.now(UTC),
        severity="high",
        raw_data='{"test": "data"}',
        raw_data_hash=f"tilos_hash_{uuid4().hex}",
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status="in_progress",
    )
    integration_test_session.add(alert)
    await integration_test_session.flush()

    analysis = AlertAnalysis(
        alert_id=alert.id,
        tenant_id=TENANT,
        status="running",
    )
    integration_test_session.add(analysis)
    await integration_test_session.flush()
    await integration_test_session.commit()
    return alert, analysis


async def _count_control_events(session, tenant_id: str, channel: str) -> int:
    result = await session.execute(
        select(ControlEvent).where(
            ControlEvent.tenant_id == tenant_id,
            ControlEvent.channel == channel,
        )
    )
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# complete_analysis → disposition:ready
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_analysis_emits_disposition_ready(
    http_client, alert_and_analysis, disposition
):
    """Completing an analysis creates exactly one disposition:ready control event."""
    ac, session = http_client
    alert, analysis = alert_and_analysis

    response = await ac.put(
        f"/v1/{TENANT}/analyses/{analysis.id}/complete",
        json={
            "disposition_id": str(disposition.id),
            "confidence": 90,
            "short_summary": "Test summary",
            "long_summary": "Test long summary",
        },
    )
    assert response.status_code == 200

    # Verify exactly one disposition:ready event was created
    count = await _count_control_events(session, TENANT, "disposition:ready")
    assert count == 1

    # Verify payload fields
    result = await session.execute(
        select(ControlEvent).where(
            ControlEvent.tenant_id == TENANT,
            ControlEvent.channel == "disposition:ready",
        )
    )
    event = result.scalar_one()
    assert event.payload["alert_id"] == str(alert.id)
    assert event.payload["analysis_id"] == str(analysis.id)
    assert event.payload["disposition_id"] == str(disposition.id)
    assert event.payload["confidence"] == 90


@pytest.mark.integration
@pytest.mark.asyncio
async def test_double_complete_analysis_emits_only_one_event(
    http_client, alert_and_analysis, disposition
):
    """Second call to complete_analysis does not emit a second control event."""
    ac, session = http_client
    _, analysis = alert_and_analysis

    body = {
        "disposition_id": str(disposition.id),
        "confidence": 80,
        "short_summary": "s",
        "long_summary": "l",
    }

    r1 = await ac.put(f"/v1/{TENANT}/analyses/{analysis.id}/complete", json=body)
    assert r1.status_code == 200

    r2 = await ac.put(f"/v1/{TENANT}/analyses/{analysis.id}/complete", json=body)
    assert r2.status_code == 200

    count = await _count_control_events(session, TENANT, "disposition:ready")
    assert count == 1  # transition guard prevents second emission


# ---------------------------------------------------------------------------
# update_analysis_status(failed) → analysis:failed
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_status_emits_analysis_failed_event(
    http_client, alert_and_analysis
):
    """Setting status=failed creates exactly one analysis:failed control event."""
    ac, session = http_client
    alert, analysis = alert_and_analysis

    response = await ac.put(
        f"/v1/{TENANT}/analyses/{analysis.id}/status",
        params={"status": "failed", "error": "something broke"},
    )
    assert response.status_code == 200

    count = await _count_control_events(session, TENANT, "analysis:failed")
    assert count == 1

    result = await session.execute(
        select(ControlEvent).where(
            ControlEvent.tenant_id == TENANT,
            ControlEvent.channel == "analysis:failed",
        )
    )
    event = result.scalar_one()
    assert event.payload["alert_id"] == str(alert.id)
    assert event.payload["analysis_id"] == str(analysis.id)
    assert event.payload["error"] == "something broke"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_double_failed_status_emits_only_one_event(
    http_client, alert_and_analysis
):
    """Second call with status=failed does not emit a second control event."""
    ac, session = http_client
    _, analysis = alert_and_analysis

    await ac.put(
        f"/v1/{TENANT}/analyses/{analysis.id}/status",
        params={"status": "failed", "error": "first"},
    )
    await ac.put(
        f"/v1/{TENANT}/analyses/{analysis.id}/status",
        params={"status": "failed", "error": "second"},
    )

    count = await _count_control_events(session, TENANT, "analysis:failed")
    assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_failed_status_does_not_emit_event(http_client, alert_and_analysis):
    """status=running and status=completed do not emit analysis:failed events."""
    ac, session = http_client
    _, analysis = alert_and_analysis

    await ac.put(
        f"/v1/{TENANT}/analyses/{analysis.id}/status",
        params={"status": "running"},
    )

    count = await _count_control_events(session, TENANT, "analysis:failed")
    assert count == 0
