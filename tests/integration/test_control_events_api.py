"""Integration tests for Control Events API (manual trigger + history)."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

TENANT = f"test-tenant-{uuid4().hex[:8]}"
BASE = f"/v1/{TENANT}/control-events"


@pytest.mark.integration
class TestControlEventsAPI:
    """Integration tests for POST/GET control events."""

    @pytest.fixture
    async def client(self, integration_test_session):
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, integration_test_session
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # POST — manual trigger
    # ------------------------------------------------------------------

    async def test_create_event_returns_201_with_pending_status(self, client):
        """Manually created event starts as pending."""
        ac, _ = client
        response = await ac.post(
            BASE,
            json={
                "channel": "disposition:ready",
                "payload": {
                    "alert_id": str(uuid4()),
                    "disposition": "Confirmed Compromise",
                },
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["channel"] == "disposition:ready"
        assert data["status"] == "pending"
        assert data["retry_count"] == 0
        assert data["tenant_id"] == TENANT
        assert "id" in data
        assert data["payload"]["disposition"] == "Confirmed Compromise"

    async def test_create_event_with_empty_payload(self, client):
        """Payload is optional — defaults to empty dict."""
        ac, _ = client
        response = await ac.post(BASE, json={"channel": "my-custom-channel"})
        assert response.status_code == 201
        assert response.json()["data"]["payload"] == {}

    async def test_create_event_missing_channel_returns_422(self, client):
        """channel is required."""
        ac, _ = client
        response = await ac.post(BASE, json={"payload": {}})
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # GET list — history
    # ------------------------------------------------------------------

    async def test_list_events_returns_created_events(self, client):
        """Created events appear in the list."""
        ac, _ = client
        channel = f"test-channel-{uuid4().hex[:8]}"

        await ac.post(BASE, json={"channel": channel, "payload": {"n": 1}})
        await ac.post(BASE, json={"channel": channel, "payload": {"n": 2}})

        response = await ac.get(BASE, params={"channel": channel})
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2
        assert len(body["data"]) == 2

    async def test_list_events_filter_by_channel(self, client):
        """Channel filter returns only matching events."""
        ac, _ = client
        ch_a = f"ch-a-{uuid4().hex[:6]}"
        ch_b = f"ch-b-{uuid4().hex[:6]}"

        await ac.post(BASE, json={"channel": ch_a})
        await ac.post(BASE, json={"channel": ch_b})

        resp_a = await ac.get(BASE, params={"channel": ch_a})
        assert resp_a.json()["meta"]["total"] == 1
        assert resp_a.json()["data"][0]["channel"] == ch_a

    async def test_list_events_filter_by_status(self, client):
        """Status filter returns only matching events."""
        ac, _ = client
        channel = f"status-test-{uuid4().hex[:6]}"

        await ac.post(BASE, json={"channel": channel})

        resp_pending = await ac.get(
            BASE, params={"channel": channel, "status": "pending"}
        )
        assert resp_pending.json()["meta"]["total"] == 1

        resp_processed = await ac.get(
            BASE, params={"channel": channel, "status": "completed"}
        )
        assert resp_processed.json()["meta"]["total"] == 0

    async def test_list_events_newest_first(self, client):
        """Events are returned newest first."""
        ac, _ = client
        channel = f"order-test-{uuid4().hex[:6]}"

        await ac.post(BASE, json={"channel": channel, "payload": {"seq": 1}})
        await ac.post(BASE, json={"channel": channel, "payload": {"seq": 2}})

        response = await ac.get(BASE, params={"channel": channel})
        events = response.json()["data"]
        assert events[0]["payload"]["seq"] == 2
        assert events[1]["payload"]["seq"] == 1

    # ------------------------------------------------------------------
    # GET single event
    # ------------------------------------------------------------------

    async def test_get_event_by_id(self, client):
        """GET /{event_id} returns the correct event."""
        ac, _ = client
        create_resp = await ac.post(
            BASE,
            json={
                "channel": "disposition:ready",
                "payload": {"alert_id": "test-123"},
            },
        )
        event_id = create_resp.json()["data"]["id"]

        get_resp = await ac.get(f"{BASE}/{event_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == event_id
        assert get_resp.json()["data"]["payload"]["alert_id"] == "test-123"

    async def test_get_nonexistent_event_returns_404(self, client):
        """Unknown event ID returns 404."""
        ac, _ = client
        response = await ac.get(f"{BASE}/{uuid4()}")
        assert response.status_code == 404
