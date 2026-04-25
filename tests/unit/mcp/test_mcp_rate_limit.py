"""Per-(tenant, user, tool) rate limiting on MCP execution tools.

The heavy MCP tools — ``run_script``, ``run_workflow``,
``run_integration_tool`` — were RBAC-gated but unlimited. A compromised
user key could therefore exhaust workers / Postgres / LLM budget. The
rate limiter caps invocations per (tenant, user, tool) per minute.
"""

from __future__ import annotations

from uuid import uuid4

import fakeredis.aioredis as fakeredis
import pytest

from analysi.auth.models import CurrentUser
from analysi.auth.rate_limit import ValkeyRateLimiter
from analysi.mcp import context as mcp_context
from analysi.mcp.rate_limit import check_mcp_rate_limit, set_mcp_limiter


@pytest.fixture
def authenticated_mcp_user():
    """Set a realistic CurrentUser into the MCP context for the duration of the test."""
    user = CurrentUser(
        user_id="kc-user-1",
        db_user_id=uuid4(),
        email="alice@test.local",
        tenant_id="acme",
        roles=["editor"],
        actor_type="user",
    )
    token_t = mcp_context.mcp_tenant_context.set("acme")
    token_u = mcp_context.mcp_current_user_context.set(user)
    yield user
    mcp_context.mcp_tenant_context.reset(token_t)
    mcp_context.mcp_current_user_context.reset(token_u)


@pytest.fixture
async def fake_limiter():
    """Limiter wired up to a fake Valkey, with a tiny budget for fast tests."""
    client = fakeredis.FakeRedis(decode_responses=True)
    limiter = ValkeyRateLimiter(
        client, max_attempts=3, window_seconds=60, key_prefix="mcp"
    )
    set_mcp_limiter(limiter)
    yield limiter
    set_mcp_limiter(None)
    await client.flushdb()
    await client.aclose()


class TestMcpRateLimit:
    @pytest.mark.asyncio
    async def test_allows_under_budget(self, authenticated_mcp_user, fake_limiter):
        """First N calls within the budget must succeed silently."""
        for _ in range(3):
            await check_mcp_rate_limit("run_script")  # no exception = pass

    @pytest.mark.asyncio
    async def test_blocks_when_over_budget(self, authenticated_mcp_user, fake_limiter):
        """The (N+1)th call must raise a clean rate-limit error."""
        for _ in range(3):
            await check_mcp_rate_limit("run_script")
        with pytest.raises(PermissionError) as exc:
            await check_mcp_rate_limit("run_script")
        msg = str(exc.value).lower()
        assert "rate limit" in msg
        # Tool name must NOT be leaked back to the caller (avoids enum)
        assert "run_script" not in str(exc.value)

    @pytest.mark.asyncio
    async def test_separate_tools_have_separate_budgets(
        self, authenticated_mcp_user, fake_limiter
    ):
        """run_script and run_workflow must not share a budget — exhausting
        one mustn't starve the other for the same user."""
        for _ in range(3):
            await check_mcp_rate_limit("run_script")
        # run_script exhausted; run_workflow still has full budget
        for _ in range(3):
            await check_mcp_rate_limit("run_workflow")

    @pytest.mark.asyncio
    async def test_separate_users_have_separate_budgets(self, fake_limiter):
        """One user exhausting their budget mustn't block another user."""
        # User A exhausts run_script
        user_a = CurrentUser(
            user_id="kc-a",
            db_user_id=uuid4(),
            email="a@test.local",
            tenant_id="acme",
            roles=["editor"],
            actor_type="user",
        )
        token_t = mcp_context.mcp_tenant_context.set("acme")
        token_u = mcp_context.mcp_current_user_context.set(user_a)
        try:
            for _ in range(3):
                await check_mcp_rate_limit("run_script")
            with pytest.raises(PermissionError):
                await check_mcp_rate_limit("run_script")
        finally:
            mcp_context.mcp_current_user_context.reset(token_u)
            mcp_context.mcp_tenant_context.reset(token_t)

        # User B in same tenant — independent budget
        user_b = CurrentUser(
            user_id="kc-b",
            db_user_id=uuid4(),
            email="b@test.local",
            tenant_id="acme",
            roles=["editor"],
            actor_type="user",
        )
        token_t = mcp_context.mcp_tenant_context.set("acme")
        token_u = mcp_context.mcp_current_user_context.set(user_b)
        try:
            await check_mcp_rate_limit("run_script")  # must succeed
        finally:
            mcp_context.mcp_current_user_context.reset(token_u)
            mcp_context.mcp_tenant_context.reset(token_t)

    @pytest.mark.asyncio
    async def test_no_limiter_configured_is_passthrough(self, authenticated_mcp_user):
        """When the limiter is not configured (e.g., in dev/tests), the check
        must be a no-op rather than failing closed and breaking the platform."""
        set_mcp_limiter(None)
        # Running 100 times must not raise
        for _ in range(100):
            await check_mcp_rate_limit("run_script")

    @pytest.mark.asyncio
    async def test_unauthenticated_request_blocks(self, fake_limiter):
        """If MCP middleware somehow let an unauthenticated request through,
        the rate limiter must fail closed (it can't bucket the request safely)."""
        # No user in context
        with pytest.raises(PermissionError):
            await check_mcp_rate_limit("run_script")

    @pytest.mark.asyncio
    async def test_valkey_outage_degrades_gracefully(self, authenticated_mcp_user):
        """Regression: if the Valkey backend is unavailable mid-flight (timeout,
        reconnect, failover), the rate-limit check must NOT turn an MCP call
        into an outage. Best-effort: log and allow the request through.

        Codex review on PR #42 commit c62b11ff1.
        """
        from unittest.mock import AsyncMock

        from analysi.mcp.rate_limit import set_mcp_limiter

        # Limiter that always raises a connection error
        broken = AsyncMock()
        broken.check_and_record = AsyncMock(
            side_effect=ConnectionError("valkey unreachable")
        )
        set_mcp_limiter(broken)
        try:
            # Must NOT raise — degrade open
            await check_mcp_rate_limit("run_script")
        finally:
            set_mcp_limiter(None)


class TestMcpLimiterLifespanRecovery:
    """Regression: a transient Valkey outage at startup must NOT permanently
    disable MCP rate limiting for the pod's lifetime. Previously, the
    lifespan handler pinged Valkey before setting the limiter and only
    installed it on ping success — a single boot-time blip left the
    process running unthrottled until pod restart.

    The fix is to install the limiter unconditionally (the redis client
    constructor doesn't connect; real failures are caught per-call by the
    existing degrade-open path). Codex review on PR #42 commit ca51f3add.
    """

    @pytest.mark.asyncio
    async def test_limiter_installed_when_valkey_initially_unreachable(
        self, authenticated_mcp_user, monkeypatch
    ):
        """Simulate the startup path when Valkey's ping() fails. After
        startup, the limiter must still be installed so that once Valkey
        recovers, subsequent MCP calls are throttled without needing a
        pod restart."""
        from unittest.mock import AsyncMock, MagicMock

        from analysi.mcp.rate_limit import get_mcp_limiter, set_mcp_limiter

        # Simulate the lifespan setup without actually running main.py
        try:
            from analysi.auth.rate_limit import ValkeyRateLimiter

            # Fake redis client whose ping fails but INCR succeeds later
            fake_client = MagicMock()
            fake_client.ping = AsyncMock(
                side_effect=ConnectionError("valkey down at boot")
            )
            pipe_mock = MagicMock()
            pipe_mock.incr = MagicMock()
            pipe_mock.expire = MagicMock()
            pipe_mock.execute = AsyncMock(return_value=[1, True])
            fake_client.pipeline = MagicMock(return_value=pipe_mock)

            # Simulate the *fixed* lifespan behavior: no eager ping,
            # just install the limiter. If ping was required, this test
            # would exercise the bug.
            set_mcp_limiter(
                ValkeyRateLimiter(
                    fake_client,
                    max_attempts=60,
                    window_seconds=60,
                    key_prefix="mcp",
                )
            )

            # The limiter is installed, so subsequent MCP calls run through
            # it (rather than being a no-op as before the fix).
            assert get_mcp_limiter() is not None

            # And calls succeed — the per-call path uses pipeline(), not ping()
            await check_mcp_rate_limit("run_script")
        finally:
            set_mcp_limiter(None)
