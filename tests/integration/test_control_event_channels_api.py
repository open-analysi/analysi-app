"""Integration tests for Control Event Channel Registry API.

TDD: tests written before implementation.
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.control_event import ControlEventRule

TENANT = f"test-tenant-{uuid4().hex[:8]}"
BASE = f"/v1/{TENANT}/control-event-channels"


@pytest.mark.integration
class TestControlEventChannelsAPI:
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

    @pytest.fixture
    async def rule_with_custom_channel(self, integration_test_session):
        """A rule using a custom (non-system) channel."""
        rule = ControlEventRule(
            tenant_id=TENANT,
            channel="my-custom-channel",
            target_type="task",
            target_id=uuid4(),
            name="custom-rule",
        )
        integration_test_session.add(rule)
        await integration_test_session.commit()
        return rule

    # ------------------------------------------------------------------
    # System channels always present
    # ------------------------------------------------------------------

    async def test_system_channels_always_returned(self, client):
        """System channels appear even when tenant has no rules."""
        ac, _ = client
        response = await ac.get(BASE)
        assert response.status_code == 200
        channels = {c["channel"]: c for c in response.json()["data"]}
        assert "disposition:ready" in channels
        assert "analysis:failed" in channels

    async def test_system_channels_have_correct_type(self, client):
        """System channels are marked type='system'."""
        ac, _ = client
        response = await ac.get(BASE)
        channels = {c["channel"]: c for c in response.json()["data"]}
        assert channels["disposition:ready"]["type"] == "system"
        assert channels["analysis:failed"]["type"] == "system"

    async def test_system_channels_have_description(self, client):
        """System channels include a non-empty description."""
        ac, _ = client
        response = await ac.get(BASE)
        channels = {c["channel"]: c for c in response.json()["data"]}
        assert channels["disposition:ready"]["description"]
        assert channels["analysis:failed"]["description"]

    async def test_system_channels_have_payload_fields(self, client):
        """System channels list their known payload fields."""
        ac, _ = client
        response = await ac.get(BASE)
        channels = {c["channel"]: c for c in response.json()["data"]}
        assert "alert_id" in channels["disposition:ready"]["payload_fields"]
        assert "alert_id" in channels["analysis:failed"]["payload_fields"]

    # ------------------------------------------------------------------
    # Configured channels derived from rules
    # ------------------------------------------------------------------

    async def test_custom_channel_from_rule_appears(
        self, client, rule_with_custom_channel
    ):
        """A channel used in a tenant rule appears as type='configured'."""
        ac, _ = client
        response = await ac.get(BASE)
        channels = {c["channel"]: c for c in response.json()["data"]}
        assert "my-custom-channel" in channels
        assert channels["my-custom-channel"]["type"] == "configured"

    async def test_system_channel_not_duplicated_when_used_in_rule(
        self, client, integration_test_session
    ):
        """A rule using a system channel doesn't cause it to appear twice."""
        rule = ControlEventRule(
            tenant_id=TENANT,
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="system-channel-rule",
        )
        integration_test_session.add(rule)
        await integration_test_session.commit()

        ac, _ = client
        response = await ac.get(BASE)
        channel_names = [c["channel"] for c in response.json()["data"]]
        assert channel_names.count("disposition:ready") == 1

    async def test_other_tenant_channels_not_returned(
        self, client, integration_test_session
    ):
        """Channels from other tenants are not visible."""
        other_rule = ControlEventRule(
            tenant_id="other-tenant",
            channel="other-tenant-channel",
            target_type="task",
            target_id=uuid4(),
            name="other-rule",
        )
        integration_test_session.add(other_rule)
        await integration_test_session.commit()

        ac, _ = client
        response = await ac.get(BASE)
        channel_names = [c["channel"] for c in response.json()["data"]]
        assert "other-tenant-channel" not in channel_names

    async def test_total_matches_channels_count(self, client, rule_with_custom_channel):
        """total field matches length of channels list."""
        ac, _ = client
        response = await ac.get(BASE)
        data = response.json()
        assert data["meta"]["total"] == len(data["data"])
