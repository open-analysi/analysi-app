"""Rate limiters for auth and tool-execution endpoints.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)

This module provides two implementations:

- ``SlidingWindowRateLimiter`` — single-process, in-memory. Useful for tests
  and single-worker dev deployments. NOT suitable for multi-worker production
  because each worker has its own bucket and an attacker can bypass the limit
  by spreading requests across processes.

- ``ValkeyRateLimiter`` — async, distributed via Valkey/Redis ``INCR + EXPIRE``.
  Atomic and shared across all workers. This is the production-correct option.

Both expose a ``check_and_record(key) -> bool`` method (sync for the in-memory
limiter, async for the Valkey one).
"""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis_async


class SlidingWindowRateLimiter:
    """Thread-unsafe but async-safe in-memory sliding-window rate limiter."""

    def __init__(self, max_attempts: int, window_seconds: int = 3600) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}

    def check_and_record(self, key: str) -> bool:
        """Return True and record the attempt if under the limit; False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        if key not in self._buckets:
            self._buckets[key] = deque()

        bucket = self._buckets[key]

        # Evict entries outside the window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_attempts:
            return False

        bucket.append(now)
        return True


class ValkeyRateLimiter:
    """Async, distributed fixed-window rate limiter backed by Valkey/Redis.

    Uses ``INCR`` + ``EXPIRE`` (NX) atomically via a pipeline. The TTL is set
    only on the first hit in a window, so subsequent hits don't extend the
    window — this gives clean fixed-window semantics:

      window 1 [t=0..60s]   accept up to N requests
      window 2 [t=60..120s] accept up to N requests
      ...

    Multiple worker processes sharing the same Valkey + ``key_prefix`` share a
    single budget per key, which closes the bypass that the in-memory limiter
    has under multi-worker deployments.
    """

    def __init__(
        self,
        client: redis_async.Redis,
        max_attempts: int,
        window_seconds: int,
        *,
        key_prefix: str,
    ) -> None:
        if not key_prefix:
            raise ValueError("key_prefix is required to avoid cross-feature collisions")
        self._client = client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._key_prefix = key_prefix

    def _full_key(self, key: str) -> str:
        return f"ratelimit:{self._key_prefix}:{key}"

    async def check_and_record(self, key: str) -> bool:
        """Return True and record the attempt if under the limit; False if rate-limited.

        The INCR+EXPIRE pair runs in a pipeline; INCR is atomic and EXPIRE
        with ``nx=True`` only sets the TTL on the first hit (so the window
        doesn't slide forward on every request).
        """
        full_key = self._full_key(key)
        pipe = self._client.pipeline(transaction=False)
        pipe.incr(full_key)
        pipe.expire(full_key, self.window_seconds, nx=True)
        results = await pipe.execute()
        count = int(results[0])
        return count <= self.max_attempts


# Module-level singleton used by the accept-invite endpoint.
# 5 attempts per token per hour, as per the spec.
# NOTE: in-memory; production should swap this for ValkeyRateLimiter when a
# Valkey client is available (see services/member_service.py).
invite_rate_limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=3600)
