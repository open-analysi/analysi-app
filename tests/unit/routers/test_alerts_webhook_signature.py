"""End-to-end tests for the alert ingestion webhook-signature dependency.

The alert POST endpoint accepts an optional ``X-Webhook-Signature`` header.
When the tenant has a configured signing secret, the request must include
a valid HMAC over the raw body. When no secret is configured, the
endpoint behaves exactly as before (backward compatible).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import require_current_user
from analysi.auth.models import CurrentUser
from analysi.auth.webhook_signature import compute_signature
from analysi.dependencies.tenant import get_tenant_id
from analysi.routers.alerts import (
    _parse_webhook_secrets_map,
    get_tenant_webhook_secret,
    router,
)


def _platform_admin() -> CurrentUser:
    return CurrentUser(
        user_id="test",
        email="test@test.local",
        tenant_id="t1",
        roles=["platform_admin"],
        actor_type="user",
    )


def _tenant_id() -> str:
    return "t1"


def _alert_response_stub() -> dict:
    """Return a fully-populated AlertResponse instance the router can serialize."""
    from analysi.routers import alerts as alerts_router

    return alerts_router.AlertResponse(
        alert_id="00000000-0000-0000-0000-000000000001",
        human_readable_id="ALERT-1",
        tenant_id="t1",
        title="ok",
        severity="medium",
        analysis_status="new",
        raw_data='{"foo": "bar"}',
        raw_data_hash="0" * 64,
        ingested_at="2026-01-01T00:00:00Z",
        triggering_event_time="2026-01-01T00:00:00Z",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        source_vendor="okta",
        source_product="okta",
    )


@pytest.fixture
def app(monkeypatch):
    """Build a FastAPI app that exercises the alert webhook signature flow.

    Mocks `AlertService.create_alert` so we can focus on signature verification
    without a database.
    """
    from analysi.routers import alerts as alerts_router

    fake_service = AsyncMock()
    fake_service.create_alert = AsyncMock(return_value=_alert_response_stub())

    def _service_factory(*args, **kwargs):
        return fake_service

    monkeypatch.setattr(alerts_router, "AlertService", _service_factory)
    # Stub the DB session dep so it doesn't try to connect
    from analysi.db import session as session_module

    async def _no_db():
        yield None

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[require_current_user] = _platform_admin
    app.dependency_overrides[get_tenant_id] = _tenant_id
    app.dependency_overrides[session_module.get_db] = _no_db
    return app


def _alert_payload() -> dict:
    return {
        "title": "Suspicious Login",
        "severity": "high",
        "source_vendor": "okta",
        "source_product": "okta",
        "triggering_event_time": "2026-01-01T00:00:00Z",
        "raw_data": '{"foo": "bar"}',
    }


class TestAlertWebhookSignature:
    @pytest.mark.asyncio
    async def test_no_secret_configured_skips_verification(self, app):
        """When the tenant has no signing secret, request goes through
        without an X-Webhook-Signature header (backward compatible)."""
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/t1/alerts", json=_alert_payload())

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, app):
        """A request with a correct HMAC signature must succeed."""
        secret = "tenant-secret-1"
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: secret

        body = json.dumps(_alert_payload()).encode()
        sig = compute_signature(body, secret)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/t1/alerts",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": sig,
                },
            )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_missing_signature_rejected_when_secret_configured(self, app):
        """If the tenant configured a secret, requests without the header
        must be rejected — never silently fall back to no-signature."""
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: "tenant-secret"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/t1/alerts", json=_alert_payload())

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_wrong_signature_rejected(self, app):
        """A signature computed with the wrong secret must be rejected."""
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: "real-secret"

        body = json.dumps(_alert_payload()).encode()
        bad_sig = compute_signature(body, "attacker-secret")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/t1/alerts",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": bad_sig,
                },
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tenant_with_dash_or_dot_works(self, app, monkeypatch):
        """Regression: tenant IDs with characters like -, ., @ are valid per
        the tenant format regex but unusable in env-var names. The secret
        lookup must use a config source that handles all valid tenant IDs.

        Codex review on PR #42 commit c62b11ff1 — without this, signature
        verification silently stays disabled for those tenants.
        """
        # A tenant ID with a dash (currently allowed by tenant format regex)
        secret_map = '{"acme-prod": "the-secret"}'
        monkeypatch.setenv("ANALYSI_ALERT_WEBHOOK_SECRETS", secret_map)

        # Override the tenant_id dep to return the dashed tenant
        from analysi.dependencies.tenant import get_tenant_id as _get_tid

        app.dependency_overrides[_get_tid] = lambda: "acme-prod"

        body = json.dumps(_alert_payload()).encode()
        sig = compute_signature(body, "the-secret")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/acme-prod/alerts",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": sig,
                },
            )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_system_actor_is_exempt(self, app):
        """Regression: internal system-actor callers (integrations-worker
        posting alerts via X-API-Key) must not be blocked by webhook
        signature verification. They've already authenticated via a trusted
        API key; the HMAC is for untrusted external sources.

        Codex review on PR #42 commit 7b9b55e06 — without the exemption,
        enabling ANALYSI_ALERT_WEBHOOK_SECRETS silently stalls internal
        alert ingestion/analysis.
        """
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: "tenant-secret"

        # Replace the default (user) actor with a system actor
        def _system_actor() -> CurrentUser:
            return CurrentUser(
                user_id="internal",
                email="system@internal",
                tenant_id="t1",
                roles=["system"],
                actor_type="system",
            )

        app.dependency_overrides[require_current_user] = _system_actor

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # No X-Webhook-Signature header, yet the request must succeed
            response = await client.post("/v1/t1/alerts", json=_alert_payload())

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_non_system_actor_still_requires_signature(self, app):
        """Companion to the system-actor exemption: user/api_key actors
        are NOT exempt — they must still provide a valid signature when
        the tenant has the secret configured. Prevents privilege-downgrade
        bypasses."""
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: "tenant-secret"

        def _user_actor() -> CurrentUser:
            return CurrentUser(
                user_id="regular-user",
                email="user@t1.local",
                tenant_id="t1",
                # platform_admin so permission check passes; the point of the
                # test is that signature is required regardless of role.
                roles=["platform_admin"],
                actor_type="user",
            )

        app.dependency_overrides[require_current_user] = _user_actor

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/t1/alerts", json=_alert_payload())

        # No signature, non-system actor → still rejected
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_body_rejected(self, app):
        """A signature for a different body must be rejected — replay defense."""
        secret = "tenant-secret"
        app.dependency_overrides[get_tenant_webhook_secret] = lambda: secret

        original = json.dumps(_alert_payload()).encode()
        sig = compute_signature(original, secret)

        # Tamper with the body — same signature
        tampered = json.dumps({**_alert_payload(), "title": "Tampered!"}).encode()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/t1/alerts",
                content=tampered,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": sig,
                },
            )
        assert response.status_code == 401


class TestWebhookSecretsMapParsing:
    """Tests for the JSON-map config source for per-tenant webhook secrets."""

    def test_empty_or_unset_returns_empty_map(self):
        assert _parse_webhook_secrets_map(None) == {}
        assert _parse_webhook_secrets_map("") == {}

    def test_parses_valid_json_object(self):
        m = _parse_webhook_secrets_map('{"default": "s1", "acme-prod": "s2"}')
        assert m == {"default": "s1", "acme-prod": "s2"}

    def test_handles_dotted_and_at_tenants(self):
        """Tenants with `.` and `@` (allowed by validator) must round-trip."""
        m = _parse_webhook_secrets_map('{"foo.bar": "x", "user@example.com": "y"}')
        assert m["foo.bar"] == "x"
        assert m["user@example.com"] == "y"

    def test_rejects_non_string_values(self):
        """A value that isn't a string is silently dropped — never crash."""
        m = _parse_webhook_secrets_map('{"default": 12345, "acme": "ok"}')
        assert "default" not in m
        assert m["acme"] == "ok"

    def test_invalid_json_returns_empty_map(self):
        """Don't crash startup on malformed config — fail safe."""
        assert _parse_webhook_secrets_map("not json") == {}
        assert _parse_webhook_secrets_map("[1, 2, 3]") == {}
        assert _parse_webhook_secrets_map('"just a string"') == {}
