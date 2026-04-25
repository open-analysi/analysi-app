"""Unit tests for the Valkey-backed rate limiter.

The in-memory `SlidingWindowRateLimiter` is a single-process design — under
multiple API workers an attacker can bypass the limit by spreading requests
across processes. `ValkeyRateLimiter` shares state across all workers via
INCR + EXPIRE in Valkey.
"""

from __future__ import annotations

import asyncio

import fakeredis.aioredis as fakeredis
import pytest

from analysi.auth.rate_limit import ValkeyRateLimiter


@pytest.fixture
async def fake_valkey():
    """A FakeRedis instance per test (auto-cleared)."""
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


class TestValkeyRateLimiter:
    """Atomic counter semantics, shared across processes (simulated)."""

    @pytest.mark.asyncio
    async def test_allows_first_attempt(self, fake_valkey):
        limiter = ValkeyRateLimiter(
            fake_valkey, max_attempts=5, window_seconds=60, key_prefix="test"
        )
        assert await limiter.check_and_record("key1") is True

    @pytest.mark.asyncio
    async def test_allows_up_to_max_attempts(self, fake_valkey):
        limiter = ValkeyRateLimiter(
            fake_valkey, max_attempts=5, window_seconds=60, key_prefix="test"
        )
        for _ in range(5):
            assert await limiter.check_and_record("key1") is True

    @pytest.mark.asyncio
    async def test_blocks_on_overflow_attempt(self, fake_valkey):
        limiter = ValkeyRateLimiter(
            fake_valkey, max_attempts=5, window_seconds=60, key_prefix="test"
        )
        for _ in range(5):
            await limiter.check_and_record("key1")
        assert await limiter.check_and_record("key1") is False

    @pytest.mark.asyncio
    async def test_different_keys_are_independent(self, fake_valkey):
        limiter = ValkeyRateLimiter(
            fake_valkey, max_attempts=3, window_seconds=60, key_prefix="test"
        )
        for _ in range(3):
            await limiter.check_and_record("a")
        assert await limiter.check_and_record("a") is False
        assert await limiter.check_and_record("b") is True

    @pytest.mark.asyncio
    async def test_window_expiry_resets_count(self, fake_valkey):
        """When the bucket TTL elapses, the next request must be allowed."""
        limiter = ValkeyRateLimiter(
            fake_valkey, max_attempts=2, window_seconds=1, key_prefix="test"
        )
        await limiter.check_and_record("key1")
        await limiter.check_and_record("key1")
        assert await limiter.check_and_record("key1") is False

        # Wait past the window
        await asyncio.sleep(1.2)
        assert await limiter.check_and_record("key1") is True

    @pytest.mark.asyncio
    async def test_distinct_prefixes_dont_collide(self, fake_valkey):
        """Two limiters with the same key string but different prefixes are
        independent — important for sharing one Valkey across multiple
        rate-limited operations."""
        a = ValkeyRateLimiter(
            fake_valkey, max_attempts=2, window_seconds=60, key_prefix="invite"
        )
        b = ValkeyRateLimiter(
            fake_valkey, max_attempts=2, window_seconds=60, key_prefix="mcp"
        )
        await a.check_and_record("k")
        await a.check_and_record("k")
        # invite limiter exhausted
        assert await a.check_and_record("k") is False
        # mcp limiter for the same key still has full budget
        assert await b.check_and_record("k") is True

    @pytest.mark.asyncio
    async def test_shared_state_across_limiter_instances(self, fake_valkey):
        """Two limiter objects (simulating two API worker processes) sharing
        the same Valkey + prefix MUST share the budget — this is the whole
        point of the Valkey backend vs. the in-memory one."""
        worker_1 = ValkeyRateLimiter(
            fake_valkey, max_attempts=3, window_seconds=60, key_prefix="test"
        )
        worker_2 = ValkeyRateLimiter(
            fake_valkey, max_attempts=3, window_seconds=60, key_prefix="test"
        )

        # Worker 1 makes 2 requests
        await worker_1.check_and_record("user-x")
        await worker_1.check_and_record("user-x")
        # Worker 2 makes 1 — should still be allowed (3rd total)
        assert await worker_2.check_and_record("user-x") is True
        # Worker 2 makes another — must be blocked (4th)
        assert await worker_2.check_and_record("user-x") is False
        # Worker 1 also blocked
        assert await worker_1.check_and_record("user-x") is False
