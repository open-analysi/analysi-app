"""Integration tests for Control Event Rules CRUD API."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.control_event import ControlEventRule

TENANT = "test-tenant"
BASE = f"/v1/{TENANT}/control-event-rules"


def _rule_payload(**overrides) -> dict:
    """Build a valid create payload."""
    defaults = {
        "name": f"test-rule-{uuid4().hex[:8]}",
        "channel": "disposition:ready",
        "target_type": "task",
        "target_id": str(uuid4()),
    }
    return {**defaults, **overrides}


@pytest.mark.integration
class TestControlEventRulesCRUD:
    """Integration tests for the control event rules REST API."""

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
    async def sample_rule(self, integration_test_session):
        """Pre-existing rule for tests that need an existing record."""
        rule = ControlEventRule(
            tenant_id=TENANT,
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="Sample Rule",
            enabled=True,
            config={},
        )
        integration_test_session.add(rule)
        await integration_test_session.flush()
        return rule

    # ------------------------------------------------------------------
    # POST — create
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_rule_returns_201(self, client):
        """POST creates a rule and returns 201 with all fields."""
        ac, _ = client
        payload = _rule_payload(config={"key": "value"})
        response = await ac.post(BASE, json=payload)

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == payload["name"]
        assert data["channel"] == payload["channel"]
        assert data["target_type"] == payload["target_type"]
        assert data["target_id"] == payload["target_id"]
        assert data["enabled"] is True
        assert data["config"] == {"key": "value"}
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_rule_with_enabled_false(self, client):
        """POST respects enabled=False."""
        ac, _ = client
        payload = _rule_payload(enabled=False)
        response = await ac.post(BASE, json=payload)

        assert response.status_code == 201
        assert response.json()["data"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_create_rule_invalid_target_type_returns_422(self, client):
        """POST rejects unknown target_type."""
        ac, _ = client
        response = await ac.post(BASE, json=_rule_payload(target_type="unknown"))
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_rule_missing_channel_returns_422(self, client):
        """POST rejects missing required field."""
        ac, _ = client
        payload = _rule_payload()
        del payload["channel"]
        response = await ac.post(BASE, json=payload)
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # GET list
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_rules_returns_all_for_tenant(self, client, sample_rule):
        """GET list returns all rules for the tenant."""
        ac, _ = client
        response = await ac.get(BASE)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] >= 1
        ids = [r["id"] for r in body["data"]]
        assert str(sample_rule.id) in ids

    @pytest.mark.asyncio
    async def test_list_rules_filter_by_channel(self, client, integration_test_session):
        """GET list ?channel=X returns only rules for that channel."""
        ac, session = client
        # Create rules on two different channels
        r1 = ControlEventRule(
            tenant_id=TENANT,
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="r1",
            enabled=True,
            config={},
        )
        r2 = ControlEventRule(
            tenant_id=TENANT,
            channel="analysis:failed",
            target_type="task",
            target_id=uuid4(),
            name="r2",
            enabled=True,
            config={},
        )
        session.add(r1)
        session.add(r2)
        await session.flush()

        response = await ac.get(BASE, params={"channel": "disposition:ready"})
        assert response.status_code == 200
        channels = {r["channel"] for r in response.json()["data"]}
        assert channels == {"disposition:ready"}

    @pytest.mark.asyncio
    async def test_list_rules_filter_enabled_only(
        self, client, integration_test_session
    ):
        """GET list ?enabled_only=true excludes disabled rules."""
        ac, session = client
        enabled_rule = ControlEventRule(
            tenant_id=TENANT,
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="enabled",
            enabled=True,
            config={},
        )
        disabled_rule = ControlEventRule(
            tenant_id=TENANT,
            channel="disposition:ready",
            target_type="task",
            target_id=uuid4(),
            name="disabled",
            enabled=False,
            config={},
        )
        session.add(enabled_rule)
        session.add(disabled_rule)
        await session.flush()

        response = await ac.get(BASE, params={"enabled_only": "true"})
        assert response.status_code == 200
        ids = {r["id"] for r in response.json()["data"]}
        assert str(enabled_rule.id) in ids
        assert str(disabled_rule.id) not in ids

    @pytest.mark.asyncio
    async def test_list_rules_empty_for_unknown_tenant(self, client):
        """GET list for an unknown tenant returns total=0."""
        ac, _ = client
        response = await ac.get("/v1/unknown-tenant-xyz/control-event-rules")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 0
        assert body["data"] == []

    # ------------------------------------------------------------------
    # GET by ID
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_rule_returns_200(self, client, sample_rule):
        """GET /{id} returns the rule."""
        ac, _ = client
        response = await ac.get(f"{BASE}/{sample_rule.id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == str(sample_rule.id)
        assert data["name"] == sample_rule.name

    @pytest.mark.asyncio
    async def test_get_rule_not_found_returns_404(self, client):
        """GET /{id} with unknown ID returns 404."""
        ac, _ = client
        response = await ac.get(f"{BASE}/{uuid4()}")
        assert response.status_code == 404

    # ------------------------------------------------------------------
    # PATCH — update
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_patch_rule_enabled_field(self, client, sample_rule):
        """PATCH /{id} toggles enabled."""
        ac, _ = client
        response = await ac.patch(f"{BASE}/{sample_rule.id}", json={"enabled": False})

        assert response.status_code == 200
        assert response.json()["data"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_patch_rule_name_only_leaves_other_fields(self, client, sample_rule):
        """PATCH with only name leaves other fields unchanged."""
        ac, _ = client
        new_name = "updated-name"
        response = await ac.patch(f"{BASE}/{sample_rule.id}", json={"name": new_name})

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == new_name
        assert data["enabled"] == sample_rule.enabled
        assert data["channel"] == sample_rule.channel

    @pytest.mark.asyncio
    async def test_patch_rule_empty_body_returns_400(self, client, sample_rule):
        """PATCH with no fields returns 400."""
        ac, _ = client
        response = await ac.patch(f"{BASE}/{sample_rule.id}", json={})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_rule_not_found_returns_404(self, client):
        """PATCH unknown ID returns 404."""
        ac, _ = client
        response = await ac.patch(f"{BASE}/{uuid4()}", json={"enabled": False})
        assert response.status_code == 404

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_rule_returns_204(self, client, sample_rule):
        """DELETE /{id} returns 204 and subsequent GET returns 404."""
        ac, _ = client
        response = await ac.delete(f"{BASE}/{sample_rule.id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await ac.get(f"{BASE}/{sample_rule.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_rule_not_found_returns_404(self, client):
        """DELETE unknown ID returns 404."""
        ac, _ = client
        response = await ac.delete(f"{BASE}/{uuid4()}")
        assert response.status_code == 404

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client, sample_rule):
        """A rule from tenant-A is not accessible under tenant-B."""
        ac, _ = client
        # sample_rule belongs to TENANT; request under different tenant
        other_tenant_url = f"/v1/other-tenant/control-event-rules/{sample_rule.id}"
        response = await ac.get(other_tenant_url)
        assert response.status_code == 404
