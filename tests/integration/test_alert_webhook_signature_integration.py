"""Integration tests for alert-ingestion webhook-signature enforcement.

These run the full FastAPI stack end-to-end (real DB session, real
AlertService, real router dependency chain) — complementing the mock-
based unit tests in tests/unit/routers/test_alerts_webhook_signature.py.

The regression they defend against:

  Sprint A introduced HMAC signature verification on POST /alerts.
  A subsequent Codex review (commit 8c64b12c3) discovered that the
  internal integrations-worker path
    Cy ingest_alerts() → AlertService.create_alert()
    → POST /v1/{tenant}/alerts with X-API-Key (system actor)
  would be blocked once a tenant enabled ANALYSI_ALERT_WEBHOOK_SECRETS,
  silently stalling all pull-mode ingestion. The fix: exempt
  actor_type == "system" from the signature requirement.

These integration tests lock that invariant down against the ACTUAL
endpoint + service + DB so future refactors can't regress it.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import require_current_user
from analysi.auth.models import CurrentUser
from analysi.auth.webhook_signature import compute_signature
from analysi.db.session import get_db
from analysi.main import app


def _system_actor(tenant: str) -> CurrentUser:
    """Construct a CurrentUser exactly as api_key.validate_api_key would
    return for a provisioned system API key (user_id IS NULL in DB)."""
    return CurrentUser(
        user_id="system:test-prefix",
        email="system@analysi.internal",
        tenant_id=tenant,
        roles=["system"],
        actor_type="system",
    )


def _user_actor(tenant: str) -> CurrentUser:
    """A regular tenant admin (platform_admin to clear RBAC)."""
    return CurrentUser(
        user_id=f"kc-{uuid4().hex[:8]}",
        email="admin@tenant.local",
        tenant_id=tenant,
        roles=["platform_admin"],
        actor_type="user",
    )


def _alert_payload() -> dict:
    return {
        "title": "Integration-test Alert",
        "triggering_event_time": datetime.now(UTC).isoformat(),
        "severity": "medium",
        "source_vendor": "test-vendor",
        "source_product": "test-product",
        "raw_data": json.dumps({"id": uuid4().hex, "payload": "x"}),
    }


@pytest.mark.integration
class TestAlertWebhookSignatureActorExemption:
    """Full-stack behaviour of the actor-type exemption on /alerts."""

    @pytest.fixture
    async def stack(
        self, integration_test_session, monkeypatch
    ) -> AsyncGenerator[tuple[AsyncClient, str]]:
        """Wire the real DB into the app and yield (client, tenant)."""
        tenant = f"t-{uuid4().hex[:8]}"

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Enable webhook signature for this tenant
        secrets_map = json.dumps({tenant: "the-tenant-secret"})
        monkeypatch.setenv("ANALYSI_ALERT_WEBHOOK_SECRETS", secrets_map)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, tenant

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_system_actor_ingests_without_signature(self, stack):
        """Regression: with ANALYSI_ALERT_WEBHOOK_SECRETS enabled for the
        tenant, a system-actor call (no X-Webhook-Signature header) must
        still create the alert. This is the integrations-worker path."""
        client, tenant = stack
        app.dependency_overrides[require_current_user] = lambda: _system_actor(tenant)

        response = await client.post(f"/v1/{tenant}/alerts", json=_alert_payload())

        assert response.status_code == 201, (
            f"System actor was blocked by webhook signature check — this "
            f"would silently stall internal ingestion. body={response.text}"
        )
        body = response.json()["data"]
        assert body["title"] == "Integration-test Alert"
        assert "alert_id" in body

    @pytest.mark.asyncio
    async def test_user_actor_without_signature_is_rejected(self, stack):
        """Companion: a non-system actor (even platform_admin) must still
        provide a valid signature when the tenant has the feature enabled.
        Prevents bypass by downgrading actor_type or role."""
        client, tenant = stack
        app.dependency_overrides[require_current_user] = lambda: _user_actor(tenant)

        response = await client.post(f"/v1/{tenant}/alerts", json=_alert_payload())

        assert response.status_code == 401, (
            f"User-actor call with no signature should have been rejected "
            f"(got {response.status_code}): {response.text}"
        )

    @pytest.mark.asyncio
    async def test_user_actor_with_valid_signature_succeeds(self, stack):
        """Happy-path external caller: correct HMAC over the raw body
        passes through end-to-end and creates the alert."""
        client, tenant = stack
        app.dependency_overrides[require_current_user] = lambda: _user_actor(tenant)

        body = json.dumps(_alert_payload()).encode()
        sig = compute_signature(body, "the-tenant-secret")

        response = await client.post(
            f"/v1/{tenant}/alerts",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )

        assert response.status_code == 201, (
            f"Signed user-actor call should have succeeded: {response.text}"
        )
